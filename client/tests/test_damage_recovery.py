"""A stage the game lost after its finish line (it crashed or hung on the loading after the results; the stage counted
from its finish-line time): the event goes on from the NEXT stage, with the car as it finished that one (the user, 24 Nov
2026). The damage read at the finish (ingamedrive.read_damage), the rally set up from a later stage of its leg
(leagues.calendar start / find_tail / recover), and START STAGE pressed when no service comes before it
(ingameapp._damage_go)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from acr_daily import ingameapp, ingamedrive, leagues, rallyweekend  # noqa: E402


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
        self.assertTrue(cal[0]['service'])                 # (its own service park first: the car is set there)
        self.assertEqual(cal[0]['day'], 0)
        self.assertEqual(leagues.find_tail(as_save(cal), ev)[1:], (0, 2))
        self.assertIsNone(leagues.find_leg(as_save(cal), ev))
        self.assertTrue(leagues.same_calendar(as_save(cal), ev))

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
            self.assertEqual(rec, {'start': 2, 'leg': 0, 'damage': {'Engine': 40.0, 'Radiator': 25.0}, 'go': True})
            self.assertEqual(leagues.recover(ev, 'none', None)['start'], 2)         # (the game's rally gone)
            self.assertIsNone(leagues.recover(ev, 'this', {'done': 2}))            # (the game is where the entry is)
            self.assertIsNone(leagues.recover(ev, 'other', {'done': 0}))
            ev2 = event(self.entry(), services=(True, False, True, True))
            self.assertFalse(leagues.recover(ev2, 'this', {'done': 1})['go'])     # (a service before it: no START at once)

    def test_only_with_the_damage_of_that_finish(self):
        with mock.patch.object(leagues, 'is_parked', return_value=False):
            self.assertIsNone(leagues.recover(event(self.entry(no=0)), 'this', {'done': 1}))   # (an older stage's)
            e = self.entry()
            e.pop('damage')
            self.assertIsNone(leagues.recover(event(e), 'this', {'done': 1}))                  # (an older app: none)
            self.assertIsNone(leagues.recover(event(self.entry(status='dnf')), 'this', {'done': 1}))
            self.assertIsNone(leagues.recover(event(self.entry(done=0, no=-1)), 'none', None))


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


class StartStage(unittest.TestCase):
    def test_pressed_when_no_service_comes_before_it(self):
        ig = ingameapp.InGameApp.__new__(ingameapp.InGameApp)
        later = []
        ig.app = mock.Mock()
        ig.app.root.after.side_effect = lambda ms, fn: later.append(fn)
        ig.note = mock.Mock()
        from acr_daily import ingamenav
        with mock.patch.object(ingamenav, 'game_in_front', return_value=True), \
                mock.patch.object(ingamenav, 'press_key') as press:
            ig._damage_go('5 damage 5 0 park go')
            ig._damage_go('6 damage 5 0 park stay')
            ig._damage_go('7 ok')
            self.assertEqual(len(later), 1)
            later[0]()
            press.assert_called_once_with(0x0D)
        with mock.patch.object(ingamenav, 'game_in_front', return_value=False), \
                mock.patch.object(ingamenav, 'press_key') as press:
            later[0]()
            press.assert_not_called()
            ig.note.assert_called_once()                    # (the game not in front: asked to press it)


if __name__ == '__main__':
    unittest.main()
