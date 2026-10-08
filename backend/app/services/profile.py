"""Deterministic onboarding logic (architecture rule 2). Pure: no I/O, no model calls.

The language model turns the admin's words into a `*Reply`; everything that
decides what is true lives here: merging a reply into the draft, validating it,
choosing the next question, inferring a profile from a sample schedule, and
rendering the plain-language summary the admin approves.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from app.domain.enums import (
    FindingType,
    GatheringKind,
    OnboardingTopic,
    Recurrence,
    Weekday,
)
from app.domain.profile import (
    AvailabilityReply,
    BasicsReply,
    ChurchProfileDraft,
    DraftAvailability,
    DraftGathering,
    DraftLeader,
    DraftLoadRule,
    DraftMinistry,
    DraftRole,
    DraftRoleMinimum,
    GatheringsReply,
    LeadersReply,
    LoadRulesReply,
    MinistriesReply,
    ReplyBase,
    ReviewReply,
    RolesReply,
    RosterSettingsReply,
    RoutingReply,
    SampleReply,
)

T = OnboardingTopic
TOPIC_ORDER: list[OnboardingTopic] = list(OnboardingTopic)
SAMPLE_DEFAULT_DURATION = 90


class ProfileProblem(ValueError):
    """An admin answer that can't be applied, explained in plain language."""


@dataclass
class TurnResult:
    draft: ChurchProfileDraft
    problems: list[str] = field(default_factory=list)
    clarifying_question: str | None = None
    ready_to_propose: bool = False


# ---------------------------------------------------------------------------
# Topic flow
# ---------------------------------------------------------------------------


def next_topic(draft: ChurchProfileDraft) -> OnboardingTopic:
    """The first topic the admin hasn't confirmed; review once all are."""
    for topic in TOPIC_ORDER:
        if topic is not T.REVIEW and topic not in draft.confirmed:
            return topic
    return T.REVIEW


def apply_reply(draft: ChurchProfileDraft, topic: OnboardingTopic, reply: ReplyBase) -> TurnResult:
    """Merge one model reply for `topic` into a copy of `draft`."""
    if reply.clarifying_question:
        return TurnResult(draft, clarifying_question=reply.clarifying_question)

    if isinstance(reply, ReviewReply):
        return _apply_review(draft, reply)

    updated = draft.model_copy(deep=True)
    try:
        _merge_section(updated, topic, reply)
    except (ProfileProblem, ValidationError) as error:
        return TurnResult(draft, problems=_messages(error))

    problems = validate_topic(updated, topic)
    if reply.topic_done and not problems:
        _confirm(updated, topic)
    elif topic in updated.confirmed:
        # The admin changed a confirmed section without saying it's done: re-confirm.
        updated.confirmed.remove(topic)
    _drop_broken_confirmations(updated)
    return TurnResult(updated, problems=problems if reply.topic_done else [])


def _apply_review(draft: ChurchProfileDraft, reply: ReviewReply) -> TurnResult:
    if reply.change_topic and reply.change_topic is not T.REVIEW:
        updated = draft.model_copy(deep=True)
        if reply.change_topic in updated.confirmed:
            updated.confirmed.remove(reply.change_topic)
        return TurnResult(updated)
    if not reply.topic_done:
        return TurnResult(draft)
    problems = proposal_blockers(draft)
    return TurnResult(draft, problems=problems, ready_to_propose=not problems)


def proposal_blockers(draft: ChurchProfileDraft) -> list[str]:
    """Why the draft can't be proposed yet; empty when it can."""
    problems = [
        f"The {_label(t)} section isn't confirmed yet."
        for t in TOPIC_ORDER
        if t is not T.REVIEW and t not in draft.confirmed
    ]
    for topic in TOPIC_ORDER:
        problems += validate_topic(draft, topic)
    problems += [
        f"Please confirm {name} (it came from the sample schedule)."
        for name in inferred_items(draft)
    ]
    return problems


def inferred_items(draft: ChurchProfileDraft) -> list[str]:
    items = [f"the gathering “{g.name}”" for g in draft.gatherings if g.inferred]
    for m in draft.ministries:
        if m.inferred:
            items.append(f"the {m.name} ministry")
        items += [f"the {m.name} role “{r.name}”" for r in m.roles if r.inferred]
    return items


