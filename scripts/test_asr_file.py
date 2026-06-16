"""测试 ASR 管线：读取 WAV 文件 → 转写 → 输出文本。

用法:
    cd /home/administrator/projects/streamer-trainer
    .venv/bin/python scripts/test_asr_file.py
    .venv/bin/python scripts/test_asr_file.py --model tiny
"""

import argparse
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from backend.asr.transcriber import Transcriber
from backend.asr.vad import SpeechSegment


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, sr


def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio
    ratio = target_sr / orig_sr
    n_out = int(len(audio) * ratio)
    return np.interp(
        np.linspace(0, len(audio) - 1, n_out),
        np.arange(len(audio)),
        audio,
    )


def main():
    parser = argparse.ArgumentParser(description="Test ASR pipeline with a WAV file")
    parser.add_argument("--wav", default=None, help="Path to WAV file")
    parser.add_argument("--model", default=None, help="Whisper model size")
    args = parser.parse_args()

    wav_path = args.wav or str(Path(__file__).resolve().parent.parent / "backend" / "data" / "hello.wav")
    if not Path(wav_path).is_file():
        print(f"Error: file not found: {wav_path}")
        return

    print(f"Reading: {wav_path}")
    audio, sr = read_wav(wav_path)
    duration = len(audio) / sr
    print(f"  Sample rate: {sr} Hz")
    print(f"  Duration: {duration:.1f}s")
    print(f"  Samples: {len(audio)}")

    if sr != 16000:
        print(f"  Resampling {sr} → 16000...")
        audio = resample(audio, sr, 16000)

    segment = SpeechSegment(
        audio=audio,
        start_time=0.0,
        end_time=len(audio) / 16000.0,
        final=True,
    )

    kwargs = {}
    if args.model:
        kwargs["model_size"] = args.model
    transcriber = Transcriber(**kwargs)

    print("Transcribing...")
    t0 = time.time()
    import asyncio
    result = asyncio.run(transcriber.transcribe(segment))
    elapsed = time.time() - t0

    print(f"\nResult ({elapsed:.1f}s):")
    print(f"  Text: {result.text!r}")
    print(f"  Start: {result.start_time:.1f}s")
    print(f"  End: {result.end_time:.1f}s")


if __name__ == "__main__":
    main()
