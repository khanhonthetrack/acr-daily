"""Writes acr_daily/icon.ico (chequered flag on the ACR Daily green) without any image library."""
import os
import struct
import zlib

BG, CHK_W, CHK_B, ACC = (11, 26, 19), (241, 246, 242), (7, 18, 13), (30, 203, 110)


def pixel(x, y, n):
    u, v = x / n, y / n
    r = 0.16  # rounded corners
    if (u < r or u > 1 - r) and (v < r or v > 1 - r):
        cx, cy = (r if u < r else 1 - r), (r if v < r else 1 - r)
        if (u - cx) ** 2 + (v - cy) ** 2 > r * r:
            return None
    if 0.18 <= u < 0.82 and 0.16 <= v < 0.70:      # 4x4 chequered flag, slanted like the logo
        uu = u + (0.70 - v) * 0.18
        col = int((uu - 0.18) / 0.16) % 4 if uu < 0.82 else None
        row = int((v - 0.16) / 0.135)
        if col is not None:
            return CHK_W if (col + row) % 2 == 0 else CHK_B
    if 0.16 <= u < 0.84 and 0.76 <= v < 0.86:      # green bar
        return ACC
    return BG


def png(n):
    raw = b''
    for y in range(n):
        raw += b'\x00'
        for x in range(n):
            p = pixel(x + 0.5, y + 0.5, n)
            raw += bytes(p) + b'\xff' if p else b'\x00\x00\x00\x00'
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [png(n) for n in sizes]
    out = struct.pack('<HHH', 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    for n, d in zip(sizes, imgs):
        out += struct.pack('<BBBBHHII', n % 256, n % 256, 0, 0, 1, 32, len(d), off)
        off += len(d)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'acr_daily', 'icon.ico')
    with open(path, 'wb') as f:
        f.write(out + b''.join(imgs))
    with open(path.replace('.ico', '-256.png'), 'wb') as f:
        f.write(imgs[-1])
    print('wrote', path)


if __name__ == '__main__':
    main()
