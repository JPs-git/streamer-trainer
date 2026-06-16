from __future__ import annotations
import asyncio
import json
import logging
import random
import time
from typing import TYPE_CHECKING, Callable, Optional

from backend.viewer.models import ViewerType

from backend.viewer.manager import ViewerManager
from backend.viewer.models import VirtualViewer

logger = logging.getLogger("scheduler")

if TYPE_CHECKING:
    from backend.llm.client import LLMClient
    from backend.llm.generator import Generator

_PROFILE_SYSTEM_PROMPT = "你是一个直播观众生成器。只输出 JSON，不要多余文字。"
_PROFILE_USER_PROMPT = """生成一位直播观众，返回 JSON。
要求：
- name：B站风格昵称（中文为主，偶尔带英文、数字或特殊符号）
- persona：一句话性格描述
  路人观众参考：
  · 偶然刷到的 看看就走
  · 潜水型 懒得说话
  · 随便逛逛 没特别关注
  · 新来的 先观察一下
- relationship：路人 或 新关注

参考这些真实 B站用户昵称的风格：
无限板板
怪盗キッドのAsuka
鈊哆哆
愿被保护一次
机智的派大星1
文青Cyan
清夏CyanSommer
断桥烟雨话江南
向日葵-MADAO
枫狼coymaple
月球秃子
今晚有宵夜吗
星华梦铃
情深的海
新潜水萌新
创逝神
中后所人士
而我能听见时光雨的声音
迷路的LuLuu

JSON格式：{"name": "...", "persona": "...", "relationship": "..."}"""

_LURKER_PHRASES = [
    "来了", "看看", "路过", "？", "哈？", "确实", "好家伙",
    "原来如此", "有点意思", "不太懂", "真的吗", "啊这", "等等",
    "细说", "笑死", "绝了", "好活", "麻了", "难绷",
    "牛的", "这啥", "懂了",
]

_GUIDER_SYSTEM_PROMPT = """你是引导型观众 负责帮主播把话题聊下去 主播是Vtuber在杂谈闲聊

主播不说话 → 发弹幕引导主播开口 比如"聊聊这个""展开讲讲""细说""然后呢""为什么"
主播说了什么 → 追问或互动 比如"真的假的""展开说说""我不太懂 讲讲""这啥情况""原来还有这种事"
始终针对主播的发言内容回应 不说空话
发短点 几个字到十来个字
不用标点符号
不用带自己名字 不用加@"""


