"""Tyres and livery picked for an event (gear.py): the counts, what goes to the game, the liveries found."""
import os
import tempfile
import unittest
from unittest import mock

from acr_daily import gear

EV = {'id': 7, 'rally': 'Wales', 'kind': 'league'}


class Tyres(unittest.TestCase):
    def setUp(self):
        p = mock.patch('acr_daily.gear.settings.save')
        p.start()
        self.addCleanup(p.stop)

    def test_counts_always_add_up(self):
        s = {}
        self.assertEqual(sum(gear.start_counts(EV).values()), gear.TYRES)
        for row, d in (('GravelSoft', 1), ('GravelSoft', 1), ('GravelHard', -1), ('GravelMedium', 1)):
            c = gear.step_tyres(s, EV, row, d)
            self.assertEqual(sum(c.values()), gear.TYRES)
            self.assertTrue(all(v >= 0 for v in c.values()))
        self.assertEqual(gear.tyres_of(s, EV), {k: v for k, v in c.items() if v})

    def test_auto_and_what_goes_to_the_game(self):
        s = {}
        self.assertEqual(gear.for_setup(s, EV, 'NoSuchCar'), {})        # (nothing picked: the game's own)
        gear.step_tyres(s, EV, 'GravelSoft', 1)
        self.assertIn('tyres', gear.for_setup(s, EV, 'NoSuchCar'))
        self.assertNotIn('tyres', gear.for_setup(s, dict(EV, kind='live'), 'NoSuchCar'))   # (ranked: all alike)
        gear.auto_tyres(s, EV)
        self.assertIsNone(gear.tyres_of(s, EV))

    def test_compounds_by_rally(self):
        self.assertEqual(gear.compounds({'rally': 'Sweden'}), ('FullSnow',))
        self.assertIn('TarmacWet', gear.compounds({'rally': 'Alsace'}))
        self.assertEqual(gear.compounds({'rally': 'Somewhere new'}), ())


MIXED = {'id': 9, 'rally': 'Alsace · Wales · Sweden', 'kind': 'league',
         'stages': [{'track': 'Alsace Obersteigen', 'stageId': 'AlsaceS4SaverneShort1Forward', 'day': 1},
                    {'track': 'Wales Afon Bidno', 'stageId': 'WelesS4HafrenSouthFullForward', 'day': 1},
                    {'track': 'Sweden Gravendal East', 'stageId': 'SwedenS3FredriksbergCut2Reverse', 'day': 1},
                    {'track': 'Alsace La Mossig', 'stageId': 'AlsaceS4SaverneShort1Reverse', 'day': 2}]}


class TyresBySurface(unittest.TestCase):
    """An event on several surfaces: a set picked for each at the start, each leg given its own (the user, 24 Nov 2026)."""
    def setUp(self):
        p = mock.patch('acr_daily.gear.settings.save')
        p.start()
        self.addCleanup(p.stop)

    def test_one_set_a_surface(self):
        self.assertEqual(gear.surfaces(MIXED), ['tarmac', 'gravel', 'snow'])
        self.assertEqual(gear.surface_stages(MIXED, 'tarmac'), [1, 4])
        self.assertEqual(gear.compounds(MIXED), ())                       # (no one set for all of it)
        s = {}
        gear.step_tyres(s, MIXED, 'TarmacSoft', 1, surface='tarmac')
        gear.step_tyres(s, MIXED, 'GravelHard', 1, surface='gravel')
        kept = s['eventTyres']['9']
        self.assertEqual(sorted(kept), ['@gravel', '@tarmac'])
        self.assertEqual(sum(gear.tyres_of(s, MIXED, surface='tarmac').values()), gear.TYRES)
        self.assertIsNone(gear.tyres_of(s, MIXED, surface='snow'))
        gear.auto_tyres(s, MIXED, surface='gravel')                       # (that surface back to the game's own)
        self.assertEqual(sorted(s['eventTyres']['9']), ['@tarmac'])

    def test_each_leg_its_own(self):
        s = {}
        gear.step_tyres(s, MIXED, 'TarmacSoft', 1, surface='tarmac')
        gear.step_tyres(s, MIXED, 'GravelHard', 1, surface='gravel')
        from acr_daily import leagues
        self.assertEqual(leagues.legs(MIXED), [(0, 1), (1, 2), (2, 3), (3, 4)])
        legs = [gear.for_setup(s, MIXED, 'NoSuchCar', leg).get('tyres') for leg in range(4)]
        self.assertIn('TarmacSoft', legs[0])
        self.assertIn('GravelHard', legs[1])
        self.assertIsNone(legs[2])                                        # (snow: the game's)
        self.assertEqual(legs[3], legs[0])

    def test_a_one_surface_events_counts_as_before(self):
        s = {'eventTyres': {'7': {'GravelSoft': 6, 'GravelMedium': 5, 'GravelHard': 5}}}
        self.assertEqual(gear.tyres_of(s, EV), {'GravelSoft': 6, 'GravelMedium': 5, 'GravelHard': 5})
        gear.step_tyres(s, EV, 'GravelSoft', 1)
        self.assertFalse(any(k.startswith('@') for k in s['eventTyres']['7']))


class PickerInTheGame(unittest.TestCase):
    """ACR DAILY's event card in the game (ig_comp.gear_picker): a set for each surface, each its own clicks."""
    def setUp(self):
        p = mock.patch('acr_daily.gear.settings.save')
        p.start()
        self.addCleanup(p.stop)

    def test_a_picker_a_surface(self):
        import json
        from acr_daily import ig_comp
        a = mock.Mock()
        a.s = {}
        a._league_car.return_value = None
        a._league_event.return_value = MIXED
        ig = mock.Mock(app=a)
        said = json.dumps(ig_comp.gear_picker(ig, MIXED), ensure_ascii=False)
        self.assertIn('TARMAC · SS1, SS4', said)
        self.assertIn('GRAVEL · SS2', said)
        self.assertNotIn('SNOW · SS3', said)                         # (one compound: nothing to pick)
        ig_comp.gear_click(a, 'tyre', '9:GravelHard:1:gravel')
        self.assertIn('@gravel', a.s['eventTyres']['9'])
        ig_comp.gear_click(a, 'tyreauto', '9:gravel')
        self.assertNotIn('9', a.s['eventTyres'])


class Liveries(unittest.TestCase):
    def test_official_and_own(self):
        base = tempfile.mkdtemp()
        for n in ('DLR', 'B team', '_off'):
            os.makedirs(os.path.join(base, 'Hyundaii20NRally2', n))
        c = gear.choices('HyundaiI20NRally2', base=base)
        self.assertEqual(c, [('Hyundaii20NRally2', 'Official'), ('usergen_B team', 'B team'), ('usergen_DLR', 'DLR')])
        self.assertEqual(gear.choices('SomeModCar', base=base), [])

    def test_only_a_livery_still_there_goes(self):
        s = {'carLivery': {'SkodaFabiaRSRally2': 'usergen_Gone'}}
        with mock.patch('acr_daily.gear.own', return_value=[]):
            self.assertEqual(gear.for_setup(s, EV, 'SkodaFabiaRSRally2'), {})
        s['carLivery']['SkodaFabiaRSRally2'] = 'SkodaFabiaRSRally2'
        self.assertEqual(gear.for_setup(s, EV, 'SkodaFabiaRSRally2')['livery'], 'SkodaFabiaRSRally2')


if __name__ == '__main__':
    unittest.main()
