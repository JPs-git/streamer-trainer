from __future__ import annotations
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from backend.config import config
from backend.asr import ASREngine
from backend.viewer.manager import ViewerManager
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
            timeout=config.llm_timeout,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens,
        )
        self.selector = Selector(model_name=config.llm_selector_model)
        self.generator = Generator(model_name=config.llm_model)
        self.viewer_manager = ViewerManager(
            max_active=config.viewer_max_active,
            min_active=config.viewer_min_active,
            cooldown_sec=config.viewer_cooldown_sec,
        )
        self.danmaku_clients: set[WebSocket] = set()

    async def broadcast_danmaku(self, message: dict):
        dead = set()
        print(f"[broadcast] sending to {len(self.danmaku_clients)} clients: "
              f"{message.get('text', '')[:40]}")
        for ws in self.danmaku_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        if dead:
            print(f"[broadcast] removed {len(dead)} dead clients")
        self.danmaku_clients -= dead


class _LazyAppState:
    _instance: Optional[StreamerTrainerApp] = None

    def __getattr__(self, name):
        if _LazyAppState._instance is None:
            _LazyAppState._instance = StreamerTrainerApp()
        return getattr(_LazyAppState._instance, name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()


async def _scheduler_loop():
    while True:
        app_state.viewer_manager.tick()
        await asyncio.sleep(30)


app_state: StreamerTrainerApp = _LazyAppState()  # type: ignore[assignment]
app = FastAPI(lifespan=lifespan)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # Prevent path traversal: ensure resolved path stays within FRONTEND_DIR
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
                    try:
                        await _process_asr_result(text)
                    except Exception:
                        pass
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


class DebugText(BaseModel):
    text: str


@app.post("/debug_text")
async def debug_text_endpoint(body: DebugText):
    """调试入口：直接传入文本触发 pipeline，结果通过 /danmaku WS 推送。"""
    try:
        await _process_asr_result(body.text)
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


async def _process_asr_result(text: str):
    timestamp = int(time.time())
    active = app_state.viewer_manager.get_active_viewers()
    print(f"[pipeline] active viewers: {len(active)}")
    for v in active:
        print(f"[pipeline]   {v.name} ({v.state})")

    for v in active:
        v.memory.add_streamer_log(text, timestamp)

    viewer_states = [
        {
            "id": v.viewer_id,
            "name": v.name,
            "personality": v.personality_type,
            "state": v.state,
            "summary": _build_viewer_summary(v),
        }
        for v in active
    ]

    selector_prompt = app_state.selector.build_prompt(text, viewer_states)
    print(f"[pipeline] selector prompt:\n{selector_prompt}")
    selector_raw = await app_state.llm.chat(
        system=Selector.SELECTOR_SYSTEM_PROMPT,
        user=selector_prompt,
        model=app_state.llm.selector_model,
    )
    print(f"[pipeline] selector raw response: {selector_raw}")
    selected = app_state.selector.parse_response(selector_raw)
    print(f"[pipeline] parsed selection: {selected}")

    if not selected:
        print("[pipeline] no viewers selected, returning")
        return

    tasks = []
    for sel in selected:
        v = app_state.viewer_manager.get_viewer(sel["id"])
        if not v or v.state != "active":
            print(f"[pipeline] viewer {sel['id']} not available, skipping")
            continue
        tasks.append(_generate_for_viewer(v, text, sel.get("intent", "")))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    print(f"[pipeline] generation results: {sum(1 for r in results if r)}/{len(results)} non-null")
    for r in results:
        if r:
            await app_state.broadcast_danmaku(r)


async def _generate_for_viewer(
    v, current_asr: str, intent: str
) -> dict | None:
    prompt = app_state.generator.build_prompt(
        name=v.name,
        persona=v.persona,
        personality_type=v.personality_type,
        streamer_log=v.memory.streamer_log,
        my_danmaku=v.memory.my_danmaku,
        other_danmaku=v.memory.other_danmaku,
        relationships=v.memory.relationships,
        current_asr=current_asr,
    )
    prompt += f"\n\n[发言意图]\n{intent}"

    raw = await app_state.llm.chat(
        system=Generator.GENERATOR_SYSTEM_PROMPT,
        user=prompt,
    )
    print(f"[pipeline] generator raw for {v.name}: {raw}")
    text = app_state.generator.parse_danmaku(raw)
    if not text:
        print(f"[pipeline] generator returned empty for {v.name}")
        return None

    v.memory.add_my_danmaku(text, int(time.time()), "streamer")
    v.last_active = int(time.time())
    v.interaction_count += 1

    effect = "highlight" if v.personality_type == "aggressive" else "normal"
    return {
        "type": "danmaku",
        "id": v.viewer_id,
        "name": v.name,
        "text": text,
        "personality": v.personality_type,
        "effect": effect,
    }


def _build_viewer_summary(v) -> str:
    parts = []
    if v.entry_time:
        elapsed = (int(time.time()) - v.entry_time) // 60
        parts.append(f"看了{elapsed}分钟")
    if v.interaction_count > 0:
        parts.append(f"发过{v.interaction_count}条弹幕")
    if v.memory.my_danmaku:
        last = v.memory.my_danmaku[-1]["text"][:20]
        parts.append(f"上次说: {last}")
    return ", ".join(parts) if parts else "还没发过言"


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config.host,
        port=config.port,
        reload=False,
    )
