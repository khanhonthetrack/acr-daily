"""The building blocks of ACR DAILY's pages in the game (ingameapp.py; drawn by mod/ACRDailyGhosts/Scripts/appui.lua).

A page is a tree of nodes, plain dicts the mod draws with the game's own widgets:

    col(*children, gap=)       a column           row(*children, gap=)    a row
    stack(*children)           layered, first at the back
    box(child, bg=, a=, r=, ol=, olw=, p=, al=, va=)   a panel: fill colour (hex, '-' none), alpha, corner radius,
                               outline colour / width, padding [l, t, r, b]; al / va: how its child sits
    txt(s, sz, f, fg, wrap=, j=, sp=, sh=)   words: size, face (light regular medium semi bold), colour, wrap,
                               justify (0 left 1 centre 2 right), letter spacing (1/1000 em), shadow
    img(path, w, h)            a picture file (PNG/JPG), fitted in w x h
    sp(w, h)                   empty room (fill=1: takes what's left in its row / column)
    size(child, w=, h=, minw=, minh=, maxw=)   a fixed / least / most size around a child
    btn(id, s) / btn(id, c=child)   a button (bg, hov: its colour under the mouse; fg, hfg: its words' colours)
    primary(id, s), quiet(id, s), link(id, s)   the app's buttons: solid white / hairline / words only
    edit(id, s, hint, w=)      a box to type in; what's typed comes back to the page's text() when Enter is pressed
                               or the box is left
    scroll(*children, id=)     a list that scrolls (the mouse wheel); the mod keeps where it was scrolled to

Every node takes its place in its parent: fill (a share of what's left), al (l c r f), va (t c b f), pad [l, t, r, b].

A page module (ig_<tab>.py) has:

    page(ig) -> node                the tab's body (under the header; the mod scrolls it)
    click(ig, action, arg)          a button whose id is '<tab>.<action>[:<arg>]' (tab_id() makes them)
    text(ig, field, words)          (optional) an edit node with id '<tab>.<field>' was typed in
    opened(ig)                      (optional) the tab opened in the game: fetch its data, as the window's tab does

ig (ingameapp.InGameApp) gives the app (ig.app), a dict per tab for the page's own state (ig.mem(tab)), ig.ask(title,
lines, go_label, fn) / ig.say(title, lines) for a question / a note over the page, and ig.window(tab) for what stays in
the app's window (picking a file). The app's own questions (messagebox.askyesno, simpledialog.askstring...) asked while
a click is done are put in the game by ig itself: call the app's methods as its window does.

Words: short and plain, the app's own where it has them (its _() strings), no explaining.
"""
import os

from . import photos, settings
from .i18n import _
from .judge import fmt_ms  # noqa: F401  (the pages' times)

try:
    from PIL import Image
except ImportError:                     # (an app built without Pillow: no pictures in the game)
    Image = None

PICS_DIR = os.path.join('hud', 'app')   # (in settings.DIR) the pictures cut for the game's pages
PAGE_W = 1840                           # a page's width in the game's units (1080 tall)

# the look: the app's colours (app.py), in the game's font (Rajdhani)
BG, PANEL, PANEL2, LINE, LINE2 = '0A0A0B', '141417', '1C1C21', '1F1F23', '2B2B31'
WHITE, SOFT, FG2, MUTED = 'F4F4F5', 'D4D4D8', 'A1A1AA', '85858E'
ACC, ACC_TEXT, GOOD, BAD, SLOW = 'E30613', 'FF4655', '30D158', 'FF453A', 'FF9F0A'
# each part's colour, as the app's tabs and the website (tabsui.TABS)
COLOUR = {'daily': WHITE, 'tt': 'BF5AF2', 'league': '5BA8FF', 'h2h': 'FF9F43', 'cup': 'FFD60A', 'event': 'FF7AC6',
          'community': '30D158', 'live': 'FF4655'}


# ---------------------------------------------------------------------- nodes
def _place(n, o):
    n.update({k: v for k, v in o.items() if v is not None})
    return n


def col(*c, **o):
    return _place(dict(t='col', c=[x for x in c if x]), o)


def row(*c, **o):
    return _place(dict(t='row', c=[x for x in c if x]), o)


def stack(*c, **o):
    return _place(dict(t='stack', c=[x for x in c if x]), o)


def box(c=None, **o):
    return _place(dict(t='box', c=c), o)


def txt(s, sz=18, f='semi', fg=SOFT, **o):
    return _place(dict(t='txt', s='' if s is None else str(s), sz=sz, f=f, fg=fg), o)


def img(src, w, h, **o):
    return _place(dict(t='img', src=src, w=w, h=h), o) if src else _place(dict(t='sp', w=w, h=h), o)


def sp(w=None, h=None, **o):
    return _place(dict(t='sp', w=w, h=h), o)


