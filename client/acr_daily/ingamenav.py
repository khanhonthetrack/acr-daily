"""The game's own menu controls in ACR DAILY's pages (0.2): the player's wheel (or other controller) buttons bound to the
game's menu actions work there too (the user, 20 Nov 2026: "so I can use my wheel to change tabs").

The bindings are the game's (EnhancedInputUserSettings.sav: "Select", "Back", "Up", "Down", "Left", "Right",
"TabLeftWheel", "TabRightWheel", each a "GenericUSBController_Button<n>_<vendor>_<product>"); a game pad's shoulders
(LB / RB) change tabs and B goes back (the pad's stick, D-pad and A move and press in the pages by themselves: Slate's
own navigation). Polled while the pages are on screen and the game is in front:

    up / down / left / right / select   the arrow keys / Enter sent to the game (the pages move and press with them)
    back                                a question closed, then the pages (ingameapp.InGameApp.back)
    tab_left / tab_right                the tab before / after (Q / E on the keyboard: the mod, appui.lua)
"""
import ctypes
import re
import struct
import threading
import time
from ctypes import wintypes

from . import autodrive

ACTIONS = {'Select': 'select', 'Back': 'back', 'Up': 'up', 'Down': 'down', 'Left': 'left', 'Right': 'right',
           'TabLeftWheel': 'tab_left', 'TabRightWheel': 'tab_right'}
