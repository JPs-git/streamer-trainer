import pytest
from backend.viewer.models import VirtualViewer
from backend.viewer.manager import ViewerManager


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


def test_get_viewer_by_id(manager):
    v = manager.get_viewer("xiaobing")
    assert v is not None
    assert v.viewer_id == "xiaobing"


def test_get_nonexistent_viewer(manager):
    assert manager.get_viewer("nonexistent") is None


def test_viewer_state_transitions(manager):
    manager.activate_viewer("xiaobing")
    v = manager.get_viewer("xiaobing")
    assert v.state == "active"

    manager.deactivate_viewer("xiaobing")
    assert v.state == "cooldown"

    manager.cooldown_sec = -1
    manager.reset_cooldown_viewers()
    assert v.state == "inactive"

    manager.activate_viewer("xiaobing")
    assert v.state == "active"


def test_active_viewers_respects_max(manager):
    for vid in ["xiaobing", "xiaoxin", "mengmeng", "aqiang", "xiaohong",
                 "tuzi", "laowang", "jingjing", "xiaohei", "dage"]:
        manager.activate_viewer(vid)
    assert len(manager.get_active_viewers()) <= manager.max_active


def test_cannot_reactivate_during_cooldown(manager):
    manager.activate_viewer("xiaobing")
    manager.deactivate_viewer("xiaobing")
    v = manager.get_viewer("xiaobing")
    assert v.state == "cooldown"
    manager.activate_viewer("xiaobing")
    assert v.state == "cooldown"


def test_cooldown_expires_after_time(manager):
    manager.cooldown_sec = -1
    manager.activate_viewer("xiaobing")
    manager.deactivate_viewer("xiaobing")
    v = manager.get_viewer("xiaobing")
    assert v.state == "cooldown"
    manager.reset_cooldown_viewers()
    assert v.state == "inactive"


def test_activate_returns_bool(manager):
    assert manager.activate_viewer("xiaobing") is True
    assert manager.activate_viewer("nonexistent") is False


def test_get_inactive_viewers(manager):
    inactives = manager.get_inactive_viewers()
    assert all(v.state == "inactive" for v in inactives)
