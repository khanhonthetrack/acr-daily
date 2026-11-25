"""COMMUNITY's packages the catalogue describes itself (community.manifest: Oxmod's Thierache stages, 25 Nov 2026): the zip
from its author's link, only the files named (by their place in the zip), and the set's stage list in the version for
the set's items installed, packed again under the set's own name (place_registry), changed as items come and go and
taken out with the last one."""
import hashlib
import io
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

from acr_daily import community, settings

VARIANTS = {'ox-a': 'menu/A/zz_acrxs_registry_P', 'ox-b': 'menu/B/zz_acrxs_registry_P',
            'ox-a+ox-b': 'menu/AB/zz_acrxs_registry_P'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = os.path.join(self.tmp, 'game')
        os.makedirs(os.path.join(self.game, 'acr', 'Content', 'Paks', '~mods'))
        open(os.path.join(self.game, 'acr', 'Content', 'Paks', 'global.utoc'), 'wb').write(b'g')
        p = mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'app'))
        p.start()
        self.addCleanup(p.stop)
        for name in ('game_running', 'game_build'):
            q = mock.patch.object(community, name, return_value=False if name == 'game_running' else '26756580')
            q.start()
            self.addCleanup(q.stop)
        self.menus = {'%s.%s' % (stem, x): ('%s-%s' % (stem, x)).encode() for stem in VARIANTS.values()
                      for x in ('pak', 'ucas', 'utoc')}
        self.packed = []                                  # (the variant each repack read)

        def run(args, what, tick=None):
            if args[1] == 'to-legacy':
                src = args[-2]
                utoc = [n for n in os.listdir(src) if n.endswith('.utoc') and not n.startswith('global')][0]
                self.packed.append(open(os.path.join(src, utoc), 'rb').read().decode())
                os.makedirs(args[-1], exist_ok=True)
            elif args[1] == 'to-zen':
                stem = args[-1][:-len('.utoc')]
                for x in ('pak', 'ucas', 'utoc'):
                    open('%s.%s' % (stem, x), 'wb').write(self.packed[-1].encode())
        q = mock.patch.object(community, '_run', side_effect=run)
        q.start()
        self.addCleanup(q.stop)

    def item(self, key, stage):
        files = {'~mods/zz_acrxs_s_%s_P.%s' % (stage, x): ('%s-%s' % (stage, x)).encode() for x in ('pak', 'ucas', 'utoc')}
        extra = {'~mods/zz_acrxs_terre_P.utoc': b'not ours to take', 'Installer.exe': b'MZ'}
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            for n, d in list(files.items()) + list(self.menus.items()) + list(extra.items()):
                z.writestr(n, d)
        path = os.path.join(self.tmp, key + '.zip')
        open(path, 'wb').write(b.getvalue())
        reg = {'name': 'zz_acrxs_oxmod_registry_P', 'group': 'oxmod', 'variants': VARIANTS,
               'sha256': {n: sha(d) for n, d in self.menus.items()}}
        it = {'id': key, 'package': {'version': '1', 'acrBuild': '26756580',
              'zip': {'name': key + '.zip', 'size': len(b.getvalue()), 'sha256': sha(b.getvalue()),
                      'url': 'https://www.patreon.com/file?h=1&m=2', 'page': 'https://www.patreon.com/posts/1'},
              'files': [{'name': n.split('/')[-1], 'from': n, 'size': len(d), 'sha256': sha(d)} for n, d in files.items()],
              'registry': reg}}
        return it, path

    def mods(self):
        return sorted(os.listdir(community.mods_dir(self.game)))

    def reg_now(self):
        p = os.path.join(community.mods_dir(self.game), 'zz_acrxs_oxmod_registry_P.utoc')
        return open(p, 'rb').read().decode() if os.path.isfile(p) else None

    def test_both_items_then_one_then_none(self):
        tools = {'retoc': 'retoc.exe'}
        a, za = self.item('ox-a', 'acrxsthi04')
        b, zb = self.item('ox-b', 'acrxsthi05')
        man_a = community.manifest(a)
        self.assertEqual(man_a['zipUrl'], 'https://www.patreon.com/file?h=1&m=2')
        with mock.patch.object(community, 'registry_tools', return_value=tools):
            community.install(self.game, man_a, za)
            self.assertEqual(self.reg_now(), 'menu/A/zz_acrxs_registry_P-utoc')
            self.assertNotIn('zz_acrxs_terre_P.utoc', self.mods())       # (only the files named)
            community.install(self.game, community.manifest(b), zb)       # (the list of ours: no clash)
            self.assertEqual(self.reg_now(), 'menu/AB/zz_acrxs_registry_P-utoc')
            self.assertIn('zz_acrxs_s_acrxsthi05_P.ucas', self.mods())
            community.uninstall(self.game, 'ox-a')
            self.assertEqual(self.reg_now(), 'menu/B/zz_acrxs_registry_P-utoc')
            self.assertNotIn('zz_acrxs_s_acrxsthi04_P.ucas', self.mods())
            community.uninstall(self.game, 'ox-b')
        self.assertIsNone(self.reg_now())
        self.assertEqual(self.mods(), [])

    def test_a_damaged_list_in_the_zip_changes_nothing(self):
        a, za = self.item('ox-a', 'acrxsthi04')
        a['package']['registry']['sha256']['menu/A/zz_acrxs_registry_P.ucas'] = '0' * 64
        with mock.patch.object(community, 'registry_tools', return_value={'retoc': 'r'}):
            with self.assertRaises(community.CommunityError) as e:
                community.install(self.game, community.manifest(a), za)
        self.assertEqual(e.exception.kind, 'files')
        self.assertEqual(self.mods(), [])

    def test_no_tools_and_none_to_fetch(self):
        a, za = self.item('ox-a', 'acrxsthi04')
        with mock.patch('acr_daily.stagelist.tools', return_value=None):
            with self.assertRaises(community.CommunityError) as e:
                community.install(self.game, community.manifest(a), za)
        self.assertEqual(e.exception.kind, 'tools')
        self.assertEqual(self.mods(), [])

    def test_the_authors_link_refused_the_page_then(self):
        a, _za = self.item('ox-a', 'acrxsthi04')
        man = community.manifest(a)
        import urllib.error
        err = urllib.error.HTTPError(man['zipUrl'], 403, 'Forbidden', {}, None)
        with mock.patch.object(community, 'find_page_download', return_value=None), \
                mock.patch('acr_daily.community.urllib.request.urlopen', side_effect=err):
            with self.assertRaises(community.CommunityError) as e:
                community.download(man)
        self.assertEqual((e.exception.kind, e.exception.detail), ('page', 'https://www.patreon.com/posts/1'))


if __name__ == '__main__':
    unittest.main()
