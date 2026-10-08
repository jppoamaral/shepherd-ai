"""All models, imported here so Alembic and `Base.metadata` see every table."""

from app.db.models.church import Church, Gathering, GatheringType, LoadRule
from app.db.models.coordination import Finding, Huddle, MemoryItem, Message
from app.db.models.governance import AuditLog, Proposal
from app.db.models.ministry import LeaderAvailability, Ministry, MinistryLeader, Role, RoleMinimum
from app.db.models.people import (
    Blockout,
    Membership,
    Person,
    Preference,
    PreferredGathering,
    RoleSkill,
)
from app.db.models.roster import Assignment, RosterSuggestion

__all__ = [
    "Assignment",
    "AuditLog",
    "Blockout",
    "Church",
    "Finding",
    "Gathering",
    "GatheringType",
    "Huddle",
    "LeaderAvailability",
    "LoadRule",
    "Membership",
    "MemoryItem",
    "Message",
    "Ministry",
    "MinistryLeader",
    "Person",
    "Preference",
    "PreferredGathering",
    "Proposal",
    "Role",
    "RoleMinimum",
    "RoleSkill",
    "RosterSuggestion",
]
