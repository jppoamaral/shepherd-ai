# Shepherd screen designs (reference for building the Angular app)

These are the approved screen mockups for the leader-facing app. They sit next to the design system (`../tokens.css`, `../components/`) and show how the pieces fit together on real screens. Read `../USAGE.md` first, then use these as the layout and copy reference.

Persona: Sarah Collins, Kids Ministry coordinator. All names and data are fictional.

## How to use these files

- Each `*.dc.html` is one screen at one width. They are readable HTML with inline styles. Open one in an editor to read the markup, copy, and spacing. They are design-tool files (they contain `<x-dc>`, `<helmet>` and a `support.js` reference), so they will not render correctly in a plain browser. Do not copy them into Angular as is.
- The mockups use raw hex values and pixel sizes. Build with the variables in `../tokens.css` and the `sh-*` classes in `../components/bundle.css` instead. Never hard-code a hex value in the app.
- `canvas.json` is the board layout from the design tool (position, size, title, which boards are interactive). It is useful as an index of what exists.
- Mobile first: 390px wide. Desktop boards are 1280px with a 240px left sidebar.
- If the app and a mockup disagree, ask the user. The mockups are the source of truth for layout and wording; `docs/PROJECT_BRIEF.md` is the source of truth for behavior.

## Screens

| Screen | Mobile | Desktop | Other states |
|---|---|---|---|
| Home: weekly briefing and approval queue | `Main.dc.html` | `Home-Desktop.dc.html` | `Home-Empty-Mobile.dc.html` ("All clear for this week"), `Send-Error-Mobile.dc.html` ("1 reminder didn't send. Try again or copy it.") |
| Rosters: Training roster vs Veteran roster | `Roster-Mobile.dc.html` (swipeable tabs) | `Roster-Desktop.dc.html` (two columns) | `Roster-Edit-Mobile.dc.html` (editing, swap list, Approve roster), `Roster-Loading-Mobile.dc.html` (drafting) |
| Conflict huddle | `Huddle-Mobile.dc.html` (pick a time) | `Huddle-Desktop.dc.html` (full flow) | `Huddle-Done-Mobile.dc.html` (time confirmed, agenda, record what you decided) |
| Memory | `Memory-Mobile.dc.html` | `Memory-Desktop.dc.html` | Pending memory suggestion sits at the top of the list |

Navigation: bottom tab bar on mobile (Home, Rosters, People, Memory, Settings), left sidebar on desktop, and a ministry switcher in the header. People and Settings are not designed yet.

## Behavior shown in the mockups

- Roster tabs switch between Training and Veteran. "Choose this roster" opens the editable view. Nothing is saved until "Approve roster".
- Home cards link to the right place: the conflict card to the huddle, the memory suggestion to Memory.
- Huddle: choose one of three time slots (radio group), confirm, then record what was decided. The record button stays disabled until an option is picked. The volunteer involved is never invited.
- Failed send: one failed reminder shows "Not sent" with Try again and Copy reminder; the rest are listed as sent.

## Rules the screens follow (keep them in code)

- Shepherd suggests, the leader decides. Nothing is recorded or sent until the leader approves, and every screen that proposes something says so.
- Status is never color alone: always an icon plus a word.
- Tap targets are at least 44px (`--tap-min`).
- Gold is a fill or decoration only; use `--gold-deep` for gold text.
- Real buttons and links, `aria-selected` / `aria-checked` / `aria-current` where they apply, `role="alert"` for the failed send, `role="status"` for loading progress, and a visible focus ring.
- Respect `prefers-reduced-motion` on the loading skeleton pulse.
- Voice: short, warm, plain. Shepherd talks like a helpful colleague, never like an alarm.
- Volunteers never use the app. Memory never stores health, family or personal reasons.

## Known quirks in the mockups

- The Home headline says "3 things need you" and counts the conflict, absence and gap cards. The overload card is marked "No action needed".
- Oct 12 is a Monday in 2026, so dates are written without weekdays. Huddle times (Tue 7:30 PM, Wed 12:15 PM, Thu 8:00 PM) are examples, not tied to a date.
- Lily Chen, Grace Lee, David Moore, Tom Ruiz and Priya Shah are invented fill-in names.
