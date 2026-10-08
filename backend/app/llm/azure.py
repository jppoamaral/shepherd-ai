"""Azure OpenAI implementation of LLMClient. Wired up in a later milestone."""

from typing import TypeVar
from urllib.parse import urlparse

from openai import AzureOpenAI
from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


def resource_endpoint(url: str) -> str:
    """The resource base URL the SDK expects (scheme + host).

    Portals often hand out a full request URL such as
    `https://<res>.services.ai.azure.com/openai/v1/responses`; the SDK appends
    its own `/openai/deployments/...` path, so anything after the host breaks it.
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT must be a URL like https://<resource>.openai.azure.com"
        )
    return f"{parsed.scheme}://{parsed.netloc}"


class AzureOpenAIClient:
    def __init__(self, settings: Settings) -> None:
        self._client = AzureOpenAI(
            azure_endpoint=resource_endpoint(settings.azure_openai_endpoint),
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
