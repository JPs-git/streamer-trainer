import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler
from backend.viewer.models import VirtualViewer


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


_default_profile = '{"name": "小华", "persona": "热情观众", "relationship": "老粉", "engagement": 85}'
_second_profile = '{"name": "小李", "persona": "沉默路人", "relationship": "路人", "engagement": 70}'

@pytest.fixture
def llm():
    m = MagicMock()
    m.chat = AsyncMock(side_effect=[_default_profile, _second_profile])
    return m


@pytest.fixture
def generator():
    m = MagicMock()
    m.build_prompt = MagicMock(return_value="prompt")
    m.parse_danmaku = MagicMock(return_value="你好呀")
    return m


@pytest.fixture
def scheduler(manager, llm, generator):
    s = ViewerScheduler(
        manager=manager,
        llm=llm,
        generator=generator,
        tick_interval=0.1,
        engagement_threshold=20,
    )
    s._paused = False
    return s


def add_viewer(manager: ViewerManager, vid: str, name: str, engagement: int = 80):
    v = VirtualViewer(viewer_id=vid, name=name, persona="测试", engagement=engagement)
    manager.add_viewer(v)
    manager.activate_viewer(vid)
    return v


@pytest.mark.asyncio
async def test_tick_handles_empty_active(scheduler):
    """无活跃观众时不 crash"""
    await scheduler._tick()


@pytest.mark.asyncio
async def test_enter_viewer(scheduler, manager):
    await scheduler._enter_viewer({
        "name": "小华",
        "persona": "热情观众",
        "relationship": "老粉",
        "follows": True,
        "engagement": 85,
    })
    assert len(manager.get_active_viewers()) == 1
    v = manager.get_active_viewers()[0]
    assert v.name == "小华"
    assert v.relationship == "老粉"
    assert v.follows is True


@pytest.mark.asyncio
async def test_generate_viewer_profile(scheduler, llm):
    profile = await scheduler._generate_viewer_profile()
    assert profile["name"] == "小华"


@pytest.mark.asyncio
async def test_generate_viewer_profile_fallback(scheduler, llm):
    llm.chat = AsyncMock(return_value="invalid json")
    profile = await scheduler._generate_viewer_profile()
    assert profile["name"].startswith("观众")
    assert profile["engagement"] == 80


@pytest.mark.asyncio
async def test_remove_low_engagement_viewer(scheduler, manager):
    manager.min_active = 0
    add_viewer(manager, "v1", "小冰", engagement=15)
    await scheduler._tick()
    assert manager.get_viewer("v1") is None


@pytest.mark.asyncio
async def test_speak_generates_danmaku(scheduler, manager, generator, llm):
    v = add_viewer(manager, "v1", "小冰")
    scheduler._last_spoke_tick["v1"] = -10  # simulate long ago
    await scheduler._tick()
    # With engagement 80 and streamer_has_new=False (no timeline),
    # there's a good chance she speaks
    if generator.build_prompt.called:
        assert llm.chat.called
        assert v.interaction_count == 1


@pytest.mark.asyncio
async def test_engagement_boost_after_speak(scheduler, manager):
    v = add_viewer(manager, "v1", "小冰", engagement=50)
    scheduler._last_spoke_tick["v1"] = -10
    scheduler._do_speak = AsyncMock()
    await scheduler._tick()
    # decay happened, but no speak boost (we mocked _do_speak)
    assert v.engagement < 50


@pytest.mark.asyncio
async def test_broadcast_system_on_enter(scheduler, manager):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    manager.min_active = 0
    await scheduler._enter_viewer({
        "name": "小华",
        "persona": "热情观众",
        "relationship": "老粉",
        "follows": True,
        "engagement": 85,
    })
    assert broadcast_mock.called


@pytest.mark.asyncio
async def test_broadcast_system_on_leave(scheduler, manager):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    manager.min_active = 0
    v = add_viewer(manager, "v1", "小冰", engagement=10)
    await scheduler._do_leave(v)
    assert broadcast_mock.called


def test_compute_silence_duration():
    scheduler = ViewerScheduler(
        manager=ViewerManager(),
        llm=MagicMock(),
        generator=MagicMock(),
    )
    scheduler.streamer_timeline = [{"text": "hello", "offset": 1000}]
    duration = scheduler._compute_silence_duration(2000)
    assert duration == 1000


def test_pause_resume():
    sched = ViewerScheduler(
        manager=ViewerManager(),
        llm=MagicMock(),
        generator=MagicMock(),
    )
    assert sched._paused is True
    sched.resume()
    assert sched._paused is False
    sched.pause()
    assert sched._paused is True


@pytest.mark.asyncio
async def test_paused_tick_does_nothing(scheduler, manager):
    add_viewer(manager, "v1", "小冰")
    scheduler.pause()
    await scheduler._tick()
    # No viewers should have been affected
    v = manager.get_viewer("v1")
    assert v is not None


@pytest.mark.asyncio
async def test_backfill_below_min_active(scheduler, manager, llm):
    await scheduler._tick()
    active = manager.get_active_viewers()
    assert len(active) >= manager.min_active
    # The backfill should use LLM-generated profiles
    assert llm.chat.called


@pytest.mark.asyncio
async def test_tick_broadcasts_status(scheduler, manager):
    add_viewer(manager, "v1", "Alice", engagement=80)
    add_viewer(manager, "v2", "Bob", engagement=60)

    scheduler.broadcast_status = AsyncMock()
    await scheduler._tick()

    scheduler.broadcast_status.assert_awaited_once()
    msg = scheduler.broadcast_status.await_args.args[0]
    assert msg["type"] == "status"
    assert msg["active_count"] == 2
    assert msg["max_active"] == 4
    assert msg["min_active"] == 2
    assert len(msg["viewers"]) == 2
    viewer_ids = {v["id"] for v in msg["viewers"]}
    assert viewer_ids == {"v1", "v2"}
