"""Ghost cars (a test): the window over the game that draws them, and its set-up window (ghostcars.py does the maths).

The overlay is one borderless, see-through, click-through window over the game's picture, redrawn about 60 times a
second from the game's shared memory (its own reader, so the app's 20 a second loop is not slowed down).

For development: ACR_DAILY_GHOST_TEST=1 draws in a plain 1280 x 720 window at (40, 40) instead of over the game (no
game window needed; with ACR_DAILY_REPLAY a recorded run plays as you).
"""
import ctypes
import math
import os
import time
import tkinter as tk
from ctypes import wintypes

from . import ghostcars as gc
from .telemetry import ReplaySource, SharedMemory

KEY = '#010203'                 # the see-through colour
BG, PANEL, LINE2 = '#0A0A0B', '#121214', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC = '#E30613'
GHOST_COL = '#B48CFF'           # the app's colour for your own run
LINE_COL = '#4CD6C0'
FONT_C = 'Bahnschrift SemiBold Condensed'
FRAME_MS = 16
SIGHT_EVERY = 6                 # frames between two line-of-sight checks

user32 = ctypes.windll.user32 if os.name == 'nt' else None
kernel32 = ctypes.windll.kernel32 if os.name == 'nt' else None


def find_game_window():
    """The game's main window (class UnrealWindow, process acr.exe), or None."""
    if user32 is None:
        return None
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _lp):
        if not user32.IsWindowVisible(h):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value != 'UnrealWindow':
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        hp = kernel32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
        if hp:
            buf, n = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
            ok = kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n))
            kernel32.CloseHandle(hp)
            r = wintypes.RECT()
            user32.GetClientRect(h, ctypes.byref(r))
            if ok and os.path.basename(buf.value).lower() == 'acr.exe' and r.right > 400 and r.bottom > 300:
                found.append(h)
                return False
        return True
    user32.EnumWindows(proc(each), 0)
    return found[0] if found else None


def client_rect(hwnd):
    """(x, y, width, height) of a window's picture on the screen, or None."""
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return p.x, p.y, r.right - r.left, r.bottom - r.top


def ours_in_front(game):
    """Is the game (or one of this app's own windows: the set-up while you line the view up) in front?"""
    fg = user32.GetForegroundWindow()
    if fg and fg == game:
        return True
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    return pid.value == os.getpid()


def config(s):
    cfg = s.setdefault('ghostCars', {})
    for k, v in gc.DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


def fmt_gap(ms):
    return '%s%.1f s' % ('+' if ms >= 0 else '−', abs(ms) / 1000.0)


