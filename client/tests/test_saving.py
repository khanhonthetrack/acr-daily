"""The timer window while a finished run's official time is on its way (app._saving, _render_saving, Overlay's bar):
what saves it with a piece going across while the game's results screen is up, then "Saving your official time…"
filling up over the save's settling (the app reads the save SETTLE_S after the game last wrote it), then saved, in
green, for a moment. A tester: "after the finish it isn't clear how long to wait"."""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import app as app_mod, saveslot  # noqa: E402
from acr_daily.app import App, Overlay  # noqa: E402


class Watch:
    def __init__(self, written=None, read=False):
        self.seen = None if written is None else (int(written * 1e9), 1000, 7)
        self.done = self.seen if read else None


class Phase(unittest.TestCase):
    def app(self, finished_ago, watch, practice=False):
        a = App.__new__(App)
        now = time.time()
        a.awaiting = [{'until': now - finished_ago + app_mod.OFFICIAL_WAIT_S, 'practice': practice}]
        a._official_watch = watch
        a.league_run = None
        return a, now

    def test_the_results_screen_still_up(self):
        a, now = self.app(20, Watch(written=time.time() - 300))      # (the save last written before the finish)
        self.assertEqual(a._saving(), 'wait')
        a, now = self.app(20, Watch())                                 # (not looked at yet)
        self.assertEqual(a._saving(), 'wait')

    def test_the_save_written_settling_then_settled(self):
        a, now = self.app(20, Watch(written=time.time() - saveslot.SETTLE_S / 2))
        self.assertAlmostEqual(a._saving(), 0.5, delta=0.05)
        a, now = self.app(60, Watch(written=time.time() - 3 * saveslot.SETTLE_S))
        self.assertEqual(a._saving(), 1.0)

    def test_read_without_its_result_waits_again(self):
        a, now = self.app(20, Watch(written=time.time() - 2, read=True))
        self.assertEqual(a._saving(), 'wait')

    def test_nothing_waits_or_only_practice(self):
        a, now = self.app(20, Watch(written=time.time() - 2), practice=True)
        self.assertIsNone(a._saving())
        a.awaiting = []
        self.assertIsNone(a._saving())

    def test_a_league_stage_too(self):
        a = App.__new__(App)
        a.awaiting, a._official_watch = [], None
        a.league_run = {'wait': {'until': time.time() - 20 + app_mod.OFFICIAL_WAIT_S,
                                 'watch': Watch(written=time.time() - saveslot.SETTLE_S / 4)}}
        self.assertAlmostEqual(a._saving(), 0.25, delta=0.05)


class Window(unittest.TestCase):
    def app(self, saving, saved_ago=None):
        a = App.__new__(App)
        a.overlay = mock.Mock()
        a._saving = lambda: saving
        a._saved_at = None if saved_ago is None else time.monotonic() - saved_ago
        return a

    def test_each_phase(self):
        a = self.app('wait')
        a._render_saving()
        self.assertEqual(a.overlay.set_alert.call_args.args[0], app_mod.OFFICIAL_ALERT)
        self.assertEqual(a.overlay.set_progress.call_args.args[0], 'wait')
        a = self.app(0.4)
        a._render_saving()
        self.assertEqual(a.overlay.set_alert.call_args.args[0], app_mod.SAVING_ALERT)
        self.assertEqual(a.overlay.set_progress.call_args.args[:2], ('saving', 0.4))
        a = self.app(None, saved_ago=1)
        a._render_saving()
        self.assertEqual(a.overlay.set_alert.call_args.args[0], 'Official time saved')
        a = self.app(None, saved_ago=app_mod.SAVED_SHOW_S + 1)
        a._render_saving()
        a.overlay.set_alert.assert_called_with('')
        a.overlay.set_progress.assert_called_with(None)


class Bar(unittest.TestCase):
    def test_the_bar_fills_goes_across_and_goes(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()
        try:
            app = mock.Mock()
            app.root = root
            app.s = {'overlay': {'x': 10, 'y': 10, 'scale': 1.0, 'visible': True, 'locked': True}}
            ov = Overlay(app)
            ov.set_alert(app_mod.SAVING_ALERT, bg=app_mod.PANEL2, fg=app_mod.WHITE)
            ov.set_progress('saving', 0.5)
            self.assertTrue(ov.prog.winfo_manager())
            x0, _y0, x1, _y1 = ov.prog.coords(ov._prog_fill)
            self.assertEqual(x0, 0)
            self.assertAlmostEqual(x1, int(ov.prog.cget('width')) * 0.5, delta=2)
            ov.set_progress('wait', colour=app_mod.SLOW)
            self.assertEqual(ov.prog.itemcget(ov._prog_fill, 'fill').upper(), app_mod.SLOW.upper())
            ov.set_progress(None)
            self.assertFalse(ov.prog.winfo_manager())
            ov.win.destroy()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
