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
- 简洁自然，像一个真实的直播间观众

参考以下弹幕风格特征来调整你的语言：

[语气与情绪基调]
轻松、幽默、直接，带有即时反应和情感表达，互动性强。

[高频句式]
- 感叹句：哇这细节！
- 疑问句：这是在加载吗？
- 猜测句：估计快完成了。
- 描述句：这操作有点秀。
- 评价句：牛啊这手速。
- 互动句：弹幕跟上。
- 预测句：感觉剧情要变。

[语言风格]
口语化、简洁、直接，常用感叹词和语气词增强效果，多用短句。

[内容类型分布]
- 感叹评价：约25%
- 观察描述：约30%
- 预测预判：约20%
- 互动提问：约15%
- 其他：约10%

[长度与节奏]
弹幕较短，通常一句话或几个词表达完整意思，节奏快速。

[常用感叹词/语气词]
哇、啊、哈、哎哟、牛啊、绝了、妙啊、真实、可以、继续、稳了

[核心风格]
以简洁直接的口语化表达，即时分享观众的情感和观点，增强直播互动性。"""

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
            "[角色档案]",
            f"昵称: {name}",
            f"人设: {persona}",
            f"关注主播: {'是' if follows else '否'}",
            f"与主播关系: {relationship or '普通观众'}",
        ]
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
        if room_chat_log:
            lines.extend(["", "[直播间聊天记录]"])
            for entry in room_chat_log[-20:]:
                speaker = entry.get("name", "")
                text = entry.get("text", "")
                lines.append(f"[{speaker}] {text}")
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
