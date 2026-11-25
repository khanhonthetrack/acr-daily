"""COPILOT's voice (copilot.py): the two of a crew talk to each other, the co-driver reading the notes out.

Nothing to install: the microphone and the speakers through Windows' own wave calls (winmm, the default devices), the
sound as 16 kHz mono, 20 ms a packet, packed 4:1 with IMA ADPCM (8 KB a second: a phone call's quality, which is what
a co-driver's voice needs; every packet carries its own start, so a lost one is a 20 ms gap, nothing after it lost).
The packets go over the crew's link (copilotlink.py): straight between the two PCs, or through the live relay.

Talk: 'ptt' (push to talk: a key or a wheel / pad button held), 'open' (the microphone open, sent while it hears
something louder than OPEN_LEVEL), 'off'. Heard: played as it comes, kept JITTER_MS ahead at most (late ones dropped:
the calls stay on time, never behind).
"""
import ctypes
import struct
import threading
import time
from collections import deque

RATE = 16000
FRAME = 320                      # samples a packet: 20 ms
FRAME_BYTES = FRAME * 2
OPEN_LEVEL = 900                 # open mic: a packet this loud (its peak, of 32767) is speech
OPEN_HANG_S = 0.4                # ... and the mic stays open this long after the last one (words' ends not cut)
JITTER_MS = 60                   # heard: this much kept ready before playing; more than MAX_QUEUE_MS: the oldest dropped
MAX_QUEUE_MS = 200
IN_BUFFERS, OUT_BUFFERS = 6, 8

# ---------------------------------------------------------------------- IMA ADPCM (4 bits a sample)
_STEPS = (7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
          107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
          876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428,
          4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350,
          22385, 24623, 27086, 29794, 32767)
_INDEX = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)


def encode(pcm, state=None):
    """16-bit mono samples (bytes) -> a packet: its start (the predicted sample, step index) then two samples a byte.
    state: a list [pred, index] carried from one packet to the next (the step stays fitted to the voice; each packet
    still says where it starts, so a lost one loses only itself), updated here; None: a packet on its own."""
    n = len(pcm) // 2
    s = struct.unpack('<%dh' % n, pcm[:n * 2])
    pred, idx = (state[0], state[1]) if state else (s[0] if s else 0, 0)
    out = bytearray(struct.pack('<hB', pred, idx))
    nib = None
    for x in s:
        step = _STEPS[idx]
        diff = x - pred
        code = 0
        if diff < 0:
            code, diff = 8, -diff
        delta = step >> 3
        if diff >= step:
            code |= 4
            diff -= step
            delta += step
        step >>= 1
        if diff >= step:
            code |= 2
            diff -= step
            delta += step
        step >>= 1
        if diff >= step:
            code |= 1
            delta += step
        pred = pred - delta if code & 8 else pred + delta
        pred = -32768 if pred < -32768 else 32767 if pred > 32767 else pred
        idx += _INDEX[code]
        idx = 0 if idx < 0 else 88 if idx > 88 else idx
        if nib is None:
            nib = code
        else:
            out.append(nib | (code << 4))
            nib = None
    if nib is not None:
        out.append(nib)
    if state is not None:
        state[:] = [pred, idx]
    return bytes(out)


def decode(packet, n=FRAME, gain=1.0):
    """A packet (encode) -> 16-bit mono samples (bytes), n of them."""
    if len(packet) < 3:
        return b'\0' * (n * 2)
    pred, idx = struct.unpack_from('<hB', packet, 0)
    idx = min(88, idx)
    out = []
    for b in packet[3:]:
        for code in (b & 15, b >> 4):
            if len(out) >= n:
                break
            step = _STEPS[idx]
            delta = step >> 3
            if code & 4:
                delta += step
            if code & 2:
                delta += step >> 1
            if code & 1:
                delta += step >> 2
            pred = pred - delta if code & 8 else pred + delta
            pred = -32768 if pred < -32768 else 32767 if pred > 32767 else pred
            idx += _INDEX[code]
            idx = 0 if idx < 0 else 88 if idx > 88 else idx
            out.append(pred)
    out += [0] * (n - len(out))
    if gain != 1.0:
        out = [max(-32768, min(32767, int(v * gain))) for v in out]
    return struct.pack('<%dh' % n, *out)


