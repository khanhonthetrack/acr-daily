"""Main window details: stage names, cancelling a DRIVE restart, and runs from a too-old app."""
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


class OfficialResult(unittest.TestCase):
    """A Rally Weekend daily: a finished run is sent with the game's own result from its save, or as a DNF."""

    def setUp(self):
        import tempfile
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_rallyweekend as t
        self.t = t
        self.T0 = t.T0
        self.save = os.path.join(tempfile.mkdtemp(), 'PlayerDataSaveSlot.sav')
        self.old = t.entry('WelesS4HafrenSouthFullForward', [t.run('HyundaiI20NRally2', [80.0, 156.1, 213.597], 29)],
                           self.T0 - 1428)
        self.write([self.old])
        a = App.__new__(App)
        a.root, a.sub_l, a.awaiting, a.active = mock.Mock(), mock.Mock(), [], 1
        a.dailies = {1: {'ch': {'mode': 'weekend', 'stageId': 'WelesS4HafrenSouthFullForward', 'carId': 'HyundaiI20NRally2'},
                         'judge': None}}
        a.on_result = mock.Mock()
        a._standing = mock.Mock()
        self.a = a
        p = mock.patch('acr_daily.saveslot.SAVE', self.save)
        p.start()
        self.addCleanup(p.stop)

    def write(self, entries):
        with open(self.save, 'wb') as f:
            f.write(b'junk' + self.t.results_list('DefaultRally', entries))

    def finish(self, clock_ms=203284):
        known = self.a._game_results()
        r = {'status': 'finished', 'reason': '', 'clockMs': clock_ms, 'resets': 1, 'totalMs': clock_ms,
             'startedAt': self.T0 + 40}
        self.a._await_official(1, r, known)
        return r

    def check(self, running=True):
        with mock.patch('acr_daily.saveslot.game_running', return_value=running):
            self.a._check_official()

    def test_sent_with_the_games_time_and_penalty(self):
        self.finish()
        self.check()
        self.a.on_result.assert_not_called()                     # not saved by the game yet
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        self.check()
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs'], r['official']['timeMs'], r['official']['penaltyMs']),
                         ('finished', 293284, 203284, 90000))
        self.assertEqual(r['official']['splitsMs'], [87618, 160034, 203284])
        self.assertEqual(self.a.awaiting, [])

    def test_no_result_from_the_game_is_a_dnf(self):
        self.finish()
        for _ in range(3):
            self.check(running=False)                            # the game closed and saved nothing new
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs']), ('dnf', None))
        self.assertIn('closed', r['reason'])
        self.assertEqual(self.a.awaiting, [])

    def test_a_result_with_another_time_is_not_this_run(self):
        self.finish(clock_ms=150000)
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        self.check()
        self.a.on_result.assert_not_called()
        for _ in range(3):
            self.check(running=False)
        r = self.a.on_result.call_args.args[0]
        self.assertEqual(r['status'], 'dnf')
        self.assertIn('3:23.284', r['reason'])


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
