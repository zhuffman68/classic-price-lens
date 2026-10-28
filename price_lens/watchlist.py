"""Saved exact item identities and bounded, visibility-based highlight events."""
import json
import time

from PySide6.QtCore import QObject, Signal


class Watchlist(QObject):
    changed = Signal()
    LIMIT = 512

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.entries = {}
        try:
            raw = settings.value("watched-items", "[]")
            rows = json.loads(raw) if isinstance(raw, str) and len(raw) < 131072 else raw
            if isinstance(rows, list):
                for row in rows[:self.LIMIT]:
                    if not isinstance(row, dict):continue
                    identity = row.get("id")
                    if type(identity) is int and 0 < identity <= 2147483647:
                        name = row.get("name")
                        self.entries[identity] = name[:200] if isinstance(name, str) and name else f"Item {identity}"
        except (ValueError, TypeError):
            pass
        self.ids = frozenset(self.entries)

    def toggle(self, item):
        if item.game_id in self.entries:
            self.remove(item.game_id)
        elif len(self.entries) < self.LIMIT:
            name = item.name
            gender = {'male':'M','female':'F'}.get(item.gender)
            if gender and not name.upper().endswith(f"({gender})"):
                name += f" ({gender})"
            if item.tier and item.tier.casefold() not in name.casefold():
                name += " · " + item.tier
            self.entries[item.game_id] = name
            self._save()

    def remove(self, identity):
        if identity in self.entries:
            del self.entries[identity]
            self._save()

    def _save(self):
        self.ids = frozenset(self.entries)
        rows = [{"id": identity, "name": self.entries[identity]} for identity in sorted(self.entries)]
        self.settings.setValue("watched-items", json.dumps(rows, ensure_ascii=False))
        self.changed.emit()


class WatchEncounters:
    REARM_SECONDS = 1.5

    def __init__(self):
        self.seen = {}
        self.sequence = 0

    def apply(self, rows, watched, page=0, now=None):
        now = time.monotonic() if now is None else now
        active = set()
        for row in rows:
            identity = row.get("item_id")
            matched = row.get("kind") in ("shop", "item") and identity in watched
            row["watched"] = matched
            if not matched:continue
            key = (row.get("kind"), row.get("key"), page if row.get("kind") == "shop" else None)
            active.add(key)
            previous = self.seen.get(key)
            if previous is None or (previous[1] is not None and now - previous[1] >= self.REARM_SECONDS):
                self.sequence += 1
                event = self.sequence
            else:
                event = previous[0]
            self.seen[key] = (event, None, now, identity)
            row["watch_event"] = event
        for key, (event, absent_since, seen_at, identity) in list(self.seen.items()):
            if identity not in watched:
                del self.seen[key]
            elif key not in active:
                absent_since = now if absent_since is None else absent_since
                if now - absent_since >= 30:
                    del self.seen[key]
                else:
                    self.seen[key] = (event, absent_since, seen_at, identity)
        if len(self.seen) > 512:
            self.seen = dict(sorted(self.seen.items(), key=lambda pair: pair[1][2], reverse=True)[:512])

