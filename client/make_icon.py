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

# full logo, viewBox 0 0 155.1 200 (as in server/src/logo.js)
LOGO_W, LOGO_H = 155.1, 200
CAR = ('M54.1 1.2L72.9 20C74.2 21.3 74.2 23.3 72.9 24.5C71.7 25.7 69.7 25.7 68.5 24.5L49.7 5.7C48.4 4.5 48.4 2.5 49.7 1.2'
       'C50.9 0 52.9 0 54.1 1.2ZM52.4 17.3L64 29C65.2 30.2 65.2 32.2 64 33.5C62.8 34.7 60.8 34.7 59.5 33.5L47.9 21.8'
       'C46.6 20.6 46.6 18.6 47.9 17.3C49.1 16.1 51.1 16.1 52.4 17.3ZM49.7 32.6L55 37.9C56.3 39.2 56.3 41.2 55 42.4'
       'C53.8 43.6 51.8 43.6 50.6 42.4L45.2 37C44 35.8 44 33.8 45.2 32.6C46.4 31.3 48.4 31.3 49.7 32.6ZM46.1 67.5L53.2 74.6'
       'C59.9 70.7 68.4 71.8 73.8 77.3C79.3 82.8 80.4 91.2 76.6 97.9L105.1 126.5C111.8 122.6 120.3 123.8 125.7 129.2'
       'C131.2 134.7 132.3 143.1 128.5 149.8L135.6 157L144.5 148C153.1 139.5 155.1 125.1 150 107.9C145 90.8 133.4 72.4 117.7 56.7'
       'L95.3 34.4C90.9 29.9 83.6 29.9 79.2 34.4L49.7 63.9C47.4 66.1 46.1 67.5 46.1 67.5ZM76.5 54.9L130.4 108.8'
       'C130.7 101.8 129 94 125.5 86.2C121.9 78.4 116.6 70.9 110.1 64.3L93.1 47.3C90.6 44.9 86.6 44.9 84.1 47.3Z'
       'M71.2 98.8C66 104 57.5 104 52.4 98.8C47.2 93.6 47.2 85.2 52.4 80C57.5 74.8 66 74.8 71.2 80C76.3 85.2 76.3 93.6 71.2 98.8Z'
       'M123.1 150.7C117.9 155.9 109.5 155.9 104.3 150.7C99.1 145.5 99.1 137.1 104.3 131.9C109.5 126.7 117.9 126.7 123.1 131.9'
       'C128.3 137.1 128.3 145.5 123.1 150.7Z')
ACR = ('M18.6 129.3L18.5 124.7C18.5 124.6 18.5 124.5 18.4 124.4C18.3 124.4 18.3 124.3 18.2 124.3L12.8 124.3'
       'C12.6 124.3 12.5 124.5 12.4 124.7L11.2 129.3C11.1 129.9 10.8 130.2 10.2 130.2L0.8 130.2C0.2 130.2 0 129.9 0.2 129.2'
       'L13.7 88C13.9 87.4 14.2 87.2 14.8 87.2L25.7 87.2C26.3 87.2 26.6 87.4 26.6 88L30 129.2L30 129.3C30 129.9 29.7 130.2 29.1 130.2'
       'L19.4 130.2C18.8 130.2 18.6 129.9 18.6 129.3ZM15.1 115.5L18 115.5C18.1 115.5 18.2 115.4 18.3 115.2L18.1 103.8'
       'C18.1 103.7 18 103.6 17.9 103.6C17.8 103.6 17.7 103.7 17.7 103.8L14.9 115.2C14.8 115.4 14.9 115.5 15.1 115.5Z'
       'M36.3 155.1C36.3 154.7 36.3 154 36.4 153L38.6 135C39.1 131.1 40.7 127.9 43.4 125.6C46 123.2 49.3 122.1 53.3 122.1'
       'C56.8 122.1 59.7 123 61.8 125C63.8 126.9 64.9 129.6 64.9 133C64.9 133.4 64.8 134 64.8 135L64.7 135.3'
       'C64.7 135.6 64.5 135.9 64.4 136C64.2 136.2 64 136.3 63.7 136.3L54.2 136.6C53.6 136.6 53.4 136.3 53.5 135.8L53.6 134.2'
       'C53.7 133.5 53.6 133 53.3 132.6C53 132.2 52.6 132 52.1 132C51.5 132 51 132.2 50.7 132.6C50.3 133 50 133.5 49.9 134.2'
       'L47.5 154C47.5 154.6 47.6 155.2 47.8 155.6C48.1 156 48.5 156.2 49.1 156.2C49.7 156.2 50.1 156 50.5 155.6'
       'C50.9 155.2 51.2 154.7 51.2 154L51.4 152.3C51.5 152 51.6 151.8 51.8 151.7C51.9 151.5 52.2 151.4 52.4 151.4'
       'L61.8 151.8C62.1 151.8 62.3 151.8 62.5 152C62.6 152.2 62.7 152.5 62.6 152.7L62.5 153C62.1 157 60.5 160.1 57.8 162.5'
       'C55.1 164.9 51.8 166.1 47.9 166.1C44.3 166.1 41.5 165.1 39.4 163.1C37.3 161.2 36.3 158.5 36.3 155.1Z'
       'M85 199.2L83.2 183.7C83.2 183.5 83.1 183.5 83 183.5C82.8 183.5 82.8 183.6 82.8 183.8L80.9 199.1C80.8 199.4 80.7 199.6 80.5 199.8'
       'C80.3 199.9 80.1 200 79.9 200L70.4 200C70.2 200 70 199.9 69.8 199.8C69.7 199.6 69.6 199.4 69.7 199.1L74.7 157.9'
       'C74.7 157.6 74.9 157.4 75 157.2C75.2 157 75.4 157 75.7 157L89.2 157C92.4 157 95 158 96.9 160.1C98.8 162.2 99.8 165 99.8 168.4'
       'C99.8 169.4 99.7 170.1 99.7 170.7C99.4 172.9 98.7 174.9 97.8 176.7C96.8 178.5 95.5 180 94 181.1C93.7 181.2 93.7 181.3 93.8 181.5'
       'L96.4 199L96.4 199.2C96.4 199.4 96.3 199.6 96.2 199.8C96 199.9 95.8 200 95.5 200L85.8 200C85.3 200 85.1 199.7 85 199.2Z'
       'M85.1 166.9C84.9 166.9 84.8 167 84.8 167.2L83.9 174.4C83.9 174.6 84 174.7 84.2 174.7L85 174.7C86 174.7 86.8 174.2 87.5 173.4'
       'C88.1 172.5 88.5 171.3 88.5 169.8C88.5 168.9 88.3 168.1 87.8 167.6C87.4 167.1 86.7 166.9 86 166.9Z')

