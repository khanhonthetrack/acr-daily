"""Incidents during a run, for the website's live commentary: a big hit, a stop on the stage, a trip off the road,
reversing, a big jump. Reset detection stays in judge.py; this only describes what happened.

Each incident is reported once it is over, with the numbers the commentary needs:
    {'type': 'hit',     'fromKmh': 63, 'toKmh': 27, 'progress': 0.49}
    {'type': 'stuck',   'seconds': 12.4, 'progress': 0.88}
    {'type': 'off',     'seconds': 4.1, 'progress': 0.30}
    {'type': 'reverse', 'metres': 24, 'progress': 0.61}
    {'type': 'jump',    'airtimeMs': 1250, 'kmh': 118, 'progress': 0.72}
Limits come from real runs (MaybeIWill on St. Geniez - Sisteron, 2026-10-06): hard braking peaks around 1.5 g, the
hits that run had were 3.1 to 3.7 g; standing still is exactly still (0.0 m between samples); walking-pace
manoeuvres pass through neutral, so nothing here relies on the gear alone.
"""
import math
from collections import deque

HIT_G = 2.5                 # slowing down harder than this (over 0.2-0.4 s) from...
HIT_FROM_KMH = 40.0         # ...at least this speed = a hit
HIT_HOLD_S = 2.0            # a hit is held this long: if a reset follows, the reset tells the story instead
STUCK_KMH, STUCK_S = 3.0, 4.0
OFF_M, OFF_BACK_M, OFF_S = 20.0, 10.0, 2.0
REVERSE = 0                 # gear numbers: 0 reverse, 1 neutral, 2 first...
REVERSE_M = 10.0
JUMP_MS = 1000
JUMP_HOLD_S = 6.0           # a long airtime followed by a reset was the car tumbling in a crash, not a jump
MIN_GAP_S = 20.0            # at most one incident every this many seconds (a messy run must not flood the ticker)
EDGE = (0.02, 0.97)         # nothing at the very start or after the finish line


class IncidentWatch:
    def __init__(self):
        self.speeds = deque()            # (t, km/h) of the last half second
        self.hit = None                  # held hit: [since, from_kmh, lowest_kmh, progress]
        self.hit_until = -1e9            # no new hit before this (one impact = one hit)
        self.stop_since = None
        self.off_since = None
        self.rev_m = 0.0
        self.rev_at = None
        self.last_xz = None
        self.last_out = -1e9
        self.out = []
        self.jumps = []                  # held big jumps: (since, incident)

    def jump(self, airtime_ms, kmh, progress, now):
        """Called by the judge for every jump it measures."""
        if airtime_ms >= JUMP_MS:
            self.jumps.append((now, {'type': 'jump', 'airtimeMs': int(airtime_ms), 'kmh': round(kmh), 'progress': progress}))

    def feed(self, f, now, progress, off_m, resetting):
        """One frame of a running stage. resetting: the judge is counting a reset right now.
        -> the incidents that just ended (usually none), with any jump() reported since the last frame."""
        inside = EDGE[0] < progress < EDGE[1]
        # ---- a big jump, once no reset followed it
        if resetting:
            self.jumps = []
        while self.jumps and now - self.jumps[0][0] >= JUMP_HOLD_S:
            self._emit(now, self.jumps.pop(0)[1])
        # ---- a big hit
        self.speeds.append((f.t, f.speed))
        while self.speeds and f.t - self.speeds[0][0] > 0.5:
            self.speeds.popleft()
        if self.hit:
            self.hit[2] = min(self.hit[2], f.speed)
            if resetting:
                self.hit = None                          # the reset is the story
            elif now - self.hit[0] >= HIT_HOLD_S:
                _, v0, low, p = self.hit
                self.hit = None
                self._emit(now, {'type': 'hit', 'fromKmh': round(v0), 'toKmh': round(low), 'progress': p})
        elif inside and now >= self.hit_until and not resetting:
            before = [(t, v) for t, v in self.speeds if 0.2 <= f.t - t <= 0.4]
            if before:
                t0, v0 = max(before, key=lambda p: p[1])
                g = (v0 - f.speed) / 3.6 / max(f.t - t0, 1e-3) / 9.81
                if v0 >= HIT_FROM_KMH and g >= HIT_G:
                    self.hit = [now, v0, f.speed, progress]
                    self.hit_until = now + 5.0
        # ---- stopped on the stage
        if f.speed < STUCK_KMH and inside and not resetting:
            if self.stop_since is None:
                self.stop_since = (now, progress)
        elif self.stop_since is not None:
            since, p = self.stop_since
            self.stop_since = None
            if (now - since >= STUCK_S) and (f.speed >= 5.0 or resetting):
                self._emit(now, {'type': 'stuck', 'seconds': round(now - since, 1), 'progress': p})
            elif f.speed < 5.0 and not resetting:
                self.stop_since = (since, p)            # still crawling: the same stop
        # ---- off the road
        if off_m > OFF_M and inside and not resetting:
            if self.off_since is None:
                self.off_since = (now, progress)
        elif self.off_since is not None and (off_m < OFF_BACK_M or resetting):
            since, p = self.off_since
            self.off_since = None
            if now - since >= OFF_S:
                self._emit(now, {'type': 'off', 'seconds': round(now - since, 1), 'progress': p})
        # ---- reversing
        xz = (f.x, f.z)
        if f.gear == REVERSE and f.speed > 2.0 and self.last_xz is not None and not resetting:
            self.rev_m += math.dist(self.last_xz, xz)
            if self.rev_at is None:
                self.rev_at = progress
        elif f.gear != REVERSE and self.rev_at is not None:
            if self.rev_m >= REVERSE_M:
                self._emit(now, {'type': 'reverse', 'metres': round(self.rev_m), 'progress': self.rev_at})
            self.rev_m, self.rev_at = 0.0, None
        self.last_xz = xz
        out, self.out = self.out, []
        return out

    def _emit(self, now, inc):
        if now - self.last_out >= MIN_GAP_S:
            self.last_out = now
            inc['progress'] = round(inc['progress'], 3)
            self.out.append(inc)
