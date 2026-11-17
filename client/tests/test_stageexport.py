"""WRC Generations' stages made on this PC (stageexport.py): the two games and Sando's tool found, Stage Exporter fetched
(every file checked) and put into the tool, its setup and its runs (export / remove) started and read for the progress,
a run stopped (the game's pack put back), an app opened again picking up a run still going. Stage Exporter's worker is
faked by a script of the test's own (the same lines it prints, its pack.json written)."""
import hashlib
import io
import json
import os
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import community, settings, stageexport as se  # noqa: E402

FAKE_WORKER = textwrap.dedent('''
    import json, os, sys, time
    args = sys.argv[1:]
    try:
        cfg = json.load(open('fake.json'))
    except OSError:
        cfg = {}

    def pack(change):
        p = os.path.join('custom', 'pack.json')
        try:
            stages = json.load(open(p)).get('stages', [])
        except OSError:
            stages = []
        json.dump({'stages': change(stages)}, open(p, 'w'))

    if args[:2] == ['-m', 'wr_setup']:
        print('Stage Exporter: preparando las mejoras')
        print('1/3 Juegos')
        open(os.path.join('custom', 'setup.ran'), 'w').write(open(os.path.join('custom', 'installs.json')).read())
        sys.exit(cfg.get('setup_rc', 0))
    slug = args[3]
    if args[:3] == ['-m', 'wr', 'export']:
        for line in ['WRCG files: C:/games/wrcg', '[%s] WRCG export' % slug, '[%s] tools.wrcg.terrain export' % slug,
                     '[%s] WRCG export done' % slug, 'building the ACR pack', 'building %s (1/1)' % slug,
                     '    [WrcgEsSS1] step road layers + terrain tiles: 12.0 s', '[%s] built in 30 s' % slug,
                     'locations: WrcgSpain', 'tools.acrmod.install install wrcg_stages',
                     'pack: %s (%s exported again) in 1.0 min' % (slug, slug)]:
            print(line, flush=True)
            time.sleep(cfg.get('sleep', 0))
        if cfg.get('export_rc'):
            for l in cfg.get('export_lines') or []:
                print(l, flush=True)
            print('ERROR: stage build failed', flush=True)
            sys.exit(cfg['export_rc'])
        pack(lambda s: s + [slug] if slug not in s else s)
    elif args[:3] == ['-m', 'wr', 'remove']:
        pack(lambda s: [x for x in s if x != slug])
        print('pack: (none exported again) in 0.5 min')
''')


def make_tool(root, name='Sando Tool', exe=True):
    tool = os.path.join(root, name)
    os.makedirs(os.path.join(tool, '_internal'))
    os.makedirs(os.path.join(tool, 'custom'))
    open(os.path.join(tool, se.WORKER), 'wb').close()
    if exe:
        open(os.path.join(tool, se.TOOL_EXE), 'wb').close()
    with open(os.path.join(tool, 'fake_worker.py'), 'w') as f:
        f.write(FAKE_WORKER)
    return tool


def fake(tool, **cfg):
    with open(os.path.join(tool, 'fake.json'), 'w') as f:
        json.dump(cfg, f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for p in (mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'app')),
                  mock.patch.object(se, '_command', lambda tool: [sys.executable, '-I', os.path.join(tool, 'fake_worker.py')]),
                  mock.patch.object(se, 'running', return_value=False)):
            p.start()
            self.addCleanup(p.stop)


