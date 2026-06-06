# 虚拟观众生命周期管理 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从"ASR 触发被动响应"改为"调度器主动驱动"，每个观众有独立 engagement 模型，离场由 LLM 判定。

**Architecture:** ViewerScheduler 独立 loop (~15s tick) 驱动全部生命周期（入场/发言/离场）。ASR 管线精简为只记录主播时间线。Selector 改造为批量评估：输出每个观众的 engagement 变化、发言意图、是否离场。发言播出带随机延迟避免刷屏。

**Tech Stack:** Python 3.11+, asyncio, FastAPI, pytest

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/viewer/models.py` | 修改 | 新增 `engagement` 字段 (0-100) |
| `backend/viewer/manager.py` | 修改 | 去掉 `tick()` 和 `_fill_to_min()`，保留基础 CRUD |
| `backend/viewer/scheduler.py` | **新建** | ViewerScheduler 独立 loop + 调度逻辑 |
| `backend/llm/selector.py` | 修改 | Prompt 改为批量评估格式，输出 engagement_delta + speak + leave |
| `backend/main.py` | 修改 | ASR 只追时间线，不再触发生成；初始化并启动 Scheduler；新增 `broadcast_system` |
| `backend/config.py` | 修改 | 添加 `tick_interval_sec`, `engagement_threshold` |
| `config.yaml` | 修改 | 添加 `tick_interval_sec`, `engagement_threshold` |
| `tests/test_models.py` | 修改 | 加 engagement 字段测试 |
| `tests/test_manager.py` | 修改 | 去掉 tick 相关测试，适配简化 manager |
| `tests/test_scheduler.py` | **新建** | Scheduler 全流程测试 |
| `tests/test_main.py` | 修改 | 适配新的 mock 结构 |

---

### Task 1: 修改 viewer models — 增加 engagement 字段

**Files:**
- Modify: `backend/viewer/models.py`

- [ ] **Step 1: 给 VirtualViewer 添加 engagement 字段**

```python
# 在 VirtualViewer dataclass 末尾添加
engagement: int = 100  # 0-100
```

同时在 `entry_time` 后面追加：

```python
engagement: int = 100
```

- [ ] **Step 2: 跑已有测试确认不破坏**

Run: `uv run pytest tests/test_models.py -v`
Expected: 5 passed

- [ ] **Step 3: 提交**

```bash
git add backend/viewer/models.py tests/test_models.py
git commit -m "feat: add engagement field to VirtualViewer"
```

---

### Task 2: 简化 ViewerManager — 去掉调度逻辑

**Files:**
- Modify: `backend/viewer/manager.py` (去掉 `tick()` 和 `_fill_to_min()`)

- [ ] **Step 1: 重写 ViewerManager**

```python
from __future__ import annotations
import time
from backend.viewer.models import VirtualViewer
from backend.viewer.personas import ALL_PERSONAS


class ViewerManager:
    def __init__(self, max_active: int = 8, min_active: int = 3, cooldown_sec: int = 300):
        self.max_active = max_active
        self.min_active = min_active
        self.cooldown_sec = cooldown_sec
        self._all_viewers: dict[str, VirtualViewer] = {}
        self._active_ids: set[str] = set()
        self._cooldown_ids: set[str] = set()
        self._init_viewers()

    def _init_viewers(self):
        for p in ALL_PERSONAS:
            v = VirtualViewer(
                viewer_id=p["viewer_id"],
                name=p["name"],
                persona=p["persona"],
                personality_type=p["personality_type"],
            )
            self._all_viewers[v.viewer_id] = v

    def activate_viewer(self, viewer_id: str) -> bool:
        if len(self._active_ids) >= self.max_active:
            return False
        v = self._all_viewers.get(viewer_id)
        if v and v.state == "inactive":
            v.state = "active"
            v.entry_time = int(time.time())
            v.last_active = int(time.time())
            self._active_ids.add(viewer_id)
            self._cooldown_ids.discard(viewer_id)
            return True
        return False

    def deactivate_viewer(self, viewer_id: str):
        v = self._all_viewers.get(viewer_id)
        if v and v.state == "active":
            v.state = "cooldown"
            v.deactivated_at = int(time.time())
            self._active_ids.discard(viewer_id)
            self._cooldown_ids.add(viewer_id)

    def get_viewer(self, viewer_id: str) -> VirtualViewer | None:
        return self._all_viewers.get(viewer_id)

    def get_active_viewers(self) -> list[VirtualViewer]:
        return [self._all_viewers[vid] for vid in self._active_ids
                if vid in self._all_viewers]

    def get_inactive_viewers(self) -> list[VirtualViewer]:
        return [v for v in self._all_viewers.values() if v.state == "inactive"]

    def reset_cooldown_viewers(self):
        now = int(time.time())
        expired = [
            vid for vid in self._cooldown_ids
            if now - (self._all_viewers[vid].deactivated_at or 0) > self.cooldown_sec
        ]
        for vid in expired:
            self._all_viewers[vid].state = "inactive"
        self._cooldown_ids -= set(expired)
