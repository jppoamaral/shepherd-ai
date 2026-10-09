# Shepherd

Church volunteer coordination app. Shepherd helps ministry leaders lead the people who serve: one record of who serves where across all ministries, roster suggestions (training and veteran paths), early warnings to the right leader, leader memory (with consent), and a conflict huddle between two leaders.

**Core rule: Shepherd suggests, a person decides.** Nothing is recorded or sent until a leader approves.
Clarified for volunteer chat: anything Shepherd *starts* (reminders, nudges) needs a leader's approval. The bot's direct replies to a volunteer's own message (thanks, one clarifying question, reading dates back) go out at once in fixed wording and never start a new ask. A volunteer's answer about herself (yes, can't make it, away dates, stop/start) is a proposal her own reply approves, applied by ApprovalService.

**Source of truth: `docs/PROJECT_BRIEF.md`.** Read it before starting any milestone. If a request conflicts with it, ask. Architecture decisions live in `docs/adr/`.

## Stack (decided; do not change without asking)

- **Backend:** Python 3.12, FastAPI, Pydantic v2
- **Database:** PostgreSQL 16 (Docker), SQLAlchemy 2.x typed ORM, Alembic migrations
- **Agents:** one worker process with APScheduler (nightly and per-cycle jobs); on-request agents are triggered by the API
- **Roster solver:** Google OR-Tools CP-SAT
- **Language model:** Azure OpenAI via the official `openai` SDK, behind a small `LLMClient` interface, with `FakeLLM` for tests. Structured outputs (JSON schema / Pydantic) for every model call.
- **Frontend:** Angular 22 in `/frontend` (standalone components, signals), styled only with the Claude Design tokens and `sh-*` classes in `frontend/design-system/` (read its `USAGE.md` and `screens/README.md` first). API types are generated from the backend's OpenAPI (`npm run api:types`). Runs on port 4300.
- **Tooling:** uv (deps), ruff (lint + format), mypy (strict on `app/domain` and `app/services`), pytest
- **Local first:** docker-compose for Postgres, API and worker; settings in `.env` (see `.env.example`). Azure deployment comes later; add no cloud resources yet.
- **Channels:** `ChannelAdapter` interface + `CopyPasteChannel` (renders approved messages as a list) + `SimulatorChannel` (the demo volunteer chat, standing in for Telegram). Each church picks one (`churches.channel`; `DEFAULT_CHANNEL` / `CHANNEL_BY_CHURCH` in `.env`); the seeds put Grace Community on the simulator. Inbound messages go through `services/inbound.py`, which Telegram will reuse. Telegram comes later.

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
/frontend         Angular 22 app (src/) built on the Claude Design system (design-system/)
/docs             PROJECT_BRIEF.md, adr/
docker-compose.yml, .env.example, CLAUDE.md
```

## Commands

Run from the repo root unless noted. (Established in Milestone 1; update this section if they change.)

| Task | Command |
| --- | --- |
| Start everything (db, migrate, seed, api, worker) | `docker compose up --build` |
| Fresh demo data (see `docs/demo.md`) | `docker compose down -v && docker compose up -d --build` |
| Frontend (Angular, port 4300) | `cd frontend && npm install && npm start` |
| Frontend build / API types | `cd frontend && npm run build` · `npm run api:types` (backend running) |
| Install deps (local) | `cd backend && uv sync` |
| Run API locally | `cd backend && uv run uvicorn app.main:app --reload` |
| Run worker locally | `cd backend && uv run python -m app.worker` |
| Migrate | `cd backend && uv run alembic upgrade head` |
| New migration | `cd backend && uv run alembic revision --autogenerate -m "<msg>"` |
| Seed | `cd backend && uv run python -m seeds` |
| Test | `cd backend && uv run pytest` (uses FakeLLM; evals excluded) |
| Model evals | `cd backend && uv run pytest -m eval tests/evals` (needs Azure OpenAI keys; skipped otherwise) |
| Onboarding chat (terminal) | `cd backend && uv run python -m app.cli.onboard` (API must be running) |
| Schedule intake (try it) | `http://localhost:8000/docs` → `POST /churches/{id}/ministries/{id}/intake` as the ministry's scheduler, then answer the questions and approve the proposal |
| Lint / format | `cd backend && uv run ruff check . && uv run ruff format .` |
| Type check | `cd backend && uv run mypy` |

Tests need Postgres running (`docker compose up -d db`). They create their own `shepherd_test` and `shepherd_test_migrations` databases, seed them with a fixed date (2026-10-08), and roll back each test.

Local setup on macOS: `brew install uv colima docker docker-compose`, then `colima start`. uv installs Python 3.12 itself.

## Language model

Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` (a model with structured outputs) and optionally `AZURE_OPENAI_API_VERSION`. Put them in `backend/.env` for local runs and the repo-root `.env` for docker compose; both are gitignored. Without them, chat endpoints return 503 and evals skip. Tests never call the real model: they inject `FakeLLM` (`app/llm/fake.py`). Prompts live in `app/llm/prompts/`. Evals are run several times before a prompt change is trusted, since model output varies; when an eval flakes, fix the cause (a missing fact such as today's date, an ambiguous field) rather than loosening the check.

## Planned work (beyond the brief's milestones)

- **Onboarding UX pass** (after M3; raised by the user after the M2 demo).
  Root causes from the user's real session (the roles topic, a Youth/Kids/Media/Worship church):
  1. **Clarifications throw information away.** When the model asks a clarifying question, nothing from that answer is applied, and the next turn only sees the last question. So "3 volunteers, 1 leader, 2 worship volunteers" was lost, and the agent asked the same thing four times. Fix:
     - Apply what is clear even while asking about the rest.
     - Keep the current topic's recent exchange as context within the session; it's discarded when the topic is confirmed, so no transcript is stored long term.
  2. **The admin's model doesn't fit ours.** Kids is organized by age groups (2 helpers each for ages 2–4, 5–7, 7–9 and 10–12, plus 2 overseers). The agent forced it into "gathering name", asked a confusing question, and saved nothing. Fix: treat age groups or classes as roles (e.g. "Helper, ages 2–4"), and propose that mapping back to the admin in plain words.
  3. **All ministries at once.** "That's all" was refused because Kids, Media and Worship had no roles yet, and the reply was an error dump. Fix:
     - Ask roles one ministry at a time.
     - Say which ministry is next.
     - Never answer "that's all" with a list of errors.
  4. **Questions in system terms** ("minimum number required for each role at the Youth Group gathering"). Fix: ask the way a leader thinks ("How many people do you need for Youth Group, and doing what?").

  Other known weak spots:
  - **Reads like a form:** 10 fixed topics in order, with long paragraph questions.
  - **The "that's all" loop:** a section isn't confirmed unless the admin says it's done, so the agent repeats itself.
  - **Walls of text:** the post-sample reply and the review summary are long bullet dumps.
  - **Raw sample guesses:** every gathering defaults to 90 minutes, and names are copied as written ("WORSHIP", "keys").
  - **Heavy roles question:** it asks for every role and minimum at every gathering at once.
  - **Going back is awkward:** an earlier section can only be changed from the review step.
  - **Bare terminal client:** no progress indicator ("step 4 of 10") and no hints.

  Directions:
  - Shorter, warmer replies, possibly written by the model from the structured facts (code still decides).
  - Show progress.
  - Treat a complete answer as confirmed.
  - Ask roles one ministry at a time.
  - Sensible defaults to confirm (e.g. a 60-minute Sunday service).
  - Tidy names from samples.
  - A proper UI once the Angular app exists.
- **Adding people and memberships** (deferred from M3): intake can't add new people, so unknown names are matched to an existing team member or left out.

## Gotchas

- **Alembic autogenerate and enums:** enum columns use `enum_column()` (text + CHECK, no native PG enums). Autogenerate emits each enum's CHECK twice, so the upgrade fails with DuplicateObject. After every autogenerate, run `uv run python migrations/fix_enum_checks.py migrations/versions/<new file>.py`. `test_migrations.py` fails if models and migrations drift.
- **Datetimes:** keep instants in UTC and convert to the church's zone only for display. Python compares and subtracts two datetimes that share a tzinfo by wall clock, ignoring DST offsets.
- **No auth yet:** endpoints are open and scoped only by `church_id` in the path. This is OK for synthetic local data; auth must land before any real church data.
- **Personal reasons:** a volunteer's reason for not serving is passed to her leader once as a `LeaderNotice` (deleted on dismiss, never audited) and stored nowhere else. Her own chat messages are never stored; the simulator keeps them in the browser, as Telegram would.
- **Seeds are fixtures:** they write the record directly, standing in for an approved onboarding profile and roster history. App code must still go through proposals and ApprovalService.

## Working agreements

- Build **one milestone at a time** from section 10 of the brief. Start each with a short plan (files, models, endpoints, tests) and **wait for approval before coding**.
- Write tests alongside code. Section 11 of the brief is the acceptance checklist: turn each relevant row into a test.
- Small commits with clear messages.
- If the brief is ambiguous, ask instead of guessing.
