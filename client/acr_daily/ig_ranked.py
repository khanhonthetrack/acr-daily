"""RANKED in the game (ingamekit.py says how a page is made), as the window's page (liverallyui.py): SERIES (my session
once I'm registered in one: who else is, then from the hour its stages and each stage's queue; then the series by their
next session, with the car to register with and REGISTER) and RESULTS (the sessions over, ALL / MINE, each opening its
report: the stages and their fastest, the podium, my result, the classification). Only in the builds that have RANKED
(liverally.ON: ingameapp.TABS). Registering, withdrawing, the car and DRIVE are the window's own methods."""
import os
import time

from . import avatars, i18n, liverally, photos, settings, tmtext
from .i18n import _, local, n_
from .ingamekit import (BAD, BG, FG2, GOOD, LINE2, MUTED, PANEL, PANEL2, PICS_DIR, SLOW, SOFT, WHITE, box, btn, chip,
                        col, edit, empty, img, kicker, link, primary, quiet, row, rule, scroll, size, sp, tab_id, tabs,
                        txt)

TAB = 'live'
LIVE = liverally.COLOUR.lstrip('#')
STRIPE = '101013'                       # (app.py: every other row)
MEDAL = {'1': 'FFD60A', '2': 'D4D4D8', '3': 'FF9F0A'}
TONE = {'good': GOOD, 'bad': BAD, 'slow': SLOW, 'live': LIVE, 'muted': MUTED}
INFO_EVERY_S = 60                       # (liverallyui.py: the series again, while the page is open)
POLL_S = 30                             # (liverallyui.py: a session, unless the server says otherwise)
RESULTS_ROWS = 200                      # (all of them: the page scrolls, the wheel steps down it)
SHOWN_ROWS = 200
CARS_A_ROW = 3


# ---------------------------------------------------------------------- what the page has to hand
def _key_arg(key):
    return '%s|%d' % (key[0], int(key[1]))


def _key_of(arg):
    s, _sep, t = (arg or '').partition('|')
    try:
        return s, int(t)
    except ValueError:
        return None


def _mem(ig):
    m = ig.mem(TAB)
    m.setdefault('tab', 'series')        # 'series' / 'results'
    m.setdefault('report', None)         # a report open: its (series, starts)
    m.setdefault('mine', False)          # RESULTS: only mine
    m.setdefault('cars', None)           # the series whose cars are listed to pick from
    m.setdefault('q', None)              # my session's queue shown: 0.. (None: as it goes)
    return m


def opened(ig):
    a = ig.app
    a._lr_ready()
    a.refresh_live_rallies()
    m = _mem(ig)
    for key in {a._lr_registered(), m['report']} - {None}:
        a._lr_poll(key)


def _keep_fresh(ig, a, m):
    """While the page is on screen in the game, the data looked at again as the window's page does (_lr_tick does it only
    while the window's page is open): the series every INFO_EVERY_S, my session and a report open at their pollS."""
    if not getattr(ig, 'shown', False):
        return
    now = time.monotonic()
    at = a._lr_at
    if now - at.get('info', -1e9) >= INFO_EVERY_S:
        a.refresh_live_rallies()
    for key in {a._lr_registered(), m['report']} - {None}:
        every = (a.lr_data.get(key) or {}).get('pollS') or POLL_S
        if now - at.get(key, -1e9) >= every:
            a._lr_poll(key)


_flags = {}                             # code -> (its PNG or None, when looked)


def flag_png(code):
    """A country's flag as a local PNG, made once (avatars.py fetches it, in a thread, the first time it is asked for:
    0.2 has no window that fetched it before, and no flag showed in the game, 22 Nov 2026). -> its path or None while
    it comes (the page then says the code)."""
    code = str(code or '').lower()
    if len(code) != 2 or not code.isalpha():
        return None
    got = _flags.get(code)
    if got and (got[0] or time.monotonic() - got[1] < 5):
        return got[0]
    out = os.path.join(settings.DIR, PICS_DIR, 'flag-%s.png' % code)
    path = out if os.path.exists(out) else None
    if path is None:
        raw = avatars._raw_of(avatars.FLAG_URL % code)
        if raw:
            try:
                os.makedirs(os.path.dirname(out), exist_ok=True)
                raw.convert('RGBA').resize((54, 36)).save(out + '.tmp', 'PNG')
                os.replace(out + '.tmp', out)
                path = out
            except (OSError, ValueError, AttributeError):
                path = None
    _flags[code] = (path, time.monotonic())
    return path


def _hex(c, default):
    c = str(c or '').lstrip('#')
    return c if len(c) == 6 and all(ch in '0123456789abcdefABCDEF' for ch in c) else default


