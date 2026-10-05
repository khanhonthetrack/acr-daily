"""Automatic route recording on real runs, and the pause / finish rule."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import recorder as rec_mod, settings  # noqa: E402
from acr_daily.recorder import RouteRecorder  # noqa: E402
from acr_daily.telemetry import Frame, Replay  # noqa: E402
from tests.test_judge import DUMP, RAW, raw_frames  # noqa: E402

settings.ROUTES = os.path.join(os.environ.get('TEMP', '.'), 'acr-daily-test-routes')
rec_mod.settings.ROUTES = settings.ROUTES


def feed_all(frames):
    r, done = RouteRecorder(), []
    for f in frames:
        r.feed(f, f.t)
        if r.state in ('done', 'failed'):
            done.append((r.state, r.saved, r.message))
            r = RouteRecorder()
            r.feed(f, f.t)
    return done


@unittest.skipUnless(os.path.exists(RAW), 'no raw log')
class RealRuns(unittest.TestCase):
    def test_clean_runs_become_routes(self):
        done = [d for d in feed_all(raw_frames()) if d[0] == 'done']
        got = [(d[1]['track'], round(d[1]['length'] / 1000, 1), d[1]['clockMs']) for d in done]
        print('\n  routes:', got)
        tracks = [g[0] for g in got]
        self.assertEqual(tracks.count('Alsace Obersteigen'), 2)
        self.assertIn('Alsace Forêt', tracks)
        for track, km, clock in got:
            self.assertTrue(4.0 < km < 10.0, (track, km))
        # the route ends where the clock stopped, not where the car rolled to afterwards
        ober = [d[1] for d in done if d[1]['track'] == 'Alsace Obersteigen']
        self.assertLess(abs(ober[0]['length'] - ober[1]['length']), 60)


@unittest.skipUnless(os.path.exists(DUMP), 'no shm dump')
class RunWithReset(unittest.TestCase):
    def test_reset_is_never_a_route(self):
        done = feed_all(Replay(DUMP).frames)
        self.assertFalse([d for d in done if d[0] == 'done'])
        self.assertTrue([d for d in done if d[0] == 'failed' and 'Reset' in d[2]])


class PauseIsNotTheFinish(unittest.TestCase):
    def drive(self, pause_at=None, pause_s=10):
        frames, t, clock, x = [], 0.0, 0, 0.0
        for _ in range(10):
            frames.append(Frame(t, 1, 0, 0.0, 0.0, 0.0, 'Car', 'Stage')); t += .05
        while x < 2500:
            t += .05; clock += 50; x += 25 * .05
            frames.append(Frame(t, 1, clock, x, 0.0, 90.0, 'Car', 'Stage'))
            if pause_at and abs(x - pause_at) < 1:
                for _ in range(int(pause_s / .05)):   # paused: clock AND car stand still
                    t += .05
                    frames.append(Frame(t, 1, clock, x, 0.0, 0.0, 'Car', 'Stage'))
                pause_at = None
        for _ in range(30):                           # past the line: clock stops, car rolls on
            t += .05; x += 10 * .05
            frames.append(Frame(t, 1, clock, x, 0.0, 36.0, 'Car', 'Stage'))
        return frames

    def test_pause_mid_stage_then_finish(self):
        done = feed_all(self.drive(pause_at=1000))
        self.assertEqual([d[0] for d in done], ['done'])
        self.assertAlmostEqual(done[0][1]['length'], 2500, delta=30)

    def test_finish(self):
        done = feed_all(self.drive())
        self.assertEqual([d[0] for d in done], ['done'])


if __name__ == '__main__':
    unittest.main()
