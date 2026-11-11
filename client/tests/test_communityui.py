"""The COMMUNITY page (communityui.py): in the nav and on HOME, its categories, an item's card saying where it stands
in this game, INSTALL putting it in (the download shown as it comes), REMOVE taking it out. On a Tk window that is never
shown; the game's folder, the downloads and the server faked."""
import os
import sys
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import communityui, tabsui  # noqa: E402
from test_inbox import click, texts  # noqa: E402
from test_tabs import Harness  # noqa: E402

LONDON = {'id': 'acrdaily-london', 'kind': 'track', 'name': 'ACR DAILY London', 'subtitle': 'Westminster · 6.1 km · tarmac',
          'description': 'A street stage through Westminster.', 'author': 'ACR DAILY',
          'image': 'https://github.com/x/releases/download/acrdaily-london/card.jpg',
          'manifest': 'https://github.com/x/releases/download/acrdaily-london/manifest.json'}
CATALOG = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [LONDON]}, {'id': 'cars', 'name': 'Cars', 'items': []},
                          {'id': 'skins', 'name': 'Skins', 'items': []}]}
MAN = {'id': 'acrdaily-london', 'version': '1', 'acrBuild': '25170642', 'zipUrl': 'https://x/London.zip',
       'zip': {'name': 'London.zip', 'size': 400 << 20, 'sha256': '0' * 64}, 'files': []}


class Now(object):
    """threading.Thread, run there and then (the download, the install): what it hands to Tk run by update()."""

    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        self.target()


