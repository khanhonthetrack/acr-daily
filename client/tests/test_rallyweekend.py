"""The Rally Weekend set-up writer and the reader of the game's own results."""
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import rallyweekend as rw, saveslot  # noqa: E402

F = saveslot._fstring


def run(car, splits, penalty, index=0):
    """One stage result as the game writes it: splits = cumulative times at each split, the last one the finish."""
    out = struct.pack('<i', index) + F(car) + struct.pack('<i', len(splits) + 1) + struct.pack('<iff', 0, 0, 0)
    prev = 0.0
    for k, t in enumerate(splits, 1):
        out += struct.pack('<iff', k, t, t - prev)
        prev = t
    return out + struct.pack('<f', penalty) + bytes(8)


def entry(stage, runs, unix):
    return F(stage) + struct.pack('<i', len(runs)) + b''.join(runs) + \
        struct.pack('<q', int(unix * 1e7) + rw.TICKS_1970)


def results_list(mode, entries):
    return F(mode) + struct.pack('<i', len(entries)) + b''.join(entries) + struct.pack('<i', 0)


T0 = 1791482963.0     # 2026-10-08 18:09:23 UTC


class Results(unittest.TestCase):
    def setUp(self):
        # the settings entry comes first under the same key and is not a results list
        self.b = (b'junk' + F('DefaultRally') + struct.pack('<i', 1) + F('ERaceEventSerializableContext::RaceEventSettings')
                  + b'more junk' + results_list('DefaultTimeAttack', [
                      entry('AlsaceS4SaverneFullForward', [run('Peugeot208Rally4', [97.0, 265.9, 368.6], 0)], T0 - 9e5)])
                  + results_list('DefaultRally', [
                      entry('WelesS4HafrenSouthFullForward', [run('HyundaiI20NRally2', [80.022, 156.138, 213.597], 29)],
                            T0 - 1428),
                      entry('WelesS4HafrenSouthFullForward', [run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)],
                            T0)]))

    def test_reads_every_result_of_a_mode(self):
        rs = rw.results(self.b)
        self.assertEqual([round(r['started']) for r in rs], [round(T0 - 1428), round(T0)])
        last = rs[-1]['runs'][0]
        self.assertEqual(last['car'], 'HyundaiI20NRally2')
        self.assertAlmostEqual(last['time'], 203.284, places=3)
        self.assertEqual(last['penalty'], 90)
        self.assertEqual([round(s, 3) for s in last['splits']], [87.618, 160.034, 203.284])
        self.assertEqual(rw.started_text(rs[-1]['started']), '2026-10-08 18:09:23 UTC')
        self.assertEqual(len(rw.results(self.b, 'DefaultTimeAttack')), 1)
        self.assertEqual(rw.results(self.b, 'DefaultFreePractice'), [])

    def test_official_result_of_a_run(self):
        before = {T0 - 1428}                     # what the save held when the run started
        o = rw.official(self.b, 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2', before, since=T0 + 40)
        self.assertEqual((round(o['time'], 3), o['penalty'], o['total']), (203.284, 90, 293.284))
        self.assertEqual(rw.known(self.b), {T0 - 1428, T0})
        # the game's names ignore case (one save spells this car HyundaiI20NRally2 and Hyundaii20NRally2)
        self.assertEqual(rw.official(self.b, 'WelesS4HafrenSouthFullForward', 'Hyundaii20NRally2', before)['total'],
                         293.284)
        # not yet there, too old, another car, another stage
        self.assertIsNone(rw.official(self.b, 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2', rw.known(self.b)))
        self.assertIsNone(rw.official(self.b, 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2', before,
                                      since=T0 + 7200))
        self.assertIsNone(rw.official(self.b, 'WelesS4HafrenSouthFullForward', 'LanciaStratosHF', before))
        self.assertIsNone(rw.official(self.b, 'WelesS4HafrenSouthFullReverse', 'HyundaiI20NRally2', before))

    def test_a_damaged_list_reads_as_nothing(self):
        i = self.b.find(F('DefaultRally'), self.b.find(F('DefaultTimeAttack')))
        broken = self.b[:i + 40] + b'\xff' * 8 + self.b[i + 48:]
        self.assertEqual(rw.results(broken), [])
        for cut in range(len(self.b) - 120, len(self.b) - 4):      # read while the game was still writing it
            self.assertEqual(len(rw.results(self.b[:cut])), 0)


@unittest.skipUnless(os.path.exists(saveslot.SAVE), 'no game save')
class Weekend(unittest.TestCase):
    """On a copy of the real save (skipped when the game's save isn't on this PC)."""

    def setUp(self):
        with open(saveslot.SAVE, 'rb') as f:
            self.b = f.read()
        try:
            self.w = rw.read_weekend(self.b)
        except saveslot.SaveError as e:
            self.skipTest('this save: %s' % e)

    def test_reads_the_current_setup(self):
        print('\n  current Rally Weekend:', self.w['preset'], [s['stage'] for s in self.w['stages']])
        self.assertTrue(self.w['stages'])

    def test_writes_a_one_stage_weekend_and_only_that(self):
        if self.w['in_progress']:
            self.skipTest('a rally is in progress in this save')
        new = rw.apply_weekend(self.b, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_LIGHT_RAIN',
                               {'penalty': 'realistic', 'damage': False})
        w = rw.read_weekend(new)
        self.assertEqual(w['preset'], 'AlsaceWeekendShort')
        self.assertEqual((w['respawn'], w['damage'], w['opponents'], w['penalty'], w['order'], w['start_position']),
                         (1, 0, 1, 2, 1, 1))
        self.assertEqual((w['intensity'], w['wear'], w['failures']), (1, 1, 0))
        self.assertEqual(len(w['stages']), 1)
        st = w['stages'][0]
        self.assertEqual((st['stage'], st['zone'], st['weather'], st['start'], st['accel'], st['grip']),
                         ('AlsaceS4SaverneShort1Forward', 'ServiceParkDefault', 5, 57600.0, 0, 4))
        self.assertAlmostEqual(st['wetness'], 0.2, places=5)
        self.assertEqual(w['next'], {k: v for k, v in st.items() if k not in ('stage', 'zone')})
        self.assertEqual(saveslot.read_setup(new)['car'][1], b'Peugeot208Rally4')
        # the block size matches the new file; before the component and after it, the file is as the single stage
        # writer leaves it
        so = saveslot._payload(new)
        self.assertEqual(struct.unpack_from('<i', new, so)[0], len(new) - so - 4)
        single = saveslot.apply_daily(self.b, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_LIGHT_RAIN')
        ws = rw.read_weekend(single)
        self.assertEqual(new[:w['data']], single[:ws['data']])
        self.assertEqual(new[w['end']:], single[ws['end']:])
        # the game's own results are still there
        self.assertEqual(rw.results(new), rw.results(self.b))

    def test_the_daily_rules_and_a_dry_road(self):
        if self.w['in_progress']:
            self.skipTest('a rally is in progress in this save')
        new = rw.apply_weekend(self.b, 'GreeceS4LoutrakiFullForward', 'SkodaFabiaRSRally2', 43200, 'WT_CLEAR')
        w = rw.read_weekend(new)
        # penalty light, respawn on, damage on (light damage, light wear, no mechanical failures)
        self.assertEqual((w['preset'], w['stages'][0]['wetness'], w['penalty'], w['respawn'], w['damage'],
                          w['intensity'], w['wear'], w['failures']), ('GreeceWeekendShort', 0.0, 1, 1, 1, 1, 1, 0))
        with self.assertRaises(saveslot.SaveError):
            rw.apply_weekend(self.b, 'GreeceS4LoutrakiFullForward', 'SkodaFabiaRSRally2', 43200, 'WT_CLEAR',
                             {'failures': 'sometimes'})

    def test_refuses_a_rally_in_progress_and_broken_files(self):
        w = self.w
        state = F('ERaceEventSerializableContext::RaceEventState')
        busy = self.b[:w['end']] + state + self.b[w['end']:]
        with self.assertRaises(saveslot.SaveError):
            rw.apply_weekend(busy, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_CLEAR')
        with self.assertRaises(saveslot.SaveError):
            rw.apply_weekend(self.b, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_SUNNY')
        # a calendar one byte off where the layout says it is
        d = w['data']
        bad = bytearray(self.b)
        struct.pack_into('<i', bad, d, struct.unpack_from('<i', bad, d)[0] + 1)
        with self.assertRaises(saveslot.SaveError):
            rw.read_weekend(bytes(bad))


if __name__ == '__main__':
    unittest.main()
