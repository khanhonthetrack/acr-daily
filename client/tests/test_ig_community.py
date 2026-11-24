"""COMMUNITY inside the running game (ig_community.py + ingameapp.py): actions stay clickable while the game runs,
downloads run in the background, cancel cancels downloading/pending installs, file-changing actions offer to close &
relaunch the game, and DRIVE on a missing community track switches to the in-game COMMUNITY tab."""
import os
import sys
import tempfile
import time
import tkinter as tk
import tkinter.messagebox as tk_messagebox
import unittest
from tkinter import simpledialog
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import communityui, ig_community, ingameapp  # noqa: E402
from test_communityui import CATALOG, EXPORTER, LONDON, MAN, Now, RIUDECANYES, SANDO, SAVALLA  # noqa: E402
from test_tabs import Harness  # noqa: E402


def _walk(node):
    if isinstance(node, dict):
        yield node
        c = node.get('c')
        for kid in (c if isinstance(c, list) else [c] if c is not None else []):
            yield from _walk(kid)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _buttons(page):
    return {n['id']: n for n in _walk(page) if n.get('t') == 'btn' and n.get('id')}


def _texts(page):
    out = [n['s'] for n in _walk(page) if n.get('t') == 'txt' and n.get('s') is not None]
    out += [n['s'] for n in _walk(page) if n.get('t') == 'btn' and n.get('s') is not None]
    return out


