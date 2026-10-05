"""Main window details: stage names, cancelling a DRIVE restart, the LIVE lines, and runs from a too-old app."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import api as api_mod  # noqa: E402
from acr_daily.app import App, stage_name  # noqa: E402

LONG = {'track': 'Monte Carlo Peïra Cava', 'stageName': 'Peïra Cava', 'menuName': 'Peïra Cava - La Bollène-Vésubie'}


def tk_root():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    root.withdraw()
    return root


class StageNames(unittest.TestCase):
    def test_menu_name_first_short_one_for_the_timer(self):
        self.assertEqual(stage_name(LONG), 'Peïra Cava - La Bollène-Vésubie')
        self.assertEqual(stage_name(LONG, short=True), 'Peïra Cava')

    def test_older_servers_send_no_menu_name(self):
        ch = {'track': 'Alsace Forêt', 'stageName': 'Forêt'}
        self.assertEqual(stage_name(ch), 'Forêt')
        self.assertEqual(stage_name({'track': 'Alsace Forêt'}), 'Alsace Forêt')
        self.assertEqual(stage_name(None), '')

    def test_long_name_fits_its_card(self):
        import tkinter as tk
        from tkinter import font as tkfont
        root = tk_root()
        try:
            a = App.__new__(App)
            a.root = root
            label = tk.Label(root)
            a._fit_name(label, stage_name(LONG).upper())     # the longest menu name: one line
            font = tkfont.Font(font=label.cget('font'))
            self.assertLessEqual(font.measure(label.cget('text')), int(label.cget('wraplength')))
            a._fit_name(label, 'OBERSTEIGEN')
            self.assertEqual(int(tkfont.Font(font=label.cget('font')).actual('size')), 24)
            a._fit_name(label, 'VERY ' * 20)                # longer than any: smallest size, wrapped
            self.assertEqual(int(tkfont.Font(font=label.cget('font')).actual('size')), 16)
            self.assertGreater(int(label.cget('wraplength')), 0)
        finally:
            root.destroy()


class CancelDrive(unittest.TestCase):
    """DRIVE with the game open waits for the game to close; the same button then reads CANCEL and goes back."""

    def app(self):
        a = App.__new__(App)
        a.root = mock.Mock()
        a.root.after.return_value = 'job-1'
        a.cards = {1: {'drive': mock.Mock()}, 2: {'drive': mock.Mock()}}
        a.sub_l = mock.Mock()
        a.dailies = {1: {'ch': {'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2'}},
                     2: {'ch': {'track': 'Wales Severn', 'car': 'VW Polo GTI R5'}}}
        return a

    def test_cancel_while_the_game_closes(self):
        a = self.app()
        with mock.patch('acr_daily.saveslot.ask_game_to_quit'):
            a._restart_into(1)
        a.cards[1]['drive'].configure.assert_called_with(text='CANCEL  ✕')
        with mock.patch('acr_daily.saveslot.game_running', return_value=True):
            a.drive_click(2)                       # the other daily's button does nothing meanwhile
            self.assertEqual(a._restarting, 1)
            a.drive_click(1)                       # CANCEL
        self.assertFalse(a._restarting)
        a.root.after_cancel.assert_called_with('job-1')
        a.cards[1]['drive'].configure.assert_called_with(text='DRIVE  ›')
        self.assertIn('Cancelled', a.sub_l.configure.call_args.kwargs['text'])


class LiveLines(unittest.TestCase):
    def test_only_as_many_lines_as_there_is_commentary(self):
        import tkinter as tk
        root = tk_root()
        try:
            a = App.__new__(App)
            a.live_ls = [tk.Label(root) for _ in range(3)]
            a.active = 1
            a.dailies = {1: {'comments': []}}
            a._render_comments()
            self.assertEqual([l.winfo_manager() for l in a.live_ls], ['pack', '', ''])
            self.assertEqual(a.live_ls[0].cget('text'), 'No commentary yet today.')
            a.dailies[1]['comments'] = [{'created': 1791231379000, 'text': 'line %d' % i} for i in range(5)]
            a._render_comments()
            self.assertEqual([l.winfo_manager() for l in a.live_ls], ['pack', 'pack', 'pack'])
            self.assertTrue(a.live_ls[2].cget('text').endswith('line 2'))
        finally:
            root.destroy()


class TooOldForTheServer(unittest.TestCase):
    def test_refused_run_is_not_queued_and_queued_ones_are_dropped(self):
        a = api_mod.Api({'token': 'x' * 64})
        refuse = api_mod.ApiError('invalid: ACR Daily 0.14.1 is too old', api_mod.TOO_OLD)
        with mock.patch.object(a, '_req', side_effect=refuse), mock.patch.object(a, '_queue') as q:
            with self.assertRaises(api_mod.ApiError):
                a.submit({'challengeId': '2026-10-06/1'})
            q.assert_not_called()
        offline = api_mod.ApiError('server not reachable')
        with mock.patch.object(a, '_req', side_effect=offline), mock.patch.object(a, '_queue') as q:
            with self.assertRaises(api_mod.ApiError):
                a.submit({'challengeId': '2026-10-06/1'})
            q.assert_called_once()


if __name__ == '__main__':
    unittest.main()
