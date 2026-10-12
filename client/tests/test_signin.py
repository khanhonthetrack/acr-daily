"""The app's Steam sign-in (api.py login): the browser comes back to the app on 127.0.0.1 with a one-time code, which
the app swaps for its token with the verifier only it knows (never in the link); another state is turned away."""
import hashlib
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import api as api_mod, settings  # noqa: E402

TOKEN = {'token': 't' * 64, 'steamId': '76561198000000001', 'name': 'Ann'}
_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # (straight to 127.0.0.1, whatever the proxy)


class SignIn(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(settings, 'DIR', tempfile.mkdtemp())          # (settings.json written here, not the real one)
        p.start()
        self.addCleanup(p.stop)
        self.a = api_mod.Api({'server': 'https://acrdaily.example', 'token': ''})
        self.opened, self.result, self.done = [], [], threading.Event()
        p = mock.patch('acr_daily.api.webbrowser.open', side_effect=self.opened.append)
        p.start()
        self.addCleanup(p.stop)

    def on_done(self, ok, info):
        self.result.append((ok, info))
        self.done.set()

    def start(self):
        """Sign in clicked: -> the link's query (state, port, challenge)."""
        self.a.login(self.on_done)
        self.assertTrue(self.opened[0].startswith('https://acrdaily.example/auth/steam/start?'), self.opened)
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.opened[0]).query).items()}

    @staticmethod
    def back(port, **q):
        """The browser sent back to the app after Steam: -> (status, page)."""
        try:
            with _local.open('http://127.0.0.1:%s/signed-in?%s' % (port, urllib.parse.urlencode(q)), timeout=10) as r:
                return r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return e.code, ''

    def test_the_code_comes_back_to_the_app_and_is_swapped_with_its_verifier(self):
        sent = []
        with mock.patch.object(self.a, '_req', side_effect=lambda *a, **k: sent.append(a) or dict(TOKEN)):
            q = self.start()
            self.assertRegex(q['challenge'], '^[0-9a-f]{64}$')
            status, page = self.back(q['port'], state=q['state'], code='c0de')
            self.assertTrue(self.done.wait(10))
        self.assertEqual((status, self.result), (200, [(True, 'Ann')]))
        self.assertIn('Signed in as Ann', page)
        (method, path, body), = sent
        self.assertEqual((method, path, body['state'], body['code']), ('POST', '/auth/exchange', q['state'], 'c0de'))
        self.assertEqual(hashlib.sha256(body['verifier'].encode()).hexdigest(), q['challenge'])   # the secret behind it
        self.assertNotIn(body['verifier'], self.opened[0])                                        # ...never in the link
        self.assertEqual((self.a.s['token'], settings.load()['token']), ('t' * 64, 't' * 64))

    def test_another_state_is_turned_away(self):
        with mock.patch.object(self.a, '_req', return_value=dict(TOKEN)) as req:
            q = self.start()
            self.assertEqual(self.back(q['port'], state='someone-elses-state', code='c0de')[0], 404)
            req.assert_not_called()
            self.assertFalse(self.done.is_set())
            self.back(q['port'], state=q['state'], code='c0de')            # (then its own: signed in)
            self.assertTrue(self.done.wait(10))
        self.assertEqual(self.result, [(True, 'Ann')])

    def test_refused_by_the_server_said_plainly(self):
        refused = api_mod.ApiError('sign-in not found or expired: sign in again', 404)
        with mock.patch.object(self.a, '_req', side_effect=refused):
            q = self.start()
            status, page = self.back(q['port'], state=q['state'], code='bad')
            self.assertTrue(self.done.wait(10))
        self.assertEqual(status, 200)
        self.assertIn('Sign-in failed', page)
        self.assertEqual(self.result, [(False, 'Sign-in failed: sign-in not found or expired: sign in again')])
        self.assertFalse(self.a.s.get('token'))

    def test_nobody_back_in_time(self):
        with mock.patch.object(api_mod, 'SIGNIN_WAIT_S', 1.5):
            self.start()
            self.assertTrue(self.done.wait(10))
        self.assertEqual(self.result, [(False, 'Steam sign-in timed out')])


if __name__ == '__main__':
    unittest.main()
