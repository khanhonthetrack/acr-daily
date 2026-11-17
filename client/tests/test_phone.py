"""ON YOUR PHONE (phoneui.py): the page on screen as a QR code, and the QR code itself (qr.py)."""
import hashlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import qr  # noqa: E402
from acr_daily.app import App  # noqa: E402


def fingerprint(m):
    return hashlib.sha256(''.join('1' if v else '0' for row in m for v in row).encode()).hexdigest()


class QrCode(unittest.TestCase):
    def test_codes_a_decoder_reads(self):
        """These two were read back by jsQR (Nov 2026; versions 1 to 10 all were): the code must not change under them.
        A version 2 (one block) and a version 9 (five blocks, interleaved, with the version's own bits)."""
        self.assertEqual(fingerprint(qr.matrix('https://acrdaily.com/')),
                         'cf640db181bb96e17c81416c8716cc3d3275c5260d79280412f99f22c18bf1cb')
        self.assertEqual(fingerprint(qr.matrix('https://acrdaily.com/d/76561198000000000/' + 'y' * 120)),
                         '0de3315afeb766ae356f615721b9830ce202e5d865d5e91bbf1a9a6deadddbc8')

    def test_the_finders_and_the_size(self):
        for text in ('A', 'https://acrdaily.com/e/63', 'x' * 200):
            m = qr.matrix(text)
            n = len(m)
            self.assertEqual((n - 17) % 4, 0)
            self.assertTrue(all(len(row) == n for row in m))
            for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):        # a finder: dark ring, light ring, dark middle
                self.assertTrue(m[cy][cx] and m[cy - 3][cx] and not m[cy - 2][cx] and m[cy - 1][cx])

    def test_the_smallest_version_that_holds_it(self):
        self.assertEqual(qr.version_for(14), 1)
        self.assertEqual(qr.version_for(15), 2)
        self.assertEqual(qr.version_for(213), 10)
        self.assertIsNone(qr.version_for(214))
        with self.assertRaises(ValueError):
            qr.matrix('y' * 300)


class PhonePage(unittest.TestCase):
    def app(self, **kw):
        a = App.__new__(App)
        a.s, a.dailies, a.active = {'steamId': '76561198000000000'}, {1: {}, 2: {}}, 2
        for k, v in kw.items():
            setattr(a, k, v)
        return a

    def test_the_page_on_screen(self):
        self.assertEqual(self.app().phone_page()[0], '/#ss2')
        self.assertEqual(self.app(tt_view=True).phone_page()[0], '/tt')
        self.assertEqual(self.app(inbox_view=True).phone_page()[0], '/inbox')
        self.assertEqual(self.app(profile_view=True).phone_page()[0], '/d/76561198000000000')
        self.assertEqual(self.app(league_view=True, league_kind='league', league_sel=63).phone_page()[0], '/e/63')
        self.assertEqual(self.app(league_view=True, league_kind='league', league_sel=None).phone_page()[0], '/leagues')
        self.assertEqual(self.app(league_view=True, league_kind='cup').phone_page()[0], '/cups')
        self.assertEqual(self.app(league_view=True, league_kind='h2h').phone_page()[0], '/1v1')
        self.assertEqual(self.app(active=None).phone_page()[0], '/')

    def test_the_window_shows_its_code(self):
        from test_app import tk_root
        root = tk_root()
        try:
            a = self.app(root=root, api=mock.Mock(configured=True, site='https://acrdaily.com'))
            w = a.open_phone()
            texts = []

            def walk(x):
                for ch in x.winfo_children():
                    if ch.winfo_class() == 'Label':
                        texts.append(ch.cget('text'))
                    walk(ch)
            walk(w)
            self.assertIn('https://acrdaily.com/#ss2', texts)
            self.assertIn('ON YOUR PHONE', texts)
            canvas = [ch for ch in w.winfo_children()[0].winfo_children() if ch.winfo_class() == 'Canvas'][0]
            self.assertGreater(len(canvas.find_all()), 50)            # (the code's dark modules)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
