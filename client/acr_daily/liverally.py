"""Ranked rallies (server src/liverallies.js): the logic of the app's RANKED page, its turn window and its bar
(liverallyui.py, rankedgate.py), without Tk.

Two series, each a car class, a session every 2 hours, the series in turn (each every 4 hours), each series in one
country a week. Registration in the 30 minutes before the hour (with a car of the class); at the hour the server draws
the rally (3 stages, the weather, the time of day: nobody can prepare it) and publishes the start list, the best rated
first. Then it runs as a real rally, by turns: 5 minutes to get the game ready, then one driver's turn at a time, 20 s
to start (green lights); the turn passes to the next driver the moment they start. A turn missed: to the end of the
queue (out after 3). Started on red: the seconds jumped are added. After each stage a 3-minute break, then the next
stage's queue, whoever is ready first going first. Ghost cars: only the session's drivers (a room of its own on the live
relay). Not rated, for now.

The session is a league event (kind 'live') driven through the leagues' DRIVE (leagueui.py): the app shows my place in
the queue in a window over the game that can't be closed (rankedgate.py), sends each start with the server's time
(Clock), and joins the next stage's queue as soon as a stage is finished. No button to press: when the app follows the
session, a start on its stage is the ranked run.
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
RULES = {'signupMin': 30, 'firstStartMin': 5, 'turnS': 20, 'earlyS': 2, 'breakS': 180, 'maxMoves': 3,
         'stages': 3}             # (the server's, until it has said its own: the session's 'live')
SOON_S = 15 * 60               # a session I'm in starting within this: the page shows it first, polled more often


class Clock:
    """The server's clock, as the app's (its PC clock may be off by seconds, the turns are to the second): the offset
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


STATE = {'turn': _('their turn'), 'waiting': _('waiting'), 'break': _('on break'), 'driving': _('on stage'),
         'done': _('finished'), 'dnf': _('DNF'), 'dns': _('did not start'), 'retired': _('retired')}
STATE_COLOUR = {'turn': 'good', 'waiting': 'soft', 'break': 'slow', 'driving': 'live', 'done': 'good', 'dnf': 'bad',
                'dns': 'muted', 'retired': 'muted'}
QUEUED = ('turn', 'waiting', 'break')


def fmt_time(ms):
    """A stage or total time: '6:12.345'."""
    if ms is None:
        return ''
    m, s = divmod(ms / 1000.0, 60)
    return '%d:%06.3f' % (m, s)


def my_start(view, now, rules=None):
    """My next turn in a published session, as it stands now: the server's last word (me.next) moved on by the clock
    between two looks. -> dict(me.next, phase, left, ahead) or None. phase: 'turn' (mine: `left` until its end), 'late'
    (its end gone by, the server not asked since: to the end of the queue), 'break' (not in the queue yet: `left` until
    I am; SS1 before its first turn too), 'wait' (in the queue: `left` until my turn at the latest, `ahead` turns before
    mine)."""
    nxt = ((view or {}).get('me') or {}).get('next')
    if not nxt or nxt.get('at') is None:
        return None
    st = nxt.get('state')
    ready = nxt.get('readyAt') if nxt.get('readyAt') is not None else nxt['at']
    est = nxt.get('estAt') if nxt.get('estAt') is not None else nxt['at']
    if st == 'turn':
        end = nxt.get('deadline') or nxt['at'] + (rules or rules_of(view))['turnS'] * 1000
        return dict(nxt, phase='turn' if now < end else 'late', left=end - now, ahead=0)
    if now < ready:
        return dict(nxt, phase='break', left=ready - now, ahead=nxt.get('ahead') or 0)
    return dict(nxt, phase='wait', left=est - now, ahead=nxt.get('ahead') or 0)


