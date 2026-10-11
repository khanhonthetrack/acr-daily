"""The inbox in the app: its requests, INBOX's unread count (asked for now and then, gone at the sign-out), and its view:
notices read once shown, the conversations, one opened, a reply sent or refused (on a Tk window that is never shown)."""
import os
import re
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import api as api_mod, inboxui, leagues  # noqa: E402
from acr_daily.app import App  # noqa: E402
from test_app import tk_root  # noqa: E402

ME, ANN, BOB = '76561198000000001', '76561198000000002', '76561198000000003'
SITE = 'https://acr-daily.acr-daily-server.workers.dev'
NOW = 1791482963000


def the_inbox():
    """/api/inbox: a new notice and an older one, a conversation with a new message and one with a driver I block."""
    return {'unread': 2,
            'notices': [{'id': 9, 'kind': 'h2h', 'body': 'Ann accepted Ann vs Me: drive it from ACR Daily\'s LEAGUES view.',
                         'ref': 'h2h:4', 'created': NOW - 120000, 'read': False},
                        {'id': 8, 'kind': 'cup', 'body': 'Autumn Cup, quarter-final: you against Bob.', 'ref': 'cup:abcd1234',
                         'created': NOW - 7200000, 'read': True}],
            'threads': [{'with': {'steamId': ANN, 'name': 'Ann', 'avatar': None, 'country': 'FR'},
                         'last': {'body': 'Good luck!', 'created': NOW - 60000, 'mine': False}, 'unread': 1, 'blocked': False},
                        {'with': {'steamId': BOB, 'name': 'Bob', 'avatar': None, 'country': None},
                         'last': {'body': 'See you on SS3', 'created': NOW - 86400000, 'mine': True}, 'unread': 0,
                         'blocked': True}]}


def with_ann():
    return {'with': {'steamId': ANN, 'name': 'Ann', 'avatar': None, 'country': 'FR'}, 'blocked': False,
            'messages': [{'id': 1, 'mine': True, 'body': 'Ready?', 'created': NOW - 120000},
                         {'id': 2, 'mine': False, 'body': 'Good luck!', 'created': NOW - 60000}]}


def texts(w):
    """Everything a part of the window says: its labels, and its text boxes."""
    out = []
    for ch in w.winfo_children():
        if isinstance(ch, tk.Label):
            out.append(ch.cget('text'))
        elif isinstance(ch, tk.Text):
            out.append(ch.get('1.0', 'end'))
        out.extend(texts(ch))
    return out


def find(w, text):
    """The label saying `text`."""
    for ch in w.winfo_children():
        if isinstance(ch, tk.Label) and ch.cget('text') == text:
            return ch
        hit = find(ch, text)
        if hit is not None:
            return hit
    return None


def click(w, seq='<Button-1>'):
    """A click (or a key) on a part of the window: its binding, run as Tk would run it."""
    w.tk.eval(re.sub(r'%[\w#]', lambda m: str(w) if m.group() == '%W' else '0', w.bind(seq)))


