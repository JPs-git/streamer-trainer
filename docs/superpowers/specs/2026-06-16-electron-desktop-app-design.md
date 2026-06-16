# Streamer Trainer — Electron 桌面客户端设计

Date: 2026-06-16
Status: Draft

## 1. 动机

- OBS 插件方案编译成本过高，不适用于 MVP 阶段
- 目标用户（主播）希望双击安装、开箱即用，不接触命令行
- 已有完整的 Python（FastAPI + ASR + LLM）后端和 H5 前端，需要一层原生 GUI 外壳
- MVP 阶段先覆盖 Windows，后续视需求扩展到 macOS / Linux

## 2. 架构

```
┌─────────────────────────────────────────────────┐
│  Electron App (Node.js 20+, Chromium)           │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │  主进程 (main.ts)                          │  │
│  │  ├─ spawn backend.exe (subprocess)         │  │
│  │  ├─ kill backend.exe on quit               │  │
│  │  ├─ 系统托盘 (最小化/退出/关于)             │  │
│  │  ├─ 自动更新 (electron-updater)            │  │
│  │  └─ 首次运行初始化 (config.yaml 生成)       │  │
│  └──────────────┬────────────────────────────┘  │
│                 │ HTTP / WS (localhost:8765)     │
│  ┌──────────────▼────────────────────────────┐  │
│  │  渲染进程 (BrowserWindow)                  │  │
│  │  ├─ 加载 http://localhost:8765             │  │
│  │  ├─ 现有 H5 前端完全复用 (index.html)       │  │
│  │  └─ preload.js 暴露 native API            │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │  Python 后端子进程 (backend.exe)           │  │
│  │  ├─ PyInstaller 打包产物                   │  │
│  │  ├─ FastAPI + uvicorn on localhost:8765   │  │
│  │  ├─ ASR Pipeline (sherpa-onnx, 本地模型)   │  │
│  │  └─ LLM Client (MoonShotAI / OpenRouter)  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 关键设计决策

- **前后端通信**：Electron 渲染进程通过 localhost HTTP/WS 与 Python 后端通信，不引入 IPC Bridge
  - 现有前端代码 100% 复用，无需修改
  - 开发时可直接用浏览器 + Python 源码启动，Electron 不是必需
- **进程管理**：Electron 主进程通过 `child_process.spawn` 管理 backend.exe，监听 stdout/stderr 做健康检查
- **端口分配**：尝试 `8765`，被占用则自动递增直到找到可用端口

## 3. 目录结构

```
streamer-trainer/
├── backend/                    # Python 后端 (已有)
│   ├── main.py
│   ├── config.py
│   ├── asr/
│   ├── llm/
│   └── viewer/
├── frontend/                   # Web 前端 (已有)
│   ├── index.html
│   ├── style.css
│   └── script.js
├── electron/                   # ★ 新增：Electron 外壳
│   ├── main.ts                 #   主进程
│   ├── preload.ts              #   preload 脚本
│   ├── tsconfig.json
│   └── package.json
├── package.json                # ★ 新增：Electron 构建入口
├── electron-builder.yml        # ★ 新增：electron-builder 配置
├── scripts/
│   ├── build-backend.bat       #   Windows: PyInstaller 构建脚本
│   └── download-models.bat     #   Windows: 模型下载脚本
├── config.yaml                 # 默认配置文件 (将拷贝到 %APPDATA%)
├── config.default.yaml
├── AGENTS.md
└── pyproject.toml
```

## 4. Electron 外壳设计

### 4.1 主进程主干逻辑

```typescript
// electron/main.ts (伪代码)
function createWindow() {
  const port = findAvailablePort(8765)
  backendProcess = spawn('backend.exe', [], { ... })
  waitForHealthCheck(`http://127.0.0.1:${port}/`)

  const win = new BrowserWindow({
    width: 420, height: 700,
    webPreferences: { preload: path.join(__dirname, 'preload.js') }
  })
  win.loadURL(`http://127.0.0.1:${port}/`)

  // 托盘：最小化到系统托盘，点击恢复
  // 退出时 kill backendProcess
}
```

### 4.2 功能清单（MVP）

| 功能 | 实现方式 | 优先级 |
|------|----------|--------|
| 启动后端子进程 | `child_process.spawn` | P0 |
| 优雅退出（kill 后端） | `process.on('before-quit')` | P0 |
| 加载前端页面 | `win.loadURL` | P0 |
| 系统托盘 | `Tray` + 右键菜单 | P1 |
| 最小化到托盘 | `win.on('close')` → `win.hide()` | P1 |
| 首次运行引导（config 生成） | 检测 `%APPDATA%/StreamerTrainer/config.yaml` | P1 |
| 关于窗口 | `dialog.showMessageBox` | P2 |
| 自动更新 | `electron-updater` | P2 |
| 崩溃/卡死检测 | 后端心跳 + 自动重启 | P2 |
| 后端日志输出到 Debug 控制台 | `backendProcess.stdout.on('data')` | P1 |

### 4.3 用户数据路径

```
Windows: %APPDATA%/StreamerTrainer/
├── config.yaml          # 配置文件（首次运行从内置 config.default.yaml 拷贝）
└── logs/
    ├── app.log          # Python 后端日志
    └── llm.log          # LLM 交互日志
