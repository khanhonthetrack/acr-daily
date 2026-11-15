"""Test builds (four-part versions: GitHub prereleases .github/workflows/dev.yml makes from main on each change of the
app): a tester's app is offered the newest one from GitHub (updater.latest_test_build), the server's release when it is
newer; everyone else only the server's (App.check_update)."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import app as app_mod, updater  # noqa: E402
from acr_daily.api import ApiError  # noqa: E402
from acr_daily.app import App  # noqa: E402


def rel(tag, pre=True, exe=True, sha=True, draft=False):
    assets = ([{'name': 'ACR-Daily.exe', 'browser_download_url': 'https://gh/%s/ACR-Daily.exe' % tag}] if exe else []) + \
        ([{'name': 'ACR-Daily.exe.sha256', 'browser_download_url': 'https://gh/%s/ACR-Daily.exe.sha256' % tag}] if sha else [])
    return {'tag_name': tag, 'prerelease': pre, 'draft': draft, 'assets': assets}


def answer(releases):
    return mock.patch.object(updater.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(releases).encode()))


class LatestTestBuild(unittest.TestCase):
    def test_the_newest_prerelease_with_its_exe(self):
        with answer([rel('v0.1.5'), rel('v0.1.5.10'), rel('v0.1.5.9'), rel('v0.1.5.11', exe=False), rel('v0.1.5.12', sha=False),
                     rel('v0.1.5.13', draft=True), rel('v0.1.5.14', pre=False), rel('acrdaily-london')]):
            self.assertEqual(updater.latest_test_build(), ('0.1.5.10', 'https://gh/v0.1.5.10/ACR-Daily.exe'))

    def test_none(self):
        with answer([rel('v0.1.5', pre=False)]):
            self.assertIsNone(updater.latest_test_build())
        with answer({'message': 'API rate limit exceeded'}):
            self.assertIsNone(updater.latest_test_build())


class Offer(unittest.TestCase):
    def offer(self, current, server_latest, test=None, server_down=False):
        a = App.__new__(App)
        a.update_info = None
        a.api = mock.Mock(base='https://acrdaily.com')
        if server_down:
            a.api.version.side_effect = ApiError('down')
        else:
            a.api.version.return_value = {'latest': server_latest, 'url': 'https://dl/v%s/ACR-Daily.exe' % server_latest}
        with mock.patch.object(app_mod, '__version__', current), \
                mock.patch.object(updater, 'latest_test_build', return_value=test) as look:
            a.check_update()
        return a.update_info, look

    def test_a_tester_gets_the_newer_test_build(self):
        info, _look = self.offer('0.1.5.3', '0.1.5', ('0.1.5.4', 'https://gh/v0.1.5.4/ACR-Daily.exe'))
        self.assertEqual(info, {'version': '0.1.5.4', 'url': 'https://gh/v0.1.5.4/ACR-Daily.exe'})
        info, _look = self.offer('0.1.5.3', '0.1.5', ('0.1.5.4', 'u'), server_down=True)   # (the server down: GitHub still)
        self.assertEqual(info['version'], '0.1.5.4')

    def test_the_release_once_it_is_out(self):
        info, _look = self.offer('0.1.5.9', '0.1.6', ('0.1.5.9', 'u'))
        self.assertEqual(info['version'], '0.1.6')

    def test_nothing_newer(self):
        info, _look = self.offer('0.1.5.4', '0.1.5', ('0.1.5.4', 'u'))
        self.assertIsNone(info)

    def test_everyone_else_never_asks_github(self):
        info, look = self.offer('0.1.5', '0.1.5', ('0.1.5.4', 'u'))
        self.assertIsNone(info)
        look.assert_not_called()


if __name__ == '__main__':
    unittest.main()
