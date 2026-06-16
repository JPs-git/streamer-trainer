# ASR 管线重构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ASR 从单文件内联逻辑拆分为管线式架构：帧协议 → VAD + 动态缓冲 → 转写 → 输出，并抽离 OBS 适配层。

**Architecture:** `AudioSource` 接口解耦音频传输与 ASR 处理。`ASRPipeline` 编排 `VADEngine` → `AudioBuffer` → `Transcriber` 三个阶段。帧化 PCM 作为 OBS 插件→后端契约。

**Tech Stack:** Python 3.11+, faster-whisper, silero-vad, numpy, asyncio, pytest

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/asr/__init__.py` | 新建 | 导出公开 API |
| `backend/asr/frame.py` | 新建 | `AudioFrame` + 编解码 |
| `backend/asr/source.py` | 新建 | `AudioSource` ABC + `WSAudioSource` + `FileAudioSource` |
| `backend/asr/vad.py` | 新建 | `VADEngine` (Silero VAD 封装) |
| `backend/asr/buffer.py` | 新建 | `AudioBuffer` (动态缓冲 + VAD 协调) |
| `backend/asr/transcriber.py` | 新建 | `Transcriber` (从 `asr.py` 提取) |
| `backend/asr/pipeline.py` | 新建 | `ASRPipeline` 编排器 |
| `backend/asr/output.py` | 新建 | `OutputHandler` |
| `backend/asr.py` | 删除 | 拆分为 `asr/` 包 |
| `backend/config.py` | 修改 | 加载 VAD 新字段 |
| `backend/main.py` | 修改 | `/audio` endpoint 改用管线 |
| `config.yaml` | 修改 | 新增 VAD 参数 |
| `config.default.yaml` | 修改 | 新增 VAD 参数 |
| `pyproject.toml` | 修改 | 添加 silero-vad |
| `tests/test_asr_frame.py` | 新建 | 帧编解码测试 |
| `tests/test_asr_source.py` | 新建 | AudioSource 测试 |
| `tests/test_asr_vad.py` | 新建 | VADEngine 测试 |
| `tests/test_asr_buffer.py` | 新建 | AudioBuffer 测试 |
| `tests/test_asr_pipeline.py` | 新建 | 管线集成测试 |
| `tests/test_main.py` | 修改 | 适配新 ASR 结构 |

---

### Task 1: 帧协议 — AudioFrame + 编解码

**Files:**
- Create: `backend/asr/__init__.py`
- Create: `backend/asr/frame.py`
- Create: `tests/test_asr_frame.py`

- [ ] **Step 1: 创建 `backend/asr/__init__.py`** — 空文件，后续逐步补充导出

- [ ] **Step 2: 编写帧编解码测试**

```python
# tests/test_asr_frame.py
import pytest
from backend.asr.frame import (
    AudioFrame, encode_frame, decode_frame,
    FRAME_HEADER_SIZE, MAGIC,
    FLAG_START, FLAG_END,
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
```

- [ ] **Step 3: 验证测试失败**

Run: `uv run pytest tests/test_asr_frame.py -v`
Expected: 7 failed (ImportError)

- [ ] **Step 4: 实现 `backend/asr/frame.py`**

```python
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
        "<2sIhHB",
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
        "<2sIhHB", data[:FRAME_HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ValueError(f"Invalid magic: {magic.hex()}")
    payload = data[FRAME_HEADER_SIZE:FRAME_HEADER_SIZE + payload_len]
    return AudioFrame(
        payload=payload,
        timestamp_ms=timestamp_ms,
        sample_rate=sample_rate,
        channels=channels,
        flags=flags,
    )
```

- [ ] **Step 5: 验证测试通过**

Run: `uv run pytest tests/test_asr_frame.py -v`
Expected: 7 passed

- [ ] **Step 6: 提交**

```bash
git add backend/asr/__init__.py backend/asr/frame.py tests/test_asr_frame.py
git commit -m "feat: add AudioFrame protocol and codec"
```

---

### Task 2: AudioSource 抽象层

**Files:**
- Create: `backend/asr/source.py`
- Create: `tests/test_asr_source.py`

- [ ] **Step 1: 编写 AudioSource 测试**

```python
# tests/test_asr_source.py
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
```

- [ ] **Step 2: 验证测试失败**

Run: `uv run pytest tests/test_asr_source.py -v`
Expected: 3 failed

- [ ] **Step 3: 实现 `backend/asr/source.py`**

```python
from __future__ import annotations
import asyncio
import logging
import struct
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from backend.asr.frame import AudioFrame, FRAME_HEADER_SIZE, decode_frame

logger = logging.getLogger(__name__)


class AudioSource(ABC):
    @abstractmethod
    def __aiter__(self) -> AsyncIterator[AudioFrame]:
        ...


class FileAudioSource(AudioSource):
    def __init__(self, path: str):
        self.path = path

    async def __aiter__(self):
        loop = asyncio.get_running_loop()
        with open(self.path, "rb") as f:
            while True:
                header = await loop.run_in_executor(None, f.read, FRAME_HEADER_SIZE)
                if not header or len(header) < FRAME_HEADER_SIZE:
                    break
                _, payload_len, *_ = struct.unpack("<2sIhHB", header)
                payload = await loop.run_in_executor(None, f.read, payload_len)
                if len(payload) < payload_len:
                    break
                yield decode_frame(header + payload)


class WSAudioSource(AudioSource):
    def __init__(self, ws):
        self._ws = ws

    async def __aiter__(self):
        try:
            while True:
                data = await self._ws.receive_bytes()
                yield decode_frame(data)
        except Exception:
            pass
```

- [ ] **Step 4: 更新 `__init__.py` 导出**

```python
# backend/asr/__init__.py
from backend.asr.frame import AudioFrame, FRAME_HEADER_SIZE, MAGIC, encode_frame, decode_frame
from backend.asr.source import AudioSource, WSAudioSource, FileAudioSource

__all__ = [
    "AudioFrame", "FRAME_HEADER_SIZE", "MAGIC", "encode_frame", "decode_frame",
    "AudioSource", "WSAudioSource", "FileAudioSource",
]
```

- [ ] **Step 5: 验证测试通过**

Run: `uv run pytest tests/test_asr_source.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add backend/asr/__init__.py backend/asr/source.py tests/test_asr_source.py
git commit -m "feat: add AudioSource abstraction with File/WSAudioSource"
```

---

### Task 3: VADEngine — 语音活动检测

**Files:**
- Create: `backend/asr/vad.py`
- Create: `tests/test_asr_vad.py`

VADEngine 对每帧音频返回一个标签，指示当前帧是静音、语音、语音开始、还是语音结束。AudioBuffer 据此决定何时开始/停止累积。

- [ ] **Step 1: 编写 VADEngine 测试**

```python
# tests/test_asr_vad.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from backend.asr.frame import AudioFrame


@pytest.fixture(autouse=True)
def mock_silero():
    with patch("backend.asr.vad.load_silero_vad") as m:
        model = MagicMock()
        m.return_value = model
        yield model


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


def test_vad_silence_returns_none(mock_silero):
    from backend.asr.vad import VADEngine
    mock_silero.return_value = [0.1]
    vad = VADEngine(vad_threshold=0.5)
    result = vad.process(_frame(_silence(0.5)))
    assert result is None


def test_vad_speech_returns_speech(mock_silero):
    from backend.asr.vad import VADEngine
    mock_silero.return_value = [0.9]
    vad = VADEngine(vad_threshold=0.5)
    result = vad.process(_frame(_speech(0.5)))
    assert result is not None
    assert not result.final


def test_vad_speech_ended_returns_final(mock_silero):
    from backend.asr.vad import VADEngine
    mock_silero.return_value = [0.9]
    vad = VADEngine(vad_threshold=0.5, silence_duration_ms=200)
    # speech frame
    vad.process(_frame(_speech(0.3), ts=1000))
    # now silence frames (each 100ms) - should accumulate
    mock_silero.return_value = [0.1]
    sil1 = vad.process(_frame(_silence(0.1), ts=1300))
    assert sil1 is None  # only 100ms of silence < 200ms threshold
    sil2 = vad.process(_frame(_silence(0.1), ts=1400))
    assert sil2 is not None  # 200ms >= 200ms
    assert sil2.final


def test_vad_speech_during_speech_returns_none(mock_silero):
    from backend.asr.vad import VADEngine
    mock_silero.return_value = [0.9]
    vad = VADEngine(vad_threshold=0.5)
    vad.process(_frame(_speech(0.3), ts=0))  # start
    result = vad.process(_frame(_speech(0.3), ts=300))  # continuing
    assert result is None  # no transition


def test_vad_reset(mock_silero):
    from backend.asr.vad import VADEngine
    mock_silero.return_value = [0.9]
    vad = VADEngine()
    vad.process(_frame(_speech(0.3), ts=0))
    vad.reset()
    assert vad._state == "silence"


def test_vad_below_threshold(mock_silero):
    from backend.asr.vad import VADEngine
    mock_silero.return_value = [0.3]
    vad = VADEngine(vad_threshold=0.5)
    assert vad.process(_frame(_speech(0.3))) is None
```

- [ ] **Step 2: 验证测试失败**

Run: `uv run pytest tests/test_asr_vad.py -v`
Expected: 6 failed

- [ ] **Step 3: 实现 `backend/asr/vad.py`**

```python
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from silero_vad import load_silero_vad

from backend.asr.frame import AudioFrame

logger = logging.getLogger(__name__)


@dataclass
class SpeechSegment:
    audio: np.ndarray
    start_time: float
    end_time: float
    final: bool = False


class VADEngine:
    def __init__(self, vad_threshold: float = 0.5, silence_duration_ms: int = 600):
        self.vad_threshold = vad_threshold
        self.silence_duration_ms = silence_duration_ms
        self._model = None
        self._state: str = "silence"
        self._speech_start_ms: int = 0
        self._silence_start_ms: int = 0

    def _ensure_model(self):
        if self._model is None:
            self._model = load_silero_vad()

    def reset(self):
        self._state = "silence"
        self._speech_start_ms = 0
        self._silence_start_ms = 0

    def process(self, frame: AudioFrame) -> Optional[SpeechSegment]:
        self._ensure_model()
        if not frame.payload:
            return None

        audio = np.frombuffer(frame.payload, dtype=np.int16).astype(np.float32) / 32768.0
        prob = self._model(audio, frame.sample_rate).item()
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

        # state == "speech"
        if is_speech:
            self._silence_start_ms = 0
            return None
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
```

- [ ] **Step 4: 验证测试通过**

Run: `uv run pytest tests/test_asr_vad.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/asr/vad.py tests/test_asr_vad.py
git commit -m "feat: add VADEngine with Silero VAD state machine"
```

---

### Task 4: AudioBuffer — 动态缓冲

**Files:**
- Create: `backend/asr/buffer.py`
- Create: `tests/test_asr_buffer.py`

- [ ] **Step 1: 编写 AudioBuffer 测试**

```python
# tests/test_asr_buffer.py
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
    assert result is None  # still accumulating


def test_add_returns_segment_on_final(buffer):
    buffer.add(_seg(1.0, start=0.0, final=False))
    result = buffer.add(_seg(0.5, start=1.0, final=True))
    assert result is not None
    assert result.final
    assert result.start_time == 0.0
    assert result.end_time == 1.5


def test_add_returns_none_when_empty(buffer):
    assert buffer.add(_seg(0, final=True)) is None


def test_max_duration_triggers_completion(buffer):
    buf = AudioBuffer(max_segment_duration=0.5)
    buf.add(_seg(0.3, start=0.0, final=False))
    result = buf.add(_seg(0.3, start=0.3, final=False))
    assert result is not None
    assert result.final
    assert result.end_time == 0.6


def test_flush_returns_accumulated(buffer):
    buffer.add(_seg(1.0, start=0.0, final=False))
    result = buffer.flush()
    assert result is not None
    assert result.final
    assert result.start_time == 0.0
    assert result.end_time == 1.0


def test_flush_empty(buffer):
    result = buffer.flush()
    assert result is None
```

- [ ] **Step 2: 验证测试失败**

Run: `uv run pytest tests/test_asr_buffer.py -v`
Expected: 6 failed

- [ ] **Step 3: 实现 `backend/asr/buffer.py`**

```python
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
        else:
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
```

- [ ] **Step 4: 验证测试通过**

Run: `uv run pytest tests/test_asr_buffer.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/asr/buffer.py tests/test_asr_buffer.py
git commit -m "feat: add AudioBuffer with dynamic VAD-based accumulation"
```

---

### Task 5: Transcriber — 从旧 ASREngine 提取

**Files:**
- Create: `backend/asr/transcriber.py`
- Create: `tests/test_asr_transcriber.py`

- [ ] **Step 1: 编写 Transcriber 测试**

```python
# tests/test_asr_transcriber.py
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
```

- [ ] **Step 2: 验证测试失败**

Run: `uv run pytest tests/test_asr_transcriber.py -v`
Expected: 4 failed

- [ ] **Step 3: 实现 `backend/asr/transcriber.py`**

```python
from __future__ import annotations
import logging
import os
import threading
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from backend.asr.vad import SpeechSegment
from backend.asr.output import TranscriptionResult

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8", download_timeout: float = 30.0):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_timeout = download_timeout
        self._model: Optional[WhisperModel] = None
        self._error: Optional[str] = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is not None:
            return
        if self._error is not None:
            raise RuntimeError(self._error)
        with self._lock:
            if self._model is not None:
                return
            self._model = self._load_model()

    def _load_model(self) -> Optional[WhisperModel]:
        try:
            return WhisperModel(
                self.model_size, device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
        except OSError:
            logger.info("Whisper model '%s' not in cache, downloading...", self.model_size)

        original_timeout = os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT")
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(int(self.download_timeout))
        try:
            return WhisperModel(
                self.model_size, device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as e:
            msg = (f"Failed to download Whisper model '{self.model_size}': {e}. "
                   "Run `uv run python scripts/download_models.py` to pre-download.")
            logger.warning(msg)
            self._error = msg
            return None
        finally:
            if original_timeout is not None:
                os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = original_timeout
            else:
                os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)

    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult:
        if segment.audio.size == 0:
            return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)

        self._ensure_model()
        if self._model is None:
            return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)

        loop = asyncio.get_running_loop()
        segments, _ = await loop.run_in_executor(
            None,
            lambda: self._model.transcribe(segment.audio, beam_size=1, language="zh"),
        )
        text = " ".join(seg.text for seg in segments)
        return TranscriptionResult(text=text, start_time=segment.start_time, end_time=segment.end_time)
```

Wait — `TranscriptionResult` is in `output.py` but I haven't created it yet. Let me create a minimal definition in `transcriber.py` itself and then move it later, or better, define `TranscriptionResult` in `frame.py` since it's a data class. Actually, let me think about the best place.

The spec says `Transcriber` returns `TranscriptionResult`. Let me define it in a separate file or in `__init__.py`. Actually, let me define it where it makes most sense — in `transcriber.py` since that's where it's produced.

But `OutputHandler` also needs to import it. Let me put it in a shared location. I'll put it in `frame.py` alongside `AudioFrame` since it's also a data class — or better, create a dedicated `types.py` or just define it in `__init__.py`.

Actually, let me just define `TranscriptionResult` in the `output.py` module and import it from there. That way `transcriber.py` imports from `output.py`, and `output.py` defines the result type. But that creates a circular dependency if `output.py` ever needs to import `transcriber.py`. It doesn't in this case, so it's fine.

Alternatively, just define it in `transcriber.py` and import from there in `output.py`. That's cleaner since the transcriber is the producer.

Let me do that:

```python
# backend/asr/transcriber.py
@dataclass
class TranscriptionResult:
    text: str
    start_time: float
    end_time: float
```

Then in output.py:
```python
from backend.asr.transcriber import TranscriptionResult
```

That's clean and has no circular dependency.

Let me correct the plan.

Also, I need `import asyncio` in the Transcriber for `run_in_executor`. Let me make sure that's included.

- [ ] **Step 3 (corrected): 实现 `backend/asr/transcriber.py`**

```python
from __future__ import annotations
import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from backend.asr.vad import SpeechSegment

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    start_time: float
    end_time: float


class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8", download_timeout: float = 30.0):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_timeout = download_timeout
        self._model: Optional[WhisperModel] = None
        self._error: Optional[str] = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is not None:
            return
        if self._error is not None:
            raise RuntimeError(self._error)
        with self._lock:
            if self._model is not None:
                return
            self._model = self._load_model()

    def _load_model(self) -> Optional[WhisperModel]:
        try:
            return WhisperModel(
                self.model_size, device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
        except OSError:
            logger.info("Whisper model '%s' not in cache, downloading...", self.model_size)

        original_timeout = os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT")
        os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = str(int(self.download_timeout))
        try:
            return WhisperModel(
                self.model_size, device=self.device,
                compute_type=self.compute_type,
            )
        except Exception as e:
            msg = (f"Failed to download Whisper model '{self.model_size}': {e}. "
                   "Run `uv run python scripts/download_models.py` to pre-download.")
            logger.warning(msg)
            self._error = msg
            return None
        finally:
            if original_timeout is not None:
                os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = original_timeout
            else:
                os.environ.pop("HF_HUB_DOWNLOAD_TIMEOUT", None)

    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult:
        if segment.audio.size == 0:
            return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)

        self._ensure_model()
        if self._model is None:
            return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)

        loop = asyncio.get_running_loop()
        segments, _ = await loop.run_in_executor(
            None,
            lambda: self._model.transcribe(segment.audio, beam_size=1, language="zh"),
        )
        text = " ".join(seg.text for seg in segments)
        return TranscriptionResult(text=text, start_time=segment.start_time, end_time=segment.end_time)
