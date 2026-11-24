"""ACR Daily live relay: where everyone on a stage is right now, passed on to everyone else on it (ghost cars).

    python3 relay.py --key-file ~/acr-live/live.key [--port 8765] [--host 127.0.0.1]
                     [--peer-host 10.90.1.10 --peer-port 8766]
                     [--node-id 1] [--peer ws://10.90.2.10:8766/live --peer ws://10.90.3.10:8766/live]

Standard library only (Python 3.9+): a small WebSocket server (RFC 6455, text frames). Each app connects to /live,
says hello with its ticket, then sends its car's samples while its stage clock runs; the relay sends them on to the
other drivers on the same stage (the stage name the game reports). Nothing is stored.

Names are checked: the ticket is the driver's Steam id and name signed by the ACR Daily server (server/src/
livetickets.js) with a key the relay holds as hex in --key-file (sha256 of 'live-relay|' + the server's ADMIN_KEY:
it checks tickets, nothing more). One connection per driver: a new one closes the old. Without --key-file the relay
takes the names it is told (for tests on one PC only).

  app -> relay   {"t": "hello", "v": 1, "ticket": "...", "car": "...", "watch": false}
                 {"t": "track", "track": "...", "at": [x, z], "room": "..."}
                 {"t": "s", "track": "...", "at": [x, z], "room": "...", "run": <run id>, "s": [[clockMs, x, y, z, heading, pitch, roll], ...]}
                 {"t": "x", "b": "..."}             (in a COPILOT crew's room, "cp:<lobby>": passed on to the partner
                                                    as {"t": "x", "id", "sid", "b"}, locally and across peer relays)
                 {"t": "leave"}                     (off the stage)
                 {"t": "follow", "id": <driver id or 0>}   (WATCH: that driver's every message, however far)
  relay -> app   {"t": "welcome", "id": <your id>}
                 {"t": "error", "e": "ticket"}       (no good ticket: then closed)
                 {"t": "s", "id": <driver id>, "sid": "<Steam id>", "name": "...", "car": "...", "run": ...,
                  "root": [forward, up], "s": [...]}
                 {"t": "bye", "id": <driver id>}      (they left the stage or closed the app)

Multi-region mesh (--node-id, --peer-port, --peer):
- Public players connect on --port (never allowed to send peer_hello when --peer-port is enabled).
- Regional relay nodes connect to each other's --peer-port over the private VPC, authenticating with HMAC derived from
  --key-file plus anti-replay nonces.
- Each connection has its own bounded non-blocking send queue (drop-oldest on congestion) and C-speed frame masking, so
  one slow Wi-Fi player can never stall other drivers or cross-region peer streams.
"""
import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import re
import signal
import ssl
import struct
import time
from urllib.parse import urlparse

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
MAX_MSG = 16 * 1024
MAX_PEER_MSG = 64 * 1024
MAX_RATE = 25            # messages a second (a second's bucket, for player connections)
MAX_CREW_RATE = 260      # a COPILOT crew's own messages ('x': its voice when the apps can't reach each other directly):
                         # a CASUAL driver passes on up to 3 co-drivers' voices besides their own (4 x 50 a second)
CREW_ROOM = re.compile(r'^cp:[0-9]{1,12}$')   # a crew's room on the relay (copilot.py: cp:<lobby>, cp:<1000000+lobby>)
MAX_CREW_B = 4000        # ... and their size (characters of their payload)
MAX_SAMPLES = 30
MAX_CONNS = 500
MAX_PEERS = 16
MAX_SHADOWS = 2000
OUT_QUEUE_MAX = 320      # comfortably above MAX_CREW_RATE (260/s for 4-player CASUAL voice bursts)
HELLO_S = 5.0            # must complete hello / peer_hello within 5 s of connecting
IDLE_S = 60
PING_S = 15
SHADOW_SYNC_S = 10.0     # periodic refresh of active local drivers over peer links
SHADOW_STALE_S = 30.0    # evict remote shadow drivers not refreshed within 30 s
PEER_SKEW_MS = 60_000
NEAR_M = 600             # one of your NEAR_MAX nearest within this: their every message; the others: one in FAR_EVERY
NEAR_MAX = 12
FAR_EVERY = 10


def clean(s, n):
    s = re.sub(r'[\x00-\x1f\x7f]', '', str(s or ''))
    return s[:n]


def room_of(track, tag=None):
    """The stage's room name: the stage the game reports, after the room's own tag when there is one (a live rally's
    session: only its drivers in it)."""
    name = re.sub(r'[^a-z0-9]', '', clean(track, 80).lower())[:48]
    tag = re.sub(r'[^a-z0-9:_-]', '', clean(tag, 40).lower()) if isinstance(tag, str) else ''
    return '%s|%s' % (tag, name) if name and tag else name


ANCHOR_M = 1500          # two drivers whose stage starts are further apart than this are on different stages
# (the name the game reports is not enough: "Alsace Forêt" is two stages, Forêt de Munster and Forêt de Saverne)


def good_at(at):
    return (isinstance(at, list) and len(at) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) and abs(v) < 1e6
                                                           for v in at))


def xor_mask(data, mask):
    """Fast C-level XOR masking/unmasking for RFC 6455 frames."""
    n = len(data)
    if not n:
        return b''
    key = (mask * ((n >> 2) + 1))[:n]
    return (int.from_bytes(data, 'big') ^ int.from_bytes(key, 'big')).to_bytes(n, 'big')


def encode_text_frame(text):
    """Encode a server->client unmasked RFC 6455 text frame once for zero-copy fan-out."""
    data = text.encode('utf-8')
    n = len(data)
    head = bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack('>H', n) if n < 65536
                            else bytes([127]) + struct.pack('>Q', n))
    return head + data


def mask_frame(opcode, payload):
    n = len(payload)
    head = bytes([0x80 | opcode]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n)
                                     if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n))
    mask = os.urandom(4)
    return head + mask + xor_mask(payload, mask)


def peer_subkey(key):
    return hashlib.sha256(b'peer-mesh|' + key).digest() if key else None


def make_peer_hello(key, node_id, now_ms=None, duplex=False):
    now_ms = int(time.time() * 1000 if now_ms is None else now_ms)
    nonce = os.urandom(12).hex()
    msg = {'t': 'peer_hello', 'node': int(node_id), 'ts': now_ms, 'nonce': nonce}
    if duplex:
        msg['duplex'] = True
    if key is not None:
        suffix = '|duplex' if duplex else ''
        raw = ('peer|%d|%d|%s%s' % (int(node_id), now_ms, nonce, suffix)).encode('utf-8')
        msg['sig'] = hmac.new(peer_subkey(key), raw, hashlib.sha256).hexdigest()
    return msg


