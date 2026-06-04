import pytest
from backend.llm.client import LLMClient


def test_client_requires_api_key():
    with pytest.raises(ValueError, match="API key"):
        LLMClient(provider="openai", api_key=None)


def test_client_initialization():
    client = LLMClient(
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
        temperature=0.8,
        max_tokens=150,
    )
    assert client.provider == "openai"
    assert client.model == "gpt-4o-mini"


def test_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported provider"):
        LLMClient(
            provider="unknown",
            api_key="sk-test",
        )


@pytest.mark.asyncio
async def test_chat_openai():
    from unittest.mock import AsyncMock, patch

    mock_response = type("Response", (), {
        "choices": [
            type("Choice", (), {
                "message": type("Message", (), {"content": "Hello!"})()
            })()
        ]
    })()

    with patch("openai.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        client = LLMClient(provider="openai", api_key="sk-test")
        result = await client.chat(system="Be helpful", user="Hi")

        assert result == "Hello!"
        mock_client.chat.completions.create.assert_awaited_once()
