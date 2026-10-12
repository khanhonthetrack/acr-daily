"""The app's tabs (tabsui.py): DAILIES, LEAGUES, 1V1 and CUPS, each underlined in its colour when on screen, the inbox's
letter (filled while something is unread); the driver strip (rating, world rank, credits); the 1V1 tab's challenges
(accept, decline, cancel) and the CUPS tab's cups (join, leave). On a Tk window that is never shown."""
import os
import sys
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import api as api_mod, inboxui, tabsui  # noqa: E402
from acr_daily.api import ApiError  # noqa: E402
from acr_daily.app import App  # noqa: E402
from test_app import tk_root  # noqa: E402
from test_inbox import ANN, BOB, ME, NOW, SITE, click, find, texts  # noqa: E402

MC3 = [{'name': 'Turini Montée'}, {'name': 'Mézien - St. Geniez'}, {'name': 'Turini Descente'}]


def challenges():
    """/api/h2h: Ann challenges me (50 each), I challenged Bob (a friendly), I beat Ann before."""
    return {'incoming': [{'id': 4, 'status': 'sent', 'stake': 50, 'mine': 'opponent', 'name': 'Friday duel', 'rally': 'Monte Carlo',
                          'challenger': {'steamId': ANN, 'name': 'Ann'}, 'opponent': {'steamId': ME, 'name': 'Me'},
                          'stages': MC3, 'answerBy': NOW + 3600000 * 5}],
            'outgoing': [{'id': 5, 'status': 'sent', 'stake': 0, 'mine': 'challenger', 'name': 'Me vs Bob', 'rally': 'Wales',
                          'challenger': {'steamId': ME, 'name': 'Me'}, 'opponent': {'steamId': BOB, 'name': 'Bob'},
                          'stages': MC3[:1], 'answerBy': NOW + 3600000}],
            'active': [],
            'past': [{'id': 3, 'status': 'settled', 'stake': 20, 'name': 'Old duel', 'winner': ME, 'note': 'by 1.250 s',
                      'challenger': {'steamId': ME, 'name': 'Me'}, 'opponent': {'steamId': ANN, 'name': 'Ann'}, 'stages': MC3}],
            'credits': True, 'maxStake': 1000}


def the_cups():
    """/api/cups: the official one (not in it), the Autumn Cup (in it)."""
    return {'open': [{'id': 'ur2m8an4', 'name': 'Inaugural Cup (beta)', 'official': True, 'fee': 0, 'prize': 1000, 'size': 128,
                      'entrants': 5, 'starts': NOW + 13 * 86400000, 'status': 'open', 'rally': 'Monte Carlo'},
                     {'id': 'abcd1234', 'name': 'Autumn Cup', 'official': False, 'fee': 25, 'prize': 0, 'size': 8, 'entrants': 3,
                      'starts': NOW + 86400000, 'status': 'open', 'rally': 'Wales'}],
            'running': [], 'finished': [], 'mine': ['abcd1234'], 'credits': True}


