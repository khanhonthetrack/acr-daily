"""Ghost cars (a test): another run drawn on the road in front of you, over the game.

The game publishes the car's position, heading, pitch and roll (telemetry.py) but nothing about its camera, so the
camera is modelled: the car's pose, moved by a mount (forward / up / side, in metres) and tilted, with a field of view.
Set up once per view (ghostui.py's set-up window); the ghost's own line on the road shows when it fits.

Runs are recorded here at 20 a second ([clockMs, x, y, z, heading, pitch, roll]) and saved in
%APPDATA%\\ACR Daily\\ghosts\\<stage>\\. For now the ghost is one of your own runs; a live driver's stream would be the
same samples, sent through the server.
"""
import bisect
import json
import math
import os
import re
import time

from . import settings
from .judge import FINISH_FREEZE_S, PAUSE_STILL_M

SAMPLE_MS = 50            # one sample every 50 ms of stage clock
KEEP_RUNS = 20            # runs kept per stage (the newest)
MIN_RUN_MS = 10000        # shorter runs are not kept
GONE_S = 5.0              # no telemetry this long = the run is over
CAR_ABOVE_GROUND = 0.53   # the telemetry's car point is this high above the tyre contacts (measured)
CAR_BOX = (4.0, 1.8, -0.5, 0.9)   # length, width, bottom and top (from the car point) of the box drawn
MAX_DRAW_M = 500.0        # further than this: not drawn
SIGHT_ROAD_M = 9.0        # line of sight further than this from the ghost's path (sideways): trees / a hill in the way

# Views to start from (the mount from the car point). The game's own camera options move them; set up from there.
VIEWS = {
    'bonnet': {'fov': 75.0, 'fwd': 0.5, 'up': 0.65, 'side': 0.0, 'tilt': 0.0, 'level': False},
    'bumper': {'fov': 75.0, 'fwd': 1.9, 'up': 0.05, 'side': 0.0, 'tilt': 0.0, 'level': False},
    'cockpit': {'fov': 70.0, 'fwd': -0.35, 'up': 0.55, 'side': -0.35, 'tilt': 0.0, 'level': False},
    'chase': {'fov': 70.0, 'fwd': -5.5, 'up': 1.7, 'side': 0.0, 'tilt': -7.0, 'level': True},
}
DEFAULTS = dict(VIEWS['bonnet'], on=False, view='bonnet', source='last', earlierS=0.0, line=True, always=False,
                mirror=False)


def runs_dir():
    return os.path.join(settings.DIR, 'ghosts')


def stage_dir(track):
    return os.path.join(runs_dir(), re.sub(r'[^\w\- ]', '_', track or 'unknown'))


# ---------------------------------------------------------------------- maths

def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def basis(h, p=0.0, r=0.0):
    """(forward, right, up) of a car with heading h, pitch p (nose up > 0), roll r (right side up > 0)."""
    f = (-math.sin(h), 0.0, math.cos(h))
    rt = (-math.cos(h), 0.0, -math.sin(h))
    u = (0.0, 1.0, 0.0)
    cp, sp = math.cos(p), math.sin(p)
    f, u = add(mul(f, cp), mul(u, sp)), sub(mul(u, cp), mul(f, sp))
    cr, sr = math.cos(r), math.sin(r)
    rt, u = add(mul(rt, cr), mul(u, sr)), sub(mul(u, cr), mul(rt, sr))
    return f, rt, u


class Camera:
    """The game's camera as modelled: where it is and which way it looks, in world coordinates."""

    def __init__(self, pos, f, r, u, fov_deg, width, height, mirror=False):
        self.pos, self.f, self.r, self.u = pos, f, r, u
        self.w, self.h = width, height
        self.focal = (width / 2.0) / math.tan(math.radians(max(10.0, min(150.0, fov_deg))) / 2.0)
        self.mirror = mirror

    def depth(self, p):
        return dot(sub(p, self.pos), self.f)

    def project(self, p, near=0.3):
        """Screen (x, y) of world point p, or None behind the camera."""
        d = sub(p, self.pos)
        z = dot(d, self.f)
        if z < near:
            return None
        x = dot(d, self.r) * (-1 if self.mirror else 1)
        y = dot(d, self.u)
        return (self.w / 2.0 + self.focal * x / z, self.h / 2.0 - self.focal * y / z)


def camera_for(pose, cfg, width, height):
    """pose: (x, y, z, heading, pitch, roll) of your car; cfg: the view (VIEWS keys)."""
    x, y, z, h, p, r = pose
    f, rt, u = basis(h, 0.0, 0.0) if cfg.get('level') else basis(h, p, r)
    pos = add(add(add((x, y, z), mul(f, cfg.get('fwd', 0.0))), mul(u, cfg.get('up', 0.0))), mul(rt, cfg.get('side', 0.0)))
    t = math.radians(cfg.get('tilt', 0.0))
    f, u = add(mul(f, math.cos(t)), mul(u, math.sin(t))), sub(mul(u, math.cos(t)), mul(f, math.sin(t)))
    return Camera(pos, f, rt, u, cfg.get('fov', 75.0), width, height, bool(cfg.get('mirror')))


