from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from backend.asr.vad import SpeechSegment

logger = logging.getLogger(__name__)


class AudioBuffer:
    def __init__(self, max_segment_duration: float = 10.0):
        self.max_segment_duration = max_segment_duration
        self._chunks: list[np.ndarray] = []
        self._start_time: float = 0.0

    def reset(self):
        self._chunks.clear()
        self._start_time = 0.0

    def add(self, segment: SpeechSegment) -> Optional[SpeechSegment]:
        if segment.audio.size == 0:
            return None

        if not self._chunks:
            self._start_time = segment.start_time

        self._chunks.append(segment.audio)
        total_duration = segment.end_time - self._start_time

        if segment.final:
            return self._build_segment()

        if total_duration >= self.max_segment_duration:
            return self._build_segment(final=True)

        return None

    def flush(self) -> Optional[SpeechSegment]:
        if not self._chunks:
            return None
        return self._build_segment()

    def _build_segment(self, final: bool = True) -> SpeechSegment:
        audio = np.concatenate(self._chunks) if len(self._chunks) > 1 else self._chunks[0]
        end_time = self._start_time + len(audio) / 16000.0
        segment = SpeechSegment(
            audio=audio,
            start_time=self._start_time,
            end_time=end_time,
            final=final,
        )
        self.reset()
        return segment
