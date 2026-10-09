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

## Suggested script (5 minutes, in the app)

1. Open http://localhost:4300 and pick **Sarah Collins** ("Who's leading today?").
2. **Home** (Kids): "2 things need you this week". The **shared volunteer** card (Anna Parker on Kids and Worship at the same time) and the **good to know** card (Anna serving 4 times, above her preferred 2). The approval queue shows reminders (sample), a **memory suggestion** and the unconnected-people notice (sample).
3. Click **Find a time to talk**. Sarah and David get three Saturday slots, Shepherd's suggested replacement for each side, and "Anna isn't invited". Pick a time, **Confirm time**, then **Record what you decided**. Shepherd moves nobody.
4. **Rosters**: Shepherd's suggested roster with a reason on every line (Emily is placed at 9:30 because she prefers it). Beside it, this week as planned, with Anna flagged double-booked and over load. **Choose this roster**, swap someone, **Approve roster**: it's recorded through the approval queue.
5. **Memory**: confirmed memories grouped by kind; **Remember** the pending suggestion. Type a note with a health detail ("she just had surgery"): Shepherd refuses to keep it.
6. **Switch leader** to David Morales: he sees both double bookings (Anna on Sunday, Hannah on Wednesday). Mike Harris (Media and Hospitality) only sees Hannah's.

On Home, the absence check-in, reminders, unconnected people and the failed send ("Review and send" shows it) are **fixed sample content**; those features come in later milestones.

## API map for the frontend

Base URL `http://localhost:8000`. CORS allows `http://localhost:4300` (the app) and `:4200`. OpenAPI is at `/openapi.json`, and an interactive version at `/docs`.

| Screen | Calls |
| --- | --- |
| Who am I | `GET /churches`, `GET /churches/{cid}/leaders` |
| Weekly briefing | `GET /churches/{cid}/leaders/{person_id}/briefing?start=YYYY-MM-DD` |
| Rosters | `GET /churches/{cid}/ministries/{mid}/suggestion`, `POST …/suggestion/approve {person_id, assignments}`, `GET /churches/{cid}/ministries/{mid}/roster?start=&end=` |
| Conflict huddle | `POST /churches/{cid}/findings/{finding_id}/huddle {person_id}`, `GET /churches/{cid}/huddles/{id}`, `POST …/huddles/{id}/choose {person_id, slot_id}`, `POST …/huddles/{id}/resolve {person_id, outcome}` |
| Memory | `GET /churches/{cid}/ministries/{mid}/memory`, `POST …/memory/notes {person_id, text, kind?, about_person_id?}`, `DELETE …/memory/{id}?person_id=` |
| Approval queue | `GET /churches/{cid}/proposals?status=pending` (each has `title` and `summary`), `POST …/proposals/{id}/approve` or `/reject` with `{person_id}` |
| (Also available) | Onboarding chat `POST /onboarding`, schedule intake `POST /churches/{cid}/ministries/{mid}/intake`; both need Azure OpenAI keys |

Everything in this table except onboarding and intake is deterministic and needs no model, so the demo can't be derailed by it.
