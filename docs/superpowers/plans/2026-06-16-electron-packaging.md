# Electron Desktop Client — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the streamer-trainer Python backend + H5 frontend into a double-click-install Windows desktop app via Electron + PyInstaller.

**Architecture:** Electron main process spawns a PyInstaller-packed backend.exe as a subprocess, then opens a BrowserWindow pointing to `http://localhost:8765`. The existing frontend code is reused unchanged. User data (config, logs) lives in `%APPDATA%/StreamerTrainer/`.

**Tech Stack:** Python 3.11 + PyInstaller (backend), Electron 30 + plain JS (shell), electron-builder 24 + NSIS (installer)

---

### Task 1: Backend --data-dir CLI argument

**Files:**
- Modify: `backend/main.py:1-30` (early startup), `backend/main.py:176-179` (path constants), `backend/main.py:381-388` (entry point)
- Create: `tests/test_backend_data_dir.py`

This enables the backend to accept a `--data-dir <path>` argument that relocates config.yaml and logs away from the current working directory — required when the backend runs as a bundled subprocess of Electron.

- [ ] **Step 1.1: Write the data-dir parsing test**

```python
# tests/test_backend_data_dir.py
import sys
from pathlib import Path
from unittest.mock import patch


def test_parse_data_dir_returns_none_when_not_provided():
    from backend.main import _parse_data_dir
    with patch.object(sys, "argv", ["backend.exe", "--port", "8765"]):
        result = _parse_data_dir()
    assert result is None


def test_parse_data_dir_extracts_path():
    from backend.main import _parse_data_dir
    with patch.object(sys, "argv", ["backend.exe", "--data-dir", "/tmp/stdir"]):
        result = _parse_data_dir()
    assert result == Path("/tmp/stdir")


def test_parse_data_dir_ignores_unknown_args():
    from backend.main import _parse_data_dir
    with patch.object(sys, "argv", ["backend.exe", "--foo", "--data-dir", "/tmp/stdir", "--bar"]):
        result = _parse_data_dir()
    assert result == Path("/tmp/stdir")
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `uv run pytest tests/test_backend_data_dir.py -v`

Expected: `FAILED` with `ModuleNotFoundError: No module named 'backend.main'` or `AttributeError: module 'backend.main' has no attribute '_parse_data_dir'`

- [ ] **Step 1.3: Add _parse_data_dir and data-dir wiring to main.py**

Add after line 16 (`from pathlib import Path`) and before line 18 (`# ── 防双加载 ──`):

```python

# ── CLI arg parsing (must happen before any path-dependent setup) ──
def _parse_data_dir() -> Optional[Path]:
    for i, arg in enumerate(sys.argv):
        if arg == "--data-dir" and i + 1 < len(sys.argv):
            p = Path(sys.argv[i + 1]).resolve()
            p.mkdir(parents=True, exist_ok=True)
            # Strip consumed args so child processes (uvicorn reload) don't re-parse
            sys.argv = sys.argv[:i] + sys.argv[i + 2:]
            return p
    return None


_DATA_DIR = _parse_data_dir()
```

Replace lines 27-28 (`_LOG_DIR = Path(__file__)...`):

```python
# ── 日志 ─────────────────────────────────────────────
if _DATA_DIR:
    _LOG_DIR = _DATA_DIR / "logs"
else:
    _LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
```

Replace lines 176-179 (FRONTEND_DIR, CONFIG_PATH, CONFIG_DEFAULT_PATH):

```python
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if _DATA_DIR:
    CONFIG_PATH = _DATA_DIR / "config.yaml"
    default_dst = _DATA_DIR / "config.default.yaml"
    if not default_dst.is_file():
        src = Path(__file__).resolve().parent.parent / "config.default.yaml"
        if src.is_file():
            shutil.copy(str(src), str(default_dst))
    CONFIG_DEFAULT_PATH = default_dst
else:
    CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
    CONFIG_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.default.yaml"
```

Also, ensure `_DATA_DIR` is set before `config.py` imports by adding after the `_DATA_DIR` assignment, before `from backend.config import config`:

```python
# Tell config module where to find config.yaml
if _DATA_DIR:
    os.environ["CONFIG_PATH"] = str(_DATA_DIR / "config.yaml")
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `uv run pytest tests/test_backend_data_dir.py -v`

Expected: `3 passed`

- [ ] **Step 1.5: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: All existing tests pass (40+ tests)

- [ ] **Step 1.6: Commit**

```bash
git add backend/main.py tests/test_backend_data_dir.py
git commit -m "feat: add --data-dir CLI argument for portable data paths"
```

---

### Task 2: Root package.json and electron-builder config

**Files:**
- Create: `package.json`
- Create: `electron-builder.yml`
- Create: `electron/preload.js`
- Modify: `.gitignore`

- [ ] **Step 2.1: Create root package.json**

```json
{
  "name": "streamer-trainer",
  "version": "1.0.0",
  "description": "实时弹幕生成系统 — 主播培训工具",
  "main": "electron/main.js",
  "scripts": {
    "build:backend": "scripts\\build-backend.bat",
    "package": "electron-builder",
    "release": "npm run build:backend && npm run package",
    "start": "electron ."
  },
  "devDependencies": {
    "electron": "^30.0.0",
    "electron-builder": "^24.0.0"
  },
  "author": "",
  "license": "MIT"
}
```

- [ ] **Step 2.2: Create electron-builder.yml**

```yaml
appId: com.streamer-trainer.app
productName: StreamerTrainer
copyright: Copyright © 2026

directories:
  output: release

files:
  - electron/**/*
  - package.json

extraResources:
  - from: dist/backend.exe
    to: ./
    filter:
      - "**/*"

win:
  target:
    - target: nsis
      arch:
        - x64
  icon: electron/assets/icon.ico

nsis:
  oneClick: true
  perMachine: false
  allowToChangeInstallationDirectory: false
  deleteAppDataOnUninstall: false
  installerIcon: electron/assets/icon.ico
  uninstallerIcon: electron/assets/icon.ico
  installerHeaderIcon: electron/assets/icon.ico
```

- [ ] **Step 2.3: Create electron/preload.js (minimal)**

```javascript
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
});
```

- [ ] **Step 2.4: Create placeholder tray icon**

Create directory and a minimal 32x32 PNG (will be replaced with real icon later).

```bash
mkdir -p electron/assets
# Generate a minimal valid 32x32 blue PNG as placeholder
python3 -c "
import struct, zlib
def create_png(w, h, color):
    raw = b''
    for y in range(h):
        raw += b'\\x00'  # filter none
        for x in range(w):
            raw += bytes(color)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    return b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
with open('electron/assets/icon.png', 'wb') as f:
    f.write(create_png(32, 32, (66, 133, 244)))
"
```

- [ ] **Step 2.5: Electron assets .gitkeep**

```bash
touch electron/assets/.gitkeep
```

- [ ] **Step 2.6: Update .gitignore**

Append to `.gitignore`:

```
# Electron
electron/assets/icon.ico
node_modules/
release/
dist/
```

- [ ] **Step 2.7: Commit**

```bash
git add package.json electron-builder.yml electron/preload.js electron/assets/ .gitignore
git commit -m "chore: add Electron project scaffolding and build config"
```

---

### Task 3: Electron main process

**Files:**
- Create: `electron/main.js`

This is the core file. It spawns the backend subprocess, creates the window, and manages system tray.

- [ ] **Step 3.1: Create electron/main.js**

```javascript
const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  nativeImage,
} = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

const BACKEND_PORT = 8765;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;

let mainWindow = null;
let tray = null;
let backendProcess = null;

// ── Backend management ──────────────────────────────

function getBackendPath() {
  if (app.isPackaged) {
    // extraResources puts backend.exe next to the app
    return path.join(process.resourcesPath, "backend.exe");
  }
  return null; // dev mode: assume backend is running separately
}

function getDataDir() {
  return path.join(app.getPath("appData"), "StreamerTrainer");
}