def driver(d, fg=SOFT, bold=False, sz=17):
    """A driver as the lists show one: their flag (or country code), [TAG] and name."""
    d = d or {}
    code = d.get('country')
    f = flag_png(code)
    mark = img(f, 27, 18, va='c', pad=[0, 0, 8, 0]) if f else (
        txt(str(code).upper(), 13, 'bold', MUTED, va='c', pad=[0, 0, 8, 0]) if code else None)
    tag = tmtext.plain(tmtext.tag_of(d))
    team = txt(tag, sz - 1, 'bold', _hex((d.get('team') or {}).get('color'), FG2), va='c', pad=[0, 0, 6, 0]) if tag else None
    return row(mark, team, txt(d.get('name') or '?', sz, 'bold' if bold else 'semi', fg, va='c'))


def cell(s, w, sz=17, f='semi', fg=SOFT, j=0, **o):
    return size(txt(s, sz, f, fg, j=j), w=w, **o)


def head_cell(s, w, j=0, **o):
    return size(kicker(s, j=j), w=w, **o) if w else kicker(s, j=j, fill=1, **o)


def heading(s, right=None):
    return col(row(kicker(s), sp(fill=1), kicker(right, fg=LIVE) if right else None), rule(pad=[0, 6, 0, 0]),
               pad=[0, 28, 0, 10])


def line_bg(i, mine):
    return PANEL2 if mine else (PANEL if i % 2 else STRIPE)


def logo(series, w, h, tile=False):
    """A series' logo (series/<key>-logo.png) or its tile (series/<key>.png), fitted in w x h, or None."""
    p = os.path.join(photos.SERIES_DIR, series + ('.png' if tile else '-logo.png')) if series else None
    return img(p, w, h, va='c') if p and os.path.isfile(p) else None


def hairline_chip(s, fg):
    return box(txt(s, 14, 'bold', fg, sp=60), bg='-', ol=fg, olw=1, p=[8, 2, 8, 2], r=2, va='c')


# ---------------------------------------------------------------------- the page
def page(ig):
    a = ig.app
    a._lr_ready()
    m = _mem(ig)
    _keep_fresh(ig, a, m)
    info = a.lr_info
    tab = m['tab']
    n = len((info or {}).get('recent') or [])
    top = row(txt(_('RANKED'), 34, 'bold', WHITE, va='c'), sp(14), hairline_chip(_('NOT RATED YET'), LIVE), sp(40),
              tabs(tab_id(TAB, 'page'), [('series', _('SERIES')),
                                         ('results', '%s  %d' % (_('RESULTS'), n) if n else _('RESULTS'))],
                   None if m['report'] else tab, va='c'),
              pad=[0, 0, 0, 14])
    if m['report']:
        return col(top, report(ig, m['report']))
    if info is None or not info.get('on'):
        msg = a.lr_msg or (_('Loading…') if info is None else _('No ranked rallies on this server yet.'))
        return col(top, empty(msg, pad=[0, 10, 0, 0]))
    if tab == 'results':
        return col(top, results_list(ig, info))
    return col(top, series_page(ig, info))


# ---- SERIES
def series_page(ig, info):
    a = ig.app
    now = a.lr_clock.now_ms()
    out = [txt(_('Official rallies every hour, four series in turn. Register in the 30 minutes before the hour: the '
                 'stages and the weather are drawn at the hour, with the start list.'), 17, 'medium', FG2, wrap=True)]
    mine = a._lr_registered()
    if mine:
        out.append(session(ig, mine, now))
    out.append(heading(_('SERIES')))
    for s in info.get('series') or []:
        out.append(series_row(ig, s, info, now))
    r = liverally.rules_of(info)
    out.append(heading(_('HOW IT WORKS')))
    # (four short lines, not a paragraph to read in the game, 22 Nov 2026)
    how = (_('Every hour, one car at a time.'), _('On your turn you have %d s to start.') % r['turnS'],
           _('Jump start: the time early is added.'), _('Restart, retiring or changed settings: DNF.'))
    for i, line in enumerate(how):
        out.append(txt(line, 17, 'medium', SOFT if i == 0 else MUTED, wrap=True, pad=[0, 0 if i == 0 else 4, 0, 0]))
    out.append(sp(h=10))
    return col(*out)


NEXT_W, ACT_W = 320, 260               # the series rows' right-hand columns: as wide on every row (the times aligned)


