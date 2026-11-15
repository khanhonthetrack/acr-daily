"""The game's FPS (README, "The timer and the game's FPS"): the app's windows over the game are not moved to the top of
Windows' order on every tick, only when another program's window has come over them; the footer's count of runs to send
is not read from disk on every tick; 'Hide while driving' takes every window of the app off the game while a run's clock
runs."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import api as api_mod, widgets  # noqa: E402
from acr_daily.app import App, Overlay  # noqa: E402
from acr_daily.judge import Judge  # noqa: E402
from acr_daily.telemetry import Frame  # noqa: E402

CH = {'id': 'd/1', 'slot': 1, 'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2', 'route': [[0, 0], [100, 0]]}


def tk_root():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    root.withdraw()
    return root


def topmost_calls(attributes):
    return [c for c in attributes.call_args_list if c.args and c.args[0] == '-topmost']


class FakeWindows:
    """Windows' order of windows, top first: (hwnd, rect, shown, pid) each; ours is OURS."""
    OURS = 100

    def __init__(self, above=(), me=(10, 10, 310, 110)):
        self.order = list(above) + [(self.OURS, me, True, os.getpid())]

    def _at(self, h):
        return next(i for i, w in enumerate(self.order) if w[0] == h)

    def wrapper(self, win):
        return self.OURS

    def above(self, h):
        i = self._at(h)
        return self.order[i - 1][0] if i > 0 else None

    def rect(self, h):
        return self.order[self._at(h)][1]

    def shown(self, h):
        return self.order[self._at(h)][2]

    def pid(self, h):
        return self.order[self._at(h)][3]


class BackOnTop(unittest.TestCase):
    """widgets.covered / keep_on_top: back on top only when another program's window is over the overlay."""
    OTHER = os.getpid() + 1

    def test_nothing_above_or_nothing_over_it(self):
        self.assertFalse(widgets.covered(FakeWindows.OURS, FakeWindows()))
        self.assertFalse(widgets.covered(FakeWindows.OURS, FakeWindows([(1, (400, 0, 900, 500), True, self.OTHER)])))
        self.assertFalse(widgets.covered(FakeWindows.OURS, FakeWindows([(1, (0, 110, 900, 500), True, self.OTHER)])))  # touching

    def test_the_game_brought_over_it(self):
        self.assertTrue(widgets.covered(FakeWindows.OURS, FakeWindows([(1, (0, 0, 1920, 1080), True, self.OTHER)])))

    def test_hidden_windows_and_our_own_dont_count(self):
        above = [(1, (0, 0, 1920, 1080), False, self.OTHER),        # hidden, minimised or cloaked
                 (2, (0, 0, 1920, 1080), True, os.getpid())]        # the ghost cars' window, a display, a dialog
        self.assertFalse(widgets.covered(FakeWindows.OURS, FakeWindows(above)))
        self.assertTrue(widgets.covered(FakeWindows.OURS, FakeWindows(above + [(3, (300, 100, 400, 200), True, self.OTHER)])))

    def test_set_only_when_covered_and_shown(self):
        win = mock.Mock()
        win.winfo_ismapped.return_value = True
        self.assertFalse(widgets.keep_on_top(win, FakeWindows()))
        self.assertEqual(topmost_calls(win.attributes), [])
        game = FakeWindows([(1, (0, 0, 1920, 1080), True, self.OTHER)])
        self.assertTrue(widgets.keep_on_top(win, game))
        self.assertEqual(len(topmost_calls(win.attributes)), 1)
        win.winfo_ismapped.return_value = False                     # (hidden: left alone)
        self.assertFalse(widgets.keep_on_top(win, game))
        self.assertEqual(len(topmost_calls(win.attributes)), 1)

    def test_no_windows_no_harm(self):
        win = mock.Mock()
        with mock.patch.object(widgets, 'windows', return_value=None):
            self.assertFalse(widgets.keep_on_top(win))
        win.attributes.assert_not_called()

    def test_the_app_looks_twice_a_second_not_every_tick(self):
        a = App.__new__(App)
        a.overlay = mock.Mock()
        a.widgets = {'strip': mock.Mock(), 'delta': mock.Mock()}
        with mock.patch.object(widgets, 'keep_on_top') as keep:
            for i in range(20):                                     # one second of ticks, 50 ms apart
                a._keep_on_top(1000.0 + i * 0.05)
        self.assertEqual(keep.call_count, 2 * 3)                    # at 0 and 0.5 s: the timer and both displays
        self.assertEqual({c.args[0] for c in keep.call_args_list},
                         {a.overlay.win, a.widgets['strip'].win, a.widgets['delta'].win})


class TimerNotRaisedEachTick(unittest.TestCase):
    def test_render_leaves_the_order_of_windows_alone(self):
        root = tk_root()
        try:
            app = mock.Mock()
            app.root = root
            app.s = {'overlay': {'x': 10, 'y': 10, 'scale': 1.0, 'visible': True, 'locked': True}}
            app.penalty_s.return_value = 0
            ov = Overlay(app)
            with mock.patch.object(ov.win, 'attributes') as attributes:
                for i in range(40):                                 # two seconds of a run: 20 ticks a second
                    ov.render('live', 'SS1 · ALSACE FORÊT', 1000 + 50 * i, 0, 'vs #1  +0.%02d' % i)
                self.assertEqual(topmost_calls(attributes), [])
            self.assertEqual(ov.time.cget('text'), '0:02.95')
            ov.show(True)                                           # shown: put on top, once
            ov.win.destroy()
        finally:
            root.destroy()

    def test_the_next_daily_card_looks_every_half_second(self):
        from acr_daily import nextcard
        root = tk_root()
        try:
            with mock.patch.object(nextcard, 'keep_on_top') as keep:
                card = nextcard.NextCard(root, (10, 10), 't', 'n', 's', 'DRIVE', lambda: None)   # (its first tick)
                with mock.patch.object(card.win, 'attributes') as attributes:
                    for _i in range(19):                            # two seconds at STEP_MS
                        card._tick()
                    self.assertEqual(topmost_calls(attributes), [])
                self.assertEqual(keep.call_count, 4)                # every 5th tick of 20
                card.close()
        finally:
            root.destroy()


