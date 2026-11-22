"""HOME in the game (ingamekit.py says how a page is made): a photo tile for each part of ACR Daily, the big ones over
the small ones (the user, 22 Nov 2026: EVENTS and RANKED on top; ONLINE RALLIES, PROFILE, WATCH and COMMUNITY under
them). Each tile says what it is, what is on now and its badge (the window's tiles' words where it has them:
homeui._home_spec); a click goes to that tab."""
from . import liverally
from .i18n import _
from .ingamekit import (ACC, BG, PAGE_W, SOFT, WHITE, box, btn, col, img, picture, row, sp, stack, tab_id, txt)

TAB = 'home'
GAP = 20
BIG_H, SMALL_H = 500, 350              # (the page's height filled: 200 were left empty at its foot, 22 Nov 2026)
BIG = ('events', 'live')
SMALL = ('comp', 'profile', 'watch', 'community')


def opened(ig):
    a = ig.app
    for name in ('refresh_challenge', 'refresh_tt', 'refresh_leagues', 'refresh_community'):
        fn = getattr(a, name, None)
        if fn:
            try:
                fn()
            except Exception:
                pass
    try:
        from . import ig_watchlist
        ig_watchlist.refresh(ig)
    except Exception:
        pass


def page(ig):
    big = [k for k in BIG if k != 'live' or liverally.ON]
    return col(tile_row(ig, big, BIG_H), tile_row(ig, list(SMALL), SMALL_H, pad=[0, GAP, 0, 0]))


def tile_row(ig, keys, h, **o):
    w = int((PAGE_W - GAP * (len(keys) - 1)) / max(1, len(keys)))
    return row(*[tile(ig, k, w, h, pad=[0 if i == 0 else GAP, 0, 0, 0]) for i, k in enumerate(keys)], **o)


def spec(ig, key):
    """What a tile says: {'title', 'photo', 'lines': [(text, 'sub' / 'info')], 'badge': (words, colour) or None}."""
    a = ig.app
    one = lambda k: (a._home_spec(k) or {})     # noqa: E731  (the window's tile)
    if key == 'events':
        d, t = one('daily'), one('tt')
        info = [x for x in ((d.get('lines') or [None, None])[1:2] + (t.get('lines') or [None, None])[1:2]) if x]
        return {'title': _('EVENTS'), 'photo': 'dailies', 'badge': d.get('badge') or t.get('badge'),
                'lines': [(_('Dailies and time trials'), 'sub')] + [(x[0], 'info') for x in info]}
    if key == 'live':
        return one('live')
    if key == 'comp':
        parts = [one(k) for k in ('league', 'h2h', 'cup')]
        badge = next((p.get('badge') for p in parts if p.get('badge')), None)
        return {'title': _('ONLINE RALLIES'), 'photo': 'leagues', 'badge': badge,
                'lines': [(_('Championships, 1V1s and cups'), 'sub')]}
    if key == 'profile':
        drv = getattr(a, 'driver', None) or {}
        credits = (getattr(a, 'credits', None) or {}).get('balance')
        who = ' · '.join(x for x in (drv.get('name') or a.s.get('name') or '',
                                     (_('%d credits') % credits) if credits is not None else '') if x)
        return {'title': _('PROFILE'), 'photo': 'portugal', 'badge': None,
                'lines': [(_('Your page, flag, team and achievements'), 'sub')] + ([(who, 'info')] if who else [])}
    if key == 'watch':
        try:
            from . import ig_watchlist
            n = len(ig_watchlist.lines(ig))
        except Exception:
            n = 0
        return {'title': _('WATCH'), 'photo': 'monte-carlo', 'badge': (_('%d LIVE') % n, ACC) if n else None,
                'lines': [(_('Everyone on a stage now'), 'sub')]}
    return one(key)


def tile(ig, key, w, h, **o):
    try:
        s = spec(ig, key) or {}
    except Exception:
        s = {'title': key.upper()}
    big = key in BIG
    lines = []
    for text, kind in short_lines(key, s.get('lines') or []):
        lines.append(txt(text, (20 if kind == 'sub' else 17) if big else 17, 'semi' if kind == 'sub' else 'medium',
                         WHITE if kind == 'sub' else SOFT, wrap=True, sh=True, pad=[0, 4, 0, 0]))
    badge = s.get('badge')
    chip = None
    if badge:
        words, colour = badge
        chip = box(txt(words, 15, 'bold', WHITE, sp=80), bg=(colour or ACC).lstrip('#'), p=[10, 3, 10, 3], r=2)
    words = col(row(chip, sp(fill=1)) if chip else None,
                sp(h=1, fill=1),
                txt(s.get('title', ''), 44 if big else 32, 'bold', WHITE, sp=20, sh=True),
                *lines,
                pad=[24, 20, 24, 20], al='f', va='f')
    face = stack(img(picture(s.get('photo'), w, h), w, h), words)
    # (a red frame under the mouse, as the game's own tiles: the button's fill shows round the picture)
    return btn(tab_id(TAB, 'go', key), c=face, bg=BG, hov=ACC, p=[3, 3, 3, 3], fill=1, **o)


def short_lines(key, lines):
    """A tile's lines for the game: what it is said shorter, and a list ("SS1 Name   ·   SS2 Name") broken only between
    its items (the window's words broke oddly on the game's tiles, 22 Nov 2026)."""
    short = {'live': _('Every hour · one car at a time')}
    out = []
    for i, (text, kind) in enumerate(lines):
        if i == 0 and kind == 'sub' and key in short:
            text = short[key]
        elif '·' in (text or ''):
            text = ' · '.join(x.strip().replace(' ', ' ') for x in text.split('·') if x.strip())
        out.append((text, kind))
    return out


def click(ig, action, arg):
    if action != 'go' or not arg:
        return
    ig.click('tab:' + arg)
