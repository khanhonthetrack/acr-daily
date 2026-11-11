"""Real cars in the game: put the game mod in place when ghost cars want it, and take it out again when they don't.

The game mod is two parts, both put into <game>\\acr\\Binaries\\Win64:
  - UE4SS, the mod loader (dwmapi.dll, ue4ss\\UE4SS.dll and its settings, UEHelpers.lua): from UE4SS_ZIP, the exact
    build it was tested with (UE4SS's own link to it is gone: it keeps only its newest build), downloaded once from
    this project on GitHub (this version's release, else mod\\ue4ss in the code) and checked against UE4SS_SHA256
    before anything is unpacked;
  - the ACR Daily mod (ue4ss\\Mods\\ACRDailyGhosts): shipped inside the app, so it always matches it.
ue4ss\\Mods\\mods.txt starts only our mod. ue4ss\\ACRDaily-install.json lists what was put there, so taking it out
removes exactly that. A UE4SS someone installed themselves is left alone: only our mod and its line in their
mods.txt come and go.

Windows won't replace or delete a DLL the running game has loaded: those steps wait until the game is closed
(Keeper tries again every RETRY_S).
"""
import glob
import hashlib
import json
import os
import re
import threading
import time
import urllib.request
import zipfile

from . import USER_AGENT, __version__, settings
from .saveslot import STEAM_APP
from .i18n import _

UE4SS_ZIP = 'UE4SS_v3.0.1-1208-g6f8dc3cc.zip'
UE4SS_SHA256 = '899b6dbe84539c0b19d5ef08eb3a6e99e2195ebc0706baf24fe5799e3a6888f8'
REPO = 'https://github.com/khanhonthetrack/acr-daily'
UE4SS_URLS = [REPO + '/releases/download/v%s/%s' % (__version__, UE4SS_ZIP),     # (release.yml puts it there)
              'https://raw.githubusercontent.com/khanhonthetrack/acr-daily/main/mod/ue4ss/' + UE4SS_ZIP]
UE4SS_FILES = {  # in the zip -> under Win64
    'dwmapi.dll': 'dwmapi.dll',
    'ue4ss/UE4SS.dll': 'ue4ss/UE4SS.dll',
    'ue4ss/UE4SS-settings.ini': 'ue4ss/UE4SS-settings.ini',
    'ue4ss/LICENSE': 'ue4ss/LICENSE',
    'ue4ss/UE4SS_SDK_Backends/UE4SS.json': 'ue4ss/UE4SS_SDK_Backends/UE4SS.json',
    'ue4ss/Mods/shared/UEHelpers/UEHelpers.lua': 'ue4ss/Mods/shared/UEHelpers/UEHelpers.lua',
}
MOD = 'ACRDailyGhosts'
MOD_FILES = ('main.lua', 'wheels.lua')
MOD_LINE = '%s : 1' % MOD
MANIFEST = 'ue4ss/ACRDaily-install.json'
LEFTOVERS = ('ue4ss/UE4SS.log', 'ue4ss/Mods/mods.txt')      # UE4SS's own log; ours: the mod list we wrote
RETRY_S = 20
CHECK_S = 300

# what Keeper.status says (short: shown in the ghost set-up)
NOTES = {'ready': _('Game mod installed.'), 'off': '', 'nogame': _("Can't find the game in Steam: real cars need it."),
         'downloading': _('Downloading the game mod...'), 'download': _("Couldn't download the game mod (no internet?). "
         'Trying again.'), 'busy': _('Close the game to finish (it is using the mod files).'),
         'error': _('Something went wrong with the game mod. Trying again.'),
         'clash': _('Another game mod uses dwmapi.dll in the game folder: real cars can\'t be added.')}


# ---------------------------------------------------------------------- where the game is

