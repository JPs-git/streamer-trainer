# ASR ONNX 迁移实施计划

## 概述

将 ASR 管线从 `faster-whisper` + `silero-vad` (torch) 迁移到 `SenseVoice ONNX` + `silero_vad.onnx` (onnxruntime)。

## Phase 0: 准备工作

### 下载模型

```bash
# SenseVoice int8 模型
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xvf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
# → model.int8.onnx (228MB) + tokens.txt

# Silero VAD ONNX 模型
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
```

**放置路径**：`backend/asr/models/`，后续通过 config 配置路径。

### 配置更新

`config.yaml` 新增字段：

```yaml
asr:
  engine: onnx                    # onnx | whisper（保留切换能力）
  model_path: backend/asr/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx
  tokens_path: backend/asr/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/tokens.txt
  vad_model_path: backend/asr/models/silero_vad.onnx
  num_threads: 4
  language: auto                  # auto | zh | en | yue | ja | ko
  use_itn: true                   # 逆文本规化（数字、日期等）
```

## Phase 1: ONNX Runtime 基础设施

### 1.1 `backend/asr/onnx/session.py`

ONNX Runtime 会话管理，可配置 `CPUExecutionProvider`，支持线程数、intra/inter op 并行度。

```python
class OrtSession:
    def __init__(self, model_path: str, num_threads: int = 4):
        # 创建 InferenceSession
        # 设置 session options (intra_op_num_threads, inter_op_num_threads)
        # 返回 session
    
    def run(self, input_dict: dict) -> list[np.ndarray]:
        # 封装 session.run()
```

### 1.2 `backend/asr/onnx/feature.py`

特征提取管线：raw PCM → FBank → LFR → CMVN。

```python
class FeatureExtractor:
    def __init__(self):
        # 初始化 kaldi-native-fbank OnlineFbank
        # 参数: 25ms帧长, 10ms帧移, 80 Mel bins, Hamming窗, dither=1.0
        
    def extract(self, audio: np.ndarray) -> np.ndarray:
        # 1. kaldi-native-fbank → 80-dim FBank
        # 2. LFR: stack 7 frames, skip 6 → 560-dim
        # 3. CMVN: (features + neg_mean) * inv_stddev
        # neg_mean/inv_stddev 从 ONNX 模型元数据读取
```

### 1.3 `backend/asr/onnx/decoder.py`

CTC 解码 + sentencepiece tokenizer。

```python
class CtcDecoder:
    def __init__(self, tokens_path: str):
        # 加载 sentencepiece 模型
        # 加载 tokens.txt 映射
        
    def decode(self, logits: np.ndarray) -> str:
        # argmax → 去重 → 去 blank → token_id → text
```

### 1.4 `backend/asr/onnx/model.py`

SenseVoice ONNX 模型封装，编排特征提取 → 推理 → 解码。

```python
class SenseVoiceONNX:
    def __init__(self, model_path, tokens_path, num_threads=4):
        # 加载 session + feature_extractor + decoder
        # 从模型元数据读取 LFR params + CMVN stats + language IDs
    
    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult:
        # 1. feature_extractor.extract(segment.audio)
        # 2. 构造输入: (features, x_length, language_id, textnorm_id)
        # 3. session.run()
        # 4. decoder.decode(logits)
        # 5. 返回 TranscriptionResult
```

**依赖**：`onnxruntime`, `kaldi-native-fbank`, `sentencepiece`

## Phase 2: VAD 替换

### 2.1 重写 `backend/asr/vad.py`

用 `silero_vad.onnx` 替换当前 `silero-vad` (torch) 实现。

```python
class VADEngine:
    def __init__(self, model_path: str, vad_threshold=0.5, silence_duration_ms=600):
        # 加载 silero_vad.onnx 到 ONNX Runtime
        # 状态机: SILENCE → SPEECH (同上)
    
    def process(self, frame: AudioFrame) -> Optional[SpeechSegment]:
        # 同现有接口，但使用 onnxruntime 推理
```

## Phase 3: 管线集成

### 3.1 替换 `backend/asr/transcriber.py`

删除原有 `Transcriber`（faster-whisper），对接 `SenseVoiceONNX`。

接口不变：

```python
class Transcriber:
    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult
```

内部实现改为调用 `SenseVoiceONNX.transcribe()`。

### 3.2 `ASRPipeline` 接口不变

```python
class ASRPipeline:
    async def run(self, callback):
        # async for frame in self.source:
        #     segment = self.vad.process(frame)
        #     if completed := self.buffer.add(segment):
        #         result = await self.transcriber.transcribe(completed)
        #         await callback(result)
```

所有外部调用方无需修改。

## Phase 4: 依赖清理

### 4.1 `pyproject.toml`

```toml
[project]
dependencies = [
    # ... 保留其他依赖
    # 移除:
    # "torch",
    # "torchaudio",
    # "faster-whisper>=1.0.0",
    # "silero-vad>=5.0",
    # 移除 ctranslate2（faster-whisper 的隐式依赖）
    # 新增:
    "onnxruntime>=1.18.0",
    "kaldi-native-fbank>=1.0",
    "sentencepiece>=0.2.0",
]

[project.optional-dependencies]
dev = [
    # 不变
]
```

### 4.2 清理已安装包

```bash
uv remove torch torchaudio faster-whisper ctranslate2 silero-vad
uv add onnxruntime kaldi-native-fbank sentencepiece
```

## Phase 5: 测试

### 5.1 单元测试

| 测试文件 | 覆盖内容 | 状态 |
|---------|---------|------|
| `tests/test_asr_frame.py` | 帧编解码 | 不变 |
| `tests/test_asr_source.py` | AudioSource | 不变 |
| `tests/test_asr_vad.py` | VADEngine (ONNX 版) | **改写** |
| `tests/test_asr_buffer.py` | AudioBuffer | 不变 |
| `tests/test_asr_transcriber.py` | Transcriber/SenseVoiceONNX | **改写** |
| `tests/test_asr_pipeline.py` | ASRPipeline | 不变 |

### 5.2 集成测试

使用预录 WAV 测试文件，验证 SenseVoice ONNX 推理输出正确文本：

```bash
uv run python scripts/test_asr_file.py --wav backend/asr/models/test_wavs/zh.wav
```

### 5.3 精度验证

用 3-5 段真实中文语音对比新旧管线的转录文本，确认 CER 无退化。

## Phase 6: 收尾

- 更新 `scripts/download_models.py` 下载 ONNX 模型
- 更新 `backend/config.py` 加载新配置项
- 删除 `backend/asr/transcriber.py`（逻辑已并入 `backend/asr/onnx/`）
- 删除 `sounddevice` 依赖（如之前添加过）
- 运行完整测试套件：`uv run pytest tests/ -v`

## 回退方案

若迁移后发现问题，可快速回退：

1. 恢复 `pyproject.toml` 中 torch/faster-whisper/silero-vad 依赖
2. `uv sync` 重新安装
3. 将 `config.yaml` `asr.engine` 设回 `whisper`
4. `Transcriber` 中通过 `asr.engine` 字段分发到 whisper 或 onnx 实现