```

- [ ] **Step 4: 验证测试通过**

Run: `uv run pytest tests/test_asr_transcriber.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/asr/transcriber.py tests/test_asr_transcriber.py
git commit -m "feat: add Transcriber extracted from legacy ASREngine"
```

---

### Task 6: OutputHandler + ASRPipeline

**Files:**
- Create: `backend/asr/output.py`
- Create: `backend/asr/pipeline.py`
- Create: `tests/test_asr_pipeline.py`

- [ ] **Step 1: 编写 OutputHandler 和 Pipeline 测试**

```python
# tests/test_asr_pipeline.py
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.asr.vad import SpeechSegment
from backend.asr.transcriber import TranscriptionResult
from backend.asr.frame import AudioFrame, encode_frame


def test_output_handler_writes_to_timeline():
    from backend.asr.output import OutputHandler
    timeline = [{"text": "old", "offset": 100}]
    chat_log = []
    handler = OutputHandler(timeline=timeline, chat_log=chat_log)
    result = TranscriptionResult(text="hello", start_time=1.0, end_time=2.0)
    handler.on_result(result, timestamp_ms=5000)
    assert len(timeline) == 2
    assert timeline[-1]["text"] == "hello"
    assert timeline[-1]["offset"] == 5
    assert chat_log[-1]["type"] == "streamer"


