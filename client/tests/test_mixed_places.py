"""An event with stages from several places (the user, 24 Nov 2026): each run of stages in one place is a Rally Weekend
of its own (leagues.legs), a new place on the same day goes on with the car as it crossed the last finish line and no
service park the event doesn't have (leagues.carried / calendar / starts_mid_day); the tyres picked only where their
surface is (gear.compounds)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from acr_daily import gear, leagues, rallyweekend  # noqa: E402

STAGES = [('AlsaceS4SaverneShort1Forward', 'Alsace Obersteigen', 1, True),
          ('AlsaceS4SaverneShort1Reverse', 'Alsace La Mossig', 1, False),
          ('SwedenS1VargasenCut3Forward', 'Sweden Vargasen South', 1, False),
          ('SwedenS1VargasenCut3Reverse', 'Sweden Vargasen North', 1, False),
          ('GreeceS1ZeliForward', 'Greece Zeli', 2, True)]


def event(stages=STAGES, entry=None):
    return {'id': 9, 'name': 'Tour', 'rally': 'Alsace · Sweden · Greece', 'rules': {}, 'entry': entry,
            'stages': [{'stageId': s, 'track': t, 'weatherGame': 'WT_CLEAR', 'startSeconds': 36000 + 3600 * k, 'day': d,
                        'service': sv} for k, (s, t, d, sv) in enumerate(stages)]}


class Legs(unittest.TestCase):
    def test_a_leg_for_each_place(self):
        ev = event()
        self.assertEqual(leagues.legs(ev), [(0, 2), (2, 4), (4, 5)])
        self.assertEqual([leagues.carried(ev, k) for k in range(5)], [False, False, True, False, False])
        self.assertTrue(leagues.starts_mid_day(ev, 1))
        self.assertFalse(leagues.starts_mid_day(ev, 2))     # (a new day: its own service park, a fresh car)

    def test_one_place_as_before(self):
        ev = event([s for s in STAGES if s[0].startswith('Alsace')])
        self.assertEqual(leagues.legs(ev), [(0, 2)])
        self.assertFalse(any(leagues.carried(ev, k) for k in range(2)))

    def test_the_new_place_has_no_extra_service_park(self):
        ev = event()
        cal = leagues.calendar(ev, 1)
        self.assertEqual([c['stage'] for c in cal], ['SwedenS1VargasenCut3Forward', 'SwedenS1VargasenCut3Reverse'])
        self.assertFalse(cal[0]['service'])
        self.assertEqual(cal[0]['day'], 0)
        with self.assertRaises(rallyweekend.SaveError):
            rallyweekend.check_itinerary(cal)
        self.assertEqual(rallyweekend.check_itinerary(cal, tail=True), 'SwedenWeekendShort')
        self.assertTrue(leagues.calendar(ev, 2)[0]['service'])
        # (the event giving it one: kept)
        st = list(STAGES)
        st[2] = st[2][:3] + (True,)
        self.assertTrue(leagues.calendar(event(st), 1)[0]['service'])

    def test_the_save_tells_the_legs_apart(self):
        ev = event()
        as_save = [{'stage': c['stage'], 'day': c['day']} for c in leagues.calendar(ev, 1)]
        self.assertEqual(leagues.find_leg(as_save, ev), (leagues.DAYS, 1))

    def test_a_lost_finish_before_a_new_place_is_recovered(self):
        ev = event(entry={'status': 'running', 'done': 2, 'damage': {'no': 1, 'parts': {'Engine': 40.0}}})
        from unittest import mock
        with mock.patch.object(leagues, 'is_parked', return_value=False):
            self.assertEqual(leagues.recover(ev, 'none', None), {'start': 2, 'leg': 1, 'damage': {'Engine': 40.0}})
            ev['entry'] = {'status': 'running', 'done': 4, 'damage': {'no': 3, 'parts': {}}}
            self.assertIsNone(leagues.recover(ev, 'none', None))     # (a new day: a fresh car)


class RallyFrom(unittest.TestCase):
    """The words "the game took your rally back to SS1: drive SS1 to SS5 again" (leagueui._again_text) said where a
    rally starts at its leg's first stage (Rally di Sanremo 1986 after a crash past SS5, 26 Nov 2026)."""

    def test_a_leg_starting_where_the_entry_is_says_nothing_to_drive_again(self):
        ev = event()
        for done in (2, 4):                                   # (the entry is at a leg's first stage)
            self.assertEqual(leagues.rally_from(ev, 'setup', None, done), done)
        self.assertEqual(leagues.rally_from(ev, 'next-leg', 2, 2), 2)

    def test_in_the_middle_of_a_leg_the_stages_before_are_driven_again(self):
        ev = event()
        self.assertEqual(leagues.rally_from(ev, 'setup', None, 3), 2)    # (SS3 counted, SS4's leg set up from SS3)
        self.assertEqual(leagues.rally_from(ev, 'setup', None, 1), 0)

    def test_a_start_and_the_other_actions(self):
        ev = event()
        self.assertEqual(leagues.rally_from(ev, 'setup', None, 0), 0)
        self.assertEqual(leagues.rally_from(ev, 'reset', None, 0), 0)
        self.assertEqual(leagues.rally_from(ev, 'resume', 3, 4), 3)      # (the game's own: fewer than the entry has)
        self.assertEqual(leagues.rally_from(ev, 'unpark', None, 4), 4)


class Tyres(unittest.TestCase):
    def test_one_surface_or_the_games_own(self):
        ev = event()
        self.assertEqual(gear.compounds(ev), ())                    # (tarmac, snow and gravel: the game's own)
        self.assertEqual(list(gear.compounds(ev, 0)), list(gear.BY_RALLY['alsace']))
        self.assertEqual(list(gear.compounds(ev, 1)), list(gear.BY_RALLY['sweden']))
        one = event([s for s in STAGES if s[0].startswith('Alsace')])
        self.assertEqual(list(gear.compounds(one)), list(gear.BY_RALLY['alsace']))
        self.assertEqual(list(gear.compounds({'rally': 'Wales', 'stages': [{'stageId': 'x'}]})), list(gear.BY_RALLY['wales']))


class InGameChallenge(unittest.TestCase):
    def test_stages_picked_in_two_places(self):
        from acr_daily import ig_comp
        cat = {'rallies': [{'name': 'Alsace', 'stages': [{'track': 'Alsace A', 'name': 'A', 'stageId': 'AlsaceS4A'}]},
                           {'name': 'Sweden', 'stages': [{'track': 'Sweden B', 'name': 'B', 'stageId': 'SwedenS1B'}]}],
               'classes': [{'cls': 'Rally4', 'group': 'Modern'}], 'cars': [], 'weathers': [{'id': 'Clear', 'label': 'Clear'}]}
        f = {'cat': cat, 'rally': 1, 'picked': ['Sweden B', 'Alsace A'], 'mode': 'class', 'car': None, 'weather': None,
             'start': '12:00', 'win': 1, 'name': '', 'hide': True}
        ev = ig_comp.challenge_of(f, now_ms=0)
        self.assertEqual([s['track'] for s in ev['stages']], ['Sweden B', 'Alsace A'])   # (in the order picked)
        self.assertEqual(ev['rally'], 'Sweden')


if __name__ == '__main__':
    unittest.main()
