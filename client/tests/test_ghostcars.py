"""Ghost cars (a test): the camera maths, the recorder, and the whole thing on a real recorded run."""
import math
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import ghostcars as gc, settings  # noqa: E402
from acr_daily.telemetry import Frame, Replay  # noqa: E402
from tests.test_judge import DUMP  # noqa: E402

W, H = 1920, 1080


def frame(t, clock, x=0.0, z=0.0, y=0.0, h=0.0, speed=80.0, track='Test Stage'):
    return Frame(t, int(t * 60), clock, x, z, speed, 'Car', track, y=y, heading=h)


class Maths(unittest.TestCase):
    def test_basis(self):
        f, r, u = gc.basis(0.0)
        self.assertEqual((round(f[0], 6), f[1], f[2]), (0, 0.0, 1.0))      # heading 0: along +z
        self.assertAlmostEqual(r[0], -1.0)                                   # right: -x
        for h, p, rl in ((0.3, 0.1, -0.2), (-2.5, -0.15, 0.3)):
            f, r, u = gc.basis(h, p, rl)
            for a, b in ((f, r), (f, u), (r, u)):
                self.assertAlmostEqual(gc.dot(a, b), 0.0, places=9)
            for a in (f, r, u):
                self.assertAlmostEqual(gc.dot(a, a), 1.0, places=9)
            self.assertAlmostEqual(f[1], math.sin(p), places=9)             # nose up: forward points up
        f, r, u = gc.basis(0.0, 0.0, 0.2)
        self.assertGreater(r[1], 0)                                          # roll > 0: right side up

    def test_project(self):
        cam = gc.camera_for((0, 0, 0, 0.0, 0, 0), dict(gc.VIEWS['bonnet'], up=0.0, fwd=0.0, tilt=0.0), W, H)
        x, y = cam.project((0, 0, 50))
        self.assertAlmostEqual(x, W / 2)
        self.assertAlmostEqual(y, H / 2)
        f, r, u = gc.basis(0.0)
        x, _ = cam.project(gc.add(gc.mul(f, 50), gc.mul(r, 5)))
        self.assertGreater(x, W / 2)                                         # to the right: right half
        _, y = cam.project((0, 3, 50))
        self.assertLess(y, H / 2)                                            # above: upper half
        self.assertIsNone(cam.project((0, 0, -5)))                           # behind
        # the field of view: a point on its edge lands on the screen's edge
        fov = math.radians(gc.VIEWS['bonnet']['fov'])
        x, _ = cam.project(gc.add(gc.mul(f, 10), gc.mul(r, 10 * math.tan(fov / 2))))
        self.assertAlmostEqual(x, W, places=6)
        cam.mirror = True
        x, _ = cam.project(gc.add(gc.mul(f, 50), gc.mul(r, 5)))
        self.assertLess(x, W / 2)

    def test_tilt(self):
        cam = gc.camera_for((0, 0, 0, 0.0, 0, 0), dict(gc.VIEWS['bonnet'], up=0.0, fwd=0.0, tilt=-10), W, H)
        _, y = cam.project((0, 0, 50))
        self.assertLess(y, H / 2)            # looking down: the road ahead moves up the screen

    def test_wide_screen_shows_more_at_the_sides(self):
        """The view keeps its height: 3440 x 1440 shows what 2560 x 1440 does, plus more at each side."""
        cfg = dict(gc.VIEWS['bonnet'], up=0.0, fwd=0.0, tilt=0.0)
        wide = gc.camera_for((0, 0, 0, 0.0, 0, 0), cfg, 3440, 1440)
        normal = gc.camera_for((0, 0, 0, 0.0, 0, 0), cfg, 2560, 1440)
        f, r, u = gc.basis(0.0)
        p = gc.add(gc.add(gc.mul(f, 40), gc.mul(r, 9)), gc.mul(u, -2))
        (xw, yw), (xn, yn) = wide.project(p), normal.project(p)
        self.assertAlmostEqual(xw - 3440 / 2, xn - 2560 / 2, places=6)
        self.assertAlmostEqual(yw, yn, places=6)
        across = 2 * math.degrees(math.atan((3440 / 2) / wide.focal))
        self.assertAlmostEqual(across, 91.2, delta=1.0)       # what the game showed on 3440 x 1440 (fitted to ~1 degree)

    def test_box(self):
        c = gc.box_corners((10, 2, 5, 0.7, 0, 0))
        self.assertEqual(len(c), 8)
        self.assertAlmostEqual(math.dist(c[0], c[3]), gc.CAR_BOX[0])   # front left to rear left: the length
        self.assertAlmostEqual(math.dist(c[0], c[1]), gc.CAR_BOX[1])   # front left to front right: the width

    def test_sight(self):
        straight = [(0, 0, z) for z in range(0, 201, 5)]
        self.assertTrue(gc.in_sight((0, 1, 0), (0, 0, 200), straight))
        # a right angle: the straight line cuts the corner, far from the road
        corner = [(0, 0, z) for z in range(0, 101, 5)] + [(-x, 0, 100) for x in range(5, 101, 5)]
        self.assertFalse(gc.in_sight((0, 1, 0), (-100, 0, 100), corner))
        self.assertTrue(gc.in_sight((0, 1, 0), (-8, 0, 100), corner))
        # a crest: the road rises 6 m between you and the ghost
        crest = [(0, 6 * math.sin(math.pi * z / 200), z) for z in range(0, 201, 5)]
        self.assertFalse(gc.in_sight((0, 1, 0), (0, 0, 200), crest))