def series_row(ig, s, info, now):
    a = ig.app
    m = _mem(ig)
    nxt = liverally.next_session(info, s['key'], now)
    key = (s['key'], nxt['starts']) if nxt else None
    mine = bool(nxt and nxt.get('signedUp'))
    cars = [c['name'] for c in s.get('cars') or []]
    title = row(box(txt(s.get('carClass') or '', 15, 'bold', BG, sp=40), bg=WHITE, p=[8, 1, 8, 1], va='c'),
                txt((s.get('name') or '').upper(), 28, 'bold', WHITE, va='c', pad=[12, 0, 0, 0]))
    car_line = None
    if mine:
        car = nxt.get('car') or ((a.lr_data.get(key) or {}).get('me') or {}).get('car') or a._lr_car(s['key']) or ''
        car_line = txt('✓  ' + _('Registered with the %s') % car, 16, 'bold', GOOD)
    elif nxt and nxt['phase'] in ('signup', 'upcoming') and cars:
        car = a._lr_car(s['key']) or ''
        car_line = row(kicker(_('CAR'), va='c', pad=[0, 0, 10, 0]),
                       btn(tab_id(TAB, 'cars', s['key']), car + '   ▾', bg=BG, hov=PANEL2, fg=WHITE, hfg=WHITE, sz=16,
                           f='semi', p=[12, 4, 12, 4], r=2, ol=LINE2))
    mid = col(title,
              txt('  ·  '.join(cars), 16, 'medium', FG2, wrap=True, pad=[0, 4, 0, 0]),
              txt(_('This week  %s   ·   next week  %s') % (s.get('rally') or '', s.get('nextRally') or ''), 16, 'medium',
                  SOFT, wrap=True, pad=[0, 2, 0, 0]),
              car_line and size(car_line, pad=[0, 10, 0, 0]),
              fill=1, va='c', pad=[20, 14, 20, 14])
    when = col(kicker(_('NEXT SESSION'), j=2),
               txt(liverally.hm(nxt['starts']) if nxt else '–', 40, 'bold', WHITE, j=2),
               txt(liverally.row_line(nxt, now), 15, 'medium', FG2, j=2, wrap=True) if nxt else None,
               va='c')
    if not nxt:
        act = None
    elif mine:
        act = hairline_chip('✓  ' + _('REGISTERED'), GOOD)
    elif nxt['phase'] == 'signup':
        act = primary(tab_id(TAB, 'register', _key_arg(key)), _('REGISTER  ›'))
    elif nxt['phase'] == 'upcoming':
        act = hairline_chip(_('OPENS %s') % liverally.hm(nxt['signupOpens']), MUTED)
    else:
        act = hairline_chip(_('UNDER WAY'), MUTED)
    line = row(size(box(None, bg=LIVE if mine else LINE2), w=5),
               logo(s['key'], 224, 126, tile=True) and size(logo(s['key'], 224, 126, tile=True), pad=[14, 10, 0, 10], va='c'),
               mid,
               size(when, w=NEXT_W, va='c'),
               size(row(sp(fill=1), act, va='c'), w=ACT_W, va='c', pad=[20, 0, 20, 0]))
    picker = None
    if m['cars'] == s['key'] and not mine and cars:
        picked = a._lr_car(s['key'])
        lines = []
        for i in range(0, len(cars), CARS_A_ROW):
            lines.append(row(*[size(btn(tab_id(TAB, 'car', '%s|%d' % (s['key'], k)), name,
                                        bg=WHITE if name == picked else '-', hov=WHITE, fg=BG if name == picked else SOFT,
                                        hfg=BG, sz=16, f='semi', p=[14, 6, 14, 6], r=2, ol=None if name == picked else LINE2),
                                    w=360, pad=[0 if k == i else 8, 0, 0, 0])
                               for k, name in enumerate(cars[i:i + CARS_A_ROW], start=i)], pad=[0, 0 if not lines else 8, 0, 0]))
        picker = col(*lines, pad=[25, 0, 20, 14])
    return box(col(line, picker), bg=PANEL, pad=[0, 8, 0, 0])


