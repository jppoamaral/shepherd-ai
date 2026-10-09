import uuid
from datetime import date, datetime, time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import GatheringKind, Period, ProfileStatus, Recurrence, Weekday


class Church(CreatedAtMixin, Base):
    """The tenant. Its `id` is the `church_id` every other table carries."""

    __tablename__ = "churches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(200), unique=True)
    timezone: Mapped[str] = mapped_column(sa.String(64))  # IANA name, e.g. "America/Chicago"
    language: Mapped[str] = mapped_column(sa.String(16), default="en")
    # How approved 1:1 messages leave Shepherd: "copy_paste", "simulator" (demo) or, later,
    # "telegram". New churches get the DEFAULT_CHANNEL setting.
    channel: Mapped[str] = mapped_column(sa.String(32), server_default="copy_paste")
    profile_status: Mapped[ProfileStatus] = mapped_column(
        enum_column(ProfileStatus), default=ProfileStatus.DRAFT
    )
    member_count: Mapped[int | None]
    # Weeks without serving before an active person is flagged as absent (set in onboarding).
    absence_threshold_weeks: Mapped[int | None]
    # Finding type -> who hears first ("scheduler", "approver"), set in onboarding.
    warning_routing: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class LoadRule(TenantMixin, Base):
    """How a church sees serving frequency. Produces warnings, never blocks.

    For a count `n` in one `period`: `n <= normal_max` is normal, up to
    `warning_above` is noted for the approver, above `warning_above` is a warning.
    A church has at most one rule per period and may have none.
    """

    __tablename__ = "load_rules"
    __extra_args__ = (
        sa.UniqueConstraint("church_id", "period"),
        sa.CheckConstraint("normal_max >= 0", name="normal_max_non_negative"),
        sa.CheckConstraint("warning_above >= normal_max", name="warning_above_normal"),
    )

    period: Mapped[Period] = mapped_column(enum_column(Period))
    normal_max: Mapped[int]
    warning_above: Mapped[int]


class GatheringType(TenantMixin, CreatedAtMixin, Base):
    """A recurring or one-off gathering, defined in the church's local time."""

    __tablename__ = "gathering_types"
    __extra_args__ = (
        sa.CheckConstraint(
            "(recurrence = 'weekly' AND weekday IS NOT NULL AND one_off_date IS NULL)"
            " OR (recurrence = 'one_off' AND one_off_date IS NOT NULL AND weekday IS NULL)",
            name="recurrence_fields",
        ),
        sa.CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )

    name: Mapped[str] = mapped_column(sa.String(200))
    kind: Mapped[GatheringKind] = mapped_column(enum_column(GatheringKind))
    recurrence: Mapped[Recurrence] = mapped_column(enum_column(Recurrence))
    weekday: Mapped[Weekday | None] = mapped_column(enum_column(Weekday))
    one_off_date: Mapped[date | None]
    local_start_time: Mapped[time] = mapped_column(sa.Time(timezone=False))
    duration_minutes: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)


class Gathering(TenantMixin, Base):
    """A concrete occurrence with real, timezone-aware start and end."""

    __tablename__ = "gatherings"
    __extra_args__ = (
        tenant_fk("gathering_type_id", "gathering_types"),
        sa.UniqueConstraint("gathering_type_id", "start_at"),
        sa.CheckConstraint("end_at > start_at", name="ends_after_start"),
    )

    gathering_type_id: Mapped[uuid.UUID]
    start_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
