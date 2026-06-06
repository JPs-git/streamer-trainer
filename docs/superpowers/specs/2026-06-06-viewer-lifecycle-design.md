# 虚拟观众生命周期管理 — 设计文档

## 概述

重新设计虚拟观众生命周期：从"ASR 触发被动响应"变为"调度器主动驱动"。
每个观众拥有独立的 engagement 模型和随机化行为，离场由 LLM 综合观众偏好和直播内容判定。

## 当前问题

- viewer lifecycle driven by ASR pipeline — no behavior when streamer is silent
- Viewer rotation purely based on count (min/max active), no content awareness
- No enter/leave events broadcast to frontend
- `entry_interval_sec` defined in config but never used
- No session duration or engagement tracking per viewer

## 新架构

```
ASR Pipeline:
  音频 → 识别文字 → 追加到 streamer_timeline
  (不再触发生成弹幕)

ViewerScheduler (独立 loop, ~15s tick):
  1. Selector batch evaluation → engagement delta + speak intent + leave decision
  2. Generator (per speaking viewer, with random delay)
  3. Leave handling → broadcast leave event
  4. Entry handling → broadcast enter event
  5. Cooldown → reset to inactive
```

### 组件

| 组件 | 职责 |
|------|------|
| `ViewerScheduler` | 独立 loop，每 tick 驱动全流程 |
| `VirtualViewer.engagement` | 数值模型 (0-100)，基础衰减+随机波动，LLM 修正 |
| `Selector` (改造) | 批量评估：每个观众的 engagement 变化、发言意图、是否离场 |
| `Generator` (不变) | 为特定观众生成弹幕文字 |
| `ASR Pipeline` | 只做语音识别，追加到 timeline，不再触发生成 |

## Engagement 模型

### 初始化
```python
engagement = random.uniform(60, 100)
```

### 每日志衰减（规则层，不走 LLM）
```python
decay_base = {
    "curious": 4,    # 没新东西很快就腻
    "aggressive": 3, # 中等，但有槽点会回血
    "cheerful": 2,   # 铁粉耐性好
    "bystander": 1.5 # 挂机党不在意
}

noise = random.uniform(-3, 3)
engagement -= (decay_base * random.uniform(0.5, 1.5) + noise)
engagement = max(0, min(100, engagement))
```

### LLM 修正（通过 Selector 合并评估）
每次 tick，Selector 基于主播最新发言和每个观众 persona 输出 `engagement_delta`：
- 内容对口 → 正值 (e.g., +5 ~ +20)
- 内容不对味 → 负值 (e.g., -5 ~ -15)
- 沉默太久 → 持续负值

最终: `engagement = clamp(engagement + delta, 0, 100)`

## Selector 改造

### 输入
- Streamer recent speech (最近 N 条，或沉默时长)
- 每个 active 观众: name, persona, personality_type, current engagement, interaction_count, last_action_summary

### 输出 JSON (per viewer)
```json
{
  "engagement_delta": -5,
  "speak": null | "criticize_play",
  "leave": false
}
```

- `engagement_delta`: LLM 根据内容喜好判断的修正值
- `speak`: 非空字符串表示发言意图，Generator 随后生成实际文字。实际广播时机由调度器加随机延迟 0-6s
- `leave`: true 表示离场。触发 deactivate + 广播

### 离场触发条件
当 engagement < 20 时，Selector 评估该观众会：
  - 抱怨一句然后离场 (speak + leave)
  - 直接离场 (leave only)
  - 再观望一下 (leave=false)

## 调度时序

```python
TICK_INTERVAL = 15  # seconds
```

每 tick:
1. 检查 `streamer_timeline` 是否有新发言 → 传入 Selector
2. 调用 Selector (批量评估所有 active 观众)
3. 对 speak=true 的观众: 启动 Generator task, 添加随机延迟 0-6s 后广播
4. 对 leave=true 的观众: deactivate, 广播 system leave 事件
5. 检查 entry timing: 按 `entry_interval_sec` 间隔从 inactive 池中随机选一个激活
6. 广播 system enter 事件
7. 检查 cooldown 到期 → reset 为 inactive

## ASR Pipeline 新职责

精简后只做：
```python
async def _process_asr_result(text: str):
    timestamp = int(time.time())
    streamer_timeline.append({"text": text, "offset": timestamp})
```

不再触发生成弹幕或调用 viewer 逻辑。

## WS 事件格式

### enter
```json
{"type": "system", "action": "enter", "name": "小冰", "id": "xiaobing"}
```

### leave
```json
{"type": "system", "action": "leave", "name": "小冰", "id": "xiaobing"}
```

### danmaku
```json
{"type": "danmaku", "id": "tuzi", "name": "兔子", "text": "这波你在送？", "personality": "aggressive", "effect": "highlight"}
```

## 配置变更

```yaml
viewer:
  min_active: 3
  max_active: 8
  entry_interval_sec: 180
  cooldown_sec: 300
  tick_interval_sec: 15     # 新增
  engagement_threshold: 20   # 新增
  memory_max_streamer_log: 50
```

## 边界与错误处理

- **离场不跌破 min_active**: 若 active ≤ min_active，Selector 的 leave 决策被忽略，不执行离场
- **Generator 失败**: 降级为不发言，不影响该观众 engagement 和 leave 状态
- **Selector 解析失败**: 跳过该 tick，重试下次
- **长沉默**: engagement 持续衰减到阈值 → LLM 决定抱怨或离场
- **ASR 长时间无输入**: scheduler 继续运行，观众因无聊陆续离场，逐渐只剩 bystander

## 测试要点

- Engagement 基础衰减 + 随机波动在预期范围内
- Selector 解析给定 JSON 格式
- Scheduler 按 tick 间隔驱动
- 沉默 n 个 tick 后观众离场
- 主播发言后 engagement 变化影响离场决策
- 广播 enter/leave 事件
