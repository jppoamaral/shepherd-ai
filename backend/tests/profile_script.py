"""Scripted admin answers (as model replies) that build a complete church profile."""

from app.domain.enums import (
    GatheringKind,
    OnboardingTopic,
    Period,
    RosterPath,
    Weekday,
)
from app.domain.profile import (
    AvailabilityIn,
    AvailabilityReply,
    BasicsReply,
    ChurchProfileDraft,
    GatheringIn,
    GatheringsReply,
    LeaderIn,
    LeadersReply,
    LoadRuleIn,
    LoadRulesReply,
    MinistriesReply,
    MinistryIn,
    ReplyBase,
    RoleIn,
    RoleMinimumIn,
    RolesReply,
    RosterSettingIn,
    RosterSettingsReply,
    RoutingReply,
    SampleReply,
    SampleSlot,
)
from app.services.profile import apply_reply

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
