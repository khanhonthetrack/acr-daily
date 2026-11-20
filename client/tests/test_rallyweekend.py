"""The Rally Weekend set-up writer and the reader of the game's own results."""
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import rallyweekend as rw, saveslot  # noqa: E402


def rw_settings():
    """The settings module rallyweekend reads the WRC Generations stages' locations from (never the real file here)."""
    from acr_daily import settings
    return settings

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

    def test_official_result_by_its_time(self):
        S, C = 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2'
        self.assertEqual(rw.official(self.b, S, C, clock_ms=203300, tol_ms=50)['total'], 293.284)
        self.assertIsNone(rw.official(self.b, S, C, clock_ms=203400, tol_ms=50))
        d = rw.describe(self.b, S, C, {T0})
        self.assertIn('203.284 +90 (there at the start)', d)
        self.assertEqual(rw.describe(None, S, C), 'no save read')

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


def old_block(weather=0, start=28800.0):
    """A weather block as saves from before the game update of 2026-10-06 have it: 38 bytes (which 4 of today's 42 it
    lacks isn't known: here 20..23)."""
    b = block(weather, start)
    return b[:20] + b[24:]


def fake_save(stages, done=None, preset='WalesWeekendLong', results=(), single=True, rally=True, old=False,
              before=(), after=(), state_copy=False):
    """A save laid out as the game's, with the parts the readers and writers look at: the per-mode settings (unless
    rally=False (a player who never started a Rally Weekend), the Rally Weekend set-up: stages (day, stage id, start,
    zone); a rally in progress when done is a number; and, unless single=False (a new player who never drove a Single
    Rally Stage), the single stage settings), then the current selection (stage, car and, with single, its weather
    options) and a results list. old: the Rally Weekend set-up in the layout from before the game update of
    2026-10-06 (38-byte weather blocks, so all after the first 4 bytes earlier; in today's offsets the opponents and
    the start position then read as the floats that follow them, as a driver's save had them, 18 Nov 2026).
    before / after: names of other entries of the per-mode map, each with a Rally Weekend set-up of its own (Greece),
    before and after the player's own (the game's 0.7 Challenges); state_copy: the rally in progress holds a copy of
    the set-up as well."""
    sh, blk = (-4, old_block) if old else (0, block)
    head = bytearray(rw.HEADER + sh)
    head[rw.RESPAWN], head[rw.DAMAGE], head[rw.INTENSITY], head[rw.WEAR] = 1, 1, 1, 1
    head[rw.WEATHER:rw.WEATHER + rw.BLOCK + sh] = blk()
    struct.pack_into('<i', head, rw.OPPONENTS + sh, 30)
    head[rw.PENALTY_AT + sh] = 1
    struct.pack_into('<i', head, rw.START_POS + sh, 1)
    if old:                                          # (what today's offsets 71 and 92 find there: the AI's floats)
        struct.pack_into('<f', head, rw.OPPONENTS, 0.85)
        struct.pack_into('<f', head, rw.START_POS, 0.61)
    cal = b''.join(struct.pack('<i', day) + F(stage) + blk(0, start) + blk(0, start) + F(zone)
                   for day, stage, start, zone in stages)
    body = bytes(head[4:]) + F(preset) + struct.pack('<i', len(stages)) + cal + struct.pack('<ii', 0, 0) + bytes(16)
    version = (bytes(range(16)), 1)
    contexts = [context('ERaceEventSerializableContext::RaceEventSettings',
                        [('RaceEventRaceSettingsRallyWeekendComponent', body)], [version, (bytes(range(16, 32)), 1 if old else 2)])]
    if done is not None:
        contexts.append(context('ERaceEventSerializableContext::RaceEventState',
                                ([('RaceEventRaceSettingsRallyWeekendComponent', body)] if state_copy else [])
                                + [('RaceEventRallyWeekendDataComponent', struct.pack('<i', done)),
                                   ('RaceEventRallyWeekendResultsComponent', b'times...'),
                                   ('RaceEventSnapshotComponent', b'damage!'),
                                   ('RaceEventParticipantsDataComponent', b'drivers')]))
    other = body.replace(F(preset), F('GreeceWeekendShort')).replace(b'Weles', b'Greek')
    challenge = [context('ERaceEventSerializableContext::RaceEventSettings',
                         [('RaceEventRaceSettingsRallyWeekendComponent', other)], [version])]
    modes = ([(n, challenge) for n in before] + ([('DefaultRally', contexts)] if rally else [])
             + [(n, challenge) for n in after])
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


