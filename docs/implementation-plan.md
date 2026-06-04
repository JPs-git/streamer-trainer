# 主播培训弹幕系统 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建一个 Python 后端服务 + H5 前端的弹幕生成系统，通过 OBS Browser Source 展示虚拟观众弹幕。

**Architecture:** FastAPI 后端通过 WebSocket 接收主播音频流，Whisper 本地 ASR 转文本，两阶段 LLM 调用（选择器→生成器）决定哪个虚拟角色说什么，结果通过 WS 推送到 H5 前端。

**Tech Stack:** Python 3.11+, FastAPI, WebSocket, faster-whisper, OpenAI/Anthropic SDK, pytest, HTML+CSS+JS

---

## 文件结构

```
streamer-trainer/
├── backend/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口, WS 路由注册
│   ├── config.py                  # 配置加载
│   ├── asr.py                     # Whisper ASR 封装
│   ├── viewer/
│   │   ├── __init__.py
│   │   ├── models.py              # VirtualViewer, ViewerMemory 数据模型
│   │   ├── manager.py             # 虚拟观众管理器 (状态机+调度)
│   │   └── personas.py            # 预定义角色库
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py              # LLM API 客户端抽象
│   │   ├── selector.py            # 选择器 (Stage 1)
│   │   └── generator.py           # 生成器 (Stage 2)
│   └── requirements.txt
├── frontend/
│   ├── index.html                 # OBS Browser Source 聊天窗口
│   ├── style.css
│   └── script.js
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_manager.py
│   ├── test_selector.py
│   └── test_generator.py
└── config.yaml
```

---

### Task 1: 项目脚手架 + 配置 + 依赖

**Files:**
- Create: `config.yaml`
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/requirements.txt`
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "streamer-trainer"
version = "0.1.0"
description = "基于主播语音的实时弹幕生成系统"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "websockets>=12.0",
    "faster-whisper>=1.0.0",
    "httpx>=0.27.0",
    "openai>=1.12.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23.0",
]
```

- [ ] **Step 2: 创建 config.yaml**

```yaml
server:
  host: "127.0.0.1"
  port: 8765

asr:
  model_size: "base"         # tiny/base/small/medium/large
  device: "cpu"              # cpu or cuda
  compute_type: "int8"       # int8/float16/float32

llm:
  provider: "openai"         # openai or anthropic
  api_key_env: "LLM_API_KEY"
  model: "gpt-4o-mini"       # 选择器用轻量模型可单独配置
  selector_model: "gpt-4o-mini"
  temperature: 0.8
  max_tokens: 150

viewer:
  min_active: 3
  max_active: 8
  entry_interval_sec: 180     # 每3分钟尝试轮换
  cooldown_sec: 300           # 离场后5分钟可重新入场
  memory_max_streamer_log: 50 # 超过此数做摘要压缩
```

- [ ] **Step 3: 创建 backend/__init__.py 和 tests/__init__.py**

- [ ] **Step 4: 创建 backend/config.py**

```python
import os
import yaml
from pathlib import Path


class Config:
    def __init__(self, path: str = "config.yaml"):
        with open(path) as f:
            raw = yaml.safe_load(f)

        s = raw["server"]
        self.host = s["host"]
        self.port = s["port"]

        a = raw["asr"]
        self.asr_model_size = a["model_size"]
        self.asr_device = a["device"]
        self.asr_compute_type = a["compute_type"]

        l = raw["llm"]
        self.llm_provider = l["provider"]
        self.llm_api_key = os.environ.get(l["api_key_env"], "")
        self.llm_model = l["model"]
        self.llm_selector_model = l.get("selector_model", l["model"])
        self.llm_temperature = l["temperature"]
        self.llm_max_tokens = l["max_tokens"]

        v = raw["viewer"]
        self.viewer_min_active = v["min_active"]
        self.viewer_max_active = v["max_active"]
        self.viewer_entry_interval_sec = v["entry_interval_sec"]
        self.viewer_cooldown_sec = v["cooldown_sec"]
        self.viewer_memory_max_streamer_log = v["memory_max_streamer_log"]


config = Config()
```

- [ ] **Step 5: 创建 __init__.py 文件**

backend/__init__.py 和 tests/__init__.py 均为空文件。

- [ ] **Step 6: 同步依赖**

Run: `uv sync`
Expected: 所有依赖安装成功，虚拟环境创建完成

---

### Task 2: 核心数据模型

