"""COMPETITIONS in the game (ingamekit.py says how a page is made): the window's three parts as sub-tabs, a list on the
left and the one picked in full on the right.

RALLIES: my championships' rounds and anyone's rallies, then the championships to join (browserui.py's list, ALL /
CHAMPIONSHIPS / RALLIES); an event picked: its photo, car (a class: its cars to pick), where I am in it, its stages, its
standings (GET /api/events/<id>) and DRIVE (app.league_drive; a private rally: its code, app.rally_code). A
championship picked: JOIN, ASK TO JOIN, TAKE IT BACK; one I run: the requests (ACCEPT / DECLINE) and ADD A DRIVER.
1V1: my matches (DRIVE), the challenges (ACCEPT / DECLINE / CANCEL / REMATCH: tabsui.py) and CHALLENGE A DRIVER, the
window's form (challengeui.py) as a page. CUPS: every cup open or under way (cupbrowser.py: ALL / OPEN / UNDER WAY /
MINE); one picked: what it races, JOIN / LEAVE, and my match in it to DRIVE.

The app's questions during a click are asked in the game by ig. What the app does later, once the server has answered
(a hidden event's set-up, the routes of its stages), is done here under ig.run, so that its questions are asked in the
game too."""
import threading
import time

from . import gear, i18n, photos, settings, tmtext
from .browserui import CHAMP, FILTERS as RALLY_FILTERS, kind_of
from .challengeui import MAX_STAGES, TIMES, WINDOWS, challenge_event, random_stages
from .cupbrowser import FILTERS as CUP_FILTERS, OFFICIAL, can_join, cups_of
from .i18n import _, n_
from .ingamekit import (BAD, BG, COLOUR, FG2, FOCUS, GOOD, LINE2, MUTED, PANEL, PANEL2, SOFT, WHITE, box, btn, chip, col,
                        edit, empty, fmt_ms, img, kicker, line_row, link, picture, primary, quiet, row, scroll, size,
                        sp, stack, tab_id, tabs, txt)
from .leagueui import EMPTY, _left, event_figures, hidden_text, hidden_what, listed_order, tab_of
from .tabsui import COMP, challenge_text, result_text
from . import leagues

CHAMP, OFFICIAL = CHAMP.lstrip('#'), OFFICIAL.lstrip('#')    # (the window's colours, as the game takes them)

TAB = 'comp'
LW, GAP, RW = 700, 36, 1080          # the list on the left, the one picked on the right (PAGE_W 1840, less the
                                     # page's scroll bar: 1100 cut the card's right edge in the game)
PHOTO_H = 260
LISTED = 200                         # rows in a list at most (the rest: the website)
SHOWN = 40                           # challenges in each part (the list scrolls)
BOARD_ROWS = 12
EVERY_S = 300                        # the lists fetched again while the page is on screen (the window's 5 min)
BOARD_EVERY_S = 120                  # an event's standings fetched again
AFTER_MS = (2500, 7000)              # a 1V1's or a cup's answer: their lists fetched again (the window's do it itself)


# ---------------------------------------------------------------------- the page's own state
def _mem(ig):
    m = ig.mem(TAB)
    m.setdefault('sub', 'league')
    m.setdefault('filter', 'all')
    m.setdefault('cfilter', 'all')
    m.setdefault('boards', {})       # event id -> {'at', 'rows', 'n', 'msg'}
    m.setdefault('busy', set())
    return m


def _said(a):
    """The app's status line (its window's sub_l): what an action said once it was done."""
    try:
        return a.sub_l.cget('text') or ''
    except Exception:
        return ''


def _later(a, fn):
    """fn on the Tk thread."""
    a.root.after(0, fn)


def _thread(fn):
    threading.Thread(target=fn, daemon=True).start()


def waiting_note(s):
    try:
        from . import waiting
        waiting.note(s)
    except Exception:
        pass


def _now():
    return time.time() * 1000


def cut(s, n):
    s = s or ''
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


# ---------------------------------------------------------------------- data
def opened(ig):
    refresh(ig)


def refresh(ig):
    a = ig.app
    m = _mem(ig)
    m['at'] = time.monotonic()
    m['said0'] = _said(a)
    for b in m['boards'].values():          # (out of date: fetched again, the old rows shown meanwhile, no "Loading…")
        b['at'] = 0
    try:
        a.refresh_leagues()
    except Exception:
        pass
    for kind in ('h2h', 'cup'):
        fetch_extras(ig, kind)


def fetch_extras(ig, kind):
    """The challenges (1V1) or the cups, as the window's refresh_tab_extras (which fetches only with its own tab on
    screen), into the app's h2h_data / cups_data (app._set_tab_extras)."""
    a = ig.app
    if not a.api.configured or not a.s.get('token'):
        return

    def go():
        try:
            r = a.api.h2h() if kind == 'h2h' else a.api.cups()
            _later(a, lambda: a._set_tab_extras(kind, r, ''))
        except Exception as e:
            msg = (_('1V1s: %s') if kind == 'h2h' else _('Cups: %s')) % e
            _later(a, lambda: a._set_tab_extras(kind, None, msg))
    _thread(go)


def fetch_board(ig, eid):
    """An event's standings (GET /api/events/<id>), into the page's state."""
    a = ig.app
    m = _mem(ig)
    if eid in m['busy'] or not a.api.configured:
        return
    m['busy'].add(eid)

    def done(entry):
        m['busy'].discard(eid)
        old = m['boards'].get(eid)
        if entry.get('rows') is None and old and old.get('rows') is not None:
            entry = old                              # (a failed look again: the rows it had stay)
        m['boards'][eid] = dict(entry, at=time.monotonic())

    def go():
        try:
            r = a.api.event(eid) or {}
            entry = {'rows': r.get('standings') or [], 'n': len(r.get('stages') or ()), 'msg': ''}
        except Exception as e:
            waiting_note('standings of %s: %r' % (eid, e))
            entry = {'rows': None, 'n': 0, 'msg': _("Couldn't load. It tries again in a moment.")}
        _later(a, lambda: done(entry))
    _thread(go)


def _again_soon(ig, kind):
    a = ig.app
    for ms in AFTER_MS:
        a.root.after(ms, lambda: fetch_extras(ig, kind))


# ---------------------------------------------------------------------- the page
def page(ig):
    a = ig.app
    m = _mem(ig)
    if ig.shown and time.monotonic() - m.get('at', 0) > EVERY_S:
        refresh(ig)
    sub = m['sub'] if m['sub'] in dict(COMP) else 'league'
    items = [(k, label + ('  %d' % n if n else '')) for (k, label), n in zip(COMP, _counts(a))]
    # (what the app says, its status line: under the pages' header for every tab, ingameapp.status)
    head = row(tabs(tab_id(TAB, 'sub'), items, sub, va='c'), sp(fill=1))
    if not a.s.get('token'):
        body = col(empty(_('Sign in with Steam in the ACR Daily window first.'), pad=[0, 0, 0, 16]),
                   quiet('window', _('OPEN THE WINDOW')), al='l')
    elif sub == 'h2h':
        body = h2h_part(ig, m)
    elif sub == 'cup':
        body = cup_part(ig, m)
    else:
        body = rally_part(ig, m)
    if not body.get('cols'):                   # (a form, a sign-in note: one scroll for it all)
        body = scroll(body, id='comp:body:%s' % sub, fill=1)
    body.pop('cols', None)
    return col(head, body, sp(h=20), fill=1)


OWN_SCROLL = True                              # (ingameapp.page: this page's lists scroll on their own)


def _counts(a):
    """Something to do in each part: rallies in progress or to drive, challenges to answer, cup matches open."""
    evs = [e for e in a.league_events or () if e.get('status') == 'open' and
           (e.get('entry') or {}).get('status') in (None, 'running') and not e.get('locked')]
    by = {k: sum(tab_of(e) == k for e in evs) for k, _l in COMP}
    by['h2h'] += len((a.h2h_data or {}).get('incoming') or ())
    return [by[k] for k, _l in COMP]


