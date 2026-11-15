# Shepherd MVP Plan

Written 2026-11-14. This is the working plan from here until the MVP is shown at university. Any model or person picking up the work should read this, then `CLAUDE.md` (rules and commands), then `docs/PROJECT_BRIEF.md` (the product). Where this plan narrows the brief's scope, this plan wins for the MVP. The reasons are in `docs/adr/0002-mvp-deploy-and-scope.md`.

## Goal

A **simple, working MVP** to show professors, online at a public URL:

- **Frontend** (Angular) on **Vercel**. Vercel rewrites `/api/*` to the backend, so no CORS setup is needed. This is the same pattern as the Alo MVP.
- **Backend** (FastAPI) and **Postgres** on **Render**'s free plan, defined in one `render.yaml` Blueprint.
- **Synthetic data only.** There is no login: the "Who's leading today?" picker stays, with a demo banner.

## Status at the start of this plan

**Built and tested** (57 commits, 234 tests):

- Data model and two seeded churches
- Onboarding (backend and terminal CLI)
- Schedule intake
- Overlap, load and below-minimum checks with private briefings
- One roster suggestion (greedy drafter, hard rules kept, a reason on every line)
- ApprovalService and the audit log
- Reminders, and volunteer replies through the chat simulator
- Ask Shepherd
- Memory notes with the privacy guard
- The conflict huddle with Resolve and Undo

**Angular pages:** Home, Ask, Rosters, Memory, Huddle, the volunteer list and the volunteer chat.

**Known gaps:**

- Approving a roster doesn't re-run the checks.
- The blockout and absence checks are missing.
- Home shows a hard-coded absence card (`frontend/src/app/pages/home/home.ts:62-72`, `home.html:113-127`).
- People and Settings are dead nav items.
- There is no deployment config.

## Decisions

| Topic | MVP decision |
| --- | --- |
| Volunteer channel | The existing chat page (`SimulatorChannel`), entered from the demo list of volunteers. **No Telegram, no personal links.** |
| Rosters | **One suggestion, from the existing greedy drafter** (`services/drafting.py`). No training or veteran paths, and no CP-SAT. |
| Onboarding | **Later phase.** The backend and CLI stay as they are; there is no UI. |
| Database | Render free Postgres. **It expires 30 days after creation**, so recreate it shortly before the presentation. |
| Worker | Free Render has no background workers, so the scheduler runs inside the API process (`RUN_SCHEDULER=true`). `app/worker.py` stays for docker-compose. |
| Auth | None, because the data is synthetic. Real auth must land before any real church data. |

## Out of the MVP (later phases)

| Left out | Why it's safe |
| --- | --- |
| Telegram, real login | The simulator and the picker cover the demo. |
| Training and veteran paths, CP-SAT, special-first, the one-path setting | One suggestion is enough. The greedy drafter keeps every hard rule. |
| Memory learned from edits, memories shaping suggestions | Leader notes, the privacy guard and delete already show the idea. |
| Shared flag across two *draft* rosters | Overlaps on real rosters are caught, and the huddle covers them. |
| Whole-ministry-silent check, failed-send card | No channel can fail in the MVP, and the silent check needs history the demo lacks. |
| People and Settings screens, onboarding UI | Not designed yet. The seeds stand in for an approved profile. |

---

## Working agreements

- **One phase at a time.** Start each phase with a short plan (files, models, endpoints, tests) and **wait for the user's approval before coding**.
- **Phase 1 is behavior-preserving.** Run the full suite after each numbered step, and commit each step on its own.
- **Phase 2 features land with tests.** Use the matching row of brief §11 where one exists.
- **The non-negotiables in `CLAUDE.md` always hold:**
  - Agents and services only *propose*, and `ApprovalService` alone applies changes and writes the audit log.
  - Every query is scoped by `church_id`.
  - No personal reasons, health, family or legal data are stored.
  - Experience is set only by leaders.
  - Membership is an input.
- **When the brief or this plan is unclear, ask.**
- **After every phase, all of these must be green:**
  - `cd backend && uv run pytest && uv run ruff check . && uv run mypy`
  - `cd frontend && npm run build`

---

## Phase 0: Plan and docs (done with this file)

- [x] Write this `Plan.md`.
- [x] Write `docs/adr/0002-mvp-deploy-and-scope.md`.
- [x] Update `CLAUDE.md`: point to this plan and note the stack changes for the MVP.
- [x] Fix the stale "people aren't connected" line in `docs/demo.md`.

