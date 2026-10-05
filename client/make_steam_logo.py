"""Writes acr_daily/steam-<size>.png (the Steam logo mark, white on transparent) for the sign-in button.

No image library: the logo's SVG path (Simple Icons, 24 x 24) is flattened to polygons and filled with
4 x 4 supersampling (even-odd rule). Steam and the Steam logo are trademarks of Valve Corporation.
"""
import os
import re
import struct
import zlib

PATH = ('M11.979 0C5.678 0 .511 4.86.022 11.037l6.432 2.658c.545-.371 1.203-.59 1.912-.59.063 0 .125.004.188.006'
        'l2.861-4.142V8.91c0-2.495 2.028-4.524 4.524-4.524 2.494 0 4.524 2.031 4.524 4.527s-2.03 4.525-4.524 4.525'
        'h-.105l-4.076 2.911c0 .052.004.105.004.159 0 1.875-1.515 3.396-3.39 3.396-1.635 0-3.016-1.173-3.331-2.727'
        'L.436 15.27C1.862 20.307 6.486 24 11.979 24c6.627 0 11.999-5.373 11.999-12S18.605 0 11.979 0z'
        'M7.54 18.21l-1.473-.61c.262.543.714.999 1.314 1.25 1.297.539 2.793-.076 3.332-1.375.263-.63.264-1.319.005-1.949'
        's-.75-1.121-1.377-1.383c-.624-.26-1.29-.249-1.878-.03l1.523.63c.956.4 1.409 1.5 1.009 2.455'
        '-.397.957-1.497 1.41-2.454 1.012H7.54z'
        'm11.415-9.303c0-1.662-1.353-3.015-3.015-3.015-1.665 0-3.015 1.353-3.015 3.015 0 1.665 1.35 3.015 3.015 3.015'
        ' 1.663 0 3.015-1.35 3.015-3.015z'
        'm-5.273-.005c0-1.252 1.013-2.266 2.265-2.266 1.249 0 2.266 1.014 2.266 2.266 0 1.251-1.017 2.265-2.266 2.265'
        '-1.253 0-2.265-1.014-2.265-2.265z')
ARGS = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Z': 0}


def polygons(d, steps=12):
    toks = re.findall(r'[MmLlHhVvCcSsZz]|-?(?:\d+\.?\d*|\.\d+)', d)
    polys, cur, x, y, sx, sy, cmd, last_c2 = [], [], 0.0, 0.0, 0.0, 0.0, None, None
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in 'Zz':
                if cur:
                    polys.append(cur)
                cur, x, y, last_c2 = [], sx, sy, None
                continue
        n = ARGS[cmd.upper()]
        a = [float(v) for v in toks[i:i + n]]
        i += n
        rel = cmd.islower()
        up = cmd.upper()
        if up == 'M':
            if cur:
                polys.append(cur)
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            sx, sy, cur, last_c2 = x, y, [(x, y)], None
            cmd = 'l' if rel else 'L'      # more pairs after a move are line-tos
        elif up == 'L':
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            cur.append((x, y)); last_c2 = None
        elif up == 'H':
            x = x + a[0] if rel else a[0]
            cur.append((x, y)); last_c2 = None
        elif up == 'V':
            y = y + a[0] if rel else a[0]
            cur.append((x, y)); last_c2 = None
        else:
            if up == 'C':
                c1 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                c2 = (x + a[2], y + a[3]) if rel else (a[2], a[3])
                end = (x + a[4], y + a[5]) if rel else (a[4], a[5])
            else:   # S: first control point mirrors the previous curve's second one
                c1 = (2 * x - last_c2[0], 2 * y - last_c2[1]) if last_c2 else (x, y)
                c2 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                end = (x + a[2], y + a[3]) if rel else (a[2], a[3])
            p0 = (x, y)
            for k in range(1, steps + 1):
                s = k / steps
                m = 1 - s
                cur.append((m ** 3 * p0[0] + 3 * m * m * s * c1[0] + 3 * m * s * s * c2[0] + s ** 3 * end[0],
                            m ** 3 * p0[1] + 3 * m * m * s * c1[1] + 3 * m * s * s * c2[1] + s ** 3 * end[1]))
            x, y = end
            last_c2 = c2
    if cur:
        polys.append(cur)
    return polys


def inside(px, py, polys):
    hit = False
    for poly in polys:
        j = len(poly) - 1
        for k in range(len(poly)):
            (xi, yi), (xj, yj) = poly[k], poly[j]
            if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
                hit = not hit
            j = k
    return hit


def png(n, polys, rgb=(255, 255, 255), ss=4):
    raw = b''
    for y in range(n):
        raw += b'\x00'
        for x in range(n):
            c = sum(inside((x + (i + .5) / ss) * 24 / n, (y + (j + .5) / ss) * 24 / n, polys)
                    for i in range(ss) for j in range(ss))
            raw += bytes(rgb) + bytes([round(255 * c / (ss * ss))])
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    polys = polygons(PATH)
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'acr_daily')
    for n in (18, 27, 36):
        with open(os.path.join(here, 'steam-%d.png' % n), 'wb') as f:
            f.write(png(n, polys))
    print('wrote steam-18/27/36.png')


if __name__ == '__main__':
    main()
