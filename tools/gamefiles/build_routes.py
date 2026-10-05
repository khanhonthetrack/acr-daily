"""Every stage variant's route from the game's own files: the centre spline between the start and end triggers."""
import json, math, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geometry as G
import iostore
import numpy as np

SP = os.path.dirname(os.path.abspath(__file__))
RUNOUT_M = 140.0      # the stage clock stops this far before the end trigger (Saverne: 141 m measured; Wales: 223 m)
ST = json.load(open(os.path.join(SP, 'st_track.json'), encoding='utf-8'))

# env folder -> (string-table prefix, location, stage-id prefix, variant kinds, menu km per variant (truncated))
ENVS = {
    'AlsaceS2Munster': ('MUNSTER', 'Alsace', 'AlsaceS2Munster', {
        'FULL_FORWARD': 10, 'FULL_REVERSE': 10, 'SHORT1_FORWARD': 7, 'SHORT1_REVERSE': 6, 'SHORT2_FORWARD': 5, 'SHORT2_REVERSE': 5}),
    'AlsaceS4Saverne': ('SAVERNE', 'Alsace', 'AlsaceS4Saverne', {
        'FULL_FORWARD': 9, 'FULL_REVERSE': 8, 'SHORT1_FORWARD': 4, 'SHORT1_REVERSE': 4}),
    'WalesS3HafrenNorth': ('HAFRENNORTH', 'Wales', 'WelesS3HafrenNorth', {
        'FULL_FORWARD': 11, 'FULL_REVERSE': 11, 'CUT1_FORWARD': 6, 'CUT1_REVERSE': 6, 'CUT2_FORWARD': 5, 'CUT2_REVERSE': 5}),
    'WalesS4HafrenSouth': ('HAFRENSOUTH', 'Wales', 'WelesS4HafrenSouth', {'FULL_FORWARD': 4, 'FULL_REVERSE': 4}),
    'MonteCarloS1Bollene': ('COLDETURINI', 'Monte Carlo', 'MonteCarloS1Bollene', {
        'FULL_FORWARD': 18, 'FULL_REVERSE': 18, 'SHORT1_FORWARD': 11, 'SHORT1_REVERSE': 11, 'SHORT2_FORWARD': 6,
        'SHORT2_REVERSE': 6, 'SHORT3_FORWARD': 5, 'SHORT3_REVERSE': 5}),
    'MonteCarloS2Sisteron': ('SISTERON', 'Monte Carlo', 'MonteCarloS2Sisteron', {
        'FULL_FORWARD': 13, 'FULL_REVERSE': 13, 'CUT1_FORWARD': 7, 'CUT1_REVERSE': 7, 'CUT2_FORWARD': 5, 'CUT2_REVERSE': 5}),
    'GreeceS3Elatia': ('ELATIA', 'Greece', 'GreeceS3Elatia', {
        'FULL_FORWARD': 11, 'FULL_REVERSE': 11, 'CUT1_FORWARD': 4, 'CUT1_REVERSE': 6, 'CUT2_FORWARD': 5, 'CUT2_REVERSE': 5}),
    'GreeceS4Loutraki': ('LOUTRAKI', 'Greece', 'GreeceS4Loutraki', {
        'FULL_FORWARD': 10, 'FULL_REVERSE': 10, 'CUT1_FORWARD': 4, 'CUT1_REVERSE': 4, 'CUT2_FORWARD': 5, 'CUT2_REVERSE': 5}),
}
# stage ids seen in a real save (the others follow the same pattern but are not confirmed)
CONFIRMED_IDS = {'AlsaceS2MunsterShort2Forward', 'AlsaceS2MunsterFullForward', 'AlsaceS2MunsterFullReverse',
                 'AlsaceS4SaverneFullForward', 'AlsaceS4SaverneFullReverse', 'AlsaceS4SaverneShort1Forward',
                 'GreeceS4LoutrakiCut1Reverse', 'GreeceS4LoutrakiCut2Forward', 'WelesS3HafrenNorthCut2Forward',
                 'WelesS3HafrenNorthCut2Reverse', 'WelesS3HafrenNorthFullForward', 'WelesS4HafrenSouthFullForward'}


def spline_records(d, S=79):
    """[(pos, arrive, leave)] in metres (x, y, z) of the main point chain (keys 0, 1, 2 ...)."""
    vec = G.vectors(d)
    best = []
    for o in sorted(vec):
        if o < 4 or abs(struct.unpack_from('<f', d, o - 4)[0]) > 1e-6:
            continue
        ch = [o]
        while ch[-1] + S in vec and abs(struct.unpack_from('<f', d, ch[-1] + S - 4)[0] - len(ch)) < 1e-3:
            ch.append(ch[-1] + S)
        if len(ch) > len(best):
            best = ch
    out = []
    for o in best:
        p = struct.unpack_from('<3d', d, o)
        a = struct.unpack_from('<3d', d, o + 24)
        l = struct.unpack_from('<3d', d, o + 48)
        out.append(tuple(np.array(v) / 100 for v in (p, a, l)))
    return out


