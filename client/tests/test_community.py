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
        os.remove(path)                                  # a damaged part: refused, nothing kept
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

    def test_no_manifest_yet(self):
        self.assertIsNone(cm.manifest({'id': 'x'}))
        self.assertEqual(cm.status({'id': 'x'}, None, self.game), 'unavailable')
        self.assertEqual(cm.status({'id': 'x'}, None, None), 'nogame')

    def test_sizes(self):
        self.assertEqual(cm.size_text(812345678), '774.7 MB')
        self.assertEqual(cm.size_text(2048), '2 KB')


if __name__ == '__main__':
    unittest.main()
