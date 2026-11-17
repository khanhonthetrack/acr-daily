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
        'series': [{'key': 'rally2', 'name': 'Rally2', 'carClass': 'Rally2/R5', 'cars': CARS, 'rally': 'Wales',
                    'nextRally': 'Alsace', 'everyHours': 4},
                   {'key': 'classic', 'name': 'Group 4 Classics', 'carClass': 'H1', 'cars': [], 'rally': 'Alsace',
                    'nextRally': 'Greece', 'everyHours': 4}],
        'sessions': [{'series': 'rally2', 'starts': H, 'signupOpens': H - 30 * MIN, 'firstStart': H + 5 * MIN, 'closes': H + 105 * MIN,
                      'phase': 'signup', 'rally': 'Wales', 'signups': 1, 'signedUp': False, 'car': None, 'eventId': None, 'entry': None},
                     {'series': 'classic', 'starts': H + 120 * MIN, 'signupOpens': H + 90 * MIN, 'firstStart': H + 125 * MIN,
                      'closes': H + 225 * MIN, 'phase': 'upcoming', 'rally': 'Alsace', 'signups': 0, 'signedUp': False,
                      'car': None, 'eventId': None, 'entry': None}]}
SIGNUP = {'now': H - 10 * MIN, 'phase': 'signup', 'starts': H, 'signupOpens': H - 30 * MIN, 'firstStart': H + 5 * MIN,
          'closes': H + 105 * MIN, 'rally': 'Wales', 'entrants': [{'steamId': '7', 'name': 'Ann', 'car': 'VW Polo GTI R5'}],
          'me': {'signedIn': True, 'signedUp': False, 'car': None}, 'pollS': 30}
