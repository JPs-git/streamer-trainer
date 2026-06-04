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
        mock_instance.llm.chat = AsyncMock(return_value='[{"id": "xiaobing", "intent": "test"}]')

        mock_instance.asr = MagicMock()
        mock_instance.asr.transcribe = MagicMock(return_value="主播说你好")

        mock_instance.selector = MagicMock()
        mock_instance.selector.build_prompt = MagicMock(return_value="prompt")
        mock_instance.selector.parse_response = MagicMock(return_value=[{"id": "xiaobing", "intent": "test"}])

        mock_instance.generator = MagicMock()
        mock_instance.generator.build_prompt = MagicMock(return_value="prompt")
        mock_instance.generator.parse_danmaku = MagicMock(return_value="大家好呀")

        mock_instance.viewer_manager = MagicMock()
        mock_instance.viewer_manager.get_active_viewers = MagicMock(return_value=[])
        mock_instance.viewer_manager.get_viewer = MagicMock(return_value=None)

        mock_instance.broadcast_danmaku = AsyncMock()
        mock_instance.danmaku_clients = set()

        yield
        # Reset lazy singleton so next test gets a fresh instance
        from backend.main import _LazyAppState
        _LazyAppState._instance = None


def test_control_ping_pong():
    """测试 /control WS 的 ping/pong 响应"""
    client = TestClient(app)
    with client.websocket_connect("/control") as ws:
        ws.send_json({"action": "ping"})
        resp = ws.receive_json()
        assert resp["type"] == "pong"


def test_danmaku_endpoint_accepts_connection():
    """测试 /danmaku WS 能正常连接"""
    client = TestClient(app)
    with client.websocket_connect("/danmaku") as ws:
        pass