def _confirm(draft: ChurchProfileDraft, topic: OnboardingTopic) -> None:
    draft.confirmed.append(topic)
    # Confirming a section confirms what the admin was shown in it, inferred items included.
    if topic is T.GATHERINGS:
        for g in draft.gatherings:
            g.inferred = False
    elif topic is T.MINISTRIES:
        for m in draft.ministries:
            m.inferred = False
    elif topic is T.ROLES:
        for m in draft.ministries:
            for r in m.roles:
                r.inferred = False


def _drop_broken_confirmations(draft: ChurchProfileDraft) -> None:
    """A change upstream (e.g. renaming a gathering) can break a confirmed section."""
    draft.confirmed = [t for t in draft.confirmed if not validate_topic(draft, t)]


# ---------------------------------------------------------------------------
# Merging replies into the draft
# ---------------------------------------------------------------------------


def _merge_section(draft: ChurchProfileDraft, topic: OnboardingTopic, reply: ReplyBase) -> None:
    match reply:
        case BasicsReply():
            if reply.timezone:
                draft.timezone = reply.timezone
            if reply.language:
                draft.language = reply.language.lower()
        case GatheringsReply():
            draft.gatherings = _keep_inferred(
                [
                    _gathering(g.name, g.kind, g.weekday, g.date, g.start_time, g.duration_minutes)
                    for g in reply.gatherings
                ],
                draft.gatherings,
            )
        case MinistriesReply():
            existing = {_key(m.name): m for m in draft.ministries}
            ministries = []
            for m in reply.ministries:
                kept = existing.get(_key(m.name))
                base = kept.model_copy(deep=True) if kept else DraftMinistry(name=m.name)
                base.name, base.aliases = (
                    m.name.strip(),
                    [a.strip() for a in m.aliases if a.strip()],
                )
                ministries.append(base)
            draft.ministries = ministries
        case RolesReply():
            roles: dict[str, list[DraftRole]] = defaultdict(list)
            for r in reply.roles:
                owner = _ministry(draft, r.ministry)
                minimums = [
                    DraftRoleMinimum(
                        gathering=_gathering_name(draft, m.gathering), minimum=m.minimum
                    )
                    for m in r.minimums
                ]
                roles[owner.name].append(DraftRole(name=r.name.strip(), minimums=minimums))
            for each in draft.ministries:
                each.roles = _keep_inferred(roles.get(each.name, []), each.roles)
        case LeadersReply():
            leaders: dict[str, list[DraftLeader]] = defaultdict(list)
            for leader in reply.leaders:
                leaders[_ministry(draft, leader.ministry).name].append(
                    DraftLeader(
                        name=leader.name.strip(),
                        can_schedule=leader.can_schedule,
                        can_approve=leader.can_approve,
                    )
                )
            for each in draft.ministries:
                each.leaders = leaders.get(each.name, [])
        case LoadRulesReply():
            draft.load_rules = [
                DraftLoadRule.model_validate(r.model_dump()) for r in reply.load_rules
            ]
            draft.absence_threshold_weeks = reply.absence_threshold_weeks
        case RoutingReply():
            draft.routing = reply.routing
        case RosterSettingsReply():
            for setting in reply.settings:
                target = _ministry(draft, setting.ministry)
                updated = DraftMinistry.model_validate(
                    {**target.model_dump(), **setting.model_dump(exclude={"ministry"})}
                )
                draft.ministries[draft.ministries.index(target)] = updated
        case AvailabilityReply():
            leader_names = {_key(name): name for name in all_leaders(draft)}
            windows = []
            for a in reply.availability:
                name = leader_names.get(_key(a.leader))
                if name is None:
                    raise ProfileProblem(f"{a.leader} isn't one of the ministry leaders.")
                windows.append(
                    DraftAvailability(
                        leader=name,
                        weekday=a.weekday,
                        start=parse_time(a.start),
                        end=parse_time(a.end),
                    )
                )
            draft.availability = windows
        case _:
            raise ProfileProblem(f"Unexpected reply for {topic}")


