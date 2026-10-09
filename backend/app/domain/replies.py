"""A volunteer's free-text chat message, as the model reads it. Code decides what to do."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ReplyIntent(StrEnum):
    CONFIRM = "confirm"  # yes, will serve
    DECLINE = "decline"  # can't serve
    MAYBE = "maybe"  # unsure, depends
    AWAY = "away"  # gives dates they are away or unavailable
    WHAT_I_KNOW = "what_i_know"  # asks what Shepherd keeps about them
    STOP = "stop"
    START = "start"
    OTHER = "other"


class ParsedReply(BaseModel):
    intent: ReplyIntent = Field(description="What the message says")
    dates: list[str] = Field(
        description="For away: each date they are away as YYYY-MM-DD, resolved against today; "
        "a range becomes every day in it. Empty otherwise."
    )
