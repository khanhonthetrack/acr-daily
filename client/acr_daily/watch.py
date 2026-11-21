"""WATCH (0.2, the user, 21 Nov 2026: "a WATCH mode, where you can select people (ghosts) right now driving on stage ...
the broadcast of the current dailies: who's currently on stage, what's the best times now, how it compares").

WATCH on a daily or a time trial takes the game to its stage (its in-game DRIVE, as DRIVE does), and at the start line
the game's camera goes onto another driver's car: the live ghost cars (livelink.py: the relay's drivers on the stage,
the game mod moves a real car for each), one followed, the camera behind it (mod main.lua: its own camera, moved every
frame). Over the game, a broadcast (ig_watch.py): who is on the stage, how far, their time and the gap to today's #1 at
the same place on the road (the #1's run, the daily's ghost: judge.Ghost), the day's best times, the followed driver
big. The wheel's / pad's / keyboard's Left / Right: the driver before / after; Up / Down: the camera.

Nothing counts while watching: a run started meanwhile is practice (app._daily_started, ttui). Leaving the stage (the
game's pause menu, MAIN MENU) ends it.
"""
import time

from .i18n import _

CAMS = ('chase', 'far', 'high', 'side', 'front')
CAM_NAMES = {'chase': _('CHASE'), 'far': _('FAR'), 'high': _('HIGH'), 'side': _('SIDE'), 'front': _('FRONT')}
FALLBACK_S = 3.0                  # the followed driver gone from the relay this long: the next one


class Watch:
    def __init__(self, app):
        self.app = app
        self.on = False
        self.kind, self.slot = None, None     # 'daily' / 'tt', its slot
        self.target = None                    # the followed driver: the relay's id (int)
        self.cam = 0
        self.since = None
        self._lost_at = None
        self.on_stage = False                 # (been on the stage since WATCH began: back in the menus ends it)

    # ---- on / off
    def start(self, kind, slot):
        self.on, self.kind, self.slot = True, kind, slot
        self.target, self.cam, self.since, self._lost_at = None, 0, time.monotonic(), None
        self.on_stage = False

    def stop(self):
        self.on = False
        self.target = None

    def ch(self):
        """The watched stage's challenge (a daily's / a time trial's), or None."""
        if self.kind == 'daily':
            return ((self.app.dailies or {}).get(self.slot) or {}).get('ch')
        return ((getattr(self.app, 'tt', None) or {}).get(self.slot) or {}).get('ch')

    def judge(self):
        if self.kind == 'daily':
            return ((self.app.dailies or {}).get(self.slot) or {}).get('judge')
        return ((getattr(self.app, 'tt', None) or {}).get(self.slot) or {}).get('judge')

    # ---- the drivers on the stage
    def drivers(self):
        """The relay's drivers on the stage now (livelink.LiveDriver), the furthest on first."""
        g = getattr(self.app, 'ghostcars', None)
        live = getattr(g, 'live', None)
        out = list(live.others()) if live is not None else []
        rows = [(self.where(d), d) for d in out]
        rows.sort(key=lambda x: -(x[0]['progress'] if x[0] else -1))
        return [d for _w, d in rows]

    def where(self, d, now=None):
        """A driver as the broadcast shows them: {'progress' 0..1, 'ms' their time, 'gap' to today's #1 at the same
        place (ms, + slower) or None, 'km'}, or None (not placed yet)."""
        now = time.monotonic() if now is None else now
        pose = d.pose(now)
        ms = d.clock_now(now)
        j = self.judge()
        if pose is None or ms is None or j is None or not getattr(j, 'route', None) or not j.route.length:
            return None
        idx, _dist = j.route.nearest(pose[0], pose[2])
        progress = j.route.cum[idx] / j.route.length
        gap = None
        if j.ghost is not None:
            best = j.ghost.total_at(idx)
            if best is not None and idx > 3:
                gap = ms - best
        return {'progress': progress, 'ms': ms, 'gap': gap, 'km': j.route.cum[idx] / 1000.0}

    def followed(self):
        """The followed driver (a LiveDriver), the target kept while it is there; another when it has gone."""
        ds = self.drivers()
        ids = [d.id for d in ds]
        now = time.monotonic()
        if self.target in ids:
            self._lost_at = None
            return next(d for d in ds if d.id == self.target)
        if self.target is not None and self._lost_at is None:
            self._lost_at = now
        if ds and (self.target is None or now - (self._lost_at or now) >= FALLBACK_S):
            self.target, self._lost_at = ds[0].id, None
            return ds[0]
        return None

    # ---- the controls
    def step(self, d):
        ds = self.drivers()
        if not ds:
            return
        ids = [x.id for x in ds]
        i = ids.index(self.target) if self.target in ids else 0
        self.target = ids[(i + d) % len(ids)]
        self._lost_at = None

    def camera(self, d):
        self.cam = (self.cam + d) % len(CAMS)

    def cam_name(self):
        return CAMS[self.cam]

    def ghost_id(self):
        """The followed driver's car as the mod knows it ('L<id>': ghostui), or None."""
        d = self.followed()
        return 'L%d' % d.id if d is not None else None
