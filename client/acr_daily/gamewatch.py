"""What the game did while a finished run waited for its official result: for the report the app sends when the game
loses that result (gamelog.py), since the game's own log is not there on players' PCs (13 Nov 2026: the first two
reports found none in %LOCALAPPDATA%\\acr\\Saved\\Logs).

The app sees, without touching the game:
- its telemetry: a stage loaded (the results screen included), back in its menus (it zeroes the blocks: it left the
  stage), or nothing new for telemetry.SharedMemory.STALE_S (closed, or frozen);
- whether Windows marks its window "Not Responding" (IsHungAppWindow);
- when its process ended and how: its exit code, read from a handle opened while it ran (0: quit the normal way, 1: ended
  from outside, e.g. the Task Manager, 0xC...: a crash).
Each change is kept with its time. Windows calls fail quietly (other systems, tests): nothing is recorded then.
"""
import os
import time

SYNCHRONIZE, QUERY_LIMITED = 0x00100000, 0x1000
STILL_ACTIVE = 259
EXIT_WORDS = {
    0: 'quit the normal way',
    1: 'ended from outside (the Task Manager, or Windows closing it after it stopped responding)',
    3: 'stopped by itself (abort: an error it could not go on from)',
    0xC0000005: 'a crash (access violation)',
    0xC0000409: 'a crash (a fatal error: the game stopped itself)',
    0xC00000FD: 'a crash (stack overflow)',
    0xC000001D: 'a crash (illegal instruction)',
    0xC0000374: 'a crash (heap corruption)',
    0xC0000017: 'a crash (out of memory)',
    0x887A0005: 'a crash (the graphics device was removed: driver reset)',
    0x887A0006: 'a crash (the graphics device hung)',
}
STATE_WORDS = {
    'stage': 'telemetry: a stage loaded (driving, or its results screen)',
    'menus': "telemetry: the game left the stage (back in its menus or loading)",
    'none': 'telemetry: nothing new from the game (closed, or frozen)',
}


def exit_words(code):
    """An exit code in words for the report."""
    if code is None:
        return 'unknown'
    code &= 0xFFFFFFFF
    words = EXIT_WORDS.get(code) or ('a crash' if code >= 0xC0000000 else 'an unusual end')
    return '%s (exit code %s)' % (words, '0x%08X' % code if code > 0xFFFF else code)


