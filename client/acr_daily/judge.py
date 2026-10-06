"""Judges one challenge run from telemetry frames.

Rules
  - the run counts only on the challenge stage + car, and only if the app saw the clock start
    (the car must be at the stage start when it does)
  - reset to the road = +60 s each (penalty set by the server). Seen as either the car jumping further than
    it can drive, or the car going from driving speed in gear to standing still in neutral at once (the game
    puts a reset car down stopped in neutral, sometimes only a few metres from where it left the road)
  - restart (clock goes back), leaving the stage, changing car, or the game frozen/paused for more
    than 30 s = DNF
  - finish = the clock stops near the end of the route, after passing >= 90 % of the route checkpoints
    (fewer = INVALID, a shortcut or a different route)
The game never reports its own penalties, so our time = stage clock + our reset penalties.
"""
import math
import time

from .incidents import IncidentWatch
from .names import same_car, same_track
from .route import Route

START_NEAR_M = 60.0       # car this close to the route start when the clock starts
FINISH_NEAR_M = 80.0      # clock stopping this close to the route end = finish
RUNOUT_M = 400.0          # ...or this close, past 85 % of it: routes taken from the game's files run on past the
                          # finish line to the stop control (the first clean run then replaces them)
FINISH_FREEZE_S = 0.6     # clock unchanged this long (game still running) = stopped
STOP_DNF_S = 30.0         # clock stopped away from the finish / no telemetry this long = DNF
CHECKPOINT_RADIUS_M = 40.0
MIN_CHECKPOINTS = 0.90
RESET_CONFIRM_S = 1.5     # a jump only counts as a reset if the run is still going this long after
TRACE_EVERY_MS = 250
MIN_JUMP_MS, MAX_JUMP_MS = 150, 3000   # shorter = a bump; longer = not a jump (a crash or a glitch)
RESET_AIR_IGNORE_MS = 6000             # airtime this close before a reset is the crash, not a jump
NEUTRAL = 1                            # gear numbers: 0 reverse, 1 neutral, 2 first...
RESET_FROM_KMH = 30.0                  # driving in gear at least this fast...
RESET_STOP_KMH = 1.0                   # ...then standing still in neutral...
RESET_STOP_WINDOW_S = 0.6              # ...this soon after = put back on the road by a reset
RESET_COOLDOWN_S = 3.0                 # one reset can't be counted twice (jump + stop seen in the same moment)
# One trace sample (the server re-checks the run from these):
#   [clockMs, x, z, kmh, resets, wallMs, physicsPackets, throttle, brake, steer, gear, rpm, airTempK]
# wallMs = PC time since the clock started, physicsPackets = game physics steps since then (~333/s)


def teleported(dist_m, dt_s, speed_kmh):
    """A jump no car could drive: 15 m, 3 m when nearly stopped, 1 m when standing still (stuck, then put back on
    the road close by: a car standing still does not move at all, 0.0 m between readings), plus 1.5x what the
    current speed covers in dt."""
    base = 1.0 if speed_kmh < 2 else 3.0 if speed_kmh < 10 else 15.0
    return dist_m > base + (speed_kmh / 3.6) * max(dt_s, 0.0) * 1.5


def fmt_ms(ms, dec=3):
    if ms is None or ms < 0:
        return '--:--.---'
    neg = ms < 0
    ms = abs(int(ms))
    m, s = divmod(ms, 60000)
    txt = '%d:%06.3f' % (m, s / 1000.0)
    if dec < 3:
        txt = txt[:dec - 3]
    return ('-' if neg else '') + txt


class Ghost:
    """A reference run (e.g. today's #1) for the live gap: total time at each route index."""

    def __init__(self, trace, route, penalty_ms):
        self.at = [None] * len(route.points)
        idx = None
        for s in trace:
            clock, x, z = s[0], s[1], s[2]
            resets = s[4] if len(s) > 4 else 0
            idx, _ = route.nearest(x, z, idx)
            total = clock + resets * penalty_ms
            if self.at[idx] is None:
                self.at[idx] = total
        last = None   # fill gaps so every index has a time
        for i, v in enumerate(self.at):
            if v is None:
                self.at[i] = last
            else:
                last = v

    def total_at(self, idx):
        return self.at[idx] if 0 <= idx < len(self.at) else None


