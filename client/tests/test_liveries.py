"""Liveries (liveries.py): a livery's zip downloaded through the server's /go (the zip itself, not a page), its folders
unzipped into the game's Documents\\My Games\\acr\\Liveries\\<car>\\<name>, the game's 25 a car kept, and taken out
again (only what was put there). The liveries folder and the downloads are a temporary folder here."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import liveries as lvs, settings  # noqa: E402

CARS = [{'id': 'Peugeot206', 'name': 'Peugeot 206 WRC'}, {'id': 'CitroenXsaraWRC', 'name': 'Citroen Xsara WRC'},
        {'id': 'HyundaiI20NRally2', 'name': 'Hyundai i20 N Rally2'}]


def make_zip(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'appdata'))
        p.start()
        self.addCleanup(p.stop)
        self.base = os.path.join(self.tmp, 'Documents', 'My Games', 'acr', 'Liveries')
        p = mock.patch.dict(os.environ, {'ACR_DAILY_LIVERIES': self.base})
        p.start()
        self.addCleanup(p.stop)
        self.lv = {'id': 7, 'car': 'Peugeot206', 'carName': 'Peugeot 206 WRC', 'title': 'Martini 1983', 'author': 'Xardas',
                   'go': 'https://acrdaily.com/api/liveries/7/go', 'direct': True}

    def zip(self, files, name='lv.zip'):
        return make_zip(os.path.join(self.tmp, name), files)


class Plan(Base):
    def test_a_folder_a_livery_a_readme_left_out(self):
        z = self.zip({'Martini/livery.json': '{}', 'Martini/colour.dds': b'dds', 'Martini/tex/rough.dds': b'r',
                      'README.txt': 'unzip me', '__MACOSX/Martini/._colour.dds': b'x', 'Martini/Thumbs.db': b'x'})
        p = lvs.plan(z, self.lv, CARS)
        self.assertEqual([(x['src'], x['name'], x['car']) for x in p], [('Martini', 'Martini', 'Peugeot206')])
        self.assertEqual(sorted(rel for _i, rel in p[0]['files']), ['colour.dds', 'livery.json', 'tex/rough.dds'])

    def test_files_at_the_top_one_livery_named_after_its_card(self):
        p = lvs.plan(self.zip({'livery.json': '{}', 'colour.dds': b'dds'}), self.lv, CARS)
        self.assertEqual([(x['src'], x['name']) for x in p], [('', 'Martini 1983')])

    def test_a_pack_for_two_cars_each_in_its_own(self):
        z = self.zip({'Halloween/Peugeot206/Pumpkin/a.dds': b'1', 'Halloween/Peugeot206/Ghost/a.dds': b'2',
                      'Halloween/CitroenXsaraWRC/Witch/a.dds': b'3', 'Halloween/project.acrlivery': b'p'})
        p = lvs.plan(z, self.lv, CARS)
        self.assertEqual(sorted((x['name'], x['car'], x['hint']) for x in p),
                         [('Ghost', 'Peugeot206', 'Peugeot206'), ('Pumpkin', 'Peugeot206', 'Peugeot206'),
                          ('Witch', 'CitroenXsaraWRC', 'CitroenXsaraWRC')])

    def test_a_program_or_a_way_out_of_the_folder_is_refused(self):
        for files in ({'Martini/a.dds': b'1', 'Martini/setup.exe': b'MZ'}, {'../evil/a.dds': b'1'}, {'/abs/a.dds': b'1'},
                      {'C:/Windows/a.dds': b'1'}, {'project.acrlivery': b'only a project'}):
            with self.assertRaises(lvs.LiveryError, msg=str(files)) as e:
                lvs.plan(self.zip(files), self.lv, CARS)
            self.assertEqual(e.exception.kind, 'files')

    def test_names_windows_and_the_game_take(self):
        self.assertEqual(lvs.clean_name('_off: "Martini"?'), 'off Martini')
        self.assertEqual(lvs.clean_name('...'), 'Livery')
        self.assertEqual(lvs.clean_name('CON'), '_CON')
        self.assertEqual(len(lvs.clean_name('x' * 200)), 60)


class Install(Base):
    def test_in_and_out_again(self):
        z = self.zip({'Martini/livery.json': '{}', 'Martini/colour.dds': b'dds'})
        self.assertEqual(lvs.status(self.lv), 'install')
        made = lvs.install(self.lv, z, CARS)
        dest = os.path.join(self.base, 'Peugeot206', 'Martini')
        self.assertEqual(made, [dest])
        with open(os.path.join(dest, 'colour.dds'), 'rb') as f:
            self.assertEqual(f.read(), b'dds')
        self.assertEqual(lvs.status(self.lv), 'installed')
        self.assertEqual(os.listdir(os.path.join(self.base, 'Peugeot206')), ['Martini'])     # (no _acrdaily- left)
        # again (an update): the old one out first, not a "Martini (2)"
        self.assertEqual(lvs.install(self.lv, z, CARS), [dest])
        # someone else's of the same name: kept, ours beside it
        lvs.uninstall(7)
        os.makedirs(os.path.join(self.base, 'Peugeot206', 'Martini'))
        self.assertEqual(lvs.install(self.lv, z, CARS), [dest + ' (2)'])
        self.assertEqual(lvs.uninstall(7), [dest + ' (2)'])
        self.assertTrue(os.path.isdir(dest))
        self.assertEqual(lvs.status(self.lv), 'install')
        self.assertEqual(lvs.status(dict(self.lv, direct=False)), 'page')
        self.assertEqual(lvs.status(dict(self.lv, go=None)), 'showonly')

    def test_the_cars_folder_as_the_game_spells_it(self):
        os.makedirs(os.path.join(self.base, 'Peugeot 206 WRC', 'Theirs'))         # (one exported by ACR Livery Tool)
        self.assertEqual(lvs.install(self.lv, self.zip({'a.dds': b'1'}), CARS),
                         [os.path.join(self.base, 'Peugeot 206 WRC', 'Martini 1983')])
        game = os.path.join(self.tmp, 'game')                                       # (the game's templates)
        os.makedirs(os.path.join(game, 'acr', 'Content', 'LiveryTemplates', 'HyundaiI20NRally2'))
        self.assertEqual(lvs.car_folder('HyundaiI20NRally2', CARS, self.base, game), 'HyundaiI20NRally2')
        self.assertEqual(lvs.car_folder('CitroenXsaraWRC', CARS, self.base, game, hint='Citroen_Xsara_WRC'), 'Citroen_Xsara_WRC')
        self.assertEqual(lvs.car_folder('CitroenXsaraWRC', CARS, self.base, game, hint='Fiat131'), 'CitroenXsaraWRC')

    def test_25_a_car(self):
        car = os.path.join(self.base, 'Peugeot206')
        for i in range(lvs.PER_CAR - 1):
            os.makedirs(os.path.join(car, 'L%02d' % i))
        os.makedirs(os.path.join(car, '_turned off'))                              # (the game skips it: not counted)
        two = self.zip({'A/a.dds': b'1', 'B/b.dds': b'2'})
        with self.assertRaises(lvs.LiveryError) as e:
            lvs.install(self.lv, two, CARS)
        self.assertEqual(e.exception.kind, 'full')
        self.assertIn('Peugeot 206 WRC has 24', e.exception.detail)
        self.assertEqual(lvs.install(self.lv, self.zip({'A/a.dds': b'1'}), CARS), [os.path.join(car, 'A')])

    def test_remove_only_what_was_put_there(self):
        lvs.install(self.lv, self.zip({'Martini/a.dds': b'1'}), CARS)
        with open(os.path.join(settings.DIR, 'liveries.json'), encoding='utf-8') as f:
            d = json.load(f)
        d['7']['dirs'].append(self.tmp)                                             # (a record that points elsewhere)
        with open(os.path.join(settings.DIR, 'liveries.json'), 'w', encoding='utf-8') as f:
            json.dump(d, f)
        lvs.uninstall(7)
        self.assertTrue(os.path.isdir(self.tmp))
        self.assertFalse(os.path.exists(os.path.join(self.base, 'Peugeot206', 'Martini')))
        self.assertEqual(lvs.uninstall(7), [])

    def test_removed_by_hand_reads_as_not_installed(self):
        made = lvs.install(self.lv, self.zip({'Martini/a.dds': b'1'}), CARS)
        shutil.rmtree(made[0])
        self.assertEqual(lvs.status(self.lv), 'install')


class Download(Base):
    def test_the_zip_through_go_direct_counted(self):
        body = io.BytesIO()
        with zipfile.ZipFile(body, 'w') as z:
            z.writestr('Martini/a.dds', b'x' * 5000)
        data = body.getvalue()
        seen = []

        class Resp(io.BytesIO):
            headers = {'Content-Type': 'application/zip', 'Content-Length': str(len(data))}

        def urlopen(req, timeout=None):
            seen.append(req.full_url)
            return Resp(data)
        progress = []
        with mock.patch.object(lvs.urllib.request, 'urlopen', side_effect=urlopen):
            path = lvs.download(self.lv, progress=lambda d, t: progress.append((d, t)))
        self.assertEqual(seen, ['https://acrdaily.com/api/liveries/7/go?direct=1'])
        self.assertEqual(progress[-1], (len(data), len(data)))
        self.assertTrue(zipfile.is_zipfile(path))

    def test_a_page_not_the_zip(self):
        class Page(io.BytesIO):
            headers = {'Content-Type': 'text/html; charset=utf-8'}
        with mock.patch.object(lvs.urllib.request, 'urlopen', return_value=Page(b'<html>Sign in</html>')):
            with self.assertRaises(lvs.LiveryError) as e:
                lvs.download(self.lv)
        self.assertEqual(e.exception.kind, 'page')
        with self.assertRaises(lvs.LiveryError) as e:
            lvs.download(dict(self.lv, direct=False))
        self.assertEqual(e.exception.kind, 'page')

    def test_not_a_zip(self):
        class Bin(io.BytesIO):
            headers = {'Content-Type': 'application/octet-stream'}
        with mock.patch.object(lvs.urllib.request, 'urlopen', return_value=Bin(b'not a zip at all')):
            with self.assertRaises(lvs.LiveryError) as e:
                lvs.download(self.lv)
        self.assertEqual(e.exception.kind, 'zip')
        self.assertEqual(os.listdir(os.path.join(settings.DIR, 'liveries')), [])   # (nothing half there)

    def test_stars(self):
        self.assertEqual(lvs.stars_text({'votes': 2, 'stars': 4.5}), '★★★★☆ 4.5 · 2 votes')
        self.assertEqual(lvs.stars_text({'votes': 0}), 'No votes yet')


if __name__ == '__main__':
    unittest.main()
