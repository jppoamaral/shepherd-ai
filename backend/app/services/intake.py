"""Turning a parsed schedule into slots and questions (architecture rule 2). Pure.

The model has read the pasted text into `ParsedEntry` rows; everything here is
deterministic: which gathering a date means, which role a label means, who a
name is. Anything not certain becomes one question per distinct subject, which
the leader answers by picking a choice.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, time

from app.domain.enums import QuestionKind
from app.domain.intake import (
    Choice,
    GatheringRef,
    IntakeContext,
    IntakeDraft,
    IntakeQuestion,
    IntakeSlot,
    LearnedNickname,
    ParsedEntry,
    PersonRef,
    RoleRef,
)
from app.services.name_matching import Ambiguous, Matched, NotOnTeam, match_name, normalize
from app.services.profile import ProfileProblem, format_time, parse_date, parse_time

K = QuestionKind
LEAVE_OUT = "leave_out"
UPCOMING_CHOICES = 6


class IntakeAnswerError(ValueError):
    """An answer that doesn't fit an open question. The message is user-facing."""


# ---------------------------------------------------------------------------
# Building the draft
# ---------------------------------------------------------------------------


def unknown_names(entries: Iterable[ParsedEntry], ctx: IntakeContext) -> list[str]:
    """Names code can't place at all; only these are worth asking the model about."""
    seen: dict[str, str] = {}
    for entry in entries:
        for written in entry.names:
            token = normalize(written)
            if token and token not in seen:
                result = match_name(written, ctx.team, ctx.others)
                if not isinstance(result, Matched | Ambiguous | NotOnTeam):
                    seen[token] = written.strip()
    return list(seen.values())


@dataclass
class _Builder:
    ctx: IntakeContext
    slots: list[IntakeSlot] = field(default_factory=list)
    questions: dict[tuple[str, str], IntakeQuestion] = field(default_factory=dict)

    def ask(
        self,
        kind: QuestionKind,
        key: str,
        subject: str,
        prompt: str,
        choices: list[Choice],
        slot_id: int,
    ) -> None:
        question = self.questions.get((kind, key))
        if question is None:
            question = IntakeQuestion(
                id=f"q{len(self.questions) + 1}",
                kind=kind,
                subject=subject,
                prompt=prompt,
                choices=[*choices, Choice(id=LEAVE_OUT, label="Leave this out")],
                slot_ids=[],
            )
            self.questions[(kind, key)] = question
        question.slot_ids.append(slot_id)


def build_intake(entries: Iterable[ParsedEntry], ctx: IntakeContext) -> IntakeDraft:
    b = _Builder(ctx)
    for entry in entries:
        names = [n.strip() for n in entry.names if n.strip()]
        if not names:
            continue
        gatherings, when, gathering_question = _resolve_gatherings(entry, ctx)
        role = _resolve_role(entry, ctx.roles)
        for gathering in gatherings:
            for written in names:
                slot = IntakeSlot(
                    id=len(b.slots) + 1,
                    when=when,
                    gathering_id=gathering.id if gathering else None,
                    gathering_label=_gathering_label(gathering) if gathering else None,
                    role_as_written=entry.role_as_written.strip(),
                    role_id=role.id if role else None,
                    role_label=role.name if role else None,
                    name_as_written=written,
                )
                b.slots.append(slot)
                if gathering is None and gathering_question is not None:
                    key, subject, choices = gathering_question
                    b.ask(
                        K.WHICH_GATHERING,
                        key,
                        subject,
                        f"Which gathering is “{subject}”?",
                        choices,
                        slot.id,
                    )
                if role is None:
                    _ask_role(b, entry.role_as_written, slot.id)
                _resolve_person(b, slot, written)
    return IntakeDraft(slots=b.slots, questions=list(b.questions.values()))


