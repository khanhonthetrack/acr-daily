"""The wheel's / pad's arrows in ACR DAILY's pages, worked out by the app (0.2).

The game's own navigation moved the selection once, then never again after a wheel's press (the user, 21 Nov 2026:
"I can go down to one tile but then cant move to other tiles using the wheel": the arrow keys reached the pages, the
selection stayed; the game's menus take the wheel for a game pad). So the app finds the button itself: where each
button sits is estimated from the page's tree (ingamekit nodes), laid out as the mod lays them out (appui.lua build /
place: columns and rows share what is left among their fill children, a box's padding, a size's width and height...),
and the nearest button that way is the one the mod focuses (ingameapp cmd "focus").

The sizes are estimates (words ~half their size wide each letter); the order of things is what counts: the row below,
the card to the right."""

TXT_W = 0.52                 # a letter's width, of the words' size (Rajdhani is narrow)
TXT_H = 1.25
PAGE_W, PAGE_H = 1840, 1000
SIDE_MAX = 120               # left / right: a button this far above or below isn't that way


def _pad(p):
    if p is None:
        return (0, 0, 0, 0)
    if isinstance(p, (int, float)):
        return (p, p, p, p)
    p = list(p) + [0, 0, 0, 0]
    return tuple(float(v or 0) for v in p[:4])


def _kids(n):
    c = n.get('c')
    if c is None:
        return []
    return [x for x in (c if isinstance(c, list) else [c]) if isinstance(x, dict)]


def measure(n, memo):
    """A node's own size (w, h), as its widgets would want it."""
    k = id(n)
    if k in memo:
        return memo[k]
    t = n.get('t')
    w = h = 0.0
    if t == 'txt' or (t == 'btn' and n.get('s') is not None):
        s, sz = str(n.get('s') or ''), float(n.get('sz') or (18 if t == 'btn' else 16))
        w, h = len(s) * sz * TXT_W, sz * TXT_H
        if n.get('wrap') and w > 600:
            lines = w / 600.0
            w, h = 600.0, h * (int(lines) + 1)
        if t == 'btn':
            l, tp, r, b = _pad(n.get('p'))
            w, h = w + l + r, h + tp + b
    elif t == 'img':
        w, h = float(n.get('w') or 0), float(n.get('h') or 0)
    elif t == 'sp':
        w, h = float(n.get('w') or 0), float(n.get('h') or 0)
    elif t == 'edit':
        w, h = float(n.get('w') or 300), float(n.get('h') or (n.get('sz') or 18) * 1.6)
    elif t in ('box', 'btn'):
        kids = _kids(n)
        cw, ch = measure(kids[0], memo) if kids else (0.0, 0.0)
        l, tp, r, b = _pad(n.get('p'))
        w, h = cw + l + r, ch + tp + b
    elif t == 'size':
        kids = _kids(n)
        cw, ch = measure(kids[0], memo) if kids else (0.0, 0.0)
        w = float(n['w']) if n.get('w') is not None else max(cw, float(n.get('minw') or 0))
        h = float(n['h']) if n.get('h') is not None else max(ch, float(n.get('minh') or 0))
    elif t in ('col', 'scroll', 'row', 'stack'):
        across = t == 'row'
        gap = float(n.get('gap') or 0)
        for i, c in enumerate(_kids(n)):
            cw, ch = measure(c, memo)
            l, tp, r, b = _pad(c.get('pad'))
            cw, ch = cw + l + r, ch + tp + b
            if t == 'stack':
                w, h = max(w, cw), max(h, ch)
            elif across:
                w, h = w + cw + (gap if i else 0), max(h, ch)
            else:
                w, h = max(w, cw), h + ch + (gap if i else 0)
    if t in ('btn',) and (n.get('w') or n.get('h')):          # (a button's own size: a size box round it)
        w = float(n.get('w') or w)
        h = float(n.get('h') or h)
    memo[k] = (w, h)
    return w, h


def _align(code, default):
    return {'l': 'l', 'c': 'c', 'r': 'r', 'f': 'f', 't': 'l', 'b': 'r'}.get(code, default)


def _within(x, W, want, how):
    """Where a child of width want sits in room W at x, its alignment how (l c r f) -> (x, w)."""
    if how == 'f' or want >= W:
        return x, W
    if how == 'c':
        return x + (W - want) / 2.0, want
    if how == 'r':
        return x + W - want, want
    return x, want


