"""Driver colours (same picks as the website), the game process lookup, the overlays' "only on the daily" rule, and how
often the app asks the server."""
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
    """App._overlays_allowed on a stand-in app (no windows)."""

    def app(self, only=True, locked=True):
        from acr_daily.app import App
        from acr_daily.judge import Judge
        a = App.__new__(App)
        a.s = {'overlay': {'onlyOnDaily': only, 'locked': locked}}
        a.recorder = None
        ch = {'id': 'd/1', 'slot': 1, 'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2', 'route': [[0, 0], [100, 0]]}
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

    def test_shown_on_the_daily_whatever_the_air(self):
        a = self.app()
        for air in (286.2, 292.7):     # the game draws the temperature anew each time: no sign of other conditions
            self.assertTrue(a._overlays_allowed(self.frame(air=air)))

    def test_always_shown_when_the_option_is_off_or_while_moving_them(self):
        self.assertTrue(self.app(only=False)._overlays_allowed(None))
        self.assertTrue(self.app(locked=False)._overlays_allowed(None))


class ServerLoad(unittest.TestCase):
    """How often the app asks the server: other drivers' positions (_live_every_s) and the once-a-minute round
    (periodic)."""

    def app(self, shown=('map',)):
        from acr_daily.app import App
        from acr_daily.judge import Judge
        a = App.__new__(App)
        a._ov_allowed = True
        a.s = {'token': 't' * 64, 'steamId': '7'}
        a.widgets = {k: mock.Mock(cfg={'visible': k in shown}) for k in ('strip', 'map', 'delta', 'field')}
        ch = {'id': 'd/1', 'slot': 1, 'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2', 'route': [[0, 0], [100, 0]]}
        a.active = 1
        a.dailies = {1: {'ch': ch, 'judge': Judge(ch)}}
        return a

    def hour_of_periodic(self, a):
        """periodic() once a minute for an hour (the clock moved along)."""
        a.root, a.api, a.update_info, a.check_update = mock.Mock(), mock.Mock(), {'version': 'x'}, mock.Mock()
        for name in ('refresh_challenge', 'refresh_routes', 'refresh_week', 'refresh_board'):
            setattr(a, name, mock.Mock())
        clock = iter(range(1000, 1000 + 60 * 60, 60))
        with mock.patch('acr_daily.app.time.monotonic', side_effect=lambda: next(clock)):
            for _ in range(60):
                a.periodic()

    def test_positions_often_on_the_stage_rarely_elsewhere_never_unseen(self):
        from acr_daily.app import TIMING
        a = self.app()
        self.assertEqual(a._live_every_s(), TIMING['liveIdleS'])          # the game is somewhere else
        for state in ('armed', 'finished', 'dnf'):
            a.dailies[1]['judge'].state = state
            self.assertEqual(a._live_every_s(), TIMING['livePollS'], state)
        a.dailies[1]['judge'].state = 'running'
        self.assertIsNone(a._live_every_s())        # driving: they come back with our own position
        a.s['token'] = ''
        self.assertEqual(a._live_every_s(), TIMING['livePollS'])           # ...unless we send none (signed out)
        a._ov_allowed = False                                              # displays hidden ('only on the daily')
        self.assertIsNone(a._live_every_s())
        self.assertIsNone(self.app(shown=('delta',))._live_every_s())       # no display that shows other drivers
        self.assertIsNone(self.app(shown=())._live_every_s())

    def test_the_server_sets_the_pace(self):
        a = self.app()
        a.dailies[1]['ch']['timing'] = {'livePollS': 8, 'liveIdleS': 30, 'liveSendS': 6}
        self.assertEqual(a._live_every_s(), 30)
        self.assertEqual(a.timing('liveSendS'), 6)
        a.dailies[1]['ch']['timing'] = {'liveSendS': 0, 'livePollS': 'x'}      # nonsense: our own values
        from acr_daily.app import TIMING
        self.assertEqual(a.timing('liveSendS'), TIMING['liveSendS'])
        self.assertEqual(a.timing('livePollS'), TIMING['livePollS'])

    def test_our_position_brings_the_others_back(self):
        from acr_daily.telemetry import Frame
        a = self.app()
        a.country, a.live_at = 'Poland', 0.0
        a.api = mock.Mock(configured=True)
        a.api.live.return_value = {'ok': True, 'drivers': [{'steamId': '7', 'name': 'me'}, {'steamId': '9', 'name': 'osiek'}]}
        j = a.dailies[1]['judge']
        with mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            a._send_live(1, j, Frame(0.0, 1, 1000, 1.0, 2.0, 80.0, 'Hyundai i20 N Rally2', 'Alsace Forêt'), 'live')
        self.assertTrue(a.api.live.call_args.args[0]['others'])
        self.assertEqual([x['name'] for x in a.dailies[1]['live']], ['osiek'])       # not us
        a.widgets['map'].cfg['visible'] = False                                    # nothing shows them: not asked
        with mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            a._send_live(1, j, Frame(0.0, 1, 2000, 1.0, 2.0, 80.0, 'Hyundai i20 N Rally2', 'Alsace Forêt'), 'live')
        self.assertFalse(a.api.live.call_args.args[0]['others'])

    def test_boards_every_2_minutes_with_the_game_5_without_the_rest_less_often(self):
        import time
        from acr_daily.app import CHALLENGE_EVERY_MIN, ROUTES_EVERY_MIN, TIMING, WEEK_EVERY_MIN
        a = self.app()
        a.dailies[1]['ch']['endsAt'] = (time.time() + 86400) * 1000
        a.last_frame = object()                                             # the game is running
        self.hour_of_periodic(a)
        self.assertEqual(a.refresh_board.call_count, 3600 // TIMING['boardS'])
        self.assertEqual(a.refresh_challenge.call_count, 60 // CHALLENGE_EVERY_MIN)
        self.assertEqual(a.refresh_week.call_count, 60 // WEEK_EVERY_MIN)
        self.assertEqual(a.refresh_routes.call_count, 60 // ROUTES_EVERY_MIN)
        b = self.app()
        b.dailies[1]['ch']['endsAt'] = (time.time() + 86400) * 1000
        b.last_frame = None                                                 # no game
        self.hour_of_periodic(b)
        self.assertEqual(b.refresh_board.call_count, 3600 // TIMING['boardIdleS'])

    def test_new_dailies_right_after_midnight_and_until_there_are_any(self):
        import time
        a = self.app()
        a.root, a.api, a.update_info = mock.Mock(), mock.Mock(), {'version': 'x'}
        for name in ('refresh_challenge', 'refresh_routes', 'refresh_week', 'refresh_board'):
            setattr(a, name, mock.Mock())
        a.dailies[1]['ch']['endsAt'] = (time.time() - 5) * 1000       # the day's dailies have just closed
        a.periodic()
        a.refresh_challenge.assert_called_once()
        a.dailies = {}                                                 # none yet (server not reachable at start)
        a.periodic()
        self.assertEqual(a.refresh_challenge.call_count, 2)


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

    def app(self, practice=False, driven_other=False, offer_setting=True):
        from acr_daily.app import App
        from acr_daily.judge import Judge
        a = App.__new__(App)
        a.s = {'overlay': {'offerNext': offer_setting}, 'steamId': '7'}   # an old settings file may still say False
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

    def test_not_after_practice_nor_when_driven(self):
        self.assertIsNone(self.app(practice=True)._next_to_offer(1))
        self.assertIsNone(self.app(driven_other=True)._next_to_offer(1))

    def test_always_on_even_with_an_old_off_setting(self):
        self.assertEqual(self.app(offer_setting=False)._next_to_offer(1), 2)

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
            card.left = 0.05
            card._tick()
            self.assertFalse(card.alive)               # closes by itself when the bar is full
            card = nextcard.NextCard(root, (10, 10), 't', 'n', 's', 'DRIVE', lambda: None)
            card.hover, card.left = True, 0.05
            card._tick()
            self.assertTrue(card.alive)                # not while the mouse is on it
            card.close()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