def peak(pcm):
    n = len(pcm) // 2
    if not n:
        return 0
    s = struct.unpack('<%dh' % n, pcm[:n * 2])
    return max(max(s), -min(s))


# ---------------------------------------------------------------------- the rally intercom (the user, 25 Nov 2026: "this
# 'driver/codriver' walkie talkie type effect, like in real rallies")
def _biquad(kind, f0, q=0.707, gain_db=0.0, fs=RATE):
    """An RBJ cookbook filter's coefficients (b0, b1, b2, a1, a2), a0 taken out: 'hp', 'lp', 'peak'."""
    import math
    w = 2 * math.pi * f0 / fs
    cw, sw = math.cos(w), math.sin(w)
    alpha = sw / (2 * q)
    if kind == 'hp':
        b = ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    elif kind == 'lp':
        b = ((1 - cw) / 2, 1 - cw, (1 - cw) / 2)
        a = (1 + alpha, -2 * cw, 1 - alpha)
    else:
        A = 10 ** (gain_db / 40)
        b = (1 + alpha * A, -2 * cw, 1 - alpha * A)
        a = (1 + alpha / A, -2 * cw, 1 - alpha / A)
    return (b[0] / a[0], b[1] / a[0], b[2] / a[0], a[1] / a[0], a[2] / a[0])


