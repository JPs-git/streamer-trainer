from __future__ import annotations
from typing import Optional


class Generator:
    GENERATOR_SYSTEM_PROMPT = """你是一个直播间的虚拟观众。根据你的角色设定、记忆和当前主播说的话，
生成一条符合角色性格的弹幕消息。

规则：
- 长度不超过40字
- 保持角色语言风格一致
- 如果是对主播说的，使用自然的语气
- 如果是回应其他人，可以 @对方昵称
- 简洁自然，像一个真实的直播间观众"""

    def __init__(self, model_name: str = "moonshot-v1-8k"):
        self.model_name = model_name

    def build_prompt(
        self,
        name: str,
        persona: str,
        streamer_log: list[dict],
        my_danmaku: list[dict],
        other_danmaku: list[dict],
        relationships: dict[str, str],
        current_asr: str,
        follows: bool = True,
        relationship: str = "",
    ) -> str:
        lines = [
            "[角色档案]",
            f"昵称: {name}",
            f"人设: {persona}",
            f"关注主播: {'是' if follows else '否'}",
            f"与主播关系: {relationship or '普通观众'}",
            "",
            "[本场记忆 - 主播说过的话]",
        ]
        for entry in streamer_log[-10:]:
            lines.append(f"- {entry['text']}")
        if my_danmaku:
            lines.extend(["", "[本场记忆 - 我发过的弹幕]"])
            for d in my_danmaku[-5:]:
                lines.append(
                    f"- @{d.get('directed_to', '所有人')}: {d['text']}"
                )
        if relationships:
            lines.extend(["", "[与其他观众的关系]"])
            for rid, desc in relationships.items():
                lines.append(f"- {rid}: {desc}")
        lines.extend([
            "",
            "[当前主播说话]",
            current_asr,
            "",
            "以角色身份发一条符合当前状态的弹幕。"
            "只输出弹幕文本，不要加引号或额外说明。",
        ])
        return "\n".join(lines)

    def parse_danmaku(self, text: str) -> Optional[str]:
        text = text.strip().strip('"').strip("'").strip()
        if not text or len(text) < 2:
            return None
        return text