def _gathering(
    name: str,
    kind: GatheringKind,
    weekday: Weekday | None,
    day: str | None,
    start: str,
    minutes: int,
) -> DraftGathering:
    one_off = parse_date(day) if day else None
    return DraftGathering(
        name=name.strip(),
        kind=kind,
        recurrence=Recurrence.ONE_OFF if one_off else Recurrence.WEEKLY,
        weekday=None if one_off else weekday,
        one_off_date=one_off,
        local_start_time=parse_time(start),
        duration_minutes=minutes,
    )


def _keep_inferred[I: (DraftGathering, DraftRole)](new: list[I], old: list[I]) -> list[I]:
    """Items the reply returns unchanged keep their 'inferred' flag until confirmed."""
    still_inferred = {_key(o.name): o for o in old if o.inferred}
    for item in new:
        previous = still_inferred.get(_key(item.name))
        if previous is not None and previous.model_dump(exclude={"inferred"}) == item.model_dump(
            exclude={"inferred"}
        ):
            item.inferred = True
    return new


def _ministry(draft: ChurchProfileDraft, name: str) -> DraftMinistry:
    wanted = _key(name)
    for m in draft.ministries:
        if wanted in {_key(m.name), *(_key(a) for a in m.aliases)}:
            return m
    raise ProfileProblem(f"I don't have a ministry called “{name}” yet.")


def _gathering_name(draft: ChurchProfileDraft, name: str) -> str:
    for g in draft.gatherings:
        if _key(g.name) == _key(name):
            return g.name
    raise ProfileProblem(f"I don't have a gathering called “{name}”.")


def all_leaders(draft: ChurchProfileDraft) -> list[str]:
    return list(dict.fromkeys(leader.name for m in draft.ministries for leader in m.leaders))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_topic(draft: ChurchProfileDraft, topic: OnboardingTopic) -> list[str]:
    problems: list[str] = []
    match topic:
        case T.BASICS:
            if not draft.timezone:
                problems.append("I still need the church's time zone.")
            elif not is_valid_timezone(draft.timezone):
                problems.append(f"“{draft.timezone}” isn't a time zone I recognise.")
        case T.GATHERINGS:
            if not draft.gatherings:
                problems.append("Add at least one service, meeting or event.")
            problems += _duplicates("gathering", [g.name for g in draft.gatherings])
        case T.MINISTRIES:
            if not draft.ministries:
                problems.append("Add at least one ministry that needs a schedule.")
            problems += _duplicates("ministry", [m.name for m in draft.ministries])
        case T.ROLES:
            gatherings = {g.name for g in draft.gatherings}
            for m in draft.ministries:
                if not m.roles:
                    problems.append(f"{m.name} has no roles yet.")
                problems += _duplicates(f"{m.name} role", [r.name for r in m.roles])
                for r in m.roles:
                    problems += [
                        f"{m.name} / {r.name} refers to an unknown gathering “{x.gathering}”."
                        for x in r.minimums
                        if x.gathering not in gatherings
                    ]
        case T.LEADERS:
            for m in draft.ministries:
                if not any(leader.can_schedule for leader in m.leaders):
                    problems.append(f"Who schedules {m.name}?")
                if not any(leader.can_approve for leader in m.leaders):
                    problems.append(f"Who approves the {m.name} schedules?")
        case T.LOAD_RULES:
            problems += _duplicates("load rule period", [r.period for r in draft.load_rules])
        case T.ROUTING:
            routed = {r.finding for r in draft.routing if r.recipients}
            problems += [
                f"Who should hear about {_finding_label(f)}?"
                for f in FindingType
                if f not in routed
            ]
        case T.AVAILABILITY:
            leaders = set(all_leaders(draft))
            problems += [
                f"{a.leader} isn't one of the ministry leaders."
                for a in draft.availability
                if a.leader not in leaders
            ]
        case T.ROSTER_SETTINGS | T.REVIEW:
            pass
    return problems


def is_valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _duplicates(kind: str, names: list[str]) -> list[str]:
    counts = Counter(_key(n) for n in names)
    return [
        f"There are two of the {kind} “{n}”." for n in dict.fromkeys(names) if counts[_key(n)] > 1
    ]


# ---------------------------------------------------------------------------
# Sample schedules
# ---------------------------------------------------------------------------


