"""A 1V1 challenge made in the app (challengeui.py): stages drawn never two on the same road, the start times, the event
as the server takes it, and the window: find a driver, pick, send. On a Tk window that is never shown."""
import os
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import challengeui  # noqa: E402
from acr_daily.api import ApiError  # noqa: E402
from acr_daily.app import App  # noqa: E402
from test_app import tk_root  # noqa: E402
from test_inbox import ANN, ME, click, find, texts  # noqa: E402

# Monte Carlo's two places, each a full stage and a cut, both ways (the game's ids)
MC = [{'track': 'Monte Carlo ' + n, 'stageId': 'MonteCarlo' + i, 'name': n, 'lengthM': m} for n, i, m in (
    ('La Bollène', 'S1BolleneFullForward', 18100), ('Peïra Cava', 'S1BolleneFullReverse', 17900),
    ('Turini Montée', 'S1BolleneCut1Forward', 11900), ('Col de Turini', 'S2TuriniFullForward', 14000),
    ('Turini Descente', 'S2TuriniFullReverse', 14000))]
CAT = {'rallies': [{'name': 'Monte Carlo', 'surface': 'Tarmac', 'stages': MC}, {'name': 'Nowhere', 'stages': []}],
       'cars': [{'name': 'Ford Fiesta Rally2', 'cls': 'Rally2/R5', 'group': 'Modern'}],
       'classes': [{'cls': 'Rally4', 'group': 'Modern'}, {'cls': 'Rally2/R5', 'group': 'Modern'}],
       'weathers': [{'id': 'Clear', 'label': 'Clear'}, {'id': 'Rain', 'label': 'Rain'}]}


class Helpers(unittest.TestCase):
    def test_roads(self):
        self.assertEqual(challengeui.road_of(MC[2]), ('MonteCarloS1Bollene', 'Cut1'))
        self.assertTrue(challengeui.same_road(MC[0], MC[1]))          # a stage and its reverse
        self.assertTrue(challengeui.same_road(MC[0], MC[2]))          # a full stage holds its cut
        self.assertFalse(challengeui.same_road(MC[2], MC[3]))

    def test_drawn_never_two_on_the_same_road(self):
        for seed in range(30):
            got = challengeui.random_stages(MC, 2, random.Random(seed))
            self.assertEqual(len(got), 2)
            self.assertFalse(challengeui.same_road(*got), got)
        self.assertEqual(len(challengeui.random_stages(MC, 4, random.Random(1))), 2)   # (two roads only)

    def test_start_times(self):
        self.assertEqual(challengeui.stage_times('12:00', 3), ['12:00', '12:30', '13:00'])
        self.assertEqual(challengeui.stage_times('22:00', 5), ['21:30', '22:00', '22:30', '23:00', '23:30'])   # all on the day

    def test_the_event(self):
        ev = challengeui.challenge_event('Monte Carlo', MC[2:4], 'Rain', '10:00', 2, 1000, car_class='Rally2/R5', name=' Duel ')
        self.assertEqual(ev, {'rally': 'Monte Carlo', 'opens': 1000, 'closes': 1000 + 2 * 86400000, 'carClass': 'Rally2/R5', 'name': 'Duel',
                              'stages': [{'track': MC[2]['track'], 'day': 1, 'weather': 'Rain', 'time': '10:00'},
                                         {'track': MC[3]['track'], 'day': 1, 'weather': 'Rain', 'time': '10:30'}]})
        self.assertNotIn('name', challengeui.challenge_event('Monte Carlo', MC[:1], 'Clear', '12:00', 1, 0, car='Ford Fiesta Rally2'))


class Dialog(unittest.TestCase):
    def setUp(self):
        self.root = tk_root()
        self.addCleanup(self.root.destroy)
        sync = lambda target, daemon: mock.Mock(start=target)
        for p in (mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)),
                  mock.patch('acr_daily.challengeui.threading.Thread', side_effect=sync)):
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch('acr_daily.challengeui.messagebox.askyesno', return_value=True)
        self.ask = p.start()
        self.addCleanup(p.stop)
        a = App.__new__(App)
        a.root, a.api, a.sub_l = self.root, mock.Mock(), mock.Mock()
        a.s = {'token': 't' * 64, 'steamId': ME}
        a.credits = {'enabled': True, 'balance': 150}
        a.api.catalog.return_value = CAT
        a.api.players.return_value = [{'steamId': ME, 'name': 'Me'}, {'steamId': ANN, 'name': 'Ann', 'country': 'fi'}]
        self.a, self.done = a, mock.Mock()
        self.d = challengeui.ChallengeDialog(a, done=self.done)

    def test_find_pick_send(self):
        d, a = self.d, self.a
        self.assertNotIn('Nowhere', d.rally.cget('values'))         # (a rally without stages: not offered)
        d.send()
        self.assertEqual(d.msg.cget('text'), 'Find who you challenge first.')
        d.q.insert(0, 'an')
        d.find()
        a.api.players.assert_called_once_with('an')
        said = texts(d.who)
        self.assertIn('Ann  (FI)', said)
        self.assertNotIn('Me', said)                                  # (not myself)
        click(find(d.who, 'Ann  (FI)'))
        self.assertIn('Ann', texts(d.who))
        d.send()
        self.assertEqual(d.msg.cget('text'), 'Pick a stage (or draw some at random).')
        with mock.patch('acr_daily.challengeui.random_stages', return_value=[MC[0], MC[3]]):
            click(d.random_b)
        self.assertEqual(d.stage_l.curselection(), (0, 3))
        d.stake.delete(0, 'end')
        d.stake.insert(0, '50')
        with mock.patch('acr_daily.challengeui.time.time', return_value=2000.0):
            d.send()
        self.assertIn('50 credits each', self.ask.call_args.args[1])
        a.api.h2h_challenge.assert_called_once_with(ANN, 50, {
            'rally': 'Monte Carlo', 'opens': 2000000, 'closes': 2000000 + 2 * 86400000, 'carClass': 'Rally2/R5',
            'stages': [{'track': MC[0]['track'], 'day': 1, 'weather': 'Clear', 'time': '12:00'},
                       {'track': MC[3]['track'], 'day': 1, 'weather': 'Clear', 'time': '12:30'}]})
        self.done.assert_called_once()
        self.assertFalse(d.win.winfo_exists())
        self.assertIn('Challenge sent to Ann', a.sub_l.configure.call_args.kwargs['text'])

    def test_refused_said_in_the_window(self):
        d, a = self.d, self.a
        d.opp = {'steamId': ANN, 'name': 'Ann'}
        d.stage_l.selection_set(1)
        d.car_mode.set('car')
        d._cars()
        a.api.h2h_challenge.side_effect = ApiError('the stake is 0 credits: you have 0', 402)
        d.send()
        self.assertEqual(a.api.h2h_challenge.call_args.args[2]['car'], 'Ford Fiesta Rally2')
        self.assertEqual(d.msg.cget('text'), 'Not sent: the stake is 0 credits: you have 0')
        self.assertTrue(d.win.winfo_exists())
        self.done.assert_not_called()

    def test_no_answer_nothing_sent(self):
        self.ask.return_value = False
        self.d.opp = {'steamId': ANN, 'name': 'Ann'}
        self.d.stage_l.selection_set(0)
        self.d.send()
        self.a.api.h2h_challenge.assert_not_called()

    def test_catalog_not_loaded(self):
        self.a.api.catalog.side_effect = ApiError('offline')
        d = challengeui.ChallengeDialog(self.a)
        self.assertEqual(d.loading.cget('text'), 'Not loaded: offline')


if __name__ == '__main__':
    unittest.main()