**Files:**
- Create: `backend/viewer/__init__.py`
- Create: `backend/viewer/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 创建 backend/viewer/__init__.py**

空文件。

- [ ] **Step 2: 写测试**

```python
from backend.viewer.models import VirtualViewer, ViewerMemory


def test_viewer_creation():
    v = VirtualViewer(
        viewer_id="test_01",
        name="小冰",
        persona="新来的好奇宝宝",
        personality_type="curious",
    )
    assert v.viewer_id == "test_01"
    assert v.name == "小冰"
    assert v.state == "inactive"
    assert v.interaction_count == 0


def test_memory_append_streamer_log():
    mem = ViewerMemory()
    mem.add_streamer_log("今天来玩一个新游戏", 12)
    assert len(mem.streamer_log) == 1
    assert mem.streamer_log[0]["text"] == "今天来玩一个新游戏"


def test_memory_append_danmaku():
    mem = ViewerMemory()
    mem.add_my_danmaku("这游戏叫什么", 14, "streamer")
    assert len(mem.my_danmaku) == 1
    assert mem.my_danmaku[0]["directed_to"] == "streamer"


def test_memory_append_other_danmaku():
    mem = ViewerMemory()
    mem.add_other_danmaku("aqiang", "streamer", "夸主播操作好")
    assert len(mem.other_danmaku) == 1
    assert mem.other_danmaku[0]["from_id"] == "aqiang"


def test_relationship_update():
    mem = ViewerMemory()
    mem.update_relationship("aqiang", "友善，他帮过我")
    assert mem.relationships["aqiang"] == "友善，他帮过我"
    mem.update_relationship("aqiang", "他刚才反驳我，不太喜欢")
    assert mem.relationships["aqiang"] == "他刚才反驳我，不太喜欢"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_models.py -v`
Expected: 失败 (ModuleNotFoundError)

- [ ] **Step 4: 创建 models.py**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ViewerMemory:
    streamer_log: list[dict] = field(default_factory=list)
    my_danmaku: list[dict] = field(default_factory=list)
    other_danmaku: list[dict] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)

    def add_streamer_log(self, text: str, offset: int):
        self.streamer_log.append({"text": text, "offset": offset})

    def add_my_danmaku(self, text: str, offset: int, directed_to: str):
        self.my_danmaku.append({
            "text": text, "offset": offset, "directed_to": directed_to
        })

    def add_other_danmaku(self, from_id: str, to: str, summary: str):
        self.other_danmaku.append({
            "from_id": from_id, "to": to, "summary": summary
        })

    def update_relationship(self, viewer_id: str, description: str):
        self.relationships[viewer_id] = description


@dataclass
class VirtualViewer:
    viewer_id: str
    name: str
    persona: str
    personality_type: str  # curious / cheerful / aggressive / bystander
    state: str = "inactive"
    memory: ViewerMemory = field(default_factory=ViewerMemory)
    entry_time: Optional[int] = None
    last_active: Optional[int] = None
    interaction_count: int = 0
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_models.py -v`
Expected: 5 passed

- [ ] **Step 6: 提交**

---

### Task 3: 预定义角色库

**Files:**
- Create: `backend/viewer/personas.py`

- [ ] **Step 1: 写测试**

```python
from backend.viewer.personas import ALL_PERSONAS, get_random_persona


def test_all_personas_loaded():
    assert len(ALL_PERSONAS) >= 8


def test_persona_has_required_fields():
    for p in ALL_PERSONAS:
        assert "viewer_id" in p
        assert "name" in p
        assert "persona" in p
        assert "personality_type" in p


def test_get_random_returns_dict():
    p = get_random_persona()
    assert "viewer_id" in p
    assert "name" in p
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 创建 personas.py**

```python
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
]


def get_random_persona() -> dict:
    return random.choice(ALL_PERSONAS).copy()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_personas.py -v` (需要先创建 test_personas.py 或用已有的 test_models.py 引用)

---

### Task 4: 虚拟观众管理器（状态机 + 调度）

**Files:**
- Create: `backend/viewer/manager.py`
- Create: `tests/test_manager.py`

- [ ] **Step 1: 写测试**

```python
import pytest
from backend.viewer.models import VirtualViewer
from backend.viewer.manager import ViewerManager


@pytest.fixture
def manager():
    return ViewerManager(max_active=4, min_active=2)


def test_initial_active_count(manager):
    """初始时应该有 min_active 个活跃观众"""
    assert len(manager.get_active_viewers()) == 2


