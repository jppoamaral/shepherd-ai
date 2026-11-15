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
| Ask Shepherd: conversational interface, placed under Home in the nav | `Ask-Mobile.dc.html` (conversation), `Ask-Start-Mobile.dc.html` (first visit, suggested questions) | `Ask-Desktop.dc.html` (conversation plus Try asking and What Shepherd looked at) | `Ask-Limits-Mobile.dc.html` (can't help with personal details, thinking, failed request) |
| Rosters: Training roster vs Veteran roster | `Roster-Mobile.dc.html` (swipeable tabs) | `Roster-Desktop.dc.html` (two columns) | `Roster-Edit-Mobile.dc.html` (editing, swap list, Approve roster), `Roster-Loading-Mobile.dc.html` (drafting) |
| Conflict huddle | `Huddle-Mobile.dc.html` (pick a time) | `Huddle-Desktop.dc.html` (full flow) | `Huddle-Done-Mobile.dc.html` (time confirmed, agenda, record what you decided) |
| Memory | `Memory-Mobile.dc.html` | `Memory-Desktop.dc.html` | Pending memory suggestion sits at the top of the list |

Navigation: bottom tab bar on mobile (Home, Rosters, People, Memory, Settings; the Ask screens show a sixth tab, Ask, right after Home; the older screens have not been updated to show it yet), left sidebar on desktop, and a ministry switcher in the header. People and Settings are not designed yet.

## Behavior shown in the mockups

- Roster tabs switch between Training and Veteran. "Choose this roster" opens the editable view. Nothing is saved until "Approve roster".
- Home cards link to the right place: the conflict card to the huddle, the memory suggestion to Memory.
- Huddle: choose one of three time slots (radio group), confirm, then record what was decided. The record button stays disabled until an option is picked. The volunteer involved is never invited.
- Resolve (Kids suggestion card): one tap accepts Shepherd's Kids suggestion (Rachel takes Anna's place) and closes the conflict without a huddle, so Worship is never told. It is a leader action and still needs approval before anything is recorded. The huddle path (pick a time, meet) stays available beside it.
- Failed send: one failed reminder shows "Not sent" with Try again and Copy reminder; the rest are listed as sent.

## Ask Shepherd behavior

- The leader types a question in their own words, or taps a suggested question. Answers come back as short messages with real data (people, rosters, availability) and a "From ..." source line so the leader can check them.
- Any action becomes a draft or a proposal, never a done deal: "Draft · not sent", then Review and send. Nothing is sent or recorded until the leader approves.
- Questions about health, family or personal reasons get "Can't help with that" and an offer of what Shepherd can show instead (for example, availability).
- States: thinking (role="status" with pulsing skeleton), failed request (role="alert", Try again, question is kept), first visit (suggested questions).
- Answers only cover the leader's own ministry. Never return one person's serving data to a group.

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

## Volunteer side (chat bot, not the Angular app)

Volunteers never install an app or log in. Everything happens in a private 1:1 chat with the Shepherd bot (Telegram first). The `Vol-*.dc.html` files are 390px chat mockups for the bot's messages, in a generic chat frame. Use them for wording and flow in the bot and `ChannelAdapter` code, not for Angular screens.

| Flow | File |
|---|---|
| Connecting the first time | `Vol-01-Connect.dc.html`; two people match the name: `Vol-01b-Connect-Check.dc.html` |
| Serving reminder | with buttons `Vol-02-Reminder.dc.html`, after Yes `Vol-02b-Reminder-Yes.dc.html`, without buttons `Vol-02c-Reminder-Text.dc.html` |
| Declining with a personal reason | `Vol-03-Decline.dc.html` |
| Away dates | `Vol-04-Blockout.dc.html` |
| Vague reply | `Vol-05-Vague.dc.html` |
| Sharing a preference | `Vol-06-Preference.dc.html` |
| "What do you remember about me?" | `Vol-07-What-I-Know.dc.html` |
| Stop | `Vol-08-Stop.dc.html` |
| Plain text fallback sent by a leader | `Vol-09-Text-Fallback.dc.html` |
| A week of messages | `Vol-10-Week.dc.html` |

Bot rules:
- Short, warm, plain. At most one emoji, usually none. Never pushy, never guilt. Never asks why someone can't serve.
- Every button is numbered, so typing 1 or 2 works the same as tapping. Without buttons, add one line: "Reply 1 = yes, 2 = can't make it."
- Never guess identity. If a name matches more than one person, the leader confirms.
- Record availability only. A personal reason is passed to the leader as said and is not stored, asked about, or mentioned again.
- One clarifying question at most. "Maybe" is never recorded as yes.
- Away dates are saved only after the volunteer confirms them.
- "What do you remember" shows only what the volunteer said themselves.
- "stop" ends reminders and tells the leader; "start" turns them back on.
- Keep the rhythm light: one reminder, one confirmation, no follow-ups after an answer.
