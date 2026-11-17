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
import os
import time

from . import __version__
from .i18n import _, n_
from .updater import is_test_build

# For the testers only, for now: LIVE in the nav and on HOME only in a test build (a four-part version, 0.1.5.32: the
# server answers only those, src/liverallies.js), never in a release; ACR_DAILY_LIVE=1 shows it from the source
ON = is_test_build(__version__) or os.environ.get('ACR_DAILY_LIVE') == '1'
COLOUR = '#FF375F'             # RANKED's colour (the nav's underline, the cards, the bar): apart from the app's own red
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
    """What a series' row says of its next session: 'Registration open · starts in 12:04 · 3 registered'."""
    if not s:
        return _('No session coming')
    n = s.get('signups') or 0
    if s['phase'] == 'upcoming':
        return _('Registration opens in %s') % left(s['signupOpens'] - now)
    if s['phase'] == 'signup':
        return _('Registration open · starts in %s · %d registered') % (left(s['starts'] - now), n)
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


QUEUE_ROWS = 60                # the timer's queue lists them all (a full session: 40 or so); more than this: "+N more"


def overlay_queue(view, no, me, now, rules=None):
    """The timer window's queue under the countdown to my start on stage `no` (liverallyui.py _lr_overlay_queue): every
    driver on that stage in start order (SS1: the start list; later: as they finished the stage before), each with what
    they are at: a finished stage's time, on stage, DNF, or their own countdown (in 0:42, GO, late); the drivers who
    left the queue without starting (missed too often, retired) are not in it. -> {'title', 'right', 'rows':
    [(start 'HH:MM:SS', name, what, kind, mine)]} (kind: 'done', 'live', 'bad', 'wait', 'go', 'late'), or None while I am
    not on that stage's list."""
    qs = (view or {}).get('queues') or []
    if not me or no >= len(qs) or not any(q.get('steamId') == me for q in qs[no]):
        return None
    r = rules or rules_of(view)
    rows, ahead, mine_at = [], 0, None
    for q in qs[no]:
        st, mine = q.get('state'), q.get('steamId') == me
        if q.get('started') is None and st in ('dns', 'dnf', 'retired'):
            continue
        if st == 'done':
            what, kind = fmt_time(q.get('timeMs')), 'done'
        elif st == 'driving':
            what, kind = _('on stage'), 'live'
        elif st == 'dnf':
            what, kind = _('DNF'), 'bad'
        else:                                        # waiting (or late): their own start, as it comes
            kind = phase(q['at'], now, r)
            what = {'wait': _('in %s') % left(q['at'] - now), 'go': _('GO'), 'late': _('late')}[kind]
            if mine_at is None and not mine:
                ahead += 1
        if mine:
            mine_at = len(rows)
        rows.append((hms(q['at']), q.get('name') or '?', what, kind, mine))
    total = len(rows)
    if len(rows) > QUEUE_ROWS:                       # (the rest, and me if I am among them: I stay listed)
        keep = rows[:QUEUE_ROWS - 1]
        if mine_at is not None and mine_at >= QUEUE_ROWS - 1:
            keep = rows[:QUEUE_ROWS - 2] + [rows[mine_at]]
        rows = keep + [('', _('+%d more') % (len(rows) - len(keep)), '', 'wait', False)]
    title = _('SS1 START LIST') if no == 0 else _('SS%d QUEUE') % (no + 1)
    mine = next((x for x in rows if x[4]), None)
    if mine and mine[3] == 'go':
        right = _('GO')
    elif mine and mine[3] == 'late':
        right = _('LATE')
    else:
        right = _("YOU'RE NEXT") if not ahead else n_('%d AHEAD OF YOU', '%d AHEAD OF YOU', ahead) % ahead
    return {'title': '%s · %d' % (title, total), 'right': right, 'rows': rows}


# ---------------------------------------------------------------------- the registration bar (as iRacing's)
def my_session(info, follow=None):
    """The session the registration bar is about: the one the app follows, else the first I registered for that is
    open for sign-up or under way. -> (series, starts) or None."""
    if follow:
        return follow
    for s in sorted((info or {}).get('sessions') or [], key=lambda x: x['starts']):
        if s.get('signedUp') and s.get('phase') in ('signup', 'running'):
            return s['series'], s['starts']
    return None


