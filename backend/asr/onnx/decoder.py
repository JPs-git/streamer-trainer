from __future__ import annotations

from pathlib import Path

import numpy as np


class CtcDecoder:
    def __init__(self, tokens_path: str):
        self.id_to_token: dict[int, str] = {}
        with open(tokens_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.rsplit(" ", 1)
                if len(parts) == 2:
                    token, token_id = parts
                    self.id_to_token[int(token_id)] = token

    def _is_special_token(self, token: str) -> bool:
        return token.startswith("<|") and token.endswith("|>")

    def decode(self, logits: np.ndarray) -> str:
        token_ids = logits.argmax(axis=-1).squeeze(0).tolist()
        collapsed = []
        prev = -1
        for t in token_ids:
            if t != prev and t != 0:
                collapsed.append(t)
            prev = t

        parts = []
        for tid in collapsed:
            token = self.id_to_token.get(tid, "")
            if not token or self._is_special_token(token):
                continue
            if token.startswith("▁"):
                parts.append(token[1:])
            else:
                if parts:
                    parts[-1] += token
                else:
                    parts.append(token)

        return " ".join(parts)
