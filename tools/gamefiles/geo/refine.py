"""anchor_fits.json -> fine fit on the OpenStreetMap roads around it (rotation +-3 deg, position +-240 m),
per variant median / 90 % distance from the roads; writes refined.json (Saverne also tried 2 and 4 % larger)."""
import sys, os, json, io, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from scipy.spatial import cKDTree
import fit
M_LAT = fit.M_LAT
rows = json.load(io.open(os.path.join(HERE, 'routes_full.json'), encoding='utf-8-sig'))[0]['results']
anchors = json.load(open(os.path.join(HERE, 'anchor_fits.json')))
PREFIX = {'Munster': 'AlsaceS2Munster', 'Saverne': 'AlsaceS4Saverne', 'Loutraki': 'GreeceS4Loutraki', 'Elatia': 'GreeceS3Elatia'}
out = {}
for name, prefix in PREFIX.items():
    lat_c, lon_c, km, _ = fit.MAPS[prefix]
    tree = cKDTree(fit.road_points(fit.osm_roads(lat_c, lon_c, km), lat_c, lon_c))
    routes = {r['stage_id']: np.array(json.loads(r['points']), float) for r in rows if (r['stage_id'] or '').startswith(prefix)}
    allp = np.concatenate([fit.resample(p, 300) for p in routes.values()])
    a = anchors[name]
    def en(lat0, lon0):
        return ((lon0 - lon_c) * fit.m_lon(lat_c), (lat0 - lat_c) * M_LAT)
    def score(rot, e0, n0, sc=1.0, pts=allp, full=False):
        x = -pts[:, 0] * sc; z = pts[:, 1] * sc
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        d, _ = tree.query(np.stack([x * c - z * s + e0, x * s + z * c + n0], 1))
        return (np.median(d), np.percentile(d, 90)) if full else np.median(d) + 0.3 * np.percentile(d, 90)
    for sc in ([1.0, 1.02, 1.04] if name == 'Saverne' else [1.0]):
        e0, n0 = en(a['lat'], a['lon']); rot = a['rotDeg']
        best = score(rot, e0, n0, sc)
        for span, st, tspan, tst in ((3, 0.5, 240, 20), (1, 0.1, 40, 4), (0.3, 0.05, 8, 1)):
            # coordinate descent: rotation, then a translation grid, coarse to fine
            for r in np.arange(rot - span, rot + span + 1e-9, st):
                v = score(r, e0, n0, sc)
                if v < best: best, rot = v, r
            grid = np.arange(-tspan, tspan + 1e-9, tst)
            be = (e0, n0)
            for de in grid:
                for dn in grid:
                    v = score(rot, e0 + de, n0 + dn, sc)
                    if v < best: best, be = v, (e0 + de, n0 + dn)
            e0, n0 = be
        per = {sid: tuple(round(float(v), 1) for v in score(rot, e0, n0, sc, fit.resample(p, 400), True)) for sid, p in routes.items()}
        lat0 = lat_c + n0 / M_LAT; lon0 = lon_c + e0 / fit.m_lon(lat_c)
        moved = math.hypot((lon0 - a['lon']) * fit.m_lon(lat0), (lat0 - a['lat']) * M_LAT)
        print('%-9s scale %.2f rot %.2f (start points said %.2f), moved %.0f m from the start-point fit' % (name, sc, rot, a['rotDeg'], moved))
        for sid, (m, p9) in sorted(per.items()): print('    %-32s median %5.1f m  90%% %5.1f m' % (sid, m, p9))
        out['%s@%.2f' % (name, sc)] = {'lat': lat0, 'lon': lon0, 'rotDeg': round(float(rot), 2), 'scale': sc, 'quality': per}
json.dump(out, open(os.path.join(HERE, 'refined.json'), 'w'), indent=1)