"""Incidents for the live commentary (incidents.py): a hit, a stop, off the road, reversing, a big jump."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily.incidents import IncidentWatch  # noqa: E402
from acr_daily.telemetry import Frame  # noqa: E402


def frame(t, kmh, x=0.0, gear=4):
    return Frame(t, 1, int(t * 1000), x, 0.0, kmh, 'C', 'S', gear=gear)


class Incidents(unittest.TestCase):
    def drive(self, w, speeds, t=0.0, x=0.0, gear=4, prog=0.5, off=0.0, resetting=False, dt=0.05):
        out = []
        for v in speeds:
            t += dt
            x += v / 3.6 * dt * (-1 if gear == 0 else 1)
            out += w.feed(frame(t, v, x, gear), t, prog, off, resetting)
        return out, t, x

    def test_a_hit(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [80] * 20)
        out, t, x = self.drive(w, [80 - 15 * k for k in range(1, 5)] + [20] * 60, t, x)   # 80 -> 20 in 0.2 s, ~8 g
        self.assertEqual([i['type'] for i in out], ['hit'])
        self.assertEqual((out[0]['fromKmh'], out[0]['toKmh']), (80, 20))

    def test_hard_braking_is_not_a_hit(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [120 - 0.6 * k for k in range(150)])   # 1.7 g for 7.5 s
        self.assertEqual(out, [])

    def test_a_hit_that_ends_in_a_reset_is_the_reset(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [80] * 20)
        out1, t, x = self.drive(w, [80 - 15 * k for k in range(1, 5)] + [0] * 10, t, x)
        out2, t, x = self.drive(w, [0] * 50, t, x, resetting=True)
        self.assertEqual(out1 + out2, [])

    def test_stopped_on_the_stage(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [0.1] * 200)       # 10 s standing still
        self.assertEqual(out, [])                     # told when it ends
        out, t, x = self.drive(w, [8] * 5, t, x)
        self.assertEqual(out[0]['type'], 'stuck')
        self.assertAlmostEqual(out[0]['seconds'], 10, delta=0.3)

    def test_a_short_stop_is_nothing(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [0.1] * 40 + [10] * 10)
        self.assertEqual(out, [])

    def test_off_the_road_and_back(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [50] * 80, off=35)
        out, t, x = self.drive(w, [50] * 5, t, x, off=3)
        self.assertEqual(out[0]['type'], 'off')

    def test_reversing(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [10] * 100, gear=0)     # ~14 m backwards
        out, t, x = self.drive(w, [5] * 3, t, x, gear=2)
        self.assertEqual(out[0]['type'], 'reverse')
        self.assertGreaterEqual(out[0]['metres'], 10)

    def test_not_at_the_start_or_after_the_finish(self):
        w = IncidentWatch()
        out, t, x = self.drive(w, [0.1] * 200 + [8] * 5, prog=0.99)
        self.assertEqual(out, [])

    def test_at_most_one_every_20_s(self):
        w = IncidentWatch()
        out = []
        t, x = 0.0, 0.0
        for _ in range(3):                             # three hits 6 s apart
            o, t, x = self.drive(w, [80] * 20, t, x)
            o2, t, x = self.drive(w, [80 - 15 * k for k in range(1, 5)] + [20] * 80, t, x)
            out += o + o2
        self.assertEqual(len(out), 1)

    def test_a_big_jump(self):
        w = IncidentWatch()
        w.jump(1250, 118, 0.5, now=1.0)
        w.jump(400, 90, 0.6, now=30.0)                 # a small one: not worth a line
        self.assertEqual(w.feed(frame(3.0, 90), 3.0, 0.6, 0.0, False), [])      # held a few seconds
        out = w.feed(frame(7.5, 90), 7.5, 0.6, 0.0, False)
        self.assertEqual([i['type'] for i in out], ['jump'])

    def test_airtime_before_a_reset_was_the_crash(self):
        w = IncidentWatch()
        w.jump(1600, 95, 0.5, now=1.0)
        w.feed(frame(3.0, 0), 3.0, 0.5, 0.0, True)                            # a reset follows
        self.assertEqual(w.feed(frame(9.0, 30), 9.0, 0.5, 0.0, False), [])


if __name__ == '__main__':
    unittest.main()