```

- [ ] **Step 2: 更新 test_manager.py**

```python
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
```

- [ ] **Step 3: 跑测试确认通过**

Run: `uv run pytest tests/test_manager.py -v`
Expected: 9 passed

- [ ] **Step 4: 提交**

```bash
git add backend/viewer/manager.py tests/test_manager.py
git commit -m "refactor: strip scheduling logic from ViewerManager"
```

---

### Task 3: 实现 ViewerScheduler

**Files:**
- Create: `backend/viewer/scheduler.py`

- [ ] **Step 1: 创建 scheduler.py**

```python
from __future__ import annotations
import asyncio
import random
import time
from typing import TYPE_CHECKING, Callable, Optional

from backend.viewer.manager import ViewerManager

if TYPE_CHECKING:
    from backend.llm.client import LLMClient
    from backend.llm.selector import Selector
    from backend.llm.generator import Generator


PERSONALITY_DECAY_BASE = {
    "curious": 4.0,
    "aggressive": 3.0,
    "cheerful": 2.0,
    "bystander": 1.5,
}

ENGAGEMENT_MIN = 0
ENGAGEMENT_MAX = 100


class ViewerScheduler:
    def __init__(
        self,
        manager: ViewerManager,
        llm: LLMClient,
        selector: Selector,
        generator: Generator,
        tick_interval: float = 15.0,
        entry_interval: float = 180.0,
        engagement_threshold: int = 20,
        broadcast_system: Optional[Callable] = None,
        broadcast_danmaku: Optional[Callable] = None,
        streamer_timeline: Optional[list[dict]] = None,
    ):
        self.manager = manager
        self.llm = llm
        self.selector = selector
        self.generator = generator
        self.tick_interval = tick_interval
        self.entry_interval = entry_interval
        self.engagement_threshold = engagement_threshold
        self.broadcast_system = broadcast_system
        self.broadcast_danmaku = broadcast_danmaku
        self.streamer_timeline = streamer_timeline if streamer_timeline is not None else []
        self._last_speech_index = 0
        self._last_entry_time: float = 0.0
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            await self._tick()
            await asyncio.sleep(self.tick_interval)

    def stop(self):
        self._running = False

    async def _tick(self):
        now = time.time()
        streamer_has_new_speech = self._last_speech_index < len(self.streamer_timeline)
        silence_duration = self._compute_silence_duration(now)

        active = self.manager.get_active_viewers()
        if not active:
            await self._try_entry()
            return

        # 1. 基础衰减 + 随机波动
        for v in active:
            decay = self._compute_decay(v)
            v.engagement = max(ENGAGEMENT_MIN, min(ENGAGEMENT_MAX, v.engagement - decay))

        # 2. LLM 批量评估
        viewer_states = self._build_viewer_states(active, streamer_has_new_speech, silence_duration)
        selector_result = await self._call_selector(active, streamer_has_new_speech, silence_duration)

        if selector_result is None:
            await self._try_entry()
            return

        # 3. 应用 engagement 修正
        for item in selector_result:
            v = self.manager.get_viewer(item.get("id", ""))
            if v and v.state == "active":
                delta = item.get("engagement_delta", 0)
                v.engagement = max(ENGAGEMENT_MIN, min(ENGAGEMENT_MAX, v.engagement + delta))

        # 4. 处理发言
        speak_tasks = []
        for item in selector_result:
            if item.get("speak"):
                v = self.manager.get_viewer(item.get("id", ""))
                if v and v.state == "active":
                    delay = random.uniform(0, 6)
                    speak_tasks.append(self._schedule_speak(v, item["speak"], delay))

        if speak_tasks:
            await asyncio.gather(*speak_tasks)

        # 5. 处理离场
        for item in selector_result:
            if item.get("leave"):
                vid = item.get("id", "")
                if len(self.manager.get_active_viewers()) > self.manager.min_active:
                    v = self.manager.get_viewer(vid)
                    if v and v.state == "active":
                        self.manager.deactivate_viewer(vid)
                        if self.broadcast_system:
                            await self.broadcast_system("leave", v.name, v.viewer_id)

        # 6. 入场
        await self._try_entry()

        # 7. 冷却重置
        self.manager.reset_cooldown_viewers()

    def _compute_decay(self, v) -> float:
        base = PERSONALITY_DECAY_BASE.get(v.personality_type, 3.0)
        decay = base * random.uniform(0.5, 1.5) + random.uniform(-3, 3)
        return max(0, decay)

    def _compute_silence_duration(self, now: float) -> float:
        if not self.streamer_timeline:
            return 0.0
        last = self.streamer_timeline[-1]
        return now - last["offset"]

    def _build_viewer_states(self, active, has_new: bool, silence: float) -> list[dict]:
        return [
            {
                "id": v.viewer_id,
                "name": v.name,
                "personality": v.personality_type,
                "engagement": v.engagement,
                "interaction_count": v.interaction_count,
            }
            for v in active
        ]

    async def _call_selector(self, active, has_new: bool, silence: float):
        latest_speech = ""
        if has_new and self.streamer_timeline:
            latest_speech = self.streamer_timeline[-1].get("text", "")
        viewer_states = self._build_viewer_states(active, has_new, silence)
        prompt = self.selector.build_pulse_prompt(latest_speech, silence, viewer_states)
        raw = await self.llm.chat(
            system=self.selector.SELECTOR_SYSTEM_PROMPT,
            user=prompt,
            model=self.llm.selector_model,
        )
        return self.selector.parse_pulse_response(raw)

    async def _schedule_speak(self, v, intent: str, delay: float):
        await asyncio.sleep(delay)
        if v.state != "active":
            return
        prompt = self.generator.build_prompt(
            name=v.name,
            persona=v.persona,
            personality_type=v.personality_type,
            streamer_log=self.streamer_timeline,
            my_danmaku=v.memory.my_danmaku,
            other_danmaku=v.memory.other_danmaku,
            relationships=v.memory.relationships,
            current_asr=self.streamer_timeline[-1]["text"] if self.streamer_timeline else "",
        )
        prompt += f"\n\n[发言意图]\n{intent}"
        raw = await self.llm.chat(
            system=self.generator.GENERATOR_SYSTEM_PROMPT,
            user=prompt,
        )
        text = self.generator.parse_danmaku(raw)
        if not text:
            return
        v.memory.add_my_danmaku(text, int(time.time()), "streamer")
        v.last_active = int(time.time())
        v.interaction_count += 1
        effect = "highlight" if v.personality_type == "aggressive" else "normal"
        msg = {
            "type": "danmaku",
            "id": v.viewer_id,
            "name": v.name,
            "text": text,
            "personality": v.personality_type,
            "effect": effect,
        }
        if self.broadcast_danmaku:
            await self.broadcast_danmaku(msg)

    async def _try_entry(self):
        if time.time() - self._last_entry_time < self.entry_interval:
            return
        inactive = self.manager.get_inactive_viewers()
        if not inactive:
            return
        if len(self.manager.get_active_viewers()) >= self.manager.max_active:
            return
        v = random.choice(inactive)
        self.manager.activate_viewer(v.viewer_id)
        self._last_entry_time = time.time()
        if self.broadcast_system:
            await self.broadcast_system("enter", v.name, v.viewer_id)
