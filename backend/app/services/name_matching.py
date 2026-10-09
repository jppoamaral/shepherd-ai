"""Deterministic name matching (architecture rule 2; brief principle 7: ask when unsure).

A name only counts as matched when exactly one person on the ministry's team
fits it by an exact rule. Two fits are ambiguous and become a question; nothing
is ever merged on similarity.
"""

import re
from dataclasses import dataclass

from app.domain.intake import PersonRef

_NOT_NAME = re.compile(r"[^\w\s'\u2019-]")  # keep letters, spaces, apostrophes, hyphens


def normalize(name: str) -> str:
    """Case- and punctuation-insensitive form: "  Anna  P. " -> "anna p"."""
    return " ".join(_NOT_NAME.sub(" ", name).casefold().split())


@dataclass(frozen=True)
class Matched:
    person: PersonRef


@dataclass(frozen=True)
class Ambiguous:
    candidates: tuple[PersonRef, ...]


@dataclass(frozen=True)
class NotOnTeam:
    """Fits someone in the church who isn't on this ministry's team."""

    people: tuple[PersonRef, ...]


@dataclass(frozen=True)
class Unknown:
    pass


Match = Matched | Ambiguous | NotOnTeam | Unknown


def match_name(written: str, team: tuple[PersonRef, ...], others: tuple[PersonRef, ...]) -> Match:
    token = normalize(written)
    if not token:
        return Unknown()
    on_team = _fits(token, team)
    if len(on_team) == 1:
        return Matched(on_team[0])
    if len(on_team) > 1:
        return Ambiguous(on_team)
    elsewhere = _fits(token, others)
    return NotOnTeam(elsewhere) if elsewhere else Unknown()


def _fits(token: str, people: tuple[PersonRef, ...]) -> tuple[PersonRef, ...]:
    """People the token names, by the strongest rule that finds anyone.

    1. Full name or a recorded nickname, exactly.
    2. First name alone ("Rachel").
    3. First name plus last initial ("Anna P").
    """
    exact = tuple(
        p
        for p in people
        if token == normalize(p.name) or token in {normalize(n) for n in p.nicknames}
    )
    if exact:
        return exact
    parts = token.split()
    if len(parts) == 1:
        return tuple(p for p in people if normalize(p.name).split()[0] == parts[0])
    if len(parts) == 2 and len(parts[1]) == 1:
        first, initial = parts
        return tuple(
            p
            for p in people
            if (words := normalize(p.name).split())[0] == first
            and len(words) > 1
            and words[-1].startswith(initial)
        )
    return ()
