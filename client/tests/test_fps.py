"""The game's FPS (README, "The timer and the game's FPS"): the app's windows over the game are not moved to the top of
Windows' order on every tick, only when another program's window has come over them; the footer's count of runs to send
is not read from disk on every tick; 'Hide while driving' (on by default after 0.1.5.1) takes the app's windows off the
screen a full-screen game fills while a run's clock runs, and only that screen."""
import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import api as api_mod, settings, widgets  # noqa: E402
from acr_daily.app import App, Overlay  # noqa: E402
from acr_daily.judge import Judge  # noqa: E402
from acr_daily.telemetry import Frame, PacketRate  # noqa: E402

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


SCREEN_A, SCREEN_B = (0, 0, 2560, 1440), (2560, 0, 4480, 1080)


class FakeScreens:
    """Windows as widgets.GameScreen and widgets.over see them: {hwnd: (rect, shown, minimised)} on two screens side by
    side (the main one 2560 x 1440, a second one 1920 x 1080 to its right)."""

    def __init__(self, wins):
        self.wins = dict(wins)
        self.u = mock.Mock()
        self.u.IsWindowVisible.side_effect = lambda h: self.wins[h][1]
        self.u.IsIconic.side_effect = lambda h: self.wins[h][2]
        self.looks = 0

    def alive(self, h):
        return h in self.wins

    @contextlib.contextmanager
    def physical(self):
        yield

    def rect(self, h):
        self.looks += 1
        return self.wins[h][0] if h in self.wins else None

    def monitor(self, h):
        r = self.wins[h][0]
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        return next((m for m in (SCREEN_A, SCREEN_B) if m[0] <= cx < m[2] and m[1] <= cy < m[3]), None)

    def wrapper(self, win):
        return win


class TheGamesScreen(unittest.TestCase):
    """widgets.screen_filled / GameScreen / over: which screen the game fills, if any, and what is on it."""

    def test_full_screen_or_borderless_at_the_screens_size(self):
        w = FakeScreens({1: (SCREEN_A, True, False), 2: (SCREEN_B, True, False), 3: ((-1, -1, 2561, 1441), True, False)})
        self.assertEqual(widgets.screen_filled(1, w), SCREEN_A)
        self.assertEqual(widgets.screen_filled(2, w), SCREEN_B)               # (the game on the second screen)
        self.assertEqual(widgets.screen_filled(3, w), SCREEN_A)               # (a frame a pixel past the edges)

    def test_a_window_minimised_hidden_or_gone_fills_none(self):
        w = FakeScreens({1: ((100, 100, 1700, 1000), True, False), 2: (SCREEN_A, True, True), 3: (SCREEN_A, False, False)})
        for h in (1, 2, 3, 4):
            self.assertIs(widgets.screen_filled(h, w), False)

    def test_looked_at_once_a_second_and_looked_for_while_not_found(self):
        t = [100.0]
        w = FakeScreens({7: (SCREEN_A, True, False)})
        found = []

        def find():
            found.append(t[0])
            return 7 if t[0] >= 103 and 7 in w.wins else None
        gs = widgets.GameScreen(w, find, clock=lambda: t[0])
        for _i in range(16):                                      # 4 s of ticks, a quarter of a second apart
            self.assertIsNone(gs.rect())                          # (not found yet: can't be told)
            t[0] += 0.25
        self.assertEqual(found, [100.0, 102.0])                   # looked for every 2 s until found
        self.assertEqual(gs.rect(), SCREEN_A)                     # (104 s: found)
        self.assertEqual(found, [100.0, 102.0, 104.0])
        looks = w.looks
        for _i in range(4):                                       # the next second: its window not looked at again
            t[0] += 0.25
            self.assertEqual(gs.rect(), SCREEN_A)
        self.assertEqual(w.looks - looks, 1)                      # (at 105 s)
        w.wins[7] = ((200, 200, 1800, 1100), True, False)         # made a window: fills no screen
        t[0] += 1.0
        self.assertIs(gs.rect(), False)
        del w.wins[7]                                             # closed: can't be told, looked for again
        t[0] += 1.0
        self.assertIsNone(gs.rect())
        self.assertEqual(found[-1], t[0])

    def test_no_windows_calls_cant_tell(self):
        self.assertIsNone(widgets.GameScreen(None).rect())

    def test_what_is_on_that_screen(self):
        w = FakeScreens({'timer': ((60, 60, 360, 200), True, False), 'strip': ((2600, 400, 2770, 820), True, False),
                         'both': ((2400, 0, 2700, 100), True, False)})
        self.assertTrue(widgets.over('timer', SCREEN_A, w))
        self.assertFalse(widgets.over('strip', SCREEN_A, w))      # on the second screen
        self.assertTrue(widgets.over('both', SCREEN_A, w))        # (any of it)
        self.assertTrue(widgets.over('gone', SCREEN_A, w))        # can't be told: it goes


