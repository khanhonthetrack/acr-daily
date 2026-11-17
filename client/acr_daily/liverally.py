"""Live rallies (server src/liverallies.js): the logic of the app's LIVE page (liverallyui.py), without Tk.

Two series, each a car class, a session every 2 hours, the series in turn (each every 4 hours), each series in one
country a week. Sign-up in the 30 minutes before the hour (with a car of the class); at the hour the server draws the
rally (3 stages, the weather, the time of day: nobody can prepare it) and publishes the start list: car 1 at the hour + 5
minutes, then one every 30 s. A finished stage puts the driver in the next stage's queue: the next free 30-s slot at
least 2 minutes on. On time: the stage clock starts from 5 s before the slot to 30 s after it. Late: to the end of the
queue (no penalty, for now); early: the seconds jumped are added. Ghost cars: only the session's drivers (a room of its
own on the live relay). Not rated, for now.

The session is a league event (kind 'live') driven through the leagues' DRIVE (leagueui.py): the app counts down to
each start on the timer window, sends each start with the server's time (Clock), and asks for the next stage's slot as
soon as a stage is finished.
"""
import time

from .i18n import _

ON = True                      # the 0.1.5.x test builds: LIVE in the nav and on HOME (the server: LIVE_FROM)
COLOUR = '#FF375F'             # LIVE's colour (the nav's underline, the cards): a live red, apart from the app's own
KIND = 'live'                  # its events' kind (/api/me/events, the session's event)
RULES = {'signupMin': 30, 'firstStartMin': 5, 'gapS': 30, 'earlyS': 5, 'windowS': 30, 'graceS': 20, 'turnaroundS': 120,
         'maxMoves': 3, 'stages': 3}      # (the server's, until it has said its own: the session's 'live')
SOON_S = 15 * 60               # a session I'm in starting within this: the page shows it first, polled more often


class Clock:
    """The server's clock, as the app's (its PC clock may be off by seconds, the slots are to the second): the offset
    learned from each answer's `now`, the one with the quickest round trip kept (the least doubt about it)."""

    def __init__(self):
        self.offset_ms = 0.0
        self.known = False
        self._rtt = None
        self._at = 0.0

    def learn(self, server_ms, sent, got):
        """An answer with the server's `now` (ms), asked at `sent` and in at `got` (time.time()): the offset, kept when
        its round trip is the quickest so far (or the last one is ten minutes old: clocks drift)."""
        if not isinstance(server_ms, (int, float)) or got < sent:
            return
        rtt = got - sent
        if self._rtt is None or rtt <= self._rtt or got - self._at > 600:
            self.offset_ms = server_ms - (sent + got) / 2 * 1000
            self._rtt, self._at, self.known = rtt, got, True

    def now_ms(self, wall=None):
        """The server's time now (ms)."""
        return (time.time() if wall is None else wall) * 1000 + self.offset_ms

    def server_ms(self, pc_ms):
        """A moment on this PC's clock (ms, e.g. a judge's start) on the server's."""
        return None if pc_ms is None else round(pc_ms + self.offset_ms)


def hms(ms, tz=None):
    """A moment (ms, the server's time) as this PC's local time of day: '08:06:30'."""
    t = time.localtime(ms / 1000.0) if tz is None else time.gmtime(ms / 1000.0 + tz)
    return time.strftime('%H:%M:%S', t)


def hm(ms, tz=None):
    return hms(ms, tz)[:5]