class Community(Harness):
    def setUp(self):
        super().setUp()
        a = self.a
        a.dailies, a.active = {}, 1
        a._build_home_box()
        a._build_community_box()
        a._side, a._main = tk.Frame(self.root), tk.Frame(self.root)
        a._side.pack(side='left')
        a._main.pack(side='left')
        a.refresh_community = mock.Mock()
        self.status = 'install'
        for name, fn in (('status', lambda *_a, **_k: self.status), ('game_running', lambda: False),
                         ('clashes', lambda *_a: [])):
            p = mock.patch.object(communityui.community, name, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(communityui.photos, 'fetch', return_value=None)    # (its picture: not downloaded here)
        p.start()
        self.addCleanup(p.stop)

    def loaded(self):
        a = self.a
        a._set_community(CATALOG, {'acrdaily-london': dict(MAN)}, '', '/games/ACR', '25170642', [])
        self.root.update()

    def card(self):
        return self.a._community_tiles['acrdaily-london']

    def words(self, t):
        cv = t.cv
        return [cv.itemcget(i, 'text') for i in cv.find_all() if cv.type(i) == 'text']

    def test_in_the_nav_the_whole_width(self):
        a = self.a
        a.nav('community')
        self.assertTrue(a.community_view)
        self.assertEqual(self.underlined(), {'community': communityui.COMMUNITY_COLOUR})
        self.assertEqual(['pack' if w.winfo_manager() else '' for w in (a.community_box, a.daily_box, a.board_l, a.tree, a._side)],
                         ['pack', '', '', '', ''])
        a.refresh_community.assert_called_once_with()
        self.assertIn('Loading…', texts(a._community_page))
        a.nav('home')                                        # HOME takes its place; a tab, the view back
        self.assertEqual((a.community_view, a.home_view, a.community_box.winfo_manager()), (False, True, ''))
        a.nav('community')
        a.show_tab('daily')
        self.assertEqual((a.community_view, self.underlined()), (False, {'daily': tabsui._c().WHITE}))
        self.assertEqual(['pack' if w.winfo_manager() else '' for w in (a.community_box, a.daily_box, a._side)],
                         ['', 'pack', 'pack'])
        a.nav('home')                                        # its tile on HOME
        click(a._home_tiles['community'].cv)
        self.assertTrue(a.community_view)

    def test_categories_and_an_items_card(self):
        a = self.a
        a.open_community()
        self.loaded()
        self.assertIn('TRACKS  1', texts(a._community_page.winfo_children()[1].winfo_children()[0]))
        words = self.words(self.card())
        self.assertIn('ACR DAILY London', words)
        self.assertIn('Not installed.', words)
        self.assertTrue(any('400.0 MB' in w for w in words))
        self.assertEqual(self.card().button.cget('text'), 'INSTALL  ›')
        self.assertEqual(a._home_spec('community')['badge'][0], '1 NEW')
        for st, badge, button in (('installed', 'INSTALLED', 'REMOVE'), ('update', 'UPDATE', 'UPDATE  ›'),
                                  ('unavailable', 'SOON', None), ('wait', None, None), ('nogame', None, None)):
            self.status = st
            a._render_community()
            t = self.card()
            self.assertEqual(((t.spec.get('badge') or (None,))[0], t.button.cget('text') if t.spec['button'] else None),
                             (badge, button), st)
        a.community_select('cars')                           # nothing there yet: said
        self.assertNotIn('acrdaily-london', a._community_tiles)
        self.assertIn('No cars yet. They will be here as the community makes them.',
                      texts(a._community_page))

    def test_install_downloads_then_puts_it_in(self):
        a = self.a
        a.open_community()
        self.loaded()
        seen = []

        def download(man, progress=None, cancel=None):
            for i in range(1, 5):
                progress(i * 100 << 20, 400 << 20)
            return '/cache/London.zip'

        def install(game, man, path, force=False):
            seen.append((game, man['id'], path, force))
            self.status = 'installed'
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.community, 'download', side_effect=download), \
                mock.patch.object(communityui.community, 'install', side_effect=install), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said:
            click(self.card().button)
            self.root.update()
        self.assertEqual(seen, [('/games/ACR', 'acrdaily-london', '/cache/London.zip', False)])
        self.assertIn('is installed', said.call_args.args[1])
        self.assertIn('Installed: in the game\'s rally selection.', self.words(self.card()))
        self.assertEqual(self.card().button.cget('text'), 'REMOVE')

    def test_the_game_running_or_other_stages_installed(self):
        a = self.a
        a.open_community()
        self.loaded()
        with mock.patch.object(communityui.community, 'clashes', return_value=['zz_acrxs_registry_P.pak']), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=False) as asked, \
                mock.patch.object(communityui, 'threading') as th:
            click(self.card().button)
        self.assertIn('zz_acrxs_registry_P.pak', asked.call_args.args[1])
        th.Thread.assert_not_called()                        # (no: nothing done)
        with mock.patch.object(communityui.community, 'game_running', return_value=True), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said, \
                mock.patch.object(communityui, 'threading') as th:
            click(self.card().button)
        self.assertIn('Close Assetto Corsa Rally first', said.call_args.args[1])
        th.Thread.assert_not_called()

    def test_remove(self):
        a = self.a
        a.open_community()
        self.status = 'installed'
        self.loaded()
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=True), \
                mock.patch.object(communityui.community, 'uninstall') as out:
            click(self.card().button)
        out.assert_called_once_with('/games/ACR', 'acrdaily-london')


if __name__ == '__main__':
    unittest.main()


class DriveNeedsIt(Community):
    """DRIVE on a stage of a community item that isn't installed: said, COMMUNITY offered, nothing set up."""

    def test_tt_on_london_not_installed(self):
        a = self.a
        a._set_community(CATALOG, {'acrdaily-london': dict(MAN)}, '', '/games/ACR', '25170642', [])
        ch = {'requires': 'acrdaily-london'}
        with mock.patch.object(communityui.community, 'requires_ok', return_value=False) as ok, \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            self.assertTrue(a.community_missing(ch, 'TT1'))
        ok.assert_called_once_with('acrdaily-london', '/games/ACR')
        self.assertIn('TT1 is on ACR DAILY London, a community track', asked.call_args.args[1])
        self.assertTrue(a.community_view)                    # (yes: the page, its tracks)
        self.assertEqual(a.community_cat, 'tracks')
        with mock.patch.object(communityui.community, 'requires_ok', return_value=True):
            self.assertFalse(a.community_missing(ch, 'TT1'))
        self.assertFalse(a.community_missing({'stageId': 'WelesS4HafrenSouthFullForward'}, 'TT2'))
        a._community_game = None                             # (a card drawn before the game is found: not installed)
        self.assertFalse(a.community_ready('acrdaily-london'))
        self.assertTrue(a.community_ready(None))