class HideWhileDriving(unittest.TestCase):
    """App._hidden_screen, hiding_while_driving and _apply_visibility on a stand-in app (no windows): the game's screen
    given (widgets.GameScreen: a rect, False for a game in a window, None when it can't be told)."""

    def app(self, hide=True, locked=True, only=True, screen=None, on_game=('timer', 'strip', 'delta')):
        a = App.__new__(App)
        a.s = {'overlay': {'onlyOnDaily': only, 'locked': locked, 'visible': True}}
        if hide is not None:
            a.s['overlay']['hideOverGame'] = hide
        a.recorder = None
        a.dailies = {1: {'ch': CH, 'judge': Judge(CH)}}
        a.game_screen = mock.Mock(rect=mock.Mock(return_value=screen))
        a._ov_allowed, a._ov_state, a.next_card = True, (True, False, False), None
        a._mod_pulse = mock.Mock(alive=mock.Mock(return_value=False))     # (the game mod not running)
        a.overlay = mock.Mock(win='timer')
        a.widgets = {k: mock.Mock(win=k, cfg={'visible': True}) for k in ('strip', 'delta')}
        self.on_game = set(on_game)                               # (our windows on the screen the game fills)
        p = mock.patch.object(widgets, 'over', lambda win, off, w=None: win in self.on_game)
        p.start()
        self.addCleanup(p.stop)
        return a

    def frame(self, clock=0):
        return Frame(0.0, 1, clock, 0.0, 0.0, 0.0, CH['car'], CH['track'])

    @staticmethod
    def running(j, paused=False):
        j.state, j.paused = 'running', paused
        return j

    @staticmethod
    def shown(a):
        """-> what was last shown or hidden: {'timer': bool, 'strip': bool, 'delta': bool}."""
        out = {'timer': a.overlay.show.call_args.args[0]} if a.overlay.show.called else {}
        out.update({k: w.show.call_args.args[0] for k, w in a.widgets.items() if w.show.called})
        return out

    def test_on_by_default(self):
        a = self.app(hide=None)
        self.running(a.dailies[1]['judge'])
        self.assertTrue(a.hiding_while_driving())
        with tempfile.TemporaryDirectory() as d, mock.patch.object(settings, 'DIR', d):
            with open(os.path.join(d, 'settings.json'), 'w', encoding='utf-8') as f:
                json.dump({'overlay': {'x': 5, 'hideDriving': False}}, f)        # (0.1.5.1's switch, off then)
            s = settings.load()
        self.assertTrue(s['overlay']['hideOverGame'])
        self.assertNotIn('hideDriving', s['overlay'])
        self.assertEqual(s['overlay']['x'], 5)

    def test_off_the_game_while_the_clock_runs(self):
        a = self.app(screen=SCREEN_A)
        a._apply_visibility(self.frame())                            # on the start line: shown
        self.assertEqual(self.shown(a), {})                          # (as it was: nothing to change)
        self.running(a.dailies[1]['judge'])
        self.assertEqual(a._hidden_screen(), SCREEN_A)
        self.assertTrue(a._overlays_allowed(self.frame(5000)))       # (allowed: hidden by the rule on top)
        a._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(a), {'timer': False, 'strip': False, 'delta': False})
        self.assertFalse(a._ov_allowed)

    def test_a_window_on_another_screen_stays(self):
        a = self.app(screen=SCREEN_A, on_game={'strip'})              # the timer and the delta on the second screen
        self.running(a.dailies[1]['judge'])
        a._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(a), {'timer': True, 'strip': False, 'delta': True})
        self.assertFalse(a._others_shown())                          # (the strip hidden: the others not asked for)

    def test_a_game_in_a_window_hides_nothing(self):
        a = self.app(screen=False)                                   # composed by Windows anyway
        self.running(a.dailies[1]['judge'])
        self.assertFalse(a.hiding_while_driving())
        a._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(a), {})

    def test_every_screen_when_it_cant_be_told(self):
        a = self.app(screen=None, on_game=())
        self.running(a.dailies[1]['judge'])
        self.assertIsNone(a._hidden_screen())
        a._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(a), {'timer': False, 'strip': False, 'delta': False})

    def test_back_when_paused_or_over(self):
        a = self.app(screen=SCREEN_A)
        j = self.running(a.dailies[1]['judge'])
        a._apply_visibility(self.frame(5000))
        j.paused = True                                              # the game's pause menu: shown
        self.assertFalse(a.hiding_while_driving())
        a._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(a), {'timer': True, 'strip': True, 'delta': True})
        j.state, j.paused = 'finished', False                        # the finish: the provisional time, the standings
        self.assertFalse(a.hiding_while_driving())

    def test_the_game_draws_them_the_windows_stand_down(self):
        a = self.app(hide=False, screen=SCREEN_A)
        a.s['overlay']['inGame'] = True
        a._apply_visibility(self.frame())
        self.assertEqual(self.shown(a), {})                          # (the mod not running: as before)
        a._mod_pulse.alive.return_value = True                       # (the displays in the game, its mod running)
        a._apply_visibility(self.frame())
        self.assertEqual(self.shown(a), {'timer': False, 'strip': False, 'delta': False})
        a.s['overlay']['locked'] = False                             # (unlocked, to be moved: the windows)
        a._apply_visibility(self.frame())
        self.assertEqual(self.shown(a), {'timer': True, 'strip': True, 'delta': True})

    def test_as_before_with_the_option_off_or_while_moving_them(self):
        a = self.app(hide=False, screen=SCREEN_A)
        self.running(a.dailies[1]['judge'])
        self.assertFalse(a.hiding_while_driving())
        a._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(a), {})
        b = self.app(locked=False, screen=SCREEN_A)
        self.running(b.dailies[1]['judge'])
        b._apply_visibility(self.frame(5000))
        self.assertEqual(self.shown(b), {})

    def test_switched_on_the_settings_page(self):
        a = self.app(hide=False, screen=SCREEN_A)
        a._overlay_buttons = lambda: None
        self.running(a.dailies[1]['judge'])
        with mock.patch.object(settings, 'save'):
            a.toggle_hide_driving()
        self.assertTrue(a.s['overlay']['hideOverGame'])
        a._apply_visibility(self.frame(5000))                        # (applied on the next tick)
        self.assertEqual(self.shown(a), {'timer': False, 'strip': False, 'delta': False})

    def test_the_next_daily_card_goes_when_a_run_starts(self):
        a = self.app(screen=SCREEN_A, on_game={'timer', 'card'})
        a.next_card = mock.Mock(win='card', alive=True)
        a._apply_visibility(self.frame())
        a.next_card.close.assert_not_called()                        # (on the start line: it stays)
        self.running(a.dailies[1]['judge'])
        a._apply_visibility(self.frame(5000))
        a.next_card.close.assert_called_once()

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
        a = self.app(screen=SCREEN_A)
        ov.app = a
        self.assertFalse(ov._app_hides())
        self.running(a.dailies[1]['judge'])
        self.assertTrue(ov._app_hides())                             # (its window is always over the game)
        a.game_screen.rect.return_value = False                      # the game in a window: its names stay
        self.assertFalse(ov._app_hides())


