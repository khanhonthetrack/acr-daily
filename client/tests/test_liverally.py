"""Ranked rallies in the app: the logic (liverally.py: the server's clock, my turn as it stands, the queues and the
results as listed, the session shown first, the timer's words, the turn window's) and the RANKED page (liverallyui.py:
in the nav and on HOME, registering, DRIVE through the leagues', the turn window over the game, each start sent with
the server's time, the next stage's queue joined at the finish, the results page and "your results are out", the ghost
cars' room). On a Tk window that is never shown; the server faked."""
import os
import sys
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import liverally, rankedgate  # noqa: E402
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


TURN = H + 5 * MIN                         # the first turn: Ann's (best rated), then mine


def qrow(sid, name, state, **k):
    return dict({'steamId': sid, 'name': name, 'car': 'Skoda', 'at': k.get('estAt') or H, 'readyAt': TURN, 'turnAt': None,
                 'deadline': None, 'estAt': None, 'ahead': 0, 'moved': 0, 'started': None, 'penaltyMs': 0, 'state': state,
                 'timeMs': None}, **k)


def nxt(**k):
    """My next turn as the server says it (me.next)."""
    return dict({'no': 0, 'state': 'break', 'at': TURN + 20000, 'readyAt': TURN, 'turnAt': None, 'deadline': None,
                 'estAt': TURN + 20000, 'ahead': 1, 'moved': 0, 'started': None, 'penaltyMs': 0, 'out': None}, **k)


def running(me_next=None, queues=None):
    """At 08:01: the start list out, Ann's turn first at 08:05, then mine."""
    return {'now': H + MIN, 'phase': 'running', 'starts': H, 'signupOpens': H - 30 * MIN, 'firstStart': TURN,
            'closes': H + 105 * MIN, 'rally': 'Wales', 'eventId': 42, 'event': dict(EVENT), 'entrants': 2,
            'queues': queues or [[qrow('7', 'Ann', 'break', estAt=TURN, ahead=0),
                                  qrow(ME, 'Me', 'break', estAt=TURN + 20000, ahead=1)], [], []],
            'standings': [], 'pollS': 10, 'resultsOut': False, 'live': {'turnS': 20, 'breakS': 180},
            'me': {'signedIn': True, 'signedUp': True, 'car': 'Skoda Fabia RS Rally2',
                   'next': me_next if me_next is not None else nxt()}}


