from __future__ import annotations

from typing import Any

import numpy as np
import onnxruntime


class OrtSession:
    def __init__(self, model_path: str, num_threads: int = 4):
        opts = onnxruntime.SessionOptions()
        opts.intra_op_num_threads = num_threads
        opts.inter_op_num_threads = num_threads
        self.session = onnxruntime.InferenceSession(
            model_path, opts, providers=["CPUExecutionProvider"],
        )
        self.metadata = self.session.get_modelmeta().custom_metadata_map or {}

    @property
    def input_names(self) -> list[str]:
        return [inp.name for inp in self.session.get_inputs()]

    def run(self, input_dict: dict[str, np.ndarray]) -> list[np.ndarray]:
        return self.session.run(None, input_dict)
