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


class Mic:
    """The default microphone: read() -> the next 20 ms (bytes) or None (none ready). No microphone: ok False."""

    def __init__(self):
        self.w = _winmm()
        self.h = ctypes.c_void_p()
        self.ok = False
        self.ready = deque()
        if self.w is None:
            return
        if self.w.waveInOpen(ctypes.byref(self.h), WAVE_MAPPER, ctypes.byref(_fmt()), 0, 0, 0) != 0:
            return
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
    talk(): 'ptt' / 'open' / 'off'; held: a function -> whether push-to-talk is held now."""

    def __init__(self, send, held=lambda: False, mode='ptt', gain=1.0, mic=None, speaker=None):
        self.send = send
        self.held = held
        self.mode = mode
        self.gain = gain
        self.on = True
        self.talking = False              # sending now
        self.hearing_at = -1e9            # the other's voice last heard
        self.seq = 0
        self._in = deque()                # (seq, packet) heard, waiting to be played
        self._last_seq = None
        self._open_at = -1e9
        self.lost = 0
        self._enc = [0, 0]                # the encoder's state (encode)
        self._mic, self._spk = mic, speaker
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @property
    def hearing(self):
        return time.monotonic() - self.hearing_at < 0.3

    def heard(self, packet):
        """A voice packet from the other one: b'<seq u16><adpcm...>'."""
        if len(packet) < 5:
            return
        seq = struct.unpack_from('<H', packet, 0)[0]
        if self._last_seq is not None and ((seq - self._last_seq) & 0xFFFF) > 0x8000:
            return                                   # (older than one already played: late, dropped)
        self._in.append((seq, packet[2:]))
        self.hearing_at = time.monotonic()
        while len(self._in) * 20 > MAX_QUEUE_MS:     # (too far behind: the oldest go, the calls stay on time)
            self._in.popleft()
            self.lost += 1

    def _run(self):
        mic = self._mic or Mic()
        spk = self._spk or Speaker()
        self.mic_ok, self.speaker_ok = mic.ok, spk.ok
        waiting = True                               # (before playing: JITTER_MS ready first)
        try:
            while self.on:
                busy = False
                pcm = mic.read()
                if pcm is not None:
                    busy = True
                    now = time.monotonic()
                    if self.mode == 'open' and peak(pcm) >= OPEN_LEVEL:
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
                if self._in and (not waiting or len(self._in) * 20 >= JITTER_MS):
                    waiting = False
                    if spk.queued() < 3:
                        seq, pkt = self._in.popleft()
                        self._last_seq = seq
                        spk.play(decode(pkt, gain=self.gain))
                        busy = True
                elif not self._in:
                    waiting = True
                if not busy:
                    time.sleep(0.004)
        finally:
            mic.close()
            spk.close()

    def close(self):
        self.on = False
