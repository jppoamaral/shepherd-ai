"""`python -m seeds`: load the synthetic churches into the configured database."""

from datetime import date

from app.db.session import get_sessionmaker
from seeds import seed_all


def main() -> None:
    with get_sessionmaker()() as session:
        results = seed_all(session, date.today())
        session.commit()
    for name, created in results.items():
        print(f"{name}: {'created' if created else 'already present, gatherings extended'}")


if __name__ == "__main__":
    main()
