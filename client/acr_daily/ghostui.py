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
import threading
import time
import tkinter as tk
from ctypes import wintypes

from . import ghostcars as gc, livelink
from .telemetry import ReplaySource, SharedMemory, _Block

KEY = '#010203'                 # the see-through colour
BG, PANEL, LINE2 = '#0A0A0B', '#121214', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC = '#E30613'
LIVE_COL = '#FFB547'            # another driver, live
FONT_C = 'Bahnschrift SemiBold Condensed'
FRAME_MS = 16
SIGHT_EVERY = 6                 # frames between two line-of-sight checks
MOD_GONE_S = 5.0                # the mod's camera not moving on for this long: the mod is not running (boxes instead)
MAX_REAL = 10                   # real cars in the game at most: the nearest (a crowded start line costs the game)
STICK_M = 50.0                  # a real car already there keeps its place unless another is this much nearer
GAP_S = 0.2                     # each driver's gap to you worked out this often (not every frame: _gap)
DRAW_OUT_M = gc.MAX_DRAW_M + 50.0   # a real car already there goes only this far away (none flickers in and out)


def open_kept(path, write=False):
    """A file kept open for good (read, or overwritten in place), the others free to read, write, replace or delete it
    meanwhile. The mod's files are never opened again each time: opening a file just changed costs a few ms (Windows'
    virus check), in the game too (mod/README.md)."""
    import msvcrt
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                              wintypes.DWORD, wintypes.HANDLE)
    h = k.CreateFileW(path, 0x80000000 | (0x40000000 if write else 0), 0x1 | 0x2 | 0x4, None,   # read (write); share all
                      4 if write else 3, 0x80, None)                                           # OPEN_ALWAYS / EXISTING
    if not h or h == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), 'cannot open', path)
    fd = msvcrt.open_osfhandle(h, os.O_RDWR if write else os.O_RDONLY)
    return os.fdopen(fd, 'r+' if write else 'r', encoding='ascii', newline='')

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
        """Which joystick ids are the bound wheels (by vendor / product id): looked for on a thread of its own, once
        a minute. A wheel's driver can fail inside Windows' joystick calls (an access violation in joyGetDevCapsW,
        seen 2026-11-10, after which the next call hung): then the wheel's button is given up for this session, and
        the window never waits on it."""
        now = time.monotonic()
        if now - self._joy_at < 60.0 or not self.joy or not self.winmm or getattr(self, '_joy_busy', False):
            return
        self._joy_at, self._joy_busy = now, True

        def look():
            found = {}
            try:
                caps = ctypes.create_string_buffer(728)
                for jid in range(16):
                    if self.winmm.joyGetDevCapsW(jid, caps, 728) == 0:
                        mid, pid = struct.unpack_from('<HH', caps.raw, 0)
                        for vid, ppid, button in self.joy:
                            if (mid, pid) == (vid, ppid):
                                found.setdefault(jid, []).append(button)
                self._joy_ids = found
            except OSError:
                self.joy, self._joy_ids = [], {}
            finally:
                self._joy_busy = False
        threading.Thread(target=look, daemon=True).start()

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
        try:
            for jid, buttons in list(self._joy_ids.items()):
                if self.winmm.joyGetPosEx(jid, ctypes.byref(info)) == 0:
                    for b in buttons:
                        n += self._edge(('j', jid, b), bool(info.dwButtons >> (b - 1) & 1))
        except OSError:                                  # (the wheel's driver failing: its button given up, _find_joys)
            self.joy, self._joy_ids = [], {}
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
        self.game, self.rect, self._rect_at, self._find_at = None, None, 0.0, 0.0
        self.status = 'Off'
        self._shown, self._n, self._sight = False, 0, True
        self._timer = False
        self.keys = CameraKeys() if user32 is not None else None
        self._phys, self.root, self._root_at = None, None, 0.0
        self._save_at = None
        self.live, self._live_want = None, None
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
            if self.live is not None:                   # (off: not on the relay either)
                self.live.close()
                self.live, self._live_want = None, None
            return 500
        try:
            f = self.src.read()
        except Exception:
            f = None
        live = self._live_link()
        if live is not None:
            live.feed(f)
        if f is None or not f.track:
            self.status = 'Waiting for the game'
            self._show(False)
            self._fine_timer(False)
            if self._phys is not None:
                self._phys.close()
                self._phys = None
            return 250
        self._fine_timer(True)
        if not self._locate():
            self.status = 'Can\'t find the game\'s window'
            self._show(False)
            return 250
        self._follow_camera()
        self._car_root(f)
        if live is not None:
            live.root = self.root                       # (sent along: where your car's model sits, for the others)
        others = live.others() if live is not None else []
        if not others:
            self.status = 'Nobody else on %s right now%s' % (f.track, self._live_note())
            if self.cfg.get('ingame'):
                self._write_ingame([])                  # (the mod takes the cars away)
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
        if (self.cfg.get('liveServer') or '').startswith(('ws://', 'wss://')):
            want = (self.cfg['liveServer'], self.app.s.get('name') or 'Driver')
        if want != getattr(self, '_live_want', None):
            if getattr(self, 'live', None) is not None:
                self.live.close()
            self.live = livelink.LiveLink(want[0], want[1], ticket=self._ticket) if want else None
            self._live_want = want
        return self.live

    def _ticket(self):
        """The ACR Daily server's ticket for the relay (on the link's own thread), or None when not signed in."""
        api = getattr(self.app, 'api', None)
        if api is None or not self.app.s.get('token'):
            return None
        return api.live_ticket()

    def _live_note(self):
        live = getattr(self, 'live', None)
        if live is None:
            return ''
        return {'live': ' · live: on', 'connecting': ' · live: connecting', 'signin': ' · live: sign in to the app first',
                'offline': ' · live: can\'t reach the server'}.get(live.state, '')

    def _follow_camera(self):
        """The game's camera key / button pressed: the next camera, like the game. (Not while the mod runs: the
        game's own camera comes from it then, nothing to count.)"""
        if self.keys is None or self.test or self._ingame_on():
            return
        n = self.keys.poll(user32.GetForegroundWindow() == self.game)
        if n and self.cfg.get('follow', True):
            views = gc.GAME_VIEWS
            self.cfg['view'] = views[(views.index(self.cfg.get('view', 'bonnet')) + n) % len(views)]
            if self._save_at:
                self.win.after_cancel(self._save_at)
            self._save_at = self.win.after(1500, self.app.save_settings)

    def _car_root(self, f):
        """Where the game's camera positions are measured from (the car's root): the car's own from the table, else
        from the tyres, once a second."""
        known = gc.car_root_of(f.car)
        if known:
            self.root = known
            return
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
        c, cfg = self.c, self.cfg
        c.delete('all')
        w, h = self.rect[2], self.rect[3]
        view = cfg.get('view', 'bonnet')
        mount = gc.view_cfg(cfg, f.car, self.root)
        cam = self._game_camera(w, h) or gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), mount, w, h)
        self._n += 1
        check = self._n % SIGHT_EVERY == 0
        cars = []                                       # (id, pose, colour, name, gap, in sight, their car)
        rates = {}                                      # id -> how the pose moves, per second (for the mod)
        status = []
        now = time.monotonic()
        sights = getattr(self, '_live_sight', {})
        for d in others:                                # live: where they are right now
            m = d.motion(now)
            if m is None:
                continue
            pose, rates['L%d' % d.id] = m
            ahead = self._gap(d, f, now)
            if check and math.dist((f.x, f.y, f.z), pose[:3]) <= DRAW_OUT_M:   # (a label only near: sight only there)
                path = []
                if ahead is not None:
                    at = d.trace.passed(f.x, f.z)
                    path = d.trace.path(at, d.clock_now(now) or at, 4.0)
                sights[d.id] = gc.in_sight(cam.pos, pose[:3], path)
            gap = ('  ·  ' + fmt_gap(ahead * 1000)) if ahead is not None else ''
            cars.append(('L%d' % d.id, pose, LIVE_COL, d.name, gap, sights.get(d.id, True), (d.car, d.root)))
        self._live_sight = sights
        gaps = getattr(self, '_gaps', {})
        if len(gaps) > 2 * len(others) + 50:            # (drivers gone: their gaps not kept)
            ids = {d.id for d in others}
            self._gaps = {k: v for k, v in gaps.items() if k in ids}
        if others:
            status.append('%d on this stage' % len(others))
        ingame = self._ingame_on()
        mode = (' · real cars in the game' if ingame else
                ' · boxes until the game mod runs (restart the game)' if cfg.get('ingame') else '')
        self.status = 'Live: %s · camera: %s%s%s' % (', '.join(status) or 'nobody yet', gc.VIEW_NAMES.get(view, view),
                                                      mode, self._live_note())
        if cfg.get('ingame'):                           # the mod puts real cars there (theirs): it is told where
            warm = {}                                   # (and which may come: made ahead while you wait, mod/README)
            for d in others:
                cls = gc.car_class(d.car)
                if cls:
                    warm[cls] = min(MAX_REAL, warm.get(cls, 0) + 1)
            self._write_ingame(self._real_cars(f, cars, rates), now, warm)
        drawn = []
        for _cid, pose, colour, label, gap, seen, _car in cars:
            dist = math.dist((f.x, f.y, f.z), pose[:3])
            if (seen or cfg.get('always')) and dist <= gc.MAX_DRAW_M and cam.depth(pose[:3]) >= 1.0:
                drawn.append((dist, pose, colour, label, gap))
        if not ingame:                                  # (real cars: never a box, even while the game loads one;
                                                        # the mod not running, e.g. just installed: boxes meanwhile)
            for dist, pose, colour, _label, _gap in sorted(drawn, key=lambda x: -x[0]):
                self._car(cam, pose, colour)            # far ones first: the nearest on top
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
            self.c.create_text(x, y, text=text, fill=colour, font=(FONT_C, 14), anchor='s')

    # ---- the ACR Daily mod in the game (mod/ACRDailyGhosts): real cars, and the game's own camera

    def _ingame_path(self, name):
        from . import settings
        return os.path.join(settings.DIR, name)

    def _gap(self, d, f, now):
        """How far ahead of you they are (s), worked out GAP_S apart for each driver (spread over the frames: with 30
        on the stage, not all at once): the label's figure needs no more."""
        gaps = self.__dict__.setdefault('_gaps', {})
        at = gaps.get(d.id)
        if at is None or now - at[0] >= GAP_S:
            at = gaps[d.id] = (now + (d.id % 7) * 0.01, d.ahead_s(f.x, f.z, now))
        return at[1]

    def _real_cars(self, f, cars, rates):
        """The cars the mod is to show: the nearest MAX_REAL within MAX_DRAW_M (one already shown: within DRAW_OUT_M,
        and STICK_M nearer than it is when ranked: no swapping back and forth). -> [(id, pose, rate, their car)]"""
        shown = getattr(self, '_real', set())
        near = []
        for cid, pose, _c, _l, _g, _s, car in cars:
            d = math.dist((f.x, f.y, f.z), pose[:3])
            if d <= gc.MAX_DRAW_M or (cid in shown and d <= DRAW_OUT_M):
                near.append((d - (STICK_M if cid in shown else 0.0), cid, pose, car))
        near.sort(key=lambda x: x[0])
        out = [(cid, pose, rates.get(cid), car) for _d, cid, pose, car in near[:MAX_REAL]]
        self._real = {x[0] for x in out}
        return out

    def _camera_text(self, now):
        """The mod's camera file, read through the file kept open (open_kept); opened again when it has not moved on
        for half a second (the mod made it again; an older mod swaps a new one in each time). None: not there."""
        fh = getattr(self, '_cam_fh', None)
        stale = now - max(getattr(self, '_cam_at', 0.0), getattr(self, '_cam_opened', 0.0)) > 0.5
        if fh is None or stale:
            if fh is not None:
                fh.close()
            self._cam_fh, self._cam_opened = None, now
            try:
                fh = self._cam_fh = open_kept(self._ingame_path('ingame-camera.txt'))
            except OSError:
                return None
        try:
            fh.seek(0)
            return fh.read()
        except (OSError, ValueError):
            fh.close()
            self._cam_fh = None
            return None

    def _game_camera(self, w, h):
        """The game's camera as the mod wrote it lately, or None (the mod not running / Real cars off). A read that
        misses (a half-written line: its two numbers differ) keeps the last one read."""
        self._cam_fresh = False
        if not self.cfg.get('ingame'):
            return None
        now = time.monotonic()
        try:
            parts = (self._camera_text(now) or '').split()
            seq, vals = int(parts[1]), [float(v) for v in parts[2:9]]
            torn = len(parts) > 9 and parts[9] != parts[1]
            if len(vals) == 7 and not torn and seq != getattr(self, '_cam_seq', None):
                self._cam_seq, self._cam_at, self._cam_vals = seq, now, vals
        except (ValueError, IndexError):
            pass
        vals = getattr(self, '_cam_vals', None)
        if vals is None or now - getattr(self, '_cam_at', 0.0) > 0.5:
            return None                                 # (not moving on: the game or the mod stopped)
        self._cam_fresh = True
        return gc.camera_from_game(vals, w, h, bool(self.cfg.get('mirror')))

    def _ingame_on(self):
        """Real cars on, and the mod seen running in the last MOD_GONE_S: a missed read of its camera, or the game
        busy for a moment, never brings the boxes back over the real cars."""
        return bool(self.cfg.get('ingame')) and time.monotonic() - getattr(self, '_cam_at', -1e9) < MOD_GONE_S

    def _write_ingame(self, cars, now=None, warm=None):
        """Where the real cars go (the game's units) and which car each one is, for the mod; a new file each time (it
        reads whole files). The car: the game's class of their car ('-': not known, the mod uses yours); placed by
        their car's root: its own from the table, else the one their app sent, else yours (it shows your car).
        With when (now, this PC's clock) and how each moves (per second): the mod carries them on every frame."""
        seq = self._ingame_seq = getattr(self, '_ingame_seq', 0) + 1
        lines = ['ACRDG 2 %d %.4f' % (seq, time.monotonic() if now is None else now)]
        for cid, pose, rate, (car, root) in cars:
            at, move = gc.ue_motion(pose, rate or (0.0,) * 6, gc.car_root_of(car) or root or self.root)
            lines.append('%s %s %.1f %.1f %.1f %.3f %.3f %.3f %.1f %.1f %.1f %.2f %.2f %.2f %d'
                         % ((cid, gc.car_class(car) or '-') + at + move + (seq,)))
        for cls, n in sorted((warm or {}).items()):     # (the drivers' models on the stage: the mod makes them ahead)
            lines.append('warm %s %d %d' % (cls, n, seq))
        lines.append('end %d' % seq)                  # (the update's number on each line: a half-read one is told)
        try:
            fh = getattr(self, '_ghosts_fh', None)
            if fh is None:                              # (kept open, overwritten in place: open_kept)
                fh = self._ghosts_fh = open_kept(self._ingame_path('ingame-ghosts.txt'), write=True)
            fh.seek(0)
            fh.write('\n'.join(lines) + '\n')
            fh.truncate()
            fh.flush()
        except (OSError, ValueError):
            fh = getattr(self, '_ghosts_fh', None)
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
            self._ghosts_fh = None                      # (opened again next time)

    def _car(self, cam, pose, colour):
        c = self.c
        pts = [cam.project(p) for p in gc.box_corners(pose)]
        if all(pts):
            c.create_polygon(*[v for p in pts[:4] for v in p], fill=colour, stipple='gray25', outline='')
            for i, j in gc.BOX_EDGES:
                c.create_line(pts[i][0], pts[i][1], pts[j][0], pts[j][1], fill=colour, width=2)

    def close(self):
        self._fine_timer(False)
        for name in ('_ghosts_fh', '_cam_fh'):
            fh = getattr(self, name, None)
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
                setattr(self, name, None)
        if getattr(self, 'live', None) is not None:
            self.live.close()
        if self.src is not self.app.shm:
            self.src.close()




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
    ('ingame', 'Real cars in the game (the app adds the game mod)'),
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
        lab(w, 'The other drivers on your stage, where they are right now.',
            FG2, 9, 'Bahnschrift').pack(anchor='w', pady=(2, 10))
        self.vars = {}
        for key, text in CHECKS[:1]:
            self._check(w, key, text)
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
            if key == 'ingame':
                self.mod_note = lab(w, '', MUTED, 9, 'Bahnschrift')
                self.mod_note.pack(anchor='w', padx=(24, 0))
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
        if key in ('on', 'ingame'):
            self.app.poke_game_mod()                   # (the game mod goes in or out with these)
        self._save_soon()

    def _mod_note(self):
        """The game mod's state, in a few words, under "Real cars in the game"."""
        keeper = getattr(self.app, 'gamemod', None)
        if keeper is None or not (self.cfg.get('on') and self.cfg.get('ingame')):
            return ''
        if keeper.status == 'ready' and find_game_window() and not self.ov._ingame_on():
            return 'Game mod installed: restart the game to see real cars.'
        return keeper.note()

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
            self._mod_t = getattr(self, '_mod_t', 0) + 1
            if self._mod_t % 8 == 1:                    # (every 2 s)
                note = self._mod_note()
                if self.mod_note.cget('text') != note:
                    self.mod_note.configure(text=note)
            self.win.after(250, self._tick)
        except tk.TclError:
            pass

    def show(self):
        self.win.deiconify()
        self.win.lift()

    def close(self):
        self.app.save_settings()
        self.win.withdraw()