def test_get_viewer_by_id(manager):
    v = manager.get_viewer("xiaobing")
    assert v is not None
    assert v.viewer_id == "xiaobing"


def test_get_nonexistent_viewer(manager):
    assert manager.get_viewer("nonexistent") is None


def test_viewer_state_transitions(manager):
    """验证状态机流转: inactive → active → cooldown"""
    v = manager.get_viewer("xiaobing")
    assert v.state == "active"

    manager.deactivate_viewer("xiaobing")
    assert v.state == "cooldown"

    manager.activate_viewer("xiaobing")
    assert v.state == "active"
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 创建 manager.py**

```python
from __future__ import annotations
import random
import time
from backend.viewer.models import VirtualViewer
from backend.viewer.personas import ALL_PERSONAS


class ViewerManager:
    def __init__(self, max_active: int = 8, min_active: int = 3, cooldown_sec: int = 300):
        self.max_active = max_active
        self.min_active = min_active
        self.cooldown_sec = cooldown_sec
        self._all_viewers: dict[str, VirtualViewer] = {}
        self._active_ids: set[str] = set()
        self._cooldown_ids: set[str] = set()
        self._init_viewers()

    def _init_viewers(self):
        for p in ALL_PERSONAS:
            v = VirtualViewer(
                viewer_id=p["viewer_id"],
                name=p["name"],
                persona=p["persona"],
                personality_type=p["personality_type"],
            )
            self._all_viewers[v.viewer_id] = v
        self._fill_to_min()

    def _fill_to_min(self):
        available = [vid for vid, v in self._all_viewers.items()
                     if v.state == "inactive"]
        random.shuffle(available)
        to_activate = available[:self.min_active - len(self._active_ids)]
        for vid in to_activate:
            self.activate_viewer(vid)

    def activate_viewer(self, viewer_id: str):
        v = self._all_viewers.get(viewer_id)
        if v and v.state in ("inactive", "cooldown"):
            v.state = "active"
            v.entry_time = int(time.time())
            v.last_active = int(time.time())
            self._active_ids.add(viewer_id)
            self._cooldown_ids.discard(viewer_id)

    def deactivate_viewer(self, viewer_id: str):
        v = self._all_viewers.get(viewer_id)
        if v and v.state == "active":
            v.state = "cooldown"
            self._active_ids.discard(viewer_id)
            self._cooldown_ids.add(viewer_id)

    def get_viewer(self, viewer_id: str) -> VirtualViewer | None:
        return self._all_viewers.get(viewer_id)

    def get_active_viewers(self) -> list[VirtualViewer]:
        return [self._all_viewers[vid] for vid in self._active_ids
                if vid in self._all_viewers]

    def tick(self):
        """定时调用: 处理轮换调度"""
        now = int(time.time())
        active = self.get_active_viewers()
        if len(active) >= self.max_active:
            oldest = min(active, key=lambda v: v.entry_time or 0)
            self.deactivate_viewer(oldest.viewer_id)
        if len(active) < self.min_active:
            self._fill_to_min()

        cooldown_expired = [
            vid for vid in self._cooldown_ids
            if now - (self._all_viewers[vid].entry_time or 0) > self.cooldown_sec
        ]
        for vid in cooldown_expired:
            self._all_viewers[vid].state = "inactive"
        self._cooldown_ids -= set(cooldown_expired)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_manager.py -v`
Expected: 4 passed

---

### Task 5: LLM API 客户端抽象

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/client.py`

- [ ] **Step 1: 写测试**

```python
import pytest
from backend.llm.client import LLMClient


@pytest.mark.asyncio
async def test_client_requires_api_key():
    with pytest.raises(ValueError, match="API key"):
        LLMClient(provider="openai", api_key="")


@pytest.mark.asyncio
async def test_client_initialization():
    client = LLMClient(
        provider="openai",
        api_key="sk-test",
        model="gpt-4o-mini",
        temperature=0.8,
        max_tokens=150,
    )
    assert client.provider == "openai"
    assert client.model == "gpt-4o-mini"
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 创建 backend/llm/__init__.py**

空文件。

- [ ] **Step 4: 创建 client.py**

