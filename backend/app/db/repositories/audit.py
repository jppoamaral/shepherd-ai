"""Append-only audit log writes. There is deliberately no update or delete."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session, church_id: uuid.UUID) -> None:
        self.session = session
        self.church_id = church_id

    def append(
        self,
        *,
        actor: str,
        action: str,
        target_type: str,
        target_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        approved_by_person_id: uuid.UUID | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            church_id=self.church_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            approved_by_person_id=approved_by_person_id,
        )
        self.session.add(entry)
        self.session.flush()
        return entry