def columns(left, right, key=''):
    """The list on the left, the one picked on the right: each scrolls on its own (the user, 21 Nov 2026), the right one
    from its top again for another pick (key)."""
    return row(size(scroll(left, id='comp:list:%s' % key.split('/')[0]), w=LW),
               sp(GAP),
               size(scroll(right, id='comp:pick:%s' % key) if right else sp(), w=RW),
               pad=[0, 18, 0, 0], fill=1, cols=True)


def list_row(id_, colour, title, sub, on, sub_fg=MUTED, right=None):
    """A line of a list (the window's server browser): a bar in its kind's colour, its name, a line under it."""
    inner = row(size(box(None, bg=colour), w=5, h=48, va='c'), sp(14),
                col(txt(cut(title, 46), 19, 'bold', WHITE), txt(cut(sub, 78), 15, 'medium', sub_fg, pad=[0, 2, 0, 0]),
                    fill=1, va='c'),
                right)
    return btn(id_, c=inner, bg=PANEL2 if on else PANEL, hov=PANEL2, foc=FOCUS, p=[12, 10, 16, 10],
               ol=LINE2 if on else None, pad=[0, 6, 0, 0], al='f')


def label_box(s):
    """A button's place with nothing to do (FINISHED, OPENS IN 2 H): its words in a hairline."""
    return box(txt(s, 18, 'bold', FG2, sp=60), bg='-', ol=LINE2, p=[24, 10, 24, 10], r=2)


def filter_row(prefix, filters, counts, on):
    return tabs(tab_id(TAB, prefix), [(k, '%s  %d' % (_(label), counts[k])) for k, label in filters], on)


def _photo(key, w, h, fallback):
    """A picture cut for the game: the app's photo or a banner fetched already; else the part's own photo."""
    for k in (key, fallback):
        try:
            p = picture(k, w, h) if k else None
        except Exception:                 # (a banner ingamekit can't cut: the part's photo)
            p = None
        if p:
            return p
    return None


# ---------------------------------------------------------------------- an event (a championship's round, a rally,
# a 1V1's or a cup's match)
def _events(a, kind):
    evs = [e for e in a.league_events or () if tab_of(e) == kind and
           (e.get('status') != 'closed' or (e.get('entry') or {}).get('status') == 'running')]
    return sorted(evs, key=listed_order)


def _status(a, ev, now):
    st = (ev.get('entry') or {}).get('status')
    try:
        text = a._status_line(ev, now)[0]
    except Exception:
        text = ''
    return text, GOOD if st == 'running' else WHITE if st == 'finished' else BAD if st in ('dnf', 'dsq') else FG2


def event_row(ig, ev, on, now):
    a = ig.app
    st = (ev.get('entry') or {}).get('status')
    colour = COLOUR.get(ev.get('kind') or 'league') or COLOUR['league']
    try:
        state = a._browse_state(ev, now)
    except Exception:
        state = ''
    what = a._event_of(ev)
    sub = ' · '.join(x for x in (what, i18n.data(ev.get('rally') or ''), state) if x)
    return list_row(tab_id(TAB, 'pick', 'e:%s' % ev['id']), colour, ev.get('name') or '', sub, on,
                    sub_fg=GOOD if st == 'running' else MUTED)


def _in_menus(a):
    """The game in its menus (the mod says no stage is loaded): CONTINUE can take the player back to a rally."""
    try:
        return bool(a._pulse().in_menus())
    except Exception:
        return False


def event_action(ig, ev, now):
    """The event's button, as its card's in the window (leagueui._event_card)."""
    a = ig.app
    entry = ev.get('entry') or {}
    status = entry.get('status')
    run = a.league_run
    following = bool(run and run['ev']['id'] == ev['id'] and a.drive_target == 'league')
    if ev.get('status') == 'upcoming':
        return label_box(_('OPENS IN %s') % _left((ev.get('opens') or 0) - now).upper())
    if status == 'finished':
        return label_box(_('FINISHED'))
    if status in ('dnf', 'dsq'):
        return label_box(_('DNF') if status == 'dnf' else _('DSQ'))
    if ev.get('status') == 'closed':
        return label_box(_('CLOSED'))
    if ev.get('locked'):
        return primary(tab_id(TAB, 'code', ev['id']), _('ENTER CODE  ›'))
    # (a run that didn't count only because the game wasn't taken there by ACR DAILY: CONTINUE does it)
    missed = following and bool(run.get('missed')) and not (run.get('missed_kind') == 'here' and status == 'running')
    if following and not missed and not _in_menus(a):     # (on a stage: the app follows it; in the game's menus:
        return label_box(_('FOLLOWING'))                   # CONTINUE takes the player back to it, drive.lua)
    return primary(tab_id(TAB, 'drive', ev['id']),
                   _('DRIVE AGAIN  ›') if missed else _('CONTINUE  ›') if status == 'running' else _('DRIVE  ›'))


def event_detail(ig, ev, w, now, photo=True):
    a = ig.app
    entry = ev.get('entry') or {}
    status = entry.get('status')
    colour = COLOUR.get(ev.get('kind') or 'league') or COLOUR['league']
    stages = ev.get('stages') or []
    km = sum(s.get('lengthM') or 0 for s in stages) / 1000
    legs = leagues.legs(ev) if stages and all('day' in s for s in stages) else []
    tags = [_('HIDDEN') if ev.get('lengthM') is None else '%.1f KM' % km,
            n_('%d DAY', '%d DAYS', ev.get('days') or 0) % (ev.get('days') or 0)]
    if len(legs) > 1:
        tags.append(n_('%d LEG', '%d LEGS', len(legs)) % len(legs))
    head = None
    if photo:
        try:
            pic = a._event_photo(ev)
        except Exception:
            pic = {}
        key = pic.get('banner') or pic.get('photo')
        part = {'h2h': 'h2h', 'cup': 'cups'}.get(ev.get('kind'), 'leagues')
        top = col(row(chip('%d SS' % len(stages), bg=colour, fg=BG), sp(10),
                      txt(i18n.data(ev.get('rally') or '').upper(), 16, 'bold', WHITE, sp=80, va='c', sh=True)),
                  sp(h=1, fill=1),
                  txt((ev.get('name') or '').upper(), 30, 'bold', WHITE, sh=True, wrap=True),
                  txt(' · '.join(tags), 16, 'semi', SOFT, sp=60, sh=True),
                  pad=[22, 18, 22, 16], al='f', va='f')
        head = stack(img(_photo(key, w, PHOTO_H, part), w, PHOTO_H), top)
    text, fg = _status(a, ev, now)
    hint = hidden_text(ev)
    if ev.get('locked'):
        hint = _('Private: enter its code to drive it. Ask its maker for it.')
    if len(legs) > 1 and not hint and status != 'running':
        hint = _('In the game: %d legs (%s), each set up by CONTINUE when the one before is done.') % (
            len(legs), ', '.join('SS%d-SS%d' % (x + 1, y) if y - x > 1 else 'SS%d' % y for x, y in legs))
    if status == 'running':
        try:
            hint = a._held_hint(ev)
        except Exception:
            pass
        if hint and 'RESUME' in hint:          # (in the game: CONTINUE does the game's RESUME itself; by hand doesn't count)
            hint = _('CONTINUE takes you straight to SS%d.') % ((entry.get('done') or 0) + 1)
    kick = [kicker(a._event_of(ev), fg=colour)]
    if status == 'running':
        kick += [sp(14), kicker(_('●  IN PROGRESS'), fg=GOOD)]
    figures = row(*[col(txt(v, 34, 'bold', WHITE), kicker(k), pad=[0 if i == 0 else 30, 0, 0, 0])
                    for i, (v, k) in enumerate(event_figures(ev, now))], va='c')
    info = col(row(*kick),
               txt(ev.get('car') or entry.get('car') or ev.get('carClass') or '', 22, 'semi', WHITE, pad=[0, 6, 0, 0]),
               txt(text, 18, 'semi', fg, pad=[0, 4, 0, 0]),
               txt(hint, 16, 'medium', MUTED, wrap=True, pad=[0, 4, 0, 0]) if hint else None,
               car_picker(ig, ev),
               gear_picker(ig, ev),
               row(event_action(ig, ev, now), sp(fill=1), figures, pad=[0, 16, 0, 0]),
               pad=[22, 16, 22, 18])
    if not photo:                     # (a cup's match under the cup: its name over it)
        info['c'].insert(1, txt(ev.get('name') or '', 24, 'bold', WHITE, wrap=True, pad=[0, 4, 0, 0]))
    return col(head, box(info, bg=PANEL), box(stage_list(ev), bg=PANEL2, p=[22, 16, 22, 16]),
               box(standings(ig, ev), bg=PANEL2, p=[22, 16, 22, 18], pad=[0, 2, 0, 0]))


