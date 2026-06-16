from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.asr.vad import SpeechSegment

MEAN_STR = ",".join("0.0" for _ in range(560))
INV_STD_STR = ",".join("1.0" for _ in range(560))


@pytest.fixture
def mock_sensevoice():
    with (
        patch("backend.asr.onnx.session.onnxruntime.InferenceSession") as ort_mock,
        patch("backend.asr.onnx.model.FeatureExtractor") as feat_mock,
        patch("backend.asr.onnx.model.CtcDecoder") as dec_mock,
    ):
        ort_session = MagicMock()
        ort_session.get_modelmeta.return_value.custom_metadata_map = {
            "neg_mean": MEAN_STR,
            "inv_stddev": INV_STD_STR,
            "lfr_window_size": "7",
            "lfr_window_shift": "6",
        }
        ort_session.get_inputs.return_value = [
            MagicMock(name="x"),
            MagicMock(name="x_length"),
            MagicMock(name="language"),
            MagicMock(name="text_norm"),
        ]
        ort_mock.return_value = ort_session

        feat_instance = MagicMock()
        feat_instance.extract.return_value = np.zeros((1, 10, 560), dtype=np.float32)
        feat_mock.return_value = feat_instance

        dec_instance = MagicMock()
        dec_instance.decode.return_value = "你好世界"
        dec_mock.return_value = dec_instance

        yield {"ort": ort_session, "feat": feat_instance, "dec": dec_instance}


@pytest.mark.asyncio
async def test_model_transcribe_returns_text(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens")
    segment = SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=0.0, end_time=1.0)

    result = await model.transcribe(segment)

    assert result.text == "你好世界"
    assert result.start_time == 0.0
    assert result.end_time == 1.0


@pytest.mark.asyncio
async def test_model_transcribe_calls_extract(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens")
    audio = np.random.randn(16000).astype(np.float32)
    segment = SpeechSegment(audio=audio, start_time=0.0, end_time=1.0)

    await model.transcribe(segment)

    mock_sensevoice["feat"].extract.assert_called_once()
    args = mock_sensevoice["feat"].extract.call_args[0][0]
    np.testing.assert_array_equal(args, audio * 32768.0)


@pytest.mark.asyncio
async def test_model_transcribe_empty_audio(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens")
    segment = SpeechSegment(audio=np.array([], dtype=np.float32), start_time=0.0, end_time=0.0)

    result = await model.transcribe(segment)

    assert result.text == ""
    mock_sensevoice["ort"].run.assert_not_called()


@pytest.mark.asyncio
async def test_model_uses_correct_input_names(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens")
    segment = SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=0.0, end_time=1.0)

    await model.transcribe(segment)

    input_dict = mock_sensevoice["ort"].run.call_args[0][1]
    assert "x" in input_dict
    assert "x_length" in input_dict
    assert "language" in input_dict
    assert "text_norm" in input_dict


@pytest.mark.asyncio
async def test_model_uses_language_zh(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens", language="zh")
    segment = SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=0.0, end_time=1.0)

    await model.transcribe(segment)

    input_dict = mock_sensevoice["ort"].run.call_args[0][1]
    assert input_dict["language"][0] == 3


@pytest.mark.asyncio
async def test_model_uses_itn(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens", use_itn=True)
    segment = SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=0.0, end_time=1.0)

    await model.transcribe(segment)

    input_dict = mock_sensevoice["ort"].run.call_args[0][1]
    assert input_dict["text_norm"][0] == 14


@pytest.mark.asyncio
async def test_model_no_itn(mock_sensevoice):
    from backend.asr.onnx.model import SenseVoiceONNX

    model = SenseVoiceONNX("dummy.onnx", "dummy.tokens", use_itn=False)
    segment = SpeechSegment(audio=np.zeros(16000, dtype=np.float32), start_time=0.0, end_time=1.0)

    await model.transcribe(segment)

    input_dict = mock_sensevoice["ort"].run.call_args[0][1]
    assert input_dict["text_norm"][0] == 15
