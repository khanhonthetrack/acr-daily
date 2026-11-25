"""Routes of community stages built with ACR Extra Stages (an own level, AcrXs<id>, its stage in one world-partition
cell with its CenterSpline and start / end triggers), from their containers: the same reading as build_routes.py's
for the game's own stages. Oxmod's Thierache (25 Nov 2026): his containers are read where the player's game has them
(never shared: only the route, the stage's line in the game's own metres, is kept).

    (iostore.py over a folder holding the stage containers: ACR_GAME_DIR=<a folder with acr\\Content\\Paks\\*.utoc>)
    python community_routes.py <extracted cells dir> <stage id> <variant stage id> <track name> [<more>...]  > routes.json

Each: <cells dir>\\<AcrXs id>\\*.umap (iostore.find('AcrXs/Stages/<id>/'), then geometry.py's scan)."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G  # noqa: E402
from build_routes import G_thin, RUNOUT_M, hermite, spline_records  # noqa: E402


def route(cells_dir, level, stage_id, track):
    env = os.path.join(cells_dir, level)
    # (only the stage's own cell: the other 160 are the host level's)
    splines, markers = G.scan(env)
    centre = max((s for s in splines if s['kind'] == 'CenterSpline'), key=lambda s: len(s['pts']))
    cell = centre['cell']
    recs = []
    for f in os.listdir(env):
        if f.startswith(cell) and f.endswith('.umap'):
            for name, d, _a in G.exports(open(os.path.join(env, f), 'rb').read()):
                if name == 'CenterSpline':
                    r = spline_records(d)
                    if len(r) > len(recs):
                        recs = r
    line = hermite(recs)
    A = G.arc([(x, y, 0) for x, y in line])

    import numpy as np
    L = np.array(line)

    def at(v):
        d = np.hypot(L[:, 0] - v[0], L[:, 1] - v[1])
        i = int(d.argmin())
        return A[i], float(d[i])
    # (the stage's own triggers: in its cell; the other cells' are the host level's)
    def trig(name):
        cands = [at(v) for m in markers if m['cell'] == cell and m['name'] == name for v in m['vecs']]
        cands = [c for c in cands if c[1] < 40]
        return min(cands, key=lambda c: c[1])[0]
    s, e = trig('BC_StartSequenceTrigger_C'), trig('BC_EndSequenceTrigger_C')
    forward = e > s
    fin = e - RUNOUT_M if forward else e + RUNOUT_M
    lo, hi = min(s, fin), max(s, fin)
    pts = [line[i] for i, a in enumerate(A) if lo <= a <= hi]
    if not forward:
        pts = pts[::-1]
    pts = G_thin(pts, 5.0)
    return {'track': track, 'stageId': stage_id, 'level': level, 'startAt': round(s), 'endTriggerAt': round(e),
            'lengthM': round(sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))),
            'points': [[round(x, 2), round(y, 2)] for x, y in pts]}


if __name__ == '__main__':
    a = sys.argv[2:]
    out = [route(sys.argv[1], a[i], a[i + 1], a[i + 2]) for i in range(0, len(a), 3)]
    for r in out:
        print('%-50s %-24s %5d m  %d points' % (r['track'], r['stageId'], r['lengthM'], len(r['points'])), file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False))
