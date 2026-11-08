"""The LIVE tab (liveui.py): who is driving right now, as on the website's live map. On a Tk window that is never shown."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import liveui  # noqa: E402
from test_inbox import ME, click, find, texts  # noqa: E402
from test_tabs import Harness  # noqa: E402

DAY = '2026-11-08'
ROAD = [[i * 10.0, 0.0] for i in range(101)]            # a straight 1 km road, east
TIMING = {'liveSendS': 5, 'livePollS': 5, 'liveIdleS': 15, 'boardS': 120, 'boardIdleS': 300}


def drivers(now):
    """/api/live?slot=all: Ann and I on SS1, Bob finished it, Cid out of it; nobody on SS2."""
    return [{'steamId': 'ann', 'slot': 1, 'name': 'Ann', 'progress': 0.64, 'totalMs': 250000, 'state': 'live', 'updated': now - 2000},
            {'steamId': ME, 'slot': 1, 'name': 'Me', 'progress': 0.31, 'totalMs': 120000, 'state': 'live', 'updated': now - 1000,
             'look': {'color': '#FFD60A'}},
            {'steamId': 'bob', 'slot': 1, 'name': 'Bob', 'progress': 1, 'totalMs': 418412, 'state': 'finished', 'updated': now - 9000,
             'team': {'tag': 'GFX'}},
            {'steamId': 'cid', 'slot': 1, 'name': 'Cid', 'progress': 0.5, 'totalMs': 200000, 'state': 'dnf', 'updated': now - 5000}]


class Words(unittest.TestCase):
    def test_the_order_on_stage_first_then_the_finishers_then_the_dnfs(self):
        now = 1e12
        self.assertEqual([d['steamId'] for d in liveui.live_order(drivers(now))], ['ann', ME, 'bob', 'cid'])
        two = [dict(drivers(now)[2], steamId='x', totalMs=300000), drivers(now)[2]]
        self.assertEqual([d['steamId'] for d in liveui.live_order(two)], ['x', 'bob'])   # (the quickest finisher first)

    def test_the_clock_runs_on_while_on_stage(self):
        d = drivers(1e12)
        self.assertEqual(liveui.clock_ms(d[0], 1e12), 252000)        # sent 2 s ago: 2 s on
        self.assertEqual(liveui.clock_ms(d[2], 1e12), 418412)        # a finish: its own
        self.assertEqual((liveui.fmt_clock(252000), liveui.fmt_clock(418412, exact=True)), ('4:12.0', '6:58.412'))


class LivePage(Harness):
    def setUp(self):
        super().setUp()
        p = mock.patch('acr_daily.liveui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target))
        p.start()
        self.addCleanup(p.stop)
        a = self.a
        a.timing = lambda key: TIMING[key]
        a.dailies = {s: {'ch': {'id': '%s/%d' % (DAY, s), 'date': DAY, 'slot': s, 'track': 'Test %d' % s, 'menuName': 'Stage %d' % s,
                                'car': 'Car %d' % s, 'route': ROAD}, 'judge': None} for s in (1, 2)}
        a._tt, a.tt_info = {}, None
        self.now = time.time() * 1000
        a.api.live_all.return_value = {'date': DAY, 'now': self.now, 'drivers': drivers(self.now)}
        a.api.tt_live_all.return_value = {'week': '2026-11-09', 'now': self.now, 'drivers': []}
        a._build_live_box()

    def test_the_tab_puts_the_live_page_in_the_views_place_and_asks_at_once(self):
        a = self.a
        click(a.live_l)
        self.assertTrue(a.live_view)
        self.assertEqual((a.live_u.cget('bg'), self.underlined()), (liveui.LIVE_COLOUR, {}))   # (no other tab)
        self.assertEqual([w.winfo_manager() for w in (a.daily_box, a.board_l, a.tree, a.live_box)], ['', '', '', 'pack'])
        a.api.live_all.assert_called_once_with(DAY)            # both dailies, one request
        said = texts(a.live_box)
        for x in ('SS1', 'STAGE 1', 'SS2', '2 ON STAGE', 'NOBODY ON STAGE', 'Ann', 'Me', '[GFX] Bob', 'Cid', '64 %', '31 %',
                  'FINISHED', 'DNF', '6:58.412', 'Nobody on this stage right now.', '2 drivers on stage'):
            self.assertIn(x, said)
        self.assertLess(said.index('Ann'), said.index('Me'))    # (the furthest along first)
        a.show_tab('cup')                                     # a tab closes it: its view, the timing sheet back
        self.assertEqual((a.live_view, a.league_view), (False, True))
        self.assertEqual([w.winfo_manager() for w in (a.league_box, a.board_l, a.tree, a.live_box)], ['pack', 'pack', 'pack', ''])

    def test_the_inbox_and_the_settings_take_turns_with_it(self):
        a = self.a
        a.s['overlay'] = {}
        a.steam_b, a.acct_l, a.overlay = mock.Mock(), mock.Mock(), mock.Mock()
        a._build_settings_box()
        a.toggle_live_view(True)
        a.toggle_settings_view(True)
        self.assertEqual((a.live_view, a.settings_view), (False, True))
        self.assertEqual([w.winfo_manager() for w in (a.live_box, a.settings_box, a.board_l, a.tree)], ['', 'pack', '', ''])
        a.toggle_live_view(True)
        a.toggle_inbox_view()
        self.assertEqual((a.live_view, a.inbox_view), (False, True))
        a.toggle_inbox_view()                                 # closed: the dailies, as they were
        self.assertEqual([w.winfo_manager() for w in (a.daily_box, a.board_l, a.tree, a.live_box)], ['pack', 'pack', 'pack', ''])

    def test_the_time_trial_part(self):
        a = self.a
        a.tt_info = {'on': True, 'week': '2026-11-09'}
        a._tt = {1: {'ch': {'id': 'tt:2026-11-09/1', 'slot': 1, 'track': 'TT', 'menuName': 'Sweet Lamb', 'route': ROAD}, 'judge': None}}
        a.toggle_live_view(True)
        click(find(a.live_box, 'TIME TRIAL'))
        a.api.tt_live_all.assert_called_once_with('2026-11-09')   # both stages, one request
        said = texts(a.live_box)
        self.assertIn('TT1', said)
        self.assertIn('SWEET LAMB', said)
        self.assertNotIn('Ann', said)

    def test_the_matches_part_a_panel_for_each_stage_someone_is_on(self):
        a = self.a
        now = self.now
        ev = lambda i, kind, name, league: {'id': i, 'name': name, 'kind': kind, 'league': league, 'rally': 'Wales',   # noqa: E731
                                            'car': 'Ford Fiesta Rally2', 'carClass': None, 'stages': [
                                                {'no': 1, 'track': 'Wales Afon Biga', 'name': 'Afon Biga', 'lengthM': 9876},
                                                {'no': 2, 'track': 'Wales Sweet Lamb', 'name': 'Sweet Lamb', 'lengthM': 4321}]}
        a.api.live_matches.return_value = {'now': now, 'events': [ev(7, 'league', 'Round 3', 'Sunday Gravel Club'),
                                                                  ev(9, 'h2h', 'Ben vs Dot', '1V1: Ben vs Dot')], 'drivers': [
            {'eventId': 7, 'stageNo': 1, 'steamId': 'ann', 'name': 'Ann', 'progress': 0.4, 'totalMs': 60000, 'state': 'live', 'updated': now},
            {'eventId': 7, 'stageNo': 0, 'steamId': 'eve', 'name': 'Eve', 'progress': 0.9, 'totalMs': 90000, 'state': 'live', 'updated': now},
            {'eventId': 9, 'stageNo': 0, 'steamId': 'ben', 'name': 'Ben', 'progress': 1, 'totalMs': 300000, 'state': 'finished',
             'updated': now}]}
        a.api.route.side_effect = lambda track: ROAD
        a.toggle_live_view(True)
        click(find(a.live_box, 'MATCHES'))
        a.api.live_matches.assert_called_once_with()           # every match, one request
        said = texts(a.live_box)
        for x in ('LEAGUE', 'Round 3', 'Sunday Gravel Club  ·  SS2 Sweet Lamb  ·  Ford Fiesta Rally2', 'SS1 Afon Biga', '1V1',
                  'Ben vs Dot', 'Ann', 'Eve', 'Ben', 'FINISHED', '2 drivers on stage'):
            self.assertTrue(any(x in t for t in said), x)
        self.assertEqual(sorted(a._live_stages), [(7, 0), (7, 1), (9, 0)])     # a panel each: the two stages of Round 3
        self.assertEqual(sorted(c.args[0] for c in a.api.route.call_args_list), ['Wales Afon Biga', 'Wales Sweet Lamb'])  # (once each)
        self.assertEqual(a._live_stages[(9, 0)]['route'], ROAD)               # in, and the map drawn with it
        a._live_take('match', {'now': now, 'events': [], 'drivers': []})
        self.assertIn('Nobody is driving a league event, a 1V1 or a cup match right now.', texts(a.live_box))
        self.web.reset_mock()
        click(a._live_site)
        self.web.assert_called_with('https://acrdaily.com/live')

    def test_each_car_on_the_road_where_the_playback_has_it(self):
        a = self.a
        a.toggle_live_view(True)
        s = a._live_stages[1]
        cv = s['canvas']
        a._live_draw_map(s)
        pb = a._live_pb[('daily', 1)]
        with mock.patch('acr_daily.liveui.time.time', return_value=self.now / 1000):
            a._live_draw_cars(s)
            at = pb.at('ann', self.now)
        names = {cv.itemcget(i, 'text'): cv.coords(i) for i in cv.find_withtag('car') if cv.type(i) == 'text'}
        self.assertEqual(set(names), {'Ann', 'Me', '[GFX] Bob', 'Cid'})
        x, y = s['to'](*s['track'].at(at['p']))                # Ann: along the road, as far as the playback says
        self.assertAlmostEqual(names['Ann'][1], y, delta=1)
        self.assertGreater(names['Ann'][0], x)                 # (her name to the right of her dot)

    def test_asked_every_few_seconds_while_someone_drives_less_often_else_never_minimised(self):
        a = self.a
        a.toggle_live_view(True)
        self.assertEqual(a._live_every_ms(), 3000)            # someone on a stage: min(livePollS, liveSendS / 2)
        a._live_take('daily', {'now': self.now, 'drivers': []})
        self.assertEqual(a._live_every_ms(), 15000)           # nobody: liveIdleS
        a.api.live_all.reset_mock()
        a._live_poll()                                         # (not due yet)
        a.api.live_all.assert_not_called()
        with mock.patch.object(a.root, 'state', return_value='iconic'):
            a._live_poll(force=True)                           # minimised: nothing asked
        a.api.live_all.assert_not_called()
        a._live_poll(force=True)
        a.api.live_all.assert_called_once()
        a.toggle_live_view(False)                              # closed: nothing asked
        a._live_poll(force=True)
        a.api.live_all.assert_called_once()


if __name__ == '__main__':
    unittest.main()
