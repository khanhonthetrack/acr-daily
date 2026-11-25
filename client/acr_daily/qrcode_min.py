"""A small QR code maker (no packages): byte mode, error correction M, versions 1 to 6 (up to 106 bytes: a web address).

matrix(text) -> a list of rows of 0 / 1 (1 dark) with no quiet zone; png(text, scale, border) -> a PNG's bytes (black
on white, RGB: the game draws a grey-only PNG in red; with the quiet zone the scanners need); write_png(path, text, ...).
"""
import struct
import zlib

# version -> (error correction codewords per block, [(blocks, data codewords per block), ...]) for level M
_M = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
      6: (16, [(4, 27)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}

_EXP, _LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if not a or not b else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n):
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _mul(c, _EXP[i])
        g = nxt
    return g


def _rs(data, n):
    """The n error correction codewords of data."""
    g = _rs_generator(n)
    rem = [0] * n
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        if f:
            for i in range(n):
                rem[i] ^= _mul(g[i + 1], f)
    return rem


def _version_for(n):
    for v in sorted(_M):
        ec, blocks = _M[v]
        cap = sum(b * d for b, d in blocks)
        if n + 2 <= cap:                         # (4 bits mode + 8 bits length + the bytes: n + 2 codewords at most)
            return v
    raise ValueError('too long for a QR code of version 6 (%d bytes)' % n)


def _codewords(data, v):
    ec, blocks = _M[v]
    cap = sum(b * d for b, d in blocks)
    bits = '0100' + format(len(data), '08b') + ''.join(format(b, '08b') for b in data)
    bits += '0' * min(4, cap * 8 - len(bits))
    bits += '0' * (-len(bits) % 8)
    words = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    while len(words) < cap:
        words.append(pad[(len(words) - len(bits) // 8) % 2])
    out, o = [], 0
    for b, d in blocks:
        for _ in range(b):
            out.append(words[o:o + d])
            o += d
    ecs = [_rs(blk, ec) for blk in out]
    res = []
    for i in range(max(len(b) for b in out)):
        for blk in out:
            if i < len(blk):
                res.append(blk[i])
    for i in range(ec):
        for e in ecs:
            res.append(e[i])
    return res


def _bch_format(bits5):
    d = bits5 << 10
    for i in range(14, 9, -1):
        if d >> i & 1:
            d ^= 0x537 << (i - 10)
    return ((bits5 << 10) | d) ^ 0x5412


def _function_cells(v, n):
    """(the cells that are function patterns, the dark ones among them)."""
    fn = [[False] * n for _ in range(n)]
    dark = [[False] * n for _ in range(n)]

    def put(r, c, d):
        if 0 <= r < n and 0 <= c < n:
            fn[r][c] = True
            dark[r][c] = d
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):          # finders with their separators
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                inside = 0 <= dr <= 6 and 0 <= dc <= 6
                d = inside and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4))
                put(r0 + dr, c0 + dc, d)
    pos = _ALIGN[v]
    for r in pos:
        for c in pos:
            if (r, c) in ((6, 6), (6, pos[-1]), (pos[-1], 6)) and (r, c) != (pos[-1], pos[-1]):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    put(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    for i in range(n):                                        # timing
        if not fn[6][i]:
            put(6, i, i % 2 == 0)
        if not fn[i][6]:
            put(i, 6, i % 2 == 0)
    put(n - 8, 8, True)                                       # the dark module
    for i in range(9):                                        # format areas (filled later)
        put(8, i, False)
        put(i, 8, False)
    for i in range(8):
        put(8, n - 1 - i, False)
        put(n - 1 - i, 8, False)
    return fn, dark


def _place(v, words):
    n = 17 + 4 * v
    fn, dark = _function_cells(v, n)
    cells = [row[:] for row in dark]
    bits = [(w >> (7 - i)) & 1 for w in words for i in range(8)]
    k, up = 0, True
    c = n - 1
    while c > 0:
        if c == 6:
            c -= 1
        rows = range(n - 1, -1, -1) if up else range(n)
        for r in rows:
            for cc in (c, c - 1):
                if not fn[r][cc]:
                    cells[r][cc] = bool(bits[k]) if k < len(bits) else False
                    k += 1
        up = not up
        c -= 2
    return n, fn, cells


_MASKS = (lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0, lambda r, c: (r + c) % 3 == 0,
          lambda r, c: (r // 2 + c // 3) % 2 == 0, lambda r, c: r * c % 2 + r * c % 3 == 0,
          lambda r, c: (r * c % 2 + r * c % 3) % 2 == 0, lambda r, c: ((r + c) % 2 + r * c % 3) % 2 == 0)


def _penalty(m):
    n = len(m)
    p = 0
    for g in (m, [list(col) for col in zip(*m)]):
        for row in g:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]:
                    run += 1
                    if run == 5:
                        p += 3
                    elif run > 5:
                        p += 1
                else:
                    run = 1
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                p += 3
    pat = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    for g in (m, [list(col) for col in zip(*m)]):
        for row in g:
            for i in range(n - 10):
                seg = [int(x) for x in row[i:i + 11]]
                if seg == pat or seg == pat[::-1]:
                    p += 40
    dark = sum(sum(1 for x in row if x) for row in m)
    p += (abs(dark * 20 - n * n * 10) // (n * n)) * 10
    return p


def matrix(text):
    data = text.encode('utf-8')
    v = _version_for(len(data))
    n, fn, cells = _place(v, _codewords(data, v))
    best = None
    for mask in range(8):
        m = [[cells[r][c] ^ (not fn[r][c] and _MASKS[mask](r, c)) for c in range(n)] for r in range(n)]
        f = _bch_format(0b00000 | mask)             # (level M = 00, then the mask)
        for i in range(15):
            bit = bool(f >> i & 1)
            if i < 6:
                m[i][8] = bit
            elif i < 8:
                m[i + 1][8] = bit
            else:
                m[n - 15 + i][8] = bit
            if i < 8:
                m[8][n - 1 - i] = bit
            elif i < 9:
                m[8][15 - i] = bit
            else:
                m[8][14 - i] = bit
        m[n - 8][8] = True
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return [[1 if x else 0 for x in row] for row in best[1]]


def png(text, scale=8, border=4):
    m = matrix(text)
    n = len(m)
    size = (n + 2 * border) * scale
    rows = []
    for r in range(-border, n + border):
        line = bytearray()
        for c in range(-border, n + border):
            dark = 0 <= r < n and 0 <= c < n and m[r][c]
            line += (b'\x00\x00\x00' if dark else b'\xff\xff\xff') * scale
        rows += [b'\x00' + bytes(line)] * scale

    def chunk(kind, body):
        c = struct.pack('>I', len(body)) + kind + body
        return c + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))


def write_png(path, text, scale=8, border=4):
    with open(path, 'wb') as f:
        f.write(png(text, scale, border))
    return path
