"""Live ghost cars: your car's position sent to the live relay (live/relay.py) while your stage clock runs, and the
other drivers on the same stage received from it, to be drawn where they are right now.

A small WebSocket client of its own (standard library), on its own thread: it never holds up the overlay. Positions
go out 10 a second, sent 5 times a second; each driver's samples are kept for their whole run (a GhostTrace), so
"where they are now" and "when they were where you are" come from the same maths as the recorded ghosts.
"""
import base64
import json
import math
import os
import queue
import socket
import ssl
import struct
import threading
import time
from urllib.parse import urlparse

from . import ghostcars as gc

SAMPLE_MS = 100          # one of your samples per 100 ms of stage clock
SEND_S = 0.2             # sent in batches this often
DELAY_MS = 30            # others are drawn this far in the past
AHEAD_MS = 400           # and at most this far past their last sample (carried on at their speed)
STALE_S = 5.0            # nothing from a driver for this long: gone
RETRY_S = (2, 5, 10, 30)


class LiveDriver:
    def __init__(self, did, name, car, run):
        self.id, self.name, self.car, self.run = did, name, car, run
        self.trace = gc.GhostTrace({'samples': []})
        self.start_wall = None       # their stage clock's 0 on this PC's clock (the earliest seen: delays only add)
        self.seen = time.monotonic()

    def add(self, samples, now):
        for s in samples:
            if self.trace.ms and s[0] <= self.trace.ms[-1]:
                continue
            self.trace.s.append(tuple(s))
            self.trace.ms.append(s[0])
        if self.trace.ms:
            w = now - self.trace.ms[-1] / 1000.0
            self.start_wall = w if self.start_wall is None else min(self.start_wall, w)
        self.seen = now

    def clock_now(self, now):
        """Their stage clock now, as best known (never further than AHEAD_MS past their last sample)."""
        if self.start_wall is None or not self.trace.ms:
            return None
        return min((now - self.start_wall) * 1000.0 - DELAY_MS, self.trace.ms[-1] + AHEAD_MS)

    def pose(self, now):
        """Where they are now: between their samples, or a little past the last one at the same speed (the next
        batch is on its way)."""
        c = self.clock_now(now)
        if c is None:
            return None
        s, ms = self.trace.s, self.trace.ms
        if c <= ms[-1] or len(s) < 2:
            return self.trace.at(c)
        a, b = s[-2], s[-1]
        k = (c - b[0]) / float(b[0] - a[0] or 1)
        return (b[1] + (b[1] - a[1]) * k, b[2] + (b[2] - a[2]) * k, b[3] + (b[3] - a[3]) * k, b[4], b[5], b[6])

    def ahead_s(self, x, z, now):
        """How long ago they were where (x, z) is (on the road: + = they are ahead of you), or None."""
        c = self.clock_now(now)
        if c is None or len(self.trace.s) < 2:
            return None
        at = self.trace.passed(x, z)
        if at is None:
            return None
        p = self.trace.at(at)
        if math.hypot(p[0] - x, p[2] - z) > 25:          # they have not been here (yet)
            return None
        return (c - at) / 1000.0


def connect(host, port, timeout):
    """A TCP connection, IPv4 addresses first (a .local name also gives IPv6 link-local ones that can hang)."""
    addrs = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addrs.sort(key=lambda a: a[0] != socket.AF_INET)
    err = None
    for family, kind, proto, _name, addr in addrs:
        s = socket.socket(family, kind, proto)
        s.settimeout(min(timeout, 3.0))
        try:
            s.connect(addr)
            s.settimeout(timeout)
            return s
        except OSError as e:
            err = e
            s.close()
    raise err or OSError('no address for ' + host)


