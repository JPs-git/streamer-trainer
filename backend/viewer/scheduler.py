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
