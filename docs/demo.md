# Shepherd demo

Synthetic data only. No login yet: the app picks "who am I" from the leaders list.

## Run it

```
docker compose down -v && docker compose up -d --build   # fresh demo data + API on :8000
cd frontend && npm install && npm start                  # app on http://localhost:4300
```

Reset the data (first command) before presenting: approving, recording a huddle or
deleting a memory changes the record. Port 4300 is used because 4200 belongs to another
local project; CORS allows both.

Seeds are relative to today. The **demo week** starts at the first upcoming Sunday; in it, at **Grace Community**:

| Story | What the seed sets up | Who is warned |
| --- | --- | --- |
| **Double booking across ministries** | Anna Parker is on Kids (Helper) and Worship (Keys) at the same Sunday 9:30 service | Sarah Collins (Kids) and David Morales (Worship) |
| **Overloaded volunteer** | Anna Parker serves 4 times that week; she prefers 2, and Grace warns above 2 | The approvers of Kids and Worship (Sarah, David) |
| **Midweek double booking** | Hannah Wright sings at Wednesday Prayer Night (7:00–8:15 PM) and runs sound at Wednesday Youth (7:30–9:00 PM) | David (Worship), and Tom Becker / Mike Harris (Media) |
| **Conflict huddle** | Sarah and David are both free Saturday 9:30/10:00–11:30/12:00 | They get 3 Saturday slots before Sunday |
| **No common time** | David and Tom share no window | The huddle says so and lists the nearest options |
| **Memory** | Kids: "You always pair Emily with Rachel.", "Emily prefers the 9:30 service." Worship: "Keep the band together for a whole month." | Pending: "Should I remember this? 'Rachel is ready to lead a class.'" |
| **A real gap** | Media's Youth roster has Sound but no Slides | Tom (Media scheduler) |
| **Reminders** | The worker drafts one reminders proposal per ministry and service for the coming week (Kids 9:30: Anna, Emily, Rachel, Megan) | The ministry's approver, on Home ("Review and send") |
| **Volunteer chat** | Grace sends through the demo chat simulator (`churches.channel = simulator`); Riverside uses the copy-paste list | Each volunteer, 1:1 |
| **Someone away** | Olivia Grant, a veteran Kids helper, is blocked out on the demo Sunday (no reason is stored) | Ask Shepherd leaves her out of cover suggestions and says so |

## Demos

Each demo starts from fresh data (reset first) with **Sarah Collins** picked on "Who's leading
today?".

**Order matters: Demos 1, 2 and 4 all use Anna Parker's Sunday double booking.** Resolve in
Demo 1, or Anna declining in Demo 4, takes her off the Kids roster. After that, Ask Shepherd no
longer offers "Who can take Anna's place?", and Sarah's reminders leave her out. For one
continuous run, do **Demo 2, then Demo 3** (Resolve, then Undo, leaves the record as it was),
**then Demo 4**. Reset before **Demo 1**. Anna's Worship place is untouched either way: as
**David Morales**, sending Worship reminders still reaches her chat. Dates below assume the demo Sunday is Oct 11; the app always shows the real dates.
Generated volunteers' names (Caleb Baker, Anna Peterson, …) can differ from these notes, and
that's fine: every answer comes from the data.

### Demo 1: Sarah's week, start to finish (5 minutes)

The main story: one double booking found days ahead, settled by the leaders, nothing sent
without approval.

1. **Home** (Kids): "2 things need you this week". The **shared volunteer** card (Anna Parker
   on Kids and Worship at the same 9:30 service) and the **good to know** card (Anna serving 4
   times, above her preferred 2). Point out "Shepherd won't move anyone" and the approval
   queue on the right.
2. Click **Find a time to talk**. Three Saturday slots that suit both Sarah and David, one
   suggested replacement per side, and "Anna isn't invited. This is a talk between leaders."
3. Two ways to settle it (pick one live):
   - **Resolve** on the Kids suggestion: one tap puts the suggested helper in Anna's place on
     Kids. "… is in Anna's place. Worship wasn't told." It went through the approval queue and
     the audit log; nobody was messaged. Show **Undo**, then Resolve again.
   - Or the huddle path: pick a time, **Confirm time**, **Record what you decided**. Shepherd
     moves nobody.