def size(c, **o):
    return _place(dict(t='size', c=c), o)


def scroll(*c, **o):
    return _place(dict(t='scroll', c=[x for x in c if x]), o)


def rule(**o):
    """A hairline across."""
    return _place(dict(t='size', h=1, c=box(None, bg=LINE)), o)


def btn(id_, s=None, c=None, **o):
    n = dict(t='btn', id=id_)
    if c is not None:
        n['c'] = c
    else:
        n['s'] = s
    return _place(n, o)


def primary(id_, s, **o):
    """The page's main button (DRIVE, JOIN): solid white, red under the mouse."""
    return btn(id_, s, **dict(dict(bg=WHITE, hov=ACC, fg=BG, hfg=WHITE, sz=20, f='bold', sp=60, p=[28, 10, 28, 10], r=2),
                              **o))


def quiet(id_, s, **o):
    """A plain button: a hairline, white under the mouse."""
    return btn(id_, s, **dict(dict(bg='-', hov=WHITE, fg=SOFT, hfg=BG, sz=17, f='semi', sp=40, p=[20, 8, 20, 8], r=2,
                                   ol=LINE2), **o))


def link(id_, s, **o):
    """Words that act as a button: quiet until the mouse is on them."""
    return btn(id_, s, **dict(dict(bg='-', hov='-', fg=FG2, hfg=WHITE, sz=17, f='semi', p=[0, 2, 0, 2], cal='l'), **o))


def chip(s, fg=WHITE, bg=ACC, **o):
    return box(txt(s, 14, 'bold', fg, sp=60), **dict(dict(bg=bg, p=[8, 2, 8, 2], r=2), **o))


def kicker(s, fg=MUTED, **o):
    """A small spaced-out uppercase label (as the app's and the website's)."""
    return txt((s or '').upper(), 14, 'bold', fg, sp=120, **o)


def edit(id_, s='', hint='', **o):
    """A box to type in (one line; multi=True: several). Its words come back to the page's text() once typed."""
    return _place(dict(t='edit', id=id_, s=s or '', hint=hint or '', sz=o.pop('sz', 18)), o)


def tabs(prefix, items, on, **o):
    """A row of sub-tabs (the app's COMPETITIONS: RALLIES / 1V1 / CUPS): items [(key, label)], on the key shown."""
    out = []
    for key, label in items:
        here = key == on
        out.append(btn('%s:%s' % (prefix, key), label, bg=PANEL2 if here else '-', hov=PANEL2, fg=WHITE if here else FG2,
                       hfg=WHITE, sz=16, f='bold', sp=80, p=[14, 6, 14, 6], ol=LINE2 if here else None,
                       pad=[0 if not out else 6, 0, 0, 0]))
    return row(*out, **o)


def empty(s, **o):
    """What a page says when it has nothing to show."""
    return txt(s, 20, 'medium', MUTED, wrap=True, **o)


def tab_id(tab, action, arg=None):
    """A page's button id: '<tab>.<action>[:<arg>]' (ingameapp sends it to that page's click())."""
    return '%s.%s%s' % (tab, action, '' if arg is None else ':%s' % arg)


KINDS = {'col', 'row', 'stack', 'box', 'txt', 'img', 'sp', 'size', 'scroll', 'btn', 'edit'}
FACES = {'light', 'regular', 'medium', 'semi', 'bold'}


