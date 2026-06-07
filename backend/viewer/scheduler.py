from __future__ import annotations
import asyncio
import json
import logging
import random
import time
from typing import TYPE_CHECKING, Callable, Optional

from backend.viewer.manager import ViewerManager
from backend.viewer.models import VirtualViewer

logger = logging.getLogger("scheduler")

if TYPE_CHECKING:
    from backend.llm.client import LLMClient
    from backend.llm.generator import Generator

_PROFILE_SYSTEM_PROMPT = "你是一个直播观众生成器。只输出 JSON，不要多余文字。"
_PROFILE_USER_PROMPT = """生成一位直播观众，返回 JSON。
要求：
- name：中文昵称（2-3字）
- persona：一句话性格描述（如"活泼外向的老粉，喜欢夸主播"）
- relationship：老粉 或 路人 或 新关注
- engagement：60-100 的数字

JSON格式：{"name": "...", "persona": "...", "relationship": "...", "engagement": 数字}"""

_COMMON_INTENTS = [
    "夸主播操作",
    "问游戏问题",
    "吐槽失误",
    "热情夸赞",
    "积极互动",
]

_SILENCE_INTENTS = [
    "催主播说话",
    "闲聊等待",
    "自言自语",
    "分享感受",
]


class ViewerScheduler:
    def __init__(
        self,
        manager: ViewerManager,
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
        self._last_spoke_tick: dict[str, int] = {}
        self._pending_profile: Optional[asyncio.Task] = None
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

        logger.debug(
            "Tick: active=%d timeline=%d has_new=%s",
            len(active), timeline_len, streamer_has_new,
        )

        # 1. Basic decay
        decay_log = []
        for v in active:
            decay = round(random.uniform(1, 5) + random.uniform(-2, 2), 1)
            before = v.engagement
            v.engagement = max(0, v.engagement - decay)
            decay_log.append(f"{v.name}: {before}->{v.engagement}(-{decay})")
        logger.info("Decay: %s", ", ".join(decay_log))

        # 2. Rules engine decisions
        speak_tasks: list[asyncio.Task] = []
        leaves = 0

        # 2a. Remove low-engagement viewers
        for v in active[:]:
            if v.engagement <= self.engagement_threshold:
                await self._do_leave(v)
                leaves += 1

        # 2b. Schedule speakers
        active = self.manager.get_active_viewers()
        speak_log = []
        for v in active:
            prob = (v.engagement / 100.0) * 0.6
            if streamer_has_new:
                prob *= 1.5
            last_tick = self._last_spoke_tick.get(v.viewer_id)
            if last_tick is not None and timeline_len - last_tick < 2:
                prob *= 0.3
            spoke = random.random() < prob
            speak_log.append(f"{v.name}(eng={v.engagement},prob={prob:.2f})={'讲' if spoke else '静'}")
            if spoke:
                intent = self._pick_intent(v, streamer_has_new)
                self._last_spoke_tick[v.viewer_id] = timeline_len
                speak_tasks.append(asyncio.create_task(self._do_speak(v, intent)))
        logger.info("Speak: %s", ", ".join(speak_log))

        if speak_tasks:
            await asyncio.gather(*speak_tasks)

        # 3. Backfill if below min_active
        active = self.manager.get_active_viewers()
        before_backfill = len(active)
        if len(active) < self.manager.min_active:
            await self._backfill_viewer()

        self._last_speech_index = timeline_len

        # 4. Broadcast viewer status heartbeat
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
    # Profile generation (LLM)
    # ------------------------------------------------------------------

    async def _generate_viewer_profile(self) -> dict:
        try:
            raw = await self.llm.chat(
                system=_PROFILE_SYSTEM_PROMPT,
                user=_PROFILE_USER_PROMPT,
            )
            profile = json.loads(raw)
            return {
                "name": profile.get("name", f"观众{random.randint(1,999)}"),
                "persona": profile.get("persona", "普通观众"),
                "relationship": profile.get("relationship", "路人"),
                "follows": profile.get("relationship", "") in ("老粉", "新关注"),
                "engagement": min(100, max(60, profile.get("engagement", 80))),
            }
        except Exception as e:
            logger.warning("Profile generation failed: %s", e)
            return {
                "name": f"观众{random.randint(1,999)}",
                "persona": "普通观众",
                "relationship": "路人",
                "follows": False,
                "engagement": 80,
            }

    async def _enter_viewer(self, profile: dict):
        if len(self.manager.get_active_viewers()) >= self.manager.max_active:
            return
        viewer_id = f"v_{int(time.time())}_{random.randint(100, 999)}"
        v = VirtualViewer(
            viewer_id=viewer_id,
            name=profile["name"],
            persona=profile["persona"],
            follows=profile["follows"],
            relationship=profile["relationship"],
            engagement=profile["engagement"],
        )
        self.manager.add_viewer(v)
        self.manager.activate_viewer(v.viewer_id)
        logger.info(
            "  Enter: %s (%s, engagement=%d)",
            v.name, v.relationship, v.engagement,
        )
        if self.broadcast_system:
            await self.broadcast_system("enter", v.name, v.viewer_id)

    # ------------------------------------------------------------------
    # Rules engine helpers
    # ------------------------------------------------------------------

    def _pick_intent(self, viewer: VirtualViewer, streamer_has_new: bool) -> str:
        pool = list(_COMMON_INTENTS)
        if not streamer_has_new:
            pool.extend(_SILENCE_INTENTS)
        if viewer.engagement > 70:
            pool.append("热情夸赞")
        if viewer.relationship == "老粉":
            pool.append("用梗互动")
        elif viewer.relationship == "路人":
            pool.append("新手提问")
        return random.choice(pool)

    async def _do_leave(self, viewer: VirtualViewer):
        logger.info("  Leave: %s (engagement=%d)", viewer.name, viewer.engagement)
        self._last_spoke_tick.pop(viewer.viewer_id, None)
        if self.broadcast_system:
            await self.broadcast_system("leave", viewer.name, viewer.viewer_id)
        self.manager.remove_viewer(viewer.viewer_id)

    async def _do_speak(self, viewer: VirtualViewer, intent: str):
        if viewer.state != "active":
            return
        delay = random.uniform(0, 4)
        await asyncio.sleep(delay)
        if viewer.state != "active":
            return

        current_asr = self.streamer_timeline[-1]["text"] if self.streamer_timeline else ""
        prompt = self.generator.build_prompt(
            name=viewer.name,
            persona=viewer.persona,
            room_chat_log=self.room_chat_log,
            my_danmaku=viewer.memory.my_danmaku,
            relationships=viewer.memory.relationships,
            current_asr=current_asr,
            follows=viewer.follows,
            relationship=viewer.relationship,
        )
        prompt += f"\n\n[发言意图]\n{intent}"
        raw = await self.llm.chat(
            system=self.generator.GENERATOR_SYSTEM_PROMPT,
            user=prompt,
        )
        text = self.generator.parse_danmaku(raw)
        if not text:
            logger.warning("  Generator returned empty for %s", viewer.name)
            return
        viewer.memory.add_my_danmaku(text, int(time.time()), "streamer")
        viewer.last_active = int(time.time())
        viewer.interaction_count += 1
        viewer.engagement = min(100, viewer.engagement + random.uniform(3, 8))
        now = int(time.time())
        self.room_chat_log.append({
            "type": "danmaku",
            "viewer_id": viewer.viewer_id,
            "name": viewer.name,
            "text": text,
            "offset": now,
        })
        if len(self.room_chat_log) > 200:
            self.room_chat_log[:50] = []
        msg = {
            "type": "danmaku",
            "id": viewer.viewer_id,
            "name": viewer.name,
            "text": text,
            "personality": "",
            "effect": "normal",
        }
        logger.info("  Danmaku: %s: %s", viewer.name, text)
        if self.broadcast_danmaku:
            await self.broadcast_danmaku(msg)

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    async def _backfill_viewer(self):
        count = 0
        while True:
            active = self.manager.get_active_viewers()
            if len(active) >= self.manager.min_active:
                break
            if len(active) >= self.manager.max_active:
                break
            profile = await self._generate_viewer_profile()
            await self._enter_viewer(profile)
            count += 1
        if count:
            logger.info("Backfill complete: %d viewer(s) entered", count)

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
