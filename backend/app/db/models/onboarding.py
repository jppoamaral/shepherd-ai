import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TenantMixin, enum_column, tenant_fk
from app.domain.enums import OnboardingStatus, OnboardingTopic


class OnboardingSession(TenantMixin, CreatedAtMixin, Base):
    """The onboarding agent's working state for one church.

    Holds only the structured draft profile and the current topic. The raw chat
    transcript is deliberately not stored (privacy, architecture rule 5).
    """

    __tablename__ = "onboarding_sessions"
    __extra_args__ = (
        tenant_fk("admin_person_id", "people"),
        tenant_fk("proposal_id", "proposals"),
    )

    admin_person_id: Mapped[uuid.UUID]
    status: Mapped[OnboardingStatus] = mapped_column(
        enum_column(OnboardingStatus), default=OnboardingStatus.ACTIVE
    )
    topic: Mapped[OnboardingTopic] = mapped_column(enum_column(OnboardingTopic))
    # ChurchProfileDraft as JSON (app/domain/profile.py).
    draft: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The question the agent is waiting on, so a reply is read in context.
    pending_question: Mapped[str | None] = mapped_column(sa.Text)
    proposal_id: Mapped[uuid.UUID | None]
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
