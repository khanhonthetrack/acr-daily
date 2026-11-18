"""Community content (community.py): an item's package checked, put into the game's ~mods and taken out again; only on
the game build it was made for, and out again after the game is updated."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import community as cm, settings  # noqa: E402


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'appdata'))
        p.start()
        self.addCleanup(p.stop)
        lib = os.path.join(self.tmp, 'lib', 'steamapps')
        self.game = os.path.join(lib, 'common', 'Assetto Corsa Rally')
        os.makedirs(os.path.join(self.game, 'acr', 'Binaries', 'Win64'))
        self.build('25170642')
        # the package: two containers in a zip, and its manifest next to it
        self.files = {'zz_acrxs_AcrXsLn02r0_P.pak': b'pak' * 100, 'zz_acrxs_AcrXsLn02r0_P.ucas': b'ucas' * 1000,
                      'zz_acrxs_registry_P.utoc': b'utoc' * 50}
        self.rel = os.path.join(self.tmp, 'release')
        os.makedirs(self.rel)
        self.zip = os.path.join(self.rel, 'ACRDaily-London-1.zip')
        with zipfile.ZipFile(self.zip, 'w') as z:
            for n, b in self.files.items():
                z.writestr('ACRDaily-London/' + n, b)
            z.writestr('ACRDaily-London/CREDITS.txt', b'credits')
        with open(self.zip, 'rb') as f:
            zb = f.read()
        self.man = {'id': 'acrdaily-london', 'version': '1', 'acrBuild': '25170642',
                    'zip': {'name': 'ACRDaily-London-1.zip', 'size': len(zb), 'sha256': sha(zb)},
                    'files': [{'name': n, 'size': len(b), 'sha256': sha(b)} for n, b in self.files.items()]}
        self.man_path = os.path.join(self.rel, 'manifest.json')
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)
        self.item = {'id': 'acrdaily-london', 'manifest': self.man_path}
        p = mock.patch.object(cm, 'game_running', lambda: False)
        p.start()
        self.addCleanup(p.stop)

    def build(self, b):
        with open(os.path.join(self.tmp, 'lib', 'steamapps', 'appmanifest_3917090.acf'), 'w') as f:
            f.write('"AppState"\n{\n\t"appid"\t\t"3917090"\n\t"buildid"\t\t"%s"\n\t"installdir"\t\t"Assetto Corsa Rally"\n}\n' % b)

    def mods(self):
        d = cm.mods_dir(self.game)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


class TestCommunity(Base):
    def test_build_from_steam(self):
        self.assertEqual(cm.game_build(self.game), '25170642')
        self.assertIsNone(cm.game_build(os.path.join(self.tmp, 'nowhere', 'x')))

    def test_install_and_uninstall(self):
        man = cm.manifest(self.item)
        self.assertEqual(man['zipUrl'], self.zip)
        self.assertEqual(cm.status(self.item, man, self.game), 'install')
        seen = []
        path = cm.download(man, progress=lambda d, t: seen.append(d))
        self.assertTrue(seen and seen[-1] == os.path.getsize(self.zip))
        cm.install(self.game, man, path)
        self.assertEqual(self.mods(), sorted(list(self.files) + [cm.INSTALLED]))
        for n, b in self.files.items():
            with open(os.path.join(cm.mods_dir(self.game), n), 'rb') as f:
                self.assertEqual(f.read(), b)
        self.assertEqual(cm.status(self.item, man, self.game), 'installed')
        self.assertTrue(cm.requires_ok('acrdaily-london', self.game))
        self.assertEqual(sorted(cm.uninstall(self.game, 'acrdaily-london')), sorted(self.files))
        self.assertEqual(self.mods(), [])
        self.assertFalse(cm.requires_ok('acrdaily-london', self.game))

    def test_a_zip_in_parts(self):
        """A zip over GitHub's 2 GB a file: in parts next to the manifest, joined as they come."""
        with open(self.zip, 'rb') as f:
            zb = f.read()
        cut = len(zb) // 3
        parts = []
        for i, chunk in enumerate((zb[:cut], zb[cut:2 * cut], zb[2 * cut:])):
            name = 'ACRDaily-London-1.zip.%03d' % (i + 1)
            with open(os.path.join(self.rel, name), 'wb') as f:
                f.write(chunk)
            parts.append({'name': name, 'size': len(chunk), 'sha256': sha(chunk)})
        os.remove(self.zip)                              # (only the parts are up)
        self.man['zip']['parts'] = parts
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)
        man = cm.manifest(self.item)
        seen = []
        path = cm.download(man, progress=lambda d, t: seen.append((d, t)))
        self.assertEqual(seen[-1], (len(zb), len(zb)))
        cm.install(self.game, man, path)
        self.assertEqual(self.mods(), sorted(list(self.files) + [cm.INSTALLED]))
        self.assertFalse(os.path.exists(path), 'in the game now: its download is not kept')
        # a damaged part: refused, nothing kept
        with open(os.path.join(self.rel, parts[1]['name']), 'r+b') as f:
            f.write(b'X')
        with self.assertRaises(cm.CommunityError) as e:
            cm.download(man)
        self.assertEqual(e.exception.kind, 'checksum')
        self.assertFalse(os.path.exists(cm.cache_path(man)))

    def test_a_damaged_download_is_refused(self):
        man = cm.manifest(self.item)
        man['zip']['sha256'] = '0' * 64
        with self.assertRaises(cm.CommunityError) as e:
            cm.download(man)
        self.assertEqual(e.exception.kind, 'checksum')
        self.assertFalse(os.path.exists(cm.cache_path(man)))

    def test_another_build_waits_and_a_game_update_takes_it_out(self):
        man = cm.manifest(self.item)
        cm.install(self.game, man, cm.download(man))
        self.build('25200000')                          # the game updated
        self.assertEqual(cm.status(self.item, man, self.game), 'wait')
        self.assertFalse(cm.requires_ok('acrdaily-london', self.game))
        with self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(e.exception.kind, 'build')
        self.assertEqual(cm.guard(self.game), ['acrdaily-london'])   # its stale registry out of the way
        self.assertEqual(self.mods(), [])
        self.assertEqual(cm.guard(self.game), [])

    def test_the_game_running_waits(self):
        man = cm.manifest(self.item)
        with mock.patch.object(cm, 'game_running', lambda: True):
            with self.assertRaises(cm.CommunityError) as e:
                cm.install(self.game, man, cm.download(man))
            self.assertEqual(e.exception.kind, 'running')
        self.assertEqual(self.mods(), [])

    def test_the_game_started_while_unpacking_leaves_nothing_behind(self):
        """The game started while the package was unpacked: nothing changes in ~mods, and no .part is left there (the
        next install took them for other converted stages)."""
        man = cm.manifest(self.item)
        cm.install(self.game, man, cm.download(man))
        calls = iter([False, True])                      # (closed at the start, open by the swap)
        with mock.patch.object(cm, 'game_running', lambda: next(calls)):
            with self.assertRaises(cm.CommunityError) as e:
                cm.install(self.game, dict(man, version='2'), cm.download(man))
        self.assertEqual(e.exception.kind, 'running')
        self.assertEqual(self.mods(), sorted(list(self.files) + [cm.INSTALLED]))
        self.assertEqual(cm.clashes(self.game, man), [])
        self.assertEqual(cm.installed(self.game)['acrdaily-london']['version'], str(man['version']))

    def test_other_converted_stages_are_asked_about(self):
        os.makedirs(cm.mods_dir(self.game))
        with open(os.path.join(cm.mods_dir(self.game), 'zz_acrxs_registry_P.pak'), 'wb') as f:
            f.write(b'someone else\'s')
        with open(os.path.join(cm.mods_dir(self.game), 'other_mod_P.pak'), 'wb') as f:
            f.write(b'unrelated')
        man = cm.manifest(self.item)
        with self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(e.exception.kind, 'clash')
        cm.install(self.game, man, cm.download(man), force=True)
        self.assertIn('other_mod_P.pak', self.mods())          # (not ours to touch, not in the way)
        self.assertNotIn('zz_acrxs_registry_P.pak', self.mods())

    def test_a_package_missing_a_file_puts_nothing_in(self):
        man = cm.manifest(self.item)
        man['files'].append({'name': 'zz_acrxs_missing_P.pak', 'size': 1, 'sha256': '1' * 64})
        with self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(e.exception.kind, 'files')
        self.assertEqual(self.mods(), [])

    def test_an_update_that_fails_leaves_the_installed_version(self):
        """Every file is checked before anything in ~mods changes: a damaged update keeps the version there."""
        man = cm.manifest(self.item)
        cm.install(self.game, man, cm.download(man))
        before = {}
        for n in self.files:
            with open(os.path.join(cm.mods_dir(self.game), n), 'rb') as f:
                before[n] = f.read()
        bad = dict(man, version='2', files=[dict(f) for f in man['files']])
        bad['files'][-1]['sha256'] = '2' * 64                   # (its last file isn't what the zip holds)
        with self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, bad, cm.download(man))
        self.assertEqual(e.exception.kind, 'files')
        self.assertEqual(self.mods(), sorted(list(self.files) + [cm.INSTALLED]))   # (no .part left either)
        for n, b in before.items():
            with open(os.path.join(cm.mods_dir(self.game), n), 'rb') as f:
                self.assertEqual(f.read(), b)
        self.assertEqual(cm.installed(self.game)['acrdaily-london']['version'], str(man['version']))

    def test_a_manifest_naming_a_path_is_refused(self):
        import json
        with open(self.item['manifest'], encoding='utf-8') as f:
            m = json.load(f)
        for bad in ('../../x', 'a/b', '..'):
            with open(self.item['manifest'], 'w', encoding='utf-8') as f:
                json.dump(dict(m, version=bad), f)
            with self.assertRaises(cm.CommunityError) as e:
                cm.manifest(self.item)
            self.assertEqual(e.exception.kind, 'manifest', bad)

    def test_a_manifest_naming_a_folder_for_a_file_is_refused(self):
        import json
        with open(self.item['manifest'], encoding='utf-8') as f:
            m = json.load(f)
        for bad in ('..', '.', '.hidden'):
            files = [dict(x) for x in m['files']]
            files[0]['name'] = bad
            with open(self.item['manifest'], 'w', encoding='utf-8') as f:
                json.dump(dict(m, files=files), f)
            with self.assertRaises(cm.CommunityError) as e:
                cm.manifest(self.item)
            self.assertEqual(e.exception.kind, 'manifest', bad)

    def test_a_package_built_from_the_games_own_files_is_offered(self):
        """ACR DAILY London from its version 8 (13 Nov 2026): the stage's own files and deltas against the game's, put
        together on the PC ('assemble', TestBuiltHere): offered like any package; an app without it says 'newer'."""
        man = dict(cm.manifest(self.item), assemble={'format': 1, 'tool': 'tools/retoc.exe', 'containers': []})
        self.assertEqual(cm.status(self.item, man, self.game), 'install')
        with mock.patch.object(cm, 'ASSEMBLES', False):
            self.assertEqual(cm.status(self.item, man, self.game), 'newer')
        cm.install(self.game, cm.manifest(self.item), cm.download(cm.manifest(self.item)))   # (an older one installed)
        self.assertEqual(cm.status(self.item, dict(man, version='2'), self.game), 'update')

    def test_no_manifest_yet(self):
        self.assertIsNone(cm.manifest({'id': 'x'}))
        self.assertEqual(cm.status({'id': 'x'}, None, self.game), 'unavailable')
        self.assertEqual(cm.status({'id': 'x'}, None, None), 'nogame')

    def test_a_file_beside_the_manifest_on_the_web_or_on_this_pc(self):
        self.assertEqual(cm._beside('https://github.com/x/y/releases/download/t/manifest.json', 'a.zip'),
                         'https://github.com/x/y/releases/download/t/a.zip')
        self.assertEqual(cm._beside(os.path.join('C:', os.sep, 'tmp', 'release', 'manifest.json'), 'a.zip'),
                         os.path.join('C:', os.sep, 'tmp', 'release', 'a.zip'))

    def test_sizes(self):
        self.assertEqual(cm.size_text(812345678), '774.7 MB')
        self.assertEqual(cm.size_text(2048), '2 KB')


