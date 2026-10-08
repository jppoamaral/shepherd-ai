"""Rule 9 (append-only audit log) and idempotent gathering generation against Postgres."""

import uuid
from datetime import date

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.db.repositories.audit import AuditLogRepository
from app.services.gatherings import ensure_gatherings
from tests.conftest import SEED_TODAY


def test_audit_log_accepts_appends(session: Session, grace_id: uuid.UUID) -> None:
    entry = AuditLogRepository(session, grace_id).append(
        actor="test", action="test.append", target_type="church", target_id=str(grace_id)
    )
    assert entry.id is not None and entry.at is not None


@pytest.mark.parametrize(
    "statement",
    [
        update(AuditLog).values(action="rewritten"),
        delete(AuditLog),
        text("TRUNCATE audit_log"),
    ],
    ids=["update", "delete", "truncate"],
)
def test_audit_log_rejects_changes(session: Session, statement: object) -> None:
    assert session.scalar(select(AuditLog.id).limit(1)) is not None  # seeds wrote entries
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(statement)  # type: ignore[call-overload]


def test_ensure_gatherings_is_idempotent(session: Session, grace_id: uuid.UUID) -> None:
    window = (SEED_TODAY, date(2027, 6, 30))
    created = ensure_gatherings(session, grace_id, *window)
    assert created > 0  # extends past the seeded horizon
    assert ensure_gatherings(session, grace_id, *window) == 0
