"""Onboarding logic that code owns: merging, validation, topic order, sample inference."""

from datetime import date, time

from app.domain.enums import (
    FindingType,
    GatheringKind,
    OnboardingTopic,
    Period,
    Recipient,
    RosterPath,
    Weekday,
)
from app.domain.profile import (
    AvailabilityIn,
    AvailabilityReply,
    BasicsReply,
    ChurchProfileDraft,
    DraftRoute,
    GatheringIn,
    GatheringsReply,
    LeaderIn,
    LeadersReply,
    LoadRuleIn,
    LoadRulesReply,
    MinistriesReply,
    MinistryIn,
    ReplyBase,
    ReviewReply,
    RoleIn,
    RoleMinimumIn,
    RolesReply,
    RosterSettingIn,
    RosterSettingsReply,
    RoutingReply,
    SampleReply,
    SampleSlot,
)
from app.services.profile import (
    TOPIC_ORDER,
    apply_reply,
    infer_from_sample,
    next_topic,
    proposal_blockers,
    render_summary,
)

T = OnboardingTopic
DONE = {"topic_done": True, "clarifying_question": None}
NOT_DONE = {"topic_done": False, "clarifying_question": None}


def basics(tz: str = "America/Chicago", done: bool = True) -> BasicsReply:
    return BasicsReply(timezone=tz, language="en", **(DONE if done else NOT_DONE))


def gatherings(done: bool = True, *extra: GatheringIn) -> GatheringsReply:
    return GatheringsReply(
        gatherings=[
            GatheringIn(
                name="Sunday Service",
                kind=GatheringKind.REGULAR,
                weekday=Weekday.SUNDAY,
                date=None,
                start_time="10:00",
                duration_minutes=90,
            ),
            GatheringIn(
                name="Wednesday Prayer",
                kind=GatheringKind.REGULAR,
                weekday=Weekday.WEDNESDAY,
                date=None,
                start_time="19:00",
                duration_minutes=75,
            ),
            GatheringIn(
                name="Christmas Eve",
                kind=GatheringKind.SPECIAL,
                weekday=None,
                date="2026-12-24",
                start_time="17:00",
                duration_minutes=90,
            ),
            *extra,
        ],
        **(DONE if done else NOT_DONE),
    )


def ministries() -> MinistriesReply:
    return MinistriesReply(
        ministries=[
            MinistryIn(name="Worship", aliases=["Band"]),
            MinistryIn(name="Kids", aliases=[]),
        ],
        **DONE,
    )


def roles() -> RolesReply:
    return RolesReply(
        roles=[
            RoleIn(
                ministry="worship",
                name="Keys",
                minimums=[
                    RoleMinimumIn(gathering="Sunday Service", minimum=1),
                    RoleMinimumIn(gathering="wednesday prayer", minimum=1),
                ],
            ),
            RoleIn(
                ministry="Band",
                name="Vocals",
                minimums=[RoleMinimumIn(gathering="Sunday Service", minimum=2)],
            ),
            RoleIn(
                ministry="Kids",
                name="Helper",
                minimums=[RoleMinimumIn(gathering="Sunday Service", minimum=2)],
            ),
        ],
        **DONE,
    )


def leaders(*, kids_approver: bool = True) -> LeadersReply:
    return LeadersReply(
        leaders=[
            LeaderIn(ministry="Worship", name="David Morales", can_schedule=True, can_approve=True),
            LeaderIn(
                ministry="Kids", name="Sarah Collins", can_schedule=True, can_approve=kids_approver
            ),
        ],
        **DONE,
    )


def load_rules() -> LoadRulesReply:
    return LoadRulesReply(
        load_rules=[LoadRuleIn(period=Period.WEEK, normal_max=1, warning_above=2)],
        absence_threshold_weeks=6,
        **DONE,
    )


def routing() -> RoutingReply:
    return RoutingReply(routing=ChurchProfileDraft().routing, **DONE)


def roster_settings() -> RosterSettingsReply:
    return RosterSettingsReply(
        settings=[
            RosterSettingIn(
                ministry="Kids",
                show_both_paths=False,
                default_path=RosterPath.TRAINING,
                draft_horizon_weeks=6,
            )
        ],
        **DONE,
    )


def availability() -> AvailabilityReply:
    return AvailabilityReply(
        availability=[
            AvailabilityIn(
                leader="sarah collins", weekday=Weekday.THURSDAY, start="12:00", end="13:00"
            )
        ],
        **DONE,
    )


SCRIPT: list[tuple[OnboardingTopic, ReplyBase]] = [
    (T.BASICS, basics()),
    (T.GATHERINGS, gatherings()),
    (T.MINISTRIES, ministries()),
    (T.ROLES, roles()),
    (T.LEADERS, leaders()),
    (T.LOAD_RULES, load_rules()),
    (T.ROUTING, routing()),
    (T.ROSTER_SETTINGS, roster_settings()),
    (T.AVAILABILITY, availability()),
]


