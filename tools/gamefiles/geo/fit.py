"""Fit ACR stage routes (game metres) onto real roads (OpenStreetMap). Scratchpad experiment.

Model per map (all variants of one map share the game's world coordinates):
    (e, n) = R(rot) * M(mirror) * (x, z) + (e0, n0)        metres east / north of the map's reference point
    lat = lat_ref + n / 111132.954,  lon = lon_ref + e / (111319.49 * cos(lat_ref))
"""
import json, math, os, sys, time, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'pylib'))
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt

M_LAT = 111132.954
def m_lon(lat): return 111319.49 * math.cos(math.radians(lat))

MAPS = {   # map prefix -> (search centre lat, lon, radius km, known start: (stage_id, lat, lon) or None)
    'WelesS3HafrenNorth': (52.4875, -3.7136, 6, None),   # the menu's start (52°29'15"N 3°42'48.99"W) is ~250 m off: not used
    'WelesS4HafrenSouth': (52.46, -3.70, 9, None),
    'MonteCarloS2Sisteron': (44.22, 5.98, 9, None),
    'MonteCarloS1Bollene': (43.97, 7.36, 13, None),
    'AlsaceS2Munster': (48.02, 7.12, 13, None),
    'AlsaceS4Saverne': (48.69, 7.32, 10, None),
    'GreeceS3Elatia': (38.64, 22.80, 14, None),
    'GreeceS4Loutraki': (37.97, 23.03, 12, None),
}


def osm_roads(lat, lon, km):
    cache = os.path.join(HERE, 'osm_%.3f_%.3f_%d.json' % (lat, lon, km))
    if os.path.exists(cache):
        return json.load(open(cache))
    dlat, dlon = km * 1000 / M_LAT, km * 1000 / m_lon(lat)
    q = ('[out:json][timeout:120];way["highway"](%f,%f,%f,%f);out geom;' % (lat - dlat, lon - dlon, lat + dlat, lon + dlon))
    for url in ('https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter'):
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': q}).encode(),
                                         headers={'User-Agent': 'acr-daily-satmap-experiment'})
            d = json.load(urllib.request.urlopen(req, timeout=180))
            ways = [[(p['lat'], p['lon']) for p in w['geometry']] for w in d['elements'] if 'geometry' in w]
            json.dump(ways, open(cache, 'w'))
            return ways
        except Exception as e:
            print('overpass', url, e)
            time.sleep(20)
    raise SystemExit('no OSM data')


def road_points(ways, lat0, lon0, step=4.0):
    """Roads as dense points in metres (e, n) around (lat0, lon0)."""
    ml = m_lon(lat0)
    pts = []
    for w in ways:
        xy = [((lo - lon0) * ml, (la - lat0) * M_LAT) for la, lo in w]
        for (a, b), (c, d) in zip(xy, xy[1:]):
            n = max(1, int(math.hypot(c - a, d - b) / step))
            for k in range(n):
                pts.append((a + (c - a) * k / n, b + (d - b) * k / n))
        if xy:
            pts.append(xy[-1])
    return np.array(pts)


MIRRORS = {'none': (1, 1), 'x': (-1, 1), 'z': (1, -1)}


def transform(xz, rot_deg, mirror, e0, n0):
    sx, sz = MIRRORS[mirror]
    x, z = xz[:, 0] * sx, xz[:, 1] * sz
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    return np.stack([x * c - z * s + e0, x * s + z * c + n0], axis=1)


def resample(p, n):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    t = np.linspace(0, d[-1], n)
    return np.stack([np.interp(t, d, p[:, 0]), np.interp(t, d, p[:, 1])], axis=1)


