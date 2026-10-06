import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily.names import same_car, same_track  # noqa: E402


def ch(car, car_id=None, aliases=()):
    return {'track': 'Alsace Forêt', 'car': car, 'carId': car_id, 'carAliases': list(aliases)}


class Names(unittest.TestCase):
    def test_exact_names_the_game_reported(self):
        self.assertTrue(same_car('Mini Cooper S 1275', ch('Mini Cooper S 1275', 'MiniCooperS1275')))
        self.assertTrue(same_car('Peugeot 208 Rally4', ch('Peugeot 208 Rally4', 'Peugeot208Rally4')))

    def test_internal_id_matches(self):
        self.assertTrue(same_car('Hyundai i20 N Rally2', ch('Hyundai i20 N Rally2', 'Hyundaii20NRally2')))
        self.assertTrue(same_car('Skoda Fabia RS Rally2', ch('Skoda Fabia RS Rally2', 'SkodaFabiaRSRally2')))

    def test_small_spelling_differences_match(self):
        self.assertTrue(same_car('Peugeot 306 II Maxi', ch('Peugeot 306 Maxi', 'Peugeot306IIMaxi')))
        self.assertTrue(same_car('Lancia Delta Integrale Evo', ch('Lancia Delta HF Integrale Evo', 'LanciaDeltaHFIntegraleEvo')))
        self.assertTrue(same_car('Citroën Xsara WRC', ch('Citroen Xsara WRC', 'CitroenXsaraWRC')))

    def test_different_models_never_match(self):
        self.assertFalse(same_car('Fiat 131 Abarth', ch('Fiat 124 Abarth', 'Fiat124Abarth')))
        self.assertFalse(same_car('Peugeot 206 WRC', ch('Peugeot 208 Rally4', 'Peugeot208Rally4')))
        self.assertFalse(same_car('Lancia Stratos HF', ch('Lancia Fulvia Coupe HF', 'LanciaFulviaCoupeHF')))
        self.assertFalse(same_car('', ch('Mini Cooper S 1275')))

    def test_names_the_game_really_reports(self):
        # what the telemetry said on the start line, 2026-10-06 (the car's name comes with the daily from the server)
        alfa = ch('Alfa Romeo Giulia GTA Junior 1300', 'AlfaRomeoGTA1300', ['Alfa_Romeo_GTA', 'Alfa Romeo GTA 1300 Junior'])
        self.assertTrue(same_car('Alfa_Romeo_GTA', alfa))
        self.assertTrue(same_track('Monte Carlo St. Geniez - Sistero', {'track': 'Monte Carlo St. Geniez - Sisteron'}))

    def test_a_cut_off_name_is_only_the_start_of_the_real_one(self):
        self.assertFalse(same_track('Monte Carlo St. Geniez', {'track': 'Monte Carlo St. Geniez - Sisteron'}))   # not cut off
        self.assertFalse(same_track('Monte Carlo St. Geniez - Mezien', {'track': 'Monte Carlo St. Geniez - Sisteron'}))

    def test_track_accents_and_case(self):
        self.assertTrue(same_track('Alsace Forêt', ch('x')))
        self.assertTrue(same_track('ALSACE FORET', ch('x')))
        self.assertFalse(same_track('Alsace Obersteigen', ch('x')))


if __name__ == '__main__':
    unittest.main()
