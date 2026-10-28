"""Screen-derived EXP sessions. No network, game access, or reference EXP table."""
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid

MAX_GAP = 5.0


@dataclass(frozen=True)
class Reading:
    at: float
    level: int
    exp: int
    percent: int  # Hundredths of a percent, as printed by the game.
    character: str = ""
    job: str = ""

    @property
    def bounds(self):
        # The on-screen percentage is rounded to two decimals. Keep the full
        # allowed interval rather than pretending that exp / percent is exact.
        numerator = self.exp * 20_000
        low = max(self.exp + 1, (numerator + 2*self.percent) // (2*self.percent + 1))
        high = numerator // (2*self.percent - 1) if self.percent else 2**63-1
        return low, high

    @classmethod
    def parse(cls, payload, at):
        try:
            level, bar = payload.get("level"), payload.get("bar") or {}
            exp, percent = bar.get("exp"), bar.get("percentHundredths")
            if (not math.isfinite(at) or any(type(v) is not int for v in (level, exp, percent))
                    or not 1 <= level <= 200 or not 0 <= exp <= 10**12 or not 0 <= percent < 10_000):
                return None
            result = cls(at, level, exp, percent, str(payload.get("character") or "")[:80],
                         str(payload.get("job") or "")[:80])
            return result if result.bounds[0] <= result.bounds[1] else None
        except (TypeError, ValueError, AttributeError):
            return None


@dataclass
class Run:
    id: str
    started: float
    character: str
    job: str
    map_name: str
    notes: str
    start_level: int
    end_level: int
    seconds: float = 0
    progress: float = 0  # Net percentage points, carrying 100 points per level-up.
    lost: float = 0
    exp: float = 0
    approximate_exp: bool = False
    gaps: int = 0
    reason: str = "Saved"
    mesos: int | None = None
    meso_seconds: float = 0
    wallet_start: int | None = None
    wallet_end: int | None = None
    session_seconds: float | None = None


class ExperienceTracker:
    def __init__(self):
        self.current = None
        self.baseline = None
        self.run = None
        self.paused = False
        self.message = "Keep the EXP bar visible to begin."
        self.bounds = None
        self.candidate = None
        self.events = deque()
        self.completed = []
        self.map_name = ""
        self.map_candidate = None
        self.map_count = 0
        self.last_map_at = None

    def fresh(self, now):
        return self.current is not None and 0 <= now-self.current.at <= MAX_GAP

    def start(self, map_name="", notes="", started=None):
        if self.current is None or self.run:
            return False
        r = self.current
        detected = self.map_name if self.last_map_at is not None and r.at-self.last_map_at <= 15 else ""
        self.run = Run(uuid.uuid4().hex, time.time() if started is None else started,
                       r.character, r.job, (map_name or detected or "Unlabelled map")[:160],
                       notes[:240], r.level, r.level)
        self.baseline = r
        self.paused = False
        self.events.clear()
        self.message = "Recording · standing still counts toward your rate."
        return True

    def pause(self, paused=True):
        self.paused = paused
        self.baseline = None
        self.message = "Session paused." if paused else "Resuming from the next readable EXP bar."

    def interrupt(self):
        if self.run and self.baseline is not None:
            self.run.gaps += 1
        self.baseline = None
        self.candidate = None

    def finish(self, reason="Saved"):
        if self.run is None:
            return None
        self.run.reason = reason
        result = self.run
        self.run = None
        self.events.clear()
        self.paused = False
        self.baseline = None
        if result.seconds > 0:
            self.completed.append(result)
        self.message = reason + " · start another session to compare."
        return result

    def observe_map(self, payload, at):
        if not payload.get("mapRead"):
            return
        value = payload.get("map") or {}
        name = str(value.get("map") or "").strip()[:120]
        street = str(value.get("street") or "").strip()[:120]
        name = f"{street}: {name}" if name and street else name
        if not name:
            self.map_candidate, self.map_count = None, 0
            if self.last_map_at is not None and at-self.last_map_at > 15:
                self.map_name = ""
            return
        if name == self.map_candidate:
            self.map_count += 1
        else:
            self.map_candidate, self.map_count = name, 1
        if self.map_count >= 2:
            if self.run and self.map_name and name != self.map_name:
                self.finish("Map changed")
            self.map_name = name
            if self.run and self.run.map_name == "Unlabelled map":
                self.run.map_name = name
            self.last_map_at = at

    def ingest(self, payload, at):
        reading = Reading.parse(payload, at)
        if reading is None:
            self.message = "EXP bar unreadable · waiting for a clear reading."
            return False
        old = self.current
        if old and old.character and not reading.character:
            self.message = "Character name unreadable · waiting for a clear status bar."
            return False
        if old and reading.at <= old.at:
            return False
        switched = bool(old and old.character and reading.character and reading.character != old.character)
        changed_level = bool(old and reading.level != old.level)
        if old and not switched and not changed_level and self.bounds:
            low, high = reading.bounds
            if max(low, self.bounds[0]) > min(high, self.bounds[1]):
                self.message = "Checking an inconsistent EXP reading…"
                return False
        decrease = bool(old and reading.level == old.level and reading.exp < old.exp)
        jump = bool(old and reading.level == old.level and reading.percent-old.percent > 2000)
        if switched or changed_level or decrease or jump:
            candidate = self.candidate
            compatible = (candidate is not None and 0 < reading.at-candidate.at <= MAX_GAP
                          and candidate.level == reading.level and candidate.character == reading.character
                          and reading.exp >= candidate.exp
                          and max(candidate.bounds[0], reading.bounds[0]) <= min(candidate.bounds[1], reading.bounds[1]))
            if not compatible:
                self.candidate = reading
                self.message = "Confirming level or EXP change…"
                return False
        self.candidate = None
        if switched or (old and changed_level and reading.level != old.level+1):
            self.finish("Character changed" if switched else "Level changed while unreadable")
            self.bounds = None
            self.baseline = None
            self.map_name = ""
            self.map_candidate, self.map_count, self.last_map_at = None, 0, None
        if old is None or switched or changed_level:
            learned = reading.bounds
        else:
            low, high = reading.bounds
            learned = (max(low, self.bounds[0]), min(high, self.bounds[1])) if self.bounds else (low, high)
        previous_bounds = self.bounds
        self.bounds = learned
        self.current = reading
        if self.run:
            self.run.end_level = reading.level
        if self.run and not self.paused:
            baseline = self.baseline
            if baseline:
                elapsed = reading.at-baseline.at
                if elapsed > MAX_GAP:
                    self.run.gaps += 1
                elif elapsed > 0:
                    progress = (reading.level-baseline.level)*100 + (reading.percent-baseline.percent)/100
                    raw = reading.exp-baseline.exp
                    approximate = False
                    if reading.level == baseline.level+1 and previous_bounds:
                        low, high = previous_bounds
                        if high == 2**63-1:
                            # No usable total was learned at 0.00%; don't invent EXP.
                            self.run.gaps += 1
                            self.baseline = reading
                            return True
                        raw += (low+high)/2
                        approximate = low != high
                    self.run.seconds += elapsed
                    self.run.progress += progress
                    self.run.lost += max(0, -progress)
                    self.run.exp += raw
                    self.run.approximate_exp |= approximate
                    self.run.end_level = reading.level
                    self.events.append((self.run.seconds, elapsed, progress, raw))
                    while self.events and self.events[0][0] < self.run.seconds-3600:
                        self.events.popleft()
            self.baseline = reading
            self.message = "Recording · standing still counts toward your rate."
        elif self.run:
            self.message = "Session paused."
        else:
            self.message = "EXP bar found · ready to start a session."
        return True

    def window(self, seconds):
        if not self.run:
            return {"seconds":0.0, "progress":0.0, "exp":0.0, "rate":None, "exp_hour":None, "eta":None}
        start = max(0, self.run.seconds-seconds)
        progress = raw = duration = 0.0
        for end, elapsed, change, exp in self.events:
            overlap = max(0, end-max(start, end-elapsed))
            fraction = overlap/elapsed
            duration += overlap
            progress += change*fraction
            raw += exp*fraction
        rate = progress/duration if duration >= 30 else None
        eta = ((100-self.current.percent/100)/rate
               if rate is not None and rate > 0 and self.current else None)
        return {"seconds":duration,"progress":progress,"exp":raw,"rate":rate,
                "exp_hour":raw/duration*3600 if duration >= 30 else None,"eta":eta}


class SessionHistory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS exp_sessions (id TEXT PRIMARY KEY, started REAL, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, run):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO exp_sessions VALUES (?,?,?)",
                       (run.id, run.started, json.dumps(asdict(run), allow_nan=False)))
            db.execute("DELETE FROM exp_sessions WHERE id IN (SELECT id FROM exp_sessions ORDER BY started DESC LIMIT -1 OFFSET 500)")

    def rows(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM exp_sessions ORDER BY started DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def export(self, path):
        fields = list(Run.__dataclass_fields__)
        with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in self.rows():
                # Spreadsheet programs interpret user-entered notes as formulas.
                writer.writerow({key: ("'"+str(value) if isinstance(value,str) and value.startswith(("=","+","-","@")) else value)
                                 for key,value in row.items()})


def duration_text(seconds,*,seconds_in_hours=False):
    if seconds is None or not math.isfinite(seconds):
        return "—"
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:return f"{hours}h {minutes:02}m"+(f" {secs:02}s" if seconds_in_hours else '')
    return f"{minutes}m {secs:02}s"
