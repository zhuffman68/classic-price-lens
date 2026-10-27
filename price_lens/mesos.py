"""Confirmed, screen-derived wallet changes. No guessed hidden balance or profit."""
import math


class MesoTracker:
    def __init__(self):
        self.reset()

    def reset(self, now=None):
        self.seconds = 0.0
        self.last_tick = now
        self.current = None
        self.last_seen = None
        self.visible = False
        self.candidate = None
        self.anchor = None
        self.baseline_seconds = None
        self.gain = 0
        self.observed = False
        self.segment_gain = 0
        self.segment_start = None
        self.segment_seconds = 0.0
        self.segment_epoch = 0.0
        self.paused = False

    def tick(self, now, connected=True):
        if not math.isfinite(now):return
        if self.last_tick is not None and connected and not self.paused:
            delta = now-self.last_tick
            if 0 < delta <= 5:self.seconds += delta
        self.last_tick = now

    def interrupt(self):
        # Pauses, capture changes and character changes cannot include invisible
        # transfers. Hiding only the inventory deliberately keeps the anchor.
        self.anchor = None
        self.candidate = None
        self.visible = False

    def pause(self, paused):
        self.paused = paused
        self.interrupt()

    def ingest(self, payload, at):
        value = payload.get('mesos') if isinstance(payload, dict) else None
        if type(value) is not int or not 0 <= value <= 2_147_483_647 or not math.isfinite(at):
            self.visible = False
            self.candidate = None
            return False
        if self.last_seen is not None and at <= self.last_seen:return False
        if self.paused:
            self.visible = False
            return False
        # Every new balance needs two consecutive, independently timed captures.
        # A cached OCR result is fine: the actual field pixels were revalidated.
        if self.current != value or self.anchor is None:
            if not self.candidate or self.candidate[0] != value or not 0.15 <= at-self.candidate[1] <= 3:
                self.candidate = (value, at)
                self.visible = False
                return False
        self.candidate = None
        if self.anchor is not None:
            change = value-self.anchor
            self.gain += change
            self.segment_gain += change
        else:
            if self.segment_start is None:
                self.segment_start = value
                self.segment_epoch = self.seconds
        if self.baseline_seconds is None:self.baseline_seconds = self.seconds
        self.anchor = self.current = value
        self.last_seen = at
        self.visible = self.observed = True
        self.segment_seconds = self.seconds-self.segment_epoch
        return True

    def fresh(self, now):
        return self.visible and self.last_seen is not None and 0 <= now-self.last_seen <= 3

    def rate(self, now):
        duration = self.seconds-(self.baseline_seconds or 0)
        return self.gain/duration*60 if duration >= 10 and self.fresh(now) else None

    def checkpoint(self):
        result = dict(mesos=self.segment_gain if self.segment_start is not None else None,
                      meso_seconds=self.segment_seconds, wallet_start=self.segment_start,
                      wallet_end=self.current if self.segment_start is not None else None)
        self.segment_gain = 0
        self.segment_start = None
        self.segment_seconds = 0
        self.interrupt()
        return result
