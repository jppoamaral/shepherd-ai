"""The onboarding agent's working state. Not the church record: agents may use it.

It reads and saves the structured draft and current topic of one session. It
can't create churches, people or anything an approval would apply.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OnboardingSession
from app.domain.enums import OnboardingStatus, OnboardingTopic
from app.domain.profile import ChurchProfileDraft


@dataclass
class OnboardingState:
    id: uuid.UUID
    church_id: uuid.UUID
    status: OnboardingStatus
    topic: OnboardingTopic
    draft: ChurchProfileDraft
    pending_question: str | None
    proposal_id: uuid.UUID | None


class OnboardingRepository:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def get(self, onboarding_id: uuid.UUID) -> OnboardingState | None:
        row = self._row(onboarding_id)
        if row is None:
            return None
        return OnboardingState(
            id=row.id,
            church_id=row.church_id,
            status=row.status,
            topic=row.topic,
            draft=ChurchProfileDraft.model_validate(row.draft),
            pending_question=row.pending_question,
            proposal_id=row.proposal_id,
        )

    def save(self, state: OnboardingState) -> None:
        row = self._row(state.id)
        assert row is not None
        # Only the agent's working fields; status moves to approved via ApprovalService.
        row.topic = state.topic
        row.draft = state.draft.model_dump(mode="json")
        row.pending_question = state.pending_question
        if state.status in (OnboardingStatus.ACTIVE, OnboardingStatus.PROPOSED):
            row.status = state.status
        row.proposal_id = state.proposal_id
        self.session.flush()

    def _row(self, onboarding_id: uuid.UUID) -> OnboardingSession | None:
        return self.session.scalar(
            select(OnboardingSession).where(
                OnboardingSession.church_id == self.church_id,
                OnboardingSession.id == onboarding_id,
            )
        )
