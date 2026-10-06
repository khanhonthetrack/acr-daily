"""Auto-drive: after DRIVE starts the game, press the menu keys a player would, up to the Service Park, and stop there.
The player presses START STAGE themselves (their first run of a daily is the one that counts).

    title screen     -> Select  (any key works there; the player's Select key)
    HOME tab         -> E       (the game's tab-right key; not rebindable on a keyboard)
    RACING tab       -> Select  (RALLY, the first tile, is highlighted; another tile: Up until it is)
    RALLY            -> Select  (SINGLE RALLY STAGE, the first tile; RALLY WEEKEND highlighted: Left first)
    stage set-up     -> Select  (START RACE; stage, car and conditions are already the daily's: saveslot.py)
    SERVICE PARK     -> stop    (START STAGE is highlighted)

Safety, in order of importance:
- every key is for a screen recognised just before it (twice in a row), so a pop-up, news, a game update that moved
  the menu, a different screen size: nothing is recognised and nothing is pressed. Screens are told apart by where
  the game's red highlight is, so the game's language does not matter;
- once it has pressed a key, the player touching the keyboard or mouse stops it at once (before that, it waits
  until they have not for QUIET_S), so does the game leaving the foreground (no key ever lands in another window,
  the game window is never brought to the front);
- one key per screen (Up / Left may repeat on the screen they fix, a few times), at most MAX_KEYS in all,
  everything within TIMEOUT_S;
- the Select, Up and Left keys come from the player's own bindings (EnhancedInputUserSettings.sav), the Exit Game key is never
  pressed, and the screenshots stay in memory: nothing is saved or sent.
"""
import ctypes
import os
import struct
import threading
import time
from ctypes import wintypes

from . import saveslot, settings

try:
    from PIL import ImageGrab
except ImportError:      # pragma: no cover - the exe bundles Pillow
    ImageGrab = None

BINDINGS = os.path.join(os.environ.get('LOCALAPPDATA') or '', 'acr', 'Saved', 'SaveGames', 'EnhancedInputUserSettings.sav')
TIMEOUT_S = 240          # the whole thing: game start (~45 s) + menus + stage loading (~25 s), with room to spare
START_WAIT_S = 150       # for the title screen or the main menu to appear after DRIVE
STEP_WAIT_S = 12         # after a key, for the next screen (the stage set-up -> Service Park step loads the stage)
LOAD_WAIT_S = 90
MAX_KEYS = 10
QUIET_S = 1.5            # no key while the player touched the keyboard or mouse in the last this many seconds
WATCH_S = 0.025          # how often the player's keyboard and mouse are looked at
POLL_S = 0.5

# ---- screens: where the game's red highlight is
# Regions in the menu's own units: the menus are sized by a 16:9 box (the whole height on wider screens, the whole
# width on narrower ones) and centred left to right, so a point is (x - width / 2) / box height, y / box height
# (narrower screens: see screen()). Measured on a 1280 x 536 capture (21:9); R(x0, y0, x1, y1) takes those pixels.
H0, CX0 = 536.0, 640.0


def R(x0, y0, x1, y1):
    return ((x0 - CX0) / H0, y0 / H0, (x1 - CX0) / H0, y1 / H0)


