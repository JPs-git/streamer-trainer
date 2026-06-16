from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest


@pytest.fixture
def tokens_file():
    content = [
        "<blank> 0",
        "a 1",
        "b 2",
        "c 3",
        "<sos/eos> 4",
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(content) + "\n")
        path = f.name
    yield path
    os.unlink(path)


def test_decode_simple(tokens_file):
    from backend.asr.onnx.decoder import CtcDecoder

    decoder = CtcDecoder(tokens_file)
    logits = np.zeros((1, 5, 5), dtype=np.float32)
    logits[0, 0, 0] = 1.0
    logits[0, 1, 0] = 1.0
    logits[0, 2, 1] = 1.0
    logits[0, 3, 1] = 1.0
    logits[0, 4, 2] = 1.0

    text = decoder.decode(logits)

    assert text == "ab"


def test_decode_removes_blanks(tokens_file):
    from backend.asr.onnx.decoder import CtcDecoder

    decoder = CtcDecoder(tokens_file)
    logits = np.zeros((1, 5, 5), dtype=np.float32)
    for t in range(5):
        logits[0, t, 0] = 1.0

    text = decoder.decode(logits)

    assert text == ""


def test_decode_collapses_repeats(tokens_file):
    from backend.asr.onnx.decoder import CtcDecoder

    decoder = CtcDecoder(tokens_file)
    logits = np.zeros((1, 6, 5), dtype=np.float32)
    logits[0, 0, 0] = 1.0
    logits[0, 1, 1] = 1.0
    logits[0, 2, 1] = 1.0
    logits[0, 3, 0] = 1.0
    logits[0, 4, 2] = 1.0
    logits[0, 5, 2] = 1.0

    text = decoder.decode(logits)

    assert text == "ab"


def test_decode_with_word_boundary():
    from backend.asr.onnx.decoder import CtcDecoder

    content = [
        "<blank> 0",
        "▁hello 1",
        "world 2",
        "▁foo 3",
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(content) + "\n")
        wb_path = f.name

    decoder = CtcDecoder(wb_path)
    logits = np.zeros((1, 3, 4), dtype=np.float32)
    logits[0, 0, 1] = 1.0
    logits[0, 1, 2] = 1.0
    logits[0, 2, 3] = 1.0

    text = decoder.decode(logits)

    assert text == "helloworld foo"
    os.unlink(wb_path)
