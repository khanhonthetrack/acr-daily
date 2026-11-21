"""DRIVE in the running game (ingamedrive.py): the set-up sent to the mod, its answers, and the stage as the game runs
it (the mod's ingame-setup.txt) checked against it at the finish."""
import os
import tempfile
import unittest
from unittest import mock

from acr_daily import ingamedrive as d
from acr_daily.app import App


DAILY = {'stageId': 'GreeceS3ElatiaCut2Forward', 'weatherGame': 'WT_LIGHT_CLOUDS', 'startSeconds': 57600,
         'carId': 'Peugeot306IIMaxiKitCar'}


class SetUp(unittest.TestCase):
    def test_a_daily(self):
        s = d.setup_of(d.daily_stages(DAILY), DAILY['carId'], None)
        self.assertEqual(s['preset'], 'GreeceWeekendShort')
        self.assertEqual(s['car'], 'Peugeot306IIMaxiKitCar')
        self.assertEqual(s['stages'], [{'track': 'GreeceS3ElatiaCut2Forward', 'day': 0, 'service': True, 'weather': 1,
                                        'start': 57600.0, 'wet': 0.0}])
        self.assertEqual(s['rules'], {'respawn': 1, 'damage': 1, 'collisions': 1, 'wear': 1, 'failures': 0, 'penalty': 1,
                                      'hardcore': 0})
        self.assertEqual((s['opponents'], s['order_type'], s['order']), (1, 1, 1))

    def test_a_car_id_the_game_wouldnt_take(self):
        from acr_daily import saveslot
        with self.assertRaises(saveslot.SaveError):
            d.setup_of(d.daily_stages(DAILY), 'Lancia Delta S4', None)


class Answers(unittest.TestCase):
    def test_ok_error_and_none(self):
        got = []
        ds = d.Drives()
        ds.send(5, lambda: got.append('ok'), lambda w: got.append('fail ' + w), now=0)
        ds.answer('5 step calendar', now=1)
        ds.answer('5 ok', now=2)
        ds.send(6, lambda: got.append('ok'), lambda w: got.append('fail ' + w), now=0)
        ds.answer('6 error not in the game\'s main menu', now=3)
        ds.send(7, lambda: None, lambda w: got.append('fail ' + w), now=0)
        ds.check(now=10)
        self.assertEqual(got, ['ok', "fail not in the game's main menu"])
        ds.check(now=40)
        self.assertEqual(got[-1], 'fail no answer')
        self.assertFalse(ds.busy())


class Why(unittest.TestCase):
    def test_continue_with_no_rally_in_the_game(self):
        self.assertEqual(d.why_words('no rally in progress in the game'), 'the game has no Rally Weekend in progress')


class LiveSetUp(unittest.TestCase):
    def file(self, text):
        p = os.path.join(tempfile.mkdtemp(), 'ingame-setup.txt')
        with open(p, 'w') as f:
            f.write(text)
        return p

    def test_read(self):
        live = d.live_setup(self.file('ACRSETUP 3 GreeceS3ElatiaCut2Forward 1 57600 0 0 4 0 0 0\nend 3\n   '))
        self.assertEqual(live, {'track': 'GreeceS3ElatiaCut2Forward', 'weather': 1, 'start': 57600, 'speed': 0,
                                'wet': 0.0, 'grip': 4, 'random': False, 'dynamic': False, 'index': 0, 'ours': None})

    def test_ours(self):
        line = 'ACRSETUP 3 GreeceS3ElatiaCut2Forward 1 57600 0 0 4 0 0 0 %s\nend 3\n'
        self.assertIs(d.live_setup(self.file(line % '1'))['ours'], True)
        self.assertIs(d.live_setup(self.file(line % '0'))['ours'], False)
        self.assertIsNone(d.live_setup(self.file(line % '-'))['ours'])

    def test_none_half_written_or_missing(self):
        self.assertIsNone(d.live_setup(self.file('ACRSETUP 4 none\nend 4\n')))
        self.assertIsNone(d.live_setup(self.file('ACRSETUP 5 GreeceS3ElatiaCut2Forward 1 57600 0 0 4 0 0 0\nend 4\n')))
        self.assertIsNone(d.live_setup(os.path.join(tempfile.mkdtemp(), 'none.txt')))

    def test_as_set_up_nothing_changed(self):
        stage = d.setup_of(d.daily_stages(DAILY), DAILY['carId'])['stages'][0]
        live = {'track': 'greeces3elatiacut2forward', 'weather': 1, 'start': 57600, 'speed': 0, 'wet': 0.0, 'grip': 4,
                'random': False, 'dynamic': False, 'index': 0}
        self.assertEqual(d.setup_changed(stage, live), [])
        self.assertEqual(d.setup_changed(stage, dict(live, track='GreeceS3ElatiaCut2Reverse', weather=5, start=28800,
                                                     speed=1, grip=2, random=True)),
                         ['stages', 'weather', 'start times', 'track conditions', 'time speed', 'random weather'])


