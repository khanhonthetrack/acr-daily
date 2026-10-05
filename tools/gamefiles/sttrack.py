import struct, re, sys, json
b = open(sys.argv[1], 'rb').read()
def fstr(o):
    n = struct.unpack_from('<i', b, o)[0]
    if 0 < n < 2000:
        return b[o + 4:o + 4 + n - 1].decode('latin-1'), o + 4 + n
    if -2000 < n < 0:
        return b[o + 4:o + 4 - 2 * n - 2].decode('utf-16-le'), o + 4 - 2 * n
    return None, o
table = {}
for m in re.finditer(rb'(TRACK_[A-Z0-9_]+|RALLY_[A-Z_]+|SURFACE_[A-Z]+)\x00', b):
    o = m.start() - 4
    k, e = fstr(o)
    if k and k == m.group(1).decode():
        v, _ = fstr(e)
        table[k] = v
json.dump(table, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for k, v in table.items():
    if k.endswith('_SHORT') or k.startswith('TRACK_LOCATION') and not k.endswith('_DESC'):
        print(k, '=', v)