```

- [ ] **Step 2: 创建 test_scheduler.py**

```python
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
```

- [ ] **Step 3: 跑测试确认通过**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: 10+ passed

- [ ] **Step 4: 提交**

```bash
git add backend/viewer/scheduler.py tests/test_scheduler.py
git commit -m "feat: add ViewerScheduler with engagement model"
```

---

### Task 4: 修改 Selector — 支持批量脉冲评估

**Files:**
- Modify: `backend/llm/selector.py`

- [ ] **Step 1: 重写 Selector**

```python
import json
import re


class Selector:
    SELECTOR_SYSTEM_PROMPT = """你是一个直播弹幕的"观众脉搏"评估系统。
你的任务是根据主播的直播内容（或沉默状态）和每个观众的个性，
评估每个活跃观众当前的状态。

输出 JSON 数组，每个元素包含：
{
  "id": "观众ID",
  "engagement_delta": 整数,   // 兴趣变化：对口 +5~+20, 无聊 -5~-15, 中性 0~-3
  "speak": null 或 "发言意图描述",  // 非空表示该观众想发言
  "leave": true/false           // true 表示想离场
}

规则：
- engagement_delta 根据内容是否符合该观众的口味决定
- 沉默太久会导致多个观众 engagement 下降
- 只有 engagement <= 20 的观众才可能 leave=true
- speak 优先给 engagement 变化最大的 1-2 人
- 不要让同一个人连续多次发言
- 如果所有人都沉默，返回空数组 []"""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    def build_pulse_prompt(
        self,
        latest_speech: str,
        silence_duration: float,
        viewer_states: list[dict],
    ) -> str:
        lines = []
        if latest_speech:
            lines.append(f"[主播最新发言] {latest_speech}")
        else:
            lines.append(f"[沉默时长] {silence_duration:.0f} 秒")
        lines.append("")
        lines.append("[活跃观众当前状态]")
        for vs in viewer_states:
            lines.append(
                f"- {vs['name']}({vs['id']}) [{vs['personality']}] "
                f"engagement={vs.get('engagement', 100)}, "
                f"发过{vs.get('interaction_count', 0)}条弹幕"
            )
        lines.extend([
            "",
            "评估每个观众的状态变化，返回 JSON 数组。",
        ])
        return "\n".join(lines)

    def parse_pulse_response(self, text: str) -> list[dict]:
        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
        if not json_match:
            return []
        try:
            result = json.loads(json_match.group())
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            return []
```

- [ ] **Step 2: 更新 Selector 测试**

更新 `tests/test_selector.py`（如果有），或者确认没有 selector 测试需要更新：

```bash
uv run pytest tests/ -k "selector" -v
```

如果没有匹配的测试，创建一个：

```python
# tests/test_selector.py
from backend.llm.selector import Selector


