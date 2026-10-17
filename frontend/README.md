# Shepherd frontend

Angular 22 app for leaders (standalone components, signals). It's built from the Claude Design
system in `design-system/`: tokens, the `sh-*` component styles, and the approved screen mockups
in `design-system/screens/`. Read `design-system/USAGE.md` first. For the whole project, see the
[root README](../README.md).

```
npm install
npm start            # http://localhost:4300 (port 4200 is used by another local project)
npm run build
npm run api:types    # regenerate src/app/api/schema.ts from the running backend's OpenAPI
```

The backend must be running (`docker compose up -d` at the repo root). After a backend schema
change, rebuild the API (`docker compose up -d --build api worker`), then run `npm run api:types`.

## GitHub Pages

The production build uses bundled synthetic data, so the demo works on GitHub Pages without a
FastAPI server. Local development uses the FastAPI API by default. The repository workflow
`.github/workflows/deploy-pages.yml` builds the app and publishes it at:

`https://jppoamaral.github.io/shepherd-ai/`

Enable **Settings → Pages → Source: GitHub Actions** once in the repository settings. The
published demo uses hash-based routes so deep links work on a static Pages host. It stores
interactive demo changes in the browser only; no real church or volunteer data is sent anywhere.

## Screens

There is no sign-in yet. Leaders are demo data with fictional names.

| Route | Screen |
| --- | --- |
| `/pick` | "Who's leading today?": choose a leader |
| `/` | Home: the weekly briefing, notices from volunteers and the approval queue |
| `/ask` | Ask Shepherd: questions answered from the record, with drafts the leader can send |
| `/rosters` | Suggested rosters next to this week as planned |
| `/memory` | What Shepherd remembers for the ministry, and pending memories |
| `/huddle/:findingId` | The conflict huddle between two leaders |
| `/demo/volunteers`, `/demo/chat/:personId` | The volunteer chat simulator (stands in for Telegram) |

How to walk through them: [docs/demo.md](../docs/demo.md).

## Code

- `src/app/api/`:
  - `ApiService`, one typed method per endpoint;
  - `types.ts`;
  - the generated `schema.ts` (don't edit it by hand).
- `src/app/core/`: the session (the chosen leader and ministry) and formatting helpers.
- `src/app/shell/`: the navigation (sidebar on desktop, tab bar on phone).
- `src/app/ui/`: small shared pieces (icons, experience badge).
- `src/app/pages/`: one folder per screen.

Everything on screen comes from the API, except one card marked `SAMPLE` in the code: the
absence check-in on Home, which the backend doesn't produce yet.