def test_output_handler_empty_text():
    from backend.asr.output import OutputHandler
    timeline = []
    chat_log = []
    handler = OutputHandler(timeline=timeline, chat_log=chat_log)
    handler.on_result(TranscriptionResult(text="", start_time=0, end_time=0), timestamp_ms=0)
    assert len(timeline) == 0


def test_output_handler_trims_chat_log():
    from backend.asr.output import OutputHandler
    chat_log = [{"type": "streamer", "text": str(i), "offset": i} for i in range(210)]
    timeline = []
    handler = OutputHandler(timeline=timeline, chat_log=chat_log)
    handler.on_result(TranscriptionResult(text="x", start_time=0, end_time=0), timestamp_ms=0)
    assert len(chat_log) <= 200  # actually 210-50+1=161, but after trim should be <= 161


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
    mock_buffer.add.side_effect = [None, SpeechSegment(
        audio=np.zeros(32000, dtype=np.float32), start_time=0.0, end_time=2.0, final=True,
    )]

    mock_transcriber = MagicMock()
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
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(b"")
    tmp.close()

    pipeline = ASRPipeline.from_components(source_type="file", path=tmp.name)
    callback = AsyncMock()
    await pipeline.run(callback)
    callback.assert_not_awaited()
    os.unlink(tmp.name)
