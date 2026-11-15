"""The photos behind the cards (photos.py) and the icons (icons.py): each photo credited and on disk, cut to the size
asked; each icon drawn at each size; an event's figures beside its card (leagueui.event_figures)."""
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import icons, leagueui, photos  # noqa: E402
from test_app import tk_root  # noqa: E402

PARTS = ('dailies', 'tt', 'leagues', 'h2h', 'cups', 'community', 'london')     # (london: ACR DAILY London's card)
RALLIES = ('Monte Carlo', 'Greece', 'Alsace', 'Wales', 'Livigno')
FREE = ('CC0 1.0', 'CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain')
SHARE_ALIKE = {'community': 'CC BY-SA'}   # (the one photo under share-alike, chosen for COMMUNITY: CREDITS.md says its
                                         # resized copy is shared under the same licence)
DAY, HOUR = 86400000, 3600000


class Photos(unittest.TestCase):
    def test_each_part_and_rally_has_a_credited_photo(self):
        m = photos.meta()
        self.assertEqual(sorted(m), sorted(PARTS + tuple(photos.for_rally(r) for r in RALLIES)))
        for key, p in m.items():
            self.assertTrue(os.path.isfile(os.path.join(photos.DIR, p['file'])), key)
            # (nothing non-free, no share-alike but the one named: from Wikimedia Commons, or a render of ours)
            self.assertIn(p['licence'], FREE + ((SHARE_ALIKE[key],) if key in SHARE_ALIKE else ()), key)
            self.assertTrue(p['author'] and p['title'] and p['url'].startswith(
                ('https://commons.wikimedia.org/', 'https://github.com/khanhonthetrack/')), key)
        self.assertEqual(len(photos.credits()), len(m))
        self.assertEqual((photos.for_rally('Monte Carlo'), photos.for_rally('Nowhere'), photos.for_rally(None)),
                         ('monte-carlo', None, None))

    @unittest.skipIf(photos.Image is None, 'Pillow (with ImageTk) not installed')
    def test_cut_to_the_cards_size(self):
        img = photos.compose('wales', 300, 120, active=True, road=[10, 10, 100, 50, 200, 30])
        self.assertEqual(img.size, (300, 120))
        self.assertGreater(img.getpixel((5, 60))[0], img.getpixel((5, 60))[2])    # (red from the left while on screen)
        self.assertIsNone(photos.compose('nowhere', 300, 120))
        root = tk_root()
        self.addCleanup(root.destroy)
        a = photos.card(root, 'wales', 200, 100)
        self.assertIs(photos.card(root, 'wales', 200, 100), a)              # (made once for each size)
        self.assertEqual((a.width(), a.height()), (200, 100))


@unittest.skipIf(photos.Image is None, 'Pillow (with ImageTk) not installed')
class Banners(unittest.TestCase):
    """A league's or a cup's banner, from the website: fetched once, its key good for the cards once here."""

    def png(self, w=300, h=100):
        b = io.BytesIO()
        photos.Image.new('RGB', (w, h), (10, 120, 200)).save(b, 'PNG')
        return b.getvalue()

    def setUp(self):
        p = mock.patch('acr_daily.photos.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target))
        p.start()
        self.addCleanup(p.stop)

    def test_fetched_once_then_a_card_and_a_thumbnail(self):
        url = 'https://x.example/l/abcd1234/banner?v=%d' % id(self)
        then = mock.Mock()
        with mock.patch('acr_daily.photos.urllib.request.urlopen', return_value=io.BytesIO(self.png())) as get:
            with mock.patch('acr_daily.photos._busy', {'url:' + url}):
                self.assertIsNone(photos.fetch(url, then))          # (on its way: not asked for twice)
            get.assert_not_called()
            key = photos.fetch(url, then)                           # (here at once: the thread stood in for)
        self.assertEqual(get.call_args.args[0].full_url, url)
        then.assert_called_once_with()
        self.assertEqual((key, photos.fetch(url)), (None, 'url:' + url))
        from acr_daily.app import App
        a = App.__new__(App)
        a.api = mock.Mock(configured=True, base='https://x.example')
        self.assertEqual(a._event_photo({'rally': 'Wales', 'leagueBanner': url[len('https://x.example'):]}), {'banner': 'url:' + url})
        self.assertTrue(photos.has('url:' + url))
        self.assertEqual(photos.compose('url:' + url, 200, 90).size, (200, 90))
        root = tk_root()
        self.addCleanup(root.destroy)
        self.assertEqual((photos.thumb(root, 'url:' + url, 132, 44).width(), photos.thumb(root, 'url:' + url, 132, 44).height()), (132, 44))

    def test_none_to_be_had_the_rallys_photo_stays(self):
        url = 'https://x.example/l/gone0000/banner?v=%d' % id(self)
        with mock.patch('acr_daily.photos.urllib.request.urlopen', side_effect=OSError('404')) as get:
            self.assertIsNone(photos.fetch(url))
            self.assertIsNone(photos.fetch(url))                    # (not asked for again)
        get.assert_called_once()
        self.assertFalse(photos.has('url:' + url))
        from acr_daily.app import App
        a = App.__new__(App)
        a.api = mock.Mock(configured=True, base='https://x.example')
        self.assertEqual(a._event_photo({'rally': 'Wales', 'leagueBanner': '/l/gone0000/banner?v=%d' % id(self)}), {'photo': 'wales'})
        self.assertEqual(a._event_photo({'rally': 'Wales'}), {'photo': 'wales'})


class Icons(unittest.TestCase):
    NAMES = ('home', 'inbox', 'shop', 'settings', 'help', 'quit', 'discord', 'user')

    def test_each_icon_drawn_at_each_size(self):
        for name in self.NAMES:
            for px in icons.SIZES:
                self.assertTrue(os.path.isfile(os.path.join(icons.DIR, '%s-%d.png' % (name, px))), (name, px))
        self.assertEqual((icons.drawn_size(18), icons.drawn_size(20), icons.drawn_size(500)), (18, 27, 96))

    def test_a_tk_image_in_the_colour_asked(self):
        root = tk_root()
        self.addCleanup(root.destroy)
        img = icons.get(root, 'settings', 18)                    # (white: without Pillow too)
        self.assertIsNotNone(img)
        self.assertIs(icons.get(root, 'settings', 18), img)
        if icons.Image is not None:
            self.assertIsNotNone(icons.get(root, 'settings', 18, '#E30613'))


class Figures(unittest.TestCase):
    def ev(self, status, opens=0, closes=0, stages=4):
        return {'status': status, 'opens': opens, 'closes': closes, 'stages': [{}] * stages}

    def test_time_left_and_stages(self):
        f = leagueui.event_figures
        self.assertEqual(f(self.ev('open', closes=3 * DAY + HOUR), 0), [('3', 'DAYS LEFT'), ('4', 'STAGES')])
        self.assertEqual(f(self.ev('open', closes=DAY + 5), 0)[0], ('1', 'DAY LEFT'))
        self.assertEqual(f(self.ev('open', closes=5 * HOUR + 7), 0)[0], ('5', 'HOURS LEFT'))
        self.assertEqual(f(self.ev('open', closes=20 * 60000), 0)[0], ('<1', 'HOUR LEFT'))
        self.assertEqual(f(self.ev('upcoming', opens=2 * DAY + 9), 0)[0], ('2', 'DAYS TO GO'))
        self.assertEqual(f(self.ev('closed', closes=DAY, stages=1), 0), [('1', 'STAGE')])   # (nothing left to count)


if __name__ == '__main__':
    unittest.main()