def read_ticket(key, ticket, now_ms=None):
    """A ticket from the ACR Daily server -> {'s': Steam id, 'n': name, 'e': expiry} or None (not signed with key,
    changed, or out of date). Same rules as server/src/livetickets.js readLiveTicket."""
    parts = str(ticket or '').split('.')
    if len(parts) != 2 or not key:
        return None
    payload, sig = parts
    want = base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()).decode().rstrip('=')
    if not hmac.compare_digest(want, sig):
        return None
    try:
        t = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)).decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return None
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    if not isinstance(t, dict) or t.get('k') != 'live' or not isinstance(t.get('s'), str) or not isinstance(t.get('n'), str):
        return None
    return t if isinstance(t.get('e'), (int, float)) and t['e'] > now_ms else None


def good_sample(x):
    return (isinstance(x, list) and len(x) == 7 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in x)
            and 0 <= x[0] < 3600 * 1000 * 3 and all(abs(v) < 1e6 for v in x[1:4]))


def good_dash(x):
    """A driver's dash: [clockMs, km/h, gear, rpm, throttle, brake, steering], plain numbers in their ranges."""
    return (isinstance(x, list) and len(x) == 7 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                         and math.isfinite(v) for v in x)
            and 0 <= x[0] < 3600 * 1000 * 3 and 0 <= x[1] < 1000 and -1 <= x[2] < 20 and 0 <= x[3] < 30000
            and all(-1.5 <= v <= 1.5 for v in x[4:7]))


class ShadowDriver:
    """A driver connected to another regional relay node, represented in this node's stage room for nearest/follow."""

    def __init__(self, did):
        self.id = int(did)
        self.watch = False               # never sent packets directly; only local watchers receive broadcasts
        self.is_shadow = True
        self.room = None
        self.pos = None
        self.sent = 0
        self.near = None
        self.follow = None
        self.seen = time.monotonic()


