# streamer-trainer (agent-pipeline 分支)

实时弹幕生成系统 — 通过主播语音生成虚拟观众弹幕，用于主播培训。

## 快速开始

```bash
cp .env.example .env          # 填入 MOONSHOT_API_KEY
uv sync --group dev            # 安装依赖（含 dev）
uv run pytest tests/           # 运行所有测试
uv run python scripts/download_models.py  # 预下载 Whisper 模型（可选）
uv run python -m backend.main  # 启动服务 → http://localhost:8765
# 在前端底部输入框输入主播台词后发送
```

## 架构概要

- **FastAPI** 后端，单进程，无数据库
- **Agent-driven pipeline**: kimi-k2.6（Agent 决策）→ Generator（moonshot-v1-8k 生成弹幕文本）
- **ASR**: faster-whisper（本地，懒加载），配置见 `config.yaml` `asr.*`
- **LLM**: MoonShotAI（OpenAI 兼容格式），配置见 `config.yaml` `llm.*`
- **Agent**: kimi-k2.6，function calling 调度观众进出场，配置见 `config.yaml` `agent.*`
- **前端**: 纯 H5 (index.html + style.css + script.js)，通过 `/danmaku` WS 实时接收弹幕
- **虚拟观众**: 每 tick 由 Agent 通过 spawn_viewer tool 动态生成，离场即删

## 入口点

| 路径 | 说明 |
|------|------|
| `backend/main.py` | FastAPI app + WS 端点 + pipeline 编排 |
| `backend/llm/agent.py` | Agent 客户端（kimi-k2.6 + function calling） |
| `backend/llm/client.py` | LLM 客户端（moonshot-v1-8k 弹幕文本生成） |
| `backend/llm/generator.py` | 弹幕生成 prompt 构建 |
| `backend/viewer/manager.py` | 观众管理（增/删/激活/查） |
| `backend/viewer/scheduler.py` | 调度器（Agent 驱动、tick 循环） |
| `backend/config.py` | 配置加载（config.yaml + .env） |
| `config.yaml` | 服务/ASR/LLM/Agent/观众参数 |

## API

- `POST /debug_text` — 传入文本追加到主播时间线，返回 `{"status":"ok"}` 或 `{"status":"error","message":"..."}` 
- `WebSocket /audio` — 接收 PCM 音频数据（16kHz 16bit），自动 ASR + LLM
- `WebSocket /danmaku` — 接收实时弹幕消息（JSON）
- `WebSocket /control` — ping/pong（心跳）
- `GET /{path}` — 静态文件服务（frontend/ 目录）

## 测试

```bash
uv run pytest tests/ -v            # 全部 40 个测试
uv run pytest tests/test_client.py # 单个文件
uv run pytest -k "scheduler"       # 按关键字过滤
```

测试特点:
- `test_main.py` 用 `autouse` fixture patch `StreamerTrainerApp`，所有 mock
- fixture teardown 重置 `_LazyAppState._instance`，避免单例污染
- LLM / Agent client 测试用 mock response，不依赖真实 API
- Scheduler 测试用 MockAgent，验证工具调用的分发和执行

## 关键陷阱

- **代理冲突**: WSL2 的 `~/.bashrc` 设置 `http_proxy` → `config.py` 在加载配置时清除 proxy env vars，避免 httpx/OpenAI SDK 走不存在的代理
- **ASR 模型懒加载**: `ASREngine` 在 `__init__` 时不加载模型，首次 `transcribe()` 才两级回退（本地缓存 → 下载）。启动时不阻塞
- **路径穿越防护**: `serve_frontend` 对请求路径做 `resolve()` + 前缀校验，防止 `GET /../.env`
- **WebSocket 音频流**: `audio_endpoint` 的 `_process_asr_result` 调用包在 try/except 内，LLM 超时不中断音频连接
- **asyncio.gather**: pipeline 内使用 `return_exceptions=True`，单个 LLM 调用失败不阻断其他角色
- **uv sync**: `[dependency-groups] dev` 含 pytest，用 `--group dev` 而非 `--optional`
- **离场即删**: 观众不再有冷却池，每次入场都是 Agent 生成的全新观众
