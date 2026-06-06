# Agent Pipeline — 虚拟观众调度系统

## 动机

将 Selector + Generator + ViewerManager 的固定模板逻辑替换为 Agent（kimi-k2.6）驱动的动态决策系统，每个虚拟观众由 Agent 在进房时生成，不再依赖预定义角色。

## 架构

每 tick（15s）一次 LLM 调用：

```
Python 收集状态 → Agent (kimi-k2.6 + function calling) → Python 执行决策
                                                             ├─ spawn_viewer → 创建对象，broadcast enter
                                                             ├─ adjust_engagement → 改数值
                                                             └─ schedule_speak → 调 moonshot-v1-8k 生文本，broadcast danmaku
                                                             └─ remove_viewer → broadcast leave，删除
```

## Agent 工具

| Tool | 参数 | 用途 |
|------|------|------|
| `spawn_viewer` | name, persona, follows, relationship, engagement | 创建观众进房 |
| `adjust_engagement` | viewer_id, delta | 修正 engagement |
| `schedule_speak` | viewer_id, intent | 标记要发言 |
| `remove_viewer` | viewer_id | 离场删除 |

## Viewer 模型变更

```python
@dataclass
class VirtualViewer:
    viewer_id: str
    name: str
    persona: str
    follows: bool = True
    relationship: str = ""       # "老粉" / "路人" / "新关注"
    personality_type: str = ""   # 不再使用，保留为空串
    ...
```

## 数据流

1. Python 侧执行基础 decay（`random.uniform(1,5) ± random`）
2. Python 将活跃观众状态、主播时间线摘要、房间统计传入 Agent
3. Agent 返回 0 个或多个工具调用
4. Python 按顺序执行：spawn → adjust → schedule_speak（并行 gather 生成文本）→ remove
5. Generator (moonshot-v1-8k) 为每个 schedule_speak 生成实际弹幕文本

## 移除的组件

- `backend/viewer/personas.py` — 不再需要固定角色
- `backend/llm/selector.py` — 被 Agent 替代
- `ViewerManager._init_viewers()` — 不再预创建观众
- `ViewerManager.reset_cooldown_viewers()` — 离场即删，无冷却重置
- `ViewerScheduler._try_entry()` / `_fill_to_min()` / `_enter_one()` — 由 Agent 的 spawn_viewer 替代

## 模型

- **Agent**: kimi-k2.6（决策）
- **Generator**: moonshot-v1-8k（弹幕文本生成）