4. **Rosters**: Shepherd's suggested roster grouped by service, a reason on every line (Emily
   is at 9:30 because she prefers it). Beside it, this week as planned. After Resolve, Anna's
   Kids place shows the new helper. **Choose this roster**, swap someone, **Approve roster**.
5. **Memory**: confirmed memories by kind; **Remember** "Rachel is ready to lead a class."
   Type a note with a health detail ("she just had surgery"): Shepherd refuses to keep it.

### Demo 2: Ask Shepherd (2 to 3 minutes)

A leader asks in their own words and gets answers from the record, with the source shown.
Suggested questions work without the language model; typed questions need the Azure keys.

1. Open **Ask Shepherd** (second in the nav). "Hi Sarah. What can I help with?" with
   suggestions built from this week's data.
2. Tap **Who can take Anna's place on Oct 11?** Free Kids helpers with their experience,
   "Olivia can't make Oct 11, so I left them out." and the closest fit. On desktop, **What
   Shepherd looked at** lists the sources. Shepherd never says why Olivia is away; it doesn't
   know.
3. Tap **Draft a message to Caleb** (or whoever is suggested): "Draft · not sent" with
   **Send to Caleb**, Edit and Copy. Nothing goes out until Sarah taps Send; that tap is her
   approval (a proposal, applied and audited by ApprovalService). Open Caleb's phone (**Show a
   volunteer's chat**): the ask arrives with **Yes, I can** / **No, sorry**. Tap Yes: Sarah's
   Home shows "Caleb Baker can serve Sun Oct 11 at 9:30 AM (Kids, Helper)" with **Put Caleb
   in**. His yes changes nothing; the roster changes only when she taps it. Someone who isn't
   connected to chat gets no Send button, only Copy.
4. Type **anyone serving too much lately?** (the model reads the question): Anna, 4 times this
   week, prefers 2 a week.
5. Type **Why is Olivia taking time off?** "Can't help with that … That's Olivia's to share."
   It offers **Check Olivia's availability** instead: blocked out Oct 11, "I only keep the
   dates, never the reasons." This refusal happens in code, before the model sees the question.
6. Optional: **Open the huddle** from the answer in step 2 jumps straight into Demo 1's huddle.

### Demo 3: The boundaries, in one minute

For a question like "what stops it from overstepping?":

1. **Ask Shepherd**: "Is Emily sick?" is refused (health), and "Why is Olivia taking time
   off?" is refused (personal reasons).
2. **Memory**: a health note is refused before it becomes a suggestion.
3. **Huddle → Resolve → Undo**: every change to the record is a proposal a leader approves,
   with an audit entry; the other leader and the volunteer are never messaged.
4. **Switch leader** to David Morales: he sees only Worship's side, plus both double bookings
   that involve Worship (Anna on Sunday, Hannah on Wednesday). Mike Harris (Media and
   Hospitality) sees only Hannah's. Ask Shepherd as David answers about Worship's team only.

### Demo 4: the volunteer's side (3 minutes)

Volunteers never use the app; in real life this is their Telegram chat with Shepherd. The
simulator stands in for Telegram. Open it beside Sarah's Home: on desktop, **Show a
volunteer's chat (demo)** at the bottom of the sidebar opens Anna's phone on the right; or
open "See what volunteers get" on "Who's leading today?" in a second window.

1. Sarah's **Home**: "4 reminders ready for Sunday 9:30 Service". **Review and send** shows
   each 1:1 message; **Send 4 reminders**. Nothing went out before this.
2. Anna's phone (within 2 seconds): "Hi Anna! You're scheduled in Kids this Sunday, Oct 11,
   at 9:30, as Helper. Can you make it?" with **1 Yes, I'll be there** / **2 I can't make it**.
3. Tap **I can't make it**. The buttons go away, her answer shows as her message, and
   Shepherd replies "Thank you for letting me know. I've told your leader you can't make
   Oct 11." Her answer is recorded as a proposal she approved herself (audit log).
4. Sarah's Home updates by itself: "Anna Parker can't make Sun Oct 11 (Kids, Helper)", the
   double booking is gone, and an **Open slot** offers a free helper: **Put Caleb in**. One tap
   records it.