if __name__ == '__main__':
    unittest.main()


SANDO = {'id': 'sando-chile-biobio', 'install': 'manager', 'group': 'sando', 'name': 'Chile BioBio',
         'stages': [{'stageId': 'SandoChlBioFull'}, {'stageId': 'SandoChlBioRevFull'}],
         'download': {'version': '0.4.2', 'acrBuild': '25170642', 'url': 'https://dl.sandorally.com/x/Sando.zip',
                      'name': 'Sando.zip', 'size': 1, 'sha256': '0' * 64,
                      'manager': 'Sando-Rally-Original-Stage-Manager.exe'}}
WRCG = {'id': 'wrcg-stages', 'install': 'link', 'group': 'wrcg', 'name': 'WRC Generations stages',
        'stages': [{'stageId': 'WrcgEsSS1Full'}, {'stageId': 'WrcgEsSS1RFull'}, {'stageId': 'WrcgSeSS3Full'}],
        'page': 'https://github.com/Faviogames/Stage-Exporter'}
LONDON_ITEM = {'id': 'acrdaily-london', 'group': 'acrdaily', 'name': 'ACR DAILY London',
               'stages': [{'stageId': 'AcrXsLn02r0FullForward'}]}


def delta_of(base, new):
    """An ACRD1 delta: new = base[:8] + b'OURS' + base[8:] (copy, insert, copy)."""
    assert new == base[:8] + b'OURS' + base[8:]
    v = lambda n: bytes([n]) if n < 128 else bytes([n & 0x7F | 0x80, n >> 7])   # noqa: E731
    return cm.DELTA_MAGIC + b'C' + v(0) + v(8) + b'I' + v(4) + b'OURS' + b'C' + v(8) + v(len(base) - 8) + b'E'


