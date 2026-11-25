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

# the cameras (mod main.lua): auto = the director cutting between them, as a rally's TV broadcast (the user, 21 Nov
# 2026: "As default, the camera should be like TV (sometimes TV sometimes cockpit etc.)")
CAMS = ('auto', 'tv', 'incar', 'seat', 'cockpit', 'onboard', 'bonnet', 'wheel', 'chase', 'far', 'heli', 'side')
CAM_NAMES = {'auto': _('AUTO'), 'tv': _('TV'), 'incar': _('IN-CAR'), 'seat': _('PASSENGER SEAT'), 'cockpit': _('COCKPIT'), 'onboard': _('ONBOARD'), 'bonnet': _('BONNET'), 'wheel': _('WHEEL'),
             'chase': _('CHASE'), 'far': _('FAR'), 'heli': _('HELICOPTER'), 'side': _('SIDE'), 'high': _('HIGH'),
             'front': _('FRONT')}
GRAPHICS = ('full', 'clean', 'off')        # all of the broadcast / the driver bar and dash only / nothing
GRAPHICS_NAMES = {'full': _('FULL'), 'clean': _('CLEAN'), 'off': _('OFF')}
FALLBACK_S = 3.0                  # the followed driver gone from the relay this long: the next one
STANDING_NEXT_S = 12.0            # the followed car standing (its finish played back: 5 s late) this long: one driving
ROUTE_AHEAD_M, ROUTE_STEP_M = 520.0, 10.0  # the road ahead of the followed car the mod is told (its TV cameras)
AUTO_DRIVER_S = 40.0              # AUTO driver: another driver at most this often
# the spectator menu's lines (Up / Down between them, Left / Right change them, Select / Back close it)
MENU = ('driver', 'camera', 'auto_driver', 'graphics', 'splits')


