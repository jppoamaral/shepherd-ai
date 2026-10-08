import pytest

from app.llm.azure import resource_endpoint


@pytest.mark.parametrize(
    "given",
    [
        "https://church-ai.openai.azure.com",
        "https://church-ai.openai.azure.com/",
        "https://church-ai.openai.azure.com/openai/v1/responses",
        "  https://church-ai.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=x ",
    ],
)
def test_endpoint_is_reduced_to_the_resource_base(given: str) -> None:
    assert resource_endpoint(given) == "https://church-ai.openai.azure.com"


def test_endpoint_must_be_a_url() -> None:
    with pytest.raises(ValueError):
        resource_endpoint("church-ai")
