from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"\xaa\xbb"
FRAME_HEADER_SIZE = 14

FLAG_START = 0x01
FLAG_END = 0x02


@dataclass
class AudioFrame:
    payload: bytes
    timestamp_ms: int
    sample_rate: int = 16000
    channels: int = 1
    flags: int = 0


def encode_frame(frame: AudioFrame) -> bytes:
    header = struct.pack(
        "<2sIIHBB",
        MAGIC,
        len(frame.payload),
        frame.timestamp_ms,
        frame.sample_rate,
        frame.channels,
        frame.flags,
    )
    return header + frame.payload


def decode_frame(data: bytes) -> AudioFrame:
    if len(data) < FRAME_HEADER_SIZE:
        raise ValueError(f"Frame too short: {len(data)} < {FRAME_HEADER_SIZE}")
    magic, payload_len, timestamp_ms, sample_rate, channels, flags = struct.unpack(
        "<2sIIHBB", data[:FRAME_HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ValueError(f"Invalid magic: {magic.hex()}")
    payload = data[FRAME_HEADER_SIZE : FRAME_HEADER_SIZE + payload_len]
    return AudioFrame(
        payload=payload,
        timestamp_ms=timestamp_ms,
        sample_rate=sample_rate,
        channels=channels,
        flags=flags,
    )
