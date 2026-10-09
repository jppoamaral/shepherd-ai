"""Conflict huddle (brief §7): two leaders, one double booking, a short time to talk.

Deterministic: shared slots come from the leaders' availability windows, and
each side's suggested replacement is a free, not-blocked-out member of that
leader's own team in the same role. Only leaders are involved; the volunteer
is never invited. The decision stays with the leaders: resolving records their
outcome and re-runs the checks, but reassigns nobody.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Assignment,
    Blockout,
    Church,
    Finding,
    Gathering,
    Huddle,
    LeaderAvailability,
    Membership,
    MinistryLeader,
    Person,
    RoleSkill,
)
from app.domain.enums import (
    AssignmentStatus,
    Experience,
    FindingStatus,
    FindingType,
    HuddleStatus,
    MembershipStatus,
)
from app.domain.schemas import HuddleAgenda, HuddleLeader, HuddleOut, HuddleSide, HuddleSlot
from app.services.checks_runner import run_checks
from app.services.huddle_slots import Window, common_slots, nearest_options
from app.services.profile import format_time

EXPERIENCE_RANK = {Experience.VETERAN: 0, Experience.EXPERIENCED: 1, Experience.NEW: 2}


class HuddleError(Exception):
    """A user-facing reason the huddle action can't happen."""


class HuddleNotFound(HuddleError):
    pass


class HuddleNotAllowed(HuddleError):
    pass


def start_huddle(
    session: Session,
    church_id: uuid.UUID,
    finding_id: uuid.UUID,
    person_id: uuid.UUID,
    now: datetime | None = None,
) -> HuddleOut:
    finding = session.scalar(
        select(Finding).where(Finding.church_id == church_id, Finding.id == finding_id)
    )
    if finding is None:
        raise HuddleNotFound("finding not found")
    if finding.type is not FindingType.OVERLAP:
        raise HuddleError("only a double booking can have a huddle")
    if finding.status is not FindingStatus.OPEN:
        raise HuddleError("this double booking is already settled")
    if person_id not in finding.recipient_person_ids:
        raise HuddleNotAllowed(
            "only the leaders warned about this double booking can start a huddle"
        )

    existing = session.scalar(
        select(Huddle).where(
            Huddle.church_id == church_id,
            Huddle.finding_id == finding.id,
            Huddle.status.in_([HuddleStatus.OFFERED, HuddleStatus.SCHEDULED]),
        )
    )
    if existing is not None:
        return huddle_out(session, existing)

    church = session.get_one(Church, church_id)
    tz = ZoneInfo(church.timezone)
    sides: list[dict[str, str]] = finding.details["sides"]
    led = _ministries_led(session, church_id, person_id)
    mine = next((s for s in sides if uuid.UUID(s["ministry_id"]) in led), None)
    theirs = next(
        (s for s in sides if s is not mine and uuid.UUID(s["ministry_id"]) not in led), None
    )
    if mine is None or theirs is None:
        raise HuddleError("both sides of this double booking are your ministry; no huddle needed")
    other_leader = _leader_of(
        session, church_id, uuid.UUID(theirs["ministry_id"]), exclude=person_id
    )
    if other_leader is None:
        raise HuddleError(f"{theirs['ministry']} has no leader to talk to")

    leader_ids = [person_id, other_leader]
    names = dict(
        session.execute(select(Person.id, Person.name).where(Person.id.in_(leader_ids))).all()
    )
    windows = _windows(session, church_id, leader_ids)
    gathering_start = min(datetime.fromisoformat(s["start"]) for s in sides).astimezone(tz)
    now = (now or datetime.now(UTC)).astimezone(tz)

    slots = common_slots(windows, now, before=gathering_start)
    nearest = (
        [] if slots else [o.label for o in nearest_options(windows, names, now, gathering_start)]
    )
    volunteer_id = finding.person_ids[0]
    volunteer = session.get_one(Person, volunteer_id).name
    agenda_sides = [
        _side(session, church_id, side, names[leader], volunteer_id, tz)
        for side, leader in ((mine, person_id), (theirs, other_leader))
    ]
    overlap = _overlap_label(finding.details, tz)
    agenda = HuddleAgenda(
        title=f"{volunteer}'s double booking, {gathering_start:%a %-d %b}",
        volunteer=volunteer,
        overlap=overlap,
        sides=agenda_sides,
    )
    huddle = Huddle(
        church_id=church_id,
        finding_id=finding.id,
        leader_person_ids=leader_ids,
        offered_slots=[
            {
                "id": f"s{i}",
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "label": s.label,
            }
            for i, s in enumerate(slots, 1)
        ],
        agenda=_agenda_text(agenda),
        status=HuddleStatus.OFFERED,
        details={"agenda": agenda.model_dump(mode="json"), "nearest_options": nearest},
    )
    session.add(huddle)
    session.flush()
    return huddle_out(session, huddle)


