"""Ghost cars (a test): the window over the game that draws them, and its set-up window (ghostcars.py does the maths).

The overlay is one borderless, see-through, click-through window over the game's picture, redrawn about 60 times a
second from the game's shared memory (its own reader, so the app's 20 a second loop is not slowed down).

The camera: the game's own (cameras.json, per car), the one you are in followed by counting presses of the game's
camera key (C, or the wheel / pad button bound to it); clicking a camera in the set-up puts it right.

For development: ACR_DAILY_GHOST_TEST=1 draws in a plain 1280 x 720 window at (40, 40) instead of over the game (no
game window needed; with ACR_DAILY_REPLAY a recorded run plays as you).
"""
import ctypes
import math
import os
import struct
import time
import tkinter as tk
from ctypes import wintypes

from . import ghostcars as gc, livelink
from .telemetry import ReplaySource, SharedMemory, _Block

KEY = '#010203'                 # the see-through colour
BG, PANEL, LINE2 = '#0A0A0B', '#121214', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC = '#E30613'
GHOST_COL = '#B48CFF'           # the app's colour for your own run
LIVE_COL = '#FFB547'            # another driver, live
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
    for k in gc.LEGACY:
        cfg.pop(k, None)
    cfg['view'] = {'cockpit': 'helmet', 'chase': 'near'}.get(cfg.get('view'), cfg.get('view'))
    if cfg.get('view') not in gc.GAME_VIEWS:
        cfg['view'] = 'bonnet'
    if not isinstance(cfg.get('adjust'), dict):
        cfg['adjust'] = {}
    for k, v in gc.DEFAULTS.items():
        cfg.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return cfg


# ---------------------------------------------------------------------- the game's camera key

BINDINGS = os.path.join(os.environ.get('LOCALAPPDATA') or '', 'acr', 'Saved', 'SaveGames', 'EnhancedInputUserSettings.sav')
XINPUT_RB = 0x0200                                   # the pad's right shoulder: the game's own pad binding


def camera_bindings(path=BINDINGS):
    """-> (keyboard virtual keys, [(vendor id, product id, button)]): what steps the game's camera on this PC.
    C, unless the player bound another key; plus the wheel button they bound (saved as "CycleCamera",
    "GenericUSBController_Button11_3670_0500", device, slot)."""
    from . import autodrive
    keys, joy = [], []
    try:
        with open(path, 'rb') as f:
            strs = [s for _o, s in autodrive._fstrings(f.read())]
    except OSError:
        strs = []
    for i, s in enumerate(strs[:-1]):
        if s != 'CycleCamera':
            continue
        k = strs[i + 1]
        m = __import__('re').match(r'GenericUSBController_Button(\d+)_([0-9A-Fa-f]{4})_([0-9A-Fa-f]{4})$', k)
        if m:
            joy.append((int(m.group(2), 16), int(m.group(3), 16), int(m.group(1))))
        elif k in autodrive.VK:
            keys.append(autodrive.VK[k])
    return (keys or [autodrive.VK['C']]), joy


class _JOYINFOEX(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('dwFlags', wintypes.DWORD), ('dwXpos', wintypes.DWORD),
                ('dwYpos', wintypes.DWORD), ('dwZpos', wintypes.DWORD), ('dwRpos', wintypes.DWORD),
                ('dwUpos', wintypes.DWORD), ('dwVpos', wintypes.DWORD), ('dwButtons', wintypes.DWORD),
                ('dwButtonNumber', wintypes.DWORD), ('dwPOV', wintypes.DWORD), ('dwReserved1', wintypes.DWORD),
                ('dwReserved2', wintypes.DWORD)]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', wintypes.DWORD), ('wButtons', wintypes.WORD), ('rest', ctypes.c_byte * 10)]


