"""The game mod for real cars (modinstall.py): finding the game, putting UE4SS and our mod in, taking them out."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import modinstall as mi, settings  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ZIP = os.path.join(REPO, 'mod', 'ue4ss', mi.UE4SS_ZIP)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(settings, 'DIR', os.path.join(self.tmp, 'appdata'))   # (the zip's cache)
        p.start()
        self.addCleanup(p.stop)
        self.game = os.path.join(self.tmp, 'lib', 'steamapps', 'common', 'Assetto Corsa Rally')
        self.win64 = os.path.join(self.game, 'acr', 'Binaries', 'Win64')
        os.makedirs(self.win64)
        open(os.path.join(self.win64, 'acr.exe'), 'wb').close()

    def files(self):
        out = []
        for d, _dirs, fs in os.walk(self.win64):
            out += [os.path.relpath(os.path.join(d, f), self.win64).replace('\\', '/') for f in fs]
        return sorted(out)

    def put(self, rel, data=b'x'):
        p = os.path.join(self.win64, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)


class FindTheGame(Base):
    def test_from_steams_library_list(self):
        steam = os.path.join(self.tmp, 'steam')
        os.makedirs(os.path.join(steam, 'steamapps'))
        lib = os.path.join(self.tmp, 'lib')
        with open(os.path.join(steam, 'steamapps', 'libraryfolders.vdf'), 'w', encoding='utf-8') as f:
            f.write('"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n'
                    % (steam.replace('\\', '\\\\'), lib.replace('\\', '\\\\')))
        with open(os.path.join(lib, 'steamapps', 'appmanifest_3917090.acf'), 'w', encoding='utf-8') as f:
            f.write('"AppState"\n{\n\t"appid"\t\t"3917090"\n\t"installdir"\t\t"Assetto Corsa Rally"\n}\n')
        self.assertEqual(os.path.normcase(mi.game_dir([steam])), os.path.normcase(self.game))
        self.assertIsNone(mi.game_dir([os.path.join(self.tmp, 'nowhere')]))


@unittest.skipUnless(os.path.isfile(ZIP), 'no UE4SS zip in the repo')
class InAndOut(Base):
    def test_a_clean_game_and_back(self):
        self.assertEqual(mi.state(self.game), 'none')
        self.assertEqual(mi.sync(True, self.game, [ZIP]), 'ready')
        self.assertEqual(self.files(), sorted(['acr.exe', 'dwmapi.dll', 'ue4ss/UE4SS.dll', 'ue4ss/UE4SS-settings.ini',
                                               'ue4ss/LICENSE', 'ue4ss/UE4SS_SDK_Backends/UE4SS.json',
                                               'ue4ss/Mods/shared/UEHelpers/UEHelpers.lua', 'ue4ss/Mods/mods.txt',
                                               'ue4ss/Mods/ACRDailyGhosts/Scripts/main.lua',
                                               'ue4ss/Mods/ACRDailyGhosts/Scripts/wheels.lua', mi.MANIFEST]))
        with open(os.path.join(self.win64, 'ue4ss', 'Mods', 'mods.txt')) as f:
            self.assertEqual(f.read(), 'ACRDailyGhosts : 1\n')                  # only ours starts
        self.assertEqual(mi.state(self.game), 'ours')
        self.assertEqual(mi.install(self.game, [ZIP]), [])                       # in place: nothing written again
        self.put('ue4ss/UE4SS.log', b'log')                                     # (the game ran)
        self.assertEqual(mi.sync(False, self.game), 'off')
        self.assertEqual(self.files(), ['acr.exe'])                              # the game as it was
        self.assertEqual(os.listdir(self.win64), ['acr.exe'])

    def test_a_new_app_brings_its_mod_up_to_date(self):
        mi.sync(True, self.game, [ZIP])
        self.put('ue4ss/Mods/ACRDailyGhosts/Scripts/main.lua', b'-- an older mod')
        self.assertEqual(mi.install(self.game, [ZIP]), ['ue4ss/Mods/ACRDailyGhosts/Scripts/main.lua'])

    def test_their_own_ue4ss_is_left_alone(self):
        self.put('dwmapi.dll', b'their dll')
        self.put('ue4ss/UE4SS.dll', b'their ue4ss')
        mods = 'BPModLoaderMod : 1\n\n; Built-in keybinds, do not move up!\nKeybinds : 1\n'
        self.put('ue4ss/Mods/mods.txt', mods.encode())
        self.put('ue4ss/Mods/mods.json', b'[{"mod_name": "BPModLoaderMod", "mod_enabled": true}]')
        before = self.files()
        self.assertEqual(mi.state(self.game), 'theirs')
        self.assertEqual(mi.sync(True, self.game, [ZIP]), 'ready')
        with open(os.path.join(self.win64, 'ue4ss', 'Mods', 'mods.txt')) as f:
            self.assertEqual(f.read().splitlines(), ['BPModLoaderMod : 1', '', 'ACRDailyGhosts : 1',
                                                     '; Built-in keybinds, do not move up!', 'Keybinds : 1'])
        with open(os.path.join(self.win64, 'ue4ss', 'Mods', 'mods.json')) as f:
            self.assertIn({'mod_name': 'ACRDailyGhosts', 'mod_enabled': True}, json.load(f))
        with open(os.path.join(self.win64, 'ue4ss', 'UE4SS.dll'), 'rb') as f:
            self.assertEqual(f.read(), b'their ue4ss')                          # not replaced
        self.assertEqual(mi.state(self.game), 'theirs')
        self.assertEqual(mi.sync(False, self.game), 'off')
        self.assertEqual(self.files(), before)
        with open(os.path.join(self.win64, 'ue4ss', 'Mods', 'mods.txt')) as f:
            self.assertNotIn('ACRDailyGhosts', f.read())
        with open(os.path.join(self.win64, 'ue4ss', 'Mods', 'mods.json')) as f:
            self.assertEqual(json.load(f), [{'mod_name': 'BPModLoaderMod', 'mod_enabled': True}])

    def test_another_mods_dll_in_the_way(self):
        self.put('dwmapi.dll', b'someone else')
        self.assertEqual(mi.sync(True, self.game, [ZIP]), 'clash')
        self.assertEqual(self.files(), ['acr.exe', 'dwmapi.dll'])

    def test_the_game_holding_a_file(self):
        """Windows won't delete a DLL the game has loaded: it waits, and finishes once the game is closed."""
        mi.sync(True, self.game, [ZIP])
        held = open(os.path.join(self.win64, 'dwmapi.dll'), 'rb')
        try:
            self.assertEqual(mi.sync(False, self.game), 'busy')
            self.assertIn('dwmapi.dll', self.files())
        finally:
            held.close()
        self.assertEqual(mi.sync(False, self.game), 'off')
        self.assertEqual(self.files(), ['acr.exe'])


