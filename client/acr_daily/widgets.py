"""Optional in-game displays, each its own small always-on-top window (switch them on in the main window).

  strip   vertical stage strip on the left: start at the bottom, finish at the top, your car, the ghosts and the
          other drivers on the stage right now (from the website's live map)
  delta   your gap to P1, and whether you are gaining or losing over the last 10 s
Drag a display to move it while the overlays are unlocked; locked = clicks go through to the game.
(The mini map and the "on stage now" list were taken out on 2026-10-11: not useful.)
"""
import ctypes
import os
import time
import tkinter as tk

from . import avatars
from . import i18n
from .i18n import _

BG, LINE, LINE2 = '#0A0A0B', '#1F1F23', '#3A3A42'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#85858E'
ACC, GOOD, BAD, SLOW = '#E30613', '#30D158', '#FF453A', '#FF9F0A'
FONT_C = i18n.font('Bahnschrift SemiBold Condensed')
GHOST = {'p1': WHITE, 'ahead': '#5BA8FF', 'me': '#B48CFF', 'field': FG2}

DEFAULTS = {                     # (any screen: fit_on_screen brings them into view)
    'strip': {'visible': False, 'x': 24, 'y': 420},
    'delta': {'visible': False, 'x': 380, 'y': 40},
}
LABELS = {'strip': _('Stage strip'), 'delta': _('Delta trend')}


# other drivers on the stage: their own colour each (same picks as the website's live map; red is you)
PALETTE = ['#5BA8FF', '#FF7AB6', '#4CD6C0', '#FF9F43', '#B48CFF', '#7BE07B', '#FFD60A', '#3DD5F3', '#F2A0FF', '#C8E06B']


def colours(ids, chosen=None):
    """{steamId: colour}: a different colour for everyone (by Steam id, the next free one on a clash); a colour bought in
    the shop (chosen: {steamId: colour}) comes first, as on the website."""
    out, used = {}, set()
    for sid, col in (chosen or {}).items():
        if str(sid) in {str(i) for i in ids}:
            out[str(sid)] = col
            if col in PALETTE:
                used.add(PALETTE.index(col))
    for sid in sorted(str(i) for i in ids):
        if sid in out:
            continue
        try:
            k = int(sid[-6:]) % len(PALETTE)
        except ValueError:
            k = 0
        for _i in range(len(PALETTE)):
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


def clamp(x, y, w, h, area):
    """(x, y) of a w x h window moved inside area = (left, top, right, bottom), as far as it fits."""
    left, top, right, bottom = area
    return max(left, min(int(x), right - w)), max(top, min(int(y), bottom - h))


def fit_on_screen(x, y, w, h):
    """(x, y) moved so a w x h window lies on the monitor nearest to it, inside its work area: a default or
    remembered position off every screen (one smaller than where it was set, or unplugged since) comes into view."""
    try:
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                        ('dwFlags', wintypes.DWORD)]
        u = ctypes.windll.user32
        u.MonitorFromRect.restype = wintypes.HMONITOR
        r = wintypes.RECT(int(x), int(y), int(x) + w, int(y) + h)
        mi = MonitorInfo()
        mi.cbSize = ctypes.sizeof(MonitorInfo)
        if not u.GetMonitorInfoW(u.MonitorFromRect(ctypes.byref(r), 2), ctypes.byref(mi)):   # 2: the nearest one
            return int(x), int(y)
        a = mi.rcWork
        return clamp(x, y, w, h, (a.left, a.top, a.right, a.bottom))
    except (AttributeError, OSError, ValueError):
        return int(x), int(y)


def fmt_gap(ms):
    return '–' if ms is None else ('+' if ms >= 0 else '−') + '%.2f' % (abs(ms) / 1000)


# ---- staying over the game
# Tk's -topmost moves the window to the top of Windows' order of windows each time it is set (SetWindowPos, even when
# it is there already), and the timer set it on every tick: 20 times a second. A window over the game already makes
# Windows compose the game's picture with it (FreeSync / G-SYNC off; with V-Sync on the game's FPS can halve: README,
# "The timer and the game's FPS"); moved over and over it costs more. Now an overlay goes back on top only when a
# window of another program has come over it (the game brought to the front), looked at every ON_TOP_S.
ON_TOP_S = 0.5


