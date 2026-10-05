"""Stage geometry from a level's cells: centre splines (SplinesActor) and start / finish markers."""
import sys, os, re, glob, struct, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zen
import numpy as np

def exports(b):
    """[(name, bytes, top actor name)] - each export with the name of the actor it belongs to."""
    p = zen.parse(b)
    ex = p['exports']
    def parent(e):
        o = e['outer']
        return ex[o] if (o >> 62) == 0 and o < len(ex) else None
    def actor(e):
        seen = 0
        while seen < 20:
            q = parent(e)
            if q is None or q['name'] == 'PersistentLevel': return e['name']
            e = q; seen += 1
        return e['name']
    pos = p['header_size']; out = []
    for e in sorted(ex, key=lambda e: e['serial']):
        out.append((e['name'], b[pos:pos + e['size']], actor(e))); pos += e['size']
    return out

def vectors(d):
    vec = {}
    for o in range(0, len(d) - 24):
        x, y, z = struct.unpack_from('<3d', d, o)
        if all(math.isfinite(v) for v in (x, y, z)) and 100 < max(abs(x), abs(y)) < 2e6 and abs(z) < 2e6:
            vec[o] = (x / 100, y / 100, z / 100)
    return vec

def spline_points(d, S=79):
    """The main point chain of a spline export: keys 0, 1, 2 ... (InVal float just before each position)."""
    vec = vectors(d)
    best = []
    for o in sorted(vec):
        if abs(struct.unpack_from('<f', d, o - 4)[0]) > 1e-6 if o >= 4 else True: continue
        ch = [o]
        while ch[-1] + S in vec and abs(struct.unpack_from('<f', d, ch[-1] + S - 4)[0] - len(ch)) < 1e-3:
            ch.append(ch[-1] + S)
        if len(ch) > len(best): best = ch
    return [vec[o] for o in best]

def densify(pts, step=5.0):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L // step))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t))
    return out

def arc(pts):
    c = [0.0]
    for a, b in zip(pts, pts[1:]): c.append(c[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return c

MARKER = re.compile(r'^(BC_EndSequenceTrigger_C|BC_StartSequenceTrigger_C|BC_CompleStartTargetPoint_C|BC_StopMarshalEndSequence_C|BC_StopMarshalStartSequence_C|MarshalEndSequence|MarshalStartSequence|StartTrigger1|Start$|SplineTrigger|PacenoteSetupActor)')

def scan(env_dir):
    splines, markers = [], []
    for path in sorted(glob.glob(os.path.join(env_dir, '*.umap'))):
        cell = os.path.basename(path)[:8]
        by_actor = {}
        for name, d, act in exports(open(path, 'rb').read()):
            if name in ('CenterSpline', 'IdealSpline'):
                pts = spline_points(d)
                if len(pts) > 10:
                    splines.append({'cell': cell, 'kind': name, 'pts': pts})
            elif MARKER.match(act):
                by_actor.setdefault(act, []).extend(vectors(d).values())
        for act, vs in by_actor.items():
            markers.append({'cell': cell, 'name': re.sub(r'_UAID_.*$', '', act), 'vecs': vs})
    return splines, markers

if __name__ == '__main__':
    env_dir = sys.argv[1]
    splines, markers = scan(env_dir)
    centres = [s for s in splines if s['kind'] == 'CenterSpline']
    for s in centres:
        a = arc(s['pts'])
        print('centre', s['cell'], 'points', len(s['pts']), 'length %.0f' % a[-1], 'from (%.0f,%.0f) to (%.0f,%.0f)' % (s['pts'][0][0], s['pts'][0][1], s['pts'][-1][0], s['pts'][-1][1]))
    if centres:
        ref = densify(centres[0]['pts']); A = arc(ref); R = np.array([[p[0], p[1]] for p in ref])
        for m in markers:
            best = None
            for v in m['vecs']:
                d = np.sqrt(((R - np.array(v[:2])) ** 2).sum(1)); i = int(d.argmin())
                if d[i] < 40 and (best is None or d[i] < best[0]):
                    best = (float(d[i]), A[i], v)
            if best:
                print('  %-8s %-34s at %6.0f m along %s (off by %.1f m)  (%.0f, %.0f)' % (m['cell'], m['name'][:34], best[1], centres[0]['cell'], best[0], best[2][0], best[2][1]))
    json.dump({'splines': splines, 'markers': [{'cell': m['cell'], 'name': m['name'], 'vecs': m['vecs'][:400]} for m in markers]},
              open(os.path.join(env_dir, 'geometry.json'), 'w'))

