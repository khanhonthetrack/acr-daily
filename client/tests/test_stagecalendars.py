"""Rally Weekend for WRC Generations' stages (stagecalendars.py): the pack's tracks opened to the offline Rally Weekend,
three calendars per [MOD] location, made with Sando's own tools (faked here) beside the pack, made again when it
changes, taken out when they can't be, left alone while the set is hidden."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import settings, stagecalendars as sc  # noqa: E402


def ref(table, row, name='0'):
    return {'Name': name, 'Value': [{'Name': 'Table', 'Value': table}, {'Name': 'Row', 'Value': row}]}


def text(name, key):
    return {'Name': name, 'Flags': 0, 'HistoryType': 'StringTableEntry', 'TableId': '/Game/ST_Track.ST_Track', 'Value': key}


def asset(rows, names):
    return {'NameMap': list(names), 'NamesReferencedFromExportDataCount': len(names) - 1,
            'Exports': [{'Table': {'Data': rows}}]}


def tracks():
    return asset([
        {'Name': 'WalesS4HafrenSouth', 'Value': [ref('TracksLocations', 'Wales', 'Location'),
                                                 {'Name': 'Variants', 'Value': [ref('TracksVariants', 'WelesS4HafrenSouthFullForward')]},
                                                 {'Name': 'RaceEventTypes', 'Value': []}]},
        {'Name': 'WrcgFrSS1R', 'Value': [ref('TracksLocations', 'WrcgFrance', 'Location'),
                                         {'Name': 'Variants', 'Value': [ref('TracksVariants', 'WrcgFrSS1RFull')]},
                                         {'Name': 'RaceEventTypes', 'Value': [ref('RaceEventTypes', 'FreePractice')]}]},
    ], ['Wales', 'WrcgFrance', 'WrcgFrSS1R', 'FreePractice', 'RaceEventTypes', '/Script/Engine'])


def locations():
    return asset([
        {'Name': 'Wales', 'Value': [text('Name', 'WALES'), text('HistoryAndTrivia', 'WALES_DESC')]},
        {'Name': 'WrcgFrance', 'Value': [
            {'Name': 'Name', 'Flags': 0, 'HistoryType': 'None', 'CultureInvariantString': '[MOD] France', 'Value': None},
            {'Name': 'HistoryAndTrivia', 'Flags': 0, 'HistoryType': 'None', 'Value': None,
             'CultureInvariantString': 'Stages imported from WRC Generations. Free Practice only.'}]},
    ], ['Wales', 'WrcgFrance', '/Script/Engine'])


def day(*tracks_):
    return {'Name': '0', 'Value': [ref('WeekDay', 'Sunday', 'WeekDay'), {'Name': 'Entries', 'Value': [
        {'Name': str(i), 'Value': [ref('PreRaceZoneConfigurations', 'ServiceParkDefault' if i == 0 else 'NoZone', 'PreRaceZone'),
                                   ref('TracksVariants', t, 'Track')]} for i, t in enumerate(tracks_)]}]}


def calendars():
    rows = []
    for length, days in sc.LENGTHS:
        rows.append({'Name': 'WalesWeekend' + length, 'Value': [
            text('Name', 'WEEKEND_WALES_%dDAY_NAME' % days), ref('TracksLocations', 'Wales', 'Location'),
            text('PresetDescription', 'WEEKEND_WALES_DESC'),
            {'Name': 'CalendarDays', 'Value': [day('WelesS3HafrenNorthFullForward', 'WelesS4HafrenSouthFullForward')
                                               for _ in range(days)]}]})
    return asset(rows, ['Wales', 'WalesWeekendShort', 'WalesWeekendMedium', 'WalesWeekendLong', '/Script/Engine'])


class Tables(unittest.TestCase):
    def test_tracks_opened_to_the_offline_rally_weekend(self):
        t = tracks()
        self.assertEqual(sc.open_tracks(t), {'WrcgFrance': ['WrcgFrSS1RFull']})
        rows = {r['Name']: r for r in t['Exports'][0]['Table']['Data']}
        self.assertEqual([sc._ref(e) for e in sc._prop(rows['WrcgFrSS1R'], 'RaceEventTypes')['Value']],
                         [('RaceEventTypes', 'FreePractice'), ('RaceEventTypes', 'Rally')])      # (never the online ones)
        self.assertEqual(sc._prop(rows['WalesS4HafrenSouth'], 'RaceEventTypes')['Value'], [])   # (the game's: as they are)
        # (a new name goes among the names the data uses, which a packed package keeps: the rest are lost)
        self.assertEqual(t['NameMap'].index('Rally'), 5)
        self.assertEqual(t['NamesReferencedFromExportDataCount'], 6)
        self.assertEqual(t['NameMap'][-1], '/Script/Engine')

    def test_three_calendars_a_location_each_day_on_its_stages(self):
        c, loc = calendars(), locations()
        added = sc.add_calendars(c, {'WrcgFrance': ['WrcgFrSS1RFull']}, sc.location_names(loc))
        self.assertEqual(added, ['WrcgFranceWeekendShort', 'WrcgFranceWeekendMedium', 'WrcgFranceWeekendLong'])
        rows = {r['Name']: r for r in c['Exports'][0]['Table']['Data']}
        m = rows['WrcgFranceWeekendMedium']
        self.assertEqual(sc._prop(m, 'Name')['CultureInvariantString'], 'Rally [MOD] France - 2 days')
        self.assertNotIn('TableId', sc._prop(m, 'Name'))
        self.assertEqual(sc._ref(sc._prop(m, 'Location')), ('TracksLocations', 'WrcgFrance'))
        days = sc._prop(m, 'CalendarDays')['Value']
        self.assertEqual([[sc._ref(sc._prop(e, 'Track'))[1] for e in sc._prop(d, 'Entries')['Value']] for d in days],
                         [['WrcgFrSS1RFull'], ['WrcgFrSS1RFull']])                              # (cut to its stages)
        self.assertEqual(sc._ref(sc._prop(sc._prop(days[0], 'Entries')['Value'][0], 'PreRaceZone'))[1], 'ServiceParkDefault')
        self.assertEqual(sc._ref(sc._prop(rows['WalesWeekendMedium'], 'Location')), ('TracksLocations', 'Wales'))   # (copied, not moved)
        n = c['NamesReferencedFromExportDataCount']
        self.assertTrue(all(c['NameMap'].index(k) < n for k in added + ['WrcgFrance', 'WrcgFrSS1RFull']))
        with self.assertRaises(sc.CalendarError):
            sc.add_calendars(c, {'WrcgFrance': ['WrcgFrSS1RFull']})                            # (once only)

    def test_the_mod_locations_no_longer_say_free_practice_only(self):
        loc = locations()
        sc.word_locations(loc)
        rows = {r['Name']: r for r in loc['Exports'][0]['Table']['Data']}
        self.assertEqual(sc._prop(rows['WrcgFrance'], 'HistoryAndTrivia')['CultureInvariantString'], sc.TEXT)
        self.assertEqual(sc._prop(rows['Wales'], 'HistoryAndTrivia')['Value'], 'WALES_DESC')


class Built(unittest.TestCase):
    """Made with the Stage Export Tool's own tools (faked: retoc reads and packs, UaTool turns tables into JSON and back)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'app'))
        p.start()
        self.addCleanup(p.stop)
        self.game = os.path.join(self.tmp, 'ACR')
        self.paks = os.path.join(self.game, 'acr', 'Content', 'Paks')
        self.mods = os.path.join(self.paks, '~mods')
        os.makedirs(self.mods)
        for n in ('global.utoc', 'global.ucas'):
            open(os.path.join(self.paks, n), 'wb').close()
        for x in sc.EXTS:
            with open(os.path.join(self.mods, sc.PACK + '.' + x), 'wb') as f:
                f.write(b'pack ' + x.encode())
        self.tool = os.path.join(self.tmp, 'tool')
        for rel in ('bin/retoc/retoc.exe', 'bin/uatool/UaTool.exe', 'bin/acr_stage.usmap'):
            os.makedirs(os.path.dirname(os.path.join(self.tool, rel)), exist_ok=True)
            open(os.path.join(self.tool, rel), 'wb').close()
        self.work = os.path.join(self.tmp, 'drive', 'ACRDaily-build', 'calendars')
        p = mock.patch.object(sc, 'work_dir', lambda g: self.work)
        p.start()
        self.addCleanup(p.stop)
        self.written, self.runs = {}, []

    def fake(self, args, what):
        self.runs.append((os.path.basename(args[0]), args[1]))
        if args[1] == 'to-legacy':
            assert args[-2].endswith('paks') or args[-2] == self.paks, args
            if args[-2] == self.paks:                     # (the game's own: never our calendars in its folder)
                assert not os.path.exists(os.path.join(self.mods, sc.NAME + '.utoc')) and \
                    not os.path.exists(os.path.join(self.paks, sc.NAME + '.utoc'))
            for rel in sc.TABLES.values():
                p = os.path.join(args[-1], *rel.split('/')) + '.uasset'
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, 'wb').close()
        elif args[1] == 'dumpjson':
            src = {'DT_Tracks': tracks(), 'DT_TracksLocations': locations(), 'DT_RallyWeekendCalendarPreset': calendars()}
            with open(args[-1], 'w', encoding='utf-8') as f:
                json.dump(src[os.path.basename(args[2])[:-len('.uasset')]], f)
        elif args[1] == 'fromjson':
            with open(args[2], encoding='utf-8') as f:
                self.written[os.path.basename(args[-1])] = json.load(f)
            open(args[-1], 'wb').close()
        elif args[1] == 'to-zen':
            for x in sc.EXTS:
                with open(args[-1][:-len('utoc')] + x, 'wb') as f:
                    f.write(b'calendars ' + x.encode())

    def test_made_beside_the_pack_and_made_again_when_it_changes(self):
        self.assertFalse(sc.stale(self.game))
        added = sc.build(self.game, self.tool, run=self.fake)
        self.assertEqual(added, ['WrcgFranceWeekendShort', 'WrcgFranceWeekendMedium', 'WrcgFranceWeekendLong'])
        self.assertTrue(all(os.path.isfile(os.path.join(self.mods, sc.NAME + '.' + x)) for x in sc.EXTS))
        self.assertEqual(sorted(self.written), ['DT_RallyWeekendCalendarPreset.uasset', 'DT_Tracks.uasset',
                                                'DT_TracksLocations.uasset'])
        self.assertEqual(len(self.written['DT_RallyWeekendCalendarPreset.uasset']['Exports'][0]['Table']['Data']), 6)
        self.assertEqual(sc.present(self.game), [self.mods])
        self.assertFalse(sc.stale(self.game))
        self.assertFalse(os.path.exists(self.work))                                           # (its work folder: gone)
        with open(os.path.join(self.mods, sc.PACK + '.ucas'), 'ab') as f:
            f.write(b' and a new stage')                                                       # (Stage Exporter made one)
        self.assertTrue(sc.stale(self.game))
        sc.build(self.game, self.tool, run=self.fake)                                         # (made again over its own)
        self.assertFalse(sc.stale(self.game))

    def test_one_that_cant_be_made_is_taken_out(self):
        sc.build(self.game, self.tool, run=self.fake)

        def broken(args, what):
            if args[1] == 'fromjson':
                raise sc.CalendarError('build', 'writing failed')
            self.fake(args, what)
        with self.assertRaises(sc.CalendarError):
            sc.build(self.game, self.tool, run=broken)
        self.assertEqual(sc.present(self.game), [])                       # (an old copy would hide new stages)
        shutil.rmtree(os.path.join(self.tool, 'bin', 'uatool'))
        with self.assertRaises(sc.CalendarError) as e:
            sc.build(self.game, self.tool, run=self.fake)
        self.assertEqual(e.exception.kind, 'tools')

    def test_left_alone_while_the_set_is_hidden_and_gone_with_the_pack(self):
        sc.build(self.game, self.tool, run=self.fake)
        for x in sc.EXTS:                                                  # (the stage switch hid the set)
            for n in (sc.PACK, sc.NAME):
                os.rename(os.path.join(self.mods, n + '.' + x), os.path.join(self.mods, n + '.' + x + '.acrdaily-off'))
        self.assertIsNone(sc.build(self.game, self.tool, run=self.fake))
        self.assertTrue(os.path.isfile(os.path.join(self.mods, sc.NAME + '.utoc.acrdaily-off')))
        for n in os.listdir(self.mods):
            if n.startswith(sc.PACK):
                os.remove(os.path.join(self.mods, n))                      # (its last stage taken out: no pack)
        self.assertIsNone(sc.build(self.game, self.tool, run=self.fake))
        self.assertEqual([n for n in os.listdir(self.mods) if n.startswith(sc.NAME)], [])


if __name__ == '__main__':
    unittest.main()
