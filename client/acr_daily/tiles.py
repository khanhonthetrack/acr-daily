"""Event tiles, as on RaceRoom's event screen: a card for each stage or event, drawn on a canvas. The one on screen (the
daily being driven or loaded, the time trial stage or league event picked) is filled in ACR red, the others are dark.
Cards side by side (TileRow: the two dailies, the two time trial stages) are kept as tall as each other.

    [ SS1 | MONTE CARLO ]                    [12.4 KM] [TARMAC]
    PEÏRA CAVA - LA BOLLÈNE-VÉSUBIE                    (the stage's road, drawn faint behind)
    HYUNDAI I20 N RALLY2 · RALLY2
    Light rain · Afternoon (16:00)                     [ DRIVE › ]
    WAGER DAILY · STAKE TO DRIVE: 100 (o)              (a strip under the card, when there is something to say)

The lock-up (a white box and an italic word, like a series' logo), outlined chips, the name as big as fits, and the
button in the corner: white on a dark card, black on the red one. Everything but the button, the links and the car
picker is drawn on the canvas, so the card can be redrawn as the window is resized (its road fits the new size).
"""
import tkinter as tk
from tkinter import font as tkfont

TITLE_SIZES = (28, 24, 21, 18, 16)    # a stage name: as big as fits on one line, else wrapped at the smallest
COMPACT_SIZES = (15, 14, 13)          # a card listed under the one picked (league events)
STRIP_BG = '#08080A'                  # the strip under a card (the wager, a time trial stage's standing)

# a card's colours: dark, or ACR red for the one on screen (light reds on it where the dark card has greys)
DARK = {'bg': '#141417', 'edge': '#26262C', 'hover': '#4A4A52', 'title': '#F4F4F5', 'sub': '#D4D4D8', 'info': '#A1A1AA',
        'muted': '#6B6B74', 'chip': '#3A3A42', 'chip_fg': '#D4D4D8', 'road': '#26262D', 'road_glow': '#19191D',
        'link': '#A1A1AA'}
RED = {'bg': '#E30613', 'edge': '#E30613', 'hover': '#FF6A72', 'title': '#FFFFFF', 'sub': '#FFE8EA', 'info': '#FFD0D3',
       'muted': '#FFB3B8', 'chip': '#FF7A82', 'chip_fg': '#FFFFFF', 'road': '#C20410', 'road_glow': '#D3050F',
       'link': '#FFE8EA'}


def _c():
    """The palette of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


_fonts = {}


def font(w, spec):
    """A Tk font for measuring (spec: (family, size[, style])), made once for w's window."""
    key = (w.tk, spec)
    f = _fonts.get(key)
    if f is None:
        fam, size = spec[0], spec[1]
        style = spec[2] if len(spec) > 2 else ''
        f = _fonts[key] = tkfont.Font(root=w, family=fam, size=size, weight='bold' if 'bold' in style else 'normal',
                                      slant='italic' if 'italic' in style else 'roman')
    return f


def fit_size(w, text, room, sizes=TITLE_SIZES, family=None):
    """The biggest of sizes at which text fits on one line in room pixels; the smallest if none (it wraps then)."""
    family = family or _c().FONT_C
    for size in sizes:
        if font(w, (family, size)).measure(text) <= room:
            return size
    return sizes[-1]


def wrap_parts(w, text, spec, room):
    """text broken into lines between its parts ('SS3 of 4 next · 13:32.000 so far · closes in 2 d 23 h'), so a line
    never ends in the middle of one ('closes in 2 / d 23 h'); a part longer than a line still wraps within it."""
    parts = text.split(' · ')
    f = font(w, spec)
    if len(parts) < 2 or f.measure(text) <= room:
        return text
    lines, cur = [], parts[0].rstrip()
    for p in parts[1:]:
        p = p.strip()
        if f.measure(cur + ' · ' + p) <= room:
            cur += ' · ' + p
        else:
            lines.append(cur + ' ·')
            cur = p
    lines.append(cur)
    return '\n'.join(lines)


