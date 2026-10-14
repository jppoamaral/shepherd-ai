# Shepherd

Shepherd helps church ministry leaders lead the people who serve. It keeps one record of who
serves where across all ministries, suggests rosters, warns the right leader early, remembers
what a leader tells it (with consent), and sets up a conflict huddle when two leaders need the
same person. Leaders use a mobile-first web app with **Ask Shepherd**, a chat that answers from
the record. Volunteers only get 1:1 chat messages.

**Shepherd suggests, a person decides.** Nothing is recorded or sent until a leader approves.
In code, agents only create proposals, and `ApprovalService` is the only place a proposal takes
effect. Every approval is written to an append-only audit log.

## Quick start

Needs Docker (on macOS: `brew install colima docker docker-compose && colima start`) and Node.

```
cp .env.example .env
docker compose up -d --build        # Postgres, migrations, demo seeds, API on :8000, worker
cd frontend && npm install && npm start   # app on http://localhost:4300
```

- There is no sign-in yet. Pick a leader on the first screen (start with **Sarah Collins**, Kids).
- The volunteer side (a chat simulator standing in for Telegram) is at
  http://localhost:4300/demo/volunteers.
- API docs: http://localhost:8000/docs.
- Fresh demo data: `docker compose down -v && docker compose up -d --build`.

The demo scripts are in [docs/demo.md](docs/demo.md).

### Language model (optional)

Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_DEPLOYMENT` (a model with
structured outputs) in `.env`, and also in `backend/.env` for local runs. Without them:
- suggested questions and buttons still work;
- typed questions in Ask Shepherd get "I can only answer the suggested questions right now";
- the onboarding chat returns 503.

Tests never call the real model.

## Development

| Task | Command |
| --- | --- |
| Install backend deps | `cd backend && uv sync` |
| Tests (needs `docker compose up -d db`) | `cd backend && uv run pytest` |
| Model evals (needs Azure keys) | `cd backend && uv run pytest -m eval tests/evals` |
| Lint / format | `cd backend && uv run ruff check . && uv run ruff format .` |
| Type check | `cd backend && uv run mypy` |
| Run API / worker locally | `uv run uvicorn app.main:app --reload` · `uv run python -m app.worker` (in `backend/`) |
| Migrate | `cd backend && uv run alembic upgrade head` |
| New migration | `uv run alembic revision --autogenerate -m "<msg>"`, then `uv run python migrations/fix_enum_checks.py migrations/versions/<file>.py` |
| Seed | `cd backend && uv run python -m seeds` |
| Frontend build | `cd frontend && npm run build` |
| Regenerate API types (backend running) | `cd frontend && npm run api:types` |

Tests create their own databases and seed them with a fixed date (2026-10-08).

## Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 and Alembic on PostgreSQL 16
- **Worker:** APScheduler, running a nightly job that adds upcoming gatherings, runs the checks and drafts reminders
- **Roster solver:** Google OR-Tools CP-SAT
- **Language model:** Azure OpenAI with structured outputs, behind `LLMClient` (`FakeLLM` in tests)
- **Frontend:** Angular 22, styled with the Claude Design system in `frontend/design-system/`
- **Channels:**
  - a copy-paste list;
  - the demo chat simulator (Grace Community uses it);
  - Telegram, later.
- **Tooling:** uv, ruff, mypy, pytest

## Repo layout

```
backend/
  app/
    api/        FastAPI routers
    domain/     Pydantic models and enums
    db/         SQLAlchemy models, session, repositories
    services/   approval, checks, roster, memory, huddle, briefing, ask, inbound chat
    agents/     create proposals only
    llm/        LLMClient, Azure client, FakeLLM, prompts
    channels/   copy-paste and simulator channels
    solver/     CP-SAT roster model
  migrations/   Alembic
  seeds/        synthetic churches (Grace Community, Riverside Fellowship)
  tests/        unit, integration, evals
frontend/       Angular app (see frontend/README.md)
docs/           project brief, demo guide, ADRs
```

## Docs

- [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md): the source of truth for what Shepherd does
- [docs/demo.md](docs/demo.md): the demo scripts, the seeded stories and the API map
- [docs/adr/](docs/adr/): architecture decisions
- [frontend/README.md](frontend/README.md): the Angular app
- [frontend/design-system/USAGE.md](frontend/design-system/USAGE.md): how the design system is used
- [CLAUDE.md](CLAUDE.md): architecture rules and working agreements for Claude Code

## Status

This is a local prototype.
- All data is synthetic, and the names are fictional.
- There is no authentication yet, so don't load real church data.
- Telegram and the Azure deployment come later.
- Shepherd stores no health, family, pastoral or background-check information. A volunteer's
  reason for not serving is passed to their leader once, then deleted.