class Finding(Base):
    def test_the_tool_from_the_folder_picked(self):
        tool = make_tool(self.tmp)
        self.assertEqual(se.tool_of(tool), tool)
        self.assertEqual(se.tool_of(os.path.join(tool, '_internal')), tool)        # (its _internal picked)
        self.assertEqual(se.tool_of(self.tmp), tool)                                 # (the folder it was unpacked into)
        make_tool(self.tmp, 'Another')
        self.assertIsNone(se.tool_of(self.tmp))                                      # (two in it: which?)
        self.assertIsNone(se.tool_of(os.path.join(self.tmp, 'nowhere')))
        self.assertIsNone(se.tool_of(''))

    def test_found_in_the_usual_places_the_saved_one_first(self):
        downloads = os.path.join(self.tmp, 'Downloads')
        bare = make_tool(os.path.join(downloads, 'a', 'b'), 'just its worker', exe=False)
        full = make_tool(os.path.join(downloads, 'c'), 'Sando-Rally-Stage-Export-Tool-0.3.7')
        places = [(downloads, 3)]
        self.assertEqual(se.find_tool(None, places), full)                          # (its .exe beside it: that one)
        self.assertEqual(se.find_tool(bare, places), bare)                          # (the folder kept: as it is)
        os.remove(os.path.join(full, se.WORKER))
        self.assertEqual(se.find_tool(None, places), bare)
        self.assertIsNone(se.find_tool(None, [(downloads, 1)]))                     # (deeper than it looks)
        self.assertIsNone(se.find_tool(None, places, budget=1))

    def test_wrc_generations_in_a_steam_library(self):
        steam, lib = os.path.join(self.tmp, 'Steam'), os.path.join(self.tmp, 'D', 'SteamLibrary')
        os.makedirs(os.path.join(steam, 'steamapps'))
        with open(os.path.join(steam, 'steamapps', 'libraryfolders.vdf'), 'w') as f:
            f.write('"libraryfolders"\n{\n "1"\n {\n  "path"  "%s"\n }\n}\n' % lib.replace('\\', '\\\\'))
        no_epic = os.path.join(self.tmp, 'ProgramData')               # (not this PC's own Epic Games launcher)
        self.assertIsNone(se.wrcg_dir([steam], no_epic))
        wrcg = os.path.join(lib, 'steamapps', 'common', se.WRCG_DIR)
        os.makedirs(wrcg)
        self.assertEqual(se.wrcg_dir([steam], no_epic), wrcg)

    def test_the_environment(self):
        tool = make_tool(self.tmp)
        with mock.patch.object(se, 'wrcg_dir', return_value='/games/WRCG'), \
                mock.patch.object(se, 'find_tool_zip', return_value='/downloads/tool.zip') as zips:
            env = se.environment(tool, search=False)
            self.assertEqual(env, {'wrcg': '/games/WRCG', 'tool': tool, 'toolZip': None, 'ready': False, 'pack': [],
                                   'failed': {}})
            zips.assert_not_called()                                                  # (the tool there: no zip looked for)
            env = se.environment(os.path.join(self.tmp, 'x'), search=False)
        self.assertEqual((env['tool'], env['toolZip']), (None, '/downloads/tool.zip'))

    def test_the_zip_it_came_in_where_downloads_go(self):
        downloads = os.path.join(self.tmp, 'Downloads')
        os.makedirs(os.path.join(downloads, 'rally'))
        old = tool_zip(os.path.join(downloads, 'Sando-Rally-Stage-Export-Tool-0.3.7.zip'),
                       ['Sando-Rally-Stage-Export-Tool/_internal/wrcg2acr-worker.exe'])
        os.utime(old, (1000, 1000))
        new = tool_zip(os.path.join(downloads, 'rally', 'Sando-Rally-Stage-Export-Tool-0.3.7 (1).zip'),
                       ['Sando-Rally-Stage-Export-Tool/_internal/wrcg2acr-worker.exe'])
        tool_zip(os.path.join(downloads, 'Sando-Rally-Stage-Export-Tool-fake.zip'), ['readme.txt'])
        tool_zip(os.path.join(downloads, 'holiday photos.zip'), ['_internal/wrcg2acr-worker.exe'])   # (not its name)
        places = [(downloads, 2)]
        self.assertEqual(se.find_tool_zip(places), new)                              # (the newest that has it)
        self.assertEqual(se.find_tool_zip([(downloads, 1)]), old)                     # (its folders not looked in)
        os.remove(new)
        self.assertEqual(se.find_tool_zip(places), old)
        self.assertIsNone(se.find_tool_zip([(os.path.join(self.tmp, 'nowhere'), 2)]))
        self.assertFalse(se.zip_has_tool(os.path.join(downloads, 'Sando-Rally-Stage-Export-Tool-fake.zip')))


