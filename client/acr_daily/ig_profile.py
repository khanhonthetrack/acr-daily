"""PROFILE in the game (ingamekit.py says how a page is made): the window's driver page (profileui.py) in its four parts.

    PROFILE        picture, name, team, flag, since when; rating, world rank and credits (the driver card's figures,
                   tabsui.py), the rating's history; career; last dailies; leagues and cups
    ACHIEVEMENTS   every one, unlocked or not
    SHOP           looks: buy, wear, take off; a daily of one's own (its fields picked from lists)
    CUSTOMIZE      a name of one's own, the flag, Steam's picture again, what is worn, the team

The changes are the window's own methods (app._shop_buy, _shop_wear, _own_daily, _set_name, _set_country,
_profile_did): their questions are asked in the game by ig. Choosing a picture file stays in the window (ig.window)."""
import datetime as dt
import hashlib
import os

from . import avatars, i18n, settings, tmtext
from .i18n import _, n_
from .ingamekit import (ACC, BAD, FG2, GOOD, LINE, LINE2, MUTED, PAGE_W, PANEL, PANEL2, PICS_DIR, SOFT, WHITE, box, col,
                        edit, empty, img, kicker, link, primary, quiet, row, size, sp, stack, tab_id, tabs, txt)
from .profileui import KINDS, LOCKED, PARTS, TIERS, career, result_line, unlocked_text

TAB = 'profile'
GAP = 28
HALF = (PAGE_W - GAP) // 2           # a column of the page
SHOP_PARTS = (('looks', _('LOOKS')), ('daily', _('A DAILY OF YOUR OWN')))
# a daily of one's own: its fields (the window's combo boxes: profileui._render_own_daily), key -> the window's word
DAILY_FIELDS = (('day', 'Day'), ('stage', 'Stage'), ('car', 'Car'), ('weather', 'Weather'), ('time', 'Time of day'))
WORDS = {'day': _('Day'), 'stage': _('Stage'), 'car': _('Car'), 'weather': _('Weather'), 'time': _('Time of day'),
         'flag': _('Flag')}


# ---------------------------------------------------------------------- helpers (ig_inbox.py uses them too)
def hexc(v, default=WHITE):
    """'#5BA8FF' / '#5bf' (the server's colours) -> '5BA8FF' as the mod takes them; anything else: default."""
    s = str(v or '').lstrip('#')
    if len(s) == 3:
        s = ''.join(ch * 2 for ch in s)
    return s.upper() if len(s) == 6 and all(ch in '0123456789abcdefABCDEF' for ch in s) else default


def drawable(s):
    """Words the game's font has (a badge may be an emoji: left out then)."""
    return bool(s) and all(ord(ch) < 0x2000 for ch in str(s))


_pics = {}                           # (what, size) -> a PNG made once


