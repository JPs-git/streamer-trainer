"""端到端实时麦克风测试：麦克风 → /audio WS → ASR → timeline → scheduler → /danmaku WS

用法：
    uv run python scripts/test_end_to_end_mic.py

依赖后端已启动（uv run python -m backend.main）。
"""

import asyncio
import json
import logging
from pathlib import Path
import queue as thread_queue
import signal
import sys
import time

# 将项目根加入 sys.path，使 backend 模块可导入
_project_root = (Path(__file__).resolve().parent.parent)
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import sounddevice as sd
import websockets

from backend.asr.frame import AudioFrame, encode_frame

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_DURATION_MS = 100
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 1600

C = {
    "reset": "\033[0m",
    "green": "\033[32m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "bold": "\033[1m",
}

log = logging.getLogger("mic_test")


def colorize(text: str, color: str) -> str:
    return f"{C[color]}{text}{C['reset']}"


def format_msg(msg: dict) -> str | None:
    t = msg.get("type", "")
    if t == "danmaku":
        return f"  {colorize(msg['name'], 'green')}: {msg['text']}"
    if t == "streamer":
        return f"  {colorize('[ASR]', 'cyan')} {msg['text']}"
    if t == "system":
        icon = {"enter": "→", "leave": "←"}.get(msg.get("action", ""), "•")
        return f"  {colorize(icon, 'gray')} {colorize(msg['name'], 'gray')} {msg.get('action', '')}"
    if t == "status":
        return (
            f"  {colorize('[观众]', 'yellow')}"
            f" 活跃: {msg.get('active_count', 0)}"
            f" 上限: {msg.get('max_active', '?')}"
        )
    return None


async def audio_sender(
    ws_url: str,
    audio_q: thread_queue.Queue,
    stop: asyncio.Event,
):
    loop = asyncio.get_running_loop()
    frame_index = 0
    last_log = 0

    async with websockets.connect(ws_url, ping_interval=None) as ws:
        log.info("Connected to /audio")
        while not stop.is_set():
            try:
                pcm = await loop.run_in_executor(
                    None, lambda: audio_q.get(timeout=1.0)
                )

                frame = AudioFrame(
                    payload=pcm,
                    timestamp_ms=frame_index * FRAME_DURATION_MS,
                    sample_rate=SAMPLE_RATE,
                    channels=CHANNELS,
                )
                await ws.send(encode_frame(frame))
                frame_index += 1

                # Log every 10 frames (1 second)
                if frame_index - last_log >= 10:
                    amp = max(abs(v) for v in memoryview(pcm).cast("h"))
                    log.info(
                        "Sent %d frames | audio level: %d",
                        frame_index, amp,
                    )
                    last_log = frame_index

            except thread_queue.Empty:
                continue
            except Exception as e:
                log.error("Audio send error: %s", e)
                break


async def danmaku_receiver(ws_url: str, stop: asyncio.Event):
    async with websockets.connect(ws_url, ping_interval=None) as ws:
        log.info("Connected to /danmaku")

        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                msg = json.loads(raw)
                line = format_msg(msg)
                if line:
                    print(line)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error("Danmaku error: %s", e)
                break


async def control_heartbeat(ws_url: str, stop: asyncio.Event):
    async with websockets.connect(ws_url, ping_interval=None) as ws:
        log.info("Connected to /control")
        while not stop.is_set():
            try:
                await ws.send(json.dumps({"action": "ping"}))
                await asyncio.wait_for(ws.recv(), timeout=10.0)
            except Exception as e:
                log.warning("Control heartbeat: %s", e)
                break
            await asyncio.sleep(15)


def mic_callback(indata, frames, time_info, status, audio_q: thread_queue.Queue):
    if status:
        log.warning("Mic status: %s", status)
    try:
        audio_q.put_nowait(indata.tobytes())
    except thread_queue.Full:
        pass


async def main():
    host, port = "localhost", 8765
    base = f"ws://{host}:{port}"

    audio_q: thread_queue.Queue = thread_queue.Queue(maxsize=64)
    stop = asyncio.Event()

    # 验证麦克风
    try:
        info = sd.query_devices(kind="input")
        log.info("Input device: %s", info["name"])
    except Exception as e:
        log.error("No input device found: %s", e)
        log.error("Try: export PULSE_SERVER=/mnt/wslg/PulseServer")
        sys.exit(1)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(audio_sender(f"{base}/audio", audio_q, stop))
        tg.create_task(danmaku_receiver(f"{base}/danmaku", stop))
        tg.create_task(control_heartbeat(f"{base}/control", stop))

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=FRAME_SIZE,
            callback=lambda i, f, t, s: mic_callback(i, f, t, s, audio_q),
        )
        stream.start()

        print(f"\n{C['bold']}=== 实时麦克风测试 ==={C['reset']}")
        print(f"  后端: {base}")
        print(f"  每 1 秒显示音频电平 | ASR 结果同步到 timeline 并打印")
        print(f"  {C['gray']}Ctrl+C 退出{C['reset']}\n")

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        loop.add_signal_handler(signal.SIGINT, fut.set_exception, KeyboardInterrupt)
        try:
            await fut
        except KeyboardInterrupt:
            pass
        finally:
            loop.remove_signal_handler(signal.SIGINT)

        print()
        log.info("Shutting down...")
        stop.set()
        stream.stop()
        stream.close()

    log.info("Done")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