class Words(unittest.TestCase):
    def test_the_rating(self):
        self.assertEqual(tabsui.rating_text({'ratingOn': True, 'rating': {'rating': 1512, 'rank': 3, 'of': 40}}), 'RATING 1512 · #3 OF 40')
        self.assertEqual(tabsui.rating_text({'ratingOn': True, 'rating': None}), 'NOT RATED YET')
        self.assertEqual(tabsui.rating_text({'ratingOn': False, 'rating': None}), '')     # (no rating on the server)
        self.assertEqual(tabsui.rating_text(None), '')

    def test_a_challenge_and_a_result(self):
        c = challenges()
        self.assertEqual(tabsui.challenge_text(c['incoming'][0], 'opponent'), 'Ann · Monte Carlo · 3 stages · 50 each')
        self.assertEqual(tabsui.challenge_text(c['outgoing'][0], 'challenger'), 'Bob · Wales · 1 stage · friendly')
        self.assertEqual(tabsui.result_text(c['past'][0], ME), 'WON vs Ann (by 1.250 s)')
        self.assertEqual(tabsui.result_text(dict(c['past'][0], winner=ANN, note=None), ME), 'LOST vs Ann')
        self.assertEqual(tabsui.result_text(dict(c['past'][0], winner=None, note='nobody finished'), ME),
                         'NO CONTEST vs Ann (nobody finished)')

    def test_the_requests(self):
        a = api_mod.Api({'token': 'x' * 64})
        with mock.patch.object(a, '_req', return_value={}) as req:
            a.h2h()
            self.assertEqual(req.call_args, mock.call('GET', '/api/h2h', auth=True))
            a.h2h_answer(4, 'accept')
            self.assertEqual(req.call_args, mock.call('POST', '/api/h2h/4/accept', {}, auth=True))
            a.cups()
            self.assertEqual(req.call_args, mock.call('GET', '/api/cups', auth=True))
            a.cup_entry('abcd1234', 'leave')
            self.assertEqual(req.call_args, mock.call('POST', '/api/cups/abcd1234/leave', {}, auth=True))
            a.driver(ME)
            self.assertEqual(req.call_args, mock.call('GET', '/api/drivers/' + ME, auth=True))
            a.h2h_rematch(3)
            self.assertEqual(req.call_args, mock.call('POST', '/api/h2h/3/rematch', {}, auth=True))
            a.h2h_rematch(3, stake=0)
            self.assertEqual(req.call_args, mock.call('POST', '/api/h2h/3/rematch', {'stake': 0}, auth=True))
            a.h2h_challenge(ANN, 50, {'rally': 'Wales'})
            self.assertEqual(req.call_args, mock.call('POST', '/api/h2h', {'opponent': ANN, 'stake': 50, 'event': {'rally': 'Wales'}}, auth=True))
            a.players('an n')
            self.assertEqual(req.call_args, mock.call('GET', '/api/players?q=an%20n'))
            a.catalog()
            self.assertEqual(req.call_args, mock.call('GET', '/api/catalog'))
        with self.assertRaises(ValueError):
            a.h2h_answer(4, 'delete')                         # (only what the server takes)
        with self.assertRaises(ValueError):
            a.cup_entry('abcd1234', 'cancel')


class Harness(unittest.TestCase):
    """A bare App with its tabs, the driver strip and the views they switch; requests answered at once, what goes to
    the Tk thread done at once, every question answered yes."""

    def setUp(self):
        self.root = tk_root()
        self.addCleanup(self.root.destroy)
        sync = lambda target, daemon: mock.Mock(start=target)
        for p in (mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)),
                  mock.patch('acr_daily.tabsui.threading.Thread', side_effect=sync),
                  mock.patch('acr_daily.inboxui.threading.Thread', side_effect=sync)):
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch('acr_daily.tabsui.messagebox.askyesno', return_value=True)
        self.ask = p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.tabsui.messagebox.showwarning')
        self.warn = p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.inboxui.webbrowser.open')
        self.web = p.start()
        self.addCleanup(p.stop)
        a = App.__new__(App)
        a.root, a.api, a.sub_l = self.root, mock.Mock(), mock.Mock()
        a.api.base, a.api.configured = SITE, True
        a.api.h2h.return_value = challenges()
        a.api.cups.return_value = the_cups()
        a.api.driver.return_value = {'name': 'MaybeIWill', 'team': {'tag': 'GFX'}, 'ratingOn': True,
                                     'rating': {'rating': 1512, 'rank': 3, 'of': 40, 'races': 9, 'peak': 1530}}
        a.s = {'token': 't' * 64, 'steamId': ME, 'name': 'Me'}
        a._league_init()
        a.refresh_leagues, a.refresh_league_board, a.refresh_credits = mock.Mock(), mock.Mock(), mock.Mock()
        a._show_board_title, a._fill_tree = mock.Mock(), mock.Mock()
        a._build_tabs(self.root)
        a._build_driver_strip(self.root)
        a._head_rule = tk.Frame(self.root)
        a._head_rule.pack(fill='x')
        a.daily_box, a.league_box, a.league_strip = tk.Frame(self.root), tk.Frame(self.root), tk.Frame(self.root)
        a.league_rows = tk.Frame(a.league_box)
        a.league_rows.pack(fill='x')
        a.daily_box.pack(fill='x')
        a._status_frame = tk.Frame(self.root)
        a._status_frame.pack(fill='x')
        a.board_l = tk.Label(self.root, text='TIMING')
        a.board_l.pack(anchor='w')
        a.tree = tk.Frame(self.root)
        a.tree.pack(fill='both', expand=True)
        a._build_inbox_box()
        a.refresh_inbox = mock.Mock()
        self.a = a

    def underlined(self):
        """The tabs underlined (with their colours), the inbox's letter among them."""
        c = tabsui._c()
        out = {k: u.cget('bg') for k, (_l, u) in self.a._tab_parts.items() if u.cget('bg') != c.BG}
        if self.a.inbox_u.cget('bg') != c.BG:
            out['inbox'] = self.a.inbox_u.cget('bg')
        return out