def fit_map(prefix, routes):
    lat_c, lon_c, km, known = MAPS[prefix]
    ways = osm_roads(lat_c, lon_c, km)
    roads = road_points(ways, lat_c, lon_c)
    tree = cKDTree(roads)
    var = {sid: np.array(p, float) for sid, p in routes.items()}
    allp = np.concatenate([resample(p, 150) for p in var.values()])
    # distance field (10 m cells, capped) for the coarse search
    cell, R = 10.0, km * 1000
    nC = int(2 * R / cell)
    grid = np.ones((nC, nC), bool)
    ij = ((roads + R) / cell).astype(int)
    ok = (ij >= 0).all(1) & (ij < nC).all(1)
    grid[ij[ok, 1], ij[ok, 0]] = False
    field = np.minimum(distance_transform_edt(grid) * cell, 150.0)

    def coarse_score(en):
        ij = ((en + R) / cell).astype(int)
        inside = (ij >= 0).all(-1) & (ij < nC).all(-1)
        ij = np.clip(ij, 0, nC - 1)
        v = field[ij[..., 1], ij[..., 0]]
        return np.where(inside, v, 150.0).mean(-1)

    best = []
    if known:
        sid, la, lo = known
        p0 = var[sid][0]
        e_s, n_s = (lo - lon_c) * m_lon(lat_c), (la - lat_c) * M_LAT
        cands = []
        for mir in MIRRORS:
            for rot in np.arange(0, 360, 1.0):
                a = transform(allp - p0, rot, mir, e_s, n_s)
                cands.append((coarse_score(a[None])[0], rot, mir, e_s - 0, n_s - 0, p0))
        cands.sort(key=lambda c: c[0])
        best = [(s, r, m, e, n, p0) for s, r, m, e, n, p0 in cands[:5]]
    else:
        sub = resample(allp, 60)
        c0 = sub.mean(0)
        steps = np.arange(-R * 0.85, R * 0.85, 100.0)
        TE, TN = np.meshgrid(steps, steps)
        T = np.stack([TE.ravel(), TN.ravel()], 1)
        cands = []
        for mir in MIRRORS if prefix == 'WelesS3HafrenNorth' else [FIXED_MIRROR]:
            for rot in (np.arange(0, 360, 3.0) if ROT_RANGE is None else np.arange(ROT_RANGE[0], ROT_RANGE[1] + 0.1, 1.0)):
                a = transform(sub - c0, rot, mir, 0, 0)
                sc = coarse_score(a[None, :, :] + T[:, None, :])
                k = np.argsort(sc)[:3]
                for kk in k:
                    cands.append((sc[kk], rot, mir, T[kk, 0], T[kk, 1], c0))
        cands.sort(key=lambda c: c[0])
        best = cands[:8]
    # refine each candidate: rotation +-3 deg by 0.1, translation +-60 m by 2 m, on the KD tree (median distance)
    sub2 = resample(allp, 400)
    results = []
    for sc, rot, mir, e, n, ref in best:
        cur = (rot, e, n)
        def med(r, e_, n_):
            a = transform(sub2 - ref, r, mir, e_, n_)
            d, _ = tree.query(a)
            return np.median(d) + 0.3 * np.percentile(d, 90)
        bestv = med(*cur)
        for span, st in ((3.0, 0.5), (0.6, 0.1)):
            for r in np.arange(cur[0] - span, cur[0] + span + 1e-9, st):
                v = med(r, cur[1], cur[2])
                if v < bestv:
                    bestv, cur = v, (r, cur[1], cur[2])
            for span_t, st_t in ((60, 10), (12, 2), (3, 0.5)):
                best_t = cur
                for de in np.arange(-span_t, span_t + 1e-9, st_t):
                    for dn in np.arange(-span_t, span_t + 1e-9, st_t):
                        v = med(cur[0], cur[1] + de, cur[2] + dn)
                        if v < bestv:
                            bestv, best_t = v, (cur[0], cur[1] + de, cur[2] + dn)
                cur = best_t
        results.append((bestv, cur, mir, ref))
    results.sort(key=lambda r: r[0])
    _, (rot, e, n), mir, ref = results[0]
    # express as: (e, n) = R M (x, z) + (E0, N0), i.e. for the game origin
    sx, sz = MIRRORS[mir]
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    rx, rz = ref[0] * sx, ref[1] * sz
    E0, N0 = e - (rx * c - rz * s), n - (rx * s + rz * c)
    out = {}
    for sid, p in var.items():
        a = transform(p, rot, mir, E0, N0)
        d, _ = tree.query(a)
        out[sid] = (float(np.median(d)), float(np.percentile(d, 90)))
    return {'latRef': lat_c, 'lonRef': lon_c, 'rotDeg': round(float(rot), 2), 'mirror': mir,
            'e0': round(float(E0), 2), 'n0': round(float(N0), 2)}, out


def to_latlon(geo, xz):
    en = transform(np.array(xz, float), geo['rotDeg'], geo['mirror'], geo['e0'], geo['n0'])
    return [(geo['latRef'] + n / M_LAT, geo['lonRef'] + e / m_lon(geo['latRef'])) for e, n in en]


FIXED_MIRROR = 'none'
ROT_RANGE = None

if __name__ == '__main__':
    rows = json.load(open(os.path.join(HERE, 'routes_full.json'), encoding='utf-8-sig'))[0]['results']
    args = sys.argv[1:]
    if args and args[0] == '--rot':
        ROT_RANGE = (float(args[1]), float(args[2])); args = args[3:]
    which = args or list(MAPS)
    fits = json.load(open(os.path.join(HERE, 'map_fits.json'))) if os.path.exists(os.path.join(HERE, 'map_fits.json')) else {}
    if 'WelesS3HafrenNorth' in fits:
        FIXED_MIRROR = fits['WelesS3HafrenNorth']['geo']['mirror']
    for prefix in which:
        routes = {r['stage_id']: json.loads(r['points']) for r in rows if (r['stage_id'] or '').startswith(prefix)}
        t0 = time.time()
        geo, q = fit_map(prefix, routes)
        if prefix == 'WelesS3HafrenNorth':
            FIXED_MIRROR = geo['mirror']
        fits[prefix] = {'geo': geo, 'quality': q}
        print(prefix, geo, {k: (round(a, 1), round(b, 1)) for k, (a, b) in q.items()}, '%.0fs' % (time.time() - t0), flush=True)
        json.dump(fits, open(os.path.join(HERE, 'map_fits.json'), 'w'), indent=1)




