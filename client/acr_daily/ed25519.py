"""Ed25519 signatures (RFC 8032) in plain Python: the replays' device key (replays.py). No package needed (the app is
built with PyInstaller and carries no crypto library); one signature takes a few milliseconds, one is made per replay.

keypair(seed32) -> (seed, public32); sign(seed, message) -> 64 bytes; verify(public, message, signature) -> bool.
Checked against RFC 8032's test vectors (tests/test_replays.py)."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
I = pow(2, (P - 1) // 4, P)


def _h(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, P - 2, P)


def _xrecover(y):
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * I) % P
    if (x * x - xx) % P != 0:
        return None
    if x % 2 != 0:
        x = P - x
    return x


_BY = (4 * _inv(5)) % P
_BX = _xrecover(_BY)
B = (_BX, _BY, 1, (_BX * _BY) % P)       # extended coordinates (X, Y, Z, T)
ZERO = (0, 1, 1, 0)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = 2 * t1 * t2 * D % P
    d = 2 * z1 * z2 % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mul(s, p):
    q = ZERO
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _encode(p):
    x, y, z, _t = p
    zi = _inv(z)
    x, y = x * zi % P, y * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, 'little')


def _decode(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= P:
        return None
    x = _xrecover(y)
    if x is None:
        return None
    if (x & 1) != sign:
        x = P - x
    if x == 0 and sign:
        return None
    return (x, y, 1, x * y % P)


def _equal(p, q):
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0


def _secret(seed):
    h = _h(seed)
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    a, _prefix = _secret(bytes(seed))
    return _encode(_mul(a, B))


def keypair(seed):
    seed = bytes(seed)
    if len(seed) != 32:
        raise ValueError('an Ed25519 seed is 32 bytes')
    return seed, public_key(seed)


def sign(seed, msg):
    a, prefix = _secret(bytes(seed))
    pub = _encode(_mul(a, B))
    r = int.from_bytes(_h(prefix + msg), 'little') % L
    big_r = _encode(_mul(r, B))
    k = int.from_bytes(_h(big_r + pub + msg), 'little') % L
    s = (r + k * a) % L
    return big_r + s.to_bytes(32, 'little')


def verify(pub, msg, sig):
    try:
        pub, sig = bytes(pub), bytes(sig)
    except (TypeError, ValueError):
        return False
    if len(pub) != 32 or len(sig) != 64:
        return False
    a = _decode(pub)
    r = _decode(sig[:32])
    s = int.from_bytes(sig[32:], 'little')
    if a is None or r is None or s >= L:
        return False
    k = int.from_bytes(_h(sig[:32] + pub + msg), 'little') % L
    return _equal(_mul(s, B), _add(r, _mul(k, a)))