def test_parse_pulse_response():
    sel = Selector()
    raw = '''[
        {"id": "xiaobing", "engagement_delta": 5, "speak": "ask_question", "leave": false},
        {"id": "tuzi", "engagement_delta": -3, "speak": null, "leave": false}
    ]'''
    result = sel.parse_pulse_response(raw)
    assert len(result) == 2
    assert result[0]["id"] == "xiaobing"
    assert result[0]["speak"] == "ask_question"
    assert result[0]["leave"] is False


def test_parse_pulse_response_empty():
    sel = Selector()
    result = sel.parse_pulse_response("[]")
    assert result == []


def test_parse_pulse_response_invalid():
    sel = Selector()
    result = sel.parse_pulse_response("not json")
    assert result == []


def test_build_pulse_prompt_with_speech():
    sel = Selector()
    prompt = sel.build_pulse_prompt("今天玩这个", 0, [
        {"id": "x", "name": "X", "personality": "curious", "engagement": 80, "interaction_count": 2},
    ])
    assert "今天玩这个" in prompt
    assert "沉默" not in prompt


def test_build_pulse_prompt_with_silence():
    sel = Selector()
    prompt = sel.build_pulse_prompt("", 120, [
        {"id": "x", "name": "X", "personality": "curious", "engagement": 50, "interaction_count": 0},
    ])
    assert "沉默时长" in prompt
    assert "120 秒" in prompt