class GameRate(unittest.TestCase):
    """telemetry.PacketRate and App._measure: how often the game writes its graphics page while a run's clock runs (its
    frames a second, if it writes one a frame), apart for what the app had over the full-screen game; in official.log
    after the run, for Send diagnostics."""

    @staticmethod
    def drive(feed, secs, per_s, key, t, p):
        """secs of 20 ticks a second, the game writing per_s packets a second. -> (t, p) after."""
        for _i in range(int(secs * 20)):
            t += 0.05
            p += per_s * 0.05
            feed(Frame(t, int(p), 1000, 0.0, 0.0, 90.0, CH['car'], CH['track']), key)
        return t, p

    def test_apart_by_what_was_over_the_game(self):
        r = PacketRate()
        t, p = self.drive(r.feed, 10, 130, 'clear', 100.0, 5000)
        t, p = self.drive(r.feed, 5, 64, 'over', t, p)
        self.assertIsNone(r.feed(None, None))                        # (paused: not counted, the run goes on)
        t, p = self.drive(r.feed, 5, 130, 'clear', t + 30, p + 999)  # (the pause's 30 s and its packets left out)
        line = r.feed(Frame(t, int(p), 0, 0.0, 0.0, 0.0, '', ''), None, end=True)
        self.assertEqual(line, '130/s with nothing of the app over the full-screen game (0:15); '
                               '64/s with a window of the app over the full-screen game (0:05)')
        self.assertEqual(r.take(), '')                               # (and it starts again)

    def test_a_stall_or_a_new_game_left_out(self):
        r = PacketRate()
        t, p = self.drive(r.feed, 3, 100, 'window', 0.0, 50000)
        r.feed(Frame(t + 2.5, 50, 1000, 0.0, 0.0, 0.0, '', ''), 'window')     # 2.5 s without a look; the game again
        t, p = self.drive(r.feed, 3, 100, 'window', t + 2.5, 50)
        self.assertEqual(r.feed(None, None, end=True), '100/s the game in a window (0:06)')

    def test_said_in_official_log_after_the_run(self):
        a = HideWhileDriving.app(self, screen=SCREEN_A)
        j = a.dailies[1]['judge']
        notes = []
        t = [0.0]
        with mock.patch('acr_daily.app.waiting.note', notes.append), \
                mock.patch.object(App, '_screen_state', lambda self: 'over' if t[0] < 2.5 else 'clear'):
            def feed(f, key):
                t[0] = f.t
                a._measure(f, f.t)
            self.drive(feed, 1, 60, None, 0.0, 0)                     # the start line: nothing measured
            j.state, j.paused = 'running', False
            tt, p = self.drive(feed, 4, 60, None, 1.0, 60)
            self.assertEqual(notes, [])
            j.state = 'finished'
            self.drive(feed, 1, 60, None, tt, p)
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith("the game's graphics packets while the clock ran: "))
        self.assertIn('60/s with a window of the app over the full-screen game (0:02)', notes[0])   # (the first 2 s)
        self.assertIn('60/s with nothing of the app over the full-screen game (0:02)', notes[0])


