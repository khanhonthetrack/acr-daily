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

    def test_a_package_built_from_the_games_own_files_waits_for_a_newer_app(self):
        """ACR DAILY London's version 8 (13 Nov 2026): the stage's own files and deltas against the game's, put
        together on the PC ('assemble'), which this app doesn't do: nothing offered, nothing downloaded."""
        man = dict(cm.manifest(self.item), assemble={'format': 1, 'tool': 'tools/retoc.exe', 'containers': []})
        self.assertEqual(cm.status(self.item, man, self.game), 'newer')
        cm.install(self.game, cm.manifest(self.item), cm.download(cm.manifest(self.item)))   # (an older one installed)
        self.assertEqual(cm.status(self.item, man, self.game), 'installed')

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
WRCG = {'id': 'wrcg-stage-exporter', 'install': 'link', 'group': 'wrcg', 'name': 'WRC Generations stages',
        'stages': [{'stageId': 'WrcgEsSS1Full'}, {'stageId': 'WrcgEsSS1RFull'}, {'stageId': 'WrcgSeSS3Full'}],
        'page': 'https://github.com/Faviogames/Stage-Exporter'}
LONDON_ITEM = {'id': 'acrdaily-london', 'group': 'acrdaily', 'name': 'ACR DAILY London',
               'stages': [{'stageId': 'AcrXsLn02r0FullForward'}]}


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