def archive(files, top='Stage-Exporter-' + 'a' * 40):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(top + '/', '')
        for path, data in files.items():
            z.writestr('%s/%s' % (top, path), data)
    return buf.getvalue()


PAYLOAD = {'payload/_internal/wr.py': b'print("wr")\n', 'payload/_internal/wr_setup.py': b'# setup\n',
           'payload/custom/data/allowed_stages.json': b'{"stages": []}\n'}
EX = {'id': 'stage-exporter', 'name': 'Stage Exporter', 'version': '1.0.0', 'commit': 'a' * 40, 'files': 3,
      'url': 'https://codeload.github.com/Faviogames/Stage-Exporter/zip/' + 'a' * 40,
      'payloadSha256': se.payload_digest(PAYLOAD), 'minutes': 40}


class TheAddon(Base):
    def got(self, data):
        return mock.patch.object(se.urllib.request, 'urlopen', return_value=io.BytesIO(data))

    def test_the_digest_is_the_catalogues_recipe(self):
        lines = ''.join('%s\t%s\n' % (p, hashlib.sha256(PAYLOAD[p]).hexdigest()) for p in sorted(PAYLOAD))
        self.assertEqual(se.payload_digest(PAYLOAD), hashlib.sha256(lines.encode()).hexdigest())

    def test_fetched_and_every_file_checked(self):
        with self.got(archive(dict(PAYLOAD, **{'README.md': b'# readme', 'INSTALAR.bat': b'@echo off'}))) as get:
            self.assertEqual(se.fetch_addon(EX), PAYLOAD)                              # (only payload/)
        self.assertEqual(get.call_args.args[0].full_url, EX['url'])
        changed = dict(PAYLOAD, **{'payload/_internal/wr.py': b'print("something else")\n'})
        with self.got(archive(changed)), self.assertRaises(se.ExportError) as e:
            se.fetch_addon(EX)
        self.assertEqual(e.exception.kind, 'checksum')
        extra = dict(PAYLOAD, **{'payload/_internal/extra.py': b'x'})
        with self.got(archive(extra)), self.assertRaises(se.ExportError):
            se.fetch_addon(EX)
        with self.assertRaises(se.ExportError) as e:                                 # (anything but a commit's archive)
            se.fetch_addon(dict(EX, url='https://example.com/Stage-Exporter.zip'))
        self.assertEqual(e.exception.kind, 'checksum')
        with mock.patch.object(se.urllib.request, 'urlopen', side_effect=OSError('offline')), \
                self.assertRaises(se.ExportError) as e:
            se.fetch_addon(EX)
        self.assertEqual(e.exception.kind, 'download')
        self.assertEqual(os.listdir(os.path.join(settings.DIR, 'community')), [])   # (nothing left behind)

    def test_put_into_the_tool_and_set_up_once(self):
        tool = make_tool(self.tmp)
        said = []
        with self.got(archive(PAYLOAD)):
            self.assertTrue(se.ensure_addon(tool, EX, '/games/ACR', 'C:\\games\\WRCG', say=said.append))
        self.assertEqual(said, ['get', 'setup'])
        with open(os.path.join(tool, '_internal', 'wr.py'), 'rb') as f:
            self.assertEqual(f.read(), PAYLOAD['payload/_internal/wr.py'])
        self.assertTrue(os.path.isfile(os.path.join(tool, 'custom', 'data', 'allowed_stages.json')))
        with open(os.path.join(tool, 'custom', 'setup.ran'), encoding='utf-8') as f:
            # (the games' folders written before its setup: it asks for none)
            self.assertEqual(json.load(f), {'wrcg': 'C:/games/WRCG', 'acr': '/games/ACR'})
        self.assertTrue(se.addon_ready(tool, EX))
        self.assertTrue(se.environment(tool, search=False)['ready'])
        with mock.patch.object(se, 'fetch_addon') as again:
            self.assertFalse(se.ensure_addon(tool, EX, '/games/ACR', '/games/WRCG'))  # (in already: nothing done)
        again.assert_not_called()
        self.assertFalse(se.addon_ready(tool, dict(EX, payloadSha256='b' * 64)))     # (a newer one: put in again)

    def test_a_setup_that_fails_is_said(self):
        tool = make_tool(self.tmp)
        fake(tool, setup_rc=2)
        with self.assertRaises(se.ExportError) as e:
            se.install_addon(tool, EX, PAYLOAD, '/games/ACR', '/games/WRCG')
        self.assertEqual(e.exception.kind, 'setup')
        self.assertFalse(se.addon_ready(tool, EX))


