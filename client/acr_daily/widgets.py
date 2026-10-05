"""Optional in-game displays, each its own small always-on-top window (switch them on in the main window).

  strip   vertical stage strip on the left: start at the bottom, finish at the top, your car and the ghosts
  map     mini map of the stage with your dot and the ghosts' dots
  delta   your gap to P1, and whether you are gaining or losing over the last 10 s
  field   who else is on this stage right now (from the website's live map)
Drag a display to move it while the overlays are unlocked; locked = clicks go through to the game.
"""
import ctypes
import math
import time
import tkinter as tk

from . import avatars

BG, LINE, LINE2 = '#0A0A0B', '#1F1F23', '#3A3A42'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC, GOOD, BAD = '#FFD100', '#30D158', '#FF453A'
FONT_C = 'Bahnschrift SemiBold Condensed'
GHOST = {'p1': WHITE, 'ahead': '#5BA8FF', 'me': '#B48CFF', 'field': FG2}

DEFAULTS = {
    'strip': {'visible': False, 'x': 24, 'y': 420},
    'map': {'visible': False, 'x': 24, 'y': 1080},
    'delta': {'visible': False, 'x': 380, 'y': 40},
    'field': {'visible': False, 'x': 700, 'y': 40},
}
LABELS = {'strip': 'Stage strip', 'map': 'Mini map', 'delta': 'Delta trend', 'field': 'Live field'}


# other drivers on the stage: their own colour each (same picks as the website's live map; yellow is you)
PALETTE = ['#5BA8FF', '#FF7AB6', '#4CD6C0', '#FF9F43', '#B48CFF', '#7BE07B', '#FF6B6B', '#3DD5F3', '#F2A0FF', '#C8E06B']


def colours(ids):
    """{steamId: colour}: a different colour for everyone (by Steam id, the next free one on a clash)."""
    out, used = {}, set()
    for sid in sorted(str(i) for i in ids):
        try:
            k = int(sid[-6:]) % len(PALETTE)
        except ValueError:
            k = 0
        for _ in range(len(PALETTE)):
            if k not in used:
                break
            k = (k + 1) % len(PALETTE)
        used.add(k)
        out[sid] = PALETTE[k]
    return out


def driver_dot(c, x, y, colour, avatar=None, r=5, ring=None):
    """Another driver: their Steam avatar in a circle ringed in their colour, or a plain coloured dot."""
    img = avatars.get(avatar, 2 * r) if avatar else None
    if img is None:
        c.create_oval(x - r, y - r, x + r, y + r, fill=colour, outline=ring or BG, width=2)
        return
    c.create_oval(x - r - 2, y - r - 2, x + r + 2, y + r + 2, fill=ring or colour, outline='')
    c.create_image(x, y, image=img)


def fmt_gap(ms):
    return '–' if ms is None else ('+' if ms >= 0 else '−') + '%.2f' % (abs(ms) / 1000)


class Widget:
    W, H = 200, 100

    def __init__(self, app, key):
        self.app, self.key = app, key
        self.cfg = app.s.setdefault('widgets', {}).setdefault(key, dict(DEFAULTS[key]))
        for k, v in DEFAULTS[key].items():
            self.cfg.setdefault(k, v)
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.94)
        self.win.configure(bg=BG)
        self.c = tk.Canvas(self.win, width=self.W, height=self.H, bg=BG, highlightthickness=0)
        self.c.pack()
        self.win.geometry('+%d+%d' % (int(self.cfg['x']), int(self.cfg['y'])))
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._drag)
        self.c.bind('<ButtonRelease-1>', self._release)
        self.win.update_idletasks()
        self.set_locked(bool(app.s['overlay'].get('locked')))
        self.show(self.cfg.get('visible'))

    def _press(self, e):
        self._off = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag(self, e):
        if not self.app.s['overlay'].get('locked'):
            self.win.geometry('+%d+%d' % (e.x_root - self._off[0], e.y_root - self._off[1]))

    def _release(self, _e):
        self.cfg['x'], self.cfg['y'] = self.win.winfo_x(), self.win.winfo_y()
        self.app.save_settings()

    def set_locked(self, locked):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20) | 0x80000 | 0x08000000
            style = style | 0x20 if locked else style & ~0x20
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass
        self.win.configure(highlightthickness=0 if locked else 1, highlightbackground=ACC)

    def show(self, on):
        if on:
            self.win.deiconify()
            self.win.attributes('-topmost', True)
        else:
            self.win.withdraw()

    def title(self, text, x=10, y=10):
        self.c.create_text(x, y, text=text, anchor='nw', fill=MUTED, font=(FONT_C, 9))

    def render(self, view):
        raise NotImplementedError


