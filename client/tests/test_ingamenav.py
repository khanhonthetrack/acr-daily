"""The wheel / pad in ACR DAILY's pages (ingamenav.py, ingameapp.InGameApp.across): a wheel's D-pad read as its hat,
and Left / Right across a page's two columns (21 Nov 2026)."""
import unittest

from acr_daily import ingamenav
from acr_daily.ingameapp import InGameApp
from acr_daily.ingamekit import btn, col, row, scroll


class Hat(unittest.TestCase):
    def test_a_press_once_and_diagonals(self):
        n = ingamenav.MenuInputs.__new__(ingamenav.MenuInputs)
        n._was = {}
        self.assertEqual(n._pov(1, 0xFFFF), [])
        self.assertEqual(n._pov(1, 9000), ['right'])
        self.assertEqual(n._pov(1, 9000), [])              # (held: not again)
        self.assertEqual(n._pov(1, 0xFFFF), [])
        self.assertEqual(n._pov(1, 17000), ['down'])       # (nearer down than right)
        self.assertEqual(n._pov(1, 35500), ['up'])


class Across(unittest.TestCase):
    def ig(self, focus):
        ig = InGameApp.__new__(InGameApp)
        ig.dialog = None
        ig.focus = focus
        left = col(btn('comp.pick:e:1', 'A'), btn('comp.pick:e:2', 'B', ol='2B2B31'), btn('comp.pick:e:3', 'C'))
        right = col(btn('comp.car:2:0', 'car'), btn('comp.drive:2', 'DRIVE'), btn(None, c=None, fid='st:2:1'))
        ig._last_page = col(row(scroll(left, id='comp:list:league'), scroll(right, id='comp:pick:league/e-2')))
        return ig

    def test_right_to_the_main_button_left_back_to_the_pick(self):
        self.assertEqual(self.ig('comp.pick:e:3').across(1), 'comp.drive:2')
        self.assertEqual(self.ig('st:2:1').across(-1), 'comp.pick:e:2')

    def test_nothing_within_a_column_or_under_a_question(self):
        self.assertIsNone(self.ig('comp.pick:e:3').across(-1))
        self.assertIsNone(self.ig('comp.drive:2').across(1))
        ig = self.ig('comp.pick:e:1')
        ig.dialog = {'title': 'x'}
        self.assertIsNone(ig.across(1))


if __name__ == '__main__':
    unittest.main()