def road(points, box):
    """A stage's road fitted into box = (x0, y0, x1, y1), keeping its shape (turned a quarter if it fits bigger so):
    flat canvas coordinates, start first; [] without a road."""
    pts = [(float(p[0]), float(p[1])) for p in (points or ())]
    if len(pts) < 2:
        return []
    step = max(1, len(pts) // 180)                    # (a few hundred points are plenty for a picture)
    pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    x0, y0, x1, y1 = box
    bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs) or 1.0, max(zs) - min(zs) or 1.0
    turned = min(bw / h, bh / w) > min(bw / w, bh / h)
    if turned:                                        # (x across becomes down the box)
        pts = [(z, x) for x, z in pts]
        w, h = h, w
        xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    k = min(bw / w, bh / h)
    ox = x0 + (bw - w * k) / 2 - min(xs) * k
    oy = y0 + (bh - h * k) / 2 + max(zs) * k          # (north up: the larger z, the higher on the card)
    out = []
    for x, z in pts:
        out.extend((ox + x * k, oy - z * k))
    return out


class Tile:
    """One card: a frame holding the canvas, and a strip under it (strip(): shown by whoever has something to say).
    render(spec) draws it; the button (made by the caller on tile.cv, so its text stays the caller's) sits in the
    bottom-right corner. spec:
      active   True: the red card (the one on screen)
      lock     ('SS1', 'MONTE CARLO'): the white box and the italic word after it, or None
      chips    ['12.4 KM', 'TARMAC']: outlined, on the right of the lock-up
      kicker   [(text, colour)]: a small line over the name (a league, IN PROGRESS...); on the red card in white
      title    the name, as big as fits (sizes: TITLE_SIZES or COMPACT_SIZES)
      lines    [(text, kind)] under it: kind 'sub' (capitals, bold), 'info', 'muted', or a colour ('good', 'bad', 'acc')
      road     the stage's road ([[x, z], ...]) drawn faint behind, or None
      below    rows of widgets made on tile.cv to sit under the lines, each row left to right (the car picker; links)
      button   False: no button this time
      sizes    the name's sizes (TITLE_SIZES, or COMPACT_SIZES for a card listed under the one picked)
    """
    PAD = 12

    def __init__(self, parent, button=None, on_click=None, restyle=None):
        """restyle(button, primary, surface): the button in the colours of the card it sits on (app.py _btn_style)."""
        c = _c()
        self.k = parent.winfo_fpixels('1i') / 96
        self.frame = tk.Frame(parent, bg=DARK['bg'], highlightthickness=1, highlightbackground=DARK['edge'], bd=0)
        self.cv = tk.Canvas(self.frame, bg=DARK['bg'], highlightthickness=0, bd=0, height=1,
                            cursor='hand2' if on_click else '')
        self.cv.pack(fill='x')
        self.button = button
        self.restyle = restyle
        self.min_h = 0                        # the canvas at least this tall (TileRow: as tall as the card beside it)
        self.natural_h = 0                    # how tall its contents make it
        self.spec = None
        self._strip = None
        self._w = 0
        self._look = DARK
        self._c = c
        self.cv.bind('<Configure>', self._resized)
        if on_click:
            self.cv.bind('<Button-1>', lambda _e: on_click())
            self.cv.bind('<Enter>', lambda _e: self._hover(True))
            self.cv.bind('<Leave>', self._left)

    # -------------------------------------------------------------- the strip under the card
    def strip(self):
        """The label under the card (made once, not shown until packed): dark, small bold capitals."""
        if self._strip is None:
            c = self._c
            self._strip = tk.Label(self.frame, text='', bg=STRIP_BG, fg=c.SOFT, font=(c.FONT, 8, 'bold'), anchor='w',
                                   padx=round(self.PAD * self.k), pady=round(6 * self.k), compound='right')
        return self._strip

    # -------------------------------------------------------------- drawing
    def _width(self):
        w = self.cv.winfo_width()
        return w if w > 1 else round(460 * self.k)    # (not on screen yet: redrawn at its width once it is)

    def _resized(self, e):
        if self.spec is not None and abs(e.width - self._w) > 1:
            self.render(self.spec, e.width)

    def _hover(self, on):
        self.frame.configure(highlightbackground=self._look['hover'] if on else self._look['edge'])

    def _left(self, _e):
        """The mouse off the card (not just onto its button)."""
        x, y = self.cv.winfo_pointerxy()
        f = self.frame
        if not (f.winfo_rootx() <= x < f.winfo_rootx() + f.winfo_width() and f.winfo_rooty() <= y < f.winfo_rooty() + f.winfo_height()):
            self._hover(False)

    def render(self, spec, width=None):
        c, k = self._c, self.k
        self.spec = spec
        look = self._look = RED if spec.get('active') else DARK
        W = width or self._width()
        self._w = W
        P = round(self.PAD * k)
        cv = self.cv
        cv.delete('all')
        cv.configure(bg=look['bg'])
        self.frame.configure(bg=look['bg'], highlightbackground=look['edge'])
        x, y = P, P
        room = W - 2 * P
        # ---- the lock-up (left) and the chips (right)
        row_h = 0
        lock = spec.get('lock')
        if lock:
            box_font, word_font = (c.FONT_C, 11), (c.FONT_C, 12, 'italic')
            tw = font(cv, box_font).measure(lock[0])
            bh = round(22 * k)
            cv.create_rectangle(x, y, x + tw + round(14 * k), y + bh, fill=c.WHITE, outline='')
            cv.create_text(x + round(7 * k), y + bh / 2, text=lock[0], anchor='w', fill=c.BG, font=box_font)
            lx = x + tw + round(14 * k)
            if lock[1]:
                cv.create_line(lx + round(9 * k), y + 1, lx + round(9 * k), y + bh - 1, fill=look['chip'])
                cv.create_text(lx + round(18 * k), y + bh / 2, text=lock[1], anchor='w', fill=look['title'], font=word_font)
            row_h = bh
        cx = W - P
        for text in reversed(spec.get('chips') or []):
            f = (c.FONT_C, 9)
            tw = font(cv, f).measure(text)
            ch = round(18 * k)
            cy = y + (max(row_h, ch) - ch) / 2
            cv.create_rectangle(cx - tw - round(12 * k), cy, cx, cy + ch, outline=look['chip'], width=1)
            cv.create_text(cx - round(6 * k), cy + ch / 2, text=text, anchor='e', fill=look['chip_fg'], font=f)
            cx -= tw + round(18 * k)
            row_h = max(row_h, ch)
        if row_h:
            y += row_h + round(7 * k)
        # ---- a small line over the name
        kicker = [(t, col) for t, col in spec.get('kicker') or [] if t]
        if kicker:
            kx = x
            for i, (t, col) in enumerate(kicker):
                item = cv.create_text(kx, y, text=t, anchor='nw', fill=look['title'] if spec.get('active') else col,
                                      font=(c.FONT, 8, 'bold'))
                kx = cv.bbox(item)[2] + round(10 * k)
            y = cv.bbox(item)[3] + round(2 * k)
        # ---- the name
        sizes = spec.get('sizes') or TITLE_SIZES
        title = spec.get('title') or ''
        size = fit_size(cv, title, room, sizes)
        item = cv.create_text(x, y, text=title, anchor='nw', fill=look['title'], font=(c.FONT_C, size), width=room)
        y = cv.bbox(item)[3] + round(1 * k)
        top_of_rest = y
        # ---- the lines under it, beside the button
        b = self.button if spec.get('button', True) else None
        bw = bh = 0
        if b is not None:
            bw, bh = b.winfo_reqwidth(), b.winfo_reqheight()
        line_room = max(80, room - (bw + round(12 * k) if b is not None else 0))
        fonts = {'sub': (c.FONT, 9, 'bold'), 'info': (c.FONT, 9), 'muted': (c.FONT, 8)}
        colour = {'sub': look['sub'], 'info': look['info'], 'muted': look['muted']}
        for text, kind in spec.get('lines') or []:
            if not text:
                continue
            fg = colour.get(kind) or (look['title'] if spec.get('active') else
                                      {'good': c.GOOD, 'bad': c.BAD, 'acc': c.ACC}.get(kind, look['info']))
            f = fonts.get(kind) or (c.FONT, 9, 'bold')
            text = wrap_parts(cv, text.upper() if kind == 'sub' else text, f, line_room)
            item = cv.create_text(x, y + round(2 * k), text=text, anchor='nw', fill=fg, font=f, width=line_room)
            y = cv.bbox(item)[3]
        # ---- the car picker, links
        for row in spec.get('below') or []:
            row = [w for w in row if w is not None]
            if not row:
                continue
            y += round(6 * k)
            bx, tallest = x, 0
            for w in row:
                if isinstance(w, tk.Label):
                    w.configure(bg=look['bg'], activebackground=look['bg'])
                    if getattr(w, '_fg', None) is not None:     # (a link: its colour on this card, white under the mouse)
                        w._fg = look['link']
                        w.configure(fg=look['link'])
                cv.create_window(bx, y, window=w, anchor='nw')
                bx += w.winfo_reqwidth() + round(14 * k)
                tallest = max(tallest, w.winfo_reqheight())
            y += tallest
        self.natural_h = max(y, top_of_rest + bh + round(2 * k)) + P
        H = max(self.natural_h, self.min_h)
        # ---- the button, in the corner
        if b is not None:
            if self.restyle is not None:
                self.restyle(b, getattr(b, '_primary', True), look['bg'])
            cv.create_window(W - P, H - P, window=b, anchor='se')
        # ---- the road, faint, behind everything
        line = road(spec.get('road'), (W * 0.42, round(8 * k), W - round(10 * k), H - round(8 * k)))
        if len(line) >= 4:
            glow = cv.create_line(*line, fill=look['road_glow'], width=round(9 * k), capstyle='round', joinstyle='round',
                                  smooth=True, tags=('road',))
            cv.create_line(*line, fill=look['road'], width=max(2, round(3 * k)), capstyle='round', joinstyle='round',
                           smooth=True, tags=('road',))
            r = round(3 * k)
            sx, sy, ex, ey = line[0], line[1], line[-2], line[-1]
            cv.create_oval(sx - r, sy - r, sx + r, sy + r, outline=look['road'], width=2, tags=('road',))   # the start
            cv.create_rectangle(ex - r, ey - r, ex + r, ey + r, fill=look['road'], outline='', tags=('road',))   # the finish
            cv.tag_lower('road')
            cv.tag_lower(glow)
        cv.configure(height=H)