class CameraKeys:
    """Counts presses of the game's camera key / buttons (only while the game is in front)."""

    def __init__(self):
        self.keys, self.joy = camera_bindings()
        self._was = {}
        self._joy_ids, self._joy_at = {}, -1e9
        try:
            self.winmm = ctypes.windll.winmm
        except Exception:
            self.winmm = None
        self.xinput = None
        for dll in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
            try:
                self.xinput = getattr(ctypes.windll, dll)
                break
            except OSError:
                continue

    def _find_joys(self):
        """Which joystick ids are the bound wheels (by vendor / product id), looked for again every 10 s."""
        now = time.monotonic()
        if now - self._joy_at < 10.0 or not self.joy or not self.winmm:
            return
        self._joy_at, self._joy_ids = now, {}
        caps = ctypes.create_string_buffer(728)
        for jid in range(16):
            if self.winmm.joyGetDevCapsW(jid, caps, 728) == 0:
                mid, pid = struct.unpack_from('<HH', caps.raw, 0)
                for vid, ppid, button in self.joy:
                    if (mid, pid) == (vid, ppid):
                        self._joy_ids.setdefault(jid, []).append(button)

    def _edge(self, key, down):
        was = self._was.get(key, False)
        self._was[key] = down
        return down and not was

    def poll(self, game_in_front):
        """-> how many presses since the last poll."""
        if not game_in_front:
            self._was = {}
            return 0
        n = 0
        for vk in self.keys:
            n += self._edge(('k', vk), bool(user32.GetAsyncKeyState(vk) & 0x8000))
        self._find_joys()
        info = _JOYINFOEX(dwSize=ctypes.sizeof(_JOYINFOEX), dwFlags=0x80)         # JOY_RETURNBUTTONS
        for jid, buttons in self._joy_ids.items():
            if self.winmm.joyGetPosEx(jid, ctypes.byref(info)) == 0:
                for b in buttons:
                    n += self._edge(('j', jid, b), bool(info.dwButtons >> (b - 1) & 1))
        if self.xinput:
            st = _XINPUT_STATE()
            for pad in range(4):
                if self.xinput.XInputGetState(pad, ctypes.byref(st)) == 0:
                    n += self._edge(('x', pad), bool(st.wButtons & XINPUT_RB))
        return n


