"""UE5.4 zen package (IoStore .umap/.uasset) header: name map + export map."""
import struct, sys
def names_batch(b, o):
    n, nbytes = struct.unpack_from('<II', b, o); o += 8
    if n == 0: return [], o
    o += 8                      # hash version
    o += 8 * n                  # hashes
    hdrs = [struct.unpack_from('>H', b, o + 2 * i)[0] for i in range(n)]; o += 2 * n
    out = []
    for h in hdrs:
        wide, ln = h & 0x8000, h & 0x7fff
        if wide:
            if o % 2: o += 1
            out.append(b[o:o + 2 * ln].decode('utf-16-le')); o += 2 * ln
        else:
            out.append(b[o:o + ln].decode('latin-1')); o += ln
    return out, o
def parse(b):
    f = struct.unpack_from('<15I', b, 0)
    has_ver, header_size, cooked_header_size, exp_map = f[0], f[1], f[5], f[8]
    exp_end = min(v for v in f[6:15] if v > exp_map)
    o = 60
    if has_ver:
        raise ValueError('versioned zen package not handled')
    names, o = names_batch(b, o)
    nexp = (exp_end - exp_map) // 72
    exports = []
    for i in range(nexp):
        e = exp_map + 72 * i
        off, size, ni, nn, outer, cls, sup, tmpl, pubhash, oflags, filt = struct.unpack_from('<QQIIQQQQQIB', b, e)
        nm = names[ni & 0x3fffffff] if (ni & 0x3fffffff) < len(names) else '?%d' % ni
        exports.append({'i': i, 'name': nm + ('_%d' % (nn - 1) if nn else ''), 'serial': off, 'size': size, 'outer': outer,
                        'cls': cls, 'pos': header_size + (off - cooked_header_size)})
    return {'header_size': header_size, 'cooked_header_size': cooked_header_size, 'names': names, 'exports': exports}
if __name__ == '__main__':
    b = open(sys.argv[1], 'rb').read()
    p = parse(b)
    print('names', len(p['names']), 'exports', len(p['exports']), 'header', p['header_size'])
    ex = sorted(p['exports'], key=lambda e: e['pos'])
    for target in [int(x) for x in sys.argv[2:]]:
        hit = [e for e in ex if e['pos'] <= target < e['pos'] + e['size']]
        print(target, '->', [(e['i'], e['name'], e['size']) for e in hit])
    import collections, re
    kinds = collections.Counter(re.sub(r'_\d+$', '', e['name']) for e in p['exports'])
    for k, c in kinds.most_common(400):
        if re.search(r'(?i)spline|pacenote|route|stage|start|finish|split|checkpoint|track|marshal|path', k):
            print(c, k)
