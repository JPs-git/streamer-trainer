from backend.viewer.models import VirtualViewer, ViewerMemory


def test_viewer_creation():
    v = VirtualViewer(
        viewer_id="test_01",
        name="小冰",
        persona="新来的好奇宝宝",
        follows=True,
        relationship="老粉",
    )
    assert v.viewer_id == "test_01"
    assert v.name == "小冰"
    assert v.follows is True
    assert v.relationship == "老粉"
    assert v.state == "inactive"
    assert v.interaction_count == 0


def test_memory_append_danmaku():
    mem = ViewerMemory()
    mem.add_my_danmaku("这游戏叫什么", 14, "streamer")
    assert len(mem.my_danmaku) == 1
    assert mem.my_danmaku[0]["directed_to"] == "streamer"


def test_relationship_update():
    mem = ViewerMemory()
    mem.update_relationship("aqiang", "友善，他帮过我")
    assert mem.relationships["aqiang"] == "友善，他帮过我"
    mem.update_relationship("aqiang", "他刚才反驳我，不太喜欢")
    assert mem.relationships["aqiang"] == "他刚才反驳我，不太喜欢"