```python
from __future__ import annotations
from typing import Optional


class LLMClient:
    def __init__(
        self,
        provider: str = "openai",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        selector_model: Optional[str] = None,
        temperature: float = 0.8,
        max_tokens: int = 150,
    ):
        if not api_key:
            raise ValueError("API key is required")
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.selector_model = selector_model or model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = self._build_client()

    def _build_client(self):
        if self.provider == "openai":
            from openai import AsyncOpenAI
            return AsyncOpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=self.api_key)
        raise ValueError(f"Unsupported provider: {self.provider}")

    async def chat(self, system: str, user: str, model: Optional[str] = None) -> str:
        if self.provider == "openai":
            resp = await self._client.chat.completions.create(
                model=model or self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content or ""
        elif self.provider == "anthropic":
            resp = await self._client.messages.create(
                model=model or self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text if resp.content else ""
        raise ValueError(f"Unsupported provider: {self.provider}")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_client.py -v`
Expected: 通过

---

### Task 6: 选择器 (Stage 1)

**Files:**
- Create: `backend/llm/selector.py`
- Create: `tests/test_selector.py`

- [ ] **Step 1: 写测试**

```python
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
    assert "laowang" in prompt
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
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 创建 selector.py**

```python
import json
import re
from typing import Optional


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


class Selector:
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
```

- [ ] **Step 4: 运行测试确认通过**

---

### Task 7: 生成器 (Stage 2)

**Files:**
- Create: `backend/llm/generator.py`
- Create: `tests/test_generator.py`

- [ ] **Step 1: 写测试**

```python
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
        personality_type="curious",
        streamer_log=[{"text": "今天来玩一个新游戏", "offset": 12}],
        my_danmaku=[],
        other_danmaku=[],
        relationships={},
        current_asr="这游戏操作很简单新手五分钟上手",
    )
    assert "小冰" in prompt
    assert "好奇宝宝" in prompt
    assert "这游戏操作很简单" in prompt


def test_parse_danmaku():
    g = Generator()
    assert g.parse_danmaku("这游戏好玩吗？") == "这游戏好玩吗？"


def test_parse_danmaku_cleans_quotes():
    g = Generator()
    assert g.parse_danmaku('"这游戏好玩吗？"') == "这游戏好玩吗？"


def test_parse_danmaku_short_response():
    g = Generator()
    result = g.parse_danmaku("")
    assert result is None
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 创建 generator.py**

```python
from __future__ import annotations
from typing import Optional


GENERATOR_SYSTEM_PROMPT = """你是一个直播间的虚拟观众。根据你的角色设定、记忆和当前主播说的话，
生成一条符合角色性格的弹幕消息。

规则：
- 长度不超过40字
- 保持角色语言风格一致
- 如果是对主播说的，使用自然的语气
- 如果是回应其他人，可以 @对方昵称
- 简洁自然，像一个真实的直播间观众"""


class Generator:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model_name = model_name

    def build_prompt(
        self,
        name: str,
        persona: str,
        personality_type: str,
        streamer_log: list[dict],
        my_danmaku: list[dict],
        other_danmaku: list[dict],
        relationships: dict[str, str],
        current_asr: str,
    ) -> str:
        lines = [
            f"[角色档案]",
            f"昵称: {name}",
            f"人设: {persona}",
            f"类型: {personality_type}",
            "",
            "[本场记忆 - 主播说过的话]",
        ]
        for entry in streamer_log[-10:]:
            lines.append(f"- {entry['text']}")
        if my_danmaku:
            lines.extend(["", "[本场记忆 - 我发过的弹幕]"])
            for d in my_danmaku[-5:]:
                lines.append(f"- @{d.get('directed_to', '所有人')}: {d['text']}")
        if relationships:
            lines.extend(["", "[与其他观众的关系]"])
            for rid, desc in relationships.items():
                lines.append(f"- {rid}: {desc}")
        lines.extend([
            "",
            "[当前主播说话]",
            current_asr,
            "",
            "以角色身份发一条符合当前状态的弹幕。只输出弹幕文本，不要加引号或额外说明。",
        ])
        return "\n".join(lines)

    def parse_danmaku(self, text: str) -> Optional[str]:
        text = text.strip().strip('"').strip("'").strip()
        if not text or len(text) < 2:
            return None
        return text
```

- [ ] **Step 4: 运行测试确认通过**

---

### Task 8: 主服务入口 + WS 路由

**Files:**
- Create: `backend/asr.py`
- Create: `backend/main.py`

- [ ] **Step 1: 创建 asr.py**

