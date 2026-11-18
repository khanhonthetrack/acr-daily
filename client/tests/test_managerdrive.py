"""Sando Rally's Stage Manager run for the player (managerdrive.py): what it answers on the manager's notes, when the
stage counts as installed (the manager's own state), and the install window's Install button found by its row."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import managerdrive as md  # noqa: E402


class Answers(unittest.TestCase):
    def test_a_note_is_ok_a_question_about_installing_yes_anything_else_the_players(self):
        self.assertEqual(md.answer('Chile BioBio 0.4.2 installed', {'ok': 1}), 'ok')
        self.assertEqual(md.answer('This stage was made for build 25170642. Install it anyway?', {'yes': 1, 'no': 2}), 'yes')
        self.assertIsNone(md.answer('Uninstall Chile BioBio?\n\nYour ACR save is copied first.', {'yes': 1, 'no': 2}))
        self.assertIsNone(md.answer('Clean up everything? Install again later.', {'yes': 1, 'no': 2}))
        self.assertIsNone(md.answer('Open the folder?', {'yes': 1, 'no': 2}))


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, 'state.json')

    def write(self, at, version='0.4.2', pack='ChileBioBio'):
        with open(self.state, 'w', encoding='utf-8') as f:
            json.dump({'format': 1, 'stages': {'cl_biobio': {'pack': pack, 'version': version, 'installed_at': at}}}, f)

    def test_installed_once_its_state_lists_it_at_its_version_after_the_start(self):
        t0 = time.mktime((2026, 11, 18, 12, 50, 0, 0, 0, -1))
        self.assertFalse(md.installed_since('ChileBioBio', '0.4.2', t0, self.state))            # (no state yet)
        self.write('20261118-110545')                                                       # (this morning's)
        self.assertFalse(md.installed_since('ChileBioBio', '0.4.2', t0, self.state))
        self.write('20261118-125042', version='0.4.1')
        self.assertFalse(md.installed_since('ChileBioBio', '0.4.2', t0, self.state))
        self.write('20261118-125042')
        self.assertTrue(md.installed_since('chilebiobio', '0.4.2', t0, self.state))


class Offer(unittest.TestCase):
    def test_its_install_button_is_the_left_of_the_two_side_by_side(self):
        # the window offering the install (its frames: the words, the tick box, a row of two buttons)
        tree = {1: [2], 2: [3], 3: [4, 5, 6, 7], 4: [9, 8], 5: [], 6: [], 7: []}
        rects = {8: (311, 185, 387, 210), 9: (391, 185, 467, 210), 4: (307, 185, 467, 210),
                 5: (22, 152, 467, 171), 6: (22, 131, 284, 152), 7: (22, 45, 255, 119), 2: (8, 31, 481, 224),
                 3: (8, 31, 481, 224)}
        parent = {k: p for p, ks in tree.items() for k in ks}

        def children(h):
            out, todo = [], list(tree.get(h, []))
            while todo:
                k = todo.pop(0)
                out.append(k)
                todo += tree.get(k, [])
            return out
        u = mock.Mock()
        u.GetParent.side_effect = lambda h: parent.get(h, 0)
        with mock.patch.object(md, '_children', side_effect=children), \
                mock.patch.object(md, '_rect', side_effect=lambda h: rects[h]), \
                mock.patch.object(md, '_user32', return_value=u):
            self.assertEqual(md.offer_install(1), 8)
        # the manager's main window: a row of six buttons, no such pair
        tree2 = {1: [2], 2: [10, 11, 12, 13, 14, 15]}
        parent2 = {k: p for p, ks in tree2.items() for k in ks}
        u.GetParent.side_effect = lambda h: parent2.get(h, 0)
        with mock.patch.object(md, '_children', side_effect=lambda h: [k for k in tree2.get(h, [])] +
                               [g for k in tree2.get(h, []) for g in tree2.get(k, [])]), \
                mock.patch.object(md, '_rect', side_effect=lambda h: (h * 100, 0, h * 100 + 80, 25)), \
                mock.patch.object(md, '_user32', return_value=u):
            self.assertIsNone(md.offer_install(1))


if __name__ == '__main__':
    unittest.main()
