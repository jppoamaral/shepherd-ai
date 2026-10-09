"""Findings, huddles, memory and messages: the outputs of agents and checks."""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import (
    FindingStatus,
    FindingType,
    HuddleStatus,
    MemoryKind,
    MemorySource,
    MessageStatus,
)


class Finding(TenantMixin, CreatedAtMixin, Base):
    """Output of a deterministic check (section 5)."""

    __tablename__ = "findings"
    __extra_args__ = (tenant_fk("gathering_id", "gatherings"),)

    type: Mapped[FindingType] = mapped_column(enum_column(FindingType))
    gathering_id: Mapped[uuid.UUID | None]
    person_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(sa.Uuid), default=list)
    recipient_person_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(sa.Uuid), default=list)
    status: Mapped[FindingStatus] = mapped_column(
        enum_column(FindingStatus), default=FindingStatus.OPEN
    )
    # Structured facts the check found (times, counts, ministries); no free-text reasons.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Huddle(TenantMixin, CreatedAtMixin, Base):
    """A short talk between two leaders about a shared conflict (section 7)."""

    __tablename__ = "huddles"
    __extra_args__ = (tenant_fk("finding_id", "findings"),)

    finding_id: Mapped[uuid.UUID]
    leader_person_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(sa.Uuid))
    offered_slots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    chosen_slot_start: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    agenda: Mapped[str | None] = mapped_column(sa.Text)
    outcome: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[HuddleStatus] = mapped_column(
        enum_column(HuddleStatus), default=HuddleStatus.OFFERED
    )
    # Structured agenda (people, gathering, overlap, sides with suggested replacements)
    # and, when no slot is shared, the nearest options.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class MemoryItem(TenantMixin, CreatedAtMixin, Base):
    """Something a leader confirmed Shepherd should remember, scoped to a ministry."""

    __tablename__ = "memory_items"
    __extra_args__ = (
        tenant_fk("ministry_id", "ministries"),
        tenant_fk("about_person_id", "people"),
        tenant_fk("confirmed_by_person_id", "people"),
    )

    ministry_id: Mapped[uuid.UUID]
    about_person_id: Mapped[uuid.UUID | None]
    kind: Mapped[MemoryKind] = mapped_column(enum_column(MemoryKind))
    text: Mapped[str] = mapped_column(sa.Text)
    proposed_from: Mapped[MemorySource] = mapped_column(enum_column(MemorySource))
    confirmed_by_person_id: Mapped[uuid.UUID]


class Message(TenantMixin, CreatedAtMixin, Base):
    """A 1:1 message to one person. Sent only after approval (rule 1)."""

    __tablename__ = "messages"
    __extra_args__ = (
        tenant_fk("person_id", "people"),
        tenant_fk("assignment_id", "assignments"),
        tenant_fk("gathering_id", "gatherings"),
        tenant_fk("role_id", "roles"),
    )

    person_id: Mapped[uuid.UUID]
    channel: Mapped[str] = mapped_column(sa.String(32))
    body: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[MessageStatus] = mapped_column(
        enum_column(MessageStatus), default=MessageStatus.DRAFT
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(sa.Text)
    # "message", "reminder", or "ask" (a leader asking someone to serve a place)
    kind: Mapped[str] = mapped_column(sa.String(32), server_default="message")
    # A reminder's assignment, so "1" or "2" in reply answers the right place.
    assignment_id: Mapped[uuid.UUID | None]
    # An ask's place (there is no assignment yet), and when the person answered it.
    gathering_id: Mapped[uuid.UUID | None]
    role_id: Mapped[uuid.UUID | None]
    answered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    buttons: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
