"""WATCH (watch.py): who is followed, the keys, where a driver is and their gap to today's #1; the broadcast's tree."""
import unittest
from unittest import mock

from acr_daily import watch
from acr_daily.ingamekit import check


class Driver:
    def __init__(self, did, x, ms, name='D'):
        from acr_daily import ghostcars
        self.id, self.name, self.car = did, name, 'Lancia Delta S4'
        self.sid = 's%d' % did
        self._x, self._ms = x, ms
        # (their run so far: 10 m a second... slower than #1 by ms - x * 100 in all, spread along)
        n = int(x // 10)
        self.trace = ghostcars.GhostTrace({'samples': [[round(ms * i / max(1, n)), i * 10.0, 0.0, 0.0, 0, 0, 0]
                                                       for i in range(n + 1)]})

    def pose(self, now):
        return (self._x, 0.0, 0.0, 0.0, 0.0, 0.0)

    def clock_now(self, now):
        return self._ms

    def dash_at(self, now):
        return {'kmh': 123.4, 'gear': 4, 'rpm': 6000, 'rpm_frac': 0.8, 'gas': 0.7, 'brake': 0.0, 'steer': 0.1}


class Route:
    def __init__(self):
        self.cum = [i * 10.0 for i in range(101)]
        self.points = [(i * 10.0, 0.0) for i in range(101)]
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
        self.assertEqual(w.cam_name(), 'auto')     # (the director, as TV: the user, 21 Nov 2026)
        w.camera(1)
        self.assertEqual(w.cam_name(), 'tv')
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


class Keys(unittest.TestCase):
    def test_the_spectator_menu(self):
        ds = [Driver(1, 100, 9000), Driver(2, 500, 52000)]
        w = watch.Watch(app_with(ds))
        w.start('daily', 2)
        w.key('right')                           # (no menu: the next driver)
        self.assertEqual(w.followed().id, 1)
        w.key('select')
        self.assertEqual(w.menu, 0)
        w.key('down')                            # camera
        w.key('right')
        self.assertEqual(w.cam_name(), 'tv')
        w.key('down')                            # AUTO driver
        w.key('left')
        self.assertTrue(w.auto_driver)
        w.key('down')                            # graphics
        w.key('right')
        self.assertEqual(w.graphics, 'clean')
        w.key('down')                            # splits
        w.key('right')
        self.assertFalse(w.splits)
        w.key('down')                            # (round to the first line)
        self.assertEqual(w.menu, 0)
        w.key('back')
        self.assertIsNone(w.menu)

    def test_auto_driver_follows_the_closest_to_the_leader(self):
        ds = [Driver(1, 300, 31000), Driver(2, 600, 66000)]    # (1: +1.0 s on #1, 2: +6.0 s)
        w = watch.Watch(app_with(ds))
        w.start('daily', 2)
        self.assertEqual(w.followed().id, 2)    # (the furthest on)
        w.auto_driver = True
        self.assertEqual(w.followed().id, 1)


class Road(unittest.TestCase):
    def test_route_ahead_in_the_games_units(self):
        w = watch.Watch(app_with([]))
        w.start('daily', 2)
        pts = w.route_ahead(Driver(1, 300, 31000))
        self.assertEqual(pts[0], (27000, 0))     # (30 m behind them, in cm)
        self.assertEqual(pts[1][0] - pts[0][0], 1000)
        self.assertLessEqual(pts[-1][0], (300 + watch.ROUTE_AHEAD_M) * 100)

    def test_splits_against_the_leader(self):
        w = watch.Watch(app_with([]))
        w.start('daily', 2)
        marks = w.split_marks()
        self.assertEqual(len(marks), 3)          # (1 km: three, the last at the finish)
        d = Driver(1, 700, 77000)                # (+7 s at 700 m, evenly: +3.33 s by the first split at 333 m)
        s = w.splits_of(d)
        self.assertIsNotNone(s[0]['ms'])
        self.assertGreater(s[0]['gap'], 0)
        self.assertIsNone(s[2]['ms'])            # (the finish: not yet)

    def test_running_place(self):
        a = app_with([])
        a.dailies[2]['board'] = {'entries': [{'totalMs': 100000}, {'totalMs': 103000}, {'totalMs': 110000}]}
        w = watch.Watch(a)
        w.start('daily', 2)
        self.assertEqual(w.running_place(2000), 2)
        self.assertEqual(w.running_place(-500), 1)
        self.assertIsNone(w.running_place(None))


class Broadcast(unittest.TestCase):
    def ig(self, drivers):
        ig = mock.Mock()
        ig.app = app_with(drivers)
        ig.app.dailies[2]['board'] = {'entries': [{'name': 'Leader', 'totalMs': 100000, 'country': 'fi'},
                                                  {'name': 'Ann', 'totalMs': 104000}]}
        ig.app.watch = watch.Watch(ig.app)
        ig.app.watch.start('daily', 2)
        return ig

    def test_tree(self):
        from acr_daily import ig_watch
        ig = self.ig([Driver(1, 300, 31000, 'Ann'), Driver(2, 600, 58000, 'Bob')])
        node = ig_watch.overlay(ig)
        self.assertEqual(check(node), [])
        ig.app.watch.stop()
        self.assertIsNone(ig_watch.overlay(ig))

    def test_every_look(self):
        from acr_daily import ig_watch
        ig = self.ig([Driver(1, 400, 47000, 'Ann')])
        w = ig.app.watch
        w.seen_shot('tv')
        for g in watch.GRAPHICS:
            for menu in (None, 2):
                w.graphics, w.menu = g, menu
                node = ig_watch.overlay(ig)
                self.assertEqual(check(node), [], (g, menu))
        ig2 = self.ig([])                        # (nobody on the stage)
        self.assertEqual(check(ig_watch.overlay(ig2)), [])

    def test_only_live_parts_change_while_driving_on(self):
        """The dash's numbers, bars and the dot move: the tree's shape (bar what is marked lv) stays, so the mod
        sets them in place instead of making the broadcast again (appui.lua set_lives)."""
        from acr_daily import ig_watch
        d = Driver(1, 100, 11000, 'Ann')         # (between splits: no split's time popping up)
        ig = self.ig([d])

        def shape(n):
            if isinstance(n, dict):
                skip = {'s'} | ({'w', 'h', 'bg', 'fg', 'a'} if n.get('lv') else set())
                return {k: shape(v) for k, v in n.items() if k not in skip}
            if isinstance(n, list):
                return [shape(x) for x in n]
            return n
        one = shape(ig_watch.overlay(ig))
        d._x, d._ms = 140, 15200
        d.dash_at = lambda now: {'kmh': 88.0, 'gear': 3, 'rpm': 7000, 'rpm_frac': 0.95, 'gas': 0.2, 'brake': 0.6,
                                 'steer': 0.0}
        self.assertEqual(shape(ig_watch.overlay(ig)), one)


class Dash(unittest.TestCase):
    def test_a_drivers_dash_through_the_relay(self):
        from acr_daily import livelink
        import importlib.util
        import os
        d = livelink.LiveDriver(1, 'Ann', 'Car', 1)
        d.add([[1000, 0, 0, 0, 0, 0, 0], [1100, 2, 0, 0, 0, 0, 0]], 10.0)
        d.add_dash([1000, 100.0, 4, 5000, 0.5, 0.0, 0.0])
        d.add_dash([1100, 110.0, 4, 5200, 0.6, 0.0, 0.0])
        d.add_dash(['x'])                        # (not a dash: left out)
        d.play_clock = lambda now: 1050
        got = d.dash_at(10.0)
        self.assertAlmostEqual(got['kmh'], 105.0)
        self.assertEqual(got['gear'], 4)
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location('relay', os.path.join(here, '..', '..', 'live', 'relay.py'))
        relay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(relay)
        self.assertTrue(relay.good_dash([1000, 100.0, 4, 5000, 0.5, 0.0, -0.3]))
        self.assertFalse(relay.good_dash([1000, 100.0, 4, 5000, 0.5, 0.0]))
        self.assertFalse(relay.good_dash([1000, 1e9, 4, 5000, 0.5, 0.0, 0.0]))
        self.assertFalse(relay.good_dash([1000, True, 4, 5000, 0.5, 0.0, 0.0]))


if __name__ == '__main__':
    unittest.main()
