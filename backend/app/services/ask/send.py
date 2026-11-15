"""Sending Ask Shepherd's drafts. The leader's tap on Send is the approval: one proposal
per kind, approved and sent by ApprovalService, as on Home."""

import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Person,
)
from app.domain.enums import (
    ProposalType,
)
from app.domain.proposals import (
    ReminderMessage,
    RemindersPayload,
    ServeAskMessage,
    ServeAskPayload,
)
from app.domain.schemas import (
    AskSendIn,
    AskSendOut,
)
from app.services import reminders
from app.services.approval import ApprovalService, propose_and_approve
from app.services.ask.queries import LOOKAHEAD_DAYS, AskNotFound, Context, load_context, place_of
from app.services.briefing import roster
from app.services.reminders import (
    already_reminded,
    pending_reminders,
    still_on_roster,
)
from app.services.text import and_list


def send_drafts(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    body: AskSendIn,
    today: date | None = None,
) -> AskSendOut:
    """The leader tapped Send on drafts they read (and maybe edited). That tap is the
    approval: one proposal per kind, approved and sent by ApprovalService, as on Home."""
    ctx = load_context(session, church_id, ministry_id, body.person_id, today)
    upcoming = roster(
        session, church_id, ministry_id, ctx.today, ctx.today + timedelta(days=LOOKAHEAD_DAYS)
    )
    places = {
        (role.role_id, g.gathering_id): role
        for g in (upcoming.gatherings if upcoming else [])
        for role in g.roles
    }
    asks: list[ServeAskMessage] = []
    reminder_items: dict[uuid.UUID, list[ReminderMessage]] = defaultdict(list)
    skipped: list[str] = []
    names: dict[uuid.UUID, str] = {}
    for d in body.drafts:
        person = session.scalar(
            select(Person).where(Person.church_id == church_id, Person.id == d.to_person_id)
        )
        place = places.get((d.role_id, d.gathering_id))
        if person is None or place is None:
            raise AskNotFound("that place isn't on this ministry's rosters in the next 4 weeks")
        first = person.name.split(" ")[0]
        names[person.id] = first
        text = d.body.strip()
        if d.kind == "ask":
            if person.id not in ctx.team:
                raise AskNotFound(f"{person.name} isn't on the {ctx.ministry.name} team")
            ask_item = ServeAskMessage(
                person_id=person.id, body=text, gathering_id=d.gathering_id, role_id=d.role_id
            )
            if d.replaces_assignment_id is not None:
                taken = place_of(ctx, d.replaces_assignment_id)
                if taken is None or (taken.gathering_id, taken.role_id) != (
                    d.gathering_id,
                    d.role_id,
                ):
                    raise AskNotFound("that place has changed since the draft")
                ask_item.replaces_assignment_id = taken.id
            asks.append(ask_item)
            continue
        assignment_id = d.assignment_id
        if assignment_id is None or not any(p.assignment_id == assignment_id for p in place.people):
            raise AskNotFound(f"{person.name} isn't on that roster")
        if not still_on_roster(session, church_id, assignment_id, person.id):
            skipped.append(f"{first} is no longer on that roster.")
            continue
        if already_reminded(session, church_id, assignment_id):
            skipped.append(f"{first} already has a reminder for this.")
            continue
        reminder_items[d.gathering_id].append(
            ReminderMessage(assignment_id=assignment_id, person_id=person.id, body=text)
        )

    for gathering_id, items in reminder_items.items():
        propose_and_approve(
            session,
            church_id,
            type=ProposalType.REMINDERS,
            payload=RemindersPayload(
                ministry_id=ministry_id,
                gathering_id=gathering_id,
                messages=items,
                buttons=reminders.BUTTONS,
            ),
            created_by_agent="ask",
            person_id=ctx.leader.id,
        )
    if asks:
        propose_and_approve(
            session,
            church_id,
            type=ProposalType.SERVE_ASK,
            payload=ServeAskPayload(ministry_id=ministry_id, messages=asks),
            created_by_agent="ask",
            person_id=ctx.leader.id,
        )
    _close_covered_reminders(ctx, set(reminder_items))

    sent: list[uuid.UUID] = []
    recipients = [m.person_id for items in reminder_items.values() for m in items]
    for person_id in [*recipients, *(m.person_id for m in asks)]:
        person = session.get_one(Person, person_id)
        first = names[person.id]
        if person.stopped:
            skipped.append(f"{first} turned messages off.")
        elif not person.opted_in:
            skipped.append(f"{first} hasn't connected to chat yet.")
        else:
            sent.append(person.id)
    return AskSendOut(
        text=_sent_text([names[p] for p in sent], skipped), sent=sent, skipped=skipped
    )


def _close_covered_reminders(ctx: Context, gathering_ids: set[uuid.UUID]) -> None:
    """Home's pending reminders for a service Ask just covered would send nothing: close
    them (rejected by the leader, audited) instead of leaving an empty card."""
    service = ApprovalService(ctx.session)
    for proposal_id, payload in pending_reminders(ctx.session, ctx.church_id).items():
        if payload.ministry_id != ctx.ministry.id or payload.gathering_id not in gathering_ids:
            continue
        if all(
            not still_on_roster(ctx.session, ctx.church_id, m.assignment_id, m.person_id)
            or already_reminded(ctx.session, ctx.church_id, m.assignment_id)
            for m in payload.messages
        ):
            service.reject(ctx.church_id, proposal_id, ctx.leader.id)


def _sent_text(sent: list[str], skipped: list[str]) -> str:
    done = f"Sent to {and_list(sent)}, 1:1." if sent else "Nothing was sent."
    return " ".join([done, *skipped])