class StageStrip(Widget):
    """Vertical: start at the bottom, finish at the top."""
    W, H = 168, 420

    def render(self, v):
        c = self.c
        c.delete('all')
        self.title('SS%s  STAGE' % v.get('slot', '–'))
        x, top, bot = 26, 40, self.H - 120
        c.create_line(x, top, x, bot, fill=LINE2, width=3)
        for frac in v.get('splits') or []:
            y = bot - (bot - top) * frac
            c.create_line(x - 6, y, x + 6, y, fill=MUTED, width=1)
        c.create_rectangle(x - 5, top - 5, x + 5, top + 5, fill=WHITE, outline='')   # finish
        c.create_rectangle(x - 5, top - 5, x, top, fill=BG, outline='')
        c.create_rectangle(x, top, x + 5, top + 5, fill=BG, outline='')
        my = v.get('progress')
        if my is not None:
            y = bot - (bot - top) * my
            c.create_line(x, bot, x, y, fill=ACC, width=3)
        # the other drivers on the stage right now: a dot on the line and their name in their colour
        last_y = None
        for name, col, prog, avatar in sorted(v.get('others_prog') or [], key=lambda o: -o[2]):
            y = bot - (bot - top) * max(0.0, min(1.0, prog))
            driver_dot(c, x, y, col, avatar, r=8)
            ly = y if last_y is None else max(y, last_y + 12)    # names never sit on top of each other
            if ly <= bot + 6:
                c.create_text(x + 24, ly, text=name[:14], anchor='w', fill=col, font=(FONT_C, 9))
            last_y = ly
        rows = v.get('ghosts') or []
        for label, kind, prog, gap in rows:
            if prog is None:
                continue
            y = bot - (bot - top) * prog
            c.create_polygon(x + 9, y, x + 17, y - 5, x + 17, y + 5, fill=GHOST.get(kind, FG2), outline='')
        if my is not None:
            y = bot - (bot - top) * my
            c.create_oval(x - 6, y - 6, x + 6, y + 6, fill=ACC, outline=BG, width=2)
        # gaps
        yy = self.H - 104
        c.create_line(10, yy - 8, self.W - 10, yy - 8, fill=LINE)
        for label, kind, prog, gap in rows[:4]:
            c.create_rectangle(10, yy + 4, 16, yy + 10, fill=GHOST.get(kind, FG2), outline='')
            c.create_text(22, yy, text=label[:16], anchor='nw', fill=SOFT, font=(FONT_C, 10))
            c.create_text(self.W - 10, yy, text=fmt_gap(gap), anchor='ne', font=(FONT_C, 11),
                          fill=MUTED if gap is None else BAD if gap > 0 else GOOD)
            yy += 22
        if not rows:
            c.create_text(10, yy, text='No ghosts yet', anchor='nw', fill=MUTED, font=(FONT_C, 10))


