import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(autouse=True)
def mock_app_dependencies():
    """Prevent real StreamerTrainerApp initialization."""
    from backend.main import _LazyAppState
    _LazyAppState._instance = MagicMock()
    _LazyAppState._instance.scheduler = MagicMock()
    _LazyAppState._instance.scheduler.start = AsyncMock()
    _LazyAppState._instance.scheduler.stop = MagicMock()
    yield
    _LazyAppState._instance = None


@pytest.fixture(autouse=True)
def mock_config_files(tmp_path):
    """Replace CONFIG_PATH and CONFIG_DEFAULT_PATH with tmp files."""
    import backend.main as main_module

    default_path = tmp_path / "config.default.yaml"
    with open(default_path, "w") as f:
        f.write("llm:\n  base_url: https://default.com/v1\n  api_key: sk-default-key-123\n")
        f.write("viewer:\n  min_active: 3\n  max_active: 8\n  churn_per_tick: 5\n")
        f.write("  tick_interval_sec: 15\n")

    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        f.write("llm:\n  base_url: https://api.moonshot.cn/v1\n  api_key: sk-mysupersecretkey\n")
        f.write("viewer:\n  min_active: 3\n  max_active: 8\n  churn_per_tick: 5\n")
        f.write("  tick_interval_sec: 15\n")

    with patch.object(main_module, "CONFIG_PATH", config_path), \
         patch.object(main_module, "CONFIG_DEFAULT_PATH", default_path):
        yield


def test_get_config_returns_masked_api_key():
    client = TestClient(app)
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm"]["base_url"] == "https://api.moonshot.cn/v1"
    assert data["llm"]["api_key"] == "sk-m****tkey"
    assert data["viewer"]["min_active"] == 3


def test_update_config_persists():
    client = TestClient(app)
    resp = client.post("/api/config", json={
        "llm": {"base_url": "https://new-url.com/v1", "api_key": "sk-newkey12345"},
        "viewer": {"min_active": 5, "max_active": 10},
    })
    assert resp.status_code == 200

    from backend.main import CONFIG_PATH, _read_config_yaml
    raw = _read_config_yaml()
    assert raw["llm"]["base_url"] == "https://new-url.com/v1"
    assert raw["llm"]["api_key"] == "sk-newkey12345"
    assert raw["viewer"]["min_active"] == 5
    assert raw["viewer"]["max_active"] == 10


def test_update_config_skips_masked_api_key():
    client = TestClient(app)
    resp = client.post("/api/config", json={
        "llm": {"api_key": "sk-m****key"},
    })
    assert resp.status_code == 200

    from backend.main import CONFIG_PATH, _read_config_yaml
    raw = _read_config_yaml()
    assert raw["llm"]["api_key"] == "sk-mysupersecretkey"


def test_reset_config_restores_defaults():
    client = TestClient(app)
    # First change something
    client.post("/api/config", json={"viewer": {"min_active": 99}})
    # Then reset
    resp = client.post("/api/config/reset")
    assert resp.status_code == 200

    from backend.main import CONFIG_PATH, _read_config_yaml
    raw = _read_config_yaml()
    assert raw["viewer"]["min_active"] == 3
    assert raw["llm"]["base_url"] == "https://default.com/v1"


def test_reset_config_missing_default_returns_error():
    import backend.main as main_module
    from pathlib import Path

    with patch.object(main_module, "CONFIG_DEFAULT_PATH", Path("/nonexistent/default.yaml")):
        client = TestClient(app)
        resp = client.post("/api/config/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
