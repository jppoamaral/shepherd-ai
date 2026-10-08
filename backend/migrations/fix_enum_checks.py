"""Remove the duplicate enum CHECK constraints Alembic autogenerate emits.

Usage: uv run python migrations/fix_enum_checks.py migrations/versions/<file>.py

`enum_column()` enums render both as `sa.Enum(..., create_constraint=True)` and as
explicit CheckConstraints (one bare-named, one `op.f("ck_...")`). The naming
convention maps the bare name onto the same constraint, so the upgrade fails with
DuplicateObject. Keep only the `op.f(...)` copy.
"""

import re
import sys
from pathlib import Path

BARE_NAMED_CHECK = re.compile(
    r"\n\s*sa\.CheckConstraint\(\s*(['\"])(?:(?!\1).)*\1,\s*name=(['\"])[a-z_]+\2,?\s*\),"
)


def main(path: str) -> None:
    file = Path(path)
    source = file.read_text().replace("create_constraint=True", "create_constraint=False")
    source, removed = BARE_NAMED_CHECK.subn("", source)
    file.write_text(source)
    print(f"removed {removed} duplicate enum CHECK constraint(s)")


if __name__ == "__main__":
    main(sys.argv[1])