```

- [ ] **Step 2: 实现 `backend/asr/output.py`**

```python
from __future__ import annotations
import asyncio
import time
import logging
from typing import Callable, Optional

from backend.asr.transcriber import TranscriptionResult

logger = logging.getLogger(__name__)


class OutputHandler:
    def __init__(self, timeline: list[dict], chat_log: list[dict],
                 broadcast: Optional[Callable] = None):
        self.timeline = timeline
        self.chat_log = chat_log
        self.broadcast = broadcast

    def on_result(self, result: TranscriptionResult, timestamp_ms: int = 0):
        text = result.text.strip()
        if not text:
            return

        ts = int(time.time())
        self.timeline.append({"text": text, "offset": ts})
        self.chat_log.append({"type": "streamer", "name": "主播", "text": text, "offset": ts})

        if len(self.chat_log) > 200:
            self.chat_log[:50] = []

        if self.broadcast:
            asyncio.ensure_future(self.broadcast({
                "type": "streamer",
                "text": text,
                "timestamp": ts,
            }))
```

Need `import asyncio` in output.py.

- [ ] **Step 3: 实现 `backend/asr/pipeline.py`**

```python
from __future__ import annotations
import logging
from typing import Callable, Optional

from backend.asr.source import AudioSource, FileAudioSource, WSAudioSource
from backend.asr.vad import VADEngine
from backend.asr.buffer import AudioBuffer
from backend.asr.transcriber import Transcriber, TranscriptionResult
from backend.asr.output import OutputHandler

