"""预下载 SenseVoice ONNX ASR 模型 + Silero VAD ONNX 模型。

用法:
    uv run python scripts/download_models.py
"""

import argparse
import tarfile
import urllib.request
from pathlib import Path

SENSEVOICE_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
)
SILERO_VAD_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
)

MODELS_DIR = Path(__file__).resolve().parent.parent / "backend" / "asr" / "models"


def download_file(url: str, dest: Path) -> None:
    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, dest)
    print(f"  -> {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Pre-download ONNX ASR models")
    parser.add_argument("--sensevoice", action="store_true", help="Download SenseVoice model only")
    parser.add_argument("--vad", action="store_true", help="Download VAD model only")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    do_sensevoice = not args.vad or args.sensevoice
    do_vad = not args.sensevoice or args.vad

    if do_sensevoice:
        tar_path = MODELS_DIR / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
        model_dir = MODELS_DIR / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
        if not model_dir.is_dir():
            download_file(SENSEVOICE_URL, tar_path)
            print("Extracting...")
            with tarfile.open(tar_path, "r:bz2") as tar:
                tar.extractall(path=MODELS_DIR)
            tar_path.unlink()
            print(f"  Extracted to {model_dir}")
        else:
            print(f"SenseVoice model already exists at {model_dir}")

    if do_vad:
        vad_path = MODELS_DIR / "silero_vad.onnx"
        if not vad_path.is_file():
            download_file(SILERO_VAD_URL, vad_path)
        else:
            print(f"VAD model already exists at {vad_path}")

    print("\nDone! Models ready at:", MODELS_DIR)


if __name__ == "__main__":
    main()