# ---- my session
def session(ig, key, now):
    a = ig.app
    v = a.lr_data.get(key)
    s_row = next((s for s in (a.lr_info or {}).get('sessions') or [] if (s['series'], s['starts']) == key), None)
    rally = (v or s_row or {}).get('rally') or ''
    phase = (v or s_row or {}).get('phase')
    chip_s = {'signup': _('REGISTRATION OPEN'), 'running': _('UNDER WAY'), 'over': _('OVER')}.get(phase, '')
    me = (v or {}).get('me') or {}
    car = me.get('car') or (s_row or {}).get('car') or ''
    if v is not None and v.get('event'):
        right = (primary if v.get('resultsOut') else quiet)(
            tab_id(TAB, 'report', _key_arg(key)), _('RESULTS') + '  ›',
            va='c')
    elif phase == 'signup':
        right = col(kicker(_('STARTS IN'), j=2), txt(liverally.left(key[1] - now), 40, 'bold', WHITE, j=2), va='c')
    else:
        right = None
    head = row(logo(key[0], 160, 90) and size(logo(key[0], 160, 90), pad=[0, 0, 18, 0], va='c'),
               col(txt('%s  ·  %s' % (a._lr_series_name(key[0]).upper(), rally.upper()), 28, 'bold', WHITE),
                   txt(_('Starts at %s') % liverally.hm(key[1]) + ('   ·   ' + car if car else ''), 16, 'medium', FG2,
                       pad=[0, 2, 0, 0]), va='c'),
               sp(fill=1), right)
    if v is None:
        body = txt(a.lr_msg or _('Loading the session…'), 17, 'medium', SOFT, pad=[0, 10, 0, 0])
    elif phase in ('upcoming', 'signup') or (v.get('publishing') and not v.get('event')):
        body = signup_part(ig, key, v)
    elif v.get('event'):
        body = rally_part(ig, key, v, me, now)
    else:
        body = txt(_('Nobody registered for this one.'), 17, 'medium', SOFT, pad=[0, 10, 0, 0])
    return col(heading(_('YOUR SESSION'), chip_s),
               box(col(size(box(None, bg=LIVE), h=4), col(head, body, pad=[24, 16, 24, 20])), bg=PANEL),
               chat_part(ig, key))


CHAT_H = 300                           # the chat's lines: this tall, scrolled (the newest at the bottom)


def chat_part(ig, key):
    """The session's chat (rankedchat.py): its drivers' lines, a box to write in and SEND; ON / OFF beside its title."""
    from . import rankedchat
    a = ig.app
    shown = rankedchat.on(a)
    switch = quiet(tab_id(TAB, 'chat_onoff'), _('CHAT ON') if shown else _('CHAT OFF'), va='c', sz=15, p=[14, 5, 14, 5])
    head = row(kicker(_('Chat · the drivers of this session'), va='c'), sp(fill=1), switch, pad=[0, 18, 0, 8])
    if not shown:
        return head
    st = rankedchat.state(_mem(ig), key)
    if getattr(ig, 'shown', False):
        rankedchat.poll(a, st, key)
    me = a.s.get('steamId')
    lines = []
    for x in st['lines']:
        mine = x.get('steamId') == me
        when = time.strftime('%H:%M', time.localtime((x.get('at') or 0) / 1000.0)) if x.get('at') else ''
        lines.append(row(size(txt(when, 14, 'medium', MUTED, va='t', pad=[0, 3, 0, 0]), w=56),
                         size(txt(x.get('name') or '?', 16, 'bold', LIVE if mine else WHITE, va='t'), w=200),
                         txt(x.get('body') or '', 17, 'medium', SOFT, wrap=True, fill=1), pad=[0, 3, 0, 3]))
    if not lines:
        lines = [empty(_('Nothing said yet. Say hello to the others in this session.'), pad=[0, 6, 0, 0])]
    area = size(box(scroll(col(*lines, pad=[16, 10, 16, 10]), id='live:chat:%s' % _key_arg(key), bottom=True, fill=1),
                    bg=PANEL2), h=CHAT_H)
    write = row(box(edit(tab_id(TAB, 'chat_draft'), st['draft'], _('Write to the others (200 characters)'), fill=1),
                    bg=PANEL2, p=[12, 8, 12, 8], r=2, ol=LINE2, fill=1),
                sp(12), primary(tab_id(TAB, 'chat_send', _key_arg(key)), _('SEND  ›') if not st['sending'] else _('SENDING…'),
                                va='c'),
                pad=[0, 10, 0, 0])
    note = txt(st['note'], 15, 'medium', BAD, wrap=True, pad=[0, 6, 0, 0]) if st['note'] else None
    return col(head, area, write, note)