class Intercom:
    """The partner's voice as a rally crew hears each other through their helmets' intercom: the headset microphones'
    narrow band (300 to 3400 Hz, a lift at 1.8 kHz: its honk), pressed hard (a fast compressor and a soft clip: the
    co-driver calling over the engine), a light hiss under it while the channel is open, a click as it opens and a
    short squelch as it closes. 20 ms frames of 16-bit samples in and out (process, tail); its filters keep their
    state from one frame to the next. Pure Python: about 1 ms a frame."""

    CHAIN = (('hp', 300.0, 0.707, 0.0), ('hp', 300.0, 0.707, 0.0), ('peak', 1800.0, 1.0, 5.0),
             ('lp', 3400.0, 0.707, 0.0), ('lp', 3400.0, 0.707, 0.0))
    TARGET = 9000.0                 # the compressor brings the voice's level up (or down) to about this (of 32767)
    MAX_GAIN = 6.0
    DRIVE = 1.8                     # the soft clip: x / (1 + |x|) at this much drive (a little grit, never a hard edge)
    HISS = 220.0                    # the open channel's hiss (of 32767)
    TAIL_FRAMES = 4                 # the squelch as the channel closes: this many 20 ms frames

    def __init__(self, seed=None):
        import random
        self.rng = random.Random(seed)
        self.coef = [_biquad(k, f, q, g) for k, f, q, g in self.CHAIN]
        self.state = [[0.0, 0.0, 0.0, 0.0] for _ in self.coef]       # (x1, x2, y1, y2) each
        self.env = 0.0
        self.open = False

    def _filter(self, x):
        for (b0, b1, b2, a1, a2), st in zip(self.coef, self.state):
            y = b0 * x + b1 * st[0] + b2 * st[1] - a1 * st[2] - a2 * st[3]
            st[1], st[0], st[3], st[2] = st[0], x, st[2], y
            x = y
        return x

    def _shape(self, x):
        """The compressor (a peak follower: fast up, slower down) and the soft clip."""
        a = abs(x)
        self.env = a if a > self.env else self.env * 0.9992
        g = min(self.MAX_GAIN, self.TARGET / max(self.env, 400.0))
        v = x * g / 32767.0 * self.DRIVE
        return v / (1.0 + abs(v)) * (32767.0 / (self.DRIVE / (1.0 + self.DRIVE))) * 0.55

    def process(self, pcm):
        """One frame of the partner's voice -> as heard on the intercom (bytes, as long). The first frame after a
        silence starts with the click of the channel opening."""
        n = len(pcm) // 2
        s = struct.unpack('<%dh' % n, pcm[:n * 2])
        out = []
        click = not self.open
        self.open = True
        rnd = self.rng.random
        for i, x in enumerate(s):
            y = self._shape(self._filter(float(x))) + (rnd() - 0.5) * 2 * self.HISS
            if click and i < 96:                     # (6 ms: a sharp tick, then a short 1.6 kHz blip)
                y += (rnd() - 0.5) * 2 * 9000 * (1 - i / 96) if i < 24 else \
                    7000 * (1 - i / 96) * (1 if (i // 5) % 2 else -1)
            out.append(-32768 if y < -32768 else 32767 if y > 32767 else int(y))
        return struct.pack('<%dh' % n, *out)

    def tail(self, n=FRAME):
        """The channel closing: TAIL_FRAMES frames of squelch (filtered noise fading out) -> [bytes]; [] when it is
        closed already."""
        if not self.open:
            return []
        self.open = False
        frames, total = [], self.TAIL_FRAMES * n
        rnd = self.rng.random
        for f in range(self.TAIL_FRAMES):
            out = []
            for i in range(n):
                k = f * n + i
                y = self._filter((rnd() - 0.5) * 2 * 14000 * (1 - k / total) ** 2)
                out.append(-32768 if y < -32768 else 32767 if y > 32767 else int(y))
            frames.append(struct.pack('<%dh' % n, *out))
        self.env = 0.0
        return frames


# ---------------------------------------------------------------------- Windows' wave calls (winmm)
class _WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('wFormatTag', ctypes.c_ushort), ('nChannels', ctypes.c_ushort), ('nSamplesPerSec', ctypes.c_uint32),
                ('nAvgBytesPerSec', ctypes.c_uint32), ('nBlockAlign', ctypes.c_ushort), ('wBitsPerSample', ctypes.c_ushort),
                ('cbSize', ctypes.c_ushort)]


class _WAVEHDR(ctypes.Structure):
    _fields_ = [('lpData', ctypes.c_void_p), ('dwBufferLength', ctypes.c_uint32), ('dwBytesRecorded', ctypes.c_uint32),
                ('dwUser', ctypes.c_size_t), ('dwFlags', ctypes.c_uint32), ('dwLoops', ctypes.c_uint32),
                ('lpNext', ctypes.c_void_p), ('reserved', ctypes.c_size_t)]


WAVE_MAPPER = 0xFFFFFFFF
WHDR_DONE = 1


def _winmm():
    try:
        w = ctypes.windll.winmm
    except (AttributeError, OSError):
        return None
    H, P, U = ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint
    for pre in ('waveIn', 'waveOut'):
        getattr(w, pre + 'Open').argtypes = [ctypes.POINTER(H), U, ctypes.POINTER(_WAVEFORMATEX), ctypes.c_size_t,
                                             ctypes.c_size_t, ctypes.c_uint32]
        for name in ('PrepareHeader', 'UnprepareHeader'):
            getattr(w, pre + name).argtypes = [H, P, U]
        getattr(w, pre + 'Close').argtypes = [H]
        getattr(w, pre + 'Reset').argtypes = [H]
    w.waveInAddBuffer.argtypes = [H, P, U]
    w.waveInStart.argtypes = [H]
    w.waveInStop.argtypes = [H]
    w.waveOutWrite.argtypes = [H, P, U]
    return w


def _fmt():
    return _WAVEFORMATEX(1, 1, RATE, RATE * 2, 2, 16, 0)


class _Buffers:
    """Wave headers with their memory, kept alive while Windows has them."""

    def __init__(self, n, size):
        self.mem = [ctypes.create_string_buffer(size) for _ in range(n)]
        self.hdr = [_WAVEHDR(ctypes.cast(m, ctypes.c_void_p), size, 0, 0, 0, 0, None, 0) for m in self.mem]


class _WAVEINCAPS(ctypes.Structure):
    _fields_ = [('wMid', ctypes.c_ushort), ('wPid', ctypes.c_ushort), ('vDriverVersion', ctypes.c_uint32),
                ('szPname', ctypes.c_wchar * 32), ('dwFormats', ctypes.c_uint32), ('wChannels', ctypes.c_ushort),
                ('wReserved1', ctypes.c_ushort)]


def mic_devices():
    """The microphones Windows has, by name (as winmm gives them: cut at 31 characters): [str]. [] when none / no winmm."""
    w = _winmm()
    if w is None:
        return []
    out = []
    try:
        for i in range(int(w.waveInGetNumDevs())):
            caps = _WAVEINCAPS()
            if w.waveInGetDevCapsW(ctypes.c_size_t(i), ctypes.byref(caps), ctypes.sizeof(caps)) == 0 and caps.szPname:
                out.append(caps.szPname)
    except (AttributeError, OSError):
        pass
    return out


def mic_index(name, devices=None):
    """The device number of the microphone called `name` (WAVE_MAPPER, Windows' default, for '' or a name not there)."""
    if not name:
        return WAVE_MAPPER
    devices = mic_devices() if devices is None else devices
    return devices.index(name) if name in devices else WAVE_MAPPER


def scale(pcm, gain):
    """16-bit mono samples (bytes) times gain (clipped)."""
    if gain == 1.0 or not pcm:
        return pcm
    n = len(pcm) // 2
    s = struct.unpack('<%dh' % n, pcm[:n * 2])
    return struct.pack('<%dh' % n, *[max(-32768, min(32767, int(v * gain))) for v in s])


class Mic:
    """A microphone (by its name in mic_devices(); '' / None: Windows' default): read() -> the next 20 ms (bytes) or
    None (none ready). No microphone: ok False."""

    def __init__(self, name=None):
        self.w = _winmm()
        self.h = ctypes.c_void_p()
        self.ok = False
        self.ready = deque()
        if self.w is None:
            return
        dev = mic_index(name)
        if self.w.waveInOpen(ctypes.byref(self.h), dev, ctypes.byref(_fmt()), 0, 0, 0) != 0:
            if dev == WAVE_MAPPER or self.w.waveInOpen(ctypes.byref(self.h), WAVE_MAPPER, ctypes.byref(_fmt()), 0, 0, 0) != 0:
                return                                   # (a microphone gone since it was picked: the default one)
        self.buf = _Buffers(IN_BUFFERS, FRAME_BYTES)
        for hd in self.buf.hdr:
            self.w.waveInPrepareHeader(self.h, ctypes.byref(hd), ctypes.sizeof(hd))
            self.w.waveInAddBuffer(self.h, ctypes.byref(hd), ctypes.sizeof(hd))
        self.next = 0
        self.ok = self.w.waveInStart(self.h) == 0

    def read(self):
        if not self.ok:
            return None
        hd = self.buf.hdr[self.next]
        if not hd.dwFlags & WHDR_DONE:
            return None
        data = ctypes.string_at(hd.lpData, hd.dwBytesRecorded)
        hd.dwFlags &= ~WHDR_DONE
        self.w.waveInAddBuffer(self.h, ctypes.byref(hd), ctypes.sizeof(hd))
        self.next = (self.next + 1) % len(self.buf.hdr)
        return data if len(data) == FRAME_BYTES else None

    def close(self):
        if self.w is not None and self.h:
            self.w.waveInStop(self.h)
            self.w.waveInReset(self.h)
            for hd in getattr(getattr(self, 'buf', None), 'hdr', []):
                self.w.waveInUnprepareHeader(self.h, ctypes.byref(hd), ctypes.sizeof(hd))
            self.w.waveInClose(self.h)
        self.ok = False


class Speaker:
    """The default speakers / headphones: play(20 ms) when a buffer is free -> True, else False."""

    def __init__(self):
        self.w = _winmm()
        self.h = ctypes.c_void_p()
        self.ok = False
        if self.w is None:
            return
        if self.w.waveOutOpen(ctypes.byref(self.h), WAVE_MAPPER, ctypes.byref(_fmt()), 0, 0, 0) != 0:
            return
        self.buf = _Buffers(OUT_BUFFERS, FRAME_BYTES)
        for hd in self.buf.hdr:
            self.w.waveOutPrepareHeader(self.h, ctypes.byref(hd), ctypes.sizeof(hd))
            hd.dwFlags |= WHDR_DONE                    # (free)
        self.ok = True

    def queued(self):
        """How many 20 ms buffers are with Windows, waiting to be heard."""
        return sum(1 for hd in self.buf.hdr if not hd.dwFlags & WHDR_DONE) if self.ok else 0

    def play(self, pcm):
        if not self.ok:
            return False
        for i, hd in enumerate(self.buf.hdr):
            if hd.dwFlags & WHDR_DONE:
                ctypes.memmove(self.buf.mem[i], pcm, min(len(pcm), FRAME_BYTES))
                hd.dwFlags &= ~WHDR_DONE
                return self.w.waveOutWrite(self.h, ctypes.byref(hd), ctypes.sizeof(hd)) == 0
        return False

    def close(self):
        if self.w is not None and self.h:
            self.w.waveOutReset(self.h)
            for hd in getattr(getattr(self, 'buf', None), 'hdr', []):
                self.w.waveOutUnprepareHeader(self.h, ctypes.byref(hd), ctypes.sizeof(hd))
            self.w.waveOutClose(self.h)
        self.ok = False


# ---------------------------------------------------------------------- talking: the key or button held
VK = {'V': 0x56, 'B': 0x42, 'T': 0x54, 'CAPSLOCK': 0x14, 'LCTRL': 0xA2, 'RCTRL': 0xA3, 'LSHIFT': 0xA0, 'LALT': 0xA4,
      'MOUSE4': 0x05, 'MOUSE5': 0x06, 'F12': 0x7B}


def key_held(name):
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK.get(name, 0)) & 0x8000) if name in VK else False
    except (AttributeError, OSError):
        return False