class FooterCount(unittest.TestCase):
    def test_runs_to_send_counted_without_reading_the_file_each_tick(self):
        a = api_mod.Api({'token': 'x' * 64})
        pending = os.path.join(tempfile.mkdtemp(), 'pending.json')
        with mock.patch('acr_daily.settings.PENDING', pending), mock.patch('acr_daily.settings.DIR', os.path.dirname(pending)):
            self.assertEqual(a.pending_count(), 0)                  # (no file yet)
            with mock.patch.object(a, '_req', side_effect=api_mod.ApiError('server not reachable')), \
                    self.assertRaises(api_mod.ApiError):
                a.submit({'challengeId': '2026-11-15/1'})          # offline: queued
            with mock.patch.object(a, '_pending', side_effect=AssertionError('read again')):
                for _i in range(20):                                # a second of ticks
                    self.assertEqual(a.pending_count(), 1)
            with mock.patch.object(a, '_req', return_value={}):
                self.assertEqual(a.flush(), 0)                      # sent
            self.assertEqual(a.pending_count(), 0)

    def test_read_once_from_disk(self):
        a = api_mod.Api({'token': ''})
        pending = os.path.join(tempfile.mkdtemp(), 'pending.json')
        with open(pending, 'w', encoding='utf-8') as f:
            f.write('[{"challengeId": "2026-11-14/1"}, {"challengeId": "2026-11-14/2"}]')
        with mock.patch('acr_daily.settings.PENDING', pending):
            self.assertEqual(a.pending_count(), 2)                  # (left from the last time the app ran)


class HideWhileDriving(unittest.TestCase):
    """App._overlays_allowed and hiding_while_driving on a stand-in app (no windows)."""

    def app(self, hide=True, locked=True, only=True):
        a = App.__new__(App)
        a.s = {'overlay': {'onlyOnDaily': only, 'locked': locked, 'hideDriving': hide}}
        a.recorder = None
        a.dailies = {1: {'ch': CH, 'judge': Judge(CH)}}
        return a

    def frame(self, clock=0):
        return Frame(0.0, 1, clock, 0.0, 0.0, 0.0, CH['car'], CH['track'])

    @staticmethod
    def running(j, paused=False):
        j.state, j.paused = 'running', paused
        return j

    def test_off_the_game_while_the_clock_runs(self):
        a = self.app()
        self.assertTrue(a._overlays_allowed(self.frame()))           # on the start line: shown
        self.running(a.dailies[1]['judge'])
        self.assertTrue(a.hiding_while_driving())
        self.assertFalse(a._overlays_allowed(self.frame(5000)))
        b = self.app(only=False)                                     # (shown everywhere else: not while driving)
        self.running(b.dailies[1]['judge'])
        self.assertFalse(b._overlays_allowed(None))

    def test_back_when_paused_or_over(self):
        a = self.app()
        j = self.running(a.dailies[1]['judge'], paused=True)
        self.assertTrue(a._overlays_allowed(self.frame(5000)))       # the game's pause menu: shown
        j.state, j.paused = 'finished', False
        self.assertFalse(a.hiding_while_driving())
        self.assertTrue(a._overlays_allowed(self.frame(90000)))      # the finish: the provisional time, the standings

    def test_as_before_with_the_option_off_or_while_moving_them(self):
        a = self.app(hide=False)
        self.running(a.dailies[1]['judge'])
        self.assertFalse(a.hiding_while_driving())
        self.assertTrue(a._overlays_allowed(self.frame(5000)))
        b = self.app(locked=False)
        self.running(b.dailies[1]['judge'])
        self.assertTrue(b._overlays_allowed(self.frame(5000)))

    def test_a_time_trial_or_league_stage_too(self):
        a = self.app()
        a._tt = {1: {'judge': self.running(Judge(dict(CH, id='tt:2026-11-09/1')))}}   # (App.tt: the week's stages)
        self.assertTrue(a.hiding_while_driving())
        b = self.app()
        b.league_run = {'judge': self.running(Judge(CH)), 'over': False}
        self.assertTrue(b.hiding_while_driving())
        b.league_run['over'] = True
        self.assertFalse(b.hiding_while_driving())

    def test_the_ghost_cars_window_asks_the_app(self):
        try:
            from acr_daily import ghostui
        except Exception as e:                                       # pragma: no cover
            self.skipTest('ghostui: %s' % e)
        ov = ghostui.GhostOverlay.__new__(ghostui.GhostOverlay)
        ov.app = mock.Mock()                                         # (a stand-in that says nothing: not hidden)
        self.assertFalse(ov._app_hides())
        a = self.app()
        ov.app = a
        self.assertFalse(ov._app_hides())
        self.running(a.dailies[1]['judge'])
        self.assertTrue(ov._app_hides())


if __name__ == '__main__':
    unittest.main()
