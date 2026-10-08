# ADR 0001: All-Python backend, Angular frontend, local Docker first

- **Status:** Accepted
- **Date:** 2026-10-08

## Context

Shepherd coordinates church volunteers across ministries. The backend has to do three quite different kinds of work:

1. A conventional multi-tenant record (churches, ministries, people, gatherings, assignments) with an approval queue and an append-only audit log.
2. Deterministic rules and constrained optimization: overlap and load checks, and roster drafting under hard rules (team membership, blockouts, no overlaps, role minimums) with weighed preferences.
3. Language work: parsing free-text schedules, matching names and nicknames, classifying volunteer replies, writing explanations and drafting messages, always from facts passed in and with structured output.

It is a prototype built by a small team, run locally first and deployed to Azure later. Leaders use a mobile-first web app; volunteers only get 1:1 chat messages.

## Decision

- **Backend: Python 3.12 only.** FastAPI + Pydantic v2 for the API (OpenAPI published for a generated TypeScript client); PostgreSQL 16 with SQLAlchemy 2.x typed ORM and Alembic migrations; one worker process running APScheduler for nightly and per-cycle agents, with on-request agents triggered by the API.
- **Roster solver: Google OR-Tools CP-SAT**, in-process.
- **Language model: Azure OpenAI** through the official `openai` SDK, wrapped in a small `LLMClient` interface so the provider can change, with a `FakeLLM` for tests. Every call uses structured outputs (JSON schema / Pydantic).
- **Frontend: Angular PWA** in `/frontend`, built in a later milestone.
- **Tooling:** uv, ruff, mypy (strict on domain and services), pytest.
- **Deployment: local Docker first** (docker-compose for Postgres, API, worker). Azure resources come later.
- **Channels:** a `ChannelAdapter` interface with a copy-paste channel first. **Telegram comes later**, after the Angular app.

## Consequences

**Positive**

- One language for API, rules, solver and model calls: shared Pydantic types flow from domain to API to structured LLM output with no translation layer.
- OR-Tools and the OpenAI SDK are first-class in Python.
- FastAPI's OpenAPI output gives the Angular app a typed client for free.
- Docker-first keeps onboarding to `docker compose up` and defers cloud cost and complexity.
- The `LLMClient` and `ChannelAdapter` seams keep Azure OpenAI and Telegram swappable and testable offline.

**Negative / risks**

- Two languages overall (Python + TypeScript); types cross the boundary only via generated OpenAPI clients, which must be regenerated when the API changes.
- CP-SAT solves are CPU-bound; long solves must run in the worker or a thread, not block API request handling.
- Python's typing is opt-in; we rely on mypy strict mode in the domain and services packages to keep it honest.
- Azure-specific deployment concerns (managed Postgres, secrets, scaling the worker) are deferred and will need their own ADR.

## Alternatives considered

- **TypeScript/Node backend** (shared language with Angular): weaker optimization and data tooling; CP-SAT bindings are not first-class.
- **Separate solver/LLM microservices:** unnecessary operational overhead for a prototype; the module boundaries (`/solver`, `/llm`) keep a later split possible.
- **Cloud-first deployment:** slows iteration and adds cost before the product is validated.
