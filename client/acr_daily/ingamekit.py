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
    # (a pad on the panel's content is the panel's own padding: the mod places pads only in rows / columns, so it was
    # lost there and words sat on the panel's edge: the user, 21 Nov 2026)
    if isinstance(c, dict) and c.get('pad') is not None and o.get('p') is None:
        c = dict(c)
        o['p'] = c.pop('pad')
    return _place(dict(t='box', c=c), o)


def txt(s, sz=18, f='semi', fg=SOFT, **o):
    return _place(dict(t='txt', s='' if s is None else str(s), sz=sz, f=f, fg=fg), o)


def img(src, w, h, **o):
    return _place(dict(t='img', src=src, w=w, h=h), o) if src else _place(dict(t='sp', w=w, h=h), o)


def banner(stage_id, w, h, fallback=None, **o):
    """A banner w x h: the game's own picture of the stage (its stage picker's: appui.lua "ue:stage:"), cropped to fill
    it and darkened towards the bottom for words on it; the picture file `fallback` where the game has none (the user,
    21 Nov 2026: "use pictures which are already in-game"). No stage (hidden): the fallback alone."""
    if not stage_id:
        return img(fallback, w, h, **o)
    pic = _place(dict(t='img', src='ue:stage:%s' % stage_id, w=w, h=h, fill_crop=True), {})
    if fallback:
        pic['alt'] = fallback
    shade = [box(None, bg='000000', a=0.12)] + [
        size(box(None, bg='000000', a=a), h=int(h * f), va='b', al='f') for f, a in ((0.6, 0.18), (0.4, 0.22), (0.22, 0.25))]
    return stack(pic, *shade, **o)


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
        out.append(btn('%s:%s' % (prefix, key), label, bg=PANEL2 if here else '-', hov=PANEL2, foc=FOCUS,
                       fg=WHITE if here else FG2,
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
        if t in ('btn', 'edit') and not (x.get('id') or (t == 'btn' and x.get('fid'))):
            out.append('%s: a %s without an id' % (p, t))         # (a list's row: no action, its fid)
        if t == 'txt' and x.get('f', 'semi') not in FACES:
            out.append('%s: face %r' % (p, x.get('f')))
        src = x.get('src')
        if t == 'img' and not (isinstance(src, str) and (os.path.isfile(src) or src.startswith('ue:'))):
            out.append('%s: picture not a file: %r' % (p, src))      # (ue:...: the game's own, appui.lua)
        if t == 'img' and x.get('alt') is not None and not os.path.isfile(str(x['alt'])):
            out.append('%s: fallback picture not a file: %r' % (p, x.get('alt')))
        for k in ('fg', 'bg', 'hov', 'hfg', 'ol', 'foc'):
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
    import hashlib
    m = photos.meta().get(key)
    # (the file's name: a photo's key as it is; a series' or a fetched banner's ('url:...': GitHub's all start alike)
    # by a hash of the whole key)
    name = key if m else 'k-' + hashlib.md5(key.encode('utf-8')).hexdigest()[:16]
    out_dir = os.path.join(settings.DIR, PICS_DIR)
    out = os.path.join(out_dir, '%s-%dx%d%s.png' % (name, w, h, '-f' if fade else ''))
    if os.path.exists(out):
        return out
    try:
        src = photos._photo(key)                 # (photos.py's own: a photo, a series' tile, a banner fetched already)
    except Exception:
        src = None
    if src is None:
        return None
    try:
        im = src.convert('RGB')
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


ROW_H = 32                              # a results row's height in the game's units (sheet())
FOCUS = '3A3A44'                        # a button the wheel / pad / keyboard is on, where its hover look wouldn't show


def line_row(line, me=False, fid=None):
    """A row of a results list: a button with no action, so the wheel's / pad's arrows (and the keyboard's) can step
    through a long list and its scroll follows (the user, 21 Nov 2026: "options to scroll through results"); mine
    stands out. fid: its name for the mod to keep the focus on it when the page is drawn again."""
    return btn(None, c=line, bg=PANEL if me else '-', hov=PANEL2, foc=FOCUS, fid=fid, p=[8, 4, 8, 4], r=2)


def sheet(lines, rows, sid, pinned=None):
    """Result rows (line_row()s): all of them, in a list of their own that scrolls once there are more than `rows`;
    pinned (my own row, when it's further down) under it."""
    if len(lines) > rows:
        body = size(scroll(*lines, id=sid), h=rows * ROW_H)
    else:
        body = col(*lines)
    return col(body, pinned)


def board(b, me, rows=12, title=None, sid='board'):
    """A timing sheet: its title, then every time in a list that scrolls (my own row pinned under it when I'm further
    down than it shows at first). b: the server's board ({'entries': [{name, steamId, totalMs}]}), None while
    loading."""
    title = title or _('Today\'s times')
    entries = [e for e in (b or {}).get('entries', []) if e.get('totalMs') is not None]
    if b is None:
        return col(kicker(title), txt(_('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    if not entries:
        return col(kicker(title), txt(_('No times yet. Be the first.'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
    head = row(kicker(title), sp(fill=1), kicker(_('%d drivers') % len(entries)), pad=[0, 0, 0, 6])
    lines, pinned = [], None
    for pos, e in enumerate(entries, 1):
        is_me = e.get('steamId') == me
        fg = WHITE if is_me else SOFT
        line = row(size(txt('%d' % pos, 17, 'bold', ACC_TEXT if pos == 1 else MUTED, j=2), w=40),
                   sp(14),
                   txt(shown_name(e), 17, 'bold' if is_me else 'semi', fg, fill=1),
                   txt(fmt_ms(e['totalMs']), 17, 'semi', fg, j=2))
        lines.append(line_row(line, is_me, fid='%s:%d' % (sid, pos)))
        if is_me and pos > rows:
            pinned = line_row(line, True, fid='%s:me' % sid)
    return col(head, sheet(lines, rows, sid, pinned))
