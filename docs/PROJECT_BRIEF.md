# Shepherd — Project Brief

Oct 8, 2026 · @João Pedro

The single source of truth for building Shepherd. It replaces the Concept Brief where the two differ, and is written to hand to Claude Code.

## 1. What Shepherd Is

Shepherd helps church leaders lead the people who serve. It keeps one honest record of who serves where across all ministries, suggests rosters, warns the right leader early, and learns with each leader how to tend their team. Every roster and every message goes through a person first.

**Users:** ministry coordinators and leaders use a mobile-first web app or their chat. Volunteers only receive 1:1 messages: no app, no login. Pastors receive what the agent hands to a person.

**Principles every feature follows:**

1. **Suggest, never decide.** Shepherd drafts rosters, warnings, reminders and meetings. A leader chooses, edits and approves before anything is recorded or sent.
2. **Membership is an input.** Shepherd never adds, removes or moves anyone between ministries, and never invents roles.
3. **People and organization only.** Shepherd handles people, rosters and organization. Legal matters such as background checks are not stored or used; the leader decides who is on the team and in which role.
4. **Every church is different.** Gatherings, roles, load limits and preferences come from the church profile set up during onboarding, never from hard-coded rules.
5. **Pastoral situations go to a person.** Shepherd can say who has been absent. It never says why, never drafts a pastoral message and never reaches out itself.
6. **Private by default.** Messages are 1:1, and no one's serving record is shown to a group.
7. **Ask when unsure.** An ambiguous name or reply produces a question, not a guess.
8. **Everything is logged.** Every change records who approved it.

## 2. Scope

The prototype covers one full weekly cycle for two seeded churches with synthetic data, including roster suggestions, memory and the conflict huddle.

**In the prototype:**

- Onboarding agent that writes the church profile, approved by a person
- Schedule intake from free text, with name and nickname matching
- Roster suggestions in two paths, shown side by side
- Deterministic checks and a private briefing for each leader
- Approval queue for rosters, reminders and memory
- Volunteer connection and replies through 1:1 chat
- Leader memory, proposed by Shepherd and confirmed by the leader
- Conflict huddle between two leaders
- Channels: Telegram and a copy-paste list, behind one channel adapter
- Audit log

**Later phases:**

- Monthly leaders' meeting and team meetings or rehearsals
- Swap requests between volunteers on the same team
- Big-event staffing view across ministries
- New volunteer onboarding and shadowing
- Calendar sync (Google, Outlook)
- Pastor's monthly summary by ministry, never by person
- Service-readiness checklists per role
- Other chat apps through the channel adapter

**Out of scope, always:** legal and compliance data (background checks, clearances), pastoral counseling, moving people between ministries, and anything shown to a group about an individual.

## 3. Church Profile and Onboarding

The church profile is how one build serves every church. The onboarding agent writes it by interviewing an admin and reading a sample of real schedules, then shows it in plain language for approval. Nothing runs until a person approves it, and the admin can edit it later in settings.

**What the profile holds:**

| Area | What it records |
| --- | --- |
| Gatherings | Every recurring service, meeting or event on any day of the week, plus one-off events. For each: name, day and time, duration, and whether it is **regular** or **special** |
| Ministries | Names and aliases the church uses, the roles each ministry fills, and the minimum people per role for each gathering |
| People in charge | For each ministry: who schedules and who approves (same person or two) |
| Load rules | How the church sees serving frequency: a weekly or monthly count, and what counts as normal versus a warning. A small ministry may expect people to serve often; another church may cap it. These are warnings, never blocks |
| Warning routing | Who receives each kind of warning |
| Roster settings | Show both suggested paths side by side (default) or only one; how far ahead to draft, set per ministry |
| Leader availability | Weekly windows each leader is usually free, used for the conflict huddle |

**Per person and per membership** (set by leaders, or by the volunteer through chat):

- **Experience per role:** set only by the leader, never computed. Someone new to the church can be a veteran from serving elsewhere. Levels: new, experienced, veteran.
- **Preferred frequency:** the volunteer's own wish, e.g. “twice a month.”
- **Blockout dates** and preferred times.

**Onboarding questions** (the agent infers the rest from sample data and asks to confirm): which services, meetings and events happen in a typical week and when; which are special; which ministries need a schedule and what they are called; who schedules and approves each; how the church sees serving often; and who should hear first about a conflict.

## 4. Roster Suggestions

