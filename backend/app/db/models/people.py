"""People and their relation to ministries.

Privacy (architecture rule 5): nothing here stores legal/background-check,
health, family or pastoral information, and blockouts deliberately have no
reason field.
"""

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import Experience, MembershipStatus, Period, StatedBy


class Person(TenantMixin, CreatedAtMixin, Base):
    __tablename__ = "people"

    name: Mapped[str] = mapped_column(sa.String(200))
    nicknames: Mapped[list[str]] = mapped_column(ARRAY(sa.String(200)), default=list)
    # Address on the chat channel (e.g. a Telegram chat id); unset until connected.
    channel_identity: Mapped[str | None] = mapped_column(sa.String(200))
    opted_in: Mapped[bool] = mapped_column(default=False)
    stopped: Mapped[bool] = mapped_column(default=False)


class Membership(TenantMixin, Base):
    """A person on a ministry's team. An input to Shepherd, never changed by it (rule 6)."""

    __tablename__ = "memberships"
    __extra_args__ = (
        tenant_fk("person_id", "people"),
        tenant_fk("ministry_id", "ministries"),
        sa.UniqueConstraint("person_id", "ministry_id"),
    )

    person_id: Mapped[uuid.UUID]
    ministry_id: Mapped[uuid.UUID]
    status: Mapped[MembershipStatus] = mapped_column(
        enum_column(MembershipStatus), default=MembershipStatus.ACTIVE
    )
    status_since: Mapped[date]
    last_served: Mapped[date | None]
    # When the approver was last asked "is this person still on the team?" about an
    # absent volunteer. Suppresses repeating that question (4 weeks after "Ask me later").
    # Not used for rotation; rotation uses last_served and assignment history.
    asked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class RoleSkill(TenantMixin, Base):
    """Experience in one role. Set only by a leader, never computed (rule 7)."""

    __tablename__ = "role_skills"
    __extra_args__ = (
        tenant_fk("membership_id", "memberships"),
        tenant_fk("role_id", "roles"),
        tenant_fk("set_by_person_id", "people"),
        sa.UniqueConstraint("membership_id", "role_id"),
    )

    membership_id: Mapped[uuid.UUID]
    role_id: Mapped[uuid.UUID]
    experience: Mapped[Experience] = mapped_column(enum_column(Experience))
    set_by_person_id: Mapped[uuid.UUID]
    set_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Preference(TenantMixin, Base):
    """A person's own serving wishes, e.g. "twice a month". Weighed, never absolute."""

    __tablename__ = "preferences"
    __extra_args__ = (
        tenant_fk("person_id", "people"),
        sa.UniqueConstraint("person_id"),
        sa.CheckConstraint(
            "(preferred_frequency IS NULL) = (preferred_frequency_period IS NULL)",
            name="frequency_has_period",
        ),
    )

    person_id: Mapped[uuid.UUID]
    preferred_frequency: Mapped[int | None]
    preferred_frequency_period: Mapped[Period | None] = mapped_column(enum_column(Period))
    stated_by: Mapped[StatedBy] = mapped_column(enum_column(StatedBy))


class PreferredGathering(TenantMixin, Base):
    """A preferred time, expressed as a gathering type ("Emily prefers 9:30")."""

    __tablename__ = "preferred_gatherings"
    __extra_args__ = (
        tenant_fk("person_id", "people"),
        tenant_fk("gathering_type_id", "gathering_types"),
        sa.UniqueConstraint("person_id", "gathering_type_id"),
    )

    person_id: Mapped[uuid.UUID]
    gathering_type_id: Mapped[uuid.UUID]
    stated_by: Mapped[StatedBy] = mapped_column(enum_column(StatedBy))


class Blockout(TenantMixin, CreatedAtMixin, Base):
    """Dates (inclusive, church-local) a person can't serve. No reason is ever stored."""

    __tablename__ = "blockouts"
    __extra_args__ = (
        tenant_fk("person_id", "people"),
        sa.CheckConstraint("end_date >= start_date", name="ends_after_start"),
    )

    person_id: Mapped[uuid.UUID]
    start_date: Mapped[date]
    end_date: Mapped[date]
    stated_by: Mapped[StatedBy] = mapped_column(enum_column(StatedBy))
