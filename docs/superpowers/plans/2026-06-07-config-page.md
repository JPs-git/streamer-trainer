# 前端配置页 Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a standalone config page (`/config.html`) with backend API to read/write config.yaml and auto-restart via uvicorn reload.

**Architecture:** Three new backend endpoints (GET/POST /api/config, POST /api/config/reset) read/write config.yaml directly. Frontend is a standalone HTML page with a JS controller, sharing style.css. Uvicorn reload on config.yaml change triggers automatic restart.

**Tech Stack:** FastAPI, Pydantic, PyYAML, vanilla JS

---

### Task 1: Create config.default.yaml

**Files:**
- Create: `config.default.yaml`

- [ ] **Step 1: Create default config file**

Copy the existing config.yaml at project root, remove all comments, as a clean reference. This file serves as the "factory reset" target.

```yaml
server:
  host: "127.0.0.1"
  port: 8765

asr:
  model_size: "base"
  device: "cpu"
  compute_type: "int8"
  download_timeout: 30.0

llm:
  provider: "openai"
  api_key_env: "MOONSHOT_API_KEY"
  base_url: "https://api.moonshot.cn/v1"
  model: "moonshot-v1-8k"
  selector_model: "moonshot-v1-8k"
  timeout: 10.0
  temperature: 0.8
  max_tokens: 150

agent:
  model: "kimi-k2.6"
  base_url: "https://api.moonshot.cn/v1"
  timeout: 120.0
  temperature: 0.6

viewer:
  min_active: 3
  max_active: 8
  entry_interval_sec: 180
  cooldown_sec: 300
  tick_interval_sec: 15
  engagement_threshold: 20
```

- [ ] **Step 2: Commit**

```bash
git add config.default.yaml
git commit -m "chore: add default config template for reset"
```

---

### Task 2: Add `api_key` field to config.yaml and update Config loader

**Files:**
- Modify: `config.yaml`
- Modify: `backend/config.py`

Allow the API key to be stored directly in config.yaml (as `llm.api_key`) as an alternative to env var lookup.

- [ ] **Step 1: Add `api_key` field to config.yaml**

Add `api_key: ""` under `llm:` section:

```yaml
llm:
  provider: "openai"
  api_key_env: "MOONSHOT_API_KEY"
  api_key: ""
  base_url: "https://api.moonshot.cn/v1"
  model: "moonshot-v1-8k"
  selector_model: "moonshot-v1-8k"
  timeout: 10.0
  temperature: 0.8
  max_tokens: 150
```

Also update `config.default.yaml` the same way.

- [ ] **Step 2: Update Config.__init__ to check api_key from yaml first**

In `backend/config.py` at line 49-56, replace the api_key resolution:

```python
llm_conf = raw["llm"]
self.llm_api_key = llm_conf.get("api_key") or os.environ.get(llm_conf["api_key_env"]) or ""
if not self.llm_api_key:
    raise ValueError(
        f"Neither 'api_key' in config nor environment variable "
        f"'{llm_conf['api_key_env']}' is set."
    )
```

This preserves backward compatibility: new yaml `api_key` field takes precedence, env var is fallback.

- [ ] **Step 3: Commit**

```bash
git add config.yaml config.default.yaml backend/config.py
git commit -m "feat: support api_key directly in config.yaml"
```

---

### Task 3: Backend config API endpoints

**Files:**
- Modify: `backend/main.py`
- Create: `tests/test_config_api.py`

Add three endpoints: GET /api/config, POST /api/config, POST /api/config/reset.

- [ ] **Step 1: Add Pydantic models before the existing app code**

In `backend/main.py`, add after the existing `DebugText` model (around line 237):

```python
class LLMConfigModel(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None

class ViewerConfigModel(BaseModel):
    min_active: Optional[int] = None
    max_active: Optional[int] = None
    entry_interval_sec: Optional[int] = None
    cooldown_sec: Optional[int] = None
    tick_interval_sec: Optional[int] = None
    engagement_threshold: Optional[int] = None

class ConfigUpdate(BaseModel):
    llm: Optional[LLMConfigModel] = None
    viewer: Optional[ViewerConfigModel] = None
```

- [ ] **Step 2: Add helper function to read raw config yaml**

