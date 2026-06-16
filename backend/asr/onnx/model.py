from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np

from backend.asr.onnx.decoder import CtcDecoder
from backend.asr.onnx.feature import FeatureExtractor
from backend.asr.onnx.session import OrtSession
from backend.asr.vad import SpeechSegment, TranscriptionResult

logger = logging.getLogger(__name__)

LANGUAGE_MAP: dict[str, int] = {
    "auto": 0,
    "zh": 3,
    "en": 4,
    "yue": 2,
    "ja": 5,
    "ko": 6,
    "nospeech": 7,
}


class SenseVoiceONNX:
    def __init__(
        self,
        model_path: str,
        tokens_path: str,
        num_threads: int = 4,
        language: str = "auto",
        use_itn: bool = True,
    ):
        self.session = OrtSession(model_path, num_threads=num_threads)
        self.decoder = CtcDecoder(tokens_path)
        self.language = language
        self.use_itn = use_itn

        meta = self.session.metadata

        mean_str = meta.get("neg_mean", "")
        inv_std_str = meta.get("inv_stddev", "")
        if mean_str and inv_std_str:
            sep = "," if "," in mean_str else " "
            mean = np.fromstring(mean_str, sep=sep, dtype=np.float32)
            inv_std = np.fromstring(inv_std_str, sep=sep, dtype=np.float32)
        else:
            mean = np.zeros(560, dtype=np.float32)
            inv_std = np.ones(560, dtype=np.float32)

        lfr_m = int(meta.get("lfr_window_size", "7"))
        lfr_n = int(meta.get("lfr_window_shift", "6"))

        self.feature_extractor = FeatureExtractor(
            lfr_m=lfr_m, lfr_n=lfr_n, mean=mean, inv_std=inv_std,
        )

    async def transcribe(self, segment: SpeechSegment) -> TranscriptionResult:
        if segment.audio.size == 0:
            return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)

        audio = segment.audio * 32768.0
        features = await asyncio.get_running_loop().run_in_executor(
            None, self.feature_extractor.extract, audio,
        )
        if features.shape[1] == 0:
            return TranscriptionResult(text="", start_time=segment.start_time, end_time=segment.end_time)

        x_length = np.array([features.shape[1]], dtype=np.int32)
        lang = np.array([LANGUAGE_MAP.get(self.language, 0)], dtype=np.int32)
        text_norm = np.array([14 if self.use_itn else 15], dtype=np.int32)

        input_dict = {
            "x": features,
            "x_length": x_length,
            "language": lang,
            "text_norm": text_norm,
        }

        logits = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.session.run(input_dict)[0],
        )

        text = self.decoder.decode(logits)

        return TranscriptionResult(text=text, start_time=segment.start_time, end_time=segment.end_time)
