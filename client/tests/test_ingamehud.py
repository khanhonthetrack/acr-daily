"""The timer in the game, for VR (ingamehud.py): what the timer window and RANKED's turn window say, as rows of
coloured text the game mod draws (mod/ACRDailyGhosts/Scripts/hud.lua), and the file it reads."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import app as app_mod, ingamehud as hud, modinstall  # noqa: E402

LIVE = {'status': 'live', 'badge': ('● LIVE', '#FFFFFF', '#E10600'), 'title': 'TT3 · LONDON',
        'time': ('1:23.45', '#F4F4F5'), 'pen': '+10 s', 'line': ('−0.84 to P1 · gaining', '#30D158'), 'alert': None, 'panel': None}


def texts(rows):
    return [' '.join(s[4] for s in segs) for _bg, segs in rows]


class Rows(unittest.TestCase):
    def test_on_stage_the_badge_the_time_its_penalty_and_the_line(self):
        r = hud.rows(LIVE)
        self.assertEqual(texts(r), ['● LIVE TT3 · LONDON', '1:23.45 +10 s', '−0.84 to P1 · gaining'])
        badge = r[0][1][0]
        self.assertEqual((badge[0], badge[1], badge[3]), ('FFFFFF', 'E10600', True))     # (its colours, as drawn)
        self.assertEqual(r[1][1][1][:2], ('0A0A0C', 'FF9F0A'))                          # (the penalty's chip)

    def test_nothing_to_show_while_waiting_for_the_game_unless_a_note_or_ranked(self):
        quiet = dict(LIVE, status='standby', pen='', line=None)
        self.assertEqual(hud.rows(quiet), [])
        note = dict(quiet, alert={'head': 'Waiting for the official time', 'lines': ['Go on from the results screen'],
                                  'bg': '#1C1C21', 'head_fg': '#FF9F0A', 'fg': '#F4F4F5', 'dot_fg': '#FF9F0A'})
        self.assertIn('Waiting for the official time', texts(hud.rows(note)))
        self.assertIn('• Go on from the results screen', texts(hud.rows(note)))
        self.assertEqual(hud.rows(note)[-1][0], '1C1C21')                                # (the note's panel colour)
        gate = {'mode': 'turn', 'kicker': 'RANKED · RALLY2', 'stage': 'SS1 · ELATIA', 'head': 'GO', 'big': '0:13',
                'line': 'It is your turn.', 'now': 'Turn: YOU', 'rows': [('1', 'YOU', 'TURN', 'turn', True)],
                'light': '#30D158', 'edge': '#30D158', 'lit': True}
        r = hud.rows(quiet, gate)
        self.assertEqual(texts(r)[:3], ['RANKED · RALLY2 SS1 · ELATIA', '● ● ● ● ●', 'GO 0:13'])
        self.assertEqual(r[2][1][0][0], '30D158')                                        # (green: my turn)
        self.assertTrue(r[2][1][0][5])                     # (GO takes the width: the countdown at the right, as the window)

    def test_the_standings_after_a_split_my_row_marked(self):
        r = hud.rows(dict(LIVE, panel={'title': 'SPLIT 2', 'pos': 'P3 / 18', 'pb': ('vs your best today −0.830', '#30D158'),
                                       'rows': [('1', 'blah_walt', '', False), ('3', 'Me', '+2.010', True)]}))
        self.assertEqual(texts(r)[3:], ['SPLIT 2 P3 / 18', '1 blah_walt ', '3 Me +2.010', 'vs your best today −0.830'])
        mine = r[5][1]
        self.assertEqual((mine[1][0], mine[1][3], mine[1][5]), ('FF4655', True, True))   # (red, bold, the name fills)

    def test_bigger_with_the_timer_and_one_line_each(self):
        r = hud.rows(dict(LIVE, title='TWO\nLINES'), scale=1.5)
        self.assertEqual(r[1][1][0][2], 54)                                             # (the time: 36 at size 1)
        self.assertEqual(r[0][1][1][4], 'TWO LINES')                                    # (never a line break: one line a row)


class File(unittest.TestCase):
    def test_the_text_the_mod_reads(self):
        t = hud.encode(7, 'top', 1.0, True, [('-', [('F4F4F5', '-', 36, True, '1:23.45'), ('0A0A0C', 'FF9F0A', 16, True, '+10 s')]),
                                              ('1C1C21', [('85858E', '-', 12, False, 'Me', True)])])
        self.assertEqual(t.splitlines(), ['ACRHUD 1 7 0.5 0.03 0.5 0 340 1 0A0A0BE6', 'R 7 -', 'S 7 F4F4F5 - 36 b 1:23.45',
                                          'S 7 0A0A0C FF9F0A 16 b +10 s', 'R 7 1C1C21', 'S 7 85858E - 12 rf Me', 'end 7'])
        self.assertIn(' 0 0A0A0BE6', hud.encode(8, 'left', 1.0, True, []).splitlines()[0])   # (nothing to show: hidden)

    def test_written_when_it_changes_and_each_half_second_overwritten_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            f = hud.Feed(os.path.join(d, 'x', hud.FILE))
            long_ = [('-', [('F4F4F5', '-', 13, False, 'a long line ' * 5)])]
            self.assertTrue(f.write('left', 1.0, True, long_, now=0.0))
            self.assertFalse(f.write('left', 1.0, True, long_, now=0.1))                # (the same: not again yet)
            self.assertTrue(f.write('left', 1.0, True, long_, now=0.6))                 # (but at least twice a second)
            self.assertTrue(f.write('left', 1.0, True, [('-', [('F4F4F5', '-', 13, False, 'short')])], now=0.7))
            f.close()
            with open(os.path.join(d, 'x', hud.FILE), 'rb') as fh:
                data = fh.read().decode('utf-8')
            head, _, rest = data.partition('end 3\n')
            self.assertTrue(head.startswith('ACRHUD 1 3 ') and 'short' in head)
            self.assertEqual(rest.strip(), '')                                          # (the longer one before: blanked)


class Settings(unittest.TestCase):
    def test_the_game_mod_goes_in_for_the_timer_too(self):
        a = mock.Mock()
        for ghosts, timer, want in (({'on': True}, False, True), ({'on': False}, False, False), ({'on': False}, True, True),
                                    ({'on': True, 'ingame': False}, False, False)):
            a.s = {'ghostCars': ghosts, 'overlay': {'inGame': timer}}
            self.assertEqual(app_mod.App.want_game_mod(a), want, (ghosts, timer))
        self.assertIn('hud.lua', modinstall.MOD_FILES)
        self.assertTrue(set(hud.PLACES) == {'left', 'top', 'bottom'})


class Snapshot(unittest.TestCase):
    """The timer window as it draws itself -> the same words and colours in the game."""

    def test_the_timer_windows_words_and_colours(self):
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
            app.penalty_s.return_value = 10
            ov = app_mod.Overlay(app)
            ov.render('finished', 'TT3 · LONDON', 251320, 1, '')
            ov.set_alert('Waiting for the official time', ['Go on from the results screen'], 'warn')
            root.update_idletasks()
            s = ov.snapshot()
            self.assertEqual((s['status'], s['title'], s['time'][0], s['pen']), ('finished', 'TT3 · LONDON', '4:11.320', '+10 s'))
            self.assertEqual(s['alert']['head'], 'Waiting for the official time')
            self.assertEqual(s['alert']['head_fg'], app_mod.ALERT_KINDS['warn'][1])
            self.assertIsNone(s['panel'])
            r = hud.rows(s)
            self.assertIn('Waiting for the official time', texts(r))
            self.assertIn('4:11.320 +10 s', texts(r))
            ov.win.destroy()
        finally:
            root.destroy()
            # (nothing of Tk left for another test's thread to collect: "Tcl_AsyncDelete: async handler deleted by the
            # wrong thread" took the whole run down)
            app = ov = root = None
            import gc
            gc.collect()


if __name__ == '__main__':
    unittest.main()
