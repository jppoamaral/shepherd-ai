"""Prompt for reading a volunteer's chat message. The model reads; code records."""

PARSE = """\
A church volunteer wrote to Shepherd, the church's scheduling bot, in a private chat.
Say what the message means. You do not answer it.

intent, one of:
- confirm: they will serve ("yes", "count me in", "see you then").
- decline: they can't serve the date they were reminded about.
- maybe: they are unsure or it depends ("maybe", "depends on work", "not sure yet").
- away: they give dates when they are away or can't serve, without answering a reminder
  ("I'm out the 19th and the 26th", "away all of November").
- what_i_know: they ask what Shepherd knows or remembers about them.
- stop: they want no more messages. start: they want messages again.
- other: anything else.

dates: only for away. Each date as YYYY-MM-DD, resolved against today's date in the facts
(the next such date on or after today). Leave out anything that isn't a date. Never copy
reasons, health, family or other personal details into any field.
"""
