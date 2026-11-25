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

    def test_only_the_watched_stages_car(self):
        # (24 Nov 2026: a driver practising the Delta S4 daily's stage in a Skoda Fabia was followed, timed against
        # the day's board)
        fabia = Driver(3, 900, 95000)
        fabia.car = 'Skoda Fabia RS Rally2'
        nameless = Driver(4, 50, 5000)
        nameless.car = ''
        a = app_with([Driver(1, 100, 9000), fabia, nameless])
        a.dailies[2]['ch'].update(car='Lancia Delta S4 Evo2 Italtecnica', carId='LanciaDeltaS4Evo2',
                                  carAliases=['Lancia Delta S4', 'Lancia Delta S4 Evo2'])
        w = watch.Watch(a)
        w.start('daily', 2)
        self.assertEqual([d.id for d in w.drivers()], [1, 4])
        self.assertEqual(w.followed().id, 1)
        # an event of two cars: either of them
        w.start('event', 1, event={'ch': {'car': 'Peugeot 208 Rally4'}, 'judge': a.dailies[2]['judge'],
                                   'cars': [{'name': 'Peugeot 208 Rally4', 'id': 'Peugeot208Rally4'},
                                            {'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}]})
        self.assertEqual([d.id for d in w.drivers()], [3, 4])

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
                skip = {'s'} | ({'w', 'h', 'bg', 'fg', 'a', 'src'} if n.get('lv') else set())
                return {k: shape(v) for k, v in n.items() if k not in skip}
            if isinstance(n, list):
                return [shape(x) for x in n]
            return n
        one = shape(ig_watch.overlay(ig))
        d._x, d._ms = 140, 15200
        d.dash_at = lambda now: {'kmh': 88.0, 'gear': 3, 'rpm': 7000, 'rpm_frac': 0.95, 'gas': 0.2, 'brake': 0.6,
                                 'steer': 0.0}
        self.assertEqual(shape(ig_watch.overlay(ig)), one)


class FromTheList(unittest.TestCase):
    """WATCH's list (ig_watchlist.py): everyone on a stage now; WATCH follows the one picked; an event's stage."""
    LINE = {'kind': 'league', 'eventId': 42, 'event': 'Winter Cup', 'league': 'Club', 'stageNo': 3,
            'stage': {'stageId': 'X', 'track': 'Stage', 'name': 'Stage', 'weatherGame': 'WT_CLEAR',
                      'startSeconds': 36000},
            # (the server's: the event's car is its name, a string; the page failed on it, 22 Nov 2026)
            'car': 'Lancia Delta S4', 'cars': [{'id': 'Car1', 'name': 'Lancia Delta S4'}],
            'steamId': 's1', 'name': 'Ann', 'country': 'fi', 'look': {'tag': {'text': '$f00ABC', 'color': '#123456'}},
            'progress': 0.4, 'totalMs': 61000}

    def ig(self, drivers=()):
        ig = mock.Mock()
        ig.app = app_with(list(drivers))
        ig.app.s = {'token': 't', 'steamId': 'me'}
        ig.app.tt = {}
        ig.app.dailies[2]['live'] = [{'steamId': 's9', 'name': 'Bob', 'state': 'live', 'progress': 0.7,
                                      'totalMs': 90000}]
        mem = {}
        ig.mem = lambda k: mem.setdefault(k, {})
        ig.shown = False
        ig.app.watch = watch.Watch(ig.app)
        return ig

    def test_the_one_picked_is_followed_first(self):
        ds = [Driver(1, 100, 9000), Driver(2, 500, 52000)]
        w = watch.Watch(app_with(ds))
        w.start('daily', 2, prefer='s1')
        self.assertEqual(w.followed().id, 1)     # (not the furthest on: the one picked on the list)

    def test_the_list_and_its_buttons(self):
        from acr_daily import ig_watchlist
        ig = self.ig()
        ig.mem(ig_watchlist.TAB)['events'] = [self.LINE]
        rows = ig_watchlist.lines(ig)
        self.assertEqual([r['name'] for r in rows], ['Bob', 'Ann'])
        self.assertEqual(rows[1]['key'], 'e:42:3:s1')
        self.assertEqual(check(ig_watchlist.page(ig)), [])
        with mock.patch('acr_daily.ig_watch.start_event') as go:
            ig_watchlist.click(ig, 'go', 'e:42:3:s1')
        self.assertEqual(go.call_args[0][1]['eventId'], 42)
        with mock.patch('acr_daily.ig_watch.start') as go:
            ig_watchlist.click(ig, 'go', 'd:2:s9')
        self.assertEqual(go.call_args[0][1:], ('daily', 2))
        self.assertEqual(go.call_args[1], {'prefer': 's9'})
        ig.mem(ig_watchlist.TAB)['events'] = []
        ig.app.dailies[2]['live'] = []
        ig.mem(ig_watchlist.TAB)['events_at'] = 1.0
        self.assertEqual(check(ig_watchlist.page(ig)), [])

    def test_an_events_stage_watched(self):
        from acr_daily import ig_watch
        held = ig_watch.event_held(self.LINE)
        self.assertEqual(held['ch']['stageId'], 'X')
        self.assertEqual(held['ch']['carId'], 'Car1')
        hidden = dict(self.LINE, stage=dict(self.LINE['stage'], weatherGame=None, startSeconds=None))
        self.assertEqual(ig_watch.event_held(hidden)['ch']['weatherGame'], 'WT_CLEAR')   # (kept from them: any)
        self.assertIsNone(ig_watch.event_held(dict(self.LINE, stage={})))
        ig = self.ig([Driver(1, 300, 31000, 'Ann')])
        ig.app.watch.start('event', 3, event=held, prefer='s1')
        held['judge'] = ig.app.dailies[2]['judge']
        ig.mem('watch')['events'] = [self.LINE]
        ig.mem('watch')['at'] = 1e18                 # (not fetched in the test)
        node = ig_watch.overlay(ig)
        self.assertEqual(check(node), [])
        self.assertIn('WINTER CUP', str(node))
        self.assertIsNone(ig.app.watch.room())
        held['kind'] = 'live'
        self.assertEqual(ig.app.watch.room(), 'live:42')
        self.assertEqual(ig_watch.team_text(self.LINE['look']['tag']), 'ABC')


class Home(unittest.TestCase):
    def test_the_tiles(self):
        from acr_daily import ig_home
        ig = FromTheList().ig()
        ig.app._home_spec = lambda k: {'title': k.upper(), 'photo': None, 'lines': [('a', 'sub'), ('b', 'info')]}
        ig.app.driver = {'name': 'Me'}
        ig.app.credits = {'balance': 50}
        node = ig_home.page(ig)
        self.assertEqual(check(node), [])
        for key in ('events', 'comp', 'profile', 'watch', 'community'):
            self.assertIn('home.go:%s' % key, str(node))
        self.assertIn('1 LIVE', str(node))           # (Bob on the daily's stage)


class EventsTab(unittest.TestCase):
    def test_events_opens_its_last_sub_tab_and_stays_lit(self):
        from acr_daily import ingameapp
        ig = ingameapp.InGameApp.__new__(ingameapp.InGameApp)
        ig.app, ig._mem, ig._mods = mock.Mock(), {}, {}
        ig.tab, ig.dialog, ig.prep = 'home', None, None
        ig.opened = lambda: None
        ig.click('tab:events')
        self.assertEqual((ig.tab, ig.head_tab()), ('daily', 'events'))
        ig.run = lambda fn: fn()
        ig.click('events.sub:tt')
        self.assertEqual(ig.tab, 'tt')
        ig.click('tab:watch')
        ig.click('tab:events')
        self.assertEqual(ig.tab, 'tt')           # (the one last shown)
        ig.click('tab:daily')                    # (a page's own link to the dailies: still EVENTS)
        self.assertEqual(ig.head_tab(), 'events')
        ig.switch_tab(1)
        self.assertNotEqual(ig.head_tab(), 'events')
        self.assertIn('events', dict(ingameapp.TABS))
        self.assertNotIn('daily', dict(ingameapp.TABS))


class RelayFollow(unittest.TestCase):
    """The relay (live/relay.py): a watcher at the start line gets the driver they follow in full, however far; another
    far driver one message in FAR_EVERY (22 Nov 2026: one a second made the car stutter and the gauge jump)."""
    def relay(self):
        import importlib.util
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location('relay', os.path.join(here, '..', '..', 'live', 'relay.py'))
        relay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(relay)
        return relay

    def test_the_followed_driver_in_full(self):
        import asyncio
        relay = self.relay()
        r = relay.Relay(None)

        class C:
            def __init__(self, cid, pos):
                self.id, self.pos, self.watch, self.near, self.follow, self.sent, self.got = cid, pos, True, None, None, 1, []

            async def send_text(self, text):
                self.got.append(text)
        me, far, other = C(1, [0, 0]), C(2, [5000, 0]), C(3, [6000, 0])
        r.rooms['x'] = {me, far, other}
        asyncio.run(r.message(me, {'t': 'follow', 'id': 2}))
        r.nearest('x', now=100.0)
        asyncio.run(r.broadcast('x', 'from far', but=far, near=far))       # (its 2nd message: not one in FAR_EVERY)
        asyncio.run(r.broadcast('x', 'from other', but=other, near=other))
        self.assertIn('from far', me.got)
        self.assertNotIn('from other', me.got)


class PlayClock(unittest.TestCase):
    def test_a_late_ask_never_moves_it_on(self):
        """Asked with a moment older than the last ask (WATCH's graphics keep the moment they started at): answered,
        nothing moved. It used to set the last ask back and count that stretch twice: the clock crept ahead of the
        driver's data and snapped back 1.5 s every few seconds (oldtimer44 watched live, 22 Nov 2026)."""
        from acr_daily import livelink
        d = livelink.LiveDriver(1, 'Ann', 'Car', 1)
        d.floor_ms = livelink.WATCH_DELAY_MS
        t, ms = 100.0, 10000
        for k in range(600):                    # 60 s of batches, 100 ms apart, 2 samples each
            d.add([[ms, k, 0, 0, 0, 0, 0], [ms + 50, k + .5, 0, 0, 0, 0, 0]], t)
            d.play_clock(t - 0.15)               # (a late ask)
            c = d.play_clock(t)
            t, ms = t + 0.1, ms + 100
        self.assertAlmostEqual(d.trace.ms[-1] - c, livelink.WATCH_DELAY_MS, delta=120)   # (still 1.5 s behind)


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
