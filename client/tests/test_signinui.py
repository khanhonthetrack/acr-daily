"""Steam first (signinui.py): signed out, a screen over the whole window asks for the Steam account and nothing else
is there; signed in, it goes, HOME comes and everything of the account is asked for. It comes back after Sign out or
when the server forgets the session. Without a server set, there is nothing to sign in to: no screen."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily.app import App  # noqa: E402
from test_app import tk_root  # noqa: E402
from test_inbox import click, find, texts  # noqa: E402

LOADS = ('refresh_board', 'refresh_leagues', 'refresh_credits', 'refresh_unread', 'refresh_driver', 'refresh_home_extras',
         'refresh_tt')


class Screen(unittest.TestCase):
    def setUp(self):
        self.root = tk_root()
        self.addCleanup(self.root.destroy)
        for p in (mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)),
                  mock.patch('acr_daily.signinui.threading.Thread')):
            p.start()
            self.addCleanup(p.stop)
        a = App.__new__(App)
        a.root, a.api, a.steam_b = self.root, mock.Mock(configured=True), mock.Mock()
        a.s = {'token': '', 'steamId': '', 'name': ''}
        a.home_box = mock.Mock()                             # (HOME built: it comes once signed in)
        for name in LOADS + ('_account_ui', '_mark_tabs', 'open_home', 'flush_leagues', 'quit'):
            setattr(a, name, mock.Mock())
        self.a = a

    def test_steam_first_then_everything_of_the_account(self):
        a = self.a
        a._gate_check()
        self.assertIsNotNone(a._gate)
        self.assertIn('SIGN IN TO START', texts(a._gate))
        self.root.update_idletasks()
        a.api.login.side_effect = lambda done: None          # (the browser open, Steam not back yet)
        click(find(a._gate, '  SIGN IN WITH STEAM'))
        click(a._gate_b)                                     # (once at a time)
        a.api.login.assert_called_once()
        self.assertEqual((a._gate_b.cget('text'), a._gate_msg.cget('text')),
                         ('  WAITING FOR STEAM…', 'Waiting for Steam in your browser…'))
        done = a.api.login.call_args.args[0]
        a.s['token'] = 't' * 64                              # (api.login keeps the token, then says so)
        done(True, 'Ann')
        self.assertIsNone(a._gate)
        for name in LOADS + ('open_home',):
            getattr(a, name).assert_called_once()
        a.refresh_tt.assert_called_once_with(full=True)
        a._gate_check()                                      # (the tick: signed in, no screen)
        self.assertIsNone(a._gate)

    def test_refused_said_on_the_screen_and_asked_again(self):
        a = self.a
        a._gate_check()
        a.api.login.side_effect = lambda done: done(False, 'Steam sign-in timed out')
        a.sign_in()
        self.assertEqual((a._gate_b.cget('text'), a._gate_msg.cget('text')),
                         ('  SIGN IN WITH STEAM', 'Steam sign-in timed out. Try again.'))
        a.sign_in()                                          # (not stuck: another go)
        self.assertEqual(a.api.login.call_count, 2)
        self.assertIsNotNone(a._gate)

    def test_back_after_the_sign_out_or_when_the_session_is_gone(self):
        a = self.a
        a.s['token'] = 't' * 64
        a._gate_check()
        self.assertIsNone(a._gate)
        a.api.logout.side_effect = lambda: a.s.update(token='', steamId='', name='')
        a._set_credits, a._set_driver = mock.Mock(), mock.Mock()
        a.login_click()                                      # Sign out
        a._gate_check()
        self.assertIsNotNone(a._gate)
        a._hide_gate()
        a.s['token'] = ''                                    # (the server forgot the session: api.py dropped it)
        a._gate_check()
        self.assertIsNotNone(a._gate)

    def test_no_server_no_screen(self):
        a = self.a
        a.api.configured = False
        a._gate_check()
        self.assertIsNone(a._gate)


if __name__ == '__main__':
    unittest.main()
