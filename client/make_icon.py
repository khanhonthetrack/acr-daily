"""Writes the ACR Daily logo for the app, without any image library:
  acr_daily/icon.ico        window, taskbar and exe icon: the D-car on a black tile (16-256 px)
  acr_daily/icon-256.png    the same at 256 px
  acr_daily/logo-<h>.png    the full logo (A, C, R and the D-car) for the app's header, h = 48/72/96 px
                            for 100/150/200 % display scaling

The drawing is the website's (server/src/logo.js): SVG paths of M/L/C/Z commands, flattened to polygons and
filled with the even-odd rule, 8 sub-scanlines per pixel and exact coverage along each one.
"""
import os
import struct
import zlib

YELLOW, WHITE, BLACK = (255, 209, 0), (244, 244, 245), (10, 10, 11)

# full logo, viewBox 0 0 163.6 200 (as in server/src/logo.js)
LOGO_W, LOGO_H = 163.6, 200
CAR = ('M110.5 2.6L121.4 29.5C122.1 31.3 121.3 33.3 119.5 34C117.7 34.7 115.7 33.9 115 32.1L104.1 5.2C103.4 3.4 '
       '104.3 1.4 106 0.7C107.8 0 109.8 0.9 110.5 2.6ZM101.9 18L108.6 34.7C109.3 36.4 108.5 38.4 106.7 39.2C104.'
       '9 39.9 102.9 39 102.2 37.3L95.5 20.6C94.8 18.9 95.6 16.8 97.4 16.1C99.1 15.4 101.2 16.3 101.9 18ZM92.7 3'
       '2.2L95.8 39.8C96.5 41.6 95.7 43.6 93.9 44.3C92.1 45 90.1 44.2 89.4 42.4L86.3 34.7C85.6 33 86.4 31 88.2 3'
       '0.3C90 29.5 92 30.4 92.7 32.2ZM74.2 65.7L78.3 75.9C86.7 74.8 94.7 79.6 97.9 87.4C101 95.2 98.6 104.2 91.'
       '8 109.2L108.3 150.1C116.7 149.1 124.7 153.8 127.9 161.6C131 169.4 128.6 178.4 121.8 183.5L125.9 193.7L13'
       '8.7 188.5C151 183.6 159.1 169.9 161.3 150.6C163.6 131.3 159.7 107.8 150.7 85.4L137.8 53.4C135.2 47.1 127'
       '.9 44 121.6 46.5L79.3 63.6C76.1 64.9 74.2 65.7 74.2 65.7ZM110.1 66.1L141.2 143.1C144.6 136.2 146.2 127.6'
       ' 145.9 118.3C145.7 109 143.6 99.1 139.8 89.8L130 65.5C128.6 62 124.5 60.3 121 61.7ZM86 107.8C78.6 110.8 '
       '70.2 107.2 67.2 99.8C64.2 92.4 67.8 83.9 75.2 80.9C82.6 77.9 91 81.5 94 88.9C97 96.4 93.5 104.8 86 107.8'
       'ZM116 182C108.6 185 100.2 181.5 97.2 174C94.2 166.6 97.7 158.2 105.2 155.2C112.6 152.2 121 155.8 124 163'
       '.2C127 170.6 123.5 179 116 182Z')
