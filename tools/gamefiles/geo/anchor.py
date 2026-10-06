"""Each map placed from the start coordinates the game menu shows for its variants (Single Rally Stage >
Change rally stage): a 2D similarity fit of the routes' first points (mirrored in x) to those coordinates.
Prints the scale (1.0 = real size), rotation and how far each start is off; writes anchor_fits.json."""
import math, json, io, os, sys
def dms(d, m, s): return d + m / 60 + s / 3600
M_LAT = 111132.954
def m_lon(lat): return 111319.49 * math.cos(math.radians(lat))
MAPS = {
 'Munster': [((-5864.6, -1110.7), dms(47,58,47.49), dms(7,6,7.09)), ((-158.2, 123.9), dms(48,1,49.84), dms(7,7,18.73)),
             ((-4525.0, 845.3), dms(47,59,27.21), dms(7,7,44.51)), ((-2774.8, 1115.4), dms(48,0,24.51), dms(7,8,0.68))],
 'Saverne': [((-2848.8, 923.1), dms(48,37,43.00), dms(7,18,22.24)), ((1622.9, 451.7), dms(48,40,14.80), dms(7,18,16.11)),
             ((-947.7, 1219.6), dms(48,38,47.11), dms(7,18,42.43))],
 'Loutraki': [((-2531.8, -2294.1), dms(37,58,30.76), dms(23,2,7.17)), ((2437.1, 2294.6), dms(38,1,8.68), dms(23,5,19.53)),
              ((-611.0, 676.2), dms(37,59,29.11), dms(23,4,7.34)), ((-1026.0, 491.7), dms(37,59,14.10), dms(23,4,0.12))],
 'Elatia': [((-1631.9, -2887.3), dms(38,37,41.38), dms(22,47,34.50)), ((2494.1, 3814.0), dms(38,39,51.52), dms(22,52,14.56)),
            ((127.8, 320.2), dms(38,38,35.40), dms(22,49,48.05)), ((151.3, 254.8), dms(38,38,36.16), dms(22,49,45.78))],
}
out = {}
for name, pts in MAPS.items():
    lat0 = sum(p[1] for p in pts) / len(pts); lon0 = sum(p[2] for p in pts) / len(pts)
    G = [(-x, z) for (x, z), la, lo in pts]                       # mirror x
    W = [((lo - lon0) * m_lon(lat0), (la - lat0) * M_LAT) for _, la, lo in pts]
    gc = [sum(c) / len(G) for c in zip(*G)]; wc = [sum(c) / len(W) for c in zip(*W)]
    # 2D similarity (complex numbers): w = s e^{i a} g + t
    gs = [complex(g[0] - gc[0], g[1] - gc[1]) for g in G]; ws = [complex(w[0] - wc[0], w[1] - wc[1]) for w in W]
    num = sum(w * g.conjugate() for g, w in zip(gs, ws)); den = sum(abs(g) ** 2 for g in gs)
    k = num / den; s, a = abs(k), math.degrees(math.atan2(k.imag, k.real)) % 360
    # also the best rigid fit (scale 1)
    k1 = k / abs(k)
    res_s = [abs(w - k * g) for g, w in zip(gs, ws)]; res_1 = [abs(w - k1 * g) for g, w in zip(gs, ws)]
    print('%-9s scale %.4f  rot %.2f deg   residuals (scaled) %s   (scale 1) %s' % (name, s, a,
          [round(r) for r in res_s], [round(r) for r in res_1]))
    # the game origin with scale 1: w = k1 (g - gc) + wc -> origin g=(0,0)
    o = k1 * complex(-gc[0], -gc[1]) + complex(*wc)
    out[name] = {'lat': lat0 + o.imag / M_LAT, 'lon': lon0 + o.real / m_lon(lat0), 'rotDeg': round(a, 2), 'scale': round(s, 4)}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'anchor_fits.json'), 'w'), indent=1)
print(json.dumps(out))