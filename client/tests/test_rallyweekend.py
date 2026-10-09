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


def block(weather=0, start=28800.0):
    """A 42-byte weather block (rallyweekend.py): weather, two rolls, the start time, a seed, wetness, snow, speed,
    grip."""
    b = bytearray(rw.BLOCK)
    b[rw.W_TYPE] = weather
    struct.pack_into('<f', b, 1, 0.37)
    struct.pack_into('<f', b, 10, 0.61)
    struct.pack_into('<f', b, rw.W_START, start)
    struct.pack_into('<i', b, 28, 11382)
    b[rw.W_GRIP] = 4
    return bytes(b)


def context(name, components, versions=()):
    """One context of a mode's settings, as the game writes it: its name, custom versions (16-byte GUID, int32),
    components (name, bytes)."""
    return (F(name) + struct.pack('<i', len(versions)) + b''.join(g + struct.pack('<i', v) for g, v in versions)
            + struct.pack('<i', len(components)) + b''.join(F(n) + struct.pack('<i', len(d)) + d for n, d in components))


def fake_save(stages, done=None, preset='WalesWeekendLong', results=(), single=True):
    """A save laid out as the game's, with the parts the readers and writers look at: the per-mode settings (the Rally
    Weekend set-up: stages (day, stage id, start, zone); a rally in progress when done is a number; and, unless
    single=False (a new player who never drove a Single Rally Stage), the single stage settings), then the current
    selection (stage, car and, with single, its weather options) and a results list."""
    head = bytearray(rw.HEADER)
    head[rw.RESPAWN], head[rw.DAMAGE], head[rw.INTENSITY], head[rw.WEAR] = 1, 1, 1, 1
    head[rw.WEATHER:rw.WEATHER + rw.BLOCK] = block()
    struct.pack_into('<i', head, rw.OPPONENTS, 30)
    head[rw.PENALTY_AT] = 1
    struct.pack_into('<i', head, rw.START_POS, 1)
    cal = b''.join(struct.pack('<i', day) + F(stage) + block(0, start) + block(0, start) + F(zone)
                   for day, stage, start, zone in stages)
    body = bytes(head[4:]) + F(preset) + struct.pack('<i', len(stages)) + cal + struct.pack('<ii', 0, 0) + bytes(16)
    version = (bytes(range(16)), 1)
    rally = [context('ERaceEventSerializableContext::RaceEventSettings',
                     [('RaceEventRaceSettingsRallyWeekendComponent', body)], [version, (bytes(range(16, 32)), 2)])]
    if done is not None:
        rally.append(context('ERaceEventSerializableContext::RaceEventState',
                             [('RaceEventRallyWeekendDataComponent', struct.pack('<i', done)),
                              ('RaceEventRallyWeekendResultsComponent', b'times...'),
                              ('RaceEventSnapshotComponent', b'damage!'),
                              ('RaceEventParticipantsDataComponent', b'drivers')]))
    modes = [('DefaultRally', rally)]
    options = struct.pack('<i', 0)
    if single:
        modes.append(('DefaultOnlineSingleStage', [context('ERaceEventSerializableContext::RaceEventSettings',
                                                           [('RaceEventRaceSettingsSingleEventComponent', bytes(73))], [version])]))
        options = (struct.pack('<i', 3) + F(saveslot.KEY_TIME) + F('(TimeSeconds=68400.000000)') + F(saveslot.KEY_PRESET)
                   + F('(WeatherType=WT_CLEAR,RandomUniform=0.500000,bRandom=False)') + F(saveslot.KEY_SPEED) + F('WT_SPEEDFIX'))
    payload = (struct.pack('<i', len(modes)) + b''.join(F(n) + struct.pack('<i', len(c)) + b''.join(c) for n, c in modes)
               + F(stages[0][1]) + F('Peugeot208Rally4') + options + results_list('DefaultRally', list(results)))
    return b'GVAS' + bytes(20) + F('PlayerSaveGameData') + struct.pack('<i', len(payload)) + payload