ACR = ('M21.5 86.4L21.3 81C21.4 80.9 21.4 80.8 21.3 80.7C21.2 80.7 21.1 80.6 21 80.6L14.8 80.6C14.6 80.6 14.4 80'
       '.7 14.3 81L13 86.4C12.8 87 12.4 87.4 11.8 87.4L1 87.4C0.3 87.4 0 87 0.2 86.2L15.8 38.6C16 38 16.4 37.7 1'
       '7.1 37.7L29.7 37.7C30.3 37.7 30.7 38 30.7 38.6L34.6 86.2L34.6 86.4C34.6 87 34.3 87.4 33.6 87.4L22.4 87.4'
       'C21.7 87.4 21.4 87 21.5 86.4ZM17.4 70.4L20.8 70.4C20.9 70.4 21 70.3 21.1 70L20.8 56.9C20.8 56.7 20.8 56.'
       '6 20.7 56.7C20.6 56.7 20.5 56.8 20.5 56.9L17.2 70C17.1 70.3 17.2 70.4 17.4 70.4ZM24.4 132.1C24.4 131.6 2'
       '4.4 130.8 24.5 129.7L27.1 109C27.6 104.4 29.5 100.7 32.5 98C35.6 95.3 39.4 94 44 94C48.1 94 51.3 95.1 53'
       '.8 97.4C56.2 99.6 57.4 102.7 57.4 106.6C57.4 107 57.3 107.8 57.2 109L57.2 109.3C57.1 109.7 57 109.9 56.8'
       ' 110.1C56.6 110.4 56.3 110.5 56 110.5L45.1 110.8C44.4 110.8 44.1 110.5 44.2 109.8L44.4 108C44.5 107.2 44'
       '.4 106.6 44 106.1C43.7 105.7 43.2 105.4 42.6 105.4C41.9 105.4 41.4 105.7 40.9 106.1C40.5 106.6 40.2 107.'
       '2 40.1 108L37.4 130.8C37.3 131.6 37.4 132.2 37.7 132.7C38 133.2 38.5 133.4 39.1 133.4C39.8 133.4 40.3 13'
       '3.2 40.8 132.7C41.2 132.3 41.5 131.6 41.6 130.8L41.8 128.9C41.9 128.6 42 128.3 42.2 128.2C42.4 128 42.7 '
       '127.9 43 127.9L53.8 128.3C54.2 128.3 54.4 128.4 54.6 128.6C54.7 128.8 54.8 129.1 54.7 129.4L54.7 129.7C5'
       '4.1 134.3 52.3 138 49.2 140.7C46.1 143.4 42.3 144.8 37.7 144.8C33.6 144.8 30.3 143.7 27.9 141.4C25.6 139'
       '.1 24.4 136 24.4 132.1ZM63 199.1L61 181.2C61 181 60.9 180.9 60.7 180.9C60.6 180.9 60.5 181 60.5 181.3L58'
       '.3 198.9C58.2 199.3 58.1 199.5 57.9 199.7C57.7 199.9 57.4 200 57.1 200L46.2 200C45.9 200 45.7 199.9 45.5'
       ' 199.7C45.4 199.5 45.3 199.3 45.3 198.9L51.2 151.4C51.2 151 51.3 150.8 51.6 150.6C51.8 150.4 52 150.3 52'
       '.3 150.3L67.8 150.3C71.6 150.3 74.6 151.5 76.8 153.9C79 156.3 80.1 159.5 80.1 163.5C80.1 164.6 80.1 165.'
       '5 80 166.1C79.7 168.7 78.9 171.1 77.8 173.1C76.6 175.2 75.2 176.9 73.4 178.1C73.1 178.3 73.1 178.4 73.2 '
       '178.6L76.2 198.8L76.2 199.1C76.2 199.4 76.1 199.6 75.9 199.8C75.8 199.9 75.5 200 75.2 200L64 200C63.4 20'
       '0 63.1 199.7 63 199.1ZM63.2 161.7C62.9 161.7 62.8 161.9 62.8 162.1L61.7 170.4C61.7 170.6 61.9 170.8 62.1'
       ' 170.8L63 170.8C64.2 170.8 65.1 170.3 65.9 169.3C66.7 168.3 67.1 166.9 67.1 165.1C67.1 164.1 66.8 163.2 '
       '66.3 162.6C65.8 162 65.1 161.7 64.2 161.7Z')

# icon art in a 100 x 100 tile: the D-car alone (32 px and below) and with two speed lines (48 px and up)
ICON_SMALL = ('M27.23 19.46L29.59 25.32C34.4 24.73 39 27.44 40.82 31.94C42.63 36.43 41.21 41.58 37.34 44.49L46.82 67.97'
              'C51.63 67.38 56.24 70.09 58.05 74.59C59.87 79.08 58.44 84.23 54.57 87.15L56.94 93L64.29 90.03C71.31 87.1'
              '9 75.98 79.36 77.27 68.25C78.55 57.14 76.35 43.67 71.15 30.8L63.73 12.41C62.26 8.77 58.07 7 54.43 8.47L3'
              '0.17 18.28C28.33 19.02 27.23 19.46 27.23 19.46ZM47.85 19.69L65.72 63.92C67.64 59.96 68.57 55.06 68.43 49'
              '.7C68.29 44.33 67.07 38.69 64.9 33.32L59.26 19.35C58.44 17.33 56.12 16.34 54.1 17.16ZM34.01 43.67C29.75 '
              '45.39 24.89 43.33 23.17 39.07C21.45 34.8 23.51 29.95 27.77 28.22C32.04 26.5 36.89 28.56 38.61 32.83C40.3'
              '4 37.09 38.28 41.94 34.01 43.67ZM51.24 86.32C46.98 88.04 42.12 85.98 40.4 81.72C38.68 77.45 40.74 72.6 4'
              '5 70.88C49.27 69.15 54.12 71.21 55.84 75.48C57.57 79.74 55.51 84.6 51.24 86.32Z')
