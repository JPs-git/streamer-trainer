import json
import re


class Selector:
    SELECTOR_SYSTEM_PROMPT = """你是一个直播弹幕选角导演。你的职责是：
1. 根据主播当前说的话，从活跃观众中选择2-3位最应该发言的人
2. 简要说明每个人应该说什么方向
3. 返回 JSON 数组

输出格式 JSON:
[{"id": "角色ID", "intent": "一句话说明发言意图"}]

重要规则：
- 优先选择状态与当前话题最相关的观众
- 压力型观众在主播犯错或说大话时优先选择
- 引导型观众在新话题开始时优先选择
- 不要让同一个观众连续两次发言
- 如果没有人适合发言，返回空数组 []"""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    def build_prompt(self, asr_text: str, viewer_states: list[dict]) -> str:
        lines = ["当前主播说: " + asr_text, "", "活跃观众状态:"]
        for vs in viewer_states:
            lines.append(
                f"- {vs['name']}({vs['id']}) "
                f"[{vs['personality']}] {vs.get('summary', '')}"
            )
        lines.extend([
            "",
            "请选择2-3位最合适的观众发言，返回JSON数组。"
            "不需要发言时返回 []。",
        ])
        return "\n".join(lines)

    def parse_response(self, text: str) -> list[dict]:
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
