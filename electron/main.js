const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  nativeImage,
  dialog,
} = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");

const BACKEND_PORT = 8765;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
const BACKEND_WAIT_RETRIES = 30;
const BACKEND_KILL_TIMEOUT_MS = 3000;

let mainWindow = null;
let tray = null;
let backendProcess = null;
let backendKillTimer = null;
let backendPollAborted = false;

// ── Backend management ──────────────────────────────

function getBackendPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend.exe");
  }
  return null;
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
  if (backendKillTimer) {
    clearTimeout(backendKillTimer);
    backendKillTimer = null;
  }
  if (backendProcess) {
    console.log("[electron] Stopping backend...");
    backendPollAborted = true;
    backendProcess.kill();
    // SIGKILL fallback if process doesn't exit gracefully
    const proc = backendProcess;
    backendKillTimer = setTimeout(() => {
      if (proc.exitCode === null) {
        console.log("[electron] Backend still alive, sending SIGKILL");
        proc.kill("SIGKILL");
      }
    }, BACKEND_KILL_TIMEOUT_MS);
    backendProcess = null;
  }
}

function waitForBackend(retries) {
  return new Promise((resolve, reject) => {
    const check = (n) => {
      if (backendPollAborted) {
        reject(new Error("Backend wait aborted by shutdown"));
        return;
      }
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
      contextIsolation: true,
      nodeIntegration: false,
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
  app.isQuitting = false;
  startBackend();
  try {
    await waitForBackend(BACKEND_WAIT_RETRIES);
  } catch (err) {
    console.error(`[electron] ${err.message}`);
    dialog.showErrorBox(
      "后端启动失败",
      `后端服务未能启动。\n\n${err.message}\n\n请检查 log 后重试。`
    );
  }
  createWindow();
  createTray();
});

app.on("before-quit", () => {
  if (tray) {
    tray.destroy();
    tray = null;
  }
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