def infer_from_sample(
    draft: ChurchProfileDraft, sample: SampleReply
) -> tuple[ChurchProfileDraft, list[str]]:
    """Fill gaps in the draft from a parsed sample schedule. Never overwrites.

    * A gathering seen on two or more dates, or in a sample spanning under two
      weeks, is weekly on that weekday and time; otherwise it's a one-off.
    * A role's minimum at a gathering is the most common head count seen there
      (the lower one on a tie).

    Everything added is marked inferred, and its section is unconfirmed, so the
    admin must look at it before the profile can be proposed. Returns the new
    draft and a plain-language list of what was added.
    """
    updated = draft.model_copy(deep=True)
    added: list[str] = []

    occurrences: dict[str, set[date | None]] = defaultdict(set)
    shape: dict[str, tuple[Weekday | None, time | None]] = {}
    labels: dict[str, str] = {}
    dated = [parse_date(s.date) for s in sample.slots if s.date]
    short_sample = not dated or (max(dated) - min(dated)) < timedelta(days=14)

    for slot in sample.slots:
        day = parse_date(slot.date) if slot.date else None
        weekday = slot.weekday or (Weekday(list(Weekday)[day.weekday()]) if day else None)
        start = parse_time(slot.start_time) if slot.start_time else None
        key = _slot_key(slot.gathering, weekday, start)
        occurrences[key].add(day)
        shape[key] = (weekday, start)
        labels[key] = (slot.gathering or "").strip() or _default_gathering_name(weekday, start)

    gathering_for_key: dict[str, str] = {}
    for key, days in occurrences.items():
        weekday, start = shape[key]
        existing = _find_gathering(updated, labels[key], weekday, start)
        if existing:
            gathering_for_key[key] = existing.name
            continue
        if start is None:
            continue  # can't place it in time; the admin's gathering answers will cover it
        real_days = sorted(d for d in days if d)
        weekly = short_sample or len(real_days) >= 2 or not real_days
        if weekly and weekday is None:
            continue
        gathering = DraftGathering(
            name=labels[key],
            recurrence=Recurrence.WEEKLY if weekly else Recurrence.ONE_OFF,
            weekday=weekday if weekly else None,
            one_off_date=None if weekly else real_days[0],
            local_start_time=start,
            duration_minutes=SAMPLE_DEFAULT_DURATION,
            inferred=True,
        )
        updated.gatherings.append(gathering)
        gathering_for_key[key] = gathering.name
        added.append(
            f"gathering “{gathering.name}” ({_when(gathering)}, about {SAMPLE_DEFAULT_DURATION} minutes)"
        )

    counts: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for slot in sample.slots:
        day = parse_date(slot.date) if slot.date else None
        weekday = slot.weekday or (Weekday(list(Weekday)[day.weekday()]) if day else None)
        start = parse_time(slot.start_time) if slot.start_time else None
        gathering_name = gathering_for_key.get(_slot_key(slot.gathering, weekday, start))
        if gathering_name is None:
            continue
        counts[(slot.ministry.strip(), slot.role.strip(), gathering_name)].append(slot.people_count)

    for (ministry_name, role_name, gathering_name), seen in counts.items():
        try:
            ministry = _ministry(updated, ministry_name)
        except ProfileProblem:
            ministry = DraftMinistry(name=ministry_name, inferred=True)
            updated.ministries.append(ministry)
            added.append(f"ministry “{ministry_name}”")
        role = next((r for r in ministry.roles if _key(r.name) == _key(role_name)), None)
        if role is None:
            role = DraftRole(name=role_name, inferred=True)
            ministry.roles.append(role)
            added.append(f"{ministry.name} role “{role_name}”")
        if not any(m.gathering == gathering_name for m in role.minimums):
            common = Counter(seen).most_common()
            top = common[0][1]
            minimum = min(count for count, freq in common if freq == top)
            role.minimums.append(DraftRoleMinimum(gathering=gathering_name, minimum=minimum))
            if not role.inferred:
                role.inferred = True
                added.append(f"{ministry.name} / {role.name}: {minimum} at {gathering_name}")

    touched = {
        T.GATHERINGS: any(g.inferred for g in updated.gatherings),
        T.MINISTRIES: any(m.inferred for m in updated.ministries),
        T.ROLES: any(r.inferred for m in updated.ministries for r in m.roles),
    }
    updated.confirmed = [t for t in updated.confirmed if not touched.get(t, False)]
    _drop_broken_confirmations(updated)
    return updated, added


