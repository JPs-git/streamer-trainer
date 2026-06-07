from __future__ import annotations
import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Callable, Optional

from backend.viewer.manager import ViewerManager
from backend.viewer.models import VirtualViewer

logger = logging.getLogger("scheduler")

if TYPE_CHECKING:
    from backend.llm.agent import AgentClient
    from backend.llm.client import LLMClient
    from backend.llm.generator import Generator


class ViewerScheduler:
    def __init__(
        self,
        manager: ViewerManager,
        agent: AgentClient,
        llm: LLMClient,
        generator: Generator,
        tick_interval: float = 15.0,
        engagement_threshold: int = 20,
        broadcast_system: Optional[Callable] = None,
        broadcast_danmaku: Optional[Callable] = None,
        broadcast_status: Optional[Callable] = None,
        streamer_timeline: Optional[list[dict]] = None,
        room_chat_log: Optional[list[dict]] = None,
    ):
        self.manager = manager
        self.agent = agent
        self.llm = llm
        self.generator = generator
        self.tick_interval = tick_interval
        self.engagement_threshold = engagement_threshold
        self.broadcast_system = broadcast_system
        self.broadcast_danmaku = broadcast_danmaku
        self.broadcast_status = broadcast_status
        self.streamer_timeline = streamer_timeline if streamer_timeline is not None else []
        self._last_speech_index = 0
        self._running = False
        self._paused = True
        self.room_chat_log = room_chat_log if room_chat_log is not None else []
        logger.info(
            "Scheduler initialized: tick=%ss threshold=%d",
            tick_interval, engagement_threshold,
        )

    async def start(self):
        self._running = True
        logger.info("Scheduler loop started (paused=%s)", self._paused)
        while self._running:
            next_tick = time.monotonic() + self.tick_interval
            try:
                await self._tick()
            except Exception as e:
                logger.error("Tick crashed: %s", e, exc_info=True)
            now = time.monotonic()
            if now < next_tick:
                await asyncio.sleep(next_tick - now)

    def stop(self):
        self._running = False
        logger.info("Scheduler stopped")

    def pause(self):
        self._paused = True
        logger.info("Scheduler paused")

    def resume(self):
        self._paused = False
        logger.info("Scheduler resumed")

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    async def _tick(self):
        if self._paused:
            return

        now = time.time()
        active = self.manager.get_active_viewers()
        timeline_len = len(self.streamer_timeline)
        streamer_has_new = self._last_speech_index < timeline_len
        silence_duration = self._compute_silence_duration(now)

        logger.debug(
            "Tick: active=%d timeline=%d has_new=%s silence=%.0fs",
            len(active), timeline_len, streamer_has_new, silence_duration,
        )

        # 1. Basic decay (no personality type dependency)
        for v in active:
            before = v.engagement
            decay = random.uniform(1, 5) + random.uniform(-2, 2)
            v.engagement = max(0, v.engagement - decay)

        # 2. Gather state and call Agent
        viewer_states = self._build_viewer_states(active)
        latest_text = (
            self.streamer_timeline[-1]["text"][:100]
            if streamer_has_new and self.streamer_timeline else ""
        )
        room_stats = {
            "active_count": len(active),
            "max_active": self.manager.max_active,
            "min_active": self.manager.min_active,
        }

        actions: list[dict] = []
        try:
            actions = await self.agent.decide(viewer_states, latest_text, silence_duration, room_stats)
        except Exception as e:
            logger.error("Agent.decide failed: %s", e)

        # 3. Execute actions (speak tasks collected for parallel generation)
        speak_tasks: list[asyncio.Task] = []
        for action in actions:
            try:
                atype = action.get("type")
                if atype == "schedule_speak":
                    speak_tasks.append(asyncio.create_task(self._do_speak(action)))
                elif atype == "spawn_viewer":
                    await self._do_spawn(action)
                elif atype == "adjust_engagement":
                    self._do_adjust(action)
                elif atype == "remove_viewer":
                    await self._do_remove(action)
                else:
                    logger.warning("  Unknown action type: %s", atype)
            except Exception as e:
                logger.error("  Action failed: %s (%s)", action.get("type"), e)

        if speak_tasks:
            await asyncio.gather(*speak_tasks)

        # 4. Backfill: if below min_active, add simple viewers
        if len(self.manager.get_active_viewers()) < self.manager.min_active:
            logger.debug("  Below min_active after tick, backfilling...")
            await self._backfill_to_min()

        self._last_speech_index = timeline_len

        # 5. Broadcast viewer status heartbeat
        active = self.manager.get_active_viewers()
        if self.broadcast_status:
            viewer_list = [
                {
                    "id": v.viewer_id,
                    "name": v.name,
                    "persona": v.persona,
                    "follows": v.follows,
                    "relationship": v.relationship,
                    "engagement": v.engagement,
                }
                for v in active
            ]
            await self.broadcast_status({
                "type": "status",
                "active_count": len(active),
                "max_active": self.manager.max_active,
                "min_active": self.manager.min_active,
                "viewers": viewer_list,
            })

    # ------------------------------------------------------------------
    # Agent action handlers
    # ------------------------------------------------------------------

    async def _do_spawn(self, action: dict):
        if len(self.manager.get_active_viewers()) >= self.manager.max_active:
            logger.debug("  Spawn skipped: at max_active")
            return
        viewer_id = f"v_{int(time.time())}_{random.randint(100, 999)}"
        v = VirtualViewer(
            viewer_id=viewer_id,
            name=action.get("name", "观众"),
            persona=action.get("persona", ""),
            follows=action.get("follows", True),
            relationship=action.get("relationship", ""),
            engagement=min(100, max(60, action.get("engagement", 80))),
        )
        self.manager.add_viewer(v)
        self.manager.activate_viewer(v.viewer_id)
        logger.info("  Enter: %s (%s, engagement=%d)", v.name, v.relationship, v.engagement)
        if self.broadcast_system:
            await self.broadcast_system("enter", v.name, v.viewer_id)

    def _do_adjust(self, action: dict):
        v = self.manager.get_viewer(action.get("viewer_id", ""))
        if v and v.state == "active":
            delta = action.get("delta", 0)
            v.engagement = max(0, min(100, v.engagement + delta))

    async def _do_speak(self, action: dict):
        v = self.manager.get_viewer(action.get("viewer_id", ""))
        if not v or v.state != "active":
            return
        intent = action.get("intent", "")
        if not intent:
            return
        delay = random.uniform(0, 4)
        await asyncio.sleep(delay)
        if v.state != "active":
            return

        current_asr = self.streamer_timeline[-1]["text"] if self.streamer_timeline else ""
        prompt = self.generator.build_prompt(
            name=v.name,
            persona=v.persona,
            room_chat_log=self.room_chat_log,
            my_danmaku=v.memory.my_danmaku,
            relationships=v.memory.relationships,
            current_asr=current_asr,
            follows=v.follows,
            relationship=v.relationship,
        )
        prompt += f"\n\n[发言意图]\n{intent}"
        raw = await self.llm.chat(
            system=self.generator.GENERATOR_SYSTEM_PROMPT,
            user=prompt,
        )
        text = self.generator.parse_danmaku(raw)
        if not text:
            logger.warning("  Generator returned empty for %s", v.name)
            return
        v.memory.add_my_danmaku(text, int(time.time()), "streamer")
        v.last_active = int(time.time())
        v.interaction_count += 1
        now = int(time.time())
        self.room_chat_log.append({
            "type": "danmaku",
            "viewer_id": v.viewer_id,
            "name": v.name,
            "text": text,
            "offset": now,
        })
        if len(self.room_chat_log) > 200:
            self.room_chat_log[:50] = []
        msg = {
            "type": "danmaku",
            "id": v.viewer_id,
            "name": v.name,
            "text": text,
            "personality": "",
            "effect": "normal",
        }
        logger.info("  Danmaku: %s: %s", v.name, text)
        if self.broadcast_danmaku:
            await self.broadcast_danmaku(msg)

    async def _do_remove(self, action: dict):
        v = self.manager.get_viewer(action.get("viewer_id", ""))
        if not v or v.state != "active":
            return
        logger.info("  Leave: %s (engagement=%d)", v.name, v.engagement)
        if self.broadcast_system:
            await self.broadcast_system("leave", v.name, v.viewer_id)
        self.manager.remove_viewer(v.viewer_id)

    # ------------------------------------------------------------------
    # Backfill for min_active
    # ------------------------------------------------------------------

    async def _backfill_to_min(self):
        """If Agent didn't spawn enough viewers, backfill with simple viewers."""
        count = 0
        while len(self.manager.get_active_viewers()) < self.manager.min_active:
            if len(self.manager.get_active_viewers()) >= self.manager.max_active:
                break
            viewer_id = f"v_{int(time.time())}_{random.randint(100, 999)}"
            v = VirtualViewer(
                viewer_id=viewer_id,
                name=f"观众{random.randint(1, 999)}",
                persona="普通观众",
                follows=True,
                relationship="普通观众",
                engagement=80,
            )
            self.manager.add_viewer(v)
            self.manager.activate_viewer(v.viewer_id)
            logger.info("  Backfill enter: %s (engagement=%d)", v.name, v.engagement)
            if self.broadcast_system:
                await self.broadcast_system("enter", v.name, v.viewer_id)
            count += 1
        if count:
            logger.info("Backfill complete: %d viewers entered", count)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_silence_duration(self, now: float) -> float:
        if not self.streamer_timeline:
            return 0.0
        last = self.streamer_timeline[-1]
        offset = last.get("offset", 0)
        if not isinstance(offset, (int, float)):
            logger.error("Bad timeline entry: %s (offset=%r)", last, offset)
            return 0.0
        return now - offset

    def _build_viewer_states(self, active: list[VirtualViewer]) -> list[dict]:
        return [
            {
                "id": v.viewer_id,
                "name": v.name,
                "persona": v.persona,
                "follows": v.follows,
                "relationship": v.relationship,
                "engagement": v.engagement,
                "interaction_count": v.interaction_count,
            }
            for v in active
        ]
