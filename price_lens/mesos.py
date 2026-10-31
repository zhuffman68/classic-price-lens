"""Track confirmed screen-log arrivals, independently of EXP and wallet changes."""
from collections import deque
from dataclasses import dataclass, replace
import math


@dataclass(frozen=True)
class PickupLine:
    key: str
    amount: int | None
    rect: tuple | None = None
    visual: str = ""
    kind: str = "anchor"

    @property
    def y(self):
        return self.rect[1] if self.rect else None

    def same(self, other):
        return ((self.key == other.key and self.amount == other.amount)
                or (self.amount is None and other.amount is None
                    and bool(self.visual) and self.visual == other.visual))

    @property
    def unknown(self):
        return self.kind == "unknown" or self.key.startswith("visual:")

    def matches(self, other):
        return self.same(other) or bool(
            self.visual and self.visual == other.visual
            and (self.unknown or other.unknown))


@dataclass
class Arrival:
    line: PickupLine
    first: float
    last: float
    counted: bool
    proven: bool


class PickupTracker:
    MAX_GAP = 1.5
    MAX_PENDING = 2.0
    MAX_TRACKS = 96

    def __init__(self):
        self.reset()

    def reset(self, now=None):
        self.seconds = 0.0
        self.last_tick = now
        self.gain = self.segment_gain = self.gaps = self.segment_gaps = 0
        self.segment_epoch = 0.0
        self.observed = self.paused = False
        self.recent = deque()
        self.recent_gain = 0
        self.last_pickup = None
        self.interrupt()

    def tick(self, now, connected=True):
        if not math.isfinite(now):
            return
        if self.last_tick is not None:
            delta = now - self.last_tick
            if delta <= 0:
                return
            if connected and not self.paused and delta <= 5:
                self.seconds += delta
        self.last_tick = now

    def interrupt(self):
        self.lines = None
        self.instances = []
        self.candidate = False
        self.last_seen = self.last_observation = None
        self.empty_at = None
        self.open_empty = False
        self.complete_lines = None
        self.complete_at = None

    def pause(self, paused):
        self.paused = paused
        self.interrupt()

    @staticmethod
    def parse(payload):
        if not isinstance(payload, dict) or payload.get("valid") is not True:
            return None
        rows = payload.get("lines")
        if not isinstance(rows, list) or len(rows) > 24:
            return None
        if payload.get("state", "readable") not in ("readable", "empty", "unreadable"):
            return None
        if type(payload.get("partial", False)) is not bool:
            return None
        result = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            key, amount = row.get("key"), row.get("mesos")
            kind = row.get("kind", "meso" if amount is not None else "anchor")
            if kind not in ("meso", "exp", "party_exp", "item", "unknown", "anchor"):
                return None
            if not isinstance(key, str) or not 1 <= len(key) <= 200:
                return None
            if amount is not None and (type(amount) is not int or not 1 <= amount <= 2_147_483_647):
                return None
            if kind == "unknown" and (amount is not None or not key.startswith("visual:")):
                return None
            rect = row.get("rect")
            if rect is not None:
                if not isinstance(rect, dict):
                    return None
                rect = tuple(rect.get(k) for k in ("x", "y", "width", "height"))
                if (any(type(v) is not int for v in rect) or rect[0] < 0 or rect[1] < 0
                        or not 1 <= rect[2] <= 720 or not 1 <= rect[3] <= 40
                        or rect[0] + rect[2] > 720 or rect[1] + rect[3] > 340):
                    return None
                if amount is not None and (row.get("kind") != "meso" or key != f"mesos:{amount}"):
                    return None
            visual = row.get("visualKey", "")
            if not isinstance(visual, str) or len(visual) > 128:
                return None
            result.append(PickupLine(key, amount, rect, visual, kind))
        if payload.get("state") == "empty" and result:
            return None
        return tuple(result)

    @staticmethod
    def match(previous, rows):
        """Match ordered lines with a common upward scroll, retaining duplicates."""
        if not previous or not rows:
            return {}, 0
        spatial = all(item.line.rect for item in previous) and all(row.rect for row in rows)
        if not spatial:
            for size in range(min(len(previous), len(rows)), 0, -1):
                if all(a.line.same(b) for a, b in zip(previous[-size:], rows[:size])):
                    return {i: len(previous)-size+i for i in range(size)}, 0
            return {}, 0
        offsets = {0}
        for old in previous:
            for row in rows:
                if old.line.matches(row) and -340 <= row.y-old.line.y <= 2:
                    offsets.add(row.y-old.line.y)
        gaps = [b.y-a.y for a, b in zip(rows, rows[1:]) if 6 <= b.y-a.y <= 40]
        pitch = sorted(gaps)[len(gaps)//2] if gaps else 14
        expected = -max(0, len(rows)-len(previous))*pitch
        best, best_offset, best_score = {}, 0, (-1, 0, 0)
        for offset in offsets:
            mapping, last = {}, -1
            for i, row in enumerate(rows):
                choices = [j for j in range(last+1, len(previous))
                           if previous[j].line.matches(row)
                           and abs(row.y-previous[j].line.y-offset) <= 2]
                if choices:
                    last = min(choices, key=lambda j: abs(row.y-previous[j].line.y-offset))
                    mapping[i] = last
            score = (len(mapping), -abs(offset-expected), -abs(offset))
            if score > best_score:
                best, best_offset, best_score = mapping, offset, score
        return best, best_offset

    def replacement_proven(self, rows, at):
        # Complete, recent views of a fixed bottom-aligned log can establish
        # a new bottom message even when an entire burst replaced the old log.
        previous = self.complete_lines
        return bool(previous and rows and self.complete_at is not None
                    and at-self.complete_at <= self.MAX_GAP
                    and all(line.rect for line in previous+rows)
                    and abs(previous[-1].y-rows[-1].y) <= 3
                    and not rows[-1].unknown
                    and not previous[-1].same(rows[-1]))

    def ingest(self, payload, at):
        if (isinstance(payload, dict) and payload.get("covered") is True
                and math.isfinite(at) and not self.paused
                and (self.last_observation is None or at > self.last_observation)):
            if self.lines is not None:
                self.gaps += 1
                self.segment_gaps += 1
            self.interrupt()
            self.last_observation = at
            return False
        rows = self.parse(payload)
        if rows is None or not math.isfinite(at) or self.paused:
            return False
        if self.last_observation is not None and at <= self.last_observation:
            return False
        self.last_observation = at
        partial = payload.get("partial", False) or payload.get("state") == "unreadable"
        if partial and not rows:
            # Failed OCR and faded glyphs do not prove that the log is empty.
            return False
        if self.last_seen is not None and at-self.last_seen > self.MAX_GAP:
            self.gaps += 1
            self.segment_gaps += 1
            self.lines = None
            self.instances = []
        self.last_seen = at
        self.observed = True
        if self.lines is None:
            self.lines = rows
            self.instances = [Arrival(row, at, at, True, False) for row in rows]
            self.candidate = False
            self.empty_at = None
            self.open_empty = not rows and not partial
            if not partial:
                self.complete_lines, self.complete_at = rows, at
            return True
        if not rows and self.lines:
            if self.empty_at is None:
                self.empty_at = at
                return False
            if at-self.empty_at < .08:
                return False
            self.lines, self.instances = (), []
            self.open_empty = True
            self.candidate = False
            self.complete_lines, self.complete_at = (), at
            return True
        self.empty_at = None
        previous = [item for item in self.instances
                    if item.counted or at-item.first <= self.MAX_PENDING]
        mapping, offset = self.match(previous, rows)
        replacement = not mapping and self.replacement_proven(rows, at)
        ambiguous = bool(self.lines and rows and not mapping and not self.open_empty and not replacement)
        if ambiguous:
            self.gaps += 1
            self.segment_gaps += 1
        tail = max(mapping, default=-1)
        current, batch = [], 0
        for index, row in enumerate(rows):
            semantic_amount = row.amount
            if index in mapping:
                item = previous[mapping[index]]
                item.line = (replace(item.line, rect=row.rect, visual=row.visual)
                             if row.unknown else row)
                item.last = at
                if not item.proven and not item.counted and replacement:
                    item.proven = True
            else:
                proven = self.open_empty or replacement or bool(mapping and index > tail)
                # Rows without geometry cannot safely reinterpret a wholesale
                # replacement. Partial spatial rows can wait for a clear view.
                seeded = not proven and (not row.rect or not partial)
                item = Arrival(row, at, at, seeded, proven)
            if (not item.counted and item.proven and at-item.first >= .08
                    and (item.line.amount is None or semantic_amount is not None)):
                item.counted = True
                batch += item.line.amount or 0
                if item.line.amount:
                    self.last_pickup = item.line.amount
                self.open_empty = False
            current.append(item)
        if partial:
            used = set(mapping.values())
            for index, item in enumerate(previous):
                if index not in used and at-item.last <= self.MAX_PENDING:
                    if item.line.rect and offset:
                        x, y, w, h = item.line.rect
                        item.line = replace(item.line, rect=(x, y+offset, w, h))
                    current.append(item)
            if all(item.line.rect for item in current):
                current.sort(key=lambda item: (item.line.y, item.first))
        self.instances = current[-self.MAX_TRACKS:]
        self.lines = rows
        self.candidate = any(not item.counted and item.proven for item in self.instances)
        if not partial:
            self.complete_lines, self.complete_at = rows, at
        if batch:
            self.gain += batch
            self.segment_gain += batch
            second = int(self.seconds)
            if self.recent and self.recent[-1][0] == second:
                self.recent[-1] = (second, self.recent[-1][1]+batch)
            else:
                self.recent.append((second, batch))
            self.recent_gain += batch
        self.trim_recent()
        return not self.candidate

    def fresh(self, now):
        return self.last_seen is not None and 0 <= now-self.last_seen <= self.MAX_GAP

    def rate(self, now):
        self.trim_recent()
        duration = min(self.seconds, 300)
        return self.recent_gain/duration*60 if self.observed and duration >= 10 else None

    def trim_recent(self):
        cutoff = int(self.seconds)-300
        while self.recent and self.recent[0][0] <= cutoff:
            self.recent_gain -= self.recent.popleft()[1]

    def checkpoint(self):
        result = dict(mesos=self.segment_gain if self.observed else None,
                      meso_seconds=max(0, self.seconds-self.segment_epoch),
                      meso_basis="pickups", pickup_gaps=self.segment_gaps)
        self.segment_gain = self.segment_gaps = 0
        self.segment_epoch = self.seconds
        return result
