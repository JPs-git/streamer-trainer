from __future__ import annotations
import asyncio
import time
import logging
from typing import Callable, Optional

from backend.asr.vad import TranscriptionResult

logger = logging.getLogger(__name__)


class OutputHandler:
    def __init__(self, timeline: list[dict], chat_log: list[dict],
                 broadcast: Optional[Callable] = None):
        self.timeline = timeline
        self.chat_log = chat_log
        self.broadcast = broadcast

    def on_result(self, result: TranscriptionResult):
        text = result.text.strip()
        if not text:
            return

        ts = int(time.time())
        self.timeline.append({"text": text, "offset": ts})
        self.chat_log.append({"type": "streamer", "name": "主播", "text": text, "offset": ts})
        logger.info("ASR: %s", text)

        if self.broadcast:
            self.broadcast({
                "type": "streamer",
                "text": text,
                "timestamp": ts,
            })

        if len(self.chat_log) > 200:
            self.chat_log[:50] = []