def bar_state(info, views, now, follow=None, armed=None, driving=None, name_of=lambda k: k, me_id=None):
    """What the registration bar along the bottom of the app says (liverallyui.py), in every view, as iRacing's: ->
    None (nothing: not registered), or {'key', 'chip', 'tone', 'words', 'label', 'time', 'button': (label, action) or
    None}. action: 'withdraw', 'drive' (my rally is out, the app not on it yet), 'arm' (START SSn: my next start
    counts), 'view' (its results). follow: the session the app follows; armed: (event id, stage) START SSn was pressed
    for; driving: the stage (0..) the app sees me driving in it, or None. tone: 'good', 'bad', 'slow', 'soft'."""
    key = my_session(info, follow)
    if not key:
        return None
    row = next((s for s in (info or {}).get('sessions') or [] if (s['series'], s['starts']) == key), {})
    v = (views or {}).get(key) or {}
    phase = v.get('phase') or row.get('phase')
    title = '%s · %s · %s' % (name_of(key[0]), hm(key[1]), v.get('rally') or row.get('rally') or '')
    out = dict(key=key, chip=_('RANKED'), tone='soft', words=title, label='', time='', button=None)
    if phase in ('signup', 'upcoming'):
        n = len(v['entrants']) if isinstance(v.get('entrants'), list) else row.get('signups') or 0
        return dict(out, chip=_('REGISTERED'), tone='good',
                    words=title + '  ·  ' + n_('%d registered', '%d registered', n) % n,
                    label=_('STARTS IN'), time=left(key[1] - now), button=(_('WITHDRAW'), 'withdraw'))
    if phase != 'running':
        return None
    me = v.get('me') or {}
    if v.get('publishing') or not v.get('event'):
        return dict(out, words=title + '  ·  ' + _('drawing the rally and the start list…')) if row.get('signedUp') else None
    if not me.get('signedUp'):
        return None
    ev = v['event']
    e = ev.get('entry') or {}
    if e.get('status') == 'finished':
        mine = next((r for r in v.get('standings') or [] if me_id and r.get('steamId') == me_id), {})
        place = (_('P%d of %d') % (mine['rank'], len(v.get('standings') or []))) if mine.get('rank') else ''
        return dict(out, chip=_('FINISHED'), tone='good', words=title + '  ·  ' + fmt_time(e.get('totalMs')),
                    label=place, button=(_('RESULTS'), 'view'))
    if e.get('status') in ('dnf', 'dsq'):
        return dict(out, chip=_('DNF'), tone='bad', words=title + ('  ·  ' + e['reason'] if e.get('reason') else ''),
                    button=(_('RESULTS'), 'view'))
    if me.get('out'):
        return dict(out, chip=_('OUT'), tone='bad', words=title + '  ·  ' + _('you missed your start %d times') % (
            (me['out'].get('moved') or 0) + 1), button=(_('RESULTS'), 'view'))
    if driving is not None:
        return dict(out, chip='SS%d' % (driving + 1), tone='good', words=title + '  ·  ' + _('on stage'))
    st = my_start(v, now)
    if not st:
        return dict(out, words=title + '  ·  ' + _('your next start comes as you finish the stage you are on'))
    ss = 'SS%d' % (st['no'] + 1)
    label, time_, tone = {'wait': (_('IN'), left(st['left']), 'soft'), 'go': ('', _('GO'), 'good'),
                          'late': ('', _('LATE'), 'bad')}[st['phase']]
    if follow != key:                                   # my rally is out, the app not on it yet: DRIVE sets it up
        return dict(out, chip=_('READY') if st['no'] == 0 else ss, tone='good' if st['no'] == 0 else tone,
                    words=title + '  ·  ' + _('your rally is ready · %s at %s') % (ss, hms(st['at'])),
                    label=label, time=time_, button=(_('DRIVE'), 'drive'))
    if armed == (ev.get('id'), st['no']):
        return dict(out, chip=ss, tone='good', words=title + '  ·  ' + _('START %s pressed · go at %s') % (ss, hms(st['at'])),
                    label=label, time=time_)
    return dict(out, chip=ss, tone=tone, words=title + '  ·  ' + _('your start %s · press START %s, then go') % (
        hms(st['at']), ss), label=label, time=time_, button=(_('START %s') % ss, 'arm'))
