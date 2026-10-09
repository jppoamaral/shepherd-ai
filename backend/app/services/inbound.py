"""A volunteer's message to the Shepherd bot, from any channel (the simulator now, Telegram later).

Rules decide (rule 2): numbered answers, yes/no, "maybe", "stop"/"start" and "what do you
remember about me" are read by code. Only other free text goes to the model, which says
what it means; code decides what happens. Anything that changes the record is a proposal
the volunteer's own reply approves, applied by ApprovalService (rule 1).

Privacy (rule 5): what the volunteer writes is never stored. If they give a reason for not
serving, it is passed to their leader once, as said (a notice deleted on dismiss), and not
asked about or mentioned again. One clarifying question at most; "maybe" is never a yes.
The bot's replies answer the volunteer's own message, in fixed wording; anything Shepherd
starts (reminders) needs a leader's approval.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import BotReply
from app.channels.factory import channel_for
from app.db.models import (
    Assignment,
    Blockout,
    Church,
    Conversation,
    Gathering,
    Membership,
    Message,
    Ministry,
    MinistryLeader,
    Person,
    Preference,
    Role,
    RoleSkill,
)
from app.db.repositories.notices import NoticeWriter
from app.db.repositories.proposals import ProposalRepository
from app.domain.enums import AssignmentStatus, MembershipStatus, MessageStatus, StatedBy
from app.domain.replies import ParsedReply, ReplyIntent
from app.llm.client import LLMClient
from app.llm.prompts.replies import PARSE
from app.services import reply_types
from app.services.approval import ApprovalService
from app.services.briefing import church_today

YES = re.compile(
    r"^\s*(1\b|y\b|yes\b|yep\b|yeah\b|sure\b|ok\b|okay\b|count me in|i'?ll be there)", re.I
)
NO = re.compile(
    r"^\s*(2\b|n\b|no\b|nope\b|can'?t\b|cannot\b|can not\b|won'?t\b|unable\b|i can'?t\b|"
    r"i won'?t\b|sorry,? i can'?t)",
    re.I,
)
MAYBE = re.compile(r"\b(maybe|not sure|unsure|depends|might|possibly|perhaps|probably)\b", re.I)
STOP = re.compile(r"^\s*(stop|unsubscribe|stop messages|no more messages)\s*[.!]?\s*$", re.I)
START = re.compile(r"^\s*(start|resume|start again)\s*[.!]?\s*$", re.I)
WHAT_I_KNOW = re.compile(r"\bwhat (do|did) you (remember|know|have|keep) (about|on) me\b", re.I)
AWAY_WORDS = re.compile(
    r"\b(away|out|off|travel\w*|vacation|holiday|not available|unavailable|can'?t do)\b", re.I
)
MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
DAY = re.compile(
    r"\b(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?"
    r"(?:the\s+)?(?P<day>[0-3]?\d)(?:st|nd|rd|th)\b",
    re.I,
)
# What's left after "2" or "no" that only restates the decline, not a reason.
PLAIN_DECLINE = re.compile(
    r"^(i\s+)?(can'?t|cannot|won'?t)?\s*(make it|make that|do it|come|serve)?[\s.!,]*(sorry)?[\s.!]*$",
    re.I,
)

YES_BUTTONS = ("Yes", "Change")
MAYBE_BUTTONS = ("Can't commit", "I'll let you know")
KNOW_BUTTONS = ("Change something", "All good")


@dataclass
class Inbound:
    session: Session
    church: Church
    person: Person
    tz: ZoneInfo
    today: date
    convo: Conversation

    @property
    def first(self) -> str:
        return self.person.name.split(" ")[0]


class UnknownPerson(LookupError):
    pass


def handle_inbound(
    session: Session,
    church_id: uuid.UUID,
    person_id: uuid.UUID,
    text: str,
    llm: LLMClient | None,
    today: date | None = None,
) -> list[BotReply]:
    """Read one message, record what it means (via proposals), and reply in the chat."""
    person = session.scalar(
        select(Person).where(Person.church_id == church_id, Person.id == person_id)
    )
    if person is None:
        raise UnknownPerson("person not found")
    church = session.get_one(Church, church_id)
    convo = session.scalar(
        select(Conversation).where(
            Conversation.church_id == church_id, Conversation.person_id == person_id
        )
    ) or Conversation(church_id=church_id, person_id=person_id, awaiting=None, context={})
    session.add(convo)
    ctx = Inbound(
        session=session,
        church=church,
        person=person,
        tz=ZoneInfo(church.timezone),
        today=today or church_today(session, church_id),
        convo=convo,
    )
    replies = _route(ctx, text.strip(), llm)
    channel = channel_for(session, church)
    for reply in replies:
        channel.reply(reply)
    session.flush()
    return replies


# ---------------------------------------------------------------------------


def _route(ctx: Inbound, text: str, llm: LLMClient | None) -> list[BotReply]:
    if not text:
        return []
    if STOP.match(text):
        return _stop(ctx)
    if START.match(text):
        return _start(ctx)
    if WHAT_I_KNOW.search(text):
        return _what_i_know(ctx)
    if ctx.person.stopped:
        return [_say(ctx, "Reminders are off. Write 'start' anytime to turn them back on.")]

    awaiting = ctx.convo.awaiting
    if awaiting == "away_confirm":
        if YES.match(text):
            return _save_away(ctx, ctx.convo.context.get("dates", []))
        if NO.match(text) or text.strip().lower().startswith("change"):
            _await(ctx, "away_dates")
            return [_say(ctx, "No problem. Which dates are you away?")]
    if awaiting == "away_dates":
        dates = _dates(ctx, text)
        if dates:
            return _confirm_away(ctx, dates)
    if awaiting == "maybe":
        reminder = _open_reminder(ctx)
        if reminder and YES.match(text):  # 1 = can't commit
            return _cant_commit(ctx, reminder)
        if reminder and (NO.match(text) or "let you know" in text.lower()):  # 2 = later
            _await(ctx, None)
            return [_say(ctx, "Okay. Reply 1 or 2 to my reminder whenever you know.")]
    if awaiting == "what_i_know":
        _await(ctx, None)
        if YES.match(text) or text.lower().startswith("change"):
            return [
                _say(
                    ctx,
                    "Tell me what to change: new away dates, how often you'd like to serve, "
                    "or write 'stop' to turn reminders off.",
                )
            ]
        if NO.match(text) or "all good" in text.lower():
            return [_say(ctx, "Great. Thank you!")]

    reminder = _open_reminder(ctx)
    if reminder:
        if MAYBE.search(text) and not NO.match(text):
            return _maybe(ctx, reminder)
        if YES.match(text):
            return _confirm(ctx, reminder)
        if NO.match(text):
            return _decline(ctx, reminder, _reason(text))

    if AWAY_WORDS.search(text) and (dates := _dates(ctx, text)):
        return _confirm_away(ctx, dates)

    # A bare number or yes/no with nothing open to answer: no model needed.
    bare = YES.match(text) or NO.match(text)
    parsed = None if bare and len(text.split()) <= 3 else _parse(ctx, text, llm)
    if parsed is not None:
        if parsed.intent is ReplyIntent.STOP:
            return _stop(ctx)
        if parsed.intent is ReplyIntent.START:
            return _start(ctx)
        if parsed.intent is ReplyIntent.WHAT_I_KNOW:
            return _what_i_know(ctx)
        if parsed.intent is ReplyIntent.AWAY:
            dates = [d for d in (_iso(x) for x in parsed.dates) if d and d >= ctx.today]
            if dates:
                return _confirm_away(ctx, sorted(set(dates)))
        if reminder:
            if parsed.intent is ReplyIntent.MAYBE:
                return _maybe(ctx, reminder)
            if parsed.intent is ReplyIntent.CONFIRM:
                return _confirm(ctx, reminder)
            if parsed.intent is ReplyIntent.DECLINE:
                return _decline(ctx, reminder, text)  # the whole message, passed on as said

    if reminder:
        return [_say(ctx, "Sorry, I didn't catch that. Reply 1 = yes, 2 = can't make it.")]
    return [
        _say(
            ctx,
            'I can help with your serving reminders, away dates ("I\'m away the 19th"), '
            "or what I know about you.",
        )
    ]


# --- answers to a reminder ---------------------------------------------------


@dataclass
class Reminder:
    assignment: Assignment
    start: datetime  # church-local
    ministry_id: uuid.UUID
    ministry: str
    role: str


def _open_reminder(ctx: Inbound) -> Reminder | None:
    """The latest reminder this person hasn't answered, for a gathering still ahead."""
    now = datetime.combine(ctx.today, time(0), tzinfo=ctx.tz)
    row = ctx.session.execute(
        select(Assignment, Gathering.start_at, Ministry.id, Ministry.name, Role.name)
        .join(Message, Message.assignment_id == Assignment.id)
        .join(Gathering, Gathering.id == Assignment.gathering_id)
        .join(Ministry, Ministry.id == Assignment.ministry_id)
        .join(Role, Role.id == Assignment.role_id)
        .where(
            Message.church_id == ctx.church.id,
            Message.person_id == ctx.person.id,
            Message.kind == "reminder",
            Message.status == MessageStatus.SENT,
            Assignment.person_id == ctx.person.id,
            Assignment.status == AssignmentStatus.APPROVED,
            Gathering.start_at >= now,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    assignment, start, ministry_id, ministry, role = row
    return Reminder(assignment, start.astimezone(ctx.tz), ministry_id, ministry, role)


def _confirm(ctx: Inbound, r: Reminder) -> list[BotReply]:
    _approve(ctx, reply_types.CONFIRM, {"assignment_id": str(r.assignment.id)})
    _await(ctx, None)
    return [_say(ctx, f"Thank you, {ctx.first}! See you {r.start:%A}.")]


def _decline(ctx: Inbound, r: Reminder, note: str | None) -> list[BotReply]:
    _approve(ctx, reply_types.DECLINE, {"assignment_id": str(r.assignment.id)})
    _await(ctx, None)
    when = _short(r.start.date())
    _tell_leaders(
        ctx,
        r.ministry_id,
        "declined",
        f"{ctx.person.name} can't make {r.start:%a} {when} ({r.ministry}, {r.role}).",
        note,
    )
    return [
        _say(ctx, f"Thank you for letting me know. I've told your leader you can't make {when}.")
    ]


def _maybe(ctx: Inbound, r: Reminder) -> list[BotReply]:
    _await(ctx, "maybe")
    when = _short(r.start.date())
    return [
        _say(
            ctx,
            f"No problem. Should I tell your leader you can't commit for {when}, or will you "
            "let me know?",
            MAYBE_BUTTONS,
        )
    ]


def _cant_commit(ctx: Inbound, r: Reminder) -> list[BotReply]:
    _await(ctx, None)
    when = _short(r.start.date())
    _tell_leaders(
        ctx,
        r.ministry_id,
        "cant_commit",
        f"{ctx.person.name} can't commit to {r.start:%a} {when} yet ({r.ministry}, {r.role}). "
        "Not confirmed.",
    )
    return [_say(ctx, f"Okay, I've let your leader know you can't commit for {when}.")]


# --- away dates, stop/start, what I know ---------------------------------------


def _confirm_away(ctx: Inbound, dates: list[date]) -> list[BotReply]:
    _await(ctx, "away_confirm", {"dates": [d.isoformat() for d in dates]})
    return [
        _say(
            ctx,
            f"Got it: you're away {_and([_short(d) for d in dates])}. Is that right?",
            YES_BUTTONS,
        )
    ]


def _save_away(ctx: Inbound, isos: list[str]) -> list[BotReply]:
    dates = [d for d in (_iso(x) for x in isos) if d]
    _await(ctx, None)
    if not dates:
        return [_say(ctx, "Which dates are you away?")]
    _approve(ctx, reply_types.AWAY, {"dates": [d.isoformat() for d in dates]})
    return [_say(ctx, f"Saved. You're away {_and([_short(d) for d in dates])}. Thank you!")]


def _stop(ctx: Inbound) -> list[BotReply]:
    _await(ctx, None)
    if not ctx.person.stopped:
        _approve(ctx, reply_types.STOP, {})
        for ministry_id in _ministries(ctx):
            _tell_leaders(ctx, ministry_id, "stopped", f"{ctx.person.name} turned off reminders.")
    return [
        _say(
            ctx,
            "Okay, I won't send you reminders anymore. I've let your leader know. "
            "Write 'start' anytime to turn them back on.",
        )
    ]


def _start(ctx: Inbound) -> list[BotReply]:
    _await(ctx, None)
    if ctx.person.stopped:
        _approve(ctx, reply_types.START, {})
        for ministry_id in _ministries(ctx):
            _tell_leaders(
                ctx, ministry_id, "started", f"{ctx.person.name} turned reminders back on."
            )
    return [_say(ctx, "Welcome back! I'll send your reminders again.")]


def _what_i_know(ctx: Inbound) -> list[BotReply]:
    """Only what the volunteer told Shepherd: never leader notes, memory or others' data."""
    s, cid, pid = ctx.session, ctx.church.id, ctx.person.id
    teams: dict[str, list[str]] = {}
    for ministry, role in s.execute(
        select(Ministry.name, Role.name)
        .select_from(Membership)
        .join(Ministry, Ministry.id == Membership.ministry_id)
        .outerjoin(RoleSkill, RoleSkill.membership_id == Membership.id)
        .outerjoin(Role, Role.id == RoleSkill.role_id)
        .where(
            Membership.church_id == cid,
            Membership.person_id == pid,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .order_by(Ministry.name, Role.name)
    ):
        teams.setdefault(ministry, [])
        if role:
            teams[ministry].append(role)
    lines = (
        ["Teams: " + "; ".join(f"{m}: {', '.join(r)}" if r else m for m, r in teams.items())]
        if teams
        else []
    )
    pref = s.scalar(
        select(Preference).where(
            Preference.church_id == cid,
            Preference.person_id == pid,
            Preference.stated_by == StatedBy.VOLUNTEER,
        )
    )
    if pref and pref.preferred_frequency and pref.preferred_frequency_period:
        times = "once" if pref.preferred_frequency == 1 else f"{pref.preferred_frequency} times"
        lines.append(f"How often: about {times} a {pref.preferred_frequency_period.value}")
    away = s.scalars(
        select(Blockout.start_date)
        .where(
            Blockout.church_id == cid,
            Blockout.person_id == pid,
            Blockout.stated_by == StatedBy.VOLUNTEER,
            Blockout.end_date >= ctx.today,
        )
        .order_by(Blockout.start_date)
    ).all()
    if away:
        lines.append(f"Away: {', '.join(_short(d) for d in away)}")
    if ctx.person.stopped:
        lines.append("Reminders: off")
    _await(ctx, "what_i_know")
    body = "Here's what I have:\n" + "\n".join(lines or ["Nothing yet."])
    body += "\nThis is only what you've told me. You can change or remove anything."
    return [_say(ctx, body, KNOW_BUTTONS)]


# --- helpers -------------------------------------------------------------------


def _approve(ctx: Inbound, kind: str, payload: dict[str, Any]) -> None:
    """Her answer is a proposal she approves herself; ApprovalService applies and audits it."""
    proposal = ProposalRepository(ctx.session, ctx.church.id).create(
        type=kind,
        payload={"person_id": str(ctx.person.id), **payload},
        created_by_agent="steward",
    )
    ApprovalService(ctx.session).approve(ctx.church.id, proposal.id, ctx.person.id)


def _tell_leaders(
    ctx: Inbound, ministry_id: uuid.UUID, kind: str, text: str, note: str | None = None
) -> None:
    NoticeWriter(ctx.session, ctx.church.id).add(
        ministry_id=ministry_id, about_person_id=ctx.person.id, kind=kind, text=text, note=note
    )


def _ministries(ctx: Inbound) -> list[uuid.UUID]:
    led = set(
        ctx.session.scalars(
            select(MinistryLeader.ministry_id).where(MinistryLeader.church_id == ctx.church.id)
        )
    )
    return [
        m
        for m in ctx.session.scalars(
            select(Membership.ministry_id).where(
                Membership.church_id == ctx.church.id,
                Membership.person_id == ctx.person.id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if m in led
    ]


def _await(ctx: Inbound, what: str | None, context: dict[str, Any] | None = None) -> None:
    ctx.convo.awaiting = what
    ctx.convo.context = context or {}


def _say(ctx: Inbound, body: str, buttons: tuple[str, ...] = ()) -> BotReply:
    return BotReply(person_id=ctx.person.id, body=body, buttons=buttons)


def _reason(text: str) -> str | None:
    """What follows "2" or "no", if it says more than the decline itself."""
    rest = NO.sub("", text, count=1).strip(" \t-:,.;!\u2013\u2014")
    return None if not rest or PLAIN_DECLINE.match(rest) else text.strip()


def _dates(ctx: Inbound, text: str) -> list[date]:
    """'the 19th and the 26th', 'Oct 19': each the next such date on or after today."""
    found = set()
    for m in DAY.finditer(text):
        day = int(m.group("day"))
        if m.group("mon"):
            month = MONTHS[m.group("mon")[:3].lower()]
            options = [(ctx.today.year, month), (ctx.today.year + 1, month)]
        else:
            options = [
                (
                    ctx.today.year + (ctx.today.month - 1 + k) // 12,
                    (ctx.today.month - 1 + k) % 12 + 1,
                )
                for k in range(13)
            ]
        for year, month in options:
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if candidate >= ctx.today:
                found.add(candidate)
                break
    return sorted(found)


def _parse(ctx: Inbound, text: str, llm: LLMClient | None) -> ParsedReply | None:
    if llm is None:
        return None
    reminder = _open_reminder(ctx)
    facts = f"Today: {ctx.today:%A} {ctx.today.isoformat()}\n"
    if reminder:
        facts += (
            f"They were reminded about {reminder.start:%A} {reminder.start.date().isoformat()}.\n"
        )
    return llm.complete(system=PARSE, user=f"{facts}\nMessage: {text}", schema=ParsedReply)


def _iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _short(d: date) -> str:
    return f"{d:%b} {d.day}"


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
