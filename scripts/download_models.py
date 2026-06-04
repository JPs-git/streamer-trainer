"""预下载 Whisper ASR 模型到本地 HuggingFace 缓存。

用法:
    uv run python scripts/download_models.py
    uv run python scripts/download_models.py --model tiny
    uv run python scripts/download_models.py --model large-v3

默认模型从 config.yaml 的 asr.model_size 读取。
"""

import argparse
import sys
from pathlib import Path

import yaml


def get_default_model() -> str:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        return raw.get("asr", {}).get("model_size", "base")
    except Exception as e:
        print(f"Warning: could not read config.yaml ({e}), falling back to 'base'")
        return "base"


def main():
    parser = argparse.ArgumentParser(description="Pre-download Whisper ASR model")
    parser.add_argument(
        "--model",
        default=None,
        help="Model size/name (default: read from config.yaml)",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="HuggingFace cache directory (default: ~/.cache/huggingface/hub/)",
    )
    args = parser.parse_args()

    model_name = args.model or get_default_model()
    kwargs = {}
    if args.cache_dir:
        kwargs["cache_dir"] = args.cache_dir

    print(f"Downloading model '{model_name}'...")
    print(f"Cache directory: {args.cache_dir or '~/.cache/huggingface/hub/'}")
    print("This may take a few minutes depending on model size and network speed.")
    print()

    from faster_whisper.utils import download_model

    path = download_model(model_name, **kwargs)
    print(f"Done! Model cached at: {path}")


if __name__ == "__main__":
    main()
