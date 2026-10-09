"""The two synthetic churches. Values here stand in for what each church would tell
Shepherd during onboarding; nothing in app code assumes them.
"""

from datetime import date, time

from app.domain.enums import Experience, GatheringKind, MemoryKind, MemorySource, Period, Weekday
from seeds.spec import (
    AssignmentSeed,
    AvailabilitySeed,
    BlockoutSeed,
    ChurchSeed,
    GatheringTypeSeed,
    LeaderSeed,
    MemorySeed,
    MinistrySeed,
    PersonSeed,
    RoleSeed,
)

NEW, EXP, VET = Experience.NEW, Experience.EXPERIENCED, Experience.VETERAN
WORSHIP, KIDS, MEDIA, HOSPITALITY = "Worship", "Kids", "Media", "Hospitality"

# Section 5 routing, as both churches answered it in onboarding.
WARNING_ROUTING = {
    "overlap": ["scheduler", "approver"],
    "blockout": ["scheduler"],
    "below_minimum": ["scheduler"],
    "load": ["approver"],
    "absent": ["approver"],
    "silent_ministry": ["approver"],
    "unmatched_name": ["scheduler"],
}


def _sundays(*keys: str, n: int) -> dict[str, int]:
    return dict.fromkeys(keys, n)


# --------------------------------------------------------------------------------------
# Grace Community: ~150 members, serving weekly is normal.
# --------------------------------------------------------------------------------------

GRACE_SUN = ("sun_0930", "sun_1100")