def signup_part(ig, key, v):
    a = ig.app
    if v.get('publishing'):
        words = _('Drawing the rally and the start list…')
    else:
        words = _('The stages, the weather and the start list come out at %s. Car 1 starts at %s.') % (
            liverally.hm(v.get('starts') or key[1]), liverally.hm(v.get('firstStart') or key[1]))
    withdraw = quiet(tab_id(TAB, 'withdraw', _key_arg(key)), _('WITHDRAW'), va='c') \
        if (v.get('me') or {}).get('signedUp') and v.get('phase') == 'signup' else None
    ents = v.get('entrants') or []
    sid = a.s.get('steamId')
    out = [row(txt(words, 17, 'medium', SOFT, wrap=True, fill=1, va='c'), withdraw, pad=[0, 14, 0, 8]),
           kicker(n_('%d DRIVER REGISTERED', '%d DRIVERS REGISTERED', len(ents)) % len(ents), pad=[0, 8, 0, 6])]
    if not ents:
        out.append(txt(_('Nobody yet.'), 16, 'medium', MUTED))
        return col(*out)
    out.append(box(row(head_cell(_('#'), 60, j=2), sp(16), head_cell(_('DRIVER'), None), head_cell(_('RATING'), 140, j=2),
                       head_cell(_('WORLD RANK'), 180, j=2), sp(24), head_cell(_('CAR'), 340)),
                   bg=PANEL2, p=[10, 6, 10, 6]))
    for i, e in enumerate(ents[:SHOWN_ROWS]):
        mine = bool(sid) and e.get('steamId') == sid
        fg = WHITE if mine else SOFT
        out.append(box(row(cell(str(i + 1), 60, fg=WHITE if mine else MUTED, f='bold', j=2), sp(16),
                           size(driver(e, fg, bold=mine), fill=1),
                           cell(str(e['rating']) if e.get('rating') is not None else '–', 140, fg=fg, j=2),
                           cell('#%d' % e['rank'] if e.get('rank') else _('not rated'), 180,
                                fg=fg if e.get('rank') else MUTED, j=2),
                           sp(24), cell(e.get('car') or '', 340, sz=16, fg=FG2), va='c'),
                       bg=line_bg(i, mine), p=[10, 6, 10, 6]))
    return col(*out)


def _in_menus(a):
    try:
        return bool(a._pulse().in_menus())
    except Exception:
        return False


def _following(a, v):
    """The app follows this session's event (a stage of it next)."""
    run = getattr(a, 'league_run', None)
    ev = v.get('event') or {}
    return bool(run and not run.get('over') and run['ev'].get('id') == ev.get('id') and a.drive_target == 'league')


def rally_part(ig, key, v, me, now):
    """From the hour: the stages, my place as it stands (with DRIVE when the rally is out and the app not on it yet),
    each stage's queue (SS1's: the start list)."""
    a = ig.app
    m = _mem(ig)
    ev = v['event']
    widths = (90, 520, 160, 280, 280)
    out = [row(*[head_cell(h, w) for h, w in zip((_('SS'), _('STAGE'), _('LENGTH'), _('WEATHER'), _('TIME OF DAY')),
                                                  widths)], pad=[0, 14, 0, 4])]
    for s in ev.get('stages') or []:
        vals = ('SS%d' % s['no'], s.get('name') or '', '%.1f km' % ((s.get('lengthM') or 0) / 1000),
                s.get('weatherLabel') or s.get('weather') or '', s.get('time') or '')
        out.append(row(*[cell(t, w, fg=WHITE if i == 1 else SOFT) for i, (t, w) in enumerate(zip(vals, widths))],
                       pad=[0, 3, 0, 0]))
    out.append(txt((ev.get('carClass') or '') + '  ·  ' + _('service park before SS1 only: the damage carries'), 15,
                   'medium', MUTED, pad=[0, 6, 0, 0]))
    st = a._lr_bar_state() if me.get('signedUp') else None
    if st and st['key'] == key:                         # my place in it: as the window's bar says, with its button
        tone = {'good': GOOD, 'bad': BAD, 'slow': SLOW}.get(st['tone'], WHITE)
        words = i18n.cap((st.get('words') or '').split('  ·  ', 1)[-1])
        act = None
        if st['button'] and st['button'][1] == 'drive':
            act = primary(tab_id(TAB, 'drive', _key_arg(key)), st['button'][0] + '  ›', va='c', pad=[20, 0, 0, 0])
        elif st['button'] and st['button'][1] == 'withdraw':
            act = quiet(tab_id(TAB, 'withdraw', _key_arg(key)), st['button'][0], va='c', pad=[20, 0, 0, 0])
        elif not st['button'] and _in_menus(a) and _following(a, v):
            # back in the game's menu between stages: CONTINUE takes the game back to the next one (drive.lua)
            act = primary(tab_id(TAB, 'drive', _key_arg(key)), _('CONTINUE  ›'), va='c', pad=[20, 0, 0, 0])
        out.append(box(row(chip(st['chip'], fg=BG if st['tone'] in ('good', 'slow') else WHITE,
                                bg=tone if st['tone'] != 'soft' else LIVE, va='c'),
                           txt(words, 22, 'bold', LIVE, va='c', fill=1, pad=[14, 0, 0, 0]),
                           kicker(st.get('label'), va='c', pad=[0, 0, 10, 0]) if st.get('label') else None,
                           txt(st.get('time'), 30, 'bold', tone, va='c') if st.get('time') else None,
                           act),
                       bg=PANEL2, p=[16, 10, 16, 10], pad=[0, 14, 0, 4]))
    n = len(ev.get('stages') or [])
    q_no = m['q']
    if q_no is None:                                    # (as it goes: my next stage's queue, else the one under way)
        s2 = liverally.my_start(v, now)
        busy = [k for k, q in enumerate(v.get('queues') or []) if any(x.get('state') in liverally.QUEUED for x in q)]
        q_no = s2['no'] if s2 else busy[0] if busy else 0
    q_no = min(q_no, max(0, n - 1))
    out.append(tabs(tab_id(TAB, 'queue'), [(k, _('START LIST') if k == 0 else _('SS%d QUEUE') % (k + 1)) for k in range(n)],
                    q_no, pad=[0, 18, 0, 8]))
    sid = a.s.get('steamId')
    rows = liverally.queue_rows(v, q_no, sid)
    people = (v.get('queues') or [])[q_no] if q_no < len(v.get('queues') or []) else []
    out.append(box(row(head_cell(_('START'), 170), head_cell(_('DRIVER'), None), head_cell(_('CAR'), 320),
                       head_cell(_('STATE'), 380)), bg=PANEL2, p=[10, 6, 10, 6]))
    if not rows:
        out.append(txt(_('Nobody yet: drivers join this queue %d minutes after they finish the stage before.') % round(
            liverally.rules_of(v)['breakS'] / 60) if q_no else _('Nobody yet.'), 16, 'medium', MUTED, pad=[10, 8, 0, 0]))
    for i, ((at, _nm, car, what, colour, mine), q) in enumerate(zip(rows[:SHOWN_ROWS], people)):
        fg = WHITE if mine else SOFT
        out.append(box(row(cell(at, 170, fg=fg), size(driver(q, fg, bold=mine), fill=1), cell(car, 320, sz=16, fg=FG2),
                           cell(what, 380, sz=16, f='bold' if mine else 'semi', fg=TONE.get(colour, SOFT)), va='c'),
                       bg=line_bg(i, mine), p=[10, 6, 10, 6]))
    return col(*out)


