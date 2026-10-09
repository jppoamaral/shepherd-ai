"""Leader memory (brief §6): Shepherd asks "Should I remember this?" and saves only what a
leader confirms. Each memory is scoped to one ministry.

Privacy (rule 5): health, family situations, reasons someone was away,
interpersonal conflict, and legal or compliance matters are never proposed or
stored. The guard is deterministic and runs before any proposal is created and
again when one is applied.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MemoryItem, Ministry, MinistryLeader, Person, Proposal
from app.db.repositories.audit import AuditLogRepository
from app.db.repositories.proposals import ProposalRepository
from app.domain.enums import MemoryKind, MemorySource, ProposalStatus
from app.domain.schemas import MemoryItemOut, MemoryOut, MemoryPendingOut

PROPOSAL_TYPE = "memory"

_PRIVATE = re.compile(
    r"\b("
    # health
    r"health|ill(ness)?|sick|hospital\w*|surg\w+|doctor|diagnos\w*|cancer|chemo\w*|pregnan\w*|"
    r"miscarri\w*|disab\w*|medica\w+|therap\w+|depress\w*|anxiety|mental|rehab|addict\w*|injur\w*|"
    # family and personal situations
    r"divorc\w*|separat\w*|marriage|custody|grie\w+|funeral|died|death|passed away|affair|"
    r"family (issue|problem|situation)s?|"
    # pastoral and interpersonal
    r"counsel\w*|pastoral|prayer request|conflict with|doesn'?t get along|argu\w+|fight\w*|"
    # legal and compliance
    r"background check|criminal|arrest\w*|police|court|lawsuit|legal|clearance|immigration|visa|debt"
    r")\b",
    re.IGNORECASE,
)


class MemoryRefused(ValueError):
    """The text can't become a memory. The message says why, without repeating it."""


class MemoryNotAllowed(PermissionError):
    pass


def private_reason(text: str) -> str | None:
    if _PRIVATE.search(text):
        return (
            "Shepherd doesn't keep health, family, pastoral, legal or personal-conflict details. "
            "I won't remember that; please handle it with the person directly."
        )
    return None


def is_leader(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID, person_id: uuid.UUID
) -> bool:
    return (
        session.scalar(
            select(MinistryLeader.id).where(
                MinistryLeader.church_id == church_id,
                MinistryLeader.ministry_id == ministry_id,
                MinistryLeader.person_id == person_id,
            )
        )
        is not None
    )


def propose_memory(
    session: Session,
    church_id: uuid.UUID,
    *,
    ministry_id: uuid.UUID,
    text: str,
    kind: MemoryKind,
    proposed_from: MemorySource,
    about_person_id: uuid.UUID | None = None,
    agent: str = "steward",
) -> Proposal:
    """Ask "Should I remember this?" as a pending proposal. Refuses private content."""
    text = " ".join(text.split())
    if not text:
        raise MemoryRefused("There's nothing to remember.")
    if reason := private_reason(text):
        raise MemoryRefused(reason)
    return ProposalRepository(session, church_id).create(
        type=PROPOSAL_TYPE,
        payload={
            "ministry_id": str(ministry_id),
            "text": text,
            "kind": kind.value,
            "proposed_from": proposed_from.value,
            "about_person_id": str(about_person_id) if about_person_id else None,
        },
        created_by_agent=agent,
    )


# --- Leader actions on confirmed memories --------------------------------------


def delete_memory(
    session: Session,
    church_id: uuid.UUID,
    ministry_id: uuid.UUID,
    memory_id: uuid.UUID,
    person_id: uuid.UUID,
) -> None:
    """A leader deletes a memory: it stops shaping suggestions at once, and the deletion is logged."""
    if not is_leader(session, church_id, ministry_id, person_id):
        raise MemoryNotAllowed("only this ministry's leaders can delete its memories")
    item = session.scalar(
        select(MemoryItem).where(
            MemoryItem.church_id == church_id,
            MemoryItem.ministry_id == ministry_id,
            MemoryItem.id == memory_id,
        )
    )
    if item is None:
        raise LookupError("memory not found")
    AuditLogRepository(session, church_id).append(
        actor=f"person:{person_id}",
        action="memory.deleted",
        target_type="memory",
        target_id=str(item.id),
        before={"kind": item.kind.value, "text": item.text},
    )
    session.delete(item)
    session.flush()


def pending_memory_proposals(
    session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID
) -> list[Proposal]:
    return [
        p
        for p in session.scalars(
            select(Proposal)
            .where(
                Proposal.church_id == church_id,
                Proposal.type == PROPOSAL_TYPE,
                Proposal.status == ProposalStatus.PENDING,
            )
            .order_by(Proposal.created_at)
        )
        if p.payload.get("ministry_id") == str(ministry_id)
    ]


def memory_view(session: Session, church_id: uuid.UUID, ministry_id: uuid.UUID) -> MemoryOut | None:
    ministry = session.scalar(
        select(Ministry).where(Ministry.church_id == church_id, Ministry.id == ministry_id)
    )
    if ministry is None:
        return None
    names = dict(
        session.execute(select(Person.id, Person.name).where(Person.church_id == church_id)).all()
    )
    items = session.scalars(
        select(MemoryItem)
        .where(MemoryItem.church_id == church_id, MemoryItem.ministry_id == ministry_id)
        .order_by(MemoryItem.created_at)
    ).all()
    pending = pending_memory_proposals(session, church_id, ministry_id)
    return MemoryOut(
        ministry_id=ministry.id,
        ministry=ministry.name,
        items=[
            MemoryItemOut(
                id=m.id,
                kind=m.kind,
                text=m.text,
                about=names.get(m.about_person_id) if m.about_person_id else None,
                proposed_from=m.proposed_from,
                confirmed_by=names.get(m.confirmed_by_person_id, "unknown"),
                created_at=m.created_at,
            )
            for m in items
        ],
        pending=[
            MemoryPendingOut(
                proposal_id=p.id,
                kind=MemoryKind(p.payload["kind"]),
                text=p.payload["text"],
                about=names.get(uuid.UUID(p.payload["about_person_id"]))
                if p.payload.get("about_person_id")
                else None,
                question=f"Should I remember this? “{p.payload['text']}”",
            )
            for p in pending
        ],
    )
