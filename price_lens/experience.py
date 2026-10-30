"""Screen-derived EXP sessions. No network, game access, or reference EXP table."""
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
import csv
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid

MAX_GAP = 5.0


def clock_text(seconds):
    seconds=max(0,int(seconds));hours,remainder=divmod(seconds,3600);minutes,seconds=divmod(remainder,60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


@dataclass(frozen=True)
class Reading:
    at: float
    level: int
    exp: int
    percent: int  # Hundredths of a percent, as printed by the game.
    character: str = ""
    job: str = ""
    identity_key: str = ""

    def same_character(self,other):
        if self.identity_key and other.identity_key:
            return self.identity_key==other.identity_key
        return self.character==other.character

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
                         str(payload.get("job") or "")[:80],str(payload.get('identityKey') or '')[:64])
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
    meso_basis: str = "wallet"  # Legacy saved runs retain their original meaning.
    pickup_gaps: int = 0
    identity_key: str = ""


class ExperienceTracker:
    def __init__(self):
        self.current = None
        self.baseline = None
        self.run = None
        self.paused = False
        self.message = "Keep the EXP bar visible to begin."
        self.bounds = None
        self.candidate = None
        self.recovery = deque(maxlen=4)
        self.read_issue = ''
        self.events = deque()
        self.pace_seconds = 0.0
        self.completed = []
        self.map_name = ""
        self.map_candidate = None
        self.map_count = 0
        self.last_map_at = None

    def fresh(self, now):
        return self.current is not None and 0 <= now-self.current.at <= MAX_GAP

    def reset_pace(self):
        self.events.clear();self.pace_seconds=0.0

    def start(self, map_name="", notes="", started=None):
        if self.current is None or self.run:
            return False
        r = self.current
        detected = self.map_name if self.last_map_at is not None and r.at-self.last_map_at <= 15 else ""
        self.run = Run(uuid.uuid4().hex, time.time() if started is None else started,
                       r.character, r.job, (map_name or detected or "Unlabelled map")[:160],
                       notes[:240], r.level, r.level,identity_key=r.identity_key)
        self.baseline = r
        self.paused = False
        self.recovery.clear()
        self.message = "Recording · standing still counts toward your rate."
        return True

    def refine_character(self,identity_key,name):
        """Correct display spelling without changing session identity or pace."""
        if not identity_key or not name or not self.current or self.current.identity_key!=identity_key:return False
        if self.current.character==name:return False
        for field in ('current','baseline','candidate'):
            reading=getattr(self,field)
            if reading and reading.identity_key==identity_key:setattr(self,field,replace(reading,character=name))
        self.recovery=deque((replace(reading,character=name) if reading.identity_key==identity_key else reading
                             for reading in self.recovery),maxlen=self.recovery.maxlen)
        for run in self.completed+([self.run] if self.run else []):
            if run.identity_key==identity_key:run.character=name
        return True

    def pause(self, paused=True):
        self.paused = paused
        self.baseline = None
        self.recovery.clear()
        self.message = "Session paused." if paused else "Resuming from the next readable EXP bar."

    def interrupt(self):
        if self.run and self.baseline is not None:
            self.run.gaps += 1
        self.baseline = None
        self.candidate = None
        self.recovery.clear()

    def finish(self, reason="Saved", *, keep_pace=False):
        if self.run is None:
            return None
        self.run.reason = reason
        result = self.run
        self.run = None
        if not keep_pace:
            self.reset_pace()
        self.paused = False
        self.baseline = None
        self.recovery.clear()
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
                self.finish("Map changed",keep_pace=True)
            self.map_name = name
            if self.run and self.run.map_name == "Unlabelled map":
                self.run.map_name = name
            self.last_map_at = at

    def recover_bounds(self, reading):
        """Relearn a numerical baseline only from changing, consistent values.

        Repeated captures of one OCR result cannot outvote an established total.
        Recovery never bridges the untrusted interval or resets the user's run.
        """
        previous = self.recovery[-1] if self.recovery else None
        if previous and reading.at <= previous.at:
            return None
        low, high = reading.bounds
        compatible = bool(previous and 0 < reading.at-previous.at <= MAX_GAP
                          and reading.same_character(previous) and reading.job==previous.job
                          and reading.level==previous.level
                          and reading.exp >= previous.exp and reading.percent >= previous.percent)
        if compatible:
            low = max(low,*(r.bounds[0] for r in self.recovery))
            high = min(high,*(r.bounds[1] for r in self.recovery))
        if not compatible or low > high:
            self.recovery.clear()
        self.recovery.append(reading)
        if (not self.current or len(self.recovery) < 3 or reading.at-self.recovery[0].at < 2
                or len({r.exp for r in self.recovery}) < 3
                or len({r.percent for r in self.recovery}) < 2):
            return None
        return (max(r.bounds[0] for r in self.recovery),
                min(r.bounds[1] for r in self.recovery))

    def ingest(self, payload, at):
        reading = Reading.parse(payload, at)
        if reading is None:
            self.message = "EXP bar unreadable · waiting for a clear reading."
            self.read_issue = 'unreadable'
            self.recovery.clear()
            return False
        old = self.current
        if old and old.character and not reading.character:
            self.message = "Character name unreadable · waiting for a clear status bar."
            self.read_issue = 'identity'
            self.recovery.clear()
            return False
        if old and reading.at <= old.at:
            return False
        switched = bool(old and old.character and reading.character and not reading.same_character(old))
        changed_level = bool(old and reading.level != old.level)
        recovered = False
        if old and not switched and not changed_level and self.bounds:
            replacement = self.recover_bounds(reading)
            low, high = reading.bounds
            if max(low, self.bounds[0]) > min(high, self.bounds[1]):
                self.message = "Checking an inconsistent EXP reading…"
                self.read_issue = 'inconsistent'
                if replacement is None:
                    return False
                self.interrupt()
                self.bounds = replacement
                recovered = True
        else:
            self.recovery.clear()
        decrease = bool(old and reading.level == old.level and reading.exp < old.exp)
        jump = bool(old and reading.level == old.level and reading.percent-old.percent > 2000)
        if (switched or changed_level or decrease or jump) and not recovered:
            candidate = self.candidate
            compatible = (candidate is not None and 0 < reading.at-candidate.at <= MAX_GAP
                          and candidate.level == reading.level and candidate.same_character(reading)
                          and reading.exp >= candidate.exp
                          and max(candidate.bounds[0], reading.bounds[0]) <= min(candidate.bounds[1], reading.bounds[1]))
            if not compatible:
                self.candidate = reading
                self.message = "Confirming level or EXP change…"
                self.read_issue = 'confirming'
                return False
        self.candidate = None
        self.read_issue = ''
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
                    self.pace_seconds += elapsed
                    self.events.append((self.pace_seconds, elapsed, progress, raw))
                    while self.events and self.events[0][0] < self.pace_seconds-3600:
                        self.events.popleft()
            self.baseline = reading
            self.message = "Recording · standing still counts toward your rate."
        elif self.run:
            self.message = "Session paused."
        else:
            self.message = "EXP bar found · ready to start a session."
        return True

    def window(self, seconds):
        if not self.current or not self.events:
            return {"seconds":0.0, "progress":0.0, "exp":0.0, "rate":None, "exp_hour":None, "eta":None}
        start = max(0, self.pace_seconds-seconds)
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

    def refine_character(self,identity_key,name):
        """Relabel only records carrying this exact captured visual identity."""
        if not identity_key or not name:return
        with self.connect() as db:
            rows=db.execute('SELECT id,payload FROM exp_sessions').fetchall()
            for record_id,payload in rows:
                value=json.loads(payload)
                if value.get('identity_key')!=identity_key or value.get('character')==name:continue
                value['character']=name
                db.execute('UPDATE exp_sessions SET payload=? WHERE id=?',
                           (json.dumps(value,allow_nan=False),record_id))

    def export(self, path):
        fields = [field for field in Run.__dataclass_fields__ if field!='identity_key']
        with Path(path).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in self.rows():
                # Spreadsheet programs interpret user-entered notes as formulas.
                writer.writerow({key: ("'"+str(value) if isinstance(value,str) and value.startswith(("=","+","-","@")) else value)
                                 for key,value in row.items() if key in fields})


def duration_text(seconds,*,seconds_in_hours=False):
    if seconds is None or not math.isfinite(seconds):
        return "—"
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:return f"{hours}h {minutes:02}m"+(f" {secs:02}s" if seconds_in_hours else '')
    return f"{minutes}m {secs:02}s"