class TestBuiltHere(Base):
    """A package holding nothing of the game's: built on this PC from the game's own packages (read with the package's
    tool, faked here), our own files and deltas, packed, checked against the manifest, then installed."""

    GAME_LEVEL = b'the game level ' * 20                 # what the tool reads out of the game

    def setUp(self):
        super().setUp()
        self.level = self.GAME_LEVEL[:8] + b'OURS' + self.GAME_LEVEL[8:]
        self.ours = b'our texture' * 30
        z = os.path.join(self.rel, 'acrdaily-london-2.zip')
        with zipfile.ZipFile(z, 'w') as zf:
            zf.writestr('acrdaily-london/tools/retoc.exe', b'tool')
            zf.writestr('acrdaily-london/own/stage/acr/Content/AcrXs/Tex/T_A.uexp', self.ours)
            zf.writestr('acrdaily-london/delta/stage/acr/Content/AcrXs/L.uexp.acrd', delta_of(self.GAME_LEVEL, self.level))
        self.packed = self.pack(self.level + self.ours)
        with open(z, 'rb') as f:
            zb = f.read()
        self.man = {'id': 'acrdaily-london', 'version': '2', 'acrBuild': '25170642',
                    'zip': {'name': 'acrdaily-london-2.zip', 'size': len(zb), 'sha256': sha(zb)},
                    'files': [{'name': n, 'size': len(b), 'sha256': sha(b)} for n, b in self.packed.items()],
                    'assemble': {'format': 1, 'tool': 'tools/retoc.exe', 'extract': ['Levels/WalesS4HafrenSouth.umap'],
                                 'bases': {'acr/Content/Levels/W.uexp': sha(self.GAME_LEVEL)},
                                 'containers': [{'name': 'zz_acrxs_s_x_P', 'root': 'stage', 'files': [
                                     {'path': 'acr/Content/AcrXs/L.uexp', 'delta': 'delta/stage/acr/Content/AcrXs/L.uexp.acrd',
                                      'base': 'acr/Content/Levels/W.uexp', 'sha256': sha(self.level)},
                                     {'path': 'acr/Content/AcrXs/Tex/T_A.uexp', 'own': 'own/stage/acr/Content/AcrXs/Tex/T_A.uexp',
                                      'sha256': sha(self.ours)}]}]}}
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)
        self.runs = []
        p = mock.patch.object(cm, '_run', side_effect=self.fake_tool)
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def pack(blob):
        return {'zz_acrxs_s_x_P.utoc': b'toc' + sha(blob).encode(), 'zz_acrxs_s_x_P.ucas': blob, 'zz_acrxs_s_x_P.pak': b'p'}

    def fake_tool(self, args, what, tick=None):
        self.runs.append(args[1])
        if tick:
            tick()                                      # (how far it is, asked as it runs)
        if args[1] == 'to-legacy':                       # the game's packages, as the game has them (its own only)
            # (a game without Paks here: no links made, Paks itself)
            assert '--filter' in args and os.path.basename(args[-2]) in (cm.OWN_PAKS, 'Paks'), args
            if os.path.basename(args[-2]) == cm.OWN_PAKS:
                assert all(cm._OWN.match(n) for n in os.listdir(args[-2])), os.listdir(args[-2])
            p = os.path.join(args[-1], 'acr', 'Content', 'Levels', 'W.uexp')
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(self.GAME_LEVEL)
        elif args[1] == 'to-zen':                        # packed: the files in a fixed order
            assert '--no-parallel' in args
            root, utoc = args[-2], args[-1]
            blob = b''
            for rel in ('acr/Content/AcrXs/L.uexp', 'acr/Content/AcrXs/Tex/T_A.uexp'):
                with open(os.path.join(root, *rel.split('/')), 'rb') as f:
                    blob += f.read()
            for n, b in self.pack(blob).items():
                with open(os.path.join(os.path.dirname(utoc), n), 'wb') as f:
                    f.write(b)

    def test_built_from_the_games_own_files(self):
        man = cm.manifest(self.item)
        said, steps = [], []
        cm.install(self.game, man, cm.download(man), say=said.append, progress=lambda s, f: steps.append((s, f)))
        self.assertEqual(self.runs, ['to-legacy', 'to-zen'])
        # how far, all along: building it here from 0 to 1 never going back, then putting it in from 0 to 1
        build = [f for s, f in steps if s == 'build']
        put = [f for s, f in steps if s == 'install']
        self.assertEqual((build[-1], put[0], put[-1]), (1.0, 0.0, 1.0))
        self.assertEqual(build, sorted(build))
        self.assertEqual(put, sorted(put))
        self.assertEqual([s for s, _f in steps], ['build'] * len(build) + ['install'] * len(put))
        self.assertEqual(self.mods(), sorted(list(self.packed) + [cm.INSTALLED]))
        with open(os.path.join(cm.mods_dir(self.game), 'zz_acrxs_s_x_P.ucas'), 'rb') as f:
            self.assertEqual(f.read(), self.level + self.ours)
        self.assertIn("Reading your game's files…", said)
        self.assertFalse(os.path.exists(cm.build_dir()))                   # (its work folder gone)
        self.assertEqual(cm.status(self.item, man, self.game), 'installed')

    def test_other_game_files_change_nothing(self):
        """The game's packages not the ones the package was made from: refused before ~mods is touched."""
        self.GAME_LEVEL = b'a modded level ' * 20
        man = cm.manifest(self.item)
        with self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(e.exception.kind, 'gamefiles')
        self.assertEqual(self.mods(), [])
        self.assertFalse(os.path.exists(cm.build_dir()))

    def test_a_package_reaching_outside_its_folder_is_refused(self):
        self.man['assemble']['containers'][0]['files'][1]['path'] = '../../evil.uexp'
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)
        man = cm.manifest(self.item)
        with self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(e.exception.kind, 'manifest')
        self.assertEqual(self.mods(), [])

    def test_an_older_version_stays_when_the_new_one_cannot_be_built(self):
        """Its version 1 installed: a build that fails leaves it in the game as it was."""
        os.makedirs(cm.mods_dir(self.game))
        with open(os.path.join(cm.mods_dir(self.game), 'zz_acrxs_s_x_P.pak'), 'wb') as f:
            f.write(b'old')
        cm._save_installed(self.game, {'acrdaily-london': {'version': '1', 'acrBuild': '25170642',
                                                           'files': ['zz_acrxs_s_x_P.pak']}})
        self.GAME_LEVEL = b'a modded level ' * 20
        man = cm.manifest(self.item)
        with self.assertRaises(cm.CommunityError):
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(self.mods(), sorted(['zz_acrxs_s_x_P.pak', cm.INSTALLED]))
        self.assertEqual(cm.installed(self.game)['acrdaily-london']['version'], '1')

    def test_the_delta(self):
        d = os.path.join(self.tmp, 'd')
        with open(d, 'wb') as f:
            f.write(delta_of(self.GAME_LEVEL, self.level))
        b = os.path.join(self.tmp, 'b')
        with open(b, 'wb') as f:
            f.write(self.GAME_LEVEL)
        cm.apply_delta(b, d, os.path.join(self.tmp, 'n'))
        with open(os.path.join(self.tmp, 'n'), 'rb') as f:
            self.assertEqual(f.read(), self.level)