# Rally Weekend's set-up looks much the same, with a white "Rally · Days" box on the stage picture: never that one
NOT_WEEKEND = (R(570, 181, 628, 195), 'not white')
ON, OFF = 0.7, 0.2       # a region is "red" with at least ON of its pixels red, "not red" with at most OFF
SCREENS = [              # (name, [(region, 'red' | 'not')]), the first full match wins
    ('title',  [(R(500, 71, 790, 110), 'logo'), (R(500, 118, 790, 130), 'not')]),   # the big ASSETTO CORSA RALLY logo
    ('park',   [(R(224, 76, 240, 96), 'red'), (R(470, 76, 490, 96), 'red'), (R(620, 440, 660, 460), 'not')]),
    ('home',   [(R(215, 77, 221, 89), 'red'), (R(263, 77, 268, 89), 'not')]),          # E works whatever tile is lit
    ('racing', [(R(263, 77, 268, 89), 'red'), (R(215, 77, 221, 89), 'not'), (R(228, 246, 242, 262), 'red')]),
    ('racing_other', [(R(263, 77, 268, 89), 'red'), (R(215, 77, 221, 89), 'not'), (R(228, 246, 242, 262), 'not')]),
    # START RACE is red whatever is selected: nothing else may be lit (the two CHANGE bars, the three settings bars)
    ('setup',  [NOT_WEEKEND, (R(230, 432, 250, 462), 'red'), (R(1030, 432, 1050, 462), 'red'), (R(620, 429, 660, 436), 'red'),
                (R(230, 266, 280, 282), 'not'), (R(660, 266, 710, 282), 'not'), (R(225, 390, 260, 408), 'not'),
                (R(510, 390, 545, 408), 'not'), (R(795, 390, 830, 408), 'not')]),
    # the mouse pointer over another button lights that one (START RACE turns white): Down until START RACE is lit
    ('setup_other', [(R(230, 432, 250, 462), 'white'), (R(1030, 432, 1050, 462), 'white'), NOT_WEEKEND,
                     ([R(230, 266, 280, 282), R(660, 266, 710, 282), R(225, 390, 260, 408), R(510, 390, 545, 408),
                       R(795, 390, 830, 408)], 'any red')]),
    ('rally',  [(R(226, 452, 244, 463), 'red'), (R(1000, 452, 1040, 463), 'not')]),
    ('rally_right', [(R(1000, 452, 1040, 463), 'red'), (R(226, 452, 244, 463), 'not')]),
]
GUARD = [(R(213, 20, 600, 30), 'not'), (R(560, 360, 720, 380), 'not')]   # never red on any of them
KEY_FOR = {'title': 'select', 'home': 'tab_right', 'racing': 'select', 'racing_other': 'up', 'rally': 'select',
           'rally_right': 'left', 'setup_other': 'down', 'setup': 'select'}
REPEAT = {'racing_other': 3, 'setup_other': 3}   # screens a key may be pressed on again (Up from the 3rd tile: twice)


def _red(p):
    return p[0] > 165 and p[1] < 80 and p[2] < 80


def _white(p):
    return p[0] > 200 and p[1] > 200 and p[2] > 200


def _frac(img, region, test=None):
    """Share of red (or test()) pixels in a region (menu units) of an RGB image."""
    w, h = img.size
    u0, v0, u1, v1 = region
    x0, x1 = int(w / 2 + u0 * h), int(w / 2 + u1 * h)
    y0, y1 = int(v0 * h), int(v1 * h)
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
        return None
    px = img.crop((x0, y0, x1, y1)).getdata()
    test = test or _red
    return sum(1 for p in px if test(p)) / float(len(px))


MARGIN = 60.0 / H0       # the pages' top and bottom margins, in box heights: the same on every screen shape


def _unstretch(img, bh):
    """A page laid out over a taller window (narrower than 16:9) as it looks in a 16:9 box of height bh: the top and
    bottom margins are the same, the part between them is stretched; squeeze that part back."""
    w, h = img.size
    m = int(MARGIN * bh)
    out = img.resize((w, bh))                  # the margins are kept below, the middle is squeezed
    out.paste(img.crop((0, 0, w, m)), (0, 0))
    out.paste(img.crop((0, m, w, h - m)).resize((w, bh - 2 * m)), (0, m))
    out.paste(img.crop((0, h - m, w, h)), (0, bh - m))
    return out


