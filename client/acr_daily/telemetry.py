"""Reads Assetto Corsa Rally's shared memory (same layout as Assetto Corsa Competizione).

What the game actually fills in (checked on real runs):
  graphics +0    int    packet id (counts up while the game runs)
  graphics +12   wchar  stage clock "MM:SS.mmm" - 00:00.000 on the start line, runs from the start
                        line, freezes at the finish
  graphics +256  float  car x, y, z (world metres)
  physics  +0    int    physics packet id: ~333 per second of game time, a clock of its own
  physics  +4/+8 float  throttle / brake 0..1;  +16 int gear;  +20 int rpm;  +24 float steering -1..1
  physics  +28   float  speed km/h
  physics  +72   float  wheel loads x4 (N): all near 0 = the car is in the air
  physics  +288  float  air temperature, kelvin (follows time of day, weather and height on the stage)
  static   +68   wchar  car name ("Peugeot 208 Rally4"), +134 stage name ("Alsace Obersteigen")
Penalties, final times, flags and assists are NOT published by the game.
"""
import ctypes
import dataclasses
import struct
import time
from ctypes import wintypes
from dataclasses import dataclass

FILE_MAP_READ = 4


@dataclass
class Frame:
    t: float            # local monotonic seconds when read
    packet: int         # graphics packet id
    clock_ms: int       # stage clock in ms, 0 on the start line, -1 when blank
    x: float
    z: float
    speed: float        # km/h
    car: str
    track: str
    ppacket: int = 0    # physics packet id
    gas: float = 0.0
    brake: float = 0.0
    steer: float = 0.0
    gear: int = 0
    rpm: int = 0
    air_k: float = 0.0  # air temperature, kelvin (depends on time of day, weather and height on the stage)
    airborne: bool = False  # all four wheels carry no load (in the air)