logger = logging.getLogger(__name__)


class ASRPipeline:
    def __init__(self, source: AudioSource, vad: VADEngine,
                 buffer: AudioBuffer, transcriber: Transcriber):
        self.source = source
        self.vad = vad
        self.buffer = buffer
        self.transcriber = transcriber

    @classmethod
    def from_config(cls, source: AudioSource, config) -> ASRPipeline:
        return cls(
            source=source,
            vad=VADEngine(
                vad_threshold=config.vad_threshold,
                silence_duration_ms=config.silence_duration_ms,
            ),
            buffer=AudioBuffer(
                max_segment_duration=config.max_segment_duration,
            ),
            transcriber=Transcriber(
                model_size=config.asr_model_size,
                device=config.asr_device,
                compute_type=config.asr_compute_type,
                download_timeout=config.asr_download_timeout,
            ),
        )

    @classmethod
    def from_components(cls, source_type: str = "file", **kwargs) -> ASRPipeline:
        if source_type == "file":
            source = FileAudioSource(kwargs.get("path", ""))
        elif source_type == "ws":
            source = WSAudioSource(kwargs.get("ws"))
        else:
            raise ValueError(f"Unknown source type: {source_type}")
        return cls(
            source=source,
            vad=VADEngine(),
            buffer=AudioBuffer(),
            transcriber=Transcriber(),
        )

    async def run(self, callback: Callable[[TranscriptionResult], None]):
        async for frame in self.source:
            segment = self.vad.process(frame)
            if segment is not None:
                completed = self.buffer.add(segment)
                if completed is not None:
                    result = await self.transcriber.transcribe(completed)
                    if result.text.strip():
                        await callback(result)
