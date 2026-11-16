"""London or WRC Generations shown (stageswitch.py): the set not shown parked by renaming its files (never deleted,
never made again), shown again in a second; the game open or a file held: nothing half done."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import stageswitch as sw  # noqa: E402


def game_with_both():
    game = tempfile.mkdtemp()
    paks = os.path.join(game, 'acr', 'Content', 'Paks')
    os.makedirs(os.path.join(paks, '~mods'))
    for n, data in (('zz_acrxs_registry_P.utoc', b'registry'), ('zz_acrxs_registry_P.ucas', b'r'), ('zz_acrxs_registry_P.pak', b'p'),
                    ('zz_acrxs_s_acrxsln02r0_P.utoc', b'\0DT_PacenoteAcrXsLn02r0FullForward\0'),
                    ('zz_acrxs_s_acrxsln02r0_P.ucas', b'stage'), ('ACRDaily-community.json', b'{}')):
        with open(os.path.join(paks, '~mods', n), 'wb') as f:
            f.write(data)
    for n, data in (('pakchunk99-WrcgStages_P.utoc', b'\0DT_PacenoteWrcgEsSS1Full\0'), ('pakchunk99-WrcgStages_P.ucas', b'big'),
                    ('pakchunk99-WrcgStages_P.pak', b'p'), ('pakchunk0-Windows.utoc', b'stock'), ('pakchunk99-ChileBioBio_P.utoc', b'sando')):
        with open(os.path.join(paks, n), 'wb') as f:
            f.write(data)
    return game, paks


def game_with_three():
    """London, WRC Generations and Sando Rally's Chile BioBio (his stage container and his manager's stage list)."""
    game, paks = game_with_both()
    for n, data in (('pakchunk99-ChileBioBio_P.utoc', b'\0DT_PacenoteSandoChlBioFull\0'), ('pakchunk99-ChileBioBio_P.ucas', b'4 GB'),
                    ('pakchunk99-ChileBioBio_P.pak', b'p'), ('pakchunk99-SandoStageList_P.utoc', b'\0DT_TracksVariants.uasset\0'),
                    ('pakchunk99-SandoStageList_P.ucas', b'list'), ('pakchunk0-Windows.utoc', b'\0DT_TracksVariants.uasset\0'),
                    ('pakchunk99-WrcgStages_P.utoc', b'\0DT_PacenoteWrcgEsSS1Full\0DT_TracksVariants.uasset\0')):
        with open(os.path.join(paks, n), 'wb') as f:
            f.write(data)
    return game, paks


class Switch(unittest.TestCase):
    def setUp(self):
        self.game, self.paks = game_with_both()
        self.no = lambda: False

    def names(self, sub=''):
        return sorted(os.listdir(os.path.join(self.paks, sub) if sub else self.paks))

    def test_both_in_then_one_shown_the_other_parked(self):
        self.assertEqual(sw.state(self.game), {'acrdaily': 'on', 'wrcg': 'on'})
        sw.show(self.game, 'wrcg', running=self.no)
        self.assertEqual(sw.state(self.game), {'acrdaily': 'off', 'wrcg': 'on'})
        self.assertEqual(self.names('~mods'), ['ACRDaily-community.json', 'zz_acrxs_registry_P.pak.acrdaily-off',
                                               'zz_acrxs_registry_P.ucas.acrdaily-off', 'zz_acrxs_registry_P.utoc.acrdaily-off',
                                               'zz_acrxs_s_acrxsln02r0_P.ucas.acrdaily-off',
                                               'zz_acrxs_s_acrxsln02r0_P.utoc.acrdaily-off'])
        self.assertIn('pakchunk99-ChileBioBio_P.utoc', self.names())                 # (Sando's: never touched)
        self.assertEqual(sw.parked_packs(self.game), {os.path.join('~mods', 'zz_acrxs_s_acrxsln02r0_P.utoc.acrdaily-off'):
                                                      ['AcrXsLn02r0FullForward']})
        sw.show(self.game, 'acrdaily', running=self.no)                              # (and back: renames only)
        self.assertEqual(sw.state(self.game), {'acrdaily': 'on', 'wrcg': 'off'})
        self.assertIn('pakchunk99-WrcgStages_P.ucas.acrdaily-off', self.names())
        with open(os.path.join(self.paks, '~mods', 'zz_acrxs_s_acrxsln02r0_P.ucas'), 'rb') as f:
            self.assertEqual(f.read(), b'stage')                                      # (the same file, not made again)
        self.assertEqual(list(sw.parked_packs(self.game).values()), [['WrcgEsSS1Full']])

    def test_a_pack_made_anew_while_parked_wins_over_the_old_copy(self):
        sw.show(self.game, 'acrdaily', running=self.no)
        with open(os.path.join(self.paks, 'pakchunk99-WrcgStages_P.utoc'), 'wb') as f:   # (Stage Exporter installed a new pack)
            f.write(b'\0DT_PacenoteWrcgEsSS1Full\0DT_PacenoteWrcgEsSS4Full\0')
        sw.show(self.game, 'wrcg', running=self.no)
        self.assertNotIn('pakchunk99-WrcgStages_P.utoc.acrdaily-off', self.names())  # (the old one: gone)
        with open(os.path.join(self.paks, 'pakchunk99-WrcgStages_P.utoc'), 'rb') as f:
            self.assertIn(b'WrcgEsSS4Full', f.read())

    def test_the_game_open_or_a_file_held_changes_nothing(self):
        with self.assertRaises(sw.SwitchError) as e:
            sw.show(self.game, 'wrcg', running=lambda: True)
        self.assertEqual(e.exception.kind, 'running')
        before = self.names('~mods')
        real = os.rename
        calls = []

        def held(a, b):
            calls.append(a)
            if len(calls) == 3:
                raise PermissionError('in use')
            real(a, b)
        with mock.patch.object(sw.os, 'rename', side_effect=held), self.assertRaises(sw.SwitchError) as e:
            sw.show(self.game, 'wrcg', running=self.no)
        self.assertEqual(e.exception.kind, 'files')
        self.assertEqual(self.names('~mods'), before)                                # (the ones renamed: put back)

    def test_forgotten_with_the_item(self):
        sw.show(self.game, 'wrcg', running=self.no)
        sw.forget(self.game, 'acrdaily', ['zz_acrxs_registry_P.utoc', 'zz_acrxs_registry_P.ucas', 'zz_acrxs_registry_P.pak'])
        self.assertNotIn('zz_acrxs_registry_P.utoc.acrdaily-off', self.names('~mods'))
        self.assertEqual(sw.state(os.path.join(self.game, 'nowhere')), {})


class Three(unittest.TestCase):
    """Sando Rally's set too: his stage container (its pace notes say Sando) and his manager's stage list (a container
    of no other set's that carries DT_TracksVariants); the game's own never."""

    def setUp(self):
        self.game, self.paks = game_with_three()
        self.no = lambda: False

    def test_his_files_found_by_what_is_in_them(self):
        shown, parked = sw.files(self.game, 'sando')
        self.assertEqual([os.path.basename(p) for p in shown],
                         ['pakchunk99-ChileBioBio_P.pak', 'pakchunk99-ChileBioBio_P.ucas', 'pakchunk99-ChileBioBio_P.utoc',
                          'pakchunk99-SandoStageList_P.ucas', 'pakchunk99-SandoStageList_P.utoc'])
        self.assertEqual(sw.state(self.game), {'acrdaily': 'on', 'wrcg': 'on', 'sando': 'on'})

    def test_one_shown_the_others_parked_each_way(self):
        sw.show(self.game, 'sando', running=self.no)
        self.assertEqual(sw.state(self.game), {'acrdaily': 'off', 'wrcg': 'off', 'sando': 'on'})
        sw.show(self.game, 'wrcg', running=self.no)
        self.assertEqual(sw.state(self.game), {'acrdaily': 'off', 'wrcg': 'on', 'sando': 'off'})
        names = os.listdir(self.paks)
        self.assertIn('pakchunk99-ChileBioBio_P.ucas.acrdaily-off', names)
        self.assertIn('pakchunk0-Windows.utoc', names)                               # (the game's own: never)
        self.assertIn(os.path.join('pakchunk99-ChileBioBio_P.utoc.acrdaily-off'), names)
        self.assertEqual(sorted(i for ids in sw.parked_packs(self.game).values() for i in ids),
                         ['AcrXsLn02r0FullForward', 'SandoChlBioFull'])
        sw.show(self.game, 'sando', running=self.no)
        with open(os.path.join(self.paks, 'pakchunk99-ChileBioBio_P.ucas'), 'rb') as f:
            self.assertEqual(f.read(), b'4 GB')                                       # (his file, as he put it)

    def test_the_others_out_while_a_wrcg_stage_is_made_and_back(self):
        done = sw.park_others(self.game, 'wrcg', running=self.no)
        self.assertEqual(sorted(done), ['acrdaily', 'sando'])
        self.assertEqual(sw.state(self.game), {'acrdaily': 'off', 'wrcg': 'on', 'sando': 'off'})
        for g in done:                                                               # (it didn't go through: back)
            sw.unpark(self.game, g)
        self.assertEqual(sw.state(self.game), {'acrdaily': 'on', 'wrcg': 'on', 'sando': 'on'})
        with self.assertRaises(sw.SwitchError):
            sw.park_others(self.game, 'wrcg', running=lambda: True)


if __name__ == '__main__':
    unittest.main()
