# ASR 管线重构设计

## 背景

当前 ASR 实现在 `backend/asr.py` 单文件中，`ASREngine` 封装 faster-whisper。音频处理（缓冲、转写）与传输（WebSocket）紧耦合在 `main.py` 的 `audio_endpoint` 内联逻辑中：

```
/audio WS handler:
  1. 接收裸 PCM bytes
  2. 固定 2s 缓冲 (32000 bytes)
  3. 调用 ASREngine.transcribe()
  4. 追加到 timeline + chat_log
```

问题：无法独立测试、无法替换音频来源、固定窗口切分句子、静音段浪费算力。

## 决策

1. **音频帧协议**：带帧头的 PCM 二进制 WebSocket，替代裸 PCM 流
2. **音频输入抽象**：`AudioSource` 接口，WS / 文件两种实现
3. **VAD + 动态缓冲**：Silero VAD 按语音边界切分，替代固定缓冲
4. **管线式编排**：独立阶段类，由 `ASRPipeline` 编排

## 帧协议

OBS 插件 ↔ 后端的网络契约：

```
Offset  Size  Field
0       2     Magic (0xAA 0xBB)
2       4     Payload Length (LE uint32)
6       4     Timestamp (LE uint32, ms)
10      2     Sample Rate (LE uint16)
12      1     Channels (uint8)
13      1     Flags (bit0: START, bit1: END)
14      N     PCM data (signed 16-bit LE mono)
```

特殊帧（Payload=0）：`Flags=0x01` STREAM_START，`Flags=0x02` STREAM_END。

## 数据类

```python
@dataclass
class AudioFrame:
    payload: bytes             # PCM 16-bit LE
    timestamp_ms: int
    sample_rate: int = 16000
    channels: int = 1
    flags: int = 0

@dataclass
class SpeechSegment:
    audio: np.ndarray          # float32 normalized
    start_time: float          # seconds
    end_time: float

@dataclass
class TranscriptionResult:
    text: str
    start_time: float
    end_time: float
```

## 组件架构

### AudioSource (ABC)

```python
class AudioSource(ABC):
    async def recv_frame(self) -> AudioFrame | None
    async def connect(self)
    async def close(self)
```

- `WSAudioSource`：包装 `/audio` WebSocket，解析二进制帧
- `FileAudioSource`：从 WAV 文件逐帧读取，用于测试

### VADEngine

封装 Silero VAD，状态机：`SILENCE → SPEECH_START → SPEECH → SPEECH_END → SILENCE`

```python
class VADEngine:
    def process(self, frame: AudioFrame) -> SpeechSegment | None
    def reset(self)
```

- 返回 `SpeechSegment`（当检测到 SPEECH_START → 持续输出直到 SPEECH_END）
- 可配置：`vad_threshold` (0.5)，`silence_duration_ms` (600)

### AudioBuffer

累积 `SpeechSegment` 的音频，在语音结束或超时时触发完成。

```python
class AudioBuffer:
    def add(self, segment: SpeechSegment) -> SpeechSegment | None
    def flush(self) -> SpeechSegment | None
```

- 可配置：`max_segment_duration` (10s)

### Transcriber

复用 `ASREngine` 的模型懒加载和 faster-whisper 调用。

```python
class Transcriber:
    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult
```

### ASRPipeline (编排器)

```python
class ASRPipeline:
    def __init__(self, source: AudioSource, config: ASRConfig)
    async def run(self, callback: Callable[[TranscriptionResult], None])
```

主循环：`recv_frame → VAD → Buffer → Transcriber → callback`

### OutputHandler

接收 `TranscriptionResult`，写入 `streamer_timeline` 和 `room_chat_log`。

## 配置变更

```yaml
asr:
  model_size: base
  device: cpu
  compute_type: int8
  download_timeout: 30.0
  # 新增:
  vad_threshold: 0.5
  silence_duration_ms: 600
  max_segment_duration: 10
  # 移除 hardcoded 常量:
  # main.py 中 32000 (2s 固定缓冲) → 被 VAD 动态缓冲替代
```

## 目录结构

```
backend/
├── asr/                      # 新建包，替代 asr.py
│   ├── __init__.py            # 导出 ASRPipeline, AudioSource
│   ├── frame.py               # AudioFrame + 编解码
│   ├── source.py              # AudioSource ABC, WSAudioSource, FileAudioSource
│   ├── vad.py                 # VADEngine (Silero VAD 封装)
│   ├── buffer.py              # AudioBuffer (动态缓冲)
│   ├── transcriber.py         # Transcriber (原 ASREngine 逻辑)
│   ├── pipeline.py            # ASRPipeline 编排器
│   └── output.py              # OutputHandler
├── config.py                  # 更新 ASR config 字段
└── main.py                    # 音频 endpoint 改用管线
```

**删除**：`backend/asr.py`

## 系统集成

`/audio` WebSocket 端点重写为：

```python
@app.websocket("/audio")
async def audio_endpoint(ws: WebSocket):
    await ws.accept()
    source = WSAudioSource(ws)
    pipeline = ASRPipeline(source, app_state.asr_config)
    await pipeline.run(callback=on_transcription_result)
```

`on_transcription_result` 写入 `streamer_timeline` + `room_chat_log`，沿用现有数据结构。

## 开发流程

### Phase 1: 基础框架

- 定义 `AudioFrame` + 帧编解码 (`frame.py`)
- 定义 `AudioSource` ABC + `WSAudioSource` + `FileAudioSource` (`source.py`)
- 更新 `/audio` endpoint 解析帧协议
- `tests/test_asr_source.py`：FileAudioSource 读 WAV 输出正确帧序列

### Phase 2: VAD + 缓冲

- 集成 silero-vad 依赖
- 实现 `VADEngine` (`vad.py`)
- 实现 `AudioBuffer` (`buffer.py`)
- 新增 VAD 配置项
- `tests/test_asr_vad.py`：预录测试音频正确切分

### Phase 3: 管线 + 集成

- 实现 `Transcriber` (`transcriber.py`，复用 `ASREngine` 模型逻辑)
- 实现 `ASRPipeline` 编排器 (`pipeline.py`)
- 实现 `OutputHandler` (`output.py`)
- 重写 `main.py` `/audio` endpoint
- 暴露 VAD 参数到 `/api/config`
- 全部 pytest 通过

### Phase 4: 边界强化

- 重连、异常、超时测试
- VAD 阈值边界测试
- 超长段截断测试
- 性能基准脚本

## 测试策略

| 层 | 工具 | 覆盖 |
|----|------|------|
| 帧协议 | `pytest` | 编解码 roundtrip，边界值 |
| AudioSource | `pytest` + 合成 WAV | FileAudioSource 帧序列正确性 |
| VAD | `pytest` + 预录测试音频 | 正确切分，阈值边界 |
| Buffer | `pytest` | 正常结束、超时、flush |
| Pipeline | `pytest` mock transcriber | 完整流通过程 |
| 集成 | `pytest` | mock ASR，不依赖真实模型 |
