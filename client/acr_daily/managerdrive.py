"""Sando Rally's Stage Manager run for the player (community.manager_install): his stages are installed only by his
own manager (their terms), so INSTALL starts it from the stage's download and does what the player would do there.

Started from a download, the manager offers to install the stage in it: a small window of its own (Tk) with Install and
Cancel side by side at its bottom right, the Install on the left. Its buttons are drawn by Tk, so they don't take a
message: the window is put in front and Install clicked where it is (its own window's middle, as the system places it:
no picture is looked at). Its notes are Windows' own message boxes, read by their words: OK pressed on a note, Yes on
a question about installing, anything else left to the player (ManagerError 'asks'). It is done when the manager's
state (%LOCALAPPDATA%\\Sando-Rally-Original-Stage-Manager\\state.json) lists the stage, at its version, installed
after the start; then the manager is closed, as the player would close it. Windows only.
"""
import ctypes
import json
import os
import subprocess
import time

STATE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Sando-Rally-Original-Stage-Manager', 'state.json')
WM_CLOSE, BM_CLICK = 0x0010, 0x00F5


class ManagerError(Exception):
    """kind: 'start' (it didn't start), 'closed' (it closed before installing), 'asks' (it asks something only the
    player can answer: detail, its words; it is left open), 'said' (it said something went wrong: its words), 'time'."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


# ---------------------------------------------------------------------- its windows

def _user32():
    return ctypes.windll.user32


def _text(h):
    u = _user32()
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value


def _class(h):
    b = ctypes.create_unicode_buffer(256)
    _user32().GetClassNameW(h, b, 256)
    return b.value


def _rect(h):
    from ctypes import wintypes
    r = wintypes.RECT()
    _user32().GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _children(h):
    from ctypes import wintypes
    out = []
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(lambda c, _l: out.append(c) or True)
    _user32().EnumChildWindows(h, cb, 0)
    return out


def windows(pid):
    """Its visible top-level windows: [(hwnd, class)]."""
    from ctypes import wintypes
    u, out = _user32(), []

    def each(h, _l):
        p = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            out.append((h, _class(h)))
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(each), 0)
    return out


def note(h):
    """A message box's words and its buttons: (words, {button text without &: hwnd})."""
    words, buttons = [], {}
    for c in _children(h):
        k = _class(c)
        if k == 'Button':
            buttons[_text(c).replace('&', '').strip().lower()] = c
        elif k == 'Static' and _text(c).strip():
            words.append(_text(c).strip())
    return '\n'.join(words), buttons


def answer(words, buttons):
    """What the player would press on a note of his manager's: a button's name, or None (only they can say)."""
    low = words.lower()
    if set(buttons) <= {'ok'}:
        return 'ok'
    if 'yes' in buttons and 'install' in low and 'uninstall' not in low and 'clean up' not in low:
        return 'yes'                                     # (install it, update it: what INSTALL asked for)
    return None


def offer_install(h):
    """The window offering to install the download's stage: its Install button's window, or None. Its two buttons
    sit side by side in a row of their own (Install, Cancel); the manager's main window has none such."""
    for c in _children(h):
        row = [k for k in _children(c) if _user32().GetParent(k) == c]
        if len(row) != 2:
            continue
        (a0, a1, a2, a3), (b0, b1, b2, b3) = _rect(row[0]), _rect(row[1])
        if (a3 - a1) == (b3 - b1) and a1 == b1 and (a2 - a0) == (b2 - b0) and 0 < (a3 - a1) < 80 and 0 < (a2 - a0) < 240:
            return row[0] if a0 < b0 else row[1]
    return None


def click(h, window):
    """A real click in the middle of a Tk widget's window (Tk's buttons take no message), its window in front."""
    u = _user32()
    u.ShowWindow(window, 9)
    u.keybd_event(0x12, 0, 0, 0)                         # (Alt: Windows lets this process bring a window forward)
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(window)
    time.sleep(0.4)
    x0, y0, x1, y1 = _rect(h)
    u.SetCursorPos((x0 + x1) // 2, (y0 + y1) // 2)
    time.sleep(0.15)
    u.mouse_event(2, 0, 0, 0, 0)                         # (left down, up)
    time.sleep(0.05)
    u.mouse_event(4, 0, 0, 0, 0)


# ---------------------------------------------------------------------- its state

def installed_since(pack, version, since, state=None):
    """His manager's state lists the stage of that pack, at that version, installed at or after `since` (seconds)."""
    try:
        with open(state or STATE, encoding='utf-8') as f:
            s = json.load(f)
    except (OSError, ValueError):
        return False
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(since))
    for st in (s.get('stages') or {}).values():
        if isinstance(st, dict) and str(st.get('pack') or '').lower() == str(pack).lower() and \
                str(st.get('version')) == str(version) and str(st.get('installed_at') or '') >= stamp:
            return True
    return False


def install(exe, pack, version, timeout=1800, say=None, state=None, env=None):
    """His manager started from the download (exe: its manager), the stage installed as the player would, the manager
    closed. Raises ManagerError."""
    say = say or (lambda _w: None)
    t0 = time.time() - 2
    try:
        proc = subprocess.Popen([exe], cwd=os.path.dirname(exe), env=env)
    except OSError as e:
        raise ManagerError('start', str(e))
    clicked, done = 0, False
    try:
        while time.time() - t0 < timeout:
            if installed_since(pack, version, t0, state):
                done = True
                break
            if proc.poll() is not None:
                raise ManagerError('closed', 'it closed before the stage was in')
            wins = windows(proc.pid)
            main = next((h for h, k in wins if k == 'TkTopLevel' and not _user32().GetWindow(h, 4)), None)
            for h, k in wins:
                if k == '#32770':                        # (a message box: read, answered as the player would)
                    words, buttons = note(h)
                    a = answer(words, buttons)
                    if a is None:
                        raise ManagerError('asks', words)
                    _user32().SendMessageW(buttons[a], BM_CLICK, 0, 0)
                    if a == 'ok' and any(w in words.lower() for w in ('error', 'failed', 'could not', "couldn't",
                                                                        'not enough', 'cannot')):
                        raise ManagerError('said', words)
                elif k == 'TkTopLevel' and h != main and clicked < 3:
                    button = offer_install(h)
                    if button is not None:
                        say('install')
                        click(button, h)
                        clicked += 1
                        time.sleep(2)
            time.sleep(1)
        if not done:
            raise ManagerError('time', 'it took over %d minutes' % (timeout // 60))
        time.sleep(1.5)                                  # (its last note, then closed as the player would)
        for h, k in windows(proc.pid):
            if k == '#32770':
                words, buttons = note(h)
                if answer(words, buttons) == 'ok':
                    _user32().SendMessageW(buttons['ok'], BM_CLICK, 0, 0)
    finally:
        if done:
            _close(proc)                                 # (else left open: what it says or asks is the player's)
    return True


def _close(proc):
    """The manager closed (WM_CLOSE to its main window, as its X)."""
    if proc.poll() is not None:
        return
    for h, k in windows(proc.pid):
        if k == 'TkTopLevel' and not _user32().GetWindow(h, 4):
            _user32().PostMessageW(h, WM_CLOSE, 0, 0)
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.terminate()
