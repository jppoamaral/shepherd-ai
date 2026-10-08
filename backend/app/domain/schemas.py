"""Read-side API shapes. Pydantic only; no I/O."""

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    Experience,
    GatheringKind,
    MembershipStatus,
    Period,
    ProfileStatus,
    Recurrence,
    RosterPath,
    Weekday,
)


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoadRuleOut(Schema):
    period: Period
    normal_max: int
    warning_above: int


class ChurchOut(Schema):
    id: uuid.UUID
    name: str
    timezone: str
    language: str
    profile_status: ProfileStatus
    member_count: int | None
    load_rules: list[LoadRuleOut]


class GatheringTypeOut(Schema):
    id: uuid.UUID
    name: str
    kind: GatheringKind
    recurrence: Recurrence
    weekday: Weekday | None
    one_off_date: date | None
    local_start_time: time
    duration_minutes: int


class RoleMinimumOut(Schema):
    gathering_type_id: uuid.UUID
    minimum: int


class RoleOut(Schema):
    id: uuid.UUID
    name: str
    minimums: list[RoleMinimumOut]


class LeaderOut(Schema):
    person_id: uuid.UUID
    name: str
    can_schedule: bool
    can_approve: bool


class MinistryOut(Schema):
    id: uuid.UUID
    name: str
    aliases: list[str]
    show_both_paths: bool
    default_path: RosterPath
    draft_horizon_weeks: int
    roles: list[RoleOut]
    leaders: list[LeaderOut]


class RoleSkillOut(Schema):
    role_id: uuid.UUID
    role: str
    experience: Experience


class MembershipOut(Schema):
    ministry_id: uuid.UUID
    ministry: str
    status: MembershipStatus
    last_served: date | None
    roles: list[RoleSkillOut]


class PersonOut(Schema):
    id: uuid.UUID
    name: str
    nicknames: list[str]
    opted_in: bool
    stopped: bool
    memberships: list[MembershipOut]


class GatheringOut(Schema):
    id: uuid.UUID
    gathering_type_id: uuid.UUID
    name: str
    kind: GatheringKind
    start_at: datetime  # in the church's time zone, with offset
    end_at: datetime