def grace_community() -> ChurchSeed:
    return ChurchSeed(
        name="Grace Community",
        timezone="America/Chicago",
        member_count=150,
        absence_threshold_weeks=6,
        load_rules=[(Period.WEEK, 1, 2)],
        gathering_types=[
            GatheringTypeSeed("sun_0930", "Sunday 9:30 Service", time(9, 30), 75, Weekday.SUNDAY),
            GatheringTypeSeed("sun_1100", "Sunday 11:00 Service", time(11, 0), 75, Weekday.SUNDAY),
            GatheringTypeSeed(
                "wed_prayer", "Wednesday Prayer Night", time(19, 0), 75, Weekday.WEDNESDAY
            ),
            # Overlaps prayer night (19:30-21:00 vs 19:00-20:15) on purpose: section 11
            # needs a midweek conflict that is flagged like a Sunday one.
            GatheringTypeSeed("wed_youth", "Wednesday Youth", time(19, 30), 90, Weekday.WEDNESDAY),
        ],
        ministries=[
            MinistrySeed(
                WORSHIP,
                aliases=["Worship Team", "Band", "Music"],
                weight=1.8,
                roles=[
                    RoleSeed(
                        "Worship Leader",
                        {**_sundays(*GRACE_SUN, n=1), "wed_prayer": 1, "wed_youth": 1},
                    ),
                    RoleSeed("Vocals", {**_sundays(*GRACE_SUN, n=2), "wed_prayer": 1}),
                    RoleSeed("Keys", {**_sundays(*GRACE_SUN, n=1), "wed_prayer": 1}),
                    RoleSeed("Guitar", {**_sundays(*GRACE_SUN, n=1), "wed_youth": 1}),
                    RoleSeed("Bass", _sundays(*GRACE_SUN, n=1)),
                    RoleSeed("Drums", _sundays(*GRACE_SUN, n=1)),
                ],
                leaders=[LeaderSeed("david", can_schedule=True, can_approve=True)],
            ),
            MinistrySeed(
                KIDS,
                aliases=["Kids Ministry", "Children's Ministry", "Sunday School"],
                weight=1.0,
                roles=[
                    RoleSeed("Lead Teacher", _sundays(*GRACE_SUN, n=1)),
                    RoleSeed("Helper", _sundays(*GRACE_SUN, n=2)),
                    RoleSeed("Check-in", _sundays(*GRACE_SUN, n=1)),
                ],
                leaders=[LeaderSeed("sarah", can_schedule=True, can_approve=True)],
            ),
            MinistrySeed(
                MEDIA,
                aliases=["Tech", "AV", "Production"],
                weight=0.7,
                roles=[
                    RoleSeed(
                        "Sound", {**_sundays(*GRACE_SUN, n=1), "wed_prayer": 1, "wed_youth": 1}
                    ),
                    RoleSeed("Slides", {**_sundays(*GRACE_SUN, n=1), "wed_youth": 1}),
                ],
                leaders=[
                    LeaderSeed("tom", can_schedule=True, can_approve=False),
                    LeaderSeed("pastor_mike", can_schedule=False, can_approve=True),
                ],
            ),
            MinistrySeed(
                HOSPITALITY,
                aliases=["Welcome Team", "Greeters"],
                weight=0.9,
                roles=[
                    RoleSeed(
                        "Greeter",
                        {**_sundays(*GRACE_SUN, n=2), "wed_prayer": 1, "wed_youth": 1},
                    ),
                    RoleSeed("Coffee", _sundays(*GRACE_SUN, n=1)),
                ],
                leaders=[
                    LeaderSeed("linda", can_schedule=True, can_approve=False),
                    LeaderSeed("pastor_mike", can_schedule=False, can_approve=True),
                ],
            ),
        ],
        people=[
            PersonSeed(
                "sarah",
                "Sarah Collins",
                skills={KIDS: {"Lead Teacher": VET}},
                availability=[
                    AvailabilitySeed(Weekday.MONDAY, time(9, 0), time(11, 0)),
                    AvailabilitySeed(Weekday.THURSDAY, time(12, 0), time(13, 30)),
                    AvailabilitySeed(Weekday.SATURDAY, time(9, 30), time(11, 30)),
                ],
            ),
            PersonSeed(
                "david",
                "David Morales",
                nicknames=["Dave"],
                skills={WORSHIP: {"Worship Leader": VET, "Guitar": VET}},
                availability=[
                    AvailabilitySeed(Weekday.TUESDAY, time(18, 0), time(20, 0)),
                    AvailabilitySeed(Weekday.THURSDAY, time(12, 0), time(13, 0)),
                    AvailabilitySeed(Weekday.SATURDAY, time(10, 0), time(12, 0)),
                ],
            ),
            PersonSeed(
                "anna_parker",
                "Anna Parker",
                nicknames=["Anna P."],
                skills={WORSHIP: {"Keys": VET}, KIDS: {"Helper": EXP}},
                preferred_frequency=(2, Period.WEEK),
            ),
            PersonSeed(
                "anna_peterson",
                "Anna Peterson",
                nicknames=["Anna P."],
                skills={KIDS: {"Helper": EXP, "Check-in": EXP}},
            ),
            PersonSeed("rachel", "Rachel Turner", skills={KIDS: {"Helper": NEW}}),
            PersonSeed(
                "emily",
                "Emily Brooks",
                skills={KIDS: {"Helper": VET, "Lead Teacher": EXP}},
                preferred_gatherings=["sun_0930"],
            ),
            PersonSeed(
                "megan",
                "Megan Lee",
                skills={KIDS: {"Check-in": EXP}, HOSPITALITY: {"Greeter": EXP}},
                blockouts=[BlockoutSeed(11, 11)],
            ),
            PersonSeed(
                "hannah",
                "Hannah Wright",
                skills={WORSHIP: {"Vocals": EXP}, MEDIA: {"Sound": EXP}},
            ),
            PersonSeed(
                "tom",
                "Tom Becker",
                nicknames=["Tommy"],
                skills={MEDIA: {"Sound": VET, "Slides": VET}},
                availability=[AvailabilitySeed(Weekday.WEDNESDAY, time(17, 0), time(18, 30))],
            ),
            PersonSeed(
                "linda",
                "Linda Shaw",
                skills={HOSPITALITY: {"Greeter": VET, "Coffee": VET}},
                availability=[AvailabilitySeed(Weekday.THURSDAY, time(12, 0), time(13, 0))],
            ),
            PersonSeed(
                "pastor_mike",
                "Mike Harris",
                nicknames=["Pastor Mike"],
                availability=[
                    AvailabilitySeed(Weekday.TUESDAY, time(9, 0), time(12, 0)),
                    AvailabilitySeed(Weekday.THURSDAY, time(9, 0), time(12, 0)),
                ],
            ),
        ],
        # The demo week (first upcoming Sunday to Saturday):
        # - Hannah sings at prayer night and runs sound at youth, which overlap (midweek clash).
        # - Anna Parker is on Kids and Worship at the same 9:30 service (double booking across
        #   ministries) and serves 4 times in the week, above her preferred 2 and Grace's limit.
        assignments=[
            AssignmentSeed("hannah", WORSHIP, "Vocals", "wed_prayer"),
            AssignmentSeed("hannah", MEDIA, "Sound", "wed_youth"),
            AssignmentSeed("anna_parker", KIDS, "Helper", "sun_0930"),
            AssignmentSeed("anna_parker", WORSHIP, "Keys", "sun_0930"),
            AssignmentSeed("anna_parker", WORSHIP, "Keys", "sun_1100"),
            AssignmentSeed("anna_parker", WORSHIP, "Keys", "wed_prayer"),
            AssignmentSeed("emily", KIDS, "Helper", "sun_0930"),
            AssignmentSeed("rachel", KIDS, "Helper", "sun_0930"),
            AssignmentSeed("sarah", KIDS, "Lead Teacher", "sun_0930"),
            AssignmentSeed("megan", KIDS, "Check-in", "sun_0930"),
            AssignmentSeed("david", WORSHIP, "Worship Leader", "sun_0930"),
            AssignmentSeed("david", WORSHIP, "Worship Leader", "sun_1100"),
        ],
        fill_rosters=[(WORSHIP, "sun_0930"), (WORSHIP, "sun_1100"), (WORSHIP, "wed_prayer")],
        memories=[
            MemorySeed(
                KIDS,
                MemoryKind.HABIT,
                "You always pair Emily with Rachel.",
                MemorySource.LEADER_EDIT,
                about="rachel",
                confirmed_by="sarah",
            ),
            MemorySeed(
                KIDS,
                MemoryKind.PREFERENCE,
                "Emily prefers the 9:30 service.",
                MemorySource.VOLUNTEER,
                about="emily",
                confirmed_by="sarah",
            ),
            MemorySeed(
                WORSHIP,
                MemoryKind.RULE,
                "Keep the band together for a whole month.",
                MemorySource.LEADER_NOTE,
                confirmed_by="david",
            ),
            MemorySeed(
                KIDS,
                MemoryKind.GROWTH,
                "Rachel is ready to lead a class.",
                MemorySource.LEADER_NOTE,
                about="rachel",
            ),
        ],
        generated_volunteers=32,
        generated_preferences=[(1, Period.WEEK), (2, Period.MONTH), (3, Period.MONTH)],
        random_seed=150,
        warning_routing=WARNING_ROUTING,
    )