class Recorder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._was = settings.DIR
        settings.DIR = self.dir

    def tearDown(self):
        settings.DIR = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def drive(self, rec, seconds, t0=0.0, clock0=0, finish=True):
        """Start line, then `seconds` of driving along +z at 20 m/s, then (finish) the clock stops while rolling on."""
        rec.feed(frame(t0, 0), t0)
        rec.feed(frame(t0 + 0.02, 0), t0 + 0.02)
        t = t0
        for i in range(1, int(seconds * 60)):
            t = t0 + 0.05 + i / 60
            ms = clock0 + int(i * 1000 / 60)
            rec.feed(frame(t, ms, z=20 * ms / 1000), t)
        if finish:
            for k in range(1, 80):        # rolls on with the clock stopped
                rec.feed(frame(t + k / 60, ms, z=20 * ms / 1000 + k * 0.3), t + k / 60)
        return ms

    def test_finished_run_saved(self):
        rec = gc.GhostRecorder()
        end = self.drive(rec, 15)
        runs = gc.list_runs('Test Stage')
        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0]['finished'])
        self.assertEqual(runs[0]['clockMs'], end)
        g = gc.load_run(runs[0])
        self.assertAlmostEqual(g.at(10000)[2], 200.0, delta=0.5)
        self.assertAlmostEqual(g.passed(0.0, 100.0), 5000, delta=20)
        gaps = [b - a for a, b in zip(g.ms, g.ms[1:])]
        self.assertTrue(all(g >= gc.SAMPLE_MS for g in gaps))

    def test_restart_keeps_the_unfinished_run(self):
        now = [1.8e9]
        rec = gc.GhostRecorder(wall=lambda: now[0])
        self.drive(rec, 12, finish=False)
        now[0] += 60
        self.drive(rec, 15, t0=100.0)            # the clock back to 0: a restart, then a run to the finish
        runs = gc.list_runs('Test Stage')
        self.assertEqual([r['finished'] for r in runs], [True, False])
        self.assertTrue(gc.pick_run('Test Stage', 'last')['finished'])
        self.assertTrue(gc.pick_run('Test Stage', 'best')['finished'])

    def test_last_run_is_the_last_finished_one(self):
        """A newer run you restarted or crashed out of is not the ghost while a finished one is there."""
        os.makedirs(gc.stage_dir('Test Stage'))
        for name in ('1000_191713_F.json', '2000_62613_U.json', '3000_36089_U.json'):
            open(os.path.join(gc.stage_dir('Test Stage'), name), 'w').close()
        self.assertEqual(gc.pick_run('Test Stage', 'last')['startedAt'], 1000)
        self.assertEqual(gc.pick_run('Test Stage', 'best')['startedAt'], 1000)
        os.remove(os.path.join(gc.stage_dir('Test Stage'), '1000_191713_F.json'))
        self.assertEqual(gc.pick_run('Test Stage', 'last')['startedAt'], 3000)    # none finished: the newest

    def test_short_run_not_kept(self):
        rec = gc.GhostRecorder()
        self.drive(rec, 5)
        self.assertEqual(gc.list_runs('Test Stage'), [])

    def test_pause_is_not_a_finish(self):
        rec = gc.GhostRecorder()
        ms = self.drive(rec, 12, finish=False)
        for k in range(1, 200):                  # paused: clock and car both stand still
            rec.feed(frame(100 + k / 60, ms, z=20 * ms / 1000), 100 + k / 60)
        self.assertEqual(rec.state, 'recording')
        self.assertEqual(gc.list_runs('Test Stage'), [])


