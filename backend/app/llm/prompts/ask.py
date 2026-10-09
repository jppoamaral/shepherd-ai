"""Prompt for Ask Shepherd. The model says what was asked; code answers."""

PARSE = """\
A church ministry leader asked Shepherd, their volunteer scheduling assistant, a
question. Say what it asks for. You do not answer it.

intent, one of:
- needs_me: what needs their attention, what's going on this week.
- free_on: who is free or available on a date (no one person named as being replaced).
- replace: who could take a named person's place, cover for them, or stand in.
- serving_a_lot: who is serving a lot, too often, or might be tired.
- draft_reminder: write reminders for a date's roster or service.
- draft_message: write a message to one named person (for example asking them to serve).
- remember: what Shepherd remembers or knows about a named person.
- availability: when a named person is free, away or blocked out.
- private: anything about health, family, faith struggles, legal matters, or why
  someone is away or taking time off. These are never answered.
- unknown: anything else.

person: the one person the question is about, copied exactly as written ("Anna",
"Rachel T."). Never complete or correct a name. Null if no one is named.

date: the date asked about as YYYY-MM-DD. Resolve "Sunday", "this week", "Oct 11"
or "next Wednesday" using today's date and the upcoming dates in the facts. Null if
no date is given.
"""