```python
from __future__ import annotations
from faster_whisper import WhisperModel


class ASREngine:
    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8"):
        self.model = WhisperModel(model_size, device=device,
                                  compute_type=compute_type)

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        import numpy as np
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(
            np.float32) / 32768.0
        segments, _ = self.model.transcribe(audio_array,
                                            beam_size=1, language="zh")
        return " ".join(seg.text for seg in segments)
```

- [ ] **Step 2: 创建 main.py**

```python
from __future__ import annotations
import asyncio
import json
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.config import config
from backend.asr import ASREngine
from backend.viewer.manager import ViewerManager
from backend.llm.client import LLMClient
from backend.llm.selector import Selector
from backend.llm.generator import Generator


class StreamerTrainerApp:
    def __init__(self):
        self.asr = ASREngine(
            model_size=config.asr_model_size,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
        )
        self.llm = LLMClient(
            provider=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            selector_model=config.llm_selector_model,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens,
        )
        self.selector = Selector(model_name=config.llm_selector_model)
        self.generator = Generator(model_name=config.llm_model)
        self.viewer_manager = ViewerManager(
            max_active=config.viewer_max_active,
            min_active=config.viewer_min_active,
            cooldown_sec=config.viewer_cooldown_sec,
        )
        self.danmaku_clients: set[WebSocket] = set()

    async def broadcast_danmaku(self, message: dict):
        dead = set()
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.danmaku_clients -= dead


app_state = StreamerTrainerApp()
app = FastAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()


async def _scheduler_loop():
    while True:
        app_state.viewer_manager.tick()
        await asyncio.sleep(30)


@app.websocket("/audio")
async def audio_endpoint(ws: WebSocket):
    await ws.accept()
    audio_buffer = bytearray()
    try:
        while True:
            data = await ws.receive_bytes()
            audio_buffer.extend(data)
            if len(audio_buffer) >= 32000:
                text = app_state.asr.transcribe(bytes(audio_buffer))
                audio_buffer.clear()
                if text.strip():
                    await _process_asr_result(text)
    except WebSocketDisconnect:
        pass


@app.websocket("/danmaku")
async def danmaku_endpoint(ws: WebSocket):
    await ws.accept()
    app_state.danmaku_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        app_state.danmaku_clients.discard(ws)


@app.websocket("/control")
async def control_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass


async def _process_asr_result(text: str):
    timestamp = int(time.time())
    active = app_state.viewer_manager.get_active_viewers()

    for v in active:
        v.memory.add_streamer_log(text, timestamp)

    viewer_states = [
        {
            "id": v.viewer_id,
            "name": v.name,
            "personality": v.personality_type,
            "state": v.state,
            "summary": _build_viewer_summary(v),
        }
        for v in active
    ]

    selector_prompt = app_state.selector.build_prompt(text, viewer_states)
    selector_raw = await app_state.llm.chat(
        system=Selector.SELECTOR_SYSTEM_PROMPT,
        user=selector_prompt,
        model=app_state.llm.selector_model,
    )
    selected = app_state.selector.parse_response(selector_raw)

    if not selected:
        return

    tasks = []
    for sel in selected:
        v = app_state.viewer_manager.get_viewer(sel["id"])
        if not v or v.state != "active":
            continue
        tasks.append(_generate_for_viewer(v, text, sel.get("intent", "")))

    results = await asyncio.gather(*tasks)
    for r in results:
        if r:
            await app_state.broadcast_danmaku(r)


async def _generate_for_viewer(
    v, current_asr: str, intent: str
) -> dict | None:
    prompt = app_state.generator.build_prompt(
        name=v.name,
        persona=v.persona,
        personality_type=v.personality_type,
        streamer_log=v.memory.streamer_log,
        my_danmaku=v.memory.my_danmaku,
        other_danmaku=v.memory.other_danmaku,
        relationships=v.memory.relationships,
        current_asr=current_asr,
    )
    # 追加意图引导
    prompt += f"\n\n[发言意图]\n{intent}"

    raw = await app_state.llm.chat(
        system=Generator.GENERATOR_SYSTEM_PROMPT,
        user=prompt,
    )
    text = app_state.generator.parse_danmaku(raw)
    if not text:
        return None

    v.memory.add_my_danmaku(text, int(time.time()), "streamer")
    v.last_active = int(time.time())
    v.interaction_count += 1

    effect = "highlight" if v.personality_type == "aggressive" else "normal"
    return {
        "type": "danmaku",
        "id": v.viewer_id,
        "name": v.name,
        "text": text,
        "personality": v.personality_type,
        "effect": effect,
    }


def _build_viewer_summary(v) -> str:
    parts = []
    if v.entry_time:
        elapsed = (int(time.time()) - v.entry_time) // 60
        parts.append(f"看了{elapsed}分钟")
    if v.interaction_count > 0:
        parts.append(f"发过{v.interaction_count}条弹幕")
    if v.memory.my_danmaku:
        last = v.memory.my_danmaku[-1]["text"][:20]
        parts.append(f"上次说: {last}")
    return ", ".join(parts) if parts else "还没发过言"


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config.host,
        port=config.port,
        reload=False,
    )
```

