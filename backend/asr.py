from __future__ import annotations
import threading
import logging
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class ASREngine:
    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8", download_timeout: float = 30.0):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_timeout = download_timeout
        self._model: Optional[WhisperModel] = None
        self._error: Optional[str] = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is not None:
            return
        if self._error is not None:
            raise RuntimeError(self._error)
        with self._lock:
            if self._model is not None:
                return
            self._model = self._load_model()

    def _load_model(self) -> Optional[WhisperModel]:
        import os

        # Level 1: local cache only — sub-second if cached
        try:
            return WhisperModel(
                self.model_size, device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
        except OSError:
            logger.info("Whisper model '%s' not in cache, downloading...",
                        self.model_size)

        # Level 2: download with timeout
        original_timeout = os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT")
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(int(self.download_timeout))
        try:
            return WhisperModel(
                self.model_size, device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as e:
            msg = (f"Failed to download Whisper model '{self.model_size}': {e}. "
                   "Run `uv run python scripts/download_models.py` to pre-download.")
            logger.warning(msg)
            self._error = msg
            return None
        finally:
            if original_timeout is not None:
                os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = original_timeout
            else:
                os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)

    def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        self._ensure_model()
        if self._model is None:
            return ""
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(
            np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio_array,
                                             beam_size=1, language="zh")
        return " ".join(seg.text for seg in segments)