def left(ms):
    """A countdown: '0:42', '12:05', '1:02:03'."""
    s = max(0, int(-(-ms // 1000)))
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return '%d:%02d:%02d' % (h, m, s) if h else '%d:%02d' % (m, s)


def rules_of(view):
    return dict(RULES, **((view or {}).get('live') or {}))


def phase(slot_at, now, rules=None):
    """Where a start stands: 'wait' (before the window), 'go' (in it: from earlyS before the slot to windowS after),
    'late' (after it: the server sends the driver to the end of the queue once graceS more have gone by)."""
    r = rules or RULES
    if now < slot_at - r['earlyS'] * 1000:
        return 'wait'
    return 'go' if now <= slot_at + r['windowS'] * 1000 else 'late'


STATE = {'waiting': _('waiting'), 'late': _('late'), 'driving': _('on stage'), 'done': _('finished'), 'dnf': _('DNF'),
         'dns': _('did not start'), 'retired': _('retired')}
STATE_COLOUR = {'waiting': 'soft', 'late': 'slow', 'driving': 'live', 'done': 'good', 'dnf': 'bad', 'dns': 'muted',
                'retired': 'muted'}


def fmt_time(ms):
    """A stage or total time: '6:12.345'."""
    if ms is None:
        return ''
    m, s = divmod(ms / 1000.0, 60)
    return '%d:%06.3f' % (m, s)


def queue_rows(view, no, me=None):
    """Stage `no`'s queue (SS1: the start list) as the page lists it: [(start 'HH:MM:SS', name, car, what, colour key,
    mine)], in start order. what: the state, a finished stage's time, a late driver's moves, a jump start's penalty."""
    out = []
    qs = (view or {}).get('queues') or []
    for q in (qs[no] if no < len(qs) else []):
        what = STATE.get(q.get('state'), q.get('state') or '')
        if q.get('state') == 'done' and q.get('timeMs') is not None:
            what = fmt_time(q['timeMs'])
        if q.get('moved'):
            what += '  ·  ' + (_('moved to the end %d×') % q['moved'])
        if q.get('penaltyMs'):
            what += '  ·  ' + (_('jump start +%d s') % round(q['penaltyMs'] / 1000))
        out.append((hms(q['at']), q.get('name') or '?', q.get('car') or '', what, STATE_COLOUR.get(q.get('state'), 'soft'),
                    bool(me) and q.get('steamId') == me))
    return out


def standings_rows(view, me=None):
    """The session's standings: [(position, name, car, total or state, gap, mine)]."""
    out = []
    for r in (view or {}).get('standings') or []:
        st = r.get('status')
        if st == 'finished':
            total, gap = fmt_time(r.get('totalMs')), ('+' + fmt_time(r['gapMs'])) if r.get('gapMs') else ''
        else:
            total, gap = (_('DNF') if st == 'dnf' else _('DSQ') if st == 'dsq' else _('SS%d of %d') % (
                (r.get('done') or 0) + 1, len((view.get('event') or {}).get('stages') or ()) or 3)), ''
        out.append((str(r.get('rank') or '–'), r.get('name') or '?', r.get('car') or '', total, gap,
                    bool(me) and r.get('steamId') == me))
    return out


def my_start(view, now, rules=None):
    """My next start in a published session: {'no', 'at', 'moved', 'phase', 'left'} (left: ms until the slot), or None."""
    nxt = ((view or {}).get('me') or {}).get('next')
    if not nxt or nxt.get('at') is None:
        return None
    return dict(nxt, phase=phase(nxt['at'], now, rules or rules_of(view)), left=nxt['at'] - now)


def pick(info, now, me_in=()):
    """The session the page shows first: one I'm in under way (or starting within SOON_S), else one open for sign-up,
    else the next. info: /api/liverallies. -> (series, starts) or None."""
    ss = (info or {}).get('sessions') or []
    mine = [s for s in ss if (s.get('signedUp') or (s.get('series'), s.get('starts')) in me_in) and s.get('phase') in ('signup', 'running')
            and (s.get('entry') or {}).get('status') not in ('finished', 'dnf', 'dsq')]
    for s in mine:
        if s['phase'] == 'running' or s['starts'] - now < SOON_S * 1000:
            return s['series'], s['starts']
    for want in ('signup', 'upcoming'):
        s = next((x for x in ss if x.get('phase') == want), None)
        if s:
            return s['series'], s['starts']
    return None


def next_session(info, series, now):
    """A series' next session to sign up for, or the one under way: its overview row, or None."""
    ss = [s for s in (info or {}).get('sessions') or [] if s.get('series') == series and s.get('phase') in ('signup', 'upcoming', 'running')]
    return ss[0] if ss else None


def card_line(s, now):
    """What a series' card says of its next session: 'SIGN-UP OPEN · STARTS IN 12:04 · 3 SIGNED UP'."""
    if not s:
        return _('No session coming')
    n = s.get('signups') or 0
    if s['phase'] == 'upcoming':
        return _('Sign-up opens in %s') % left(s['signupOpens'] - now)
    if s['phase'] == 'signup':
        return _('Sign-up open · starts in %s · %d signed up') % (left(s['starts'] - now), n)
    if s['phase'] == 'running':
        return _('Under way · %d drivers') % n if n else _('Under way')
    return ''


def overlay(view, no, now):
    """The timer window before stage `no` of a session (not driving it yet): (status, ms shown, line, colour key) or
    None (no slot known). status: 'wait' (the countdown to the slot), 'go' (start now: the window's time left),
    'late' (the window gone: the server moves me to the end of the queue)."""
    st = my_start(view, now)
    if not st or st['no'] != no:
        return None
    r = rules_of(view)
    if st['phase'] == 'wait':
        moved = (' · ' + _('moved: late')) if st.get('moved') else ''
        line = _('SS%d at %s · start at GO') % (no + 1, hms(st['at'])) + moved
        return 'wait', st['left'], line, 'slow' if st['left'] < 60000 else 'soft'
    if st['phase'] == 'go':
        rest = st['at'] + r['windowS'] * 1000 - now
        return 'go', 0, _('GO · start SS%d now · %d s left') % (no + 1, max(0, round(rest / 1000))), 'good'
    return 'late', 0, _('LATE · to the end of the queue: wait'), 'bad'