def check(n, path='page'):
    """A page's tree as the mod can draw it -> the faults found, [str] (tests: every page, every state). Plain JSON
    only, known node kinds, buttons and boxes to type in with ids, pictures as files."""
    import json
    out = []

    def walk(x, p):
        if x is None:
            return
        if not isinstance(x, dict) or x.get('t') not in KINDS:
            out.append('%s: not a node: %r' % (p, x if not isinstance(x, dict) else x.get('t')))
            return
        t = x['t']
        if t in ('btn', 'edit') and not x.get('id'):
            out.append('%s: a %s without an id' % (p, t))
        if t == 'txt' and x.get('f', 'semi') not in FACES:
            out.append('%s: face %r' % (p, x.get('f')))
        if t == 'img' and not (isinstance(x.get('src'), str) and os.path.isfile(x['src'])):
            out.append('%s: picture not a file: %r' % (p, x.get('src')))
        for k in ('fg', 'bg', 'hov', 'hfg', 'ol'):
            v = x.get(k)
            if v is not None and v != '-' and not (isinstance(v, str) and len(v) in (6, 8)
                                                   and all(ch in '0123456789abcdefABCDEF' for ch in v)):
                out.append('%s: colour %s=%r (hex without #)' % (p, k, v))
        kids = x.get('c')
        if isinstance(kids, list):
            for i, c in enumerate(kids):
                walk(c, '%s/%s[%d]' % (p, t, i))
        elif kids is not None:
            walk(kids, '%s/%s' % (p, t))
    walk(n, path)
    try:
        json.dumps(n, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        out.append('%s: not plain JSON: %s' % (path, e))
    return out


# ---------------------------------------------------------------------- pictures, cut for the game
def picture(key, w, h, fade=True):
    """One of the app's photos (photos.py: a rally's, a part's, a league's banner fetched already) cut to w x h (its
    focus point kept), darkened towards its bottom for the words on it -> the PNG's path (made once), or None."""
    if Image is None or not key:
        return None
    m = photos.meta().get(key)
    src = os.path.join(photos.DIR, m['file']) if m else None
    raw = None if m else getattr(photos, '_raw', {}).get(key)
    if not src and not raw:
        return None
    safe = ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in key)[:60]
    out_dir = os.path.join(settings.DIR, PICS_DIR)
    out = os.path.join(out_dir, '%s-%dx%d%s.png' % (safe, w, h, '-f' if fade else ''))
    if os.path.exists(out):
        return out
    try:
        import io
        im = (Image.open(src) if src else Image.open(io.BytesIO(raw))).convert('RGB')
        fx, fy = ((m or {}).get('focus') or [0.5, 0.5])[:2]
        sw, sh = im.size
        k = max(w / sw, h / sh)
        im = im.resize((max(w, round(sw * k)), max(h, round(sh * k))), Image.LANCZOS)
        sw, sh = im.size
        x = min(max(0, round(fx * sw - w / 2)), sw - w)
        y = min(max(0, round(fy * sh - h / 2)), sh - h)
        im = im.crop((x, y, x + w, y + h))
        if fade:
            shade = Image.new('L', (1, h))
            for i in range(h):
                a = max(0.0, (i / h - 0.35) / 0.65)
                shade.putpixel((0, i), round(235 * a ** 1.4))
            dark = Image.new('RGB', (w, h), (10, 10, 11))
            im = Image.composite(dark, im, shade.resize((w, h)))
        os.makedirs(out_dir, exist_ok=True)
        im.save(out + '.tmp', 'PNG')
        os.replace(out + '.tmp', out)
        return out
    except (OSError, ValueError, KeyError):
        return None


def png_of(path_or_none):
    """A picture file the game can load (PNG / JPG / BMP) or None: anything else (WEBP...) converted once."""
    p = path_or_none
    if not p or not os.path.exists(p):
        return None
    if p.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')) or Image is None:
        return p
    out = os.path.join(settings.DIR, PICS_DIR, 'conv-%x.png' % (hash(p) & 0xFFFFFFFF))
    if not os.path.exists(out):
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            Image.open(p).convert('RGBA').save(out, 'PNG')
        except (OSError, ValueError):
            return None
    return out


# ---------------------------------------------------------------------- the app's words for a stage (app.py's own)
def stage_name(ch, short=False):
    from . import app as app_mod
    return app_mod.stage_name(ch, short)


def conditions(ch):
    from . import app as app_mod
    return app_mod.conditions(ch)


def set_by(ch):
    from . import app as app_mod
    return app_mod.set_by(ch)


def shown_name(e):
    from . import app as app_mod
    return app_mod.shown_name(e)


def board(b, me, rows=12, title=None):
    """A timing sheet: its title, then the top rows (my own pinned at the bottom when I'm further down). b: the
    server's board ({'entries': [{name, steamId, totalMs}]}), None while loading."""
    title = title or _('Today\'s times')
    entries = [e for e in (b or {}).get('entries', []) if e.get('totalMs') is not None]
    if b is None:
        return col(kicker(title), txt(_('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    if not entries:
        return col(kicker(title), txt(_('No times yet. Be the first.'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    shown = entries[:rows]
    mine = next((e for e in entries if e.get('steamId') == me), None)
    if mine is not None and mine not in shown:
        shown = shown[:rows - 1] + [mine]
    best = entries[0]['totalMs']
    out = [row(kicker(title), sp(fill=1), kicker(_('%d drivers') % len(entries)), pad=[0, 0, 0, 6])]
    for e in shown:
        pos = entries.index(e) + 1
        is_me = e.get('steamId') == me
        gap = '' if pos == 1 else '+' + fmt_ms(e['totalMs'] - best).lstrip('0:')
        fg = WHITE if is_me else SOFT
        line = row(txt('%d' % pos, 17, 'bold', ACC_TEXT if pos == 1 else MUTED, j=2),
                   sp(14),
                   txt(shown_name(e), 17, 'bold' if is_me else 'semi', fg, fill=1),
                   txt(fmt_ms(e['totalMs']), 17, 'semi', fg, j=2),
                   sp(14),
                   txt(gap, 15, 'medium', MUTED, j=2),
                   pad=[0, 5, 0, 0])
        out.append(box(line, bg=PANEL, p=[6, 0, 6, 4]) if is_me else line)
    return col(*out)
