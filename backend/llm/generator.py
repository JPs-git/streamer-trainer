from __future__ import annotations
from typing import Optional


class Generator:
    GENERATOR_SYSTEM_PROMPT = """你是在看直播的路人观众 主播是Vtuber在杂谈闲聊 随便发弹幕就行

发短点 几个字到十来个字就够了
不用标点符号
不知道说啥就发来了看看路过 不用硬凑内容
对主播说话直接说就行 不用加@
不要带自己名字 直接发弹幕内容 不要自己喊自己名字
可以冷漠 不用热情 刚进直播间什么都不懂很正常"""

    def __init__(self, model_name: str = "moonshot-v1-8k"):
        self.model_name = model_name

    def build_prompt(
        self,
        name: str,
        persona: str,
        room_chat_log: list[dict],
        my_danmaku: list[dict],
        relationships: dict[str, str],
        current_asr: str,
        follows: bool = True,
        relationship: str = "",
    ) -> str:
        lines = [
            "主播刚说：",
            current_asr,
            "",
            f"你叫{name} {persona}",
            f"{'关注了主播' if follows else '没关注主播'} 和主播关系是{relationship or '普通观众'}",
        ]
        if relationships:
            lines.extend(["", "和其他观众的关系："])
            for rid, desc in relationships.items():
                lines.append(f"- {rid}: {desc}")
        if room_chat_log:
            lines.extend(["", "直播间聊天记录："])
            for entry in room_chat_log[-20:]:
                speaker = entry.get("name", "")
                text = entry.get("text", "")
                lines.append(f"{speaker}说{text}")
        lines.extend([
            "",
            "针对主播刚才说的内容发一条弹幕 回应或者提问都行",
        ])
        return "\n".join(lines)

    def parse_danmaku(self, text: str) -> Optional[str]:
        text = text.strip().strip('"').strip("'").strip()
        text = self._strip_own_name(text)
        text = self._strip_at_streamer(text)
        if not text or len(text) < 2 or len(text) > 20:
            return None
        return text

    @staticmethod
    def _strip_own_name(text: str) -> str:
        import re
        return re.sub(r'^[^：:]{1,10}[：:]', '', text).strip()

    @staticmethod
    def _strip_at_streamer(text: str) -> str:
        for prefix in ("@streamer", "@主播", "@所有人"):
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip("：:，, ").strip()
        return text
