from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.asr.frame import AudioFrame


def _vad_output(prob: float):
    return [
        np.array([[prob]], dtype=np.float32),
        np.zeros((2, 1, 64), dtype=np.float32),
        np.zeros((2, 1, 64), dtype=np.float32),
    ]


@pytest.fixture(autouse=True)
def mock_ort():
    with patch("onnxruntime.InferenceSession") as m:
        session = MagicMock()
        session.run.return_value = _vad_output(0.1)
        m.return_value = session
        yield m


def _frame(audio: np.ndarray, ts: int = 0) -> AudioFrame:
    return AudioFrame(
        payload=(audio * 32767).astype(np.int16).tobytes(),
        timestamp_ms=ts,
        sample_rate=16000,
        channels=1,
    )


def _silence(dur_s: float, sr: int = 16000) -> np.ndarray:
    return np.zeros(int(dur_s * sr), dtype=np.float32)


def _speech(dur_s: float, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0, dur_s, int(dur_s * sr), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * 440 * t)


def test_vad_silence_returns_none(mock_ort):
    from backend.asr.vad import VADEngine

    mock_ort.return_value.run.return_value = _vad_output(0.1)
    vad = VADEngine(model_path="dummy.onnx", vad_threshold=0.5)
    result = vad.process(_frame(_silence(0.5)))
    assert result is None


def test_vad_speech_returns_nonfinal_segment(mock_ort):
    from backend.asr.vad import VADEngine

    mock_ort.return_value.run.return_value = _vad_output(0.9)
    vad = VADEngine(model_path="dummy.onnx", vad_threshold=0.5)
    result = vad.process(_frame(_speech(0.5)))
    assert result is not None
    assert not result.final


def test_vad_speech_ended_returns_final(mock_ort):
    from backend.asr.vad import VADEngine

    vad = VADEngine(model_path="dummy.onnx", vad_threshold=0.5, silence_duration_ms=200)
    mock_ort.return_value.run.return_value = _vad_output(0.9)
    vad.process(_frame(_speech(0.3), ts=1000))
    mock_ort.return_value.run.return_value = _vad_output(0.1)
    sil1 = vad.process(_frame(_silence(0.1), ts=1300))
    assert sil1 is None
    sil2 = vad.process(_frame(_silence(0.1), ts=1400))
    assert sil2 is not None
    assert sil2.final


def test_vad_continuous_speech_returns_segment(mock_ort):
    from backend.asr.vad import VADEngine

    mock_ort.return_value.run.return_value = _vad_output(0.9)
    vad = VADEngine(model_path="dummy.onnx")
    first = vad.process(_frame(_speech(0.3), ts=0))
    assert first is not None
    assert not first.final
    result = vad.process(_frame(_speech(0.3), ts=300))
    assert result is not None
    assert not result.final


def test_vad_reset(mock_ort):
    from backend.asr.vad import VADEngine

    mock_ort.return_value.run.return_value = _vad_output(0.9)
    vad = VADEngine(model_path="dummy.onnx")
    vad.process(_frame(_speech(0.3), ts=0))
    vad.reset()
    assert vad._state == "silence"


def test_vad_below_threshold(mock_ort):
    from backend.asr.vad import VADEngine

    mock_ort.return_value.run.return_value = _vad_output(0.3)
    vad = VADEngine(model_path="dummy.onnx", vad_threshold=0.5)
    assert vad.process(_frame(_speech(0.3))) is None
