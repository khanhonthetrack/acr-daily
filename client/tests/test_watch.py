"""WATCH (watch.py): who is followed, the keys, where a driver is and their gap to today's #1; the broadcast's tree."""
import unittest
from unittest import mock

from acr_daily import watch
from acr_daily.ingamekit import check


class Driver:
    def __init__(self, did, x, ms, name='D'):
        self.id, self.name, self.car = did, name, 'Lancia Delta S4'
        self._x, self._ms = x, ms

    def pose(self, now):
        return (self._x, 0.0, 0.0, 0.0, 0.0, 0.0)

    def clock_now(self, now):
        return self._ms


class Route:
    def __init__(self):
        self.cum = [i * 10.0 for i in range(101)]
        self.length = 1000.0

    def nearest(self, x, z):
        return max(0, min(100, int(x / 10))), 0.0


class Ghost:
    def total_at(self, idx):
        return idx * 1000                      # (#1: 10 m a second)


def app_with(drivers):
    a = mock.Mock()
    a.ghostcars.live.others.return_value = drivers
    j = mock.Mock()
    j.route, j.ghost = Route(), Ghost()
    a.dailies = {2: {'judge': j, 'ch': {'stageId': 'X', 'menuName': 'Stage'}, 'board': {'entries': []}}}
    return a


class Following(unittest.TestCase):
    def test_furthest_first_and_the_keys(self):
        ds = [Driver(1, 100, 9000), Driver(2, 500, 52000)]
        w = watch.Watch(app_with(ds))
        w.start('daily', 2)
        self.assertEqual([d.id for d in w.drivers()], [2, 1])
        self.assertEqual(w.followed().id, 2)
        w.step(1)
        self.assertEqual(w.followed().id, 1)
        w.camera(1)
        self.assertEqual(w.cam_name(), 'far')
        self.assertEqual(w.ghost_id(), 'L1')

    def test_where_and_the_gap(self):
        w = watch.Watch(app_with([]))
        w.start('daily', 2)
        at = w.where(Driver(1, 500, 52000))
        self.assertAlmostEqual(at['progress'], 0.5)
        self.assertEqual(at['gap'], 2000)        # (#1 was there at 50 s)

    def test_a_driver_gone_another_after_a_while(self):
        ds = [Driver(1, 100, 9000)]
        a = app_with(ds)
        w = watch.Watch(a)
        w.start('daily', 2)
        w.target = 7
        with mock.patch('acr_daily.watch.time.monotonic', return_value=100.0):
            self.assertIsNone(w.followed())      # (kept a moment: they may come back)
        with mock.patch('acr_daily.watch.time.monotonic', return_value=100.0 + watch.FALLBACK_S):
            self.assertEqual(w.followed().id, 1)


class Broadcast(unittest.TestCase):
    def test_tree(self):
        from acr_daily import ig_watch
        ig = mock.Mock()
        ig.app = app_with([Driver(1, 300, 31000, 'Ann'), Driver(2, 600, 58000, 'Bob')])
        ig.app.watch = watch.Watch(ig.app)
        ig.app.watch.start('daily', 2)
        node = ig_watch.overlay(ig)
        self.assertEqual(check(node), [])
        ig.app.watch.stop()
        self.assertIsNone(ig_watch.overlay(ig))


if __name__ == '__main__':
    unittest.main()
