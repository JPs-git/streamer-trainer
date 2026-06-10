from __future__ import annotations
import logging
from typing import Callable, Optional

from backend.asr.source import AudioSource, FileAudioSource, WSAudioSource
from backend.asr.vad import VADEngine
from backend.asr.buffer import AudioBuffer
from backend.asr.transcriber import Transcriber, TranscriptionResult

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
                        await callback(result)