THREE_DAYS = [(0, 'WelesS3HafrenNorthFullForward', 28800, 'ServiceParkDefault'),
              (0, 'WelesS4HafrenSouthFullForward', 54000, 'NoZone'),
              (0, 'WelesS3HafrenNorthCut2Reverse', 64800, 'ServiceParkDefault'),
              (1, 'WelesS3HafrenNorthFullForward', 28800, 'ServiceParkDefault'),
              (1, 'WelesS4HafrenSouthFullForward', 54000, 'NoZone'),
              (2, 'WelesS3HafrenNorthCut2Reverse', 64800, 'ServiceParkDefault')]
EVENT = [{'stage': 'GreeceS4LoutrakiFullForward', 'weather': 'WT_CLEAR', 'start': 32400, 'day': 0, 'service': True},
         {'stage': 'GreeceS3ElatiaCut1Forward', 'weather': 'WT_LIGHT_CLOUDS', 'start': 39600, 'day': 0,
          'service': False},
         {'stage': 'GreeceS3ElatiaCut2Reverse', 'weather': 'WT_LIGHT_RAIN', 'start': 50400, 'day': 0, 'service': True},
         {'stage': 'GreeceS4LoutrakiCut1Reverse', 'weather': 'WT_HEAVY_CLOUDS', 'start': 36000, 'day': 1,
          'service': True}]


