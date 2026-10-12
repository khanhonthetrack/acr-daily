"""Trackmania's $ codes in team tags (acr_daily/tmtext.py): the same answers as the server's (server src/tmtext.js and
its test in test/drivers.test.mjs)."""
import unittest

from acr_daily import tmtext


class Codes(unittest.TestCase):
    def test_colours_per_letter_dark_ones_lightened(self):
        self.assertEqual([(x['t'], x['c']) for x in tmtext.spans('$f00G$fffF$00fX')],
                         [('G', '#FF1C1C'), ('F', '#FFFFFF'), ('X', '#3F3FFF')])
        self.assertEqual([x['c'] for x in tmtext.spans('$fa0$0c0x')], ['#00CC00'])
        self.assertEqual([x['c'] for x in tmtext.spans('$000dark$g back')], ['#4D4D4D', None])

    def test_bold_italic_wide_narrow_reset(self):
        self.assertEqual([(x['t'], x['b']) for x in tmtext.spans('$oBold$z plain')], [('Bold', 1), (' plain', 0)])
        self.assertEqual([(x['t'], x['i'], x['w'], x['n']) for x in tmtext.spans('$i$wa$nb')], [('a', 1, 1, 0), ('b', 1, 0, 1)])

    def test_what_it_reads_as(self):
        self.assertEqual(tmtext.plain('$tgfx'), 'GFX')
        self.assertEqual(tmtext.plain('$$5 $l[https://x.y]Link$l'), '$5 Link')
        self.assertEqual(tmtext.plain('$h[a]b'), 'b')
        self.assertEqual(tmtext.plain('end$'), 'end')
        self.assertEqual(tmtext.plain('$q?'), '?')
        self.assertEqual(tmtext.plain(None), '')
        self.assertEqual(tmtext.spans('GFX'), [dict(t='GFX', c=None, b=0, i=0, w=0, n=0, u=0, s=0)])


if __name__ == '__main__':
    unittest.main()
