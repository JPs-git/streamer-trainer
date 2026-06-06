import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler, PERSONALITY_DECAY_BASE, ENGAGEMENT_MIN, ENGAGEMENT_MAX


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


@pytest.fixture
def llm():
    m = MagicMock()
    m.chat = AsyncMock(return_value='[{"id": "xiaobing", "engagement_delta": 5, "speak": "ask_question", "leave": false}]')
    m.selector_model = "test-model"
    return m


@pytest.fixture
def selector():
    m = MagicMock()
    m.build_pulse_prompt = MagicMock(return_value="prompt")
    m.parse_pulse_response = MagicMock(return_value=[
        {"id": "xiaobing", "engagement_delta": 5, "speak": "ask_question", "leave": False},
    ])
    return m


@pytest.fixture
def generator():
    m = MagicMock()
    m.build_prompt = MagicMock(return_value="prompt")
    m.parse_danmaku = MagicMock(return_value="你好呀")
    return m


@pytest.fixture
def scheduler(manager, llm, selector, generator):
    return ViewerScheduler(
        manager=manager,
        llm=llm,
        selector=selector,
        generator=generator,
        tick_interval=0.1,
        entry_interval=0.1,
        engagement_threshold=20,
    )


@pytest.mark.asyncio
async def test_scheduler_tick_calls_selector(scheduler, manager, selector):
    manager.activate_viewer("xiaobing")
    await scheduler._tick()
    assert selector.build_pulse_prompt.called


@pytest.mark.asyncio
async def test_scheduler_engagement_decay(scheduler, manager):
    manager.activate_viewer("xiaobing")
    v = manager.get_viewer("xiaobing")
    v.engagement = 80
    await scheduler._tick()
    assert v.engagement <= 80


@pytest.mark.asyncio
async def test_scheduler_delta_applied(scheduler, manager):
    manager.activate_viewer("xiaobing")
    v = manager.get_viewer("xiaobing")
    v.engagement = 50
    await scheduler._tick()
    # decay + delta 5
    assert v.engagement < 55


@pytest.mark.asyncio
async def test_scheduler_leave_respects_min_active(scheduler, manager, selector):
    manager.activate_viewer("xiaobing")
    manager.activate_viewer("xiaoxin")
    selector.parse_pulse_response.return_value = [
        {"id": "xiaobing", "engagement_delta": 0, "speak": None, "leave": True},
        {"id": "xiaoxin", "engagement_delta": 0, "speak": None, "leave": False},
    ]
    await scheduler._tick()
    # min_active=2 so xiaobing should NOT leave
    assert manager.get_viewer("xiaobing").state == "active"


@pytest.mark.asyncio
async def test_scheduler_entry_timing(scheduler, manager):
    """新观众应在 entry_interval 后进场"""
    assert len(manager.get_active_viewers()) == 0
    await scheduler._tick()
    assert len(manager.get_active_viewers()) >= 1


@pytest.mark.asyncio
async def test_scheduler_handles_empty_active(scheduler, manager):
    """无活跃观众时不 crash"""
    await scheduler._tick()


@pytest.mark.asyncio
async def test_scheduler_broadcast_system_on_leave(scheduler, manager, selector):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    manager.min_active = 1
    manager.activate_viewer("xiaobing")
    manager.activate_viewer("xiaoxin")
    manager.activate_viewer("mengmeng")
    selector.parse_pulse_response.return_value = [
        {"id": "xiaobing", "engagement_delta": 0, "speak": None, "leave": True},
        {"id": "xiaoxin", "engagement_delta": 0, "speak": None, "leave": False},
    ]
    await scheduler._tick()
    assert broadcast_mock.called


@pytest.mark.asyncio
async def test_scheduler_broadcast_system_on_entry(scheduler, manager):
    broadcast_mock = AsyncMock()
    scheduler.broadcast_system = broadcast_mock
    scheduler._last_entry_time = -9999
    await scheduler._tick()
    assert broadcast_mock.called


@pytest.mark.asyncio
async def test_scheduler_speak_with_random_delay(scheduler, manager, generator):
    manager.activate_viewer("xiaobing")
    await scheduler._tick()
    assert generator.build_prompt.called


@pytest.mark.asyncio
async def test_decay_by_personality():
    from backend.viewer.models import VirtualViewer
    curious = VirtualViewer(viewer_id="a", name="a", persona="a", personality_type="curious", engagement=100)
    bystander = VirtualViewer(viewer_id="b", name="b", persona="b", personality_type="bystander", engagement=100)
    mgr = ViewerManager()
    sched = ViewerScheduler(manager=mgr, llm=MagicMock(), selector=MagicMock(), generator=MagicMock())
    for _ in range(20):
        d1 = sched._compute_decay(curious)
        d2 = sched._compute_decay(bystander)
        assert d1 >= 0
        assert d2 >= 0


def test_compute_silence_duration():
    manager = ViewerManager()
    scheduler = ViewerScheduler(manager=manager, llm=MagicMock(), selector=MagicMock(), generator=MagicMock())
    scheduler.streamer_timeline = [{"text": "hello", "offset": 1000}]
    duration = scheduler._compute_silence_duration(2000)
    assert duration == 1000
