from __future__ import annotations
import random
import time
from backend.viewer.models import VirtualViewer
from backend.viewer.personas import ALL_PERSONAS


class ViewerManager:
    def __init__(self, max_active: int = 8, min_active: int = 3, cooldown_sec: int = 300):
        self.max_active = max_active
        self.min_active = min_active
        self.cooldown_sec = cooldown_sec
        self._all_viewers: dict[str, VirtualViewer] = {}
        self._active_ids: set[str] = set()
        self._cooldown_ids: set[str] = set()
        self._init_viewers()

    def _init_viewers(self):
        for p in ALL_PERSONAS:
            v = VirtualViewer(
                viewer_id=p["viewer_id"],
                name=p["name"],
                persona=p["persona"],
                personality_type=p["personality_type"],
            )
            self._all_viewers[v.viewer_id] = v
        self._fill_to_min()

    def _fill_to_min(self):
        available = [vid for vid, v in self._all_viewers.items()
                     if v.state == "inactive"]
        random.shuffle(available)
        to_activate = available[:self.min_active - len(self._active_ids)]
        for vid in to_activate:
            self.activate_viewer(vid)

    def activate_viewer(self, viewer_id: str):
        if len(self._active_ids) >= self.max_active:
            return
        v = self._all_viewers.get(viewer_id)
        if v and v.state == "inactive":
            v.state = "active"
            v.entry_time = int(time.time())
            v.last_active = int(time.time())
            self._active_ids.add(viewer_id)
            self._cooldown_ids.discard(viewer_id)

    def deactivate_viewer(self, viewer_id: str):
        v = self._all_viewers.get(viewer_id)
        if v and v.state == "active":
            v.state = "cooldown"
            v.deactivated_at = int(time.time())
            self._active_ids.discard(viewer_id)
            self._cooldown_ids.add(viewer_id)

    def get_viewer(self, viewer_id: str) -> VirtualViewer | None:
        return self._all_viewers.get(viewer_id)

    def get_active_viewers(self) -> list[VirtualViewer]:
        return [self._all_viewers[vid] for vid in self._active_ids
                if vid in self._all_viewers]

    def tick(self):
        now = int(time.time())
        active = self.get_active_viewers()
        if len(active) >= self.max_active:
            oldest = min(active, key=lambda v: v.entry_time or 0)
            self.deactivate_viewer(oldest.viewer_id)
            active = self.get_active_viewers()
        if len(active) < self.min_active:
            self._fill_to_min()

        cooldown_expired = [
            vid for vid in self._cooldown_ids
            if now - (self._all_viewers[vid].deactivated_at or 0) > self.cooldown_sec
        ]
        for vid in cooldown_expired:
            self._all_viewers[vid].state = "inactive"
        self._cooldown_ids -= set(cooldown_expired)
