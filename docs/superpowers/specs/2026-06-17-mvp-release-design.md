# StreamerTrainer v1.0.0 MVP 发布方案

Date: 2026-06-17 | Status: Draft

## 1. 动机

- 项目功能已基本成型（ASR 本地推理 + LLM 弹幕生成 + 虚拟观众管理 + Electron 桌面壳）
- 需要将 MVP 以桌面安装包形式交付给主播用户
- 解决 API Key 分发、配置管理、安装体验等发布前问题

## 2. API Key 策略

**原则**：内置受限 Key 开箱即用，支持用户自带 Key 覆盖。

| 层级 | 来源 | 限制 | 适用场景 |
|------|------|------|----------|
| 内置 | OpenRouter 受限子 Key | 仅免费模型，月度预算 $5 | 首次启动，零配置 |
| 用户覆盖 | Config 页输入 | 用户自己控制 | 需要更高额度/质量 |
| 降级 | 无 Key/无网络 | 仅 lurker 预设短语 | 网络故障或 Key 失效 |

加载优先级（config.py:63-68）：
```
config.yaml 中 api_key 字段
  → 环境变量 (api_key_env)
    → config.default.yaml 中默认 api_key
```

**实现方式**：
- 在 OpenRouter 后台创建子 API Key，限制仅可调用 `openrouter/free` 模型池
- 设置月度预算上限 $5 USD
- 构建脚本通过环境变量或文件替换将 key 写入 `config.default.yaml`
- `config.default.yaml` 中保留 `api_key_env: OPENROUTER_API_KEY`，同时 `api_key` 字段填入内置 key
- 用户 Config 页的 `api_key` 存入 `config.yaml`，覆盖默认值

**安全考量**：
- OpenRouter 子 Key 即使被提取，$5 上限 + 免费模型 = 攻击价值极低
- 用户如果输入自己的 Key，存在 `config.yaml`（`%APPDATA%`），不会被分发
- 后续可增加 Key 过期轮换机制

## 3. 平台

- **操作系统**：Windows 10+ x64
- **安装包格式**：NSIS one-click installer（无管理员要求）
- **安装路径**：`%LOCALAPPDATA%\Programs\StreamerTrainer\`
- **数据路径**：`%APPDATA%\StreamerTrainer\`（config.yaml + logs/）
- **卸载行为**：彻底删除所有用户数据

## 4. 功能变更

### 4.1 配置变更自动重启

- Electron 主进程通过 `fs.watchFile` 监控 `%APPDATA%/StreamerTrainer/config.yaml`
- 变更检测加入 500ms debounce，防止多次保存触发连锁重启
- 重启流程：`stopBackend()` → 等待端口释放 → `startBackend()` → 前端显示"配置已生效"
- 通过 `backendPollAborted` 避免重启过程中的健康检查误报

### 4.2 单例锁

- 使用 `app.requestSingleInstanceLock()` 防止多开
- 第二个实例启动时，发送 IPC 消息激活已有窗口

### 4.3 产品信息统一

| 位置 | 当前值 | 目标值 |
|------|--------|--------|
| `package.json` | `"version": "1.0.0"` | `"version": "1.0.0"` |
| `electron-builder.yml` | `productName: StreamerTrainer` | `productName: StreamerTrainer` |
| `pyproject.toml` | `version = "0.1.0"` | `version = "1.0.0"` |
| NSIS 安装包名 | `StreamerTrainer-Setup-1.0.0.exe` | `StreamerTrainer-Setup-1.0.0.exe` |

### 4.4 配置文件更新

`config.default.yaml` 更新为 MVP 可用配置：

```yaml
server:
  host: "127.0.0.1"
  port: 8765

asr:
  engine: onnx
  model_path: "backend/asr/models/.../model.int8.onnx"
  vad_model_path: "backend/asr/models/silero_vad.onnx"
  num_threads: 4
  language: auto
  use_itn: true
  vad_threshold: 0.5
  silence_duration_ms: 600
  max_segment_duration: 10

llm:
  provider: openai
  api_key_env: "OPENROUTER_API_KEY"
  api_key: ""    # ← 构建时注入的受限 Key
  base_url: "https://openrouter.ai/api/v1"
  model: "openrouter/free"
  timeout: 15.0
  temperature: 0.8
  max_tokens: 150
  request_interval: 2.0
  max_interval: 15.0

viewer:
  min_active: 5
  max_active: 20
  churn_per_tick: 5
  guider_ratio: 0.3
  tick_interval_sec: 10
```

## 5. 构建流程

```
构建机:
  1. 设置 OPENROUTER_BUILD_KEY 环境变量
  2. npm run build:backend
     → 读取环境变量 → 写入 config.default.yaml
     → PyInstaller --onefile --name backend
       --add-data config.default.yaml;.
       --add-data frontend;frontend
       --add-data backend/asr/models;backend/asr/models
     → dist/backend.exe (~190MB)

  3. npm run package
     → electron-builder
     → release/StreamerTrainer-Setup-1.0.0.exe (~250MB)

产物: release/StreamerTrainer-Setup-1.0.0.exe
```

## 6. 改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `config.default.yaml` | 修改 | 更新 ASR 配置 + LLM 默认使用 OpenRouter + 内置 key 占位 |
| `electron/main.js` | 修改 | 新增 fs.watch + 单例锁 + 自动重启逻辑 |
| `electron-builder.yml` | 修改 | `productName: StreamerTrainer`, `deleteAppDataOnUninstall: true` |
| `scripts/build-backend.bat` | 修改 | 注入 OpenRouter key 到 config.default.yaml |
| `pyproject.toml` | 修改 | `version = "1.0.0"` |
| `package.json` | 确认 | 确认 `version` 一致 |
| `.gitignore` | 确认 | 确认 `release/` `dist/` 已忽略 |
| `LICENSE` | 新增 | MIT License + 免责声明 |

**不修改的后端文件**：`backend/config.py`、`backend/main.py`、`backend/viewer/`、`backend/llm/`、`backend/asr/`（后端 100% 不知道自己被 Electron 包裹）

## 7. 错误场景处理

| 场景 | 表现 |
|------|------|
| OpenRouter Key 失效（额度用尽/吊销） | LLM 调用失败 → 降级 lurker 模式 → Config 页提示用户换 Key |
| 网络不通 | LLM 超时 → 降级 lurker → 弹窗提示检查网络 |
| 配置损坏 | 回退到 config.default.yaml，提示用户 |
| 后端崩溃 | Electron 自动重启一次，再次崩溃弹窗报告 |
| 安装包损坏 | NSIS 自校验失败，提示重新下载 |
| 端口占用 | 自动尝试递增端口，Electron 动态跟随 |
| ASR 模型缺失 | 后端日志记录，前端显示"语音识别未就绪" |

## 8. 许可

**MIT License** + 附加免责声明：

```
本软件使用第三方 LLM API（OpenRouter/MoonShotAI）生成内容。
开发者对 LLM 生成的文本内容不承担任何责任。
用户应遵守所用 API 平台的服务条款。
```

## 9. 未来扩展方向（非 MVP）

- **macOS/Linux 支持**：调整 build 脚本和 electron-builder 配置
- **系统音频捕获**：通过 Electron `desktopCapturer` API 捕获桌面音频
- **自动更新**：集成 `electron-updater`
- **崩溃报告**：接入 Sentry 或类似服务
- **OBS 集成**：OBS WebSocket 插件获取直播状态
