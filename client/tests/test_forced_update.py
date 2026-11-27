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


def check(version_answer, mine):
    me = types.SimpleNamespace(api=types.SimpleNamespace(version=lambda: version_answer, base='https://x'),
                               update_info=None)
    with mock.patch.object(appmod, '__version__', mine), mock.patch.object(appmod.updater, 'is_test_build',
                                                                           return_value=False):
        appmod.App.check_update(me)
    return me.update_info


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
