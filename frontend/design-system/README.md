Shepherd helps a church ministry leader lead the volunteers who serve. It keeps one honest record of who serves where, suggests rosters, warns the right leader early, and learns each leader's habits. The product rule shapes every screen: **Shepherd suggests, the leader decides.** Nothing is recorded or sent until a leader approves. Volunteers never use the app.

## Content fundamentals

- Speak like a helpful colleague, never an alarm. Short, warm, plain. "Kids Ministry: 3 things need you this week." "All clear for this week."
- Say what is true and what the leader can do. "Oct 19 Assistant: no one free on your team." not "Roster incomplete."
- Name people by first and last name on first mention, first name after. Use "you" for the leader, never "the user".
- Buttons say what will happen: Approve roster, Review and send, See options, Find a time to talk, Yes, Ask me later, Remember, Not now. Never "Submit" or "OK".
- Every Shepherd suggestion is labeled as one ("Suggestion", "Memory suggestion"). Anything that could send or record says so plainly: "Nothing is sent until you approve."
- Say what Shepherd will not do, quietly: "Shepherd won't contact Hannah." "The volunteer isn't invited."
- Never store or mention health, family or personal reasons: "Shepherd never stores health, family or personal reasons."
- No exclamation marks, no emoji, no urgency words. Sentence case everywhere. All names in examples are fictional.

## Visual foundations

- **Color.** Page on `cream`, cards on `paper`, quiet panels on `sage`, structure and primary actions in `forest`. Body text is `ink`; secondary lines, reasons and captions are `ink-muted`, never lighter. `gold` is an accent used once per screen at most: the suggestion spark and the New badge. Never use `gold` as text or as a thin line (2.2:1 on cream); `gold-deep` is the readable gold. `gold-soft`, `forest-deep`, `forest-mid` and `sage-deep` are supporting tones from the pitch deck.
- **Status is never color alone.** Every status pairs an icon and a word (Badge, status tags, InlineFlag, Notice). Use `status-attn-*` for heads-ups, `status-ok-*` for confirmed, `status-alert-*` only for a failure such as a reminder that did not send.
- **Type.** Headings and people's names in EB Garamond (`t-display`, `t-h1`, `t-h2`, `t-h3`); everything else in DM Sans (`t-body` 16/24, `t-body-sm`, `t-label`, `t-caption`). Both load from Google Fonts. Body text is 16px on phone; nothing is smaller than 12px (`t-caption`, `ink-muted` or stronger).
- **Shape.** Rounded and soft: cards `radius-lg`, rows and notices `radius-md`, inline flags `radius-sm`, buttons, badges, tags and chips `radius-pill`. Cards sit on cream with a `line` hairline and `shadow-card`; no heavy shadows, no gradients.
- **Space.** Phone screens have a `space-4` gutter, cards are `space-3` apart, sections `space-6`. Anything tapped is at least `tap-min` (44px) high and wide, with thumb-reachable actions at the bottom of a card.
- **Focus.** A solid 3px `focus` ring with a 2px offset (forest on light surfaces, gold on forest).
- **Motion.** Almost none. The loading skeleton pulses gently and stops when reduced motion is requested.

## Layout

Design phone first at 390px (single column, bottom tab bar), then show desktop: a 240px sidebar (Navigation) and content at most 760px for a single column, or two equal columns (`.sh-cols`) where two paths sit side by side, such as the Training and Veteran rosters. On phone those two rosters become two swipeable Tabs.

## Screens, from these parts

- **Roster suggestions:** Tabs, RosterRow inside a card, InlineFlag, Button (Choose this roster, then Approve roster), Notice "Nothing is sent until you approve".
- **Weekly briefing and approval queue:** a `t-display` headline, BriefingCard for each item, QueueItem for reminders and Memory suggestion, Notice (info) for people not connected, States for empty and loading, Notice (error) for failed sends.
- **Conflict huddle:** who is involved and the gathering as plain rows; suggestions labeled with the Suggestion tag; TimeSlot chips; a confirmation card with a short neutral agenda; "Record what you decided" as a list of options.
- **Memory:** a pending Memory suggestion at the top, MemoryItem grouped by kind, the footer promise.

## Iconography

Simple 24px outline icons, 1.75px stroke, round caps, drawn in `currentColor`: check, alert, clock, users, spark, star, calendar, copy, send, pencil, trash, home, list, bookmark, gear, chevron. The icons here are a small hand-drawn set inline in each preview; swap for a licensed set with the same stroke weight if one is adopted. The spark is Shepherd's own mark for "a suggestion". No emoji.