def steam_account():
    """SteamID64 of the account the Steam client is logged in with right now (what the game runs under), or None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam\ActiveProcess') as k:
            uid, _ = winreg.QueryValueEx(k, 'ActiveUser')
        return str(76561197960265728 + int(uid)) if int(uid) else None
    except (OSError, ValueError, ImportError):
        return None


def parse_clock(text):
    """'02:33.634' -> 153634, '' -> -1."""
    if not text:
        return -1
    try:
        parts = text.split(':')
        sec = float(parts[-1])
        mins = int(parts[-2]) if len(parts) > 1 else 0
        hours = int(parts[-3]) if len(parts) > 2 else 0
        return int(round(((hours * 60 + mins) * 60 + sec) * 1000))
    except ValueError:
        return -1


def _wstr(b):
    return b.decode('utf-16-le', 'replace').split('\x00')[0].strip()


def frame_from_bytes(t, graphics, physics, static):
    """Build a Frame from the three raw blocks (also used to replay recorded dumps)."""
    packet = struct.unpack_from('<i', graphics, 0)[0]
    clock = parse_clock(_wstr(graphics[12:42]))
    x, _y, z = struct.unpack_from('<3f', graphics, 256)
    if physics and len(physics) >= 32:
        # packet, gas, brake, fuel, gear, rpm, steer, speed
        pp, gas, brake, _fuel, gear, rpm, steer, speed = struct.unpack_from('<ifffiiff', physics, 0)
    else:
        pp, gas, brake, gear, rpm, steer, speed = 0, 0.0, 0.0, 0, 0, 0.0, 0.0
    air = struct.unpack_from('<f', physics, 288)[0] if physics and len(physics) >= 292 else 0.0
    loads = struct.unpack_from('<4f', physics, 72) if physics and len(physics) >= 88 else (1000.0,) * 4
    return Frame(t, packet, clock, x, z, speed, _wstr(static[68:134]), _wstr(static[134:200]),
                 pp, gas, brake, steer, gear, rpm, air, max(loads) < 50.0)


class _Block:
    _k32 = None

    @classmethod
    def k32(cls):
        if cls._k32 is None:
            k = ctypes.WinDLL('kernel32', use_last_error=True)
            k.OpenFileMappingW.restype = wintypes.HANDLE
            k.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
            k.MapViewOfFile.restype = ctypes.c_void_p
            k.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
            k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            cls._k32 = k
        return cls._k32

    def __init__(self, name, size):
        k = self.k32()
        self.size = size
        self.handle = k.OpenFileMappingW(FILE_MAP_READ, False, 'Local\\' + name)
        if not self.handle:
            raise OSError('no mapping ' + name)
        self.addr = k.MapViewOfFile(self.handle, FILE_MAP_READ, 0, 0, size)
        if not self.addr:
            k.CloseHandle(self.handle)
            raise OSError('cannot map ' + name)

    def read(self):
        return ctypes.string_at(self.addr, self.size)

    def close(self):
        k = self.k32()
        k.UnmapViewOfFile(self.addr)
        k.CloseHandle(self.handle)


class SharedMemory:
    """Live source. read() returns a Frame, or None while the game is not running.

    Our handle keeps the mapping alive after the game exits, so a packet id that stops moving for
    STALE_S seconds makes us let go and look again."""
    STALE_S = 5.0

    def __init__(self):
        self.blocks = None
        self.last_packet = None
        self.last_change = 0.0
        self.unloaded = False   # the game is there but has no stage loaded (back in its menus: it zeroes the blocks)

    def _open(self):
        try:
            self.blocks = (_Block('acpmf_graphics', 268), _Block('acpmf_physics', 296), _Block('acpmf_static', 200))
        except OSError:
            self.blocks = None

    def close(self):
        if self.blocks:
            for b in self.blocks:
                b.close()
        self.blocks = None

    def read(self):
        now = time.monotonic()
        self.unloaded = False
        if self.blocks is None:
            self._open()
            if self.blocks is None:
                return None
            self.last_packet, self.last_change = None, now
        g, p, s = (b.read() for b in self.blocks)
        f = frame_from_bytes(now, g, p, s)
        if f.packet != self.last_packet:
            self.last_packet, self.last_change = f.packet, now
        elif now - self.last_change > self.STALE_S:
            self.close()
            return None
        if f.packet == 0 and not f.track:
            self.unloaded = True
            return None   # mapping exists but the game has not loaded anything (or quit the stage to its menus)
        return f


class ReplaySource:
    """Developer/demo mode: plays a dump back in real time as if the game were running.
    Set ACR_DAILY_REPLAY=<dump.jsonl> (and optionally ACR_DAILY_REPLAY_FROM=<seconds to skip>)."""

    def __init__(self, path, skip=0.0):
        self.frames = [f for f in Replay(path).frames if f.t >= skip]
        self.t0 = time.monotonic() - (self.frames[0].t if self.frames else 0)
        self.i = 0

    def read(self):
        now = time.monotonic() - self.t0
        while self.i + 1 < len(self.frames) and self.frames[self.i + 1].t <= now:
            self.i += 1
        if not self.frames or now > self.frames[-1].t + 5:
            return None
        return dataclasses.replace(self.frames[self.i], t=self.frames[self.i].t + self.t0)

    def close(self):
        pass


class Replay:
    """Plays back a JSONL dump of the shared memory blocks (one frame per line), for tests."""

    def __init__(self, path):
        import json
        self.frames = []
        blocks = {}
        last_t = None
        with open(path) as fh:
            for line in fh:
                e = json.loads(line)
                if 'hex' in e:
                    blocks[e['block']] = bytearray(bytes.fromhex(e['hex']))
                    continue
                if 'off' not in e or e['block'] not in blocks:
                    continue
                if last_t is not None and e['t'] != last_t:
                    self._snap(last_t, blocks)
                last_t = e['t']
                blocks[e['block']][e['off']:e['off'] + 4] = (e['new'] & 0xffffffff).to_bytes(4, 'little')
        if last_t is not None:
            self._snap(last_t, blocks)

    def _snap(self, t, blocks):
        g, p, s = blocks.get('acpmf_graphics'), blocks.get('acpmf_physics'), blocks.get('acpmf_static')
        if g is not None and s is not None:
            self.frames.append(frame_from_bytes(t, bytes(g), bytes(p) if p is not None else b'', bytes(s)))
