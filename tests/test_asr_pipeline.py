import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.asr.vad import SpeechSegment
from backend.asr.vad import TranscriptionResult
from backend.asr.frame import AudioFrame, encode_frame


def test_output_handler_writes_to_timeline():
    from backend.asr.output import OutputHandler
    timeline = [{"text": "old", "offset": 100}]
    chat_log = []
    handler = OutputHandler(timeline=timeline, chat_log=chat_log)
    result = TranscriptionResult(text="hello", start_time=1.0, end_time=2.0)
    handler.on_result(result)
    assert len(timeline) == 2
    assert timeline[-1]["text"] == "hello"
    assert chat_log[-1]["type"] == "streamer"


def test_output_handler_empty_text():
    from backend.asr.output import OutputHandler
    timeline = []
    chat_log = []
    handler = OutputHandler(timeline=timeline, chat_log=chat_log)
    handler.on_result(TranscriptionResult(text="", start_time=0, end_time=0))
    assert len(timeline) == 0


def test_output_handler_trims_chat_log():
    from backend.asr.output import OutputHandler
    chat_log = [{"type": "streamer", "text": str(i), "offset": i} for i in range(210)]
    timeline = []
    handler = OutputHandler(timeline=timeline, chat_log=chat_log)
    handler.on_result(TranscriptionResult(text="x", start_time=0, end_time=0))
    assert len(chat_log) <= 200


@pytest.mark.asyncio
async def test_pipeline_full_flow():
    from backend.asr.pipeline import ASRPipeline
    from backend.asr.source import FileAudioSource
    from backend.asr.vad import VADEngine
    from backend.asr.buffer import AudioBuffer
    import tempfile, os

    payload = b"\x00\x01" * 16000
    frames = [
        AudioFrame(payload=payload, timestamp_ms=0),
        AudioFrame(payload=payload, timestamp_ms=1000),
    ]
    data = b"".join(encode_frame(f) for f in frames)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(data)
    tmp.close()

    mock_vad = MagicMock(spec=VADEngine)
    mock_vad.process.side_effect = [
        SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=0.0, end_time=1.0, final=False),
        SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=1.0, end_time=2.0, final=True),
    ]

    mock_buffer = MagicMock(spec=AudioBuffer)
    mock_buffer.add.side_effect = [
        None,
        SpeechSegment(audio=np.zeros(32000, dtype=np.float32), start_time=0.0, end_time=2.0, final=True),
    ]
    mock_buffer.flush.return_value = None

    mock_transcriber = AsyncMock()
    mock_transcriber.transcribe = AsyncMock(return_value=TranscriptionResult(
        text="test result", start_time=0.0, end_time=2.0,
    ))

    callback = AsyncMock()
    source = FileAudioSource(tmp.name)
    pipeline = ASRPipeline(source=source, vad=mock_vad, buffer=mock_buffer, transcriber=mock_transcriber)
    await pipeline.run(callback)

    callback.assert_awaited_once()
    assert callback.call_args[0][0].text == "test result"
    os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_pipeline_empty_source():
    from backend.asr.pipeline import ASRPipeline
    from backend.asr.source import FileAudioSource
    from backend.asr.vad import VADEngine
    from backend.asr.buffer import AudioBuffer
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(b"")
    tmp.close()

    mock_buffer = MagicMock(spec=AudioBuffer)
    mock_buffer.flush.return_value = None
    pipeline = ASRPipeline(
        source=FileAudioSource(tmp.name),
        vad=MagicMock(spec=VADEngine),
        buffer=mock_buffer,
        transcriber=AsyncMock(),
    )
    callback = AsyncMock()
    await pipeline.run(callback)
    callback.assert_not_awaited()
    os.unlink(tmp.name)