class Runs(Base):
    def test_export_read_for_its_progress_its_log_kept(self):
        tool = make_tool(self.tmp)
        prog, lines = se.Progress('es_ss1'), []
        steps = []

        def line(text):
            lines.append(text)
            prog.feed(text)
            steps.append((prog.phase, round(prog.fraction(), 3)))
        job = se.start(tool, ['export', 'es_ss1'], line)
        self.assertTrue(os.path.isfile(os.path.join(settings.DIR, se.RUN)))         # (a run going on: written down)
        self.assertTrue(job.wait(poll=0.02))
        self.assertEqual(se.pack(tool), ['es_ss1'])
        self.assertEqual(lines[0], 'wr export es_ss1')
        self.assertIn('pack: es_ss1 (es_ss1 exported again) in 1.0 min', lines)
        fractions = [f for _p, f in steps]
        self.assertEqual(fractions, sorted(fractions))                               # (never backwards)
        self.assertEqual(prog.fraction(), 1.0)
        self.assertEqual([p for p, _f in steps][-1], 'pack')
        self.assertIn('wrcg', [p for p, _f in steps])
        self.assertIn('build', [p for p, _f in steps])
        with open(job.log, encoding='utf-8') as f:
            self.assertIn('building es_ss1 (1/1)', f.read())
        self.assertFalse(os.path.isfile(os.path.join(settings.DIR, se.RUN)))        # (it ended: forgotten)
        job = se.start(tool, ['remove', 'es_ss1'])
        self.assertTrue(job.wait(poll=0.02))
        self.assertEqual(se.pack(tool), [])

    def test_a_failed_export_says_its_last_lines(self):
        tool = make_tool(self.tmp)
        fake(tool, export_rc=1)
        job = se.start(tool, ['export', 'gr_ss3'])
        self.assertFalse(job.wait(poll=0.02))
        self.assertEqual(job.last(1), ['ERROR: stage build failed'])
        self.assertEqual(se.pack(tool), [])

    def test_a_stage_the_tool_cant_convert_is_remembered(self):
        """ZonneBeke (BE_YPRES/ES1, 2026-11-17): a road piece turned in its level, which the tool doesn't handle: said
        so, and remembered for the Stage Exporter in the tool (another one is let try again)."""
        tool = make_tool(self.tmp)
        with open(os.path.join(tool, 'custom', se.STATE), 'w') as f:
            json.dump({'payload': 'p1'}, f)
        fake(tool, export_rc=1, export_lines=[
            '[be_es1] ValueError: node BE_SS1_BoucleVille_Road_0 has a non-identity rotation/scale (0.0, 0.0, 8.83) '
            '(1.0, 1.0, 1.0); not handled', 'Traceback (most recent call last):'] + ['  File "x.py", line %d' % i for i in range(60)])
        job = se.start(tool, ['export', 'be_es1'])
        self.assertFalse(job.wait(poll=0.02))
        why = se.cant_make_in(se.log_lines(job.log))                 # (read from the whole log: far above its last lines)
        self.assertEqual(why, {'kind': 'turned', 'part': 'BE_SS1_BoucleVille_Road_0'})
        self.assertIsNone(se.cant_make_in(['ERROR: stage build failed']))
        se.note_failed(tool, 'be_es1', why)
        self.assertEqual(set(se.failed(tool)), {'be_es1'})
        self.assertEqual(se.environment(tool, search=False, wrcg=self.tmp)['failed']['be_es1']['part'], 'BE_SS1_BoucleVille_Road_0')
        with open(os.path.join(tool, 'custom', se.STATE), 'w') as f:
            json.dump({'payload': 'p2'}, f)                          # (another Stage Exporter: tried again)
        self.assertEqual(se.failed(tool), {})
        se.forget_failed('be_es1')
        self.assertNotIn('be_es1', settings.load().get(se.FAILED_SETTING) or {})

    def test_stopped_halfway(self):
        tool = make_tool(self.tmp)
        fake(tool, sleep=2)
        job = se.start(tool, ['export', 'es_ss1'])
        out = []
        t = threading.Thread(target=lambda: out.append(job.wait(poll=0.02)))
        t.start()
        time.sleep(0.3)
        job.cancel()
        t.join(10)
        self.assertEqual(out, [False])
        self.assertTrue(job.cancelled)
        self.assertEqual(se.pack(tool), [])

    def test_never_two_at_once(self):
        tool = make_tool(self.tmp)
        with mock.patch.object(se, 'running', return_value=True), self.assertRaises(se.ExportError) as e:
            se.start(tool, ['export', 'es_ss1'])
        self.assertEqual(e.exception.kind, 'busy')

    def test_an_app_opened_again_picks_up_the_run(self):
        logs = os.path.join(settings.DIR, 'logs')
        os.makedirs(logs)
        log = os.path.join(logs, 'stage-export-1.log')
        with open(log, 'w', encoding='utf-8') as f:
            f.write('wr export es_ss1\nbuilding es_ss1 (1/1)\npack: es_ss1 (es_ss1 exported again) in 40 min\n')
        se._write_run({'args': ['export', 'es_ss1'], 'log': log, 'pid': 4321})
        with mock.patch.object(se, 'running', return_value=True):
            run = se.current_run()
        self.assertEqual(run['args'], ['export', 'es_ss1'])
        seen = []
        job = se.Job(attach=run, on_line=seen.append)
        self.assertTrue(job.wait(poll=0.01))                                         # (not running any more: its log says)
        self.assertIn('building es_ss1 (1/1)', seen)
        self.assertIsNone(se.current_run())
        se._write_run({'args': ['export', 'es_ss1'], 'log': log, 'pid': 4321})
        self.assertIsNone(se.current_run())                                          # (it ended meanwhile: forgotten)
        self.assertFalse(os.path.isfile(os.path.join(settings.DIR, se.RUN)))

    def test_the_pack_set_aside_goes_back(self):
        paks = os.path.join(self.tmp, 'ACR', 'acr', 'Content', 'Paks')
        os.makedirs(paks)
        for n in ('wr_previous_pakchunk99-wrcg_stages_P.utoc.bak', 'wr_previous_pakchunk99-wrcg_stages_P.ucas.bak',
                  'pakchunk0-Windows.utoc'):
            open(os.path.join(paks, n), 'wb').close()
        self.assertEqual(sorted(se.restore_aside(os.path.join(self.tmp, 'ACR'))),
                         ['pakchunk99-wrcg_stages_P.ucas', 'pakchunk99-wrcg_stages_P.utoc'])
        self.assertEqual(sorted(os.listdir(paks)), ['pakchunk0-Windows.utoc', 'pakchunk99-wrcg_stages_P.ucas',
                                                    'pakchunk99-wrcg_stages_P.utoc'])
        mods = os.path.join(paks, '~mods')                                         # (1.5: its pack in ~mods)
        os.makedirs(mods)
        open(os.path.join(mods, 'wr_previous_pakchunk99-WrcgStages_P.pak.bak'), 'wb').close()
        self.assertEqual(se.restore_aside(os.path.join(self.tmp, 'ACR')), ['pakchunk99-WrcgStages_P.pak'])
        self.assertEqual(os.listdir(mods), ['pakchunk99-WrcgStages_P.pak'])

    def test_room_looked_at_as_it_runs_not_asked_for_ahead(self):
        tool = make_tool(self.tmp)
        with mock.patch.object(se.shutil, 'disk_usage', return_value=mock.Mock(free=5 << 30)):
            self.assertIsNone(se.low_space([self.tmp]))                                # (5 GB: on it goes)
        with mock.patch.object(se.shutil, 'disk_usage', return_value=mock.Mock(free=100 << 20)), \
                self.assertRaises(se.ExportError) as e:
            se.start(tool, ['export', 'es_ss1'], watch=[tool])                        # (full already: said at once)
        self.assertEqual((e.exception.kind, e.exception.detail), ('space', tool))
        fake(tool, sleep=1)
        free = [50 << 30]
        with mock.patch.object(se, 'SPACE_EVERY', 0), \
                mock.patch.object(se.shutil, 'disk_usage', side_effect=lambda p: mock.Mock(free=free[0])):
            job = se.start(tool, ['export', 'es_ss1'], watch=[tool])
            free[0] = 200 << 20                                                         # (the drive fills up as it runs)
            self.assertFalse(job.wait(poll=0.02))
        self.assertEqual((job.no_space, job.cancelled), (tool, True))
        self.assertEqual(se.pack(tool), [])

    def test_a_full_drive_in_its_log(self):
        tool = make_tool(self.tmp)
        job = se.Job(attach={'args': ['export', 'es_ss1'], 'log': os.path.join(self.tmp, 'x.log')}, watch=['D:/tool'])
        job._line(b'OSError: [WinError 112] There is not enough space on the disk')
        self.assertEqual(job.no_space, 'D:/tool')
        with mock.patch.object(se.zipfile, 'ZipFile', side_effect=OSError(28, 'No space left on device')), \
                self.assertRaises(se.ExportError) as e:
            se.unpack_tool(os.path.join(self.tmp, 'tool.zip'))
        self.assertEqual(e.exception.kind, 'space')


