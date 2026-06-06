from __future__ import annotations
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")

_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(_fmt)

_file = logging.FileHandler(str(_LOG_DIR / "app.log"), mode="a", encoding="utf-8")
_file.setLevel(logging.DEBUG)
_file.setFormatter(_fmt)

root = logging.getLogger()
root.setLevel(logging.DEBUG)
root.addHandler(_console)
root.addHandler(_file)

from backend.config import config
from backend.asr import ASREngine
from backend.viewer.manager import ViewerManager
from backend.viewer.scheduler import ViewerScheduler
from backend.llm.client import LLMClient
from backend.llm.selector import Selector
from backend.llm.generator import Generator


class StreamerTrainerApp:
    def __init__(self):
        self.asr = ASREngine(
            model_size=config.asr_model_size,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
            download_timeout=config.asr_download_timeout,
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
        self.selector = Selector()
        self.generator = Generator()
        self.viewer_manager = ViewerManager(
            max_active=config.viewer_max_active,
            min_active=config.viewer_min_active,
            cooldown_sec=config.viewer_cooldown_sec,
        )
        self.streamer_timeline: list[dict] = []
        self.danmaku_clients: set[WebSocket] = set()
        self.scheduler = ViewerScheduler(
            manager=self.viewer_manager,
            llm=self.llm,
            selector=self.selector,
            generator=self.generator,
            tick_interval=config.viewer_tick_interval_sec,
            entry_interval=config.viewer_entry_interval_sec,
            engagement_threshold=config.viewer_engagement_threshold,
            broadcast_system=self.broadcast_system,
            broadcast_danmaku=self.broadcast_danmaku,
            streamer_timeline=self.streamer_timeline,
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
    audio_buffer = bytearray()
    try:
        while True:
            data = await ws.receive_bytes()
            audio_buffer.extend(data)
            if len(audio_buffer) >= 32000:
                text = app_state.asr.transcribe(bytes(audio_buffer))
                audio_buffer.clear()
                if text.strip():
                    timestamp = int(time.time())
                    app_state.streamer_timeline.append({"text": text, "offset": timestamp})
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
        reload=False,
    )
