"""Shared fixtures.

Integration tests run against a dedicated `shepherd_test` database on the compose
Postgres (`docker compose up -d db`). It is recreated, migrated and seeded once per
run with a fixed "today"; each test then runs inside a transaction that is rolled
back, so tests never see each other's writes.
"""

import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Church
from app.db.session import get_session
from app.main import app
from seeds import seed_all

BACKEND_DIR = Path(__file__).resolve().parents[1]
SEED_TODAY = date(2026, 10, 8)  # a Thursday; the next Wednesday is 2026-10-14
GRACE = "Grace Community"
RIVERSIDE = "Riverside Fellowship"


def database_url_for(name: str = "shepherd_test") -> str:
    return (
        make_url(get_settings().database_url)
        .set(database=name)
        .render_as_string(hide_password=False)
    )


def recreate_database(url: str) -> None:
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    name = make_url(url).database
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


def alembic_config(url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = database_url_for()
    recreate_database(url)
    command.upgrade(alembic_config(url), "head")
    engine = create_engine(url)
    with Session(engine) as session:
        seed_all(session, SEED_TODAY)
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def church_id(session: Session, name: str) -> uuid.UUID:
    cid = session.scalar(select(Church.id).where(Church.name == name))
    assert cid is not None, f"{name} not seeded"
    return cid


@pytest.fixture
def grace_id(session: Session) -> uuid.UUID:
    return church_id(session, GRACE)


@pytest.fixture
def riverside_id(session: Session) -> uuid.UUID:
    return church_id(session, RIVERSIDE)
