"""Enumerations shared by the database, services and API. No I/O."""

from enum import StrEnum


class ProfileStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class GatheringKind(StrEnum):
    REGULAR = "regular"
    SPECIAL = "special"


class Recurrence(StrEnum):
    WEEKLY = "weekly"
    ONE_OFF = "one_off"


class Weekday(StrEnum):
    """Weekday names; `.number` matches `date.weekday()` (Monday = 0)."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    @property
    def number(self) -> int:
        return list(Weekday).index(self)


class Period(StrEnum):
    WEEK = "week"
    MONTH = "month"


class RosterPath(StrEnum):
    TRAINING = "training"
    VETERAN = "veteran"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Experience(StrEnum):
    """Set only by a leader, never computed (architecture rule 7)."""

    NEW = "new"
    EXPERIENCED = "experienced"
    VETERAN = "veteran"


class StatedBy(StrEnum):
    """Who told Shepherd a preference or blockout. Volunteers may only see their own."""

    VOLUNTEER = "volunteer"
    LEADER = "leader"


class AssignmentStatus(StrEnum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    SERVED = "served"


class AssignmentSource(StrEnum):
    SUGGESTION = "suggestion"
    LEADER = "leader"


class FindingType(StrEnum):
    OVERLAP = "overlap"
    BLOCKOUT = "blockout"
    BELOW_MINIMUM = "below_minimum"
    LOAD = "load"
    ABSENT = "absent"
    SILENT_MINISTRY = "silent_ministry"
    UNMATCHED_NAME = "unmatched_name"


class FindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class MemoryKind(StrEnum):
    HABIT = "habit"
    PREFERENCE = "preference"
    GROWTH = "growth"
    RULE = "rule"


class MemorySource(StrEnum):
    LEADER_EDIT = "leader_edit"
    LEADER_NOTE = "leader_note"
    VOLUNTEER = "volunteer"


class HuddleStatus(StrEnum):
    OFFERED = "offered"
    SCHEDULED = "scheduled"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class MessageStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class OnboardingTopic(StrEnum):
    """Onboarding interview topics, in the order the agent asks them."""

    BASICS = "basics"
    GATHERINGS = "gatherings"
    MINISTRIES = "ministries"
    ROLES = "roles"
    LEADERS = "leaders"
    LOAD_RULES = "load_rules"
    ROUTING = "routing"
    ROSTER_SETTINGS = "roster_settings"
    AVAILABILITY = "availability"
    REVIEW = "review"


class OnboardingStatus(StrEnum):
    ACTIVE = "active"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
