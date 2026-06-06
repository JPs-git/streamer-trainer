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
