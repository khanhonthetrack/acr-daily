"""HOME in the game (ingamekit.py says how a page is made): the app's HOME, a photo tile for each part of ACR Daily, the
big ones over the small ones (homeui.py: DAILIES, TIME TRIAL, RANKED over RALLIES, 1V1, CUPS, COMMUNITY). Each tile says
what the window's says (homeui._home_spec: its name, what it is, what is on now, its badge); a click goes to that tab
(RALLIES, 1V1 and CUPS: COMPETITIONS on that part)."""
from . import homeui
from .ingamekit import (ACC, BG, PAGE_W, SOFT, WHITE, box, btn, col, img, picture, row, sp, stack, tab_id, txt)

TAB = 'home'
GAP = 20
BIG_H, SMALL_H = 430, 290
COMP = ('league', 'h2h', 'cup')       # (COMPETITIONS' parts: ig_comp.py's sub-tabs)


def opened(ig):
    a = ig.app
    for name in ('refresh_challenge', 'refresh_tt', 'refresh_leagues', 'refresh_community'):
        fn = getattr(a, name, None)
        if fn:
            try:
                fn()
            except Exception:
                pass


def page(ig):
    big = [k for k, _r, _c, _s in homeui.PLACES if k in homeui.BIG]
    small = [k for k, _r, _c, _s in homeui.PLACES if k not in homeui.BIG]
    return col(tile_row(ig, big, BIG_H), tile_row(ig, small, SMALL_H, pad=[0, GAP, 0, 0]))


def tile_row(ig, keys, h, **o):
    w = int((PAGE_W - GAP * (len(keys) - 1)) / max(1, len(keys)))
    return row(*[tile(ig, k, w, h, pad=[0 if i == 0 else GAP, 0, 0, 0]) for i, k in enumerate(keys)], **o)


def tile(ig, key, w, h, **o):
    try:
        spec = ig.app._home_spec(key) or {}
    except Exception:
        spec = {'title': key.upper()}
    big = key in homeui.BIG
    lines = []
    for text, kind in spec.get('lines') or []:
        lines.append(txt(text, (20 if kind == 'sub' else 17) if big else 17, 'semi' if kind == 'sub' else 'medium',
                         WHITE if kind == 'sub' else SOFT, wrap=True, sh=True, pad=[0, 4, 0, 0]))
    badge = spec.get('badge')
    chip = None
    if badge:
        words, colour = badge
        chip = box(txt(words, 15, 'bold', WHITE, sp=80), bg=(colour or ACC).lstrip('#'), p=[10, 3, 10, 3], r=2)
    words = col(row(chip, sp(fill=1)) if chip else None,
                sp(h=1, fill=1),
                txt(spec.get('title', ''), 44 if big else 32, 'bold', WHITE, sp=20, sh=True),
                *lines,
                pad=[24, 20, 24, 20], al='f', va='f')
    face = stack(img(picture(spec.get('photo'), w, h), w, h), words)
    # (a red frame under the mouse, as the game's own tiles: the button's fill shows round the picture)
    return btn(tab_id(TAB, 'go', key), c=face, bg=BG, hov=ACC, p=[3, 3, 3, 3], fill=1, **o)


def click(ig, action, arg):
    if action != 'go' or not arg:
        return
    if arg in COMP:
        m = ig.mem('comp')
        m['sub'] = arg
        ig.tab = 'comp'
    else:
        ig.tab = arg
    ig.opened()