class Voice:
    """Both ways: the microphone to send(packet), the packets heard (heard()) to the speakers. A thread of its own.
    talk(): 'ptt' / 'open' / 'off'; held: a function -> whether push-to-talk is held now.

    Up to four in a crew (a casual lobby: the driver and three co-drivers): every speaker has a seat (0 the driver,
    1..3 the co-drivers) and a queue of their own; the frames heard are mixed. speaking(): who is heard or talking now
    (the pages' small speaker icons: mine as 'me'). mic: the microphone's name (mic_devices; '' = the default),
    mic_gain: how loud it goes out (0.25 to 4), level: the microphone's level now, 0..1 (the settings' meter)."""

    def __init__(self, send, held=lambda: False, mode='ptt', gain=1.0, mic=None, speaker=None, radio=True,
                 mic_name='', mic_gain=1.0, seat=None):
        self.send = send
        self.radio = radio                # the partner's voice through the rally intercom (Intercom)
        self.fx = Intercom()
        self.held = held
        self.mode = mode
        self.gain = gain
        self.mic_name = mic_name or ''
        self.mic_gain = mic_gain
        self.seat = seat                  # mine, when in a crew (what I send is tagged with it by the link; my own coming back is dropped)
        self.on = True
        self.talking = False              # sending now
        self.level = 0.0                  # the microphone's level now (0..1), whatever the mode
        self.seq = 0
        self._wait = set()                # seats before their first frame (JITTER_MS ready first)
        self._in = {}                     # seat -> deque of (seq, packet) heard, waiting to be played
        self._last = {}                   # seat -> the last seq played
        self._at = {}                     # seat -> when last heard
        self._open_at = -1e9
        self.lost = 0
        self._enc = [0, 0]                # the encoder's state (encode)
        self._mic, self._spk = mic, speaker
        self.mic_ok = self.speaker_ok = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def hearing_at(self):
        return max(self._at.values(), default=-1e9)

    @property
    def hearing(self):
        return time.monotonic() - self.hearing_at < 0.3

    def speaking(self, now=None):
        """Who is talking now: a set of seats heard in the last 0.3 s, and 'me' while I send."""
        now = time.monotonic() if now is None else now
        out = {s for s, t in self._at.items() if now - t < 0.3}
        if self.talking:
            out.add('me')
        return out

    def heard(self, packet, seat=0):
        """A voice packet from the seat's speaker: b'<seq u16><adpcm...>'."""
        if len(packet) < 5 or seat == self.seat:
            return
        seq = struct.unpack_from('<H', packet, 0)[0]
        last = self._last.get(seat)
        if last is not None and ((seq - last) & 0xFFFF) > 0x8000:
            return                                   # (older than one already played: late, dropped)
        q = self._in.setdefault(seat, deque())
        if not q and seat not in self._wait and not self._at.get(seat, -1e9) > time.monotonic() - 0.15:
            self._wait.add(seat)                      # (a new burst of words: JITTER_MS first)
        q.append((seq, packet[2:]))
        self._at[seat] = time.monotonic()
        while len(q) * 20 > MAX_QUEUE_MS:            # (too far behind: the oldest go, the calls stay on time)
            q.popleft()
            self.lost += 1

    def _next_frame(self, waiting=None):
        """The next 20 ms to play: one frame of each seat that has some (mixed), or None. waiting: the seats before
        their first frame (JITTER_MS kept ready first)."""
        waiting = self._wait if waiting is None else waiting
        frames = []
        for seat, q in list(self._in.items()):
            if not q:
                waiting.add(seat)
                continue
            if seat in waiting:
                if len(q) * 20 < JITTER_MS:
                    continue
                waiting.discard(seat)
            seq, pkt = q.popleft()
            self._last[seat] = seq
            frames.append(decode(pkt, gain=self.gain))
        if not frames:
            return None
        if len(frames) == 1:
            return frames[0]
        n = len(frames[0]) // 2
        cols = [struct.unpack('<%dh' % n, f) for f in frames]
        return struct.pack('<%dh' % n, *[max(-32768, min(32767, sum(c[i] for c in cols))) for i in range(n)])

    def _run(self):
        mic = self._mic or Mic(self.mic_name)
        spk = self._spk or Speaker()
        self.mic_ok, self.speaker_ok = mic.ok, spk.ok
        open_ch = False
        try:
            while self.on:
                busy = False
                pcm = mic.read()
                if pcm is not None:
                    busy = True
                    now = time.monotonic()
                    pcm = scale(pcm, self.mic_gain)
                    pk = peak(pcm)
                    self.level = max(pk / 32767.0, self.level * 0.85)
                    if self.mode == 'open' and pk >= OPEN_LEVEL:
                        self._open_at = now
                    want = (self.mode == 'ptt' and self.held()) or (self.mode == 'open' and now - self._open_at < OPEN_HANG_S)
                    self.talking = bool(want)
                    if want:
                        self.seq = (self.seq + 1) & 0xFFFF
                        try:
                            self.send(struct.pack('<H', self.seq) + encode(pcm, self._enc))
                        except Exception:
                            pass
                    else:
                        self._enc = [0, 0]           # (a new start for the next words)
                if spk.queued() < 3:
                    frame = self._next_frame()
                    if frame is not None:
                        open_ch = True
                        spk.play(self.fx.process(frame) if self.radio else frame)
                        busy = True
                    elif open_ch and not any(self._in.values()) and time.monotonic() - self.hearing_at > 0.12:
                        open_ch = False
                        if self.radio:
                            for f in self.fx.tail():         # (their words over: the channel closes, its squelch)
                                spk.play(f)
                if not busy:
                    time.sleep(0.004)
        finally:
            mic.close()
            spk.close()

    def close(self):
        self.on = False


class MicTest:
    """The microphone alone, for the settings' meter (no crew): level 0..1 while on. Stops itself after `secs`."""

    def __init__(self, name='', gain=1.0, secs=20.0):
        self.name, self.gain, self.until = name, gain, time.monotonic() + secs
        self.level = 0.0
        self.ok = None
        self.on = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        mic = Mic(self.name)
        self.ok = mic.ok
        try:
            while self.on and time.monotonic() < self.until:
                pcm = mic.read()
                if pcm is None:
                    time.sleep(0.01)
                    continue
                self.level = max(peak(scale(pcm, self.gain)) / 32767.0, self.level * 0.85)
        finally:
            mic.close()
            self.on = False
            self.level = 0.0

    def close(self):
        self.on = False
