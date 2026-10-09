"""Volunteer chat: conversation state, one-time notices for leaders, and the simulator's thread.

None of these is the record. Assignments, blockouts and stop/start change only through
proposals applied by ApprovalService.
"""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, tenant_fk


class Conversation(TenantMixin, Base):
    """What the bot last asked one person, so "1" or "Yes" can be understood.

    Holds ids and dates only, never what the person wrote.
    """

    __tablename__ = "conversations"
    __extra_args__ = (tenant_fk("person_id", "people"), sa.UniqueConstraint("person_id"))

    person_id: Mapped[uuid.UUID]
    awaiting: Mapped[str | None] = mapped_column(sa.String(32))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class LeaderNotice(TenantMixin, CreatedAtMixin, Base):
    """Something a volunteer told Shepherd for their leader, shown once on Home.

    Deleted when the leader dismisses it; never copied to the audit log. It may hold a
    personal reason the volunteer chose to pass on, exactly as they said it.
    """

    __tablename__ = "leader_notices"
    __extra_args__ = (
        tenant_fk("ministry_id", "ministries"),
        tenant_fk("about_person_id", "people"),
    )

    ministry_id: Mapped[uuid.UUID]
    about_person_id: Mapped[uuid.UUID]
    kind: Mapped[str] = mapped_column(sa.String(32))  # declined, cant_commit, stopped, started
    text: Mapped[str] = mapped_column(sa.Text)
    note: Mapped[str | None] = mapped_column(sa.Text)  # the volunteer's own words, if any


class SimulatorMessage(TenantMixin, CreatedAtMixin, Base):
    """What the demo chat shows from Shepherd: the simulator stands in for Telegram.

    Only Shepherd's side is kept (approved messages and the bot's replies). The
    volunteer's own messages stay in the simulator's browser, as they would in Telegram.
    """

    __tablename__ = "simulator_messages"
    __extra_args__ = (tenant_fk("person_id", "people"), tenant_fk("message_id", "messages"))

    person_id: Mapped[uuid.UUID] = mapped_column(index=True)
    body: Mapped[str] = mapped_column(sa.Text)
    buttons: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    message_id: Mapped[uuid.UUID | None]  # set for approved messages; null for bot replies