## Phase 1: Focused cleanup (no behavior change) — done 2026-11-14

Done on the `mvp-cleanup` branch, one commit per step. What the next phases can rely on:

- **Proposal types and payloads:** `ProposalType` in `app/domain/enums.py`; one payload model per type in `app/domain/proposals.py` (`PAYLOADS` maps type to model). `ProposalRepository.create` takes the model. A new proposal type needs an enum value, a payload model and a handler in `approval.HANDLERS`; `tests/unit/test_proposals.py` fails if one is missing.
- **Handlers describe themselves:** `ProposalHandler.describe` (names come from `app/services/names.py`).
- **Leader checks:** `is_ministry_leader` and `ministries_led` in `app/db/repositories/reads.py`.
- **A tap that is the approval:** `approval.propose_and_approve`.
- **Ask Shepherd:** the package `app/services/ask/` (`intents`, `queries`, `send`). Notice helpers are in `app/services/notices.py`, chat reads in `app/services/chat.py`, wording helpers in `app/services/text.py`.
- **API:** shared dependencies in `app/api/deps.py`. Service errors become HTTP in `app/api/errors.py`, which also rolls the request back; routers don't catch them.
- **Architecture test:** only named modules may write the audit log or notices, and routers import no writing repository.
- **Frontend:** Home's cards are `notice-card`, `finding-card` and `proposal-card` in `pages/home/`; Ask's draft is `pages/ask/ask-draft.ts`.

**Left open for the user:** deleting a memory (`services/memory.py: delete_memory`) writes its own audit entry instead of going through a proposal. The architecture test allows it by name. Making it a proposal would change the audit entry's action, so it was not done in a no-behavior-change phase.

The steps, as planned:

This gives clean seams before new features. The steps are ordered by value, and each is a separate commit.

1. **Add a `ProposalType` StrEnum and typed payloads.**
   - Add `ProposalType` to `app/domain/enums.py` and replace the bare type strings everywhere. Known duplicates:
     - `"church_profile"` in `app/agents/onboarding.py` and `app/services/profile_apply.py`
     - `"leader_roster"` in `roster_apply.py`, `agents/steward.py` (`ROSTER_PROPOSAL`) and as a bare string in `suggestion.py`
     - the constants re-exported from `memory.py`, `reminders.py`, `serve_ask.py`, `huddle_replacement.py` and `reply_types.py`
   - Add one Pydantic payload model per type, following `ChurchProfileDraft`, which already works this way. Build the payloads at the call sites:
     - `ask.py`, `huddle.py`, `memory.py`, `put_in.py`
     - `reminders.py`, `suggestion.py`, `steward.py`, `inbound.py`
   - Read them with `Model.model_validate(proposal.payload)` in the `*_apply.py` handlers and `proposal_text.py`, instead of `payload["..."]`.
   - Leave the stored JSON shape unchanged, so no migration is needed.
2. **Handlers describe their proposals.**
   - Add `describe: Callable[[Session, Proposal], ProposalText]` to `ProposalHandler` in `app/services/approval.py`.
   - Move each branch of `app/services/proposal_text.py` into its handler.
   - `proposal_text.py` becomes a lookup.
3. **Write one leader-permission helper.**
   - Add `is_ministry_leader(session, church_id, ministry_id, person_id, *, can_schedule=None, can_approve=None)` in `app/db/repositories/reads.py`.
   - Replace the nine hand-written checks:
     - `reads.py` (~216)
     - `api/chat.py` (~145, ~190)
     - `services/memory.py` (~66, `is_leader`)
     - `reminders_apply.py` (~29)
     - `huddle_apply.py` (~43)
     - `huddle.py` (~319)
     - `roster_apply.py` (~42)
     - `briefing.py` (~89)
4. **Split the god modules.**
   - `app/services/ask.py` (about 1,166 lines) becomes a package, `app/services/ask/`:
     - `__init__.py` re-exports the public API, so routers don't change
     - `intents.py` holds the intent handlers
     - `queries.py` holds the record reads
     - `send.py` holds `send_drafts`
   - `app/services/inbound.py` (about 922 lines): move the leader-notice helpers (`notice_settled`, `notice_put_in`, `swap_from` and friends, from about line 816 on) to `app/services/notices.py`. Update the imports in `put_in.py` and `api/chat.py`.
   - Move the shared text helpers (`_short` and `_and` from `ask.py` and `inbound.py`, `_day` and `_count` from `ask.py`) into `app/services/text.py`.