After the Pydantic models, add:

```python
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CONFIG_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.default.yaml"

def _read_config_yaml() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _write_config_yaml(data: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

- [ ] **Step 3: Add GET /api/config endpoint**

```python
@app.get("/api/config")
async def get_config():
    raw = _read_config_yaml()
    llm = raw.get("llm", {})
    viewer = raw.get("viewer", {})

    api_key = llm.get("api_key", "")
    if api_key and len(api_key) > 8:
        masked = api_key[:4] + "****" + api_key[-4:]
    elif api_key:
        masked = "****"
    else:
        masked = ""

    return {
        "llm": {
            "base_url": llm.get("base_url", ""),
            "api_key": masked,
        },
        "viewer": {
            "min_active": viewer.get("min_active", 3),
            "max_active": viewer.get("max_active", 8),
            "entry_interval_sec": viewer.get("entry_interval_sec", 180),
            "cooldown_sec": viewer.get("cooldown_sec", 300),
            "tick_interval_sec": viewer.get("tick_interval_sec", 15),
            "engagement_threshold": viewer.get("engagement_threshold", 20),
        },
    }
```

- [ ] **Step 4: Add POST /api/config endpoint**

```python
@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    raw = _read_config_yaml()

    if body.llm is not None:
        if "llm" not in raw:
            raw["llm"] = {}
        if body.llm.base_url is not None:
            raw["llm"]["base_url"] = body.llm.base_url
        if body.llm.api_key is not None:
            # Only update if it's not a masked value
            if not (body.llm.api_key.startswith("sk-") and "****" in body.llm.api_key):
                raw["llm"]["api_key"] = body.llm.api_key

    if body.viewer is not None:
        if "viewer" not in raw:
            raw["viewer"] = {}
        updates = body.viewer.model_dump(exclude_none=True)
        raw["viewer"].update(updates)

    _write_config_yaml(raw)
    logger.info("Config updated via API, restarting...")
    return {"status": "ok", "message": "Config saved, restarting..."}
```

- [ ] **Step 5: Add POST /api/config/reset endpoint**

```python
@app.post("/api/config/reset")
async def reset_config():
    if not CONFIG_DEFAULT_PATH.is_file():
        return {"status": "error", "message": "Default config file not found"}
    import shutil
    shutil.copy(str(CONFIG_DEFAULT_PATH), str(CONFIG_PATH))
    logger.info("Config reset to defaults via API, restarting...")
    return {"status": "ok", "message": "Config reset to defaults, restarting..."}