```

- [ ] **Step 4: 更新 `__init__.py` 导出**

```python
from backend.asr.frame import AudioFrame, FRAME_HEADER_SIZE, MAGIC, encode_frame, decode_frame
from backend.asr.source import AudioSource, WSAudioSource, FileAudioSource
from backend.asr.pipeline import ASRPipeline

__all__ = [
    "AudioFrame", "FRAME_HEADER_SIZE", "MAGIC", "encode_frame", "decode_frame",
    "AudioSource", "WSAudioSource", "FileAudioSource",
    "ASRPipeline",
]
```

- [ ] **Step 5: 验证测试通过**

Run: `uv run pytest tests/test_asr_pipeline.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add backend/asr/__init__.py backend/asr/output.py backend/asr/pipeline.py tests/test_asr_pipeline.py
git commit -m "feat: add OutputHandler, ASRPipeline orchestrator"
```

---

### Task 7: 配置 + main.py 集成

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/main.py`
- Modify: `config.yaml`
- Modify: `config.default.yaml`

- [ ] **Step 1: 更新 config.yaml**

新增 VAD 字段：
```yaml
asr:
  model_size: base
  device: cpu
  compute_type: int8
  download_timeout: 30.0
  vad_threshold: 0.5
  silence_duration_ms: 600
  max_segment_duration: 10
```

- [ ] **Step 2: 更新 config.default.yaml**

相同变更。

- [ ] **Step 3: 更新 config.py**

```python
# 在 asr_conf 块内添加
self.vad_threshold = asr_conf.get("vad_threshold", 0.5)
self.silence_duration_ms = asr_conf.get("silence_duration_ms", 600)
self.max_segment_duration = asr_conf.get("max_segment_duration", 10.0)
```