class OtherStores(Base):
    """WRC Generations not from Steam: the Epic Games launcher's, or a folder the player showed."""

    def epic(self, items=(), installed=()):
        pd = os.path.join(self.tmp, 'ProgramData')
        mans = os.path.join(pd, 'Epic', 'EpicGamesLauncher', 'Data', 'Manifests')
        os.makedirs(mans, exist_ok=True)
        for i, d in enumerate(items):
            with open(os.path.join(mans, '%d.item' % i), 'w', encoding='utf-8-sig') as f:
                json.dump(d, f)
        if installed:
            dat = os.path.join(pd, 'Epic', 'UnrealEngineLauncher')
            os.makedirs(dat, exist_ok=True)
            with open(os.path.join(dat, 'LauncherInstalled.dat'), 'w', encoding='utf-8') as f:
                json.dump({'InstallationList': list(installed)}, f)
        return pd

    def test_from_the_epic_games_launcher(self):
        game = os.path.join(self.tmp, 'Epic Games', 'WRCGenerations')
        os.makedirs(game)
        fortnite = os.path.join(self.tmp, 'Epic Games', 'Fortnite')
        os.makedirs(fortnite)
        pd = self.epic([{'DisplayName': 'Fortnite', 'AppName': 'Fortnite', 'InstallLocation': fortnite},
                        {'DisplayName': 'WRC Generations – The FIA WRC Official Game', 'AppName': 'a1b2c3',
                         'InstallLocation': game}])
        self.assertEqual(se.wrcg_epic(pd), game)
        self.assertEqual(se.wrcg_dir([], pd), game)                                  # (no Steam: Epic's)
        os.rmdir(game)
        self.assertIsNone(se.wrcg_epic(pd))                                           # (listed, but not there)
        self.assertIsNone(se.wrcg_epic(os.path.join(self.tmp, 'nowhere')))

    def test_from_the_launchers_own_list(self):
        game = os.path.join(self.tmp, 'D', 'Games', 'WRCGenerations')
        os.makedirs(game)
        pd = self.epic(installed=[{'AppName': 'f00d', 'InstallLocation': game}])   # (its name: an id; its folder says)
        self.assertEqual(se.wrcg_epic(pd), game)

    def test_a_folder_that_looks_like_it(self):
        game = os.path.join(self.tmp, 'Games', 'WRC Generations')
        os.makedirs(game)
        self.assertTrue(se.looks_like_wrcg(game))                                    # (its name)
        elsewhere = os.path.join(self.tmp, 'Games', 'Rally')
        os.makedirs(elsewhere)
        self.assertFalse(se.looks_like_wrcg(elsewhere))
        open(os.path.join(elsewhere, 'WRCG.exe'), 'wb').close()
        self.assertTrue(se.looks_like_wrcg(elsewhere))                               # (a file in it)

    def test_the_folder_shown_comes_first(self):
        shown = os.path.join(self.tmp, 'Rally')
        os.makedirs(shown)
        with mock.patch.object(se, 'wrcg_dir', return_value='/steam/WRCG'):
            self.assertEqual(se.environment(None, search=False, wrcg=shown)['wrcg'], shown)
            self.assertEqual(se.environment(None, search=False, wrcg=shown + '-gone')['wrcg'], '/steam/WRCG')