class PadSlots(unittest.TestCase):
    """The ghost cars' camera key (ghostui.CameraKeys): an empty pad slot is asked again every PAD_LOOK_S, not on every
    frame (Microsoft: XInputGetState on an empty slot is slow)."""

    def test_empty_slots_asked_every_few_seconds(self):
        try:
            from acr_daily import ghostui
        except Exception as e:                                       # pragma: no cover
            self.skipTest('ghostui: %s' % e)
        asked = []

        class XInput:
            plugged = {0}

            def XInputGetState(self, pad, st):
                asked.append(pad)
                return 0 if pad in self.plugged else 1167            # ERROR_DEVICE_NOT_CONNECTED
        k = ghostui.CameraKeys.__new__(ghostui.CameraKeys)
        k.keys, k.joy, k._was, k._joy_ids, k._joy_at, k.winmm = [], [], {}, {}, 0.0, None
        k.xinput, k._pad_next = XInput(), {}
        t = [500.0]
        with mock.patch.object(ghostui.time, 'monotonic', lambda: t[0]):
            for _i in range(120):                                    # 2 s of frames, 60 a second
                k.poll(True)
                t[0] += 1 / 60
            self.assertEqual(asked.count(0), 120)                    # the pad that is there: every frame
            self.assertEqual([asked.count(p) for p in (1, 2, 3)], [1, 1, 1])
            k.xinput.plugged = {0, 2}                                # a second pad plugged in: seen within PAD_LOOK_S
            for _i in range(int(ghostui.PAD_LOOK_S * 60)):
                k.poll(True)
                t[0] += 1 / 60
        self.assertEqual([asked.count(p) for p in (1, 3)], [2, 2])
        self.assertGreater(asked.count(2), 10)


if __name__ == '__main__':
    unittest.main()
