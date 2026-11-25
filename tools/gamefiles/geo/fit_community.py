"""A community stage on the real roads (fit.py's search, every mirror and rotation: a community stage's own tool may lay
it out its own way), from a route of community_routes.py: python fit_community.py <routes.json> <stage id> <lat> <lon>
<km> -> the geofits.js entry (lat / lon of the game's (0, 0), rotDeg, mirror, how far from the roads)."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import fit  # noqa: E402

routes = {r['stageId']: r['points'] for r in json.load(open(sys.argv[1], encoding='utf-8'))}
sid, lat, lon, km = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
fit.MAPS[sid] = (lat, lon, km, None)
best = None
for mir in fit.MIRRORS:
    fit.FIXED_MIRROR = mir
    geo, q = fit.fit_map(sid, {sid: routes[sid]})
    med, p90 = q[sid]
    print(mir, geo, 'median %.1f m, 90 %% %.1f m' % (med, p90), flush=True)
    if best is None or med + 0.3 * p90 < best[0]:
        best = (med + 0.3 * p90, geo, med, p90)
_s, geo, med, p90 = best
# as geofits.js has it: where the game's (0, 0) is, the rotation and the mirror
lat0 = geo['latRef'] + geo['n0'] / fit.M_LAT
lon0 = geo['lonRef'] + geo['e0'] / fit.m_lon(geo['latRef'])
print(json.dumps({'lat': round(lat0, 7), 'lon': round(lon0, 7), 'rotDeg': geo['rotDeg'], 'mirror': geo['mirror'],
                  'medianM': round(med, 1), 'p90M': round(p90, 1), 'ok': p90 < 40}))