def box_corners(pose):
    """The 8 corners of the car-sized box at pose: bottom 4 (front left, front right, rear right, rear left), then top 4."""
    x, y, z, h, p, r = pose
    f, rt, u = basis(h, p, r)
    length, width, lo, hi = CAR_BOX
    out = []
    for up in (lo, hi):
        for a, b in ((1, -1), (1, 1), (-1, 1), (-1, -1)):
            out.append(add(add(add((x, y, z), mul(f, a * length / 2)), mul(rt, b * width / 2)), mul(u, up)))
    return out


BOX_EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]


def _angle_lerp(a, b, k):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * k


# ---------------------------------------------------------------------- a recorded run

class GhostTrace:
    """One run: samples [clockMs, x, y, z, heading, pitch, roll], the clock always going up."""

    def __init__(self, data):
        self.track, self.car = data.get('track', ''), data.get('car', '')
        self.finished = bool(data.get('finished'))
        self.clock_ms = data.get('clockMs')
        self.started_at = data.get('startedAt')
        self.s = [tuple(x) for x in data.get('samples') or []]
        self.ms = [x[0] for x in self.s]
        self._hint = 0

    @property
    def end_ms(self):
        return self.ms[-1] if self.ms else 0

    def at(self, ms):
        """(x, y, z, heading, pitch, roll) at its own stage clock ms (held at its first / last sample outside)."""
        if not self.s:
            return None
        i = bisect.bisect_right(self.ms, ms)
        if i <= 0:
            return self.s[0][1:]
        if i >= len(self.s):
            return self.s[-1][1:]
        a, b = self.s[i - 1], self.s[i]
        k = (ms - a[0]) / float(b[0] - a[0] or 1)
        return (a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k,
                _angle_lerp(a[4], b[4], k), a[5] + (b[5] - a[5]) * k, a[6] + (b[6] - a[6]) * k)

    def index_at(self, ms):
        return max(0, min(len(self.s) - 1, bisect.bisect_right(self.ms, ms) - 1))

    def passed(self, x, z, ahead=80, back=10):
        """Its own clock when it was where (x, z) is (closest point of its line), searched from where it was found last
        (a road that comes back near itself does not confuse it); the whole run when the nearby part is far off."""
        if len(self.s) < 2:
            return None
        last = len(self.s) - 1
        lo, hi = max(0, self._hint - back), min(last, self._hint + ahead)
        best = self._nearest(x, z, lo, hi)           # (segments lo .. hi - 1)
        at_edge = (best[0] == lo and lo > 0 and best[2] == 0.0) or (best[0] == hi - 1 and hi < last and best[2] == 1.0)
        if best[1] > 30.0 or at_edge:
            best = self._nearest(x, z, 0, last)
        i, _d, k = best
        self._hint = i
        a, b = self.s[i], self.s[min(i + 1, len(self.s) - 1)]
        return a[0] + (b[0] - a[0]) * k

    def _nearest(self, x, z, lo, hi):
        """(segment index, distance, how far along it) of the point of segments lo..hi closest to (x, z)."""
        best = (lo, 1e18, 0.0)
        s = self.s
        for i in range(lo, max(lo + 1, hi)):
            if i + 1 >= len(s):
                break
            ax, az, bx, bz = s[i][1], s[i][3], s[i + 1][1], s[i + 1][3]
            dx, dz = bx - ax, bz - az
            ll = dx * dx + dz * dz
            k = 0.0 if ll <= 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / ll))
            px, pz = ax + dx * k, az + dz * k
            d = (x - px) ** 2 + (z - pz) ** 2
            if d < best[1]:
                best = (i, d, k)
        return best[0], math.sqrt(best[1]), best[2]

    def path(self, ms_a, ms_b, step_m=3.0, max_m=None):
        """Its line from its clock ms_a to ms_b: [(x, y, z)], a point every step_m (at least), up to max_m long."""
        if not self.s:
            return []
        i, j = self.index_at(ms_a), self.index_at(ms_b) + 1
        out, run = [], 0.0
        for k in range(i, min(j + 1, len(self.s))):
            p = self.s[k][1:4]
            if out:
                d = math.dist(out[-1], p)
                if d < step_m:
                    continue
                run += d
                if max_m is not None and run > max_m:
                    break
            out.append(p)
        return out


