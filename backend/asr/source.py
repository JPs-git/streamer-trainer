from __future__ import annotations

import asyncio
import logging
import struct
from abc import ABC, abstractmethod
from typing import AsyncIterator

from fastapi import WebSocketDisconnect

from backend.asr.frame import FRAME_HEADER_SIZE, MAGIC, AudioFrame, decode_frame

logger = logging.getLogger(__name__)


class AudioSource(ABC):
    @abstractmethod
    def __aiter__(self) -> AsyncIterator[AudioFrame]:
        ...


class FileAudioSource(AudioSource):
    def __init__(self, path: str):
        self.path = path

    async def __aiter__(self):
        loop = asyncio.get_running_loop()
        with open(self.path, "rb") as f:
            while True:
                header = await loop.run_in_executor(None, f.read, FRAME_HEADER_SIZE)
                if not header or len(header) < FRAME_HEADER_SIZE:
                    break
                magic, payload_len, *_ = struct.unpack("<2sIIHBB", header)
                if magic != MAGIC:
                    raise ValueError(f"Invalid magic: {magic.hex()}")
                payload = await loop.run_in_executor(None, f.read, payload_len)
                if len(payload) < payload_len:
                    break
                yield decode_frame(header + payload)


class WSAudioSource(AudioSource):
    def __init__(self, ws):
        self._ws = ws

    async def __aiter__(self):
        try:
            while True:
                data = await self._ws.receive_bytes()
                yield decode_frame(data)
        except (WebSocketDisconnect, ConnectionResetError, OSError, StopAsyncIteration):
            pass
