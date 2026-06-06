import pytest
from backend.viewer.models import VirtualViewer
from backend.viewer.manager import ViewerManager


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


@pytest.fixture
def viewer():
    return VirtualViewer(viewer_id="test_01", name="测试", persona="测试")


def test_add_and_remove(manager, viewer):
    manager.add_viewer(viewer)
    assert manager.get_viewer("test_01") is viewer
    manager.remove_viewer("test_01")
    assert manager.get_viewer("test_01") is None


def test_get_nonexistent_viewer(manager):
    assert manager.get_viewer("nonexistent") is None


def test_viewer_state_transitions(manager, viewer):
    manager.add_viewer(viewer)
    assert viewer.state == "inactive"
    manager.activate_viewer(viewer.viewer_id)
    assert viewer.state == "active"
    manager.deactivate_viewer(viewer.viewer_id)
    assert viewer.state == "cooldown"


def test_activate_viewer_requires_add(manager):
    assert manager.activate_viewer("nonexistent") is False


def test_active_viewers_respects_max(manager):
    for i in range(10):
        v = VirtualViewer(viewer_id=f"v_{i}", name=f"观众{i}", persona="普通")
        manager.add_viewer(v)
        manager.activate_viewer(v.viewer_id)
    assert len(manager.get_active_viewers()) <= manager.max_active


def test_activate_returns_bool(manager):
    v = VirtualViewer(viewer_id="t1", name="t1", persona="t")
    manager.add_viewer(v)
    assert manager.activate_viewer("t1") is True
    assert manager.activate_viewer("nonexistent") is False


def test_get_inactive_viewers(manager):
    v = VirtualViewer(viewer_id="t1", name="t1", persona="t")
    manager.add_viewer(v)
    inactives = manager.get_inactive_viewers()
    assert v in inactives


def test_remove_also_from_active(manager, viewer):
    manager.add_viewer(viewer)
    manager.activate_viewer(viewer.viewer_id)
    assert len(manager.get_active_viewers()) == 1
    manager.remove_viewer(viewer.viewer_id)
    assert len(manager.get_active_viewers()) == 0