EVENT = {'id': 42, 'kind': 'live', 'series': 'rally2', 'sessionStarts': H, 'name': 'Rally2 · Wales · 08:00 UTC',
         'league': 'Rally2', 'rally': 'Wales', 'carClass': 'Rally2/R5', 'cars': [dict(c, cls='Rally2/R5') for c in CARS],
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
    def test_on_only_in_a_test_build(self):
        import importlib
        from acr_daily import updater
        self.assertTrue(updater.is_test_build('0.1.5.32'))
        for version, env, on in (('0.1.5.32', None, True), ('0.1.6', None, False), ('0.1.6', '1', True)):
            with mock.patch('acr_daily.__version__', version), mock.patch.dict(os.environ, {'ACR_DAILY_LIVE': env} if env else {}):
                if not env:
                    os.environ.pop('ACR_DAILY_LIVE', None)
                self.assertEqual(importlib.reload(liverally).ON, on, version)
        importlib.reload(liverally)

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
        self.assertEqual(liverally.card_line(INFO['sessions'][0], now), 'Registration open · starts in 10:00 · 1 registered')
        self.assertEqual(liverally.card_line(INFO['sessions'][1], now), 'Registration opens in 1:40:00')

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


def info_with(**row):
    """INFO with the first session (Rally2, 08:00) as given."""
    return dict(INFO, sessions=[dict(INFO['sessions'][0], **row)] + INFO['sessions'][1:])


class Bar(unittest.TestCase):
    """The registration bar along the bottom (liverally.bar_state), as iRacing's: what it says as the session goes."""

    def state(self, info, view=None, now=H - 10 * MIN, **kw):
        return liverally.bar_state(info, {('rally2', H): view} if view else {}, now, name_of=lambda k: {'rally2': 'Rally2'}[k],
                                   me_id=ME, **kw)

    def test_from_registered_to_the_result(self):
        self.assertIsNone(self.state(INFO))                                         # not registered: no bar
        st = self.state(info_with(signedUp=True, signups=3))
        self.assertEqual((st['chip'], st['label'], st['time'], st['button']), ('REGISTERED', 'STARTS IN', '10:00', ('WITHDRAW', 'withdraw')))
        self.assertEqual(st['words'], 'Rally2 · %s · Wales  ·  3 registered' % liverally.hm(H))
        on = info_with(signedUp=True, phase='running')
        at = H + 5 * MIN + 30000
        st = self.state(on, running(), now=H + MIN)                                 # the rally is out: DRIVE
        self.assertEqual((st['chip'], st['button'], st['time']), ('READY', ('DRIVE', 'drive'), '4:30'))
        st = self.state(on, running(), now=H + MIN, follow=('rally2', H))           # followed: START SS1
        self.assertEqual((st['chip'], st['button']), ('SS1', ('START SS1', 'arm')))
        self.assertIn('press START SS1, then go', st['words'])
        st = self.state(on, running(), now=at - 2000, follow=('rally2', H), armed=(42, 0))
        self.assertEqual((st['chip'], st['button'], st['time'], st['tone']), ('SS1', None, 'GO', 'good'))
        self.assertEqual(self.state(on, running(), now=at + 1000, follow=('rally2', H), driving=0)['words'][-8:], 'on stage')
        done = running()
        done['event'] = dict(EVENT, entry={'status': 'finished', 'done': 3, 'totalMs': 1_100_000})
        done['standings'] = [{'steamId': '7', 'rank': 1, 'status': 'finished'}, {'steamId': ME, 'rank': 2, 'status': 'finished'}]
        st = self.state(on, done, now=H + 40 * MIN)
        self.assertEqual((st['chip'], st['label'], st['button']), ('FINISHED', 'P2 of 2', ('RESULTS', 'view')))
        self.assertIn('18:20.000', st['words'])
        dnf = running()
        dnf['event'] = dict(EVENT, entry={'status': 'dnf', 'reason': 'SS1 started without START SS1'})
        self.assertEqual(self.state(on, dnf, now=H + 9 * MIN)['chip'], 'DNF')
        out = running(me_next={})
        out['me']['out'] = {'no': 0, 'moved': 3}
        self.assertEqual(self.state(on, out, now=H + 9 * MIN)['words'][-29:], 'you missed your start 4 times')
        self.assertIsNone(self.state(info_with(signedUp=True, phase='over'), running(), now=H + 2 * 3600000))


def queue_view():
    """SS2's queue: Kalle finished, Ann on it, me next but one after Ott (waiting), Sam's start just now, Dan out."""
    q = lambda sid, name, at, state, **k: dict({'steamId': sid, 'name': name, 'car': 'Skoda', 'at': at, 'moved': 0,   # noqa: E731
                                                'started': H if state in ('done', 'driving') else None, 'penaltyMs': 0,
                                                'state': state, 'timeMs': None}, **k)
    s2 = [q('8', 'Kalle R.', H + 14 * MIN, 'done', timeMs=365_900), q('7', 'Ann', H + 14 * MIN + 30000, 'driving'),
          q('11', 'Dan', H + 15 * MIN, 'dns'), q('10', 'Ott T.', H + 15 * MIN + 30000, 'waiting'),
          q(ME, 'Me', H + 16 * MIN, 'waiting'), q('12', 'Sam', H + 16 * MIN + 30000, 'waiting')]
    return running(queues=[[], s2, []], me_next={'no': 1, 'at': H + 16 * MIN, 'moved': 0, 'started': None, 'penaltyMs': 0,
                                                    'out': None})


class TimerQueue(unittest.TestCase):
    """The timer window's queue (liverally.overlay_queue): the whole of my next stage's, in start order."""

    def test_every_driver_in_start_order_with_what_they_are_at(self):
        now = H + 15 * MIN + 10_000
        q = liverally.overlay_queue(queue_view(), 1, ME, now)
        self.assertEqual(q['title'], 'SS2 QUEUE · 5')                    # (Dan: out of it, not listed)
        self.assertEqual([r[1:] for r in q['rows']], [
            ('Kalle R.', '6:05.900', 'done', False), ('Ann', 'on stage', 'live', False),
            ('Ott T.', 'in 0:20', 'wait', False), ('Me', 'in 0:50', 'wait', True), ('Sam', 'in 1:20', 'wait', False)])
        self.assertEqual(q['rows'][3][0], liverally.hms(H + 16 * MIN))
        self.assertEqual(q['right'], '1 AHEAD OF YOU')                     # (Ott: not started yet)
        q = liverally.overlay_queue(queue_view(), 1, ME, H + 15 * MIN + 40_000)
        self.assertEqual([r[2:4] for r in q['rows'][2:4]], [('GO', 'go'), ('in 0:20', 'wait')])
        q = liverally.overlay_queue(queue_view(), 1, ME, H + 16 * MIN + 31_000)
        self.assertEqual((q['rows'][3][2:4], q['right']), (('late', 'late'), 'LATE'))
        v = queue_view()
        v['queues'][1][3]['state'], v['queues'][1][3]['started'] = 'driving', H
        self.assertEqual(liverally.overlay_queue(v, 1, ME, now)['right'], "YOU'RE NEXT")

    def test_none_while_i_am_not_on_its_list(self):
        self.assertIsNone(liverally.overlay_queue(queue_view(), 2, ME, H))
        self.assertIsNone(liverally.overlay_queue(queue_view(), 1, '999', H))
        self.assertIsNone(liverally.overlay_queue({}, 0, ME, H))

    def test_a_very_long_one_keeps_me_in_it(self):
        v = queue_view()
        v['queues'][1] = [dict(v['queues'][1][-1], steamId=str(100 + i), name='D%d' % i, at=H + 20 * MIN + i * 30000)
                          for i in range(liverally.QUEUE_ROWS + 9)] + [dict(v['queues'][1][4], at=H + 60 * MIN)]
        q = liverally.overlay_queue(v, 1, ME, H)
        self.assertEqual(len(q['rows']), liverally.QUEUE_ROWS)
        self.assertTrue(q['rows'][-2][4])                                  # me, last but one
        self.assertEqual(q['rows'][-1][1], '+11 more')


@unittest.skipUnless(liverally.ON, 'LIVE: the test builds only (ACR_DAILY_LIVE=1 from the source)')
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
        a._build_lr_bar(self.root)
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
        self.assertEqual(a._tab_parts['live'][0].cget('text'), 'RANKED')
        a.nav('live')
        self.assertTrue(a.lr_view)
        self.assertEqual(self.underlined(), {'live': liverally.COLOUR})
        self.assertEqual(['pack' if w.winfo_manager() else '' for w in (a.lr_box, a.daily_box, a._side)], ['pack', '', ''])
        a.api.live_rallies.assert_called_once_with()
        a.api.live_session.assert_called_with('rally2', H)                     # the session open for registration, shown
        words = self.page()
        for w in ('RANKED', 'RALLY2', 'REGISTER  ›', 'This week  Wales   ·   next week  Alsace', 'OPENS 09:30',
                  'RALLY2  ·  %s  ·  WALES' % liverally.hm(H), 'REGISTRATION OPEN', '1   R E G I S T E R E D', 'Ann'):
            self.assertIn(w, words)
        a.show_tab('daily')                                                    # a tab: RANKED goes, the panel back
        self.assertEqual((a.lr_view, a.lr_box.winfo_manager(), a._side.winfo_manager()), (False, '', 'pack'))
        a.nav('home')
        spec = a._home_tiles['live'].spec
        self.assertEqual((spec['title'], spec['badge'][0], spec['photo']), ('RANKED', 'REGISTRATION OPEN', 'wales'))
        click(a._home_tiles['live'].cv)
        self.assertTrue(a.lr_view)

    def test_register_with_a_car_and_the_bar(self):
        a = self.a
        a.nav('live')
        self.assertIsNotNone(self.label('VW Polo GTI R5  ▾'))                   # the class's first car, until one is picked
        a.lr_pick_car('rally2', 'Skoda Fabia RS Rally2')
        self.assertEqual(a.s['liveCars'], {'rally2': 'Skoda Fabia RS Rally2'})
        self.assertIsNotNone(self.label('Skoda Fabia RS Rally2  ▾'))
        self.assertEqual(a.lr_bar.winfo_manager(), '')                          # (not registered: no bar)
        a.api.live_signup.return_value = a.api.live_session.return_value = dict(
            SIGNUP, me={'signedIn': True, 'signedUp': True, 'car': 'Skoda Fabia RS Rally2'})
        a.api.live_rallies.return_value = info_with(signedUp=True, signups=2)
        click(self.label('REGISTER  ›'))
        a.api.live_signup.assert_called_once_with('rally2', H, 'Skoda Fabia RS Rally2')
        self.assertIn('✓ Registered with the Skoda Fabia RS Rally2', self.page())
        a._lr_bar_render()                                                     # the bar, along the bottom in every view
        self.assertEqual(a.lr_bar.winfo_manager(), 'pack')
        self.assertEqual((a.lr_bar_chip.cget('text'), a.lr_bar_button.cget('text')), ('REGISTERED', 'WITHDRAW'))
        a.api.live_withdraw.return_value = a.api.live_session.return_value = SIGNUP
        a.api.live_rallies.return_value = INFO
        click(a.lr_bar_button)
        a.api.live_withdraw.assert_called_once_with('rally2', H)
        a._lr_bar_render()
        self.assertEqual(a.lr_bar.winfo_manager(), '')
        self.assertIn('REGISTER  ›', self.page())

    def test_your_rally_is_ready(self):
        """At the hour: the card over everything with DRIVE and the time left, the bar READY, the start list."""
        a = self.a
        a.api.live_session.return_value = running()
        a.api.live_rallies.return_value = info_with(signedUp=True, phase='running')
        a._lr_ready()
        a.lr_clock.offset_ms = H + 2 * MIN - __import__('time').time() * 1000    # (the server's clock: 08:02)
        a.nav('live')
        card = a._lr_cards['ready']
        self.assertEqual(card.go_b.cget('text'), 'DRIVE  ›')
        self.assertTrue(card.cd_words.cget('text').startswith('Your start  SS1  %s' % liverally.hms(H + 5 * MIN + 30000)))
        self.assertEqual(card.cd_time.cget('text'), '4:30')                    # (the server's clock: its answer, 08:01)
        self.assertGreater(card.deadline - __import__('time').monotonic(), 230)   # (to the end of my start's window)
        words = self.page()
        self.assertIn('START LIST', words)
        self.assertIn('your rally is ready · SS1 at %s' % liverally.hms(H + 5 * MIN + 30000), words)
        self.assertEqual([e['id'] for e in a.league_events], [42])            # (among the app's events: DRIVE finds it)
        a._lr_bar_render()
        self.assertEqual((a.lr_bar_chip.cget('text'), a.lr_bar_button.cget('text')), ('READY', 'DRIVE  ›'))
        card._go()                                                             # DRIVE on the card
        a.league_drive.assert_called_once_with(42)
        self.assertEqual(a.s['leagueCars'], {'42': 'Skoda Fabia RS Rally2'})  # (the car registered with)
        a._lr_poll(('rally2', H))
        self.assertNotIn('ready', a._lr_cards)                                 # (once)
        out = running(me_next={})                                              # out (missed too often): no DRIVE
        out['me']['out'] = {'no': 0, 'at': H + 9 * MIN, 'moved': 3, 'out': 'dns'}
        a.api.live_session.return_value = out
        a._lr_poll(('rally2', H))
        self.assertIsNone(self.label('DRIVE  ›'))
        self.assertIn('you missed your start 4 times', self.page())


    def test_start_ssn_on_the_start_line(self):
        """Following the session, on SS1's start line, START SS1 not pressed: its card under the timer; pressed, it goes and
        the next start counts."""
        a = self.a
        a.api.live_session.return_value = running()
        a.api.live_rallies.return_value = info_with(signedUp=True, phase='running')
        a._lr_ready()
        a.refresh_live_rallies()
        for card in list(a._lr_cards.values()):
            card.close()
        ev = dict(a.lr_data[('rally2', H)]['event'], entry=None)
        car = {'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}
        j = Judge(__import__('acr_daily.leagues', fromlist=['x']).stage_ch(ev, 0, car))
        a.league_run, a.drive_target = {'ev': ev, 'car': car, 'no': 0, 'judge': j, 'known': None, 'ignore': None, 'wait': None}, 'league'
        a._lr_cards_tick()
        self.assertNotIn('start', a._lr_cards)                                 # (not on its start line yet)
        j.state = 'armed'                                                      # on SS1's start line
        a._lr_cards_tick()
        card = a._lr_cards['start']
        self.assertEqual(card.go_b.cget('text'), 'START SS1  ›')
        card._go()
        self.assertEqual(a._lr_armed, (42, 0))
        a._lr_cards_tick()
        self.assertNotIn('start', a._lr_cards)                                 # (pressed: no card)
        a._lr_bar_render()
        self.assertEqual((a.lr_bar_chip.cget('text'), a.lr_bar_button.winfo_manager()), ('SS1', ''))


class Following(unittest.TestCase):
    """The app following a session's stage (leagueui.py): the timer's countdown, the start on the server's clock, the
    next stage's slot at the finish, the ghost cars' room."""

    def app(self):
        from acr_daily.app import App
        a = App.__new__(App)
        a.s = {'token': 't', 'steamId': ME}
        a.api, a.root, a.sub_l = mock.Mock(), mock.Mock(), mock.Mock()
        a.dailies = {}
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
        self.assertEqual(ov[4], 'Press START SS1 first · your start %s' % liverally.hms(at))   # (not pressed yet: red)
        a._lr_armed = (42, 0)
        self.assertIn('SS1 at %s' % liverally.hms(at), a._league_overlay_state(None)[2][4])
        a.lr_clock.offset_ms += 80_000
        self.assertEqual(a._league_overlay_state(None)[2][0], 'go')

    def test_the_start_goes_with_the_servers_time(self):
        a = self.app()
        a.lr_clock.offset_ms, a.lr_clock.known = 1500.0, True
        a._league_send = mock.Mock()
        a.league_run['judge']._start_wall = 1000.0              # (started_ms: 1 000 000)
        a.league_run['ev']['entry'] = None
        a._lr_armed = (42, 0)                                    # START SS1 pressed
        with mock.patch('acr_daily.leagueui.saveslot.read_save', return_value=b''), \
                mock.patch('acr_daily.leagueui.leagues.known', return_value=None), \
                mock.patch('acr_daily.leagueui.rallyweekend.read_weekend', return_value={'stages': []}), \
                mock.patch('acr_daily.leagueui.leagues.same_calendar', return_value=True), \
                mock.patch('acr_daily.leagueui.leagues.changed_in_game', return_value=[]):
            a._league_started(a.league_run)
        item = a._league_send.call_args.args[0]
        self.assertEqual((item['kind'], item['at'], item['serverAt']), ('start', 1_000_000, 1_001_500))
        self.assertIsNone(a._lr_armed)                           # (used up)

    def test_a_start_without_start_ssn_is_a_dnf(self):
        """On the stage, followed, START SS1 not pressed: practice on a ranked stage, a DNF (one run, one mode)."""
        a = self.app()
        a._lr_out, a._league_send = mock.Mock(), mock.Mock()
        a._lr_armed = (42, 1)                                    # (pressed for another stage: not this one)
        a._league_started(a.league_run)
        self.assertEqual(a._lr_out.call_args.args[1:], (0, 'SS1 started without START SS1'))
        a._league_send.assert_not_called()

    def test_start_ssn_and_a_dailys_start_official_rally_one_at_a_time(self):
        a = self.app()
        a.lr_drive = mock.Mock()
        a.dailies = {1: {'committed': {'date': 'x'}}}
        a.lr_clock.offset_ms = H + MIN - __import__('time').time() * 1000
        a.lr_arm(('rally2', H))
        self.assertEqual((a._lr_armed, a.dailies[1]['committed']), ((42, 0), None))
        self.assertIn('SS1 counts for ranked', a.sub_l.configure.call_args.kwargs['text'])
        a._lr_disarm()                                           # (app.commit: START OFFICIAL RALLY on a daily)
        self.assertIsNone(a._lr_armed)
        a.drive_target = 'daily'                                 # not following the session: START SS1 is DRIVE first
        a.lr_arm(('rally2', H))
        a.lr_drive.assert_called_once_with(('rally2', H))
        self.assertIsNone(a._lr_armed)

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

    def test_out_of_the_session(self):
        """Missed my start too often (the server took me out of the queue): the timer says so, no countdown."""
        a = self.app()
        a.lr_data[('rally2', H)]['me'].update(next=None, out={'no': 0, 'at': H + 9 * MIN, 'moved': 3, 'out': 'dns'})
        status, sub, ov = a._league_overlay_state(None)
        self.assertEqual((ov[0], ov[4]), ('dnf', 'OUT · you missed your start 4 times'))
        self.assertIsNone(a._lr_overlay_queue())

    def test_the_queue_under_the_countdown(self):
        a = self.app()
        a.lr_data[('rally2', H)] = queue_view()
        a.lr_clock.offset_ms = H + 15 * MIN - __import__('time').time() * 1000
        a.league_run['no'] = 0
        self.assertIsNone(a._lr_overlay_queue())                         # (on SS1: my start known is SS2's)
        a.league_run['wait'] = {'id': 'x'}                                # SS1 finished, its official time on its way
        q = a._lr_overlay_queue()
        self.assertEqual((q['title'], len(q['rows'])), ('SS2 QUEUE · 5', 5))
        a.league_run.update(wait=None, no=1)                              # on SS2's start line
        self.assertEqual(a._lr_overlay_queue()['title'], 'SS2 QUEUE · 5')
        a.league_run['judge'].state = 'running'                           # driving: the timer's own
        self.assertIsNone(a._lr_overlay_queue())
        a.league_run['judge'].state = 'armed'
        a.drive_target = 'daily'
        self.assertIsNone(a._lr_overlay_queue())

    def test_the_timer_window_draws_it(self):
        from acr_daily import app as app_mod
        from test_app import tk_root
        root = tk_root()
        self.addCleanup(root.destroy)
        o = app_mod.Overlay(mock.Mock(root=root, s={'overlay': {}}))
        q = liverally.overlay_queue(queue_view(), 1, ME, H + 15 * MIN + 10_000)
        o.show_queue(q)
        root.update_idletasks()
        self.assertEqual(o.queue.winfo_manager(), 'pack')
        self.assertEqual((o.q_title.cget('text'), o.q_right.cget('text')), ('SS2 QUEUE · 5', '1 AHEAD OF YOU'))
        self.assertEqual([[w.cget('text') for w in r] for r in o.q_rows][3][1:], ['YOU', 'in 0:50'])
        self.assertEqual(o.q_rows[3][1].cget('fg'), app_mod.ACC_TEXT)
        self.assertEqual(o.q_rows[1][2].cget('fg'), liverally.COLOUR)      # (on stage)
        short = dict(q, rows=q['rows'][:2])                                # a shorter one: the other rows put away
        o.show_queue(short)
        self.assertEqual([bool(r[0].winfo_manager()) for r in o.q_rows], [True, True, False, False, False])
        o.show_queue(None)
        self.assertEqual(o.queue.winfo_manager(), '')

    def sync(self, a):
        """Threads run there and then, what goes to the Tk thread done at once (the session not asked for again)."""
        a._lr_poll = mock.Mock()
        for p in (mock.patch('acr_daily.liverallyui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)),
                  mock.patch('acr_daily.liverallyui._c')):
            m = p.start()
            self.addCleanup(p.stop)
        m.return_value.ui = lambda w, fn, *x: fn(*x)

    def frame(self, clock, track='Wales Stage 1', x=0.0, z=0.0):
        from acr_daily.telemetry import Frame
        return Frame(0.0, 1, clock, x, z, 50.0, 'Skoda Fabia RS Rally2', track)

    def start_on(self, a, track, x=0.0, judges=lambda: None):
        a._lr_watching = a._lr_watch_list()
        a._lr_watch(self.frame(0, track, x))                  # on its start line, the clock at 0
        a._lr_watch(self.frame(120, track, x))               # ...then running
        judges()                                              # (every mode's judge sees that frame)
        a._lr_watch(self.frame(170, track, x))               # decided on the next frame

    def test_a_stage_driven_before_its_start_is_a_dnf(self):
        """SS2 driven (any mode) while I am due on SS1: out of the rally, here and on the server."""
        a = self.app()
        self.sync(a)
        a._notify = mock.Mock()
        self.start_on(a, 'Wales Stage 1')
        a.api.live_out.assert_called_once_with('rally2', H, 1, 'SS2 driven outside the rally, before its start')
        self.assertEqual((a.league_run['over'], a.drive_target, a.league_run['ev']['entry']['status']), (True, 'daily', 'dnf'))
        self.assertIn('In a ranked rally every start on its stages counts', a.sub_l.configure.call_args.kwargs['text'])
        a._notify.assert_called_once()
        self.assertEqual(a._lr_outed[('rally2', H)][2:], [])                # (sent: not again)
        self.start_on(a, 'Wales Stage 2')                                  # (out already: nothing more)
        a.api.live_out.assert_called_once()

    def test_not_following_yet_it_counts_too(self):
        a = self.app()
        self.sync(a)
        a._notify = mock.Mock()
        a.league_run, a.drive_target = None, 'daily'                        # (DRIVE not pressed yet)
        self.start_on(a, 'Wales Stage 0')
        self.assertEqual(a.api.live_out.call_args.args[2:], (0, 'SS1 driven outside the rally, before its start'))

    def test_the_counted_run_another_stage_and_a_counted_one_again(self):
        a = self.app()
        self.sync(a)
        a._notify = mock.Mock()
        a.league_run['judge'].state = 'running'                            # SS1: the judge took its start (leagueui.py)
        self.start_on(a, 'Wales Stage 0')
        self.start_on(a, 'Wales Stage 1', x=5000.0)                        # another stage of that name: far from its start
        self.start_on(a, 'Alsace Somewhere')
        a.league_run['ev']['entry']['done'] = 2                            # SS1 and SS2 counted, the game took its rally back
        a.league_run['no'] = 2
        a.league_run['judge'].state = 'armed'
        self.start_on(a, 'Wales Stage 0')                                  # SS1 again: changes nothing
        a.api.live_out.assert_not_called()

    def test_outside_the_sessions_rally_weekend_or_its_settings_changed(self):
        """Followed, but not in the session's Rally Weekend (the wrong mode, another rally) or with its settings changed in
        the game's menus: a DNF, not a run that just doesn't count."""
        for same, changed, why in ((False, [], "SS1 driven outside the session's Rally Weekend"),
                                   (True, ['weather'], "the session's weather changed in the game")):
            a = self.app()
            a._lr_out, a._league_send = mock.Mock(), mock.Mock()
            a.league_run['ev']['entry'] = None
            a._lr_armed = (42, 0)                                            # (START SS1 pressed: then the rally's checks)
            with mock.patch('acr_daily.leagueui.saveslot.read_save', return_value=b''), \
                    mock.patch('acr_daily.leagueui.leagues.known', return_value=None), \
                    mock.patch('acr_daily.leagueui.rallyweekend.read_weekend', return_value={'stages': []}), \
                    mock.patch('acr_daily.leagueui.leagues.same_calendar', return_value=same), \
                    mock.patch('acr_daily.leagueui.leagues.changed_in_game', return_value=changed):
                a._league_started(a.league_run)
            self.assertEqual(a._lr_out.call_args.args[1:], (0, why))
            a._league_send.assert_not_called()
        a = self.app()                                                       # the save not readable now: counted
        a._lr_out, a._league_send = mock.Mock(), mock.Mock()
        a.league_run['ev']['entry'] = None
        a._lr_armed = (42, 0)
        with mock.patch('acr_daily.leagueui.saveslot.read_save', side_effect=OSError):
            a._league_started(a.league_run)
        a._lr_out.assert_not_called()
        self.assertEqual(a._league_send.call_args.args[0]['kind'], 'start')

    def test_a_dailys_or_the_time_trials_run_on_a_ranked_stage_is_fine(self):
        """The daily or the time trial on a stage of the session (the draw takes any stage): their counted runs are theirs,
        no DNF in ranked; the daily driven without START OFFICIAL RALLY is practice, and that on a ranked stage is one."""
        a = self.app()
        self.sync(a)
        a._notify = mock.Mock()
        a.league_run, a.drive_target = None, 'daily'                       # (the daily's DRIVE: the app on the dailies)
        j = Judge({'id': 'd/1', 'slot': 1, 'track': 'Wales Stage 1', 'car': 'VW Polo GTI R5', 'route': [[0, 0], [100, 0]]})
        d = a.dailies[1] = {'ch': {}, 'judge': j, 'norally': False, 'practice': False}
        self.start_on(a, 'Wales Stage 1', judges=lambda: setattr(j, 'state', 'running'))   # its counted run: fine
        a.api.live_out.assert_not_called()
        d['norally'] = True                                                # START OFFICIAL RALLY not pressed: practice
        j.state = 'armed'
        self.start_on(a, 'Wales Stage 1', judges=lambda: setattr(j, 'state', 'running'))
        self.assertEqual(a.api.live_out.call_args.args[2], 1)
        b = self.app()                                                     # the time trial's run on SS3
        self.sync(b)
        b._notify = mock.Mock()
        b.league_run, b.drive_target = None, 'tt'
        tj = Judge({'id': 'tt:w/1', 'track': 'Wales Stage 2', 'car': 'VW Polo GTI R5', 'route': [[0, 0], [100, 0]]})
        b._tt = {1: {'ch': {}, 'judge': tj, 'entered': True}}
        self.start_on(b, 'Wales Stage 2', judges=lambda: setattr(tj, 'state', 'running'))
        b.api.live_out.assert_not_called()

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