def car_picker(ig, ev):
    """A class: its cars to pick before the start (the window's drop-down), the one picked white."""
    a = ig.app
    if ev.get('car') or (ev.get('entry') or {}).get('status') or ev.get('locked') or not ev.get('cars'):
        return None
    cur = (a._league_car(ev) or {}).get('name')
    lines, line = [], []
    for i, c in enumerate(ev['cars']):
        on = c['name'] == cur
        line.append(btn(tab_id(TAB, 'car', '%s:%d' % (ev['id'], i)), c['name'], bg=WHITE if on else PANEL2,
                        hov=WHITE, fg=BG if on else SOFT, hfg=BG, sz=16, f='semi', p=[12, 5, 12, 5], r=2,
                        pad=[0 if not line else 6, 0, 0, 0]))
        if len(line) == 4:
            lines.append(row(*line, pad=[0, 6, 0, 0]))
            line = []
    if line:
        lines.append(row(*line, pad=[0, 6, 0, 0]))
    title = cur or _('Pick your %s car') % (ev.get('carClass') or '')
    return col(kicker(title, fg=WHITE if cur else SOFT), *lines, pad=[0, 12, 0, 0])


def _gear_car(a, ev):
    """The car an event will be driven in: its own, my entry's, or the one picked; None before a pick."""
    entry = ev.get('entry') or {}
    car = (leagues.car_of(ev, entry.get('car')) if entry.get('car') else None) or a._league_car(ev)
    return car


def gear_picker(ig, ev):
    """TYRES and LIVERY for an event not started yet (gear.py): the counts of each compound its rally takes, adding up
    to the rally's tyres (AUTO: the game's own), and the car's livery (GAME'S PICK: whatever the garage has)."""
    a = ig.app
    if (ev.get('entry') or {}).get('status') or ev.get('locked') or ev.get('status') not in (None, 'open'):
        return None
    car = _gear_car(a, ev)
    out = []
    rows = gear.compounds(ev) if ev.get('kind') != 'live' else ()
    if len(rows) > 1:                         # (one compound, Sweden's snow: nothing to pick)
        mine = gear.tyres_of(a.s, ev)
        counts = mine or gear.start_counts(ev)
        cells = []
        for i, r in enumerate(rows):
            n = counts.get(r, 0)
            cells.append(row(txt(gear.NAMES.get(r, r), 16, 'semi', SOFT, va='c'), sp(8),
                             quiet(tab_id(TAB, 'tyre', '%s:%s:-1' % (ev['id'], r)), '‹', p=[10, 2, 10, 2], va='c'),
                             size(txt('%d' % n, 18, 'bold', WHITE if mine else MUTED, j=1, va='c'), w=34),
                             quiet(tab_id(TAB, 'tyre', '%s:%s:1' % (ev['id'], r)), '›', p=[10, 2, 10, 2], va='c'),
                             pad=[0 if i == 0 else 22, 0, 0, 0]))
        auto = btn(tab_id(TAB, 'tyreauto', ev['id']), _('AUTO'), bg=WHITE if not mine else '-', hov=WHITE, foc=FOCUS,
                   fg=BG if not mine else SOFT, hfg=BG, sz=15, f='bold', p=[12, 3, 12, 3], r=2, ol=None if not mine else LINE2)
        out += [row(kicker(_('Tyres · %d') % gear.TYRES, fg=WHITE if mine else SOFT, va='c'), sp(14), auto,
                    pad=[0, 14, 0, 0]),
                row(*cells, pad=[0, 6, 0, 0])]
    if car:
        picked = gear.livery_of(a.s, car['id'])
        opts = [('', _("GAME'S PICK"))] + gear.choices(car['id'])
        line = []
        for i, (name, words) in enumerate(opts):
            on = (name or None) == picked
            line.append(btn(tab_id(TAB, 'livery', '%s:%d' % (ev['id'], i)), words.upper() if i == 0 else words,
                            bg=WHITE if on else PANEL2, hov=WHITE, foc=FOCUS, fg=BG if on else SOFT, hfg=BG, sz=16,
                            f='semi', p=[12, 5, 12, 5], r=2, pad=[0 if i == 0 else 6, 0, 0, 0]))
        out += [kicker(_('Livery · %s') % car['name'], fg=WHITE if picked else SOFT, pad=[0, 14, 0, 0]),
                row(*line[:5], pad=[0, 6, 0, 0])]
        if len(line) > 5:
            out.append(row(*[dict(x, pad=[0 if j == 0 else 6, 0, 0, 0]) for j, x in enumerate(line[5:10])],
                           pad=[0, 6, 0, 0]))
    return col(*out) if out else None


def gear_click(a, action, arg):
    parts = arg.split(':')
    ev = a._league_event(_int(parts[0]))
    if not ev:
        return
    if action == 'tyre' and len(parts) == 3:
        gear.step_tyres(a.s, ev, parts[1], 1 if parts[2] == '1' else -1)
    elif action == 'tyreauto':
        gear.auto_tyres(a.s, ev)
    elif action == 'livery' and len(parts) == 2:
        car = _gear_car(a, ev)
        if not car:
            return
        opts = [''] + [n for n, _w in gear.choices(car['id'])]
        try:
            name = opts[int(parts[1])]
        except (ValueError, IndexError):
            return
        if name:
            gear.pick_livery(a.s, car['id'], name)
        else:
            (a.s.get('carLivery') or {}).pop(car['id'], None)
            settings.save(a.s)


