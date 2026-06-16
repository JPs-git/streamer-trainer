from __future__ import annotations

import numpy as np
import pytest


def test_feature_extractor_output_shape():
    from backend.asr.onnx.feature import FeatureExtractor

    extractor = FeatureExtractor()
    sr = 16000
    audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr, endpoint=False)).astype(np.float32)

    features = extractor.extract(audio)

    assert features.ndim == 3
    assert features.shape[0] == 1
    assert features.shape[2] == 560


def test_feature_extractor_realistic_audio():
    from backend.asr.onnx.feature import FeatureExtractor

    extractor = FeatureExtractor()
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    audio = (0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)

    features = extractor.extract(audio)

    num_frames = features.shape[1]
    expected_fbank = int((0.5 - 0.025) / 0.010) + 1
    expected_lfr = (expected_fbank - 7) // 6 + 1
    assert num_frames == expected_lfr


def test_feature_extractor_different_lengths():
    from backend.asr.onnx.feature import FeatureExtractor

    extractor = FeatureExtractor()

    audio_short = np.zeros(int(16000 * 0.3), dtype=np.float32)
    audio_long = np.zeros(int(16000 * 2.0), dtype=np.float32)

    feat_short = extractor.extract(audio_short)
    feat_long = extractor.extract(audio_long)

    assert feat_short.shape[0] == 1
    assert feat_long.shape[0] == 1
    assert feat_long.shape[1] > feat_short.shape[1]