class _Win:
    """The few Windows calls the watch makes, or None where there are none."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes
        k, u = ctypes.WinDLL('kernel32', use_last_error=True), ctypes.WinDLL('user32', use_last_error=True)
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
        u.IsHungAppWindow.argtypes = [wintypes.HWND]
        u.IsHungAppWindow.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.k, self.u = k, u

    def open(self, pid):
        h = self.k.OpenProcess(SYNCHRONIZE | QUERY_LIMITED, False, pid)
        return h or None

    def image(self, h):
        buf, n = self.ct.create_unicode_buffer(1024), self.wt.DWORD(1024)
        return buf.value if self.k.QueryFullProcessImageNameW(h, 0, buf, self.ct.byref(n)) else None

    def ended(self, h):
        """-> the exit code once the process has ended, else None."""
        if self.k.WaitForSingleObject(h, 0) != 0:
            return None
        code = self.wt.DWORD()
        return code.value if self.k.GetExitCodeProcess(h, self.ct.byref(code)) else None

    def close(self, h):
        self.k.CloseHandle(h)

    def hung(self, pid):
        """Is a visible window of this process "Not Responding"? -> True / False, None: no window of it."""
        found = []
        proc = self.ct.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)

        def each(hwnd, _lp):
            p = self.wt.DWORD()
            self.u.GetWindowThreadProcessId(hwnd, self.ct.byref(p))
            if p.value == pid and self.u.IsWindowVisible(hwnd):
                found.append(bool(self.u.IsHungAppWindow(hwnd)))
            return True
        self.u.EnumWindows(proc(each), 0)
        return any(found) if found else None


def _win():
    if os.name != 'nt':
        return None
    try:
        return _Win()
    except Exception:
        return None


class GameWatch:
    """One game session watched while finished runs wait (app.py, leagueui.py). telemetry() each frame, process() at
    each look at the save (every 2 s). events: [(unix time, words)], each change once."""

    def __init__(self, win=False, clock=time.time):
        self.win = _win() if win is False else win
        self.clock = clock
        self.events = []
        self.exe = None             # the game's own path (where its Saved folder is)
        self._state = None
        self._pid = self._h = None
        self._hung = None

    def _add(self, text, t=None):
        self.events.append((self.clock() if t is None else t, text))
        del self.events[:-200]

    def telemetry(self, state):
        """'stage', 'menus' or 'none' (telemetry.SharedMemory: a frame, unloaded, nothing)."""
        if state != self._state:
            self._state = state
            self._add(STATE_WORDS.get(state, state))

    def process(self, find):
        """The game's process: its window responding, and its end. find: saveslot.game_pids, asked only until a handle
        on the game is open (a tasklist each time)."""
        w = self.win
        if w is None:
            return
        try:
            if self._h is not None:
                code = w.ended(self._h)
                if code is not None:
                    self._add('the game ended: %s' % exit_words(code))
                    w.close(self._h)
                    self._h = self._pid = self._hung = None
                    return
            elif (pids := find()):
                pid = pids[0]
                h = w.open(pid)
                if h:
                    self._h, self._pid = h, pid
                    self.exe = self.exe or w.image(h)
            if self._pid is not None:
                hung = w.hung(self._pid)
                if hung is not None and hung != self._hung:
                    if hung or self._hung is not None:
                        self._add('Windows: the game is "Not Responding"' if hung else
                                  'Windows: the game responds again')
                    self._hung = hung
        except Exception:
            pass

    def close(self):
        if self._h is not None and self.win is not None:
            try:
                self.win.close(self._h)
            except Exception:
                pass
        self._h = None

    def snapshot(self):
        """What the report takes: {'events': [...], 'exe': path or None}."""
        return {'events': list(self.events), 'exe': self.exe}


def timeline(events, since, until=None):
    """The events from a run's finish (`since`, unix time) on, as '+12 s  words' lines (a minute before it too)."""
    out = []
    for t, text in events:
        if t < since - 60 or (until is not None and t > until):
            continue
        d = t - since
        sign = '-' if d < 0 else '+'
        d = abs(d)
        when = '%d:%02d' % (d // 60, d % 60) if d >= 60 else '%d s' % d
        out.append('%s%s  %s' % (sign, when, text))
    return out


def summary(events, since):
    """The key facts after a finish in a sentence or two, for the report's body."""
    after = [(t, x) for t, x in events if t >= since - 1]
    first = lambda key: next((t for t, x in after if key in x), None)     # noqa: E731
    left, frozen, hung, ended = first('left the stage'), first('nothing new'), first('Not Responding'), first('ended:')
    bits = []
    fmt = lambda t: '+%d:%02d' % ((t - since) // 60, (t - since) % 60)    # noqa: E731
    if left is not None:
        bits.append('the game left the stage at %s (so it got past its results screen)' % fmt(left))
    elif after:
        bits.append('the game never left the stage (still on it, or its results screen)')
    if frozen is not None and (ended is None or frozen < ended - 6):
        bits.append('its telemetry stopped at %s' % fmt(frozen))
    if hung is not None:
        bits.append('Windows marked it "Not Responding" at %s' % fmt(hung))
    if ended is not None:
        bits.append('it %s at %s' % (next(x for t, x in after if t == ended and 'ended:' in x)[len('the game '):],
                                     fmt(ended)))
    return ('After the finish ' + '; '.join(bits) + '.') if bits else ''