def hermite(recs, step=2.0):
    """Sample the spline (cubic Hermite between keys, as Unreal does) every ~step metres -> [(x, y)]."""
    pts = []
    for (p0, _a0, l0), (p1, a1, _l1) in zip(recs, recs[1:]):
        n = max(1, int(np.linalg.norm(p1[:2] - p0[:2]) // step))
        for k in range(n):
            t = k / n
            h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
            q = h00 * p0 + h10 * l0 + h01 * p1 + h11 * a1
            pts.append((float(q[0]), float(q[1])))
    pts.append((float(recs[-1][0][0]), float(recs[-1][0][1])))
    return pts


def cell_bytes(env, cell8):
    d = os.path.join(SP, 'ext', env)
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.startswith(cell8) and f.endswith('.umap'):
            return open(os.path.join(d, f), 'rb').read()
    for t, f, i in iostore.find('Levels/%s/_Generated_/%s' % (env, cell8)):
        os.makedirs(d, exist_ok=True)
        return t.extract_index(i, os.path.join(d, os.path.basename(f)))
    raise FileNotFoundError(cell8)


def build(env):
    prefix, location, idpre, menu = ENVS[env]
    g = json.load(open(os.path.join(SP, 'ext', env, 'geometry.json')))
    centre = [s for s in g['splines'] if s['kind'] == 'CenterSpline'][0]
    b = cell_bytes(env, centre['cell'])
    recs = []
    for name, d, _a in G.exports(b):
        if name == 'CenterSpline':
            r = spline_records(d)
            if len(r) > len(recs):
                recs = r
    line = hermite(recs)
    A = G.arc([(x, y, 0) for x, y in line])
    L = np.array(line)

    def at(v):
        d = np.sqrt(((L - np.array(v[:2])) ** 2).sum(1)); i = int(d.argmin())
        return (A[i], float(d[i]))

    # each trigger's place along the line, and (from its cell's data layers) the variants it serves
    import variants as V
    guid_of, layers, _g = V.assign(env)
    starts, ends = {}, {}
    for m in g['markers']:
        if m['name'] not in ('BC_StartSequenceTrigger_C', 'BC_EndSequenceTrigger_C'):
            continue
        cands = [c for c in (at(v) for v in m['vecs']) if c[1] < 40]
        if not cands:
            continue
        s = min(cands, key=lambda c: c[1])[0]
        for k, gid in guid_of.items():
            if gid in layers.get(m['cell'], ()):
                (starts if m['name'] == 'BC_StartSequenceTrigger_C' else ends)[k] = s
    out = {k: ('FORWARD' if ends[k] > starts[k] else 'REVERSE', starts[k], ends[k])
           for k in menu if k in starts and k in ends}
    missing = sorted(set(menu) - set(out))
    routes = []
    for key, (direction, s, e) in sorted(out.items()):
        # along the line in the driving direction; the clock stops RUNOUT_M before the end trigger
        fin = e - RUNOUT_M if direction == 'FORWARD' else e + RUNOUT_M
        lo, hi = min(s, fin), max(s, fin)
        idx = [i for i, a in enumerate(A) if lo <= a <= hi]
        pts = [line[i] for i in idx]
        if direction == 'REVERSE':
            pts = pts[::-1]
        pts = G_thin(pts, 5.0)
        short = ST.get('TRACK_%s_%s_SHORT' % (prefix, key))
        full_name = ST.get('TRACK_%s_%s' % (prefix, key))
        kind, d = key.split('_')
        sid = idpre + kind.capitalize() + d.capitalize()
        routes.append({'env': env, 'key': key, 'track': '%s %s' % (location, short), 'menuName': full_name,
                       'stageId': sid, 'stageIdConfirmed': sid in CONFIRMED_IDS, 'menuKm': menu.get(key),
                       'lengthM': round(sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))), 'startAt': s, 'endTriggerAt': e,
                       'points': [[round(x, 2), round(y, 2)] for x, y in pts]})
    return routes, {'missing': missing}


def G_thin(points, step):
    out, acc = [points[0]], 0.0
    for a, b in zip(points, points[1:]):
        acc += math.dist(a, b)
        if acc >= step:
            out.append(b); acc = 0.0
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


if __name__ == '__main__':
    allr = []
    for env in (sys.argv[1:] or ENVS):
        routes, info = build(env)
        print('==', env, info)
        for r in routes:
            print('  %-15s %-34s %-34s %5.2f km (menu %s)  id %s%s' % (r['key'], r['track'], r['menuName'], r['lengthM'] / 1000, r['menuKm'],
                                                                 r['stageId'], '' if r['stageIdConfirmed'] else ' (?)'))
        allr += routes
    json.dump(allr, open(os.path.join(SP, 'game_routes.json'), 'w', encoding='utf-8'), ensure_ascii=False)
