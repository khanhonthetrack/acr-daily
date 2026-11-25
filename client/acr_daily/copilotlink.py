"""COPILOT's link between a crew's two apps (copilot.py): the driver's car (its samples, as the live relay has them)
and both voices (voice.py), the shortest way there is.

Straight between the two PCs when their routers let it through (UDP "hole punching", as games and calls do): each app
asks a STUN server how the internet sees its socket (its public address and port), and puts that and its addresses on
its own network on the lobby (the server's /api/copilot/lobbies/:id/signal: the only thing the server carries). Each
then sends to every address of the other's until one answers: from then on the packets go straight, the ping the
distance between the two PCs (two drivers in Japan: a few ms, never through Europe). The lobby's server only
introduced them.

When no address answers within DIRECT_WAIT_S (a router that doesn't allow it), the voice goes through the live relay
instead (its crew messages, livelink.send_crew: live/relay.py passes them on in the crew's room), and the car as it
always does there.

A packet: MAGIC, its kind (H hello / P its answer, S samples, V voice, C a status), the sender's key (8 bytes, made for this
link, given only to the other through the lobby: packets with another key are not theirs), then its payload.
"""
import base64
import json
import os
import secrets
import socket
import struct
import threading
import time

MAGIC = b'ACP1'
STUN = (('stun.cloudflare.com', 3478), ('stun.l.google.com', 19302))
PUNCH_S = 0.2                    # hello to every address of the other's this often until one answers
PING_S = 1.0                     # then a hello a second: the ping, and the way kept open in the routers
DEAD_S = 6.0                     # nothing from the other this long: the direct way is gone (punching again)
DIRECT_WAIT_S = 8.0              # no answer this long after the other's details came: the relay for the voice
STUN_COOKIE = 0x2112A442


def stun_request(tid):
    return struct.pack('>HHI', 0x0001, 0, STUN_COOKIE) + tid


def stun_address(data, tid):
    """A STUN Binding answer -> 'ip:port' (its XOR-MAPPED-ADDRESS, else MAPPED-ADDRESS), or None."""
    if len(data) < 20 or struct.unpack_from('>H', data, 0)[0] != 0x0101 or data[8:20] != tid:
        return None
    n = struct.unpack_from('>H', data, 2)[0]
    o, end, plain = 20, min(len(data), 20 + n), None
    while o + 4 <= end:
        t, ln = struct.unpack_from('>HH', data, o)
        v = data[o + 4:o + 4 + ln]
        if t in (0x0020, 0x8020) and len(v) >= 8 and v[1] == 1:
            port = struct.unpack_from('>H', v, 2)[0] ^ (STUN_COOKIE >> 16)
            ip = struct.unpack_from('>I', v, 4)[0] ^ STUN_COOKIE
            return '%s:%d' % (socket.inet_ntoa(struct.pack('>I', ip)), port)
        if t == 0x0001 and len(v) >= 8 and v[1] == 1:
            plain = '%s:%d' % (socket.inet_ntoa(v[4:8]), struct.unpack_from('>H', v, 2)[0])
        o += 4 + ln + (-ln % 4)
    return plain


def _addr(s):
    try:
        host, port = str(s).rsplit(':', 1)
        socket.inet_aton(host)
        port = int(port)
        return (host, port) if 0 < port < 65536 else None
    except (ValueError, OSError):
        return None


def local_addresses(port):
    """This PC's own addresses (IPv4, not loopback) with the link's port: for a crew on the same network."""
    out = []
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith('127.') and ip not in out:
                out.append(ip)
    except OSError:
        pass
    return ['%s:%d' % (ip, port) for ip in out[:4]]


