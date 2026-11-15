"""MVP deploy pieces (ADR 0002): database URL, the in-process scheduler, demo reset."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.demo import demo_mode
from app.config import Settings
from app.db.models import Assignment, AuditLog, Church, Person
from app.main import app
from app.scheduler import build_scheduler
from tests.conftest import GRACE, RIVERSIDE


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@host:5432/db",
        "postgresql://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
    ],
)
def test_database_url_always_uses_the_psycopg_driver(given: str) -> None:
    assert Settings(database_url=given).database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_scheduler_and_demo_mode_are_off_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert (settings.run_scheduler, settings.demo_mode) == (False, False)


def test_scheduler_runs_the_nightly_job_at_startup_and_every_night() -> None:
    jobs = {job.id: job for job in build_scheduler().get_jobs()}
    assert set(jobs) == {"extend_gatherings", "at_startup"}
    assert str(jobs["extend_gatherings"].trigger) == "cron[hour='2', minute='0']"


def test_demo_reset_is_not_found_unless_demo_mode_is_on(client: TestClient) -> None:
    assert client.post("/demo/reset").status_code == 404


@pytest.fixture
def demo_on() -> Iterator[None]:
    app.dependency_overrides[demo_mode] = lambda: True
    yield
    app.dependency_overrides.pop(demo_mode, None)


def test_demo_reset_puts_the_seeded_data_back(
    client: TestClient, session: Session, demo_on: None
) -> None:
    grace = session.scalars(select(Church).where(Church.name == GRACE)).one()
    # Leave marks a demo would: a renamed person and no rosters.
    anna = session.scalars(
        select(Person).where(Person.church_id == grace.id, Person.name == "Anna Parker")
    ).one()
    anna.name = "Somebody Else"
    for assignment in session.scalars(select(Assignment)):
        session.delete(assignment)
    session.flush()

    response = client.post("/demo/reset")
    assert response.status_code == 200, response.text
    assert response.json() == {"churches": [GRACE, RIVERSIDE]}

    session.expire_all()
    names = set(session.scalars(select(Person.name)))
    assert "Anna Parker" in names and "Somebody Else" not in names
    assert session.scalar(select(func.count()).select_from(Assignment))
    # Only what the seeds themselves log is left in the audit log.
    assert set(session.scalars(select(AuditLog.actor))) == {"seed"}
    briefing = client.get(f"/churches/{client.get('/churches').json()[0]['id']}/leaders").json()
    assert briefing


def test_the_audit_log_is_append_only_again_after_a_reset(
    client: TestClient, session: Session, demo_on: None
) -> None:
    assert client.post("/demo/reset").status_code == 200
    church = session.scalars(select(Church)).first()
    assert church is not None
    session.add(AuditLog(church_id=church.id, actor="seed", action="test", target_type="test"))
    session.flush()
    for statement in (
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
        "UPDATE audit_log SET actor = 'x'",
    ):
        with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
            session.execute(text(statement))