5. **Add one create-and-approve helper.**
   - `approval.propose_and_approve(session, church_id, type, payload, actor_id)` for the "the tap is the approval" cases.
   - Use it in `put_in.py` and in `inbound._approve` (about line 681).
6. **Tidy the API layer.**
   - Move `SessionDep` and `ReaderDep` to `app/api/deps.py`. Today they are imported from `routes.py`, and `chat.py` imports from `ask.py`.
   - Register one FastAPI exception handler in `app/main.py` that maps `app/services/errors.py` (NotFound → 404, NotAllowed → 403, ApprovalError → 409 or 422, keeping today's codes) to HTTP, with rollback.
   - Remove the copied try/except blocks from `chat.py`, `proposals.py`, `suggestion.py`, `ask.py` and `onboarding.py`.
   - Move `api/chat.py`'s direct `select(...)` queries and its dismiss permission check into services (`notices.py`).
7. **Widen the architecture test** in `tests/unit/test_architecture.py`.
   - Add the `notices` and `audit` repositories to `WRITE_REPOSITORIES`.
   - Add `profile_apply` and `memory_apply` to `WRITE_REPOSITORY_IMPORTERS`.
   - Fix any violations this exposes, e.g. `services/memory.py` writing audit directly on delete. Route it through the approval or audit path, or allow it explicitly with a comment explaining why.
8. **Split the frontend, lightly.**
   - Home (`pages/home/`, about 470 lines) gets notice, finding and proposal card components.
   - Ask (`pages/ask/`, about 430 lines) gets message and draft components.
   - Keep using only the `sh-*` classes and the design tokens.

**Do not** move the proposal-creating services into `app/agents/`. The approval rule already holds and is tested.

**Done when:** every test passes unchanged (except import paths), ruff, mypy and the frontend build are green, and a manual run of Demos 1, 2 and 4 behaves as before.

## Phase 2: Finish the MVP features — done 2026-11-14

Done on the `mvp-cleanup` branch, one commit per step. How it differs from the steps written below:

- **Check before approval (step 1):** a separate `POST …/suggestion/check` returns what the edited roster would newly flag (`checks_runner.preview_checks`, which saves nothing). `…/suggestion/approve` is unchanged. The Rosters page calls the check on the first press of Approve and shows "Approve anyway" / "Keep editing". `roster_apply.apply` re-runs the checks over the days it touched.
- **Blockout check (step 2):** `checks.blockouts`, in `CHECKED_TYPES`, routed to the scheduler.
- **Absence check (step 3):** the user chose to **work out "last served" and write nothing**. There is no nightly "served" job and no system approval. `services/absence.py` takes the latest past assignment that wasn't declined, or `Membership.last_served` (set by seeds or a profile). It skips people with no serving on record and people already on a coming roster. `POST /churches/{cid}/findings/{id}/answer`: `still_here` dismisses the finding until the person serves and goes quiet again; `later` sets `Membership.asked_at` and asks again after 4 weeks. The seeded card is **Olivia Grant** (Kids), not Hannah, who isn't on Kids.
- **Volunteer chat (step 5):** only two wording fixes were needed. Two design screens have no flow and were left for later: Vol-05's "Check Friday" button (Shepherd would start a follow-up) and Vol-06 (a volunteer stating how often they'd like to serve).
- **Repo (step 6):** design screens committed; `shepherd-design-brief/` is in `.gitignore`.

The steps as planned:

1. **Approving a roster re-runs the checks** (brief §11: "Leader edits a draft and creates a conflict").
   - `POST /churches/{cid}/ministries/{mid}/suggestion/approve` first returns the findings the edited roster *would* create. Use a check-only pass of the pure functions in `services/checks.py` on the proposed assignments plus the existing ones.
   - The Rosters page shows those warnings on the approve step. The leader can still approve, because warnings never block.
   - After approval, `roster_apply.apply` calls `run_checks`, so Home updates.
   - Tests: an edit that double-books someone is flagged before approval, and the finding exists after approval.