```

- [ ] **Step 6: Write the failing test**

Create `tests/test_config_api.py`:

```python
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(autouse=True)
def mock_config_files(tmp_path):
    """Replace CONFIG_PATH and CONFIG_DEFAULT_PATH with tmp files."""
    import backend.main as main_module

    default_data = {
        "llm": {"base_url": "https://default.com/v1", "api_key": "sk-default-key-123"},
        "viewer": {"min_active": 3, "max_active": 8, "entry_interval_sec": 180,
                    "cooldown_sec": 300, "tick_interval_sec": 15, "engagement_threshold": 20},
    }
    default_path = tmp_path / "config.default.yaml"
    with open(default_path, "w") as f:
        f.write("llm:\n  base_url: https://default.com/v1\n  api_key: sk-default-key-123\n")
        f.write("viewer:\n  min_active: 3\n  max_active: 8\n  entry_interval_sec: 180\n")
        f.write("  cooldown_sec: 300\n  tick_interval_sec: 15\n  engagement_threshold: 20\n")

    config_data = {
        "llm": {"base_url": "https://api.moonshot.cn/v1", "api_key": "sk-mysupersecretkey"},
        "viewer": {"min_active": 3, "max_active": 8, "entry_interval_sec": 180,
                    "cooldown_sec": 300, "tick_interval_sec": 15, "engagement_threshold": 20},
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        f.write("llm:\n  base_url: https://api.moonshot.cn/v1\n  api_key: sk-mysupersecretkey\n")
        f.write("viewer:\n  min_active: 3\n  max_active: 8\n  entry_interval_sec: 180\n")
        f.write("  cooldown_sec: 300\n  tick_interval_sec: 15\n  engagement_threshold: 20\n")

    with patch.object(main_module, "CONFIG_PATH", config_path), \
         patch.object(main_module, "CONFIG_DEFAULT_PATH", default_path):
        yield


def test_get_config_returns_masked_api_key():
    client = TestClient(app)
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm"]["base_url"] == "https://api.moonshot.cn/v1"
    assert data["llm"]["api_key"] == "sk-m****key"
    assert data["viewer"]["min_active"] == 3


def test_update_config_persists():
    client = TestClient(app)
    resp = client.post("/api/config", json={
        "llm": {"base_url": "https://new-url.com/v1", "api_key": "sk-newkey12345"},
        "viewer": {"min_active": 5, "max_active": 10},
    })
    assert resp.status_code == 200

    # Verify written to file
    from backend.main import CONFIG_PATH, _read_config_yaml
    raw = _read_config_yaml()
    assert raw["llm"]["base_url"] == "https://new-url.com/v1"
    assert raw["llm"]["api_key"] == "sk-newkey12345"
    assert raw["viewer"]["min_active"] == 5
    assert raw["viewer"]["max_active"] == 10


def test_update_config_skips_masked_api_key():
    client = TestClient(app)
    # Submit masked key -> should NOT overwrite the real key
    resp = client.post("/api/config", json={
        "llm": {"api_key": "sk-m****key"},
    })
    assert resp.status_code == 200

    from backend.main import CONFIG_PATH, _read_config_yaml
    raw = _read_config_yaml()
    assert raw["llm"]["api_key"] == "sk-mysupersecretkey"


def test_reset_config_restores_defaults():
    client = TestClient(app)
    # First change something
    client.post("/api/config", json={"viewer": {"min_active": 99}})
    # Then reset
    resp = client.post("/api/config/reset")
    assert resp.status_code == 200

    from backend.main import CONFIG_PATH, _read_config_yaml
    raw = _read_config_yaml()
    assert raw["viewer"]["min_active"] == 3
    assert raw["llm"]["base_url"] == "https://default.com/v1"


def test_reset_config_missing_default_returns_error():
    import backend.main as main_module
    from pathlib import Path

    with patch.object(main_module, "CONFIG_DEFAULT_PATH", Path("/nonexistent/default.yaml")):
        client = TestClient(app)
        resp = client.post("/api/config/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
```

- [ ] **Step 7: Run tests to verify they fail**

```bash
uv run pytest tests/test_config_api.py -v
```
Expected: 5 tests found, at least 4 fail (import errors, missing endpoints).

- [ ] **Step 8: Add import for yaml at top of backend/main.py**

Add after the existing imports (around line 14):

```python
import shutil
import yaml
from pathlib import Path
```

Note: `Path` is already imported at line 14 in the original file. Only add `shutil` and `yaml` if missing.

- [ ] **Step 9: Run tests to verify they pass**

```bash
uv run pytest tests/test_config_api.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 10: Run existing tests to verify no regression**

```bash
uv run pytest tests/ -v
```
Expected: all existing tests still PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/main.py tests/test_config_api.py
git commit -m "feat: add /api/config endpoints for frontend config page"
```

---

### Task 4: Enable uvicorn reload with config.yaml watch

**Files:**
- Modify: `backend/main.py`

Change the `__main__` block to use reload mode watching config.yaml.

- [ ] **Step 1: Update the uvicorn.run call**

Replace the existing `uvicorn.run(...)` block (lines 275-281):

```python
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config.host,
        port=config.port,
        reload=True,
        reload_includes=["config.yaml"],
    )
```

- [ ] **Step 2: Run tests to verify**

```bash
uv run pytest tests/ -v
```
Expected: all tests still PASS (reload doesn't affect tests).

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: enable uvicorn reload watching config.yaml"
```

---

### Task 5: Frontend config page HTML

**Files:**
- Create: `frontend/config.html`

- [ ] **Step 1: Create config.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="style.css">
  <title>系统配置</title>
</head>
<body>
  <div id="config-container">
    <div id="config-header">
      <span>系统配置</span>
      <a href="/" class="nav-link">← 返回直播间</a>
    </div>

    <div id="config-body">
      <div class="config-group">
        <div class="group-title">LLM 连接</div>
        <div class="config-field">
          <label for="llm-base-url">Base URL</label>
          <input id="llm-base-url" type="text" placeholder="https://api.moonshot.cn/v1">
        </div>
        <div class="config-field">
          <label for="llm-api-key">API Key</label>
          <input id="llm-api-key" type="password" placeholder="sk-...">
        </div>
      </div>

      <div class="config-group">
        <div class="group-title">观众参数</div>
        <div class="config-field">
          <label for="viewer-min-active">最小活跃观众数</label>
          <input id="viewer-min-active" type="number" min="0" max="20">
        </div>
        <div class="config-field">
          <label for="viewer-max-active">最大活跃观众数</label>
          <input id="viewer-max-active" type="number" min="1" max="50">
        </div>
        <div class="config-field">
          <label for="viewer-entry-interval">入场间隔 (秒)</label>
          <input id="viewer-entry-interval" type="number" min="10" max="600">
        </div>
        <div class="config-field">
          <label for="viewer-cooldown">冷却时间 (秒)</label>
          <input id="viewer-cooldown" type="number" min="10" max="3600">
        </div>
        <div class="config-field">
          <label for="viewer-tick-interval">Tick 间隔 (秒)</label>
          <input id="viewer-tick-interval" type="number" min="3" max="120">
        </div>
        <div class="config-field">
          <label for="viewer-engagement">弹幕触发阈值</label>
          <input id="viewer-engagement" type="number" min="1" max="100">
        </div>
      </div>

      <div id="config-actions">
        <button id="btn-save-config" class="btn-primary">保存</button>
        <button id="btn-reset-config" class="btn-secondary">恢复默认</button>
      </div>

      <div id="config-status" class="status-hidden"></div>
    </div>
  </div>
  <script src="config.js?v=20260607"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/config.html
git commit -m "feat: add config page HTML"
```

---

### Task 6: Frontend config page JS logic

**Files:**
- Create: `frontend/config.js`

- [ ] **Step 1: Write config.js**

```javascript
const CONFIG_API = '/api/config';

document.addEventListener('DOMContentLoaded', async () => {
  const statusEl = document.getElementById('config-status');
  const btnSave = document.getElementById('btn-save-config');
  const btnReset = document.getElementById('btn-reset-config');

  function showStatus(msg, type) {
    statusEl.textContent = msg;
    statusEl.className = type === 'error' ? 'status-error' : type === 'success' ? 'status-success' : 'status-hidden';
    if (type !== 'error') {
      setTimeout(() => { statusEl.className = 'status-hidden'; }, 5000);
    }
  }

  async function loadConfig() {
    try {
      const resp = await fetch(CONFIG_API);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      document.getElementById('llm-base-url').value = data.llm.base_url || '';
      document.getElementById('llm-api-key').value = data.llm.api_key || '';
      document.getElementById('viewer-min-active').value = data.viewer.min_active;
      document.getElementById('viewer-max-active').value = data.viewer.max_active;
      document.getElementById('viewer-entry-interval').value = data.viewer.entry_interval_sec;
      document.getElementById('viewer-cooldown').value = data.viewer.cooldown_sec;
      document.getElementById('viewer-tick-interval').value = data.viewer.tick_interval_sec;
      document.getElementById('viewer-engagement').value = data.viewer.engagement_threshold;
    } catch (err) {
      showStatus('加载配置失败: ' + err.message, 'error');
    }
  }

  async function saveConfig() {
    btnSave.disabled = true;
    showStatus('保存中...', '');
    try {
      const payload = {
        llm: {
          base_url: document.getElementById('llm-base-url').value.trim(),
          api_key: document.getElementById('llm-api-key').value.trim(),
        },
        viewer: {
          min_active: parseInt(document.getElementById('viewer-min-active').value) || 3,
          max_active: parseInt(document.getElementById('viewer-max-active').value) || 8,
          entry_interval_sec: parseInt(document.getElementById('viewer-entry-interval').value) || 180,
          cooldown_sec: parseInt(document.getElementById('viewer-cooldown').value) || 300,
          tick_interval_sec: parseInt(document.getElementById('viewer-tick-interval').value) || 15,
          engagement_threshold: parseInt(document.getElementById('viewer-engagement').value) || 20,
        },
      };
      const resp = await fetch(CONFIG_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await resp.json();
      if (result.status === 'ok') {
        showStatus('保存成功，服务即将重启...', 'success');
        // Service will restart via uvicorn reload; reconnect after delay
        setTimeout(() => {
          showStatus('服务重启中，请稍候...', '');
          location.reload();
        }, 3000);
      } else {
        showStatus('保存失败: ' + (result.message || '未知错误'), 'error');
      }
    } catch (err) {
      showStatus('保存失败: ' + err.message, 'error');
    } finally {
      btnSave.disabled = false;
    }
  }

  async function resetConfig() {
    if (!confirm('确定恢复默认配置吗？当前配置将被覆盖。')) return;
    btnReset.disabled = true;
    showStatus('恢复中...', '');
    try {
      const resp = await fetch('/api/config/reset', { method: 'POST' });
      const result = await resp.json();
      if (result.status === 'ok') {
        showStatus('已恢复默认，服务即将重启...', 'success');
        setTimeout(() => {
          showStatus('服务重启中，请稍候...', '');
          location.reload();
        }, 3000);
      } else {
        showStatus('恢复失败: ' + (result.message || '未知错误'), 'error');
      }
    } catch (err) {
      showStatus('恢复失败: ' + err.message, 'error');
    } finally {
      btnReset.disabled = false;
    }
  }

  btnSave.addEventListener('click', saveConfig);
  btnReset.addEventListener('click', resetConfig);

  await loadConfig();
});
```

- [ ] **Step 2: Commit**

```bash
git add frontend/config.js
git commit -m "feat: add config page JS logic"
```

---

### Task 7: Add config page styles

**Files:**
- Modify: `frontend/style.css`

- [ ] **Step 1: Append config page styles to style.css (at end of file)**

```css
/* ── Config page ── */

#config-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: rgba(0, 0, 0, 0.85);
  border-radius: 8px;
  overflow: hidden;
}

#config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 15px;
  flex-shrink: 0;
}

