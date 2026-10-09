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


class Recipient(StrEnum):
    """Who in a ministry hears about a finding first (warning routing)."""

    SCHEDULER = "scheduler"
    APPROVER = "approver"


class IntakeStatus(StrEnum):
    NEEDS_ANSWERS = "needs_answers"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class QuestionKind(StrEnum):
    AMBIGUOUS_NAME = "ambiguous_name"
    UNKNOWN_NAME = "unknown_name"
    NOT_ON_TEAM = "not_on_team"
    WHICH_GATHERING = "which_gathering"
    UNKNOWN_ROLE = "unknown_role"


class AskIntent(StrEnum):
    """What a leader's Ask Shepherd question is about. Code answers each one."""

    NEEDS_ME = "needs_me"  # what needs me this week
    FREE_ON = "free_on"  # who is free on a date
    REPLACE = "replace"  # who can take someone's place
    SERVING_A_LOT = "serving_a_lot"  # who is serving a lot right now
    DRAFT_REMINDER = "draft_reminder"  # reminders for a date's roster
    DRAFT_MESSAGE = "draft_message"  # a 1:1 ask to one person
    REMEMBER = "remember"  # what Shepherd remembers about someone
    AVAILABILITY = "availability"  # someone's blocked-out dates
    PRIVATE = "private"  # health, family or personal reasons: never answered
    UNKNOWN = "unknown"
