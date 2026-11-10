"""The app's driver page (profileui.py): the profile, the achievements, the shop and the driver's own settings, as on
the website. On a Tk window that is never shown."""
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import profileui  # noqa: E402
from test_inbox import ME, click, find, texts  # noqa: E402
from test_tabs import Harness  # noqa: E402

ACH = [{'id': 'first-finish', 'name': 'First finish', 'desc': 'Finish a daily.', 'tier': 'bronze', 'glyph': 'flag', 'label': None,
        'at': 1791504000000, 'rarity': 61.5},
       {'id': 'serial-winner', 'name': 'Serial winner', 'desc': 'Win 10 dailies.', 'tier': 'platinum', 'glyph': 'crown', 'label': '10',
        'at': None, 'rarity': 0.8}]


def page():
    """GET /api/drivers/<me>?full=1, as the server answers it (src/drivers.js driverPage)."""
    return {'steamId': ME, 'name': 'MaybeIWill', 'avatar': None, 'country': 'fi', 'since': 1791504000000,
            'look': {'color': '#5BA8FF', 'badge': '*'}, 'team': {'id': 'team0001', 'name': 'Gravel Foxes', 'tag': 'GFX', 'color': '#7BE07B'},
            'rating': {'rating': 1512, 'rank': 3, 'of': 40, 'races': 9, 'peak': 1530}, 'ratingOn': True,
            'history': [{'rating': 1500 + i, 'delta': 1, 'at': i} for i in range(5)],
            'achievements': ACH,
            'stats': {'dailies': 12, 'finishes': 11, 'wins': 2, 'podiums': 5, 'best': 1, 'runs': 30, 'km': 412.5,
                      'cars': [{'car': 'Hyundai i20 N Rally2', 'runs': 9}], 'rally': 'Wales', 'oneVone': {'won': 3, 'lost': 1, 'drawn': 0}},
            'recent': [{'date': '2026-11-08', 'slot': 1, 'place': 3, 'field': 40, 'status': 'finished', 'stage': 'Peïra Cava', 'delta': 12.4},
                       {'date': '2026-11-07', 'slot': 2, 'place': None, 'field': 30, 'status': 'dnf', 'stage': 'Obersteigen', 'delta': -8}],
            'leagues': [{'id': 'pub00001', 'name': 'Sunday Gravel Club'}], 'cups': [],
            'me': {'customName': 'MaybeIWill', 'steamName': 'maybe', 'ownAvatar': False, 'nextNameChange': None}}


def shop():
    return {'enabled': True, 'signedIn': True, 'balance': 300, 'worn': {'color': 'color:sky', 'badge': None, 'frame': None},
            'items': [{'id': 'color:sky', 'kind': 'color', 'name': 'Sky', 'price': 250, 'color': '#5BA8FF', 'owned': True},
                      {'id': 'color:mint', 'kind': 'color', 'name': 'Mint', 'price': 250, 'color': '#4CD6C0', 'owned': True},
                      {'id': 'color:gold', 'kind': 'color', 'name': 'Gold', 'price': 400, 'color': '#FFD60A', 'owned': False},
                      {'id': 'frame:neon', 'kind': 'frame', 'name': 'Neon', 'price': 200, 'ring': '#3DD5F3', 'width': 3, 'owned': False}],
            'daily': {'price': 5000, 'slot': 1, 'from': '2026-11-10', 'to': '2026-11-12', 'tracks': [{'track': 'Wales Sweet Lamb', 'name': 'Sweet Lamb'}],
                      'cars': [{'name': 'Ford Fiesta Rally2', 'cls': 'Rally2'}], 'weathers': [{'id': 'clear', 'label': 'Clear'}],
                      'times': [{'id': 'morning', 'label': 'Morning (09:00)'}], 'mine': []}}


class Words(unittest.TestCase):
    def test_the_career_numbers_and_a_result(self):
        self.assertEqual(profileui.career(page()['stats'])[:5], [('DAILIES', '12'), ('FINISHES', '11'), ('WINS', '2'), ('PODIUMS', '5'),
                                                                  ('BEST', 'P1')])
        self.assertIn(('KM DRIVEN', '412.5'), profileui.career(page()['stats']))
        self.assertIn(('1V1', '3 – 1 – 0'), profileui.career(page()['stats']))
        self.assertEqual(profileui.result_line(page()['recent'][0]), ('Sun 08 Nov', 'SS1 · Peïra Cava', 'P3 / 40', '+12'))
        self.assertEqual(profileui.result_line(page()['recent'][1])[2:], ('DNF', '-8'))

    def test_an_achievements_line(self):
        self.assertTrue(profileui.unlocked_text(ACH[0]).startswith('Unlocked '))
        self.assertTrue(profileui.unlocked_text(ACH[0]).endswith(' · 61.5 %'))
        self.assertEqual(profileui.unlocked_text(ACH[1]), 'Locked · 0.8 %')

    def test_a_picture_cut_square_and_small_enough(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (900, 600), '#E30613').save(buf, 'PNG')
        data, kind = profileui.square_picture(buf.getvalue())
        img = Image.open(io.BytesIO(data))
        self.assertEqual((img.size, kind), ((256, 256), 'image/jpeg'))
        self.assertLess(len(data), 60000)                    # (the server takes 60 KB at most)


