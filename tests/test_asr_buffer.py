from __future__ import annotations

import numpy as np
import pytest

from backend.asr.vad import SpeechSegment


@pytest.fixture
def buffer():
    from backend.asr.buffer import AudioBuffer

    return AudioBuffer(max_segment_duration=10.0)


def _seg(dur_s: float, start: float = 0.0, final: bool = False) -> SpeechSegment:
    n = int(dur_s * 16000)
    audio = np.zeros(n, dtype=np.float32)
    return SpeechSegment(audio=audio, start_time=start, end_time=start + dur_s, final=final)


def test_add_returns_none_during_speech(buffer):
    result = buffer.add(_seg(1.0, start=0.0, final=False))
    assert result is None


def test_add_returns_segment_on_final(buffer):
    buffer.add(_seg(1.0, start=0.0, final=False))
    result = buffer.add(_seg(0.5, start=1.0, final=True))
    assert result is not None
    assert result.final
    assert abs(result.start_time - 0.0) < 0.01
    assert abs(result.end_time - 1.5) < 0.1


def test_add_returns_none_when_empty(buffer):
    assert buffer.add(_seg(0, final=True)) is None


def test_max_duration_triggers_completion():
    from backend.asr.buffer import AudioBuffer

    buf = AudioBuffer(max_segment_duration=0.5)
    buf.add(_seg(0.3, start=0.0, final=False))
    result = buf.add(_seg(0.3, start=0.3, final=False))
    assert result is not None
    assert result.final
    assert abs(result.end_time - 0.6) < 0.1


def test_flush_returns_accumulated(buffer):
    buffer.add(_seg(1.0, start=0.0, final=False))
    result = buffer.flush()
    assert result is not None
    assert result.final
    assert abs(result.start_time - 0.0) < 0.01


def test_flush_empty(buffer):
    result = buffer.flush()
    assert result is None