Shepherd drafts two roster paths for a ministry and period, shown side by side. The leader picks one, edits it, and approves it. Nothing is recorded or sent before that approval.

|  | Training roster | Veteran roster |
| --- | --- | --- |
| Purpose | Grow the team | Get a big moment right |
| Who it favors | Mixes experienced and veteran people with newer ones, so a new person never serves a role alone | Veterans in every role |
| Typical use | Regular gatherings | Special services and events |
| Expected pattern | Spreads serving across the team | Veterans will usually serve every big event; that is normal, not a warning to suppress |

Including an “almost veteran” on a veteran roster is the leader's call, made by editing the draft. Shepherd does not substitute on its own.

**Hard rules (a draft never breaks them):**

- Only people on that ministry's team, in roles the leader has given them
- No assignment on a person's blockout dates
- No assignment that overlaps in time with another assignment, in any ministry, on any day
- Fill each role's minimum where the team allows; when it can't, leave the slot empty and say so

**Preferences (weighed, never absolute):**

- The church's load rules and each person's preferred frequency
- Rotation, so the same people are not always first
- Pairings and habits the leader confirmed in memory
- Preferred times

When a small team means someone must serve more than their preference or the church's usual load, the draft still includes them and marks it, e.g. “Anna: 3 times this week, above her preferred 2.” The leader decides.

**Every assignment explains itself** in one line, e.g. “Rachel with Emily: Rachel is new in this role, Emily is a veteran.” The rules choose who can serve; the language model writes the explanations and summaries.

**Settings:** show both paths (default) or a single default path. When both show, the veteran path comes first for gatherings marked special, and the training path first for regular ones. Leader edits on a draft can become memory proposals (section 6).

**Shared volunteers:** when two ministries' drafts want the same person at overlapping times, both leaders see a **shared** flag. Shepherd suggests a replacement for each leader from that leader's own team. The two leaders talk, then send their resolution back to Shepherd, which updates both rosters and re-runs the checks.

## 5. Weekly Cycle and Checks

A leader either picks a suggested roster or submits their own in any format. From there the cycle is the same: check, brief, settle, approve, remind, and record what happened.

1. **Roster in:** a chosen suggestion, or a pasted schedule parsed from free text (names, dates, role shorthand). Unmatched or ambiguous names produce a question.
2. **Checks run** against the unified record across all ministries and gatherings.
3. **Briefing:** each leader gets a private message with only what concerns their ministry, plus a link into the app.
4. **Settle:** conflicts go to both leaders, who may use the conflict huddle (section 7). Shepherd suggests a replacement for each leader from their own team; the leaders decide together and send the resolution back.
5. **Approve and remind:** reminders are drafted in the church's wording and sent 1:1 only after approval.
6. **Replies:** confirmations, declines and blockout dates are recorded. A decline re-runs the checks and reports the new gap.
7. **After the gathering:** the nightly run records who actually served and updates load counts.

**Checks (deterministic rules, never model judgment):**

| Check | Goes to |
| --- | --- |
| Same person in two assignments whose times overlap, any ministries, any day | Both ministries' scheduler and approver |
| Assignment on a blockout date | That ministry's scheduler |
| Role below its minimum | That ministry's scheduler, with who on the team is free |
| Serving above the church's load rules or the person's preference | The approver |
| Active person absent for the church's set number of weeks | The approver, once |
| A whole ministry silent | Escalated once as a broken source |
| Unmatched or ambiguous name | The scheduler, as a question |

## 6. Memory: Learning With the Leader

Shepherd learns how each leader tends their team, but it never saves anything silently. It notices a pattern or hears a note, asks “Should I remember this?”, and saves only what the leader confirms.

**What it can remember:**

- **Habits:** “You always pair Emily with Rachel.”
- **Volunteer preferences** the volunteer stated: “Emily prefers 9:30.”
- **Growth notes:** “Rachel is ready to lead a class.”
- **Rules of thumb:** “Keep the band together for a whole month.”

**Where it comes from:** edits the leader makes to a suggested roster (the same change twice becomes a proposal), notes the leader writes in chat, and preferences volunteers state.

**How it is used:** confirmed memories become preferences in the next roster suggestions, and each suggestion names the memory it used.

**What it never stores:** health, family situations, reasons someone gave for being away, interpersonal conflicts, and legal or compliance information.

**Control:** each memory is scoped to its ministry, visible to that ministry's leaders, and can be edited or deleted at any time. Volunteers can ask to see what Shepherd remembers about them, and see only what they told Shepherd themselves (their preferences and blockouts), never notes a leader saved. Every save and delete goes to the audit log.

