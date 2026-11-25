"""RANKED in the game (ig_ranked.py): a special event's card (25 Nov 2026: the Skoda Saturday Challenge), and WATCH LIVE
(every session under way, a WATCH for each of its stages; a driver of the session only for the stages they drove, a
start on one of theirs before their run being a DNF), and the ranked stage's times as WATCH's board (ig_watch)."""
import time
import types
import unittest
from unittest import mock

from acr_daily import ig_ranked, ig_watch, liverally

NOW = 1795867200000 - 3 * 86400000          # (Wed 25 Nov 2026, 12:00 UTC: three days before the special)
SPECIAL = {'key': 'skoda', 'name': 'Skoda Saturday Challenge', 'special': True, 'starts': 1795867200000, 'stages': 4,
           'rally': 'Greece', 'prize': 50, 'phase': 'signup', 'signups': 7, 'signedUp': False,
           'cars': [{'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}]}
RUNNING = ('rally2', NOW - 20 * 60000)


def walk(n):
    if isinstance(n, dict):
        yield n
        for v in n.values():
            yield from walk(v)
    elif isinstance(n, list):
        for v in n:
            yield from walk(v)


def ids(tree):
    return [n['id'] for n in walk(tree) if n.get('t') == 'btn' and n.get('id')]


def words(tree):
    return ' '.join(str(n.get('s')) for n in walk(tree) if n.get('t') in ('txt', 'btn') and n.get('s'))


def view(done=0, signed=False, status='running'):
    stage = lambda no, name: {'no': no, 'name': name, 'track': 'Monte Carlo %s' % name, 'stageId': 'MC%d' % no,  # noqa: E731
                              'lengthM': 9000, 'weatherGame': 'WT_CLEAR', 'startSeconds': 36000}
    q = lambda *xs: [dict({'steamId': s, 'name': n, 'country': 'fi', 'car': 'Skoda Fabia RS Rally2'}, **o) for s, n, o in xs]  # noqa: E731
    return {'phase': 'running', 'rally': 'Monte Carlo', 'eventId': 77, 'entrants': 3,
            'me': {'signedUp': signed}, 'event': {'id': 77, 'stages': [stage(1, 'Sospel'), stage(2, 'Turini'), stage(3, 'Col')],
                                                   'cars': [{'name': 'Skoda Fabia RS Rally2', 'id': 'SkodaFabiaRSRally2'}],
                                                   'entry': {'status': status, 'done': done} if signed else None},
            'queues': [q(('1', 'Ann', {'state': 'done', 'timeMs': 401000}), ('2', 'Ben', {'state': 'done', 'timeMs': 399500,
                                                                                         'team': {'tag': 'BEN', 'color': '336699'}}),
                         ('3', 'Cat', {'state': 'driving'})),
                       q(('1', 'Ann', {'state': 'driving'}), ('2', 'Ben', {'state': 'waiting', 'estAt': NOW})), []]}


def app(sessions, data, me=None):
    a = types.SimpleNamespace()
    a.lr_info = {'on': True, 'series': [dict(SPECIAL, key='skoda'), {'key': 'rally2', 'name': 'Rally2', 'cars': []}],
                 'specials': [SPECIAL], 'sessions': sessions, 'recent': []}
    a.lr_data = data
    a.lr_clock = types.SimpleNamespace(now_ms=lambda: NOW)
    a.lr_msg = ''
    a.s = {'steamId': '1', 'token': 't'}
    a._lr_at = {}
    a.polled = []
    a._lr_ready = lambda: None
    a.refresh_live_rallies = lambda: None
    a._lr_registered = lambda: me
    a._lr_series_name = lambda k: {'skoda': 'Skoda Saturday Challenge', 'rally2': 'Rally2'}.get(k, k)
    a._lr_poll = lambda k: a.polled.append(k)
    a._lr_car = lambda k: None
    a._lr_bar_state = lambda: None
    return a


def ig_of(a):
    mem = {}
    return types.SimpleNamespace(app=a, shown=True, mem=lambda k: mem.setdefault(k, {}), said=[],
                                 say=lambda t, lines: None)


class SpecialCard(unittest.TestCase):
    def test_its_card_first_with_register_its_series_row_left_out(self):
        a = app([dict(SPECIAL, series='skoda')], {})
        tree = ig_ranked.page(ig_of(a))
        w = words(tree)
        self.assertIn('SKODA SATURDAY CHALLENGE', w)
        self.assertIn('50 credits for every driver who finishes', w)
        self.assertIn('4 stages of Greece, drawn at the start', w)
        self.assertIn('3d 0:00:00', w)                       # (three days to go: days in the countdown)
        self.assertIn('live.register:skoda|1795867200000', ids(tree))
        self.assertNotIn('live.cars:skoda', ids(tree))      # (one car: nothing to pick)

    def test_registered_withdraw(self):
        a = app([dict(SPECIAL, series='skoda', signedUp=True)], {})
        a.lr_info['specials'] = [dict(SPECIAL, signedUp=True)]
        tree = ig_ranked.page(ig_of(a))
        self.assertIn('live.withdraw:skoda|1795867200000', ids(tree))
        self.assertNotIn('live.register:skoda|1795867200000', ids(tree))


class WatchLive(unittest.TestCase):
    def sessions(self):
        return [{'series': 'rally2', 'starts': RUNNING[1], 'phase': 'running', 'eventId': 77}]

    def test_a_watch_for_each_stage_of_a_session_under_way_and_its_view_polled(self):
        a = app(self.sessions(), {RUNNING: view()})
        tree = ig_ranked.page(ig_of(a))
        got = [i for i in ids(tree) if i.startswith('live.watch:')]
        self.assertEqual(got, ['live.watch:rally2|%d|%d' % (RUNNING[1], n) for n in (1, 2, 3)])
        self.assertIn('WATCH  SS1  ·  1 on it', words(tree))
        self.assertEqual(a.polled, [RUNNING])

    def test_a_driver_of_it_only_the_stages_they_drove(self):
        v = view(done=1, signed=True)
        self.assertEqual([ig_ranked.watchable(v, n)[0] for n in (1, 2, 3)], [True, False, False])
        self.assertTrue(ig_ranked.watchable(view(done=1, signed=True, status='dnf'), 3)[0])     # (over: any)
        self.assertTrue(ig_ranked.watchable(view(), 3)[0])                                       # (not in it: any)
        a = app(self.sessions(), {RUNNING: v})
        ig = ig_of(a)
        said = []
        ig.say = lambda t, lines: said.append(lines)
        with mock.patch.object(ig_watch, 'start_event') as go:
            ig_ranked.click(ig, 'watch', 'rally2|%d|2' % RUNNING[1])
            go.assert_not_called()
            self.assertTrue(said)
            ig_ranked.click(ig, 'watch', 'rally2|%d|1' % RUNNING[1])
        x = go.call_args[0][1]
        self.assertEqual([x['eventId'], x['kind'], x['stageNo'], x['stage']['stageId'], x['steamId'], x['session']],
                         [77, 'live', 1, 'MC1', '3', RUNNING])       # (following the car on it: Cat)
        held = ig_watch.event_held(x)
        self.assertEqual([held['ch']['stageId'], held['ch']['carId'], held['session']], ['MC1', 'SkodaFabiaRSRally2', RUNNING])

    def test_the_stage_s_times_as_watch_s_board(self):
        a = app(self.sessions(), {RUNNING: view()})
        a._lr_at = {RUNNING: time.monotonic()}             # (asked just now: not again)
        held = {'session': RUNNING}
        ig_watch.ranked_board(a, held, 1)
        e = held['board']['entries']
        self.assertEqual([(x['name'], x['totalMs']) for x in e], [('Ben', 399500), ('Ann', 401000)])
        self.assertEqual(e[0]['look']['tag'], {'text': 'BEN', 'color': '336699'})
        self.assertEqual(a.polled, [])
        a._lr_at = {}
        ig_watch.ranked_board(a, held, 2)
        self.assertEqual(held['board']['entries'], [])
        self.assertEqual(a.polled, [RUNNING])


class Countdown(unittest.TestCase):
    def test_days(self):
        self.assertEqual(liverally.left(42000), '0:42')
        self.assertEqual(liverally.left(3 * 86400000 + 3723000), '3d 1:02:03')


if __name__ == '__main__':
    unittest.main()
