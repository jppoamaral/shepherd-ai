"""Architecture rules enforced by static checks over the source tree."""

import ast
import re
from pathlib import Path

import app.db.models  # noqa: F401  (registers every table)
from app.db.base import Base

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Rule 1: agents read through `reads` and write only Proposals.
AGENT_ALLOWED_APP_IMPORTS = (
    "app.db.repositories.reads",
    "app.db.repositories.proposals",
    # Agents' own working state (onboarding draft, schedule intake), not the record.
    "app.db.repositories.onboarding",
    "app.db.repositories.intake",
    "app.domain",
    "app.llm",
    "app.config",
)
AGENT_FORBIDDEN_PREFIXES = ("app.db", "app.services.approval", "app.channels")

# Rule 1: only ApprovalService may import the record-writing repositories and the
# proposal handlers that apply side effects.
WRITE_REPOSITORIES = (
    "app.db.repositories.assignments",
    "app.db.repositories.messages",
    "app.services.profile_apply",
    "app.services.roster_apply",
    "app.services.memory_apply",
    "app.services.huddle_apply",
    "app.services.reminders_apply",
    "app.services.reply_apply",
    "app.services.serve_ask_apply",
)
# ApprovalService, and the handlers it calls, which write through the repositories.
WRITE_REPOSITORY_IMPORTERS = {
    "app.services.approval",
    "app.services.roster_apply",
    "app.services.huddle_apply",
    "app.services.reminders_apply",
    "app.services.reply_apply",
    "app.services.serve_ask_apply",
}


def module_name(path: Path) -> str:
    parts = path.relative_to(APP_DIR.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported_modules(source: str, module: str) -> set[str]:
    """Every module a source file imports, with relative imports resolved."""
    found: set[str] = set()
    package = module.split(".")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join([*package[: len(package) - node.level], base]).strip(".")
            found.add(base)
            # `from app.db.repositories import assignments` imports a submodule.
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def agent_violations(source: str, module: str) -> list[str]:
    bad = []
    for imported in imported_modules(source, module):
        if imported.startswith(AGENT_ALLOWED_APP_IMPORTS):
            continue
        if imported.startswith(AGENT_FORBIDDEN_PREFIXES):
            bad.append(imported)
    return sorted(bad)


def python_files(package: str) -> list[Path]:
    return sorted((APP_DIR / package).rglob("*.py"))


def test_agents_never_import_record_writers() -> None:
    files = python_files("agents")
    assert files, "app/agents should exist"
    violations = {module_name(f): agent_violations(f.read_text(), module_name(f)) for f in files}
    assert {m: v for m, v in violations.items() if v} == {}


def test_agent_import_check_catches_direct_writes() -> None:
    """Guard the guard: the check must flag the imports an agent would need to write."""
    module = "app.agents.roster"
    assert agent_violations("from app.db.repositories.assignments import AssignmentWriter", module)
    assert agent_violations("from app.db.repositories import messages", module)
    assert agent_violations("from ..db.repositories.assignments import AssignmentWriter", module)
    assert agent_violations("from app.db.models import Assignment", module)
    assert agent_violations("from app.db.session import get_sessionmaker", module)
    assert agent_violations("import app.services.approval", module)
    assert agent_violations("from app.channels.copy_paste import CopyPasteChannel", module)
    assert not agent_violations(
        "from app.db.repositories.proposals import ProposalRepository", module
    )
    assert not agent_violations("from app.db.repositories.reads import ChurchReader", module)


def test_only_approval_service_imports_write_repositories() -> None:
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        module = module_name(path)
        if module in WRITE_REPOSITORIES or module in WRITE_REPOSITORY_IMPORTERS:
            continue
        imports = imported_modules(path.read_text(), module)
        if any(i.startswith(WRITE_REPOSITORIES) for i in imports):
            offenders.append(module)
    assert offenders == []


# Rule 5: no column anywhere for legal/background, health, family or pastoral data.
FORBIDDEN_COLUMN_WORDS = re.compile(
    r"health|medical|diagnos|illness|disab|allerg|background|clearance|criminal|legal"
    r"|compliance|family|spouse|marital|child_of|pastoral|counsel|prayer_request|religio",
)


def test_no_column_stores_private_categories() -> None:
    offenders = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if FORBIDDEN_COLUMN_WORDS.search(column.name)
    ]
    assert offenders == []


def test_blockouts_have_no_reason_field() -> None:
    columns = set(Base.metadata.tables["blockouts"].columns.keys())
    assert not columns & {"reason", "note", "notes", "why", "details"}


# Rule 3: every table is owned by a church.
def test_every_table_has_church_id() -> None:
    missing = [
        name
        for name, table in Base.metadata.tables.items()
        if name != "churches" and "church_id" not in table.columns
    ]
    assert missing == []


# Rule 6: membership is an input. Application code never creates, updates or deletes one.
def membership_writes(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        args = [a.id for a in node.args if isinstance(a, ast.Name)]
        if name == "Membership":
            found.append("Membership(...)")
        elif name in {"insert", "update", "delete"} and "Membership" in args:
            found.append(f"{name}(Membership)")
    return found


def test_no_application_code_writes_memberships() -> None:
    offenders = {
        module_name(p): w
        for p in APP_DIR.rglob("*.py")
        if not module_name(p).startswith("app.db.models")
        and (w := membership_writes(p.read_text()))
    }
    assert offenders == {}


def test_membership_write_check_catches_writes() -> None:
    assert membership_writes("session.add(Membership(person_id=p, ministry_id=m))")
    assert membership_writes("session.execute(update(Membership).values(ministry_id=x))")
    assert membership_writes("session.execute(delete(Membership))")
    assert not membership_writes("session.scalars(select(Membership))")