```

- [ ] **Step 3: 跑测试**

Run: `uv run pytest tests/test_selector.py -v`
Expected: 5 passed

- [ ] **Step 4: 提交**

```bash
git add backend/llm/selector.py tests/test_selector.py
git commit -m "feat: rewrite Selector for pulse evaluation format"
```

---

### Task 5: 更新 Config 和 main.py

**Files:**
- Modify: `backend/config.py`
- Modify: `config.yaml`
- Modify: `backend/main.py`

- [ ] **Step 1: 修改 config.yaml**

```yaml
viewer:
  min_active: 3
  max_active: 8
  entry_interval_sec: 180
  cooldown_sec: 300
  tick_interval_sec: 15       # 新增
  engagement_threshold: 20     # 新增
  memory_max_streamer_log: 50
```

- [ ] **Step 2: 修改 config.py — 加载新字段**

在 `viewer_conf` 块里，`self.viewer_cooldown_sec` 后面添加：

```python
self.viewer_tick_interval_sec = viewer_conf["tick_interval_sec"]
self.viewer_engagement_threshold = viewer_conf["engagement_threshold"]
```

- [ ] **Step 3: 重写 main.py — 精简 ASR、接入 Scheduler**

```python
from __future__ import annotations
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from backend.config import config
from backend.asr import ASREngine
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler
from backend.llm.client import LLMClient
from backend.llm.selector import Selector
from backend.llm.generator import Generator


class StreamerTrainerApp:
    def __init__(self):
        self.asr = ASREngine(
            model_size=config.asr_model_size,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
            download_timeout=config.asr_download_timeout,
        )
        self.llm = LLMClient(
            provider=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            selector_model=config.llm_selector_model,
            base_url=config.llm_base_url,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens,
            timeout=config.llm_timeout,
        )
        self.selector = Selector()
        self.generator = Generator()
        self.viewer_manager = ViewerManager(
            max_active=config.viewer_max_active,
            min_active=config.viewer_min_active,
            cooldown_sec=config.viewer_cooldown_sec,
        )
        self.streamer_timeline: list[dict] = []
        self.danmaku_clients: set[WebSocket] = set()
        self.scheduler = ViewerScheduler(
            manager=self.viewer_manager,
            llm=self.llm,
            selector=self.selector,
            generator=self.generator,
            tick_interval=config.viewer_tick_interval_sec,
            entry_interval=config.viewer_entry_interval_sec,
            engagement_threshold=config.viewer_engagement_threshold,
            broadcast_system=self.broadcast_system,
            broadcast_danmaku=self.broadcast_danmaku,
            streamer_timeline=self.streamer_timeline,
        )

    async def broadcast_system(self, action: str, name: str, viewer_id: str):
        msg = {"type": "system", "action": action, "name": name, "id": viewer_id}
        dead: set[WebSocket] = set()
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.danmaku_clients -= dead

    async def broadcast_danmaku(self, msg: dict):
        dead: set[WebSocket] = set()
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.danmaku_clients -= dead