KEYS = {'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27, 'select': 0x0D}
EXTENDED = {0x26, 0x28, 0x25, 0x27}
PAD = {0x0100: 'tab_left', 0x0200: 'tab_right', 0x2000: 'back', 0x1000: 'pad_a'}   # XInput LB, RB, B, A
# A wheel's D-pad: Windows reports it as a POV hat (its direction in hundredths of a degree) while the game numbers it as
# buttons of its own ("Up" -> Button22 on the user's wheel, 21 Nov 2026: the arrows did nothing in the pages). So the hat
# is read too, on a controller with menu buttons bound: 0 up, 9000 right, 18000 down, 27000 left.
POV_DIRS = ((0, 'up'), (9000, 'right'), (18000, 'down'), (27000, 'left'))
PAD_LOOK_S = 3.0
JOY_RE = re.compile(r'GenericUSBController_Button(\d+)_([0-9A-Fa-f]{4})_([0-9A-Fa-f]{4})$')


def bindings(path=None):
    """-> [(action, vendor id, product id, button)] the player bound to the game's menu actions on a wheel or another
    controller (not the keyboard: its keys reach the pages as they are)."""
    from .ghostui import BINDINGS
    try:
        with open(path or BINDINGS, 'rb') as f:
            strs = [s for _o, s in autodrive._fstrings(f.read())]
    except OSError:
        return []
    out = []
    for i, s in enumerate(strs[:-1]):
        a = ACTIONS.get(s)
        m = JOY_RE.match(strs[i + 1]) if a else None
        if m:
            out.append((a, int(m.group(2), 16), int(m.group(3), 16), int(m.group(1))))
    return out


class _JOYINFOEX(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('dwFlags', wintypes.DWORD), ('dwXpos', wintypes.DWORD),
                ('dwYpos', wintypes.DWORD), ('dwZpos', wintypes.DWORD), ('dwRpos', wintypes.DWORD),
                ('dwUpos', wintypes.DWORD), ('dwVpos', wintypes.DWORD), ('dwButtons', wintypes.DWORD),
                ('dwButtonNumber', wintypes.DWORD), ('dwPOV', wintypes.DWORD), ('dwReserved1', wintypes.DWORD),
                ('dwReserved2', wintypes.DWORD)]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', wintypes.DWORD), ('wButtons', wintypes.WORD), ('rest', ctypes.c_byte * 10)]


class MenuInputs:
    """poll() -> the menu actions pressed since the last poll, in order. As ghostui.CameraKeys: the joystick ids found on
    a thread of their own once a minute (a wheel's driver once failed inside joyGetDevCapsW and hung the next call)."""

    def __init__(self, binds=None):
        self.binds = bindings() if binds is None else binds
        self._was = {}
        self._joy_ids, self._joy_at, self._joy_busy = {}, -1e9, False
        try:
            self.winmm = ctypes.windll.winmm
        except Exception:
            self.winmm = None
        self.xinput = None
        self._pad_next = {}
        for dll in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
            try:
                self.xinput = getattr(ctypes.windll, dll)
                break
            except OSError:
                continue

    def _find_joys(self):
        now = time.monotonic()
        if now - self._joy_at < 60.0 or not self.binds or not self.winmm or self._joy_busy:
            return
        self._joy_at, self._joy_busy = now, True

        def look():
            found = {}
            try:
                caps = ctypes.create_string_buffer(728)
                for jid in range(16):
                    if self.winmm.joyGetDevCapsW(jid, caps, 728) == 0:
                        mid, pid = struct.unpack_from('<HH', caps.raw, 0)
                        for action, vid, ppid, button in self.binds:
                            if (mid, pid) == (vid, ppid):
                                found.setdefault(jid, []).append((action, button))
                self._joy_ids = found
            except OSError:
                self.binds, self._joy_ids = [], {}
            finally:
                self._joy_busy = False
        threading.Thread(target=look, daemon=True).start()

    def _edge(self, key, down):
        was = self._was.get(key, False)
        self._was[key] = down
        return down and not was

    def _pov(self, jid, pov):
        """The hat's direction now -> [the direction just pressed] (none centred: 0xFFFF; diagonals count as the nearer
        one)."""
        held = None
        if pov <= 36000:
            held = min(POV_DIRS, key=lambda d: min(abs(pov - d[0]), 36000 - abs(pov - d[0])))[1]
        out = []
        for _deg, d in POV_DIRS:
            if self._edge(('pov', jid, d), held == d):
                out.append(d)
        return out

    def poll(self):
        out = []
        self._find_joys()
        info = _JOYINFOEX(dwSize=ctypes.sizeof(_JOYINFOEX), dwFlags=0x80 | 0x40)   # JOY_RETURNBUTTONS | JOY_RETURNPOV
        try:
            for jid, binds in list(self._joy_ids.items()):
                if self.winmm.joyGetPosEx(jid, ctypes.byref(info)) == 0:
                    for action, b in binds:
                        if b <= 32 and self._edge(('j', jid, b, action), bool(info.dwButtons >> (b - 1) & 1)):
                            out.append(action)
                    out.extend(self._pov(jid, info.dwPOV))
        except OSError:
            self.binds, self._joy_ids = [], {}
        if self.xinput:
            st, now = _XINPUT_STATE(), time.monotonic()
            for pad in range(4):
                if now < self._pad_next.get(pad, 0.0):
                    continue
                if self.xinput.XInputGetState(pad, ctypes.byref(st)) == 0:
                    for bit, action in PAD.items():
                        if self._edge(('x', pad, bit), bool(st.wButtons & bit)):
                            out.append(action)
                else:
                    self._pad_next[pad] = now + PAD_LOOK_S
        seen, once = set(), []                 # (a wheel telling one press both as a button and as its hat: once)
        for a in out:
            if a not in seen:
                seen.add(a)
                once.append(a)
        return once

    def reset(self):
        """(the pages away, the game behind: what is held now isn't a press when they come back)"""
        self._was = {}


def press_key(vk):
    """A key pressed and let go, to the window in front (the game: its pages move / press with it)."""
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk, 0)
    flag = 0x1 if vk in EXTENDED else 0
    user32.keybd_event(vk, scan, flag, 0)
    user32.keybd_event(vk, scan, flag | 0x2, 0)


def game_in_front():
    from . import ghostui
    try:
        h = ghostui.find_game_window()
        return bool(h) and ctypes.windll.user32.GetForegroundWindow() == h
    except Exception:
        return False
