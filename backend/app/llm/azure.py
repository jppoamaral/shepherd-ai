"""Azure OpenAI implementation of LLMClient. Wired up in a later milestone."""

from typing import TypeVar

from openai import AzureOpenAI
from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class AzureOpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment

    def complete(self, *, system: str, user: str, schema: type[T]) -> T:
        completion = self._client.chat.completions.parse(
            model=self._deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("model returned no structured output")
        return parsed
