"""Deterministic synthetic volunteers to fill out realistic rosters."""

import random

from app.domain.enums import Experience
from seeds.spec import BlockoutSeed, ChurchSeed, PersonSeed

FIRST_NAMES = [
    "Aaron", "Abigail", "Adam", "Alexander", "Alicia", "Amy", "Andrew", "Angela", "Benjamin",
    "Brandon", "Brianna", "Caleb", "Cameron", "Chloe", "Christopher", "Claire", "Daniel",
    "Deborah", "Derek", "Diana", "Elijah", "Elizabeth", "Ethan", "Faith", "Gabriel", "Grace",
    "Isaac", "Isabel", "Jacob", "Jasmine", "Jennifer", "Jessica", "Jonathan", "Jordan", "Joshua",
    "Julia", "Kayla", "Kevin", "Laura", "Leah", "Lucas", "Lydia", "Matthew", "Maya", "Michelle",
    "Miriam", "Naomi", "Nathan", "Nicholas", "Noah", "Olivia", "Paul", "Peter", "Rebecca",
    "Robert", "Ruth", "Samuel", "Sophia", "Stephen", "Tabitha", "Timothy", "Tyler", "Victoria",
    "William", "Zachary", "Zoe",
]  # fmt: skip

LAST_NAMES = [
    "Allen", "Bailey", "Baker", "Bell", "Bennett", "Campbell", "Carter", "Clark", "Cooper",
    "Davis", "Diaz", "Edwards", "Evans", "Fisher", "Garcia", "Gray", "Green", "Hall", "Hayes",
    "Hill", "Howard", "Hughes", "Jackson", "James", "Jenkins", "Johnson", "Kelly", "King",
    "Lopez", "Martin", "Mitchell", "Moore", "Murphy", "Nelson", "Owens", "Patel", "Perry",
    "Phillips", "Price", "Ramirez", "Reed", "Richardson", "Roberts", "Robinson", "Rogers",
    "Russell", "Sanders", "Scott", "Simmons", "Stewart", "Sullivan", "Taylor", "Thomas",
    "Torres", "Walker", "Ward", "Watson", "White", "Williams", "Wood", "Young",
]  # fmt: skip

NICKNAMES = {
    "Abigail": "Abby", "Alexander": "Alex", "Benjamin": "Ben", "Christopher": "Chris",
    "Daniel": "Dan", "Deborah": "Deb", "Elizabeth": "Liz", "Jennifer": "Jen", "Jessica": "Jess",
    "Jonathan": "Jon", "Joshua": "Josh", "Matthew": "Matt", "Michelle": "Shelly",
    "Nicholas": "Nick", "Rebecca": "Becca", "Robert": "Rob", "Samuel": "Sam", "Stephen": "Steve",
    "Timothy": "Tim", "Victoria": "Tori", "William": "Will", "Zachary": "Zach",
}  # fmt: skip


def generate_volunteers(church: ChurchSeed) -> list[PersonSeed]:
    """`church.generated_volunteers` people spread over ministries and roles.

    Roles are dealt in proportion to their largest minimum, and the first person
    dealt each role is a veteran, so every role has someone who can lead it.
    """
    rng = random.Random(church.random_seed)
    taken = {p.name for p in church.people}
    taken_first = {p.name.split()[0] for p in church.people}
    names = [
        f"{first} {last}"
        for first in FIRST_NAMES
        for last in LAST_NAMES
        if first not in taken_first and f"{first} {last}" not in taken
    ]
    rng.shuffle(names)
    # One person per first name keeps nickname matching unambiguous except where seeded on purpose.
    chosen: list[str] = []
    seen_first: set[str] = set()
    for name in names:
        first = name.split()[0]
        if first not in seen_first:
            chosen.append(name)
            seen_first.add(first)
        if len(chosen) == church.generated_volunteers:
            break

    ministries = church.ministries
    role_decks = {
        m.name: [r.name for r in m.roles for _ in range(max(r.minimums.values(), default=1))]
        for m in ministries
    }
    for deck in role_decks.values():
        rng.shuffle(deck)
    dealt: dict[str, int] = dict.fromkeys(role_decks, 0)
    has_veteran: set[tuple[str, str]] = set()

    def deal(ministry: str) -> tuple[str, Experience]:
        deck = role_decks[ministry]
        role = deck[dealt[ministry] % len(deck)]
        dealt[ministry] += 1
        if (ministry, role) not in has_veteran:
            has_veteran.add((ministry, role))
            return role, Experience.VETERAN
        return role, rng.choices(list(Experience), weights=[25, 45, 30])[0]

    people: list[PersonSeed] = []
    for i, name in enumerate(chosen):
        first = name.split()[0]
        ministry = rng.choices(ministries, weights=[m.weight for m in ministries])[0].name
        role, experience = deal(ministry)
        skills = {ministry: {role: experience}}
        if rng.random() < 0.3:
            second_role, second_exp = deal(ministry)
            skills[ministry].setdefault(second_role, second_exp)
        if rng.random() < 0.2:
            other = rng.choice([m.name for m in ministries if m.name != ministry])
            other_role, other_exp = deal(other)
            skills[other] = {other_role: other_exp}

        blockouts = []
        if rng.random() < 0.3:
            start = rng.randint(3, 80)
            blockouts.append(BlockoutSeed(start, start + rng.choice([0, 0, 2, 6, 9])))

        preference = (
            rng.choice(church.generated_preferences)
            if church.generated_preferences and rng.random() < 0.5
            else None
        )
        people.append(
            PersonSeed(
                key=f"gen_{i:03d}",
                name=name,
                nicknames=[NICKNAMES[first]] if first in NICKNAMES else [],
                skills=skills,
                preferred_frequency=preference,
                blockouts=blockouts,
                opted_in=rng.random() < 0.85,
            )
        )
    return people
