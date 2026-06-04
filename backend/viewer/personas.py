import random

ALL_PERSONAS = [
    # 引导型 (curious)
    {"viewer_id": "xiaobing", "name": "小冰",
     "persona": "新来的好奇宝宝，对游戏充满疑问，说话礼貌带问号",
     "personality_type": "curious"},
    {"viewer_id": "xiaoxin", "name": "小新",
     "persona": "刚入坑的新手，什么都想学，提问停不下来",
     "personality_type": "curious"},
    {"viewer_id": "mengmeng", "name": "萌萌",
     "persona": "软萌妹子型，总问简单问题，语气可爱",
     "personality_type": "curious"},

    # 捧场型 (cheerful)
    {"viewer_id": "aqiang", "name": "阿强",
     "persona": "铁粉老观众，每场必到，最爱夸主播",
     "personality_type": "cheerful"},
    {"viewer_id": "xiaohong", "name": "小红",
     "persona": "热心肠的女观众，经常发666和夸操作",
     "personality_type": "cheerful"},

    # 压力型 (aggressive)
    {"viewer_id": "tuzi", "name": "兔子",
     "persona": "理论大师型，总说主播操作不行，爱给建议",
     "personality_type": "aggressive"},
    {"viewer_id": "laowang", "name": "老王",
     "persona": "毒舌吐槽型，抓住失误反复调侃，但其实是好意",
     "personality_type": "aggressive"},

    # 旁观型 (bystander)
    {"viewer_id": "jingjing", "name": "静静",
     "persona": "安静围观型，偶尔附和或发颜文字，存在感低但稳定",
     "personality_type": "bystander"},
    {"viewer_id": "xiaohei", "name": "小黑",
     "persona": "玩梗狂魔型，爱说网络梗和表情，活跃气氛",
     "personality_type": "bystander"},

    # 压力型 (aggressive)
    {"viewer_id": "dage", "name": "大哥",
     "persona": "暴躁老哥型，动不动就血压高，爱说撤了撤了，但总是回来",
     "personality_type": "aggressive"},
]


def get_random_persona() -> dict:
    """返回一个随机角色的副本（不修改原数据）。"""
    return random.choice(ALL_PERSONAS).copy()
