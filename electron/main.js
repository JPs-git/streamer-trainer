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
