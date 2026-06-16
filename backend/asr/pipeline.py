from __future__ import annotations
import asyncio
import logging
from typing import Callable, Optional

from backend.asr.source import AudioSource, FileAudioSource, WSAudioSource
from backend.asr.vad import VADEngine
from backend.asr.buffer import AudioBuffer
from backend.asr.transcriber import Transcriber
from backend.asr.vad import TranscriptionResult

logger = logging.getLogger(__name__)


class ASRPipeline:
    def __init__(self, source: AudioSource, vad: VADEngine,
                 buffer: AudioBuffer, transcriber: Transcriber):
        self.source = source
        self.vad = vad
        self.buffer = buffer
        self.transcriber = transcriber

    async def run(self, callback: Callable[[TranscriptionResult], None]):
        async for frame in self.source:
            segment = self.vad.process(frame)
            if segment is not None:
                completed = self.buffer.add(segment)
                if completed is not None:
                    result = await self.transcriber.transcribe(completed)
                    if result.text.strip():
                        await _invoke(callback, result)

        remaining = self.buffer.flush()
        if remaining is not None and remaining.audio.size > 0:
            result = await self.transcriber.transcribe(remaining)
            if result.text.strip():
                await _invoke(callback, result)


async def _invoke(callback, result):
    r = callback(result)
    if asyncio.iscoroutine(r):
        await r
