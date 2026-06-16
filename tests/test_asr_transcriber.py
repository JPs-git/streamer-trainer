from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from backend.asr.vad import SpeechSegment, TranscriptionResult


@pytest.fixture(autouse=True)
def mock_sensevoice():
    with patch("backend.asr.transcriber.SenseVoiceONNX") as m:
        instance = MagicMock()

        async def fake_transcribe(segment):
            if segment.audio.size == 0:
                return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)
            return TranscriptionResult(text="你好世界", start_time=segment.start_time, end_time=segment.end_time)

        instance.transcribe = fake_transcribe
        m.return_value = instance
        yield m


def _segment(dur_s: float = 1.0) -> SpeechSegment:
    return SpeechSegment(
        audio=np.zeros(int(dur_s * 16000), dtype=np.float32),
        start_time=0.0,
        end_time=dur_s,
        final=True,
    )


@pytest.mark.asyncio
async def test_transcribe_returns_text():
    from backend.asr.transcriber import Transcriber

    t = Transcriber("dummy.onnx", "dummy.tokens")
    result = await t.transcribe(_segment())
    assert result.text == "你好世界"


@pytest.mark.asyncio
async def test_transcribe_lazy_loads_model():
    from backend.asr.transcriber import Transcriber

    t = Transcriber("dummy.onnx", "dummy.tokens")
    assert t._model is None
    await t.transcribe(_segment())
    assert t._model is not None


@pytest.mark.asyncio
async def test_transcribe_empty_audio():
    from backend.asr.transcriber import Transcriber

    t = Transcriber("dummy.onnx", "dummy.tokens")
    result = await t.transcribe(_segment(dur_s=0.0))
    assert result.text == ""


@pytest.mark.asyncio
async def test_transcribe_result_has_timestamps():
    from backend.asr.transcriber import Transcriber

    t = Transcriber("dummy.onnx", "dummy.tokens")
    result = await t.transcribe(_segment(2.0))
    assert result.start_time == 0.0
    assert result.end_time == 2.0
