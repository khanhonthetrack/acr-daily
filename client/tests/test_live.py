"""Driver colours (same picks as the website), the game process lookup, and the overlays' "only on the daily" rule."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import saveslot  # noqa: E402
from acr_daily.widgets import PALETTE, colours  # noqa: E402


class Colours(unittest.TestCase):
    def test_everyone_gets_a_different_colour(self):
        ids = ['76561198019002579', '76561198051420773', '76561198000000009', '76561198000000019']
        c = colours(ids)
        self.assertEqual(len(set(c.values())), len(ids))
        self.assertTrue(all(v in PALETTE for v in c.values()))

    def test_same_driver_same_colour_whatever_the_order(self):
        ids = ['76561198019002579', '76561198051420773', '76561198000000009']
        self.assertEqual(colours(ids), colours(list(reversed(ids))))

    def test_matches_the_website_rule(self):
        # site.js: Number(id.slice(-6)) % 10, sorted ids, next free colour on a clash
        self.assertEqual(colours(['76561198000000013'])['76561198000000013'], PALETTE[13 % 10])
        c = colours(['76561198000000003', '76561198000000013'])
        self.assertEqual(c['76561198000000003'], PALETTE[3])
        self.assertEqual(c['76561198000000013'], PALETTE[4])


class GameProcess(unittest.TestCase):
    def test_reads_tasklist_csv(self):
        out = '"acr.exe","4242","Console","1","1,234,567 K"\n'
        with mock.patch('os.popen', return_value=mock.Mock(read=lambda: out)):
            self.assertEqual(saveslot.game_pids(), [4242])
            self.assertTrue(saveslot.game_running())

    def test_not_running(self):
        out = 'INFO: No tasks are running which match the specified criteria.\n'
        with mock.patch('os.popen', return_value=mock.Mock(read=lambda: out)):
            self.assertEqual(saveslot.game_pids(), [])
            self.assertFalse(saveslot.ask_game_to_quit())


class OnlyOnTheDaily(unittest.TestCase):
    """App._overlays_allowed / _check_conditions on a stand-in app (no windows)."""

    def app(self, only=True, locked=True):
        from acr_daily.app import App
        from acr_daily.judge import Judge
        a = App.__new__(App)
        a.s = {'overlay': {'onlyOnDaily': only, 'locked': locked}}
        a.recorder = None
        ch = {'id': 'd/1', 'slot': 1, 'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2', 'route': [[0, 0], [100, 0]],
              'startTempK': 290.0}
        a.dailies = {1: {'ch': ch, 'judge': Judge(ch)}}
        return a

    def frame(self, track='Alsace Forêt', car='Hyundai i20 N Rally2', air=290.5, clock=0):
        from acr_daily.telemetry import Frame
        return Frame(0.0, 1, clock, 0.0, 0.0, 0.0, car, track, air_k=air)

    def test_hidden_off_the_daily(self):
        a = self.app()
        self.assertFalse(a._overlays_allowed(None))
        self.assertFalse(a._overlays_allowed(self.frame(track='Wales Afon Bidno')))
        self.assertFalse(a._overlays_allowed(self.frame(car='Peugeot 208 Rally4')))

    def test_shown_on_the_daily_with_the_right_conditions(self):
        a = self.app()
        f = self.frame()
        a._check_conditions(f)
        self.assertTrue(a.dailies[1]['cond_ok'])
        self.assertTrue(a._overlays_allowed(f))

    def test_hidden_when_the_air_says_other_conditions(self):
        a = self.app()
        f = self.frame(air=296.0)
        a._check_conditions(f)
        self.assertFalse(a.dailies[1]['cond_ok'])
        self.assertFalse(a._overlays_allowed(f))

    def test_no_one_finished_yet_means_shown(self):
        a = self.app()
        a.dailies[1]['ch']['startTempK'] = None
        f = self.frame(air=300.0)
        a._check_conditions(f)
        self.assertIsNone(a.dailies[1]['cond_ok'])
        self.assertTrue(a._overlays_allowed(f))

    def test_always_shown_when_the_option_is_off_or_while_moving_them(self):
        self.assertTrue(self.app(only=False)._overlays_allowed(None))
        self.assertTrue(self.app(locked=False)._overlays_allowed(None))


if __name__ == '__main__':
    unittest.main()
