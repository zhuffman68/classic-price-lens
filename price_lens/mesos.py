"""Confirmed arrivals in the visible pickup log, never a guessed wallet/profit."""
import math


class PickupTracker:
    MAX_GAP = 1.5

    def __init__(self):
        self.reset()

    def reset(self, now=None):
        self.seconds = 0.0
        self.last_tick = now
        self.last_seen = None
        self.gain = self.segment_gain = self.gaps = self.segment_gaps = 0
        self.segment_epoch = 0.0
        self.observed = self.paused = False
        self.lines = None
        self.candidate = None
        self.instances = []
        self.empty_at = None
        self.open_empty = False

    def tick(self, now, connected=True):
        if not math.isfinite(now):return
        if self.last_tick is not None and connected and not self.paused:
            delta = now-self.last_tick
            if 0 < delta <= 5:self.seconds += delta
        self.last_tick = now

    def interrupt(self):
        self.lines = self.candidate = None
        self.instances = [];self.empty_at=None;self.open_empty=False
        self.last_seen = None

    def pause(self, paused):
        self.paused = paused
        self.interrupt()

    @staticmethod
    def parse(payload):
        if not isinstance(payload,dict) or payload.get('valid') is not True:return None
        rows=payload.get('lines')
        if not isinstance(rows,list) or len(rows)>24:return None
        result=[]
        for row in rows:
            if not isinstance(row,dict):return None
            key=row.get('key');amount=row.get('mesos')
            if not isinstance(key,str) or not 1<=len(key)<=200:return None
            if amount is not None and (type(amount) is not int or not 1<=amount<=2_147_483_647):return None
            result.append((key,amount))
        return tuple(result)

    def ingest(self, payload, at):
        rows=self.parse(payload)
        if rows is None or not math.isfinite(at) or self.paused:return False
        if self.last_seen is not None and at<=self.last_seen:return False
        gap=self.last_seen is not None and at-self.last_seen>self.MAX_GAP
        if gap:
            self.gaps+=1;self.segment_gaps+=1;self.lines=None;self.candidate=None
        self.last_seen=at;self.observed=True
        if self.lines is None:
            # Start/Resume and lost coverage seed existing messages without
            # counting them as new income.
            self.lines=rows;self.instances=[(key,amount,at,True) for key,amount in rows]
            self.candidate=None;self.empty_at=None;self.open_empty=not rows;return True
        if not rows and self.lines:
            # A one-frame OCR miss is not proof the log disappeared.
            if self.empty_at is None:self.empty_at=at;return False
            if at-self.empty_at<.08:return False
            self.lines=();self.instances=[];self.open_empty=True;self.candidate=None;return True
        self.empty_at=None
        previous=self.lines;overlap=0
        for size in range(min(len(previous),len(rows)),0,-1):
            if previous[-size:]==rows[:size]:overlap=size;break
        known=self.instances[-overlap:] if overlap else []
        ambiguous=bool(previous and rows and not overlap and not self.open_empty)
        if ambiguous:self.gaps+=1;self.segment_gaps+=1
        current=known+[(key,amount,at,ambiguous) for key,amount in rows[overlap:]]
        confirmed=[];pending=False
        for key,amount,first,counted in current:
            if not counted and at-first>=.08:
                self.gain+=amount or 0;self.segment_gain+=amount or 0;counted=True
                self.open_empty=False
            pending|=not counted;confirmed.append((key,amount,first,counted))
        self.lines=rows;self.instances=confirmed;self.candidate=pending
        return not pending

    def fresh(self, now):
        return self.last_seen is not None and 0<=now-self.last_seen<=self.MAX_GAP

    def rate(self, now):
        return self.gain/self.seconds*60 if self.observed and self.seconds>=10 else None

    def checkpoint(self):
        result=dict(mesos=self.segment_gain if self.observed else None,
                    meso_seconds=max(0,self.seconds-self.segment_epoch),
                    meso_basis='pickups',pickup_gaps=self.segment_gaps)
        self.segment_gain=self.segment_gaps=0;self.segment_epoch=self.seconds
        return result
