"""Ask Shepherd: what the model reads from a leader's question.

The model only says what was asked (an intent, a name as written, a date). Code
finds the facts and writes the answer (architecture rule 2).
"""

from pydantic import BaseModel, Field

from app.domain.enums import AskIntent


class ParsedQuestion(BaseModel):
    intent: AskIntent = Field(description="What the question asks for")
    person: str | None = Field(
        description="The one person the question is about, copied as written; null if none"
    )
    date: str | None = Field(
        description="YYYY-MM-DD resolved against today's date in the facts; null if no date"
    )
