"""A replay played back in the game (replays.py has what a replay is). The game is taken to the replay's stage as WATCH
takes it (ig_watch.start: the in-game DRIVE, the player's car left at the start line), and the replay's car is a
WATCH driver of its own: a real car moved by the mod along the replay's poses, the TV director's cameras, its dash, its
engine heard (ghostui / main.lua, as a live driver). Nobody from the relay meanwhile: only the replay's car.

Its clock is the viewer's: PLAY / PAUSE, 0.5x to 8x (the mod told the speed: the "wrate" line), back / on 10 s, to the
start; the broadcast's time shows the replay's own clock and the gap to the day's #1 where known."""
import collections
import time

from . import livelink, replays

RATES = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
ARM_S = 2.0                      # the viewer's car this long at the start line: the replay plays
REPLAY_ID = 9001                 # its car's id for the mod ('L9001')
JUMP_MS = 10000


class ReplayDriver(livelink.LiveDriver):
    """A replay as WATCH's driver: every pose there from the start, its clock the viewer's (rate, pause, seek)."""

    def __init__(self, doc):
        h = doc['head']
        super().__init__(REPLAY_ID, (h.get('driver') or {}).get('name') or 'Replay', h.get('car') or '', 1)
        rows = doc['rows']
        for r in rows:
            self.trace.s.append((r[0], r[1] / 100.0, r[2] / 100.0, r[3] / 100.0, r[4] / 10000.0, r[5] / 10000.0,
                                 r[6] / 10000.0))
            self.trace.ms.append(r[0])
        self.dash = collections.deque(((r[0], r[7] / 10.0, r[8], r[9], r[10] / 1000.0, r[11] / 1000.0, r[12] / 1000.0)
                                       for r in rows), maxlen=len(rows) + 1)
        self.rpm_top = max([r[9] for r in rows] + [6000])
        self.doc = doc
        self.sid = (h.get('driver') or {}).get('steamId')
        self.first, self.last = rows[0][0], rows[-1][0]
        self.fin_ms = h.get('finMs')
        self.start_wall = time.monotonic()
        self.rate, self.paused = 1.0, True       # (paused at its start until the car is in view: start())
        self._at_ms, self._at_wall = float(self.first), time.monotonic()
        self.track = h.get('track') or ''
        self.waiting, self._there_at = True, None   # (until the viewer's car is at the stage's start line: arm())

    def arm(self, f, now=None):
        """Every frame while it is watched: the game on its stage, the viewer's car at the start line (the clock at 0)
        for ARM_S -> played from its start. (Started as the game set the stage up, it was half a minute in by the time
        the camera got there: the in-game test, 26 Nov 2026.)"""
        if not self.waiting:
            return
        now = time.monotonic() if now is None else now
        from .names import same_track
        there = (f is not None and getattr(f, 'track', None) and same_track(f.track, {'track': self.track})
                 and getattr(f, 'clock_ms', None) is not None and f.clock_ms >= 0)
        if not there:
            self._there_at = None
            return
        if self._there_at is None:
            self._there_at = now
        elif now - self._there_at >= ARM_S:
            self.waiting = False
            self.seek(self.first)
            self.play(True)

    # ---- the viewer's clock
    def clock(self, now=None):
        now = time.monotonic() if now is None else now
        if self.paused:
            return self._at_ms
        c = self._at_ms + (now - self._at_wall) * 1000.0 * self.rate
        if c >= self.last:                       # (its end: held there)
            self._at_ms, self._at_wall, self.paused = float(self.last), now, True
            return self._at_ms
        return c

    def _anchor(self, now=None):
        now = time.monotonic() if now is None else now
        self._at_ms, self._at_wall = self.clock(now), now

    def play(self, on=None):
        self._anchor()
        if self.paused and self._at_ms >= self.last:
            self._at_ms = float(self.first)
        self.paused = (not self.paused) if on is None else not on

    def speed(self, d):
        """d +1 / -1: the next speed up / down."""
        self._anchor()
        i = min(range(len(RATES)), key=lambda k: abs(RATES[k] - self.rate))
        self.rate = RATES[max(0, min(len(RATES) - 1, i + d))]

    def seek(self, ms):
        self._at_ms, self._at_wall = float(max(self.first, min(self.last, ms))), time.monotonic()

    def jump(self, d):
        self.seek(self.clock() + d * JUMP_MS)

    def rate_now(self):
        return 0.0 if self.paused else self.rate

    # ---- as a LiveDriver to WATCH and the ghost cars
    def play_clock(self, now):
        self.seen = now
        return self.clock(now)

    def clock_now(self, now):
        return self.clock(now)

    def delay_ms(self):
        return 0


