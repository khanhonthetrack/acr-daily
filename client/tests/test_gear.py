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
