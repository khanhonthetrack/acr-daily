"""A sound and a Windows notification when a finished run's official time is in, or lost (from 0.1.5).

Drivers closed the game, or started the stage again, before it had saved their result (12-14 Nov 2026), and nothing
told them when it was safe to. So once the wait for the game's result ends (app.py _official_in, leagueui.py) the app
says how it went where the driver is looking: a system sound (heard over a full-screen game too) and a notification in
Windows' corner, as ACRK's tray app does ("a notification, or a sound with the game full screen, tells you how it went").

The notification is a balloon from an icon the app puts in the notification area for it (Shell_NotifyIconW; Windows 10
and 11 show it as a toast), taken away when the app quits (close()). The setting 'notify' (on by default) turns both off.
Nothing happens on other systems or when a call fails: never raises.
"""
import ctypes
import os

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_ICON, NIF_TIP, NIF_INFO = 0x2, 0x4, 0x10
NIIF_INFO, NIIF_WARNING = 0x1, 0x2
ICON_ID = 0xACD1
SOUNDS = {True: 'SystemAsterisk', False: 'SystemExclamation'}
ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
def _nid_type():
    from ctypes import wintypes

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND), ('uID', wintypes.UINT),
                    ('uFlags', wintypes.UINT), ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON),
                    ('szTip', wintypes.WCHAR * 128), ('dwState', wintypes.DWORD), ('dwStateMask', wintypes.DWORD),
                    ('szInfo', wintypes.WCHAR * 256), ('uTimeoutOrVersion', wintypes.UINT),
                    ('szInfoTitle', wintypes.WCHAR * 64), ('dwInfoFlags', wintypes.DWORD),
                    ('guidItem', ctypes.c_byte * 16), ('hBalloonIcon', wintypes.HICON)]
    return NOTIFYICONDATAW


class Notifier:
    """One per app: notify(ok, title, text). hwnd: the app's main window (its notification icon belongs to it)."""

    def __init__(self, hwnd_of=None, enabled=lambda: True):
        self.hwnd_of = hwnd_of
        self.enabled = enabled
        self.added = False
        self._icon = None
        self.sent = []          # (ok, title, text): what was said (tests; and nothing else keeps it)

    def notify(self, ok, title, text):
        self.sent.append((ok, title, text))
        del self.sent[:-20]
        try:
            if not self.enabled() or os.name != 'nt':
                return
        except Exception:
            return
        self._sound(ok)
        self._balloon(ok, title, text)

    @staticmethod
    def _sound(ok):
        try:
            import winsound
            winsound.PlaySound(SOUNDS[bool(ok)], winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass

    def _nid(self):
        nid = _nid_type()()
        nid.cbSize = ctypes.sizeof(nid)
        nid.hWnd = self.hwnd_of() if self.hwnd_of else None
        nid.uID = ICON_ID
        return nid

    def _balloon(self, ok, title, text):
        try:
            user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
            if self._icon is None:
                self._icon = (user32.LoadImageW(None, ICON, 1, 16, 16, 0x10) if os.path.exists(ICON) else 0) or \
                    user32.LoadIconW(None, ctypes.c_void_p(32512))          # (IDI_APPLICATION)
            nid = self._nid()
            nid.uFlags = NIF_ICON | NIF_TIP | NIF_INFO
            nid.hIcon = self._icon
            nid.szTip = 'ACR Daily'
            nid.szInfoTitle = title[:63]
            nid.szInfo = text[:255]
            nid.dwInfoFlags = NIIF_INFO if ok else NIIF_WARNING
            if not self.added:
                self.added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
            else:
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            pass

    def close(self):
        """The app quits: its notification icon goes."""
        if not self.added:
            return
        try:
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))
        except Exception:
            pass
        self.added = False
