"""Value types for turning gathering recurrences into concrete occurrences."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time

from app.domain.enums import Recurrence, Weekday


@dataclass(frozen=True)
class GatheringTypeSpec:
    """The parts of a GatheringType needed to place it in time (church-local)."""

    id: uuid.UUID
    recurrence: Recurrence
    weekday: Weekday | None
    one_off_date: date | None
    local_start_time: time
    duration_minutes: int
    active: bool = True


@dataclass(frozen=True)
class Occurrence:
    gathering_type_id: uuid.UUID
    start_at: datetime  # timezone-aware
    end_at: datetime  # timezone-aware
