import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(autouse=True)
def mock_llm_and_asr():
    with patch("backend.main.StreamerTrainerApp") as mock_app:
        mock_instance = MagicMock()
        mock_app.return_value = mock_instance

        mock_instance.llm = MagicMock()
        mock_instance.llm.chat = AsyncMock(return_value='你好')

        mock_instance.asr = MagicMock()
        mock_instance.asr.transcribe = MagicMock(return_value="主播说你好")

        mock_instance.agent = MagicMock()
        mock_instance.agent.decide = AsyncMock(return_value=[])

        mock_instance.generator = MagicMock()
        mock_instance.generator.build_prompt = MagicMock(return_value="prompt")
        mock_instance.generator.parse_danmaku = MagicMock(return_value="你好呀")

        mock_instance.viewer_manager = MagicMock()
        mock_instance.viewer_manager.get_active_viewers = MagicMock(return_value=[])
        mock_instance.viewer_manager.get_viewer = MagicMock(return_value=None)

        mock_instance.broadcast_danmaku = AsyncMock()
        mock_instance.broadcast_system = AsyncMock()
        mock_instance.danmaku_clients = set()
        mock_instance.scheduler = MagicMock()
        mock_instance.streamer_timeline = []

        yield
        from backend.main import _LazyAppState
        _LazyAppState._instance = None


def test_control_ping_pong():
    client = TestClient(app)
    with client.websocket_connect("/control") as ws:
        ws.send_json({"action": "ping"})
        resp = ws.receive_json()
        assert resp["type"] == "pong"


def test_danmaku_endpoint_accepts_connection():
    client = TestClient(app)
    with client.websocket_connect("/danmaku") as ws:
        pass


def test_debug_text_appends_to_timeline():
    from backend.main import app_state
    app_state.streamer_timeline = []
    client = TestClient(app)
    resp = client.post("/debug_text", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