def run(
    script: list[tuple[OnboardingTopic, ReplyBase]], draft: ChurchProfileDraft | None = None
) -> ChurchProfileDraft:
    draft = draft or ChurchProfileDraft()
    for topic, reply in script:
        result = apply_reply(draft, topic, reply)
        assert not result.problems, (topic, result.problems)
        draft = result.draft
    return draft


def test_topics_are_asked_in_order_then_review() -> None:
    draft = ChurchProfileDraft()
    seen = []
    for topic, reply in SCRIPT:
        assert next_topic(draft) is topic
        seen.append(topic)
        draft = apply_reply(draft, topic, reply).draft
    assert next_topic(draft) is T.REVIEW
    assert [*seen, T.REVIEW] == TOPIC_ORDER


def test_full_script_produces_a_proposable_draft() -> None:
    draft = run(SCRIPT)
    assert proposal_blockers(draft) == []
    result = apply_reply(draft, T.REVIEW, ReviewReply(change_topic=None, **DONE))
    assert result.ready_to_propose


def test_weekday_gatherings_and_special_events_are_parsed() -> None:
    draft = run(SCRIPT[:2])
    by_name = {g.name: g for g in draft.gatherings}
    assert by_name["Wednesday Prayer"].weekday is Weekday.WEDNESDAY
    assert by_name["Wednesday Prayer"].local_start_time == time(19, 0)
    christmas = by_name["Christmas Eve"]
    assert christmas.kind is GatheringKind.SPECIAL
    assert christmas.one_off_date == date(2026, 12, 24) and christmas.weekday is None


def test_a_clarifying_question_changes_nothing() -> None:
    draft = run(SCRIPT[:1])
    vague = GatheringsReply(
        gatherings=[],
        topic_done=False,
        clarifying_question="What time on Sunday morning does the service start?",
    )
    result = apply_reply(draft, T.GATHERINGS, vague)
    assert result.draft == draft
    assert result.clarifying_question == "What time on Sunday morning does the service start?"


def test_an_unreadable_time_is_reported_and_nothing_changes() -> None:
    draft = run(SCRIPT[:1])
    bad = GatheringsReply(
        gatherings=[
            GatheringIn(
                name="Sunday",
                kind=GatheringKind.REGULAR,
                weekday=Weekday.SUNDAY,
                date=None,
                start_time="morning",
                duration_minutes=60,
            )
        ],
        **DONE,
    )
    result = apply_reply(draft, T.GATHERINGS, bad)
    assert result.draft == draft
    assert any("morning" in p for p in result.problems)


def test_unknown_time_zone_is_not_confirmed() -> None:
    result = apply_reply(ChurchProfileDraft(), T.BASICS, basics("Mars/Olympus"))
    assert T.BASICS not in result.draft.confirmed
    assert result.problems


def test_partial_answer_is_kept_but_topic_stays_open() -> None:
    result = apply_reply(ChurchProfileDraft(), T.BASICS, basics(done=False))
    assert result.draft.timezone == "America/Chicago"
    assert next_topic(result.draft) is T.BASICS


def test_every_ministry_needs_a_scheduler_and_an_approver() -> None:
    draft = run(SCRIPT[:4])
    result = apply_reply(draft, T.LEADERS, leaders(kids_approver=False))
    assert T.LEADERS not in result.draft.confirmed
    assert result.problems == ["Who approves the Kids schedules?"]


def test_roles_must_belong_to_a_known_ministry() -> None:
    draft = run(SCRIPT[:3])
    reply = RolesReply(roles=[RoleIn(ministry="Parking", name="Attendant", minimums=[])], **DONE)
    result = apply_reply(draft, T.ROLES, reply)
    assert result.draft == draft
    assert "Parking" in result.problems[0]


def test_load_rules_may_be_empty_but_never_inverted() -> None:
    draft = run(SCRIPT[:5])
    none = LoadRulesReply(load_rules=[], absence_threshold_weeks=None, **DONE)
    assert T.LOAD_RULES in apply_reply(draft, T.LOAD_RULES, none).draft.confirmed

    inverted = LoadRulesReply(
        load_rules=[LoadRuleIn(period=Period.MONTH, normal_max=3, warning_above=2)],
        absence_threshold_weeks=None,
        **DONE,
    )
    result = apply_reply(draft, T.LOAD_RULES, inverted)
    assert result.draft == draft and result.problems


def test_routing_must_cover_every_finding() -> None:
    draft = run(SCRIPT[:6])
    partial = RoutingReply(
        routing=[DraftRoute(finding=FindingType.OVERLAP, recipients=[Recipient.APPROVER])], **DONE
    )
    result = apply_reply(draft, T.ROUTING, partial)
    assert T.ROUTING not in result.draft.confirmed
    assert len(result.problems) == len(FindingType) - 1