- [ ] **Step 4: 重写 /audio endpoint 并初始化管线**

修改 `backend/main.py`：

替换 import:
```python
from backend.asr.pipeline import ASRPipeline
from backend.asr.source import WSAudioSource
from backend.asr.transcriber import Transcriber
from backend.asr.vad import VADEngine
from backend.asr.buffer import AudioBuffer
from backend.asr.output import OutputHandler
```

替换 `StreamerTrainerApp.__init__` 中 ASR 初始化：
```python
self.asr_transcriber = Transcriber(
    model_size=config.asr_model_size,
    device=config.asr_device,
    compute_type=config.asr_compute_type,
    download_timeout=config.asr_download_timeout,
)
self.asr_config = config  # pass full config for from_config
```

替换 `/audio` endpoint：
```python
@app.websocket("/audio")
async def audio_endpoint(ws: WebSocket):
    await ws.accept()
    source = WSAudioSource(ws)
    pipeline = ASRPipeline(
        source=source,
        vad=VADEngine(
            vad_threshold=config.vad_threshold,
            silence_duration_ms=config.silence_duration_ms,
        ),
        buffer=AudioBuffer(
            max_segment_duration=config.max_segment_duration,
        ),
        transcriber=app_state.asr_transcriber,
    )
    output = OutputHandler(
        timeline=app_state.streamer_timeline,
        chat_log=app_state.room_chat_log,
        broadcast=app_state.broadcast_danmaku,
    )
    try:
        await pipeline.run(callback=output.on_result)
    except WebSocketDisconnect:
        pass
```

Remove the old ASREngine import:
```python
# remove this line:
# from backend.asr import ASREngine
```

- [ ] **Step 5: 更新 test_main.py mock**

```python
# 在 mock_llm_and_asr fixture 中
mock_instance.asr_transcriber = MagicMock()
mock_instance.asr_transcriber.transcribe = AsyncMock(return_value="主播说你好")
```

- [ ] **Step 6: 验证全部测试通过**

Run: `uv run pytest tests/ -v`
Expected: 所有测试通过（可能需微调）

- [ ] **Step 7: 提交**

```bash
git add backend/config.py backend/main.py config.yaml config.default.yaml tests/test_main.py
git commit -m "feat: integrate ASRPipeline into main app, add VAD config"
```

---

### Task 8: 清理 — 删除旧 asr.py + 安装 silero-vad

**Files:**
- Delete: `backend/asr.py`
- Modify: `pyproject.toml`
- Verify: `backend/asr/__init__.py` 已完整

- [ ] **Step 1: 检查旧 asr.py 的引用**

```bash
rg "from backend.asr import|from backend.asr\.asr import" --type py
```

确认 `main.py` 已更新为 `from backend.asr.transcriber import Transcriber`，不再引用 `backend.asr.ASREngine`。

- [ ] **Step 2: 删除 `backend/asr.py`**

```bash
git rm backend/asr.py
```

- [ ] **Step 3: 更新 pyproject.toml**

在 `dependencies` 中添加：
```toml
"silero-vad>=5.0",
"aiofiles>=24.0",  # 如果 FileAudioSource 需要 async file ops，暂不需要
```

实际只需要 silero-vad，FileAudioSource 使用 `run_in_executor` 无需 aiofiles。

- [ ] **Step 4: 运行全部测试确认不破坏**

Run: `uv run pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml
git rm backend/asr.py
git commit -m "chore: remove legacy ASREngine, add silero-vad dependency"
```

---

### Task 9: 最终验证

- [ ] **Step 1: 全量测试**

Run: `uv run pytest tests/ -v`
Expected: 全部通过（可能新增测试约 30+ 个）

- [ ] **Step 2: 完整提交历史**

```bash
git log --oneline -10
```

确认 8 个提交：
1. feat: add AudioFrame protocol and codec
2. feat: add AudioSource abstraction with File/WSAudioSource
3. feat: add VADEngine with Silero VAD state machine
4. feat: add AudioBuffer with dynamic VAD-based accumulation
5. feat: add Transcriber extracted from legacy ASREngine
6. feat: add OutputHandler, ASRPipeline orchestrator
7. feat: integrate ASRPipeline into main app, add VAD config
8. chore: remove legacy ASREngine, add silero-vad dependency
