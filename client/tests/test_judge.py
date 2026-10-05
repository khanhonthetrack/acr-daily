"""Judge tests on real recorded data.

  python -m unittest discover -s tests      (from the client folder)

Uses telemetry recordings from the folder in ACR_DAILY_RECORDINGS when they exist (skipped otherwise):
  tools\\shm-dump.jsonl  Wales Afon Bidno, Mini: one reset, finish at 4:13.870
  logs\\acr-raw.log      a 5 Hz log: three Alsace runs + one run joined half way
"""
import json
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acr_daily.judge import Judge, fmt_ms  # noqa: E402
from acr_daily.route import thin  # noqa: E402
from acr_daily.telemetry import Frame, Replay, parse_clock  # noqa: E402

DLR = os.environ.get('ACR_DAILY_RECORDINGS', '')
DUMP = os.path.join(DLR, 'tools', 'shm-dump.jsonl')
RAW = os.path.join(DLR, 'logs', 'acr-raw.log')


def run(judge, frames):
    t = [0.0]
    judge.now = lambda: t[0]
    events = []
    for f in frames:
        t[0] = f.t
        for e in judge.feed(f):
            events.append((round(f.t, 1), e, judge.total_ms))
    return events


def raw_frames():
    out = []
    pat = re.compile(r'^(\d\d):(\d\d):(\d\d\.\d+) .*?pos=(-?[\d.]+),(-?[\d.]+),(-?[\d.]+) v=([\d.]+) g=(-?\d+) '
                     r'rpm=(\d+)/\d+/\d+ thr=([\d.]+) brk=([\d.]+) .*?'
                     r'pkt=(\d+)/(\d+) str="([^"]*)" car="([^"]*)" track="([^"]*)"')
    with open(RAW, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = pat.match(line)
            if m:
                h, mi, s, x, _y, z, v, g, rpm, thr, brk, ppkt, gpkt, clock, car, track = m.groups()
                out.append(Frame(int(h) * 3600 + int(mi) * 60 + float(s), int(gpkt), parse_clock(clock),
                                 float(x), float(z), float(v), car, track,
                                 int(ppkt), float(thr), float(brk), 0.0, int(g), int(rpm)))
    return out


def dlr_route(track):
    with open(os.path.join(DLR, 'rally', 'stages.json'), encoding='utf-8') as fh:
        st = next(s for s in json.load(fh) if s['track'] == track)
    for name in os.listdir(os.path.join(DLR, 'rally')):
        if name.startswith('trace-'):
            with open(os.path.join(DLR, 'rally', name), encoding='utf-8') as fh:
                pts = [(p['x'], p['z']) for p in json.load(fh)]
            if math.dist(pts[0], (st['startX'], st['startZ'])) < 40:
                return thin(pts)
    raise LookupError(track)


class Synthetic(unittest.TestCase):
    """A straight 2 km road, driven at 100 km/h, sampled at 20 Hz."""
    ROUTE = [[i * 5.0, 0.0] for i in range(401)]
    CH = {'id': 't', 'track': 'Test Stage', 'car': 'Test Car', 'route': ROUTE, 'penaltyMs': 60000}

    def drive(self, jump_at=None, restart_at=None, shortcut=False, stop_at=None):
        frames, t, clock, x, pkt = [], 0.0, 0, 0.0, 1
        for _ in range(20):                       # on the start line
            frames.append(Frame(t, pkt, 0, x, 0.0, 0.0, 'Test Car', 'Test Stage')); t += .05; pkt += 1
        v = 100 / 3.6
        while x < 2000:
            t += .05; pkt += 1; clock += 50; x += v * .05
            if jump_at and x >= jump_at:
                x -= 60                            # reset: put back 60 m (once)
                jump_at = None
            if shortcut and 700 < x < 1300:
                x = 1300.0
            if restart_at and x >= restart_at:
                frames.append(Frame(t, pkt, 0, 0.0, 0.0, 0.0, 'Test Car', 'Test Stage'))
                return frames
            if stop_at and x >= stop_at:
                for _ in range(int(35 / .05)):
                    t += .05; pkt += 1
                    frames.append(Frame(t, pkt, clock, x, 0.0, 0.0, 'Test Car', 'Test Stage'))
                return frames
            frames.append(Frame(t, pkt, clock, x, 0.0, 100.0, 'Test Car', 'Test Stage'))
        for _ in range(40):                        # past the line: clock frozen, car rolls on
            t += .05; pkt += 1; x += 5 * .05
            frames.append(Frame(t, pkt, clock, x, 0.0, 20.0, 'Test Car', 'Test Stage'))
        return frames

    def test_clean_finish(self):
        j = Judge(self.CH)
        ev = run(j, self.drive())
        self.assertEqual([e[1] for e in ev], ['start', 'split', 'split', 'split', 'finished'])
        self.assertEqual(j.result['resets'], 0)
        self.assertEqual(j.result['totalMs'], j.result['clockMs'])
        self.assertAlmostEqual(j.result['clockMs'] / 1000, 2000 / (100 / 3.6), delta=0.2)

    def test_reset_costs_60s(self):
        j = Judge(self.CH)
        ev = run(j, self.drive(jump_at=800))
        self.assertEqual([e[1] for e in ev], ['start', 'split', 'reset', 'split', 'split', 'finished'])
        self.assertEqual(j.result['totalMs'], j.result['clockMs'] + 60000)

    def test_restart_is_dnf(self):
        j = Judge(self.CH)
        run(j, self.drive(restart_at=900))
        self.assertEqual(j.state, 'dnf')
        self.assertIn('restart', j.result['reason'])

    def test_stopping_is_dnf(self):
        j = Judge(self.CH)
        run(j, self.drive(stop_at=900))
        self.assertEqual(j.state, 'dnf')

    def test_shortcut_is_invalid(self):
        j = Judge(self.CH)
        run(j, self.drive(shortcut=True))
        self.assertEqual(j.state, 'invalid')

    def test_wrong_car_never_starts(self):
        j = Judge(dict(self.CH, car='Other Car'))
        ev = run(j, self.drive())
        self.assertEqual(ev, [])
        self.assertIn('Not today', j.message)

    def test_ghost_gap(self):
        ref = Judge(self.CH)
        run(ref, self.drive())
        j = Judge(self.CH)
        j.set_ghost(ref.result['trace'])
        frames = self.drive(jump_at=800)
        run(j, frames[:int(len(frames) * .8)])  # stop at ~80 %, after the reset
        self.assertEqual(j.state, 'running')
        self.assertGreater(j.gap_ms, 55000)        # 60 s penalty, minus the 60 m given back... roughly
        self.assertLess(j.gap_ms, 70000)


@unittest.skipUnless(os.path.exists(DUMP), 'no shm dump')
class RecordedDump(unittest.TestCase):
    def test_wales_reset_and_finish(self):
        frames = Replay(DUMP).frames
        on = [f for f in frames if f.clock_ms > 0]
        # reference route = this run's own path without the reset jump (circular, but checks the state machine)
        pts, prev = [], None
        for f in on:
            if prev is None or math.dist((prev.x, prev.z), (f.x, f.z)) < 15:
                pts.append((f.x, f.z))
            prev = f
        ch = {'id': 'w', 'track': frames[-1].track or on[0].track, 'car': on[0].car, 'route': thin(pts), 'penaltyMs': 60000}
        self.assertEqual((ch['track'], ch['car']), ('Wales Afon Bidno', 'Mini Cooper S 1275'))
        j = Judge(ch)
        ev = run(j, frames)
        print('\n  wales events:', ev, '\n ', j.message)
        self.assertEqual([e[1] for e in ev], ['start', 'split', 'reset', 'split', 'split', 'finished'])
        sp = j.result['splits']
        self.assertEqual(len(sp), 3)
        self.assertTrue(sp[0] < sp[1] < sp[2] < j.result['totalMs'])
        self.assertGreater(sp[1] - sp[0], 60000)   # the reset between split 1 and 2 adds its +60 s
        self.assertEqual(j.result['clockMs'], 253870)
        self.assertEqual(j.result['totalMs'], 313870)
        self.assertEqual(fmt_ms(j.result['totalMs']), '5:13.870')


@unittest.skipUnless(os.path.exists(RAW), 'no raw log')
class CompanionRawLog(unittest.TestCase):
    def judge_for(self, track):
        return Judge({'id': 'x', 'track': track, 'car': 'Peugeot 208 Rally4', 'route': dlr_route(track), 'penaltyMs': 60000})

    def test_obersteigen_two_runs(self):
        j = self.judge_for('Alsace Obersteigen')
        results = []
        t = [0.0]
        j.now = lambda: t[0]
        for f in raw_frames():
            t[0] = f.t
            if j.feed(f) and j.state in ('finished', 'dnf', 'invalid'):
                results.append((j.state, j.result['clockMs'], j.result['resets'], j.result['checkpoints']))
        print('\n  obersteigen:', results)
        self.assertEqual([(r[0], r[1]) for r in results], [('finished', 162300), ('finished', 153634)])

    def test_foret(self):
        j = self.judge_for('Alsace Forêt')
        results = []
        t = [0.0]
        j.now = lambda: t[0]
        for f in raw_frames():
            t[0] = f.t
            if j.feed(f) and j.state in ('finished', 'dnf', 'invalid'):
                results.append((j.state, j.result['clockMs'], j.result['resets'], j.result['checkpoints']))
        print('\n  foret:', results)
        self.assertEqual([(r[0], r[1]) for r in results], [('finished', 368568)])

    def test_joined_mid_run_not_counted(self):
        j = Judge({'id': 'x', 'track': 'Wales Afon Bidno', 'car': 'Mini Cooper S 1275',
                   'route': [[0, 0], [5000, 0]], 'penaltyMs': 60000})
        t = [0.0]
        j.now = lambda: t[0]
        ev = []
        for f in raw_frames():
            t[0] = f.t
            ev += j.feed(f)
        self.assertNotIn('start', ev)


if __name__ == '__main__':
    unittest.main()