class InGameCommunity(Harness):
    def setUp(self):
        super().setUp()
        self.home = tempfile.mkdtemp()
        p = mock.patch.object(communityui.settings, 'DIR', self.home)
        p.start()
        self.addCleanup(p.stop)
        ig_community._cut.clear()

        # Preserve module-level tkinter dialogs mutated by InGameApp.questions()
        saved_mb = {n: getattr(tk_messagebox, n) for n in (
            'showinfo', 'showwarning', 'showerror', 'askyesno', 'askokcancel',
            'askyesnocancel', 'askretrycancel', 'askquestion')}
        saved_sd = simpledialog.askstring
        self.addCleanup(lambda: [setattr(tk_messagebox, n, f) for n, f in saved_mb.items()])
        self.addCleanup(lambda: setattr(simpledialog, 'askstring', saved_sd))

        a = self.a
        a.dailies, a.active = {}, 1
        a._build_home_box()
        a._build_community_box()
        a._side, a._main = tk.Frame(self.root), tk.Frame(self.root)
        a._side.pack(side='left')
        a._main.pack(side='left')
        a.refresh_community = mock.Mock()
        a._pulse = lambda: mock.Mock(alive=lambda: True)

        self.status_map = {'acrdaily-london': 'install'}
        self.game_running = True
        for name, fn in (('status', lambda it, *_a, **_k: self.status_map.get(it['id'], 'install')),
                         ('game_running', lambda: self.game_running),
                         ('clashes', lambda *_a: [])):
            p = mock.patch.object(communityui.community, name, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)
        for p in (mock.patch.object(communityui.photos, 'fetch', return_value=None),
                  mock.patch.object(ig_community.photos, 'fetch', return_value=None)):
            p.start()
            self.addCleanup(p.stop)

        self.ig = a.ingame_app = ingameapp.InGameApp(a)
        self.addCleanup(self.ig.writer.close)
        self.addCleanup(self.ig.events.close)
        self.ig.questions()
        self.ig.tab = ig_community.TAB
        self.ig.shown = True
        ig_community._mem(self.ig).update({'run_t': time.monotonic(), 'running': True})

    def load_catalog(self, cat=None, mans=None, packs=None, switch=None):
        a = self.a
        a._set_community(cat or CATALOG, mans or {'acrdaily-london': dict(MAN)}, '',
                         '/games/ACR', '25170642', [], packs or {}, switch=switch)
        self.root.update()

    def test_page_offers_install_all_and_showonly_while_game_runs(self):
        self.load_catalog()
        btns = _buttons(ig_community.page(self.ig))
        self.assertEqual(btns['community.go:acrdaily-london']['s'], 'INSTALL  ›')

        from test_stageswitch import game_with_both
        game, _paks = game_with_both()
        london = dict(LONDON, group='acrdaily', stages=[{'stageId': 'AcrXsLn02r0FullForward'}])
        cat = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [london, RIUDECANYES, SAVALLA]},
                              {'id': 'cars', 'name': 'Cars', 'items': []}],
               'tools': {'stage-exporter': EXPORTER}}
        self.status_map = {'acrdaily-london': 'installed', 'wrcg-es-ss1': 'installed', 'wrcg-es-ss4': 'install'}
        with mock.patch.object(self.a, '_export_set_env'):
            self.a._set_community(cat, {'acrdaily-london': dict(MAN)}, '', game, '25170642', [],
                                  {'x.utoc': ['AcrXsLn02r0FullForward', 'WrcgEsSS1Full']},
                                  switch={'acrdaily': 'on', 'wrcg': 'on'}, parked={})
        self.root.update()
        btns = _buttons(ig_community.page(self.ig))
        self.assertIn('community.all', btns)
        self.assertIn('INSTALL ALL', btns['community.all']['s'])
        self.assertEqual(btns['community.showonly:acrdaily']['s'], 'SHOW ONLY LONDON')
        self.assertEqual(btns['community.showonly:wrcg']['s'], 'SHOW ONLY WRC GENERATIONS')

    def test_install_downloads_pending_and_cancel_works_in_game(self):
        self.load_catalog()
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.community, 'download', return_value='/cache/London.zip'), \
                mock.patch.object(communityui.community, 'install') as inst, \
                mock.patch.object(self.a, '_community_poll_game'):
            self.ig.click('community.go:acrdaily-london')
        inst.assert_not_called()
        self.assertIn('acrdaily-london', self.a._community_pending)
        self.assertIsNotNone(self.ig.dialog)
        self.assertEqual(self.ig.dialog['go'][0], 'CLOSE GAME & INSTALL')
        self.assertEqual(self.ig.dialog['cancel'], 'WHEN I CLOSE THE GAME')

        self.ig.click('cancel')
        self.assertIsNone(self.ig.dialog)
        btns = _buttons(ig_community.page(self.ig))
        self.assertEqual(btns['community.go:acrdaily-london']['s'], 'CLOSE GAME & INSTALL  ›')
        self.assertEqual(btns['community.cancel:acrdaily-london']['s'], 'CANCEL')

        self.ig.click('community.cancel:acrdaily-london')
        self.assertNotIn('acrdaily-london', self.a._community_pending)
        self.assertEqual(_buttons(ig_community.page(self.ig))['community.go:acrdaily-london']['s'], 'INSTALL  ›')

    def test_remove_show_showonly_and_all_confirm_close_and_relaunch(self):
        cat = {'categories': [{'id': 'tracks', 'name': 'Tracks',
                               'items': [dict(LONDON, group='acrdaily'), SANDO]},
                              {'id': 'cars', 'name': 'Cars', 'items': []}]}
        mans = {'acrdaily-london': dict(MAN), 'sando-chile-biobio': communityui.community.manifest(SANDO)}
        after_jobs = []
        self.load_catalog(cat=cat, mans=mans, switch={'acrdaily': 'on', 'sando': 'on'})

        with mock.patch.object(self.a.root, 'after', side_effect=lambda ms, fn: after_jobs.append(fn) or len(after_jobs)), \
                mock.patch.object(communityui.saveslot, 'ask_game_to_quit') as quit_game, \
                mock.patch.object(ig_community.saveslot, 'launch_game') as launch_game:
            # 1) Installed -> CLOSE GAME & REMOVE -> uninstall + relaunch
            self.status_map['acrdaily-london'] = 'installed'
            self.ig.click('community.go:acrdaily-london')
            self.assertEqual(self.ig.dialog['go'][0], 'CLOSE GAME & REMOVE')
            with mock.patch.object(ig_community.community, 'uninstall') as uninst, \
                    mock.patch.object(ig_community.community, 'stage_packs', return_value={}), \
                    mock.patch.object(ig_community.stageswitch, 'state', return_value={}):
                self.ig.click('go')
                quit_game.assert_called_once()
                self.game_running = False
                while after_jobs:
                    after_jobs.pop(0)()
            uninst.assert_called_once_with('/games/ACR', 'acrdaily-london')
            launch_game.assert_called_once()

            # 2) Hidden (off) -> CLOSE GAME & SWITCH -> community_show + relaunch
            self.game_running = True
            self.status_map['acrdaily-london'] = 'off'
            self.ig.click('community.go:acrdaily-london')
            self.assertEqual(self.ig.dialog['go'][0], 'CLOSE GAME & SWITCH')
            with mock.patch.object(self.a, 'community_show') as show_one:
                self.ig.click('go')
                self.game_running = False
                while after_jobs:
                    after_jobs.pop(0)()
            show_one.assert_called_once()
            self.assertEqual(launch_game.call_count, 2)

            # 3) SHOW ONLY -> CLOSE GAME & SWITCH -> _community_show_group + relaunch
            self.game_running = True
            self.ig.click('community.showonly:acrdaily')
            self.assertEqual(self.ig.dialog['go'][0], 'CLOSE GAME & SWITCH')
            with mock.patch.object(self.a, '_community_show_group') as show_grp:
                self.ig.click('go')
                self.game_running = False
                while after_jobs:
                    after_jobs.pop(0)()
            show_grp.assert_called_once_with('acrdaily')
            self.assertEqual(launch_game.call_count, 3)

            # 4) ALL TRACKS -> CLOSE GAME & INSTALL -> community_install_all(confirmed=True, relaunch=True)
            self.game_running = True
            self.status_map = {'acrdaily-london': 'install', 'sando-chile-biobio': 'installed'}
            self.ig.click('community.all')
            self.assertEqual(self.ig.dialog['go'][0], 'CLOSE GAME & INSTALL')
            with mock.patch.object(self.a, 'community_install_all') as inst_all:
                self.ig.click('go')
                self.game_running = False
                while after_jobs:
                    after_jobs.pop(0)()
            inst_all.assert_called_once_with(confirmed=True, relaunch=True)
            self.assertEqual(launch_game.call_count, 3)

    def test_community_missing_switches_ingame_tab_and_starts_install(self):
        self.load_catalog()
        self.ig.tab = 'daily'
        with mock.patch.object(communityui.community, 'requires_ok', return_value=False), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True), \
                mock.patch.object(self.a, '_community_start') as start:
            stopped = self.a.community_missing({'requires': 'acrdaily-london'}, 'TT1')
        self.assertTrue(stopped)
        self.assertEqual(self.ig.tab, 'community')
        self.assertEqual(self.a.community_picks.get('tracks'), 'acrdaily-london')
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0]['id'], 'acrdaily-london')


if __name__ == '__main__':
    unittest.main()