class ViewerScheduler:
    def __init__(
        self,
        manager: ViewerManager,
        llm: LLMClient,
        generator: Generator,
        tick_interval: float = 15.0,
        churn_per_tick: int = 5,
        guider_ratio: float = 0.3,
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
        self.churn_per_tick = churn_per_tick
        self.guider_ratio = guider_ratio
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
            "Scheduler initialized: tick=%ss churn=%d guider_ratio=%.2f",
            tick_interval, churn_per_tick, guider_ratio,
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

        active = self.manager.get_active_viewers()
        timeline_len = len(self.streamer_timeline)
        streamer_has_new = self._last_speech_index < timeline_len

        logger.debug(
            "Tick: active=%d timeline=%d has_new=%s",
            len(active), timeline_len, streamer_has_new,
        )

        # 1. Schedule speakers (fixed base rate)
        speak_tasks: list[asyncio.Task] = []
        speak_log = []
        for v in active:
            prob = 0.35 if v.viewer_type == "lurker" else 0.6
            if streamer_has_new:
                prob = min(1.0, prob * 3.0)
            last_tick = self._last_spoke_tick.get(v.viewer_id)
            if last_tick is not None and timeline_len - last_tick < 2:
                prob *= 0.3
            spoke = random.random() < prob
            speak_log.append(f"{v.name}(prob={prob:.2f})={'讲' if spoke else '静'}")
            if spoke:
                self._last_spoke_tick[v.viewer_id] = timeline_len
                speak_tasks.append(asyncio.create_task(self._do_speak(v)))
        logger.info("Speak: %s", ", ".join(speak_log))

        if speak_tasks:
            await asyncio.gather(*speak_tasks)

        # 2. Churn — normal distribution centered at 0
        active = self.manager.get_active_viewers()
        current = len(active)
        sigma = max(1.0, self.churn_per_tick / 5)
        delta = int(round(random.gauss(0, sigma)))
        delta = max(-self.churn_per_tick, min(self.churn_per_tick, delta))
        target = max(self.manager.min_active, min(self.manager.max_active, current + delta))

        churn_tasks: list[asyncio.Task] = []
        if target > current:
            for _ in range(target - current):
                profile = await self._generate_viewer_profile()
                delay = random.uniform(0, self.tick_interval)
                churn_tasks.append(asyncio.create_task(self._delayed_enter(profile, delay)))
        elif target < current:
            remove_count = current - target
            lurkers = [v for v in active if v.viewer_type == "lurker"]
            candidates = lurkers if lurkers else active
            to_remove = random.sample(candidates, min(remove_count, len(candidates)))
            for v in to_remove:
                delay = random.uniform(0, self.tick_interval)
                churn_tasks.append(asyncio.create_task(self._delayed_leave(v, delay)))

        if churn_tasks:
            await asyncio.gather(*churn_tasks)

        self._last_speech_index = timeline_len

        # 3. Broadcast viewer status heartbeat
        active = self.manager.get_active_viewers()
        if self.broadcast_status:
            viewer_list = [
                {
                    "id": v.viewer_id,
                    "name": v.name,
                    "persona": v.persona,
                    "viewer_type": v.viewer_type,
                    "follows": v.follows,
                    "relationship": v.relationship,
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
        viewer_type: ViewerType = "guider" if random.random() < self.guider_ratio else "lurker"
        try:
            raw = await self.llm.chat(
                system=_PROFILE_SYSTEM_PROMPT,
                user=_PROFILE_USER_PROMPT,
            )
            if raw is None:
                raise ValueError("LLM returned None")
            profile = json.loads(raw)
            return {
                "name": profile.get("name", f"观众{random.randint(1,999)}"),
                "persona": profile.get("persona", "普通观众"),
                "viewer_type": viewer_type,
                "relationship": profile.get("relationship", "路人"),
                "follows": profile.get("relationship", "") == "新关注",
            }
        except Exception as e:
            logger.warning("Profile generation failed: %s", e)
            return {
                "name": f"观众{random.randint(1,999)}",
                "persona": "普通观众",
                "viewer_type": viewer_type,
                "relationship": "路人",
                "follows": False,
            }

    async def _enter_viewer(self, profile: dict):
        if len(self.manager.get_active_viewers()) >= self.manager.max_active:
            return
        viewer_id = f"v_{int(time.time())}_{random.randint(100, 999)}"
        v = VirtualViewer(
            viewer_id=viewer_id,
            name=profile["name"],
            persona=profile["persona"],
            viewer_type=profile.get("viewer_type", "lurker"),
            follows=profile["follows"],
            relationship=profile["relationship"],
        )
        self.manager.add_viewer(v)
        self.manager.activate_viewer(v.viewer_id)
        logger.info("  Enter: %s (%s) [%s]", v.name, v.relationship, v.viewer_type)
        if self.broadcast_system:
            await self.broadcast_system("enter", v.name, v.viewer_id)

    # ------------------------------------------------------------------
    # Rules engine helpers
    # ------------------------------------------------------------------

    async def _do_leave(self, viewer: VirtualViewer):
        logger.info("  Leave: %s", viewer.name)
        self._last_spoke_tick.pop(viewer.viewer_id, None)
        if self.broadcast_system:
            await self.broadcast_system("leave", viewer.name, viewer.viewer_id)
        self.manager.remove_viewer(viewer.viewer_id)

    async def _do_speak(self, viewer: VirtualViewer):
        if viewer.state != "active":
            return
        delay = random.uniform(0, 4)
        await asyncio.sleep(delay)
        if viewer.state != "active":
            return

        if viewer.viewer_type == "lurker":
            text = random.choice(_LURKER_PHRASES)
        else:
            since = viewer.entry_time or 0
            recent = [e for e in self.streamer_timeline if e.get("offset", 0) >= since]
            recent = recent[-10:]
            current_asr = "\n".join(e["text"] for e in recent) if recent else "主播还没说话"
            chat_since = [e for e in self.room_chat_log if e.get("offset", 0) >= since]
            prompt = self.generator.build_prompt(
                name=viewer.name,
                persona=viewer.persona,
                room_chat_log=chat_since,
                my_danmaku=[],
                relationships=viewer.memory.relationships,
                current_asr=current_asr,
                follows=viewer.follows,
                relationship=viewer.relationship,
            )
            raw = await self.llm.chat(
                system=_GUIDER_SYSTEM_PROMPT,
                user=prompt,
            )
            if raw is None:
                return
            text = self.generator.parse_danmaku(raw)
            if not text:
                logger.warning("  Generator returned empty for %s", viewer.name)
                return
        viewer.memory.add_my_danmaku(text, int(time.time()), "streamer")
        viewer.last_active = int(time.time())
        viewer.interaction_count += 1
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
        logger.info("  Danmaku: %s [%s]: %s", viewer.viewer_type, viewer.name, text)
        if self.broadcast_danmaku:
            await self.broadcast_danmaku(msg)

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    async def _delayed_enter(self, profile: dict, delay: float):
        await asyncio.sleep(delay)
        await self._enter_viewer(profile)

    async def _delayed_leave(self, viewer: VirtualViewer, delay: float):
        await asyncio.sleep(delay)
        await self._do_leave(viewer)

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
