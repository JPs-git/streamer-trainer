from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from backend.asr.frame import AudioFrame

logger = logging.getLogger(__name__)


@dataclass
class SpeechSegment:
    audio: np.ndarray
    start_time: float
    end_time: float
    final: bool = False


class VADEngine:
    def __init__(self, vad_threshold: float = 0.5, silence_duration_ms: int = 600):
        self.vad_threshold = vad_threshold
        self.silence_duration_ms = silence_duration_ms
        self._model = None
        self._state: str = "silence"
        self._speech_start_ms: int = 0
        self._silence_start_ms: int = 0

    def _ensure_model(self):
        if self._model is None:
            from silero_vad import load_silero_vad

            self._model = load_silero_vad()

    def reset(self):
        self._state = "silence"
        self._speech_start_ms = 0
        self._silence_start_ms = 0

    def process(self, frame: AudioFrame) -> Optional[SpeechSegment]:
        self._ensure_model()
        if not frame.payload:
            return None

        audio = np.frombuffer(frame.payload, dtype=np.int16).astype(np.float32) / 32768.0
        prob = self._model(audio, frame.sample_rate).item()
        is_speech = prob >= self.vad_threshold
        frame_end_ms = frame.timestamp_ms + int(len(audio) / frame.sample_rate * 1000)

        if self._state == "silence":
            if is_speech:
                self._state = "speech"
                self._speech_start_ms = frame.timestamp_ms
                self._silence_start_ms = 0
                return SpeechSegment(
                    audio=audio,
                    start_time=frame.timestamp_ms / 1000.0,
                    end_time=frame_end_ms / 1000.0,
                    final=False,
                )
            return None

        if is_speech:
            self._silence_start_ms = 0
            return None
        else:
            if self._silence_start_ms == 0:
                self._silence_start_ms = frame.timestamp_ms
            elapsed = frame_end_ms - self._silence_start_ms
            if elapsed >= self.silence_duration_ms:
                self._state = "silence"
                return SpeechSegment(
                    audio=audio,
                    start_time=self._speech_start_ms / 1000.0,
                    end_time=frame_end_ms / 1000.0,
                    final=True,
                )
            return None