def _saved(key, name, make):
    if key in _pics:
        return _pics[key]
    out = os.path.join(settings.DIR, PICS_DIR, name)
    try:
        if not os.path.exists(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            make().save(out + '.tmp', 'PNG')
            os.replace(out + '.tmp', out)
    except (OSError, ValueError):
        out = None
    _pics[key] = out
    return out


def avatar_png(url, px):
    """A driver's picture (avatars.py downloads it, in a thread) cut round, px big -> a PNG's path, or None while it is
    on its way (the page is drawn again every 100 ms: it shows once in)."""
    if not url or avatars.Image is None:
        return None
    if (url, px) in _pics:
        return _pics[(url, px)]
    raw = avatars._raw_of(url)
    if not raw:
        return None
    h = hashlib.md5(url.encode('utf-8')).hexdigest()[:16]
    return _saved((url, px), 'avatar-%s-%d.png' % (h, px), lambda: avatars.round_image(raw, px))


def flag_png(code, w=30, h=20):
    """A country's flag (the website's pictures, avatars.FLAG_URL) -> a PNG's path, or None."""
    code = str(code or '').lower()
    if len(code) != 2 or not code.isalpha() or avatars.Image is None:
        return None
    url = avatars.FLAG_URL % code
    if (url, w) in _pics:
        return _pics[(url, w)]
    raw = avatars._raw_of(url)
    if not raw:
        return None
    return _saved((url, w), 'flag-%s-%dx%d.png' % (code, w, h), lambda: raw.convert('RGB').resize((w, h)))


def portrait(url, px, ring=WHITE):
    """A picture in its ring (a frame from the shop, or white); ACR red until it is in."""
    inner = px - 8
    return stack(size(box(None, bg=ring, r=px // 2), w=px, h=px),
                 size(box(None, bg=ACC, r=inner // 2), w=inner, h=inner, al='c', va='c'),
                 img(avatar_png(url, inner), inner, inner, al='c', va='c'))


def tag_pieces(team, sz=20):
    """A team's tag as the website shows it (Trackmania's $ codes: tmtext.py), each piece in its colour."""
    if team.get('tagFmt'):
        parts = tmtext.spans(team['tagFmt'])
    else:
        parts = [{'t': team.get('tag') or ''}]
    out = [txt(x['t'].upper() if x.get('u') else x['t'], sz, 'bold' if x.get('b') else 'semi',
               hexc(x.get('c') or team.get('color'), WHITE)) for x in parts if x.get('t')]
    return row(*out, va='c') if out else None


def panel(title, *body, right=None, **o):
    return box(col(row(kicker(title), sp(fill=1), right, pad=[0, 0, 0, 10]), *body),
               **dict(dict(bg=PANEL, p=[22, 16, 22, 18], ol=LINE), **o))


def note(s, **o):
    return txt(s, 16, 'medium', FG2, wrap=True, **o)


class Picked:
    """A field picked in the game, as the window's combo box hands it over (.get())."""

    def __init__(self, v):
        self.v = v

    def get(self):
        return self.v


# ---------------------------------------------------------------------- the page
def opened(ig):
    a = ig.app
    ig.mem(TAB)['pick'] = None
    a._profile_fetch()


def page(ig):
    a = ig.app
    m = ig.mem(TAB)
    part = a.profile_part if a.profile_part in dict(PARTS) else 'profile'
    if not a.s.get('token'):
        return col(kicker(_('Profile')),
                   txt(_('Sign in with Steam to see your driver page, your achievements and the shop.'), 22, 'medium',
                       SOFT, wrap=True, pad=[0, 10, 0, 18]),
                   quiet('window', _('OPEN THE WINDOW')), al='l')
    head = row(tabs(tab_id(TAB, 'part'), PARTS, part, va='c'), sp(fill=1),
               txt(a.profile_msg, 16, 'medium', BAD, va='c', pad=[0, 0, 18, 0]) if a.profile_msg else None,
               link(tab_id(TAB, 'site'), _('Your page on the website  ›'), va='c'), pad=[0, 0, 0, 18])
    d = a.profile_data
    if d is None:
        return col(head, empty(a.profile_msg or _('Loading your driver page…')))
    if m.get('pick'):
        return col(head, picker(ig, m['pick']))
    body = {'profile': part_profile, 'achievements': part_achievements, 'shop': part_shop,
            'customize': part_customize}[part](ig, d)
    return col(head, body)


# ---- PROFILE
def part_profile(ig, d):
    left = col(panel(_('Driver'), who(ig, d)),
               panel(_('Driver rating'), rating(d), pad=[0, 16, 0, 0]),
               leagues(d))
    right = col(panel(_('Career'), career_grid(d)),
                panel(_('Last dailies'), last_dailies(d), pad=[0, 16, 0, 0]))
    return row(size(left, w=HALF), sp(GAP), size(right, w=HALF))


def who(ig, d):
    a = ig.app
    look = d.get('look') or {}
    team = d.get('team') or {}
    name = (look['badge'] + ' ' if drawable(look.get('badge')) else '') + (d.get('name') or '')
    colour = hexc(look.get('color'), WHITE) if not look.get('grad') else WHITE
    since = (_('Driving since %s') % i18n.strftime(_('%B %Y'), dt.datetime.fromtimestamp(d['since'] / 1000).timetuple())
             if d.get('since') else '')
    place = row(img(flag_png(d.get('country')), 30, 20, va='c', pad=[0, 0, 10, 0]) if d.get('country') else None,
                txt('  ·  '.join(x for x in (a._country_name(d.get('country')), since) if x), 16, 'medium', FG2, va='c'),
                pad=[0, 6, 0, 0])
    team_line = row(tag_pieces(team, 18), sp(10) if team.get('tag') else None,
                    link(tab_id(TAB, 'team'), team['name'].upper(), fg=hexc(team.get('color'), 'FF4655'), sz=16, f='bold',
                         va='c'), pad=[0, 4, 0, 0]) if team.get('name') else None
    ring = hexc((look.get('frame') or {}).get('color'), WHITE)
    figs = figures(a, d)
    return row(portrait(d.get('avatar'), 132, ring), sp(22),
               col(txt(name, 38, 'bold', colour), team_line, place, figs, fill=1, va='c'))


def figures(a, d):
    """The driver card's figures (tabsui._render_driver): RATING, WORLD RANK, CREDITS."""
    cr = a.credits or {}
    out = []                                  # (the rating and world rank: the Driver rating panel below says them)
    if cr.get('enabled') and cr.get('signedIn') and cr.get('earning', True):
        out.append((_('CREDITS'), '%d' % (cr.get('balance') or 0)))
    elif cr.get('enabled') and cr.get('signedIn'):
        out.append((_('CREDITS'), _('finish a run to earn credits')))
    if not out:
        return None
    return row(*[col(kicker(w), txt(v, 22, 'bold', WHITE), pad=[0 if i == 0 else 36, 0, 0, 0])
                 for i, (w, v) in enumerate(out)], pad=[0, 14, 0, 0])


def rating(d):
    r = d.get('rating') or {}
    if not d.get('ratingOn'):
        return note(_('No rating on this server.'))
    if not r:
        return note(_('Not rated yet: finish a daily to get your rating.'))
    extra = '  ·  '.join(x for x in (_('Peak %d') % r['peak'] if r.get('peak') else '',
                                     n_('%d race', '%d races', r['races']) % r['races'] if r.get('races') else '') if x)
    return col(row(txt('%d' % r['rating'], 56, 'bold', WHITE, va='c'), sp(20),
                   col(txt(_('WORLD #%d OF %d') % (r['rank'], r['of']), 22, 'bold', SOFT),
                       txt(extra, 16, 'medium', MUTED) if extra else None, va='c')),
               chart(d.get('history') or [], HALF - 44, 120, pad=[0, 14, 0, 0]))


def chart(history, w, h, **o):
    """The rating after each race (the last 80): bars from its lowest to its highest, the last one white."""
    pts = [x['rating'] for x in history if x.get('rating') is not None][-80:]
    if len(pts) < 2:
        return txt(_('The rating\'s history: after a few races'), 15, 'medium', MUTED, **o)
    lo, hi = min(pts), max(pts)
    span = max(1, hi - lo)
    left, gap = 56, 2
    bw = max(2, int((w - left - gap * (len(pts) - 1)) / len(pts)))
    bars = [size(box(None, bg=WHITE if i == len(pts) - 1 else ACC), w=bw, h=6 + round((h - 6) * (v - lo) / span),
                 va='b', pad=[0 if i == 0 else gap, 0, 0, 0]) for i, v in enumerate(pts)]
    scale = size(col(txt(str(hi), 14, 'medium', MUTED), sp(fill=1), txt(str(lo), 14, 'medium', MUTED)), w=left, h=h)
    return size(row(scale, *bars), h=h, **o)


def leagues(d):
    lc = [link(tab_id(TAB, 'league', x['id']), (_('Championship ·') + ' ') + x['name'] + '  ›', pad=[0, 0, 0, 6])
          for x in (d.get('leagues') or []) if x.get('id')]
    lc += [link(tab_id(TAB, 'cup', x['id']), _('Cup · %s%s') % (x['name'], ' · P%d' % x['place'] if x.get('place') else '')
                + '  ›', pad=[0, 0, 0, 6]) for x in (d.get('cups') or []) if x.get('id')]
    return panel(_('Championships and cups'), *lc, pad=[0, 16, 0, 0]) if lc else None


def career_grid(d):
    cells = career(d.get('stats'))
    rows = []
    for i in range(0, len(cells), 3):
        rows.append(row(*[size(col(kicker(w), txt(v, 26, 'bold', WHITE)), w=(HALF - 44) // 3)
                          for w, v in cells[i:i + 3]], pad=[0, 0 if i == 0 else 12, 0, 0]))
    cars = (d.get('stats') or {}).get('cars') or []
    if cars:
        rows.append(note((_('Most driven:') + ' ') + ', '.join('%s (%d)' % (x['car'], x['runs']) for x in cars),
                         pad=[0, 14, 0, 0]))
    return col(*rows)


def last_dailies(d):
    rows = (d.get('recent') or [])[:8]
    if not rows:
        return note(_('No dailies yet.'))
    out = []
    for r in rows:
        day, where, place, delta = result_line(r)
        fg = BAD if place == _('DNF') else WHITE if place.startswith('P1 ') else SOFT
        dfg = GOOD if delta.startswith('+') else BAD if delta.startswith('-') else MUTED
        out.append(row(size(txt(day, 17, 'medium', MUTED), w=150), txt(where, 17, 'semi', SOFT, fill=1),
                       size(txt(place, 17, 'bold', fg, j=2), w=110), size(txt(delta, 17, 'semi', dfg, j=2), w=70),
                       pad=[0, 4, 0, 0]))
    return col(*out)


# ---- ACHIEVEMENTS
def part_achievements(ig, d):
    achs = d.get('achievements') or []
    got = sum(1 for x in achs if x.get('at'))
    bar_w = PAGE_W - 360
    on_w = round(bar_w * got / max(1, len(achs)))
    head = row(txt('%d' % got, 40, 'bold', WHITE, va='b'),
               txt(' ' + _('/ %d UNLOCKED') % len(achs), 22, 'bold', FG2, va='b', pad=[0, 0, 0, 5]), sp(fill=1),
               row(size(box(None, bg=ACC), w=on_w, h=8) if on_w else None,
                   size(box(None, bg=PANEL2), w=bar_w - on_w, h=8) if bar_w - on_w else None, va='c'),
               pad=[0, 0, 0, 16])
    per, gap = 4, 16
    w = (PAGE_W - gap * (per - 1)) // per
    rows = []
    for i in range(0, len(achs), per):
        rows.append(row(*[size(ach_tile(x), w=w, pad=[0 if j == 0 else gap, 0, 0, 0])
                          for j, x in enumerate(achs[i:i + per])], pad=[0, 0 if i == 0 else gap, 0, 0]))
    return col(head, *rows) if achs else col(head, empty(_('No achievements yet.')))


def ach_tile(x):
    on = bool(x.get('at'))
    top, _bottom, rim = TIERS.get(x.get('tier'), TIERS['bronze']) if on else LOCKED
    mark = size(box(txt(x['label'], 15, 'bold', '16161A') if on and x.get('label') else None, bg=hexc(top), ol=hexc(rim),
                    olw=2, r=3, al='c', va='c'), w=56, h=56, va='t')
    words = col(txt(x.get('name') or x.get('id'), 20, 'bold', WHITE if on else FG2, wrap=True),
                txt(x.get('desc') or '', 15, 'medium', FG2 if on else MUTED, wrap=True),
                txt(unlocked_text(x), 14, 'semi', GOOD if on else MUTED, pad=[0, 4, 0, 0]), fill=1)
    return box(row(mark, sp(14), words), bg=PANEL, p=[14, 12, 14, 12], ol=LINE, va='f')


# ---- SHOP
def part_shop(ig, d):
    a = ig.app
    m = ig.mem(TAB)
    shop = a.shop_data
    if shop is None:
        return empty(a.profile_msg or _('Opening the shop…'))
    if not shop.get('enabled'):
        return empty(_('The shop opens with credits: they are off on this server.'))
    inner = m.get('shop') or 'looks'
    balance = shop.get('balance') or 0
    head = row(kicker(_('BALANCE'), va='c'), sp(12), txt(_('%d credits') % balance, 30, 'bold', WHITE, va='c'), sp(24),
               txt(_('Looks change nothing on the stage. Credits are only ever earned.'), 16, 'medium', MUTED, va='c'),
               sp(fill=1), tabs(tab_id(TAB, 'shop'), SHOP_PARTS, inner, va='c'), pad=[0, 0, 0, 16])
    if inner == 'daily':
        return col(head, own_daily(ig, shop))
    worn = shop.get('worn') or {}
    items = shop.get('items') or []
    out = [head]
    per, gap = 8, 10
    w = (PAGE_W - 44 - gap * (per - 1)) // per
    for kind, title, about in KINDS:
        mine = [x for x in items if x.get('kind') == kind]
        rows = []
        for i in range(0, len(mine), per):
            rows.append(row(*[size(look_tile(x, worn.get(kind) == x.get('id'), balance, w, a), w=w,
                                   pad=[0 if j == 0 else gap, 0, 0, 0]) for j, x in enumerate(mine[i:i + per])],
                            pad=[0, 0 if i == 0 else gap, 0, 0]))
        out.append(panel(title, *(rows or [note(_('Nothing yet.'))]), right=txt(about, 15, 'medium', MUTED),
                         pad=[0, 0 if len(out) == 1 else 14, 0, 0]))
    return col(*out)


def look_tile(it, worn, balance, w, a):
    kind = it.get('kind')
    if kind == 'color':
        grad = it.get('grad') or [it.get('color')]
        sw = max(1, (w - 20) // len(grad))
        name = a.s.get('name') or _('Your name')
        show = col(txt(name, 18, 'bold', hexc(it.get('color')), j=1),
                   row(*[size(box(None, bg=hexc(c)), w=sw, h=6) for c in grad], al='c', pad=[0, 6, 0, 0]))
    elif kind == 'badge':
        show = txt(it.get('badge') if drawable(it.get('badge')) else '', 26, 'bold', WHITE, j=1)
    else:
        show = stack(size(box(None, bg=hexc(it.get('ring')), r=20), w=40, h=40),
                     size(box(None, bg=ACC, r=16), w=32, h=32, al='c', va='c'), al='c')
    if worn:
        b = primary(tab_id(TAB, 'off', it['id']), _('WORN  ✓'), sz=15, p=[12, 5, 12, 5])
    elif it.get('owned'):
        b = quiet(tab_id(TAB, 'wear', it['id']), _('WEAR'), sz=15, p=[12, 5, 12, 5])
    elif balance >= (it.get('price') or 0):
        b = primary(tab_id(TAB, 'buy', it['id']), _('%d credits') % it['price'], sz=15, p=[12, 5, 12, 5])
    else:
        b = quiet(tab_id(TAB, 'buy', it['id']), _('%d credits') % it['price'], sz=15, p=[12, 5, 12, 5])
    return box(col(size(show, h=46), txt(it.get('name') or '', 17, 'semi', WHITE, j=1, pad=[0, 4, 0, 6]),
                   row(b, al='c')),
               bg='101013', p=[8, 10, 8, 10], ol=WHITE if worn else LINE)


def own_daily(ig, shop):
    """A daily of one's own (profileui._render_own_daily): its fields picked from lists, then the window's _own_daily."""
    dd = shop.get('daily') or {}
    mine = dd.get('mine') or []
    lines = [note(_('SS%s of a day of your choice: its stage, car, weather and time of day. It names you ("set by"). '
                    'One at a time; change it for free until two days before.') % dd.get('slot', 1))]
    for x in mine:
        lines.append(txt(_('Yours: %s · %s · %s%s') % (x['date'], x.get('track'), x.get('car'),
                                                       '' if x.get('editable') else (' ' + _('(fixed now)'))),
                         16, 'bold', GOOD, pad=[0, 6, 0, 0]))
    form = []
    for key, _word in DAILY_FIELDS:
        v = chosen(ig, key)
        form.append(row(size(txt(WORDS[key], 18, 'semi', FG2, va='c'), w=180),
                        size(quiet(tab_id(TAB, 'open', key), (v or '–') + '  ›', fg=WHITE, cal='l', al='f'), minw=520)
                        if v is not None
                        else txt('–', 18, 'semi', MUTED), pad=[0, 8, 0, 0]))
    change = bool(mine and mine[0].get('editable'))
    label = _('CHANGE IT') if change else '%s %s' % (_('SET IT  ·  %d') % (dd.get('price') or 0), _('CREDITS'))
    go = primary(tab_id(TAB, 'set_daily'), label, pad=[0, 20, 0, 0], al='l')
    return size(panel(_('A daily of your own'), *lines, col(*form, pad=[0, 8, 0, 0]), go), w=HALF)


# ---- CUSTOMIZE
def part_customize(ig, d):
    a = ig.app
    m = ig.mem(TAB)
    me = d.get('me') or {}
    look = d.get('look') or {}
    draft = m['name'] if 'name' in m else (me.get('customName') or '')
    name = [note(_('Your name on the timing sheets, the live maps and your page. One change a week; your Steam name is %s.')
                 % (me.get('steamName') or '–')),
            row(box(edit(tab_id(TAB, 'name'), draft, _('Your name'), fill=1), bg=PANEL2, p=[12, 8, 12, 8], r=2, ol=LINE2,
                    fill=1), sp(12), primary(tab_id(TAB, 'save_name'), _('SAVE'), va='c'), pad=[0, 12, 0, 0])]
    if me.get('customName'):
        name.append(link(tab_id(TAB, 'steam_name'), _('Use my Steam name again  ›'), pad=[0, 10, 0, 0]))
    if me.get('nextNameChange'):
        nxt = dt.datetime.fromtimestamp(me['nextNameChange'] / 1000)
        if nxt > dt.datetime.now():
            name.append(txt(_('Your next change: %s.') % i18n.strftime(_('%a %d %b, %H:%M'), nxt.timetuple()), 15,
                            'medium', MUTED, pad=[0, 6, 0, 0]))
    flag = chosen(ig, 'flag')
    code = next((cc for cc, n in (a.countries or []) if n == flag), None)
    flags = [note(_('By your name everywhere, and the ranking of your country.')),
             row(img(flag_png(code), 30, 20, va='c', pad=[0, 0, 12, 0]) if code else None,
                 size(quiet(tab_id(TAB, 'open', 'flag'), flag + '  ›', fg=WHITE, cal='l', al='f'), minw=420, va='c')
                 if a.countries is not None else txt(_('Loading…'), 18, 'medium', MUTED, va='c'),
                 sp(12), primary(tab_id(TAB, 'save_flag'), _('SAVE'), va='c') if a.countries is not None else None,
                 pad=[0, 12, 0, 0])]
    acts = row(quiet(tab_id(TAB, 'choose'), _('CHOOSE A PICTURE…')),
               quiet(tab_id(TAB, 'steam_pic'), _('USE MY STEAM PICTURE'), pad=[12, 0, 0, 0]) if me.get('ownAvatar') else None,
               pad=[0, 12, 0, 0])
    picture = row(portrait(d.get('avatar'), 100, hexc((look.get('frame') or {}).get('color'))), sp(20),
                  col(note(_('Your picture on your page, the timing sheets and the live maps: a square one is best (it is '
                             'cut square from the middle).')), acts, fill=1, va='c'))
    left = col(panel(_('Name'), *name), panel(_('Flag'), *flags, pad=[0, 16, 0, 0]))
    right = col(panel(_('Picture'), picture), panel(_('Your look'), *worn_rows(ig, d),
                                                    right=link(tab_id(TAB, 'part', 'shop'), _('Shop  ›')),
                                                    pad=[0, 16, 0, 0]))
    return row(size(left, w=HALF), sp(GAP), size(right, w=HALF))


def worn_rows(ig, d):
    look = d.get('look') or {}
    team = d.get('team') or {}
    out = []
    for word, v, swatch in ((_('Colour'), look.get('color'), True), (_('Badge'), look.get('badge'), False),
                            (_('Frame'), (look.get('frame') or {}).get('color'), True)):
        if not v:
            what = txt(_('none (the shop has them)'), 17, 'medium', MUTED, va='c')
        elif swatch:
            what = size(box(None, bg=hexc(v), r=2), w=22, h=22, va='c')
        else:
            what = txt(v if drawable(v) else '✓', 20, 'semi', WHITE, va='c')
        out.append(row(size(txt(word, 17, 'semi', FG2, va='c'), w=120), what, pad=[0, 4, 0, 0]))
    out.append(row(size(txt(_('Team'), 17, 'semi', FG2, va='c'), w=120),
                   link(tab_id(TAB, 'team'), (team['name'] + '  ›') if team.get('name')
                        else _('Make or join a team on the website  ›'), va='c'), pad=[0, 12, 0, 0]))
    return out


# ---- the lists a field is picked from (the window's combo boxes)
def options(ig, field):
    a = ig.app
    if field == 'flag':
        return [_('No flag')] + [n for _code, n in (a.countries or [])]
    dd = (a.shop_data or {}).get('daily') or {}
    if field == 'day':
        return a._days(dd.get('from'), dd.get('to'))
    if field == 'stage':
        return [t.get('name') or t.get('track') for t in dd.get('tracks') or []]
    if field == 'car':
        return [x['name'] for x in dd.get('cars') or []]
    if field == 'weather':
        return [x['label'] for x in dd.get('weathers') or []]
    if field == 'time':
        return [x['label'] for x in dd.get('times') or []]
    return []


def chosen(ig, field):
    """The value picked for a field (still one of its list), else what the window's form starts with; None: no list."""
    a = ig.app
    opts = options(ig, field)
    v = (ig.mem(TAB).get('sel') or {}).get(field)
    if v in opts:
        return v
    if field == 'flag':
        return a._country_name((a.profile_data or {}).get('country')) or _('No flag')
    if not opts:
        return None
    dd = (a.shop_data or {}).get('daily') or {}
    mine = (dd.get('mine') or [{}])[0]
    if mine.get('editable'):                    # (mine: its settings in the form, to change: as the window's)
        start = {'day': mine.get('date'), 'car': mine.get('car'),
                 'stage': next((t.get('name') or t.get('track') for t in dd.get('tracks') or []
                                if t.get('track') == mine.get('track')), None),
                 'weather': next((x['label'] for x in dd.get('weathers') or [] if x.get('id') == mine.get('weather')), None),
                 'time': next((x['label'] for x in dd.get('times') or [] if x.get('id') == mine.get('time')), None)}
        if start.get(field) in opts:
            return start[field]
    return opts[0]


def picker(ig, field):
    """A field's list, in the place of the page's part: a click picks."""
    opts = options(ig, field)
    on = chosen(ig, field)
    per, gap = 4, 10
    w = (PAGE_W - 44 - gap * (per - 1)) // per
    rows = []
    for i in range(0, len(opts), per):
        cells = []
        for j, v in enumerate(opts[i:i + per]):
            here = v == on
            cells.append(size(quiet(tab_id(TAB, 'pick', i + j), v, bg=WHITE if here else '-', fg='0A0A0B' if here else SOFT,
                                    cal='l', al='f'), w=w, pad=[0 if j == 0 else gap, 0, 0, 0]))
        rows.append(row(*cells, pad=[0, 0 if i == 0 else gap, 0, 0]))
    return panel(WORDS.get(field, field), *(rows or [note(_('Nothing to pick.'))]),
                 right=quiet(tab_id(TAB, 'unpick'), _('CANCEL')))


# ---------------------------------------------------------------------- what's clicked and typed
def text(ig, field, words):
    if field == 'name':
        ig.mem(TAB)['name'] = words


def click(ig, action, arg):
    a = ig.app
    m = ig.mem(TAB)
    shop = a.shop_data or {}
    item = next((x for x in shop.get('items') or [] if x.get('id') == arg), None)
    if action == 'part':
        m['pick'] = None
        if arg in dict(PARTS):
            a.profile_part = arg                # (the window's own: its fetch takes what the part needs)
            a._profile_fetch()
    elif action == 'site':
        a.open_my_page()
    elif action == 'team':                      # (the page's team: the driver card's may not be in yet)
        tid = ((a.profile_data or {}).get('team') or {}).get('id')
        a.open_page('/t/%s' % tid) if tid else a.open_team()
    elif action == 'league' and arg:
        a.open_page('/l/%s' % arg)
    elif action == 'cup' and arg:
        a.open_page('/cup/%s' % arg)
    elif action == 'shop':
        m['shop'] = arg if arg in dict(SHOP_PARTS) else 'looks'
    elif action == 'buy' and item:
        a._shop_buy(item, shop.get('balance') or 0)
    elif action == 'wear' and item:
        a._shop_wear(item, item['id'])
    elif action == 'off' and item:
        a._shop_wear(item, None)
    elif action == 'open':
        m['pick'] = arg
    elif action == 'unpick':
        m['pick'] = None
    elif action == 'pick' and m.get('pick'):
        opts = options(ig, m['pick'])
        try:
            m.setdefault('sel', {})[m['pick']] = opts[int(arg)]
        except (TypeError, ValueError, IndexError):
            pass
        m['pick'] = None
    elif action == 'set_daily':
        dd = shop.get('daily') or {}
        if not dd:
            return
        boxes = {word: Picked(chosen(ig, key) or '') for key, word in DAILY_FIELDS}
        mine = dd.get('mine') or []
        a._own_daily(dd, boxes, bool(mine))
    elif action == 'save_name':
        me = (a.profile_data or {}).get('me') or {}
        a._set_name((m['name'] if 'name' in m else me.get('customName') or '').strip())
    elif action == 'steam_name':
        m.pop('name', None)
        a._set_name(None)
    elif action == 'save_flag':
        a._set_country(chosen(ig, 'flag'))
    elif action == 'choose':                    # (a file picker: the window's)
        ig.window(TAB)
        if getattr(a, 'profile_view', False):
            a.profile_show_part('customize')
    elif action == 'steam_pic':
        a._profile_did(_('Not changed'), a.api.remove_avatar, _('Your Steam picture is back.'))
