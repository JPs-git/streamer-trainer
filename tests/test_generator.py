import pytest
from backend.llm.generator import Generator


def test_generator_init():
    g = Generator(model_name="gpt-4o-mini")
    assert g.model_name == "gpt-4o-mini"


def test_build_prompt():
    g = Generator()
    prompt = g.build_prompt(
        name="小冰",
        persona="新来的好奇宝宝",
        streamer_log=[{"text": "今天来玩一个新游戏", "offset": 12}],
        my_danmaku=[],
        other_danmaku=[],
        relationships={},
        current_asr="这游戏操作很简单新手五分钟上手",
        follows=True,
        relationship="老粉",
    )
    assert "小冰" in prompt
    assert "好奇宝宝" in prompt
    assert "这游戏操作很简单" in prompt
    assert "今天来玩一个新游戏" in prompt


def test_build_prompt_with_memory():
    g = Generator()
    prompt = g.build_prompt(
        name="老王",
        persona="毒舌吐槽型",
        streamer_log=[{"text": "主播说这个游戏很难", "offset": 1}],
        my_danmaku=[{"text": "这就难了？", "offset": 2, "directed_to": "streamer"}],
        other_danmaku=[{"from_id": "小冰", "directed_to": "streamer",
                        "summary": "问了游戏难度"}],
        relationships={"小冰": "一起吐槽过"},
        current_asr="这个Boss我打了三次才过",
        follows=False,
        relationship="路人",
    )
    assert "老王" in prompt
    assert "这就难了" in prompt
    assert "一起吐槽过" in prompt


def test_parse_danmaku():
    g = Generator()
    assert g.parse_danmaku("这游戏好玩吗？") == "这游戏好玩吗？"


def test_parse_danmaku_cleans_quotes():
    g = Generator()
    assert g.parse_danmaku('"这游戏好玩吗？"') == "这游戏好玩吗？"
    assert g.parse_danmaku("'这游戏好玩吗？'") == "这游戏好玩吗？"


def test_parse_danmaku_empty():
    g = Generator()
    assert g.parse_danmaku("") is None


def test_parse_danmaku_too_short():
    g = Generator()
    assert g.parse_danmaku("啊") is None


def test_default_model_name():
    g = Generator()
    assert g.model_name == "moonshot-v1-8k"
