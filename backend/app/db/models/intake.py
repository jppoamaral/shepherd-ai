import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import IntakeStatus


class ScheduleIntake(TenantMixin, CreatedAtMixin, Base):
    """A scheduler's pasted roster, parsed into slots plus open questions.

    The steward agent's working state. The pasted text itself is never stored;
    only the parsed slots (names as written, resolved ids) and the questions.
    """

    __tablename__ = "schedule_intakes"
    __extra_args__ = (
        tenant_fk("ministry_id", "ministries"),
        tenant_fk("submitted_by_person_id", "people"),
        tenant_fk("proposal_id", "proposals"),
    )

    ministry_id: Mapped[uuid.UUID]
    submitted_by_person_id: Mapped[uuid.UUID]
    status: Mapped[IntakeStatus] = mapped_column(
        enum_column(IntakeStatus), default=IntakeStatus.NEEDS_ANSWERS
    )
    # IntakeDraft as JSON (app/domain/intake.py).
    draft: Mapped[dict[str, Any]] = mapped_column(JSONB)
    proposal_id: Mapped[uuid.UUID | None]
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
