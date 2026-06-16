from __future__ import annotations

import logging

from backend.asr.onnx.model import SenseVoiceONNX
from backend.asr.vad import SpeechSegment, TranscriptionResult

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_path: str, tokens_path: str, num_threads: int = 4,
                 language: str = "auto", use_itn: bool = True):
        self.model_path = model_path
        self.tokens_path = tokens_path
        self.num_threads = num_threads
        self.language = language
        self.use_itn = use_itn
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            self._model = SenseVoiceONNX(
                model_path=self.model_path,
                tokens_path=self.tokens_path,
                num_threads=self.num_threads,
                language=self.language,
                use_itn=self.use_itn,
            )

    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult:
        self._ensure_model()
        return await self._model.transcribe(segment)