def _slot_key(gathering: str | None, weekday: Weekday | None, start: time | None) -> str:
    if gathering and gathering.strip():
        return f"name:{_key(gathering)}"
    return f"at:{weekday}:{start}"


def _default_gathering_name(weekday: Weekday | None, start: time | None) -> str:
    day = weekday.value.capitalize() if weekday else "Gathering"
    return f"{day} {format_time(start)}" if start else day


def _find_gathering(
    draft: ChurchProfileDraft, label: str, weekday: Weekday | None, start: time | None
) -> DraftGathering | None:
    for g in draft.gatherings:
        if _key(g.name) == _key(label):
            return g
        if weekday and start and g.weekday is weekday and g.local_start_time == start:
            return g
    return None


# ---------------------------------------------------------------------------
# Plain-language rendering (deterministic, so it can't misstate the profile)
# ---------------------------------------------------------------------------

QUESTIONS: dict[OnboardingTopic, str] = {
    T.BASICS: "Let's set up your church. Where is the church (city or time zone), and what language should messages use?",
    T.GATHERINGS: (
        "Which services, meetings and events happen in a typical week, and when? Include any day of the week "
        "(e.g. a Wednesday prayer night), how long each lasts, and any one-off special events with their date. "
        "You can also paste a past schedule and I'll work out what I can from it."
    ),
    T.MINISTRIES: "Which ministries need a schedule, and what do people call them (any nicknames or other names)?",
    T.ROLES: "For each ministry, which roles do you fill, and how many people does each role need at each gathering?",
    T.LEADERS: "For each ministry, who makes the schedule and who approves it? It can be the same person or two people.",
    T.LOAD_RULES: (
        "How does your church think about serving often? For example 'weekly is normal, more than twice a week is "
        "too much' or 'no more than twice a month'. And after how many weeks without serving should the approver "
        "hear that someone has been away? These only ever produce warnings, never blocks."
    ),
    T.ROUTING: "Here's who I'd tell first about each kind of warning. Does that work, or would you change anyone?",
    T.ROSTER_SETTINGS: (
        "When I suggest rosters I can show two paths side by side (a training roster and a veteran roster), or "
        "just one. And how many weeks ahead should I draft for each ministry?"
    ),
    T.AVAILABILITY: (
        "When two leaders need to sort out a conflict I can find them a short time to talk. When is each leader "
        "usually free during the week? You can skip anyone."
    ),
    T.REVIEW: "Here's the whole profile. Does it look right? Nothing runs until you approve it.",
}


def question_for(topic: OnboardingTopic) -> str:
    return QUESTIONS[topic]


def render_section(draft: ChurchProfileDraft, topic: OnboardingTopic) -> str:
    match topic:
        case T.BASICS:
            return f"Time zone: {draft.timezone or 'not set'}. Language: {draft.language}."
        case T.GATHERINGS:
            return _lines([_gathering_line(g) for g in draft.gatherings], "No gatherings yet.")
        case T.MINISTRIES:
            return _lines(
                [
                    m.name
                    + (f" (also called {', '.join(m.aliases)})" if m.aliases else "")
                    + (" — from the sample, please confirm" if m.inferred else "")
                    for m in draft.ministries
                ],
                "No ministries yet.",
            )
        case T.ROLES:
            return _lines(
                [
                    f"{m.name}: " + ("; ".join(_role_line(r) for r in m.roles) or "no roles yet")
                    for m in draft.ministries
                ],
                "No ministries yet.",
            )
        case T.LEADERS:
            return _lines(
                [
                    f"{m.name}: " + ("; ".join(_leader_line(x) for x in m.leaders) or "nobody yet")
                    for m in draft.ministries
                ],
                "No ministries yet.",
            )
        case T.LOAD_RULES:
            rules = [
                f"Per {r.period}: up to {r.normal_max} is normal, "
                + (
                    f"{r.normal_max + 1} to {r.warning_above} is noted for the approver, "
                    if r.warning_above > r.normal_max
                    else ""
                )
                + f"more than {r.warning_above} is a warning."
                for r in draft.load_rules
            ]
            rules = rules or ["No serving-frequency rules (no load warnings)."]
            away = (
                f"After {draft.absence_threshold_weeks} weeks without serving, the approver hears about it."
                if draft.absence_threshold_weeks
                else "No absence reminder set."
            )
            return _lines([*rules, away], "")
        case T.ROUTING:
            return _lines(
                [
                    f"{_finding_label(r.finding).capitalize()}: {' and '.join(r.recipients)}"
                    for r in draft.routing
                ],
                "No routing yet.",
            )
        case T.ROSTER_SETTINGS:
            return _lines(
                [
                    f"{m.name}: "
                    + (
                        "both paths side by side"
                        if m.show_both_paths
                        else f"only the {m.default_path} path"
                    )
                    + f", drafted {m.draft_horizon_weeks} weeks ahead"
                    for m in draft.ministries
                ],
                "No ministries yet.",
            )
        case T.AVAILABILITY:
            return _lines(
                [
                    f"{a.leader}: {a.weekday.value.capitalize()} {format_time(a.start)} to {format_time(a.end)}"
                    for a in draft.availability
                ],
                "No availability windows (that's fine).",
            )
        case T.REVIEW:
            return render_summary(draft)


