"""Ghost cars (a test): another run drawn on the road in front of you, over the game.

The game publishes the car's position, heading, pitch and roll (telemetry.py) but nothing about its camera, so the
camera is modelled: the car's pose, moved by a mount (forward / up / side, in metres) and tilted, with a field of view.
The mounts are the game's own, per car and camera (cameras.json, read out of the game files by
tools/gamefiles/cameras.py), measured from the car's root (found from the tyres); you can fine-tune each on top.

Runs are recorded here at 20 a second ([clockMs, x, y, z, heading, pitch, roll]) and saved in
%APPDATA%\\ACR Daily\\ghosts\\<stage>\\. Live drivers (livelink.py) are the same samples, sent through the live relay.
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

# The game's driving cameras, in the order its camera key (C, or a wheel / pad button) steps through them.
GAME_VIEWS = ('bonnet', 'gauge', 'helmet', 'near', 'far', 'bumper')
VIEW_NAMES = {'bonnet': 'Bonnet', 'gauge': 'Dash', 'helmet': 'Helmet', 'near': 'Chase near', 'far': 'Chase far',
              'bumper': 'Bumper'}
CHASE = ('near', 'far')
# Where the ghost's line starts (m ahead of your car point): not over your own bonnet, dash or car.
LINE_FROM_M = {'bonnet': 4.0, 'bumper': 2.5, 'gauge': 8.0, 'helmet': 9.0, 'near': 3.5, 'far': 3.5}
# The car's root (the game's car actor: where its camera positions are measured from) seen from the telemetry's car
# point (forward, up), until the tyres tell (car_root()). Read from the game itself (the ACR Daily mod, 2026-11-05):
# 0.13 m behind and 0.57 m below the car point on the Skoda, i.e. 0.04 m ahead of the middle of the wheelbase and
# 0.10 m below the tyres' contact points.
ROOT_DEFAULT = (-0.13, -0.57)
ACTOR_FROM_CONTACTS = (0.04, -0.10)
FALLBACK_CAR = 'SkodaFabiaRSRally2'
ADJUST = ('fwd', 'up', 'side', 'tilt', 'fov')      # your own fine-tuning of a view, on top of the game's camera
LIVE_SERVER = 'wss://immich.tail0d617f.ts.net:10000/live'   # the live relay (live/relay.py on the Raspberry Pi)
DEFAULTS = dict(on=False, view='bonnet', follow=True, adjust={}, source='last', earlierS=0.0, line=True, always=False,
                mirror=False, live=False, liveServer=LIVE_SERVER, ingame=False)
LEGACY = ('fov', 'fwd', 'up', 'side', 'tilt', 'level')   # (the first test's hand-set view: no longer used)


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
    """The game's camera as modelled: where it is and which way it looks, in world coordinates.

    fov_deg is the field of view across a 16:9 picture. The game keeps the height of the view and shows more at the
    sides on a wider screen: on 3440 x 1440 the bonnet camera measured 91 degrees across, which is 75 at 16:9."""

    def __init__(self, pos, f, r, u, fov_deg, width, height, mirror=False):
        self.pos, self.f, self.r, self.u = pos, f, r, u
        self.w, self.h = width, height
        half = math.tan(math.radians(max(10.0, min(150.0, fov_deg))) / 2.0)
        self.focal = (height / 2.0) / (half * 9.0 / 16.0)
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
    """pose: (x, y, z, heading, pitch, roll) of your car; cfg: the mount (view_cfg(): fwd, up, side in metres from the
    car point, tilt (+ = up) and yaw (+ = right) in degrees, fov)."""
    x, y, z, h, p, r = pose
    f, rt, u = basis(h, 0.0, 0.0) if cfg.get('level') else basis(h, p, r)
    pos = add(add(add((x, y, z), mul(f, cfg.get('fwd', 0.0))), mul(u, cfg.get('up', 0.0))), mul(rt, cfg.get('side', 0.0)))
    yw = math.radians(cfg.get('yaw', 0.0))
    if yw:
        f, rt = add(mul(f, math.cos(yw)), mul(rt, math.sin(yw))), sub(mul(rt, math.cos(yw)), mul(f, math.sin(yw)))
    t = math.radians(cfg.get('tilt', 0.0))
    f, u = add(mul(f, math.cos(t)), mul(u, math.sin(t))), sub(mul(u, math.cos(t)), mul(f, math.sin(t)))
    return Camera(pos, f, rt, u, cfg.get('fov', 75.0), width, height, bool(cfg.get('mirror')))


# ---------------------------------------------------------------------- the game's cameras

_TABLE = None


def camera_table():
    """cameras.json (tools/gamefiles/cameras.py reads it out of the game): {'cars': {blueprint: {names, cameras}}}."""
    global _TABLE
    if _TABLE is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cameras.json'), encoding='utf-8') as f:
                _TABLE = json.load(f)
        except (OSError, ValueError):
            _TABLE = {'cars': {}}
    return _TABLE


def car_cameras(car):
    """The game's cameras of the car the telemetry names, or None for a car not in the table."""
    from .names import same_car
    for key, c in camera_table().get('cars', {}).items():
        n = c.get('names') or [key]
        if same_car(car, {'car': n[0], 'carId': key, 'carAliases': n[1:]}):
            return c['cameras']
    return None