def in_sight(cam_pos, ghost_pos, path, road_m=SIGHT_ROAD_M):
    """Can you see the ghost from cam_pos (a guess: the game tells nothing of trees or hills)? Yes while the straight line
    to it stays over its line on the road (within road_m sideways) and above the road (no crest in between)."""
    if len(path) < 3:
        return True
    cx, cy, cz = cam_pos
    gx, gy, gz = ghost_pos
    gy += 0.2                                   # aim at the middle of the car
    dx, dz = gx - cx, gz - cz
    ll = dx * dx + dz * dz
    if ll < 25.0:
        return True
    # crest: a point of the road (car point - CAR_ABOVE_GROUND) above the line of sight
    for px, py, pz in path[1:-1]:
        k = ((px - cx) * dx + (pz - cz) * dz) / ll
        if 0.05 < k < 0.95 and py - CAR_ABOVE_GROUND > cy + (gy - cy) * k + 0.2:
            return False
    # corner: points along the line of sight far from the road
    n = max(2, int(math.sqrt(ll) / 6.0))
    j = 0
    for m in range(1, n):
        k = m / float(n)
        sx, sz = cx + dx * k, cz + dz * k
        best = 1e18
        # the path goes from you to the ghost like the line of sight: look near the last match
        for t in range(max(0, j - 3), len(path) - 1):
            ax, az, bx, bz = path[t][0], path[t][2], path[t + 1][0], path[t + 1][2]
            ex, ez = bx - ax, bz - az
            el = ex * ex + ez * ez
            q = 0.0 if el <= 1e-9 else max(0.0, min(1.0, ((sx - ax) * ex + (sz - az) * ez) / el))
            d = (sx - ax - ex * q) ** 2 + (sz - az - ez * q) ** 2
            if d < best:
                best, j = d, t
        if best > road_m * road_m:
            return False
    return True


# ---------------------------------------------------------------------- recording and the saved runs

class GhostRecorder:
    """Keeps every run (from the stage clock's start to the finish, a restart or the game going away) as a ghost."""

    def __init__(self, wall=time.time):
        self.wall = wall             # (the tests' own clock)
        self.state = 'idle'          # idle | armed | recording
        self.samples, self.track, self.car = [], '', ''
        self.clock = 0
        self.started_at = None
        self._prev = None
        self._freeze = None
        self._gone_at = None
        self.saved = None            # the path of the last run saved

    def feed(self, f, now=None):
        now = time.monotonic() if now is None else now
        if f is None:
            if self.state == 'recording':
                self._gone_at = self._gone_at or now
                if now - self._gone_at > GONE_S:
                    self._end(False)
            return
        self._gone_at = None
        prev, self._prev = self._prev, f
        if self.state == 'recording':
            if f.clock_ms < self.clock - 500 or f.track != self.track:     # restarted, or another stage
                self._end(False)
            else:
                self._record(f, now)
                return
        if f.clock_ms == 0 and f.track:
            self.state = 'armed'
        elif self.state == 'armed' and f.clock_ms > 0 and prev is not None and prev.clock_ms == 0:
            self.state, self.track, self.car, self.samples = 'recording', f.track, f.car, []
            self.clock, self._freeze, self.started_at = f.clock_ms, None, int(self.wall() * 1000)
            self._record(f, now)

    def _record(self, f, now):
        if not self.samples or f.clock_ms >= self.samples[-1][0] + SAMPLE_MS:
            self.samples.append([f.clock_ms, round(f.x, 2), round(f.y, 2), round(f.z, 2), round(f.heading, 4),
                                 round(f.pitch, 4), round(f.roll, 4)])
        if f.clock_ms == self.clock:
            if self._freeze is None:
                self._freeze = (now, (f.x, f.z))
            t0, at = self._freeze
            # finish = the clock stopped while the car kept rolling (a pause freezes the car too)
            if now - t0 >= FINISH_FREEZE_S and math.dist(at, (f.x, f.z)) > PAUSE_STILL_M:
                self.samples = [s for s in self.samples if s[0] <= self.clock]
                self._end(True)
        else:
            self._freeze = None
            self.clock = f.clock_ms

    def _end(self, finished):
        if self.samples and self.samples[-1][0] >= MIN_RUN_MS:
            self.saved = save_run({'track': self.track, 'car': self.car, 'startedAt': self.started_at,
                                   'clockMs': self.clock, 'finished': finished, 'samples': self.samples})
        self.state, self.samples, self._freeze = 'idle', [], None


def save_run(data):
    d = stage_dir(data['track'])
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, '%d_%d_%s.json' % (data['startedAt'] or 0, data['clockMs'], 'F' if data['finished'] else 'U'))
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))
    os.replace(path + '.tmp', path)
    for old in list_runs(data['track'])[KEEP_RUNS:]:
        try:
            os.remove(old['path'])
        except OSError:
            pass
    return path


def list_runs(track):
    """The runs saved on a stage, newest first: [{'path', 'startedAt', 'clockMs', 'finished'}] (from the file names)."""
    out = []
    try:
        names = os.listdir(stage_dir(track))
    except OSError:
        return out
    for n in names:
        m = re.match(r'^(\d+)_(\d+)_([FU])\.json$', n)
        if m:
            out.append({'path': os.path.join(stage_dir(track), n), 'startedAt': int(m.group(1)),
                        'clockMs': int(m.group(2)), 'finished': m.group(3) == 'F'})
    return sorted(out, key=lambda r: -r['startedAt'])


def pick_run(track, source='last'):
    """'last': the newest run on the stage; 'best': the fastest finished one (the newest if none finished)."""
    runs = list_runs(track)
    if source == 'best':
        done = [r for r in runs if r['finished']]
        if done:
            return min(done, key=lambda r: r['clockMs'])
    return runs[0] if runs else None


def load_run(meta):
    try:
        with open(meta['path'], encoding='utf-8') as f:
            return GhostTrace(json.load(f))
    except (OSError, ValueError, KeyError):
        return None
