"""The car as it crossed the finish line goes on to the next stage (the user, 24 Nov 2026), whatever happened past the
line. NEXT STAGE in the game: the game mod's own work (drive.lua). After the game lost a finished stage (it crashed or
hung on the loading after the results; the stage counted from its finish-line time) the event goes on from the NEXT
stage: the damage read at the finish (ingamedrive.read_damage), the rally set up from a later stage of its leg with no
extra service park (leagues.calendar start / find_tail / recover, rallyweekend.check_itinerary tail)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from acr_daily import ingamedrive, leagues, rallyweekend  # noqa: E402


def event(entry=None, services=(True, False, False, True)):
    ids = ('GreeceS1ZeliForward', 'GreeceS1ZeliReverse', 'GreeceS2ElatiaForward', 'GreeceS2ElatiaReverse')
    return {'id': 7, 'name': 'Acropolis', 'rules': {}, 'entry': entry,
            'stages': [{'stageId': s, 'weatherGame': 'WT_CLEAR', 'startSeconds': 36000 + 3600 * k, 'day': 1,
                        'service': services[k]} for k, s in enumerate(ids)]}


def as_save(cal):
    """A calendar as the game's save gives it back (rallyweekend.read_weekend's stages)."""
    return [{'stage': c['stage'], 'day': c['day'], 'weather': rallyweekend.WEATHERS.index(c['weather']), 'start': c['start']}
            for c in cal]


class Tail(unittest.TestCase):
    def test_a_leg_from_a_later_stage_is_told_back(self):
        ev = event()
        cal = leagues.calendar(ev, 0, start=2)
        self.assertEqual([c['stage'] for c in cal], ['GreeceS2ElatiaForward', 'GreeceS2ElatiaReverse'])
        self.assertFalse(cal[0]['service'])                # (none the event hasn't: no repairs the others didn't get)
        self.assertEqual(cal[0]['day'], 0)
        self.assertEqual(leagues.find_tail(as_save(cal), ev)[1:], (0, 2))
        self.assertIsNone(leagues.find_leg(as_save(cal), ev))
        self.assertTrue(leagues.same_calendar(as_save(cal), ev))
        with self.assertRaises(rallyweekend.SaveError):
            rallyweekend.check_itinerary(cal)               # (a whole leg must open with one)
        rallyweekend.check_itinerary(cal, tail=True)
        self.assertTrue(leagues.calendar(ev, 0)[0]['service'])                        # (the leg itself: its own)
        self.assertTrue(leagues.calendar(event(services=(True, False, True, True)), 0, start=2)[0]['service'])

    def test_a_daily_on_the_same_stage_is_not_one(self):
        ev = event()
        one = as_save(leagues.calendar(ev, 0, start=3))
        self.assertEqual(leagues.find_tail(one, ev)[1:], (0, 3))
        one[0]['start'] += 4 * 3600                         # (another start time: a daily, not this event)
        self.assertIsNone(leagues.find_tail(one, ev))


class Recover(unittest.TestCase):
    def entry(self, done=2, no=1, status='running'):
        return {'status': status, 'done': done, 'damage': {'no': no, 'parts': {'Engine': 40.0, 'Radiator': 25.0}}}

    def test_on_from_the_next_stage_with_the_car_as_it_finished(self):
        ev = event(self.entry())
        with mock.patch.object(leagues, 'is_parked', return_value=False):
            rec = leagues.recover(ev, 'this', {'done': 1})            # (the game's rally: SS1 only, the entry has 2)
            self.assertEqual(rec, {'start': 2, 'leg': 0, 'damage': {'Engine': 40.0, 'Radiator': 25.0}})
            self.assertEqual(leagues.recover(ev, 'none', None)['start'], 2)         # (the game's rally gone)
            self.assertIsNone(leagues.recover(ev, 'this', {'done': 2}))            # (the game is where the entry is)
            self.assertIsNone(leagues.recover(ev, 'other', {'done': 0}))

    def test_only_with_the_damage_of_that_finish(self):
        with mock.patch.object(leagues, 'is_parked', return_value=False):
            self.assertIsNone(leagues.recover(event(self.entry(no=0)), 'this', {'done': 1}))   # (an older stage's)
            e = self.entry()
            e.pop('damage')
            self.assertIsNone(leagues.recover(event(e), 'this', {'done': 1}))                  # (an older app: none)
            self.assertIsNone(leagues.recover(event(self.entry(status='dnf')), 'this', {'done': 1}))
            self.assertIsNone(leagues.recover(event(self.entry(done=0, no=-1)), 'none', None))


class WholeCar(unittest.TestCase):
    """The whole car at the line (the mod's ingame-finishcar.json: body, panels, scratches, lights, wear, tyres) kept
    with the event's stage on this PC and given back when the next stage is set up again (the user, 26 Nov 2026:
    going on from ACR DAILY must look as going on in the game)."""
    WHOLE = {'v': 1, 'at': 1000.0, 'world': 'World /Game/Levels/X.X', 'lights': 'FrontLeft,FrontRight',
             'car': {'CarDamage': {'PartsStates': {'n': 1, 'by': {'Engine': {'LifePoints': 0.4}}}}},
             'tyres': {'ProviderState': {'Tires': {'n': 1, 'by': {'TarmacSoft_0': {'MaxTread': {'n': 1, '1': 0.5}}}}}}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dirs = mock.patch.object(leagues, 'CARS_DIR', self.tmp.name)
        self.dirs.start()

    def tearDown(self):
        self.dirs.stop()
        self.tmp.cleanup()

    def test_kept_with_the_stage_and_given_back(self):
        self.assertIsNone(leagues.kept_car(7, 1))
        self.assertTrue(leagues.keep_car(7, 1, self.WHOLE))
        self.assertEqual(leagues.kept_car(7, 1), self.WHOLE)
        self.assertIsNone(leagues.kept_car(7, 0))                    # (another stage's)
        self.assertFalse(leagues.keep_car(7, 2, {'v': 1}))           # (no car in it)
        ev = event({'status': 'running', 'done': 2, 'damage': {'no': 1, 'parts': {'Engine': 40.0}}})
        with mock.patch.object(leagues, 'is_parked', return_value=False):
            rec = leagues.recover(ev, 'none', None)
        self.assertEqual(rec['whole'], self.WHOLE)
        self.assertEqual(rec['damage'], {'Engine': 40.0})           # (the server's parts as before)

    def test_the_servers_copy_on_another_pc(self):
        z = leagues.pack_car(self.WHOLE)
        self.assertLess(len(z), 600)                                  # (gzip + base64: small)
        self.assertEqual(leagues.unpack_car(z), self.WHOLE)
        self.assertIsNone(leagues.unpack_car('not base64!'))
        self.assertIsNone(leagues.unpack_car(leagues.pack_car({'v': 1})))   # (no car in it)
        e = {'status': 'running', 'done': 2, 'damage': {'no': 1, 'parts': {'Engine': 40.0}},
             'carState': {'no': 1, 'z': z}}
        with mock.patch.object(leagues, 'is_parked', return_value=False):
            self.assertEqual(leagues.recover(event(e), 'none', None)['whole'], self.WHOLE)   # (nothing on this PC)
            e['carState'] = {'no': 0, 'z': z}                         # (another stage's: not used)
            self.assertNotIn('whole', leagues.recover(event(e), 'none', None))

    def test_only_the_newest_are_kept(self):
        with mock.patch.object(leagues, 'CARS_KEPT', 3):
            for no in range(5):
                leagues.keep_car(7, no, self.WHOLE)
                t = 1000 + no
                os.utime(leagues._car_path(7, no), (t, t))
        self.assertEqual(len(os.listdir(self.tmp.name)), 3)

    def test_the_finish_file_read_only_while_fresh(self):
        import json
        p = os.path.join(self.tmp.name, 'ingame-finishcar.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(self.WHOLE, f)
        self.assertEqual(ingamedrive.read_finish_car(p, now=1010), self.WHOLE)
        self.assertIsNone(ingamedrive.read_finish_car(p, now=1000 + ingamedrive.FINISH_CAR_FRESH_S + 1))   # (an old one)
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{"v": 1, "at": 10')                                 # (half written)
        self.assertIsNone(ingamedrive.read_finish_car(p, now=10))


class DamageFile(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'ingame-damage.txt')
            with open(p, 'w', encoding='ascii') as f:
                f.write(text + ' ' * 40 + '\n')
            return ingamedrive.read_damage(p)

    def test_the_parts_below_100(self):
        self.assertEqual(self.read('ACRDMG 12 Engine=40.0 GearBox=35.5 end 12'), {'Engine': 40.0, 'GearBox': 35.5})
        self.assertEqual(self.read('ACRDMG 3  end 3'), {})                       # (an intact car)
        self.assertIsNone(self.read('ACRDMG 4 none end 4'))                       # (no car of yours)
        self.assertIsNone(self.read('ACRDMG 5 Engine=40.0 end 4'))                # (half written)
        self.assertIsNone(self.read('ACRDMG 6 Engine=x end 6'))


if __name__ == '__main__':
    unittest.main()