5. Optional, typed in Anna's (or Emily's) chat:
   - "2 — my mom is in the hospital." Sarah sees the note once, with "It isn't kept:
     dismissing deletes it." Shepherd never asks why and stores the reason nowhere else.
   - "maybe, depends on work": one clarifying question, **Can't commit** / **I'll let you
     know**. Never recorded as a yes.
   - "I'm out the 19th and the 26th.": read back with **1 Yes / 2 Change**; saved only on Yes.
   - "What do you remember about me?": only her teams, her stated preference and her away
     dates; never leader notes or memory.
   - "stop" / "start": reminders off and on; her leader is told.
   - "hi" or "When am I serving?" (on any volunteer's phone, even before a reminder): a
     greeting by name with three option buttons, or her places for the next 4 weeks from
     approved rosters. A place caught in an open double booking is left out ("Your leaders
     will confirm Wed Oct 14 with you."), as on Hannah's phone. An unclear message gets
     different wording the second time, with buttons, so the bot never repeats itself.

Reset before presenting. Anna's own messages are kept in the browser per person, and a
reset gives everyone new ids, so her phone starts clean; **Clear Anna's side of this demo
chat** under the phone is there for a rerun without a reset.

### What is sample content

On Home, the absence check-in and the "people aren't connected yet" notice are **fixed
sample content**; those come in later milestones. Reminders are real: drafted by the worker,
sent only on approval.
Ask Shepherd's drafts are real text from the roster, sent only when the leader taps Send.
"Draft a reminder" sends real reminders (1/2 answers work); Home's reminder card then leaves
out anyone already reminded.

## API map for the frontend

Base URL `http://localhost:8000`. CORS allows `http://localhost:4300` (the app) and `:4200`. OpenAPI is at `/openapi.json`, and an interactive version at `/docs`.

| Screen | Calls |
| --- | --- |
| Who am I | `GET /churches`, `GET /churches/{cid}/leaders` |
| Weekly briefing | `GET /churches/{cid}/leaders/{person_id}/briefing?start=YYYY-MM-DD` |
| Rosters | `GET /churches/{cid}/ministries/{mid}/suggestion`, `POST …/suggestion/approve {person_id, assignments}`, `GET /churches/{cid}/ministries/{mid}/roster?start=&end=` |
| Conflict huddle | `POST /churches/{cid}/findings/{finding_id}/huddle {person_id}`, `GET /churches/{cid}/huddles/{id}`, `POST …/huddles/{id}/choose {person_id, slot_id}`, `POST …/huddles/{id}/resolve {person_id, outcome}`, `POST …/huddles/{id}/accept-replacement {person_id, ministry_id}` (Resolve), `POST …/huddles/{id}/undo-replacement {person_id}` |
| Volunteer chat (demo) | `GET /churches/{cid}/volunteers`, `GET /churches/{cid}/people/{pid}/chat` (Shepherd's side), `POST …/people/{pid}/chat {text}` (her message; the same handling Telegram will use) |
| Reminders and notices | `POST /churches/{cid}/ministries/{mid}/reminders/draft`, approve through the approval queue; `GET /churches/{cid}/leaders/{pid}/notices`, `DELETE /churches/{cid}/notices/{id}?person_id=` |
| Ask Shepherd | `GET /churches/{cid}/ministries/{mid}/ask?person_id=` (greeting and suggestions), `POST …/ask {person_id, question}` or `{person_id, intent, about_person_id?, on?, role_id?}`, `POST …/ask/send {person_id, drafts}` (Send: the leader's approval) |
| Memory | `GET /churches/{cid}/ministries/{mid}/memory`, `POST …/memory/notes {person_id, text, kind?, about_person_id?}`, `DELETE …/memory/{id}?person_id=` |
| Approval queue | `GET /churches/{cid}/proposals?status=pending` (each has `title` and `summary`), `POST …/proposals/{id}/approve` or `/reject` with `{person_id}` |
| (Also available) | Onboarding chat `POST /onboarding`, schedule intake `POST /churches/{cid}/ministries/{mid}/intake`; both need Azure OpenAI keys |

Everything in this table except onboarding, intake and typed Ask questions is deterministic and needs no model, so the demo can't be derailed by it. Without Azure keys, a typed Ask question gets "I can only answer the suggested questions right now" and the suggestions still work.
