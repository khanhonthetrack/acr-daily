"""Live rallies in the app: the logic (liverally.py: the server's clock, the start windows, the queues as listed, the
session shown first, the timer's countdown) and the LIVE page (liverallyui.py: in the nav and on HOME, signing up,
DRIVE through the leagues', each start sent with the server's time, the next stage's slot asked at the finish, the
ghost cars' room). On a Tk window that is never shown; the server faked."""
import os
import sys
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import liverally, tabsui  # noqa: E402
from acr_daily.judge import Judge  # noqa: E402
from test_inbox import ME, click, texts  # noqa: E402
from test_tabs import Harness  # noqa: E402

H = 1_794_988_800_000                      # Wed 18 Nov 2026, 08:00 UTC: a Rally2 session (server src/liverallies.js)
MIN = 60000
CARS = [{'name': 'VW Polo GTI R5', 'id': 'VWPoloGTIR5'}, {'name': 'Hyundai i20 N Rally2', 'id': 'HyundaiI20NRally2'},
        {'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}]
INFO = {'now': H - 10 * MIN, 'on': True, 'pollS': 60,
        'series': [{'key': 'rally2', 'name': 'Rally2 Live', 'carClass': 'Rally2/R5', 'cars': CARS, 'rally': 'Wales',
                    'nextRally': 'Alsace', 'everyHours': 4},
                   {'key': 'classic', 'name': 'Group 4 Classics Live', 'carClass': 'H1', 'cars': [], 'rally': 'Alsace',
                    'nextRally': 'Greece', 'everyHours': 4}],
        'sessions': [{'series': 'rally2', 'starts': H, 'signupOpens': H - 30 * MIN, 'firstStart': H + 5 * MIN, 'closes': H + 105 * MIN,
                      'phase': 'signup', 'rally': 'Wales', 'signups': 1, 'signedUp': False, 'car': None, 'eventId': None, 'entry': None},
                     {'series': 'classic', 'starts': H + 120 * MIN, 'signupOpens': H + 90 * MIN, 'firstStart': H + 125 * MIN,
                      'closes': H + 225 * MIN, 'phase': 'upcoming', 'rally': 'Alsace', 'signups': 0, 'signedUp': False,
                      'car': None, 'eventId': None, 'entry': None}]}
SIGNUP = {'now': H - 10 * MIN, 'phase': 'signup', 'starts': H, 'signupOpens': H - 30 * MIN, 'firstStart': H + 5 * MIN,
          'closes': H + 105 * MIN, 'rally': 'Wales', 'entrants': [{'steamId': '7', 'name': 'Ann', 'car': 'VW Polo GTI R5'}],
          'me': {'signedIn': True, 'signedUp': False, 'car': None}, 'pollS': 30}
EVENT = {'id': 42, 'kind': 'live', 'series': 'rally2', 'sessionStarts': H, 'name': 'Rally2 Live · Wales · 08:00 UTC',
         'league': 'Rally2 Live', 'rally': 'Wales', 'carClass': 'Rally2/R5', 'cars': [dict(c, cls='Rally2/R5') for c in CARS],
         'rules': {}, 'opens': H, 'closes': H + 105 * MIN, 'status': 'open', 'entry': None,
         'stages': [{'no': k + 1, 'track': 'Wales Stage %d' % k, 'stageId': 'S%d' % k, 'name': 'Stage %d' % k, 'lengthM': 8000,
                     'weather': 'Clear', 'weatherLabel': 'Clear', 'weatherGame': 'WT_CLEAR', 'time': '12:%02d' % (20 * k),
                     'startSeconds': 43200 + 1200 * k, 'day': 1, 'service': k == 0, 'route': [[0, 0], [100, 0]]}
                    for k in range(3)]}


def running(me_next=None, queues=None):
    return {'now': H + MIN, 'phase': 'running', 'starts': H, 'signupOpens': H - 30 * MIN, 'firstStart': H + 5 * MIN,
            'closes': H + 105 * MIN, 'rally': 'Wales', 'eventId': 42, 'event': dict(EVENT), 'entrants': 2,
            'queues': queues or [[{'steamId': '7', 'name': 'Ann', 'car': 'VW Polo GTI R5', 'at': H + 5 * MIN, 'moved': 0,
                                   'started': None, 'penaltyMs': 0, 'state': 'waiting', 'timeMs': None},
                                  {'steamId': ME, 'name': 'Me', 'car': 'Skoda Fabia RS Rally2', 'at': H + 5 * MIN + 30000,
                                   'moved': 0, 'started': None, 'penaltyMs': 0, 'state': 'waiting', 'timeMs': None}], [], []],
            'standings': [], 'pollS': 10,
            'me': {'signedIn': True, 'signedUp': True, 'car': 'Skoda Fabia RS Rally2',
                   'next': me_next if me_next is not None else {'no': 0, 'at': H + 5 * MIN + 30000, 'moved': 0, 'started': None,
                                                                'penaltyMs': 0, 'out': None}}}


class Logic(unittest.TestCase):
    def test_the_servers_clock_from_the_quickest_answer(self):
        c = liverally.Clock()
        c.learn(1_000_000, 990.0, 991.0)              # 1 s round trip: the server 9.5 s ahead... (doubtful)
        self.assertAlmostEqual(c.offset_ms, 1_000_000 - 990_500)
        c.learn(1_000_100, 990.05, 990.15)            # 0.1 s: kept
        self.assertAlmostEqual(c.offset_ms, 1_000_100 - 990_100)
        c.learn(5_000_000, 990.2, 992.2)              # 2 s: not
        self.assertAlmostEqual(c.offset_ms, 10_000)
        self.assertEqual(c.server_ms(990_000), 1_000_000)
        self.assertIsNone(c.server_ms(None))

    def test_a_starts_window(self):
        at = H + 5 * MIN
        self.assertEqual([liverally.phase(at, at + d) for d in (-6000, -5000, 0, 30000, 30001)],
                         ['wait', 'go', 'go', 'go', 'late'])
        self.assertEqual([liverally.left(ms) for ms in (0, 999, 42_000, 725_000, 3_723_000)], ['0:00', '0:01', '0:42', '12:05', '1:02:03'])

    def test_the_queues_and_the_standings_as_listed(self):
        v = running(queues=[[{'steamId': '7', 'name': 'Ann', 'car': 'VW Polo GTI R5', 'at': H + 5 * MIN, 'moved': 0,
                              'penaltyMs': 12000, 'state': 'done', 'timeMs': 372000},
                             {'steamId': ME, 'name': 'Me', 'car': 'Skoda', 'at': H + 7 * MIN, 'moved': 1, 'penaltyMs': 0,
                              'state': 'waiting', 'timeMs': None}], [], []])
        rows = liverally.queue_rows(v, 0, ME)
        self.assertEqual([(r[1], r[3], r[4], r[5]) for r in rows],
                         [('Ann', '6:12.000  ·  jump start +12 s', 'good', False), ('Me', 'waiting  ·  moved to the end 1×', 'soft', True)])
        self.assertEqual(liverally.queue_rows(v, 2), [])
        self.assertEqual(liverally.queue_rows({}, 1), [])
        v['standings'] = [{'steamId': '7', 'name': 'Ann', 'car': 'VW', 'status': 'finished', 'totalMs': 1_100_000, 'rank': 1},
                          {'steamId': ME, 'name': 'Me', 'car': 'Skoda', 'status': 'running', 'done': 1, 'rank': None}]
        self.assertEqual(liverally.standings_rows(v, ME), [('1', 'Ann', 'VW', '18:20.000', '', False),
                                                           ('–', 'Me', 'Skoda', 'SS2 of 3', '', True)])

    def test_the_session_shown_first(self):
        now = H - 10 * MIN
        self.assertEqual(liverally.pick(INFO, now), ('rally2', H))              # the one open for sign-up
        info = dict(INFO, sessions=[dict(INFO['sessions'][0], phase='over'), dict(INFO['sessions'][1], signedUp=True)])
        self.assertEqual(liverally.pick(info, H + 100 * MIN), ('classic', H + 120 * MIN))   # mine, starting soon
        self.assertIsNone(liverally.pick({}, now))
        self.assertEqual(liverally.card_line(INFO['sessions'][0], now), 'Sign-up open · starts in 10:00 · 1 signed up')
        self.assertEqual(liverally.card_line(INFO['sessions'][1], now), 'Sign-up opens in 1:40:00')

    def test_the_timers_countdown(self):
        v = running()
        at = H + 5 * MIN + 30000
        st, ms, line, col = liverally.overlay(v, 0, at - 90_000)
        self.assertEqual((st, ms, col), ('wait', 90_000, 'soft'))
        self.assertIn('start at GO', line)
        self.assertEqual(liverally.overlay(v, 0, at - 30_000)[3], 'slow')       # (the last minute)
        st, ms, line, col = liverally.overlay(v, 0, at + 10_000)
        self.assertEqual((st, col), ('go', 'good'))
        self.assertIn('· 20 s left', line)
        self.assertEqual(liverally.overlay(v, 0, at + 31_000)[0], 'late')
        self.assertIsNone(liverally.overlay(v, 1, at))                         # (another stage's: not known yet)
        self.assertIsNone(liverally.overlay(running(me_next={}), 0, at))


class Page(Harness):
    def setUp(self):
        super().setUp()
        a = self.a
        sync = lambda target, daemon: mock.Mock(start=target)    # noqa: E731
        p = mock.patch('acr_daily.liverallyui.threading.Thread', side_effect=sync)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.liverallyui.settings.save')
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.liverallyui.photos.for_rally', side_effect=lambda r: (r or '').lower() or None)
        p.start()
        self.addCleanup(p.stop)
        a.dailies, a.active = {}, 1
        a._build_home_box()
        a._build_lr_box()
        a._side, a._main = tk.Frame(self.root), tk.Frame(self.root)
        a._side.pack(side='left')
        a._main.pack(side='left')
        a.api.live_rallies.return_value = INFO
        a.api.live_session.return_value = SIGNUP
        a.league_drive = mock.Mock()
        a._pick_car = lambda ev, name: a.s.setdefault('leagueCars', {}).__setitem__(str(ev['id']), name)

    def page(self):
        out = []

        def walk(w):
            out.extend(texts(w))
            for ch in w.winfo_children():
                if not isinstance(ch, tk.Canvas):
                    walk(ch)
        walk(self.a._lr_page)
        return out

    def label(self, text):
        """The last label on the page saying text (a series' card says SIGN UP too: the session's own comes after)."""
        found = []

        def walk(w):
            for ch in w.winfo_children():
                if isinstance(ch, tk.Label) and ch.cget('text') == text:
                    found.append(ch)
                walk(ch)
        walk(self.a._lr_page)
        return found[-1] if found else None

    def test_in_the_nav_and_on_home(self):
        a = self.a
        self.assertIn('live', a._tab_parts)
        a.nav('live')
        self.assertTrue(a.lr_view)
        self.assertEqual(self.underlined(), {'live': liverally.COLOUR})
        self.assertEqual(['pack' if w.winfo_manager() else '' for w in (a.lr_box, a.daily_box, a._side)], ['pack', '', ''])
        a.api.live_rallies.assert_called_once_with()
        a.api.live_session.assert_called_with('rally2', H)                     # the session open for sign-up, shown
        words = self.page()
        self.assertIn('RALLY2 LIVE  ·  %s  ·  WALES' % liverally.hm(H), words)
        self.assertIn('SIGN UP  ›', words)
        self.assertIn('1 signed up: Ann', words)
        a.show_tab('daily')                                                    # a tab: LIVE goes, the panel back
        self.assertEqual((a.lr_view, a.lr_box.winfo_manager(), a._side.winfo_manager()), (False, '', 'pack'))
        a.nav('home')
        spec = a._home_tiles['live'].spec
        self.assertEqual((spec['title'], spec['badge'][0], spec['photo']), ('LIVE', 'SIGN-UP OPEN', 'wales'))
        click(a._home_tiles['live'].cv)
        self.assertTrue(a.lr_view)

    def test_sign_up_with_a_car_of_the_class(self):
        a = self.a
        a.nav('live')
        click(self.label('Skoda Fabia RS Rally2'))                            # the car picked (remembered for the series)
        self.assertEqual(a.s['liveCars'], {'rally2': 'Skoda Fabia RS Rally2'})
        a.api.live_signup.return_value = a.api.live_session.return_value = dict(
            SIGNUP, me={'signedIn': True, 'signedUp': True, 'car': 'Skoda Fabia RS Rally2'})
        click(self.label('SIGN UP  ›'))
        a.api.live_signup.assert_called_once_with('rally2', H, 'Skoda Fabia RS Rally2')
        self.assertIn('✓ Signed up with the Skoda Fabia RS Rally2', self.page())
        a.api.live_withdraw.return_value = a.api.live_session.return_value = SIGNUP
        click(self.label('WITHDRAW'))
        a.api.live_withdraw.assert_called_once_with('rally2', H)
        self.assertIn('SIGN UP  ›', self.page())

    def test_drive_a_session_under_way(self):
        a = self.a
        a.api.live_session.return_value = running()
        a._lr_ready()
        a.lr_clock.offset_ms = H + 2 * MIN - __import__('time').time() * 1000    # (the server's clock: 08:02)
        a.nav('live')
        words = self.page()
        self.assertIn('SS1 START LIST', words)
        self.assertTrue(any(w.startswith('YOUR START  SS1  %s' % liverally.hms(H + 5 * MIN + 30000)) for w in words), words)
        self.assertIn('Me', words)
        self.assertEqual([e['id'] for e in a.league_events], [42])            # (among the app's events: DRIVE finds it)
        told = [c.kwargs.get('text', '') for c in a.sub_l.configure.call_args_list]   # (its rally out: said once)
        self.assertEqual(sum('The rally is out: press DRIVE on LIVE' in t for t in told), 1)
        click(self.label('DRIVE  ›'))
        a.league_drive.assert_called_once_with(42)
        self.assertEqual(a.s['leagueCars'], {'42': 'Skoda Fabia RS Rally2'})  # (the car signed up with)


class Following(unittest.TestCase):
    """The app following a session's stage (leagueui.py): the timer's countdown, the start on the server's clock, the
    next stage's slot at the finish, the ghost cars' room."""

    def app(self):
        from acr_daily.app import App
        a = App.__new__(App)
        a.s = {'token': 't', 'steamId': ME}
        a.api, a.root, a.sub_l = mock.Mock(), mock.Mock(), mock.Mock()
        a._league_init()
        a._lr_ready()
        ev = dict(EVENT, entry={'status': 'running', 'done': 0, 'totalMs': 0, 'car': 'Skoda Fabia RS Rally2'})
        a.league_events = [ev]
        car = {'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}
        a.league_run = {'ev': ev, 'car': car, 'no': 0, 'judge': Judge(__import__('acr_daily.leagues', fromlist=['x']).stage_ch(ev, 0, car)),
                        'known': None, 'ignore': None, 'wait': None}
        a.drive_target = 'league'
        a.lr_data[('rally2', H)] = running()
        return a

    def test_the_timer_counts_down_to_my_start(self):
        a = self.app()
        at = H + 5 * MIN + 30000
        a.lr_clock.offset_ms = at - 75_000 - __import__('time').time() * 1000
        status, sub, ov = a._league_overlay_state(None)
        self.assertEqual(ov[0], 'wait')
        self.assertAlmostEqual(ov[2], 75_000, delta=2000)                     # the time shown: the countdown
        self.assertIn('SS1 at %s' % liverally.hms(at), ov[4])
        a.lr_clock.offset_ms += 80_000
        self.assertEqual(a._league_overlay_state(None)[2][0], 'go')

    def test_the_start_goes_with_the_servers_time(self):
        a = self.app()
        a.lr_clock.offset_ms = 1500.0
        a._league_send = mock.Mock()
        a.league_run['judge']._start_wall = 1000.0              # (started_ms: 1 000 000)
        with mock.patch('acr_daily.leagueui.saveslot.read_save', side_effect=OSError):
            a.league_run['ev']['entry'] = None
            a._league_started(a.league_run)
        # (outside the event's rally here: not counted, nothing sent; in it, the start with serverAt)
        a._league_send.assert_not_called()
        with mock.patch('acr_daily.leagueui.saveslot.read_save', return_value=b''), \
                mock.patch('acr_daily.leagueui.leagues.known', return_value=None), \
                mock.patch('acr_daily.leagueui.rallyweekend.read_weekend', return_value={'stages': []}), \
                mock.patch('acr_daily.leagueui.leagues.same_calendar', return_value=True), \
                mock.patch('acr_daily.leagueui.leagues.changed_in_game', return_value=[]):
            a._league_started(a.league_run)
        item = a._league_send.call_args.args[0]
        self.assertEqual((item['kind'], item['at'], item['serverAt']), ('start', 1_000_000, 1_001_500))

    def test_the_next_slot_asked_at_the_finish(self):
        a = self.app()
        a.api.live_queue.return_value = {'now': H, 'slot': {'no': 1, 'at': H + 14 * MIN, 'moved': 0}}
        a._lr_poll = mock.Mock()                                           # (the session looked at again: not here)
        with mock.patch('acr_daily.liverallyui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)), \
                mock.patch('acr_daily.liverallyui._c') as c:
            c.return_value.ui = lambda w, fn, *x: fn(*x)
            a._lr_finished(a.league_run['ev'], 0)
        self.assertEqual(a.api.live_queue.call_args.args[:3], ('rally2', H, 1))
        self.assertEqual(a.lr_data[('rally2', H)]['me']['next']['at'], H + 14 * MIN)
        self.assertEqual(a._lr_queue_want, {})
        a._lr_finished(a.league_run['ev'], 2)                                # (the last stage: nothing to queue for)
        self.assertEqual(a._lr_queue_want, {})

    def test_the_ghost_cars_room(self):
        a = self.app()
        link = mock.Mock(room=None)
        a.ghostcars = mock.Mock(live=link)
        a._lr_room()
        self.assertEqual(link.room, 'live:42')
        a.league_run['over'] = True
        a._lr_room()
        self.assertIsNone(link.room)


if __name__ == '__main__':
    unittest.main()