ICON_BIG = ('M48.63 9.72L52.37 18.98C52.84 20.14 52.28 21.46 51.12 21.93C49.95 22.4 48.63 21.84 48.16 20.68L44.42 11.'
            '42C43.96 10.26 44.52 8.94 45.68 8.47C46.84 8 48.16 8.56 48.63 9.72ZM43.38 17.72L45.08 21.92C45.55 23.08 '
            '44.99 24.4 43.83 24.87C42.66 25.34 41.34 24.78 40.87 23.62L39.17 19.41C38.7 18.25 39.27 16.93 40.43 16.4'
            '6C41.59 15.99 42.91 16.55 43.38 17.72ZM32.63 35.92L34.44 40.38C38.1 39.94 41.61 42.01 43 45.43C44.38 48.'
            '86 43.29 52.78 40.34 55.01L47.58 72.91C51.24 72.46 54.76 74.53 56.14 77.96C57.52 81.38 56.44 85.31 53.49'
            ' 87.54L55.29 92L60.9 89.73C66.25 87.57 69.81 81.6 70.79 73.13C71.78 64.65 70.1 54.38 66.13 44.56L60.47 3'
            '0.54C59.35 27.77 56.16 26.41 53.38 27.54L34.88 35.01C33.47 35.58 32.63 35.92 32.63 35.92ZM48.36 36.09L61'
            '.99 69.82C63.45 66.81 64.16 63.07 64.05 58.98C63.95 54.89 63.02 50.58 61.37 46.49L57.06 35.84C56.44 34.2'
            '9 54.67 33.54 53.12 34.16ZM37.81 54.38C34.55 55.69 30.85 54.12 29.54 50.87C28.22 47.62 29.8 43.92 33.05 '
            '42.6C36.3 41.29 40 42.86 41.32 46.11C42.63 49.36 41.06 53.06 37.81 54.38ZM50.95 86.9C47.7 88.22 43.99 86'
            '.65 42.68 83.4C41.37 80.14 42.94 76.44 46.19 75.13C49.44 73.81 53.14 75.39 54.46 78.64C55.77 81.89 54.2 '
            '85.59 50.95 86.9Z')
# the black tile: 100 x 100, corner radius 18 (a cubic per corner)
_K = 18 * 0.5523
TILE = ('M18 0L82 0C%(a)s 0 100 %(b)s 100 18L100 82C100 %(a)s %(a)s 100 82 100L18 100C%(b)s 100 0 %(a)s 0 82'
        'L0 18C0 %(b)s %(b)s 0 18 0Z' % {'a': 82 + _K, 'b': 18 - _K})


def polygons(d, scale, dx=0.0, dy=0.0, steps=16):
    """M/L/C/Z path (absolute coordinates) -> closed polygons in pixels."""
    toks = d.replace('M', ' M ').replace('L', ' L ').replace('C', ' C ').replace('Z', ' Z ').split()
    polys, cur, i, cmd = [], [], 0, None
    pt = lambda x, y: (float(x) * scale + dx, float(y) * scale + dy)
    while i < len(toks):
        if toks[i] in 'MLCZ':
            cmd = toks[i]
            i += 1
        if cmd == 'M':
            if cur:
                polys.append(cur)
            cur = [pt(toks[i], toks[i + 1])]
            i += 2
            cmd = 'L'
        elif cmd == 'L':
            cur.append(pt(toks[i], toks[i + 1]))
            i += 2
        elif cmd == 'C':
            p0 = cur[-1]
            c1, c2, p3 = pt(toks[i], toks[i + 1]), pt(toks[i + 2], toks[i + 3]), pt(toks[i + 4], toks[i + 5])
            i += 6
            for k in range(1, steps + 1):
                s = k / steps
                m = 1 - s
                cur.append((m ** 3 * p0[0] + 3 * m * m * s * c1[0] + 3 * m * s * s * c2[0] + s ** 3 * p3[0],
                            m ** 3 * p0[1] + 3 * m * m * s * c1[1] + 3 * m * s * s * c2[1] + s ** 3 * p3[1]))
        elif cmd == 'Z':
            if cur:
                polys.append(cur)
            cur = []
    if cur:
        polys.append(cur)
    return polys