# ---- RESULTS
def results_list(ig, info):
    a = ig.app
    m = _mem(ig)
    every = info.get('recent') or []
    rows = [s for s in every if s.get('mine')] if m['mine'] else every
    n_mine = sum(1 for s in every if s.get('mine'))
    filt = tabs(tab_id(TAB, 'filter'), [('all', '%s  %d' % (_('ALL RESULTS'), len(every))),
                                        ('mine', '%s  %d' % (_('MY RESULTS'), n_mine))],
                'mine' if m['mine'] else 'all', pad=[0, 12, 0, 12])
    out = [txt(_('Every ranked rally of the last week. Open one for its full report: each stage, the podium and '
                 'every driver\'s times.'), 17, 'medium', FG2, wrap=True), filt]
    if not rows:
        out.append(box(txt(_('You have not driven a ranked rally in the last week. Yours show here once they are over.')
                           if m['mine'] and every else _('No results yet. A session\'s results show here once it is over.'),
                           18, 'medium', SOFT, wrap=True), bg=PANEL, p=[22, 18, 22, 18]))
        return col(*out)
    out.append(box(row(head_cell(_('WHEN'), 200), head_cell(_('SERIES'), 320), head_cell(_('COUNTRY'), 200),
                       head_cell(_('DRIVERS'), 120, j=2), sp(30), head_cell(_('WINNER'), None), head_cell(_('YOU'), 180),
                       sp(200)), bg=PANEL2, p=[12, 6, 12, 6]))
    for i, s in enumerate(rows[:RESULTS_ROWS]):
        key = (s['series'], s['starts'])
        mine = bool(s.get('mine'))
        when = liverally.day_hm(s['starts'])
        w = s.get('winner')
        win = row(driver(w, WHITE, sz=17), txt(liverally.fmt_time(w.get('totalMs')), 16, 'semi', FG2, va='c',
                                                 pad=[12, 0, 0, 0])) if w else txt(_('nobody finished'), 16, 'medium', MUTED)
        me = s.get('me')
        if me and me.get('rank'):
            you, fg = _('P%d of %d') % (me['rank'], s.get('drivers') or 0), LIVE
        elif me:
            you, fg = {'dnf': _('DNF'), 'dsq': _('DSQ')}.get(me.get('status'), '–'), BAD
        else:
            you, fg = '–', MUTED
        series = row(logo(s['series'], 64, 36) and size(logo(s['series'], 64, 36), pad=[0, 0, 10, 0]),
                     txt(a._lr_series_name(s['series']), 17, 'semi', SOFT, va='c'))
        out.append(box(row(cell(('✓ ' if mine else '') + when, 200, f='bold', fg=GOOD if mine else WHITE),
                           size(series, w=320), cell(s.get('rally') or '', 200),
                           cell(str(s.get('drivers') or 0), 120, j=2), sp(30), size(win, fill=1),
                           cell(you, 180, f='bold', fg=fg),
                           size(row(sp(fill=1), quiet(tab_id(TAB, 'report', _key_arg(key)), _('RESULTS  ›'))), w=200),
                           va='c'),
                       bg=line_bg(i, mine), p=[12, 6, 12, 6]))
    return col(*out)