def tool_zip(path, names):
    with zipfile.ZipFile(path, 'w') as z:
        for n in names:
            z.writestr(n, b'x')
    return path


class ToolZip(Base):
    """FIND TOOL with the zip Sando's tool came in: unpacked into the app's folder."""

    def test_unpacked_into_the_app(self):
        z = tool_zip(os.path.join(self.tmp, 'Sando-Rally-Stage-Export-Tool-0.3.7.zip'),
                     ['Sando-Rally-Stage-Export-Tool-0.3.7/Sando-Rally-Stage-Export-Tool.exe',
                      'Sando-Rally-Stage-Export-Tool-0.3.7/_internal/wrcg2acr-worker.exe',
                      'Sando-Rally-Stage-Export-Tool-0.3.7/_internal/base_library.zip'])
        seen = []
        tool = se.unpack_tool(z, lambda done, total: seen.append((done, total)))
        self.assertEqual(tool, os.path.join(settings.DIR, 'tools', 'Sando-Rally-Stage-Export-Tool-0.3.7',
                                            'Sando-Rally-Stage-Export-Tool-0.3.7'))
        self.assertTrue(se.is_tool(tool))
        self.assertEqual(seen[-1], (3, 3))
        flat = tool_zip(os.path.join(self.tmp, 'flat.zip'), ['_internal/wrcg2acr-worker.exe', 'Sando-Rally-Stage-Export-Tool.exe'])
        self.assertEqual(se.unpack_tool(flat), os.path.join(settings.DIR, 'tools', 'flat'))

    def test_a_zip_without_it_or_that_climbs_out(self):
        z = tool_zip(os.path.join(self.tmp, 'other.zip'), ['readme.txt'])
        with self.assertRaises(se.ExportError) as e:
            se.unpack_tool(z)
        self.assertEqual(e.exception.kind, 'notool')
        z = tool_zip(os.path.join(self.tmp, 'evil.zip'), ['_internal/wrcg2acr-worker.exe', '../../outside.txt'])
        with self.assertRaises(se.ExportError) as e:
            se.unpack_tool(z)
        self.assertEqual(e.exception.kind, 'files')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'outside.txt')))
        with open(os.path.join(self.tmp, 'broken.zip'), 'wb') as f:
            f.write(b'not a zip')
        with self.assertRaises(se.ExportError) as e:
            se.unpack_tool(os.path.join(self.tmp, 'broken.zip'))
        self.assertEqual(e.exception.kind, 'files')
        self.assertEqual(sorted(os.listdir(os.path.join(settings.DIR, 'tools'))), [])   # (nothing half there)


