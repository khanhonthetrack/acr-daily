"""Driver colours (same picks as the website), the game process lookup, and the overlays' "only on the daily" rule."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import saveslot  # noqa: E402
from acr_daily.widgets import PALETTE, colours  # noqa: E402


class Colours(unittest.TestCase):
    def test_everyone_gets_a_different_colour(self):
        ids = ['76561198019002579', '76561198051420773', '76561198000000009', '76561198000000019']
        c = colours(ids)
        self.assertEqual(len(set(c.values())), len(ids))
        self.assertTrue(all(v in PALETTE for v in c.values()))

    def test_same_driver_same_colour_whatever_the_order(self):
        ids = ['76561198019002579', '76561198051420773', '76561198000000009']
        self.assertEqual(colours(ids), colours(list(reversed(ids))))

    def test_matches_the_website_rule(self):
        # site.js: Number(id.slice(-6)) % 10, sorted ids, next free colour on a clash
        self.assertEqual(colours(['76561198000000013'])['76561198000000013'], PALETTE[13 % 10])
        c = colours(['76561198000000003', '76561198000000013'])
        self.assertEqual(c['76561198000000003'], PALETTE[3])
        self.assertEqual(c['76561198000000013'], PALETTE[4])


class GameProcess(unittest.TestCase):
    def test_reads_tasklist_csv(self):
        out = '"acr.exe","4242","Console","1","1,234,567 K"\n'
        with mock.patch('os.popen', return_value=mock.Mock(read=lambda: out)):
            self.assertEqual(saveslot.game_pids(), [4242])
            self.assertTrue(saveslot.game_running())

    def test_not_running(self):
        out = 'INFO: No tasks are running which match the specified criteria.\n'
        with mock.patch('os.popen', return_value=mock.Mock(read=lambda: out)):
            self.assertEqual(saveslot.game_pids(), [])
            self.assertFalse(saveslot.ask_game_to_quit())


class OnlyOnTheDaily(unittest.TestCase):
    """App._overlays_allowed / _check_conditions on a stand-in app (no windows)."""

    def app(self, only=True, locked=True):
        from acr_daily.app import App
        from acr_daily.judge import Judge
        a = App.__new__(App)
        a.s = {'overlay': {'onlyOnDaily': only, 'locked': locked}}
        a.recorder = None
        ch = {'id': 'd/1', 'slot': 1, 'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2', 'route': [[0, 0], [100, 0]],
              'startTempK': 290.0}
        a.dailies = {1: {'ch': ch, 'judge': Judge(ch)}}
        return a

    def frame(self, track='Alsace Forêt', car='Hyundai i20 N Rally2', air=290.5, clock=0, x=0.0):
        from acr_daily.telemetry import Frame
        return Frame(0.0, 1, clock, x, 0.0, 0.0, car, track, air_k=air)

    def test_hidden_off_the_daily(self):
        a = self.app()
        self.assertFalse(a._overlays_allowed(None))
        self.assertFalse(a._overlays_allowed(self.frame(track='Wales Afon Bidno', x=5000.0)))   # another stage, elsewhere
        self.assertFalse(a._overlays_allowed(self.frame(car='Peugeot 208 Rally4')))

    def test_shown_on_the_daily_with_the_right_conditions(self):
        a = self.app()
        f = self.frame()
        a._check_conditions(f)
        self.assertTrue(a.dailies[1]['cond_ok'])
        self.assertTrue(a._overlays_allowed(f))

    def test_hidden_when_the_air_says_other_conditions(self):
        a = self.app()
        f = self.frame(air=296.0)
        a._check_conditions(f)
        self.assertFalse(a.dailies[1]['cond_ok'])
        self.assertFalse(a._overlays_allowed(f))

    def test_no_one_finished_yet_means_shown(self):
        a = self.app()
        a.dailies[1]['ch']['startTempK'] = None
        f = self.frame(air=300.0)
        a._check_conditions(f)
        self.assertIsNone(a.dailies[1]['cond_ok'])
        self.assertTrue(a._overlays_allowed(f))

    def test_always_shown_when_the_option_is_off_or_while_moving_them(self):
        self.assertTrue(self.app(only=False)._overlays_allowed(None))
        self.assertTrue(self.app(locked=False)._overlays_allowed(None))


class Avatars(unittest.TestCase):
    def test_round_image(self):
        from acr_daily import avatars
        if avatars.Image is None:
            self.skipTest('no Pillow')
        img = avatars.Image.new('RGBA', (64, 64), (255, 0, 0, 255))
        r = avatars.round_image(img, 16)
        self.assertEqual(r.size, (16, 16))
        self.assertEqual(r.getpixel((0, 0))[3], 0)        # corners see-through
        self.assertEqual(r.getpixel((8, 8))[3], 255)      # middle solid

    def test_every_display_draws_other_drivers(self):
        """All overlays render with drivers on stage, with and without an avatar (no window shown)."""
        import tkinter as tk
        from acr_daily import avatars, widgets
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()
        try:
            app = mock.Mock()
            app.root = root
            app.s = {'overlay': {'locked': True}, 'widgets': {}}
            if avatars.Image is not None:     # a ready avatar, as if downloaded
                avatars._raw['http://x/a.jpg'] = avatars.Image.new('RGBA', (64, 64), (0, 128, 255, 255))
            drivers = [{'steamId': '1', 'name': 'osiek', 'x': 50.0, 'z': 0.0, 'progress': 0.4, 'state': 'live', 'avatar': 'http://x/a.jpg'},
                       {'steamId': '2', 'name': 'IndyCheck', 'x': 80.0, 'z': 0.0, 'progress': 1.0, 'state': 'finished'}]
            cols = colours(['1', '2'])
            view = {'slot': 1, 'running': True, 'route': [[i * 5.0, 0.0] for i in range(40)], 'splits': [0.25, 0.5, 0.75],
                    'progress': 0.3, 'ghosts': [], 'ghost_pos': [], 'me_pos': (10.0, 0.0), 'gap_p1': 1200, 'p1_name': 'osiek',
                    'field': drivers, 'colours': cols,
                    'others': [(x['name'], cols[x['steamId']], (x['x'], x['z']), x.get('avatar')) for x in drivers],
                    'others_prog': [(x['name'], cols[x['steamId']], x['progress'], x.get('avatar')) for x in drivers]}
            for key, cls in widgets.CLASSES.items():
                w = cls(app, key)
                w.render(view)
                self.assertGreaterEqual(len(w.c.find_all()), 2, key)
                if avatars.Image is not None and key in ('strip', 'map', 'field'):
                    self.assertTrue(any(w.c.type(i) == 'image' for i in w.c.find_all()), key + ' shows the avatar')
        finally:
            root.destroy()


class NextDaily(unittest.TestCase):
    """After a counted run of one daily, the card offering the other one (app._next_to_offer, nextcard.NextCard)."""

    def app(self, offer=True, practice=False, driven_other=False):
        from acr_daily.app import App
        from acr_daily.judge import Judge
        a = App.__new__(App)
        a.s = {'overlay': {'offerNext': offer}, 'steamId': '7'}
        a._offered = set()
        a.dailies = {}
        for slot in (1, 2):
            ch = {'id': '2026-10-06/%d' % slot, 'slot': slot, 'track': 'T%d' % slot, 'car': 'C', 'route': [[0, 0], [100, 0]]}
            a.dailies[slot] = {'ch': ch, 'judge': Judge(ch), 'board': {'entries': []}}
        a.dailies[1]['practice'] = practice
        if driven_other:
            a.dailies[2]['board'] = {'entries': [{'steamId': '7', 'rank': 1}]}
        return a

    def test_offers_the_other_daily_once(self):
        a = self.app()
        self.assertEqual(a._next_to_offer(1), 2)
        self.assertIsNone(a._next_to_offer(1))        # once per daily and day

    def test_not_after_practice_nor_when_driven_nor_when_off(self):
        self.assertIsNone(self.app(practice=True)._next_to_offer(1))
        self.assertIsNone(self.app(driven_other=True)._next_to_offer(1))
        self.assertIsNone(self.app(offer=False)._next_to_offer(1))

    def test_the_card_drives_closes_and_times_out(self):
        import tkinter as tk
        from acr_daily import nextcard
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()
        try:
            driven = []
            card = nextcard.NextCard(root, (10, 10), 'SS1 FINISHED · P3 today', 'Next: SS2 · Cwmbiga - Fedw Fain',
                                     'Hyundai i20 N Rally2 · Light fog', 'DRIVE SS2 ›  restarts the game', lambda: driven.append(2))
            self.assertTrue(card.alive)
            card._drive()
            self.assertEqual(driven, [2])
            self.assertFalse(card.alive)               # clicking DRIVE closes the card
            card = nextcard.NextCard(root, (10, 10), 't', 'n', 's', 'DRIVE', lambda: None)
            card.left = 1
            card._tick()
            self.assertFalse(card.alive)               # closes by itself when the countdown runs out
            card = nextcard.NextCard(root, (10, 10), 't', 'n', 's', 'DRIVE', lambda: None)
            card.hover, card.left = True, 1
            card._tick()
            self.assertTrue(card.alive)                # not while the mouse is on it
            card.close()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
