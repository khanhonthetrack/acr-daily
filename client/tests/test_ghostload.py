"""Ghost cars with many drivers on the stage: the app's work a frame stays small (the grid of each run's line), the
game gets the nearest few only, and the files the app and the mod share are kept open and written in place."""
import math
import os
import random
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import ghostcars as gc  # noqa: E402

try:
    from acr_daily import ghostui
except Exception:          # (no display / not Windows)
    ghostui = None


def winding_run(n=4000, every_ms=50):
    """A long run along a winding road (n samples): [clockMs, x, y, z, heading, pitch, roll]."""
    s, x, z, h = [], 0.0, 0.0, 0.0
    for i in range(n):
        h += 0.02 * math.sin(i / 90.0)
        x -= math.sin(h) * 1.5
        z += math.cos(h) * 1.5
        s.append([i * every_ms, x, 0.0, z, h, 0.0, 0.0])
    return s


class WhereTheyPassed(unittest.TestCase):
    def test_the_grid_finds_what_a_whole_run_search_finds(self):
        s = winding_run()
        g = gc.GhostTrace({'samples': s})
        rnd = random.Random(3)
        for _ in range(200):
            k = rnd.randrange(len(s) - 1)
            x, z = s[k][1] + rnd.uniform(-15, 15), s[k][3] + rnd.uniform(-15, 15)
            g._hint = rnd.randrange(len(s))              # (as if last found somewhere else on the run)
            got = g.passed(x, z)
            i, d, kk = g._nearest(x, z, 0, len(s) - 1)    # the whole run, the slow way
            want = s[i][0] + (s[i + 1][0] - s[i][0]) * kk
            if d < 25.0:
                self.assertAlmostEqual(got, want, delta=1.0)

    def test_a_driver_behind_you_costs_no_whole_run_search(self):
        """They have not been where you are: the search looks near you only (it scanned all of their run each frame:
        3 ms a frame with 10 drivers)."""
        s = winding_run()
        g = gc.GhostTrace({'samples': s[:2000]})        # they are halfway; you are further on
        far = s[3500]
        looked = []
        nearest = g._nearest
        g._nearest = lambda x, z, lo, hi: (looked.append(max(1, hi - lo)), nearest(x, z, lo, hi))[1]
        for _ in range(5):
            g.passed(far[1], far[3])
        self.assertLess(sum(looked), 5 * 200)

    def test_a_live_driver_growing(self):
        s = winding_run(600)
        g = gc.GhostTrace({'samples': []})
        for row in s[:300]:
            g.s.append(tuple(row))
            g.ms.append(row[0])
        g.passed(s[100][1], s[100][3])
        for row in s[300:]:                               # (more samples come: the grid takes them in when asked)
            g.s.append(tuple(row))
            g.ms.append(row[0])
        g._hint = 0
        self.assertAlmostEqual(g.passed(s[500][1], s[500][3]), s[500][0], delta=60)


@unittest.skipIf(ghostui is None or os.name != 'nt', 'Windows only')
class TheGamesShare(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        ov = ghostui.GhostOverlay.__new__(ghostui.GhostOverlay)
        ov._ingame_path = lambda name: os.path.join(self.d, name)
        ov.root, ov.cfg = None, {'ingame': True}
        self.addCleanup(lambda: [getattr(ov, n).close() for n in ('_ghosts_fh', '_cam_fh') if getattr(ov, n, None)])
        self.ov = ov

    def test_the_nearest_ten_go_to_the_game(self):
        f = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
        cars = [('L%d' % i, (0.0, 0.0, 30.0 * (i + 1), 0, 0, 0), None, '', '', True, ('Car', None)) for i in range(15)]
        out = self.ov._real_cars(f, cars, {})
        self.assertEqual([c[0] for c in out], ['L%d' % i for i in range(10)])          # the nearest 10 of 15
        far = [(cid, (0.0, 0.0, 520.0, 0, 0, 0), *rest) for cid, p, *rest in cars[:1]]
        self.assertEqual([c[0] for c in self.ov._real_cars(f, far, {})], ['L0'])        # 520 m: still shown...
        self.assertEqual(self.ov._real_cars(f, [(c[0], (0.0, 0.0, 560.0, 0, 0, 0), *c[2:]) for c in far], {}), [])
        self.assertEqual(self.ov._real_cars(f, far, {}), [])                              # ...gone: back only by 500

    def test_the_ghosts_file_written_in_place(self):
        car = ('Skoda Fabia RS Rally2', None)
        reader = None
        try:
            self.ov._write_ingame([('L1', (1.0, 2.0, 3.0, 0.1, 0.0, 0.0), (5.0, 0.0, 0.0, 0.0, 0.0, 0.0), car),
                                   ('L2', (4.0, 2.0, 3.0, 0.1, 0.0, 0.0), None, car)], 100.0)
            reader = open(os.path.join(self.d, 'ingame-ghosts.txt'), newline='')   # (as the mod: opened once)
            first = reader.read().split('\n')
            self.assertEqual(first[0].split()[:3], ['ACRDG', '2', '1'])
            self.assertTrue(all(line.split()[-1] == '1' for line in first[1:3]))      # each line: the update's number
            self.assertEqual(len(first[1].split()), 15)
            self.assertEqual(first[3], 'end 1')
            self.ov._write_ingame([], 101.0)
            reader.seek(0)
            self.assertEqual(reader.read(), 'ACRDG 2 2 101.0000\nend 2\n')            # the same file, nothing left over
        finally:
            if reader:
                reader.close()

    def test_a_half_written_camera_is_skipped(self):
        path = os.path.join(self.d, 'ingame-camera.txt')
        with open(path, 'w') as fh:
            fh.write('CAM 7 100.00 200.00 300.00 -5.0 90.0 0.0 80.0 7'.ljust(159) + '\n')
        self.assertIsNotNone(self.ov._game_camera(1920, 1080))
        self.assertEqual(self.ov._cam_seq, 7)
        with open(path, 'r+') as fh:                    # (in place, as the mod writes it: the reader's file still open)
            fh.write('CAM 8 999.00 999.00 999.00 -5.0 90.0 0.0 80.0 7'.ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual(self.ov._cam_seq, 7)            # two numbers that differ: a half-written line, not taken
        with open(path, 'r+') as fh:
            fh.write('CAM 9 101.00 200.00 300.00 -5.0 90.0 0.0 80.0 9'.ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual(self.ov._cam_seq, 9)


if __name__ == '__main__':
    unittest.main()
