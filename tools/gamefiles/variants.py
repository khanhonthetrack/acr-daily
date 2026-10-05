"""Which start / end trigger belongs to which stage variant: the world partition cell of each trigger carries the
variant's data layers; each variant's PacenoteSetupActor (label "Pacenote_FullForward", "Pacenote_Cut1_Reverse")
tells which data layer is which variant."""
import json, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zen, iostore
import geometry as G
import build_routes as B

SP = B.SP


def persistent(env):
    path = os.path.join(SP, 'ext', env + '.umap')
    if not os.path.exists(path):
        t, f, i = [x for x in iostore.find('Levels/%s.umap' % env) if x[1].endswith('Levels/%s.umap' % env)][0]
        t.extract_index(i, path)
    return open(path, 'rb').read()


def cell_layers(env):
    """{cell 8-char prefix: set of DataLayer GUID names}"""
    b = persistent(env)
    p = zen.parse(b)
    nm = p['names']
    pos = p['header_size']; out = {}
    for e in sorted(p['exports'], key=lambda e: e['serial']):
        d = b[pos:pos + e['size']]; pos += e['size']
        if re.fullmatch(r'[0-9A-Z]{25}', e['name']):
            ls = set()
            for o in range(0, len(d) - 7):
                i, n = struct.unpack_from('<II', d, o)
                if i < len(nm) and n == 0 and nm[i].startswith('DataLayer_'):
                    ls.add(nm[i])
            out[e['name'][:8]] = ls
    return out


def variant_key(label, kinds):
    """'Pacenote_Cut1_Reverse' -> 'SHORT1_REVERSE' or 'CUT1_REVERSE' (whatever the env's string table uses)."""
    m = re.search(r'(Full|Cut(\d)|Short(\d))_?(Forward|Reverse)', label)
    if m:
        n, d = m.group(2) or m.group(3), m.group(4).upper()
    else:   # Wales: "PacenoteSetupActorForwardCut1", "PacenoteSetupActorReverse" (= full)
        m = re.search(r'(Forward|Reverse)(?:Cut(\d)|Short(\d))?$', label)
        if not m:
            return None
        n, d = m.group(2) or m.group(3), m.group(1).upper()
    if not n:
        return 'FULL_' + d
    for k in kinds:
        if re.fullmatch(r'(CUT|SHORT)%s_%s' % (n, d), k):
            return k
    return None


def assign(env):
    prefix, location, idpre, menu = B.ENVS[env]
    layers = cell_layers(env)
    g = json.load(open(os.path.join(SP, 'ext', env, 'geometry.json')))
    guid_of = {}
    for m in g['markers']:
        if m['name'] != 'PacenoteSetupActor':
            continue
        b = B.cell_bytes(env, m['cell'])
        labels = set()
        for name, d, act in G.exports(b):
            if act.startswith('PacenoteSetupActor'):
                labels.update(x.decode() for x in re.findall(rb'Pacenote[A-Za-z0-9_]+', d))
        for lab in labels:
            k = variant_key(lab, menu)
            if k and len(layers.get(m['cell'], ())) == 1:
                guid_of[k] = next(iter(layers[m['cell']]))
    return guid_of, layers, g


if __name__ == '__main__':
    for env in (sys.argv[1:] or B.ENVS):
        guid_of, layers, g = assign(env)
        print('==', env, {k: v[10:18] for k, v in guid_of.items()})
        for m in g['markers']:
            if m['name'] in ('BC_StartSequenceTrigger_C', 'BC_EndSequenceTrigger_C'):
                vs = sorted(k for k, gid in guid_of.items() if gid in layers.get(m['cell'], ()))
                print('   ', m['cell'], m['name'][3:8], vs)
