"""Builds the configured LLMClient. Tests inject FakeLLM instead."""

from app.config import Settings, get_settings
from app.llm.azure import AzureOpenAIClient
from app.llm.client import LLMClient


class LLMNotConfigured(RuntimeError):
    pass


def is_configured(settings: Settings) -> bool:
    return bool(
        settings.azure_openai_endpoint
        and settings.azure_openai_api_key
        and settings.azure_openai_deployment
    )


def get_llm() -> LLMClient:
    settings = get_settings()
    if not is_configured(settings):
        raise LLMNotConfigured(
            "Azure OpenAI is not configured: set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT"
        )
    return AzureOpenAIClient(settings)
