"""Demo reset (ADR 0002): put the synthetic data back as the seeds make it.

Only reachable with `DEMO_MODE=true`, on deployments that hold synthetic data
and nothing else. It empties every table, the audit log included, so it must
never be enabled where a real church's data lives.

The audit log is append-only (rule 9): a database trigger rejects UPDATE,
DELETE and TRUNCATE. The reset is the one written exception (ADR 0002). It
switches that trigger off, empties the tables and switches it back on, all in
the caller's transaction, so a failure rolls back with the guard in place.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base
from app.worker import run_nightly
from seeds import seed_all


def reset_demo(session: Session, today: date | None = None) -> list[str]:
    """Empty the database, reload the seeds and run the nightly job. No commit.

    `today` is for tests; without it each church is seeded for its own local date.
    """
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
    session.expire_all()
    churches = list(seed_all(session, today))
    session.flush()
    run_nightly(session)
    return churches
