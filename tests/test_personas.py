from backend.viewer.personas import ALL_PERSONAS, get_random_persona


def test_all_personas_loaded():
    assert len(ALL_PERSONAS) == 10


def test_persona_has_required_fields():
    for p in ALL_PERSONAS:
        assert "viewer_id" in p
        assert "name" in p
        assert "persona" in p
        assert "personality_type" in p
        assert p["personality_type"] in ("curious", "cheerful", "aggressive", "bystander")


def test_get_random_returns_dict():
    p = get_random_persona()
    assert "viewer_id" in p
    assert "name" in p
    assert "persona" in p
    assert "personality_type" in p


def test_get_random_is_random():
    results = {get_random_persona()["viewer_id"] for _ in range(20)}
    assert len(results) > 1
