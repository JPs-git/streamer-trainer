from __future__ import annotations
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("agent")

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "spawn_viewer",
            "description": "创建一位新观众进入直播间。每次调用创建一个观众，如需多人可多次调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "观众昵称"},
                    "persona": {"type": "string", "description": "角色设定描述，如'热情外向的老粉，喜欢夸主播操作'"},
                    "follows": {"type": "boolean", "description": "是否关注了主播"},
                    "relationship": {"type": "string", "description": "与主播的关系，如'老粉'、'路人'、'新关注'"},
                    "engagement": {"type": "integer", "description": "初始兴趣值 60-100", "minimum": 60, "maximum": 100},
                },
                "required": ["name", "persona", "follows", "relationship", "engagement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_engagement",
            "description": "调整某个活跃观众的 engagement 值（-20 ~ +20）。调动因（内容是否对口、主播表现等）由你判断。",
            "parameters": {
                "type": "object",
                "properties": {
                    "viewer_id": {"type": "string", "description": "观众ID"},
                    "delta": {"type": "integer", "description": "变化值", "minimum": -20, "maximum": 20},
                },
                "required": ["viewer_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_speak",
            "description": "安排一位观众发言。实际弹幕文本将由另一个模型生成，你只需提供发言意图。",
            "parameters": {
                "type": "object",
                "properties": {
                    "viewer_id": {"type": "string", "description": "观众ID"},
                    "intent": {"type": "string", "description": "发言意图描述，如'夸主播操作''问游戏技巧''吐槽失误'"},
                },
                "required": ["viewer_id", "intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_viewer",
            "description": "观众离场。离场后该观众将被删除，不再出现。只有 engagement <= 20 的观众才可以离场。",
            "parameters": {
                "type": "object",
                "properties": {
                    "viewer_id": {"type": "string", "description": "观众ID"},
                },
                "required": ["viewer_id"],
            },
        },
    },
]

_SYSTEM_PROMPT = """你是直播间"观众脉搏"调度系统。每 15 秒评估一次直播间状态，通过工具调用管理虚拟观众。

当前职责：
1. 如果房间活跃人数 < min_active，必须立即进人到 min_active
2. 根据主播内容决定谁发言、谁离场、是否进新人
3. 每次 tick 可以执行多个操作（调用多次工具）

观众管理规则：
- 每位观众有 engagement（0-100），低于 20 可离场
- 发言概率与 engagement 正相关
- 活跃人数不能超过 max_active
- 离场观众立即删除，不可再出现"""


class AgentClient:
    def __init__(
        self,
        api_key: str,
        model: str = "kimi-k2.6",
        base_url: Optional[str] = None,
        temperature: float = 0.8,
        timeout: float = 30.0,
    ):
        from openai import AsyncOpenAI
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)
        self.model = model
        self.temperature = temperature

    async def decide(
        self,
        viewer_states: list[dict],
        timeline_text: str,
        silence_sec: float,
        room_stats: dict,
    ) -> list[dict[str, Any]]:
        user_prompt = self._build_user_prompt(viewer_states, timeline_text, silence_sec, room_stats)
        logger.debug("Agent prompt:\n%s", user_prompt)

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=1.0,  # kimi-k2.6 只允许 1
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                tools=TOOLS,
                tool_choice="auto",
            )
        except Exception as e:
            logger.error("Agent API call failed: %s", e)
            body = getattr(e, "body", None) or getattr(e, "response", None)
            if isinstance(body, dict):
                logger.error("API error detail: %s", body)
            elif body is not None:
                logger.error("API error response: %s", str(body)[:500])
            return []

        msg = resp.choices[0].message
        if not msg.tool_calls:
            logger.debug("Agent returned no tool calls")
            return []

        actions: list[dict[str, Any]] = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
                actions.append({"type": tc.function.name, **args})
            except json.JSONDecodeError:
                logger.warning("Agent returned invalid JSON: %s", tc.function.arguments)
                continue

        logger.debug("Agent actions: %d calls", len(actions))
        for a in actions:
            logger.debug("  %s: %s", a["type"], {k: v for k, v in a.items() if k != "type"})
        return actions

    @staticmethod
    def _build_user_prompt(
        viewer_states: list[dict],
        timeline_text: str,
        silence_sec: float,
        room_stats: dict,
    ) -> str:
        lines = ["--- 当前直播间状态 ---"]
        if timeline_text:
            lines.append(f"[主播最近发言] {timeline_text}")
        else:
            lines.append(f"[沉默时长] {silence_sec:.0f} 秒")
        lines.append("")
        lines.append(
            f"房间: {room_stats['active_count']}/{room_stats['max_active']} 人活跃, "
            f"还可进 {room_stats['max_active'] - room_stats['active_count']} 人, "
            f"min_active={room_stats['min_active']}"
        )
        lines.append("")
        if viewer_states:
            lines.append("[活跃观众]")
            for vs in viewer_states:
                follows = "[关注]" if vs.get("follows") else "[未关注]"
                lines.append(
                    f"- {vs['name']}({vs['id']}) engagement={vs.get('engagement', 100)} "
                    f"{follows} {vs.get('relationship', '')} "
                    f"人设: {vs.get('persona', '')}"
                )
        else:
            lines.append("[当前无活跃观众]")
        lines.extend([
            "",
            "请根据以上状态，通过工具调用管理观众。如需多人入场或发言，多次调用工具。",
        ])
        return "\n".join(lines)