@unittest.skipUnless(os.path.isfile(ZIP), 'no UE4SS zip in the repo')
class TheAppsKeeper(Base):
    def wait_for(self, keeper, status):
        for _ in range(100):
            if keeper.status == status:
                return
            time.sleep(0.1)
        self.fail('status %r, not %r' % (keeper.status, status))

    def test_in_when_wanted_out_when_not(self):
        wanted = {'on': True}
        with mock.patch.object(mi, 'game_dir', return_value=self.game), \
                mock.patch.object(mi, 'UE4SS_URLS', [ZIP]):                 # (never the real game, never online)
            keeper = mi.Keeper(lambda: wanted['on'])
            self.wait_for(keeper, 'ready')
            self.assertIn('ue4ss/Mods/ACRDailyGhosts/Scripts/main.lua', self.files())
            wanted['on'] = False
            keeper.poke()
            self.wait_for(keeper, 'off')
            self.assertEqual(self.files(), ['acr.exe'])


class Download(Base):
    def test_only_the_expected_file(self):
        bad = os.path.join(self.tmp, 'bad.zip')
        with open(bad, 'wb') as f:
            f.write(b'PK not ue4ss')
        with self.assertRaises(mi.InstallError) as e:
            mi.ue4ss_zip([bad])
        self.assertEqual(e.exception.args[0], 'download')
        self.assertFalse(os.path.exists(mi.cache_path()))
        self.assertEqual(mi.sync(True, self.game, [bad]), 'download')
        self.assertEqual(self.files(), ['acr.exe'])                              # nothing half-done

    def test_no_game(self):
        with mock.patch.object(mi, 'game_dir', return_value=None):
            self.assertEqual(mi.sync(True), 'nogame')
            self.assertEqual(mi.sync(False), 'off')


if __name__ == '__main__':
    unittest.main()