2. **Blockout check.**
   - Add a pure check in `services/checks.py` for an assignment on a person's blockout date.
   - Add it to `CHECKED_TYPES` in `checks_runner.py`, routed to the ministry's scheduler (defaults in `domain/profile.py` ~125-130).
   - Show it in the briefing (`services/briefing.py`) and on Home.
   - Unit and integration tests.
3. **Absence check, and recording who served.**
   - **Recording who served:**
     - The nightly job (`worker.extend_gatherings`) marks past approved or confirmed assignments as served and updates `Membership.last_served`.
     - It goes through a proposal approved by a system actor via `propose_and_approve`, so it is audited.
     - **Ask the user before building** whether this fits the core rule ("recording what already happened" isn't Shepherd starting something).
   - **The finding:** an absence finding for active members whose `last_served` is older than `Church.absence_threshold_weeks`, sent to the approver only once (don't re-raise a dismissed one).
   - **Seeds:** give Hannah, or another volunteer, a past history so the demo card is real.
   - **Home:** replace the hard-coded sample card with this finding. "Yes, still on the team" dismisses it; "Ask me later" snoozes it. Neither one changes membership.
4. **Remove the remaining sample content.**
   - Remove `showSamples` and the sample card from `home.ts` and `home.html`.
   - Remove the fixed sentence appended to the overload card (`home.html` ~82), or move that wording to the backend.
   - Hide the People and Settings nav items in `shell/shell.ts`.
5. **Polish the volunteer chat.**
   - Compare `pages/demo/chat.ts` and the bot wording in `services/inbound.py` against `frontend/design-system/screens/Vol-01…Vol-10*.dc.html`.
   - Fix gaps in wording and buttons only. Add no new flows.
6. **Clean up the repo.**
   - Commit the untracked design screens: `Ask-*`, `Vol-*`, and the Huddle, README and canvas changes in `frontend/design-system/screens/`.
   - Ask the user whether `shepherd-design-brief/` (the pitch deck) should go into `.gitignore`.

**Done when:**
- The new tests pass.
- Home shows no fixed sample content.
- An edited roster with a conflict warns before approval.
- Sarah's Home shows a real absence card.

## Phase 3: Deploy (Vercel + Render) — code done 2026-11-14; dashboards pending

The code is on the `mvp-cleanup` branch and was checked locally (the image run with `start.sh`, `postgres://`, `$PORT`, `RUN_SCHEDULER` and `DEMO_MODE`; the demo build; a reset end to end). What is left is done by the user in the Render and Vercel dashboards, following the README section "Online demo (Vercel + Render)"; then check the "Done when" list against the live URLs.

How it differs from the steps written below:

- **Demo reset and the audit log:** `audit_log` has a trigger that rejects TRUNCATE. The user chose to lift it for the reset only: `services/demo.py` switches the trigger off and on inside the reset's transaction. This is the one written exception to rule 9 (ADR 0002, `CLAUDE.md`).
- **Scheduler:** `app/scheduler.py` builds it; the start-up run is a one-off job, so start-up and `/health` don't wait for it. `worker.run_nightly(session)` is the job without the commit, shared with the reset.
- **Demo build:** a `demo` configuration in `angular.json`, used as `ng build --configuration production,demo` (`npm run build:demo`). `npm run build` still targets `localhost:8000`.
- **`CORS_ORIGINS` is not in `render.yaml`:** the browser only talks to Vercel, which forwards `/api/*`, so no cross-origin call happens.

The steps as planned:

### Backend on Render

**`render.yaml` at the repo root** (a Blueprint):

- **Database:** a `databases:` entry, `shepherd-db`, on the free plan.
- **Web service:**
  - `shepherd-api`, `runtime: docker`
  - `dockerfilePath: ./backend/Dockerfile`, `dockerContext: ./backend`
  - `plan: free`, `healthCheckPath: /health`
  - `autoDeploy: true`
- **Environment variables:**

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | `fromDatabase` |
| `RUN_SCHEDULER` | `true` |
| `DEMO_MODE` | `true` |
| `CORS_ORIGINS` | the Vercel URL, as a JSON list |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` | `sync: false`, pasted in the dashboard |

**Backend changes:**

- **`app/config.py`:**
  - Normalize `postgres://` and `postgresql://` to `postgresql+psycopg://` (Render hands out `postgres://`).
  - Add the `run_scheduler` and `demo_mode` settings.
- **`backend/start.sh`:** `alembic upgrade head && python -m seeds && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`. The seeds are idempotent.
- **`backend/Dockerfile`:** run `start.sh` and add a non-root user. docker-compose keeps its own commands.
- **Scheduler inside the API:**
  - With `run_scheduler` on, start an APScheduler `BackgroundScheduler` in the FastAPI lifespan in `app/main.py`.
  - It runs `worker.extend_gatherings` once at startup, which also covers waking from sleep, then nightly at 02:00 UTC.
  - Shut it down when the app stops.
- **Demo reset:**
  - With `demo_mode` on, `POST /demo/reset` truncates every table except `alembic_version`, re-runs the seeds and runs `extend_gatherings`.
  - The seeds are relative to today, so the demo week is always upcoming.
  - Tests: 404 with the flag off; with it on, the data comes back.

### Frontend on Vercel

**Project setup:** Root Directory `frontend`.

**Production build:**
- `src/environments/environment.prod.ts` with `apiUrl: '/api'` and `demo: true`
- a `fileReplacements` entry in `angular.json`
- a `build:demo` npm script

**`frontend/vercel.json`:**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "installCommand": "npm ci",
  "buildCommand": "npm run build:demo",
  "outputDirectory": "dist/<app-name>/browser",
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://shepherd-api-9wtg.onrender.com/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ],
  "headers": [
    { "source": "/(.*)", "headers": [
      { "key": "X-Content-Type-Options", "value": "nosniff" },
      { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
      { "key": "X-Frame-Options", "value": "SAMEORIGIN" }
    ]}
  ]
}
```

- Check `<app-name>` in `angular.json`.
- Shepherd's API has no `/api` prefix, so the rewrite strips it.
- `X-Frame-Options` must be **SAMEORIGIN, not DENY**, because the shell embeds the volunteer chat in an iframe.

**Frontend changes:**
- **"Waking up Shepherd…" notice:** when the first API call takes more than about 3 s (Render cold start, about a minute).
- **"Reset demo data" button** on the picker page, shown only when `environment.demo` is on.

**Docs:**
- An "Online demo (Vercel + Render)" section in `README.md`:
  1. Push to GitHub.
  2. Render → New → Blueprint.
  3. Check `/health`.
  4. Fix the API URL in `vercel.json` if Render gave a different one.
  5. Vercel → import → Root Directory `frontend`.
- State the free-tier limits: the API sleeps after 15 minutes, and the database expires after 30 days.

**Done when:**
- `https://shepherd-api-9wtg.onrender.com/health` answers.
- The Vercel URL loads the picker.
- Reset works.
- Demo 1 runs online.

## Phase 4: Demo readiness

- **Rewrite `docs/demo.md` for the online URL**, in this order:
  1. Reset.
  2. Demo 1, Sarah's week.
  3. Demo 2, Ask Shepherd.
  4. Demo 4, the volunteer's side.
  5. Demo 3, the boundaries, kept as a backup for questions.
- **Rehearsal checklist:**
  - Wake the API about 2 minutes before.
  - Reset the data.
  - Check the Azure keys, or use only the suggested questions.
  - Use a desktop, plus a phone for the volunteer chat.
- **Walk the whole demo once** in Chrome against the deployed site, and fix what breaks.

---

## Later phases (after the MVP, in suggested order)

1. **Onboarding UX pass and onboarding UI.** The root causes are listed in `CLAUDE.md` under "Planned work".
2. **Roster paths.** Training and veteran paths side by side, special gatherings first, the one-path setting. Move to CP-SAT (`app/solver/`) if the greedy drafter gets too limited.
3. **Memory.** Edit detection (the same change twice becomes a proposal). Confirmed memories shape suggestions and are named in their reasons.
4. **More checks.**
   - The shared flag across draft rosters
   - The whole-ministry-silent check
   - The failed-send card in the briefing
5. **People and Settings screens.** Adding people and memberships.
6. **Real auth** before any real church data, then **Telegram** through `ChannelAdapter`, then **Azure** deployment.

## Verification (every phase)

- **Backend:** `cd backend && uv run pytest && uv run ruff check . && uv run mypy`
- **Frontend:** `cd frontend && npm run build`; run `npm run api:types` after any backend schema change.
- **Local end to end:** `docker compose down -v && docker compose up -d --build`, then `cd frontend && npm start`, and walk Demos 1, 2 and 4 from `docs/demo.md` in Chrome.
