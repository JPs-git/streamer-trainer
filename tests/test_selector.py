import pytest
from backend.llm.selector import Selector


def test_selector_initialization():
    s = Selector(model_name="gpt-4o-mini")
    assert s.model_name == "gpt-4o-mini"


def test_build_prompt():
    s = Selector()
    prompt = s.build_prompt(
        asr_text="这游戏操作很简单新手五分钟上手",
        viewer_states=[
            {"id": "xiaobing", "name": "小冰", "personality": "curious",
             "state": "active", "summary": "刚进来2分钟，还没发过言"},
            {"id": "laowang", "name": "老王", "personality": "aggressive",
             "state": "active", "summary": "看了15分钟，上次吐槽了主播"},
        ],
    )
    assert "xiaobing" in prompt
    assert "老王" in prompt
    assert "这游戏操作很简单" in prompt


def test_parse_response():
    s = Selector()
    result = s.parse_response('''[
        {"id": "xiaobing", "intent": "作为新人询问是否真的简单"},
        {"id": "laowang", "intent": "反驳五分钟上手的说法"}
    ]''')
    assert len(result) == 2
    assert result[0]["id"] == "xiaobing"
    assert result[1]["intent"] == "反驳五分钟上手的说法"


def test_parse_response_fallback_on_invalid():
    s = Selector()
    result = s.parse_response("抱歉我无法处理这个请求")
    assert result == []


def test_parse_response_fallback_on_empty():
    s = Selector()
    result = s.parse_response("[]")
    assert result == []


def test_default_model_name():
    s = Selector()
    assert s.model_name == "gpt-4o-mini"