## 7. Conflict Huddle

When two leaders share a conflict, Shepherd offers them a short time to talk instead of only a warning. It is the first meeting feature, and the only one in the prototype.

1. A double booking is found. Both leaders' briefings include it, with an option: **Find a time to talk**.
2. Either leader taps it. Shepherd compares both leaders' availability windows from the profile and offers 2–3 slots of 15 minutes before the gathering.
3. The first leader picks a slot. The other leader gets it 1:1 and accepts or picks another offered slot.
4. Both receive the confirmed time with a short agenda: who is involved, which gathering, and the time overlap. The agenda also lists Shepherd's suggested replacement for each side, drawn from each leader's own team. The decision stays with the leaders.
5. After the huddle, either leader sends the resolution back to Shepherd in one tap. Checks re-run.

**Rules:** only leaders are invited, never the volunteer in question. No common slot means Shepherd says so and lists the nearest options. Leaders can always ignore the huddle and settle it their own way.

## 8. Data Model

Every table belongs to one church (multi-tenant from day one). Names below are a starting point for Claude Code, not a final schema.

| Entity | Key fields |
| --- | --- |
| Church | id, name, timezone, language, profile\_status (draft or approved) |
| GatheringType | church, name, weekday, start\_time, duration, kind (regular or special), recurring or one-off |
| Gathering | church, gathering\_type, start, end |
| Ministry | church, name, aliases, roles (name, minimum per gathering type) |
| MinistryLeader | ministry, person, can\_schedule, can\_approve, availability windows |
| Person | church, name, nicknames, channel\_identity, opted\_in, stopped |
| Membership | person, ministry, status (active or inactive), status\_since, last\_served, asked\_at |
| RoleSkill | membership, role, experience (new, experienced, veteran), set\_by |
| Preference | person, preferred\_frequency, preferred\_times |
| Blockout | person, from, to |
| LoadRule | church, period (week or month), normal\_max, warning\_above |
| RosterSuggestion | ministry, period, path (training or veteran), created\_at, chosen, approved\_by |
| Assignment | gathering, ministry, role, person, status (suggested, approved, confirmed, declined, served), reason, source (suggestion or leader) |
| Finding | church, type, gathering, people, recipients, status |
| MemoryItem | ministry, about\_person (optional), kind (habit, preference, growth, rule), text, proposed\_from, confirmed\_by, created\_at |
| Huddle | finding, leaders, offered\_slots, chosen\_slot, agenda, outcome |
| Message | person, channel, body, status (draft, approved, sent, failed) |
| AuditLog | church, actor, action, target, before, after, approved\_by, at |

No field anywhere stores legal, health or pastoral information.

## 9. Agents and Architecture

Five agents share one record and one approval queue. The rules and solver decide what is true and who can serve; the language model only reads text, matches names, explains and drafts.

&#91;embedded content: architecture · 5 agents behind one approval queue\]

| Agent | Runs | Does |
| --- | --- | --- |
| Onboarding | Once per church, then on settings changes | Interviews the admin, reads sample schedules, writes the profile for approval |
| Steward | Nightly | Reads replies, matches names and nicknames, keeps the record current, records who served, proposes memories |
| Weekly Check | Each scheduling cycle | Runs every check, re-verifies its output, drafts briefings and reminders |
| Roster | When a leader asks, or ahead of each period | Drafts the training and veteran paths with a reason per assignment |
| Huddle | When a leader taps Find a time to talk | Offers shared slots, confirms the time, drafts a neutral agenda |

## 10. Build Plan for Claude Code

Build in eight milestones, each ending in something you can run. Hand Claude Code one milestone at a time with this brief attached.

| # | Milestone | Done when |
| --- | --- | --- |
| 1 | Data model, migrations, and two seeded churches with synthetic data | Both churches load; one treats weekly serving as normal, the other caps it at twice a month |
| 2 | Onboarding agent and profile approval | An admin goes from nothing to an approved profile in chat, including weekday gatherings and special events |
| 3 | Schedule intake: free-text parser and name matcher | A messy pasted schedule is parsed; ambiguous names produce a question, never a guess |
| 4 | Deterministic checks and briefings | Every check in section 5 fires on the seed data, and each leader sees only their own ministry |
| 5 | Roster suggestions | Both paths are drafted side by side, every hard rule holds, and each assignment has a one-line reason |
| 6 | Approval, channels and volunteer replies | Approved reminders go out on Telegram and as a copy-paste list; replies update the record and re-run checks |
| 7 | Memory | A repeated leader edit becomes a proposal; once confirmed, it shapes the next suggestion and is named in its reason |
| 8 | Conflict huddle | Both leaders get matching slots, a chosen time, and a neutral agenda; the outcome re-runs checks |