# ---- a session's report
def report(ig, key):
    a = ig.app
    m = _mem(ig)
    v = a.lr_data.get(key) or {}
    back = link(tab_id(TAB, 'back'), '‹  ' + (_('RESULTS') if m['tab'] == 'results' else _('SERIES')), pad=[0, 0, 0, 10])
    ev = v.get('event') or {}
    stages = ev.get('stages') or []
    when = i18n.strftime(_('%a %d %b %H:%M'), time.localtime(key[1] / 1000))
    n = len(v.get('standings') or [])
    bits = [when, ev.get('carClass') or '', n_('%d driver', '%d drivers', n) % n if n else '']
    final = v.get('resultsOut')
    band = box(col(size(box(None, bg=LIVE), h=4),
                   row(logo(key[0], 224, 126) and size(logo(key[0], 224, 126), pad=[0, 0, 24, 0], va='c'),
                       col(txt('%s  ·  %s' % (a._lr_series_name(key[0]).upper(), (v.get('rally') or '').upper()), 38,
                               'bold', WHITE),
                           txt('   ·   '.join(b for b in bits if b), 17, 'medium', FG2, pad=[0, 2, 0, 0]), va='c', fill=1),
                       hairline_chip(_('FINAL') if final else _('PROVISIONAL · STILL RUNNING'), GOOD if final else SLOW),
                       pad=[24, 18, 24, 18])),
               bg=PANEL)
    out = [back, band]
    if not v:
        out.append(txt(a.lr_msg or _('Loading the results…'), 18, 'medium', SOFT, pad=[0, 14, 0, 0]))
        return col(*out)
    if stages:                                          # the stages, each with its fastest
        fast = liverally.stage_winners(v)
        cards = []
        for k, s in enumerate(stages):
            f = fast[k] if k < len(fast) else None
            cards.append(box(col(kicker('SS%d' % s['no']),
                                 txt(s.get('name') or '', 24, 'bold', WHITE, wrap=True),
                                 txt('   ·   '.join(x for x in ('%.1f km' % ((s.get('lengthM') or 0) / 1000),
                                                              s.get('weatherLabel') or s.get('weather') or '',
                                                              s.get('time') or '') if x), 15, 'medium', FG2,
                                     pad=[0, 2, 0, 8]),
                                 row(kicker(_('FASTEST'), va='c', pad=[0, 0, 10, 0]),
                                     txt(liverally.fmt_time(f[2]) if f else '–', 22, 'bold', WHITE if f else MUTED)),
                                 driver({'name': f[0], 'country': f[1]}, SOFT, sz=16) if f else None),
                             bg=PANEL, p=[18, 14, 18, 16], fill=1, pad=[0 if k == 0 else 10, 0, 0, 0]))
        out += [heading(_('STAGES')), row(*cards)]
    sid = a.s.get('steamId')
    rows = liverally.results_rows(v, sid)
    top = [x for x in rows if x['pos'] in ('1', '2', '3')][:3]
    if top:                                             # the podium
        cards = []
        for k, x in enumerate(top):
            medal = MEDAL[x['pos']]
            cards.append(box(col(size(box(None, bg=medal), h=4),
                                 row(txt('P' + x['pos'], 44, 'bold', medal, va='c', pad=[0, 0, 18, 0]),
                                     col(driver(x, WHITE, bold=True, sz=20),
                                         txt(x['total'] + ('   ' + x['gap'] if x['gap'] else ''), 20, 'semi', SOFT,
                                             pad=[0, 4, 0, 0]),
                                         txt(x['car'], 15, 'medium', FG2), va='c', fill=1),
                                     pad=[18, 14, 18, 16])),
                             bg=PANEL2 if x['mine'] else PANEL, fill=1, pad=[0 if k == 0 else 10, 0, 0, 0]))
        out += [heading(_('PODIUM')), row(*cards)]
    mine = liverally.my_result(v, sid)
    if mine:
        out.append(box(row(size(box(None, bg=LIVE), w=5),
                           kicker(_('YOUR RESULT'), va='c', pad=[20, 0, 24, 0]),
                           txt(mine[0], 38, 'bold', WHITE, va='c'),
                           txt(local(mine[1]), 26, 'semi', SOFT, va='c', pad=[24, 0, 0, 0])),
                       bg=PANEL2, pad=[0, 18, 0, 0], p=[0, 12, 20, 12]))
    out.append(heading(_('CLASSIFICATION')))
    k = len(stages) or 3
    car = k <= 4                                         # (many stages: no car column; it is on the podium)
    SS_W = 230
    out.append(box(row(head_cell(_('POS'), 80, j=2), sp(20), head_cell(_('DRIVER'), None),
                       head_cell(_('CAR'), 260) if car else None,
                       *[head_cell('SS%d' % (i + 1), SS_W) for i in range(k)],
                       head_cell(_('TOTAL'), 170), head_cell(_('GAP'), 150)), bg=PANEL2, p=[10, 6, 10, 6]))
    if not rows:
        out.append(txt(_('No times yet.'), 16, 'medium', MUTED, pad=[10, 8, 0, 0]))
    for i, x in enumerate(rows):
        bad = x['state'] in ('dnf', 'dsq')
        fg = WHITE if x['mine'] else SOFT
        cells = []
        for j in range(k):
            t, note, jump = x['stages'][j] if j < len(x['stages']) else ('', '', False)
            cells.append(size(row(txt(t, 17, 'semi', SOFT if t != '–' else MUTED, va='c'),
                                  txt(note, 13, 'medium', SLOW if jump else MUTED, va='c', pad=[6, 0, 0, 0]) if note else None),
                              w=SS_W))
        line = row(cell(x['pos'], 80, sz=19, f='bold', fg=LIVE if x['mine'] else WHITE, j=2), sp(20),
                   size(driver(x, fg, bold=x['mine']), fill=1),
                   cell(x['car'], 260, sz=15, f='medium', fg=FG2) if car else None,
                   *cells,
                   cell(x['total'], 170, sz=18, f='bold' if x['mine'] else 'semi', fg=BAD if bad else WHITE),
                   cell(x['gap'], 150, sz=16, fg=FG2), va='c')
        why = txt(local(x['reason']), 14, 'medium', MUTED, pad=[100, 2, 0, 0]) if bad and x['reason'] else None
        out.append(box(col(line, why), bg=line_bg(i, x['mine']), p=[10, 6, 10, 6]))
    out.append(txt(_('Stage times include the jump starts\' seconds. Ranked rallies are not rated yet.'), 15, 'medium',
                   MUTED, pad=[0, 10, 0, 10]))
    return col(*out)


