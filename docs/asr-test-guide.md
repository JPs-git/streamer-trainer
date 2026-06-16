# ASR 实时语音识别测试指南

## 架构概览

```
麦克风 (WSL/Windows)
  │  sounddevice InputStream (16kHz int16, 100ms帧)
  │  AudioFrame.encode_frame() → 二进制帧协议
  ▼
/audio WebSocket → WSAudioSource
  │
  ▼
VADEngine (silero_vad.onnx)
  │  512样本窗口, ONNX Runtime 推理
  │  状态机: silence → speech → final
  ▼
AudioBuffer
  │  累积语音段, 静音600ms + 最大10s 截断
  ▼
Transcriber (SenseVoice ONNX)
  │  kaldi-native-fbank → LFR (m=7/n=6) → ONNX → CTC解码
  │  支持 zh/en/ja/ko/yue 自动检测
  ▼
OutputHandler → streamer_timeline + room_chat_log + /danmaku广播
```

## 启动

```bash
# 1. 安装依赖
uv sync --group dev

# 2. 下载模型 (首次)
uv run python scripts/download_models.py

# 3. 启动后端
uv run python -m backend.main

# 4. 打开前端
# 浏览器访问 http://localhost:8765
```

## 测试方法

### 方式一：实时麦克风测试

```bash
# 另开终端
uv run python scripts/test_end_to_end_mic.py
```

输出示例：
```
15:10:38 [mic_test] INFO Connected to /audio
15:10:38 [mic_test] INFO Connected to /danmaku
15:10:39 [mic_test] INFO Sent 10 frames | audio level: 482
  [ASR] 你好我是主播
  [ASR] 今天我们来聊聊天
...
```

- 每 1 秒打印音频电平（音频活跃时 > 0）
- ASR 识别结果实时打印 `[ASR] 文本`
- Ctrl+C 退出

### 方式二：WAV 文件测试

```bash
uv run python scripts/test_pipeline_wav.py
```

输出示例：
```
Running ASR pipeline...
  [0.00s - 3.50s] 你好我是星湖破碎欢迎进入直播间
  [3.50s - 7.00s] 今天我们要聊的是关于录制的二三事

Total segments: 2
Full transcription: 你好我是星湖破碎欢迎进入直播间 今天我们要聊的是关于录制的二三事
```

### 方式三：API 调试

```bash
# 手动添加文本到 timeline（不经过 ASR）
curl -X POST http://localhost:8765/debug_text \
  -H "Content-Type: application/json" \
  -d '{"text": "测试文本"}'

# 控制调度器
curl -X POST http://localhost:8765/control/scheduler \
  -H "Content-Type: application/json" \
  -d '{"action": "resume"}'
curl -X POST http://localhost:8765/control/scheduler \
  -H "Content-Type: application/json" \
  -d '{"action": "pause"}'
```

## 全链路流程

```
麦克风 → frame → /audio WS → VAD → Buffer → Transcriber → timeline
                                                              ↓
前端 ← /danmaku WS ← 调度器 ← timeline + chat_log ← ← ←
         ↑                    ↑
   观众弹幕/进场    tick: 每10-15s
```

- 调度器默认**暂停**，需要前端按钮或 API 开启
- 开启后自动管理观众进场/离场/发言
- 发言概率：路人 35%，引导型 60%；主播有发言时概率 ×3

## 关键配置 (config.yaml)

```yaml
asr:
  engine: onnx
  model_path: backend/asr/models/sherpa-onnx-sense-voice-.../model.int8.onnx
  tokens_path: .../tokens.txt
  vad_model_path: backend/asr/models/silero_vad.onnx
  num_threads: 4
  language: auto
  use_itn: true
  vad_threshold: 0.5
  silence_duration_ms: 600
  max_segment_duration: 10.0
```

## 运行测试

```bash
uv run pytest tests/ -v        # 全部 95 个测试
uv run pytest tests/test_asr_onnx_model.py  # ONNX ASR 测试
uv run pytest tests/test_asr_vad.py         # VAD 测试
```