function startBackend() {
  const exePath = getBackendPath();
  if (!exePath) {
    console.log("[electron] Dev mode — backend should be started manually");
    return;
  }
  if (!fs.existsSync(exePath)) {
    console.error(`[electron] backend.exe not found at: ${exePath}`);
    return;
  }

  const dataDir = getDataDir();
  console.log(`[electron] Starting backend: ${exePath} --data-dir ${dataDir}`);

  backendProcess = spawn(exePath, ["--data-dir", dataDir], {
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  backendProcess.stdout.on("data", (d) => {
    console.log(`[backend] ${d.toString().trim()}`);
  });
  backendProcess.stderr.on("data", (d) => {
    console.error(`[backend] ${d.toString().trim()}`);
  });
  backendProcess.on("exit", (code, signal) => {
    console.log(`[electron] Backend exited (code=${code}, signal=${signal})`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    console.log("[electron] Stopping backend...");
    backendProcess.kill();
    backendProcess = null;
  }
}

function waitForBackend(retries) {
  return new Promise((resolve, reject) => {
    const check = (n) => {
      if (n <= 0) {
        reject(new Error("Backend failed to start within timeout"));
        return;
      }
      http
        .get(BACKEND_URL, () => resolve())
        .on("error", () => {
          setTimeout(() => check(n - 1), 500);
        });
    };
    check(retries);
  });
}

// ── Window management ───────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 420,
    height: 700,
    resizable: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });

  mainWindow.loadURL(BACKEND_URL);

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ── System tray ─────────────────────────────────────

function createTray() {
  const iconPath = path.join(__dirname, "assets", "icon.png");
  let icon;
  try {
    icon = nativeImage.createFromPath(iconPath);
    if (icon.isEmpty()) throw new Error("Empty icon");
  } catch {
    icon = nativeImage.createEmpty();
  }

  tray = new Tray(icon);
  tray.setToolTip("Streamer Trainer");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "显示窗口",
      click: () => {
        if (mainWindow) mainWindow.show();
      },
    },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on("click", () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

// ── App lifecycle ───────────────────────────────────

app.whenReady().then(async () => {
  startBackend();
  try {
    await waitForBackend(30);
  } catch (err) {
    console.error(`[electron] ${err.message}`);
    // Still create window — will show error page
  }
  createWindow();
  createTray();
});

app.on("before-quit", () => {
  stopBackend();
});

app.on("window-all-closed", () => {
  // Don't quit on last window close (tray keeps running)
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  } else {
    mainWindow.show();
  }
});
```

- [ ] **Step 3.2: Manual smoke test**

Run: `npm install && npx electron .` (with backend running separately on :8765)

Expected: Window opens showing the chat interface, tray icon appears.

- [ ] **Step 3.3: Commit**

```bash
git add electron/main.js
git commit -m "feat: add Electron main process with backend spawn and tray"
```

---

### Task 4: Build scripts

**Files:**
- Create: `scripts/build-backend.bat`
- Create: `scripts/download-models.bat`

- [ ] **Step 4.1: Create scripts/build-backend.bat**

```batch
@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set DIST=%ROOT%\dist

echo === Building backend.exe with PyInstaller ===

if not exist "%DIST%" mkdir "%DIST%"

:: Activate uv venv if available
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set PYTHON=%ROOT%\.venv\Scripts\python.exe
) else (
    where python >nul 2>nul || (
        echo ERROR: Python not found
        exit /b 1
    )
    set PYTHON=python
)

:: Ensure PyInstaller is installed
"%PYTHON%" -m pip install pyinstaller >nul 2>&1

:: Build
"%PYTHON%" -m PyInstaller ^
    --onefile ^
    --name backend ^
    --distpath "%DIST%" ^
    --add-data "%ROOT%\config.default.yaml;." ^
    --add-data "%ROOT%\frontend;frontend" ^
    --add-data "%ROOT%\backend\asr\models;backend\asr\models" ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    "%ROOT%\backend\main.py"

echo === Done: %DIST%\backend.exe ===
```

- [ ] **Step 4.2: Create scripts/download-models.bat**

```batch
@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set MODELS_DIR=%ROOT%\backend\asr\models

echo === Downloading ASR models ===

if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"

echo Downloading sherpa-onnx-sense-voice model...
:: For MVP, point to your model source (e.g., HuggingFace or internal mirror)
:: Example:
:: "%PYTHON%" -m pip install huggingface-hub
:: "%PYTHON%" -c "from huggingface_hub import snapshot_download; snapshot_download('csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17', local_dir='%MODELS_DIR%/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17')"

echo Downloading Silero VAD model...
:: "%PYTHON%" -c "import urllib.request; urllib.request.urlretrieve('https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx', '%MODELS_DIR%/silero_vad.onnx')"

echo Note: Manual model download may be needed. See docs for details.
echo Done.
```

- [ ] **Step 4.3: Commit**

```bash
git add scripts/build-backend.bat scripts/download-models.bat
git commit -m "chore: add Windows build scripts for PyInstaller and model download"
```

---

### Task 5: Integration verification

- [ ] **Step 5.1: Run all Python tests**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 5.2: Verify node deps install**

```bash
npm install
```

Expected: No errors, electron and electron-builder installed in node_modules/

- [ ] **Step 5.3: Final commit**

```bash
git add -A
git commit -m "chore: finalize Electron packaging scaffolding"
```