class Tabs(Harness):
    def test_each_tab_underlined_in_its_colour_and_its_view_on_screen(self):
        a = self.a
        self.assertEqual(self.underlined(), {'daily': tabsui._c().WHITE})
        a.show_tab('h2h')
        self.assertEqual((a.league_view, a.league_kind, self.underlined()), (True, 'h2h', {'h2h': '#FF9F43'}))
        a.api.h2h.assert_called_once()                      # (its challenges)
        a.show_tab('cup')
        self.assertEqual((a.league_kind, self.underlined()), ('cup', {'cup': '#FFD60A'}))
        a.api.cups.assert_called_once()
        a.show_tab('league')
        self.assertEqual((a.league_kind, self.underlined()), ('league', {'league': '#5BA8FF'}))
        a.toggle_inbox_view()                                # the letter: a tab too
        self.assertEqual(self.underlined(), {'inbox': inboxui.INBOX_COLOUR})
        a.show_tab('daily')
        self.assertEqual((a.league_view, a.inbox_view, self.underlined()), (False, False, {'daily': tabsui._c().WHITE}))
        self.assertEqual(a.daily_box.winfo_manager(), 'pack')

    def test_the_letter_is_filled_while_something_is_unread(self):
        a = self.a
        body = lambda: a.inbox_b.itemcget(a.inbox_b.find_all()[0], 'fill')
        self.assertEqual((body(), a.inbox_n.winfo_manager()), (tabsui._c().BG, ''))
        a.inbox_unread = 3
        a._inbox_badge()
        self.assertEqual((body(), a.inbox_n.cget('text'), a.inbox_n.winfo_manager()), (inboxui.INBOX_COLOUR, '3', 'pack'))
        a.inbox_unread = 0
        a._inbox_badge()
        self.assertEqual((body(), a.inbox_n.winfo_manager()), (tabsui._c().BG, ''))


class DriverStrip(Harness):
    def test_name_team_rating_rank_and_credits(self):
        a = self.a
        a.credits = {'enabled': True, 'signedIn': True, 'balance': 150}
        a.refresh_driver()
        a.api.driver.assert_called_once_with(ME)
        self.assertEqual((a.driver_name.cget('text'), a.driver_rating.cget('text'), a.driver_credits.cget('text')),
                         ('[GFX] MaybeIWill', 'RATING 1512 · #3 OF 40', '150 '))
        a._set_driver(dict(a.driver, rating=None, team=None))
        self.assertEqual((a.driver_name.cget('text'), a.driver_rating.cget('text')), ('MaybeIWill', 'NOT RATED YET'))
        a._account_ui, a._wager_marks = mock.Mock(), mock.Mock()   # (the account line at the bottom, the dailies' cards)
        a._set_credits({'enabled': True, 'signedIn': True, 'balance': 0, 'earning': False})
        self.assertEqual(a.driver_credits.cget('text'), 'finish a run to earn credits')
        click(a.driver_page)
        self.web.assert_called_once_with('https://acrdaily.com/d/' + ME)

    def test_gone_when_signed_out(self):
        a = self.a
        self.assertEqual(a.driver_box.winfo_manager(), 'pack')
        a.s.pop('token')
        a._set_driver(None)
        self.assertEqual((a.driver, a.driver_box.winfo_manager()), (None, ''))
        a.s['token'] = 't' * 64                              # signed in again: back, over the rule
        a._set_driver({'name': 'Me', 'ratingOn': True, 'rating': None})
        self.assertEqual(a.driver_box.winfo_manager(), 'pack')


