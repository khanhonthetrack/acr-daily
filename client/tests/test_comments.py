"""A comment on a run (commentui.py, server/src/comments.js): offered once a daily's counted run, a time trial run or a
league stage is on the server; the box; sending it (a league stage's after its result); shown on the timing sheets."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import api as api_mod, commentui, nextcard  # noqa: E402
from acr_daily.app import App  # noqa: E402
from acr_daily.commentui import MAX, with_comment  # noqa: E402

DAY = '2026-11-15'
SYNC = dict(side_effect=lambda target, daemon: mock.Mock(start=target))   # threads run at once


def tk_root():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    root.withdraw()
    return root


def bare_app():
    a = App.__new__(App)
    a.root, a.api, a.sub_l = mock.Mock(), mock.Mock(), mock.Mock()
    a.later = []
    a.root.after.side_effect = lambda ms, fn: a.later.append(fn)
    a.s = {'steamId': '7', 'token': 't' * 64, 'name': 'me'}
    a.dailies = {1: {'ch': {'id': DAY + '/1', 'date': DAY, 'slot': 1, 'stageName': 'Peïra Cava', 'car': 'C'},
                     'board': {'entries': []}}}
    a._tt = {2: {'ch': {'id': 'tt:2026-11-09/2', 'stageName': 'Sweet Lamb'}}}   # (App.tt reads it)
    a.refresh_board, a.refresh_credits, a.refresh_tt_board = mock.Mock(), mock.Mock(), mock.Mock()
    return a


def run_ui(a):
    while a.later:
        a.later.pop(0)()


class Cell(unittest.TestCase):
    def test_the_driver_cell_with_their_comment(self):
        self.assertEqual(with_comment('Ann', None), 'Ann')
        self.assertEqual(with_comment('Ann', 'Lost the rear\n in the hairpin'), 'Ann   “Lost the rear in the hairpin”')
        long = with_comment('Ann', 'x' * 100)
        self.assertTrue(long.endswith('x…”') and len(long) == len('Ann   “') + commentui.CELL + 1, long)


class Api(unittest.TestCase):
    def test_the_calls(self):
        a = api_mod.Api.__new__(api_mod.Api)
        with mock.patch.object(api_mod.Api, '_req', return_value={'comment': None}) as req:
            a.comment(DAY + '/1', 'Clean run')
            req.assert_called_with('POST', '/api/comments', {'on': DAY + '/1', 'text': 'Clean run'}, auth=True)
        with mock.patch.object(api_mod.Api, '_req', return_value={'comments': {'event:3/0': 'GG'}}) as req:
            self.assertEqual(a.my_comments(['event:3/0', 'tt:2026-11-09/1']), {'event:3/0': 'GG'})
            self.assertEqual(req.call_args.args[1], '/api/comments/mine?on=event%3A3%2F0%2Ctt%3A2026-11-09%2F1')


class Offers(unittest.TestCase):
    """Offered once the run is on the server: a daily's counted run (a time or a DNF), a time trial run, a league stage
    (or the DNF it ended on); never a practice run."""

    def submit(self, a, answer, result=None):
        a.api.submit.return_value = answer
        with mock.patch('acr_daily.app.settings.append_result'), mock.patch('acr_daily.app.threading.Thread', **SYNC):
            a.on_result(result or {'challengeId': DAY + '/1'})
            run_ui(a)

    def test_a_dailys_counted_run(self):
        a = bare_app()
        self.submit(a, {'ok': True, 'counted': True, 'status': 'finished', 'totalMs': 201456, 'rank': 3})
        self.assertEqual(a.comment_offer, {'on': DAY + '/1', 'what': 'SS1 · Peïra Cava · 3:21.456', 'kind': 'daily', 'short': 'SS1'})
        a.comment_offer = None
        self.submit(a, {'ok': True, 'counted': True, 'status': 'dnf', 'reason': 'retired'})
        self.assertEqual(a.comment_offer['what'], 'SS1 · Peïra Cava · DNF')

    def test_not_a_practice_run_nor_one_the_server_refused(self):
        a = bare_app()
        self.submit(a, {'ok': True, 'counted': False, 'status': 'finished', 'totalMs': 199000})
        self.assertIsNone(a.comment_offer)
        a.api.submit.side_effect = api_mod.ApiError('invalid run', 422)
        self.submit(a, None)
        self.assertIsNone(a.comment_offer)

    def test_a_time_trial_run(self):
        a = bare_app()
        a._offer_tt_comment({'challengeId': 'tt:2026-11-09/2', 'totalMs': 300000}, {'ok': True, 'totalMs': 299500})
        self.assertEqual(a.comment_offer, {'on': 'tt:2026-11-09/2', 'what': 'TT2 · Sweet Lamb · 4:59.500', 'kind': 'tt', 'short': 'TT2'})

    def test_a_league_stage_and_the_dnf_it_ended_on(self):
        a = bare_app()
        a._league_send_stage = mock.Mock(return_value=(200000, 5000))
        a._notify, a._render_leagues = mock.Mock(), mock.Mock()
        ev = {'id': 7, 'name': 'Final', 'kind': 'cup', 'stages': [{'name': 'Sweet Lamb'}]}
        run = {'ev': ev, 'no': 0, 'wait': {'result': {}}}
        a._league_stage_done(run, {'time': 200.0, 'penalty': 5.0})
        self.assertEqual(a.comment_offer, {'on': 'event:7/0', 'what': 'Final · SS1 · 3:25.000', 'kind': 'cup', 'short': 'SS1'})
        a._league_dnf_entry = mock.Mock()
        ev2 = {'id': 8, 'name': 'Round 2', 'stages': [{}, {}], 'entry': {'status': 'running', 'done': 1}}
        a._league_failed({'ev': ev2, 'no': 1}, 'retired')
        self.assertEqual(a.comment_offer, {'on': 'event:8/1', 'what': 'Round 2 · SS2 · DNF', 'kind': 'league', 'short': 'SS2'})


class Sending(unittest.TestCase):
    def go(self, a, offer, text):
        box = mock.Mock()
        with mock.patch('acr_daily.commentui.threading.Thread', **SYNC):
            a._send_comment(offer, text, box)
        run_ui(a)
        return box

    def test_sent_then_said(self):
        a = bare_app()
        o = {'on': DAY + '/1', 'what': 'SS1 · Peïra Cava · 3:21.456', 'kind': 'daily', 'short': 'SS1'}
        box = self.go(a, o, 'Clean run')
        a.api.comment.assert_called_once_with(DAY + '/1', 'Clean run')
        box.close.assert_called_once()
        self.assertEqual(a._comment_said, {DAY + '/1': 'Clean run'})
        self.assertIn('Comment sent: SS1 · Peïra Cava · 3:21.456', a.sub_l.configure.call_args.kwargs['text'])
        a.refresh_board.assert_called_once()
        self.go(a, o, '')
        self.assertEqual(a.sub_l.configure.call_args.kwargs['text'], 'Comment taken back.')

    def test_a_league_stage_after_its_result(self):
        a = bare_app()
        order = mock.Mock()
        a.flush_leagues, a.api.comment = order.flush, order.comment
        self.go(a, {'on': 'event:7/0', 'what': 'Final · SS1', 'kind': 'cup', 'short': 'SS1'}, 'GG')
        self.assertEqual([c[0] for c in order.mock_calls], ['flush', 'comment'])

    def test_refused_said_in_the_box(self):
        a = bare_app()
        a.api.comment.side_effect = api_mod.ApiError('too late to comment on that daily', 409)
        box = self.go(a, {'on': DAY + '/1', 'what': 'SS1', 'kind': 'daily', 'short': 'SS1'}, 'x')
        box.failed.assert_called_once_with('too late to comment on that daily')
        box.close.assert_not_called()

    def test_signed_out_no_box(self):
        a = bare_app()
        a.s['token'] = ''
        a.comment_offer = {'on': DAY + '/1', 'what': 'SS1', 'kind': 'daily', 'short': 'SS1'}
        with mock.patch('acr_daily.commentui.CommentDialog') as dlg:
            a.open_comment()
        dlg.assert_not_called()
        self.assertIn('Sign in with Steam', a.sub_l.configure.call_args.kwargs['text'])


class Box(unittest.TestCase):
    """The box itself, on a real Tk (skipped without a display)."""

    def setUp(self):
        self.root = tk_root()
        self.addCleanup(self.root.destroy)

    def test_one_line_cut_to_max_sent_without_extra_spaces(self):
        sent = []
        d = commentui.CommentDialog(self.root, 'SS1 · Peïra Cava · 3:21.456', commentui.NOTE['daily'], '', sent.append)
        d.var.set('  Lost   the rear  ')
        d._send()
        self.assertEqual(sent, ['Lost the rear'])
        self.assertTrue(d.busy)
        d.failed('too late')
        self.assertFalse(d.busy)
        self.assertEqual(d.msg.cget('text'), 'Not sent: too late')
        d.var.set('y' * (MAX + 30))                       # (a long paste)
        self.assertEqual(len(d.var.get()), MAX)
        self.assertEqual(d.count.cget('text'), '%d / %d' % (MAX, MAX))
        d.close()
        self.assertFalse(d.alive)

    def test_what_was_sent_before_fills_it_unless_typed_meanwhile(self):
        d = commentui.CommentDialog(self.root, 'SS1', commentui.NOTE['league'], '', lambda t: None)
        d.prefill('From the server')
        self.assertEqual(d.var.get(), 'From the server')
        d2 = commentui.CommentDialog(self.root, 'SS1', commentui.NOTE['league'], '', lambda t: None)
        d2.var.set('typing')
        d2.prefill('From the server')
        self.assertEqual(d2.var.get(), 'typing')

    def test_the_next_card_has_comment_only_when_offered(self):
        clicked = []
        c = nextcard.NextCard(self.root, (10, 10), 'SS1 FINISHED', 'Next: SS2', 'C', 'DRIVE', lambda: None,
                              on_comment=lambda: clicked.append(1))
        self.assertIsNotNone(c.comment_b)
        c.comment_b.event_generate('<Button-1>')
        self.assertEqual(clicked, [1])
        self.assertTrue(c.alive)                          # (the card stays)
        c.close()
        c2 = nextcard.NextCard(self.root, (10, 10), 'SS1 FINISHED', 'Next: SS2', 'C', 'DRIVE', lambda: None)
        self.assertIsNone(c2.comment_b)
        c2.close()


if __name__ == '__main__':
    unittest.main()
