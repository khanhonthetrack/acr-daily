"""The save editor on a copy of the real save (skipped when the game's save isn't on this PC)."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import saveslot  # noqa: E402


@unittest.skipUnless(os.path.exists(saveslot.SAVE), 'no game save')
class SaveSlot(unittest.TestCase):
    def setUp(self):
        with open(saveslot.SAVE, 'rb') as f:
            self.b = f.read()

    def test_reads_the_current_setup(self):
        s = saveslot.read_setup(self.b)
        print('\n  current online single stage:', {k: v[1].decode() for k, v in s.items()})
        self.assertRegex(s['stage'][1].decode(), r'S\d')
        self.assertTrue(s['time'][1].startswith(b'(TimeSeconds='))

    def test_writes_a_daily_and_only_that(self):
        new = saveslot.apply_daily(self.b, 'WelesS4HafrenSouthFullForward', 'LanciaStratosHF', 57600, 'WT_LIGHT_FOG')
        s = saveslot.read_setup(new)
        self.assertEqual(s['stage'][1], b'WelesS4HafrenSouthFullForward')
        self.assertEqual(s['car'][1], b'LanciaStratosHF')
        self.assertEqual(s['time'][1], b'(TimeSeconds=57600.000000)')
        self.assertTrue(s['preset'][1].startswith(b'(WeatherType=WT_LIGHT_FOG,'))
        self.assertTrue(s['preset'][1].endswith(b'bRandom=False)'))
        self.assertEqual(s['speed'][1], b'WT_SPEEDFIX')
        # the block size matches the new file
        so = saveslot._payload(new)
        self.assertEqual(struct.unpack_from('<i', new, so)[0], len(new) - so - 4)
        # everything before the online single stage settings is byte for byte the same
        i = self.b.find(saveslot.SECTION)
        self.assertEqual(new[so + 4:i], self.b[so + 4:i])
        self.assertEqual(new[:so], self.b[:so])
        # and the end of the file (records etc.) too
        tail = 1500
        self.assertEqual(new[-tail:], self.b[-tail:])

    def test_setting_it_back_gives_the_original_file(self):
        s = saveslot.read_setup(self.b)
        new = saveslot.apply_daily(self.b, 'AlsaceS4SaverneFullForward', 'Peugeot208Rally4', 32400, 'WT_CLEAR')
        orig = {k: v[1].decode() for k, v in s.items()}
        import re
        back = saveslot.apply_daily(new, orig['stage'], orig['car'],
                                    float(re.search(r'=([0-9.]+)', orig['time']).group(1)),
                                    re.search(r'WeatherType=(\w+)', orig['preset']).group(1), orig['speed'])
        self.assertEqual(back, self.b)

    def test_refuses_a_broken_file(self):
        with self.assertRaises(saveslot.SaveError):
            saveslot.apply_daily(self.b[:-10], 'AlsaceS4SaverneFullForward', 'Peugeot208Rally4', 32400, 'WT_CLEAR')
        with self.assertRaises(saveslot.SaveError):
            saveslot.apply_daily(b'NOPE' + self.b[4:], 'AlsaceS4SaverneFullForward', 'Peugeot208Rally4', 32400, 'WT_CLEAR')


if __name__ == '__main__':
    unittest.main()
