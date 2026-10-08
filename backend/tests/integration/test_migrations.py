"""Migrations apply cleanly, match the models, and fully reverse."""

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.db.models  # noqa: F401
from app.db.base import Base
from tests.conftest import alembic_config, database_url_for, recreate_database


def test_upgrade_downgrade_upgrade_and_no_drift() -> None:
    url = database_url_for("shepherd_test_migrations")
    recreate_database(url)
    config = alembic_config(url)
    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        tables = set(inspect(engine).get_table_names())
        assert set(Base.metadata.tables) <= tables

        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"models and migrations differ: {diff}"

        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}

        command.upgrade(config, "head")
        assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