---

### Task 9: H5 前端

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/style.css`
- Create: `frontend/script.js`

- [ ] **Step 1: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="style.css">
  <title>直播间聊天</title>
</head>
<body>
  <div id="chat-container">
    <div id="chat-header">
      <span>直播间聊天</span>
      <span id="viewer-count">0人在线</span>
    </div>
    <div id="chat-messages"></div>
  </div>
  <script src="script.js"></script>
</body>
</html>
```

- [ ] **Step 2: 创建 style.css**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, "Microsoft YaHei", sans-serif;
  background: transparent;
  overflow: hidden;
  width: 360px;
  height: 600px;
}

#chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 8px;
  overflow: hidden;
}

#chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 14px;
  flex-shrink: 0;
}

#viewer-count {
  font-size: 12px;
  color: #aaa;
}

#chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
}

.msg {
  margin-bottom: 6px;
  animation: fadeIn 0.3s ease;
  line-height: 1.5;
  font-size: 13px;
  word-break: break-all;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.name { font-weight: 600; margin-right: 4px; }

.name.curious { color: #4FC3F7; }
.name.cheerful { color: #81C784; }
.name.aggressive { color: #FF8A65; }
.name.bystander { color: #B0BEC5; }

.text { color: #e0e0e0; }

.msg.system { color: #888; font-size: 12px; text-align: center; }
.msg.system.enter { color: #81C784; }
.msg.system.leave { color: #FF8A65; }

.msg.highlight {
  background: rgba(255, 138, 101, 0.12);
  border-left: 3px solid #FF8A65;
  padding: 2px 8px;
  border-radius: 4px;
}

#chat-messages::-webkit-scrollbar { width: 0; }
```

- [ ] **Step 3: 创建 script.js**

```javascript
const wsUrl = `ws://${location.host.replace(/:\d+$/, ':8765')}/danmaku`;
let ws = null;
let reconnectTimer = null;

function connect() {
  ws = new WebSocket(wsUrl);
  ws.onopen = () => {
    console.log('Connected');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  };
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      handleMessage(data);
    } catch (err) { console.error(err); }
  };
  ws.onclose = () => {
    reconnectTimer = setTimeout(connect, 3000);
  };
}

function handleMessage(data) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');

  if (data.type === 'danmaku') {
    div.className = `msg ${data.effect === 'highlight' ? 'highlight' : ''}`;
    const nameSpan = document.createElement('span');
    nameSpan.className = `name ${data.personality || 'bystander'}`;
    nameSpan.textContent = data.name + ': ';
    const textSpan = document.createElement('span');
    textSpan.className = 'text';
    textSpan.textContent = data.text;
    div.appendChild(nameSpan);
    div.appendChild(textSpan);
  } else if (data.type === 'system') {
    div.className = `msg system ${data.action}`;
    if (data.action === 'enter') {
      div.textContent = `🟢 ${data.name} 进入了直播间`;
    } else if (data.action === 'leave') {
      div.textContent = `🔴 ${data.name} 离开了直播间`;
    }
  }

  if (div.textContent || div.childNodes.length) {
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  // 限制消息数量防止内存溢出
  while (container.children.length > 200) {
    container.removeChild(container.firstChild);
  }
}

connect();
```

---

### Task 10: 整合验证

- [ ] **Step 1: 启动服务**

Run: `LLM_API_KEY=sk-xxx python -m backend.main`

- [ ] **Step 2: H5 前端可用性检查**

在浏览器打开 `http://127.0.0.1:8765/frontend/index.html`（或通过 OBS Browser Source 加载），确认界面正常渲染。

- [ ] **Step 3: 端到端流程检查**

1. 启动后端
2. OBS 音频插件连接到 `ws://127.0.0.1:8765/audio` 并发送音频
3. 浏览器打开前端页面，连接 `ws://127.0.0.1:8765/danmaku`
4. 观察弹幕是否正常生成和展示