class Watch:
    def __init__(self, app):
        self.app = app
        self.on = False
        self.kind, self.slot = None, None     # 'daily' / 'tt' / 'event', its slot (an event's: its stage number)
        self.event, self.prefer = None, None  # (an event's stage: start())
        self.target = None                    # the followed driver: the relay's id (int)
        self.cam = 0
        self.since = None
        self._lost_at = None
        self._standing_at = None              # (the followed car standing since: followed())
        self.on_stage = False                 # (been on the stage since WATCH began: back in the menus ends it)
        self.menu = None                      # the spectator menu: None (closed) or the line on (MENU's index)
        self.graphics = 'full'
        self.splits = True                    # the split times beside the driver bar
        self.auto_driver = False              # the director picks the driver too
        self._auto_at = 0.0
        self.shot = None                      # the camera on now, as the mod says (main.lua: tv, onboard...)
        self.shot_at = 0.0                    # (when it changed: its name shown a moment)

    # ---- on / off
    def start(self, kind, slot, event=None, prefer=None):
        """kind 'daily' / 'tt' (slot: its slot), or 'event' (a championship's, a cup's, a 1V1's stage: slot its stage
        number, event its own dict, event_held()). prefer: the Steam id of the driver to follow first (WATCH's list)."""
        self.on, self.kind, self.slot = True, kind, slot
        self.event = event if kind == 'event' else None
        self.prefer = prefer
        self.target, self.cam, self.since, self._lost_at = None, 0, time.monotonic(), None
        self.on_stage = False
        self.menu, self.shot = None, None
        if self.copilot():                    # (COPILOT's co-driver: in the car, beside the driver, as the real one)
            self.cam = CAMS.index('seat')     # (the passenger seat: next to the driver, not between the headrests)
            self.graphics = 'off'

    def stop(self):
        self.on = False
        self.target = None
        self.event = None
        self.drivers()                               # (their playback back to as soon as it can be: driving)

    def ch(self):
        """The watched stage's challenge (a daily's / a time trial's / an event stage's), or None."""
        return self.held().get('ch')

    def judge(self):
        return self.held().get('judge')

    def room(self):
        """The relay's room for the watched stage: a ranked session's own (only its drivers), else None (the stage's)."""
        ev = getattr(self, 'event', None) if self.on else None
        if ev and ev.get('kind') == 'live' and ev.get('eventId'):
            return 'live:%d' % int(ev['eventId'])
        if ev and ev.get('kind') == 'copilot' and ev.get('eventId'):   # (a COPILOT crew's: its driver only, copilot.py)
            return 'cp:%d' % int(ev['eventId'])
        return None

    def copilot(self):
        """Watching as a COPILOT crew's co-driver (copilot.py): the driver's car from inside, the notes over it."""
        ev = getattr(self, 'event', None) if self.on else None
        return bool(ev and ev.get('kind') == 'copilot')

    # ---- the drivers on the stage
    def drivers(self):
        """The relay's drivers on the stage now (livelink.LiveDriver), the furthest on first."""
        g = getattr(self.app, 'ghostcars', None)
        live = getattr(g, 'live', None)
        out = list(live.others()) if live is not None else []
        from .livelink import COPILOT_DELAY_MS, WATCH_DELAY_MS
        floor = (COPILOT_DELAY_MS if self.copilot() else WATCH_DELAY_MS) if self.on else 0
        for d in out:                                # (a broadcast's steady delay: livelink.WATCH_DELAY_MS)
            d.floor_ms = floor
        # only the cars of what is watched: the relay has everyone on the stage, so a driver practising it in another
        # car (a Skoda Fabia on a Delta S4 daily, 24 Nov 2026) was followed, timed against the day's board. (Not for a
        # CODRIVER crew: the co-driver follows their own driver, whatever the car.)
        if not self.copilot():
            out = [d for d in out if self.fits(d.car)]
        rows = [(self.where(d), d) for d in out]
        # (the cars driving first, furthest on first; then the ones standing: at the start, or after their finish)
        rows.sort(key=lambda x: (bool(getattr(x[1], 'standing', False)), -(x[0]['progress'] if x[0] else -1)))
        return [d for _w, d in rows]

    def fits(self, car):
        """A car the watched stage is driven in: the daily's / time trial's own, one of an event's; a driver whose app
        names no car is kept (nothing to tell by)."""
        if not car:
            return True
        from .names import same_car
        h = self.held()
        cars = [{'car': c.get('name'), 'carId': c.get('id'), 'carAliases': c.get('aliases') or []}
                for c in h.get('cars') or () if isinstance(c, dict)]
        ch = h.get('ch') or {}
        if not cars and (ch.get('car') or ch.get('carId')):
            cars = [ch]
        return not cars or any(same_car(car, c) for c in cars)

    def held(self):
        """The watched daily's / time trial's own dict (its 'live' list: the website's, ig_daily.refresh_live)."""
        if self.kind == 'daily':
            return (self.app.dailies or {}).get(self.slot) or {}
        if self.kind == 'event':
            return getattr(self, 'event', None) or {}
        return (getattr(self.app, 'tt', None) or {}).get(self.slot) or {}

    def rows(self, now=None):
        """Everyone on the stage now, the furthest on first: [{'name', 'car', 'at': where(), 'driver': the relay's
        LiveDriver or None}]. The relay's drivers (a car to watch), and the website's live list for the rest (a
        driver whose app doesn't send their car to the relay, an older one: on the map, no car: 21 Nov 2026)."""
        now = time.monotonic() if now is None else now
        out, names = [], set()
        for d in self.drivers():
            out.append({'name': d.name, 'car': d.car, 'at': self.where(d, now), 'driver': d,
                        'country': self.country_of(d.name, getattr(d, 'sid', None))})
            names.add((d.name or '').strip().lower())
        h = self.held()
        age = now - h.get('live_at', now)
        for x in h.get('live') or ():
            name = x.get('name') or ''
            if x.get('state') != 'live' or name.strip().lower() in names:
                continue
            at = self.at_progress(x.get('progress'), (x.get('totalMs') or 0) + age * 1000.0)
            out.append({'name': name, 'car': x.get('car') or '', 'at': at, 'driver': None,
                        'country': x.get('country') or self.country_of(name, x.get('steamId'))})
        out.sort(key=lambda r: -((r['at'] or {}).get('progress') or -1))
        return out

    def country_of(self, name, sid=None):
        """A driver's country (two letters) for their flag: today's board, the website's live list, their driver page
        (fetched once); None when not known."""
        n = (name or '').strip().lower()
        h = self.held()
        for e in ((h.get('board') or {}).get('entries') or []) + list(h.get('live') or []):
            if (sid and e.get('steamId') == sid) or (n and (e.get('name') or '').strip().lower() == n):
                if e.get('country'):
                    return e['country']
        prof = self.profile(sid) if sid else None
        return (prof or {}).get('country') or None

    def at_progress(self, progress, ms):
        """where() from how far along (0..1) and the clock, as the website has them."""
        j = self.judge()
        if progress is None or j is None or not getattr(j, 'route', None) or not j.route.length:
            return None
        want = progress * j.route.length
        idx = next((i for i, c in enumerate(j.route.cum) if c >= want), len(j.route.cum) - 1)
        gap = None
        if j.ghost is not None and idx > 3:
            best = j.ghost.total_at(idx)
            if best is not None:
                gap = ms - best
        return {'progress': progress, 'ms': ms, 'gap': gap, 'km': want / 1000.0}

    def where(self, d, now=None):
        """A driver as the broadcast shows them: {'progress' 0..1, 'ms' their time, 'gap' to today's #1 at the same
        place (ms, + slower) or None, 'km'}, or None (not placed yet)."""
        now = time.monotonic() if now is None else now
        pose = d.pose(now)
        # (their clock where they are drawn, not where they are now: the gap and the time match the car on screen)
        ms = d.play_clock(now) if hasattr(d, 'play_clock') else d.clock_now(now)
        j = self.judge()
        if pose is None or ms is None or j is None or not getattr(j, 'route', None) or not j.route.length:
            return None
        idx, _dist = j.route.nearest(pose[0], pose[2])
        progress = j.route.cum[idx] / j.route.length
        # (their time held at the finish: past it their samples' clock runs on, the car rolling to a stop; the user,
        # 26 Nov 2026: "the times are still running even if the car already finished". Their app says where it
        # stopped (LiveDriver.fin_ms); an older app doesn't: held where they reach the end of the route)
        if getattr(d, 'fin_ms', None) is None and idx >= len(j.route.cum) - 1:
            d.fin_ms = ms
        if hasattr(d, 'shown_clock'):
            ms = d.shown_clock(ms)
        gap = None
        if j.ghost is not None:
            best = j.ghost.total_at(idx)
            if best is not None and idx > 3:
                gap = ms - best
        return {'progress': progress, 'ms': ms, 'gap': gap, 'km': j.route.cum[idx] / 1000.0}

    def followed(self):
        """The followed driver (a LiveDriver), the target kept while it is there; another when it has gone. AUTO
        driver: now and then the one closest to the day's #1 (the fight worth watching), else the one furthest on."""
        ds = self.drivers()
        ids = [d.id for d in ds]
        now = time.monotonic()
        if self.auto_driver and ds and now - self._auto_at >= AUTO_DRIVER_S:
            self._auto_at = now
            best = None
            for d in ds:
                if getattr(d, 'standing', False):
                    continue                         # (standing at the start / after the finish: not a fight to watch)
                g = (self.where(d, now) or {}).get('gap')
                if g is not None and (best is None or g < best[0]):
                    best = (g, d.id)
            self.target = best[1] if best else ds[0].id
            self._lost_at = None
        if self.target is None and getattr(self, 'prefer', None):    # (the driver picked on WATCH's list)
            for d in ds:
                if str(getattr(d, 'sid', '') or '') == str(self.prefer):
                    self.target, self.prefer = d.id, None
                    break
            else:
                if now - (self.since or now) < 20.0:        # (not on the relay yet: a while for them to come)
                    return None
                self.prefer = None
        if self.target in ids:
            self._lost_at = None
            d = next(d for d in ds if d.id == self.target)
            # (a car standing: their finish shown, then on to one driving, if any: the cars stay on the stage now,
            # standing at the start and after the finish, 24 Nov 2026)
            if getattr(d, 'standing', False):
                if self._standing_at is None:
                    self._standing_at = now
                moving = [x for x in ds if not getattr(x, 'standing', False)]
                if moving and now - self._standing_at >= STANDING_NEXT_S:
                    self.target, self._standing_at = moving[0].id, None
                    return moving[0]
            else:
                self._standing_at = None
            return d
        if self.target is not None and self._lost_at is None:
            self._lost_at = now
        if ds and (self.target is None or now - (self._lost_at or now) >= FALLBACK_S):
            self.target, self._lost_at = ds[0].id, None
            return ds[0]
        return None

    def why_waiting(self, rows):
        """The broadcast's line while no car is followed: why, as far as known (a friend, 24 Nov 2026: "it just stays
        stuck on WAITING FOR NEXT CAR... it won't let me switch to any other car")."""
        g = getattr(self.app, 'ghostcars', None)
        live = getattr(g, 'live', None)
        state = getattr(live, 'state', None)
        if not self.app.s.get('token'):
            return _('Sign in to ACR DAILY to watch the cars (the live server wants it).')
        if live is None or state == 'connecting':
            return _('Connecting to the live server…')
        if state == 'signin':
            return _('The live server refused the sign-in: sign in to ACR DAILY again.')
        if state == 'offline':
            return _("Can't reach the live server: trying again…")
        if rows and not any(r.get('driver') for r in rows):
            names = ', '.join(r['name'] for r in rows[:3] if r.get('name'))
            return _('%s on the stage: their ACR DAILY sends no car to watch (an older version, or the car not sent yet).') \
                % names if names else _('Waiting for the next car…')
        if rows:
            return _('Waiting for the next car…')
        return _('Waiting for a driver on the stage…')

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

    def key(self, k):
        """The wheel's / pad's / keyboard's keys while watching: 'select' opens / closes the spectator menu; in it,
        up / down between its lines, left / right change the line, back closes it; outside it, left / right the
        driver before / after, up / down the camera. -> whether something changed. A COPILOT co-driver's keys move
        through the notes instead (copilot.py)."""
        if self.copilot():
            cp = self.app.crew_owner() if hasattr(self.app, 'crew_owner') else getattr(self.app, 'copilot', None)
            return bool(cp is not None and cp.key(k))
        if k == 'select':
            self.menu = None if self.menu is not None else 0
            return True
        if self.menu is None:
            if k in ('left', 'right'):
                self.auto_driver = False             # (picked by hand: the director leaves the driver be)
                self.step(-1 if k == 'left' else 1)
            elif k in ('up', 'down'):
                self.camera(-1 if k == 'up' else 1)
            else:
                return False
            return True
        if k == 'back':
            self.menu = None
        elif k in ('up', 'down'):
            self.menu = (self.menu + (-1 if k == 'up' else 1)) % len(MENU)
        elif k in ('left', 'right'):
            d = -1 if k == 'left' else 1
            line = MENU[self.menu]
            if line == 'driver':
                self.auto_driver = False
                self.step(d)
            elif line == 'camera':
                self.camera(d)
            elif line == 'auto_driver':
                self.auto_driver = not self.auto_driver
                self._auto_at = 0.0
            elif line == 'graphics':
                self.graphics = GRAPHICS[(GRAPHICS.index(self.graphics) + d) % len(GRAPHICS)]
            elif line == 'splits':
                self.splits = not self.splits
        else:
            return False
        return True

    def profile(self, steam_id):
        """A driver's page as the server gives it ({name, country, look: {tag}...}), fetched once in a thread; None until
        it has come (or for a driver with no Steam id: an older app's)."""
        if not steam_id:
            return None
        got = self.__dict__.setdefault('_profiles', {})
        if steam_id in got:
            return got[steam_id]
        got[steam_id] = None
        import threading

        def go():
            try:
                r = self.app.api.driver(steam_id)
                got[steam_id] = r if isinstance(r, dict) else {}
            except Exception:
                got[steam_id] = {}
        threading.Thread(target=go, daemon=True).start()
        return None

    def seen_shot(self, shot):
        """The mod's camera on now (its camera line's W group), noted when it changes."""
        if shot != self.shot:
            self.shot, self.shot_at = shot, time.monotonic()

    # ---- the road
    def route_ahead(self, d, now=None):
        """The road ahead of driver d for the mod's TV cameras: [(X, Y)] in the game's units (cm), from a little
        behind them to ROUTE_AHEAD_M ahead, every ROUTE_STEP_M; [] when not known."""
        now = time.monotonic() if now is None else now
        j = self.judge()
        pose = d.pose(now) if d is not None else None
        if pose is None or j is None or not getattr(j, 'route', None) or not j.route.length:
            return []
        r = j.route
        idx, _dist = r.nearest(pose[0], pose[2])
        start = r.cum[idx] - 30.0
        out, want = [], start
        i = max(0, idx - 10)
        while i < len(r.points) and r.cum[i] <= start + ROUTE_AHEAD_M:
            if r.cum[i] >= want:
                x, z = r.points[i]
                out.append((round(x * 100.0), round(z * 100.0)))
                want = r.cum[i] + ROUTE_STEP_M
            i += 1
        return out

    # ---- the splits
    def split_marks(self):
        """Where the stage's splits are: [(route index, km)], the last at the finish (3 to 7 of them, about every
        3 km); [] when the route isn't known."""
        j = self.judge()
        if j is None or not getattr(j, 'route', None) or not j.route.length:
            return []
        r = j.route
        n = max(3, min(7, round(r.length / 3000.0)))
        out = []
        for k in range(1, n + 1):
            want = r.length * k / n
            idx = next((i for i, c in enumerate(r.cum) if c >= want - 1e-6), len(r.cum) - 1)
            out.append((idx, r.cum[idx] / 1000.0))
        return out

    def splits_of(self, d, now=None):
        """Driver d's times at the splits they have passed, against the day's #1 there: [{'km', 'ms', 'best',
        'gap'}] (ms None: not there yet)."""
        now = time.monotonic() if now is None else now
        j = self.judge()
        out = []
        at = self.where(d, now) if d is not None else None
        for idx, km in self.split_marks():
            best = j.ghost.total_at(idx) if j is not None and j.ghost is not None else None
            got = d.__dict__.setdefault('_split_ms', {}) if d is not None else {}
            ms = got.get(idx)
            if ms is None and at and at['progress'] * j.route.length >= j.route.cum[idx] + 15 and len(d.trace.s) > 1:
                x, z = j.route.points[idx]
                passed = d.trace.passed(x, z)
                if passed is not None:
                    p = d.trace.at(passed)
                    if abs(p[0] - x) + abs(p[2] - z) < 80:
                        ms = got[idx] = passed           # (once found: kept, their trace not searched again)
            out.append({'km': km, 'ms': ms, 'best': best,
                        'gap': ms - best if ms is not None and best is not None else None})
        return out

    def running_place(self, gap):
        """Where a gap to the day's #1 (ms) would put a driver on today's board now: 1, 2... (None: no gap)."""
        if gap is None:
            return None
        entries = [e for e in (self.held().get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
        if not entries:
            return None
        projected = entries[0]['totalMs'] + gap
        return 1 + sum(1 for e in entries if e['totalMs'] < projected)
