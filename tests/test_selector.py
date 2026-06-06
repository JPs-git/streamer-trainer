from backend.llm.selector import Selector


def test_parse_pulse_response():
    sel = Selector()
    raw = '''[
        {"id": "xiaobing", "engagement_delta": 5, "speak": "ask_question", "leave": false},
        {"id": "tuzi", "engagement_delta": -3, "speak": null, "leave": false}
    ]'''
    result = sel.parse_pulse_response(raw)
    assert len(result) == 2
    assert result[0]["id"] == "xiaobing"
    assert result[0]["speak"] == "ask_question"
    assert result[0]["leave"] is False


def test_parse_pulse_response_empty():
    sel = Selector()
    result = sel.parse_pulse_response("[]")
    assert result == []


def test_parse_pulse_response_invalid():
    sel = Selector()
    result = sel.parse_pulse_response("not json")
    assert result == []


def test_build_pulse_prompt_with_speech():
    sel = Selector()
    prompt = sel.build_pulse_prompt("今天玩这个", 0, [
        {"id": "x", "name": "X", "personality": "curious", "engagement": 80, "interaction_count": 2},
    ])
    assert "今天玩这个" in prompt
    assert "沉默" not in prompt


def test_build_pulse_prompt_with_silence():
    sel = Selector()
    prompt = sel.build_pulse_prompt("", 120, [
        {"id": "x", "name": "X", "personality": "curious", "engagement": 50, "interaction_count": 0},
    ])
    assert "沉默时长" in prompt
    assert "120 秒" in prompt
