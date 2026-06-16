# ADR: ASR 管线迁移 — faster-whisper → FunASR SenseVoice ONNX

## 状态

已决策，待实施

## 日期

2026-06-16

## 背景

当前 ASR 管线使用 `faster-whisper` (base model) + `silero-vad`，均依赖 `torch`。`torch` 在无 GPU 的开发环境下仍需要下载 ~4GB 的 CUDA 库，拖慢 CI 和本地构建。同时 Whisper 的中文识别精度（CER 9-18%）远落后于中文专用模型。

## 决策

替换 ASR 管线为 **FunASR SenseVoice-Small ONNX int8 模型**，通过 `onnxruntime` 进行 CPU 推理。

## 驱动因素

1. **消除 torch 依赖** — 切换到纯 ONNX Runtime，依赖体积从 ~4GB 降至 ~40MB（不含模型）
2. **中文精度提升** — SenseVoice 在 AISHELL-1 的 CER 为 2.8%，vs Whisper large-v3 的 9.1%
3. **CPU 推理更优** — SenseVoice ONNX int8 在 CPU 上 RTF 0.02-0.06（17-50x 实时），faster-whisper base 在 CPU 上约 1x 实时
4. **内置功能** — SenseVoice 单模型包含 ASR + VAD + 语种识别 + 情感识别 + 音频事件检测 + ITN（逆文本规化）

## 否决方案

| 方案 | 否决原因 |
|------|----------|
| 保持 faster-whisper + torch | torch 依赖体积不可接受，中文精度不足 |
| FunASR SenseVoice + PyTorch | 仍依赖 torch，未解决核心问题 |
| FunASR Paraformer ONNX | 精度略低于 SenseVoice，且只支持中英文 |
| sherpa-onnx 全栈集成 | 功能重叠过多，控制力不足，定制成本高 |

## 新架构

```
                onnxruntime                onnxruntime
silero_vad.onnx ────────── SenseVoice ──────────────────
                                         model.int8.onnx
Mic → AudioFrame → VAD(ONNX) → Buffer → FeatureExtract → ONNX Inference → CTC Decode → Text
                  (kaldi-native-fbank + LFR + CMVN + sentencepiece)
```

### 组件变更

| 组件 | 当前 (删除) | 新增 |
|------|-------------|------|
| VAD | `silero-vad` (torch) | `silero_vad.onnx` (onnxruntime) |
| ASR | `faster-whisper` + `ctranslate2` | `SenseVoiceONNX` + `kaldi-native-fbank` + `sentencepiece` |
| 模型 | Whisper base ~140MB | SenseVoice int8 ~228MB |

### 依赖变更

| 操作 | 包 | 体积 |
|------|-----|------|
| 移除 | `torch`, `torchaudio` | ~4GB |
| 移除 | `faster-whisper`, `ctranslate2` | ~100MB |
| 移除 | `silero-vad` | ~5MB |
| 新增 | `onnxruntime` | ~10MB |
| 新增 | `kaldi-native-fbank` | ~5MB |
| 新增 | `sentencepiece` | ~1MB |

### 新增目录结构

```
backend/asr/
├── __init__.py
├── frame.py              # 不变
├── source.py              # 不变
├── vad.py                 # 重写：silero_vad.onnx 封装，替代 torch 版
├── buffer.py              # 不变
├── transcriber.py         # 删除，由 onnx/ 替代
├── pipeline.py            # 不变
├── output.py              # 不变
└── onnx/                  # 新增
    ├── __init__.py
    ├── session.py          # ONNX Runtime 会话管理
    ├── feature.py          # kaldi-native-fbank + LFR + CMVN
    ├── decoder.py          # CTC 解码 + sentencepiece tokenizer
    └── model.py            # SenseVoiceONNX 封装
```

## 风险

1. **FBank 数值差异** — `kaldi-native-fbank` 与 `torchaudio.compliance.kaldi.fbank` 不是同一个实现，存在 ~1e-4 的浮点误差，但经业界验证不影响 ASR 精度
2. **kaldi-native-fbank 编译** — C++ native 扩展，Linux x86_64 有预编译 wheel，arm/riscv 需要编译工具链
3. **ONNX 模型分发** — 228MB 模型需要下载，需加入下载脚本或首次运行时懒加载
4. **回退成本** — 切换后如果出现问题，回退需要重新安装 torch 全家桶

## 结论

迁移收益远大于风险。SenseVoice ONNX 方案在中文精度、CPU 实时率和依赖体积三个维度都显著优于当前方案。迁移后开发环境不再需要 torch，CI 流水线也将显著加速。
