from __future__ import annotations
import asyncio
import logging
import os
import shutil
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path

# ── 防双加载 ──────────────────────────────────────────
# python -m backend.main 将模块注册为 __main__ 而非 backend.main，
# 后续 uvicorn.run("backend.main:app") 会重新导入导致所有模块级
# 代码执行两次（日志 handler 重复、FastAPI 重复、单例失效）。
_own_key = "backend.main"
if __name__ == "__main__" and _own_key not in sys.modules:
    sys.modules[_own_key] = sys.modules["__main__"]

# ── 日志 ─────────────────────────────────────────────
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")

root = logging.getLogger()
# 幂等：只添加一次，避免双加载后翻倍
if not any(isinstance(h, logging.StreamHandler) and h.formatter._fmt == _fmt._fmt for h in root.handlers):
    _console = logging.StreamHandler()
    _console.setLevel(logging.INFO)
    _console.setFormatter(_fmt)
    root.addHandler(_console)

if not any(isinstance(h, logging.FileHandler) and h.baseFilename.endswith("app.log") for h in root.handlers):
    _file = logging.FileHandler(str(_LOG_DIR / "app.log"), mode="a", encoding="utf-8")
    _file.setLevel(logging.DEBUG)
    _file.setFormatter(_fmt)
    root.addHandler(_file)

