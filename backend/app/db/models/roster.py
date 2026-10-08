import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import AssignmentSource, AssignmentStatus, RosterPath


class RosterSuggestion(TenantMixin, CreatedAtMixin, Base):
    __tablename__ = "roster_suggestions"
    __extra_args__ = (
        tenant_fk("ministry_id", "ministries"),
        tenant_fk("approved_by_person_id", "people"),
        sa.CheckConstraint("period_end >= period_start", name="ends_after_start"),
    )

    ministry_id: Mapped[uuid.UUID]
    period_start: Mapped[date]
    period_end: Mapped[date]
    path: Mapped[RosterPath] = mapped_column(enum_column(RosterPath))
    chosen: Mapped[bool] = mapped_column(default=False)
    approved_by_person_id: Mapped[uuid.UUID | None]
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Assignment(TenantMixin, CreatedAtMixin, Base):
    """One person in one role at one gathering.

    Written only by ApprovalService (rule 1) and, for fixtures, by seeds.
    """

    __tablename__ = "assignments"
    __extra_args__ = (
        tenant_fk("gathering_id", "gatherings"),
        tenant_fk("ministry_id", "ministries"),
        tenant_fk("role_id", "roles"),
        tenant_fk("person_id", "people"),
        tenant_fk("roster_suggestion_id", "roster_suggestions"),
        sa.ForeignKeyConstraint(["ministry_id", "role_id"], ["roles.ministry_id", "roles.id"]),
        sa.Index(None, "person_id", "gathering_id"),
    )

    gathering_id: Mapped[uuid.UUID]
    ministry_id: Mapped[uuid.UUID]
    role_id: Mapped[uuid.UUID]
    person_id: Mapped[uuid.UUID]
    status: Mapped[AssignmentStatus] = mapped_column(enum_column(AssignmentStatus))
    # One-line explanation shown to the leader, e.g. "Rachel with Emily: ...".
    reason: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[AssignmentSource] = mapped_column(enum_column(AssignmentSource))
    roster_suggestion_id: Mapped[uuid.UUID | None]