def game_view(car, view, root=None):
    """The game's camera `view` on `car`, as a mount on the car point: {fwd, up, side, tilt, yaw, fov}.
    root: (forward, up) of the car's root from the car point (car_root()). The chase cameras follow the car and
    look level with it whatever their own pitch says (seen in the game)."""
    cams = car_cameras(car) or (camera_table().get('cars', {}).get(FALLBACK_CAR) or {}).get('cameras')
    if not cams or view not in cams:
        return {'fwd': 1.09, 'up': 0.58, 'side': 0.0, 'tilt': -5.3, 'yaw': 0.0, 'fov': 75.0}
    c = cams[view]
    rf, ru = root or ROOT_DEFAULT
    return {'fwd': c['y'] / 100.0 + rf, 'up': c['z'] / 100.0 + ru, 'side': -c['x'] / 100.0,
            'tilt': 0.0 if view in CHASE else c['pitch'], 'yaw': c['yaw'] - 90.0, 'fov': c['fov']}


def view_cfg(cfg, car, root=None):
    """The camera to draw with: the game's view chosen in cfg, plus your own fine-tuning of it."""
    view = cfg.get('view') if cfg.get('view') in GAME_VIEWS else 'bonnet'
    out = game_view(car, view, root)
    adj = (cfg.get('adjust') or {}).get(view) or {}
    for k in ADJUST:
        out[k] += float(adj.get(k, 0.0) or 0.0)
    out['mirror'] = bool(cfg.get('mirror'))
    return out


def car_root(contacts, pose):
    """(forward, up) of the car's root (the game's car actor) from the car point, from the four tyre contact points
    (FL, FR, RL, RR, world): the middle of the wheelbase on the contact plane, moved by ACTOR_FROM_CONTACTS."""
    f, _r, u = basis(pose[3], pose[4], pose[5])
    rel = [sub(c, pose[:3]) for c in contacts]
    fw = [dot(d, f) for d in rel]
    up = [dot(d, u) for d in rel]
    return (((fw[0] + fw[1]) / 2.0 + (fw[2] + fw[3]) / 2.0) / 2.0 + ACTOR_FROM_CONTACTS[0],
            sum(up) / 4.0 + ACTOR_FROM_CONTACTS[1])


# ---------------------------------------------------------------------- the game's own units (the ACR Daily mod)
# The game's world: X = telemetry x, Y = telemetry z, Z = telemetry y, in centimetres. Its car actor's yaw is the
# telemetry heading (degrees); the car model faces the actor's +Y, so the actor's pitch is the car's roll and its roll
# the car's pitch, both the other way round (checked against the telemetry while driving).

def ue_pose(pose, root=None):
    """A telemetry pose (car point) -> the game actor's (X, Y, Z, Pitch, Yaw, Roll) for a car there."""
    x, y, z, h, p, r = pose
    f, _rt, u = basis(h, p, r)
    rf, ru = root or ROOT_DEFAULT
    px, py, pz = add(add((x, y, z), mul(f, rf)), mul(u, ru))
    return (px * 100.0, pz * 100.0, py * 100.0, -math.degrees(r), math.degrees(h), -math.degrees(p))


def camera_from_game(cam, width, height, mirror=False):
    """The game's own camera (the mod's ingame-camera.txt: X, Y, Z, Pitch, Yaw, Roll, horizontal fov) -> a Camera."""
    X, Y, Z, P, Yw, R, fov = cam
    sp, cp = math.sin(math.radians(P)), math.cos(math.radians(P))
    sy, cy = math.sin(math.radians(Yw)), math.cos(math.radians(Yw))
    sr, cr = math.sin(math.radians(R)), math.cos(math.radians(R))
    fwd = (cp * cy, cp * sy, sp)                                   # Unreal's rotation matrix: X, Y (right), Z (up)
    right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    tele = lambda v: (v[0], v[2], v[1])                            # the game's axes -> the telemetry's
    c = Camera((X / 100.0, Z / 100.0, Y / 100.0), tele(fwd), tele(right), tele(up), 75.0, width, height, mirror)
    c.focal = (width / 2.0) / math.tan(math.radians(max(10.0, min(170.0, fov))) / 2.0)
    return c


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
    """'last': the newest finished run on the stage; 'best': the fastest finished one.
    With none finished, the newest run (a run you restarted or left)."""
    runs = list_runs(track)
    done = [r for r in runs if r['finished']]
    if done:
        return min(done, key=lambda r: r['clockMs']) if source == 'best' else done[0]
    return runs[0] if runs else None


def load_run(meta):
    try:
        with open(meta['path'], encoding='utf-8') as f:
            return GhostTrace(json.load(f))
    except (OSError, ValueError, KeyError):
        return None
