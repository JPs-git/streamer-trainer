from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from backend.asr.vad import SpeechSegment


@pytest.fixture(autouse=True)
def mock_whisper():
    with patch("backend.asr.transcriber.WhisperModel") as m:
        instance = MagicMock()
        seg = MagicMock()
        seg.text = "你好世界"
        instance.transcribe.return_value = ([seg], None)
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

    t = Transcriber()
    result = await t.transcribe(_segment())
    assert result.text == "你好世界"


@pytest.mark.asyncio
async def test_transcribe_lazy_loads_model():
    from backend.asr.transcriber import Transcriber, WhisperModel

    t = Transcriber()
    assert t._model is None
    await t.transcribe(_segment())
    assert t._model is not None


@pytest.mark.asyncio
async def test_transcribe_empty_audio():
    from backend.asr.transcriber import Transcriber

    t = Transcriber()
    result = await t.transcribe(_segment(dur_s=0.0))
    assert result.text == ""


@pytest.mark.asyncio
async def test_transcribe_result_has_timestamps():
    from backend.asr.transcriber import Transcriber

    t = Transcriber()
    result = await t.transcribe(_segment(2.0))
    assert result.start_time == 0.0
    assert result.end_time == 2.0