def turns_view(now_turn='7'):
    """SS1 under way: Ann's turn (08:05:00, to :20) or mine, then Ott's; Kalle on stage, Dan out."""
    q = [qrow('8', 'Kalle R.', 'driving', started=TURN - 30000, turnAt=TURN - 30000),
         qrow('7', 'Ann', 'turn' if now_turn == '7' else 'driving', turnAt=TURN, deadline=TURN + 20000, estAt=TURN,
              **({'started': TURN + 3000} if now_turn != '7' else {})),
         qrow(ME, 'Me', 'turn' if now_turn == ME else 'waiting', ahead=0 if now_turn == ME else 1,
              turnAt=TURN + 3000 if now_turn == ME else None, deadline=TURN + 23000 if now_turn == ME else None,
              estAt=TURN + 3000 if now_turn == ME else TURN + 20000),
         qrow('10', 'Ott T.', 'waiting', ahead=1 if now_turn == ME else 2, estAt=TURN + 40000 if now_turn != ME else TURN + 23000),
         qrow('11', 'Dan', 'dns', moved=3)]
    me = q[2]
    v = running(queues=[q, [], []], me_next=nxt(state=me['state'], at=me['estAt'], turnAt=me['turnAt'], deadline=me['deadline'],
                                                  estAt=me['estAt'], ahead=me['ahead']))
    return v


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

    def test_my_turn_as_it_stands(self):
        self.assertEqual([liverally.left(ms) for ms in (0, 999, 42_000, 725_000, 3_723_000)], ['0:00', '0:01', '0:42', '12:05', '1:02:03'])
        st = liverally.my_start(running(), H + MIN)                              # before the first turn: getting ready
        self.assertEqual((st['phase'], st['left'], st['ahead']), ('break', 4 * MIN, 1))
        st = liverally.my_start(turns_view(), TURN + 5000)                       # Ann's turn: me next, at most 15 s
        self.assertEqual((st['phase'], st['left'], st['ahead']), ('wait', 15000, 1))
        st = liverally.my_start(turns_view(ME), TURN + 8000)                     # mine: 15 s left
        self.assertEqual((st['phase'], st['left']), ('turn', 15000))
        self.assertEqual(liverally.my_start(turns_view(ME), TURN + 24000)['phase'], 'late')   # (gone by, not asked since)
        self.assertIsNone(liverally.my_start(running(me_next={}), TURN))

    def test_the_queues_and_the_standings_as_listed(self):
        rows = liverally.queue_rows(turns_view(), 0, ME)
        self.assertEqual([(r[0], r[1], r[3], r[4], r[5]) for r in rows], [
            (liverally.hms(TURN - 30000), 'Kalle R.', 'on stage', 'live', False), ('NOW', 'Ann', 'their turn', 'good', False),
            ('≤ ' + liverally.hms(TURN + 20000), 'Me', 'waiting', 'soft', True),
            ('≤ ' + liverally.hms(TURN + 40000), 'Ott T.', 'waiting', 'soft', False),
            ('', 'Dan', 'did not start  ·  missed 3 turns', 'muted', False)])
        v = running(queues=[[qrow('7', 'Ann', 'done', started=TURN, timeMs=372000, penaltyMs=5000)], [], []])
        self.assertEqual(liverally.queue_rows(v, 0)[0][3], '6:12.000  ·  jump start +5 s')
        self.assertEqual(liverally.queue_rows(running(), 0)[0][3], 'waiting')   # (SS1 before its first turn)
        self.assertEqual(liverally.queue_rows(v, 2), [])
        self.assertEqual(liverally.queue_rows({}, 1), [])
        v['standings'] = [{'steamId': '7', 'name': 'Ann', 'car': 'VW', 'status': 'finished', 'totalMs': 1_100_000, 'rank': 1},
                          {'steamId': ME, 'name': 'Me', 'car': 'Skoda', 'status': 'running', 'done': 1, 'rank': None}]
        self.assertEqual(liverally.standings_rows(v, ME), [('1', 'Ann', 'VW', '18:20.000', '', False),
                                                           ('–', 'Me', 'Skoda', 'SS2 of 3', '', True)])

    def test_the_results_as_listed(self):
        v = running()
        st = lambda t, pos, pen=0: {'totalMs': t, 'pos': pos, 'stewardMs': pen}   # noqa: E731
        v['standings'] = [
            {'steamId': '7', 'name': 'Ann', 'car': 'VW', 'status': 'finished', 'rank': 1, 'totalMs': 1_100_000,
             'stages': [st(372_000, 1), st(360_000, 2), st(368_000, 1)]},
            {'steamId': ME, 'name': 'Me', 'car': 'Skoda', 'status': 'finished', 'rank': 2, 'totalMs': 1_105_000, 'gapMs': 5000,
             'stages': [st(380_000, 2, 5000), st(355_000, 1), st(370_000, 2)]},
            {'steamId': '9', 'name': 'Bo', 'car': 'Fabia', 'status': 'dnf', 'reason': 'restarted SS2', 'done': 1,
             'stages': [st(390_000, 3), None, None]}]
        rows = liverally.results_rows(v, ME)
        self.assertEqual([(r['pos'], r['name'], r['total'], r['gap'], r['mine']) for r in rows],
                         [('1', 'Ann', '18:20.000', '', False), ('2', 'Me', '18:25.000', '+0:05.000', True), ('–', 'Bo', 'DNF', '', False)])
        self.assertEqual(rows[1]['stages'], [('6:20.000', 'P2  +5 s jump'), ('5:55.000', 'P1'), ('6:10.000', 'P2')])
        self.assertEqual((rows[2]['stages'][1], rows[2]['reason']), (('–', ''), 'restarted SS2'))
        self.assertEqual(liverally.my_result(v, ME), ('P2 of 3', '18:25.000'))
        self.assertEqual(liverally.my_result(v, '9'), ('DNF', 'restarted SS2'))
        out = running(me_next={})
        out['me']['out'] = {'no': 0, 'moved': 3}
        self.assertEqual(liverally.my_result(out, ME), ('DID NOT START', 'missed your turn 4 times'))

    def test_the_session_shown_first(self):
        now = H - 10 * MIN
        self.assertEqual(liverally.pick(INFO, now), ('rally2', H))              # the one open for sign-up
        info = dict(INFO, sessions=[dict(INFO['sessions'][0], phase='over'), dict(INFO['sessions'][1], signedUp=True)])
        self.assertEqual(liverally.pick(info, H + 100 * MIN), ('classic', H + 120 * MIN))   # mine, starting soon
        self.assertIsNone(liverally.pick({}, now))
        self.assertEqual(liverally.card_line(INFO['sessions'][0], now), 'Registration open · starts in 10:00 · 1 registered')
        self.assertEqual(liverally.card_line(INFO['sessions'][1], now), 'Registration opens in 1:40:00')

    def test_the_timer_window(self):
        st, ms, line, col = liverally.overlay(running(), 0, H + 2 * MIN)       # getting ready: red, the first turn in 3:00
        self.assertEqual((st, ms, col), ('wait', 3 * MIN, 'bad'))
        self.assertIn('the first turn in 3:00', line)
        st, ms, line, col = liverally.overlay(turns_view(), 0, TURN + 5000)    # waiting: red, at most 15 s
        self.assertEqual((st, ms, line, col), ('wait', 15000, "WAIT · SS1 · You're next", 'bad'))
        st, ms, line, col = liverally.overlay(turns_view(ME), 0, TURN + 8000)  # my turn: green
        self.assertEqual((st, ms, col), ('go', 15000, 'good'))
        self.assertEqual(liverally.overlay(turns_view(ME), 0, TURN + 24000)[0], 'late')
        v = running(me_next=nxt(no=1, readyAt=H + 14 * MIN, estAt=H + 14 * MIN, at=H + 14 * MIN, ahead=0))
        self.assertEqual(liverally.overlay(v, 1, H + 12 * MIN)[:2], ('break', 2 * MIN))   # between stages: amber
        self.assertIsNone(liverally.overlay(v, 0, H))                           # (another stage's)
        self.assertIsNone(liverally.overlay(running(me_next={}), 0, TURN))