def choose_slot(
    session: Session, church_id: uuid.UUID, huddle_id: uuid.UUID, person_id: uuid.UUID, slot_id: str
) -> HuddleOut:
    huddle = _load(session, church_id, huddle_id, person_id)
    if huddle.status not in (HuddleStatus.OFFERED, HuddleStatus.SCHEDULED):
        raise HuddleError(f"this huddle is already {huddle.status.value}")
    slot = next((s for s in huddle.offered_slots if s["id"] == slot_id), None)
    if slot is None:
        raise HuddleError("that isn't one of the offered times")
    huddle.chosen_slot_start = datetime.fromisoformat(slot["start"])
    huddle.status = HuddleStatus.SCHEDULED
    session.flush()
    return huddle_out(session, huddle)


def resolve(
    session: Session, church_id: uuid.UUID, huddle_id: uuid.UUID, person_id: uuid.UUID, outcome: str
) -> HuddleOut:
    """Record what the leaders decided and re-run the checks. Nobody is reassigned here."""
    huddle = _load(session, church_id, huddle_id, person_id)
    if huddle.status is HuddleStatus.RESOLVED:
        raise HuddleError("this huddle is already resolved")
    huddle.outcome = outcome.strip()
    huddle.status = HuddleStatus.RESOLVED
    finding = session.get_one(Finding, huddle.finding_id)
    on = datetime.fromisoformat(finding.details["sides"][0]["start"]).date()
    run_checks(session, church_id, on - timedelta(days=7), on + timedelta(days=7))
    session.flush()
    return huddle_out(session, huddle)


def get_huddle(session: Session, church_id: uuid.UUID, huddle_id: uuid.UUID) -> HuddleOut:
    huddle = session.scalar(
        select(Huddle).where(Huddle.church_id == church_id, Huddle.id == huddle_id)
    )
    if huddle is None:
        raise HuddleNotFound("huddle not found")
    return huddle_out(session, huddle)


def huddle_out(session: Session, huddle: Huddle) -> HuddleOut:
    names = dict(
        session.execute(
            select(Person.id, Person.name).where(Person.id.in_(huddle.leader_person_ids))
        ).all()
    )
    slots = [HuddleSlot(**s) for s in huddle.offered_slots]
    chosen = next(
        (s for s in slots if huddle.chosen_slot_start and s.start == huddle.chosen_slot_start), None
    )
    finding = session.get_one(Finding, huddle.finding_id)
    return HuddleOut(
        id=huddle.id,
        finding_id=huddle.finding_id,
        status=huddle.status,
        leaders=[HuddleLeader(person_id=p, name=names[p]) for p in huddle.leader_person_ids],
        slots=slots,
        chosen_slot=chosen,
        no_common_slot=not slots,
        nearest_options=huddle.details.get("nearest_options", []),
        agenda=HuddleAgenda.model_validate(huddle.details["agenda"]),
        agenda_text=huddle.agenda or "",
        outcome=huddle.outcome,
        finding_status=finding.status,
    )


# ---------------------------------------------------------------------------


def _load(
    session: Session, church_id: uuid.UUID, huddle_id: uuid.UUID, person_id: uuid.UUID
) -> Huddle:
    huddle = session.scalar(
        select(Huddle).where(Huddle.church_id == church_id, Huddle.id == huddle_id)
    )
    if huddle is None:
        raise HuddleNotFound("huddle not found")
    if person_id not in huddle.leader_person_ids:
        raise HuddleNotAllowed("only the two leaders in this huddle can do that")
    return huddle


def _ministries_led(session: Session, church_id: uuid.UUID, person_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(MinistryLeader.ministry_id).where(
                MinistryLeader.church_id == church_id, MinistryLeader.person_id == person_id
            )
        )
    )


def _leader_of(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID, exclude: uuid.UUID
) -> uuid.UUID | None:
    leaders = session.scalars(
        select(MinistryLeader).where(
            MinistryLeader.church_id == church_id, MinistryLeader.ministry_id == ministry_id
        )
    ).all()
    ranked = sorted(
        (x for x in leaders if x.person_id != exclude),
        key=lambda x: (not x.can_schedule, not x.can_approve),
    )
    return ranked[0].person_id if ranked else None


