import uuid
from datetime import time

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, enum_column, tenant_fk
from app.domain.enums import RosterPath, Weekday


class Ministry(TenantMixin, Base):
    __tablename__ = "ministries"
    __extra_args__ = (sa.UniqueConstraint("church_id", "name"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(sa.String(200)), default=list)
    # Roster settings (section 3): both paths side by side by default, or one default path.
    show_both_paths: Mapped[bool] = mapped_column(default=True)
    default_path: Mapped[RosterPath] = mapped_column(
        enum_column(RosterPath), default=RosterPath.TRAINING
    )
    draft_horizon_weeks: Mapped[int] = mapped_column(default=4)


class Role(TenantMixin, Base):
    """A role a ministry fills, e.g. Keys or Check-in. Never invented by Shepherd."""

    __tablename__ = "roles"
    __extra_args__ = (
        tenant_fk("ministry_id", "ministries"),
        sa.UniqueConstraint("ministry_id", "name"),
        # Lets assignments prove their role belongs to their ministry.
        sa.UniqueConstraint("ministry_id", "id"),
    )

    ministry_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(sa.String(200))


class RoleMinimum(TenantMixin, Base):
    """Minimum people for a role at each gathering of a given type."""

    __tablename__ = "role_minimums"
    __extra_args__ = (
        tenant_fk("role_id", "roles"),
        tenant_fk("gathering_type_id", "gathering_types"),
        sa.UniqueConstraint("role_id", "gathering_type_id"),
        sa.CheckConstraint("minimum >= 0", name="minimum_non_negative"),
    )

    role_id: Mapped[uuid.UUID]
    gathering_type_id: Mapped[uuid.UUID]
    minimum: Mapped[int]


class MinistryLeader(TenantMixin, Base):
    """Who schedules and who approves for a ministry (same person or two)."""

    __tablename__ = "ministry_leaders"
    __extra_args__ = (
        tenant_fk("ministry_id", "ministries"),
        tenant_fk("person_id", "people"),
        sa.UniqueConstraint("ministry_id", "person_id"),
        sa.CheckConstraint("can_schedule OR can_approve", name="has_a_duty"),
    )

    ministry_id: Mapped[uuid.UUID]
    person_id: Mapped[uuid.UUID]
    can_schedule: Mapped[bool]
    can_approve: Mapped[bool]


class LeaderAvailability(TenantMixin, Base):
    """A weekly window a leader is usually free, in the church's time zone (for huddles).

    Kept per person rather than per MinistryLeader so a person leading two
    ministries has one set of windows.
    """

    __tablename__ = "leader_availability"
    __extra_args__ = (
        tenant_fk("person_id", "people"),
        sa.CheckConstraint("end_time > start_time", name="ends_after_start"),
    )

    person_id: Mapped[uuid.UUID]
    weekday: Mapped[Weekday] = mapped_column(enum_column(Weekday))
    start_time: Mapped[time]
    end_time: Mapped[time]