class GhostOverlay:
    def __init__(self, app):
        self.app = app
        self.cfg = config(app.s)
        self.src = app.shm if isinstance(app.shm, ReplaySource) else SharedMemory()
        self.rec = gc.GhostRecorder()
        self.ghost, self._ghost_key = None, None
        self.game, self.rect, self._rect_at, self._find_at = None, None, 0.0, 0.0
        self.status = 'Off'
        self._shown, self._n, self._sight = False, 0, True
        self._timer = False
        self.test = os.environ.get('ACR_DAILY_GHOST_TEST') == '1'
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        if not self.test:
            self.win.attributes('-transparentcolor', KEY)
        self.win.configure(bg=KEY)
        self.c = tk.Canvas(self.win, bg='#202024' if self.test else KEY, highlightthickness=0, bd=0)
        self.c.pack(fill='both', expand=True)
        self.win.update_idletasks()
        self._click_through()
        self.win.after(500, self._loop)

    def _click_through(self):
        if self.test:
            return
        try:
            hwnd = user32.GetParent(self.win.winfo_id())
            LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
            style = user32.GetWindowLongW(hwnd, -20) | LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
            user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def _fine_timer(self, on):
        """Windows' timer to 1 ms while drawing (Tk's 16 ms waits are otherwise rounded up to 31)."""
        if on != self._timer:
            try:
                (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)
                self._timer = on
            except Exception:
                pass

    def _show(self, on):
        if on and not self._shown:
            self.win.deiconify()
            self.win.attributes('-topmost', True)
            self._click_through()
        elif not on and self._shown:
            self.c.delete('all')
            self.win.withdraw()
        self._shown = on

    def _loop(self):
        try:
            delay = self._frame()
        except Exception:
            import traceback
            traceback.print_exc()
            delay = 250
        self.win.after(delay, self._loop)

    # -------------------------------------------------------------- one frame

    def _frame(self):
        if not self.cfg.get('on'):
            self.status = 'Off'
            self._show(False)
            self._fine_timer(False)
            return 500
        try:
            f = self.src.read()
        except Exception:
            f = None
        self.rec.feed(f)
        if f is None or not f.track:
            self.status = 'Waiting for the game'
            self._show(False)
            self._fine_timer(False)
            return 250
        self._fine_timer(True)
        self._load_ghost(f.track)
        if not self._locate():
            self.status = 'Can\'t find the game\'s window'
            self._show(False)
            return 250
        if self.ghost is None:
            self.status = 'No run of yours on %s yet: drive it once' % f.track
            self._show(False)
            return FRAME_MS
        if not (self.test or ours_in_front(self.game)) or f.clock_ms < 0:
            self._show(False)
            return FRAME_MS
        self._show(True)
        self._draw(f)
        return FRAME_MS

    def _load_ghost(self, track):
        """The run to show on this stage (looked for again on another stage or choice, a new run saved, every 5 s)."""
        want = (track, self.cfg.get('source', 'last'), self.rec.saved, int(time.monotonic() // 5))
        if want == getattr(self, '_want', None):
            return
        self._want = want
        meta = gc.pick_run(track, self.cfg.get('source', 'last'))
        key = meta and meta['path']
        if key != self._ghost_key:
            self._ghost_key = key
            self.ghost = gc.load_run(meta) if meta else None

    def _locate(self):
        if self.test:
            if self.rect is None:
                self.rect = (40, 40, 1280, 720)
                self.win.geometry('1280x720+40+40')
            return True
        now = time.monotonic()
        if self.game and not user32.IsWindow(self.game):
            self.game = None
        if self.game is None and now - self._find_at > 2.0:
            self._find_at = now
            self.game = find_game_window()
        if self.game is None:
            return False
        if now - self._rect_at > 1.0 or self.rect is None:
            self._rect_at = now
            r = client_rect(self.game)
            if r is None:
                return False
            if r != self.rect:
                self.rect = r
                self.win.geometry('%dx%d+%d+%d' % (r[2], r[3], r[0], r[1]))
        return True

    def _draw(self, f):
        c, cfg, g = self.c, self.cfg, self.ghost
        c.delete('all')
        w, h = self.rect[2], self.rect[3]
        cam = gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), cfg, w, h)
        early = int(float(cfg.get('earlierS') or 0) * 1000)
        my_ms = max(0, f.clock_ms)
        g_ms = my_ms + early
        passed = g.passed(f.x, f.z)
        name = 'BEST RUN' if cfg.get('source') == 'best' else 'LAST RUN'
        self.status = 'Ghost: your %s on %s (%s)%s' % (
            name.lower(), g.track, fmt_ms(g.clock_ms), ', %d s earlier' % (early // 1000) if early else '')
        if cfg.get('line') and passed is not None:      # its line on the road ahead of you: to line the view up
            pts = [cam.project((x, y - gc.CAR_ABOVE_GROUND, z)) for x, y, z in g.path(passed, passed + 600000, 3.0, 150.0)]
            for a, b in zip(pts, pts[1:]):
                if a and b and -w < a[0] < 2 * w and -h < a[1] < 2 * h:
                    c.create_line(a[0], a[1], b[0], b[1], fill=LINE_COL, width=3)
        if g_ms > g.end_ms + 10000:                     # it finished a while ago
            return
        pose = g.at(g_ms)
        dist = math.dist((f.x, f.y, f.z), pose[:3])
        if dist > gc.MAX_DRAW_M or cam.depth(pose[:3]) < 1.0:
            return
        self._n += 1
        if self._n % SIGHT_EVERY == 0:
            path = g.path(passed if passed is not None else g_ms, g_ms, 4.0) if g_ms >= (passed or 0) else []
            self._sight = gc.in_sight(cam.pos, pose[:3], path)
        if not (self._sight or cfg.get('always')):
            return
        pts = [cam.project(p) for p in gc.box_corners(pose)]
        if all(pts):
            c.create_polygon(*[v for p in pts[:4] for v in p], fill=GHOST_COL, stipple='gray25', outline='')
            for i, j in gc.BOX_EDGES:
                c.create_line(pts[i][0], pts[i][1], pts[j][0], pts[j][1], fill=GHOST_COL, width=2)
        top = cam.project(gc.add(pose[:3], (0.0, 1.6, 0.0)))
        if top:
            text = '%s  ·  %d m%s' % (name, dist, ('  ·  ' + fmt_gap(my_ms + early - passed)) if passed is not None else '')
            c.create_text(top[0] + 1, top[1] + 1, text=text, fill=BG, font=(FONT_C, 14), anchor='s')
            c.create_text(top[0], top[1], text=text, fill=WHITE, font=(FONT_C, 14), anchor='s')

    def close(self):
        self._fine_timer(False)
        if self.src is not self.app.shm:
            self.src.close()


def fmt_ms(ms):
    if ms is None:
        return '–'
    return '%d:%06.3f' % (ms // 60000, (ms % 60000) / 1000.0)


# ---------------------------------------------------------------------- set-up window

SLIDERS = [  # key, label, from, to, step
    ('earlierS', 'Starts earlier (s)', 0, 60, 1),
    ('fov', 'Field of view', 30, 120, 0.5),
    ('fwd', 'Camera forward (m)', -8, 4, 0.05),
    ('up', 'Camera height (m)', -0.5, 3, 0.05),
    ('side', 'Camera side (m)', -1.5, 1.5, 0.05),
    ('tilt', 'Camera tilt (°)', -20, 20, 0.5),
]
CHECKS = [  # key, label
    ('on', 'Ghost cars on'),
    ('line', 'Show its line on the road'),
    ('always', 'Show through trees and hills'),
    ('level', 'Camera stays level'),
    ('mirror', 'Swap left and right'),
]


class GhostSetup:
    def __init__(self, app, overlay):
        self.app, self.ov, self.cfg = app, overlay, overlay.cfg
        self._save_after = None
        w = self.win = tk.Toplevel(app.root)
        w.title('Ghost cars (test)')
        w.configure(bg=BG, padx=18, pady=14)
        w.resizable(False, False)
        try:
            w.iconbitmap(os.path.join(os.path.dirname(__file__), 'icon.ico'))
        except tk.TclError:
            pass
        lab = lambda parent, text, fg=SOFT, size=10, font=FONT_C: tk.Label(parent, text=text, bg=BG, fg=fg,
                                                                           font=(font, size), anchor='w', justify='left')
        lab(w, 'GHOST CARS (TEST)', WHITE, 14).pack(anchor='w')
        lab(w, 'Your last run, drawn on the road. Drive a stage once; on the next run it drives with you.\n'
               'Line it up: stop the car, then move the sliders until the green line sits on the road.',
            FG2, 9, 'Bahnschrift').pack(anchor='w', pady=(2, 10))
        self.vars = {}
        for key, text in CHECKS[:1]:
            self._check(w, key, text)
        src = tk.Frame(w, bg=BG)
        src.pack(anchor='w', pady=(4, 6))
        self.src = tk.StringVar(value=self.cfg.get('source', 'last'))
        for val, text in (('last', 'Last run'), ('best', 'Best run')):
            tk.Radiobutton(src, text=text, value=val, variable=self.src, command=self._source, bg=BG, fg=SOFT,
                           selectcolor=PANEL, activebackground=BG, activeforeground=WHITE,
                           font=(FONT_C, 10)).pack(side='left', padx=(0, 12))
        views = tk.Frame(w, bg=BG)
        views.pack(anchor='w', pady=(4, 6))
        lab(views, 'View', MUTED).pack(side='left', padx=(0, 10))
        for v in gc.VIEWS:
            b = tk.Label(views, text=v.upper(), bg=BG, fg=FG2, font=(FONT_C, 10), padx=8, pady=3, cursor='hand2',
                         highlightthickness=1, highlightbackground=LINE2)
            b.bind('<Button-1>', lambda _e, v=v: self._view(v))
            b.pack(side='left', padx=(0, 6))
        self.scales = {}
        for key, text, lo, hi, step in SLIDERS:
            row = tk.Frame(w, bg=BG)
            row.pack(fill='x')
            lab(row, text, MUTED, 9, 'Bahnschrift').pack(side='left', pady=4)
            value = lab(row, '', SOFT, 9, 'Bahnschrift')
            # (a Scale's background is its knob: light, on a lighter track than the window)
            s = tk.Scale(row, from_=lo, to=hi, resolution=step, orient='horizontal', length=230, width=12,
                         showvalue=False, bg=FG2, troughcolor=LINE2, highlightthickness=0, bd=0, sliderrelief='flat',
                         sliderlength=14, activebackground=ACC,
                         command=lambda val, k=key, v=value: (v.configure(text=val), self._set(k, float(val))))
            s.set(self.cfg.get(key, 0))
            s.pack(side='right')
            value.configure(width=6, anchor='e', text=s.get())     # (set() at the slider's own start value says nothing)
            value.pack(side='right', padx=(8, 8))
            self.scales[key] = s
        for key, text in CHECKS[1:]:
            self._check(w, key, text)
        self.status = lab(w, '', FG2, 9, 'Bahnschrift')
        self.status.pack(anchor='w', pady=(10, 0))
        w.protocol('WM_DELETE_WINDOW', self.close)
        self._tick()

    def _check(self, parent, key, text):
        v = self.vars[key] = tk.BooleanVar(value=bool(self.cfg.get(key)))
        tk.Checkbutton(parent, text=text, variable=v, command=lambda: self._set(key, bool(v.get())), bg=BG, fg=SOFT,
                       selectcolor=PANEL, activebackground=BG, activeforeground=WHITE,
                       font=(FONT_C, 10)).pack(anchor='w')

    def _set(self, key, val):
        self.cfg[key] = val
        if key == 'on':
            self.app.ghost_buttons()
        self._save_soon()

    def _source(self):
        self._set('source', self.src.get())

    def _view(self, name):
        self.cfg.update(gc.VIEWS[name], view=name)
        for k, s in self.scales.items():
            s.set(self.cfg.get(k, 0))
        self.vars['level'].set(bool(self.cfg.get('level')))
        self._save_soon()

    def _save_soon(self):
        if self._save_after:
            self.win.after_cancel(self._save_after)
        self._save_after = self.win.after(600, self.app.save_settings)

    def _tick(self):
        try:
            if self.status.cget('text') != self.ov.status:
                self.status.configure(text=self.ov.status)
            self.win.after(400, self._tick)
        except tk.TclError:
            pass

    def show(self):
        self.win.deiconify()
        self.win.lift()

    def close(self):
        self.app.save_settings()
        self.win.withdraw()
