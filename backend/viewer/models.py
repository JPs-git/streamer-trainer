from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

ViewerType = Literal["lurker", "guider"]


@dataclass
class ViewerMemory:
    my_danmaku: list[dict] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)

    def add_my_danmaku(self, text: str, offset: int, directed_to: str):
        self.my_danmaku.append({
            "text": text, "offset": offset, "directed_to": directed_to
        })

    def update_relationship(self, viewer_id: str, description: str):
        self.relationships[viewer_id] = description


@dataclass
class VirtualViewer:
    viewer_id: str
    name: str
    persona: str
    viewer_type: ViewerType = "lurker"
    follows: bool = True
    relationship: str = ""
    personality_type: str = ""
    state: Literal["inactive", "active", "cooldown"] = "inactive"
    memory: ViewerMemory = field(default_factory=ViewerMemory)
    entry_time: Optional[int] = None
    last_active: Optional[int] = None
    deactivated_at: Optional[int] = None
    interaction_count: int = 0
