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


if __name__ == '__main__':
    unittest.main()