def _resolve_person(b: _Builder, slot: IntakeSlot, written: str) -> None:
    ctx = b.ctx
    token = normalize(written)
    result = match_name(written, ctx.team, ctx.others)
    match result:
        case Matched(person):
            slot.person_id, slot.person_label = person.id, person.name
        case Ambiguous(candidates):
            b.ask(
                K.AMBIGUOUS_NAME,
                token,
                written,
                f"“{written}” could be {_or(p.name for p in candidates)}. Who is it?",
                [_person_choice(i, p) for i, p in enumerate(candidates, 1)],
                slot.id,
            )
        case NotOnTeam(people):
            b.ask(
                K.NOT_ON_TEAM,
                token,
                written,
                f"{_or(p.name for p in people)} isn't on the {ctx.ministry_name} team in my records. "
                f"Who did you mean by “{written}”, or should I leave it out?",
                [_person_choice(i, p) for i, p in enumerate(_sorted(ctx.team), 1)],
                slot.id,
            )
        case _:
            suggested = [p for p in ctx.team if p.id in ctx.suggestions.get(token, ())]
            rest = [p for p in _sorted(ctx.team) if p not in suggested]
            choices = [
                _person_choice(i, p, nickname=written) for i, p in enumerate([*suggested, *rest], 1)
            ]
            hint = f" It might be {_or(p.name for p in suggested)}." if suggested else ""
            b.ask(
                K.UNKNOWN_NAME,
                token,
                written,
                f"I don't know “{written}” on the {ctx.ministry_name} team.{hint} Is it a nickname for "
                "someone on the team, or should I leave it out? (I can't add new people yet.)",
                choices,
                slot.id,
            )


def _ask_role(b: _Builder, written: str, slot_id: int) -> None:
    choices = [Choice(id=f"c{i}", label=r.name, value=r.id) for i, r in enumerate(b.ctx.roles, 1)]
    b.ask(
        K.UNKNOWN_ROLE,
        normalize(written),
        written,
        f"Which {b.ctx.ministry_name} role is “{written}”?",
        choices,
        slot_id,
    )


def _resolve_role(entry: ParsedEntry, roles: tuple[RoleRef, ...]) -> RoleRef | None:
    by_name = {normalize(r.name): r for r in roles}
    for candidate in (entry.role, entry.role_as_written):
        if not candidate:
            continue
        token = normalize(candidate)
        role = (
            by_name.get(token) or by_name.get(token.removesuffix("s")) or by_name.get(f"{token}s")
        )
        if role:
            return role
    return None


def _resolve_gatherings(
    entry: ParsedEntry, ctx: IntakeContext
) -> tuple[Sequence[GatheringRef | None], str, tuple[str, str, list[Choice]] | None]:
    """The gatherings an entry means, or [None] plus the question to ask."""
    day = _safe_date(entry.date)
    at = _safe_time(entry.time)
    label = (entry.gathering or "").strip()

    if day is None:
        # No date: offer the next few gatherings that fit the weekday (or any) to pick from.
        upcoming = [
            g
            for g in ctx.gatherings
            if g.local_date >= ctx.today
            and g.ministry_serves
            and (entry.weekday is None or g.local_date.weekday() == entry.weekday.number)
        ]
        subject = (
            " ".join(
                x
                for x in (
                    entry.weekday.value.capitalize() if entry.weekday else "",
                    label,
                    format_time(at) if at else "",
                )
                if x
            )
            or "no date given"
        )
        return (
            [None],
            subject,
            (
                f"nodate:{normalize(subject)}",
                subject,
                _gathering_choices(upcoming[:UPCOMING_CHOICES]),
            ),
        )

    when = f"{day:%a %-d %b}"
    that_day = [g for g in ctx.gatherings if g.local_date == day]
    relevant = [g for g in that_day if g.ministry_serves] or that_day

    if at is not None:
        exact = [g for g in that_day if g.local_time == at]
        if len(exact) == 1:
            return [exact[0]], f"{when} {format_time(at)}", None
    elif entry.all_gatherings_that_day and relevant:
        return list(relevant), when, None
    elif label:
        named = [
            g
            for g in relevant
            if normalize(label) in normalize(g.name) or normalize(g.name) in normalize(label)
        ]
        if len(named) == 1:
            return named, when, None
    if at is None and not label and len(relevant) == 1:
        return [relevant[0]], when, None

    subject = " ".join(x for x in (when, label, format_time(at) if at else "") if x)
    return [None], when, (f"{day}:{at}:{normalize(label)}", subject, _gathering_choices(that_day))


