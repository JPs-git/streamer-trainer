from __future__ import annotations
import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Callable, Optional

from backend.viewer.manager import ViewerManager

logger = logging.getLogger("scheduler")

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
        self._startup_filled = False
        self._running = False
        self._paused = False
        logger.info(
            "Scheduler initialized: tick=%ss entry_interval=%ss threshold=%d",
            tick_interval, entry_interval, engagement_threshold,
        )

    async def start(self):
        self._running = True
        logger.info("Scheduler started")
        while self._running:
            await self._tick()
            await asyncio.sleep(self.tick_interval)

    def stop(self):
        self._running = False
        logger.info("Scheduler stopped")

    def pause(self):
        self._paused = True
        logger.info("Scheduler paused")

    def resume(self):
        self._paused = False
        logger.info("Scheduler resumed")

    async def _tick(self):
        if self._paused:
            return

        now = time.time()
        timeline_len = len(self.streamer_timeline)
        streamer_has_new_speech = self._last_speech_index < timeline_len
        silence_duration = self._compute_silence_duration(now)

        active = self.manager.get_active_viewers()
        logger.debug(
            "Tick: active=%d timeline=%d has_new=%s silence=%.0fs",
            len(active), timeline_len, streamer_has_new_speech, silence_duration,
        )

        if not active:
            await self._try_entry()
            return

        # 1. 基础衰减 + 随机波动
        for v in active:
            before = v.engagement
            decay = self._compute_decay(v)
            v.engagement = max(ENGAGEMENT_MIN, min(ENGAGEMENT_MAX, v.engagement - decay))
            logger.debug("  Decay %s: %d -> %d (decay=%.1f)", v.name, before, v.engagement, decay)

        # 2. LLM 批量评估
        viewer_states = self._build_viewer_states(active, streamer_has_new_speech, silence_duration)
        selector_result = await self._call_selector(active, streamer_has_new_speech, silence_duration)

        if selector_result is None:
            logger.warning("  Selector returned None, skipping tick")
            await self._try_entry()
            return

        logger.info("  Selector result: %d items", len(selector_result))
        for item in selector_result:
            logger.debug("    %s: delta=%+d speak=%s leave=%s",
                         item.get("id", "?"), item.get("engagement_delta", 0),
                         item.get("speak"), item.get("leave"))

        # 3. 应用 engagement 修正
        for item in selector_result:
            v = self.manager.get_viewer(item.get("id", ""))
            if v and v.state == "active":
                delta = item.get("engagement_delta", 0)
                if delta != 0:
                    logger.debug("  Engagement fix %s: %d %+d -> %d", v.name, v.engagement, delta, v.engagement + delta)
                v.engagement = max(ENGAGEMENT_MIN, min(ENGAGEMENT_MAX, v.engagement + delta))

        # 4. 处理发言
        speak_tasks = []
        for item in selector_result:
            if item.get("speak"):
                v = self.manager.get_viewer(item.get("id", ""))
                if v and v.state == "active":
                    delay = random.uniform(0, 6)
                    logger.info("  Speak scheduled: %s intent=%s delay=%.1fs", v.name, item["speak"], delay)
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
                        logger.info("  Leave: %s (engagement=%d)", v.name, v.engagement)
                        self.manager.deactivate_viewer(vid)
                        if self.broadcast_system:
                            await self.broadcast_system("leave", v.name, v.viewer_id)
                else:
                    logger.info("  Leave blocked for %s: at min_active (%d)", vid, self.manager.min_active)

        # 6. 入场
        await self._try_entry()

        # 7. 冷却重置
        self.manager.reset_cooldown_viewers()

        # 8. 更新已处理的发言索引
        self._last_speech_index = timeline_len

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
                "last_danmaku": v.memory.my_danmaku[-1]["text"][:40] if v.memory.my_danmaku else None,
            }
            for v in active
        ]

    async def _call_selector(self, active, has_new: bool, silence: float):
        latest_speech = ""
        if has_new and self.streamer_timeline:
            latest_speech = self.streamer_timeline[-1].get("text", "")
        viewer_states = self._build_viewer_states(active, has_new, silence)
        prompt = self.selector.build_pulse_prompt(latest_speech, silence, viewer_states)
        logger.debug("  Selector prompt (%d chars): latest=%r silence=%.0fs",
                     len(prompt), latest_speech[:50], silence)
        raw = await self.llm.chat(
            system=self.selector.SELECTOR_SYSTEM_PROMPT,
            user=prompt,
            model=self.llm.selector_model,
        )
        logger.debug("  Selector raw response: %s", raw[:200] if raw else "None")
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
            logger.warning("  Generator returned empty for %s, skipping", v.name)
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
        logger.info("  Danmaku: %s: %s", v.name, text)
        # 广播到所有人的 other_danmaku，供后续引用
        for other in self.manager.get_active_viewers():
            if other.viewer_id != v.viewer_id:
                other.memory.add_other_danmaku(v.viewer_id, "streamer", text[:40])
        if self.broadcast_danmaku:
            await self.broadcast_danmaku(msg)

    async def _try_entry(self):
        # 启动阶段：一次性填到 min_active
        if not self._startup_filled:
            self._startup_filled = True
            await self._fill_to_min()
            return
        # 正常阶段：按 entry_interval 每次进一个
        if time.time() - self._last_entry_time < self.entry_interval:
            return
        await self._enter_one()

    async def _fill_to_min(self):
        count = 0
        while len(self.manager.get_active_viewers()) < self.manager.min_active:
            inactive = self.manager.get_inactive_viewers()
            if not inactive or len(self.manager.get_active_viewers()) >= self.manager.max_active:
                break
            v = random.choice(inactive)
            self.manager.activate_viewer(v.viewer_id)
            logger.info("  Startup enter: %s (%s, engagement=%d)", v.name, v.personality_type, v.engagement)
            if self.broadcast_system:
                await self.broadcast_system("enter", v.name, v.viewer_id)
            count += 1
        self._last_entry_time = time.time()
        logger.info("Startup fill complete: %d viewers entered, %d active", count, len(self.manager.get_active_viewers()))

    async def _enter_one(self):
        inactive = self.manager.get_inactive_viewers()
        if not inactive:
            logger.debug("  Entry skipped: no inactive viewers")
            return
        if len(self.manager.get_active_viewers()) >= self.manager.max_active:
            logger.debug("  Entry skipped: at max_active")
            return
        v = random.choice(inactive)
        self.manager.activate_viewer(v.viewer_id)
        self._last_entry_time = time.time()
        logger.info("  Enter: %s (%s, engagement=%d)", v.name, v.personality_type, v.engagement)
        if self.broadcast_system:
            await self.broadcast_system("enter", v.name, v.viewer_id)