# --------------------------------------------------------------------------------------
# Riverside Fellowship: ~800 members, serving capped at twice a month.
# --------------------------------------------------------------------------------------

RIVER_SUN = ("sun_0900", "sun_1100")


def next_christmas_eve(today: date) -> date:
    this_year = date(today.year, 12, 24)
    return this_year if today <= this_year else date(today.year + 1, 12, 24)


def riverside_fellowship(today: date) -> ChurchSeed:
    xmas = "christmas_eve"
    return ChurchSeed(
        name="Riverside Fellowship",
        timezone="America/Los_Angeles",
        member_count=800,
        absence_threshold_weeks=8,
        load_rules=[(Period.MONTH, 2, 2)],
        gathering_types=[
            GatheringTypeSeed("sun_0900", "Sunday 9:00 Service", time(9, 0), 75, Weekday.SUNDAY),
            GatheringTypeSeed("sun_1100", "Sunday 11:00 Service", time(11, 0), 75, Weekday.SUNDAY),
            GatheringTypeSeed("fri_youth", "Friday Youth Night", time(19, 0), 120, Weekday.FRIDAY),
            GatheringTypeSeed(
                xmas,
                "Christmas Eve Service",
                time(17, 0),
                90,
                one_off_date=next_christmas_eve(today),
                kind=GatheringKind.SPECIAL,
            ),
        ],
        ministries=[
            MinistrySeed(
                WORSHIP,
                aliases=["Worship Team", "Band"],
                weight=1.3,
                draft_horizon_weeks=8,
                roles=[
                    RoleSeed(
                        "Worship Leader",
                        {**_sundays(*RIVER_SUN, n=1), "fri_youth": 1, xmas: 1},
                    ),
                    RoleSeed("Vocals", {**_sundays(*RIVER_SUN, n=2), xmas: 4}),
                    RoleSeed("Keys", {**_sundays(*RIVER_SUN, n=1), xmas: 1}),
                    RoleSeed("Guitar", {**_sundays(*RIVER_SUN, n=1), "fri_youth": 1, xmas: 2}),
                    RoleSeed("Bass", {**_sundays(*RIVER_SUN, n=1), xmas: 1}),
                    RoleSeed("Drums", {**_sundays(*RIVER_SUN, n=1), "fri_youth": 1, xmas: 1}),
                ],
                leaders=[
                    LeaderSeed("marcus", can_schedule=True, can_approve=False),
                    LeaderSeed("pastor_jenna", can_schedule=False, can_approve=True),
                ],
            ),
            MinistrySeed(
                KIDS,
                aliases=["Riverside Kids", "Children's Church"],
                weight=1.1,
                draft_horizon_weeks=4,
                roles=[
                    RoleSeed("Lead Teacher", {**_sundays(*RIVER_SUN, n=1), xmas: 1}),
                    RoleSeed("Helper", {**_sundays(*RIVER_SUN, n=2), xmas: 3}),
                    RoleSeed("Check-in", {**_sundays(*RIVER_SUN, n=1), xmas: 2}),
                ],
                leaders=[
                    LeaderSeed("priya", can_schedule=True, can_approve=False),
                    LeaderSeed("carol", can_schedule=False, can_approve=True),
                ],
            ),
            MinistrySeed(
                MEDIA,
                aliases=["Production", "Tech Team"],
                weight=0.8,
                draft_horizon_weeks=6,
                roles=[
                    RoleSeed("Sound", {**_sundays(*RIVER_SUN, n=1), "fri_youth": 1, xmas: 1}),
                    RoleSeed("Slides", {**_sundays(*RIVER_SUN, n=1), "fri_youth": 1, xmas: 1}),
                    RoleSeed("Livestream", {**_sundays(*RIVER_SUN, n=1), xmas: 1}),
                ],
                leaders=[LeaderSeed("ben", can_schedule=True, can_approve=True)],
            ),
            MinistrySeed(
                HOSPITALITY,
                aliases=["Guest Services", "First Impressions"],
                weight=1.0,
                draft_horizon_weeks=4,
                roles=[
                    RoleSeed("Greeter", {**_sundays(*RIVER_SUN, n=2), "fri_youth": 1, xmas: 4}),
                    RoleSeed("Usher", {**_sundays(*RIVER_SUN, n=1), xmas: 3}),
                    RoleSeed("Coffee", {**_sundays(*RIVER_SUN, n=1), xmas: 1}),
                ],
                leaders=[
                    LeaderSeed("gloria", can_schedule=True, can_approve=False),
                    LeaderSeed("pastor_jenna", can_schedule=False, can_approve=True),
                ],
            ),
        ],
        people=[
            PersonSeed(
                "marcus",
                "Marcus Reid",
                skills={WORSHIP: {"Worship Leader": VET, "Keys": VET}},
                availability=[AvailabilitySeed(Weekday.TUESDAY, time(19, 0), time(21, 0))],
            ),
            PersonSeed(
                "pastor_jenna",
                "Jenna Ortiz",
                nicknames=["Pastor Jenna"],
                availability=[
                    AvailabilitySeed(Weekday.TUESDAY, time(10, 0), time(12, 0)),
                    AvailabilitySeed(Weekday.WEDNESDAY, time(14, 0), time(16, 0)),
                ],
            ),
            PersonSeed(
                "priya",
                "Priya Shah",
                skills={KIDS: {"Lead Teacher": VET}},
                availability=[AvailabilitySeed(Weekday.WEDNESDAY, time(13, 0), time(15, 0))],
            ),
            PersonSeed(
                "carol",
                "Carol Nguyen",
                skills={KIDS: {"Helper": VET}},
                availability=[AvailabilitySeed(Weekday.MONDAY, time(18, 0), time(19, 30))],
            ),
            PersonSeed(
                "ben",
                "Ben Foster",
                skills={MEDIA: {"Sound": VET, "Livestream": VET}},
                availability=[AvailabilitySeed(Weekday.THURSDAY, time(19, 0), time(20, 0))],
            ),
            PersonSeed(
                "gloria",
                "Gloria Adams",
                skills={HOSPITALITY: {"Greeter": VET, "Usher": VET}},
                availability=[AvailabilitySeed(Weekday.WEDNESDAY, time(14, 30), time(16, 0))],
            ),
        ],
        generated_volunteers=64,
        generated_preferences=[(1, Period.MONTH), (2, Period.MONTH)],
        random_seed=800,
        warning_routing=WARNING_ROUTING,
    )
