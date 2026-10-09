"""Sets a daily up in Assetto Corsa Rally's own save (PlayerDataSaveSlot.sav), so the game opens on it.

The save is an Unreal GVAS file whose game data is one block ("PlayerSaveGameData" + its byte size).
Inside, after the game's per-mode settings (a map: int32 count, then per mode its FString name, "DefaultRally",
"DefaultOnlineSingleStage"..., and its contexts: see _modes_end), comes the player's current selection, as plain
length-prefixed strings:
    stage id   e.g. AlsaceS4SaverneFullForward
    car id     e.g. Peugeot208Rally4      (the car Rally Weekend and Single Rally Stage are driven in)
    int32 n, n x (key, value):            (n = 0 until the player has driven a Single Rally Stage)
        /Script/acr.WeatherOptions/StartingTime  (TimeSeconds=57600.000000)
        /Script/acr.WeatherOptions/Preset        (WeatherType=WT_LIGHT_RAIN,RandomUniform=0.5,bRandom=False)
        /Script/acr.WeatherOptions/TimeSpeed     WT_SPEEDFIX     (time of day stands still: same light for everyone)
The map only holds the modes the player has used; a new player's save has just "DefaultRally" (seen in the game
2026-10-09), so the selection is found by walking the map, not by a mode's name.
Only those strings are replaced and the block size is corrected; anything not exactly as expected = nothing
is written. Every write keeps a backup first, and only while the game is closed (it rewrites the save on exit).
"""
import os
import re
import shutil
import struct
import time

SAVE = os.path.join(os.environ.get('LOCALAPPDATA') or '', 'acr', 'Saved', 'SaveGames', 'PlayerDataSaveSlot.sav')
GAME_EXE = 'acr.exe'          # acr\Binaries\Win64\acr.exe
STEAM_APP = 3917090
SECTION = b'DefaultOnlineSingleStage\x00'
STAGE_RE = re.compile(rb'^(Alsace|Weles|Wales|Greece|MonteCarlo|Livigno|Sweden)S\d[A-Za-z0-9]*(Forward|Reverse)$')
KEY_TIME = b'/Script/acr.WeatherOptions/StartingTime'
KEY_PRESET = b'/Script/acr.WeatherOptions/Preset'
KEY_SPEED = b'/Script/acr.WeatherOptions/TimeSpeed'


class SaveError(Exception):
    pass


def _fstring_at(b, o):
    """Unreal FString at offset o: int32 length (incl. the NUL) + ASCII. -> (bytes, end) or None."""
    if o + 4 > len(b):
        return None
    n = struct.unpack_from('<i', b, o)[0]
    if not 1 <= n <= 300 or o + 4 + n > len(b) or b[o + 4 + n - 1] != 0:
        return None
    s = b[o + 4:o + 4 + n - 1]
    if any(c < 32 or c > 126 for c in s):
        return None
    return s, o + 4 + n


def _fstring(s):
    s = s.encode('ascii') if isinstance(s, str) else s
    return struct.pack('<i', len(s) + 1) + s + b'\x00'


def _strings(b, a, z):
    """Every FString that starts between a and z (a scan; the section has binary data between them)."""
    out, o = [], a
    while o < z:
        f = _fstring_at(b, o)
        if f and len(f[0]) >= 3:
            out.append((o, f[0], f[1]))
            o = f[1]
        else:
            o += 1
    return out


def _payload(b):
    """-> offset of the PlayerSaveGameData size field; checks the block runs exactly to the end of the file."""
    if b[:4] != b'GVAS':
        raise SaveError('not a GVAS save')
    i = b.find(b'PlayerSaveGameData\x00')
    if i < 0:
        raise SaveError('no PlayerSaveGameData')
    so = i + len(b'PlayerSaveGameData\x00')
    size = struct.unpack_from('<i', b, so)[0]
    if so + 4 + size != len(b):
        raise SaveError('unexpected save layout (size %d at %d, file %d)' % (size, so, len(b)))
    return so


MODE_RE = re.compile(rb'^Default[A-Za-z]+$')
START_ONE = 'In the game: Racing › Rally › Rally Weekend › START RALLY, then CONFIRM AND START RALLY. Then click DRIVE again.'
NO_OPTIONS = ('The game has no Single Rally Stage weather settings yet: it makes them the first time you drive one.\n\n'
              'Once: in the game, Racing › Rally › Single Rally Stage › START RACE, with any stage and car, and let it '
              'load. Then click DRIVE again.')


