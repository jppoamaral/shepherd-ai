"""Deterministic checks (brief §5; architecture rule 2). Pure: no I/O, no model.

* Overlap: one person in two assignments whose real times overlap, in any
  ministries, on any day of the week.
* Load: serving count per week or month against the church's load rules and
  the person's own preferred frequency. Warnings, never blocks (rule 8).
* Below minimum: a role short of its minimum at a gathering whose roster has
  been started (an untouched gathering isn't a gap yet, just not scheduled).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta

from app.domain.checks import AssignmentFact, Issue, LoadRuleFact, PreferenceFact, RoleNeed
from app.domain.enums import FindingType, Period
from app.services.profile import format_time

WARNING = "warning"
NOTED = "noted"


def overlaps(assignments: Sequence[AssignmentFact]) -> list[Issue]:
    by_person: dict[object, list[AssignmentFact]] = defaultdict(list)
    for a in assignments:
        by_person[a.person_id].append(a)

    issues: list[Issue] = []
    for items in by_person.values():
        items.sort(key=lambda a: (a.start, a.ministry_name, a.role_name))
        for i, first in enumerate(items):
            for second in items[i + 1 :]:
                if second.start >= first.end:
                    break  # sorted by start: nothing later can overlap `first`
                issues.append(_overlap_issue(first, second))
    return issues


def _overlap_issue(a: AssignmentFact, b: AssignmentFact) -> Issue:
    same_gathering = a.gathering_id == b.gathering_id
    day = f"{a.local_start:%a %-d %b}"
    if same_gathering:
        text = (
            f"{a.person_name} is booked twice at {a.gathering_name} ({day} {format_time(a.local_start.time())}): "
            f"{a.ministry_name} ({a.role_name}) and {b.ministry_name} ({b.role_name})."
        )
    else:
        text = (
            f"{a.person_name} is booked at overlapping times on {day}: "
            f"{_slot(a)} ({a.ministry_name}, {a.role_name}) and {_slot(b)} ({b.ministry_name}, {b.role_name})."
        )
    return Issue(
        type=FindingType.OVERLAP,
        key=f"overlap:{a.person_id}:{a.id}:{b.id}",
        severity=WARNING,
        text=text,
        gathering_id=a.gathering_id,
        person_ids=(a.person_id,),
        ministry_ids=tuple(dict.fromkeys((a.ministry_id, b.ministry_id))),
        on=a.local_start.date().isoformat(),
        details={
            "assignment_ids": [str(a.id), str(b.id)],
            "gathering_ids": list(dict.fromkeys((str(a.gathering_id), str(b.gathering_id)))),
            "sides": [_side(a), _side(b)],
            "overlap_start": max(a.start, b.start).isoformat(),
            "overlap_end": min(a.end, b.end).isoformat(),
        },
    )


def _side(a: AssignmentFact) -> dict[str, str]:
    return {
        "assignment_id": str(a.id),
        "ministry_id": str(a.ministry_id),
        "ministry": a.ministry_name,
        "role_id": str(a.role_id),
        "role": a.role_name,
        "gathering_id": str(a.gathering_id),
        "gathering": a.gathering_name,
        "start": a.local_start.isoformat(),
        "end": a.local_end.isoformat(),
    }


def _slot(a: AssignmentFact) -> str:
    return f"{a.gathering_name} {format_time(a.local_start.time())} to {format_time(a.local_end.time())}"


def load(
    assignments: Sequence[AssignmentFact],
    rules: Iterable[LoadRuleFact],
    preferences: dict[object, PreferenceFact],
    church_name: str,
) -> list[Issue]:
    """One issue per person per period bucket that is above normal or above their preference."""
    rules_by_period = {r.period: r for r in rules}
    periods = set(rules_by_period) | {p.period for p in preferences.values()}

    issues: list[Issue] = []
    for period in sorted(periods):
        buckets: dict[tuple[object, date], list[AssignmentFact]] = defaultdict(list)
        for a in assignments:
            buckets[(a.person_id, _bucket_start(a.local_start, period))].append(a)
        rule = rules_by_period.get(period)
        for (person_id, start), items in sorted(
            buckets.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
        ):
            count = len(items)
            preference = preferences.get(person_id)
            over_preference = (
                preference is not None and preference.period is period and count > preference.count
            )
            over_normal = rule is not None and count > rule.normal_max
            over_warning = rule is not None and count > rule.warning_above
            if not (over_preference or over_normal):
                continue
            name = items[0].person_name
            reasons = []
            if over_preference and preference is not None:
                reasons.append(f"above their preferred {preference.count}")
            if over_warning and rule is not None:
                reasons.append(
                    f"above {church_name}'s limit (more than {rule.warning_above} is a warning)"
                )
            elif over_normal and rule is not None:
                reasons.append(f"above {church_name}'s usual {rule.normal_max}")
            when = f"the week of {start:%-d %b}" if period is Period.WEEK else f"in {start:%B}"
            issues.append(
                Issue(
                    type=FindingType.LOAD,
                    key=f"load:{person_id}:{period}:{start.isoformat()}",
                    severity=WARNING if over_warning else NOTED,
                    text=f"{name} is serving {count} times {when}, " + " and ".join(reasons) + ".",
                    gathering_id=None,
                    person_ids=(items[0].person_id,),
                    ministry_ids=tuple(dict.fromkeys(a.ministry_id for a in items)),
                    on=min(a.local_start for a in items).date().isoformat(),
                    details={
                        "period": period.value,
                        "period_start": start.isoformat(),
                        "count": count,
                        "preferred": preference.count
                        if preference and preference.period is period
                        else None,
                        "normal_max": rule.normal_max if rule else None,
                        "warning_above": rule.warning_above if rule else None,
                        "assignments": [_side(a) for a in sorted(items, key=lambda a: a.start)],
                    },
                )
            )
    return issues


def _bucket_start(local: datetime, period: Period) -> date:
    day = local.date()
    if period is Period.WEEK:
        # A church week runs Sunday to Saturday, so a Sunday and the Wednesday after it count together.
        return day - timedelta(days=(day.weekday() + 1) % 7)
    return day.replace(day=1)


def below_minimum(needs: Iterable[RoleNeed]) -> list[Issue]:
    return [
        Issue(
            type=FindingType.BELOW_MINIMUM,
            key=f"below_minimum:{n.gathering_id}:{n.role_id}",
            severity=WARNING,
            text=(
                f"{n.ministry_name} needs {n.minimum} {n.role_name} at {n.gathering_name} "
                f"({n.local_start:%a %-d %b} {format_time(n.local_start.time())}) and has {n.filled}."
            ),
            gathering_id=n.gathering_id,
            person_ids=(),
            ministry_ids=(n.ministry_id,),
            on=n.local_start.date().isoformat(),
            details={
                "role_id": str(n.role_id),
                "role": n.role_name,
                "minimum": n.minimum,
                "filled": n.filled,
            },
        )
        for n in needs
        if n.filled < n.minimum
    ]
