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
        self.assertIsNone(se.wrcg_dir([steam]))
        wrcg = os.path.join(lib, 'steamapps', 'common', se.WRCG_DIR)
        os.makedirs(wrcg)
        self.assertEqual(se.wrcg_dir([steam]), wrcg)

    def test_the_environment(self):
        tool = make_tool(self.tmp)
        with mock.patch.object(se, 'wrcg_dir', return_value='/games/WRCG'):
            env = se.environment(tool, search=False)
        self.assertEqual(env, {'wrcg': '/games/WRCG', 'tool': tool, 'ready': False, 'pack': []})
        with mock.patch.object(se, 'wrcg_dir', return_value=None):
            self.assertIsNone(se.environment(os.path.join(self.tmp, 'x'), search=False)['tool'])


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

    def test_room_for_it(self):
        with mock.patch.object(se.shutil, 'disk_usage', return_value=mock.Mock(free=5 << 30)):
            self.assertEqual(se.space_short(self.tmp), se.NEED_FREE - (5 << 30))
        with mock.patch.object(se.shutil, 'disk_usage', return_value=mock.Mock(free=500 << 30)):
            self.assertEqual(se.space_short(self.tmp), 0)


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
        self.assertEqual(st(ready, {'x.utoc': ['wrcgesss1full']}), 'installed')
        self.assertEqual(st({'wrcg': None, 'tool': '/t'}), 'nowrcg')
        self.assertEqual(st({'wrcg': '/w', 'tool': None}), 'notool')
        self.assertEqual(st({'wrcg': None, 'tool': None}, {'x.utoc': ['WrcgEsSS1Full']}), 'installed')   # (in: in)
        self.assertEqual(st(None), 'install')                                           # (not looked at yet)
        self.assertEqual(st(ready, game=None), 'nogame')
        self.assertIsNone(community.manifest(self.IT))


if __name__ == '__main__':
    unittest.main()