class Challenges(Harness):
    def setUp(self):
        super().setUp()
        self.a.show_tab('h2h')
        self.a._render_leagues()

    def test_listed_with_what_each_can_do(self):
        said = texts(self.a.league_rows)
        for x in ('No 1V1 matches open right now.', 'Ann · Monte Carlo · 3 stages · 50 each', 'ACCEPT', 'DECLINE',
                  'Bob · Wales · 1 stage · friendly', 'Waiting for their answer', 'CANCEL', 'WON vs Ann (by 1.250 s)', 'REMATCH'):
            self.assertIn(x, said)
        with mock.patch('acr_daily.challengeui.ChallengeDialog') as dlg:   # a new challenge: made here, not on the website
            click(find(self.a.league_rows, 'Challenge a driver  ›'))
        dlg.assert_called_once()
        self.web.assert_not_called()

    def test_rematch_asks_then_sends_the_same_again(self):
        a = self.a
        click(find(a.league_rows, 'REMATCH'))
        self.assertIn('Rematch Ann: the same stages, car and rules?', self.ask.call_args.args[1])
        self.assertIn('20 credits each', self.ask.call_args.args[1])
        a.api.h2h_rematch.assert_called_once_with(3)
        a.refresh_credits.assert_called()
        a.api.h2h_rematch.side_effect = ApiError('the stake is 20 credits: you have 5', 402)
        click(find(a.league_rows, 'REMATCH'))
        self.warn.assert_called_once_with('ACR Daily', 'Not sent: the stake is 20 credits: you have 5')

    def test_accept_takes_the_stake_after_asking(self):
        a = self.a
        a.credits = {'balance': 150}
        click(find(a.league_rows, 'ACCEPT'))
        self.assertIn('50 credits each (you have 150)', self.ask.call_args.args[1])
        a.api.h2h_answer.assert_called_once_with(4, 'accept')
        a.refresh_leagues.assert_called()                   # (the match: in 1V1 now)
        a.refresh_credits.assert_called()

    def test_refused_said_plainly(self):
        a = self.a
        a.api.h2h_answer.side_effect = ApiError('the stake is 50 credits: you have 10', 402)
        click(find(a.league_rows, 'ACCEPT'))
        self.warn.assert_called_once_with('ACR Daily', 'Not done: the stake is 50 credits: you have 10')

    def test_decline_and_cancel(self):
        a = self.a
        click(find(a.league_rows, 'DECLINE'))
        click(find(a.league_rows, 'CANCEL'))
        self.assertEqual(a.api.h2h_answer.call_args_list, [mock.call(4, 'decline'), mock.call(5, 'cancel')])

    def test_not_asked_yes_nothing_sent(self):
        self.ask.return_value = False
        click(find(self.a.league_rows, 'ACCEPT'))
        self.a.api.h2h_answer.assert_not_called()


class Cups(Harness):
    def setUp(self):
        super().setUp()
        self.a.show_tab('cup')
        self.a._render_leagues()

    def test_mine_and_the_ones_open(self):
        said = texts(self.a.league_rows)
        self.assertIn('Autumn Cup', said)                    # mine: LEAVE before the start
        self.assertIn('LEAVE', said)
        self.assertIn('OFFICIAL · Inaugural Cup (beta)', said)   # open for entries: JOIN
        self.assertTrue(any('free entry · prize 1000 · 5 of 128' in x for x in said), said)
        self.assertEqual(said.count('JOIN'), 1)

    def test_join_and_leave(self):
        a = self.a
        click(find(a.league_rows, 'JOIN'))
        click(find(a.league_rows, 'LEAVE'))
        self.assertEqual(a.api.cup_entry.call_args_list, [mock.call('ur2m8an4', 'join'), mock.call('abcd1234', 'leave')])
        self.assertIn('entry fee of 25 credits comes back', self.ask.call_args.args[1])
        click(find(a.league_rows, 'CUP ›'))
        self.web.assert_called_with('https://acrdaily.com/cup/abcd1234')


if __name__ == '__main__':
    unittest.main()