class Conn:
    _next = 1

    def __init__(self, reader, writer, cid=None):
        self.r, self.w = reader, writer
        if cid is None:
            self.id = Conn._next
            Conn._next += 1
        else:
            self.id = int(cid)
        self.name, self.car, self.room, self.sid = 'Driver', '', None, ''
        self.raw_track, self.raw_at, self.raw_room_tag = '', None, ''
        self.hello = False
        self.is_peer = False
        self.peer_node = None
        self.shadows = {}                        # remote driver id -> ShadowDriver (for inbound peer conns)
        self.watch = True                        # False: sends only (ghost cars off): gets nobody's samples or byes
        self.pos = None                          # where they are [x, z]: their newest sample, or their stage's start
        self.sent = 0                            # their sample messages so far (one in FAR_EVERY goes to the far ones)
        self.near = None                         # the ids of the drivers they get in full (None: not known, all)
        self.follow = None                       # WATCH: the driver they follow, in full however far (follow message)
        self.bucket, self.bucket_at = 0, 0.0
        self.xbucket = 0                         # (this second's crew messages: 'x')
        self.crew = None                         # their crew's room (a 'crew' message), whatever stage they are on, if any
        self.last = time.monotonic()
        self.lock = asyncio.Lock()
        self.out_q = asyncio.Queue(maxsize=OUT_QUEUE_MAX) if writer is not None else None

    def enqueue_frame(self, frame_bytes, critical=False):
        if self.out_q is None:
            return
        try:
            self.out_q.put_nowait(frame_bytes)
        except asyncio.QueueFull:
            if critical:
                try:
                    self.out_q.get_nowait()
                    self.out_q.put_nowait(frame_bytes)
                except Exception:
                    pass
            else:
                # Drop oldest queued sample batch so slow client gets freshest positions without stalling others
                try:
                    self.out_q.get_nowait()
                    self.out_q.put_nowait(frame_bytes)
                except Exception:
                    pass

    async def writer_loop(self):
        try:
            while True:
                first = await self.out_q.get()
                batch = [first]
                while len(batch) < 32 and not self.out_q.empty():
                    try:
                        batch.append(self.out_q.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                payload = batch[0] if len(batch) == 1 else b''.join(batch)
                async with self.lock:
                    self.w.write(payload)
                    await asyncio.wait_for(self.w.drain(), 4.0)
        except asyncio.CancelledError:
            pass
        except Exception:
            try:
                self.w.close()
            except Exception:
                pass

    async def send_text(self, text):
        frame = encode_text_frame(text)
        async with self.lock:
            self.w.write(frame)
            await self.w.drain()

    async def send_ctl(self, opcode, payload=b''):
        async with self.lock:
            self.w.write(bytes([0x80 | opcode, len(payload)]) + payload)
            await self.w.drain()

    async def read_frame(self):
        """-> (opcode, payload) of one whole message (continuations joined)."""
        parts, first_op = [], None
        limit = MAX_PEER_MSG if self.is_peer else MAX_MSG
        while True:
            b1, b2 = await self.r.readexactly(2)
            fin, op, masked, n = b1 & 0x80, b1 & 0x0f, b2 & 0x80, b2 & 0x7f
            if n == 126:
                n = struct.unpack('>H', await self.r.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', await self.r.readexactly(8))[0]
            if not masked:
                raise ValueError('client frames must be masked')
            if n > limit or sum(map(len, parts)) + n > limit:
                raise ValueError('message too big')
            mask = await self.r.readexactly(4)
            raw = await self.r.readexactly(n)
            data = xor_mask(raw, mask)
            if op >= 8:                          # control frames come whole, between fragments
                return op, data
            if first_op is None:
                first_op = op
            parts.append(data)
            if fin:
                return first_op, b''.join(parts)


class _DuplexPeerConn:
    """Inbound shadow holder for a full-duplex outbound drain-bridge PeerOut."""
    def __init__(self, peer_node):
        self.peer_node = int(peer_node)
        self.is_peer = True
        self.duplex = False
        self.watch = False
        self.out_q = None
        self.shadows = {}


class PeerOut:
    """Persistent outbound WebSocket link pushing this relay's local driver events to one peer relay."""

    def __init__(self, relay_srv, url, duplex=False):
        self.relay = relay_srv
        self.url = url
        self.duplex = bool(duplex)
        self.connected = False
        self._q = asyncio.Queue(maxsize=1000)
        self._crit = asyncio.Queue(maxsize=512)  # dedicated critical control queue (bye / track / sid never dropped)
        self._closed = False
        self._task = None

    def start(self):
        if self._task is None:
            self._task = asyncio.ensure_future(self._run())

    def stop(self):
        self._closed = True
        if self._task is not None:
            self._task.cancel()

    def push(self, msg, critical=False):
        if not self.connected or self._closed:
            return
        raw = json.dumps(msg, separators=(',', ':'))
        q = self._crit if critical else self._q
        try:
            q.put_nowait(raw)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(raw)
            except Exception:
                pass

    @staticmethod
    async def _read_server_frame(reader):
        parts, first_op = [], None
        while True:
            b1, b2 = await reader.readexactly(2)
            fin, op, masked, n = b1 & 0x80, b1 & 0x0f, b2 & 0x80, b2 & 0x7f
            if n == 126:
                n = struct.unpack('>H', await reader.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', await reader.readexactly(8))[0]
            if n > MAX_PEER_MSG or sum(map(len, parts)) + n > MAX_PEER_MSG:
                raise ValueError('peer frame too big')
            mask = await reader.readexactly(4) if masked else None
            raw = await reader.readexactly(n)
            data = xor_mask(raw, mask) if mask else raw
            if op >= 8:
                return op, data
            if first_op is None:
                first_op = op
            parts.append(data)
            if fin:
                return first_op, b''.join(parts)

    async def _run(self):
        backoff = (0.5, 1.0, 2.0, 5.0)
        tries = 0
        while not self._closed:
            writer = None
            sender_task = None
            ping_task = None
            sync_task = None
            duplex_conn = None
            try:
                u = urlparse(self.url)
                host = u.hostname or '127.0.0.1'
                port = u.port or (443 if u.scheme == 'wss' else 80)
                path = (u.path or '/live') + ('?' + u.query if u.query else '')
                ssl_ctx = ssl.create_default_context() if u.scheme == 'wss' else None
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port, ssl=ssl_ctx, server_hostname=host if ssl_ctx else None),
                    8.0,
                )
                ws_key = base64.b64encode(os.urandom(16)).decode()
                req = ('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                       'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n'
                       % (path, host, port, ws_key)).encode()
                writer.write(req)
                await writer.drain()
                resp = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 8.0)
                if b' 101 ' not in resp.split(b'\r\n', 1)[0]:
                    raise ConnectionError('peer handshake rejected')

                op, _data = await asyncio.wait_for(self._read_server_frame(reader), 5.0)
                if op != 1:
                    raise ConnectionError('unexpected initial frame')
                hello = make_peer_hello(self.relay.key, self.relay.node_id, duplex=self.duplex)
                write_lock = asyncio.Lock()

                async def send_masked(opcode, payload_bytes):
                    async with write_lock:
                        writer.write(mask_frame(opcode, payload_bytes))
                        await asyncio.wait_for(writer.drain(), 5.0)

                await send_masked(1, json.dumps(hello, separators=(',', ':')).encode('utf-8'))
                op, data = await asyncio.wait_for(self._read_server_frame(reader), 5.0)
                ack = json.loads(data.decode('utf-8')) if op == 1 else {}
                if ack.get('t') != 'peer_welcome':
                    raise ConnectionError('peer auth rejected: %s' % ack)
                if self.duplex and isinstance(ack.get('node'), int) and ack['node'] != self.relay.node_id:
                    duplex_conn = _DuplexPeerConn(ack['node'])
                    self.relay.peer_conns.add(duplex_conn)

                for q in (self._q, self._crit):
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                self.connected = True
                tries = 0
                for snap in self.relay.snapshot_local_drivers():
                    self.push(snap, critical=True)

                async def sender():
                    while not self._closed:
                        if not self._crit.empty():
                            raw = self._crit.get_nowait()
                        else:
                            done_c = asyncio.ensure_future(self._crit.get())
                            done_q = asyncio.ensure_future(self._q.get())
                            done, pending = await asyncio.wait({done_c, done_q}, return_when=asyncio.FIRST_COMPLETED)
                            for p in pending:
                                p.cancel()
                            raw = next(iter(done)).result()
                        await send_masked(1, raw.encode('utf-8'))

                async def pinger():
                    while not self._closed:
                        await asyncio.sleep(PING_S)
                        await send_masked(9, b'p')

                async def syncer():
                    while not self._closed:
                        await asyncio.sleep(SHADOW_SYNC_S)
                        for snap in self.relay.snapshot_local_drivers(tracks_only=True):
                            self.push(snap, critical=False)

                sender_task = asyncio.ensure_future(sender())
                ping_task = asyncio.ensure_future(pinger())
                sync_task = asyncio.ensure_future(syncer())

                while not self._closed:
                    op, payload = await asyncio.wait_for(self._read_server_frame(reader), IDLE_S)
                    if op == 8:
                        break
                    if op == 9:
                        await send_masked(10, payload[:125])
                    elif op == 1 and duplex_conn is not None:
                        try:
                            msg = json.loads(payload.decode('utf-8'))
                        except ValueError:
                            continue
                        if isinstance(msg, dict):
                            await self.relay._peer_message(duplex_conn, msg)
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            finally:
                self.connected = False
                if duplex_conn is not None:
                    self.relay.peer_conns.discard(duplex_conn)
                    for sh in list(duplex_conn.shadows.values()):
                        old_room = sh.room
                        if self.relay.leave(sh):
                            await self.relay.broadcast(old_room, json.dumps({'t': 'bye', 'id': sh.id}), critical=True)
                    duplex_conn.shadows.clear()
                for t in (sender_task, ping_task, sync_task):
                    if t is not None:
                        t.cancel()
                if writer is not None:
                    try:
                        writer.close()
                    except Exception:
                        pass
            if self._closed:
                break
            await asyncio.sleep(backoff[min(tries, len(backoff) - 1)])
            tries += 1


