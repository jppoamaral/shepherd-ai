"""Writes to the roster record.

Only ApprovalService (and seed fixtures) may import this module. Agents must not;
`tests/unit/test_architecture.py` enforces that (architecture rule 1).
"""

import uuid

from sqlalchemy.orm import Session

from app.db.models import Assignment
from app.domain.enums import AssignmentSource, AssignmentStatus


class AssignmentWriter:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def create(
        self,
        *,
        gathering_id: uuid.UUID,
        ministry_id: uuid.UUID,
        role_id: uuid.UUID,
        person_id: uuid.UUID,
        status: AssignmentStatus,
        source: AssignmentSource,
        reason: str | None = None,
        roster_suggestion_id: uuid.UUID | None = None,
    ) -> Assignment:
        assignment = Assignment(
            church_id=self.church_id,
            gathering_id=gathering_id,
            ministry_id=ministry_id,
            role_id=role_id,
            person_id=person_id,
            status=status,
            source=source,
            reason=reason,
            roster_suggestion_id=roster_suggestion_id,
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def reassign(
        self,
        assignment: Assignment,
        *,
        person_id: uuid.UUID,
        reason: str | None,
        source: AssignmentSource,
    ) -> Assignment:
        """Put someone else in the same place (gathering, ministry, role)."""
        if assignment.church_id != self.church_id:
            raise ValueError("assignment belongs to another church")
        assignment.person_id = person_id
        assignment.reason = reason
        assignment.source = source
        self.session.flush()
        return assignment

    def set_status(self, assignment: Assignment, status: AssignmentStatus) -> Assignment:
        """A volunteer's own answer: confirmed or declined."""
        if assignment.church_id != self.church_id:
            raise ValueError("assignment belongs to another church")
        assignment.status = status
        self.session.flush()
        return assignment
