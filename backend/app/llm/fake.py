"""Deterministic stand-in for tests: returns queued responses per schema."""

from collections import defaultdict, deque
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    def __init__(self) -> None:
        self._responses: dict[type[BaseModel], deque[BaseModel]] = defaultdict(deque)
        self.calls: list[dict[str, Any]] = []

    def queue(self, response: BaseModel) -> None:
        self._responses[type(response)].append(response)

    def complete(self, *, system: str, user: str, schema: type[T]) -> T:
        self.calls.append({"system": system, "user": user, "schema": schema})
        queued = self._responses[schema]
        if not queued:
            raise AssertionError(f"FakeLLM has no queued response for {schema.__name__}")
        response = queued.popleft()
        assert isinstance(response, schema)
        return response