def render_summary(draft: ChurchProfileDraft) -> str:
    return "\n\n".join(
        f"{_label(topic).capitalize()}:\n{render_section(draft, topic)}"
        for topic in TOPIC_ORDER
        if topic is not T.REVIEW
    )


def _label(topic: OnboardingTopic) -> str:
    return {
        T.BASICS: "basics",
        T.LOAD_RULES: "serving frequency",
        T.ROUTING: "warnings",
        T.ROSTER_SETTINGS: "roster settings",
        T.AVAILABILITY: "leader availability",
    }.get(topic, topic.value)


def _finding_label(finding: FindingType) -> str:
    return {
        FindingType.OVERLAP: "someone booked at overlapping times",
        FindingType.BLOCKOUT: "someone scheduled on a date they're away",
        FindingType.BELOW_MINIMUM: "a role below its minimum",
        FindingType.LOAD: "someone serving more than usual",
        FindingType.ABSENT: "someone away for a while",
        FindingType.SILENT_MINISTRY: "a whole ministry sending nothing",
        FindingType.UNMATCHED_NAME: "a name I can't match",
    }[finding]


def _when(g: DraftGathering) -> str:
    if g.recurrence is Recurrence.WEEKLY and g.weekday:
        return f"every {g.weekday.value.capitalize()} at {format_time(g.local_start_time)}"
    assert g.one_off_date is not None
    return f"{g.one_off_date:%A %-d %B %Y} at {format_time(g.local_start_time)}"


def _gathering_line(g: DraftGathering) -> str:
    kind = "special" if g.kind is GatheringKind.SPECIAL else "regular"
    note = " — from the sample, please confirm" if g.inferred else ""
    return f"{g.name}: {_when(g)}, {g.duration_minutes} minutes, {kind}{note}"


def _role_line(r: DraftRole) -> str:
    needs = ", ".join(f"{m.minimum} at {m.gathering}" for m in r.minimums if m.minimum)
    return f"{r.name}" + (f" ({needs})" if needs else "") + (" [from sample]" if r.inferred else "")


def _leader_line(leader: DraftLeader) -> str:
    duties = " and ".join(
        d for d, on in (("schedules", leader.can_schedule), ("approves", leader.can_approve)) if on
    )
    return f"{leader.name} {duties}"


def _lines(lines: list[str], empty: str) -> str:
    return "\n".join(f"• {line}" for line in lines) if lines else empty


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def parse_time(value: str) -> time:
    match = _TIME.match(value)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ProfileProblem(f"“{value}” isn't a time I can read (use HH:MM).")
    return time(int(match[1]), int(match[2]))


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise ProfileProblem(f"“{value}” isn't a date I can read (use YYYY-MM-DD).") from error


def format_time(value: time) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def _key(name: str) -> str:
    return " ".join(name.casefold().split())


def _messages(error: Exception) -> list[str]:
    if isinstance(error, ValidationError):
        return [str(e["msg"]).removeprefix("Value error, ") for e in error.errors()]
    return [str(error)]
