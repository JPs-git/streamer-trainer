from __future__ import annotations

from typing import Optional

import kaldi_native_fbank as knf
import numpy as np


class FeatureExtractor:
    def __init__(
        self,
        lfr_m: int = 7,
        lfr_n: int = 6,
        mean: Optional[np.ndarray] = None,
        inv_std: Optional[np.ndarray] = None,
    ):
        self.lfr_m = lfr_m
        self.lfr_n = lfr_n
        self.mean = mean
        self.inv_std = inv_std
        opts = knf.FbankOptions()
        opts.frame_opts.samp_freq = 16000
        opts.frame_opts.frame_shift_ms = 10
        opts.frame_opts.frame_length_ms = 25
        opts.frame_opts.dither = 1.0
        opts.mel_opts.num_bins = 80
        opts.use_log_fbank = True
        opts.use_power = True
        self._opts = opts

    def extract(self, audio: np.ndarray) -> np.ndarray:
        fbank = knf.OnlineFbank(self._opts)
        fbank.accept_waveform(16000, audio.astype(np.float32).tolist())
        fbank.input_finished()
        num_frames = fbank.num_frames_ready
        if num_frames == 0:
            return np.zeros((1, 0, self.lfr_m * 80), dtype=np.float32)

        feats = np.array([fbank.get_frame(i) for i in range(num_frames)], dtype=np.float32)

        num_lfr = (num_frames - self.lfr_m) // self.lfr_n + 1
        if num_lfr <= 0:
            return np.zeros((1, 0, self.lfr_m * 80), dtype=np.float32)

        out = np.zeros((num_lfr, self.lfr_m * 80), dtype=np.float32)
        for i in range(num_lfr):
            start = i * self.lfr_n
            out[i] = feats[start:start + self.lfr_m].ravel()

        if self.mean is not None and self.inv_std is not None:
            out = (out + self.mean) * self.inv_std

        return out[np.newaxis, :, :]