def _gathering_choices(gatherings: list[GatheringRef]) -> list[Choice]:
    return [
        Choice(id=f"c{i}", label=_gathering_label(g), value=g.id)
        for i, g in enumerate(gatherings, 1)
    ]


def _gathering_label(g: GatheringRef) -> str:
    return f"{g.name}, {g.local_start:%a %-d %b} {format_time(g.local_time)}"


def _person_choice(i: int, person: PersonRef, nickname: str | None = None) -> Choice:
    label = person.name + (f" (remember “{nickname}” for them)" if nickname else "")
    return Choice(id=f"c{i}", label=label, value=person.id, learn_nickname=nickname is not None)


def _sorted(people: tuple[PersonRef, ...]) -> list[PersonRef]:
    return sorted(people, key=lambda p: p.name)


def _or(names: Iterable[str]) -> str:
    items = list(names)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" or {items[-1]}"


def _safe_date(value: str | None) -> date | None:
    try:
        return parse_date(value) if value else None
    except ProfileProblem:
        return None


def _safe_time(value: str | None) -> time | None:
    try:
        return parse_time(value) if value else None
    except ProfileProblem:
        return None


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def apply_answer(draft: IntakeDraft, question_id: str, choice_id: str) -> IntakeDraft:
    updated = draft.model_copy(deep=True)
    question = next((q for q in updated.questions if q.id == question_id), None)
    if question is None:
        raise IntakeAnswerError("That question isn't open any more.")
    choice = next((c for c in question.choices if c.id == choice_id), None)
    if choice is None:
        raise IntakeAnswerError("That isn't one of the choices for this question.")

    for slot in updated.slots:
        if slot.id not in question.slot_ids:
            continue
        if choice.value is None:
            slot.left_out = True
        elif question.kind is K.WHICH_GATHERING:
            slot.gathering_id, slot.gathering_label = choice.value, choice.label
        elif question.kind is K.UNKNOWN_ROLE:
            slot.role_id, slot.role_label = choice.value, choice.label
        else:
            slot.person_id, slot.person_label = choice.value, choice.label.split(" (remember")[0]

    if choice.value is not None and choice.learn_nickname:
        learned = LearnedNickname(person_id=choice.value, nickname=question.subject)
        if learned not in updated.nicknames:
            updated.nicknames.append(learned)
    updated.questions = [q for q in updated.questions if q.id != question_id]
    # Questions whose slots were all left out no longer need an answer.
    left = {s.id for s in updated.slots if s.left_out}
    updated.questions = [q for q in updated.questions if not set(q.slot_ids) <= left]
    return updated


def is_ready(draft: IntakeDraft) -> bool:
    return not draft.questions and all(s.resolved for s in draft.slots)


@dataclass(frozen=True)
class ResolvedAssignment:
    gathering_id: uuid.UUID
    role_id: uuid.UUID
    person_id: uuid.UUID


def assignments(draft: IntakeDraft) -> list[ResolvedAssignment]:
    """Distinct (gathering, role, person) from resolved slots that weren't left out."""
    found: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], ResolvedAssignment] = {}
    for s in draft.slots:
        if s.left_out or s.gathering_id is None or s.role_id is None or s.person_id is None:
            continue
        found.setdefault(
            (s.gathering_id, s.role_id, s.person_id),
            ResolvedAssignment(s.gathering_id, s.role_id, s.person_id),
        )
    return list(found.values())


def render_intake(draft: IntakeDraft) -> str:
    lines = []
    for s in draft.slots:
        if s.left_out:
            lines.append(f"• {s.when} · {s.role_as_written} · {s.name_as_written} — left out")
            continue
        gathering = s.gathering_label or f"{s.when} (which gathering?)"
        role = s.role_label or f"“{s.role_as_written}” (which role?)"
        person = s.person_label or f"“{s.name_as_written}” (who?)"
        lines.append(f"• {gathering} · {role} · {person}")
    return "\n".join(lines) or "Nothing found in that schedule."