.nav-link {
  color: #4FC3F7;
  text-decoration: none;
  font-size: 13px;
}

.nav-link:hover {
  text-decoration: underline;
}

#config-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.config-group {
  margin-bottom: 20px;
}

.group-title {
  color: #aaa;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 6px;
}

.config-field {
  margin-bottom: 12px;
}

.config-field label {
  display: block;
  color: #ccc;
  font-size: 13px;
  margin-bottom: 4px;
}

.config-field input {
  width: 100%;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #e0e0e0;
  padding: 7px 10px;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}

.config-field input:focus {
  border-color: rgba(79, 195, 247, 0.5);
}

#config-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.btn-primary {
  flex: 1;
  background: rgba(79, 195, 247, 0.25);
  border: 1px solid rgba(79, 195, 247, 0.35);
  color: #4FC3F7;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover {
  background: rgba(79, 195, 247, 0.35);
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: default;
}

.btn-secondary {
  flex: 1;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #e0e0e0;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

.btn-secondary:disabled {
  opacity: 0.4;
  cursor: default;
}

#config-status {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  text-align: center;
}

.status-hidden { display: none; }
.status-success {
  display: block;
  background: rgba(129, 199, 132, 0.15);
  color: #81C784;
  border: 1px solid rgba(129, 199, 132, 0.3);
}
.status-error {
  display: block;
  background: rgba(255, 138, 101, 0.15);
  color: #FF8A65;
  border: 1px solid rgba(255, 138, 101, 0.3);
}

#config-body::-webkit-scrollbar { width: 6px; }
#config-body::-webkit-scrollbar-track { background: transparent; }
#config-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 3px; }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/style.css
git commit -m "feat: add config page styles"
```

---

### Task 8: Verify everything works end-to-end

**Files:**
- Run tests

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -v
```
Expected: all tests PASS (existing + new config API tests).

- [ ] **Step 2: Manual smoke test (optional)**

```bash
uv run python -m backend.main
```
Then:
- Visit `http://localhost:8765/config.html` — config page should load
- Visit `http://localhost:8765/` — danmaku display page should load
- Change a value and click "保存" — service should restart, page should reload
- Click "恢复默认" — config should reset, service should restart
