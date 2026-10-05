import sys, os
sys.path.insert(0, sys.argv[1])
import iostore
env = sys.argv[2]
out = os.path.join(sys.argv[1], 'ext', env); os.makedirs(out, exist_ok=True)
n = 0
for t, f, i in iostore.find('Levels/%s/_Generated_/' % env):
    p = os.path.join(out, os.path.basename(f))
    if not os.path.exists(p): t.extract_index(i, p)
    n += 1
print(env, 'cells', n)
