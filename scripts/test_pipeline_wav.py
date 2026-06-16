"""测试 ASR 管线：读取 WAV 文件，经过 VAD + Buffer + Transcriber，输出结果。"""

import asyncio
import wave
from pathlib import Path

import numpy as np

from backend.asr.frame import AudioFrame, encode_frame
from backend.asr.source import FileAudioSource
from backend.asr.vad import VADEngine
from backend.asr.buffer import AudioBuffer
from backend.asr.transcriber import Transcriber
from backend.asr.pipeline import ASRPipeline
from backend.asr.output import OutputHandler


def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear resampling."""
    duration = len(audio) / orig_sr
    target_len = int(duration * target_sr)
    indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def wav_to_frame_file(wav_path: str, out_path: str, target_sr: int = 16000,
                      frame_dur_s: float = 0.5):
    """Convert WAV to frame-format file for FileAudioSource."""
    with wave.open(wav_path) as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16)

    if sr != target_sr:
        audio = np.clip(np.round(resample(audio.astype(np.float32), sr, target_sr)), -32768, 32767).astype(np.int16)

    frame_size = int(target_sr * frame_dur_s)
    with open(out_path, "wb") as f:
        for start in range(0, len(audio), frame_size):
            chunk = audio[start:start + frame_size]
            if len(chunk) < frame_size:
                chunk = np.pad(chunk, (0, frame_size - len(chunk)), "constant")
            af = AudioFrame(
                payload=chunk.tobytes(),
                timestamp_ms=int(start / target_sr * 1000),
                sample_rate=target_sr,
                channels=1,
            )
            f.write(encode_frame(af))


async def main():
    config = {
        "model_path": "backend/asr/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx",
        "tokens_path": "backend/asr/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/tokens.txt",
        "vad_model_path": "backend/asr/models/silero_vad.onnx",
        "num_threads": 4,
    }

    # Convert WAV to frame format
    tmp_path = Path("/tmp/test_frames.bin")
    wav_to_frame_file("backend/data/hello.wav", str(tmp_path))

    # Build pipeline
    source = FileAudioSource(str(tmp_path))
    vad = VADEngine(
        model_path=config["vad_model_path"],
        vad_threshold=0.5,
        silence_duration_ms=600,
    )
    buffer = AudioBuffer(max_segment_duration=10.0)
    transcriber = Transcriber(
        model_path=config["model_path"],
        tokens_path=config["tokens_path"],
        num_threads=config["num_threads"],
    )
    pipeline = ASRPipeline(
        source=source,
        vad=vad,
        buffer=buffer,
        transcriber=transcriber,
    )

    # Collect results
    results: list[str] = []

    async def callback(result):
        text = result.text.strip()
        if text:
            print(f"  [{result.start_time:.2f}s - {result.end_time:.2f}s] {text}")
            results.append(text)

    print("Running ASR pipeline...")
    await pipeline.run(callback)

    if not results:
        print("(no speech detected)")
    else:
        print(f"\nTotal segments: {len(results)}")
        print(f"Full transcription: {' '.join(results)}")

    tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