class Gate(unittest.TestCase):
    """The turn window's words (liverally.gate): red while I wait, green on my turn, amber on the break."""

    def test_from_the_start_list_to_my_turn(self):
        g = liverally.gate(running(), ME, H + MIN, following=False)             # the rally out, not set up yet: DRIVE
        self.assertEqual((g['mode'], g['head'], g['big'], g['drive']), ('ready', 'YOUR RALLY IS READY', '4:00', True))
        self.assertEqual((g['kicker'], g['stage']), ('RANKED · Rally2', 'SS1 · STAGE 0'))
        g = liverally.gate(running(), ME, H + MIN)                              # set up: red, the first turn in 4:00
        self.assertEqual((g['mode'], g['head'], g['big'], g['drive']), ('wait', 'WAIT', '4:00', False))
        self.assertIn('You are #2 on the start list', g['line'])
        self.assertEqual(g['rows'], [('1', 'Ann', 'ready', 'break', False), ('2', 'Me', 'ready', 'break', True)])
        g = liverally.gate(turns_view(), ME, TURN + 5000)                       # Ann's turn
        self.assertEqual((g['mode'], g['big'], g['now']), ('wait', '0:15', 'Turn: Ann · 0:15'))
        self.assertEqual(g['line'], "You're next: your turn in 0:15 at the latest.")
        self.assertEqual(g['rows'], [('1', 'Ann', 'TURN', 'turn', False), ('2', 'Me', '≤ 0:15', 'waiting', True),
                                     ('3', 'Ott T.', '≤ 0:35', 'waiting', False)])
        g = liverally.gate(turns_view(ME), ME, TURN + 8000)                     # mine: green, 20 s to start
        self.assertEqual((g['mode'], g['head'], g['big'], g['line'], g['now']),
                         ('turn', 'GO', '0:15', 'It is your turn. You have 20 seconds to start.', ''))
        self.assertEqual(liverally.gate(turns_view(ME), ME, TURN + 30000)['mode'], 'late')

    def test_more_drivers_before_me_and_the_break(self):
        v = turns_view()
        v['me']['next'].update(ahead=3, estAt=TURN + 60000)
        g = liverally.gate(v, ME, TURN + 5000)
        self.assertEqual(g['line'], '3 drivers before you: your turn in 0:55 at the latest.')
        v = running(me_next=nxt(no=1, readyAt=H + 14 * MIN, estAt=H + 14 * MIN, at=H + 14 * MIN, ahead=0))
        g = liverally.gate(v, ME, H + 12 * MIN)
        self.assertEqual((g['mode'], g['head'], g['big'], g['stage']), ('break', 'BREAK', '2:00', 'SS2 · STAGE 1'))
        self.assertEqual(g['line'], 'Load SS2. You join its queue in 2:00.')
        self.assertIsNone(liverally.gate(running(me_next={}), ME, H))

    def test_a_long_queue_keeps_me_in_it(self):
        q = [qrow(str(100 + i), 'D%d' % i, 'waiting', estAt=TURN + i * 20000, ahead=i) for i in range(12)]
        q.append(qrow(ME, 'Me', 'waiting', estAt=TURN + 12 * 20000, ahead=12))
        v = running(queues=[q, [], []], me_next=nxt(state='waiting', ahead=12, estAt=TURN + 12 * 20000))
        g = liverally.gate(v, ME, TURN)
        self.assertEqual(len(g['rows']), liverally.GATE_ROWS)
        self.assertEqual(g['rows'][-1][:2], ('13', 'Me'))


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
        me = ('rally2', H)
        st = self.state(on, running(), now=H + MIN)                                 # the rally is out: DRIVE
        self.assertEqual((st['chip'], st['button'], st['time']), ('READY', ('DRIVE', 'drive'), '4:00'))
        st = self.state(on, running(), now=H + MIN, follow=me)                      # followed: getting ready, no button
        self.assertEqual((st['chip'], st['button'], st['tone'], st['time']), ('SS1', None, 'slow', '4:00'))
        st = self.state(on, turns_view(), now=TURN + 5000, follow=me)                # waiting: red
        self.assertEqual((st['tone'], st['label'], st['time']), ('bad', 'AT MOST', '0:15'))
        self.assertIn("wait: you're next", st['words'])
        st = self.state(on, turns_view(ME), now=TURN + 8000, follow=me)              # my turn: green
        self.assertEqual((st['tone'], st['label'], st['time'], st['button']), ('good', 'GO', '0:15', None))
        self.assertEqual(self.state(on, running(), now=TURN + 1000, follow=me, driving=0)['words'][-8:], 'on stage')
        done = running()
        done['event'] = dict(EVENT, entry={'status': 'finished', 'done': 3, 'totalMs': 1_100_000})
        done['standings'] = [{'steamId': '7', 'rank': 1, 'status': 'finished'}, {'steamId': ME, 'rank': 2, 'status': 'finished'}]
        st = self.state(on, done, now=H + 40 * MIN)
        self.assertEqual((st['chip'], st['label'], st['button']), ('FINISHED', 'P2 of 2', ('RESULTS', 'results')))
        self.assertIn('18:20.000', st['words'])
        dnf = running()
        dnf['event'] = dict(EVENT, entry={'status': 'dnf', 'reason': 'restarted'})
        self.assertEqual(self.state(on, dnf, now=H + 9 * MIN)['chip'], 'DNF')
        out = running(me_next={})
        out['me']['out'] = {'no': 0, 'moved': 3}
        self.assertEqual(self.state(on, out, now=H + 9 * MIN)['words'][-28:], 'you missed your turn 4 times')
        self.assertIsNone(self.state(info_with(signedUp=True, phase='over'), running(), now=H + 2 * 3600000))


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

    def at(self, ms):
        """The server's clock at ms."""
        self.a._lr_ready()
        self.a.lr_clock.offset_ms = ms - __import__('time').time() * 1000

    def test_your_rally_is_ready_and_the_turn_window(self):
        """At the hour: the turn window over everything, YOUR RALLY IS READY with DRIVE; set up, red WAIT; my turn green;
        driving, it gives way. It can't be closed."""
        a = self.a
        a._notify = mock.Mock()
        a.api.live_session.return_value = running()
        a.api.live_rallies.return_value = info_with(signedUp=True, phase='running')
        self.at(H + MIN)
        a.nav('live')
        a._lr_tick()
        g = a._lr_gate
        self.assertTrue(g.shown)
        self.assertEqual((g.head.cget('text'), g.big.cget('text'), g.act.winfo_manager()), ('YOUR RALLY IS READY', '4:00', 'pack'))
        self.assertEqual(g.win.overrideredirect(), True)                       # (no title bar: nothing to close it with)
        a._notify.assert_called_once()                                         # (the rally is out: said aloud)
        words = self.page()
        self.assertIn('START LIST', words)
        self.assertEqual([e['id'] for e in a.league_events], [42])            # (among the app's events: DRIVE finds it)
        a._lr_bar_render()
        self.assertEqual((a.lr_bar_chip.cget('text'), a.lr_bar_button.cget('text')), ('READY', 'DRIVE  ›'))
        g.drive_b.event_generate('<Button-1>')
        click(g.drive_b)
        a.league_drive.assert_called_with(42)
        self.assertEqual(a.s['leagueCars'], {'42': 'Skoda Fabia RS Rally2'})  # (the car registered with)
        ev = dict(a.lr_data[('rally2', H)]['event'])                           # following it now
        car = {'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}
        j = Judge(__import__('acr_daily.leagues', fromlist=['x']).stage_ch(ev, 0, car))
        a.league_run, a.drive_target = {'ev': ev, 'car': car, 'no': 0, 'judge': j, 'known': None, 'ignore': None, 'wait': None}, 'league'
        a._lr_gate_tick()
        self.assertEqual((g.head.cget('text'), g.act.winfo_manager(), g.strip.cget('bg')), ('WAIT', '', rankedgate.RED))
        a.lr_data[('rally2', H)] = turns_view(ME)                              # my turn
        self.at(TURN + 8000)
        a._lr_gate_tick()
        self.assertEqual((g.head.cget('text'), g.big.cget('text'), g.strip.cget('bg')), ('GO', '0:15', rankedgate.GREEN))
        self.assertEqual(g.line.cget('text'), 'It is your turn. You have 20 seconds to start.')
        self.assertEqual(a._notify.call_args.args[1], 'RANKED · YOUR TURN')
        a._lr_gate_tick()
        self.assertEqual(a._notify.call_count, 2)                              # (said once)
        j.state = 'running'                                                    # started: it gives way
        a._lr_gate_tick()
        self.assertFalse(g.shown)
        self.assertTrue(g.alive)
        j.state = 'armed'
        a._lr_gate_tick()
        self.assertTrue(g.shown)                                               # (back: SS1 not started, my turn still)
        g.win.event_generate('<Escape>')
        g.win.tk.eval(g.win.protocol('WM_DELETE_WINDOW'))                       # (closing it: nothing)
        self.assertTrue(g.alive)
        out = turns_view()                                                     # out of it (missed too often): gone
        out['me'].update(next=None, out={'no': 0, 'moved': 3, 'out': 'dns'})
        a.lr_data[('rally2', H)] = out
        a._lr_gate_tick()
        self.assertFalse(g.shown)
        g.close()

    def test_the_results_page_and_your_results_are_out(self):
        a = self.a
        a._notify = mock.Mock()
        v = running(me_next={})                                                # (finished: no turn to come)
        v['event'] = dict(EVENT, entry={'status': 'finished', 'done': 3, 'totalMs': 1_105_000})
        st = lambda t, pos: {'totalMs': t, 'pos': pos, 'stewardMs': 0}   # noqa: E731
        v['standings'] = [{'steamId': '7', 'name': 'Ann', 'car': 'VW', 'status': 'finished', 'rank': 1, 'totalMs': 1_100_000,
                           'stages': [st(372_000, 1), st(360_000, 2), st(368_000, 1)]},
                          {'steamId': ME, 'name': 'Me', 'car': 'Skoda', 'status': 'finished', 'rank': 2, 'totalMs': 1_105_000,
                           'gapMs': 5000, 'stages': [st(380_000, 2), st(355_000, 1), st(370_000, 2)]}]
        a.api.live_session.return_value = v
        a.api.live_rallies.return_value = info_with(signedUp=True, phase='running', eventId=42)
        self.at(H + 40 * MIN)
        a.nav('live')
        a._lr_tick()
        self.assertNotIn('results', a._lr_cards)                               # (not out yet: Ann's... still running)
        self.assertIn('RESULTS SO FAR  ›', self.page())
        click(self.label('RESULTS SO FAR  ›'))                                 # a page of their own
        words = self.page()
        for w in ('RESULTS', 'PROVISIONAL · STILL RUNNING', 'Y O U R   R E S U L T', 'P2 of 2', '18:25.000', '+0:05.000',
                  '6:20.000  P2', 'YOU  ·  Me'):
            self.assertIn(w, words)
        a.api.live_session.return_value = dict(v, resultsOut=True)
        a._lr_poll(('rally2', H))
        a._lr_results_tick()
        card = a._lr_cards['results']                                          # out: said, once
        self.assertEqual(card.go_b.cget('text'), 'VIEW RESULTS  ›')
        self.assertEqual(a._notify.call_args.args[1], 'RANKED · RESULTS')
        self.assertIn('Your results are out: P2 of 2  ·  18:25.000', a._notify.call_args.args[2])
        self.assertEqual(a.s['rankedTold'], [['rally2', H]])
        self.assertIn('FINAL', self.page())
        a._lr_results_tick()
        self.assertEqual(a._notify.call_count, 1)
        click(self.label('‹  RANKED'))                                         # back to RANKED
        self.assertIn('SERIES', ' '.join(self.page()).replace('  ', ' ') + ' SERIES')
        self.assertIsNone(a.lr_results)
        card._go()                                                             # VIEW RESULTS on the card
        self.assertEqual(a.lr_results, ('rally2', H))
        a._lr_bar_render()
        self.assertEqual(a.lr_bar_button.cget('text'), 'RESULTS')
        a.lr_close_results()
        click(a.lr_bar_button)                                                 # ...and on the bar
        self.assertEqual(a.lr_results, ('rally2', H))


class Following(unittest.TestCase):
    """The app following a session's stage (leagueui.py): the timer's words, the start on the server's clock, the next
    stage's queue at the finish, the ghost cars' room."""

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

    def test_the_timer_says_the_wait_and_my_turn(self):
        a = self.app()
        a.lr_data[('rally2', H)] = turns_view()
        a.lr_clock.offset_ms = TURN + 5000 - __import__('time').time() * 1000
        status, sub, ov = a._league_overlay_state(None)
        self.assertEqual((ov[0], ov[4]), ('wait', "WAIT · SS1 · You're next"))
        self.assertAlmostEqual(ov[2], 15_000, delta=2000)                     # the time shown: at most this long
        a.lr_data[('rally2', H)] = turns_view(ME)
        self.assertEqual(a._league_overlay_state(None)[2][0], 'go')
        from acr_daily import app as app_mod
        self.assertEqual([app_mod.STATUS[k][0] for k in ('wait', 'go', 'break', 'late')], ['WAIT', 'GO', 'BREAK', 'MISSED'])

    def test_the_start_goes_with_the_servers_time_nothing_to_press(self):
        a = self.app()
        a.lr_clock.offset_ms, a.lr_clock.known = 1500.0, True
        a._league_send = mock.Mock()
        a._lr_out = mock.Mock()
        a.league_run['judge']._start_wall = 1000.0              # (started_ms: 1 000 000)
        a.league_run['ev']['entry'] = None
        with mock.patch('acr_daily.leagueui.saveslot.read_save', return_value=b''), \
                mock.patch('acr_daily.leagueui.leagues.known', return_value=None), \
                mock.patch('acr_daily.leagueui.rallyweekend.read_weekend', return_value={'stages': []}), \
                mock.patch('acr_daily.leagueui.leagues.same_calendar', return_value=True), \
                mock.patch('acr_daily.leagueui.leagues.changed_in_game', return_value=[]):
            a._league_started(a.league_run)
        item = a._league_send.call_args.args[0]
        self.assertEqual((item['kind'], item['at'], item['serverAt']), ('start', 1_000_000, 1_001_500))
        a._lr_out.assert_not_called()

    def test_the_next_stages_queue_joined_at_the_finish(self):
        a = self.app()
        a.api.live_queue.return_value = {'now': H, 'slot': {'no': 1, 'at': H + 14 * MIN, 'readyAt': H + 14 * MIN, 'moved': 0}}
        a._lr_poll = mock.Mock()                                           # (the session looked at again: not here)
        a.lr_clock.offset_ms = H + 11 * MIN - __import__('time').time() * 1000
        with mock.patch('acr_daily.liverallyui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)), \
                mock.patch('acr_daily.liverallyui._c') as c:
            c.return_value.ui = lambda w, fn, *x: fn(*x)
            a._lr_finished(a.league_run['ev'], 0)
        self.assertEqual(a.api.live_queue.call_args.args[:3], ('rally2', H, 1))
        self.assertEqual(a.lr_data[('rally2', H)]['me']['next']['readyAt'], H + 14 * MIN)
        self.assertIn('SS2: a break, then its queue (in 3:00)', a.sub_l.configure.call_args.kwargs['text'])
        self.assertEqual(liverally.my_start(a.lr_data[('rally2', H)], H + 12 * MIN)['phase'], 'break')
        self.assertEqual(a._lr_queue_want, {})
        a._lr_finished(a.league_run['ev'], 2)                                # (the last stage: nothing to queue for)
        self.assertEqual(a._lr_queue_want, {})
        a.league_run['wait'] = {'id': 'x'}                                    # SS1's official time on its way: the next line
        self.assertIn('Next: SS2 · a break, its queue in', a._lr_next_line(a.league_run))

    def test_out_of_the_session(self):
        """Missed my turn too often (the server took me out of the queue): the timer says so, no countdown."""
        a = self.app()
        a.lr_data[('rally2', H)]['me'].update(next=None, out={'no': 0, 'at': H + 9 * MIN, 'moved': 3, 'out': 'dns'})
        status, sub, ov = a._league_overlay_state(None)
        self.assertEqual((ov[0], ov[4]), ('dnf', 'OUT · you missed your turn 4 times'))
        self.assertIsNone(a._lr_gate_state())

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
