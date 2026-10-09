"""Ask Shepherd: a leader asks in their own words; Shepherd answers from the record.

Rule 2: the model only says what was asked (an intent, a name as written, a date).
Code finds the facts and writes every answer, so nothing can drift from the record.
Rule 5: answers cover the leader's own ministry and team; questions about health,
family or personal reasons are refused before the model sees them. Asking never
writes to the record, and drafts are returned for the leader to copy: Shepherd
neither stores nor sends them. Nothing of the conversation is kept.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Blockout,
    Church,
    Finding,
    Gathering,
    GatheringType,
    Membership,
    MemoryItem,
    Ministry,
    Person,
    Preference,
    Role,
    RoleSkill,
)
from app.domain.ask import ParsedQuestion
from app.domain.enums import AskIntent, AssignmentStatus, Experience, FindingType, MembershipStatus
from app.domain.schemas import (
    AskAction,
    AskAnswer,
    AskDraft,
    AskIn,
    AskPerson,
    AskStart,
    RosterGathering,
)
from app.llm.client import LLMClient
from app.llm.prompts.ask import PARSE
from app.services.briefing import briefing, church_today, roster
from app.services.huddle_replacement import EXPERIENCE_RANK, free_candidates, unavailable_on
from app.services.memory import is_leader, pending_memory_proposals, private_reason
from app.services.profile import format_time

LOOKAHEAD_DAYS = 28
MAX_PEOPLE = 6

# "Why is Emily away?" asks for a personal reason even without a sensitive word.
_WHY_AWAY = re.compile(
    r"\bwhy\b.*\b(away|off|absent|missing|gone|out|leav\w*|quit\w*|stopp\w*|"
    r"not (serving|coming|here)|skipp\w*|miss\w*)\b|\btime off\b",
    re.IGNORECASE,
)

# Small talk is answered in code, without the model.
_GREETING = re.compile(
    r"^\s*(hi|hello|hey|hiya|howdy|good (morning|afternoon|evening))"
    r",?( there| shepherd)?[\s!.,]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(
    r"^\s*(thanks?( you)?|thank you( so much| very much)?|thx|ty|cheers|great|ok(ay)?|perfect)"
    r",?( shepherd)?[\s!.,]*$",
    re.IGNORECASE,
)

NEEDS_PERSON = {
    AskIntent.REPLACE,
    AskIntent.DRAFT_MESSAGE,
    AskIntent.REMEMBER,
    AskIntent.AVAILABILITY,
}


class AskNotAllowed(PermissionError):
    pass


class AskNotFound(LookupError):
    pass


@dataclass
class TeamMember:
    person_id: uuid.UUID
    name: str
    nicknames: list[str]
    experience: Experience | None = None
    role_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def first(self) -> str:
        return self.name.split(" ")[0]


@dataclass
class Context:
    session: Session
    church_id: uuid.UUID
    ministry: Ministry
    leader: Person
    tz: ZoneInfo
    today: date
    team: dict[uuid.UUID, TeamMember]

    @property
    def leader_first(self) -> str:
        return self.leader.name.split(" ")[0]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def ask_start(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    person_id: uuid.UUID,
    today: date | None = None,
) -> AskStart:
    ctx = _context(session, church_id, ministry_id, person_id, today)
    return AskStart(
        ministry=ctx.ministry.name,
        greeting=f"Hi {ctx.leader_first}. What can I help with?",
        suggestions=_suggestions(ctx),
    )


def ask(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    body: AskIn,
    llm: LLMClient | None,
    today: date | None = None,
) -> AskAnswer:
    ctx = _context(session, church_id, ministry_id, body.person_id, today)
    if body.intent is not None:
        return _answer(ctx, body.intent, body.about_person_id, body.on, body.role_id)

    question = (body.question or "").strip()
    if private_reason(question) or _WHY_AWAY.search(question):
        named = _named_in(ctx, question)
        return _private(ctx, named[0] if len(named) == 1 else None)
    if _GREETING.match(question):
        return AskAnswer(
            intent=AskIntent.UNKNOWN,
            text=f"Hi {ctx.leader_first}! Ask me in your own words, or start with one of these.",
            actions=_suggestions(ctx),
        )
    if _THANKS.match(question):
        return AskAnswer(
            intent=AskIntent.UNKNOWN,
            text="You're welcome. Anything else?",
            actions=_suggestions(ctx),
        )
    if llm is None:
        return AskAnswer(
            intent=AskIntent.UNKNOWN,
            text="I can only answer the suggested questions right now. Typed questions need "
            "the language model, which isn't set up here.",
            actions=_suggestions(ctx),
        )

    parsed = llm.complete(system=PARSE, user=_facts(ctx, question), schema=ParsedQuestion)
    on = _parse_date(parsed.date)
    person: TeamMember | None = None
    if parsed.person:
        matches = _match(ctx, parsed.person)
        if parsed.intent is AskIntent.PRIVATE:
            return _private(ctx, matches[0] if len(matches) == 1 else None)
        if not matches:
            return AskAnswer(
                intent=parsed.intent,
                text=f"I couldn't find {parsed.person} on the {ctx.ministry.name} team.",
                notes=["I can only look up people on your own team."],
            )
        if len(matches) > 1:
            return AskAnswer(
                intent=parsed.intent,
                text=f"Which {parsed.person} do you mean?",
                actions=[
                    AskAction(
                        label=m.name,
                        kind="ask",
                        intent=parsed.intent,
                        about_person_id=m.person_id,
                        on=on,
                    )
                    for m in matches
                ],
            )
        person = matches[0]
    return _answer(ctx, parsed.intent, person.person_id if person else None, on, None)


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def _answer(
    ctx: Context,
    intent: AskIntent,
    about: uuid.UUID | None,
    on: date | None,
    role_id: uuid.UUID | None,
) -> AskAnswer:
    person = ctx.team.get(about) if about else None
    if about and person is None:
        return AskAnswer(
            intent=intent,
            text=f"That person isn't on the {ctx.ministry.name} team.",
            notes=["I can only look up people on your own team."],
        )
    if intent in NEEDS_PERSON and person is None:
        return AskAnswer(
            intent=intent,
            text="Who do you mean? Ask again with their name.",
        )
    if intent is AskIntent.NEEDS_ME:
        return _needs_me(ctx)
    if intent is AskIntent.FREE_ON:
        return _free_on(ctx, on)
    if intent is AskIntent.SERVING_A_LOT:
        return _serving_a_lot(ctx)
    if intent is AskIntent.DRAFT_REMINDER:
        return _draft_reminder(ctx, on)
    if intent is AskIntent.PRIVATE:
        return _private(ctx, person)
    if person is not None:
        if intent is AskIntent.REPLACE:
            return _replace(ctx, person, on)
        if intent is AskIntent.DRAFT_MESSAGE:
            return _draft_message(ctx, person, on, role_id)
        if intent is AskIntent.REMEMBER:
            return _remember(ctx, person)
        if intent is AskIntent.AVAILABILITY:
            return _availability(ctx, person)
    return AskAnswer(
        intent=AskIntent.UNKNOWN,
        text="I can't answer that yet. Here's what I can help with.",
        actions=_suggestions(ctx),
    )


def _needs_me(ctx: Context) -> AskAnswer:
    brief = briefing(ctx.session, ctx.church_id, ctx.leader.id, ctx.today)
    items = [i for i in brief.items if ctx.ministry.name in i.ministries]
    looked_at = [f"This week's checks for {ctx.ministry.name}", "Rosters across all ministries"]
    if not items:
        return AskAnswer(
            intent=AskIntent.NEEDS_ME,
            text=f"Nothing needs you this week. Every check came back clear for {ctx.ministry.name}.",
            source="From this week's checks",
            looked_at=looked_at,
        )
    actions: list[AskAction] = []
    for item in items:
        if item.type is not FindingType.OVERLAP:
            continue
        for member in (m for m in ctx.team.values() if m.name in item.people):
            actions.append(
                AskAction(
                    label=f"Who can take {member.first}'s place?",
                    kind="ask",
                    intent=AskIntent.REPLACE,
                    about_person_id=member.person_id,
                    on=item.on,
                )
            )
        if item.can_huddle:
            actions.append(
                AskAction(label="Open the huddle", kind="link", href=f"/huddle/{item.finding_id}")
            )
    n = len(items)
    return AskAnswer(
        intent=AskIntent.NEEDS_ME,
        text=f"{n} {'thing needs' if n == 1 else 'things need'} you this week.",
        notes=[i.text for i in items],
        actions=actions,
        source="From this week's checks",
        looked_at=looked_at,
    )


def _free_on(ctx: Context, on: date | None) -> AskAnswer:
    day = on or _next_day(ctx)
    if day is None:
        return _nothing_scheduled(ctx, AskIntent.FREE_ON)
    gatherings = _gatherings_on(ctx, day)
    if not gatherings:
        return AskAnswer(
            intent=AskIntent.FREE_ON,
            text=f"{ctx.ministry.name} has nothing on {_day(day)}.",
            source=f"From the {ctx.ministry.name} calendar",
        )
    ids = [p for p in ctx.team if p != ctx.leader.id]  # never suggest the leader asking
    blocked = _blocked_on(ctx, ids, day)
    free_for: dict[uuid.UUID, list[str]] = defaultdict(list)
    for g in gatherings:
        busy = _busy(ctx, ids, g.start_at, g.end_at)
        for person_id in ids:
            if person_id not in busy and person_id not in blocked:
                free_for[person_id].append(g.name)
    free = sorted(
        (ctx.team[p] for p in free_for),
        key=lambda m: (_rank(m.experience), m.name),
    )
    shown = free[:MAX_PEOPLE]
    notes = []
    if len(free) > len(shown):
        notes.append(f"{len(free) - len(shown)} more on your team are free too.")
    if left_out := sorted(ctx.team[p].first for p in blocked):
        notes.append(f"{_and(left_out)} can't make {_day(day)}, so I left them out.")
    n = len(free)
    return AskAnswer(
        intent=AskIntent.FREE_ON,
        text=(
            f"Nobody on your team is free on {_day(day)}."
            if n == 0
            else f"{_count(n, 'person', 'people')} on your team {'is' if n == 1 else 'are'} "
            f"free on {_day(day)}."
        ),
        people=[
            AskPerson(
                person_id=m.person_id,
                name=m.name,
                experience=m.experience,
                detail=(
                    "Free all day"
                    if len(gatherings) > 1 and len(free_for[m.person_id]) == len(gatherings)
                    else f"Free for the {_and(free_for[m.person_id])}"
                ),
            )
            for m in shown
        ],
        notes=notes,
        source=f"From the {_short(day)} roster and availability",
        looked_at=[f"{_short(day)} rosters, all ministries", "Availability for your team"],
    )


def _replace(ctx: Context, person: TeamMember, on: date | None) -> AskAnswer:
    place = _next_assignment(ctx, person.person_id, on)
    if place is None:
        when = f" on {_day(on)}" if on else " in the next 4 weeks"
        return AskAnswer(
            intent=AskIntent.REPLACE,
            text=f"{person.first} isn't on the {ctx.ministry.name} roster{when}.",
            source=f"From the {ctx.ministry.name} roster",
        )
    assignment, gathering, role, gathering_name = place
    start, end = gathering.start_at, gathering.end_at
    day = start.astimezone(ctx.tz).date()
    candidates = free_candidates(
        ctx.session, ctx.church_id, ctx.ministry.id, role.id, person.person_id, start, end
    )
    in_role = [m.person_id for m in ctx.team.values() if role.id in m.role_ids]
    blocked = sorted(
        ctx.team[p].first for p in _blocked_on(ctx, in_role, day) if p != person.person_id
    )
    notes = []
    if blocked:
        notes.append(f"{_and(blocked)} can't make {_short(day)}, so I left them out.")
    actions: list[AskAction] = []
    if candidates:
        best = candidates[0]
        notes.append(f"{best.name.split(' ')[0]} is the closest fit for {role.name}.")
        actions.append(
            AskAction(
                label=f"Draft a message to {best.name.split(' ')[0]}",
                kind="ask",
                intent=AskIntent.DRAFT_MESSAGE,
                about_person_id=best.person_id,
                on=day,
                role_id=role.id,
            )
        )
    if finding_id := _open_overlap(ctx, assignment.id):
        actions.append(
            AskAction(label="Open the huddle", kind="link", href=f"/huddle/{finding_id}")
        )
    n = len(candidates)
    where = f"the {gathering_name} on {_short(day)}"
    return AskAnswer(
        intent=AskIntent.REPLACE,
        text=(
            f"Nobody else on your team who serves as {role.name} is free for {where}."
            if n == 0
            else f"{_count(n, 'person', 'people')} on your team {'is' if n == 1 else 'are'} "
            f"free for {where}."
        ),
        people=[
            AskPerson(
                person_id=c.person_id,
                name=c.name,
                experience=c.experience,
                detail="Free at that time",
            )
            for c in candidates[:MAX_PEOPLE]
        ],
        notes=notes,
        actions=actions,
        source=f"From the {_short(day)} roster and availability",
        looked_at=[f"{_short(day)} rosters, all ministries", f"Availability for your {role.name}s"],
    )


def _serving_a_lot(ctx: Context) -> AskAnswer:
    ids = list(ctx.team)
    start = datetime.combine(ctx.today, time(0), tzinfo=ctx.tz)
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for person_id in ctx.session.scalars(
        select(Assignment.person_id)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .where(
            Assignment.church_id == ctx.church_id,
            Assignment.person_id.in_(ids),
            Assignment.status != AssignmentStatus.DECLINED,
            Gathering.start_at >= start,
            Gathering.start_at < start + timedelta(days=7),
        )
    ):
        counts[person_id] += 1
    preferences = {
        p.person_id: p
        for p in ctx.session.scalars(
            select(Preference).where(
                Preference.church_id == ctx.church_id, Preference.person_id.in_(ids)
            )
        )
    }
    busy = sorted(
        (p for p, n in counts.items() if n >= 2),
        key=lambda p: (-counts[p], ctx.team[p].name),
    )
    looked_at = ["This week's rosters, all ministries", "Your team's stated preferences"]
    if not busy:
        return AskAnswer(
            intent=AskIntent.SERVING_A_LOT,
            text=f"Nobody on {ctx.ministry.name} serves more than once this week.",
            source="From this week's rosters across all ministries",
            looked_at=looked_at,
        )
    people, notes = [], []
    for person_id in busy:
        member, n = ctx.team[person_id], counts[person_id]
        detail = f"{n} times this week"
        pref = preferences.get(person_id)
        if pref and pref.preferred_frequency and pref.preferred_frequency_period:
            wish = f"{pref.preferred_frequency} a {pref.preferred_frequency_period.value}"
            detail += f" · prefers {wish}"
            if pref.preferred_frequency_period.value == "week" and n > pref.preferred_frequency:
                notes.append(f"That's above {member.first}'s preferred {wish}.")
        people.append(
            AskPerson(
                person_id=person_id, name=member.name, experience=member.experience, detail=detail
            )
        )
    n = len(busy)
    return AskAnswer(
        intent=AskIntent.SERVING_A_LOT,
        text=f"{_count(n, 'person', 'people')} on your team "
        f"{'serves' if n == 1 else 'serve'} more than once this week.",
        people=people[:MAX_PEOPLE],
        notes=notes,
        actions=[AskAction(label="Open rosters", kind="link", href="/rosters")],
        source="From this week's rosters across all ministries",
        looked_at=looked_at,
    )


def _draft_reminder(ctx: Context, on: date | None) -> AskAnswer:
    day = on or _next_day(ctx)
    if day is None:
        return _nothing_scheduled(ctx, AskIntent.DRAFT_REMINDER)
    drafts = []
    for g in _gatherings_on(ctx, day):
        local = g.start_at.astimezone(ctx.tz)
        for role in g.roles:
            for p in role.people:
                if p.status is AssignmentStatus.DECLINED or p.person_id == ctx.leader.id:
                    continue
                drafts.append(
                    AskDraft(
                        to_person_id=p.person_id,
                        to=p.name,
                        body=(
                            f"Hi {p.name.split(' ')[0]}, a friendly reminder that you're serving "
                            f"as {role.role} with {ctx.ministry.name} on {_day(day)} at "
                            f"{format_time(local.time())}. Reply here if anything changes. "
                            f"Thank you, {ctx.leader_first}"
                        ),
                    )
                )
    source = f"From your {ctx.ministry.name} roster for {_short(day)}"
    if not drafts:
        return AskAnswer(
            intent=AskIntent.DRAFT_REMINDER,
            text=f"Nobody is on the {ctx.ministry.name} roster for {_day(day)} yet.",
            source=source,
        )
    n = len(drafts)
    return AskAnswer(
        intent=AskIntent.DRAFT_REMINDER,
        text=f"Here {'is a reminder' if n == 1 else f'are {n} reminders'} for {_day(day)} "
        "for you to look over.",
        drafts=drafts,
        source=source,
        looked_at=[f"{_short(day)} {ctx.ministry.name} roster"],
    )


def _draft_message(
    ctx: Context, person: TeamMember, on: date | None, role_id: uuid.UUID | None
) -> AskAnswer:
    day = on or _next_day(ctx)
    gatherings = _gatherings_on(ctx, day) if day else []
    if day is None or not gatherings:
        return _nothing_scheduled(ctx, AskIntent.DRAFT_MESSAGE)
    gathering = next(
        (g for g in gatherings if any(r.role_id == role_id for r in g.roles)), gatherings[0]
    )
    role = next((r.role for r in gathering.roles if r.role_id == role_id), None)
    local = gathering.start_at.astimezone(ctx.tz)
    as_role = f" as {role}" if role else ""
    body = (
        f"Hi {person.first}, could you serve{as_role} with {ctx.ministry.name} on {_day(day)} "
        f"at {format_time(local.time())}? Let me know either way. Thanks, {ctx.leader_first}"
    )
    notes = []
    if person.person_id in _blocked_on(ctx, [person.person_id], day):
        notes.append(f"{person.first} can't make {_short(day)}.")
    return AskAnswer(
        intent=AskIntent.DRAFT_MESSAGE,
        text="Here is a short draft for you to look over.",
        drafts=[AskDraft(to_person_id=person.person_id, to=person.name, body=body)],
        notes=notes,
        source=f"From your {ctx.ministry.name} roster and {person.first}'s availability",
        looked_at=[f"{_short(day)} {ctx.ministry.name} roster", f"{person.first}'s blockout dates"],
    )


def _remember(ctx: Context, person: TeamMember) -> AskAnswer:
    items = [
        m
        for m in ctx.session.scalars(
            select(MemoryItem)
            .where(MemoryItem.church_id == ctx.church_id, MemoryItem.ministry_id == ctx.ministry.id)
            .order_by(MemoryItem.created_at)
        )
        if m.about_person_id == person.person_id
        or re.search(rf"\b{re.escape(person.first)}\b", m.text)
    ]
    pending = [
        p.payload["text"]
        for p in pending_memory_proposals(ctx.session, ctx.church_id, ctx.ministry.id)
        if p.payload.get("about_person_id") == str(person.person_id)
    ]
    notes = [m.text for m in items]
    notes += [f"Waiting for you to confirm: “{text}”" for text in pending]
    return AskAnswer(
        intent=AskIntent.REMEMBER,
        text=(
            f"Here's what I remember about {person.first}."
            if items
            else f"I don't remember anything about {person.first} yet."
        ),
        notes=notes,
        actions=[AskAction(label="Open Memory", kind="link", href="/memory")],
        source=f"From {ctx.ministry.name} memory, only what you confirmed",
        looked_at=[f"{ctx.ministry.name} memory"],
    )


def _availability(ctx: Context, person: TeamMember) -> AskAnswer:
    end = ctx.today + timedelta(days=LOOKAHEAD_DAYS)
    blockouts = ctx.session.scalars(
        select(Blockout)
        .where(
            Blockout.church_id == ctx.church_id,
            Blockout.person_id == person.person_id,
            Blockout.end_date >= ctx.today,
            Blockout.start_date < end,
        )
        .order_by(Blockout.start_date)
    ).all()
    ranges = [
        _short(b.start_date)
        if b.start_date == b.end_date
        else f"{_short(b.start_date)} to {_short(b.end_date)}"
        for b in blockouts
    ]
    return AskAnswer(
        intent=AskIntent.AVAILABILITY,
        text=(
            f"{person.first} is blocked out {_and(ranges)}."
            if ranges
            else f"{person.first} has no blocked-out dates in the next 4 weeks."
        ),
        notes=["I only keep the dates, never the reasons."],
        source=f"From {person.first}'s blockout dates",
        looked_at=[f"{person.first}'s blockout dates"],
    )


def _private(ctx: Context, person: TeamMember | None) -> AskAnswer:
    if person is None:
        return AskAnswer(
            intent=AskIntent.PRIVATE,
            text="I don't keep health, family or personal reasons, so I can't answer that.",
            notes=["I can show who is free, who is serving and what's on the roster."],
            refused=True,
        )
    return AskAnswer(
        intent=AskIntent.PRIVATE,
        text=f"I don't keep personal reasons, so I can't answer that. That's {person.first}'s "
        "to share.",
        notes=[f"I can show whether {person.first} is free on the dates that matter."],
        actions=[
            AskAction(
                label=f"Check {person.first}'s availability",
                kind="ask",
                intent=AskIntent.AVAILABILITY,
                about_person_id=person.person_id,
            )
        ],
        refused=True,
    )


def _nothing_scheduled(ctx: Context, intent: AskIntent) -> AskAnswer:
    return AskAnswer(
        intent=intent,
        text=f"{ctx.ministry.name} has nothing scheduled in the next 4 weeks.",
        source=f"From the {ctx.ministry.name} calendar",
    )


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


def _suggestions(ctx: Context) -> list[AskAction]:
    suggestions = [
        AskAction(label="What needs me this week?", kind="ask", intent=AskIntent.NEEDS_ME)
    ]
    brief = briefing(ctx.session, ctx.church_id, ctx.leader.id, ctx.today)
    clash = next(
        (
            (member, item.on)
            for item in brief.items
            if item.type is FindingType.OVERLAP and ctx.ministry.name in item.ministries
            for member in ctx.team.values()
            if member.name in item.people
        ),
        None,
    )
    if clash:
        member, on = clash
        suggestions.append(
            AskAction(
                label=f"Who can take {member.first}'s place on {_short(on)}?",
                kind="ask",
                intent=AskIntent.REPLACE,
                about_person_id=member.person_id,
                on=on,
            )
        )
    day = _next_day(ctx)
    if day:
        suggestions.append(
            AskAction(
                label=f"Who is free on {_short(day)}?", kind="ask", intent=AskIntent.FREE_ON, on=day
            )
        )
    suggestions.append(
        AskAction(
            label="Who is serving a lot right now?", kind="ask", intent=AskIntent.SERVING_A_LOT
        )
    )
    if day:
        suggestions.append(
            AskAction(
                label=f"Draft a reminder for {_short(day)}",
                kind="ask",
                intent=AskIntent.DRAFT_REMINDER,
                on=day,
            )
        )
    remembered: dict[uuid.UUID, int] = defaultdict(int)
    for about in ctx.session.scalars(
        select(MemoryItem.about_person_id).where(
            MemoryItem.church_id == ctx.church_id,
            MemoryItem.ministry_id == ctx.ministry.id,
            MemoryItem.about_person_id.is_not(None),
        )
    ):
        if about in ctx.team:
            remembered[about] += 1
    if remembered:
        top = max(remembered, key=lambda p: (remembered[p], ctx.team[p].name))
        suggestions.append(
            AskAction(
                label=f"What do you remember about {ctx.team[top].first}?",
                kind="ask",
                intent=AskIntent.REMEMBER,
                about_person_id=top,
            )
        )
    return suggestions


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


def _context(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    person_id: uuid.UUID,
    today: date | None,
) -> Context:
    ministry = session.scalar(
        select(Ministry).where(Ministry.church_id == church_id, Ministry.id == ministry_id)
    )
    if ministry is None:
        raise AskNotFound("ministry not found")
    if not is_leader(session, church_id, ministry_id, person_id):
        raise AskNotAllowed("only this ministry's leaders can ask about it")
    leader = session.get_one(Person, person_id)
    church = session.get_one(Church, church_id)
    return Context(
        session=session,
        church_id=church_id,
        ministry=ministry,
        leader=leader,
        tz=ZoneInfo(church.timezone),
        today=today or church_today(session, church_id),
        team=_team(session, church_id, ministry_id),
    )


def _team(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID
) -> dict[uuid.UUID, TeamMember]:
    team: dict[uuid.UUID, TeamMember] = {}
    for person, role_id, experience in session.execute(
        select(Person, RoleSkill.role_id, RoleSkill.experience)
        .join(Membership, Membership.person_id == Person.id)
        .outerjoin(RoleSkill, RoleSkill.membership_id == Membership.id)
        .where(
            Membership.church_id == church_id,
            Membership.ministry_id == ministry_id,
            Membership.status == MembershipStatus.ACTIVE,
            Person.stopped.is_(False),
        )
    ):
        member = team.setdefault(
            person.id, TeamMember(person.id, person.name, list(person.nicknames))
        )
        if role_id is not None:
            member.role_ids.add(role_id)
        if experience is not None and _rank(experience) < _rank(member.experience):
            member.experience = experience
    return team


def _match(ctx: Context, written: str) -> list[TeamMember]:
    """Team members a name as written could mean. Several means ask; none means not found."""
    q = written.strip().rstrip(".").casefold()
    if not q:
        return []
    exact = [
        m
        for m in ctx.team.values()
        if q == m.name.casefold() or q in (n.rstrip(".").casefold() for n in m.nicknames)
    ]
    if exact:
        return exact
    return sorted(
        (
            m
            for m in ctx.team.values()
            if q == m.first.casefold()
            or m.name.casefold().startswith(q + " ")
            or (len(q) > 2 and m.name.casefold().startswith(q))
        ),
        key=lambda m: m.name,
    )


def _named_in(ctx: Context, text: str) -> list[TeamMember]:
    """Team members whose full or first name appears in the text (no model needed)."""
    full = [m for m in ctx.team.values() if re.search(rf"\b{re.escape(m.name)}\b", text, re.I)]
    if full:
        return full
    return [m for m in ctx.team.values() if re.search(rf"\b{re.escape(m.first)}\b", text, re.I)]


def _gatherings_on(ctx: Context, day: date) -> list[RosterGathering]:
    out = roster(ctx.session, ctx.church_id, ctx.ministry.id, day, day + timedelta(days=1))
    return [g for g in out.gatherings if g.roles] if out else []


def _next_day(ctx: Context) -> date | None:
    out = roster(
        ctx.session,
        ctx.church_id,
        ctx.ministry.id,
        ctx.today,
        ctx.today + timedelta(days=LOOKAHEAD_DAYS),
    )
    days = [
        g.start_at.astimezone(ctx.tz).date() for g in (out.gatherings if out else []) if g.roles
    ]
    return min(days) if days else None


def _busy(ctx: Context, ids: list[uuid.UUID], start: datetime, end: datetime) -> set[uuid.UUID]:
    return set(
        ctx.session.scalars(
            select(Assignment.person_id)
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(
                Assignment.church_id == ctx.church_id,
                Assignment.person_id.in_(ids),
                Assignment.status != AssignmentStatus.DECLINED,
                Gathering.start_at < end,
                Gathering.end_at > start,
            )
        )
    )


def _blocked_on(ctx: Context, ids: list[uuid.UUID], day: date) -> set[uuid.UUID]:
    """Blocked out that day, or declined a place that day."""
    return unavailable_on(ctx.session, ctx.church_id, ids, day, ctx.tz)


def _next_assignment(
    ctx: Context, person_id: uuid.UUID, on: date | None
) -> tuple[Assignment, Gathering, Role, str] | None:
    start = datetime.combine(on or ctx.today, time(0), tzinfo=ctx.tz)
    end = start + timedelta(days=1 if on else LOOKAHEAD_DAYS)
    row = ctx.session.execute(
        select(Assignment, Gathering, Role, GatheringType.name)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .join(GatheringType, GatheringType.id == Gathering.gathering_type_id)
        .join(Role, Role.id == Assignment.role_id)
        .where(
            Assignment.church_id == ctx.church_id,
            Assignment.ministry_id == ctx.ministry.id,
            Assignment.person_id == person_id,
            Assignment.status != AssignmentStatus.DECLINED,
            Gathering.start_at >= start,
            Gathering.start_at < end,
        )
        .order_by(Gathering.start_at)
        .limit(1)
    ).first()
    return (row[0], row[1], row[2], row[3]) if row else None


def _open_overlap(ctx: Context, assignment_id: uuid.UUID) -> uuid.UUID | None:
    brief = briefing(ctx.session, ctx.church_id, ctx.leader.id, ctx.today)
    for item in brief.items:
        if item.type is not FindingType.OVERLAP or not item.can_huddle:
            continue
        finding = ctx.session.get_one(Finding, item.finding_id)
        if str(assignment_id) in finding.details.get("assignment_ids", []):
            return item.finding_id
    return None


def _facts(ctx: Context, question: str) -> str:
    out = roster(
        ctx.session,
        ctx.church_id,
        ctx.ministry.id,
        ctx.today,
        ctx.today + timedelta(days=LOOKAHEAD_DAYS),
    )
    days = sorted(
        {g.start_at.astimezone(ctx.tz).date() for g in (out.gatherings if out else []) if g.roles}
    )
    upcoming = ", ".join(f"{d:%A} {d.isoformat()}" for d in days[:8]) or "none"
    return (
        f"Today: {ctx.today:%A} {ctx.today.isoformat()}\n"
        f"Ministry: {ctx.ministry.name}\n"
        f"Upcoming {ctx.ministry.name} dates: {upcoming}\n\n"
        f"Question: {question}"
    )


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _rank(experience: Experience | None) -> int:
    return EXPERIENCE_RANK[experience] if experience else len(EXPERIENCE_RANK)


def _day(d: date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


def _short(d: date) -> str:
    return f"{d:%b} {d.day}"


def _count(n: int, one: str, many: str) -> str:
    return f"{'One' if n == 1 else n} {one if n == 1 else many}"


def _and(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"
