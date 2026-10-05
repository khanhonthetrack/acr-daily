import sys, os, json, math
import numpy as np
sys.path.insert(0, r'D:\ACR-Daily\client'); sys.path.insert(0, r'D:\ACR-Daily\client\tests')
os.environ['ACR_DAILY_RECORDINGS'] = r'D:\DLR-Stream'
from acr_daily.judge import Judge
from acr_daily.telemetry import Frame, Replay
import test_judge as T
gen = {r['track']: r for r in json.load(open('game_routes.json', encoding='utf-8'))}
def dev(a, b):
    A, B = np.array(a), np.array(b)
    d = np.sqrt(((A[:, None] - B[None]) ** 2).sum(-1)).min(1)
    return d
print('--- generated vs recorded routes')
for n in ('Alsace Forêt', 'Alsace Obersteigen', 'Wales Afon Bidno'):
    rec = json.load(open(r'D:\ACR-Daily\routes\%s.json' % n, encoding='utf-8'))['points']
    g = gen[n]['points']
    d = dev(rec, g)
    print('%-20s start %.1f m apart, end %.1f m apart, length %d vs %d m; recorded points from the generated line: median %.1f, 95%% %.1f, max %.1f m' % (
        n, math.dist(rec[0], g[0]), math.dist(rec[-1], g[-1]), gen[n]['lengthM'],
        sum(math.dist(a, b) for a, b in zip(rec, rec[1:])), np.median(d), np.percentile(d, 95), d.max()))
def judge_run(track, car, frames):
    ch = {'id': 'x', 'track': track, 'car': car, 'route': gen[track]['points'], 'penaltyMs': 60000}
    j = Judge(ch); t = [0.0]; j.now = lambda: t[0]; res = []
    for f in frames:
        t[0] = f.t
        for e in j.feed(f):
            if e in ('finished', 'dnf', 'invalid'): res.append((e, j.result['clockMs'], j.result['resets'], j.result['checkpoints'], j.result['reason']))
    return res
print('--- judge with generated routes')
raw = T.raw_frames()
print('Obersteigen runs:', judge_run('Alsace Obersteigen', 'Peugeot 208 Rally4', raw))
print('Foret (raw log):', judge_run('Alsace Forêt', 'Peugeot 208 Rally4', raw))
fr = Replay(T.DUMP).frames
print('Wales dump:', judge_run('Wales Afon Bidno', fr[-1].car or 'Mini Cooper S 1275', fr))
runs = json.load(open('runs.json', encoding='utf-8-sig'))[0]['results'] if os.path.exists('runs.json') else []   # optional: a D1 export of runs with traces
for r in runs:
    tr = json.loads(r['trace'])
    frames = [Frame(-1.0, 0, 0, tr[0][1], tr[0][2], 0, 'C', 'Alsace Forêt', gear=2)] + [Frame(s[5] / 1000, i + 1, max(1, s[0]), s[1], s[2], s[3], 'C', 'Alsace Forêt', s[6], s[7], s[8], s[9], s[10], s[11]) for i, s in enumerate(tr)]
    last = frames[-1]
    frames += [Frame(last.t + k * .05, 99999 + k, last.clock_ms, last.x + k * 0.3, last.z, 20, 'C', 'Alsace Forêt') for k in range(1, 40)]
    print('today', r['name'], judge_run('Alsace Forêt', 'C', frames), 'actual clock', r['clock_ms'])
