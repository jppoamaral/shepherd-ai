"""The language-model seam (architecture rule 2).

The model only handles language: parsing free text, matching names, classifying
replies, explaining and drafting, always from facts passed in. Every call returns
a validated Pydantic object (structured output); there is no free-form text API.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    def complete(self, *, system: str, user: str, schema: type[T]) -> T:
        """Return the model's answer parsed into `schema`."""
        ...