```

Electron 主进程将 `--data-dir` 参数传给 backend.exe，后端据此定位 config.yaml 和日志目录。

## 5. PyInstaller 打包

### 5.1 打包内容

- Python 3.11 运行时（内置于 exe）
- 所有 Python 依赖（torch 已排除，sherpa-onnx 无 torch 依赖）
- ASR 模型文件（sherpa-onnx-sense-voice ~100MB）
- VAD 模型文件（silero_vad.onnx ~10MB）
- 前端静态文件（frontend/ 目录）
- config.default.yaml

### 5.2 打包命令

```bash
pyinstaller --onefile --name backend ^
  --add-data "backend/asr/models;backend/asr/models" ^
  --add-data "frontend;frontend" ^
  --add-data "config.default.yaml;." ^
  backend/main.py
```

### 5.3 体积估算

| 组件 | 体积 |
|------|------|
| Python 运行时 + 依赖 | ~80MB |
| ASR 模型 | ~100MB |
| 前端 + 配置文件 | <1MB |
| **backend.exe 小计** | **~180MB** |
| Electron shell | ~60MB |
| **安装包总计** | **~240MB** |

## 6. electron-builder 配置

```yaml
# electron-builder.yml
appId: com.streamer-trainer.app
productName: StreamerTrainer
directories:
  output: release
files:
  - electron/dist/**/*
extraResources:
  - from: dist/backend.exe
    to: backend.exe
win:
  target: nsis
  icon: electron/assets/icon.ico
nsis:
  oneClick: true
  perMachine: false
  installerIcon: electron/assets/icon.ico
  uninstallerIcon: electron/assets/icon.ico
```

## 7. 构建流程

```
                    ┌─────────────────────┐
                    │  开发者运行 npm run   │
                    │  build:all           │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │ npm run       │ │ npm run       │ │ npm run       │
      │ build:backend │ │ build:electron │ │ package       │
      └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
             │                │                │
             ▼                ▼                ▼
      PyInstaller →    tsc → dist/    electron-builder
      dist/backend.exe electron/      → release/
                                       StreamerTrainer-
                                       Setup-1.0.0.exe
```

## 8. 错误处理

### 场景 + 处理方式

| 场景 | 表现 |
|------|------|
| 后端启动失败（端口占用） | 自动尝试下一个端口，弹窗提示实际端口 |
| 后端启动超时（10s） | 弹窗重试/退出，日志记录原因 |
| 后端运行中崩溃 | 自动重启一次，若再次崩溃则弹窗报告 |
| 后端退出时未清理 | Electron before-quit 确保 kill |
| 网络不通（LLM API） | 前端已有错误提示，后端日志记录 |
| ASR 模型缺失 | 后端日志记录，前端显示"语音识别未就绪" |
| 配置损坏 | 回退到内置 config.default.yaml，提示用户 |

## 9. 与现有代码的兼容性

- 不修改 `backend/` 目录下任何 Python 代码 — 后端完全不知道自己被 Electron 包裹
- 不修改 `frontend/` 目录下任何前端代码 — 前端依然认为自己运行在浏览器中
- Electron 新增 `electron/` 目录和 `package.json`
- 新增 `scripts/build-backend.bat` 和 `scripts/download-models.bat`

唯一需要的后端改动：接受 `--data-dir` 命令行参数，用于覆盖 config.yaml 和日志路径。

## 10. 未来扩展方向（非 MVP）

- **系统音频捕获**：通过 Electron `desktopCapturer` API 捕获桌面音频，替代浏览器麦克风
- **OBS 集成**：通过 OBS WebSocket 插件获取直播状态、场景切换等事件
- **macOS/Linux 支持**：调整 PyInstaller 和 electron-builder 配置，差异主要在路径和安装程序格式
- **便携版（免安装）**：electron-builder 的 portable 选项，打成单个 exe