class Relay:
    def __init__(self, key=None, node_id=1, peers=(), separate_peer_port=False, drain_peer=''):
        self.key = key                           # None: names not checked (tests on one PC)
        self.node_id = max(1, int(node_id or 1))
        self.separate_peer_port = bool(separate_peer_port)
        self.drain_peer = (drain_peer or '').strip()
        self.draining = False
        self._drain_settled = False
        self._drain_task = None
        self.drain_done = asyncio.Event()
        # Incorporate boot epoch bits so IDs never collide across quick node restarts, while staying within node slice:
        # [node_id * 10_000_000 .. (node_id + 1) * 10_000_000)
        self._id_base = self.node_id * 10_000_000 + (int(time.time()) % 9000) * 1000
        self._seq = 0
        self.conns = set()                       # local player connections
        self.peer_conns = set()                  # authenticated inbound peer connections
        self.peer_outs = [PeerOut(self, u) for u in (peers or ()) if u]
        self._seen_nonces = {}                   # (node, nonce) -> expiry monotonic s
        self.rooms = {}                          # (stage name, n) -> set of Conn / ShadowDriver
        self.crews = {}                          # a crew's room ('cp:<n>') -> set of Conn: its voice in the menus too
        self.anchors = {}                        # (stage name, n) -> where that stage starts [x, z] (or None)
        self._n = 0
        self._near_at = {}                       # room -> when its drivers' nearest were worked out
        self._sweep_task = None

    def next_id(self):
        self._seq = (self._seq + 1) % 10_000_000
        offset = (self._id_base % 10_000_000 + self._seq) % 9_999_999 + 1
        return self.node_id * 10_000_000 + offset

    def start_peers(self):
        for p in self.peer_outs:
            p.start()
        if self._sweep_task is None:
            self._sweep_task = asyncio.ensure_future(self._sweep_shadows_loop())

    def stop_peers(self):
        for p in self.peer_outs:
            p.stop()
        if self._sweep_task is not None:
            self._sweep_task.cancel()
            self._sweep_task = None
        if self._drain_task is not None:
            self._drain_task.cancel()
            self._drain_task = None

    def begin_drain(self, settle_s=10.0, timeout_s=1740.0):
        """Enter zero-drop rollout drain: flip /readyz to 503 so new drivers go to the new pod, bridge live ghosts
        bidirectionally to the new pod, keep all mid-stage drivers undisturbed up to timeout_s (default ~29 min), and
        exit immediately once the last mid-stage driver finishes."""
        if self.draining:
            return self._drain_task
        self.draining = True
        self._drain_task = asyncio.ensure_future(self._run_drain(float(settle_s), float(timeout_s)))
        return self._drain_task

    async def _close_player_conn(self, c):
        try:
            await c.send_ctl(8, b'')
        except Exception:
            pass
        try:
            c.w.close()
        except Exception:
            pass

    async def _run_drain(self, settle_s, timeout_s):
        try:
            deadline = time.monotonic() + max(0.5, timeout_s)
            if settle_s > 0:
                await asyncio.sleep(min(settle_s, max(0.1, deadline - time.monotonic())))
            self._drain_settled = True
            if self.drain_peer:
                bridge = PeerOut(self, self.drain_peer, duplex=True)
                self.peer_outs.append(bridge)
                bridge.start()
            while time.monotonic() < deadline:
                now = time.monotonic()
                # Hand off menu-idle clients (neither on a stage nor in a crew room) cleanly to the new Ready pod
                for c in list(self.conns):
                    if c.room is None and getattr(c, 'crew', None) is None and now - getattr(c, 'connected_at', 0.0) > 1.0:
                        await self._close_player_conn(c)
                if not self.conns:
                    break
                await asyncio.sleep(0.25)
            for c in list(self.conns):
                await self._close_player_conn(c)
        except asyncio.CancelledError:
            raise
        finally:
            self.drain_done.set()

    async def _sweep_shadows_loop(self):
        try:
            while True:
                await asyncio.sleep(5.0)
                await self.sweep_stale_shadows()
                for pc in list(self.peer_conns):
                    if getattr(pc, 'duplex', False) and pc.out_q is not None:
                        for snap in self.snapshot_local_drivers(tracks_only=True):
                            pc.enqueue_frame(encode_text_frame(json.dumps(snap, separators=(',', ':'))), critical=False)
        except asyncio.CancelledError:
            pass

    async def sweep_stale_shadows(self, now=None):
        now = time.monotonic() if now is None else now
        for pc in list(self.peer_conns):
            for did, sh in list(pc.shadows.items()):
                if now - sh.seen > SHADOW_STALE_S:
                    pc.shadows.pop(did, None)
                    old_room = sh.room
                    if self.leave(sh):
                        await self.broadcast(old_room, json.dumps({'t': 'bye', 'id': sh.id}), critical=True)

    def _push_peers(self, msg, critical=False):
        for p in self.peer_outs:
            p.push(msg, critical=critical)
        frame = None
        for pc in list(self.peer_conns):
            if getattr(pc, 'duplex', False) and pc.out_q is not None:
                if frame is None:
                    frame = encode_text_frame(json.dumps(msg, separators=(',', ':')))
                pc.enqueue_frame(frame, critical=critical)

    def snapshot_local_drivers(self, tracks_only=False):
        out = []
        for c in list(self.conns):
            if not c.hello or c.is_peer:
                continue
            if c.sid and not tracks_only:
                out.append({'t': 'peer_sid', 'id': c.id, 'sid': c.sid})
            if c.room and c.raw_track:
                out.append({
                    't': 'peer_track',
                    'id': c.id,
                    'track': c.raw_track,
                    'at': c.raw_at,
                    'room': c.raw_room_tag,
                    'pos': c.pos,
                })
        return out

    def room_for(self, c, track, at, tag=None):
        """The room for a driver on `track` whose stage starts at `at` (tag: a room of its own, see the top): the one
        they are in if it still fits, else one of that name starting within ANCHOR_M, else a new one."""
        name = room_of(track, tag)
        if not name:
            return None
        at = at if good_at(at) else None
        near = lambda key: at is None or self.anchors.get(key) is None or math.dist(at, self.anchors[key]) <= ANCHOR_M
        if c.room and c.room[0] == name and near(c.room):
            if at is not None and self.anchors.get(c.room) is None:
                self.anchors[c.room] = at
            return c.room
        for key in self.rooms:
            if key[0] == name and near(key):
                return key
        self._n += 1
        key = (name, self._n)
        self.anchors[key] = at
        return key

    def crew_leave(self, c):
        crew = getattr(c, 'crew', None)
        if crew and c in self.crews.get(crew, ()):
            self.crews[crew].discard(c)
            if not self.crews[crew]:
                del self.crews[crew]
        c.crew = None

    def leave(self, c):
        if c.room and c in self.rooms.get(c.room, ()):
            self.rooms[c.room].discard(c)
            if not self.rooms[c.room]:
                del self.rooms[c.room]
                self.anchors.pop(c.room, None)
                self._near_at.pop(c.room, None)
            return True
        return False

    def nearest(self, room, now=None):
        """Each driver in the room: the ids of the NEAR_MAX nearest to them within NEAR_M (worked out once a second)."""
        now = time.monotonic() if now is None else now
        if now - self._near_at.get(room, -1e9) < 1.0:
            return
        self._near_at[room] = now
        conns = [c for c in self.rooms.get(room, ()) if c.pos]
        for o in self.rooms.get(room, ()):
            if not o.watch:                      # (sends only, or a remote shadow driver: nobody's samples to rank)
                continue
            if not o.pos:
                o.near = None
                continue
            d = sorted((math.dist(o.pos, c.pos), c.id) for c in conns if c is not o)
            o.near = {cid for dist, cid in d[:NEAR_MAX] if dist <= NEAR_M}
            if o.follow is not None:             # (WATCH: the one followed, however far from the watcher's car)
                o.near.add(o.follow)

    async def broadcast(self, room, text, but=None, near=None, critical=False):
        """To everyone in the room but `but`; near: a driver's samples, all of them only to those they are one of the
        nearest of (nearest()), the others this message only if it is one in FAR_EVERY."""
        every = near is None or near.sent % FAR_EVERY == 0 or not near.pos
        frame = None
        for o in list(self.rooms.get(room, ())):
            if o is but or not o.watch:
                continue
            if not every and o.near is not None and near.id not in o.near:
                continue
            out_q = getattr(o, 'out_q', None)
            if out_q is not None and 'send_text' not in o.__dict__:
                if frame is None:
                    frame = encode_text_frame(text)
                o.enqueue_frame(frame, critical=critical)
            else:
                try:
                    await asyncio.wait_for(o.send_text(text), 2.0)
                except Exception:
                    pass

    def _verify_peer_hello(self, m):
        node = m.get('node')
        ts = m.get('ts')
        nonce = m.get('nonce')
        duplex = bool(m.get('duplex'))
        if not (isinstance(node, int) and not isinstance(node, bool) and 1 <= node <= 999 and node != self.node_id):
            return None
        if not (isinstance(ts, (int, float)) and abs(time.time() * 1000 - ts) <= PEER_SKEW_MS):
            return None
        if not (isinstance(nonce, str) and 8 <= len(nonce) <= 64):
            return None
        if self.key is not None:
            sig = str(m.get('sig') or '')
            suffix = '|duplex' if duplex else ''
            raw = ('peer|%d|%d|%s%s' % (node, int(ts), nonce, suffix)).encode('utf-8')
            want = hmac.new(peer_subkey(self.key), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(want, sig):
                return None
        mono = time.monotonic()
        if len(self._seen_nonces) > 256:
            self._seen_nonces = {k: exp for k, exp in self._seen_nonces.items() if exp > mono}
        nk = (node, nonce)
        if self._seen_nonces.get(nk, 0) > mono:
            return None
        self._seen_nonces[nk] = mono + 120.0
        return node

    async def handle(self, reader, writer):
        await self._serve_ws(reader, writer, peer_listener=False)

    async def handle_peer(self, reader, writer):
        await self._serve_ws(reader, writer, peer_listener=True)

    async def _serve_ws(self, reader, writer, peer_listener=False):
        try:
            req = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5.0)
        except Exception:
            writer.close()
            return
        lines = req.decode('latin-1').split('\r\n')
        headers = {k.strip().lower(): v.strip() for k, _s, v in (l.partition(':') for l in lines[1:] if ':' in l)}
        path = lines[0].split(' ')[1] if len(lines[0].split(' ')) > 1 else '/'
        if headers.get('upgrade', '').lower() != 'websocket':
            clean_path = path.split('?', 1)[0]
            if clean_path == '/readyz':
                status = b'503 Service Unavailable' if self.draining else b'200 OK'
                body = b'draining\n' if self.draining else b'ready\n'
                writer.write(b'HTTP/1.1 %s\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'
                             % (status, len(body)) + body)
                await writer.drain()
                writer.close()
                return
            remote_n = sum(len(p.shadows) for p in self.peer_conns)
            peers_up = sum(1 for p in self.peer_outs if p.connected)
            extra = (' (+ %d remote drivers, %d/%d peers)' % (remote_n, peers_up, len(self.peer_outs))
                     if (self.peer_outs or self.peer_conns) else '')
            drain_tag = ' [DRAINING]' if self.draining else ''
            body = ('ACR Daily live relay: %d drivers (%d with ghost cars on), %d stages%s%s\n'
                    % (len(self.conns), sum(1 for c in self.conns if c.watch), len(self.rooms), extra, drain_tag)).encode()
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'
                         % len(body) + body)
            await writer.drain()
            writer.close()
            return
        key = headers.get('sec-websocket-key', '')
        cap_full = (len(self.peer_conns) >= MAX_PEERS) if peer_listener else (len(self.conns) >= MAX_CONNS)
        if not path.startswith('/live') or not key or cap_full or (not peer_listener and self._drain_settled):
            writer.write(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                         if (not peer_listener and self._drain_settled) else
                         b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
            writer.close()
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        writer.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                      'Sec-WebSocket-Accept: %s\r\n\r\n' % accept).encode())
        await writer.drain()
        c = Conn(reader, writer, cid=self.next_id())
        c.connected_at = time.monotonic()
        if not peer_listener:
            self.conns.add(c)
        connected_at = c.connected_at
        pinger = asyncio.ensure_future(self.ping(c))
        writer_task = asyncio.ensure_future(c.writer_loop())
        try:
            await c.send_text(json.dumps({'t': 'welcome', 'id': c.id, 'node': self.node_id}))
            while True:
                authed = c.hello or c.is_peer
                wait_s = IDLE_S if authed else max(0.2, HELLO_S - (time.monotonic() - connected_at))
                op, data = await asyncio.wait_for(c.read_frame(), wait_s)
                c.last = time.monotonic()
                if not authed and c.last - connected_at > HELLO_S:
                    raise ConnectionError('hello deadline exceeded')
                if op == 8:                      # close
                    break
                if op == 9:                      # ping
                    await c.send_ctl(10, data[:125])
                    continue
                if op != 1:
                    continue
                try:
                    m = json.loads(data.decode('utf-8'))
                except ValueError:
                    continue
                if not c.is_peer:
                    now = time.monotonic()
                    if now - c.bucket_at >= 1.0:
                        c.bucket, c.xbucket, c.bucket_at = 0, 0, now
                    crew = isinstance(m, dict) and m.get('t') == 'x'  # (a COPILOT crew's voice: a bucket of its own)
                    if crew:
                        c.xbucket += 1
                        if c.xbucket > MAX_CREW_RATE:
                            continue
                    else:
                        c.bucket += 1
                        if c.bucket > MAX_RATE:
                            continue
                if peer_listener and not c.is_peer and (not isinstance(m, dict) or m.get('t') != 'peer_hello'):
                    raise ConnectionError('expected peer_hello on peer listener')
                await self.message(c, m, peer_listener=peer_listener)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError, OSError):
            pass
        finally:
            pinger.cancel()
            writer_task.cancel()
            self.conns.discard(c)
            self.peer_conns.discard(c)
            self.crew_leave(c)
            if c.is_peer:
                for sh in list(c.shadows.values()):
                    old_room = sh.room
                    if self.leave(sh):
                        await self.broadcast(old_room, json.dumps({'t': 'bye', 'id': sh.id}), critical=True)
                c.shadows.clear()
            else:
                room = c.room
                if self.leave(c):
                    await self.broadcast(room, json.dumps({'t': 'bye', 'id': c.id}), critical=True)
                    self._push_peers({'t': 'peer_bye', 'id': c.id}, critical=True)
            try:
                writer.close()
            except Exception:
                pass

    async def _peer_message(self, c, m):
        t = m.get('t')
        did = m.get('id')
        if not (isinstance(did, int) and not isinstance(did, bool) and did > 0):
            return
        # Enforce node-id namespace ownership so peer N can only speak for IDs in [N*10_000_000, (N+1)*10_000_000)
        if did // 10_000_000 != c.peer_node:
            return
        if t == 'peer_sid':
            sid = m.get('sid')
            if isinstance(sid, str) and sid:
                for o in [o for o in self.conns if not o.is_peer and o.sid == sid]:
                    try:
                        o.w.close()
                    except Exception:
                        pass
            return
        if t == 'peer_bye':
            sh = c.shadows.pop(did, None)
            if sh is not None:
                old_room = sh.room
                if self.leave(sh):
                    await self.broadcast(old_room, json.dumps({'t': 'bye', 'id': sh.id}), critical=True)
            return
        if t == 'peer_x':
            b = m.get('b')
            crew_tag = clean(m.get('crew'), 40) if isinstance(m.get('crew'), str) else ''
            if crew_tag and not CREW_ROOM.match(crew_tag):
                crew_tag = ''
            raw_tag = clean(m.get('room'), 40) if isinstance(m.get('room'), str) else ''
            if not crew_tag and CREW_ROOM.match(raw_tag):
                crew_tag = raw_tag
            if not (isinstance(b, str) and 0 < len(b) <= MAX_CREW_B and (crew_tag or raw_tag.startswith('cp:'))):
                return
            targets = []
            seen = set()
            for o in list(self.crews.get(crew_tag, ()) if crew_tag else ()):
                if not getattr(o, 'is_shadow', False) and o not in seen:
                    seen.add(o)
                    targets.append(o)
            if raw_tag.startswith('cp:') and m.get('track'):
                sh = c.shadows.get(did)
                if sh is None and len(c.shadows) < MAX_SHADOWS:
                    sh = c.shadows[did] = ShadowDriver(did)
                if sh is not None:
                    sh.seen = time.monotonic()
                    room = self.room_for(sh, m.get('track'), m.get('at'), raw_tag)
                    if room:
                        if room != sh.room:
                            old = sh.room
                            if self.leave(sh):
                                await self.broadcast(old, json.dumps({'t': 'bye', 'id': sh.id}), critical=True)
                            sh.room = room
                            self.rooms.setdefault(room, set()).add(sh)
                            self._near_at.pop(room, None)
                        for o in list(self.rooms.get(room, ())):
                            if not getattr(o, 'is_shadow', False) and o not in seen:
                                seen.add(o)
                                targets.append(o)
            if not targets:
                return
            out = json.dumps({'t': 'x', 'id': did, 'sid': clean(m.get('sid'), 32), 'b': b}, separators=(',', ':'))
            frame = None
            for o in targets:
                out_q = getattr(o, 'out_q', None)
                if out_q is not None and 'send_text' not in o.__dict__:
                    if frame is None:
                        frame = encode_text_frame(out)
                    o.enqueue_frame(frame, critical=False)
                else:
                    try:
                        await asyncio.wait_for(o.send_text(out), 2.0)
                    except Exception:
                        pass
            return
        if t in ('peer_track', 'peer_s'):
            sh = c.shadows.get(did)
            if sh is None:
                if len(c.shadows) >= MAX_SHADOWS:
                    return
                sh = c.shadows[did] = ShadowDriver(did)
            sh.seen = time.monotonic()
            room = self.room_for(sh, m.get('track'), m.get('at'), m.get('room'))
            if not room:
                return
            if room != sh.room:
                old = sh.room
                if self.leave(sh):
                    await self.broadcast(old, json.dumps({'t': 'bye', 'id': sh.id}), critical=True)
                sh.room = room
                self.rooms.setdefault(room, set()).add(sh)
                self._near_at.pop(room, None)
            pos = m.get('pos')
            if good_at(pos):
                sh.pos = pos
            if t == 'peer_s':
                payload = m.get('payload')
                sent = m.get('sent')
                if isinstance(payload, str) and len(payload) <= MAX_MSG:
                    try:
                        p_obj = json.loads(payload)
                    except ValueError:
                        return
                    if not isinstance(p_obj, dict) or p_obj.get('t') != 's' or p_obj.get('id') != did:
                        return
                    sh.sent = int(sent) if isinstance(sent, int) and sent >= 0 else sh.sent
                    self.nearest(room)
                    await self.broadcast(room, payload, but=sh, near=sh)
                    sh.sent += 1

    async def message(self, c, m, peer_listener=False):
        if not isinstance(m, dict):
            return
        t = m.get('t')
        if t == 'peer_hello' and not getattr(c, 'hello', False) and not getattr(c, 'is_peer', False):
            if self.separate_peer_port and not peer_listener:
                await c.send_text(json.dumps({'t': 'error', 'e': 'peer_port_only'}))
                raise ConnectionError('peer_hello not allowed on public port')
            node = self._verify_peer_hello(m)
            if node is None or len(self.peer_conns) >= MAX_PEERS:
                await c.send_text(json.dumps({'t': 'error', 'e': 'peer_auth'}))
                raise ConnectionError('bad peer_hello')
            # Detach shadows cleanly from any superseded inbound connection for the same peer node before closing it
            transferred = {}
            for old in [p for p in list(self.peer_conns) if p.peer_node == node]:
                transferred.update(old.shadows)
                old.shadows.clear()
                self.peer_conns.discard(old)
                try:
                    old.w.close()
                except Exception:
                    pass
            self.conns.discard(c)
            c.is_peer = True
            c.duplex = bool(m.get('duplex'))
            c.watch = False
            c.peer_node = node
            c.shadows = transferred
            now_mono = time.monotonic()
            for sh in c.shadows.values():
                sh.seen = now_mono
            self.peer_conns.add(c)
            await c.send_text(json.dumps({'t': 'peer_welcome', 'node': self.node_id}))
            if c.duplex and c.out_q is not None:
                for snap in self.snapshot_local_drivers():
                    c.enqueue_frame(encode_text_frame(json.dumps(snap, separators=(',', ':'))), critical=True)
            return
        if getattr(c, 'is_peer', False):
            await self._peer_message(c, m)
            return
        if t == 'hello':
            if self.key is not None:
                tk = read_ticket(self.key, m.get('ticket'))
                if tk is None:
                    await c.send_text(json.dumps({'t': 'error', 'e': 'ticket'}))
                    raise ConnectionError('no good ticket')
                if c.sid != tk['s']:
                    for o in [o for o in self.conns if o is not c and o.sid == tk['s']]:
                        try:                     # the same driver again (a restart, another PC): the old one goes
                            o.w.close()
                        except Exception:
                            pass
                c.sid, c.name = tk['s'], clean(tk['n'], 32).strip() or 'Driver'
                self._push_peers({'t': 'peer_sid', 'id': c.id, 'sid': c.sid}, critical=True)
            else:
                c.name = clean(m.get('name'), 24).strip() or 'Driver'
            c.car = clean(m.get('car'), 48)
            # (their car's livery: those watching them see it; its catalogue id, to fetch one they don't have)
            c.livery = clean(m.get('livery'), 80) if isinstance(m.get('livery'), str) else ''
            lid = m.get('liveryId')
            c.livery_id = lid if isinstance(lid, int) and not isinstance(lid, bool) and 0 < lid < 10 ** 9 else None
            c.watch = m.get('watch') is not False
            c.hello = True
        elif t in ('s', 'track') and c.hello:
            raw_track = clean(m.get('track'), 80)
            raw_at = m.get('at') if good_at(m.get('at')) else None
            raw_tag = clean(m.get('room'), 40) if isinstance(m.get('room'), str) else ''
            room = self.room_for(c, raw_track, raw_at, raw_tag)
            if not room:
                return
            c.raw_track = raw_track
            c.raw_at = raw_at if raw_at is not None else c.raw_at
            c.raw_room_tag = raw_tag
            if room != c.room:
                old = c.room
                if self.leave(c):
                    await self.broadcast(old, json.dumps({'t': 'bye', 'id': c.id}), critical=True)
                c.room = room
                self.rooms.setdefault(room, set()).add(c)
                self._near_at.pop(room, None)
            if t == 'track':                     # on this stage (not driving yet): hears the others
                c.pos = raw_at if raw_at is not None else c.pos
                self._push_peers({
                    't': 'peer_track',
                    'id': c.id,
                    'track': c.raw_track,
                    'at': c.raw_at,
                    'room': c.raw_room_tag,
                    'pos': c.pos,
                }, critical=True)
                return
            samples = [x for x in (m.get('s') or [])[:MAX_SAMPLES] if good_sample(x)]
            run = m.get('run') if isinstance(m.get('run'), int) else 0
            root = m.get('root')                 # (their car's root from its car point: where its model goes)
            root = root if good_at(root) and all(abs(v) < 3 for v in root) else None
            if samples:
                c.pos = [samples[-1][1], samples[-1][3]]
                self.nearest(room)
                out = {'t': 's', 'id': c.id, 'sid': c.sid, 'name': c.name, 'car': c.car, 'run': run, 's': samples}
                if root:
                    out['root'] = root
                if good_dash(m.get('d')):            # (their dash: speed, gear, revs, pedals, for WATCH's broadcast)
                    out['d'] = m['d']
                if getattr(c, 'livery', ''):
                    out['livery'] = c.livery
                    if getattr(c, 'livery_id', None):
                        out['liveryId'] = c.livery_id
                text = json.dumps(out, separators=(',', ':'))
                await self.broadcast(room, text, but=c, near=c)
                self._push_peers({
                    't': 'peer_s',
                    'id': c.id,
                    'track': c.raw_track,
                    'at': c.raw_at,
                    'room': c.raw_room_tag,
                    'pos': c.pos,
                    'sent': c.sent,
                    'payload': text,
                })
                c.sent += 1
        elif t == 'follow':
            fid = m.get('id')
            c.follow = fid if isinstance(fid, int) and not isinstance(fid, bool) and fid > 0 else None
            if c.follow is not None and c.near is not None:
                c.near.add(c.follow)
        elif t == 'leave':
            room = c.room
            if self.leave(c):
                c.room = None
                c.raw_track, c.raw_at, c.raw_room_tag = '', None, ''
                await self.broadcast(room, json.dumps({'t': 'bye', 'id': c.id}), critical=True)
                self._push_peers({'t': 'peer_bye', 'id': c.id}, critical=True)
            if self._drain_settled and not getattr(c, 'crew', None):
                await self._close_player_conn(c)
                raise ConnectionError('drained cleanly after stage finish')
        elif t == 'crew' and getattr(c, 'hello', False):
            # a crew's own room, joined from the lobby (the app's copilot.py: in the game's menus too, before any
            # stage; 26 Nov 2026): its 'x' messages go to the others in it. None / '': out of it.
            room = m.get('room')
            self.crew_leave(c)
            if isinstance(room, str) and CREW_ROOM.match(room):
                c.crew = room
                self.crews.setdefault(room, set()).add(c)
            elif self._drain_settled and getattr(c, 'room', None) is None:
                await self._close_player_conn(c)
                raise ConnectionError('drained cleanly after crew leave')
        elif t == 'x' and getattr(c, 'hello', False) and (
                getattr(c, 'crew', None) or (getattr(c, 'room', None) and str(c.room[0]).startswith('cp:'))):
            # a COPILOT / CASUAL crew's own message (its voice, when the apps can't reach each other directly:
            # copilotlink.py): passed on in the crew's room locally AND across peer relays when split across regions!
            b = m.get('b')
            if isinstance(b, str) and 0 < len(b) <= MAX_CREW_B:
                crew_tag = getattr(c, 'crew', None)
                out = json.dumps({'t': 'x', 'id': c.id, 'sid': getattr(c, 'sid', ''), 'b': b}, separators=(',', ':'))
                to = self.crews.get(crew_tag, ()) if crew_tag else self.rooms.get(c.room, ())
                frame = None
                for o in list(to):
                    if o is c or getattr(o, 'is_shadow', False):
                        continue
                    out_q = getattr(o, 'out_q', None)
                    if out_q is not None and 'send_text' not in o.__dict__:
                        if frame is None:
                            frame = encode_text_frame(out)
                        o.enqueue_frame(frame, critical=False)
                    else:
                        try:
                            await asyncio.wait_for(o.send_text(out), 2.0)
                        except Exception:
                            pass
                self._push_peers({
                    't': 'peer_x',
                    'id': c.id,
                    'sid': getattr(c, 'sid', ''),
                    'crew': crew_tag or '',
                    'track': getattr(c, 'raw_track', ''),
                    'at': getattr(c, 'raw_at', None),
                    'room': getattr(c, 'raw_room_tag', ''),
                    'b': b,
                })

    async def ping(self, c):
        try:
            while True:
                await asyncio.sleep(PING_S)
                await c.send_ctl(9, b'p')
        except Exception:
            pass