FAKE_KIT = r'''
import os, sys
pkg = os.getcwd()
assert not os.path.exists(os.path.join(pkg, 'installed.json')), "its author's own state left in"
print('=== finding Assetto Corsa Rally'); print('game: ' + sys.argv[1])
print('=== stage build + offline checks (several minutes)', flush=True)
if os.environ.get('FAKE_KIT_FAIL'):
    print('FAIL  respawn walls: 0 found'); sys.exit(1)
dist = os.path.join(pkg, 'kit', 'work', 'acr', 'additive', 'dist')
reg = os.path.join(pkg, 'kit', 'work', 'acr', 'additive', 'mod-registry', 'acr', 'Content')
os.makedirs(dist); os.makedirs(reg)
open(os.path.join(reg, 'DT_TracksVariants.uasset'), 'wb').write(b'rows')
for n in ('zz_acrxs_registry_P', 'zz_acrxs_s_acrxsptlousa_P'):
    for x in ('pak', 'ucas', 'utoc'):
        open(os.path.join(dist, n + '.' + x), 'wb').write((n + x).encode())
'''


class TestKit(Base):
    """A package its author's kit builds on this PC (Hattori Rally's Lousã): the kit unpacked on the game's drive, its
    own script run to build only (faked here), its stage list packed again under the package's own name, the files put
    in like any package's, the work folder gone; London (ours, hidden by the stage switch) never in the way."""

    FILES = ['zz_acrxs_lousa_registry_P.pak', 'zz_acrxs_lousa_registry_P.ucas', 'zz_acrxs_lousa_registry_P.utoc',
             'zz_acrxs_s_acrxsptlousa_P.pak', 'zz_acrxs_s_acrxsptlousa_P.ucas', 'zz_acrxs_s_acrxsptlousa_P.utoc']

    def setUp(self):
        super().setUp()
        z = os.path.join(self.rel, 'Hattori_Rally-Lousa.zip')
        with zipfile.ZipFile(z, 'w') as zf:
            zf.writestr('Lousa-installer/install.ps1', b'# the kit')
            zf.writestr('Lousa-installer/installed.json', b'{"game": "c:\\\\author\\\\pc"}')   # (its author's)
            zf.writestr('Lousa-installer/kit/work/bin/bin/retoc.exe', b'tool')
        with open(z, 'rb') as f:
            zb = f.read()
        self.man = {'id': 'hattori-lousa', 'version': '1',
                    'zip': {'name': 'Hattori_Rally-Lousa.zip', 'size': len(zb), 'sha256': sha(zb)},
                    'kit': {'format': 1, 'script': 'Lousa-installer/install.ps1', 'dist': 'kit/work/acr/additive/dist',
                            'registry': {'from': 'kit/work/acr/additive/mod-registry', 'name': 'zz_acrxs_lousa_registry_P',
                                         'tool': 'kit/work/bin/bin/retoc.exe'}},
                    'files': [{'name': n} for n in self.FILES]}
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)
        self.item = {'id': 'hattori-lousa', 'manifest': self.man_path}
        script = os.path.join(self.tmp, 'fake_kit.py')
        with open(script, 'w') as f:
            f.write(FAKE_KIT)
        self.work = os.path.join(self.tmp, 'drive', cm.KIT_DIR, 'hattori-lousa')
        self.runs = []
        for p in (mock.patch.object(cm, '_kit_command', lambda s, g: [sys.executable, script, g]),
                  mock.patch.object(cm, 'kit_dir', lambda g, m: self.work),
                  mock.patch.object(cm, '_run', side_effect=self.fake_retoc)):
            p.start()
            self.addCleanup(p.stop)
        # London in the game, hidden by the stage switch (its files renamed): ours, never in the way
        os.makedirs(cm.mods_dir(self.game))
        # the game's own containers, and Sando's stage list beside them in Paks (never read as the game's)
        for n in ('global.utoc', 'pakchunk1-Windows.utoc', 'pakchunk99-SandoRegistry_2_P.utoc'):
            with open(os.path.join(os.path.dirname(cm.mods_dir(self.game)), n), 'wb') as f:
                f.write(n.encode())
        for n in ('zz_acrxs_registry_P.utoc', 'zz_acrxs_s_acrxsln02r0_P.utoc'):
            with open(os.path.join(cm.mods_dir(self.game), n + '.acrdaily-off'), 'wb') as f:
                f.write(b'london')
        cm._save_installed(self.game, {'acrdaily-london': {'version': '9', 'acrBuild': '25170642', 'at': 1,
                                                           'files': ['zz_acrxs_registry_P.utoc', 'zz_acrxs_s_acrxsln02r0_P.utoc']}})

    CAL = 'acr/Content/Data/Database/Main/Common/DT_RallyWeekendCalendarPreset.uexp'
    GAME_CAL = b'the game calendars ' * 10

    def fake_retoc(self, args, what, tick=None):
        self.runs.append(args)
        if args[1] == 'to-legacy':                     # (the game's calendars, read from its own containers only)
            assert args[-2] == os.path.join(self.game, cm.OWN_PAKS), args
            assert sorted(os.listdir(args[-2])) == ['global.utoc', 'pakchunk1-Windows.utoc'], os.listdir(args[-2])
            p = os.path.join(args[-1], *self.CAL.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(self.game_cal)
            return
        assert args[1] == 'to-zen' and os.path.isdir(args[-2]), args
        cal = os.path.join(args[-2], *self.CAL.split('/'))
        self.packed_cal = None
        if os.path.isfile(cal):
            with open(cal, 'rb') as f:
                self.packed_cal = f.read()
        for x in ('pak', 'ucas', 'utoc'):
            with open(args[-1][:-len('utoc')] + x, 'wb') as f:
                f.write(b'lousa registry ' + x.encode())

    def with_calendars(self):
        """The manifest carries Lousã's calendars: a delta against the game's calendar table."""
        import base64
        self.ours_cal = self.GAME_CAL[:8] + b'OURS' + self.GAME_CAL[8:]
        d = delta_of(self.GAME_CAL, self.ours_cal)
        self.man['kit']['calendars'] = {'format': 1, 'tool': 'kit/work/bin/bin/retoc.exe', 'files': [
            {'path': self.CAL, 'base': sha(self.GAME_CAL), 'sha256': sha(self.ours_cal),
             'delta': base64.b64encode(d).decode('ascii')}]}
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)

    def test_its_calendars_go_into_its_stage_list(self):
        self.with_calendars()
        self.game_cal = self.GAME_CAL
        cm.install(self.game, cm.manifest(self.item), cm.download(cm.manifest(self.item)))
        self.assertEqual(self.packed_cal, self.ours_cal)                       # (in the stage list it packs)
        self.assertIn('zz_acrxs_lousa_registry_P.utoc', self.mods())

    def test_a_game_with_other_calendars_gets_it_without(self):
        self.with_calendars()
        self.game_cal = b'another build of the game'
        cm.install(self.game, cm.manifest(self.item), cm.download(cm.manifest(self.item)))
        self.assertIsNone(self.packed_cal)                                     # (the stage still goes in)
        self.assertIn('zz_acrxs_s_acrxsptlousa_P.utoc', self.mods())

    def test_built_by_its_kit_and_installed(self):
        man = cm.manifest(self.item)
        self.assertEqual(cm.status(self.item, man, self.game), 'install')
        self.assertEqual(cm.clashes(self.game, man), [])                       # (London hidden: still ours)
        seen = []
        cm.install(self.game, man, cm.download(man), progress=lambda s, f: seen.append((s, round(f, 2))))
        self.assertEqual(self.mods(), sorted(self.FILES + [cm.INSTALLED, 'zz_acrxs_registry_P.utoc.acrdaily-off',
                                                           'zz_acrxs_s_acrxsln02r0_P.utoc.acrdaily-off']))
        with open(os.path.join(cm.mods_dir(self.game), 'zz_acrxs_lousa_registry_P.utoc'), 'rb') as f:
            self.assertEqual(f.read(), b'lousa registry utoc')                 # (packed again under its own name)
        self.assertEqual(self.runs[0][-1], os.path.join(self.work, 'out', 'zz_acrxs_lousa_registry_P.utoc'))
        have = cm.installed(self.game)['hattori-lousa']
        self.assertEqual((have['acrBuild'], sorted(have['files'])), ('25170642', sorted(self.FILES)))   # (built for this one)
        self.assertEqual(cm.status(self.item, man, self.game), 'installed')
        self.assertFalse(os.path.exists(self.work))                            # (the work folder: gone)
        self.assertEqual(seen[-1], ('install', 1.0))
        self.assertIn(('build', 1.0), seen)
        self.build('25999999')                             # (the game updated: out, as London, built again later)
        self.assertEqual(sorted(cm.guard(self.game)), ['acrdaily-london', 'hattori-lousa'])
        self.assertEqual(self.mods(), [])

    def test_a_build_that_fails_leaves_the_game_as_it_was(self):
        man = cm.manifest(self.item)
        before = self.mods()
        with mock.patch.dict(os.environ, {'FAKE_KIT_FAIL': '1'}), self.assertRaises(cm.CommunityError) as e:
            cm.install(self.game, man, cm.download(man))
        self.assertEqual(e.exception.kind, 'assemble')
        self.assertIn('respawn walls', str(e.exception))                       # (the kit's own words)
        self.assertEqual(self.mods(), before)
        self.assertFalse(os.path.exists(self.work))

    def test_a_zip_only_a_browser_downloads_is_picked_up_where_downloads_go(self):
        """Its host (file.kiwi) downloads only in a browser: the player does, and the zip is found by its size and
        SHA-256 whatever the browser named it; until then, 'page' (the app opens it)."""
        with open(os.path.join(self.rel, 'Hattori_Rally-Lousa.zip'), 'rb') as f:
            zb = f.read()
        self.man['zip'] = dict(self.man['zip'], page='https://file.kiwi/79f605e7#key')
        with open(self.man_path, 'w') as f:
            json.dump(self.man, f)
        man = cm.manifest(self.item)
        self.assertEqual(man['zipUrl'], 'https://file.kiwi/79f605e7#key')
        downloads = os.path.join(self.tmp, 'Downloads')
        os.makedirs(os.path.join(downloads, 'mods'))
        with open(os.path.join(downloads, 'Hattori-Rally-Lousã_V0.1 (1).zip'), 'wb') as f:
            f.write(zb[:-1] + b'x')                                            # (another file of its size)
        places = [(downloads, 2)]
        self.assertIsNone(cm.find_page_download(man, places))
        with mock.patch.object(cm, 'find_page_download', return_value=None), self.assertRaises(cm.CommunityError) as e:
            cm.download(man)
        self.assertEqual((e.exception.kind, e.exception.detail), ('page', 'https://file.kiwi/79f605e7#key'))
        got = os.path.join(downloads, 'mods', 'Hattori-Rally-Lousã_V0.1.zip')
        with open(got, 'wb') as f:
            f.write(zb)
        self.assertEqual(cm.find_page_download(man, places), got)
        with mock.patch.object(cm, 'find_page_download', return_value=got):
            self.assertEqual(cm.download(man), got)
        cm.install(self.game, man, got)
        self.assertTrue(os.path.isfile(got))                                   # (the player's own download: left alone)

    def test_a_kit_needs_no_sums_other_packages_do(self):
        bad = dict(self.man, kit=None)
        with open(self.man_path, 'w') as f:
            json.dump(bad, f)
        with self.assertRaises(cm.CommunityError):
            cm.manifest(self.item)