class Link:
    """publish(details): this side's details to the lobby (a dict); on_samples(message dict), on_voice(packet, seat): what
    came from the other; relay(): the live relay's link (livelink.LiveLink) or None, for the voice when there is no
    direct way. stun: (host, port) servers (tests: none)."""

    def __init__(self, publish, on_samples, on_voice, relay=lambda: None, stun=STUN, bind=('0.0.0.0', 0), on_status=None):
        self.publish, self.on_samples, self.on_voice, self.relay = publish, on_samples, on_voice, relay
        self.on_status = on_status        # the other's status line (copilot.py: their game's own co-driver), or None
        self.key = secrets.token_bytes(8)
        self.peer_key, self.cands, self.peer_sid = None, [], None
        self.addr = None                  # the other's address that answered (the direct way), or None
        self.state = 'starting'           # starting | waiting (for the other's details) | punching | direct | relay
        self.rtt_ms = None
        self.public = None                # how the internet sees this socket ('ip:port'), as STUN said
        self.on = True
        self.sent = self.got = 0
        self._heard_at = -1e9
        self._peer_at = None              # when the other's details came
        self._stun = list(stun)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(bind)
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._run, daemon=True).start()

    # ---- the other's details (from the lobby)
    def details(self):
        return {'v': 1, 'key': self.key.hex(), 'pub': self.public, 'loc': local_addresses(self.port)}

    def peer(self, data, sid=None):
        """The other's details as the lobby has them (their publish()): a JSON string or a dict."""
        try:
            d = json.loads(data) if isinstance(data, str) else dict(data or {})
            key = bytes.fromhex(str(d.get('key') or ''))
        except (ValueError, TypeError):
            return
        if len(key) != 8:
            return
        cands = [a for a in [_addr(d.get('pub'))] + [_addr(x) for x in (d.get('loc') or [])[:4]] if a]
        if key != self.peer_key or set(cands) != set(self.cands):
            self.peer_key, self.cands = key, cands
            if self._peer_at is None:
                self._peer_at = time.monotonic()
        if sid:
            self.peer_sid = str(sid)

    @property
    def direct(self):
        return self.addr is not None and time.monotonic() - self._heard_at < DEAD_S

    def mode(self):
        """'direct', 'relay', 'connecting' or 'none' (nothing either way yet): as the page says it."""
        if self.direct:
            return 'direct'
        if self.state == 'relay' and self.relay() is not None and getattr(self.relay(), 'state', None) == 'live':
            return 'relay'
        return 'connecting' if self.on else 'none'

    # ---- sending
    def _packet(self, kind, payload=b''):
        return MAGIC + kind + self.key + payload

    def send_samples(self, m):
        """The driver's samples (a relay 's' message, with its sid / name / car): straight when there is a way."""
        if self.direct:
            data = json.dumps(m, separators=(',', ':')).encode()
            if len(data) < 1200:
                self._send(self._packet(b'S', data), self.addr)

    def send_voice(self, packet, who=0, relay=True):
        """A voice packet to the other, tagged with the seat of whoever spoke (0 the driver, 1..3 the co-drivers): straight
        when there is a way, else through the relay (relay False: only straight; copilot.py sends a relay one once)."""
        tagged = bytes([who & 3]) + packet
        if self.direct:
            self._send(self._packet(b'V', tagged), self.addr)
        elif relay:
            r = self.relay()
            if r is not None:
                r.send_crew('v' + base64.b64encode(tagged).decode())

    def send_status(self, s):
        """A short status for the other (copilot.py: '1' / '0' / '-', my game's own co-driver off / on / not known)."""
        s = str(s)[:48]
        if self.direct:
            self._send(self._packet(b'C', s.encode('ascii', 'replace')), self.addr)
        else:
            r = self.relay()
            if r is not None:
                r.send_crew('c' + s)

    def _status(self, s):
        fn = self.on_status
        if fn is not None:
            try:
                fn(s)
            except Exception:
                pass

    def crew(self, sid, b):
        """A crew message the relay passed on (livelink.on_crew): the other's voice (and status) when there is no
        direct way."""
        if self.peer_sid and sid and sid != self.peer_sid:
            return
        if isinstance(b, str) and b.startswith('v'):
            try:
                raw = base64.b64decode(b[1:])
                self.on_voice(raw[1:], raw[0] & 3)
            except (ValueError, TypeError, IndexError):
                pass
        elif isinstance(b, str) and b.startswith('c'):
            self._status(b[1:])

    def _send(self, data, addr):
        try:
            self.sock.sendto(data, addr)
            self.sent += 1
        except OSError:
            pass

    # ---- the loop
    def _run(self):
        tid = os.urandom(12)
        published, stun_at, stun_tries = False, -1e9, 0
        punch_at = ping_at = -1e9
        try:
            while self.on:
                now = time.monotonic()
                if self.public is None and self._stun and stun_tries < 6 and now - stun_at > 0.7:
                    stun_at, stun_tries = now, stun_tries + 1
                    for host, port in self._stun:
                        try:
                            self.sock.sendto(stun_request(tid), (socket.gethostbyname(host), port))
                        except OSError:
                            pass
                if not published and (self.public is not None or stun_tries >= 6 or not self._stun):
                    published = self._publish()
                if self.peer_key and not self.direct:
                    self.state = 'punching' if now - (self._peer_at or now) < DIRECT_WAIT_S else 'relay'
                    if now - punch_at >= PUNCH_S:
                        punch_at = now
                        for a in self.cands:
                            self._send(self._packet(b'H', struct.pack('<d', now)), a)
                elif self.direct:
                    self.state = 'direct'
                    if now - ping_at >= PING_S:
                        ping_at = now
                        self._send(self._packet(b'H', struct.pack('<d', now)), self.addr)
                elif published:
                    self.state = 'waiting'
                try:
                    data, addr = self.sock.recvfrom(2048)
                except (socket.timeout, BlockingIOError):
                    continue
                except OSError:
                    time.sleep(0.05)
                    continue
                if data[:2] == b'\x01\x01':            # (a STUN answer)
                    got = stun_address(data, tid)
                    if got and self.public is None:
                        self.public = got
                        if published:
                            self._publish()
                    continue
                self._take(data, addr, time.monotonic())
        finally:
            try:
                self.sock.close()
            except OSError:
                pass

    def _publish(self):
        try:
            self.publish(self.details())
            return True
        except Exception:
            return False

    def _take(self, data, addr, now):
        if len(data) < 13 or data[:4] != MAGIC or self.peer_key is None or data[5:13] != self.peer_key:
            return
        kind, body = data[4:5], data[13:]
        self.got += 1
        self._heard_at = now
        if self.addr != addr:
            self.addr = addr                       # (the way that works: their answer's own address)
        if kind == b'H':
            self._send(self._packet(b'P', body[:8]), addr)
        elif kind == b'P' and len(body) >= 8:
            sent = struct.unpack('<d', body[:8])[0]
            if 0 <= now - sent < 10:
                ms = (now - sent) * 1000.0
                self.rtt_ms = ms if self.rtt_ms is None else self.rtt_ms * 0.8 + ms * 0.2
        elif kind == b'S':
            try:
                m = json.loads(body.decode('utf-8'))
            except ValueError:
                return
            if isinstance(m, dict):
                try:
                    self.on_samples(m)
                except Exception:
                    pass
        elif kind == b'V' and body:
            try:
                self.on_voice(body[1:], body[0] & 3)
            except Exception:
                pass
        elif kind == b'C':
            self._status(body.decode('ascii', 'replace'))

    def close(self):
        self.on = False
