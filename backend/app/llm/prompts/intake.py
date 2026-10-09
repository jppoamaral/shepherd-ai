"""Prompts for schedule intake. The model reads and suggests; code decides."""

PARSE = """\
You read a volunteer schedule that a church ministry leader pasted, in any format,
and list what it says. You do not decide who anyone is.

For every role filled at every gathering, return one entry:
- date: the date as YYYY-MM-DD. Resolve short forms like "10/11" or "Sun 11th"
  using today's date from the facts (the schedule is usually for upcoming weeks).
  Null if no date is written.
- weekday: the weekday if written, else null.
- time: 24-hour HH:MM if a time is written for that gathering, else null.
- gathering: a gathering name or label if written ("prayer night", "2nd service"), else null.
- all_gatherings_that_day: true only if it says it applies to every service that day
  ("both services", "all services").
- role_as_written: the role exactly as written ("kb", "chk-in", "helpers").
- role: one of the ministry's role names from the facts if you are sure what
  role_as_written means; otherwise null.
- names: the people's names exactly as written, one per item. Copy them; never
  correct, complete or guess a name.

Leave out anything that isn't a name, such as notes about why someone is away,
health, family or other personal details. If the text isn't a schedule at all,
return no entries and one short clarifying_question.
"""

SUGGEST = """\
Some names in a church volunteer schedule don't exactly match anyone on the team.
For each name, list the team members (full names, copied exactly from the team
list) it could plausibly be a nickname or short form for, e.g. "Annie" -> "Anna
Peterson". Only list real possibilities; an empty list is fine. These are only
suggestions; the leader will choose.
"""
