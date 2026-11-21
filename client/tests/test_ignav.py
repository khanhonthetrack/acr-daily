"""The wheel's arrows worked out by the app (ignav.py): where the buttons sit, the nearest one each way."""
import unittest

from acr_daily import ignav
from acr_daily.ingamekit import btn, col, row, scroll, size, sp, txt


def card(n):
    return col(size(sp(), h=200), btn('drive:%d' % n, 'DRIVE'), btn('watch:%d' % n, 'WATCH', pad=[0, 10, 0, 0]),
               scroll(*[btn(None, c=row(txt('row %d' % i)), fid='board:%d:%d' % (n, i)) for i in range(1, 6)],
                      id='b%d' % n), fill=1)


def page():
    return col(row(btn('tab:a', 'HOME'), btn('tab:b', 'DAILIES'), sp(fill=1), btn('close', 'BACK')),
               row(card(1), card(2), card(3), gap=20), fill=1)


class Moves(unittest.TestCase):
    def test_a_grid_of_cards(self):
        p = page()
        seq = [('down', 'drive:1'), ('right', 'drive:2'), ('right', 'drive:3'), ('right', None),
               ('down', 'watch:3'), ('down', 'board:3:1'), ('down', 'board:3:2'), ('left', 'board:2:2'),
               ('up', 'board:2:1'), ('up', 'watch:2'), ('up', 'drive:2'), ('up', 'tab:b')]      # (the nearer tab)
        at = 'tab:a'
        for d, want in seq:
            got = ignav.move(p, None, at, d)
            self.assertEqual(got, want, (at, d))
            at = got or at

    def test_a_question_alone(self):
        dialog = col(txt('Sure?'), row(btn('go', 'YES'), btn('cancel', 'NO')))
        self.assertEqual(set(ignav.places(page(), dialog)), {'go', 'cancel'})
        self.assertEqual(ignav.move(page(), dialog, 'go', 'right'), 'cancel')

    def test_nothing_focused_yet(self):
        self.assertEqual(ignav.move(page(), None, None, 'down'), 'tab:a')


class Guess(unittest.TestCase):
    def test_a_dash_from_how_the_car_moves(self):
        from acr_daily import livelink
        d = livelink.LiveDriver(1, 'Ann', 'Car', 1)
        # (speeding up: 20 m/s to 30 m/s over a second, along x)
        s, x = [], 0.0
        for i in range(0, 21):
            v = 20.0 + 10.0 * i / 20.0
            s.append([i * 50, x, 0.0, 0.0, 0.0, 0.0, 0.0])
            x += v * 0.05
        d.add(s, 10.0)
        d.play_clock = lambda now: 900
        got = d.dash_at(10.0)
        self.assertTrue(got['guess'])
        self.assertGreater(got['gas'], 0.5)
        self.assertEqual(got['brake'], 0.0)
        self.assertEqual(got['gear'], 5)          # (about 100 km/h: 4th gear, 2 = first)


if __name__ == '__main__':
    unittest.main()
