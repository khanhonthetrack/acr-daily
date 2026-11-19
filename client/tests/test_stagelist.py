"""One stage list for every set of stages in the game (stagelist.py): which containers carry the game's stage tables
(their index, by package id), the order the game loads them in, the game's tables with every set's rows added (names
where a packed package keeps them), made with Sando's own tools (faked here), made again when a set changes, taken
out when it can't be or isn't needed."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import settings, stagelist as sl  # noqa: E402

TRACKS = 'Database/Main/TrackSelection/DT_Tracks'
LEVELS = 'Database/Main/Common/DT_Levels'


def table(rows, names, imports=None):
    return {'NameMap': list(names) + ['/Script/Engine'], 'NamesReferencedFromExportDataCount': len(names),
            'Imports': imports or [{'ObjectName': 'DataTable'}], 'Generations': [{'NameCount': len(names) + 1}],
            'Exports': [{'Table': {'Data': rows}}]}


def row(name, *values):
    return {'Name': name, 'Value': [{'Name': 'Location', 'Value': v} for v in values]}


def index(*tables):
    """A container's index (.utoc) holding these tables' data."""
    return b'header ' + b''.join(sl._CHUNKS[t] for t in tables) + b' tail'


class Ids(unittest.TestCase):
    def test_a_tables_package_id_is_the_games(self):
        # (as the game's own pakchunk1-Windows.utoc lists DT_Tracks: 59683ba08e4de735 0000 00 01)
        self.assertEqual(sl.package_id('/Game/Data/Database/Main/TrackSelection/DT_Tracks'), 0x35e74d8ea03b6859)
        self.assertEqual(sl._CHUNKS[TRACKS], bytes.fromhex('59683ba08e4de73500000001'))
        self.assertEqual(sl.package_id('/Game/Data/UI/Datatable/DT_LoadingScreen'), 0x6b2a005b35638a3b)

    def test_the_order_the_game_loads_them_in(self):
        self.assertEqual(sl.pak_order('pakchunk1-Windows'), 3)
        self.assertEqual(sl.pak_order('pakchunk99-WrcgStages_P'), 103)
        self.assertEqual(sl.pak_order('zz_acrxs_registry_P'), 103)
        self.assertEqual(sl.pak_order('pakchunk99-SandoRegistry_2_P'), 303)        # (Sando's list: above the plain ones)
        self.assertEqual(sl.pak_order(sl.NAME), 1003)                                 # (ours: above them all)


class Merge(unittest.TestCase):
    def test_every_sets_rows_added_to_the_games(self):
        stock = table([row('Wales', 'W')], ['Wales', 'W'])
        london = table([row('Wales', 'W'), row('AcrXsLn02r0', 'London')], ['Wales', 'W', 'AcrXsLn02r0', 'London'])
        wrcg = table([row('Wales', 'W'), row('WrcgKeSS1', 'WrcgKenya')], ['Wales', 'WrcgKeSS1', 'W', 'WrcgKenya'])
        merged, brought, clash = sl.merge(stock, [('acrdaily', london), ('wrcg', wrcg)])
        self.assertEqual([r['Name'] for r in sl._rows(merged)], ['Wales', 'AcrXsLn02r0', 'WrcgKeSS1'])
        self.assertEqual(brought, {'acrdaily': ['AcrXsLn02r0'], 'wrcg': ['WrcgKeSS1']})
        self.assertEqual(clash, [])
        # (their names among the ones the data uses: a packed package keeps only those)
        n = merged['NamesReferencedFromExportDataCount']
        self.assertEqual(merged['NameMap'][n:], ['/Script/Engine'])
        self.assertTrue({'AcrXsLn02r0', 'London', 'WrcgKeSS1', 'WrcgKenya'} <= set(merged['NameMap'][:n]))
        self.assertEqual(merged['Generations'][0]['NameCount'], len(merged['NameMap']))

    def test_a_later_copy_wins_a_row_and_a_row_two_sets_differ_on_is_named(self):
        stock = table([row('Wales', 'W')], ['Wales', 'W'])
        pack = table([row('WrcgKeSS1', 'FreePractice')], ['WrcgKeSS1', 'FreePractice'])
        ours = table([row('WrcgKeSS1', 'FreePractice', 'Rally')], ['WrcgKeSS1', 'FreePractice', 'Rally'])
        merged, brought, clash = sl.merge(copy.deepcopy(stock), [('wrcg', pack), ('wrcg', ours)])
        self.assertEqual(sl._rows(merged)[1]['Value'][1]['Value'], 'Rally')     # (the calendars' copy, loaded later)
        self.assertEqual((brought, clash), ({'wrcg': ['WrcgKeSS1']}, []))        # (one set: no clash)
        other = table([row('WrcgKeSS1', 'Elsewhere')], ['WrcgKeSS1', 'Elsewhere'])
        _m, _b, clash = sl.merge(copy.deepcopy(stock), [('wrcg', pack), ('other:x', other)])
        self.assertEqual(clash, ['WrcgKeSS1'])

    def test_imports_matter_only_to_a_row_that_refers_to_one(self):
        stock = table([], [], imports=[{'ObjectName': 'ST_Track'}])
        unknown = [{'ObjectName': 'UnknownExport'}]           # (a copy read on its own: another package's import)
        texts = table([row('AcrXsPtWeekendShort', 'Portugal')], ['AcrXsPtWeekendShort', 'Portugal'], imports=unknown)
        sl.merge(copy.deepcopy(stock), [('lousa', texts)])
        bad = table([{'Name': 'X', 'Value': [{'$type': 'UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI',
                                              'Name': 'Icon', 'Value': -1}]}], ['X'], imports=unknown)
        with self.assertRaises(sl.ListError):
            sl.merge(copy.deepcopy(stock), [('lousa', bad)])


class Built(unittest.TestCase):
    """The game with London's, Lousã's, WRC Generations' (the pack and our calendars) and Sando's lists; the tools
    faked (retoc reads and packs, UaTool turns tables into JSON and back)."""

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
        self.put(self.paks, 'global', b'global')
        self.put(self.paks, 'pakchunk0-Windows', b'no tables here')
        self.put(self.paks, 'pakchunk1-Windows', index(*sl.TABLES))
        self.sets = {'zz_acrxs_registry_P': (self.mods, [TRACKS, LEVELS], 'AcrXsLn02r0'),
                     'zz_acrxs_lousa_registry_P': (self.mods, [TRACKS], 'AcrXsPtLousa'),
                     'pakchunk99-WrcgStages_P': (self.mods, [TRACKS, LEVELS], 'WrcgKeSS1'),
                     'pakchunk99-SandoRegistry_2_P': (self.paks, [TRACKS, LEVELS], 'SandoChlBio')}
        for stem, (d, tables, _r) in self.sets.items():
            self.put(d, stem, index(*tables))
        self.put(self.mods, 'zz_acrxs_s_acrxsln02r0_P', b'a stage: DT_PacenoteAcrXsLn02r0')   # (no tables: not a list)
        self.tool = os.path.join(self.tmp, 'tool')
        for rel in ('bin/retoc/retoc.exe', 'bin/uatool/UaTool.exe', 'bin/acr_stage.usmap'):
            os.makedirs(os.path.dirname(os.path.join(self.tool, rel)), exist_ok=True)
            open(os.path.join(self.tool, rel), 'wb').close()
        self.work = os.path.join(self.tmp, 'drive', 'ACRDaily-build', 'stagelist')
        p = mock.patch.object(sl, 'work_dir', lambda g: self.work)
        p.start()
        self.addCleanup(p.stop)
        self.written, self.read = {}, []
        p = mock.patch('acr_daily.community.game_build', return_value='25170642')
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def put(d, stem, utoc):
        with open(os.path.join(d, stem + '.utoc'), 'wb') as f:
            f.write(utoc)
        for x in ('ucas', 'pak'):
            with open(os.path.join(d, stem + '.' + x), 'wb') as f:
                f.write(stem.encode())

    def fake(self, args, what):
        if args[1] == 'to-legacy':
            src, out = args[-2], args[-1]
            stems = [n[:-len('.utoc')] for n in os.listdir(src) if n.endswith('.utoc') and not n.startswith('global')]
            assert all(not s.startswith(sl.NAME) for s in stems)                 # (never our own list as a set's)
            have = set()
            for s in stems:
                with open(os.path.join(src, s + '.utoc'), 'rb') as f:
                    data = f.read()
                have |= {t for t in sl.TABLES if sl._CHUNKS[t] in data}
            for t in have:
                if t.rsplit('/', 1)[-1] in args[args.index('--filter') + 1] or (
                        args[args.index('--filter') + 1] == 'Database/Main/' and t.startswith('Database/Main/')):
                    p = os.path.join(out, 'acr', 'Content', 'Data', *t.split('/')) + '.uasset'
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    with open(p, 'w', encoding='utf-8') as f:
                        f.write(','.join(stems))
        elif args[1] == 'dumpjson':
            with open(args[2], encoding='utf-8') as f:
                stems = f.read().split(',')
            name = os.path.basename(args[2])[:-len('.uasset')]
            self.read.append((stems, name))
            rows = [row('Wales', 'W')]
            names = ['Wales', 'W']
            if stems != ['pakchunk1-Windows']:
                r = self.sets[stems[0]][2]
                rows.append(row(r, r + 'Location'))
                names += [r, r + 'Location']
            with open(args[-1], 'w', encoding='utf-8') as f:
                json.dump(table(rows, names), f)
        elif args[1] == 'fromjson':
            with open(args[2], encoding='utf-8') as f:
                self.written[os.path.basename(args[-1])] = json.load(f)
            open(args[-1], 'wb').close()
        elif args[1] == 'to-zen':
            for x in sl.EXTS:
                with open(args[-1][:-len('utoc')] + x, 'wb') as f:
                    f.write(b'list ' + x.encode())

    def test_the_sets_lists_and_the_order_the_game_loads_them(self):
        found = sl.carriers(self.game)
        self.assertEqual([os.path.basename(s) for s, _t in found],
                         ['pakchunk99-WrcgStages_P', 'zz_acrxs_lousa_registry_P', 'zz_acrxs_registry_P',
                          'pakchunk99-SandoRegistry_2_P'])
        self.assertEqual(sl.sets(self.game, found), ['wrcg', 'lousa', 'acrdaily', 'sando'])
        self.assertTrue(sl.needed(self.game, found))

    def test_one_list_with_every_sets_rows_made_again_when_a_set_changes(self):
        self.assertEqual(sl.build(self.game, self.tool, run=self.fake),
                         {'wrcg': 2, 'lousa': 1, 'acrdaily': 2, 'sando': 2})
        self.assertTrue(all(os.path.isfile(os.path.join(self.mods, sl.NAME + '.' + x)) for x in sl.EXTS))
        tracks = self.written['DT_Tracks.uasset']
        # ACR Extra Stages' rows first (London, Lousã: after Stage Exporter's their Rally Weekends had no tyres and the
        # game crashed), then the others in the game's own order
        self.assertEqual([r['Name'] for r in sl._rows(tracks)],
                         ['Wales', 'AcrXsLn02r0', 'AcrXsPtLousa', 'WrcgKeSS1', 'SandoChlBio'])
        self.assertEqual(sorted(self.written), ['DT_Levels.uasset', 'DT_Tracks.uasset'])   # (only the tables sets carry)
        self.assertTrue(sl.present(self.game))
        self.assertFalse(sl.stale(self.game))
        self.assertFalse(os.path.exists(self.work))                                       # (its work folder: gone)
        self.assertNotIn(sl.NAME, [os.path.basename(s) for s, _t in sl.carriers(self.game)])
        with open(os.path.join(self.mods, 'zz_acrxs_lousa_registry_P.ucas'), 'ab') as f:
            f.write(b' built again')                                                     # (Lousã installed again)
        self.assertTrue(sl.stale(self.game))
        sl.build(self.game, self.tool, run=self.fake)
        self.assertFalse(sl.stale(self.game))

    def test_none_on_a_game_build_its_mappings_dont_read(self):
        sl.build(self.game, self.tool, run=self.fake)
        with mock.patch('acr_daily.community.game_build', return_value='25300000'):          # (the game updated)
            self.assertFalse(sl.needed(self.game))
            self.assertIsNone(sl.build(self.game, self.tool, run=self.fake))
        self.assertFalse(sl.present(self.game))

    def test_the_games_07_with_the_apps_own_mappings(self):
        """The game's 0.7 (build 26756580) changed the calendars' and the loading screens' tables: Sando's mappings read
        them as no table. Its own mappings are in the app (MAPPINGS\\26756580.usmap, dumped from the game by UE4SS):
        the list is made with them, and the old build still with Sando's."""
        self.assertTrue(os.path.isfile(os.path.join(sl.MAPPINGS, '26756580.usmap')))
        used = []
        with mock.patch('acr_daily.community.game_build', return_value='26756580'):
            self.assertTrue(sl.supported(self.game))
            self.assertEqual(sl.tools(self.tool, self.game)['usmap'], os.path.join(sl.MAPPINGS, '26756580.usmap'))
            sl.build(self.game, self.tool, run=lambda a, w: (used.append(a[3]) if a[1] in ('dumpjson', 'fromjson') else None,
                                                              self.fake(a, w)))
        self.assertTrue(used and all(u == os.path.join(sl.MAPPINGS, '26756580.usmap') for u in used))
        self.assertEqual(sl.tools(self.tool, self.game)['usmap'], os.path.join(self.tool, 'bin', 'acr_stage.usmap'))
        with mock.patch('acr_daily.community.game_build', return_value='26999999'):        # (a build with none: not made)
            self.assertFalse(sl.supported(self.game))
            self.assertIsNone(sl.mappings(self.game))

    def test_one_set_needs_none_and_ours_goes(self):
        sl.build(self.game, self.tool, run=self.fake)
        for stem in ('zz_acrxs_registry_P', 'zz_acrxs_lousa_registry_P', 'pakchunk99-SandoRegistry_2_P'):
            d = self.sets[stem][0]
            for x in ('utoc', 'ucas', 'pak'):
                os.rename(os.path.join(d, stem + '.' + x), os.path.join(d, stem + '.' + x + '.acrdaily-off'))
        self.assertTrue(sl.stale(self.game))                                              # (parked: not in the game)
        self.assertFalse(sl.needed(self.game))
        self.assertIsNone(sl.build(self.game, self.tool, run=self.fake))
        self.assertFalse(sl.present(self.game))

    def test_one_that_cant_be_made_leaves_none_of_ours(self):
        sl.build(self.game, self.tool, run=self.fake)

        def broken(args, what):
            if args[1] == 'fromjson':
                raise sl.ListError('build', 'writing failed')
            self.fake(args, what)
        with self.assertRaises(sl.ListError):
            sl.build(self.game, self.tool, run=broken)
        self.assertFalse(sl.present(self.game))                       # (an old list would name stages not there)
        shutil.rmtree(os.path.join(self.tool, 'bin', 'uatool'))
        with mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'none')), self.assertRaises(sl.ListError) as e:
            sl.build(self.game, self.tool, run=self.fake)
        self.assertEqual(e.exception.kind, 'tools')

    def test_sandos_tools_from_his_stage_download_when_there_is_no_export_tool(self):
        self.assertIsNone(sl.tools(None))
        b = os.path.join(settings.DIR, 'community', 'sando-chile-biobio-0.4.2', 'files', 'bin')
        for rel in ('retoc/retoc.exe', 'uatool/UaTool.exe', 'acr_stage.usmap'):
            os.makedirs(os.path.dirname(os.path.join(b, rel)), exist_ok=True)
            open(os.path.join(b, rel), 'wb').close()
        self.assertEqual(sl.tools(None)['uatool'], os.path.join(b, 'uatool', 'UaTool.exe'))
        self.assertEqual(sl.tools(self.tool)['uatool'], os.path.join(self.tool, 'bin', 'uatool', 'UaTool.exe'))


if __name__ == '__main__':
    unittest.main()
