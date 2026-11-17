"""A QR code for a link, drawn by the app itself (phoneui.py: a page of the website, scanned with a phone's camera).

QR Code Model 2 (ISO/IEC 18004), only what a link needs: byte mode, error correction level M (15 %), versions 1 to 10
(up to 213 bytes: acrdaily.com's addresses are under 60), the mask that scores best. After Project Nayuki's QR Code
generator (MIT), cut down to that. No package for it: the app ships with Pillow and truststore only.

    matrix('https://acrdaily.com/tt') -> rows of True (dark) / False (light), without the quiet zone (4 modules)
"""

# level M, versions 1..10 (index 0 unused): error correction codewords per block, and blocks
ECC_PER_BLOCK = (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
BLOCKS = (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
FORMAT_M = 0                     # (the format's two bits for level M: L 1, M 0, Q 3, H 2)
MAX_VERSION = 10


def raw_modules(ver):
    """The modules a version has for data and error correction (all but the function patterns)."""
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        n -= (25 * align - 10) * align - 55
        if ver >= 7:
            n -= 36
    return n


def data_codewords(ver):
    return raw_modules(ver) // 8 - ECC_PER_BLOCK[ver] * BLOCKS[ver]


def _gf_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _gf_mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _gf_mul(root, 0x02)
    return out


def _rs_remainder(data, divisor):
    out = [0] * len(divisor)
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, coef in enumerate(divisor):
            out[i] ^= _gf_mul(coef, factor)
    return out


def _codewords(data, ver):
    """The data in byte mode, padded, with its error correction, blocks interleaved."""
    bits = []

    def put(value, n):
        bits.extend((value >> i) & 1 for i in range(n - 1, -1, -1))
    put(0b0100, 4)                                  # byte mode
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    cap = data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))                 # terminator
    put(0, -len(bits) % 8)
    words = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < cap // 8:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    n_blocks, ecc_len = BLOCKS[ver], ECC_PER_BLOCK[ver]
    raw = raw_modules(ver) // 8
    short = n_blocks - raw % n_blocks
    short_len = raw // n_blocks
    div = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(n_blocks):
        dat = words[k:k + short_len - ecc_len + (0 if i < short else 1)]
        k += len(dat)
        ecc = _rs_remainder(dat, div)
        if i < short:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= short:
                out.append(blk[i])
    return out


def _align_positions(ver, size):
    if ver == 1:
        return []
    n = ver // 7 + 2
    step = (ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    out = [6]
    pos = size - 7
    while len(out) < n:
        out.insert(1, pos)
        pos -= step
    return out


class _Grid:
    def __init__(self, ver):
        self.ver = ver
        self.size = size = ver * 4 + 17
        self.dark = [[False] * size for _ in range(size)]
        self.fixed = [[False] * size for _ in range(size)]

    def set(self, x, y, dark):
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def functions(self):
        size = self.size
        for i in range(size):                       # timing
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):      # finders, with their separators
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _align_positions(self.ver, size)
        last = len(pos) - 1
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)                         # (reserved now, written again with the mask picked)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = size - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def format_bits(self, mask):
        data = FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1          # noqa: E731
        size = self.size
        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, size - 15 + i, bit(i))
        self.set(8, size - 8, True)                 # (the dark module)

    def place(self, words):
        size, i, total = self.size, 0, len(words) * 8
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vert in range(size):
                y = size - 1 - vert if upward else vert
                for j in range(2):
                    x = right - j
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def mask(self, m):
        for y in range(self.size):
            for x in range(self.size):
                if self.fixed[y][x]:
                    continue
                if ((x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0, (x // 3 + y // 2) % 2 == 0,
                        x * y % 2 + x * y % 3 == 0, (x * y % 2 + x * y % 3) % 2 == 0,
                        ((x + y) % 2 + x * y % 3) % 2 == 0)[m]:
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self):
        size, d, score = self.size, self.dark, 0
        lines = [row for row in d] + [[d[y][x] for y in range(size)] for x in range(size)]
        finder = ((True, False, True, True, True, False, True, False, False, False, False),
                  (False, False, False, False, True, False, True, True, True, False, True))
        for line in lines:
            run, prev = 0, None
            for v in line:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + run - 5
                    run, prev = 1, v
            if run >= 5:
                score += 3 + run - 5
            t = tuple(line)
            for i in range(size - 10):
                if t[i:i + 11] in finder:
                    score += 40
        for y in range(size - 1):
            for x in range(size - 1):
                if d[y][x] == d[y][x + 1] == d[y + 1][x] == d[y + 1][x + 1]:
                    score += 3
        dark = sum(v for row in d for v in row)
        total = size * size
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
        return score


def version_for(n_bytes):
    """The smallest version that holds n bytes, or None (longer than version 10 holds)."""
    for ver in range(1, MAX_VERSION + 1):
        if 4 + (8 if ver < 10 else 16) + 8 * n_bytes <= data_codewords(ver) * 8:
            return ver
    return None


def matrix(text):
    """The QR code of text (UTF-8) as rows of booleans (True: dark), the quiet zone not included."""
    data = text.encode('utf-8')
    ver = version_for(len(data))
    if ver is None:
        raise ValueError('too long for a QR code here: %d bytes' % len(data))
    words = _codewords(data, ver)
    best = None
    for m in range(8):
        g = _Grid(ver)
        g.functions()
        g.place(words)
        g.mask(m)
        g.format_bits(m)
        score = g.penalty()
        if best is None or score < best[0]:
            best = (score, g)
    return best[1].dark
