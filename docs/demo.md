# Shepherd demo

Synthetic data only. No login yet: the app picks "who am I" from the leaders list.

## Reset to a fresh demo

```
docker compose down -v && docker compose up -d --build
```

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

## Suggested script (5 minutes)

1. **Sarah's weekly briefing:** two warnings, Anna's double booking and Anna's overload.
2. Tap **Find a time to talk** on the double booking. Sarah and David are offered Saturday slots, with a neutral agenda: the overlap, plus one suggested replacement from each leader's own team. Anna isn't invited.
3. **Choose a slot**, then **resolve** with the leaders' decision. Checks re-run; Shepherd reassigns nobody.
4. **Kids roster:** Anna is flagged `double_booked` and `over_load`, with experience levels shown.
5. **David's briefing** also shows Hannah's Wednesday clash, flagged the same way as a Sunday conflict.
6. **Memory:** confirmed Kids memories, plus a pending "Should I remember this?". Try adding a note with a health detail: it's refused (privacy).
7. **Approval queue:** approve the memory. Nothing is saved until a person approves, and every decision is in the audit log.

## API map for the frontend

Base URL `http://localhost:8000`. CORS allows `http://localhost:4200`. OpenAPI is at `/openapi.json`, and an interactive version at `/docs`.

| Screen | Calls |
| --- | --- |
| Who am I | `GET /churches`, `GET /churches/{cid}/leaders` |
| Weekly briefing | `GET /churches/{cid}/leaders/{person_id}/briefing?start=YYYY-MM-DD` |
| Rosters | `GET /churches/{cid}/ministries`, `GET /churches/{cid}/ministries/{mid}/roster?start=&end=` |
| Conflict huddle | `POST /churches/{cid}/findings/{finding_id}/huddle {person_id}`, `GET /churches/{cid}/huddles/{id}`, `POST …/huddles/{id}/choose {person_id, slot_id}`, `POST …/huddles/{id}/resolve {person_id, outcome}` |
| Memory | `GET /churches/{cid}/ministries/{mid}/memory`, `POST …/memory/notes {person_id, text, kind?, about_person_id?}`, `DELETE …/memory/{id}?person_id=` |
| Approval queue | `GET /churches/{cid}/proposals?status=pending` (each has `title` and `summary`), `POST …/proposals/{id}/approve` or `/reject` with `{person_id}` |
| (Also available) | Onboarding chat `POST /onboarding`, schedule intake `POST /churches/{cid}/ministries/{mid}/intake`; both need Azure OpenAI keys |

Everything in this table except onboarding and intake is deterministic and needs no model, so the demo can't be derailed by it.