def queue_rows(view, no, me=None):
    """Stage `no`'s queue (SS1: the start list) as the page lists it, in the order of the turns: [(when, name, car, what,
    colour key, mine)]. when: a start's time, NOW for the turn, '≤ 08:06:30' for the latest a waiting turn comes. what:
    the state, a finished stage's time, a missed turn's moves, a jump start's penalty."""
    out = []
    qs = (view or {}).get('queues') or []
    for q in (qs[no] if no < len(qs) else []):
        st = q.get('state')
        what = STATE.get(st, st or '')
        if st == 'break' and no == 0:
            what = _('waiting')
        if st == 'done' and q.get('timeMs') is not None:
            what = fmt_time(q['timeMs'])
        if q.get('moved'):
            what += '  ·  ' + (n_('missed a turn', 'missed %d turns', q['moved']) % q['moved'])
        if q.get('penaltyMs'):
            what += '  ·  ' + (_('jump start +%d s') % round(q['penaltyMs'] / 1000))
        if q.get('started') is not None:
            when = hms(q['started'])
        elif st == 'turn':
            when = _('NOW')
        elif st in QUEUED and q.get('estAt') is not None:
            when = '≤ ' + hms(q['estAt'])
        else:
            when = ''
        out.append((when, q.get('name') or '?', q.get('car') or '', what, STATE_COLOUR.get(st, 'soft'),
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


def results_rows(view, me=None):
    """The results page's table: [{'pos', 'name', 'car', 'stages': [(time, note)], 'total', 'gap', 'state', 'mine'}]:
    each stage's time with its place on it (a jump start's seconds, a stage not driven: '–'), the total and the gap, or
    the DNF with its reason."""
    out = []
    n = len(((view or {}).get('event') or {}).get('stages') or ()) or 3
    for r in (view or {}).get('standings') or []:
        cells = []
        for k in range(n):
            x = (r.get('stages') or [None] * n)[k] if k < len(r.get('stages') or ()) else None
            if not x or x.get('totalMs') is None:
                cells.append(('–', ''))
                continue
            note = ('P%d' % x['pos']) if x.get('pos') else (_('retired') if x.get('retired') else '')
            if x.get('stewardMs'):
                note += ('  ' if note else '') + _('+%d s jump') % round(x['stewardMs'] / 1000)
            cells.append((fmt_time(x['totalMs']), note))
        st = r.get('status')
        total = fmt_time(r.get('totalMs')) if st == 'finished' or r.get('classified') else             {'dnf': _('DNF'), 'dsq': _('DSQ')}.get(st, _('on SS%d') % ((r.get('done') or 0) + 1))
        out.append({'pos': str(r['rank']) if r.get('rank') else '–', 'name': r.get('name') or '?', 'car': r.get('car') or '',
                    'stages': cells, 'total': total, 'gap': ('+' + fmt_time(r['gapMs'])) if r.get('gapMs') else '',
                    'state': st, 'reason': r.get('reason') or '', 'mine': bool(me) and r.get('steamId') == me})
    return out


def my_result(view, me):
    """My line in a session's results: ('P2 of 5', '18:42.123') or ('DNF', reason), or None."""
    rows = (view or {}).get('standings') or []
    r = next((x for x in rows if me and x.get('steamId') == me), None)
    if not r:
        out = ((view or {}).get('me') or {}).get('out')
        return (_('DID NOT START'), _('missed your turn %d times') % ((out.get('moved') or 0) + 1)) if out else None
    if r.get('rank'):
        return _('P%d of %d') % (r['rank'], len(rows)), fmt_time(r.get('totalMs'))
    return {'dnf': _('DNF'), 'dsq': _('DSQ')}.get(r.get('status'), _('RUNNING')), r.get('reason') or ''


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
        return n_('Under way · %d driver', 'Under way · %d drivers', n) % n if n else _('Under way')
    return ''


def overlay(view, no, now):
    """The timer window before stage `no` of a session (not driving it yet): (status, ms shown, line, colour key) or
    None (no turn known). status: 'wait' (red: the time to my turn at the latest), 'go' (my turn: its time left),
    'break' (between stages: the time to the queue), 'late' (my turn gone by: to the end of the queue)."""
    st = my_start(view, now)
    if not st or st['no'] != no:
        return None
    if st['phase'] == 'turn':
        return 'go', max(0, st['left']), _('YOUR TURN · start SS%d now') % (no + 1), 'good'
    if st['phase'] == 'late':
        return 'late', 0, _('Turn missed · to the end of the queue'), 'bad'
    if st['phase'] == 'break':
        if no == 0:
            return 'wait', st['left'], _('SS1 · the first turn in %s · get ready') % left(st['left']), 'bad'
        return 'break', st['left'], _('BREAK · then the SS%d queue') % (no + 1), 'slow'
    ahead = st['ahead']
    words = _("You're next") if ahead <= 1 else n_('%d driver before you', '%d drivers before you', ahead) % ahead
    return 'wait', st['left'], _('WAIT · SS%d · %s') % (no + 1, words), 'bad'


GATE_ROWS = 8                  # the turn window lists this many of the queue (the turn, then the next ones; me always)


def gate(view, me, now, following=True, stage_name=None):
    """What the turn window says (rankedgate.py): my place in my next stage's queue, as it goes. -> None (nothing to wait
    for: not in a session's queue now), or {'mode', 'no', 'kicker', 'stage', 'head', 'big', 'line', 'now', 'rows',
    'drive'}. mode: 'ready' (the rally is out, the app not set up for it yet: DRIVE), 'wait' (red lights: the time to
    my turn at the latest), 'turn' (green: mine, 20 s to start), 'break' (amber: between stages), 'late' (my turn gone
    by, the server not asked since). now: whose turn it is ('Ben · 0:12'); rows: [(place, name, what, kind, mine)]."""
    st = my_start(view, now)
    if not st:
        return None
    no = st['no']
    ev = (view or {}).get('event') or {}
    stages = ev.get('stages') or []
    name = stage_name or (stages[no].get('name') if no < len(stages) else '') or ''
    out = {'no': no, 'kicker': _('RANKED · %s') % (ev.get('league') or ev.get('name') or ''), 'drive': not following,
           'stage': ('SS%d · %s' % (no + 1, name.upper())).strip(' ·'), 'now': '', 'rows': []}
    qs = (view or {}).get('queues') or []
    q = qs[no] if no < len(qs) else []
    cur = next((x for x in q if x.get('state') == 'turn'), None)
    if cur and cur.get('steamId') != me:
        out['now'] = _('Turn: %s · %s') % (cur.get('name') or '?', left((cur.get('deadline') or now) - now))
    rows = []
    for x in q:
        if x.get('state') not in QUEUED:
            continue
        mine = x.get('steamId') == me
        what = {'turn': _('TURN'), 'break': _('break') if no else _('ready'), 'waiting': ''}[x['state']]
        if x['state'] == 'waiting' and x.get('estAt') is not None:
            what = '≤ ' + left(x['estAt'] - now)
        rows.append((str(len(rows) + 1), x.get('name') or '?', what, x['state'], mine))
    mine_at = next((i for i, r in enumerate(rows) if r[4]), None)
    if len(rows) > GATE_ROWS:
        keep = rows[:GATE_ROWS]
        if mine_at is not None and mine_at >= GATE_ROWS:
            keep = rows[:GATE_ROWS - 1] + [rows[mine_at]]
        rows = keep
    out['rows'] = rows
    if not following:                                  # the rally is out: DRIVE sets the game up for it
        return dict(out, mode='ready', head=_('YOUR RALLY IS READY'), big=left(st['left']),
                    line=_('Press DRIVE: the app sets the game up. Your turn in %s at the latest.') % left(st['left'])
                    if st['phase'] != 'turn' else _('It is your turn now: press DRIVE, then start.'))
    if st['phase'] == 'turn':
        r = rules_of(view)
        return dict(out, mode='turn', head=_('GO'), big=left(st['left']),
                    line=_('It is your turn. You have %d seconds to start.') % r['turnS'])
    if st['phase'] == 'late':
        return dict(out, mode='late', head=_('TURN MISSED'), big='', line=_('To the end of the queue: wait for your next turn.'))
    if st['phase'] == 'break':
        if no == 0:
            return dict(out, mode='wait', head=_('WAIT'), big=left(st['left']),
                        line=_('Get the game ready on SS1: the first turn in %s. You are %s on the start list.') % (
                            left(st['left']), _('first') if not st['ahead'] else '#%d' % (st['ahead'] + 1)))
        return dict(out, mode='break', head=_('BREAK'), big=left(st['left']),
                    line=_('Load SS%d. You join its queue in %s.') % (no + 1, left(st['left'])))
    ahead = st['ahead']
    who = _("You're next") if ahead <= 1 else n_('%d driver before you', '%d drivers before you', ahead) % ahead
    return dict(out, mode='wait', head=_('WAIT'), big=left(st['left']),
                line=_('%s: your turn in %s at the latest.') % (who, left(st['left'])))


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


def bar_state(info, views, now, follow=None, driving=None, name_of=lambda k: k, me_id=None):
    """What the registration bar along the bottom of the app says (liverallyui.py), in every view, as iRacing's: ->
    None (nothing: not registered), or {'key', 'chip', 'tone', 'words', 'label', 'time', 'button': (label, action) or
    None}. action: 'withdraw', 'drive' (my rally is out, the app not on it yet), 'results' (its results page). follow:
    the session the app follows; driving: the stage (0..) the app sees me driving in it, or None. tone: 'good', 'bad',
    'slow', 'soft'."""
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
    results = (_('RESULTS'), 'results')
    if e.get('status') == 'finished':
        mine = next((r for r in v.get('standings') or [] if me_id and r.get('steamId') == me_id), {})
        place = (_('P%d of %d') % (mine['rank'], len(v.get('standings') or []))) if mine.get('rank') else ''
        return dict(out, chip=_('FINISHED'), tone='good', words=title + '  ·  ' + fmt_time(e.get('totalMs')),
                    label=place, button=results)
    if e.get('status') in ('dnf', 'dsq'):
        return dict(out, chip=_('DNF'), tone='bad', words=title + ('  ·  ' + e['reason'] if e.get('reason') else ''),
                    button=results)
    if me.get('out'):
        return dict(out, chip=_('OUT'), tone='bad', words=title + '  ·  ' + _('you missed your turn %d times') % (
            (me['out'].get('moved') or 0) + 1), button=results)
    if driving is not None:
        return dict(out, chip='SS%d' % (driving + 1), tone='good', words=title + '  ·  ' + _('on stage'))
    st = my_start(v, now)
    if not st:
        return dict(out, words=title + '  ·  ' + _('your next stage\'s queue comes as you finish the stage you are on'))
    ss = 'SS%d' % (st['no'] + 1)
    if follow != key:                                   # my rally is out, the app not on it yet: DRIVE sets it up
        return dict(out, chip=_('READY'), tone='good', words=title + '  ·  ' + _('your rally is ready: DRIVE'),
                    label=_('TURN IN'), time=left(st['left']), button=(_('DRIVE'), 'drive'))
    if st['phase'] == 'turn':
        return dict(out, chip=ss, tone='good', words=title + '  ·  ' + _('your turn: start %s now') % ss,
                    label=_('GO'), time=left(st['left']))
    if st['phase'] == 'late':
        return dict(out, chip=ss, tone='bad', words=title + '  ·  ' + _('turn missed: to the end of the queue'))
    if st['phase'] == 'break':
        return dict(out, chip=ss, tone='slow', words=title + '  ·  ' + (_('the first turn comes soon: get ready') if st['no'] == 0
                                                                           else _('break, then the %s queue') % ss),
                    label=_('IN'), time=left(st['left']))
    ahead = st['ahead']
    return dict(out, chip=ss, tone='bad', words=title + '  ·  ' + (_("wait: you're next") if ahead <= 1 else
                                                                     _('wait: %d drivers before you') % ahead),
                label=_('AT MOST'), time=left(st['left']))
