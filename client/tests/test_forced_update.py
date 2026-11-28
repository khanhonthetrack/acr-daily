"""An app too old for the server (below MIN_APP_VERSION, from MIN_APP_FROM on: GET /api/version's min / minFrom)
updates itself at once, no click (the user, 26 Nov 2026): App.check_update marks the offer 'forced'; updatescreen.py
shows the download going."""
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from acr_daily import app as appmod, updatescreen  # noqa: E402


def check(version_answer, mine, launch=False):
    me = types.SimpleNamespace(api=types.SimpleNamespace(version=lambda: version_answer, base='https://x'),
                               update_info=None)
    with mock.patch.object(appmod, '__version__', mine), mock.patch.object(appmod.updater, 'is_test_build',
                                                                           return_value=False):
        appmod.App.check_update(me, launch)
    return me.update_info


class AskedAtLaunch(unittest.TestCase):
    """A newer version the server still takes: asked about once at launch, Yes / No over every window (the user,
    28 Nov 2026); never while a run is on or the game is open; the UPDATE bar either way."""
    V = {'latest': '0.2.4', 'url': 'https://example.invalid/ACR-Daily.exe', 'min': '0.2.3', 'minFrom': '2026-11-28'}

    def app(self, info, driving=False, game=False):
        a = appmod.App.__new__(appmod.App)
        a.update_info, a.update_busy = info, ''
        a.root, a.upd, a.state_l = mock.Mock(), mock.Mock(), mock.Mock()
        a.upd.cget.return_value = ''
        a._driving = lambda: driving
        a._game_open_cached = lambda: game
        a.to_front, a.do_update = mock.Mock(), mock.Mock()
        return a

    def test_marked_at_launch_only(self):
        with mock.patch('time.gmtime', return_value=(2026, 11, 28, 0, 0, 0, 5, 332, 0)):
            self.assertTrue(check(self.V, '0.2.3', launch=True)['ask'])
            self.assertNotIn('ask', check(self.V, '0.2.3'))             # (the 30-minute check: the bar only)
            self.assertNotIn('ask', check(self.V, '0.2.2', launch=True))   # (too old: updated at once instead)

    def test_asked_once_not_over_a_run_or_the_game(self):
        for driving, game in ((True, False), (False, True)):
            a = self.app({'version': '0.2.4', 'url': 'u', 'ask': True}, driving, game)
            with mock.patch.object(appmod.updater, 'can_self_update', return_value=True):
                a._render_update()
            a.root.after.assert_not_called()
            self.assertTrue(a.update_info['ask'])                       # (asked later)
        a = self.app({'version': '0.2.4', 'url': 'u', 'ask': True})
        with mock.patch.object(appmod.updater, 'can_self_update', return_value=True):
            a._render_update()
            a._render_update()
        a.root.after.assert_called_once_with(0, a._ask_update)
        with mock.patch.object(appmod.messagebox, 'askyesno', return_value=True) as ask:
            a._ask_update()
        self.assertIn('0.2.4', ask.call_args.args[1])
        a.to_front.assert_called_once()
        a.root.attributes.assert_any_call('-topmost', True)
        a.do_update.assert_called_once()
        with mock.patch.object(appmod.messagebox, 'askyesno', return_value=False):
            a._ask_update()
        a.do_update.assert_called_once()                                # (No: the bar stays, nothing downloaded)


class Forced(unittest.TestCase):
    V = {'latest': '0.2.3', 'url': 'https://example.invalid/ACR-Daily.exe', 'min': '0.2.2', 'minFrom': '2026-11-26'}

    def test_below_the_minimum_from_its_day(self):
        with mock.patch('time.gmtime', return_value=(2026, 11, 27, 0, 0, 0, 4, 331, 0)):
            self.assertTrue(check(self.V, '0.2.1')['forced'])
            self.assertNotIn('forced', check(self.V, '0.2.2'))          # (at the minimum: the UPDATE bar only)
            self.assertNotIn('forced', check(self.V, '0.2.2.5'))        # (a test build of it)
            self.assertNotIn('forced', check(dict(self.V, min=None), '0.2.1'))   # (no minimum set)
        with mock.patch('time.gmtime', return_value=(2026, 11, 25, 0, 0, 0, 2, 329, 0)):
            self.assertNotIn('forced', check(self.V, '0.2.1'))          # (before its day: still taken)
        self.assertIsNone(check(dict(self.V, latest='0.2.1'), '0.2.1'))  # (nothing newer: nothing to do)

    def test_the_screen_reads_the_download_share(self):
        self.assertEqual(updatescreen.percent('DOWNLOADING 0.2.3  ·  42 %'), 0.42)
        self.assertIsNone(updatescreen.percent('INSTALLING 0.2.3 ...'))
        self.assertIsNone(updatescreen.percent(''))


if __name__ == '__main__':
    unittest.main()