class Calendars(unittest.TestCase):
    """League events: calendars of several stages and days (on made-up saves laid out as the game's)."""

    def test_reads_the_days_of_a_calendar(self):
        w = rw.read_weekend(fake_save(THREE_DAYS))
        self.assertEqual(w['preset'], 'WalesWeekendLong')
        self.assertEqual([(s['day'], s['zone']) for s in w['stages']],
                         [(0, 'ServiceParkDefault'), (0, 'NoZone'), (0, 'ServiceParkDefault'),
                          (1, 'ServiceParkDefault'), (1, 'NoZone'), (2, 'ServiceParkDefault')])
        self.assertFalse(w['in_progress'])
        self.assertIsNone(rw.progress(fake_save(THREE_DAYS)))
        # days out of order are not the game's
        with self.assertRaises(saveslot.SaveError):
            rw.read_weekend(fake_save([THREE_DAYS[0], (2,) + THREE_DAYS[1][1:]]))

    def test_writes_a_league_event(self):
        new = rw.apply_event(fake_save(THREE_DAYS), EVENT, 'SkodaFabiaRSRally2',
                             {'damageIntensity': 'severe', 'penalty': 'realistic', 'respawn': False})
        w = rw.read_weekend(new)
        self.assertEqual(w['preset'], 'GreeceWeekendMedium')                 # 2 days
        self.assertEqual([(s['stage'], s['day'], s['zone'], s['weather'], s['start']) for s in w['stages']],
                         [('GreeceS4LoutrakiFullForward', 0, 'ServiceParkDefault', 0, 32400.0),
                          ('GreeceS3ElatiaCut1Forward', 0, 'NoZone', 1, 39600.0),
                          ('GreeceS3ElatiaCut2Reverse', 0, 'ServiceParkDefault', 5, 50400.0),
                          ('GreeceS4LoutrakiCut1Reverse', 1, 'ServiceParkDefault', 2, 36000.0)])
        self.assertEqual((w['intensity'], w['penalty'], w['respawn'], w['damage'], w['opponents'], w['order']),
                         (2, 2, 0, 1, 1, 1))
        self.assertEqual(new[w['tail']:w['tail'] + 4], struct.pack('<i', 1))      # an edited calendar
        self.assertEqual(saveslot.read_setup(new)['car'][1], b'SkodaFabiaRSRally2')
        # the daily's one-stage weekend is the same writer with one stage
        one = rw.read_weekend(rw.apply_weekend(fake_save(THREE_DAYS), 'AlsaceS4SaverneShort1Forward',
                                               'Peugeot208Rally4', 57600, 'WT_LIGHT_RAIN'))
        self.assertEqual((one['preset'], len(one['stages']), one['stages'][0]['zone']),
                         ('AlsaceWeekendShort', 1, 'ServiceParkDefault'))

    def test_refuses_what_the_game_would_not_make(self):
        b = fake_save(THREE_DAYS)
        bad = [EVENT[:1] + [dict(EVENT[1], stage='AlsaceS4SaverneFullForward')],   # two locations
               [dict(EVENT[0], service=False)] + EVENT[1:],                       # day 1 without its service park
               EVENT[:3] + [dict(EVENT[3], service=False)],                       # day 2 without one
               EVENT[:1] + [dict(EVENT[1], day=2)],                               # day 2 missing
               [dict(EVENT[0], day=1)],                                           # not starting on day 1
               [dict(EVENT[0], weather='WT_SUNNY')], [dict(EVENT[0], start=86400)],
               [dict(EVENT[0], stage='Greece Elatia')], [], [EVENT[0]] * (rw.MAX_STAGES + 1),
               [dict(EVENT[0], day=d, service=True) for d in range(rw.MAX_DAYS + 1)]]
        for stages in bad:
            with self.assertRaises(saveslot.SaveError, msg=stages):
                rw.apply_event(b, stages, 'SkodaFabiaRSRally2')

    def test_a_rally_in_progress_is_parked_and_brought_back(self):
        old = entry('WelesS4HafrenSouthFullForward', [run('HyundaiI20NRally2', [80.0, 156.1, 213.6], 29)], T0)
        busy = fake_save(THREE_DAYS, done=2, results=[old])
        self.assertEqual(rw.progress(busy)['done'], 2)
        with self.assertRaises(saveslot.SaveError):                  # no new rally over one in progress
            rw.apply_event(busy, EVENT, 'SkodaFabiaRSRally2')
        parked, value = rw.park(busy)
        self.assertIsNone(rw.progress(parked))
        self.assertEqual(len(rw.results(parked)), 1)                 # the game's results stay
        daily = rw.apply_weekend(parked, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_CLEAR')
        self.assertEqual(rw.read_weekend(daily)['stages'][0]['stage'], 'AlsaceS4SaverneShort1Forward')
        back = rw.unpark(daily, value)
        p = rw.progress(back)
        self.assertEqual((p['done'], [s['stage'] for s in p['stages']]), (2, [s[1] for s in THREE_DAYS]))
        k = busy.find(rw.RALLY_KEY)
        self.assertEqual(back[k:k + len(rw.RALLY_KEY) + len(value)], busy[k:k + len(rw.RALLY_KEY) + len(value)])
        so = saveslot._payload(back)
        self.assertEqual(struct.unpack_from('<i', back, so)[0], len(back) - so - 4)
        with self.assertRaises(saveslot.SaveError):
            rw.park(parked)                                          # nothing to set aside
        with self.assertRaises(saveslot.SaveError):
            rw.unpark(parked, b'not a rally')

    def test_a_new_players_save_has_only_the_rally_settings(self):
        """No single stage settings (never driven one): the Rally Weekend is the last entry, the selection follows it."""
        busy = fake_save(THREE_DAYS, done=1, single=False)
        self.assertEqual([m[0] for m in saveslot.modes(busy)], ['DefaultRally'])
        parked, value = rw.park(busy)
        daily = rw.apply_weekend(parked, 'AlsaceS4SaverneShort1Forward', 'CitroenXsaraWRC', 57600, 'WT_CLEAR')
        self.assertEqual(saveslot.read_setup(daily)['car'][1], b'CitroenXsaraWRC')
        back = rw.unpark(daily, value)
        self.assertEqual(rw.progress(back)['done'], 1)
        self.assertEqual(rw.read_weekend(back)['stages'], rw.read_weekend(busy)['stages'])


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
        self.assertEqual(w['next'], {k: v for k, v in st.items() if k not in ('stage', 'zone', 'day')})
        self.assertEqual(saveslot.read_setup(new)['car'][1], b'Peugeot208Rally4')
        # the block size matches the new file; before the component and after it, the file is as the single stage
        # writer leaves it
        so = saveslot._payload(new)
        self.assertEqual(struct.unpack_from('<i', new, so)[0], len(new) - so - 4)
        single = saveslot.apply_daily(self.b, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_LIGHT_RAIN')
        ws = rw.read_weekend(single)
        so = saveslot._payload(single)             # (the block's size before it differs when the calendar's length does)
        self.assertEqual(new[:so] + new[so + 4:w['data']], single[:so] + single[so + 4:ws['data']])
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