def stage_list(ev):
    stages = ev.get('stages') or []
    out = [kicker(_('Stages'))]
    if not stages:
        out.append(txt(_('HIDDEN'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    for k, s in enumerate(stages):
        km = '%.1f km' % (s['lengthM'] / 1000) if s.get('lengthM') else ''
        when = ' · '.join(x for x in (i18n.data(s.get('weatherLabel') or ''), s.get('time') or '') if x)
        out.append(row(txt('SS%d' % (s.get('no') or k + 1), 17, 'bold', MUTED), sp(16),
                       txt(cut(s.get('name') or s.get('track') or _('HIDDEN'), 52), 17, 'semi', WHITE, fill=1),
                       txt(when, 16, 'medium', FG2, j=2), sp(18), txt(km, 16, 'medium', FG2, j=2),
                       pad=[0, 6, 0, 0]))
    return col(*out)


def standings(ig, ev):
    """The event's standings as its page on the website has them: finished by total, then running, DNF, DSQ; mine
    pinned under the top ones."""
    m = _mem(ig)
    title = _('Standings')
    if ev.get('locked'):
        return col(kicker(title), txt(_('Private: enter its code to drive it. Ask its maker for it.'), 17, 'medium',
                                      MUTED, pad=[0, 8, 0, 0]))
    b = m['boards'].get(ev['id'])
    if b is None or time.monotonic() - b.get('at', 0) > BOARD_EVERY_S:
        fetch_board(ig, ev['id'])
    if b is None:
        return col(kicker(title), txt(_('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    rows = b.get('rows')
    if rows is None:
        return col(kicker(title), txt(b.get('msg') or '', 17, 'medium', BAD, pad=[0, 8, 0, 0]))
    if not rows:
        return col(kicker(title), txt(_('No times yet. Be the first.'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    me = ig.app.s.get('steamId')
    n = b.get('n') or len(ev.get('stages') or ())
    out = [row(kicker(title), sp(fill=1), kicker(n_('%d driver', '%d drivers', len(rows)) % len(rows)),
               pad=[0, 0, 0, 6])]
    # (every row, each one the wheel's arrows can step to: the event's panel scrolls with them; no gap to the leader)
    for r in rows:
        is_me = r.get('steamId') == me
        st = r.get('status')
        total = fmt_ms(r['totalMs']) if r.get('totalMs') is not None else '–'
        state = (_('DNF') if st == 'dnf' else _('DSQ') if st == 'dsq' else
                 'SS%d/%d' % (r.get('done') or 0, n) if st == 'running' else '')
        fg = WHITE if is_me else SOFT
        line = row(size(txt(r.get('rank') or '–', 17, 'bold', MUTED, j=2), w=40),
                   sp(14),
                   txt(cut(tmtext.tagged(r), 32), 17, 'bold' if is_me else 'semi', fg, fill=1),
                   txt(cut(r.get('car') or '', 28), 15, 'medium', MUTED, j=2), sp(18),
                   txt(state, 15, 'bold', BAD if st in ('dnf', 'dsq') else GOOD if st == 'running' else MUTED, j=2),
                   sp(12), size(txt(total, 17, 'semi', fg, j=2), w=110))
        out.append(line_row(line, is_me, fid='st:%s:%d' % (ev['id'], len(out))))
    return col(*out)


# ---------------------------------------------------------------------- RALLIES
def rally_part(ig, m):
    a = ig.app
    now = _now()
    evs = _events(a, 'league')
    champs = list(a.champ_rows or ())
    every = list(evs) + [dict(x, _champ=True) for x in champs]
    counts = {'all': len(every), 'league': sum(kind_of(e) == 'league' for e in every),
              'event': sum(kind_of(e) == 'event' for e in every)}
    shown = [e for e in every if m['filter'] == 'all' or kind_of(e) == m['filter']]
    pick = m.get('pick_league')
    ids = [('c', str(x['id'])) if x.get('_champ') else ('e', x['id']) for x in shown]
    if pick not in ids:
        pick = m['pick_league'] = ids[0] if ids else None
    lines = []
    asking = [x for x in champs if x.get('_requests')]         # (championships I run: drivers asking to join)
    for x in asking[:3]:
        k = len(x['_requests'])
        lines.append(link(tab_id(TAB, 'pick', 'c:%s' % x['id']),
                          n_('%d request to join %s  ›', '%d requests to join %s  ›', k) % (k, x.get('name') or ''),
                          fg=GOOD, pad=[0, 6, 0, 0]))
    for x, key in list(zip(shown, ids))[:LISTED]:
        if key[0] == 'c':
            lines.append(list_row(tab_id(TAB, 'pick', 'c:%s' % x['id']), CHAMP, x.get('name') or '',
                                  ' · '.join([_('Official championship') if x.get('official') else
                                              _('Championship by %s') % (x.get('owner') or '?'), a._champ_state(x)]),
                                  key == pick, sub_fg=CHAMP))
        else:
            lines.append(event_row(ig, x, key == pick, now))
    if not shown:
        lines.append(empty(a.league_msg or EMPTY['league'][1], pad=[0, 12, 0, 0]))
    left = col(filter_row('filter', RALLY_FILTERS, counts, m['filter']), sp(h=6), *lines)
    if pick is None:
        right = None
    elif pick[0] == 'c':
        right = champ_detail(ig, m, _champ(a, pick[1]))
    else:
        ev = a._league_event(pick[1])
        right = event_detail(ig, ev, RW, now) if ev else None
    return columns(left, right, 'league/%s' % ('-'.join(map(str, pick)) if pick else ''))


def champ_detail(ig, m, x):
    """A championship to join (or ask to), or one I run (its requests, ADD A DRIVER): leagueui._champ_card."""
    a = ig.app
    if not x:
        return None
    rounds = x.get('events') or 0
    state = x.get('_state') or 'join'
    sub = [_('Official championship') if x.get('official') else _('Championship by %s') % (x.get('owner') or '?'),
           n_('%d driver', '%d drivers', x.get('members') or 0) % (x.get('members') or 0),
           n_('%d round', '%d rounds', rounds) % rounds, a._champ_state(x)]
    about = ' '.join((x.get('about') or '').split())
    if len(about) > 400:
        about = about[:397].rstrip() + '…'

    def day(ms):
        return i18n.strftime(_('%a %d %b'), time.localtime((ms or 0) / 1000))
    note = {'ask': _('Private: the admins accept drivers.'),
            'asked': _('You asked to join on %s. The admins answer in your inbox.') % day(x.get('_asked')),
            'declined': _('Your request was declined. You can ask again from %s.') % day(x.get('_again'))}.get(state)
    try:
        banner = a.banner_key(x.get('banner'), lambda: None)
    except Exception:
        banner = None
    top = col(row(chip(_('CHAMPIONSHIP'), bg=CHAMP, fg=BG)), sp(h=1, fill=1),
              txt((x.get('name') or '').upper(), 30, 'bold', WHITE, sh=True, wrap=True),
              pad=[22, 18, 22, 16], al='f', va='f')
    head = stack(img(_photo(banner, RW, 200, 'leagues'), RW, 200), top)
    act = {'join': (_('JOIN  ›'), 'join'), 'ask': (_('ASK TO JOIN  ›'), 'ask'),
           'asked': (_('TAKE IT BACK'), 'withdraw')}.get(state)
    button = None
    if act:
        button = (primary if state != 'asked' else quiet)(tab_id(TAB, act[1], x['id']), act[0])
    info = col(txt('   ·   '.join(s for s in sub if s), 17, 'semi', SOFT, wrap=True),
               txt(about, 16, 'medium', MUTED, wrap=True, pad=[0, 8, 0, 0]) if about else None,
               txt(note, 16, 'medium', FG2, wrap=True, pad=[0, 8, 0, 0]) if note else None,
               row(button, pad=[0, 16, 0, 0]) if button else None,
               pad=[22, 16, 22, 18])
    parts = [head, box(info, bg=PANEL)]
    if state == 'run':
        parts.append(box(run_part(ig, m, x), bg=PANEL2, p=[22, 16, 22, 18]))
    return col(*parts)


def run_part(ig, m, x):
    """A championship I run: the drivers asking to join (ACCEPT / DECLINE), and ADD A DRIVER found by name."""
    out = []
    reqs = x.get('_requests') or ()
    if reqs:
        k = len(reqs)
        out.append(kicker(n_('%d request to join', '%d requests to join', k) % k))
    for r in reqs:
        sid = r.get('steamId')
        out.append(row(col(txt(r.get('name') or _('Driver'), 19, 'bold', WHITE),
                           txt('“%s”' % r['message'], 16, 'medium', SOFT, wrap=True) if r.get('message') else None,
                           fill=1, va='c'),
                       quiet(tab_id(TAB, 'answer', '%s:%s:0' % (x['id'], sid)), _('DECLINE'), va='c'), sp(8),
                       primary(tab_id(TAB, 'answer', '%s:%s:1' % (x['id'], sid)), _('ACCEPT'), va='c'),
                       pad=[0, 8, 0, 0]))
    add = m.get('add') or {}
    if add.get('cid') != x['id']:
        add = {}
    out.append(kicker(_('ADD A DRIVER  ›').rstrip(' ›'), pad=[0, 16 if reqs else 0, 0, 0]))
    out.append(row(size(box(edit(tab_id(TAB, 'addq'), add.get('q') or '', '', fill=1),
                            bg=PANEL, p=[12, 8, 12, 8], r=2, ol=LINE2), w=420),
                   sp(10), quiet(tab_id(TAB, 'addfind', x['id']), _('FIND'), va='c'), pad=[0, 8, 0, 0]))
    if add.get('msg'):
        out.append(txt(add['msg'], 16, 'medium', MUTED, pad=[0, 6, 0, 0]))
    for i, p in enumerate((add.get('found') or [])[:8]):
        out.append(row(txt(tmtext.tagged(p), 18, 'semi', WHITE, fill=1, va='c'),
                       quiet(tab_id(TAB, 'addp', i), _('ADD'), va='c'), pad=[0, 6, 0, 0]))
    return col(*out)


# ---------------------------------------------------------------------- 1V1
def _h2h(a):
    r = a.h2h_data or {}
    return r.get('incoming') or [], r.get('outgoing') or [], r.get('past') or []


def challenge_line(id_pairs, text, sub, colour=WHITE):
    buttons = []
    for b in id_pairs:
        buttons += [sp(8), b]
    return box(row(col(txt(cut(text, 60), 18, 'bold', colour), txt(cut(sub, 80), 15, 'medium', MUTED, pad=[0, 2, 0, 0]),
                       fill=1, va='c'), *buttons),
               bg=PANEL, p=[14, 10, 14, 10], ol=LINE2, pad=[0, 6, 0, 0])


def h2h_part(ig, m):
    a = ig.app
    now = _now()
    evs = _events(a, 'h2h')
    pick = m.get('pick_h2h')
    if pick != 'form' and pick not in [e['id'] for e in evs]:
        pick = m['pick_h2h'] = evs[0]['id'] if evs else None
    left = [kicker('1V1')]
    for ev in evs[:LISTED]:
        left.append(event_row(ig, ev, ev['id'] == pick, now))
    if not evs:
        left.append(empty(a.league_msg or EMPTY['h2h'][1], pad=[0, 8, 0, 0]))
    left.append(row(kicker(_('Challenges')), sp(fill=1),
                    link(tab_id(TAB, 'form'), _('CHALLENGE A DRIVER  ›'), fg=COLOUR['h2h']), pad=[0, 26, 0, 0]))
    if a.h2h_data is None:
        left.append(txt(a.tab_msg or _('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    else:
        incoming, outgoing, past = _h2h(a)
        me = a.s.get('steamId')
        if not (incoming or outgoing or past):
            left.append(empty(_('No challenges yet: challenge a driver (above), or wait for one.'), pad=[0, 8, 0, 0]))
        for h in incoming[:SHOWN]:
            left.append(challenge_line([quiet(tab_id(TAB, 'decline', h['id']), _('DECLINE'), va='c'),
                                        primary(tab_id(TAB, 'accept', h['id']), _('ACCEPT'), va='c')],
                                       challenge_text(h, 'opponent'),
                                       _('Challenges you · answer within %s') % _left((h.get('answerBy') or 0) - now),
                                       COLOUR['h2h']))
        for h in outgoing[:SHOWN]:
            left.append(challenge_line([quiet(tab_id(TAB, 'cancel', h['id']), _('CANCEL'), va='c')],
                                       challenge_text(h, 'challenger'), _('Waiting for their answer')))
        for h in past[:SHOWN // 2]:
            left.append(challenge_line([quiet(tab_id(TAB, 'rematch', h['id']), _('REMATCH'), va='c')]
                                       if h.get('status') == 'settled' else [],
                                       result_text(h, me), h.get('name') or '', SOFT))
    if pick == 'form':
        right = form_page(ig, m)
    else:
        ev = a._league_event(pick) if pick is not None else None
        right = event_detail(ig, ev, RW, now) if ev else None
    return columns(col(*left), right, 'h2h/%s' % pick)


# ---- CHALLENGE A DRIVER (challengeui.ChallengeDialog as a page)
def _form(ig):
    m = _mem(ig)
    f = m.get('form')
    if f is None:
        f = m['form'] = {'cat': None, 'msg': '', 'q': '', 'found': [], 'opp': None, 'rally': 0, 'picked': [],
                         'mode': 'class', 'car': None, 'weather': None, 'start': '12:00', 'win': 1, 'stake': '0',
                         'hide': True, 'name': '', 'busy': False}
    return f


def open_form(ig):
    a = ig.app
    m = _mem(ig)
    m['pick_h2h'] = 'form'
    f = _form(ig)
    if f['cat'] is not None or f['busy']:
        return
    f['busy'], f['msg'] = True, ''

    def go():
        try:
            cat = a.api.catalog() or {}
            msg = ''
        except Exception as e:
            cat, msg = None, _('Not loaded: %s') % e

        def put():
            f['busy'], f['cat'], f['msg'] = False, cat, msg
        _later(a, put)
    _thread(go)


def _rallies(f):
    return [r for r in (f['cat'] or {}).get('rallies') or [] if r.get('stages')]


def _car_values(f):
    """(values, labels) of the car picker: the classes or the cars (challengeui._cars)."""
    cat = f['cat'] or {}
    if f['mode'] == 'car':
        cars = cat.get('cars') or []
        return [x['name'] for x in cars], ['%s · %s' % (x['name'], x.get('cls') or '') for x in cars]
    cls = cat.get('classes') or []
    return [k['cls'] for k in cls], ['%s (%s)' % (k['cls'], k.get('group') or '') for k in cls]


def _car_index(f):
    values, _labels = _car_values(f)
    if not values:
        return -1
    if f['car'] is None or not 0 <= f['car'] < len(values):
        f['car'] = values.index('Rally2/R5') if 'Rally2/R5' in values else 0
    return f['car']


def _weather_index(f):
    ws = (f['cat'] or {}).get('weathers') or []
    if f['weather'] is None or not 0 <= f['weather'] < len(ws):
        ids = [x['id'] for x in ws]
        f['weather'] = ids.index('Clear') if 'Clear' in ids else 0
    return f['weather']


def cycler(field, label, w=300):
    return row(quiet(tab_id(TAB, 'f', '%s:-1' % field), '‹', p=[14, 8, 14, 8], va='c'),
               size(box(txt(label, 18, 'semi', WHITE, j=1), bg=PANEL2, p=[10, 9, 10, 9], al='f'), w=w, va='c'),
               quiet(tab_id(TAB, 'f', '%s:1' % field), '›', p=[14, 8, 14, 8], va='c'))


def field_box(id_, s, hint, w):
    return size(box(edit(id_, s, hint, fill=1), bg=PANEL2, p=[12, 8, 12, 8], r=2, ol=LINE2), w=w)


def toggle(id_, s, on):
    return btn(id_, s, bg=WHITE if on else PANEL2, hov=WHITE, fg=BG if on else SOFT, hfg=BG, sz=16, f='semi',
               p=[14, 6, 14, 6], r=2)


def form_page(ig, m):
    a = ig.app
    f = _form(ig)
    out = [txt(_('CHALLENGE A DRIVER'), 30, 'bold', COLOUR['h2h']),
           txt(_('Lower total wins the stakes.'), 16, 'medium', MUTED, pad=[0, 2, 0, 0])]
    if f['cat'] is None:
        out.append(txt(f['msg'] or _('Loading the stages…'), 18, 'medium', BAD if f['msg'] else MUTED,
                       pad=[0, 14, 0, 0]))
        out.append(row(quiet(tab_id(TAB, 'f', 'close'), _('CANCEL')), pad=[0, 16, 0, 0]))
        return box(col(*out), bg=PANEL, p=[24, 20, 24, 22])

    def part(s, **o):
        return kicker(s, pad=o.pop('pad', [0, 18, 0, 6]))
    # who
    out.append(part(_('Who')))
    if f['opp']:
        out.append(row(txt(tmtext.tagged(f['opp']), 22, 'bold', WHITE, va='c'), sp(14),
                       link(tab_id(TAB, 'f', 'change'), _('CHANGE'), va='c')))
    else:
        out.append(row(field_box(tab_id(TAB, 'who'), f['q'], '', 420), sp(10),
                       quiet(tab_id(TAB, 'f', 'find'), _('FIND'), va='c')))
        for i, p in enumerate(f['found'][:6]):
            out.append(link(tab_id(TAB, 'f', 'opp:%d' % i), '%s%s' % (
                tmtext.tagged(p), ('  (%s)' % p['country'].upper()) if p.get('country') else ''), fg=SOFT,
                pad=[0, 6, 0, 0]))
    # where, which stages
    rallies = _rallies(f)
    r = rallies[f['rally'] % len(rallies)] if rallies else None
    out.append(part(_('Where')))
    out.append(cycler('rally', i18n.data(r['name']) if r else '–', 420))
    out.append(row(part(_('Stages (1 to %d)') % MAX_STAGES, pad=[0, 18, 0, 0]), sp(fill=1),
                   link(tab_id(TAB, 'f', 'draw'), _('DRAW 2'), va='b'), pad=[0, 0, 0, 6]))
    for i, s in enumerate((r or {}).get('stages') or []):
        on = i in f['picked']
        out.append(btn(tab_id(TAB, 'f', 'stage:%d' % i), '%s · %.1f km' % (s['name'], (s.get('lengthM') or 0) / 1000),
                       bg=WHITE if on else PANEL2, hov=WHITE, fg=BG if on else SOFT, hfg=BG, sz=17, f='semi',
                       p=[14, 6, 14, 6], cal='l', al='f', pad=[0, 4, 0, 0]))
    # the car
    out.append(part(_('Car')))
    _values, labels = _car_values(f)
    k = _car_index(f)
    out.append(row(toggle(tab_id(TAB, 'f', 'mode:class'), _('A class (each picks a car of it)'), f['mode'] == 'class'),
                   sp(8), toggle(tab_id(TAB, 'f', 'mode:car'), _('One car'), f['mode'] == 'car')))
    out.append(row(cycler('car', labels[k] if k >= 0 else '–', 520), pad=[0, 8, 0, 0]))
    # the conditions, the window, the stake
    out.append(part(_('Weather · SS1 starts at · open for')))
    ws = (f['cat'] or {}).get('weathers') or []
    wi = _weather_index(f)
    out.append(row(cycler('weather', i18n.data(ws[wi]['label']) if ws else '–', 220), sp(14),
                   cycler('start', f['start'], 110), sp(14), cycler('win', WINDOWS[f['win']][1], 140)))
    cr = a.credits or {}
    if cr.get('enabled'):
        out.append(part(_('Stake each, in credits (0: a friendly)')))
        out.append(row(field_box(tab_id(TAB, 'stake'), f['stake'], '0', 160), sp(14),
                       txt(_('You have %d.') % (cr.get('balance') or 0), 17, 'medium', MUTED, va='c')))
    out.append(row(toggle(tab_id(TAB, 'f', 'hide'), _('Keep the stages, weather and times hidden until it ends'),
                          f['hide']), pad=[0, 18, 0, 0]))
    out.append(part(_('Name (optional)')))
    out.append(field_box(tab_id(TAB, 'cname'), f['name'], '', 520))
    out.append(row(primary(tab_id(TAB, 'f', 'send'), _('SEND THE CHALLENGE')), sp(fill=1),
                   link(tab_id(TAB, 'f', 'close'), _('CANCEL'), va='c'), pad=[0, 22, 0, 0]))
    if f['msg']:
        out.append(txt(f['msg'], 17, 'medium', BAD, wrap=True, pad=[0, 10, 0, 0]))
    return box(col(*out), bg=PANEL, p=[24, 20, 24, 22])


def form_click(ig, what):
    a = ig.app
    f = _form(ig)
    m = _mem(ig)
    key, _sep, arg = (what or '').partition(':')
    rallies = _rallies(f)
    if key == 'close':
        m['pick_h2h'] = None
        m['form'] = None
    elif key == 'change':
        f['opp'], f['found'] = None, []
    elif key == 'find':
        find_driver(ig, f['q'])
    elif key == 'opp':
        try:
            f['opp'] = f['found'][int(arg)]
        except (ValueError, IndexError):
            pass
    elif key in ('rally', 'car', 'weather', 'start', 'win'):
        step = -1 if arg == '-1' else 1
        if key == 'rally' and rallies:
            f['rally'], f['picked'] = (f['rally'] + step) % len(rallies), []
        elif key == 'car':
            values, _l = _car_values(f)
            if values:
                f['car'] = (_car_index(f) + step) % len(values)
        elif key == 'weather':
            ws = (f['cat'] or {}).get('weathers') or []
            if ws:
                f['weather'] = (_weather_index(f) + step) % len(ws)
        elif key == 'start':
            i = TIMES.index(f['start']) if f['start'] in TIMES else 2
            f['start'] = TIMES[(i + step) % len(TIMES)]
        else:
            f['win'] = (f['win'] + step) % len(WINDOWS)
    elif key == 'stage':
        i = int(arg)
        f['picked'] = [x for x in f['picked'] if x != i] if i in f['picked'] else f['picked'] + [i]
    elif key == 'draw' and rallies:
        r = rallies[f['rally'] % len(rallies)]
        f['picked'] = [r['stages'].index(s) for s in random_stages(r['stages'], 2)]
    elif key == 'mode' and arg in ('class', 'car'):
        f['mode'], f['car'] = arg, None
    elif key == 'hide':
        f['hide'] = not f['hide']
    elif key == 'send':
        send_challenge(ig)


def find_driver(ig, q):
    a = ig.app
    f = _form(ig)
    q = (q or '').strip()
    if len(q) < 2:
        f['msg'] = _('Type 2 letters of their name at least.')
        return
    me = a.s.get('steamId')

    def go():
        try:
            found = [p for p in a.api.players(q) if p.get('steamId') != me]
            msg = '' if found else _('Nobody by that name.')
        except Exception as e:
            found, msg = [], _('Not found: %s') % e

        def put():
            f['found'], f['msg'] = found, msg
        _later(a, put)
    _thread(go)


def challenge_of(f, now_ms=None):
    """The event from the form, or a str: what is missing (challengeui.ChallengeDialog.event)."""
    rallies = _rallies(f)
    if not rallies:
        return _('Pick where.')
    r = rallies[f['rally'] % len(rallies)]
    picked = [r['stages'][i] for i in sorted(f['picked']) if 0 <= i < len(r['stages'])]
    if not picked:
        return _('Pick a stage (or draw some at random).')
    if len(picked) > MAX_STAGES:
        return _('Up to %d stages.') % MAX_STAGES
    values, _l = _car_values(f)
    k = _car_index(f)
    if k < 0:
        return _('Pick the car.')
    ws = (f['cat'] or {}).get('weathers') or []
    weather = ws[_weather_index(f)]['id'] if ws else 'Clear'
    return challenge_event(r['name'], picked, weather, f['start'] or '12:00', WINDOWS[f['win']][0],
                           now_ms if now_ms is not None else _now(),
                           car=values[k] if f['mode'] == 'car' else None,
                           car_class=values[k] if f['mode'] == 'class' else None, name=f['name'], hide=f['hide'])


def send_challenge(ig):
    a = ig.app
    f = _form(ig)
    if not f['opp']:
        f['msg'] = _('Find who you challenge first.')
        return
    ev = challenge_of(f)
    if isinstance(ev, str):
        f['msg'] = ev
        return
    try:
        stake = int((f['stake'] or '0').strip() or 0) if (a.credits or {}).get('enabled') else 0
        if stake < 0:
            raise ValueError
    except ValueError:
        f['msg'] = _('The stake: a whole number of credits, 0 for a friendly.')
        return
    f['msg'] = ''
    n = len(ev['stages'])
    ask = n_('Challenge %s: %s, %d stage, open %s?', 'Challenge %s: %s, %d stages, open %s?', n) % (
        f['opp']['name'], i18n.data(ev['rally']), n, WINDOWS[f['win']][1])
    more = (_('%d credits each.') % stake) if stake else _('A friendly: no credits.')
    opp = f['opp']

    def go():
        def sent():
            ig.say(_('CHALLENGE A DRIVER'), [_('Challenge sent to %s: they have a day to answer.') % opp['name']])
            _mem(ig)['form'] = None
            _mem(ig)['pick_h2h'] = None
            fetch_extras(ig, 'h2h')
            try:
                a.refresh_credits()
            except Exception:
                pass

        def failed(e):
            f['msg'] = _('Not sent: %s') % e

        def call():
            try:
                a.api.h2h_challenge(opp['steamId'], stake, ev)
                _later(a, sent)
            except Exception as e:
                why = str(e)                   # (e is gone once the except is left)
                _later(a, lambda: failed(why))
        _thread(call)
    ig.ask(_('CHALLENGE A DRIVER'), [ask, more], _('SEND THE CHALLENGE'), go)


# ---------------------------------------------------------------------- CUPS
def cup_part(ig, m):
    a = ig.app
    now = _now()
    cups, mine = cups_of(a.cups_data)
    groups = {'all': cups, 'open': [x for x in cups if x.get('status') == 'open'],
              'running': [x for x in cups if x.get('status') != 'open'], 'mine': [x for x in cups if x['id'] in mine]}
    shown = groups.get(m['cfilter']) or []
    pick = m.get('pick_cup')
    if pick not in [x['id'] for x in shown]:
        # (one of mine with a match to drive first, as the window's)
        withmatch = [x for x in shown if x['id'] in mine and a._cup_match(x['id'])]
        pick = m['pick_cup'] = (withmatch or shown)[0]['id'] if shown else None
    left = [filter_row('cfilter', CUP_FILTERS, {k: len(v) for k, v in groups.items()}, m['cfilter']), sp(h=6)]
    if a.cups_data is None:
        left.append(txt(a.tab_msg or _('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    for x in shown[:LISTED]:
        state, me_word = _cup_state(a, x, mine)
        sub = ' · '.join(y for y in (i18n.data(x.get('rally') or ''), '%d / %d' % (x.get('entrants') or 0,
                                                                                    x.get('size') or 0),
                                     (_('%d credits') % x['fee']) if x.get('fee') else _('free'), state, me_word) if y)
        left.append(list_row(tab_id(TAB, 'pick', 'u:%s' % x['id']), OFFICIAL if x.get('official') else COLOUR['cup'],
                             a._cup_title(x), sub, x['id'] == pick, sub_fg=GOOD if x['id'] in mine else MUTED))
    if a.cups_data is not None and not shown:
        left.append(empty(_('No cups open right now.'), pad=[0, 12, 0, 0]))
    x = next((y for y in shown if y['id'] == pick), None)
    return columns(col(*left), cup_detail(ig, x, mine, now) if x else None, 'cup/%s' % pick)


def _cup_state(a, x, mine):
    """(when it starts or that it is under way, where I am in it): cupbrowser._cup_values's."""
    if x.get('status') == 'open':
        state = _('Starts %s') % i18n.strftime(_('%a %d %b %H:%M'), time.localtime((x.get('starts') or 0) / 1000))
    else:
        state = _('Under way')
    if x['id'] in mine:
        me = _('Match open') if a._cup_match(x['id']) else _('Joined') if x.get('status') == 'open' else _('In it')
    else:
        me = _('Full') if x.get('status') == 'open' and not can_join(x, mine) else ''
    return state, me


def cup_detail(ig, x, mine, now):
    a = ig.app
    colour = OFFICIAL if x.get('official') else COLOUR['cup']
    try:
        banner = a.banner_key(x.get('banner'), lambda: None)
    except Exception:
        banner = None
    rally = (x.get('rallies') or [None])[0] or x.get('rally')
    official = bool(x.get('official'))
    top = col(row(chip(_('OFFICIAL') if official else _('CUP'), bg=colour, fg=WHITE if official else BG),
                  sp(10), txt(i18n.data(x.get('rally') or '').upper(), 16, 'bold', WHITE, sp=80, va='c', sh=True)),
              sp(h=1, fill=1),
              txt((x.get('name') or '').upper(), 30, 'bold', WHITE, sh=True, wrap=True),
              pad=[22, 18, 22, 16], al='f', va='f')
    head = stack(img(_photo(banner or photos.for_rally(rally), RW, PHOTO_H, 'cups'), RW, PHOTO_H), top)
    state, me_word = _cup_state(a, x, mine)
    figs = [('%d / %d' % (x.get('entrants') or 0, x.get('size') or 0), _('DRIVERS')),
            (str(x['fee']) if x.get('fee') else _('free'), _('ENTRY')),
            (str(x.get('pot') or x.get('prize') or 0), _('PRIZE'))]
    figures = row(*[col(txt(v, 34, 'bold', WHITE), kicker(k), pad=[0 if i == 0 else 30, 0, 0, 0])
                    for i, (v, k) in enumerate(figs)], va='c')
    if can_join(x, mine):
        button = primary(tab_id(TAB, 'cjoin', x['id']), _('JOIN'))
    elif x.get('status') == 'open' and x['id'] in mine:
        button = quiet(tab_id(TAB, 'cleave', x['id']), _('LEAVE'))
    else:
        button = label_box(me_word.upper() or state.upper())
    about = ' '.join((x.get('about') or '').split())
    if len(about) > 400:
        about = about[:397].rstrip() + '…'
    info = col(kicker(' · '.join(y for y in (state, me_word) if y), fg=GOOD if x['id'] in mine else FG2),
               txt(x.get('car') or x.get('carClass') or '', 22, 'semi', WHITE, pad=[0, 6, 0, 0]),
               txt(about, 16, 'medium', MUTED, wrap=True, pad=[0, 6, 0, 0]) if about else None,
               row(button, sp(fill=1), figures, pad=[0, 16, 0, 0]),
               pad=[22, 16, 22, 18])
    stages = [kicker(_('Stages'))]
    for k, s in enumerate(x.get('stages') or []):
        when = ' · '.join(y for y in (i18n.data(s.get('weather') or ''), s.get('time') or '') if y)
        stages.append(row(txt('SS%d' % (k + 1), 17, 'bold', MUTED), sp(16),
                          txt(cut(s.get('name') or '?', 52), 17, 'semi', WHITE, fill=1),
                          txt(when, 16, 'medium', FG2, j=2), pad=[0, 6, 0, 0]))
    parts = [head, box(info, bg=PANEL), box(col(*stages), bg=PANEL2, p=[22, 16, 22, 16])]
    match = a._cup_match(x['id']) if x['id'] in mine else None
    if match:
        parts.append(col(kicker(_('MATCH'), fg=colour, pad=[0, 22, 0, 8]),
                         event_detail(ig, match, RW, now, photo=False)))
    return col(*parts)


# ---------------------------------------------------------------------- what's clicked, what's typed
def _find_h2h(a, hid):
    for h in [x for part in _h2h(a) for x in part]:
        if str(h.get('id')) == str(hid):
            return h
    return None


def _find_cup(a, cid):
    cups, _mine = cups_of(a.cups_data)
    return next((x for x in cups if str(x['id']) == str(cid)), None)


def _champ(a, cid):
    """A championship of the list by its id as a button carries it (words)."""
    return next((x for x in a.champ_rows or () if str(x.get('id')) == str(cid)), None)


def _cid(a, s):
    """The championship's id as the app has it (a button's are words)."""
    x = _champ(a, s)
    return x['id'] if x else s


def _int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return s


def click(ig, action, arg):
    a = ig.app
    m = _mem(ig)
    m['said0'] = _said(a)                      # (what the app says from now on shows over the page)
    if action == 'sub':
        if arg in dict(COMP):
            m['sub'] = arg
            if arg in ('h2h', 'cup'):
                fetch_extras(ig, arg)
    elif action == 'filter':
        m['filter'] = arg or 'all'
    elif action == 'cfilter':
        m['cfilter'] = arg or 'all'
    elif action == 'pick' and arg:
        kind, _sep, key = arg.partition(':')
        if kind == 'c':
            m['pick_league'] = ('c', key)
        elif kind == 'e':
            eid = _int(key)
            ev = a._league_event(eid)
            if ev is not None:
                m['pick_' + tab_of(ev)] = ('e', eid) if tab_of(ev) == 'league' else eid
                m['boards'].pop(eid, None)
        elif kind == 'u':
            m['pick_cup'] = next((x['id'] for x in cups_of(a.cups_data)[0] if str(x['id']) == key), key)
    elif action == 'drive':
        drive(ig, _int(arg))
    elif action == 'code':
        a.rally_code(_int(arg))
    elif action == 'car' and arg:
        eid, _sep, i = arg.rpartition(':')
        ev = a._league_event(_int(eid))
        try:
            a._pick_car(ev, ev['cars'][int(i)]['name'])
        except (TypeError, KeyError, IndexError, ValueError):
            pass
    elif action in ('tyre', 'tyreauto', 'livery') and arg:
        gear_click(a, action, arg)
    elif action == 'join':
        a.champ_join(_cid(a, arg))
    elif action == 'ask':
        a.champ_ask(_cid(a, arg))
    elif action == 'withdraw':
        a.champ_withdraw(_cid(a, arg))
    elif action == 'answer' and arg:
        cid, sid, yes = arg.rsplit(':', 2)
        x = _champ(a, cid) or {}
        req = next((r for r in x.get('_requests') or () if str(r.get('steamId')) == sid), None)
        if req is not None:
            a.champ_answer(x['id'], req, yes == '1')
    elif action == 'addfind':
        add = m.get('add') or {}
        cid = _cid(a, arg)
        add_find(ig, cid, add.get('q') if add.get('cid') == cid else '')
    elif action == 'addp':
        add_driver(ig, _int(arg))
    elif action in ('accept', 'decline', 'cancel', 'rematch'):
        h = _find_h2h(a, arg)
        if h is not None:
            if action == 'rematch':
                a.rematch(h)
            else:
                a.answer_challenge(h, action)
            _again_soon(ig, 'h2h')
    elif action == 'form':
        open_form(ig)
    elif action == 'f':
        form_click(ig, arg)
    elif action in ('cjoin', 'cleave'):
        x = _find_cup(a, arg)
        if x is not None:
            a.cup_entry(x, 'join' if action == 'cjoin' else 'leave')
            _again_soon(ig, 'cup')


def text(ig, field, words):
    m = _mem(ig)
    words = words or ''
    if field == 'who':
        f = _form(ig)
        f['q'] = words
        if len(words.strip()) >= 2:
            find_driver(ig, words)
    elif field == 'stake':
        _form(ig)['stake'] = words.strip()
    elif field == 'cname':
        _form(ig)['name'] = words[:80]
    elif field == 'addq':
        pick = m.get('pick_league') or ('', '')
        cid = _cid(ig.app, pick[1]) if pick[0] == 'c' else (m.get('add') or {}).get('cid')
        if cid is not None:
            add_find(ig, cid, words)


# ---- DRIVE: the window's (app.league_drive), with what it fetches first done here (its questions in the game then)
def drive(ig, eid):
    a = ig.app
    ev = a._league_event(eid)
    if not ev:
        return
    entry = ev.get('entry') or {}
    car = (leagues.car_of(ev, entry.get('car')) if entry.get('car') else None) or a._league_car(ev)
    if ev.get('locked') or not car:            # (its code asked for; or "pick your car first": the app's own)
        a.league_drive(eid)
        return
    if ev.get('hidden') and not ev.get('revealed'):
        reveal(ig, ev)
        return
    if not a._fill_routes(ev):                 # (fetched, then DRIVE again: its question asked in the game)
        a._league_routes(ev, lambda: ig.run(lambda: drive(ig, eid)))
        return
    a.league_drive(eid)


def reveal(ig, ev):
    """A hidden event: the app's question, then its set-up from the server (app._league_reveal / _league_revealed),
    then DRIVE."""
    a = ig.app
    eid = ev['id']
    ask = _('%s keeps its %s hidden until it ends.\n\nDRIVE gets them now and sets the '
            'rally up: from then on you know them, so start it as soon as you can.\n\nGo?') % (
        ev['name'], hidden_what(ev['hidden']))

    def got(full):
        e = a._league_event(eid)
        if not e:
            return
        for k in ('stages', 'lengthM', 'hidden', 'revealed', 'cars', 'days'):
            if k in full:
                e[k] = full[k]
        e['revealed'] = True
        _mem(ig)['boards'].pop(eid, None)
        ig.run(lambda: drive(ig, eid))

    def go():
        def call():
            try:
                full = a.api.reveal(eid) or {}
                _later(a, lambda: got(full))
            except Exception as e:
                said = _('Could not get the stages of %s (%s). Try again.') % (ev['name'], e)
                _later(a, lambda: ig.say(ev['name'], [said]))
        _thread(call)
    ig.ask(ev['name'], ask.split('\n\n'), _('DRIVE'), go)


# ---- ADD A DRIVER (app.champ_add asks its last question once the server has answered: done here)
def add_find(ig, cid, q):
    a = ig.app
    m = _mem(ig)
    q = (q or '').strip()
    add = m['add'] = {'cid': cid, 'q': q, 'found': [], 'msg': ''}
    if len(q) < 2:
        add['msg'] = _('Type 2 letters of their name at least.')
        return

    def go():
        try:
            ps = a.api.players(q) or []
            same = [p for p in ps if (p.get('name') or '').casefold() == q.casefold()]
            found = same or ps
            msg = '' if ps else _('No driver of that name.')
        except Exception as e:
            found, msg = [], str(e)

        def put():
            if m.get('add') is add:
                add['found'], add['msg'] = found, msg
        _later(a, put)
    _thread(go)


def add_driver(ig, i):
    a = ig.app
    add = _mem(ig).get('add') or {}
    try:
        p = add['found'][i]
    except (KeyError, IndexError, TypeError):
        return
    x = a._champ(add['cid']) or {}
    cid = add['cid']

    def done(_r, e):
        if e is not None:
            ig.say(x.get('name') or 'ACR Daily', [str(e)])
            return
        _mem(ig)['add'] = None
        told = _('%s is in %s: told in their inbox.') % (p.get('name'), x.get('name', ''))
        ig.say(x.get('name') or 'ACR Daily', [told])
        a.refresh_leagues()
    ig.ask(x.get('name') or 'ACR Daily', [_('Add %s to %s?') % (p.get('name'), x.get('name', ''))], _('YES'),
           lambda: a._bg(lambda: a.api.league_add(cid, p.get('steamId')), done))
