"""Sets a daily up in Assetto Corsa Rally's own save (PlayerDataSaveSlot.sav), so the game opens on it.

The save is an Unreal GVAS file whose game data is one block ("PlayerSaveGameData" + its byte size).
Inside, the game's settings for "Online single stage" hold, as plain length-prefixed strings:
    stage id   e.g. AlsaceS4SaverneFullForward
    car id     e.g. Peugeot208Rally4
    /Script/acr.WeatherOptions/StartingTime  (TimeSeconds=57600.000000)
    /Script/acr.WeatherOptions/Preset        (WeatherType=WT_LIGHT_RAIN,RandomUniform=0.5,bRandom=False)
    /Script/acr.WeatherOptions/TimeSpeed     WT_SPEEDFIX     (time of day stands still: same light for everyone)
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


def read_setup(b):
    """What the online single stage set-up currently holds: {'stage', 'car', 'time', 'preset', 'speed'} + offsets."""
    _payload(b)
    i = b.find(SECTION)
    if i < 0:
        raise SaveError('no online single stage settings in the save (start an online single stage once)')
    end = b.find(b'\x00\x00\x00Default', i + len(SECTION))      # the next settings entry
    end = len(b) if end < 0 else end
    strs = _strings(b, i + len(SECTION), end)
    found = {}
    for k, (o, s, e) in enumerate(strs):
        if 'stage' not in found and STAGE_RE.match(s):
            found['stage'] = (o, s, e)
            if k + 1 < len(strs):
                found['car'] = strs[k + 1]
        for key, name in ((KEY_TIME, 'time'), (KEY_PRESET, 'preset'), (KEY_SPEED, 'speed')):
            if s == key and k + 1 < len(strs):
                found[name] = strs[k + 1]
    missing = [n for n in ('stage', 'car', 'time', 'preset', 'speed') if n not in found]
    if missing:
        raise SaveError('the save does not look as expected (missing %s)' % ', '.join(missing))
    if not re.match(rb'^[A-Za-z0-9]+$', found['car'][1]):
        raise SaveError('unexpected car entry %r' % found['car'][1])
    return found


def apply_daily(b, stage_id, car_id, start_seconds, weather_game, time_speed='WT_SPEEDFIX'):
    """-> new save bytes with the daily set up. Raises SaveError if anything is unexpected."""
    found = read_setup(b)
    preset_old = found['preset'][1].decode('ascii')
    m = re.search(r'RandomUniform=([0-9.]+)', preset_old)
    preset = '(WeatherType=%s,RandomUniform=%s,bRandom=False)' % (weather_game, m.group(1) if m else '0.500000')
    new_values = {
        'stage': stage_id, 'car': car_id,
        'time': '(TimeSeconds=%.6f)' % float(start_seconds),
        'preset': preset, 'speed': time_speed,
    }
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


def write_daily(ch):
    """Set the game's save to the daily `ch` (needs stageId, carId, weatherGame, startSeconds). -> message."""
    if game_running():
        raise SaveError('Close Assetto Corsa Rally first: it rewrites its save when it exits.')
    if not os.path.exists(SAVE):
        raise SaveError('No game save found. Start Assetto Corsa Rally once first.')
    for k in ('stageId', 'carId', 'weatherGame', 'startSeconds'):
        if ch.get(k) in (None, ''):
            raise SaveError('This daily has no %s yet, set it up in the game by hand.' % k)
    with open(SAVE, 'rb') as f:
        b = f.read()
    new = apply_daily(b, ch['stageId'], ch['carId'], ch['startSeconds'], ch['weatherGame'])
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
    return 'Set up: %s · %s · %s' % (ch['stageId'], ch['carId'], ch.get('weatherLabel') or ch['weatherGame'])


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