# icon art in a 100 x 100 tile: the D-car alone (32 px and below) and with two speed lines (48 px and up)
ICON_SMALL = ('M16.55 34.05L20.92 38.43C25.04 36.05 30.23 36.74 33.58 40.1C36.94 43.45 37.62 48.64 35.25 52.75L52.79 70.3'
              'C56.91 67.92 62.1 68.61 65.45 71.97C68.81 75.32 69.5 80.51 67.12 84.63L71.5 89L76.99 83.51'
              'C82.24 78.26 83.45 69.41 80.36 58.9C77.27 48.38 70.13 37.08 60.51 27.46L46.77 13.72C44.05 11 39.6 11 36.88 13.72'
              'L18.75 31.85C17.37 33.23 16.55 34.05 16.55 34.05ZM35.23 26.36L68.28 59.41C68.5 55.11 67.47 50.33 65.29 45.55'
              'C63.1 40.76 59.85 36.14 55.84 32.13L45.4 21.69C43.89 20.18 41.41 20.18 39.9 21.69Z'
              'M31.94 53.28C28.75 56.47 23.58 56.47 20.4 53.28C17.21 50.1 17.21 44.93 20.4 41.74C23.58 38.56 28.75 38.56 31.94 41.74'
              'C35.12 44.93 35.12 50.1 31.94 53.28ZM63.81 85.15C60.62 88.34 55.45 88.34 52.27 85.15C49.08 81.97 49.08 76.8 52.27 73.61'
              'C55.45 70.43 60.62 70.43 63.81 73.61C66.99 76.8 66.99 81.97 63.81 85.15Z')
ICON_BIG = ('M28.55 12.91L35.8 20.16C36.71 21.06 36.71 22.54 35.8 23.45C34.89 24.36 33.41 24.36 32.51 23.45L25.26 16.2'
            'C24.35 15.29 24.35 13.82 25.26 12.91C26.17 12 27.64 12 28.55 12.91ZM26.8 22.57L30.09 25.86C31 26.77 31 28.25 30.09 29.16'
            'C29.18 30.07 27.71 30.07 26.8 29.16L23.5 25.86C22.59 24.95 22.59 23.48 23.5 22.57C24.41 21.66 25.89 21.66 26.8 22.57Z'
            'M23.94 44.09L27.44 47.58C30.72 45.69 34.87 46.24 37.56 48.92C40.24 51.6 40.78 55.75 38.89 59.03L52.91 73.05'
            'C56.19 71.16 60.34 71.7 63.02 74.39C65.71 77.07 66.25 81.22 64.36 84.5L67.85 88L72.25 83.61'
            'C76.44 79.42 77.41 72.34 74.94 63.94C72.47 55.54 66.76 46.5 59.07 38.82L48.09 27.84C45.92 25.67 42.36 25.67 40.19 27.84'
            'L25.7 42.33C24.6 43.43 23.94 44.09 23.94 44.09ZM38.87 37.94L65.29 64.35C65.46 60.92 64.64 57.1 62.89 53.27'
            'C61.15 49.45 58.54 45.76 55.34 42.55L47 34.21C45.79 33 43.81 33 42.61 34.21Z'
            'M36.24 59.46C33.69 62 29.56 62 27.02 59.46C24.47 56.91 24.47 52.78 27.02 50.24C29.56 47.69 33.69 47.69 36.24 50.24'
            'C38.78 52.78 38.78 56.91 36.24 59.46ZM61.71 84.93C59.16 87.47 55.03 87.47 52.49 84.93C49.94 82.38 49.94 78.25 52.49 75.7'
            'C55.03 73.16 59.16 73.16 61.71 75.7C64.25 78.25 64.25 82.38 61.71 84.93Z')
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
