"""What the game does while a finished run waits for its official result (gamewatch.py): its telemetry, its window
"Not Responding", how its process ended; in words for the report."""
import unittest

from acr_daily import gamewatch


class FakeWin:
    """The Windows calls, as a game that runs, hangs, and is then ended from the Task Manager."""

    def __init__(self):
        self.code, self.hung_now, self.opened = None, False, []

    def open(self, pid):
        self.opened.append(pid)
        return 77

    def image(self, h):
        return r'D:\Games\Assetto Corsa Rally\acr\Binaries\Win64\acr.exe'

    def ended(self, h):
        return self.code

    def close(self, h):
        pass

    def hung(self, pid):
        return self.hung_now


class Watch(unittest.TestCase):
    def setUp(self):
        self.t = 1000.0
        self.win = FakeWin()
        self.w = gamewatch.GameWatch(win=self.win, clock=lambda: self.t)
        self.finds = 0

    def find(self):
        self.finds += 1
        return [4242]

    def test_a_game_that_hangs_and_is_ended_from_outside(self):
        w = self.w
        for state in ('stage', 'stage', 'menus'):
            w.telemetry(state)
            self.t += 10
        w.process(self.find)
        w.process(self.find)
        self.assertEqual((self.finds, self.win.opened, w.exe[-7:]), (1, [4242], 'acr.exe'))   # (one look-up, a handle)
        self.win.hung_now = True
        self.t += 5
        w.process(self.find)
        w.telemetry('none')
        self.t += 700
        self.win.code = 1
        w.process(self.find)
        texts = [x for _t, x in w.events]
        self.assertEqual(texts, [gamewatch.STATE_WORDS['stage'], gamewatch.STATE_WORDS['menus'],
                                 'Windows: the game is "Not Responding"', gamewatch.STATE_WORDS['none'],
                                 'the game ended: ' + gamewatch.exit_words(1)])
        said = gamewatch.summary(w.events, 1005)
        for part in ('left the stage at +0:15', '"Not Responding" at +0:30', 'ended from outside', 'at +12:10'):
            self.assertIn(part, said)
        lines = gamewatch.timeline(w.events, 1005)
        self.assertEqual(lines[0], '-5 s  ' + gamewatch.STATE_WORDS['stage'])
        self.assertTrue(lines[-1].startswith('+12:10  the game ended'))

    def test_exit_codes_in_words(self):
        self.assertIn('quit the normal way', gamewatch.exit_words(0))
        self.assertIn('Task Manager', gamewatch.exit_words(1))
        self.assertIn('access violation', gamewatch.exit_words(0xC0000005))
        self.assertIn('0xC0000005', gamewatch.exit_words(-1073741819))       # (a signed DWORD from ctypes)
        self.assertIn('a crash (exit code 0xC0001234)', gamewatch.exit_words(0xC0001234))
        self.assertEqual(gamewatch.exit_words(None), 'unknown')

    def test_without_windows_nothing_is_recorded_and_nothing_breaks(self):
        w = gamewatch.GameWatch(win=None)
        w.process(self.find)
        w.close()
        self.assertEqual((w.events, self.finds), ([], 0))
        self.assertEqual(gamewatch.summary([], 1000), '')

    def test_a_game_that_never_left_its_results_screen(self):
        w = self.w
        w.telemetry('stage')
        self.t += 790
        self.win.code = 0
        w.process(self.find)
        w.process(self.find)
        said = gamewatch.summary(w.events, 1000)
        self.assertIn('never left the stage', said)
        self.assertIn('quit the normal way', said)


if __name__ == '__main__':
    unittest.main()