@unittest.skipUnless(os.path.exists(DUMP), 'no shm dump')
class RealRun(unittest.TestCase):
    """The recorded Wales run (Mini): record it as a ghost, play it back, and point the camera along it."""

    @classmethod
    def setUpClass(cls):
        cls.frames = [f for f in Replay(DUMP).frames]
        cls.dir = tempfile.mkdtemp()
        cls._was = settings.DIR
        settings.DIR = cls.dir
        rec = gc.GhostRecorder()
        for f in cls.frames:
            rec.feed(f, f.t)
        rec.feed(None, cls.frames[-1].t + 1)
        rec.feed(None, cls.frames[-1].t + 10)
        cls.runs = gc.list_runs(cls.frames[-1].track)
        cls.ghost = gc.load_run(cls.runs[0]) if cls.runs else None

    @classmethod
    def tearDownClass(cls):
        settings.DIR = cls._was
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_recorded(self):
        print('\n  runs:', [(r['clockMs'], r['finished']) for r in self.runs])
        self.assertTrue(self.runs)
        self.assertTrue(self.runs[0]['finished'])
        self.assertAlmostEqual(self.runs[0]['clockMs'], 253870, delta=100)   # 4:13.870

    def test_playback_follows_the_run(self):
        g, errs, clock_errs = self.ghost, [], []
        running = [f for f in self.frames if 0 < f.clock_ms < g.end_ms]
        for f in running[::25]:
            p = g.at(f.clock_ms)
            errs.append(math.dist(p[:3], (f.x, f.y, f.z)))
        g._hint = 0
        for f in running[::25]:
            clock_errs.append(abs(g.passed(f.x, f.z) - f.clock_ms))
        errs.sort()
        clock_errs.sort()
        print('\n  position error: median %.2f m, 95%% %.2f m; time at a place: median %d ms, 95%% %d ms' % (
            errs[len(errs) // 2], errs[int(len(errs) * .95)], clock_errs[len(clock_errs) // 2],
            clock_errs[int(len(clock_errs) * .95)]))
        self.assertLess(errs[int(len(errs) * .95)], 1.5)
        self.assertLess(clock_errs[int(len(clock_errs) * .95)], 150)

    def test_road_ahead_is_in_front(self):
        """Where the car is 1.5 s later is in front of the bonnet camera and on the screen, and on the side it turns to."""
        g = self.ghost
        cfg = dict(gc.VIEWS['bonnet'])
        on_screen = sides = turning = 0
        n = 0
        for f in [f for f in self.frames if 2000 < f.clock_ms < g.end_ms - 2000 and f.speed > 40][::10]:
            cam = gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), cfg, W, H)
            ahead = g.at(f.clock_ms + 1500)
            pt = cam.project(ahead[:3])
            n += 1
            if pt and 0 <= pt[0] <= W and 0 <= pt[1] <= H:
                on_screen += 1
            turn = (ahead[3] - f.heading + math.pi) % (2 * math.pi) - math.pi
            if pt and abs(turn) > 0.3:          # heading going up = turning right (ghostcars.basis)
                turning += 1
                sides += (pt[0] > W / 2) == (turn > 0)
        print('\n  1.5 s ahead on screen: %d / %d; on the side of the turn: %d / %d' % (on_screen, n, sides, turning))
        self.assertGreater(on_screen / n, 0.9)
        self.assertGreater(sides / max(1, turning), 0.9)

    def test_ghost_line_sits_low_on_the_screen(self):
        """Its line 20 m ahead (on the road) is below the middle of the screen from a bonnet camera: the camera is above the road."""
        g, below, n = self.ghost, 0, 0
        cfg = dict(gc.VIEWS['bonnet'], tilt=0.0)
        for f in [f for f in self.frames if 2000 < f.clock_ms < g.end_ms - 2000 and f.speed > 40][::20]:
            cam = gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), cfg, W, H)
            g._hint = 0
            at = g.passed(f.x, f.z)
            pts = g.path(at, at + 60000, 3.0, 20.0)
            if len(pts) < 3:
                continue
            x, y, z = pts[-1]
            pt = cam.project((x, y - gc.CAR_ABOVE_GROUND, z))
            n += 1
            below += bool(pt and pt[1] > H / 2)
        print('\n  line 20 m ahead below the middle: %d / %d' % (below, n))
        self.assertGreater(below / n, 0.85)


if __name__ == '__main__':
    unittest.main()
