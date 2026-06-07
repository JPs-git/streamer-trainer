# 规则引擎调度器 — 替代 Agent (kimi-k2.6) function calling

## 背景

当前架构每 tick 调用一次 `agent.decide()`（kimi-k2.6 + function calling），实际耗时 4~21s（服务端波动），远超预期（~5s）。且 moonshot-v1-8k 不支持 tool calling，无法做低成本替换。

## 决策

将调度决策从 LLM function calling 改为**纯本地规则引擎**，只在观众入场和弹幕文本生成时调用 LLM（moonshot-v1-8k），消除每 tick 的 Agent 等待。

## 架构对比

### 之前

```
每 tick (15s):
  1. 基础 decay（本地）
  2. await Agent (kimi-k2.6)  ← 4~21s，瓶颈
     ├─ spawn_viewer
     ├─ adjust_engagement
     ├─ schedule_speak
     └─ remove_viewer
  3. 执行动作（含 speak → LLM 生成弹幕）
  4. 背填充
  5. asyncio.sleep(剩余时间)
```

### 之后

```
每 tick (规则引擎，0 LLM 开销):
  1. 基础 decay（本地）
  2. 规则引擎决策（纯本地，<1ms）
     ├─ spawn_viewer        ← 自动背填充
     ├─ adjust_engagement   ← 发言/交互自动修正
     ├─ schedule_speak      ← 概率抽选
     └─ remove_viewer       ← engagement 过低自动离场
  3. 执行动作（含 speak → await LLM 生成弹幕）← 并发生成
  4. 背填充
  5. asyncio.sleep(剩余时间)

入场时（非每 tick）:
  - await LLM (moonshot-v1-8k) 生成观众资料 JSON  ← ~3s
```

## 规则引擎逻辑

### spawn_viewer（背填充入场）

```python
if active_count < min_active and active_count < max_active:
    # 补到 min_active
    for i in range(min_active - active_count):
        name, persona, relationship, engagement = await _generate_viewer_profile()
        create_viewer(name, persona, relationship, engagement)
```

**观众资料生成**由 moonshot-v1-8k 完成，一次产生一个观众的结构化 JSON：

```
输入: 无（或直播主题上下文）
输出: {"name": "小星星", "persona": "活泼健谈的老粉", "relationship": "老粉", "engagement": 85}
```

### adjust_engagement（自动修正）

```python
# 每 tick 基础衰减（已有）
for v in active:
    v.engagement -= random.uniform(1, 5) + random.uniform(-2, 2)

# 发言后奖励
事后: v.engagement += random.uniform(3, 8)

# 互动越多 engagement 越高（慢增长）
if v.interaction_count > 5:
    v.engagement = min(100, v.engagement + 1)
```

### schedule_speak（概率抽选发言人）

```python
for v in active:
    # engagement 越高发言概率越大
    prob = v.engagement / 100.0 * 0.6
    # 刚发过言的概率降低
    if 刚发过言: prob *= 0.3
    # 主播刚说话时所有观众发言概率提升
    if streamer_has_new: prob *= 1.5

    if random.random() < prob:
        schedule_speak(v)
```

### remove_viewer（低 engagement 自动离场）

```python
for v in active:
    if v.engagement <= threshold:
        v 离场，删除
```

## 删除的组件

| 标识 | 说明 |
|------|------|
| `backend/llm/agent.py` | AgentClient + Agent 系统提示词 + 工具定义，全部删除 |
| `config.yaml agent.*` | agent.model、agent.base_url、agent.timeout、agent.temperature 删除 |

## 保留的组件

| 标识 | 说明 |
|------|------|
| `backend/llm/client.py` | LLMClient（moonshot-v1-8k），弹幕文本生成不变 |
| `backend/llm/generator.py` | Generator，弹幕 prompt 构建 + 解析不变 |
| `backend/viewer/scheduler.py` | ViewerScheduler，_tick 循环不变，替换内部逻辑 |
| `backend/viewer/manager.py` | ViewerManager，增删改查不变 |
| `backend/viewer/models.py` | VirtualViewer 模型不变 |

## 观众资料生成 API（新增）

新增 moonshot-v1-8k 的一次性调用，传入可选直播主题，返回结构化观众 JSON。

```python
async def generate_viewer_profile(topic: str = "") -> dict:
    prompt = f"生成一位直播观众，返回 JSON。\n主题：{topic}\n要求：名字中文2-3字，人设一句话，关系为老粉/路人/新关注，engagement 60-100。\n{{"name": "...", "persona": "...", "relationship": "...", "engagement": 数字}}"
    response = await llm.chat(system=SYSTEM, user=prompt)
    return json.loads(parse_json(response))
```

## 迁移步骤

1. 实现规则引擎替换 `agent.decide()` 在 `_tick()` 中的调用
2. 实现 `_generate_viewer_profile()` 调用 moonshot-v1-8k
3. 删除 `backend/llm/agent.py`
4. 删除 `config.yaml` 中 `agent.*` 配置段
5. 更新 `backend/config.py` 移除 agent 配置加载
6. 更新 `backend/main.py` 移除 AgentClient 实例化
7. 更新测试：`test_agent.py` 删除，`test_scheduler.py` 适配规则引擎
8. 清理文档