def coverage(polys, w, h, ss=8):
    """Even-odd fill: per-pixel coverage 0..1 (ss sub-scanlines per pixel row, exact spans along each)."""
    edges = []
    for poly in polys:
        for k in range(len(poly)):
            (x0, y0), (x1, y1) = poly[k - 1], poly[k]
            if y0 != y1:
                edges.append((x0, y0, x1, y1) if y0 < y1 else (x1, y1, x0, y0))
    cov = [[0.0] * w for _ in range(h)]
    for row in range(h * ss):
        y = (row + 0.5) / ss
        xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for x0, y0, x1, y1 in edges if y0 <= y < y1)
        line = cov[row // ss]
        for a, b in zip(xs[0::2], xs[1::2]):
            a, b = max(a, 0.0), min(b, float(w))
            if b <= a:
                continue
            ia, ib = int(a), int(b)
            if ia == ib:
                line[ia] += (b - a) / ss
                continue
            line[ia] += (ia + 1 - a) / ss
            for x in range(ia + 1, min(ib, w)):
                line[x] += 1 / ss
            if ib < w:
                line[ib] += (b - ib) / ss
    return cov


def png(w, h, px):
    """px: rows of (r, g, b, a) tuples."""
    raw = b''.join(b'\x00' + b''.join(bytes(p) for p in row) for row in px)
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def layers(w, h, parts):
    """parts: [(coverage, rgb)] that do not overlap -> RGBA rows."""
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            a = sum(min(1.0, c[y][x]) for c, _ in parts)
            if a <= 0:
                row.append((0, 0, 0, 0))
                continue
            rgb = [sum(min(1.0, c[y][x]) * col[i] for c, col in parts) / a for i in range(3)]
            row.append(tuple(round(v) for v in rgb) + (round(255 * min(1.0, a)),))
        rows.append(row)
    return rows


def icon_png(n):
    s = n / 100
    tile = coverage(polygons(TILE, s), n, n)
    car = coverage(polygons(ICON_SMALL if n <= 32 else ICON_BIG, s), n, n)
    rows = []
    for y in range(n):
        row = []
        for x in range(n):
            t, c = min(1.0, tile[y][x]), min(1.0, car[y][x])
            row.append(tuple(round(BLACK[i] + (YELLOW[i] - BLACK[i]) * c) for i in range(3)) + (round(255 * t),))
        rows.append(row)
    return png(n, n, rows)


def logo_png(h):
    s = (h - 2) / LOGO_H                  # 1 px clear on every side
    w = int(LOGO_W * s + 0.999) + 2
    car = coverage(polygons(CAR, s, 1, 1), w, h)
    acr = coverage(polygons(ACR, s, 1, 1), w, h)
    return png(w, h, layers(w, h, [(car, YELLOW), (acr, WHITE)]))


def main():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'acr_daily')
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [icon_png(n) for n in sizes]
    out = struct.pack('<HHH', 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    for n, d in zip(sizes, imgs):
        out += struct.pack('<BBBBHHII', n % 256, n % 256, 0, 0, 1, 32, len(d), off)
        off += len(d)
    with open(os.path.join(here, 'icon.ico'), 'wb') as f:
        f.write(out + b''.join(imgs))
    with open(os.path.join(here, 'icon-256.png'), 'wb') as f:
        f.write(imgs[-1])
    for h in (48, 72, 96):
        with open(os.path.join(here, 'logo-%d.png' % h), 'wb') as f:
            f.write(logo_png(h))
    print('wrote icon.ico, icon-256.png, logo-48/72/96.png in', here)


if __name__ == '__main__':
    main()
