import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.llm.agent import AgentClient


@pytest.fixture
def mock_openai():
    with patch("openai.AsyncOpenAI") as m:
        client = MagicMock()
        client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(tool_calls=None))]
            )
        )
        m.return_value = client
        yield client


@pytest.mark.asyncio
async def test_decide_uses_configured_temperature(mock_openai):
    agent = AgentClient(api_key="test-key", temperature=0.6)
    await agent.decide(
        viewer_states=[],
        timeline_text="",
        silence_sec=0.0,
        room_stats={"active_count": 0, "max_active": 10, "min_active": 2},
    )
    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0.6