def compute_node_id(node_id=1, region_slot=None):
    if region_slot is None:
        return max(1, int(node_id or 1))
    slot = max(1, min(9, int(region_slot)))
    # Deterministic 2-second epoch bucket modulo 80 -> unique across rolling pods, <= 799 (< 2^31 when * 10_000_000)
    return slot + ((int(time.time()) // 2) % 80) * 10


async def main(host, port, key, node_id=1, peers=(), peer_host='0.0.0.0', peer_port=None,
               drain_peer='', drain_settle=10.0, drain_timeout=1740.0):
    separate = bool(peer_port and int(peer_port) != int(port))
    relay = Relay(key, node_id=node_id, peers=peers, separate_peer_port=separate, drain_peer=drain_peer)
    server = await asyncio.start_server(relay.handle, host, port)
    peer_server = await asyncio.start_server(relay.handle_peer, peer_host, int(peer_port)) if separate else None
    relay.start_peers()

    loop = asyncio.get_running_loop()
    for sig_name in ('SIGTERM', 'SIGINT'):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, lambda: relay.begin_drain(settle_s=drain_settle, timeout_s=drain_timeout))
            except (NotImplementedError, RuntimeError):
                pass

    print('ACR Daily live relay node=%d on %s:%d%s (%s, %d peers)' % (
        relay.node_id, host, port,
        (' peer=%s:%d' % (peer_host, int(peer_port))) if separate else '',
        'names checked' if key else 'NAMES NOT CHECKED', len(relay.peer_outs)), flush=True)
    try:
        serve_tasks = [asyncio.ensure_future(server.serve_forever())]
        if peer_server is not None:
            serve_tasks.append(asyncio.ensure_future(peer_server.serve_forever()))
        drain_wait = asyncio.ensure_future(relay.drain_done.wait())
        done, pending = await asyncio.wait(serve_tasks + [drain_wait], return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
    finally:
        relay.stop_peers()
        server.close()
        if peer_server is not None:
            peer_server.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default=os.environ.get('RELAY_BIND_HOST', '0.0.0.0'))
    ap.add_argument('--port', type=int, default=int(os.environ.get('RELAY_PORT', '8765')))
    ap.add_argument('--peer-host', default=os.environ.get('RELAY_PEER_BIND_HOST', '0.0.0.0'))
    ap.add_argument('--peer-port', type=int,
                    default=int(os.environ['RELAY_PEER_PORT']) if os.environ.get('RELAY_PEER_PORT') else None,
                    help='dedicated VPC-only port for peer mesh links')
    ap.add_argument('--node-id', type=int, default=int(os.environ.get('RELAY_NODE_ID', '1')),
                    help='unique regional node id (1..999)')
    ap.add_argument('--region-slot', type=int,
                    default=int(os.environ['RELAY_REGION_SLOT']) if os.environ.get('RELAY_REGION_SLOT') else None,
                    help='regional slot 1..9 to auto-assign non-colliding node-ids across rolling pods')
    ap.add_argument('--peer', action='append', default=[], help='peer relay WebSocket URL (repeatable)')
    ap.add_argument('--drain-peer', default=os.environ.get('RELAY_DRAIN_PEER', ''),
                    help='local cluster relay peer URL bridged bidirectionally while draining on SIGTERM')
    ap.add_argument('--drain-settle', type=float, default=float(os.environ.get('RELAY_DRAIN_SETTLE_S', '10.0')))
    ap.add_argument('--drain-timeout', type=float, default=float(os.environ.get('RELAY_DRAIN_TIMEOUT_S', '1740.0')))
    ap.add_argument('--key-file', help='the live key (hex): without it, checks LIVE_RELAY_KEY or ADMIN_KEY env')
    a = ap.parse_args()
    env_peers = [p.strip() for p in re.split(r'[\s,]+', os.environ.get('RELAY_PEERS', '')) if p.strip()]
    all_peers = list(dict.fromkeys(list(a.peer) + env_peers))
    key = None
    if a.key_file:
        with open(a.key_file) as f:
            key = bytes.fromhex(f.read().strip())
        if len(key) != 32:
            raise SystemExit('the key file should hold 64 hex digits')
    elif os.environ.get('LIVE_RELAY_KEY', '').strip():
        key = bytes.fromhex(os.environ['LIVE_RELAY_KEY'].strip())
        if len(key) != 32:
            raise SystemExit('LIVE_RELAY_KEY should hold 64 hex digits')
    elif os.environ.get('ADMIN_KEY', '').strip():
        key = hashlib.sha256(('live-relay|' + os.environ['ADMIN_KEY'].strip()).encode('utf-8')).digest()
    eff_node = compute_node_id(node_id=a.node_id, region_slot=a.region_slot)
    asyncio.run(main(a.host, a.port, key, node_id=eff_node, peers=all_peers,
                     peer_host=a.peer_host, peer_port=a.peer_port,
                     drain_peer=a.drain_peer, drain_settle=a.drain_settle, drain_timeout=a.drain_timeout))
