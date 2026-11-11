"""One ACR Daily at a time. Two copies judge the same runs and send them twice: a league stage's start sent by both is
a second start to the server, which ends the entry ("DNF: SS2 started again", seen 2026-11-09 with two copies open),
and both share one queue of results to send (league-pending.json). A named Windows mutex, held while the app runs: the
second copy says the app is open already and quits. The updater's new copy (--updated) waits for the old one to go."""
import ctypes
import sys
import time
from .i18n import _

NAME = 'Local\\ACRDaily.OneCopy'
ERROR_ALREADY_EXISTS = 183
_held = None                # the mutex's handle, kept for the app's life (Windows closes it when the app ends)


def _kernel32():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    k.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    k.CloseHandle.argtypes = (ctypes.c_void_p,)
    return k


def acquire(wait_s=0.0, kernel32=None, last_error=None, sleep=time.sleep, clock=time.monotonic):
    """True when no other ACR Daily runs (it is ours now), False when one does (after waiting up to wait_s for it to
    quit). Not on Windows, or the mutex not made at all: True (better a second copy than no app)."""
    global _held
    if kernel32 is None:
        if sys.platform != 'win32':
            return True
        kernel32, last_error = _kernel32(), ctypes.get_last_error
    end = clock() + wait_s
    while True:
        h = kernel32.CreateMutexW(None, 0, NAME)
        if not h:
            return True
        if last_error() != ERROR_ALREADY_EXISTS:
            _held = h
            return True
        kernel32.CloseHandle(h)
        if clock() >= end:
            return False
        sleep(0.25)


def tell_running():
    """The second copy: say so (no window of its own yet), then it quits."""
    try:
        ctypes.windll.user32.MessageBoxW(None, _('ACR Daily is open already: look for its window (or its icon on the '
                                               'taskbar).\n\nOnly one ACR Daily can run at a time.'), 'ACR Daily', 0x40)
    except (AttributeError, OSError):
        print('ACR Daily is open already: only one can run at a time.')