class InboxApi(unittest.TestCase):
    def test_the_requests(self):
        a = api_mod.Api({'token': 'x' * 64})
        with mock.patch.object(a, '_req', return_value={'unread': 3}) as req:
            self.assertEqual(a.inbox_unread(), 3)
            self.assertEqual(req.call_args, mock.call('GET', '/api/inbox/unread', auth=True))
            a.inbox()
            self.assertEqual(req.call_args, mock.call('GET', '/api/inbox', auth=True))
            a.inbox_with(ANN)
            self.assertEqual(req.call_args, mock.call('GET', '/api/inbox/with/' + ANN, auth=True))
            a.inbox_send(ANN, 'Good luck!')
            self.assertEqual(req.call_args, mock.call('POST', '/api/inbox/send', {'to': ANN, 'body': 'Good luck!'}, auth=True))
            a.inbox_read([9, 8])
            self.assertEqual(req.call_args, mock.call('POST', '/api/inbox/read', {'ids': [9, 8]}, auth=True))
            a.inbox_read()                                   # all of them
            self.assertEqual(req.call_args, mock.call('POST', '/api/inbox/read', {}, auth=True))

    def test_sent_signed_in_and_refusals_said_as_the_server_says_them(self):
        import io
        import urllib.error
        a = api_mod.Api({'token': 'x' * 64, 'server': SITE})
        refused = urllib.error.HTTPError(SITE + '/api/inbox/send', 429, 'Too Many Requests', {},
                                         io.BytesIO(b'{"error": "30 messages an hour at most: try again later"}'))
        with mock.patch('urllib.request.urlopen', side_effect=refused) as op, self.assertRaises(api_mod.ApiError) as e:
            a.inbox_send(ANN, 'One more')
        req = op.call_args.args[0]
        self.assertEqual((req.get_method(), req.full_url, req.get_header('Authorization')),
                         ('POST', SITE + '/api/inbox/send', 'Bearer ' + 'x' * 64))   # (the app's POSTs: by its sign-in)
        self.assertEqual((str(e.exception), e.exception.code), ('30 messages an hour at most: try again later', 429))


class DriverNames(unittest.TestCase):
    """A driver's own name and team (set on their driver page, server src/drivers.js) in the app."""

    def test_a_team_tag_by_the_name_on_the_timing_sheet(self):
        from acr_daily.app import shown_name
        self.assertEqual(shown_name({'name': 'Ann', 'look': {'tag': {'text': 'GFX', 'color': '#7BE07B'}}}), '[GFX] Ann')
        self.assertEqual(shown_name({'name': 'Ann', 'look': {'badge': 'x'}}), 'Ann')
        self.assertEqual(shown_name({'name': 'Ann'}), 'Ann')

    def test_the_name_set_on_the_website_comes_to_the_app(self):
        a = App.__new__(App)
        a.s = {'token': 't' * 64, 'name': 'SteamName'}
        a._account_ui, a._wager_marks = mock.Mock(), mock.Mock()
        with mock.patch('acr_daily.app.settings.save') as save:
            a._set_credits({'enabled': True, 'signedIn': True, 'name': 'Speedy Ann'})
            a._set_credits({'enabled': True, 'signedIn': True, 'name': 'Speedy Ann'})
        self.assertEqual(a.s['name'], 'Speedy Ann')
        save.assert_called_once()                            # (only when it changed)


class Harness(unittest.TestCase):
    """A bare App (App.__new__) with the parts of the window the inbox uses; its requests answered at once, and
    what goes to the Tk thread done at once."""

    def setUp(self):
        self.root = tk_root()
        self.addCleanup(self.root.destroy)
        for p in (mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)),
                  mock.patch('acr_daily.inboxui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)),
                  mock.patch.object(leagues, 'PARK_DIR', os.path.join(tempfile.mkdtemp(), 'league-rallies'))):
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch('acr_daily.inboxui.webbrowser.open')
        self.web = p.start()                                 # (the website's pages: where they would open)
        self.addCleanup(p.stop)
        a = App.__new__(App)
        a.root, a.api, a.sub_l = self.root, mock.Mock(), mock.Mock()
        a.api.base = SITE
        a.api.inbox.return_value = the_inbox()
        a.api.inbox_with.return_value = with_ann()
        a.api.inbox_unread.return_value = 0
        a.s = {'token': 't' * 64, 'steamId': ME, 'name': 'Me'}
        head = tk.Frame(self.root)
        head.pack(fill='x')
        a._build_inbox_button(head)
        a.daily_box, a.league_box, a.league_strip = tk.Frame(self.root), tk.Frame(self.root), tk.Frame(self.root)
        a.daily_box.pack(fill='x')
        a._status_frame = tk.Frame(self.root)
        a._status_frame.pack(fill='x')
        a.board_l = tk.Label(self.root, text='TIMING')
        a.board_l.pack(anchor='w', padx=20, pady=(14, 2))
        a.tree = tk.Frame(self.root)
        a.tree.pack(fill='both', expand=True, padx=20)
        a._build_inbox_box()
        self.a = a

    def said(self):
        return ' | '.join(texts(self.a.inbox_box))