def screen(img):
    """-> which menu screen the capture shows ('title', 'home', 'racing', 'rally', 'setup', 'park') or None."""
    img = img.convert('RGB')
    w, h = img.size
    views = [img]
    if w * 9 < h * 16:                         # narrower than 16:9 (16:10, 4:3), the game lays a page out either
        bh = int(w * 9 / 16)                   # in a 16:9 box fitted to the width, centred up and down (main menu)
        views = [img.crop((0, (h - bh) // 2, w, (h - bh) // 2 + bh)),
                 _unstretch(img, bh)]          # or over the whole height between fixed margins (the other pages)
    for view in views:
        if view.size[1] > H0 * 1.2:            # same scale as the measurements: quicker, and the same pixel sizes
            view = view.resize((max(1, int(view.size[0] * H0 / view.size[1])), int(H0)))
        for name, checks in SCREENS:
            ok = True
            for region, want in checks + GUARD:
                if want == 'any red':             # at least one of these regions is red
                    fs = [_frac(view, r) for r in region]
                    if None in fs or max(fs) < ON:
                        ok = False
                        break
                    continue
                f = _frac(view, region, _white if want in ('white', 'not white') else _red)
                if f is None or (want in ('red', 'white') and f < ON) or (want in ('not', 'not white') and f > OFF) or \
                        (want == 'logo' and f < 0.25):
                    ok = False
                    break
            if ok:
                return name
    return None


# ---- the player's keys
# UE key names -> Windows virtual keys (the keyboard keys a menu could sensibly be on)
VK = {'Enter': 0x0D, 'SpaceBar': 0x20, 'Escape': 0x1B, 'Tab': 0x09, 'BackSpace': 0x08,
      'Up': 0x26, 'Down': 0x28, 'Left': 0x25, 'Right': 0x27,
      'NumPadZero': 0x60, 'NumPadOne': 0x61, 'NumPadTwo': 0x62, 'NumPadThree': 0x63, 'NumPadFour': 0x64,
      'NumPadFive': 0x65, 'NumPadSix': 0x66, 'NumPadSeven': 0x67, 'NumPadEight': 0x68, 'NumPadNine': 0x69}
VK.update({c: ord(c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'})
VK.update({n: 0x30 + i for i, n in enumerate(['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine'])})
EXTENDED = {0x26, 0x28, 0x25, 0x27}
DEFAULT_KEYS = {'select': 'Enter', 'tab_right': 'E', 'up': 'Up', 'down': 'Down', 'left': 'Left'}   # the game's
REBINDABLE = {'select': 'SelectKeyboard', 'up': 'UpKeyboard', 'down': 'DownKeyboard', 'left': 'LeftKeyboard'}  # not tabs
NEVER = {'Y'}                                            # Exit Game on the main menu


def _fstrings(b):
    """Every ASCII FString in a GVAS file, in order: [(offset, text)]."""
    out, o = [], 0
    while o + 5 <= len(b):
        n = struct.unpack_from('<i', b, o)[0]
        if 2 <= n <= 200 and o + 4 + n <= len(b) and b[o + 4 + n - 1] == 0:
            s = b[o + 4:o + 4 + n - 1]
            if all(32 <= c < 127 for c in s):
                out.append((o, s.decode('ascii')))
                o += 4 + n
                continue
        o += 1
    return out


def player_keys(path=BINDINGS):
    """-> {'select', 'tab_right', 'up', 'left': key name}: the game's defaults, with the player's own keyboard keys
    where they changed them (each binding is saved as: mapping name, key, device, slot). Raises ValueError on a key
    this can't press."""
    keys = dict(DEFAULT_KEYS)
    try:
        with open(path, 'rb') as f:
            b = f.read()
    except OSError:
        return keys
    strs = [s for _o, s in _fstrings(b)]
    names = {v: k for k, v in REBINDABLE.items()}
    for i, s in enumerate(strs[:-1]):
        if s in names and strs[i + 1] not in ('None', ''):
            keys[names[s]] = strs[i + 1]
    for what, k in keys.items():
        if k not in VK or k in NEVER:
            raise ValueError('your menu %s key (%s) is one auto-drive does not press' % (what.replace('_', ' '), k))
    return keys


KEY_WORDS = {'SpaceBar': 'Space', 'Up': 'Up arrow', 'Down': 'Down arrow', 'Left': 'Left arrow', 'Right': 'Right arrow',
             'BackSpace': 'Backspace'}


def describe_keys(keys):
    """player_keys() in words, for the player: 'Enter to select, E for the Racing tab, ...'."""
    say = lambda k: KEY_WORDS.get(k, k[len('NumPad'):] + ' (numpad)' if k.startswith('NumPad') else k)
    return '%s to select, %s for the Racing tab, %s, %s and %s to move the highlight onto the right button' % (
        say(keys['select']), say(keys['tab_right']), say(keys['up']), say(keys['down']), say(keys['left']))


# ---- Windows: the game window, captures, keys, the player's own input
user32 = ctypes.windll.user32 if os.name == 'nt' else None


class _KI(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', _KI), ('pad', ctypes.c_byte * 32)]
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', _U)]




def game_window():
    pids = set(saveslot.game_pids())
    if not pids:
        return None
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(h):
            r = wintypes.RECT()
            user32.GetClientRect(h, ctypes.byref(r))
            if r.right > 400 and r.bottom > 300:
                found.append(h)
        return True
    user32.EnumWindows(proc(each), 0)
    return found[0] if found else None


def capture(hwnd):
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return ImageGrab.grab(bbox=(p.x, p.y, p.x + r.right, p.y + r.bottom), all_screens=True)


class InputWatch:
    """The player's own keyboard and mouse: the cursor moving, a mouse button or any key down, sampled every
    WATCH_S on its own thread. (Windows' "last input" time is no use: a wheel or pedals can refresh it non-stop.)
    touched: monotonic time of the last touch; the key auto-drive is pressing does not count."""

    def __init__(self):
        self.touched = time.monotonic()
        self.ours = None                      # the virtual key being pressed by auto-drive right now
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        last = None
        while self.running:
            p = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(p))
            if last is not None and (abs(p.x - last[0]) > 2 or abs(p.y - last[1]) > 2):
                self.touched = time.monotonic()
            last = (p.x, p.y)
            ours = self.ours
            for vk in range(0x01, 0xFF):
                if vk != ours and vk not in (0x10, 0x11, 0x12) and user32.GetAsyncKeyState(vk) & 0x8000:
                    self.touched = time.monotonic()
                    break
            time.sleep(WATCH_S)

    def stop(self):
        self.running = False


def press(name, watch=None):
    vk = VK[name]
    if watch:
        watch.ours = vk
    scan = user32.MapVirtualKeyW(vk, 0)          # the scan code of this layout (AZERTY etc.)
    for up in (0, 2):
        flags = 0x0008 | up | (0x0001 if vk in EXTENDED else 0)
        i = _INPUT(type=1)
        i.ki = _KI(vk, scan, flags, 0, 0)
        user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))
        time.sleep(0.08)
    if watch:
        time.sleep(0.15)                       # until the key-up has gone through
        watch.ours = None


# ---- the run
class AutoDrive:
    """One trip from the game's start to the Service Park, on its own thread. say(text) reports progress (called on
    that thread); done is set when it ends (state: 'park', 'stopped' or 'failed')."""

    def __init__(self, say):
        self.say = say
        self.state = 'starting'
        self.cancelled = False
        self.done = threading.Event()
        self.trail = []                  # what it saw and did, for the record kept when it stops (record())
        self.last_img = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def cancel(self):
        self.cancelled = True

    def _end(self, state, text):
        self.state = state
        self._note(text)
        if state != 'park':
            self.record()
        self.say(text)
        self.done.set()

    def _note(self, text):
        self.trail.append('%s  %s' % (time.strftime('%H:%M:%S'), text))

    def record(self, folder=None):
        """When it stops short: the last game screen it saw and its steps, on this PC only (in the app's folder:
        autodrive-last.jpg, autodrive-last.txt), so a report can say exactly where it stopped. Nothing is sent."""
        folder = folder or settings.DIR
        try:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, 'autodrive-last.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.trail) + '\n')
            if self.last_img is not None:
                img = self.last_img.convert('RGB')
                if img.size[0] > 1600:
                    img = img.resize((1600, max(1, int(img.size[1] * 1600 / img.size[0]))))
                img.save(os.path.join(folder, 'autodrive-last.jpg'), quality=85)
        except Exception:
            pass                         # a record is a nice-to-have, never a reason to fail

    def _run(self):
        self.watch = InputWatch() if user32 is not None else None
        try:
            self._drive()
        except Exception as e:           # never take the app down
            self._end('failed', 'Auto-drive stopped (%s). Carry on in the game by hand.' % e)
        finally:
            if self.watch:
                self.watch.stop()

    def _drive(self):
        if ImageGrab is None or user32 is None:
            return self._end('failed', 'Auto-drive is not available on this PC.')
        try:
            keys = player_keys()
        except ValueError as e:
            return self._end('failed', 'Auto-drive is off for you: %s. Carry on in the game by hand.' % e)
        t0 = time.monotonic()
        pressed_on, seen, keys_sent, repeats = None, [], 0, 0   # pressed_on: the screen the last key was pressed on
        waited_since, pressed_at = time.monotonic(), None
        self.say('Auto-drive: waiting for the game. Touch the keyboard or mouse to take over.')
        while True:
            time.sleep(POLL_S)
            now = time.monotonic()
            if self.cancelled:
                return self._end('stopped', 'Auto-drive stopped.')
            # (after START RACE no key follows, and the game moves the pointer itself as the stage loads)
            if pressed_at is not None and pressed_on != 'setup' and self.watch.touched > pressed_at:
                return self._end('stopped', 'You took over: auto-drive stopped.')   # (before the first key: free)
            if now - t0 > TIMEOUT_S:
                return self._end('failed', 'Auto-drive gave up (took too long). Carry on in the game by hand.')
            hwnd = game_window()
            if not hwnd:
                if keys_sent:
                    return self._end('failed', 'The game closed: auto-drive stopped.')
                if now - waited_since > START_WAIT_S:
                    return self._end('failed', 'The game did not start: auto-drive stopped.')
                continue
            if user32.GetForegroundWindow() != hwnd:
                if keys_sent:
                    return self._end('stopped', 'The game is not in front any more: auto-drive stopped.')
                continue                          # never bring it to the front: wait for the player / the game
            self.last_img = capture(hwnd)
            s = screen(self.last_img)
            if not seen or seen[-1] != s:
                self._note('screen: %s' % (s or 'not recognised'))
            seen = (seen + [s])[-2:]
            if s == 'park':
                return self._end('park', 'On the Service Park: press START STAGE when you are ready. Good luck!')
            step = decide(pressed_on, seen, now - waited_since, repeats)
            if step == 'wait':
                continue
            if step != 'press':
                return self._end('failed', step + ' Carry on in the game by hand.')
            if time.monotonic() - self.watch.touched < QUIET_S:
                continue                          # the player touched something just now: not while they do
            if keys_sent >= MAX_KEYS:
                return self._end('failed', 'Auto-drive stopped (too many steps). Carry on in the game by hand.')
            self.say('Auto-drive: ' + LABEL[s] + '...')
            self._note('key: %s (%s)' % (keys[KEY_FOR[s]], KEY_FOR[s]))
            press(keys[KEY_FOR[s]], self.watch)
            pressed_at = time.monotonic()
            keys_sent += 1
            repeats = repeats + 1 if s == pressed_on else 0
            pressed_on, seen, waited_since = s, [], time.monotonic()


LABEL = {'title': 'title screen', 'home': 'main menu', 'racing': 'Racing', 'racing_other': 'Racing, to the RALLY tile',
         'rally': 'Rally', 'rally_right': 'Rally, to SINGLE RALLY STAGE', 'setup_other': 'Single Rally Stage, to START RACE',
         'setup': 'Single Rally Stage, START RACE'}
# what may follow each key (the main menu opens on the tab and tile the player left it on)
RACING = {'racing', 'racing_other'}
SETUP = {'setup', 'setup_other'}
ALLOWED = {None: {'title', 'home'} | RACING, 'title': {'home'} | RACING, 'home': RACING, 'racing': {'rally', 'rally_right'},
           'racing_other': RACING, 'rally': SETUP, 'rally_right': {'rally'}, 'setup_other': SETUP, 'setup': {'park'}}


def decide(pressed_on, seen, waited, repeats=0):
    """-> 'press' (the last two captures show the same expected screen), 'wait', or why to stop.
    pressed_on: the screen the last key was pressed on (None before the first); waited: seconds since then;
    repeats: how many times in a row the key was pressed on that screen already."""
    s = seen[-1] if seen else None
    limit = START_WAIT_S if pressed_on is None else (LOAD_WAIT_S if pressed_on == 'setup' else STEP_WAIT_S)
    if len(seen) < 2 or seen[0] != s or s is None:          # changing, fading, loading, or not a known screen
        return 'Auto-drive did not recognise the game screen, so it stopped.' if waited > limit else 'wait'
    if s == pressed_on:                                     # the key has not done anything (yet)
        if s in REPEAT and repeats + 1 < REPEAT[s] and waited > 1.0:
            return 'press'                                  # Up / Down moved one button: one more
        return 'The game did not react as expected: auto-drive stopped.' if waited > STEP_WAIT_S else 'wait'
    if s not in ALLOWED[pressed_on]:
        return 'The game showed an unexpected screen (%s): auto-drive stopped.' % LABEL.get(s, s)
    return 'press'