def _steam_dirs():
    try:
        import winreg
    except ImportError:            # (not Windows)
        return []
    out = []
    for hive, key, value in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                             (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                             (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath')):
        try:
            with winreg.OpenKey(hive, key) as k:
                p = os.path.normpath(winreg.QueryValueEx(k, value)[0])
        except OSError:
            continue
        if p not in out:
            out.append(p)
    return out


def libraries(steam):
    """Steam's library folders (steam itself first) from its steamapps\\libraryfolders.vdf."""
    out = [steam]
    try:
        with open(os.path.join(steam, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return out
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = os.path.normpath(m.group(1).replace('\\\\', '\\'))
        if p not in out:
            out.append(p)
    return out


def _is_game(path):
    return bool(path) and os.path.isfile(os.path.join(path, 'acr', 'Binaries', 'Win64', 'acr.exe'))


def game_dir(steam_dirs=None, running=True):
    """The game's folder (the one with acr\\Binaries\\Win64\\acr.exe), or None. running: if Steam doesn't list it, ask
    the running game where it is."""
    for steam in (_steam_dirs() if steam_dirs is None else steam_dirs):
        for lib in libraries(steam):
            try:
                with open(os.path.join(lib, 'steamapps', 'appmanifest_%d.acf' % STEAM_APP), encoding='utf-8',
                          errors='replace') as f:
                    m = re.search(r'"installdir"\s+"([^"]+)"', f.read())
            except OSError:
                continue
            if m:
                path = os.path.join(lib, 'steamapps', 'common', m.group(1))
                if _is_game(path):
                    return path
    return _running_game_dir() if steam_dirs is None and running else None


def _kernel32():
    """kernel32 with the types set (its own copy: other modules' calls keep theirs)."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32')
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k.Process32FirstW.argtypes = k.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                             ctypes.POINTER(wintypes.DWORD))
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    return k


def _game_pids(k):
    """The running game's process ids (from Windows' process list: no tasklist, so no console window flashes)."""
    import ctypes
    from ctypes import wintypes
    from .saveslot import GAME_EXE

    class Entry(ctypes.Structure):                                      # PROCESSENTRY32W
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                    ('szExeFile', ctypes.c_wchar * 260)]
    snap = k.CreateToolhelp32Snapshot(2, 0)                            # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return []
    pids = []
    try:
        e = Entry()
        e.dwSize = ctypes.sizeof(Entry)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == GAME_EXE.lower():
                pids.append(e.th32ProcessID)
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return pids


def _running_game_dir():
    """From the running game itself (a game outside Steam's lists)."""
    try:
        import ctypes
        from ctypes import wintypes
        k = _kernel32()
        for pid in _game_pids(k):
            h = k.OpenProcess(0x1000, False, pid)                       # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                continue
            try:
                buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
                if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                    path = buf.value                     # ...\acr\Binaries\Win64\acr.exe, or the launcher at the top
                    for up in (3, 0):
                        d = os.path.dirname(path)
                        for _i in range(up):
                            d = os.path.dirname(d)
                        if _is_game(d):
                            return d
            finally:
                k.CloseHandle(h)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------- the files

def _bundle_dir():
    """Where the app keeps the ACR Daily mod: in the built exe, acr_daily\\mod\\...; from source, the repo's mod\\."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, 'mod', MOD, 'Scripts'),
              os.path.join(os.path.dirname(os.path.dirname(here)), 'mod', MOD, 'Scripts')):
        if all(os.path.isfile(os.path.join(d, f)) for f in MOD_FILES):
            return d
    return None


def mod_files():
    """{path under Win64: bytes} of the ACR Daily mod this app carries."""
    d = _bundle_dir()
    if not d:
        raise InstallError(_('the app is missing its game mod files'))
    out = {}
    for f in MOD_FILES:
        with open(os.path.join(d, f), 'rb') as fh:
            out['ue4ss/Mods/%s/Scripts/%s' % (MOD, f)] = fh.read()
    return out


class InstallError(Exception):
    pass


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def cache_path():
    return os.path.join(settings.DIR, 'gamemod', UE4SS_ZIP)


def ue4ss_zip(urls=None, timeout=60):
    """The checked UE4SS zip (kept in the app's folder after the first download). Raises InstallError('download')."""
    path = cache_path()
    if os.path.isfile(path):
        with open(path, 'rb') as f:
            if _sha(f.read()) == UE4SS_SHA256:
                return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    last = None
    for url in urls or UE4SS_URLS:
        try:
            if url.startswith(('http://', 'https://')):
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': USER_AGENT}),
                                            timeout=timeout) as r:
                    data = r.read()
            else:                                             # (a file: tests, or a copy at hand)
                with open(url, 'rb') as f:
                    data = f.read()
        except Exception as e:
            last = e
            continue
        if _sha(data) != UE4SS_SHA256:
            last = 'not the expected file'
            continue
        with open(path + '.tmp', 'wb') as f:
            f.write(data)
        os.replace(path + '.tmp', path)
        return path
    raise InstallError('download', last)


def _read(path):
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError:
        return None


def _write(path, data):
    """Write a file whole (a temporary file moved into place). PermissionError: the game holds it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.acrdaily-new'
    with open(tmp, 'wb') as f:
        f.write(data)
    try:
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _prune(win64, rel):
    """Remove the empty folders above a removed file, up to Win64."""
    d = os.path.dirname(os.path.join(win64, rel))
    while os.path.normcase(d) != os.path.normcase(win64):
        try:
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def _manifest(win64):
    data = _read(os.path.join(win64, MANIFEST))
    try:
        return json.loads(data) if data else None
    except ValueError:
        return None


def _mods_list(text, on):
    """Their mods.txt with our line in (before UE4SS's Keybinds line, which must stay last) or out."""
    lines = [l for l in text.splitlines() if l.split(':')[0].strip() != MOD]
    if on:
        at = next((i for i, l in enumerate(lines) if l.strip().startswith('; Built-in keybinds') or
                   l.split(':')[0].strip() == 'Keybinds'), len(lines))
        lines.insert(at, MOD_LINE)
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------- in and out

def state(game=None):
    """-> 'none' (no UE4SS), 'ours' (put there by the app), 'theirs' (the player's own UE4SS), 'clash' (another
    mod's dwmapi.dll, no UE4SS: it can't go in)."""
    win64 = os.path.join(game, 'acr', 'Binaries', 'Win64')
    man = _manifest(win64)
    if man is not None:
        return 'ours' if man.get('ue4ss') == 'ours' else 'theirs'
    if os.path.isfile(os.path.join(win64, 'ue4ss', 'UE4SS.dll')):
        return 'theirs'
    if os.path.exists(os.path.join(win64, 'dwmapi.dll')):
        return 'clash'
    return 'none'


def install(game, zip_urls=None):
    """Put the game mod in place (or bring it up to date). -> list of files written. Raises PermissionError (the game
    is using a file: try again once it is closed) or InstallError."""
    win64 = os.path.join(game, 'acr', 'Binaries', 'Win64')
    kind = state(game)
    if kind == 'clash':
        raise InstallError('clash')
    want = dict(mod_files())
    man = _manifest(win64) or {}
    if kind in ('none', 'ours'):
        files = man.get('files') or {}
        if any(_sha(_read(os.path.join(win64, rel)) or b'') != files.get(rel) for rel in UE4SS_FILES.values()) \
                or any(files.get(rel) is None for rel in UE4SS_FILES.values()):
            with zipfile.ZipFile(ue4ss_zip(zip_urls)) as z:
                for src, rel in UE4SS_FILES.items():
                    want[rel] = z.read(src)
        else:
            for rel in UE4SS_FILES.values():
                want[rel] = None                          # (in place and unchanged)
        want['ue4ss/Mods/mods.txt'] = (MOD_LINE + '\n').encode('ascii')
    else:                                                 # their UE4SS: our mod, and its line in their list(s)
        for name in ('mods.txt',):
            p = os.path.join(win64, 'ue4ss', 'Mods', name)
            text = (_read(p) or b'').decode('utf-8', 'replace')
            want['ue4ss/Mods/' + name] = _mods_list(text, True).encode('utf-8')
        mj = os.path.join(win64, 'ue4ss', 'Mods', 'mods.json')
        if os.path.isfile(mj):
            try:
                mods = json.loads(_read(mj).decode('utf-8'))
                if isinstance(mods, list) and not any(isinstance(m, dict) and m.get('mod_name') == MOD for m in mods):
                    mods.append({'mod_name': MOD, 'mod_enabled': True})
                    want['ue4ss/Mods/mods.json'] = json.dumps(mods, indent=4).encode('utf-8')
            except ValueError:
                pass
    written = []
    # the DLLs last: if the game holds them, everything else is already in place
    for rel in sorted(want, key=lambda r: r.endswith('.dll')):
        data = want[rel]
        if data is None:
            continue
        p = os.path.join(win64, rel)
        if _read(p) != data:
            _write(p, data)
            written.append(rel)
    files = {rel: _sha(_read(os.path.join(win64, rel)) or b'') for rel in want
             if kind != 'theirs' or rel.startswith('ue4ss/Mods/%s/' % MOD)}
    record = {'ue4ss': 'ours' if kind in ('none', 'ours') else 'theirs', 'build': UE4SS_ZIP, 'files': files}
    if record != man:
        _write(os.path.join(win64, MANIFEST), json.dumps(record, indent=1).encode('utf-8'))
    return written


def uninstall(game):
    """Take out what install() put there. -> list of files removed. Raises PermissionError (the game holds a file)."""
    win64 = os.path.join(game, 'acr', 'Binaries', 'Win64')
    man = _manifest(win64)
    if man is None:
        return []
    removed = []
    rels = list(man.get('files') or {})
    if man.get('ue4ss') == 'ours':
        rels += [r for r in LEFTOVERS if r not in rels]
        rels += [os.path.relpath(p, win64).replace('\\', '/') for p in glob.glob(os.path.join(win64, 'ue4ss', '*.dmp'))]
    else:                                                  # their UE4SS: take our line out of their list(s)
        p = os.path.join(win64, 'ue4ss', 'Mods', 'mods.txt')
        text = _read(p)
        if text is not None and MOD_LINE.encode() in text:
            _write(p, _mods_list(text.decode('utf-8', 'replace'), False).encode('utf-8'))
        mj = os.path.join(win64, 'ue4ss', 'Mods', 'mods.json')
        if os.path.isfile(mj):
            try:
                mods = json.loads(_read(mj).decode('utf-8'))
                kept = [m for m in mods if not (isinstance(m, dict) and m.get('mod_name') == MOD)]
                if kept != mods:
                    _write(mj, json.dumps(kept, indent=4).encode('utf-8'))
            except (ValueError, TypeError):
                pass
    for rel in sorted(rels, key=lambda r: r.endswith('.dll')):     # the DLLs last (the game may hold them)
        p = os.path.join(win64, rel)
        if os.path.exists(p):
            os.remove(p)
            removed.append(rel)
        _prune(win64, rel)
    _remove(os.path.join(win64, MANIFEST))
    _prune(win64, MANIFEST)
    return removed


def sync(want, game=None, zip_urls=None):
    """One step towards what the settings want. -> a NOTES key ('ready', 'off', 'busy', 'nogame', 'download', ...)."""
    game = game or game_dir(running=want)          # (nothing wanted: Steam's lists are enough to find ours to remove)
    if not game:
        return 'nogame' if want else 'off'
    try:
        if want:
            install(game, zip_urls)
            return 'ready'
        uninstall(game)
        return 'off'
    except PermissionError:
        return 'busy'
    except InstallError as e:
        return e.args[0] if e.args and e.args[0] in ('download', 'clash') else 'error'
    except OSError:
        return 'busy'


class Keeper:
    """Keeps the game mod in line with the settings, on its own thread. want(): True when real cars are wanted.
    poke() after the settings change; while something is left to do (the game holding a file, no internet) it tries
    again every RETRY_S, else checks every CHECK_S. status: a NOTES key."""

    def __init__(self, want):
        self.want = want
        self.status = 'off'
        self._wake = threading.Event()
        self._wake.set()
        threading.Thread(target=self._run, daemon=True).start()

    def poke(self):
        self._wake.set()

    def note(self):
        return NOTES.get(self.status, '')

    def _run(self):
        while True:
            self._wake.wait(RETRY_S if self.status in ('busy', 'download', 'error') else CHECK_S)
            self._wake.clear()
            try:
                want = bool(self.want())
                if want and self.status != 'ready' and not os.path.isfile(cache_path()):
                    self.status = 'downloading'
                self.status = sync(want)
            except Exception:                                  # never take the app down
                self.status = 'error'
            time.sleep(0.5)