# ── LLM 交互专用日志 ────────────────────────────────────
_llm_trace = logging.getLogger("llm_trace")
_llm_trace.propagate = False
if not _llm_trace.handlers:
    _llm_handler = logging.FileHandler(str(_LOG_DIR / "llm.log"), mode="a", encoding="utf-8")
    _llm_handler.setLevel(logging.DEBUG)
    _llm_handler.setFormatter(logging.Formatter(
        "%(asctime)s\n%(message)s\n", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _llm_trace.addHandler(_llm_handler)
    _llm_trace.setLevel(logging.DEBUG)

root.setLevel(logging.DEBUG)

from backend.config import config
from backend.asr.pipeline import ASRPipeline
from backend.asr.source import WSAudioSource
from backend.asr.vad import VADEngine
from backend.asr.buffer import AudioBuffer
from backend.asr.transcriber import Transcriber
from backend.asr.output import OutputHandler
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler
from backend.llm.client import LLMClient
from backend.llm.generator import Generator


class StreamerTrainerApp:
    def __init__(self):
        self.asr_transcriber = Transcriber(
            model_path=config.asr_model_path,
            tokens_path=config.asr_tokens_path,
            num_threads=config.asr_num_threads,
            language=config.asr_language,
            use_itn=config.asr_use_itn,
        )
        self.llm = LLMClient(
            provider=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            selector_model=config.llm_selector_model,
            base_url=config.llm_base_url,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens,
            timeout=config.llm_timeout,
        )
        self.generator = Generator()
        self.viewer_manager = ViewerManager(
            max_active=config.viewer_max_active,
            min_active=config.viewer_min_active,
        )
        self.streamer_timeline: list[dict] = []
        self.room_chat_log: list[dict] = []
        self.danmaku_clients: set[WebSocket] = set()
        self.scheduler = ViewerScheduler(
            manager=self.viewer_manager,
            llm=self.llm,
            generator=self.generator,
            tick_interval=config.viewer_tick_interval_sec,
            churn_per_tick=config.viewer_churn_per_tick,
            guider_ratio=config.viewer_guider_ratio,
            broadcast_system=self.broadcast_system,
            broadcast_danmaku=self.broadcast_danmaku,
            broadcast_status=self.broadcast_status,
            streamer_timeline=self.streamer_timeline,
            room_chat_log=self.room_chat_log,
        )

    async def broadcast_system(self, action: str, name: str, viewer_id: str):
        msg = {"type": "system", "action": action, "name": name, "id": viewer_id}
        dead: set[WebSocket] = set()
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.danmaku_clients -= dead

    async def broadcast_danmaku(self, msg: dict):
        dead: set[WebSocket] = set()
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.danmaku_clients -= dead

    async def broadcast_status(self, msg: dict):
        dead: set[WebSocket] = set()
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        self.danmaku_clients -= dead


class _LazyAppState:
    _instance: Optional[StreamerTrainerApp] = None

    def __getattr__(self, name):
        if _LazyAppState._instance is None:
            _LazyAppState._instance = StreamerTrainerApp()
        return getattr(_LazyAppState._instance, name)


logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting scheduler...")
    task = asyncio.create_task(app_state.scheduler.start())
    logger.info("App ready")
    yield
    logger.info("Shutting down scheduler...")
    app_state.scheduler.stop()
    task.cancel()
    logger.info("Shutdown complete")


app_state: StreamerTrainerApp = _LazyAppState()
app = FastAPI(lifespan=lifespan)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
CONFIG_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.default.yaml"


def _read_config_yaml() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _write_config_yaml(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


class LLMConfigModel(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class ViewerConfigModel(BaseModel):
    min_active: Optional[int] = Field(default=None, ge=0, le=100)
    max_active: Optional[int] = Field(default=None, ge=1, le=200)
    churn_per_tick: Optional[int] = Field(default=None, ge=1, le=20)
    guider_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tick_interval_sec: Optional[int] = Field(default=None, ge=1, le=300)


class ConfigUpdate(BaseModel):
    llm: Optional[LLMConfigModel] = None
    viewer: Optional[ViewerConfigModel] = None


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
            "churn_per_tick": viewer.get("churn_per_tick", 5),
            "guider_ratio": viewer.get("guider_ratio", 0.3),
            "tick_interval_sec": viewer.get("tick_interval_sec", 15),
        },
    }


@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    raw = _read_config_yaml()

    if body.llm is not None:
        if "llm" not in raw:
            raw["llm"] = {}
        if body.llm.base_url is not None:
            raw["llm"]["base_url"] = body.llm.base_url
        if body.llm.api_key is not None:
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


@app.post("/api/config/reset")
async def reset_config():
    if not CONFIG_DEFAULT_PATH.is_file():
        return {"status": "error", "message": "Default config file not found"}
    shutil.copy(str(CONFIG_DEFAULT_PATH), str(CONFIG_PATH))
    logger.info("Config reset to defaults via API, restarting...")
    return {"status": "ok", "message": "Config reset to defaults, restarting..."}


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    target = (FRONTEND_DIR / full_path).resolve()
    if not str(target).startswith(str(FRONTEND_DIR)):
        index = FRONTEND_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return FileResponse(str(index))
    if target.is_file():
        return FileResponse(str(target))
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return FileResponse(str(index))


@app.websocket("/audio")
async def audio_endpoint(ws: WebSocket):
    await ws.accept()
    source = WSAudioSource(ws)
    pipeline = ASRPipeline(
        source=source,
        vad=VADEngine(
            model_path=config.asr_vad_model_path,
            vad_threshold=config.vad_threshold,
            silence_duration_ms=config.silence_duration_ms,
        ),
        buffer=AudioBuffer(
            max_segment_duration=config.max_segment_duration,
        ),
        transcriber=app_state.asr_transcriber,
    )
    output = OutputHandler(
        timeline=app_state.streamer_timeline,
        chat_log=app_state.room_chat_log,
        broadcast=app_state.broadcast_danmaku,
    )
    try:
        await pipeline.run(callback=output.on_result)
    except WebSocketDisconnect:
        pass


@app.websocket("/danmaku")
async def danmaku_endpoint(ws: WebSocket):
    await ws.accept()
    app_state.danmaku_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        app_state.danmaku_clients.discard(ws)


@app.websocket("/control")
async def control_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass


class ControlAction(BaseModel):
    action: str


class DebugText(BaseModel):
    text: str


@app.post("/control/scheduler")
async def control_scheduler_endpoint(body: ControlAction):
    if body.action == "pause":
        app_state.scheduler.pause()
        logger.info("Scheduler paused via API")
        return {"status": "ok", "paused": True}
    elif body.action == "resume":
        app_state.scheduler.resume()
        logger.info("Scheduler resumed via API")
        return {"status": "ok", "paused": False}
    return {"status": "error", "message": f"unknown action: {body.action}"}


@app.post("/debug_text")
async def debug_text_endpoint(body: DebugText):
    """调试入口：传入文本追加到主播时间线，并广播到直播间。"""
    try:
        timestamp = int(time.time())
        app_state.streamer_timeline.append({"text": body.text, "offset": timestamp})
        app_state.room_chat_log.append({"type": "streamer", "name": "主播", "text": body.text, "offset": timestamp})
        if len(app_state.room_chat_log) > 200:
            app_state.room_chat_log[:50] = []
        logger.info("Timeline: + '%s' (total %d entries)", body.text, len(app_state.streamer_timeline))
        await app_state.broadcast_danmaku({
            "type": "streamer",
            "text": body.text,
            "timestamp": timestamp,
        })
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config.host,
        port=config.port,
        reload=True,
        reload_includes=["config.yaml"],
    )
