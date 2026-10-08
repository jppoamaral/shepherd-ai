"""Agents: onboarding, steward, weekly_check, roster, huddle.

Agents read through `app.db.repositories.reads` and write only Proposals through
`app.db.repositories.proposals`. They never touch assignments, messages or
channels directly; `tests/unit/test_architecture.py` enforces this.
"""
