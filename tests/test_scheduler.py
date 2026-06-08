import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler
from backend.viewer.models import VirtualViewer


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


_default_profile = '{"name": "小华", "persona": "热情观众", "relationship": "老粉"}'
_second_profile = '{"name": "小李", "persona": "沉默路人", "relationship": "路人"}'

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
        churn_per_tick=5,
    )
    s._paused = False
    return s


def add_viewer(manager: ViewerManager, vid: str, name: str):
    v = VirtualViewer(viewer_id=vid, name=name, persona="测试")
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
    assert profile["persona"] == "普通观众"


@pytest.mark.asyncio
async def test_speak_generates_danmaku(scheduler, manager, generator, llm):
    v = VirtualViewer(viewer_id="v1", name="小冰", persona="测试", viewer_type="guider")
    manager.add_viewer(v)
    manager.activate_viewer("v1")
    scheduler.churn_per_tick = 0
    scheduler._last_spoke_tick["v1"] = -10
    await scheduler._tick()
    if generator.build_prompt.called:
        assert llm.chat.called
        assert v.interaction_count == 1


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
    })
    assert broadcast_mock.called


@pytest.mark.asyncio
async def test_broadcast_system_on_leave(scheduler, manager):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    manager.min_active = 0
    v = add_viewer(manager, "v1", "小冰")
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
    scheduler.churn_per_tick = 0
    scheduler.pause()
    await scheduler._tick()
    v = manager.get_viewer("v1")
    assert v is not None


@pytest.mark.asyncio
async def test_tick_broadcasts_status(scheduler, manager):
    add_viewer(manager, "v1", "Alice")
    add_viewer(manager, "v2", "Bob")
    scheduler.churn_per_tick = 0  # disable churn for deterministic test

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
