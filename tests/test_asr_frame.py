from __future__ import annotations

import pytest

from backend.asr.frame import (
    FRAME_HEADER_SIZE,
    FLAG_END,
    FLAG_START,
    MAGIC,
    AudioFrame,
    decode_frame,
    encode_frame,
)


def test_encode_decode_roundtrip():
    payload = b"\x00\x01\x02\x03"
    frame = AudioFrame(payload=payload, timestamp_ms=12345, sample_rate=16000, channels=1, flags=0)
    data = encode_frame(frame)
    decoded = decode_frame(data)
    assert decoded.payload == payload
    assert decoded.timestamp_ms == 12345
    assert decoded.sample_rate == 16000
    assert decoded.channels == 1
    assert decoded.flags == 0


def test_header_size():
    data = encode_frame(AudioFrame(payload=b"", timestamp_ms=0))
    assert len(data) == FRAME_HEADER_SIZE


def test_start_flag():
    data = encode_frame(AudioFrame(payload=b"", timestamp_ms=0, flags=FLAG_START))
    assert decode_frame(data).flags & FLAG_START


def test_end_flag():
    data = encode_frame(AudioFrame(payload=b"", timestamp_ms=0, flags=FLAG_END))
    assert decode_frame(data).flags & FLAG_END


def test_large_payload():
    payload = b"\x00\x01" * 16000
    frame = AudioFrame(payload=payload, timestamp_ms=5000, sample_rate=16000, channels=1)
    data = encode_frame(frame)
    decoded = decode_frame(data)
    assert decoded.payload == payload
    assert decoded.timestamp_ms == 5000


def test_decode_invalid_magic():
    with pytest.raises(ValueError, match="Invalid magic"):
        decode_frame(b"\x00\x00" + b"\x00" * 12)


def test_decode_truncated():
    with pytest.raises(ValueError, match="too short"):
        decode_frame(b"\xaa")


def test_stereo():
    payload = b"\x00\x01" * 32000
    frame = AudioFrame(payload=payload, timestamp_ms=0, sample_rate=44100, channels=2)
    data = encode_frame(frame)
    decoded = decode_frame(data)
    assert decoded.channels == 2
    assert decoded.sample_rate == 44100