class Finish(unittest.TestCase):
    """A run set up in the running game: judged at the finish on the stage as the game ran it, not on the save (its
    first write after the stage still holds the set-up before: 20 Nov 2026)."""

    def app(self):
        a = App.__new__(App)
        a.sub_l, a.awaiting = mock.Mock(), []
        a._official_in = mock.Mock()
        a._void_daily = mock.Mock()
        return a

    def test_counted_at_once_whatever_the_save_says(self):
        a = self.app()
        item, o = {'id': 'daily:x', 'kind': 'daily', 'slot': 1, 'ingameChanged': []}, {'time': 100.0}
        a.awaiting = [item]
        with mock.patch('acr_daily.app.leagues.daily_changed', return_value=['stages']) as save_check:
            a._official_found(item, o, b'save')
        a._official_in.assert_called_once_with(item, o)
        save_check.assert_not_called()

    def test_changed_in_the_game_not_counted_at_once(self):
        a = self.app()
        item = {'id': 'daily:x', 'kind': 'daily', 'slot': 1, 'ingameChanged': ['weather']}
        a.awaiting = [item]
        with mock.patch('acr_daily.app.waiting.note'), mock.patch('acr_daily.app.waiting.remove'):
            a._official_found(item, {'time': 100.0}, b'save')
        a._official_in.assert_not_called()
        self.assertEqual(str(a._void_daily.call_args.args[1]), "the daily's weather changed in the game")
        self.assertEqual(a.awaiting, [])


class SetUpHere(unittest.TestCase):
    """Only a stage ACR DAILY took the game to counts: a Rally Weekend set up by hand in the game's menus, even with a
    daily's settings, is no Rally Weekend to the judges (mode_rw False: practice; 21 Nov 2026)."""

    def app(self, ours, mode='weekend', ingame=True):
        a = App.__new__(App)
        a.ingame_app = mock.Mock() if ingame else None
        a.game_mode = lambda: mode
        live = {'ours': ours}
        return a, mock.patch('acr_daily.app.ingamedrive.live_setup', return_value=live)

    def test_taken_there_by_acr_daily(self):
        a, p = self.app(True)
        with p:
            self.assertIs(a.mode_rw(), True)

    def test_set_up_by_hand(self):
        a, p = self.app(False)
        with p:
            self.assertIs(a.set_up_here(), False)
            self.assertIs(a.mode_rw(), False)

    def test_cant_be_told(self):
        for ours, ingame in ((None, True), (False, False)):
            a, p = self.app(ours, ingame=ingame)
            with p:
                self.assertIs(a.mode_rw(), True)
        a, p = self.app(True, mode='practice')
        with p:
            self.assertIs(a.mode_rw(), False)


class OverEventLine(unittest.TestCase):
    """An event just over: its FINISHED line stays while the game is still on its stage, not on FREE PRACTICE of the
    same stage afterwards (21 Nov 2026)."""

    def app(self, menus=False, rw=True):
        a = App.__new__(App)
        ev = {'name': 'Test', 'stages': [{'name': 'A'}, {'name': 'B'}], 'entry': {'status': 'finished', 'totalMs': 1000}}
        judge = mock.Mock()
        judge._right.return_value = True
        a.league_run = {'ev': ev, 'no': 1, 'judge': judge, 'over': True}
        a.drive_target = 'daily'
        pulse = mock.Mock()
        pulse.in_menus.return_value = menus
        a._pulse = lambda: pulse
        a.mode_rw = lambda: rw
        return a, pulse

    def test_on_its_stage(self):
        a, _p = self.app()
        self.assertEqual(a._league_overlay_state(mock.Mock(track='t'))[2][0], 'finished')

    def test_free_practice_after(self):
        a, _p = self.app(rw=False)
        self.assertIsNone(a._league_overlay_state(mock.Mock(track='t')))

    def test_menus_then_the_same_stage_again(self):
        a, pulse = self.app(menus=True)
        self.assertIsNone(a._league_overlay_state(mock.Mock(track='t')))
        pulse.in_menus.return_value = False
        a.mode_rw = lambda: None                      # (mode not told)
        self.assertIsNone(a._league_overlay_state(mock.Mock(track='t')))


class BackInMenus(unittest.TestCase):
    """A finished run's time not saved and the game back in its menus BACK_IN_MENUS_S: lost now, not 30 min later
    (21 Nov 2026: quit from the results screen; the app said "leave the results screen" for half an hour)."""

    def test_menus_long_enough(self):
        from acr_daily import app as app_mod
        a = App.__new__(App)
        pulse = mock.Mock()
        a._pulse = lambda: pulse
        item = {}
        pulse.in_menus.return_value = False
        self.assertFalse(a.back_in_menus(item))
        pulse.in_menus.return_value = True
        with mock.patch('acr_daily.app.time.monotonic', return_value=1000.0):
            self.assertFalse(a.back_in_menus(item))                    # (just back: the save may still come)
        with mock.patch('acr_daily.app.time.monotonic', return_value=1000.0 + app_mod.BACK_IN_MENUS_S):
            self.assertTrue(a.back_in_menus(item))
        pulse.in_menus.return_value = False                           # (on a stage again: starts over)
        self.assertFalse(a.back_in_menus(item))
        self.assertNotIn('menusSince', item)


if __name__ == '__main__':
    unittest.main()