class OtherTools(Base):
    """Stages from other tools (the test builds): Sando Rally's, installed by Sando's Stage Manager from the official
    download, and Stage-Exporter's (WRC Generations', made on the player's PC). What is in the game is read from its
    packages; only one tool's stages show at a time."""

    def paks(self, *rel):
        p = os.path.join(self.game, 'acr', 'Content', 'Paks', *rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def put(self, rel, data):
        with open(self.paks(*rel.split('/')), 'wb') as f:
            f.write(data)

    def test_a_packages_index_says_which_stages_it_carries(self):
        """Sando's Chile BioBio .utoc (0.4.2) lists DT_PacenoteSandoChlBioFull and ...RevFull; the game's own
        containers are never read as a tool's."""
        self.put('~mods/chile_biobio/pakchunk99-ChileBioBio_P.utoc',
                 b'-==-\x00/Game/Levels\x00DT_PacenoteSandoChlBioFull\x00DT_PacenoteSandoChlBioRevFull\x00MI_SandoRoad')
        self.put('pakchunk0-Windows.utoc', b'DT_PacenoteWelesS4HafrenSouthFullForward')
        self.put('global.utoc', b'DT_PacenoteX1234')
        self.put('~mods/wrcg_pack_P.utoc', b'\x00/Game/Levels/WrcgEsSS1\x00WrcgEsSS1Full\x00')   # (named otherwise)
        self.put('~mods/textures_P.utoc', b'nothing of a stage')
        packs = cm.stage_packs(self.game, ['WrcgEsSS1Full', 'WrcgSeSS3Full'])
        self.assertEqual(packs, {os.path.join('~mods', 'chile_biobio', 'pakchunk99-ChileBioBio_P.utoc'):
                                 ['SandoChlBioFull', 'SandoChlBioRevFull'],
                                 os.path.join('~mods', 'wrcg_pack_P.utoc'): ['WrcgEsSS1Full']})
        self.assertEqual(cm.stages_in_game(SANDO, packs), ['SandoChlBioFull', 'SandoChlBioRevFull'])
        self.assertEqual(cm.stages_in_game(WRCG, packs), ['WrcgEsSS1Full'])
        self.assertEqual(cm.stage_packs(None), {})

    def test_where_each_stands(self):
        man = cm.manifest(SANDO)
        self.assertEqual((man['version'], man['zip']['size'], man['manager']), ('0.4.2', 1, SANDO['download']['manager']))
        self.assertEqual(cm.status(SANDO, man, self.game), 'install')             # (not looked at yet: not installed)
        os.makedirs(cm.unpacked_dir(man))
        open(os.path.join(cm.unpacked_dir(man), man['manager']), 'wb').close()
        self.assertEqual(cm.status(SANDO, man, self.game, packs={}), 'ready')     # downloaded: its manager installs it
        packs = {'x.utoc': ['SandoChlBioFull']}
        self.assertEqual(cm.status(SANDO, man, self.game, packs=packs), 'installed')
        self.assertIsNone(cm.manifest(WRCG))
        self.assertEqual(cm.status(WRCG, None, self.game, packs=packs), 'link')
        self.assertEqual(cm.status(WRCG, None, self.game, packs={'y.utoc': ['wrcgsess3full']}), 'installed')   # (any case)
        self.assertEqual(cm.status(WRCG, None, None), 'nogame')

    def test_a_newer_version_than_his_manager_installed_an_update(self):
        """Sando's stage in the game at a version his manager's state says (by the download's pack) is older than the
        catalogue's: UPDATE; the same or newer, or not listed: installed."""
        from acr_daily import managerdrive
        state = os.path.join(self.tmp, 'state.json')

        def has(version):
            with open(state, 'w', encoding='utf-8') as f:
                json.dump({'stages': {'cl_biobio': {'id': 'cl_biobio', 'pack': 'ChileBioBio', 'version': version}}}, f)
        item = dict(SANDO, download=dict(SANDO['download'], pack='ChileBioBio', version='0.4.10'))
        man = cm.manifest(item)
        packs = {'x.utoc': ['SandoChlBioFull']}
        with mock.patch.object(managerdrive, 'STATE', state):
            self.assertEqual(cm.manager_version(man), None)                       # (no state: not known)
            self.assertEqual(cm.status(item, man, self.game, packs=packs), 'installed')
            has('0.4.2')
            self.assertEqual(cm.manager_version(man), '0.4.2')
            self.assertEqual(cm.status(item, man, self.game, packs=packs), 'update')   # (0.4.2 < 0.4.10)
            has('0.4.10')
            self.assertEqual(cm.status(item, man, self.game, packs=packs), 'installed')
            has('0.5')
            self.assertEqual(cm.status(item, man, self.game, packs=packs), 'installed')   # (his is newer)
            self.assertEqual(cm.status(item, man, self.game, packs={}), 'install')   # (not in the game: INSTALL)
            man2 = cm.manifest(dict(item, download=dict(item['download'], pack='../x')))
            self.assertIsNone(man2['pack'])                                      # (not a pack's name: never looked up)
        self.assertTrue(cm.older('0.4.2', '0.4.10') and cm.older('0.4', '0.4.1') and cm.older('0.4.2', '0.4.2b'))
        self.assertFalse(cm.older('0.4.10', '0.4.2') or cm.older('1.0', '1.0'))

    def test_only_one_tools_stages_show_so_two_are_a_clash(self):
        items = [LONDON_ITEM, SANDO, WRCG]
        one = {'a.utoc': ['SandoChlBioFull', 'SandoChlBioRevFull']}
        self.assertEqual(cm.pack_groups(items, one, self.game), {'sando': ['Chile BioBio']})
        two = dict(one, **{'b.utoc': ['WrcgSeSS3Full'], os.path.join('~mods', 'old_P.utoc'): ['SandoXyzFull']})
        self.assertEqual(cm.pack_groups(items, two, self.game),
                         {'sando': ['Chile BioBio'], 'wrcg': ['WRC Generations stages'],
                          'other:' + os.path.join('~mods', 'old_P.utoc'): ['old_P.utoc']})
        cm._save_installed(self.game, {'acrdaily-london': {'version': '1', 'files': []}})   # (this app's own, installed)
        self.assertIn('acrdaily', cm.pack_groups(items, one, self.game))

    def test_the_official_download_checked_unpacked_and_its_zip_gone(self):
        src = os.path.join(self.tmp, 'Sando.zip')
        with zipfile.ZipFile(src, 'w') as z:
            z.writestr('README.txt', b'readme')
            z.writestr('Sando-Rally-Original-Stage-Manager.exe', b'MZ manager')
            z.writestr('files/stage/pakchunk99-ChileBioBio_P.utoc', b'DT_PacenoteSandoChlBioFull')
        data = open(src, 'rb').read()
        item = dict(SANDO, download=dict(SANDO['download'], size=len(data), sha256=sha(data)))
        man = cm.manifest(item)
        man['zipUrl'] = src                                  # (a file here, not the web)
        seen = []
        path = cm.download(man)
        exe = cm.unpack(man, path, progress=lambda d, t: seen.append((d, t)))
        self.assertEqual(exe, os.path.join(cm.unpacked_dir(man), 'Sando-Rally-Original-Stage-Manager.exe'))
        self.assertEqual(cm.manager_exe(man), exe)
        self.assertTrue(os.path.isfile(os.path.join(cm.unpacked_dir(man), 'files', 'stage', 'pakchunk99-ChileBioBio_P.utoc')))
        self.assertFalse(os.path.exists(path))               # (unpacked: the zip goes)
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertGreater(cm.download_size(man), 0)
        cm.delete_download(man)
        self.assertIsNone(cm.manager_exe(man))
        self.assertEqual(cm.download_size(man), 0)

    def test_a_name_outside_its_folder_or_no_manager_unpacks_nothing(self):
        man = cm.manifest(SANDO)
        for names in (['../evil.txt', 'Sando-Rally-Original-Stage-Manager.exe'], ['README.txt']):
            z = os.path.join(self.tmp, 'bad.zip')
            with zipfile.ZipFile(z, 'w') as f:
                for n in names:
                    f.writestr(n, b'x')
            with self.assertRaises(cm.CommunityError) as e:
                cm.unpack(man, z)
            self.assertEqual(e.exception.kind, 'files')
            self.assertFalse(os.path.exists(cm.unpacked_dir(man)))
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(cm.unpacked_dir(man)), 'evil.txt')))

    def test_a_download_cut_off_goes_on_from_where_it_stopped(self):
        data = os.urandom(3 * cm.CHUNK + 123)
        src = os.path.join(self.tmp, 'big.zip')
        with open(src, 'wb') as f:
            f.write(data)
        man = {'id': 'sando-chile-biobio', 'version': '0.4.2', 'zipUrl': src,
               'zip': {'name': 'big.zip', 'size': len(data), 'sha256': sha(data)}}
        part = cm.cache_path(man) + '.part'
        os.makedirs(os.path.dirname(part))
        with open(part, 'wb') as f:
            f.write(data[:cm.CHUNK + 7])                     # (what came before the line dropped)
        seen = []
        path = cm.download(man, progress=lambda d, t: seen.append(d))
        self.assertEqual(open(path, 'rb').read(), data)
        self.assertGreater(seen[0], cm.CHUNK)                # (counted from where it stopped)
        cut = [0]

        def cancel():
            cut[0] += 1
            return cut[0] > 2
        os.remove(path)
        with self.assertRaises(cm.CommunityError):
            cm.download(man, cancel=cancel)
        self.assertTrue(os.path.isfile(part))                # (cancelled: kept for next time)
        self.assertEqual(open(cm.download(man), 'rb').read(), data)

    def test_a_download_that_doesnt_read_as_one_is_refused(self):
        for bad in ({'url': 'http://x/Sando.zip'}, {'sha256': 'abc'}, {'name': '../Sando.zip'}, {'manager': 'run.bat'},
                    {'size': 0}):
            with self.assertRaises(cm.CommunityError, msg=bad):
                cm.manifest(dict(SANDO, download=dict(SANDO['download'], **bad)))

    def test_space_it_needs(self):
        man = cm.manifest(dict(SANDO, download=dict(SANDO['download'], size=4 << 30)))
        with mock.patch.object(cm.shutil, 'disk_usage', return_value=mock.Mock(free=5 << 30)):
            short = cm.space_needed(man, self.game)
        self.assertEqual([f for f, _n in short], [settings.DIR, self.game][:1])   # (8 GB in the app's folder: short)
        with mock.patch.object(cm.shutil, 'disk_usage', return_value=mock.Mock(free=50 << 30)):
            self.assertEqual(cm.space_needed(man, self.game), [])