class MiniMap(Widget):
    W, H = 260, 190

    def __init__(self, app, key):
        super().__init__(app, key)
        self._route_id, self._proj, self._line = None, None, None

    def _fit(self, pts):
        mx = sum(p[0] for p in pts) / len(pts)
        mz = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - mx) ** 2 for p in pts)
        szz = sum((p[1] - mz) ** 2 for p in pts)
        sxz = sum((p[0] - mx) * (p[1] - mz) for p in pts)
        a = -0.5 * math.atan2(2 * sxz, sxx - szz)
        ca, sa = math.cos(a), math.sin(a)
        rot = [((p[0] - mx) * ca - (p[1] - mz) * sa, (p[0] - mx) * sa + (p[1] - mz) * ca) for p in pts]
        x0, x1 = min(r[0] for r in rot), max(r[0] for r in rot)
        y0, y1 = min(r[1] for r in rot), max(r[1] for r in rot)
        pad, top = 14, 26
        k = min((self.W - 2 * pad) / max(1, x1 - x0), (self.H - top - pad) / max(1, y1 - y0))
        ox = (self.W - (x1 - x0) * k) / 2 - x0 * k
        oy = top + (self.H - top - pad - (y1 - y0) * k) / 2 - y0 * k

        def proj(p):
            X, Y = (p[0] - mx) * ca - (p[1] - mz) * sa, (p[0] - mx) * sa + (p[1] - mz) * ca
            return X * k + ox, Y * k + oy
        return proj

    def render(self, v):
        c = self.c
        pts = v.get('route')
        if not pts or len(pts) < 2:
            c.delete('all')
            self.title('MAP')
            return
        if self._route_id != id(pts):
            self._route_id, self._proj = id(pts), self._fit(pts)
            step = max(1, len(pts) // 300)
            self._line = [xy for p in pts[::step] + [pts[-1]] for xy in self._proj(p)]
        c.delete('all')
        self.title('SS%s  MAP' % v.get('slot', '–'))
        c.create_line(*self._line, fill=LINE2, width=2, smooth=False)
        sx, sy = self._proj(pts[0])
        c.create_oval(sx - 3, sy - 3, sx + 3, sy + 3, fill=WHITE, outline='')
        fx, fy = self._proj(pts[-1])
        c.create_rectangle(fx - 4, fy - 4, fx + 4, fy + 4, fill=WHITE, outline='')
        for label, kind, pos in v.get('ghost_pos') or []:
            if pos is None:
                continue
            gx, gy = self._proj(pos)
            c.create_oval(gx - 4, gy - 4, gx + 4, gy + 4, fill=GHOST.get(kind, FG2), outline=BG, width=1)
        for name, col, pos, avatar in v.get('others') or []:
            ox, oy = self._proj(pos)
            driver_dot(c, ox, oy, col, avatar, r=7)
            c.create_text(ox + 11, oy, text=name[:10], anchor='w', fill=col, font=(FONT_C, 8))
        me = v.get('me_pos')
        if me:
            mx, my = self._proj(me)
            c.create_oval(mx - 5, my - 5, mx + 5, my + 5, fill=ACC, outline=BG, width=2)


class DeltaTrend(Widget):
    W, H = 250, 78

    def __init__(self, app, key):
        super().__init__(app, key)
        self.hist = []          # (monotonic time, gap ms)

    def render(self, v):
        c = self.c
        c.delete('all')
        gap, now = v.get('gap_p1'), time.monotonic()
        if v.get('running') and gap is not None:
            self.hist.append((now, gap))
        if not v.get('running'):
            self.hist = []
        self.hist = [h for h in self.hist if now - h[0] <= 12]
        self.title('VS P1' + (('  ' + v['p1_name'].upper()) if v.get('p1_name') else ''))
        c.create_text(10, 28, text=fmt_gap(gap), anchor='nw', font=(FONT_C, 30),
                      fill=MUTED if gap is None else BAD if gap > 0 else GOOD)
        old = next((g for t, g in self.hist if now - t >= 9.5), None) if self.hist else None
        if old is not None and gap is not None:
            d = gap - old
            arrow, col = ('▲', BAD) if d > 30 else ('▼', GOOD) if d < -30 else ('■', MUTED)
            word = 'losing' if d > 30 else 'gaining' if d < -30 else 'steady'
            c.create_text(self.W - 10, 32, text='%s %s' % (arrow, fmt_gap(d)), anchor='ne', fill=col, font=(FONT_C, 14))
            c.create_text(self.W - 10, 54, text='%s · last 10 s' % word, anchor='ne', fill=MUTED, font=(FONT_C, 9))


class LiveField(Widget):
    W, H = 260, 150

    def render(self, v):
        c = self.c
        c.delete('all')
        drivers = v.get('field') or []
        self.title('ON STAGE NOW  %d' % len(drivers))
        y = 30
        cols = v.get('colours') or {}
        for d in drivers[:5]:
            col = cols.get(str(d.get('steamId')), FG2)
            ring = None if d['state'] == 'live' else WHITE if d['state'] == 'finished' else BAD
            driver_dot(c, 16, y + 9, col, d.get('avatar'), r=7, ring=ring)
            c.create_text(30, y, text=d['name'][:18], anchor='nw', fill=col, font=(FONT_C, 11))
            right = '%d%%' % round(d['progress'] * 100) if d['state'] == 'live' else d['state'].upper()
            c.create_text(self.W - 10, y, text=right, anchor='ne',
                          fill=FG2 if d['state'] == 'live' else WHITE if d['state'] == 'finished' else BAD, font=(FONT_C, 11))
            y += 22
        if not drivers:
            c.create_text(10, y, text='Nobody else on this stage', anchor='nw', fill=MUTED, font=(FONT_C, 10))


CLASSES = {'strip': StageStrip, 'map': MiniMap, 'delta': DeltaTrend, 'field': LiveField}
