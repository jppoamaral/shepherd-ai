# ADR 0002: MVP on Vercel + Render, narrowed scope

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

Shepherd will be shown to university professors as a simple, working MVP at a public URL, using synthetic data only. ADR 0001 planned three things for that stage:
- local Docker first, then Azure
- a separate worker process
- CP-SAT roster drafting with training and veteran paths

Telegram was planned to follow the Angular app. Building all of this would delay a demo that doesn't need it. The working plan is in `Plan.md`.

## Decision

- **Deploy the MVP like the Alo MVP:**
  - The Angular frontend runs on **Vercel**, which rewrites `/api/*` to the backend.
  - The FastAPI backend runs on **Render** as a Docker web service on the free plan, with **Render free Postgres**.
  - Azure comes later.
- **Run the scheduler inside the API process** (`RUN_SCHEDULER=true`), because free Render has no background workers. The nightly job also runs at startup, which covers waking from sleep. `app/worker.py` stays the worker for docker-compose.
- **Add demo mode** (`DEMO_MODE=true`). It enables `POST /demo/reset`, which reloads the synthetic seeds.
  - **The one exception to the append-only audit log.** The reset empties every table, the audit log included. The database trigger that rejects changes to `audit_log` is switched off and back on inside the reset's own transaction (`services/demo.py`), so a failure leaves the guard in place. Nothing else may do this, and demo mode must never be on where real data lives.
- **Use one roster suggestion from the existing greedy drafter** (`services/drafting.py`). Training and veteran paths and CP-SAT move to a later phase. `app/solver/` stays empty until then.
- **No Telegram in the MVP.** Volunteers use the in-app chat (`SimulatorChannel`), entered from the demo list of volunteers.
- **No onboarding UI in the MVP.** The onboarding backend and terminal CLI stay.
- **No auth in the MVP.** This is acceptable only because all data is synthetic. Auth must land before any real church data.

## Consequences

**Positive**
- Free hosting. Every push to the main branch deploys.
- No CORS setup, thanks to the Vercel rewrite.
- A simpler roster story that already keeps every hard rule.

**Negative / risks**
- **Render's free tier:**
  - The API sleeps after 15 minutes, and the first request takes about a minute. The frontend shows a "waking up" notice.
  - Free Postgres expires 30 days after creation, so recreate it before the presentation.
- **The scheduler shares the API process.** That's fine for one instance; with several instances, it would need a lock or a separate worker again.
- **Parts of the brief are deferred:** §4 training and veteran paths, part of §6 (memory shaping suggestions), and some §5 checks. Their §11 rows stay without tests until the later phases.
