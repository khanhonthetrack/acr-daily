"""ACR Daily live relay: where everyone on a stage is right now, passed on to everyone else on it (ghost cars).

    python3 relay.py [--port 8765] [--host 127.0.0.1]

Standard library only (Python 3.9+): a small WebSocket server (RFC 6455, text frames). Each app connects to /live,
says hello, then sends its car's samples while its stage clock runs; the relay sends them on to the other drivers
on the same stage (the stage name the game reports). Nothing is stored.

  app -> relay   {"t": "hello", "v": 1, "name": "...", "car": "..."}
                 {"t": "track", "track": "..."}      (on this stage, not driving yet: hears the others)
                 {"t": "s", "track": "...", "run": <run id>, "s": [[clockMs, x, y, z, heading, pitch, roll], ...]}
                 {"t": "leave"}                     (off the stage)
  relay -> app   {"t": "welcome", "id": <your id>}
                 {"t": "s", "id": <driver id>, "name": "...", "car": "...", "run": ..., "s": [...]}
                 {"t": "bye", "id": <driver id>}      (they left the stage or closed the app)

GET / (no upgrade) answers how many drivers are connected: a health check.
Limits: 16 KB a message, 25 messages a second, 30 samples a message, 500 connections; quiet for 60 s = closed.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import math
import re
import struct
import time

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
MAX_MSG = 16 * 1024
MAX_RATE = 25            # messages a second (a second's bucket)
MAX_SAMPLES = 30
MAX_CONNS = 500
IDLE_S = 60
PING_S = 15


def clean(s, n):
    s = re.sub(r'[\x00-\x1f\x7f]', '', str(s or ''))
    return s[:n]


def room_of(track):
    return re.sub(r'[^a-z0-9]', '', clean(track, 80).lower())[:48]


def good_sample(x):
    return (isinstance(x, list) and len(x) == 7 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in x)
            and 0 <= x[0] < 3600 * 1000 * 3 and all(abs(v) < 1e6 for v in x[1:4]))


class Conn:
    _next = 1

    def __init__(self, reader, writer):
        self.r, self.w = reader, writer
        self.id = Conn._next
        Conn._next += 1
        self.name, self.car, self.room = 'Driver', '', None
        self.hello = False
        self.bucket, self.bucket_at = 0, 0.0
        self.last = time.monotonic()
        self.lock = asyncio.Lock()

    async def send_text(self, text):
        data = text.encode()
        n = len(data)
        head = bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n) if n < 65536
                                else bytes([127]) + struct.pack('>Q', n))
        async with self.lock:
            self.w.write(head + data)
            await self.w.drain()

    async def send_ctl(self, opcode, payload=b''):
        async with self.lock:
            self.w.write(bytes([0x80 | opcode, len(payload)]) + payload)
            await self.w.drain()

    async def read_frame(self):
        """-> (opcode, payload) of one whole message (continuations joined)."""
        parts, first_op = [], None
        while True:
            b1, b2 = await self.r.readexactly(2)
            fin, op, masked, n = b1 & 0x80, b1 & 0x0f, b2 & 0x80, b2 & 0x7f
            if n == 126:
                n = struct.unpack('>H', await self.r.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', await self.r.readexactly(8))[0]
            if not masked:
                raise ValueError('client frames must be masked')
            if n > MAX_MSG or sum(map(len, parts)) + n > MAX_MSG:
                raise ValueError('message too big')
            mask = await self.r.readexactly(4)
            data = bytearray(await self.r.readexactly(n))
            for i in range(n):
                data[i] ^= mask[i & 3]
            if op >= 8:                          # control frames come whole, between fragments
                return op, bytes(data)
            if first_op is None:
                first_op = op
            parts.append(bytes(data))
            if fin:
                return first_op, b''.join(parts)


class Relay:
    def __init__(self):
        self.conns = set()
        self.rooms = {}                          # room -> set of Conn

    def leave(self, c):
        if c.room and c in self.rooms.get(c.room, ()):
            self.rooms[c.room].discard(c)
            if not self.rooms[c.room]:
                del self.rooms[c.room]
            return True
        return False

    async def broadcast(self, room, text, but=None):
        for o in list(self.rooms.get(room, ())):
            if o is not but:
                try:
                    await asyncio.wait_for(o.send_text(text), 2.0)
                except Exception:
                    pass

    async def handle(self, reader, writer):
        try:
            req = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 10)
        except Exception:
            writer.close()
            return
        lines = req.decode('latin-1').split('\r\n')
        headers = {k.strip().lower(): v.strip() for k, _s, v in (l.partition(':') for l in lines[1:] if ':' in l)}
        path = lines[0].split(' ')[1] if len(lines[0].split(' ')) > 1 else '/'
        if headers.get('upgrade', '').lower() != 'websocket':
            body = ('ACR Daily live relay: %d drivers, %d stages\n' % (len(self.conns), len(self.rooms))).encode()
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'
                         % len(body) + body)
            await writer.drain()
            writer.close()
            return
        key = headers.get('sec-websocket-key', '')
        if not path.startswith('/live') or not key or len(self.conns) >= MAX_CONNS:
            writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
            writer.close()
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        writer.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Sec-WebSocket-Accept: %s\r\n\r\n' % accept).encode())
        await writer.drain()
        c = Conn(reader, writer)
        self.conns.add(c)
        pinger = asyncio.ensure_future(self.ping(c))
        try:
            await c.send_text(json.dumps({'t': 'welcome', 'id': c.id}))
            while True:
                op, data = await asyncio.wait_for(c.read_frame(), IDLE_S)
                c.last = time.monotonic()
                if op == 8:                      # close
                    break
                if op == 9:                      # ping
                    await c.send_ctl(10, data[:125])
                    continue
                if op != 1:
                    continue
                now = time.monotonic()
                if now - c.bucket_at >= 1.0:
                    c.bucket, c.bucket_at = 0, now
                c.bucket += 1
                if c.bucket > MAX_RATE:
                    continue
                try:
                    m = json.loads(data.decode('utf-8'))
                except ValueError:
                    continue
                await self.message(c, m)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError, OSError):
            pass
        finally:
            pinger.cancel()
            self.conns.discard(c)
            room = c.room
            if self.leave(c):
                await self.broadcast(room, json.dumps({'t': 'bye', 'id': c.id}))
            try:
                writer.close()
            except Exception:
                pass

    async def message(self, c, m):
        if not isinstance(m, dict):
            return
        t = m.get('t')
        if t == 'hello':
            c.name = clean(m.get('name'), 24).strip() or 'Driver'
            c.car = clean(m.get('car'), 48)
            c.hello = True
        elif t in ('s', 'track') and c.hello:
            room = room_of(m.get('track'))
            if not room:
                return
            if room != c.room:
                old = c.room
                if self.leave(c):
                    await self.broadcast(old, json.dumps({'t': 'bye', 'id': c.id}))
                c.room = room
                self.rooms.setdefault(room, set()).add(c)
            if t == 'track':                     # on this stage (not driving yet): hears the others
                return
            samples = [x for x in (m.get('s') or [])[:MAX_SAMPLES] if good_sample(x)]
            run = m.get('run') if isinstance(m.get('run'), int) else 0
            if samples:
                await self.broadcast(room, json.dumps({'t': 's', 'id': c.id, 'name': c.name, 'car': c.car, 'run': run,
                                                       's': samples}, separators=(',', ':')), but=c)
        elif t == 'leave':
            room = c.room
            if self.leave(c):
                c.room = None
                await self.broadcast(room, json.dumps({'t': 'bye', 'id': c.id}))

    async def ping(self, c):
        try:
            while True:
                await asyncio.sleep(PING_S)
                await c.send_ctl(9, b'p')
        except Exception:
            pass


async def main(host, port):
    relay = Relay()
    server = await asyncio.start_server(relay.handle, host, port)
    print('ACR Daily live relay on %s:%d' % (host, port), flush=True)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    asyncio.run(main(a.host, a.port))
