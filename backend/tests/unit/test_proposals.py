"""Proposal types, their payload models and their handlers stay in step."""

import uuid
from datetime import date

from app.domain.enums import MemoryKind, MemorySource, ProposalType
from app.domain.proposals import (
    PAYLOADS,
    LeaderRosterPayload,
    MemoryPayload,
    ReplyAwayPayload,
    RosterLine,
)
from app.services.approval import HANDLERS


def test_every_proposal_type_has_a_payload_model_and_a_handler() -> None:
    assert set(PAYLOADS) == set(ProposalType)
    assert set(HANDLERS) == set(ProposalType)


def test_a_stored_payload_reads_back_the_same() -> None:
    roster = LeaderRosterPayload(
        ministry_id=uuid.uuid4(),
        source="suggestion",
        assignments=[
            RosterLine(gathering_id=uuid.uuid4(), role_id=uuid.uuid4(), person_id=uuid.uuid4())
        ],
    )
    away = ReplyAwayPayload(person_id=uuid.uuid4(), dates=[date(2026, 10, 12), date(2026, 10, 19)])
    for payload in (roster, away):
        assert type(payload).model_validate(payload.stored()) == payload
    assert away.stored()["dates"] == ["2026-10-12", "2026-10-19"]


def test_stored_payloads_leave_out_what_is_not_set() -> None:
    memory = MemoryPayload(
        ministry_id=uuid.uuid4(),
        text="Keep the band together for a whole month.",
        kind=MemoryKind.RULE,
        proposed_from=MemorySource.LEADER_NOTE,
    )
    assert "about_person_id" not in memory.stored()
