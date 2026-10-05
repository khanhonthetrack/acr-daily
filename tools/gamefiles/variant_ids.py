import sys, re, struct
sys.path.insert(0, sys.argv[1])
import zen
b = open(sys.argv[2], 'rb').read()
p = zen.parse(b)
nm = p['names']
ids = {i: n for i, n in enumerate(nm) if re.search(r'(Forward|Reverse)$', n) and re.match(r'(Alsace|Weles|Greece|MonteCarlo|Livigno)', n)}
# every row-name reference (FName index + number 0) and every string-table key in the data, in file order
events = []
for o in range(p['header_size'], len(b) - 8):
    i, n = struct.unpack_from('<II', b, o)
    if n == 0 and i in ids: events.append((o, 'ROW', ids[i]))
for m in re.finditer(rb'TRACK_[A-Z0-9_]+?(?:FORWARD|REVERSE)(?:_SHORT)?\x00', b):
    events.append((m.start(), 'KEY', m.group()[:-1].decode()))
events.sort()
row = None
pairs = {}
for o, kind, v in events:
    if kind == 'ROW': row = v
    elif row and not v.endswith('_SHORT') and row not in pairs: pairs[row] = v
for k in sorted(pairs): print(k, '->', pairs[k])

