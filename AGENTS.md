# streamer-trainer

实时弹幕生成系统 — 通过主播语音生成虚拟观众弹幕，用于主播培训。

## 快速开始

```bash
cp .env.example .env          # 填入 MOONSHOT_API_KEY
uv sync --group dev            # 安装依赖（含 dev）
uv run pytest tests/           # 运行所有测试
uv run python scripts/download_models.py  # 预下载 Whisper 模型（可选）
uv run python -m backend.main  # 启动服务 → http://localhost:8765
uv run python scripts/debug_client.py    # 另一个终端，调试用
```

## 架构概要

- **FastAPI** 后端，单进程，无数据库
- **两阶段 LLM pipeline**: Selector（选角）→ Generator（生成弹幕），角色记忆隔离
- **ASR**: faster-whisper（本地，懒加载），配置见 `config.yaml` `asr.*`
- **LLM**: MoonShotAI（OpenAI 兼容格式），配置见 `config.yaml` `llm.*`
- **前端**: 纯 H5 (index.html + style.css + script.js)，通过 `/danmaku` WS 实时接收弹幕
- **虚拟观众**: 10 个预定义角色（4 种类型: curious/cheerful/aggressive/bystander），带状态机 (inactive→active→cooldown)

## 入口点

| 路径 | 说明 |
|------|------|
| `backend/main.py` | FastAPI app + WS 端点 + pipeline 编排 |
| `backend/llm/client.py` | LLM 客户端（OpenAI 兼容 / Anthropic） |
| `backend/llm/selector.py` | Stage 1: 选角导演 |
| `backend/llm/generator.py` | Stage 2: 弹幕生成 |
| `backend/viewer/manager.py` | 观众状态机 + 轮换调度 |
| `backend/viewer/personas.py` | 10 个预定义角色 |
| `backend/config.py` | 配置加载（config.yaml + .env） |
| `config.yaml` | 服务/ASR/LLM/观众参数 |

## API

- `POST /debug_text` — 传入文本触发完整 pipeline，返回 `{"status":"ok"}` 或 `{"status":"error","message":"..."}` 
- `WebSocket /audio` — 接收 PCM 音频数据（16kHz 16bit），自动 ASR + LLM
- `WebSocket /danmaku` — 接收实时弹幕消息（JSON）
- `WebSocket /control` — ping/pong（心跳）
- `GET /{path}` — 静态文件服务（frontend/ 目录）

## 测试

```bash
uv run pytest tests/ -v            # 全部 37 个测试
uv run pytest tests/test_client.py # 单个文件
uv run pytest -k "selector"        # 按关键字过滤
```

测试特点:
- `test_main.py` 用 `autouse` fixture patch `StreamerTrainerApp`，所有 mock
- fixture teardown 重置 `_LazyAppState._instance`，避免单例污染
- LLM client 测试用 mock response，不依赖真实 API

## 关键陷阱

- **代理冲突**: WSL2 的 `~/.bashrc` 设置 `http_proxy` → `config.py` 在加载配置时清除 proxy env vars，避免 httpx/OpenAI SDK 走不存在的代理
- **ASR 模型懒加载**: `ASREngine` 在 `__init__` 时不加载模型，首次 `transcribe()` 才两级回退（本地缓存 → 下载）。启动时不阻塞
- **路径穿越防护**: `serve_frontend` 对请求路径做 `resolve()` + 前缀校验，防止 `GET /../.env`
- **WebSocket 音频流**: `audio_endpoint` 的 `_process_asr_result` 调用包在 try/except 内，LLM 超时不中断音频连接
- **asyncio.gather**: pipeline 内使用 `return_exceptions=True`，单个 LLM 调用失败不阻断其他角色
- **uv sync**: `[dependency-groups] dev` 含 pytest，用 `--group dev` 而非 `--optional`