# ---------------------------------------------------------------------- the buttons
def click(ig, action, arg):
    a = ig.app
    a._lr_ready()
    m = _mem(ig)
    if action == 'page':                    # SERIES / RESULTS
        m['tab'], m['report'] = (arg if arg in ('series', 'results') else 'series'), None
    elif action == 'filter':                # RESULTS: ALL / MINE
        m['mine'] = arg == 'mine'
    elif action == 'report':
        key = _key_of(arg)
        if key:
            m['report'] = key
            a._lr_poll(key)
    elif action == 'back':
        m['report'] = None
    elif action == 'queue':                 # my session: the START LIST / SSn QUEUE shown
        try:
            m['q'] = int(arg)
        except (TypeError, ValueError):
            m['q'] = None
    elif action == 'cars':                  # the cars to pick from, shown / put away
        m['cars'] = None if m['cars'] == arg else arg
    elif action == 'car':
        series, _sep, k = (arg or '').partition('|')
        s = a._lr_series(series) or {}
        cars = [c['name'] for c in s.get('cars') or []]
        if k.isdigit() and int(k) < len(cars):
            a.lr_pick_car(series, cars[int(k)])
        m['cars'] = None
    elif action in ('register', 'withdraw'):
        key = _key_of(arg)
        if key:
            m['cars'] = None
            a.lr_signup(key, withdraw=action == 'withdraw')
    elif action == 'drive':
        key = _key_of(arg)
        if key:
            a.lr_drive(key)
    elif action == 'chat_onoff':            # the session's chat shown / put away (rankedchat.py)
        from . import rankedchat
        rankedchat.toggle(a)
    elif action == 'chat_send':
        key = _key_of(arg)
        if key:
            from . import rankedchat
            rankedchat.send(a, rankedchat.state(m, key), key)


def text(ig, field, words):
    """Words typed in the page: the chat's draft (kept per session: the one on screen is mine)."""
    if field == 'chat_draft':
        key = ig.app._lr_registered()
        if key:
            from . import rankedchat
            rankedchat.state(_mem(ig), key)['draft'] = words