def _windows(
    session: Session, church_id: uuid.UUID, people: list[uuid.UUID]
) -> dict[uuid.UUID, list[Window]]:
    windows: dict[uuid.UUID, list[Window]] = {p: [] for p in people}
    for w in session.scalars(
        select(LeaderAvailability).where(
            LeaderAvailability.church_id == church_id, LeaderAvailability.person_id.in_(people)
        )
    ):
        windows[w.person_id].append(Window(w.weekday, w.start_time, w.end_time))
    return windows


def _side(
    session: Session,
    church_id: uuid.UUID,
    side: dict[str, str],
    leader: str,
    volunteer_id: uuid.UUID,
    tz: ZoneInfo,
) -> HuddleSide:
    start, end = datetime.fromisoformat(side["start"]), datetime.fromisoformat(side["end"])
    replacement = _replacement(session, church_id, side, volunteer_id, start, end)
    when = f"{start.astimezone(tz):%a %-d %b} {format_time(start.astimezone(tz).time())}"
    if replacement is None:
        note = f"Nobody else on {side['ministry']} who plays {side['role']} is free then."
    else:
        note = f"{replacement[0]} ({replacement[1].value}) is free and not blocked out."
    return HuddleSide(
        ministry=side["ministry"],
        role=side["role"],
        gathering=f"{side['gathering']}, {when}",
        leader=leader,
        replacement=replacement[0] if replacement else None,
        replacement_note=note,
    )


def _replacement(
    session: Session,
    church_id: uuid.UUID,
    side: dict[str, str],
    volunteer_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> tuple[str, Experience] | None:
    """A free team member in the same role: most experienced first, then lightest week, then name."""
    candidates = session.execute(
        select(Person.id, Person.name, RoleSkill.experience)
        .join(Membership, Membership.person_id == Person.id)
        .join(RoleSkill, RoleSkill.membership_id == Membership.id)
        .where(
            Membership.church_id == church_id,
            Membership.ministry_id == uuid.UUID(side["ministry_id"]),
            Membership.status == MembershipStatus.ACTIVE,
            RoleSkill.role_id == uuid.UUID(side["role_id"]),
            Person.id != volunteer_id,
            Person.stopped.is_(False),
        )
    ).all()
    if not candidates:
        return None
    ids = [c.id for c in candidates]
    busy = set(
        session.scalars(
            select(Assignment.person_id)
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(
                Assignment.church_id == church_id,
                Assignment.person_id.in_(ids),
                Assignment.status != AssignmentStatus.DECLINED,
                Gathering.start_at < end,
                Gathering.end_at > start,
            )
        )
    )
    day = start.date()
    blocked = set(
        session.scalars(
            select(Blockout.person_id).where(
                Blockout.church_id == church_id,
                Blockout.person_id.in_(ids),
                Blockout.start_date <= day,
                Blockout.end_date >= day,
            )
        )
    )
    # Lighter week first: assignments within a few days either side of this one.
    week_load: dict[uuid.UUID, int] = {
        person_id: count
        for person_id, count in session.execute(
            select(Assignment.person_id, func.count())
            .join(Gathering, Gathering.id == Assignment.gathering_id)
            .where(
                Assignment.church_id == church_id,
                Assignment.person_id.in_(ids),
                Assignment.status != AssignmentStatus.DECLINED,
                Gathering.start_at >= start - timedelta(days=3),
                Gathering.start_at < start + timedelta(days=4),
            )
            .group_by(Assignment.person_id)
        )
    }
    free = [c for c in candidates if c.id not in busy and c.id not in blocked]
    free.sort(key=lambda c: (EXPERIENCE_RANK[c.experience], week_load.get(c.id, 0), c.name))
    return (free[0].name, free[0].experience) if free else None


def _overlap_label(details: dict[str, Any], tz: ZoneInfo) -> str:
    start = datetime.fromisoformat(details["overlap_start"]).astimezone(tz)
    end = datetime.fromisoformat(details["overlap_end"]).astimezone(tz)
    return f"{start:%a %-d %b}, {format_time(start.time())} to {format_time(end.time())}"


def _agenda_text(agenda: HuddleAgenda) -> str:
    lines = [agenda.title, f"Overlap: {agenda.overlap}", ""]
    for side in agenda.sides:
        lines.append(
            f"{side.ministry} ({side.leader}): {agenda.volunteer} on {side.role} at {side.gathering}."
        )
        lines.append(
            f"  Possible replacement: {side.replacement or 'none free'}. {side.replacement_note}"
        )
    lines += [
        "",
        f"{agenda.volunteer} isn't part of this conversation. You two decide; Shepherd won't reassign anyone.",
    ]
    return "\n".join(lines)
