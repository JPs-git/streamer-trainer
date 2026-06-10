from __future__ import annotations

import pytest
from backend.asr.frame import AudioFrame, encode_frame, FLAG_START, FLAG_END


@pytest.mark.asyncio
async def test_file_source_yields_frames():
    from backend.asr.source import FileAudioSource
    import tempfile, os

    payload = b"\x00\x01" * 16000
    frames = [
        AudioFrame(payload=payload, timestamp_ms=0, flags=FLAG_START),
        AudioFrame(payload=payload, timestamp_ms=1000),
        AudioFrame(payload=b"", timestamp_ms=2000, flags=FLAG_END),
    ]
    data = b"".join(encode_frame(f) for f in frames)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(data)
    tmp.close()
    try:
        source = FileAudioSource(tmp.name)
        collected = []
        async for frame in source:
            collected.append(frame)
        assert len(collected) == 3
        assert collected[0].flags & FLAG_START
        assert collected[2].flags & FLAG_END
    finally:
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_file_source_empty():
    from backend.asr.source import FileAudioSource
    import tempfile, os

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(b"")
    tmp.close()
    try:
        source = FileAudioSource(tmp.name)
        collected = []
        async for frame in source:
            collected.append(frame)
        assert len(collected) == 0
    finally:
        os.unlink(tmp.name)


def test_abc_not_instantiable():
    from backend.asr.source import AudioSource

    with pytest.raises(TypeError):
        AudioSource()


@pytest.mark.asyncio
async def test_ws_source_yields_frames():
    from unittest.mock import AsyncMock, MagicMock

    from backend.asr.source import WSAudioSource

    ws = MagicMock()
    payload = b"\x00\x01" * 160
    frame = AudioFrame(payload=payload, timestamp_ms=100)
    ws.receive_bytes = AsyncMock(
        side_effect=[
            encode_frame(frame),
            encode_frame(AudioFrame(payload=payload, timestamp_ms=200)),
        ]
    )
    source = WSAudioSource(ws)
    collected = []
    async for f in source:
        collected.append(f)
    assert len(collected) == 2
    assert collected[0].timestamp_ms == 100
    assert collected[1].timestamp_ms == 200


@pytest.mark.asyncio
async def test_ws_source_disconnect_stops():
    from unittest.mock import AsyncMock, MagicMock

    from backend.asr.source import WSAudioSource
    from fastapi import WebSocketDisconnect

    ws = MagicMock()
    ws.receive_bytes = AsyncMock(side_effect=WebSocketDisconnect())
    source = WSAudioSource(ws)
    collected = []
    async for f in source:
        collected.append(f)
    assert len(collected) == 0


@pytest.mark.asyncio
async def test_ws_source_valueerror_propagates():
    from unittest.mock import AsyncMock, MagicMock

    from backend.asr.source import WSAudioSource

    ws = MagicMock()
    ws.receive_bytes = AsyncMock(return_value=b"\x00" * 14)
    source = WSAudioSource(ws)
    with pytest.raises(ValueError):
        async for f in source:
            pass


@pytest.mark.asyncio
async def test_file_source_bad_magic_raises():
    from backend.asr.source import FileAudioSource
    import os
    import tempfile

    data = b"\x00\x00" + b"\x00" * 12
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(data)
    tmp.close()
    try:
        source = FileAudioSource(tmp.name)
        with pytest.raises(ValueError, match="Invalid magic"):
            async for f in source:
                pass
    finally:
        os.unlink(tmp.name)