class DriverPage(Harness):
    def setUp(self):
        super().setUp()
        for p in (mock.patch('acr_daily.profileui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)),):
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch('acr_daily.profileui.messagebox.askyesno', return_value=True)
        self.ask = p.start()
        self.addCleanup(p.stop)
        a = self.a
        a.api.driver_page.return_value = page()
        a.api.shop.return_value = shop()
        a.api.countries.return_value = [['fi', 'Finland'], ['gb', 'United Kingdom']]
        a.refresh_driver, a.refresh_credits = mock.Mock(), mock.Mock()
        a.coin_img = None
        a._build_profile_box()

    def test_it_takes_the_views_place_and_a_tab_closes_it(self):
        a = self.a
        a.open_profile()
        a.api.driver_page.assert_called_once_with(ME)
        self.assertEqual([w.winfo_manager() for w in (a.daily_box, a.board_l, a.tree, a.profile_box)], ['', '', '', 'pack'])
        self.assertEqual(self.underlined(), {})              # (no tab: the driver page)
        said = texts(a.profile_box)
        for x in ('* MaybeIWill', 'GRAVEL FOXES', '1512', 'WORLD #3 OF 40', 'D A I L I E S', '12', 'P1', 'Wales', '3 – 1 – 0',
                  'SS1 · Peïra Cava', 'P3 / 40', '+12', 'DNF', 'League · Sunday Gravel Club  ›'):
            self.assertIn(x, said)
        a.show_tab('daily')
        self.assertEqual([w.winfo_manager() for w in (a.daily_box, a.board_l, a.tree, a.profile_box)], ['pack', 'pack', 'pack', ''])

    def test_the_achievements(self):
        a = self.a
        a.open_profile('achievements')
        said = texts(a.profile_box)
        for x in ('1', ' / 2 UNLOCKED', 'First finish', 'Finish a daily.', 'Serial winner', 'Win 10 dailies.', 'Locked · 0.8 %'):
            self.assertIn(x, said)

    def test_the_shop_buy_wear_take_off(self):
        a = self.a
        a.open_profile('shop')
        a.api.shop.assert_called_once()
        said = texts(a.profile_box)
        for x in ('BALANCE', 'Sky', 'WORN  ✓', 'Mint', 'WEAR', 'Gold', '400 ', 'Neon', '200 ', 'LOOKS', 'A DAILY OF YOUR OWN'):
            self.assertIn(x, said)
        click(find(a.profile_box, '200 '))                   # Neon: bought (asked first)
        self.assertIn('Buy Neon for 200 credits?', self.ask.call_args.args[1])
        a.api.shop_buy.assert_called_once_with('frame:neon')
        a.refresh_credits.assert_called()
        click(find(a.profile_box, 'WEAR'))
        a.api.shop_wear.assert_called_with('color', 'color:mint')
        click(find(a.profile_box, 'WORN  ✓'))                # a click on what is worn takes it off
        a.api.shop_wear.assert_called_with('color', None)
        with mock.patch('acr_daily.profileui.messagebox.showinfo') as info:
            click(find(a.profile_box, '400 '))               # Gold: 400, I have 300
        a.api.shop_buy.assert_called_once()
        self.assertIn('you have 300', info.call_args.args[1])
        click(find(a.profile_box, 'A DAILY OF YOUR OWN'))    # a daily of my own: its own part of the shop
        click(find(a.profile_box, 'SET IT  ·  5000 '))
        a.api.shop_daily.assert_called_once_with({'date': '2026-11-10', 'track': 'Wales Sweet Lamb', 'car': 'Ford Fiesta Rally2',
                                                  'weather': 'clear', 'time': 'morning'})

    def test_customize_name_flag_picture(self):
        a = self.a
        a.open_profile('customize')
        a.api.countries.assert_called_once()
        said = texts(a.profile_box)
        for x in ('N A M E', 'F L A G', 'P I C T U R E', 'Y O U R   L O O K', 'CHOOSE A PICTURE…', 'Gravel Foxes  ›'):
            self.assertIn(x, said)
        a._name_var.set('Maybe I Will')
        click(find(a.profile_box, 'SAVE'))
        a.api.set_name.assert_called_once_with('Maybe I Will')
        a._set_country('United Kingdom')
        a.api.set_country.assert_called_with('gb')
        a._set_country('No flag')
        a.api.set_country.assert_called_with(None)
        with mock.patch('acr_daily.profileui.filedialog.askopenfilename', return_value=''):
            click(find(a.profile_box, 'CHOOSE A PICTURE…'))  # (nothing chosen: nothing sent)
        a.api.set_avatar.assert_not_called()

    def test_signed_out(self):
        a = self.a
        a.s['token'] = ''
        a.open_profile()
        a.api.driver_page.assert_not_called()
        self.assertTrue(any('Sign in with Steam' in t for t in texts(a.profile_box)))


if __name__ == '__main__':
    unittest.main()
