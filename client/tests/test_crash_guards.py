"""The guards against the crashes and stray jumps of 24 Nov 2026: no app window over the game in front (DLSS frame
generation's present failed: widgets.game_in_front), no in-game DRIVE on packages changed since the game started
(ingamedrive.packages_changed_since_start), no stage list made under a running game (stagelist.build), and a question
that does something never outliving what it was about (ingameapp._dialog_upkeep)."""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from acr_daily import ingameapp, ingamedrive, stagelist, widgets  # noqa: E402


class PackagesSinceStart(unittest.TestCase):
    def test_a_package_newer_than_the_game(self):
        with tempfile.TemporaryDirectory() as game:
            mods = os.path.join(game, 'acr', 'Content', 'Paks', '~mods')
            os.makedirs(mods)
            p = os.path.join(mods, 'zz_acrdaily_stagelist_9_P.ucas')
            open(p, 'wb').close()
            now = time.time()
            os.utime(p, (now - 600, now - 600))
            started = now - 300
            # (the creation time of a file written just now is now: only the time it was changed is set back here)
            with mock.patch.object(os.path, 'getctime', lambda _p: now - 600):
                self.assertFalse(ingamedrive.packages_changed_since_start(game, started))
                os.utime(p, (now, now))                  # made again 30 s after the game started (24 Nov 2026)
                self.assertTrue(ingamedrive.packages_changed_since_start(game, started))
            self.assertFalse(ingamedrive.packages_changed_since_start(game, 0))     # (not running: nothing to say)
            other = os.path.join(mods, 'notes.txt')
            open(other, 'w').close()
            with mock.patch.object(os.path, 'getctime', lambda _p: now - 600):
                os.utime(p, (now - 600, now - 600))
                self.assertFalse(ingamedrive.packages_changed_since_start(game, started))   # (only packages count)


class NoListUnderTheGame(unittest.TestCase):
    def test_refused_while_the_game_runs(self):
        with mock.patch.object(stagelist, '_game_running', return_value=True), \
                mock.patch.object(stagelist, 'remove') as remove:
            with self.assertRaises(stagelist.ListError) as e:
                stagelist.build('X:\\game')
            self.assertEqual(e.exception.kind, 'running')
            remove.assert_not_called()                   # (the list the game runs with: left as it is)


class Win:
    """A Tk toplevel as the gate sees it."""

    def __init__(self, shown=True):
        self._state = 'normal' if shown else 'withdrawn'
        self.calls = []

    def state(self):
        return self._state

    def withdraw(self):
        self._state = 'withdrawn'
        self.calls.append('withdraw')

    def deiconify(self):
        self._state = 'normal'
        self.calls.append('deiconify')

    def winfo_ismapped(self):
        return self._state == 'normal'

    def attributes(self, *a):
        self.calls.append(a)


class NoWindowOverTheGame(unittest.TestCase):
    def test_kept_back_while_the_game_is_in_front_and_shown_after(self):
        w = Win(shown=True)
        with mock.patch.object(widgets, 'game_in_front', return_value=True):
            self.assertTrue(widgets.born(w))
            self.assertEqual(w.state(), 'withdrawn')
            self.assertFalse(widgets.show_window(w))      # (the card's own "back in the window": kept back)
            self.assertEqual(w.state(), 'withdrawn')
            self.assertFalse(widgets.keep_on_top(w, object()))
        with mock.patch.object(widgets, 'game_in_front', return_value=False):
            self.assertTrue(widgets.keep_on_top(w, object()))   # (the game no longer in front: shown)
            self.assertEqual(w.state(), 'normal')
            with mock.patch.object(widgets, 'game_in_front', return_value=True):
                widgets.keep_on_top(w, object())          # (the game brought to the front: put away again)
            self.assertEqual(w.state(), 'withdrawn')

    def test_put_away_on_purpose_stays_away(self):
        w = Win(shown=True)
        widgets.hide_window(w)                           # (the game draws it)
        with mock.patch.object(widgets, 'game_in_front', return_value=False):
            self.assertFalse(widgets.keep_on_top(w, object()))
        self.assertEqual(w.state(), 'withdrawn')


class Questions(unittest.TestCase):
    def ig(self):
        ig = ingameapp.InGameApp.__new__(ingameapp.InGameApp)
        ig.dialog, ig.ask_open, ig.prep = None, False, None
        ig._stage_n, ig._was_on_stage, ig._down_since = 0, False, None
        ig.on_stage, ig.up = False, True
        ig._on_a_stage = lambda: ig.on_stage
        ig.game_up = lambda: ig.up
        return ig

    def test_a_failed_drive_question_does_not_wait_through_a_stage(self):
        ig = self.ig()
        ig.ask('SS1', ['Not set up in the game.'], 'RESTART THE GAME', lambda: None, safe=True)
        ig.ask_open = True
        ig._dialog_upkeep(100.0)
        self.assertIsNotNone(ig.dialog)
        ig.on_stage = True                                # (the player drove the stage meanwhile)
        ig._dialog_upkeep(101.0)
        self.assertIsNone(ig.dialog)
        self.assertFalse(ig.ask_open)                     # (and the pages don't open for it on the next main menu)

    def test_the_game_closed_a_while_or_its_time_up(self):
        ig = self.ig()
        ig.ask('SS1', ['x'], 'GO', lambda: None)
        ig.up = False
        ig._dialog_upkeep(100.0)
        ig._dialog_upkeep(103.0)
        self.assertIsNotNone(ig.dialog)                   # (a hitch: kept)
        ig._dialog_upkeep(106.0)
        self.assertIsNone(ig.dialog)
        ig.up = True
        with mock.patch.object(ingameapp.time, 'monotonic', return_value=500.0):
            ig.ask('SS1', ['x'], 'GO', lambda: None, expires_s=120)
        ig._dialog_upkeep(560.0)
        self.assertIsNotNone(ig.dialog)
        ig._dialog_upkeep(621.0)
        self.assertIsNone(ig.dialog)

    def test_a_note_stays_and_a_safe_question_starts_on_cancel(self):
        ig = self.ig()
        ig.say('ACR Daily', ['Read me.'])
        ig.on_stage = True
        ig._dialog_upkeep(1.0)
        self.assertIsNotNone(ig.dialog)                   # (nothing to do by a stray press: kept)
        ig.dialog = None
        ig.ask('SS1', ['x'], 'RESTART THE GAME', lambda: None, safe=True)
        self.assertTrue(ig.dialog['safe'])


if __name__ == '__main__':
    unittest.main()