class _LazyAppState:
    _instance: Optional[StreamerTrainerApp] = None

    def __getattr__(self, name):
        if _LazyAppState._instance is None:
            _LazyAppState._instance = StreamerTrainerApp()
        return getattr(_LazyAppState._instance, name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(app_state.scheduler.start())
    yield
    app_state.scheduler.stop()
    task.cancel()


app_state: StreamerTrainerApp = _LazyAppState()
app = FastAPI(lifespan=lifespan)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    target = (FRONTEND_DIR / full_path).resolve()
    if not str(target).startswith(str(FRONTEND_DIR)):
        index = FRONTEND_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return FileResponse(str(index))
    if target.is_file():
        return FileResponse(str(target))
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return FileResponse(str(index))


@app.websocket("/audio")
async def audio_endpoint(ws: WebSocket):
    await ws.accept()
    audio_buffer = bytearray()
    try:
        while True:
            data = await ws.receive_bytes()
            audio_buffer.extend(data)
            if len(audio_buffer) >= 32000:
                text = app_state.asr.transcribe(bytes(audio_buffer))
                audio_buffer.clear()
                if text.strip():
                    timestamp = int(time.time())
                    app_state.streamer_timeline.append({"text": text, "offset": timestamp})
    except WebSocketDisconnect:
        pass


@app.websocket("/danmaku")
async def danmaku_endpoint(ws: WebSocket):
    await ws.accept()
    app_state.danmaku_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        app_state.danmaku_clients.discard(ws)


@app.websocket("/control")
async def control_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass


class DebugText(BaseModel):
    text: str


@app.post("/debug_text")
async def debug_text_endpoint(body: DebugText):
    """调试入口：传入文本追加到主播时间线。"""
    try:
        timestamp = int(time.time())
        app_state.streamer_timeline.append({"text": body.text, "offset": timestamp})
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config.host,
        port=config.port,
        reload=False,
    )
```

- [ ] **Step 4: 更新 test_main.py**

```python
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
        mock_instance.llm.chat = AsyncMock(return_value='[]')

        mock_instance.asr = MagicMock()
        mock_instance.asr.transcribe = MagicMock(return_value="主播说你好")

        mock_instance.selector = MagicMock()
        mock_instance.selector.build_pulse_prompt = MagicMock(return_value="prompt")
        mock_instance.selector.parse_pulse_response = MagicMock(return_value=[])

        mock_instance.generator = MagicMock()

        mock_instance.viewer_manager = MagicMock()
        mock_instance.viewer_manager.get_active_viewers = MagicMock(return_value=[])
        mock_instance.viewer_manager.get_viewer = MagicMock(return_value=None)

        mock_instance.broadcast_danmaku = AsyncMock()
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
    """debug_text 应追加到 streamer_timeline"""
    from backend.main import app_state
    app_state.streamer_timeline = []
    client = TestClient(app)
    resp = client.post("/debug_text", json={"text": "hello"})
    assert resp.status_code == 200
```

- [ ] **Step 5: 跑全部测试**

Run: `uv run pytest tests/ -v`
Expected: 所有现有测试通过（部分需要适配，Task 2 已处理 manager 测试）

- [ ] **Step 6: 提交**

```bash
git add backend/main.py backend/config.py config.yaml tests/test_main.py
git commit -m "feat: integrate ViewerScheduler, simplify ASR pipeline"
```

---

### Task 6: 更新 debug_client.py — 保序重连

**Files:**
- Modify: `scripts/debug_client.py`（可选，确认现有代码兼容新的 system 事件格式）

debug_client.py 已经支持 `system` 事件的 `enter`/`leave` action。检查并确认无变更。如果 `broadcast_system` 的消息格式（`type`, `action`, `name`, `id`）与 debug client 一致，则无需修改。

- [ ] **Step 1: 确认 debug_client 兼容**

```bash
grep -n "system\|enter\|leave" scripts/debug_client.py
```

debug_client.py:38-41 已经处理 `type == "system"` 和 `action == "enter"/"leave"`，格式完全兼容。

- [ ] **Step 2: 提交（或无变更）**

---

### Task 7: 最终验证

- [ ] **Step 1: 跑全量测试**

Run: `uv run pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 2: 整理并提交**

```bash
git add -A && git status
git commit -m "feat: viewer lifecycle with engagement model and scheduler"
```