class FetchTool(Base):
    """Without the tool or its zip: the catalogue's copy of Sando's zip downloaded, checked against its size and SHA-256."""

    DATA = b'PK sando tool zip bytes'

    def dl(self, **k):
        return dict({'name': 'Sando-Rally-Stage-Export-Tool-0.3.7.zip', 'size': len(self.DATA),
                     'url': 'https://web.archive.org/web/20261104103223id_/https://sandorally.com/downloads/x.zip',
                     'sha256': hashlib.sha256(self.DATA).hexdigest()}, **k)

    def test_downloaded_and_checked(self):
        seen = []
        with mock.patch.object(se.urllib.request, 'urlopen', return_value=io.BytesIO(self.DATA)) as got:
            path = se.fetch_tool(self.dl(), lambda done, total: seen.append((done, total)))
        self.assertEqual(got.call_args.args[0].full_url, self.dl()['url'])
        self.assertEqual(path, os.path.join(settings.DIR, 'community', 'Sando-Rally-Stage-Export-Tool-0.3.7.zip'))
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), self.DATA)
        self.assertEqual(seen[-1], (len(self.DATA), len(self.DATA)))

    def test_another_file_or_none_is_refused_and_nothing_left(self):
        for data, dl, kind in ((b'PK something else entirely', self.dl(), 'checksum'),
                               (self.DATA, self.dl(size=len(self.DATA) + 1), 'checksum'),
                               (self.DATA, self.dl(url='http://web.archive.org/x.zip'), 'checksum'),
                               (self.DATA, self.dl(sha256=None), 'checksum')):
            with mock.patch.object(se.urllib.request, 'urlopen', return_value=io.BytesIO(data)), \
                    self.assertRaises(se.ExportError) as e:
                se.fetch_tool(dl)
            self.assertEqual(e.exception.kind, kind)
        with mock.patch.object(se.urllib.request, 'urlopen', side_effect=OSError('offline')), \
                self.assertRaises(se.ExportError) as e:
            se.fetch_tool(self.dl())
        self.assertEqual(e.exception.kind, 'download')
        self.assertEqual(os.listdir(os.path.join(settings.DIR, 'community')), [])        # (no zip, no .part)