def overlap(a, b):
    """Do two rectangles (left, top, right, bottom) overlap?"""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class _Windows:
    """The few Windows calls keep_on_top makes (user32 and dwmapi, their own copies: other modules' calls keep their
    types)."""

    def __init__(self):
        from ctypes import wintypes
        self.wt = wintypes
        u = ctypes.WinDLL('user32')
        u.GetWindow.restype = u.GetParent.restype = wintypes.HWND
        u.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
        u.GetParent.argtypes = u.IsWindowVisible.argtypes = u.IsIconic.argtypes = (wintypes.HWND,)
        u.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        u.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.u = u
        try:
            self.d = ctypes.WinDLL('dwmapi')
            self.d.DwmGetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        except OSError:
            self.d = None

    def wrapper(self, win):
        """The Windows window of a Tk toplevel (its frame, as set_locked uses it)."""
        return self.u.GetParent(win.winfo_id())

    def above(self, h):
        return self.u.GetWindow(h, 3)                                 # GW_HWNDPREV: the next one up

    def rect(self, h):
        r = self.wt.RECT()
        return (r.left, r.top, r.right, r.bottom) if self.u.GetWindowRect(h, ctypes.byref(r)) else None

    def shown(self, h):
        """On the screen: not hidden, minimised or cloaked (kept by Windows but not shown: a closed app's window)."""
        if not self.u.IsWindowVisible(h) or self.u.IsIconic(h):
            return False
        c = self.wt.DWORD()
        return not (self.d and self.d.DwmGetWindowAttribute(h, 14, ctypes.byref(c), 4) == 0 and c.value)   # DWMWA_CLOAKED

    def pid(self, h):
        p = self.wt.DWORD()
        self.u.GetWindowThreadProcessId(h, ctypes.byref(p))
        return p.value


_windows = None


def windows():
    """The Windows calls, or None (another system)."""
    global _windows
    if _windows is None:
        try:
            _windows = _Windows() if os.name == 'nt' else False
        except (AttributeError, OSError):
            _windows = False
    return _windows or None


def covered(hwnd, w):
    """Is a window of another program, on the screen, above this one and over any of it? (Our own windows don't count:
    the displays, the ghost cars, a dialog of the app.)"""
    me = w.rect(hwnd) if hwnd else None
    if not me:
        return False
    h = w.above(hwnd)
    for _i in range(500):                 # (Windows' list ends; never round and round all the same)
        if not h:
            return False
        r = w.rect(h)
        if r and overlap(me, r) and w.shown(h) and w.pid(h) != os.getpid():
            return True
        h = w.above(h)
    return False


def keep_on_top(win, w=None):
    """A shown overlay (a Tk toplevel) back on top if another program's window has come over it. -> True if it was."""
    w = w or windows()
    if w is None:
        return False
    try:
        if win.winfo_ismapped() and covered(w.wrapper(win), w):
            win.attributes('-topmost', True)
            return True
    except Exception:                     # (closed meanwhile...): never a reason to stop the app's tick
        pass
    return False


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
        self.win.geometry('+%d+%d' % fit_on_screen(self.cfg['x'], self.cfg['y'], self.W, self.H))
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
        self.title(_('%s  STAGE') % (v.get('label') or 'SS%s' % v.get('slot', '–')))   # (a time trial's: 'TT1')
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
                          fill=MUTED if gap is None else SLOW if gap > 0 else GOOD)
            yy += 22
        if not rows:
            c.create_text(10, yy, text=_('No ghosts yet'), anchor='nw', fill=MUTED, font=(FONT_C, 10))


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
        self.title(_('VS P1') + (('  ' + v['p1_name'].upper()) if v.get('p1_name') else ''))
        c.create_text(10, 28, text=fmt_gap(gap), anchor='nw', font=(FONT_C, 30),
                      fill=MUTED if gap is None else SLOW if gap > 0 else GOOD)
        old = next((g for t, g in self.hist if now - t >= 9.5), None) if self.hist else None
        if old is not None and gap is not None:
            d = gap - old
            arrow, col = ('▲', SLOW) if d > 30 else ('▼', GOOD) if d < -30 else ('■', MUTED)
            word = _('losing') if d > 30 else _('gaining') if d < -30 else _('steady')
            c.create_text(self.W - 10, 32, text='%s %s' % (arrow, fmt_gap(d)), anchor='ne', fill=col, font=(FONT_C, 14))
            c.create_text(self.W - 10, 54, text=_('%s · last 10 s') % word, anchor='ne', fill=MUTED, font=(FONT_C, 9))


CLASSES = {'strip': StageStrip, 'delta': DeltaTrend}