class WebSocket:
    """Just enough of a WebSocket client: text messages, ping / pong, close."""

    def __init__(self, url, timeout=8.0):
        u = urlparse(url)
        port = u.port or (443 if u.scheme == 'wss' else 80)
        sock = connect(u.hostname, port, timeout)
        if u.scheme == 'wss':
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or '/') + ('?' + u.query if u.query else '')
        sock.sendall(('GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nUser-Agent: ACR-Daily\r\n\r\n'
                      % (path, u.hostname, key)).encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError('closed during the handshake')
            head += chunk
            if len(head) > 16384:
                raise ConnectionError('bad handshake')
        status, _, rest = head.partition(b'\r\n\r\n')
        if b' 101 ' not in status.split(b'\r\n')[0]:
            raise ConnectionError('refused: ' + status.split(b'\r\n')[0].decode('latin-1'))
        self.sock, self.buf = sock, rest
        self.lock = threading.Lock()

    def _send(self, op, data):
        n = len(data)
        head = bytes([0x80 | op]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n)
                                      if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n))
        mask = os.urandom(4)
        body = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
        with self.lock:
            self.sock.sendall(head + mask + body)

    def send(self, text):
        self._send(1, text.encode())

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError('closed')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        """-> the next text message (str); answers pings on the way. Raises ConnectionError when closed."""
        parts = []
        while True:
            b1, b2 = self._read(2)
            fin, op, n = b1 & 0x80, b1 & 0x0f, b2 & 0x7f
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            if n > 1 << 20:
                raise ConnectionError('message too big')
            data = self._read(n)
            if op == 9:
                self._send(10, data)
                continue
            if op == 8:
                raise ConnectionError('closed by the relay')
            if op == 10:
                continue
            parts.append(data)
            if fin:
                return b''.join(parts).decode('utf-8', 'replace')

    def close(self):
        try:
            self._send(8, b'')
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class LiveLink:
    """The connection to the relay, kept up on its own thread while `on`. feed(frame) from the overlay's loop.
    ticket: a function -> the server's ticket for the relay ({ticket, name, ...}, api.live_ticket()), or None when not
    signed in; called on this thread before each connection (the relay checks names with it)."""

    def __init__(self, url, name, car='', ticket=None):
        self.url, self.name, self.car = url, name or 'Driver', car
        self.ticket_fn = ticket
        self._ticket = None
        self.on = True
        self.state = 'connecting'     # connecting | live | offline | signin
        self.drivers = {}             # id -> LiveDriver
        self.my_id = None
        self._out = queue.Queue(maxsize=200)
        self._batch, self._last_sample, self._last_send = [], -1, 0.0
        self._track, self._run, self._was_on_stage = None, None, False
        self._joined = None           # the stage the relay was told you are on (name, where it starts)
        self._at, self._at_track = None, None
        self._lock = threading.Lock()
        self._ws = None
        threading.Thread(target=self._run_loop, daemon=True).start()

    # ---- your car
    def feed(self, f):
        """Every frame the overlay reads. Samples while your stage clock runs; batches out every SEND_S. A new run
        (its own id) when the clock starts again or the stage changes."""
        now = time.monotonic()
        track = f.track if f is not None and f.track else None
        # where your stage starts, as far as known (the relay tells two stages of the same name apart by it): your
        # car waiting to start (the clock at 0), then where the clock started; unknown when joined mid-run
        if track != self._at_track:
            self._at_track, self._at = track, None
        if track and f.clock_ms == 0 and self._at is None:
            self._at = [round(f.x), round(f.z)]
        new_run = track and f.clock_ms > 0 and (f.track != self._track or self._run is None or
                                                 f.clock_ms < self._last_sample - 500)
        if new_run and f.clock_ms < 2000:                # (seen from its start: that is the start line)
            start = [round(f.x), round(f.z)]
            if self._at is None or math.dist(start, self._at) > 50:
                self._at = start
        joined = (track, tuple(self._at) if self._at else None)
        if joined != self._joined and self.state == 'live':
            self._put({'t': 'track', 'track': track, 'at': self._at} if track else {'t': 'leave'})
            self._joined = joined
        on_stage = track and f.clock_ms > 0
        if not on_stage:
            self._was_on_stage, self._batch = False, []
            return
        self._was_on_stage = True
        if new_run:
            self._track, self._run, self._last_sample, self._batch = f.track, int(time.time() * 1000), -1, []
        run_id = self._run
        if f.car and f.car != self.car:
            self.car = f.car
            self._put(self._hello())
        if f.clock_ms >= self._last_sample + SAMPLE_MS:
            self._last_sample = f.clock_ms
            self._batch.append([f.clock_ms, round(f.x, 2), round(f.y, 2), round(f.z, 2), round(f.heading, 4),
                                round(f.pitch, 4), round(f.roll, 4)])
        if self._batch and now - self._last_send >= SEND_S:
            self._last_send = now
            self._put({'t': 's', 'track': f.track, 'at': self._at, 'run': int(run_id or 0), 's': self._batch})
            self._batch = []

    def _put(self, m):
        if self.state != 'live':
            return
        try:
            self._out.put_nowait(json.dumps(m, separators=(',', ':')))
        except queue.Full:
            pass

    # ---- the others
    def others(self, now=None):
        """The drivers heard from lately (on your stage: the relay only sends those)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            for k in [k for k, d in self.drivers.items() if now - d.seen > STALE_S]:
                del self.drivers[k]
            return list(self.drivers.values())

    def _hello(self):
        m = {'t': 'hello', 'v': 1, 'name': self.name, 'car': self.car}
        if self._ticket:
            m['ticket'] = self._ticket['ticket']
        return m

    def _get_ticket(self):
        """The server's ticket, kept until half an hour before it runs out. -> False when we are not signed in."""
        if self.ticket_fn is None:
            return True
        if self._ticket and self._ticket.get('expires', 0) / 1000.0 - time.time() > 1800:
            return True
        try:
            self._ticket = self.ticket_fn()
        except Exception:
            self._ticket = None
        if self._ticket:
            self.name = self._ticket.get('name') or self.name
        return bool(self._ticket)

    def _got(self, m):
        now = time.monotonic()
        t = m.get('t')
        with self._lock:
            if t == 'error':
                self._ticket = None                  # (refused: a fresh ticket next time)
                self._refused = True
            elif t == 'welcome':
                self.my_id = m.get('id')
            elif t == 's':
                did = m.get('id')
                d = self.drivers.get(did)
                if d is None or d.run != m.get('run'):
                    d = self.drivers[did] = LiveDriver(did, m.get('name') or 'Driver', m.get('car') or '', m.get('run'))
                    d.sid = m.get('sid') or ''
                d.add(m.get('s') or [], now)
            elif t == 'bye':
                self.drivers.pop(m.get('id'), None)

    # ---- the connection
    def _run_loop(self):
        tries = 0
        while self.on:
            try:
                self.state = 'connecting'
                self._refused = False
                self._get_ticket()                   # (none: the relay says whether it wants one)
                ws = self._ws = WebSocket(self.url)
                ws.sock.settimeout(None)
                self._joined = None                  # (told again on this connection)
                ws.send(json.dumps(self._hello()))
                self.state = 'live'
                tries = 0
                threading.Thread(target=self._writer, args=(ws,), daemon=True).start()
                while self.on:
                    try:
                        m = json.loads(ws.recv())
                    except ValueError:
                        continue
                    if isinstance(m, dict):
                        self._got(m)
            except Exception:
                pass
            finally:
                self.state = 'signin' if getattr(self, '_refused', False) else 'offline'
                if self._ws is not None:
                    self._ws.close()
                    self._ws = None
                with self._lock:
                    self.drivers.clear()
            if not self.on:
                break
            time.sleep(RETRY_S[min(tries, len(RETRY_S) - 1)])
            tries += 1

    def _writer(self, ws):
        while self.on and self._ws is ws:
            try:
                text = self._out.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                ws.send(text)
            except Exception:
                ws.close()
                return

    def close(self):
        self.on = False
        if self._ws is not None:
            self._ws.close()