class ChildEnvironment(unittest.TestCase):
    def test_this_apps_packaging_left_out(self):
        with mock.patch.dict(os.environ, {'_PYI_APPLICATION_HOME_DIR': 'C:/Temp/_MEI1', '_MEIPASS2': 'C:/Temp/_MEI1',
                                          'PYTHONHOME': 'x', 'TCL_LIBRARY': 'y', 'KEEP_ME': '1'}):
            env = se._env()
        for k in ('_PYI_APPLICATION_HOME_DIR', '_MEIPASS2', 'PYTHONHOME', 'TCL_LIBRARY'):
            self.assertNotIn(k, env)
        self.assertEqual((env['KEEP_ME'], env['PYINSTALLER_RESET_ENVIRONMENT'], env['PYTHONIOENCODING']), ('1', '1', 'utf-8'))


class Status(unittest.TestCase):
    IT = {'id': 'wrcg-es-ss1', 'install': 'export', 'slug': 'es_ss1', 'stages': [{'stageId': 'WrcgEsSS1Full'}]}

    def test_where_it_stands(self):
        st = lambda env, packs=None, game='/games/ACR': community.status(self.IT, None, game, packs=packs, env=env)
        ready = {'wrcg': '/w', 'tool': '/t'}
        self.assertEqual(st(ready), 'install')
        self.assertEqual(st({'wrcg': '/w', 'tool': None, 'toolZip': '/d/tool.zip'}), 'install')   # (its zip: unpacked)
        self.assertEqual(st({'wrcg': '/w', 'tool': None, 'toolZip': None, 'toolUrl': {'url': 'https://x'}}),
                         'install')                                                     # (downloaded by INSTALL)
        self.assertEqual(st(ready, {'x.utoc': ['wrcgesss1full']}), 'installed')
        self.assertEqual(st({'wrcg': None, 'tool': '/t'}), 'nowrcg')
        self.assertEqual(st({'wrcg': '/w', 'tool': None}), 'notool')
        self.assertEqual(st({'wrcg': None, 'tool': None}, {'x.utoc': ['WrcgEsSS1Full']}), 'installed')   # (in: in)
        self.assertEqual(st(dict(ready, failed={'es_ss1': {'kind': 'turned'}})), 'cantmake')
        self.assertEqual(st(dict(ready, failed={'es_ss1': {}}), {'x.utoc': ['WrcgEsSS1Full']}), 'installed')
        self.assertEqual(st(None), 'install')                                           # (not looked at yet)
        self.assertEqual(st(ready, game=None), 'nogame')
        self.assertIsNone(community.manifest(self.IT))


if __name__ == '__main__':
    unittest.main()