def _i(b, o):
    return struct.unpack_from('<i', b, o)[0]


def _modes(b, o, count):
    """Walk the per-mode settings map from its first entry at o: per mode an FString name, int32 contexts, per context
    an FString name, int32 n x (16-byte GUID, int32 version), int32 m x (FString component, int32 size, `size` bytes).
    -> [(name, offset of the name, offset of the value (its contexts count), end)], or None if it isn't one."""
    out = []
    try:
        for _k in range(count):
            at = o
            name = _fstring_at(b, o)
            if not name or not MODE_RE.match(name[0]):
                return None
            o = name[1]
            contexts = _i(b, o)
            o += 4
            if not 0 <= contexts <= 8:
                return None
            for _c in range(contexts):
                ctx = _fstring_at(b, o)
                if not ctx:
                    return None
                o = ctx[1]
                versions = _i(b, o)
                if not 0 <= versions <= 32:
                    return None
                o += 4 + 20 * versions
                parts = _i(b, o)
                o += 4
                if not 0 <= parts <= 32:
                    return None
                for _p in range(parts):
                    part = _fstring_at(b, o)
                    if not part:
                        return None
                    size = _i(b, part[1])
                    o = part[1] + 4 + size
                    if not 0 <= size or o > len(b):
                        return None
            out.append((name[0].decode(), at, name[1], o))
    except struct.error:
        return None
    return out


def modes(b):
    """The game's per-mode settings ("DefaultRally", "DefaultOnlineSingleStage"... only the modes the player has used),
    in the save's order: [(name, offset of the name, offset of the value, end)]. The current selection (stage, car,
    weather options) follows the last one. Raises SaveError."""
    o = b.find(b'Default')
    while o >= 0:
        start = o - 4                                      # the map's first name (an FString) ...
        count = _i(b, start - 4) if start >= 4 else 0      # ... after its entry count
        name = _fstring_at(b, start)
        if name and MODE_RE.match(name[0]) and 1 <= count <= 32:
            out = _modes(b, start, count)
            stage = out and _fstring_at(b, out[-1][3])
            car = stage and _fstring_at(b, stage[1])           # (any of the game's ids: not only the dailies')
            if car and 0 <= _i(b, car[1]) <= 16:
                return out
        o = b.find(b'Default', o + 1)
    raise SaveError('The game\'s save has no stage and car selection yet (or it does not look as expected).\n\n' + START_ONE)


def _selection_at(b):
    """-> offset of the current selection (stage, car, weather options), just after the per-mode settings."""
    return modes(b)[-1][3]


def read_setup(b):
    """The game's current selection: {'stage', 'car'} and, once the player has driven a Single Rally Stage, its
    weather options {'time', 'preset', 'speed'}; each (offset, value, end)."""
    _payload(b)
    o = _selection_at(b)
    stage = _fstring_at(b, o)
    car = _fstring_at(b, stage[1])
    found = {'stage': (o, stage[0], stage[1]), 'car': (stage[1], car[0], car[1])}
    o = car[1] + 4
    for _k in range(_i(b, car[1])):
        key = _fstring_at(b, o)
        val = key and _fstring_at(b, key[1])
        if not val:
            raise SaveError('the save does not look as expected (weather options)')
        for k, name in ((KEY_TIME, 'time'), (KEY_PRESET, 'preset'), (KEY_SPEED, 'speed')):
            if key[0] == k:
                found[name] = (key[1], val[0], val[1])
        o = val[1]
    return found


def apply_daily(b, stage_id, car_id, start_seconds, weather_game, time_speed='WT_SPEEDFIX', options=True):
    """-> new save bytes with the daily set up: the selection's stage and car, and its weather options (time of day,
    weather, time standing still). options=False (a Rally Weekend, whose stages carry their own weather): those
    are set only if the save has them. Raises SaveError if anything is unexpected."""
    found = read_setup(b)
    new_values = {'stage': stage_id, 'car': car_id}
    has = all(n in found for n in ('time', 'preset', 'speed'))
    if options and not has:
        raise SaveError(NO_OPTIONS)
    if has:
        m = re.search(r'RandomUniform=([0-9.]+)', found['preset'][1].decode('ascii'))
        new_values.update(time='(TimeSeconds=%.6f)' % float(start_seconds), speed=time_speed,
                          preset='(WeatherType=%s,RandomUniform=%s,bRandom=False)' % (weather_game, m.group(1) if m else '0.500000'))
    # replace from the end of the file backwards, so earlier offsets stay valid
    out = bytearray(b)
    for name in sorted(new_values, key=lambda n: -found[n][0]):
        o, _old, e = found[name]
        out[o:e] = _fstring(new_values[name])
    so = _payload(b)
    struct.pack_into('<i', out, so, len(out) - so - 4)
    # check: the result reads back with exactly the new values
    back = read_setup(bytes(out))
    for name, v in new_values.items():
        if back[name][1].decode('ascii') != v:
            raise SaveError('verification failed for %s' % name)
    return bytes(out)