def start(ig, name):
    """REPLAY's WATCH: the replay `name` (a file in the store) on its stage in the game."""
    a = ig.app
    from .i18n import _
    p = replays.path_of(name)
    if not p:
        ig.say(_('REPLAY'), [_('That replay is no longer on this PC.')])
        return
    try:
        doc = replays.read(p)
    except (OSError, ValueError) as e:
        ig.say(_('REPLAY'), [str(e)])
        return
    h = doc['head']
    stage_id, car_id = h.get('stageId'), h.get('carId')
    if not stage_id or not car_id:
        stage_id, car_id = lookup_ids(a, h)
    if not stage_id or not car_id:
        ig.say(_('REPLAY'), [_("This replay's stage or car isn't known to ACR DAILY: it can't be set up in the game."),
                             _('Its page on the website plays it on the map: SHARE, then OPEN.')])
        return
    from . import ig_watch, ingamedrive, saveslot
    ch = {'id': 'replay:%s' % name, 'track': h.get('track'), 'stageId': stage_id, 'car': h.get('car'), 'carId': car_id,
          'carAliases': [], 'route': None, 'penaltyMs': 0, 'mode': 'weekend', 'weatherGame': h.get('weather') or 'WT_CLEAR',
          'startSeconds': h.get('startSeconds') or 12 * 3600, 'weekend': None}
    route = route_of(a, h.get('track'))
    judge = None
    if route:
        ch['route'] = route
        try:
            from .judge import Judge
            judge = Judge(ch)
        except Exception:
            judge = None
    held = {'ch': ch, 'judge': judge, 'live': [], 'board': None, 'name': h.get('title') or _('REPLAY'),
            'eventId': None, 'kind': 'replay', 'cars': [{'id': car_id, 'name': h.get('car')}]}
    try:
        setup = ingamedrive.setup_of(ingamedrive.daily_stages(ch), car_id, None)
    except (saveslot.SaveError, KeyError, ValueError):
        ig.say(_('REPLAY'), [_("This replay's stage can't be set up in the game.")])
        return
    driver = ReplayDriver(doc)

    def begin():
        a.watch.start('event', 1, event=held)
        a.watch.replay = driver
        a.watch.target = driver.id               # (played once the viewer is at the start line: ReplayDriver.arm)
    from .names import same_track
    f = getattr(a, 'last_frame', None)
    if f is not None and getattr(f, 'track', None) and same_track(f.track, {'track': h.get('track')}):
        begin()                                  # (on its stage already, a run just driven: watched from here)
        ig.note(_('Replay on: it plays from its start.'))
        return
    ig_watch._when_ready(ig, lambda: ig_watch._go(ig, setup, ch, begin))


def route_of(a, track):
    try:
        r = a.api._req('GET', '/api/route?track=' + __import__('urllib.parse').parse.quote(track or ''), timeout=8)
        return r.get('route') if isinstance(r, dict) else None
    except Exception:
        return None


def lookup_ids(a, h):
    """A replay made before its stage / car ids were kept (a practice run): from the server's stages and cars."""
    stage_id = car_id = None
    try:
        from .names import same_car, same_track
        for r in a.api._req('GET', '/api/routes', timeout=8) or []:
            if isinstance(r, dict) and same_track(h.get('track') or '', {'track': r.get('track')}) and r.get('stageId'):
                stage_id = r['stageId']
                break
        for c in a.api._req('GET', '/api/cars', timeout=8) or []:
            if isinstance(c, dict) and same_car(h.get('car') or '', {'car': c.get('name'), 'carId': c.get('id'),
                                                                     'carAliases': [c.get('telemetry')] + list(c.get('aliases') or [])}):
                car_id = c.get('id')
                break
    except Exception:
        pass
    return stage_id, car_id
