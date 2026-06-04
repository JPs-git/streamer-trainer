import pytest
from backend.viewer.models import VirtualViewer
from backend.viewer.manager import ViewerManager


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


def test_initial_active_count(manager):
    """初始时应该有 min_active 个活跃观众"""
    assert len(manager.get_active_viewers()) >= 2


def test_get_viewer_by_id(manager):
    v = manager.get_viewer("xiaobing")
    assert v is not None
    assert v.viewer_id == "xiaobing"


def test_get_nonexistent_viewer(manager):
    assert manager.get_viewer("nonexistent") is None


def test_viewer_state_transitions(manager):
    """验证状态机流转: inactive → active → cooldown → inactive"""
    manager.activate_viewer("xiaobing")
    v = manager.get_viewer("xiaobing")
    assert v.state == "active"

    manager.deactivate_viewer("xiaobing")
    assert v.state == "cooldown"

    manager.cooldown_sec = -1
    manager.tick()
    assert v.state == "inactive"

    manager.activate_viewer("xiaobing")
    assert v.state == "active"


def test_active_viewers_respects_max(manager):
    """活跃人数不应超过 max_active"""
    for vid in ["xiaobing", "xiaoxin", "mengmeng", "aqiang", "xiaohong",
                 "tuzi", "laowang", "jingjing", "xiaohei", "dage"]:
        manager.activate_viewer(vid)
    assert len(manager.get_active_viewers()) <= manager.max_active


def test_tick_fills_to_min(manager):
    """tick 应保持活跃人数不低于 min_active"""
    # 全部停用
    for v in list(manager._active_ids):
        manager.deactivate_viewer(v)
    assert len(manager.get_active_viewers()) == 0

    manager.tick()
    assert len(manager.get_active_viewers()) >= manager.min_active


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
    manager.tick()
    assert v.state == "inactive"
