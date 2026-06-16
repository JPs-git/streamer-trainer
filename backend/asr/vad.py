from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import onnxruntime

from backend.asr.frame import AudioFrame

logger = logging.getLogger(__name__)

VAD_WINDOW_SIZE = 512
VAD_STATE_DIM = 64


@dataclass
class SpeechSegment:
    audio: np.ndarray
    start_time: float
    end_time: float
    final: bool = False


@dataclass
class TranscriptionResult:
    text: str
    start_time: float
    end_time: float


class VADEngine:
    def __init__(self, model_path: str = "", vad_threshold: float = 0.5,
                 silence_duration_ms: int = 600):
        self.model_path = model_path
        self.vad_threshold = vad_threshold
        self.silence_duration_ms = silence_duration_ms
        self._session = None
        self._state: str = "silence"
        self._speech_start_ms: int = 0
        self._silence_start_ms: int = 0
        self._h = np.zeros((2, 1, VAD_STATE_DIM), dtype=np.float32)
        self._c = np.zeros((2, 1, VAD_STATE_DIM), dtype=np.float32)

    def _ensure_model(self):
        if self._session is None:
            self._session = onnxruntime.InferenceSession(
                self.model_path, providers=["CPUExecutionProvider"],
            )

    def reset(self):
        self._state = "silence"
        self._speech_start_ms = 0
        self._silence_start_ms = 0
        self._h.fill(0)
        self._c.fill(0)

    def _get_speech_prob(self, audio: np.ndarray) -> float:
        num_samples = len(audio)
        probs = []
        for start in range(0, num_samples, VAD_WINDOW_SIZE):
            chunk = audio[start:start + VAD_WINDOW_SIZE]
            if len(chunk) < VAD_WINDOW_SIZE:
                chunk = np.pad(chunk, (0, VAD_WINDOW_SIZE - len(chunk)), "constant")
            inp = chunk.astype(np.float32).reshape(1, -1)
            out = self._session.run(None, {
                "x": inp,
                "h": self._h,
                "c": self._c,
            })
            self._h = out[1]
            self._c = out[2]
            probs.append(float(out[0][0, 0]))
        return float(np.max(probs))

    def process(self, frame: AudioFrame) -> Optional[SpeechSegment]:
        self._ensure_model()
        if not frame.payload:
            return None

        audio = np.frombuffer(frame.payload, dtype=np.int16).astype(np.float32) / 32768.0
        prob = self._get_speech_prob(audio)
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
            frame_end_s = frame_end_ms / 1000.0
            return SpeechSegment(
                audio=audio,
                start_time=frame.timestamp_ms / 1000.0,
                end_time=frame_end_s,
                final=False,
            )
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
