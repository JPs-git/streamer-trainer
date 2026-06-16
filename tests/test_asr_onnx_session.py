from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def mock_ort_session():
    with patch("onnxruntime.InferenceSession") as m:
        session = MagicMock()
        session.get_modelmeta.return_value.custom_metadata_map = {}
        session.get_inputs.return_value = [
            MagicMock(name="speech"),
            MagicMock(name="speech_lengths"),
            MagicMock(name="lang"),
            MagicMock(name="textnorm"),
        ]
        m.return_value = session
        yield session


@pytest.fixture
def mock_ort_session_with_metadata():
    with patch("onnxruntime.InferenceSession") as m:
        session = MagicMock()
        session.get_modelmeta.return_value.custom_metadata_map = {
            "mean": " ".join(str(float(i)) for i in range(560)),
            "inv_std": " ".join(str(1.0 / (i + 1)) for i in range(560)),
        }
        m.return_value = session
        yield session


def test_session_creates_with_threads(mock_ort_session):
    from backend.asr.onnx.session import OrtSession

    session = OrtSession("dummy.onnx", num_threads=2)

    assert session.session is mock_ort_session


def test_session_reads_metadata(mock_ort_session_with_metadata):
    from backend.asr.onnx.session import OrtSession

    session = OrtSession("dummy.onnx")

    assert "mean" in session.metadata
    assert "inv_std" in session.metadata


def test_session_run_returns_expected(mock_ort_session):
    from backend.asr.onnx.session import OrtSession

    mock_ort_session.run.return_value = [np.array([[0.1, 0.9]])]
    session = OrtSession("dummy.onnx")

    result = session.run({"input": np.array([[1.0]])})

    np.testing.assert_array_equal(result[0], [[0.1, 0.9]])