class UnreadCount(Harness):
    def test_asked_for_and_shown_by_inbox(self):
        a = self.a
        a.api.inbox_unread.return_value = 3
        a.refresh_unread()
        self.assertEqual((a.inbox_unread, a.inbox_n.cget('text'), a.inbox_n.winfo_manager()), (3, '3', 'pack'))
        a.api.inbox_unread.side_effect = api_mod.ApiError('server not reachable')
        a.refresh_unread()                                   # offline: the count stays
        self.assertEqual(a.inbox_unread, 3)
        a.api.inbox_unread.side_effect, a.api.inbox_unread.return_value = None, 0
        a.refresh_unread()
        self.assertEqual(a.inbox_n.winfo_manager(), '')      # nothing unread: no count
        a.api.inbox.assert_not_called()                      # (the inbox itself: only for its view)

    def test_every_few_minutes_and_every_minute_while_the_inbox_is_open(self):
        a = App.__new__(App)
        a.root, a.api, a.update_info = mock.Mock(), mock.Mock(), {'version': '9.9.9'}
        a.dailies = {1: {'ch': {'endsAt': 9e15}}}
        for name in ('refresh_challenge', 'refresh_routes', 'refresh_leagues', 'refresh_credits', 'refresh_board',
                     'refresh_unread', 'flush_leagues'):
            setattr(a, name, mock.Mock())
        with mock.patch('acr_daily.app.threading.Thread'):
            for _ in range(10):
                a.periodic()                                 # (once a minute)
            self.assertEqual(a.refresh_unread.call_count, 10 // inboxui.INBOX_EVERY_MIN)
            a.inbox_view = True
            a.periodic()
        self.assertEqual(a.refresh_unread.call_count, 10 // inboxui.INBOX_EVERY_MIN + 1)

    def test_asked_for_at_the_sign_in(self):
        a = self.a
        a.s['token'] = ''
        a.api.configured = True
        a.api.login.side_effect = lambda done: done(True, 'Me')
        a.steam_b = mock.Mock()
        for name in ('_account_ui', 'refresh_board', 'refresh_leagues', 'refresh_credits', 'refresh_unread'):
            setattr(a, name, mock.Mock())
        with mock.patch('acr_daily.app.threading.Thread'):
            a.login_click()
        a.refresh_unread.assert_called_once()

    def test_the_sign_out_takes_it_all_away(self):
        a = self.a
        a.api.inbox_unread.return_value = 4
        a.toggle_inbox_view()
        a.refresh_unread()
        self.assertEqual(a.inbox_n.winfo_manager(), 'pack')
        a.api.logout.side_effect = lambda: a.s.update(token='', steamId='', name='')
        a._set_credits, a.refresh_leagues = mock.Mock(), mock.Mock()
        a.login_click()                                      # (signed in: Sign out)
        self.assertEqual((a.inbox_unread, a.inbox, a.inbox_n.winfo_manager()), (0, None, ''))
        self.assertIn('Sign in with Steam', self.said())
        self.assertNotIn('Good luck!', self.said())
        a._set_unread(4)                                     # an answer asked for before the sign-out
        self.assertEqual(a.inbox_unread, 0)


class View(Harness):
    def test_it_takes_the_cards_and_the_timing_sheets_place_and_gives_it_back(self):
        a = self.a
        a.toggle_inbox_view()
        self.assertEqual([w.winfo_manager() for w in (a.daily_box, a.board_l, a.tree, a.inbox_box)], ['', '', '', 'pack'])
        self.assertEqual(a.inbox_b.cget('fg'), inboxui._c().WHITE)
        a.toggle_inbox_view()
        self.assertEqual([w.winfo_manager() for w in (a.daily_box, a.board_l, a.tree, a.inbox_box)], ['pack', 'pack', 'pack', ''])
        self.assertEqual(int(a.board_l.pack_info()['padx']), 20)
        self.assertEqual(a.root.pack_slaves()[-2:], [a.board_l, a.tree])   # (in their place: last)
        # LEAGUES while the inbox is open: it makes way
        a.toggle_inbox_view()
        a.view_b, a.league_rows = mock.Mock(), tk.Frame(a.league_box)
        a.refresh_leagues, a._show_board_title, a._fill_tree = mock.Mock(), mock.Mock(), mock.Mock()
        a.toggle_league_view(True)
        self.assertFalse(a.inbox_view)
        self.assertEqual([w.winfo_manager() for w in (a.league_box, a.daily_box, a.tree, a.inbox_box)], ['pack', '', 'pack', ''])

    def test_notices_and_conversations(self):
        a = self.a
        a.toggle_inbox_view()
        said = self.said()
        for x in ('Ann accepted Ann vs Me', 'Autumn Cup, quarter-final', 'Ann', '1 NEW', 'Good luck!', 'You: See you on SS3',
                  'BLOCKED', 'Challenge a driver  ›', 'Cups  ›'):
            self.assertIn(x, said)
        # the new notice, shown: read (on the server, then in the count; Ann's message is still new)
        a.api.inbox_read.assert_called_once_with([9])
        self.assertEqual((a.inbox_unread, a.inbox['notices'][0]['read']), (1, True))
        a._render_inbox()
        a.api.inbox_read.assert_called_once()                # (not again)
        # what the app doesn't do: the website
        for link, path in (('Challenge a driver  ›', '/1v1'), ('Cups  ›', '/cups'), ('1V1s  ›', '/1v1'),
                           ('The cup  ›', '/cup/abcd1234')):
            click(find(a.inbox_box, link))
            self.web.assert_called_with('https://acrdaily.com' + path)
        # a notice of a match to drive: LEAGUES
        a.toggle_league_view = mock.Mock()
        click(find(a.inbox_box, 'LEAGUES  ›'))
        a.toggle_league_view.assert_called_once_with(True)

    def test_messages_are_said_not_to_be_private_and_my_page_is_a_click_away(self):
        a = self.a
        a.s['steamId'] = ME
        a.toggle_inbox_view()
        self.assertIn(inboxui.PRIVATE, self.said())
        click(find(a.inbox_box, 'Your driver page  ›'))
        self.web.assert_called_with('https://acrdaily.com/d/' + ME)
        click(find(a.inbox_box, 'Good luck!'))               # a conversation: under its reply box
        self.assertIn(inboxui.PRIVATE, self.said())

    def test_a_notice_not_marked_read_stays_new(self):
        a = self.a
        a.api.inbox_read.side_effect = api_mod.ApiError('server not reachable')
        a.toggle_inbox_view()
        self.assertEqual((a.inbox_unread, a.inbox['notices'][0]['read']), (2, False))
        a.api.inbox_read.side_effect = None
        a._render_inbox()                                    # shown again: read this time
        self.assertEqual(a.inbox_unread, 1)

    def test_a_conversation_opened(self):
        a = self.a
        a.toggle_inbox_view()
        click(find(a.inbox_box, 'Good luck!'))               # (a click anywhere on its row)
        a.api.inbox_with.assert_called_once_with(ANN)
        self.assertEqual((a.inbox_with, a.inbox_unread), (ANN, 0))   # (its messages read: the server's count)
        said = a.inbox_text.get('1.0', 'end')
        self.assertLess(said.index('You · '), said.index('Ready?'))
        self.assertLess(said.index('Ready?'), said.index('Ann · '))
        self.assertLess(said.index('Ann · '), said.index('Good luck!'))
        self.assertEqual(a.inbox['threads'][0]['unread'], 0)
        click(find(a.inbox_box, 'Open on the website  ›'))
        self.web.assert_called_with('https://acrdaily.com/inbox?with=' + ANN)
        click(find(a.inbox_box, '‹  INBOX'))                 # back: the list, asked for again
        self.assertIsNone(a.inbox_with)
        self.assertEqual(a.api.inbox.call_count, 2)
        self.assertIn('You: See you on SS3', self.said())

    def test_a_reply_sent(self):
        a = self.a
        a.toggle_inbox_view()
        a.open_conversation(ANN)
        a._inbox_var.set('  See you on SS1  ')
        click(a.inbox_entry, '<Return>')                     # (Enter, or SEND)
        a.api.inbox_send.assert_called_once_with(ANN, 'See you on SS1')
        self.assertEqual(a._inbox_var.get(), '')
        self.assertTrue(a.inbox_text.get('1.0', 'end').rstrip().endswith('See you on SS1'))
        a._inbox_var.set('Again')
        click(find(a.inbox_box, 'SEND  ›'))
        self.assertEqual(a.api.inbox_send.call_args.args, (ANN, 'Again'))

    def test_a_reply_refused_says_why_and_stays_in_the_box(self):
        a = self.a
        a.toggle_inbox_view()
        a.open_conversation(ANN)
        for err, said in ((api_mod.ApiError('30 messages an hour at most: try again later', 429),
                           'Not sent: 30 messages an hour at most: try again later.'),
                          (api_mod.ApiError('this driver takes no messages from you', 403),
                           'Not sent: this driver takes no messages from you.')):
            a.api.inbox_send.side_effect = err
            a._inbox_var.set('One more')
            a.inbox_send()
            self.assertEqual((a._inbox_note_l.cget('text'), a._inbox_note_l.cget('fg')), (said, inboxui._c().BAD))
            self.assertEqual(a._inbox_var.get(), 'One more')  # (to send again)
            self.assertNotIn('One more', a.inbox_text.get('1.0', 'end'))
        a._render_inbox()                                    # (drawn again: still said)
        self.assertIn('Not sent: this driver', self.said())
        a.api.inbox_send.reset_mock()
        a._inbox_var.set('x' * 501)                          # too long: not sent at all
        a.inbox_send()
        a.api.inbox_send.assert_not_called()
        self.assertIn('500 characters at most (this one has 501)', a._inbox_note_l.cget('text'))

    def test_signed_out_or_the_server_unreachable(self):
        a = self.a
        a.api.inbox.side_effect = api_mod.ApiError('server not reachable (timed out)')
        a.toggle_inbox_view()
        self.assertIn('Inbox: server not reachable (timed out)', self.said())
        a.toggle_inbox_view()
        a.s['token'] = ''
        a.toggle_inbox_view()
        self.assertIn('Sign in with Steam', self.said())


class Helpers(unittest.TestCase):
    def test_how_long_ago_and_where_a_notice_points(self):
        self.assertEqual([inboxui.ago(NOW - s * 1000, NOW) for s in (5, 600, 3 * 3600, 2 * 86400)],
                         ['now', '10 min', '3 h', '2 d'])
        self.assertEqual(inboxui.ref_page('cup:abcd1234'), ('The cup  ›', '/cup/abcd1234'))
        self.assertEqual(inboxui.ref_page('h2h:4'), ('1V1s  ›', '/1v1'))
        self.assertIsNone(inboxui.ref_page(None))
        self.assertEqual(inboxui.one_line('a\nb  c'), 'a b c')
        self.assertEqual(len(inboxui.one_line('x' * 100)), 60)
        self.assertEqual(inboxui.site_url(SITE, '/cups'), 'https://acrdaily.com/cups')


if __name__ == '__main__':
    unittest.main()