class TileRow:
    """Cards side by side in a frame (a grid of equal columns, gap between them), as tall as each other and at least
    base pixels: each canvas is made up to the tallest card, its strip included (the wager under a daily)."""

    def __init__(self, frame, n, base=0, gap=12, padx=20):
        self.frame, self.n, self.base, self.gap, self.padx = frame, n, base, gap, padx
        self.tiles = []
        self._job = None
        for i in range(n):
            frame.columnconfigure(i, weight=1, uniform='tiles')
        frame.bind('<Configure>', lambda _e: self.later(), add='+')

    def add(self, tile):
        i = len(self.tiles)
        self.tiles.append(tile)
        tile.frame.grid(row=0, column=i, sticky='nsew', padx=(self.padx if i == 0 else self.gap // 2,
                                                                 self.padx if i == self.n - 1 else self.gap // 2))
        return tile

    def later(self):
        """Evened once Tk is idle (the cards redraw themselves at a new width first)."""
        if self._job is None:
            self._job = self.frame.after_idle(self.even)

    def even(self):
        self._job = None
        strips = [t._strip.winfo_reqheight() if t._strip is not None and t._strip.winfo_manager() else 0 for t in self.tiles]
        tallest = max([self.base] + [t.natural_h + st for t, st in zip(self.tiles, strips)])
        for t, st in zip(self.tiles, strips):
            if t.min_h != tallest - st and t.spec is not None:
                t.min_h = tallest - st
                t.render(t.spec, t._w or None)
