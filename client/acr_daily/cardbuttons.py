"""A wheel's or a game pad's own buttons for the cards in the game (the comment after a run, the next daily): the user,
24 Nov 2026, "it would be nice if ... you could bind the keys for comment and closing with actual wheel or gamepad".

SETTINGS › Timer › Wheel / pad buttons: SET, then a press of the button wanted (any controller: a wheel, a button box,
a pad) binds it to that action. While a card is up in the game, a press of it does the action: COMMENT opens the box (its
key pressed for the game mod, hud.lua), a second press sends what is written (Enter); CLOSE closes the card (or the box
while writing in it). The buttons' ids: 'j:<vid>:<pid>:<n>' (a controller's button n, as Windows numbers them) or
'x:<bit>' (an XInput pad's button).
"""
import ctypes
import struct
import threading
import time

from .ingamenav import _JOYINFOEX, _XINPUT_STATE

ACTIONS = ('comment', 'close')
CAPTURE_S = 10.0                      # SET waits this long for a press
XNAMES = {0x1000: 'A', 0x2000: 'B', 0x4000: 'X', 0x8000: 'Y', 0x0100: 'LB', 0x0200: 'RB', 0x0010: 'START',
          0x0020: 'BACK', 0x0040: 'L3', 0x0080: 'R3'}


def name(bid):
    """A button's id as a person reads it: 'PAD A', 'BUTTON 7'."""
    if not bid:
        return '–'
    p = str(bid).split(':')
    if p[0] == 'x' and len(p) == 2:
        try:
            return 'PAD ' + XNAMES.get(int(p[1]), p[1])
        except ValueError:
            return 'PAD'
    if p[0] == 'j' and len(p) == 4:
        return 'BUTTON %s' % p[3]
    return str(bid)


class Buttons:
    """poll() -> the ids of the buttons pressed since the last poll (every controller, every button)."""

    def __init__(self):
        self._was = set()
        self._ids, self._ids_at, self._busy = {}, -1e9, False
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

    def _find(self):
        now = time.monotonic()
        if now - self._ids_at < 60.0 or not self.winmm or self._busy:
            return
        self._ids_at, self._busy = now, True

        def look():                          # (on a thread: a wheel's driver once hung inside joyGetDevCapsW)
            found = {}
            try:
                caps = ctypes.create_string_buffer(728)
                for jid in range(16):
                    if self.winmm.joyGetDevCapsW(jid, caps, 728) == 0:
                        mid, pid = struct.unpack_from('<HH', caps.raw, 0)
                        found[jid] = '%04x:%04x' % (mid, pid)
                self._ids = found
            except OSError:
                self._ids = {}
            finally:
                self._busy = False
        threading.Thread(target=look, daemon=True).start()

    def held(self):
        """Every button held now: {id}."""
        self._find()
        out = set()
        if self.winmm:
            info = _JOYINFOEX(dwSize=ctypes.sizeof(_JOYINFOEX), dwFlags=0x80)   # JOY_RETURNBUTTONS
            for jid, dev in list(self._ids.items()):
                try:
                    if self.winmm.joyGetPosEx(jid, ctypes.byref(info)) != 0:
                        continue
                except OSError:
                    continue
                for i in range(32):
                    if info.dwButtons >> i & 1:
                        out.add('j:%s:%d' % (dev, i + 1))
        if self.xinput:
            st = _XINPUT_STATE()
            for pad in range(4):
                try:
                    if self.xinput.XInputGetState(pad, ctypes.byref(st)) == 0:
                        for bit in XNAMES:
                            if st.wButtons & bit:
                                out.add('x:%d' % bit)
                except OSError:
                    break
        return out

    def poll(self):
        now = self.held()
        new = now - self._was
        self._was = now
        return sorted(new)


def bound(s):
    """The buttons set for the cards' actions: {action: id}."""
    got = ((s.get('overlay') or {}).get('inGameButtons')) or {}
    return {a: got[a] for a in ACTIONS if isinstance(got.get(a), str) and got[a]}


class CardButtons:
    """The app's side: SET (capture) and, while a card is up in the game, its actions from the buttons."""

    def __init__(self, app):
        self.app = app
        self.buttons = Buttons()
        self.capturing = None                # (action, until)

    def capture(self, action):
        if action in ACTIONS:
            self.buttons.poll()              # (what is held now: not the press)
            self.capturing = (action, time.monotonic() + CAPTURE_S)

    def clear(self, action):
        o = self.app.s.setdefault('overlay', {})
        got = dict(o.get('inGameButtons') or {})
        got.pop(action, None)
        o['inGameButtons'] = got
        from . import settings
        settings.save(self.app.s)

    def tick(self):
        """-> the actions pressed since the last tick ([] while capturing: the press is the button being set)."""
        pressed = self.buttons.poll()
        if self.capturing:
            action, until = self.capturing
            if time.monotonic() > until:
                self.capturing = None
            elif pressed:
                o = self.app.s.setdefault('overlay', {})
                got = {a: b for a, b in (o.get('inGameButtons') or {}).items() if b != pressed[0]}   # (one action a button)
                got[action] = pressed[0]
                o['inGameButtons'] = got
                from . import settings
                settings.save(self.app.s)
                self.capturing = None
            return []
        binds = bound(getattr(self.app, 's', None) or {})
        return [a for a, b in binds.items() if b in pressed]