_GUID = re.compile(rb'^[0-9A-F]{32}$')


def driver_country(b=None):
    """The nationality in the player's in-game driver profile (e.g. 'Vietnam'), or None.
    The save ends with driver then co-driver, each as: GUID, first name, GUID, last name, country."""
    try:
        if b is None:
            with open(SAVE, 'rb') as f:
                b = f.read()
        strs = [s for _o, s, _e in _strings(b, max(0, len(b) - 2000), len(b))]
        for i in range(len(strs) - 4):
            if _GUID.match(strs[i]) and _GUID.match(strs[i + 2]) and not _GUID.match(strs[i + 4]):
                c = strs[i + 4].decode('ascii', 'replace').strip()
                return c if 2 <= len(c) <= 40 else None
    except (OSError, ValueError):
        pass
    return None


def game_pids():
    """Process ids of the running game (empty when it is closed)."""
    try:
        out = os.popen('tasklist /FI "IMAGENAME eq %s" /FO CSV /NH' % GAME_EXE).read()
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == GAME_EXE.lower() and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def game_running():
    return bool(game_pids())


def ask_game_to_quit():
    """Ask the game to close the normal way (like clicking the window's X), so it saves as it always does on exit.
    -> True if a game window got the request. The game may still ask the player to confirm."""
    import ctypes
    from ctypes import wintypes
    pids = set(game_pids())
    if not pids:
        return False
    user32 = ctypes.windll.user32
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd, _lp):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(proc(each), 0)
    for hwnd in found:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
    return bool(found)


def backup_dir():
    from . import settings
    return os.path.join(settings.DIR, 'save-backups')


def read_for_daily(ch):
    """The save as it is, once it may be rewritten for the daily `ch` (needs stageId, carId, weatherGame,
    startSeconds). Raises SaveError."""
    if game_running():
        raise SaveError('Close Assetto Corsa Rally first: it rewrites its save when it exits.')
    if not os.path.exists(SAVE):
        # (starting the game is not enough: it writes its save only once something is started in it)
        raise SaveError('The game has no save yet: it writes one once you start something in it.\n\n' + START_ONE)
    for k in ('stageId', 'carId', 'weatherGame', 'startSeconds'):
        if ch.get(k) in (None, ''):
            raise SaveError('This daily has no %s yet, set it up in the game by hand.' % k)
    with open(SAVE, 'rb') as f:
        return f.read()


def write_daily(ch):
    """Set the game's save to the daily `ch` (its Single Rally Stage). -> message."""
    b = read_for_daily(ch)
    replace(apply_daily(b, ch['stageId'], ch['carId'], ch['startSeconds'], ch['weatherGame']))
    return 'Set up: %s · %s · %s' % (ch['stageId'], ch['carId'], ch.get('weatherLabel') or ch['weatherGame'])


def replace(new):
    """Write `new` as the game's save, keeping a backup of the old one first."""
    os.makedirs(backup_dir(), exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(SAVE, os.path.join(backup_dir(), 'PlayerDataSaveSlot-%s.sav' % stamp))
    olds = sorted(n for n in os.listdir(backup_dir()) if n.endswith('.sav'))
    for n in olds[:-15]:   # keep the last 15
        os.remove(os.path.join(backup_dir(), n))
    tmp = SAVE + '.acrdaily.tmp'
    with open(tmp, 'wb') as f:
        f.write(new)
    os.replace(tmp, SAVE)


def restore_latest():
    """Put back the save from before the last set-up. -> message."""
    if game_running():
        raise SaveError('Close Assetto Corsa Rally first.')
    olds = sorted(n for n in os.listdir(backup_dir()) if n.endswith('.sav')) if os.path.isdir(backup_dir()) else []
    if not olds:
        raise SaveError('No backup yet.')
    shutil.copy2(os.path.join(backup_dir(), olds[-1]), SAVE)
    return 'Restored the save from %s' % olds[-1][len('PlayerDataSaveSlot-'):-4]


def launch_game():
    os.startfile('steam://rungameid/%d' % STEAM_APP)
