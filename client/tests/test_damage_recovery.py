"""The car as it crossed the finish line goes on to the next stage (the user, 24 Nov 2026), whatever happened past the
line: after every finish (ingameapp.next_damage, leagueui._next_stage_damage) and after the game lost a finished stage
(it crashed or hung on the loading after the results; the stage counted from its finish-line time: the event goes on
from the NEXT stage). The damage read at the finish (ingamedrive.read_damage), the rally set up from a later stage of
its leg with no extra service park (leagues.calendar start / find_tail / recover, rallyweekend.check_itinerary tail)."""
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

    def test_the_place_in_the_calendar(self):
        ev = event()
        self.assertEqual(leagues.calendar_index(ev, 2), 2)     # (a whole leg: from its first stage)
        self.assertEqual(leagues.calendar_index(ev, 3, 2), 1)  # (a recovery's tail from SS3: SS4 second)

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


class NextStage(unittest.TestCase):
    def app(self):
        ig = ingameapp.InGameApp.__new__(ingameapp.InGameApp)
        ig.cmd = {'n': 4, 'do': 'focus', 'id': 'x'}
        ig.damage_next = None
        ig.drives = mock.Mock()
        return ig

    def test_kept_in_the_state_until_the_mod_answers(self):
        ig = self.app()
        n = ig.next_damage({'Engine': 40.0}, 1)
        self.assertEqual(ig.damage_next, {'id': n, 'parts': {'Engine': 40.0}, 'index': 1})
        self.assertEqual(ig.cmd['do'], 'focus')            # (no command taken: a click's still goes)
        ig.event('drive', '%d step x' % n)
        ig.event('drive', '%d damage 26 0 line set' % (n + 1))
        self.assertIsNotNone(ig.damage_next)
        ig.event('drive', '%d damage 26 0 line set' % n)
        self.assertIsNone(ig.damage_next)
        self.assertEqual(ig.drives.answer.call_count, 3)

    def test_a_new_id_each_time(self):
        ig = self.app()
        a = ig.next_damage({}, 1)
        with mock.patch.object(ingameapp.time, 'time', return_value=0):
            b = ig.next_damage({'Radiator': 10.0}, 2)
        self.assertGreater(b, a)

    def test_the_next_stage_of_the_same_leg_only(self):
        from acr_daily import leagueui
        cls = next(c for c in vars(leagueui).values() if isinstance(c, type) and hasattr(c, '_next_stage_damage'))
        ev = event()

        def sent(k, run=None, legs=None):
            ui = mock.Mock()
            with mock.patch.object(leagueui.waiting, 'note'), \
                    mock.patch.object(leagues, 'legs', return_value=legs or [(0, 4)]):
                cls._next_stage_damage(ui, run or {}, ev, k, {'Engine': 40.0})
            return ui.ingame_app.next_damage.call_args_list

        self.assertEqual(sent(0), [mock.call({'Engine': 40.0}, 1)])
        self.assertEqual(sent(2, {'ingame': {'first': 2}}), [mock.call({'Engine': 40.0}, 1)])   # (a recovery's tail)
        self.assertEqual(sent(3), [])                                   # (the last stage)
        self.assertEqual(sent(1, legs=[(0, 2), (2, 4)]), [])           # (the next leg: a fresh car)
        self.assertEqual(sent(2, legs=[(0, 2), (2, 4)]), [mock.call({'Engine': 40.0}, 1)])


if __name__ == '__main__':
    unittest.main()