class GoneCalendars(unittest.TestCase):
    """A Rally Weekend on a calendar or a stage of a set the stage switch hid: the game's calendar editor crashes on it
    (London's calendar with London hidden, 18 Nov 2026), so it is noticed and set back to one of the game's own."""

    def test_a_hidden_sets_calendar_or_stage_is_noticed(self):
        london = fake_save([(0, 'AcrXsLn02r0FullForward', 43200, 'ServiceParkDefault')], preset='AcrXsLnWeekendShort')
        self.assertEqual(rw.calendar_gone(london), 'calendar AcrXsLnWeekendShort')
        self.assertIsNone(rw.calendar_gone(london, ('AcrXsLn',), ('AcrXsLn',)))           # (London shown)
        wrcg = fake_save([(0, 'WrcgFrSS1RFull', 43200, 'ServiceParkDefault')], preset='WrcgFranceWeekendShort')
        self.assertEqual(rw.calendar_gone(wrcg, ('AcrXsLn',), ('AcrXsLn',)), 'calendar WrcgFranceWeekendShort')
        self.assertEqual(rw.calendar_gone(wrcg, (), ('Wrcg',)), 'calendar WrcgFranceWeekendShort')   # (no calendars)
        self.assertIsNone(rw.calendar_gone(wrcg, ('Wrcg',), ('Wrcg',)))
        # (a mod's stage in a calendar of the game's: the app's London daily in Wales' calendar)
        daily = fake_save([(0, 'AcrXsLn02r0FullForward', 43200, 'ServiceParkDefault')], preset='WalesWeekendShort')
        self.assertEqual(rw.calendar_gone(daily, ('Wrcg',), ('Wrcg',)), 'stage AcrXsLn02r0FullForward')
        self.assertIsNone(rw.calendar_gone(fake_save(THREE_DAYS)))                          # (the game's own)
        going = fake_save([(0, 'AcrXsLn02r0FullForward', 43200, 'ServiceParkDefault')], done=0,
                          preset='AcrXsLnWeekendShort')
        self.assertIsNone(rw.calendar_gone(going))                                          # (in progress: left alone)
        self.assertIsNone(rw.calendar_gone(fake_save(THREE_DAYS, rally=False)))

    def test_sweden_is_one_of_the_games_own(self):
        """The game's 0.7 (19 Nov 2026) added Sweden: a player's own Sweden Rally Weekend is the game's, never set back
        to Wales; and the app sets one up in Sweden's own calendar (checked in the game: Vargåsvägen East, Delta S4)."""
        swe = fake_save([(0, 'SwedenS1VargasenCut1Forward', 43200, 'ServiceParkDefault')], preset='SwedenWeekendShort')
        self.assertIsNone(rw.calendar_gone(swe))
        self.assertIsNone(rw.calendar_gone(swe, ('AcrXsLn',), ('AcrXsLn',)))
        self.assertEqual(rw.location_preset('SwedenS1VargasenCut1Forward'), 'SwedenWeekendShort')
        self.assertEqual(rw.location_preset('SwedenS3FredriksbergCu1Reverse'), 'SwedenWeekendShort')   # (the game's "Cu1")
        w = rw.read_weekend(rw.apply_weekend(fake_save(THREE_DAYS), 'SwedenS3FredriksbergFullForward', 'LanciaDeltaS4',
                                             43200, 'WT_LIGHT_SNOW'))
        self.assertEqual((w['preset'], [s['stage'] for s in w['stages']]), ('SwedenWeekendShort', ['SwedenS3FredriksbergFullForward']))

    def test_set_back_to_one_of_the_games_own(self):
        b = rw.reset_to_game(fake_save([(0, 'WrcgFrSS1RFull', 43200, 'ServiceParkDefault')], preset='WrcgFranceWeekendShort'))
        w = rw.read_weekend(b)
        self.assertEqual((w['preset'], [s['stage'] for s in w['stages']]), ('WalesWeekendShort', ['WelesS4HafrenSouthFullForward']))
        self.assertIsNone(rw.calendar_gone(b))
        self.assertEqual(saveslot.read_setup(b)['car'][1], b'Peugeot208Rally4')            # (the car kept)


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

    def test_the_games_random_weather_is_switched_off(self):
        """Reported 2026-11-07 (ACR Hungary, Teszt verseny): the player's save had the game's random weather on (bytes
        5, 14 and 20 of each weather block: 1). The event's blocks are copies of the save's own, so they had it on too,
        and the game drew another weather for every stage at each START RALLY: the event's Clear never held, and the
        app rightly said the weather had changed. Written now with the switches off, as in the game's own set-up."""
        b = bytearray(fake_save(THREE_DAYS))
        w = rw.read_weekend(bytes(b))
        at = [w['data'] + rw.WEATHER]                              # the header's block, then each stage's two
        o = saveslot._fstring_at(b, w['data'] + rw.HEADER)[1] + 4
        for _s in w['stages']:
            o = saveslot._fstring_at(b, o + 4)[1]
            at += [o, o + rw.BLOCK]
            o = saveslot._fstring_at(b, o + 2 * rw.BLOCK)[1]
        for o in at:
            for k in rw.W_RANDOM:
                b[o + k] = 1
        w = rw.read_weekend(bytes(b))
        self.assertTrue(w['next']['random'] and all(s['random'] for s in w['stages']))   # read as the game left it
        new = rw.apply_event(bytes(b), EVENT, 'SkodaFabiaRSRally2')
        back = rw.read_weekend(new)
        self.assertFalse(back['next']['random'] or any(s['random'] for s in back['stages']))
        self.assertEqual([s['weather'] for s in back['stages']], [rw.WEATHERS.index(s['weather']) for s in EVENT])
        o = saveslot._fstring_at(new, back['data'] + rw.HEADER)[1] + 4
        for _s in back['stages']:                                  # the default (RESET) copy too
            o = saveslot._fstring_at(new, o + 4)[1]
            self.assertEqual([new[o + rw.BLOCK + k] for k in rw.W_RANDOM], [0, 0, 0])
            o = saveslot._fstring_at(new, o + 2 * rw.BLOCK)[1]

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

    def test_a_rally_left_unfinished_before_the_games_update_is_set_aside_too(self):
        """A driver's own Rally Weekend from before the game update of 2026-10-06, left unfinished, kept in the old
        layout: DRIVE stopped with 'unexpected Rally Weekend settings {... opponents: 1062836634 (0.85 as a float),
        penalty: 0, order: 0, start_position: 1058805560 ...}' (18 Nov 2026). It reads, is set aside and put back as it
        was; the set-up is written from the game's own defaults, in today's layout."""
        busy = fake_save(THREE_DAYS, done=2, old=True)
        with self.assertRaisesRegex(saveslot.SaveError, 'unexpected Rally Weekend settings'):
            rw._read_weekend(busy, rw.BLOCK)                         # (what DRIVE stopped on)
        w = rw.read_weekend(busy)
        self.assertEqual((w['old'], w['in_progress'], w['opponents'], w['penalty'], w['start_position'], w['preset'], w['next']),
                         (True, True, 30, 1, 1, 'WalesWeekendLong', None))
        self.assertEqual([(s['stage'], s['day'], s['zone']) for s in w['stages']], [(s[1], s[0], s[3]) for s in THREE_DAYS])
        self.assertEqual(rw.progress(busy)['done'], 2)
        with self.assertRaises(saveslot.SaveError):                  # no new rally over one in progress
            rw.apply_event(busy, EVENT, 'SkodaFabiaRSRally2')
        parked, value = rw.park(busy)
        self.assertIsNone(rw.progress(parked))
        self.assertTrue(rw.read_weekend(parked)['old'])
        daily = rw.apply_weekend(parked, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_CLEAR')
        d = rw.read_weekend(daily)
        self.assertEqual((d['old'], [s['stage'] for s in d['stages']], d['opponents'], d['stages'][0]['start']),
                         (False, ['AlsaceS4SaverneShort1Forward'], 1, 57600.0))
        # (in today's layout with the game's own versions: its default settings context, then the set-up written over it)
        ctx = rw.RALLY_ENTRY[len(rw.RALLY_KEY) + 4:rw.RALLY_ENTRY.find(rw.COMPONENT)]
        self.assertIn(ctx, daily)
        back = rw.unpark(daily, value)
        p = rw.progress(back)
        self.assertEqual((p['done'], [s['stage'] for s in p['stages']]), (2, [s[1] for s in THREE_DAYS]))
        k = busy.find(rw.RALLY_KEY)
        self.assertEqual(back[k:k + len(rw.RALLY_KEY) + len(value)], busy[k:k + len(rw.RALLY_KEY) + len(value)])
        # old settings without a rally in progress: written over the same way
        one = rw.read_weekend(rw.apply_event(fake_save(THREE_DAYS, old=True), EVENT, 'SkodaFabiaRSRally2'))
        self.assertEqual((one['old'], len(one['stages'])), (False, len(EVENT)))

    def test_a_community_stage_in_its_own_locations_calendar(self):
        """ACR DAILY London (acr-extrastages' AcrXs id, community.py): its one-stage weekend in London's own calendar
        (Wales', which it once used, crashes the game at the tyre allocation now that London is a level of its own), and
        a save with it in its calendar and its results still read. Lousã: Portugal's (AcrXsPt)."""
        new = rw.apply_weekend(fake_save(THREE_DAYS), 'AcrXsLn02r0FullForward', 'Peugeot208Rally4', 43200, 'WT_CLEAR')
        w = rw.read_weekend(new)
        self.assertEqual((w['preset'], [s['stage'] for s in w['stages']], w['stages'][0]['zone']),
                         ('AcrXsLnWeekendShort', ['AcrXsLn02r0FullForward'], 'ServiceParkDefault'))
        self.assertEqual(rw.location_preset('AcrXsLn02r1FullForward'), 'AcrXsLnWeekendShort')
        self.assertEqual(rw.location_preset('AcrXsPtLousaFullForward'), 'AcrXsPtWeekendShort')
        res = results_list('DefaultRally', [entry('AcrXsLn02r0FullForward', [run('Peugeot208Rally4', [101.5, 240.25], 0)], T0)])
        self.assertEqual([r['stage'] for r in rw.results(b'junk' + res)], ['AcrXsLn02r0FullForward'])
        for bad in ('AcrXsFullForward', 'LondonS1WestminsterFullForward'):
            with self.assertRaises(saveslot.SaveError):
                rw.apply_weekend(fake_save(THREE_DAYS), bad, 'Peugeot208Rally4', 43200, 'WT_CLEAR')

    def test_mods_stages_in_the_save_change_nothing_for_the_dailies(self):
        """Stages of mods (Sando Rally's SandoChlBioFull, Stage Exporter's WrcgEsSS1Full) in the player's own Rally
        Weekend or results: the save still reads, DRIVE still writes the daily, and the daily's official time is found
        next to them."""
        mods = [(0, 'WrcgEsSS1Full', 32400, 'ServiceParkDefault'), (0, 'SandoChlBioFull', 39600, 'NoZone'),
                (1, 'WrcgSeSS3Full', 36000, 'ServiceParkDefault')]
        w = rw.read_weekend(fake_save(mods))
        self.assertEqual([s['stage'] for s in w['stages']], ['WrcgEsSS1Full', 'SandoChlBioFull', 'WrcgSeSS3Full'])
        new = rw.apply_weekend(fake_save(mods), 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2', 43200, 'WT_CLEAR')
        self.assertEqual([s['stage'] for s in rw.read_weekend(new)['stages']], ['WelesS4HafrenSouthFullForward'])
        res = results_list('DefaultRally', [
            entry('WrcgEsSS1Full', [run('SkodaFabiaRSRally2', [120.0, 301.5], 0)], T0 - 7200),
            entry('SandoChlBioFull', [run('HyundaiI20NRally2', [150.0, 410.25], 10)], T0 - 3600),
            entry('WelesS4HafrenSouthFullForward', [run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], T0)])
        b = b'junk' + res
        self.assertEqual([r['stage'] for r in rw.results(b)], ['WrcgEsSS1Full', 'SandoChlBioFull',
                                                                'WelesS4HafrenSouthFullForward'])
        got = rw.official(b, 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2', since=T0)
        self.assertEqual((round(got['time'], 3), got['penalty']), (203.284, 90.0))
        with self.assertRaises(saveslot.SaveError):                # (Sando Rally's: Free Practice only, never written)
            rw.apply_weekend(fake_save(THREE_DAYS), 'SandoChlBioFull', 'HyundaiI20NRally2', 43200, 'WT_CLEAR')

    def test_a_wrc_generations_stage_in_its_locations_own_calendar(self):
        """A WRC Generations stage (Stage Exporter's Wrcg id: a private time trial's) in a Rally Weekend of its [MOD]
        location's own 1-day calendar, which the app made (stagecalendars.py): the location the calendars were made
        from (settings), else the pack's own naming (Wrcg + the country)."""
        with mock.patch.object(rw_settings(), 'load', return_value={}):
            self.assertEqual(rw.location_preset('WrcgDePanzerplatteFull'), 'WrcgGermanyWeekendShort')
            self.assertEqual(rw.location_preset('WrcgEsSS4RFull'), 'WrcgSpainWeekendShort')
            self.assertIsNone(rw.location_preset('WrcgXxSS1Full'))
            self.assertIsNone(rw.location_preset('SandoChlBioFull'))
            self.assertEqual(rw.location_preset('AcrXsLn02r0FullForward'), 'AcrXsLnWeekendShort')
            self.assertEqual(rw.location_preset('WelesS4HafrenSouthFullForward'), 'WalesWeekendShort')
            new = rw.apply_weekend(fake_save(THREE_DAYS), 'WrcgDePanzerplatteFull', 'Peugeot208Rally4', 43200, 'WT_CLEAR')
        w = rw.read_weekend(new)
        self.assertEqual((w['preset'], [s['stage'] for s in w['stages']], w['stages'][0]['zone']),
                         ('WrcgGermanyWeekendShort', ['WrcgDePanzerplatteFull'], 'ServiceParkDefault'))
        with mock.patch.object(rw_settings(), 'load', return_value={'wrcgLocations': {'WrcgDePanzerplatteFull': 'WrcgDeArena'}}):
            self.assertEqual(rw.location_preset('WrcgDePanzerplatteFull'), 'WrcgDeArenaWeekendShort')
        with self.assertRaises(saveslot.SaveError):                # (one location a weekend)
            with mock.patch.object(rw_settings(), 'load', return_value={}):
                rw.apply_event(fake_save(THREE_DAYS), [
                    {'stage': 'WrcgDePanzerplatteFull', 'weather': 'WT_CLEAR', 'start': 43200, 'day': 0, 'service': True},
                    {'stage': 'WrcgEsSS1Full', 'weather': 'WT_CLEAR', 'start': 46800, 'day': 0}], 'Peugeot208Rally4')

    def test_a_player_who_never_started_a_rally_weekend(self):
        """No Rally Weekend settings at all (only Single Rally Stages driven): the game's default ones are added."""
        b = fake_save(THREE_DAYS, rally=False)
        self.assertNotIn(rw.COMPONENT, b)
        self.assertIsNone(rw.progress(b))                            # no rally in progress (not an error)
        new = rw.apply_weekend(b, 'MonteCarloS1BolleneFullReverse', 'CitroenXsaraWRC', 57600, 'WT_HEAVY_CLOUDS')
        self.assertEqual([m[0] for m in saveslot.modes(new)], ['DefaultOnlineSingleStage', 'DefaultRally'])
        w = rw.read_weekend(new)
        self.assertEqual((w['preset'], [s['stage'] for s in w['stages']], w['opponents'], w['in_progress']),
                         ('MontecarloWeekendShort', ['MonteCarloS1BolleneFullReverse'], 1, False))
        self.assertEqual(saveslot.read_setup(new)['car'][1], b'CitroenXsaraWRC')
        so = saveslot._payload(new)
        self.assertEqual(struct.unpack_from('<i', new, so)[0], len(new) - so - 4)
        with self.assertRaises(saveslot.SaveError):                 # nothing to read in the save itself
            rw.read_weekend(b)

    def test_the_default_rally_settings_are_the_games_own(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'saves', 'new-player.sav'), 'rb') as f:
            game = f.read()
        (_name, at, _value, end), = saveslot.modes(game)
        self.assertEqual(rw.RALLY_ENTRY, game[at:end])

    def test_a_save_made_with_settings_the_dailies_never_use(self):
        """The player's own Rally Weekend somewhere else, with the menu's fastest time, and results in any car: still
        readable (only its layout is checked), and DRIVE replaces it."""
        b = bytearray(fake_save([(0, 'SwedenS1VarmlandFullForward', 28800, 'ServiceParkDefault')], preset='SwedenWeekendShort',
                                results=[entry('SwedenS1VarmlandFullForward', [run('Ford_EscortMk2', [100.0, 200.0], 0)], T0)]))
        stage = F('SwedenS1VarmlandFullForward')
        b[b.find(stage) + len(stage) + rw.W_ACCEL] = rw.ACCEL_MAX       # the calendar's stage (before the selection)
        w = rw.read_weekend(bytes(b))
        self.assertEqual((w['preset'], w['stages'][0]['accel']), ('SwedenWeekendShort', rw.ACCEL_MAX))
        self.assertEqual(rw.results(bytes(b))[0]['runs'][0]['car'], 'Ford_EscortMk2')
        daily = rw.apply_weekend(bytes(b), 'GreeceS4LoutrakiCut2Reverse', 'HyundaiI20NRally2', 57600, 'WT_CLEAR')
        self.assertEqual(rw.read_weekend(daily)['stages'][0]['accel'], 0)

    def test_more_rally_weekend_set_ups_in_the_save_game_07(self):
        """The game's 0.7 (19 Nov 2026) can keep more than one Rally Weekend set-up in the save (its Challenges, entries
        of the per-mode map under names of their own; a copy in the rally in progress). 0.1.6 then said "no Rally
        Weekend set-up in the save" and DRIVE stopped. The player's own is the one in DefaultRally's settings: read,
        written, parked and put back there, the others left as they are."""
        for kw in ({'before': ['ChallengeGreece01'], 'after': ['DefaultChallenge']},
                   {'before': ['DefaultRallyChallenge', 'Fixed_Challenge.07']},
                   {'after': ['Challenge_Seasonal_1'], 'single': False}):
            b = fake_save(THREE_DAYS, **kw)
            names = [m[0] for m in saveslot.modes(b)]
            self.assertIn('DefaultRally', names)
            self.assertEqual(len(names), len(kw.get('before', ())) + len(kw.get('after', ())) + 1 + kw.get('single', 1))
            self.assertEqual(rw.read_weekend(b)['preset'], 'WalesWeekendLong')
            self.assertIsNone(rw.progress(b))
            new = rw.apply_weekend(b, 'GreeceS4LoutrakiCut2Reverse', 'HyundaiI20NRally2', 57600, 'WT_CLEAR')
            w = rw.read_weekend(new)
            self.assertEqual((w['preset'], [s['stage'] for s in w['stages']]),
                             ('GreeceWeekendShort', ['GreeceS4LoutrakiCut2Reverse']))
            self.assertEqual([m[0] for m in saveslot.modes(new)], names)
            for n in kw.get('before', []) + kw.get('after', []):       # the others: as they were
                (o,) = [m for m in saveslot.modes(b) if m[0] == n]
                (p,) = [m for m in saveslot.modes(new) if m[0] == n]
                self.assertEqual(b[o[1]:o[3]], new[p[1]:p[3]])
            self.assertEqual(saveslot.read_setup(new)['car'][1], b'HyundaiI20NRally2')
        # a rally in progress with a copy of its set-up in it, and a Challenge beside it
        busy = fake_save(THREE_DAYS, done=2, state_copy=True, after=['ChallengeAlsace02'])
        self.assertEqual(rw.progress(busy)['done'], 2)
        with self.assertRaises(saveslot.SaveError):
            rw.apply_weekend(busy, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_CLEAR')
        parked, value = rw.park(busy)
        self.assertIsNone(rw.progress(parked))
        daily = rw.apply_weekend(parked, 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_CLEAR')
        self.assertEqual(rw.read_weekend(daily)['stages'][0]['stage'], 'AlsaceS4SaverneShort1Forward')
        back = rw.unpark(daily, value)
        self.assertEqual(rw.progress(back)['done'], 2)
        # only a Challenge's set-up (never started a Rally Weekend of their own): the game's default ones are added
        only = fake_save(THREE_DAYS, rally=False, before=['ChallengeGreece01'])
        self.assertFalse(rw.has_weekend(only))
        self.assertIsNone(rw.progress(only))
        new = rw.apply_weekend(only, 'MonteCarloS1BolleneFullReverse', 'CitroenXsaraWRC', 57600, 'WT_CLEAR')
        self.assertEqual([m[0] for m in saveslot.modes(new)],
                         ['ChallengeGreece01', 'DefaultOnlineSingleStage', 'DefaultRally'])
        self.assertEqual(rw.read_weekend(new)['preset'], 'MontecarloWeekendShort')

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