**Stack (decided):** all Python on the backend. Angular PWA for leaders and admins; FastAPI with Pydantic and a generated TypeScript client; Postgres with SQLAlchemy 2 and Alembic; one worker process with APScheduler for the agents; OR-Tools CP-SAT for roster drafts; Azure OpenAI behind one interface so the provider can change. Everything runs locally with Docker first and deploys to Azure later. Telegram comes after the Angular app; until then the copy-paste channel is the only sender.

**Working with Claude Code:** start each milestone with a short plan, ask for tests alongside the code, and keep the test cases in section 11 as the acceptance check.

## 11. Test Cases

Each row is one automated test. The first block carries over from the Use Cases doc; the second covers the new features.

| Area | Situation | Expected behavior |
| --- | --- | --- |
| Intake | “Anna P.” matches two people | Ask the scheduler; never merge on similarity |
| Intake | A new name appears | Ask whether it is a new person or a known nickname |
| Replies | “maybe, depends on work” | Ask one clarifying question; record nothing |
| Replies | “I'm out the 12th and the 19th” | Record two blockout dates |
| Replies | “stop” | End reminders and tell the leader |
| Replies | A personal or pastoral reason is shared | Record availability only; pass the rest to the leader |
| Checks | Double booking with no alternative on either team | Warn both leaders; propose nothing |
| Checks | Double booking with free people on both teams | Warn both leaders and suggest one replacement per side from each leader's own team; leaders decide |
| Checks | Overlap between a Wednesday prayer night and a midweek youth event | Flag it, the same as a Sunday conflict |
| Checks | A whole ministry submits nothing | Escalate one broken source, not one question per person |
| Checks | A decline arrives after approval | Re-run checks, report the new gap, reassign nothing |
| Checks | A send fails | Show it in the briefing; never fail silently |
| Roster | Training path | Every new person in a role is paired with an experienced or veteran person in that role |
| Roster | Veteran path for a special event | Only veterans are drafted; the same veterans on every big event is not flagged as a problem |
| Roster | Gathering marked special, both paths shown | Veteran path appears first |
| Roster | Two ministries' drafts want the same person at overlapping times | Both see a shared flag and one suggested replacement each; the agreed resolution updates both rosters |
| Roster | Team too small to meet preferences | Draft still fills the slot and marks who is above their preference |
| Roster | Not enough people for a role's minimum | Leave the slot empty and say so; never pull from another ministry |
| Roster | Person blocked out or already serving at an overlapping time | Never drafted for that slot |
| Roster | Leader edits a draft and creates a conflict | Checks re-run on the edited roster before approval |
| Roster | Setting changed to one path | Only the default path is drafted |
| Roster | Draft horizon set per ministry | Each ministry is drafted only as far ahead as its own setting |
| Memory | Leader makes the same pairing edit twice | Shepherd proposes a memory; saves only after confirmation |
| Memory | Leader mentions a health or family situation | Nothing is proposed or stored |
| Memory | Leader deletes a memory | It stops shaping suggestions immediately; the deletion is logged |
| Memory | Volunteer asks what Shepherd remembers | Shows only what that volunteer told Shepherd, never a leader's notes |
| Huddle | Leaders' availability windows in their profiles overlap | 2–3 slots offered before the gathering |
| Huddle | No common window | Shepherd says so and lists the nearest options |
| Huddle | Agenda | Names the people, gathering and overlap, plus one suggested replacement per side; the volunteer is never invited |

## 12. Decisions on Earlier Open Questions

All five are decided and written into the sections above.

| Question | Decision | Section |
| --- | --- | --- |
| Can volunteers see what Shepherd remembers about them? | Yes, but only what they told Shepherd themselves, never what a leader saved | 6 |
| Two drafts want the same shared volunteer | Both leaders see a shared flag and a suggested replacement each; they talk and send the resolution back | 4, 5, 7 |
| Where do leaders keep their availability for huddles? | In their profile | 3, 7 |
| How far ahead are suggestions drafted? | Set per ministry | 3 |
| Is the veteran path shown first for special gatherings? | Yes, with both paths still shown | 4 |