def test_renaming_a_gathering_reopens_roles_that_used_it() -> None:
    draft = run(SCRIPT[:4])
    assert T.ROLES in draft.confirmed
    renamed = gatherings(True)
    renamed.gatherings[0] = renamed.gatherings[0].model_copy(update={"name": "Sunday Morning"})
    result = apply_reply(draft, T.GATHERINGS, renamed)
    assert T.GATHERINGS in result.draft.confirmed
    assert T.ROLES not in result.draft.confirmed
    assert next_topic(result.draft) is T.ROLES


def test_review_can_send_the_admin_back_to_a_section() -> None:
    draft = run(SCRIPT)
    result = apply_reply(draft, T.REVIEW, ReviewReply(change_topic=T.LOAD_RULES, **NOT_DONE))
    assert next_topic(result.draft) is T.LOAD_RULES
    assert not result.ready_to_propose


def test_review_refuses_to_propose_an_incomplete_draft() -> None:
    draft = run(SCRIPT[:3])
    result = apply_reply(draft, T.REVIEW, ReviewReply(change_topic=None, **DONE))
    assert not result.ready_to_propose
    assert result.problems


def test_summary_names_weekday_gatherings_and_special_events() -> None:
    summary = render_summary(run(SCRIPT))
    assert "Wednesday Prayer: every Wednesday at 7:00 PM, 75 minutes, regular" in summary
    assert "Christmas Eve: Thursday 24 December 2026 at 5:00 PM, 90 minutes, special" in summary
    assert "Kids: only the training path, drafted 6 weeks ahead" in summary
    assert (
        "Per week: up to 1 is normal, 2 to 2 is noted for the approver, more than 2 is a warning."
        in summary
    )
    assert "Sarah Collins: Thursday 12:00 PM to 1:00 PM" in summary


# ---------------------------------------------------------------------------
# Sample schedules
# ---------------------------------------------------------------------------


def slot(
    day: str, at: str, ministry: str, role: str, count: int, gathering: str | None = None
) -> SampleSlot:
    return SampleSlot(
        date=day,
        weekday=None,
        start_time=at,
        gathering=gathering,
        ministry=ministry,
        role=role,
        people_count=count,
    )


THREE_WEEKS = SampleReply(
    slots=[
        *(
            slot(d, "19:00", "Worship", "Keys", 1)
            for d in ("2026-09-02", "2026-09-09", "2026-09-16")
        ),
        slot("2026-09-06", "09:30", "Kids", "Helper", 2),
        slot("2026-09-13", "09:30", "Kids", "Helper", 2),
        slot("2026-09-20", "09:30", "Kids", "Helper", 3),
        slot("2026-09-24", "18:00", "Worship", "Vocals", 4, gathering="Harvest Night"),
    ],
    clarifying_question=None,
)


def test_sample_infers_weekly_gatherings_one_offs_and_minimums() -> None:
    draft, added = infer_from_sample(ChurchProfileDraft(), THREE_WEEKS)
    by_name = {g.name: g for g in draft.gatherings}

    wednesday = by_name["Wednesday 7:00 PM"]
    assert (wednesday.weekday, wednesday.local_start_time) == (Weekday.WEDNESDAY, time(19, 0))
    assert by_name["Sunday 9:30 AM"].weekday is Weekday.SUNDAY
    harvest = by_name["Harvest Night"]
    assert harvest.one_off_date == date(2026, 9, 24) and harvest.weekday is None
    assert all(g.inferred for g in draft.gatherings)

    kids = next(m for m in draft.ministries if m.name == "Kids")
    (helper,) = kids.roles
    assert [(m.gathering, m.minimum) for m in helper.minimums] == [
        ("Sunday 9:30 AM", 2)
    ]  # most common count
    assert added


def test_inferred_items_block_the_proposal_until_confirmed() -> None:
    draft = run(SCRIPT)
    draft, _ = infer_from_sample(draft, THREE_WEEKS)
    assert T.GATHERINGS not in draft.confirmed and T.ROLES not in draft.confirmed
    assert any("sample schedule" in p for p in proposal_blockers(draft))

    # The admin looks at the gatherings as shown and says they're right.
    shown = GatheringsReply(
        gatherings=[
            GatheringIn(
                name=g.name,
                kind=g.kind,
                weekday=g.weekday,
                date=g.one_off_date.isoformat() if g.one_off_date else None,
                start_time=g.local_start_time.strftime("%H:%M"),
                duration_minutes=g.duration_minutes,
            )
            for g in draft.gatherings
        ],
        **DONE,
    )
    draft = apply_reply(draft, T.GATHERINGS, shown).draft
    assert not any(g.inferred for g in draft.gatherings)


def test_sample_never_overwrites_what_the_admin_said() -> None:
    draft = run(SCRIPT[:4])
    sample = SampleReply(
        slots=[slot("2026-09-02", "19:00", "Worship", "Keys", 3, gathering="Wednesday Prayer")],
        clarifying_question=None,
    )
    updated, added = infer_from_sample(draft, sample)
    assert updated.gatherings == draft.gatherings
    keys = next(r for m in updated.ministries for r in m.roles if r.name == "Keys")
    assert {m.gathering: m.minimum for m in keys.minimums}["Wednesday Prayer"] == 1
    assert added == []
