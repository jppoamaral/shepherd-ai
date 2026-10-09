"""The steward agent's intake working state. Not the roster record: agents may use it.

It creates and saves one schedule intake (parsed slots and open questions). It
can't write assignments, people or memberships; approval does that.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ScheduleIntake
from app.domain.enums import IntakeStatus
from app.domain.intake import IntakeDraft


@dataclass
class IntakeState:
    id: uuid.UUID
    ministry_id: uuid.UUID
    submitted_by_person_id: uuid.UUID
    status: IntakeStatus
    draft: IntakeDraft
    proposal_id: uuid.UUID | None


class IntakeRepository:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def create(
        self, *, ministry_id: uuid.UUID, submitted_by_person_id: uuid.UUID, draft: IntakeDraft
    ) -> IntakeState:
        row = ScheduleIntake(
            church_id=self.church_id,
            ministry_id=ministry_id,
            submitted_by_person_id=submitted_by_person_id,
            status=IntakeStatus.NEEDS_ANSWERS,
            draft=draft.model_dump(mode="json"),
        )
        self.session.add(row)
        self.session.flush()
        return self._state(row)

    def get(self, intake_id: uuid.UUID) -> IntakeState | None:
        row = self._row(intake_id)
        return self._state(row) if row else None

    def save(self, state: IntakeState) -> None:
        row = self._row(state.id)
        assert row is not None
        row.draft = state.draft.model_dump(mode="json")
        # Only the agent's own statuses; approved/rejected are set by ApprovalService handlers.
        if state.status in (IntakeStatus.NEEDS_ANSWERS, IntakeStatus.PROPOSED):
            row.status = state.status
        row.proposal_id = state.proposal_id
        self.session.flush()

    def _row(self, intake_id: uuid.UUID) -> ScheduleIntake | None:
        return self.session.scalar(
            select(ScheduleIntake).where(
                ScheduleIntake.church_id == self.church_id, ScheduleIntake.id == intake_id
            )
        )

    @staticmethod
    def _state(row: ScheduleIntake) -> IntakeState:
        return IntakeState(
            id=row.id,
            ministry_id=row.ministry_id,
            submitted_by_person_id=row.submitted_by_person_id,
            status=row.status,
            draft=IntakeDraft.model_validate(row.draft),
            proposal_id=row.proposal_id,
        )