class Judge:
    def __init__(self, challenge, clock=time.monotonic):
        """challenge: {'id', 'track', 'car', 'route': [[x, z]...], 'penaltyMs'}"""
        self.ch = challenge
        self.route = Route(challenge['route'])
        self.penalty_ms = int(challenge.get('penaltyMs', 60000))
        self.split_at = list(challenge.get('splits') or [0.25, 0.5, 0.75])   # fractions of the route
        self.now = clock
        self.state = 'waiting'      # waiting | armed | running | finished | dnf | invalid
        self.message = 'Waiting for Assetto Corsa Rally'
        self.result = None          # dict of the last finished/dnf/invalid run
        self.ghost = None
        self._track_alias = None    # the game's name for the stage, when it was recognised by its start line
        self.gap_ms = None          # live gap to the ghost (+ = slower)
        self._reset_run()
        self._last = None           # last frame
        self._last_seen = 0.0

    # ------------------------------------------------------------------ public

    @property
    def clock_ms(self):
        return self._clock if self.state == 'running' else (self.result or {}).get('clockMs', 0)

    @property
    def total_ms(self):
        """Stage clock + penalties so far (what the timer window shows)."""
        if self.state == 'running':
            return self._clock + self.resets * self.penalty_ms
        if self.result:
            return self.result.get('totalMs') or self.result.get('clockMs', 0) + self.result.get('resets', 0) * self.penalty_ms
        return 0

    @property
    def progress(self):
        return self.route.cum[self._max_idx] / self.route.length if self.route.length else 0.0

    def set_ghost(self, trace):
        self.ghost = Ghost(trace, self.route, self.penalty_ms) if trace else None

    def feed(self, f):
        """Feed one frame (or None when the game is not there). Returns a list of event strings."""
        ev = []
        now = self.now()
        if f is None:
            if self.state == 'running' and now - self._last_seen > STOP_DNF_S:
                self._end('dnf', 'lost the game (closed or frozen)', ev)
            elif self.state != 'running':
                self.message = 'Waiting for Assetto Corsa Rally'
                if self.state == 'armed':
                    self.state = 'waiting'
            return ev
        self._last_seen = now
        right = self._right(f)
        if self.state in ('finished', 'dnf', 'invalid'):
            if f.clock_ms == 0:
                self.state = 'waiting'   # back on a start line: ready for a new attempt
            else:
                self._last = f
                return ev
        if self.state in ('waiting', 'armed'):
            self._idle(f, right, ev)
        elif self.state == 'running':
            self._running(f, right, now, ev)
        self._last = f
        return ev

    # ------------------------------------------------------------------ states

    def _right(self, f):
        """Today's stage + car. The stage is known by name, or - for stages whose telemetry name is only a guess
        (routes taken from the game's files) - by the car standing on the route's start line before the clock
        starts; the name the game reports then counts as this stage until the run ends."""
        if not same_car(f.car, self.ch):
            return False
        if same_track(f.track, self.ch) or (self._track_alias and f.track == self._track_alias):
            return True
        if f.track and f.clock_ms <= 0 and self.state != 'running' and \
                math.dist((f.x, f.z), self.route.start) <= START_NEAR_M:
            self._track_alias = f.track
            return True
        return False

    def _idle(self, f, right, ev):
        prev = self._last
        stage = self.ch.get('menuName') or self.ch['track']   # as the game's menu names it
        if not f.track:
            self.state, self.message = 'waiting', 'Load the stage: %s · %s' % (stage, self.ch['car'])
            return
        if not right:
            self.state = 'waiting'
            self.message = 'Not today\'s challenge (%s · %s). Load %s · %s' % (f.track, f.car or '?', stage, self.ch['car'])
            return
        if f.clock_ms <= 0:
            self.state, self.message = 'armed', 'Ready. The run starts when the stage clock starts.'
            return
        if self.state == 'armed' and prev is not None and prev.clock_ms <= 0:
            d = math.dist((f.x, f.z), self.route.start)
            self._reset_run()
            self.state = 'running'
            self._clock = f.clock_ms
            self._freeze_since = None
            self._start_wall = time.time()
            if d > START_NEAR_M:
                self._end('invalid', 'the clock started %.0f m away from the stage start' % d, ev)
                return
            self._trace_add(f, force=True)
            self.message = 'On stage'
            ev.append('start')
            return
        self.state = 'waiting'
        self.message = 'A run is already going: restart the stage to take part'

    def _running(self, f, right, now, ev):
        prev = self._last
        if not right:
            self._end('dnf', 'left the stage' if not f.track else 'changed stage or car', ev)
            return
        if f.clock_ms < self._clock - 500 or (f.clock_ms <= 0 and self._clock > 0):
            self._end('dnf', 'restarted', ev)
            return
        # resets: the car jumps; it counts once the run is still alive RESET_CONFIRM_S later
        cooled = now - self._last_reset >= RESET_COOLDOWN_S
        if prev is not None and self._pending is None and cooled:
            d = math.dist((prev.x, prev.z), (f.x, f.z))
            if teleported(d, f.t - prev.t, max(prev.speed, f.speed)):
                self._pending = (now, d)
                self._trace_add(prev, force=True)
        # ...or put down stopped in neutral right after driving in gear (a reset that barely moves the car)
        if f.speed >= RESET_FROM_KMH and f.gear > NEUTRAL:
            self._fast_at = f.t
        elif (prev is not None and self._pending is None and cooled and self._fast_at is not None
              and f.speed < RESET_STOP_KMH and f.gear == NEUTRAL and f.t - self._fast_at <= RESET_STOP_WINDOW_S):
            self._pending = (now, math.dist((prev.x, prev.z), (f.x, f.z)))
            self._trace_add(prev, force=True)
        if self._pending and now - self._pending[0] >= RESET_CONFIRM_S:
            self.resets += 1
            self._pending = None
            self._last_reset = now
            self._fast_at = None
            ev.append('reset')
            self._trace_add(f, force=True)
            # a crash before a reset tumbles the car: that is not a jump
            self.jumps = [j for j in self.jumps if j[0] < f.clock_ms - RESET_AIR_IGNORE_MS]
            self._air = None
        # jumps: all four wheels unloaded at speed, timed at the app's 20 Hz
        if f.airborne and f.speed > 20 and self._pending is None:
            if self._air is None:
                self._air = (f.clock_ms, self.route.cum[self._max_idx], f.speed)
        elif self._air is not None:
            start, at_m, kmh = self._air
            dur = f.clock_ms - start
            if MIN_JUMP_MS <= dur <= MAX_JUMP_MS:
                self.jumps.append([start, dur, round(at_m), round(kmh, 1)])
                self.incidents.jump(dur, kmh, self.progress, now)
            self._air = None
        # progress along the route
        idx, off = self.route.nearest(f.x, f.z, self._idx)
        self._idx = idx
        if off < 120:
            self._max_idx = max(self._max_idx, idx)
        for k, ci in enumerate(self.route.checkpoints):
            if k not in self._hit:
                cx, cz = self.route.points[ci]
                if (cx - f.x) ** 2 + (cz - f.z) ** 2 <= CHECKPOINT_RADIUS_M ** 2:
                    self._hit.add(k)
        # splits (same rule as the server: first time the run reaches that fraction of the route)
        now_t = max(self._clock, f.clock_ms) + self.resets * self.penalty_ms
        prog = self.progress
        while len(self.splits) < len(self.split_at) and prog >= self.split_at[len(self.splits)]:
            frac, (p0, t0) = self.split_at[len(self.splits)], self._split_prev
            # estimate the moment the split point was crossed between the last two readings (like the server)
            t = t0 + (min(frac, prog) - p0) / (prog - p0) * (now_t - t0) if prog > p0 and frac > p0 else now_t
            self.splits.append(int(round(t)))
            ev.append('split')
        self._split_prev = (prog, now_t)
        # incidents for the live commentary (a hit, a stop, off the road, reversing, a big jump)
        for inc in self.incidents.feed(f, now, prog, off, resetting=self._pending is not None or 'reset' in ev):
            self.incident_queue.append(dict(inc, clockMs=max(self._clock, f.clock_ms)))
            ev.append('incident')
        # clock stopped?
        if f.clock_ms == self._clock:
            if self._freeze_since is None:
                self._freeze_since, self._freeze_frame = now, f
            frozen = now - self._freeze_since
            ff = self._freeze_frame   # where the car was when the clock stopped (it rolls on after the line)
            to_end = math.dist((ff.x, ff.z), self.route.end)
            near_end = to_end <= FINISH_NEAR_M or self.progress >= 0.97 or (to_end <= RUNOUT_M and self.progress >= 0.85)
            if frozen >= FINISH_FREEZE_S and near_end and f.clock_ms > 0:
                self._trace_add(ff, force=True)
                self._finish(ev)
                return
            if frozen >= STOP_DNF_S:
                self._end('dnf', 'stopped (clock frozen away from the finish)', ev)
                return
        else:
            self._freeze_since = None
        self._clock = max(self._clock, f.clock_ms)
        self._trace_add(f)
        if self.ghost:
            g = self.ghost.total_at(self._max_idx)
            self.gap_ms = (self.total_ms - g) if g is not None else None
        self.message = 'On stage · %d%%' % round(self.progress * 100)

    # ------------------------------------------------------------------ helpers

    def _reset_run(self):
        self.resets = 0
        self.splits = []            # total time at each split passed so far
        self.jumps = []             # [clockMs at take-off, airtime ms, metres along the route, km/h at take-off]
        self._air = None
        self.incidents = IncidentWatch()
        self.incident_queue = []    # incidents the app has not sent yet (it pops them on 'incident' events)
        self._split_prev = (0.0, 0)
        self._clock = 0
        self._idx = None
        self._max_idx = 0
        self._hit = set()
        self._pending = None
        self._last_reset = -10 ** 9
        self._fast_at = None        # last moment driving in gear at RESET_FROM_KMH or more
        self._freeze_since = None
        self._freeze_frame = None
        self._trace = []
        self._trace_last = -10 ** 9
        self._t0 = self._p0 = None
        self._start_wall = None
        self.gap_ms = None

    def _trace_add(self, f, force=False):
        if force or f.clock_ms - self._trace_last >= TRACE_EVERY_MS:
            if self._t0 is None:
                self._t0, self._p0 = f.t, f.ppacket
            self._trace.append([max(0, f.clock_ms), round(f.x, 2), round(f.z, 2), round(f.speed, 1), self.resets,
                                int(round((f.t - self._t0) * 1000)), f.ppacket - self._p0,
                                round(f.gas, 2), round(f.brake, 2), round(f.steer, 3), f.gear, f.rpm,
                                round(f.air_k, 2)])
            self._trace_last = f.clock_ms

    def _finish(self, ev):
        # only the checkpoints before where the clock stopped count (a route may run on past the finish line)
        due = [k for k, ci in enumerate(self.route.checkpoints) if ci <= self._max_idx]
        total = len(due) or len(self.route.checkpoints)
        hit = len([k for k in due if k in self._hit]) if due else len(self._hit)
        ratio = hit / total if total else 1.0
        if ratio < MIN_CHECKPOINTS:
            self._end('invalid', 'missed part of the stage (%d of %d checkpoints)' % (hit, total), ev)
        else:
            self._end('finished', '', ev)

    def _end(self, status, reason, ev):
        self._pending = None
        total = len(self.route.checkpoints)
        self.result = {
            'challengeId': self.ch.get('id'),
            'track': self.ch['track'],
            'car': self.ch['car'],
            'status': status,
            'reason': reason,
            'clockMs': self._clock,
            'resets': self.resets,
            'penaltyMs': self.penalty_ms,
            'totalMs': self._clock + self.resets * self.penalty_ms if status == 'finished' else None,
            'checkpoints': [len(self._hit), total],
            'splits': list(self.splits),
            'jumps': list(self.jumps),
            'startedAt': self._start_wall,
            'endedAt': time.time(),
            'trace': self._trace,
        }
        self.state = status
        if status == 'finished':
            self.message = 'FINISHED %s (clock %s + %d reset%s)' % (
                fmt_ms(self.result['totalMs']), fmt_ms(self._clock), self.resets, '' if self.resets == 1 else 's')
        else:
            self.message = '%s: %s' % (status.upper(), reason)
        ev.append(status)
