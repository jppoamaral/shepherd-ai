"""Proposals (what agents may write) and the append-only audit log."""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import ProposalStatus


class Proposal(TenantMixin, CreatedAtMixin, Base):
    """Something an agent suggests. Only ApprovalService applies its side effects."""

    __tablename__ = "proposals"
    __extra_args__ = (
        tenant_fk("decided_by_person_id", "people"),
        sa.Index(None, "church_id", "status"),
    )

    type: Mapped[str] = mapped_column(sa.String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[ProposalStatus] = mapped_column(
        enum_column(ProposalStatus), default=ProposalStatus.PENDING
    )
    created_by_agent: Mapped[str] = mapped_column(sa.String(64))
    decided_by_person_id: Mapped[uuid.UUID | None]
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuditLog(Base):
    """Append-only (rule 9): a database trigger rejects UPDATE, DELETE and TRUNCATE."""

    __tablename__ = "audit_log"
    __table_args__ = (
        tenant_fk("approved_by_person_id", "people"),
        sa.Index(None, "church_id", "at"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    church_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("churches.id"))
    actor: Mapped[str] = mapped_column(sa.String(200))  # "person:<id>", "agent:<name>", "seed"
    action: Mapped[str] = mapped_column(sa.String(64))
    target_type: Mapped[str] = mapped_column(sa.String(64))
    target_id: Mapped[str | None] = mapped_column(sa.String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approved_by_person_id: Mapped[uuid.UUID | None]
    at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