def arrange(n, x, y, W, H, out, memo, path=()):
    """Every button's place: out[id] = (x, y, w, h)."""
    t = n.get('t')
    if t == 'btn':
        bid = n.get('id') or n.get('fid')
        if bid:
            out[bid] = (x, y, W, H)
        if n.get('s') is None:
            kids = _kids(n)
            if kids:
                l, tp, r, b = _pad(n.get('p'))
                arrange(kids[0], x + l, y + tp, max(0, W - l - r), max(0, H - tp - b), out, memo, path)
        return
    if t == 'edit':
        if n.get('id'):
            out[n['id']] = (x, y, W, H)
        return
    if t in ('box', 'size'):
        kids = _kids(n)
        if not kids:
            return
        l, tp, r, b = _pad(n.get('p')) if t == 'box' else (0, 0, 0, 0)
        ix, iy, iw, ih = x + l, y + tp, max(0, W - l - r), max(0, H - tp - b)
        if t == 'size':
            iw = float(n['w']) if n.get('w') is not None else iw
            ih = float(n['h']) if n.get('h') is not None else ih
        c = kids[0]
        cw, ch = measure(c, memo)
        cx, cw2 = _within(ix, iw, cw, _align(n.get('al'), 'f'))
        cy, ch2 = _within(iy, ih, ch, _align(n.get('va'), 'f'))
        arrange(c, cx, cy, cw2, ch2, out, memo, path)
        return
    if t == 'stack':
        for c in _kids(n):
            l, tp, r, b = _pad(c.get('pad'))
            cw, ch = measure(c, memo)
            cx, cw2 = _within(x + l, max(0, W - l - r), cw, _align(c.get('al'), 'f'))
            cy, ch2 = _within(y + tp, max(0, H - tp - b), ch, _align(c.get('va'), 'f'))
            arrange(c, cx, cy, cw2, ch2, out, memo, path)
        return
    if t not in ('col', 'row', 'scroll'):
        return
    across = t == 'row'
    kids = _kids(n)
    gap = float(n.get('gap') or 0)
    sizes, fills = [], 0.0
    for i, c in enumerate(kids):
        cw, ch = measure(c, memo)
        l, tp, r, b = _pad(c.get('pad'))
        if c.get('pad') is None and gap and i:
            l, tp = (gap, 0) if across else (0, gap)
        f = c.get('fill')
        f = (1.0 if f is True else float(f)) if f and t != 'scroll' else 0.0
        fills += f
        sizes.append((cw, ch, (l, tp, r, b), f))
    room = (W if across else H) - sum((s[0] + s[2][0] + s[2][2]) if across else (s[1] + s[2][1] + s[2][3])
                                      for s in sizes if not s[3])
    room -= sum((s[2][0] + s[2][2]) if across else (s[2][1] + s[2][3]) for s in sizes if s[3])
    pos = x if across else y
    for c, (cw, ch, (l, tp, r, b), f) in zip(kids, sizes):
        if across:
            w_main = max(0.0, room * f / fills) if f else cw
            cx = pos + l
            # (a button with words in a row: in the middle of it, as the mod puts it)
            dv = 'c' if (c.get('t') == 'btn' and c.get('s') is not None and not c.get('fill')) else 'f'
            cy, ch2 = _within(y + tp, max(0, H - tp - b), ch, _align(c.get('va'), dv))
            arrange(c, cx, cy, w_main, ch2, out, memo, path)
            pos = cx + w_main + r
        else:
            h_main = max(0.0, room * f / fills) if f else ch
            cy = pos + tp
            dh = 'l' if (c.get('t') == 'btn' and c.get('s') is not None and not c.get('fill')) else 'f'
            cx, cw2 = _within(x + l, max(0, W - l - r), cw, _align(c.get('al'), dh))
            arrange(c, cx, cy, cw2, h_main, out, memo, path)
            pos = cy + h_main + b


def places(page, dialog=None):
    """-> {button id: (x, y, w, h)}: the dialog's alone when there is one (the page's are out of reach then)."""
    out, memo = {}, {}
    if isinstance(dialog, dict):
        w, h = measure(dialog, memo)
        arrange(dialog, (PAGE_W - w) / 2.0, (PAGE_H - h) / 2.0, w, h, out, memo)
        return out
    if isinstance(page, dict):
        arrange(page, 0.0, 0.0, PAGE_W, PAGE_H, out, memo)
    return out


def move(page, dialog, focus, d):
    """The button to go to from `focus` going d ('up' 'down' 'left' 'right'), or None. Nothing focused yet: the first
    button."""
    at = places(page, dialog)
    if not at:
        return None
    if focus not in at:
        return next(iter(at))
    ax, ay, aw, ah = at[focus]
    acx, acy = ax + aw / 2.0, ay + ah / 2.0
    best = None
    for bid, (x, y, w, h) in at.items():
        if bid == focus:
            continue
        cx, cy = x + w / 2.0, y + h / 2.0
        # (that way: starting past this one's edge; a wider button just under it isn't "to the right")
        if d in ('down', 'up'):
            ahead = (y - (ay + ah)) if d == 'down' else (ay - (y + h))        # (the gap between them that way)
            if (y < ay + ah - 4) if d == 'down' else (y + h > ay + 4):
                continue
            side = max(0.0, x - (ax + aw), ax - (x + w))                       # (0: they overlap across)
            off = abs(cx - acx)
        else:
            ahead = (x - (ax + aw)) if d == 'right' else (ax - (x + w))
            if (x < ax + aw - 4) if d == 'right' else (x + w > ax + 4):
                continue
            side = max(0.0, y - (ay + ah), ay - (y + h))
            if side > SIDE_MAX:                  # (left / right: about level with it; the last card's Right went
                continue                         # up to the header's BACK)
            off = abs(cy - acy)
        # (the nearest that way first, then the one most in line: from a tab, the card's own DRIVE under it, not its list)
        score = 2.0 * max(ahead, 0.0) + 1.5 * side + 0.1 * off
        if best is None or score < best[0]:
            best = (score, bid)
    return best[1] if best else None
