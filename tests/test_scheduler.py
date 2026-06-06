import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler
from backend.viewer.models import VirtualViewer


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


@pytest.fixture
def agent():
    m = MagicMock()
    m.decide = AsyncMock(return_value=[])
    return m


@pytest.fixture
def llm():
    m = MagicMock()
    m.chat = AsyncMock(return_value="你好呀")
    return m


@pytest.fixture
def generator():
    m = MagicMock()
    m.build_prompt = MagicMock(return_value="prompt")
    m.parse_danmaku = MagicMock(return_value="你好呀")
    return m


@pytest.fixture
def scheduler(manager, agent, llm, generator):
    s = ViewerScheduler(
        manager=manager,
        agent=agent,
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
async def test_tick_calls_agent(scheduler, manager, agent):
    add_viewer(manager, "v1", "小冰")
    await scheduler._tick()
    assert agent.decide.called


@pytest.mark.asyncio
async def test_tick_handles_empty_active(scheduler, agent):
    """无活跃观众时不 crash"""
    await scheduler._tick()


@pytest.mark.asyncio
async def test_agent_spawn_viewer(scheduler, manager, agent):
    manager.min_active = 0  # prevent backfill
    agent.decide.return_value = [{
        "type": "spawn_viewer",
        "name": "小华",
        "persona": "热情观众",
        "follows": True,
        "relationship": "老粉",
        "engagement": 85,
    }]
    await scheduler._tick()
    assert len(manager.get_active_viewers()) == 1
    v = manager.get_active_viewers()[0]
    assert v.name == "小华"
    assert v.relationship == "老粉"
    assert v.follows is True


@pytest.mark.asyncio
async def test_agent_adjust_engagement(scheduler, manager, agent):
    v = add_viewer(manager, "v1", "小冰", engagement=50)
    agent.decide.return_value = [{
        "type": "adjust_engagement",
        "viewer_id": "v1",
        "delta": 10,
    }]
    await scheduler._tick()
    # decay (-5~-1) + delta +10, should be higher than before
    assert v.engagement > 50 or v.engagement == 50


@pytest.mark.asyncio
async def test_agent_remove_viewer(scheduler, manager, agent):
    manager.min_active = 0  # prevent backfill
    add_viewer(manager, "v1", "小冰")
    agent.decide.return_value = [{
        "type": "remove_viewer",
        "viewer_id": "v1",
    }]
    await scheduler._tick()
    assert manager.get_viewer("v1") is None
    assert len(manager.get_active_viewers()) == 0


@pytest.mark.asyncio
async def test_agent_speak_generates_danmaku(scheduler, manager, agent, generator, llm):
    v = add_viewer(manager, "v1", "小冰")
    agent.decide.return_value = [{
        "type": "schedule_speak",
        "viewer_id": "v1",
        "intent": "夸主播操作",
    }]
    await scheduler._tick()
    assert generator.build_prompt.called
    assert llm.chat.called
    assert v.interaction_count == 1


@pytest.mark.asyncio
async def test_broadcast_system_on_enter(scheduler, manager, agent):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    manager.min_active = 0  # prevent backfill
    agent.decide.return_value = [{
        "type": "spawn_viewer",
        "name": "小华",
        "persona": "热情观众",
        "follows": True,
        "relationship": "老粉",
        "engagement": 85,
    }]
    await scheduler._tick()
    assert broadcast_mock.called


@pytest.mark.asyncio
async def test_broadcast_system_on_leave(scheduler, manager, agent):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    manager.min_active = 0  # prevent backfill
    add_viewer(manager, "v1", "小冰")
    agent.decide.return_value = [{
        "type": "remove_viewer",
        "viewer_id": "v1",
    }]
    await scheduler._tick()
    assert broadcast_mock.called


def test_compute_silence_duration():
    scheduler = ViewerScheduler(
        manager=ViewerManager(),
        agent=MagicMock(),
        llm=MagicMock(),
        generator=MagicMock(),
    )
    scheduler.streamer_timeline = [{"text": "hello", "offset": 1000}]
    duration = scheduler._compute_silence_duration(2000)
    assert duration == 1000


def test_pause_resume():
    sched = ViewerScheduler(
        manager=ViewerManager(),
        agent=MagicMock(),
        llm=MagicMock(),
        generator=MagicMock(),
    )
    assert sched._paused is True
    sched.resume()
    assert sched._paused is False
    sched.pause()
    assert sched._paused is True


@pytest.mark.asyncio
async def test_paused_tick_does_nothing(scheduler, manager, agent):
    add_viewer(manager, "v1", "小冰")
    scheduler.pause()
    await scheduler._tick()
    assert not agent.decide.called


@pytest.mark.asyncio
async def test_backfill_below_min_active(scheduler, manager, agent):
    agent.decide.return_value = []
    await scheduler._tick()
    assert len(manager.get_active_viewers()) >= manager.min_active
