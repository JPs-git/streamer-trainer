from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class ViewerMemory:
    streamer_log: list[dict] = field(default_factory=list)
    my_danmaku: list[dict] = field(default_factory=list)
    other_danmaku: list[dict] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)

    def add_streamer_log(self, text: str, offset: int):
        self.streamer_log.append({"text": text, "offset": offset})

    def add_my_danmaku(self, text: str, offset: int, directed_to: str):
        self.my_danmaku.append({
            "text": text, "offset": offset, "directed_to": directed_to
        })

    def add_other_danmaku(self, from_id: str, directed_to: str, summary: str):
        self.other_danmaku.append({
            "from_id": from_id, "directed_to": directed_to, "summary": summary
        })

    def update_relationship(self, viewer_id: str, description: str):
        self.relationships[viewer_id] = description


@dataclass
class VirtualViewer:
    viewer_id: str
    name: str
    persona: str
    follows: bool = True
    relationship: str = ""
    personality_type: str = ""
    state: Literal["inactive", "active", "cooldown"] = "inactive"
    memory: ViewerMemory = field(default_factory=ViewerMemory)
    entry_time: Optional[int] = None
    last_active: Optional[int] = None
    deactivated_at: Optional[int] = None
    interaction_count: int = 0
    engagement: int = 100  # 0-100