def read_contacts(block):
    """The four tyre contact points (FL, FR, RL, RR, world) from the game's physics page, or None."""
    try:
        b = block.read()
    except Exception:
        return None
    if not b or len(b) < 468:
        return None
    pts = [struct.unpack_from('<3f', b, 420 + 12 * i) for i in range(4)]
    return pts if any(any(v) for v in pts) else None


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
        self.keys = CameraKeys() if user32 is not None else None
        self._phys, self.root, self._root_at = None, None, 0.0
        self._save_at = None
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
        live = self._live_link()
        if live is not None:
            live.feed(f, self.rec.started_at if self.rec.state == 'recording' else None)
        if f is None or not f.track:
            self.status = 'Waiting for the game'
            self._show(False)
            self._fine_timer(False)
            if self._phys is not None:
                self._phys.close()
                self._phys = None
            return 250
        self._fine_timer(True)
        self._load_ghost(f.track)
        if not self._locate():
            self.status = 'Can\'t find the game\'s window'
            self._show(False)
            return 250
        self._follow_camera()
        self._car_root(f)
        others = live.others() if live is not None else []
        if self.ghost is None and not others:
            self.status = 'No run of yours on %s yet: drive it once' % f.track + self._live_note()
            self._show(False)
            return FRAME_MS
        if not (self.test or ours_in_front(self.game)) or f.clock_ms < 0:
            self._show(False)
            return FRAME_MS
        self._show(True)
        self._draw(f, others)
        return FRAME_MS

    def _live_link(self):
        """The connection to the live relay, while Live is on (made again when the server or your name changes)."""
        want = None
        if self.cfg.get('live') and (self.cfg.get('liveServer') or '').startswith(('ws://', 'wss://')):
            want = (self.cfg['liveServer'], self.app.s.get('name') or 'Driver')
        if want != getattr(self, '_live_want', None):
            if getattr(self, 'live', None) is not None:
                self.live.close()
            self.live = livelink.LiveLink(want[0], want[1]) if want else None
            self._live_want = want
        return self.live

    def _live_note(self):
        live = getattr(self, 'live', None)
        if live is None:
            return ''
        return {'live': ' · live: on', 'connecting': ' · live: connecting', 'offline': ' · live: can\'t reach the server'}.get(
            live.state, '')

    def _follow_camera(self):
        """The game's camera key / button pressed: the next camera, like the game."""
        if self.keys is None or self.test:
            return
        n = self.keys.poll(user32.GetForegroundWindow() == self.game)
        if n and self.cfg.get('follow', True):
            views = gc.GAME_VIEWS
            self.cfg['view'] = views[(views.index(self.cfg.get('view', 'bonnet')) + n) % len(views)]
            if self._save_at:
                self.win.after_cancel(self._save_at)
            self._save_at = self.win.after(1500, self.app.save_settings)

    def _car_root(self, f):
        """Where the game's camera positions are measured from (the car's root), from the tyres, once a second."""
        now = time.monotonic()
        if now - self._root_at < 1.0 or isinstance(self.src, ReplaySource):
            return
        self._root_at = now
        if self._phys is None:
            try:
                self._phys = _Block('acpmf_physics', 480)
            except OSError:
                return
        pts = read_contacts(self._phys)
        if pts:
            fw, up = gc.car_root(pts, (f.x, f.y, f.z, f.heading, f.pitch, f.roll))
            if abs(fw) < 1.5 and -1.2 < up < -0.1:          # (a car in the air or a reset tells nothing)
                self.root = (fw, up) if self.root is None else (self.root[0] * 0.8 + fw * 0.2, self.root[1] * 0.8 + up * 0.2)

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

    def _draw(self, f, others=()):
        c, cfg, g = self.c, self.cfg, self.ghost
        c.delete('all')
        w, h = self.rect[2], self.rect[3]
        view = cfg.get('view', 'bonnet')
        mount = gc.view_cfg(cfg, f.car, self.root)
        cam = gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), mount, w, h)
        self._n += 1
        check = self._n % SIGHT_EVERY == 0
        cars = []                                       # (distance, pose, colour, label): drawn far to near
        name = 'BEST RUN' if cfg.get('source') == 'best' else 'LAST RUN'
        status = []
        if g is not None:
            early = int(float(cfg.get('earlierS') or 0) * 1000)
            my_ms = max(0, f.clock_ms)
            g_ms = my_ms + early
            passed = g.passed(f.x, f.z)
            status.append('your %s (%s)%s' % (name.lower(), fmt_ms(g.clock_ms),
                                             ', %d s earlier' % (early // 1000) if early else ''))
            if cfg.get('line') and passed is not None:  # its line on the road ahead of you, from past your own car
                ground = self.root[1] if self.root else -gc.CAR_ABOVE_GROUND
                line, run, prev = [], 0.0, (f.x, f.y, f.z)
                for p in g.path(passed, passed + 600000, 3.0, 160.0):
                    run += math.dist(prev, p)
                    prev = p
                    if run >= gc.LINE_FROM_M.get(view, 4.0):
                        line.append(cam.project((p[0], p[1] + ground, p[2])))
                for a, b in zip(line, line[1:]):
                    if a and b and -w < a[0] < 2 * w and -h < a[1] < 2 * h:
                        c.create_line(a[0], a[1], b[0], b[1], fill=LINE_COL, width=3)
            if g_ms <= g.end_ms + 10000:                # (gone once it finished a while ago)
                pose = g.at(g_ms)
                if check:
                    path = g.path(passed if passed is not None else g_ms, g_ms, 4.0) if g_ms >= (passed or 0) else []
                    self._sight = gc.in_sight(cam.pos, pose[:3], path)
                if self._sight or cfg.get('always'):
                    gap = ('  ·  ' + fmt_gap(my_ms + early - passed)) if passed is not None else ''
                    cars.append((pose, GHOST_COL, name, gap))
        now = time.monotonic()
        sights = getattr(self, '_live_sight', {})
        for d in others:                                # live: where they are right now
            pose = d.pose(now)
            if pose is None:
                continue
            ahead = d.ahead_s(f.x, f.z, now)
            if check:
                path = []
                if ahead is not None:
                    at = d.trace.passed(f.x, f.z)
                    path = d.trace.path(at, d.clock_now(now) or at, 4.0)
                sights[d.id] = gc.in_sight(cam.pos, pose[:3], path)
            if sights.get(d.id, True) or cfg.get('always'):
                gap = ('  ·  ' + fmt_gap(ahead * 1000)) if ahead is not None else ''
                cars.append((pose, LIVE_COL, d.name, gap))
        self._live_sight = sights
        if others:
            status.append('%d live on this stage' % len(others))
        self.status = 'Ghost: %s · camera: %s%s' % (', '.join(status) or 'nobody yet', gc.VIEW_NAMES.get(view, view),
                                                     self._live_note())
        drawn = []
        for pose, colour, label, gap in cars:
            dist = math.dist((f.x, f.y, f.z), pose[:3])
            if dist <= gc.MAX_DRAW_M and cam.depth(pose[:3]) >= 1.0:
                drawn.append((dist, pose, colour, label, gap))
        for dist, pose, colour, _label, _gap in sorted(drawn, key=lambda x: -x[0]):
            self._car(cam, pose, colour)                # far ones first: the nearest on top
        labels = []                                     # (the nearest car's label keeps its place; the others move up)
        for dist, pose, colour, label, gap in sorted(drawn, key=lambda x: x[0]):
            top = cam.project(gc.add(pose[:3], (0.0, 1.6, 0.0)))
            if top:
                labels.append((top, colour, '%s  ·  %d m%s' % (label, dist, gap)))
        placed = []
        for (x, y), colour, text in labels:
            half = 4.2 * len(text)
            while any(abs(x - px) < half + ph and abs(y - py) < 20 for px, py, ph in placed):
                y -= 20
            placed.append((x, y, half))
            self.c.create_text(x + 1, y + 1, text=text, fill=BG, font=(FONT_C, 14), anchor='s')
            self.c.create_text(x, y, text=text, fill=WHITE if colour == GHOST_COL else colour, font=(FONT_C, 14),
                               anchor='s')

    def _car(self, cam, pose, colour):
        c = self.c
        pts = [cam.project(p) for p in gc.box_corners(pose)]
        if all(pts):
            c.create_polygon(*[v for p in pts[:4] for v in p], fill=colour, stipple='gray25', outline='')
            for i, j in gc.BOX_EDGES:
                c.create_line(pts[i][0], pts[i][1], pts[j][0], pts[j][1], fill=colour, width=2)

    def close(self):
        self._fine_timer(False)
        if getattr(self, 'live', None) is not None:
            self.live.close()
        if self.src is not self.app.shm:
            self.src.close()


def fmt_ms(ms):
    if ms is None:
        return '–'
    return '%d:%06.3f' % (ms // 60000, (ms % 60000) / 1000.0)


# ---------------------------------------------------------------------- set-up window

TUNE = [  # key, label, from, to, step: your own changes to the camera you are in (like the game's Camera Customization)
    ('up', 'Height (m)', -1, 1, 0.02),
    ('fwd', 'Distance (m)', -3, 3, 0.05),
    ('side', 'Lateral (m)', -1, 1, 0.02),
    ('tilt', 'Pitch (°)', -10, 10, 0.25),
    ('fov', 'Field of view', -30, 30, 0.5),
]
CHECKS = [  # key, label
    ('on', 'Ghost cars on'),
    ('live', 'Live: show the others on your stage right now'),
    ('line', 'Show its line on the road'),
    ('always', 'Show through trees and hills'),
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
        lab(w, 'Your last run, driven again with you. Drive a stage once; on the next run it drives with you.',
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
        self._slider(w, 'earlierS', 'Starts earlier (s)', 0, 60, 1, self.cfg.get('earlierS', 0))
        lab(w, 'CAMERA', MUTED, 10).pack(anchor='w', pady=(10, 2))
        views = tk.Frame(w, bg=BG)
        views.pack(anchor='w')
        self.view_b = {}
        for v in gc.GAME_VIEWS:
            b = tk.Label(views, text=gc.VIEW_NAMES[v].upper(), bg=BG, fg=FG2, font=(FONT_C, 10), padx=7, pady=3,
                         cursor='hand2', highlightthickness=1, highlightbackground=LINE2)
            b.bind('<Button-1>', lambda _e, v=v: self._view(v))
            b.pack(side='left', padx=(0, 5))
            self.view_b[v] = b
        lab(w, 'Follows the game when you press C (or your camera button). Wrong one? Click the right one.',
            MUTED, 9, 'Bahnschrift').pack(anchor='w', pady=(3, 6))
        tune = tk.Frame(w, bg=BG)
        tune.pack(fill='x')
        lab(tune, 'Fine-tune this camera', MUTED, 9, 'Bahnschrift').pack(side='left')
        reset = lab(tune, 'Reset', FG2, 9, 'Bahnschrift')
        reset.configure(cursor='hand2')
        reset.bind('<Button-1>', lambda _e: self._reset())
        reset.pack(side='right')
        self.scales = {}
        for key, text, lo, hi, step in TUNE:
            self.scales[key] = self._slider(w, key, text, lo, hi, step, self._adj().get(key, 0.0), tune=True)
        for key, text in CHECKS[1:]:
            self._check(w, key, text)
        srv = tk.Frame(w, bg=BG)
        srv.pack(fill='x', pady=(4, 0))
        tk.Label(srv, text='Live server', bg=BG, fg=MUTED, font=('Bahnschrift', 9)).pack(side='left')
        self.server = tk.StringVar(value=self.cfg.get('liveServer') or '')
        e = tk.Entry(srv, textvariable=self.server, width=34, bg=PANEL, fg=SOFT, insertbackground=SOFT, relief='flat',
                     font=('Bahnschrift', 9))
        e.pack(side='right')
        self.server.trace_add('write', lambda *_a: self._set('liveServer', self.server.get().strip()))
        self.status = lab(w, '', FG2, 9, 'Bahnschrift')
        self.status.pack(anchor='w', pady=(10, 0))
        w.protocol('WM_DELETE_WINDOW', self.close)
        self._shown_view = None
        self._tick()

    def _slider(self, parent, key, text, lo, hi, step, start, tune=False):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x')
        tk.Label(row, text=text, bg=BG, fg=MUTED, font=('Bahnschrift', 9)).pack(side='left', pady=4)
        value = tk.Label(row, text='', bg=BG, fg=SOFT, font=('Bahnschrift', 9), width=6, anchor='e')
        set_ = self._tune if tune else self._set
        # (a Scale's background is its knob: light, on a lighter track than the window)
        s = tk.Scale(row, from_=lo, to=hi, resolution=step, orient='horizontal', length=230, width=12,
                     showvalue=False, bg=FG2, troughcolor=LINE2, highlightthickness=0, bd=0, sliderrelief='flat',
                     sliderlength=14, activebackground=ACC,
                     command=lambda val, k=key, v=value: (v.configure(text=val), set_(k, float(val))))
        s.set(start)
        s.pack(side='right')
        value.configure(text=s.get())                 # (set() at the slider's own start value says nothing)
        value.pack(side='right', padx=(8, 8))
        s.value_label = value
        return s

    def _adj(self):
        return self.cfg.setdefault('adjust', {}).setdefault(self.cfg.get('view', 'bonnet'), {})

    def _tune(self, key, val):
        adj = self._adj()
        if abs(val) < 1e-9:
            adj.pop(key, None)
        else:
            adj[key] = val
        self._save_soon()

    def _reset(self):
        self.cfg.setdefault('adjust', {}).pop(self.cfg.get('view', 'bonnet'), None)
        self._load_tune()
        self._save_soon()

    def _load_tune(self):
        adj = self._adj()
        for k, s in self.scales.items():
            s.set(adj.get(k, 0.0))
            s.value_label.configure(text=s.get())

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
        self.cfg['view'] = name
        self._save_soon()
        self._show_view()

    def _show_view(self):
        """The camera buttons and the fine-tune sliders follow the camera you are in (it changes with the C key)."""
        v = self.cfg.get('view', 'bonnet')
        if v == self._shown_view:
            return
        self._shown_view = v
        for name, b in self.view_b.items():
            on = name == v
            b.configure(bg=ACC if on else BG, fg=WHITE if on else FG2, highlightbackground=ACC if on else LINE2)
        self._load_tune()

    def _save_soon(self):
        if self._save_after:
            self.win.after_cancel(self._save_after)
        self._save_after = self.win.after(600, self.app.save_settings)

    def _tick(self):
        try:
            self._show_view()
            if self.status.cget('text') != self.ov.status:
                self.status.configure(text=self.ov.status)
            self.win.after(250, self._tick)
        except tk.TclError:
            pass

    def show(self):
        self.win.deiconify()
        self.win.lift()

    def close(self):
        self.app.save_settings()
        self.win.withdraw()
