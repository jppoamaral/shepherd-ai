# Shepherd

Church volunteer coordination app. Shepherd helps ministry leaders lead the people who serve: one record of who serves where across all ministries, roster suggestions (training and veteran paths), early warnings to the right leader, leader memory (with consent), and a conflict huddle between two leaders.

**Core rule: Shepherd suggests, a person decides.** Nothing is recorded or sent until a leader approves.

**Source of truth: `docs/PROJECT_BRIEF.md`.** Read it before starting any milestone. If a request conflicts with it, ask. Architecture decisions live in `docs/adr/`.

## Stack (decided; do not change without asking)

- **Backend:** Python 3.12, FastAPI, Pydantic v2
- **Database:** PostgreSQL 16 (Docker), SQLAlchemy 2.x typed ORM, Alembic migrations
- **Agents:** one worker process with APScheduler (nightly and per-cycle jobs); on-request agents are triggered by the API
- **Roster solver:** Google OR-Tools CP-SAT
- **Language model:** Azure OpenAI via the official `openai` SDK, behind a small `LLMClient` interface, with `FakeLLM` for tests. Structured outputs (JSON schema / Pydantic) for every model call.
- **Frontend:** Angular PWA in `/frontend` (later milestone; placeholder for now). The API publishes OpenAPI so a TypeScript client can be generated.
- **Tooling:** uv (deps), ruff (lint + format), mypy (strict on `app/domain` and `app/services`), pytest
- **Local first:** docker-compose for Postgres, API and worker; settings in `.env` (see `.env.example`). Azure deployment comes later; add no cloud resources yet.
- **Channels:** `ChannelAdapter` interface + `CopyPasteChannel` (renders approved messages as a list). Telegram comes later.

## Architecture rules (non-negotiable; enforce in code and tests)

1. **Proposals and approval.** Agents never write to the record or send messages. They create `Proposal` rows (type, JSON payload, status pending/approved/rejected, created_by_agent). `ApprovalService` is the ONLY code that applies a proposal's side effects, and it writes an `AuditLog` entry every time. A test fails if any module under `app/agents` imports the repositories that write assignments or messages.
2. **Rules decide truth; the model handles language.** Conflicts, gaps, load counts, overlaps and draft eligibility are deterministic code. The model only parses free text, matches/suggests names, classifies replies, writes explanations and drafts messages, working only from facts passed to it.
3. **Multi-tenant from day one.** Every table has `church_id`; every query is scoped by it.
4. **Time.** `GatheringType` stores a recurrence in the church's time zone; concrete `Gathering` rows have timezone-aware start/end. Overlap checks use real start/end on any day of the week.
5. **Privacy.** No field stores legal/background-check, health, family or pastoral information. The memory module rejects such content before proposing a memory. Messages are 1:1 only; no endpoint returns one person's serving data to a group.
6. **Membership is an input.** No code path adds, removes or moves a person between ministries.
7. **Experience per role** (new / experienced / veteran) is set only by a leader, never computed.
8. **Load rules and preferences** come from the church profile (per church and per person). They produce warnings, never blocks.
9. **AuditLog is append-only.**

## Repo layout

```
/backend
  /app
    /api          FastAPI routers
    /domain       Pydantic models and enums (no I/O)
    /db           SQLAlchemy models, session, repositories
    /services     approval, checks, roster, memory, huddle, briefing
    /agents       onboarding, steward, weekly_check, roster, huddle (create Proposals only)
    /llm          LLMClient interface, AzureOpenAIClient, FakeLLM, prompts/
    /channels     ChannelAdapter, CopyPasteChannel (Telegram later)
    /solver       CP-SAT roster model
  /migrations     Alembic
  /seeds          synthetic data
  /tests          unit, integration, and /evals for model behavior
/frontend         Angular (placeholder for now)
/docs             PROJECT_BRIEF.md, adr/
docker-compose.yml, .env.example, CLAUDE.md
```

## Commands

Run from the repo root unless noted. (Established in Milestone 1; update this section if they change.)

| Task | Command |
| --- | --- |
| Start everything (db, migrate, seed, api, worker) | `docker compose up --build` |
| Install deps (local) | `cd backend && uv sync` |
| Run API locally | `cd backend && uv run uvicorn app.main:app --reload` |
| Run worker locally | `cd backend && uv run python -m app.worker` |
| Migrate | `cd backend && uv run alembic upgrade head` |
| New migration | `cd backend && uv run alembic revision --autogenerate -m "<msg>"` |
| Seed | `cd backend && uv run python -m seeds` |
| Test | `cd backend && uv run pytest` |
| Lint / format | `cd backend && uv run ruff check . && uv run ruff format .` |
| Type check | `cd backend && uv run mypy` |

Tests need Postgres running (`docker compose up -d db`). They create their own `shepherd_test` and `shepherd_test_migrations` databases, seed them with a fixed date (2026-10-08), and roll back each test.

Local setup on macOS: `brew install uv colima docker docker-compose`, then `colima start`. uv installs Python 3.12 itself.

## Gotchas

- **Alembic autogenerate and enums:** enum columns use `enum_column()` (text + CHECK, no native PG enums). Autogenerate emits each enum's CHECK twice, so the upgrade fails with DuplicateObject. After every autogenerate, run `uv run python migrations/fix_enum_checks.py migrations/versions/<new file>.py`. `test_migrations.py` fails if models and migrations drift.
- **Datetimes:** keep instants in UTC and convert to the church's zone only for display. Python compares and subtracts two datetimes that share a tzinfo by wall clock, ignoring DST offsets.
- **No auth yet:** endpoints are open and scoped only by `church_id` in the path. This is OK for synthetic local data; auth must land before any real church data.
- **Seeds are fixtures:** they write the record directly, standing in for an approved onboarding profile and roster history. App code must still go through proposals and ApprovalService.

## Working agreements

- Build **one milestone at a time** from section 10 of the brief. Start each with a short plan (files, models, endpoints, tests) and **wait for approval before coding**.
- Write tests alongside code. Section 11 of the brief is the acceptance checklist: turn each relevant row into a test.
- Small commits with clear messages.
- If the brief is ambiguous, ask instead of guessing.
