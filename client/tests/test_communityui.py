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
          'image': 'https://github.com/x/releases/download/acrdaily-london/card.jpg', 'photo': 'london',
          'manifest': 'https://github.com/x/releases/download/acrdaily-london/manifest.json'}
CATALOG = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [LONDON]}, {'id': 'cars', 'name': 'Cars', 'items': []}]}
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
        self.assertEqual(['pack' if w.winfo_manager() else '' for w in (a.community_box, a.daily_box, a._side)],
                         ['pack', '', ''])
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
        self.assertEqual(self.card().spec['photo'], 'london')      # (its render, bundled: the release's not in yet)
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


LIVERIES = {'liveries': [
    {'id': 7, 'car': 'Peugeot206', 'carName': 'Peugeot 206 WRC', 'title': 'Martini 1983', 'author': 'Xardas',
     'description': 'Stripes.', 'shot': 'https://acrdaily.com/api/liveries/7/shot?v=1', 'go': 'https://acrdaily.com/api/liveries/7/go',
     'direct': True, 'hostName': 'Dropbox', 'stars': 4.5, 'votes': 2, 'mine': 0, 'clicks': 12, 'published': 2},
    {'id': 8, 'car': 'CitroenXsaraWRC', 'carName': 'Citroen Xsara WRC', 'title': 'Halloween', 'author': 'Xardas',
     'description': '', 'shot': None, 'go': 'https://acrdaily.com/api/liveries/8/go', 'direct': False, 'hostName': 'Overtake.gg',
     'stars': 5, 'votes': 1, 'mine': 0, 'clicks': 40, 'published': 3}],
    'cars': [{'id': 'Peugeot206', 'name': 'Peugeot 206 WRC', 'count': 1}, {'id': 'CitroenXsaraWRC', 'name': 'Citroen Xsara WRC', 'count': 1},
             {'id': 'Fiat131Abarth', 'name': 'Fiat 131 Abarth', 'count': 0}], 'limits': {'perCar': 25}}


class Liveries(Community):
    """COMMUNITY > LIVERIES: the drivers' liveries, a car and an order picked, INSTALL (the zip unzipped into the game),
    DOWNLOAD (a page: the browser), REMOVE, RATE."""

    def setUp(self):
        super().setUp()
        import copy
        self.data = copy.deepcopy(LIVERIES)
        self.lv_status = {7: 'install', 8: 'page'}
        p = mock.patch.object(communityui.liveries, 'status', side_effect=lambda lv: self.lv_status[lv['id']])
        p.start()
        self.addCleanup(p.stop)

    def opened(self):
        a = self.a
        a.open_community('liveries')
        a._set_liveries(self.data, '')
        self.root.update()

    def lv(self, livery_id):
        """That livery picked in the list: the card over it (one card: the one picked)."""
        self.a.livery_pick_one(livery_id)
        return self.a._livery_tiles[livery_id]

    def test_the_tab_its_cards_the_car_and_the_order(self):
        a = self.a
        a.open_community('liveries')
        self.assertIn('Loading…', texts(a._community_page))
        a._set_liveries(None, "Couldn't load the liveries (server not reachable).")
        self.assertIn("Couldn't load the liveries (server not reachable).", texts(a._community_page))
        a._set_liveries(self.data, '')
        self.assertIn('LIVERIES  2', texts(a._community_page.winfo_children()[1].winfo_children()[2]))
        self.assertEqual(list(a._livery_tree.get_children()), ['8', '7'])   # top rated first, one under another
        self.assertEqual(list(a._livery_tiles), [8])                      # (the first one picked: its card over the list)
        self.assertEqual(a._livery_tree.item('7', 'values')[:3], ('Martini 1983', 'Peugeot 206 WRC', 'Xardas'))
        martini = self.lv(7)
        words = self.words(martini)
        self.assertIn('Martini 1983', words)
        self.assertTrue(any('★★★★☆ 4.5 · 2 votes' in w and '12 downloads' in w and 'from Dropbox' in w for w in words))
        self.assertIn('Not in your game yet: INSTALL puts it in.', words)
        self.assertEqual(martini.spec['chips'], ['Peugeot 206 WRC'])
        self.assertEqual(martini.button.cget('text'), 'INSTALL  ›')
        self.assertEqual(self.lv(8).button.cget('text'), 'DOWNLOAD  ›')
        pick, order = a._livery_pickers
        self.assertEqual(list(pick.cget('values')), ['All cars (2)', 'Citroen Xsara WRC (1)', 'Peugeot 206 WRC (1)'])
        a.livery_filter(sort='clicks')
        self.assertEqual(list(a._livery_tree.get_children()), ['8', '7'])
        a.livery_filter(sort='new')
        self.assertEqual(list(a._livery_tree.get_children()), ['8', '7'])
        a.livery_filter(car='Peugeot206')
        self.assertEqual(list(a._livery_tree.get_children()), ['7'])
        self.assertEqual(a._livery_pickers[0].get(), 'Peugeot 206 WRC (1)')
        self.data['liveries'] = []
        a.livery_filter(car='')
        self.assertIn('No liveries yet: publish the first one on the website!', texts(a._community_page))

    def test_install_downloads_then_unzips_it_into_the_game(self):
        a = self.a
        self.opened()
        seen = []

        def download(lv, progress=None, cancel=None):
            progress(5 << 20, 10 << 20)
            self.assertIn('Downloading 5.0 MB of 10.0 MB…', self.words(self.lv(7)))
            return '/cache/7.zip'

        def install(lv, path, cars, game=None):
            seen.append((lv['id'], path, [c['id'] for c in cars][:1], game))
            self.lv_status[7] = 'installed'
            return ['/docs/Liveries/Peugeot206/Martini']
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.liveries, 'download', side_effect=download), \
                mock.patch.object(communityui.liveries, 'install', side_effect=install), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said:
            click(self.lv(7).button)
            self.root.update()
        self.assertEqual(seen, [(7, '/cache/7.zip', ['Peugeot206'], '/games/ACR' if a._community_game else None)])
        self.assertIn('Martini 1983 is in your game', said.call_args.args[1])
        self.assertIn('Peugeot206\\Martini', said.call_args.args[1])
        t = self.lv(7)
        self.assertEqual((t.spec['badge'][0], t.button.cget('text')), ('INSTALLED', 'REMOVE'))
        self.assertTrue(any('13 downloads' in w for w in self.words(t)))
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=True), \
                mock.patch.object(communityui.liveries, 'uninstall', side_effect=lambda i: self.lv_status.update({7: 'install'})) as out:
            click(t.button)
        out.assert_called_once_with(7)
        self.assertEqual(self.lv(7).button.cget('text'), 'INSTALL  ›')

    def test_a_link_that_is_a_page_or_a_full_car(self):
        a = self.a
        self.opened()
        with mock.patch.object(communityui.webbrowser, 'open') as web:
            click(self.lv(8).button)
        web.assert_called_once_with('https://acrdaily.com/api/liveries/8/go')
        for kind, detail in (('full', 'the game takes 25 liveries a car'), ('page', 'a web page')):
            err = communityui.liveries.LiveryError(kind, detail)
            with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                    mock.patch.object(communityui.liveries, 'download', side_effect=err), \
                    mock.patch.object(communityui.messagebox, 'showinfo') as said, \
                    mock.patch.object(communityui.messagebox, 'askyesno', return_value=False) as asked:
                click(self.lv(7).button)
                self.root.update()
            box = said if kind == 'full' else asked
            self.assertIn(detail, box.call_args.args[1])
            self.assertEqual(self.lv(7).button.cget('text'), 'INSTALL  ›')

    def test_rate_it(self):
        a = self.a
        self.opened()
        a.api.livery_vote.return_value = {'votes': 3, 'stars': 4.3, 'mine': 4}
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)):
            a.livery_vote(self.data['liveries'][0], 4)
        a.api.livery_vote.assert_called_once_with(7, 4)
        t = self.lv(7)
        self.assertEqual(t._lv_links[0].cget('text'), 'YOUR VOTE ★★★★  ›')
        self.assertTrue(any('4.3 · 3 votes' in w for w in self.words(t)))


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


SANDO = {'id': 'sando-chile-biobio', 'kind': 'track', 'install': 'manager', 'group': 'sando', 'name': 'Chile BioBio',
         'tool': "Sando Rally's Stage Manager",
         'managerName': "Sando Rally's Stage Manager", 'subtitle': 'Sando Rally · gravel · Free Practice',
         'description': 'Two gravel stages.', 'author': 'Sando Rally', 'terms': 'Free for personal play.',
         'stages': [{'stageId': 'SandoChlBioFull'}, {'stageId': 'SandoChlBioRevFull'}],
         'page': 'https://sandorally.com/original-stages',
         'download': {'version': '0.4.2', 'acrBuild': '25170642', 'url': 'https://dl.sandorally.com/x/Sando.zip',
                      'name': 'Sando.zip', 'size': 4319139566, 'sha256': '1' * 64,
                      'manager': 'Sando-Rally-Original-Stage-Manager.exe'}}
WRCG = {'id': 'wrcg-stage-exporter', 'kind': 'track', 'install': 'link', 'group': 'wrcg', 'name': 'WRC Generations stages',
        'tool': 'Stage-Exporter',
        'subtitle': 'Stage-Exporter', 'description': 'From your own WRC Generations.', 'author': 'Faviogames',
        'stages': [{'stageId': 'WrcgEsSS1Full'}, {'stageId': 'WrcgEsSS1RFull'}, {'stageId': 'WrcgSeSS3Full'}],
        'page': 'https://github.com/Faviogames/Stage-Exporter'}
TOOLS = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [SANDO, WRCG]}, {'id': 'cars', 'name': 'Cars', 'items': []}]}


class OtherTools(Harness):
    """Other tools' stages (the test builds): Sando's (INSTALL: the official download, unpacked, Sando's Stage Manager
    opened; MANAGE: it again) and Stage-Exporter's (GET IT: its page). Only one tool's stages show at a time: said."""

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
        for name, value in (('game_running', False), ('manager_exe', None), ('space_needed', [])):
            p = mock.patch.object(communityui.community, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(communityui.photos, 'fetch', return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def loaded(self, packs=None):
        a = self.a
        mans = {'sando-chile-biobio': communityui.community.manifest(SANDO), 'wrcg-stage-exporter': None}
        a._set_community(TOOLS, mans, '', '/games/ACR', '25170642', [], packs or {})
        self.root.update()

    def card(self, item_id):
        """That item picked in the list: the card over it (one card: the one picked)."""
        self.a.community_pick(item_id)
        return self.a._community_tiles[item_id]

    def words(self, t):
        return [t.cv.itemcget(i, 'text') for i in t.cv.find_all() if t.cv.type(i) == 'text']

    def test_the_cards_where_they_stand(self):
        a = self.a
        a.open_community()
        self.loaded()
        self.assertEqual(list(a._community_tree.get_children()), ['sando-chile-biobio', 'wrcg-stage-exporter'])
        self.assertEqual(a._community_tree.item('sando-chile-biobio', 'values')[3:], ('4.0 GB', 'Not installed'))
        sando = self.card('sando-chile-biobio')
        self.assertEqual(sando.button.cget('text'), 'INSTALL  ›')
        self.assertTrue(any("INSTALL downloads it from dl.sandorally.com (4.0 GB) and opens Sando Rally's Stage Manager"
                            in w for w in self.words(sando)))
        self.assertEqual(self.card('wrcg-stage-exporter').button.cget('text'), 'GET IT  ›')
        self.assertEqual(a._home_spec('community')['badge'][0], '1 NEW')      # (Sando's: one to install)
        self.loaded({'a.utoc': ['SandoChlBioFull', 'SandoChlBioRevFull'], 'b.utoc': ['WrcgSeSS3Full']})
        self.assertEqual(a._community_tree.item('wrcg-stage-exporter', 'values')[4], 'Installed')
        wrcg = self.card('wrcg-stage-exporter')
        self.assertEqual(wrcg.button.cget('text'), 'OPEN PAGE')
        self.assertTrue(any('1 of its 3 stages is in your game.' in w for w in self.words(wrcg)))
        sando = self.card('sando-chile-biobio')
        self.assertEqual((sando.button.cget('text'), sando.spec['badge'][0]), ('MANAGE', 'INSTALLED'))
        # both in the game: only one tool's show, said over the cards and on them
        said = texts(a._community_page)
        self.assertTrue(any("Only one tool's stages show in the game at a time" in w and "stages from Sando Rally's "
                            'Stage Manager and Stage-Exporter' in w for w in said), said)
        self.assertTrue(any("Another tool's stages are in the game too" in w for w in self.words(sando)))
        self.loaded({'a.utoc': ['SandoChlBioFull']})
        self.assertFalse(any("Only one tool's stages" in w for w in texts(a._community_page)))

    def test_install_downloads_unpacks_and_opens_the_manager(self):
        a = self.a
        a.open_community()
        self.loaded()
        steps, proc = [], mock.Mock()

        def download(man, progress=None, cancel=None):
            progress(2 << 30, 4 << 30)
            steps.append('download')
            return '/cache/Sando.zip'

        def unpack(man, path, progress=None):
            progress(50, 100)
            steps.append(('unpack', path))

        def opened(man):
            steps.append('manager')
            return proc
        installed = {'a.utoc': ['SandoChlBioFull', 'SandoChlBioRevFull']}
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.community, 'download', side_effect=download), \
                mock.patch.object(communityui.community, 'unpack', side_effect=unpack), \
                mock.patch.object(communityui.community, 'open_manager', side_effect=opened), \
                mock.patch.object(communityui.community, 'stage_packs', return_value=installed), \
                mock.patch.object(communityui.community, 'manager_exe',
                                  side_effect=lambda man: '/x/m.exe' if len(steps) > 1 else None), \
                mock.patch.object(communityui.community, 'download_size', return_value=4 << 30), \
                mock.patch.object(communityui.community, 'delete_download') as gone, \
                mock.patch.object(communityui.messagebox, 'askyesno', side_effect=[True, False]) as asked:
            click(self.card('sando-chile-biobio').button)
            self.root.update()
        self.assertEqual(steps, ['download', ('unpack', '/cache/Sando.zip'), 'manager'])
        self.assertIn('Free for personal play.', asked.call_args_list[0].args[1])       # (its terms, before anything)
        self.assertIn('Keep its download (4.0 GB)', asked.call_args_list[1].args[1])
        gone.assert_called_once()                             # (no: let go)
        proc.wait.assert_called_once()
        self.assertEqual(self.card('sando-chile-biobio').button.cget('text'), 'MANAGE')

    def test_manage_opens_the_manager_and_the_game_running_waits(self):
        a = self.a
        a.open_community()
        self.loaded({'a.utoc': ['SandoChlBioFull']})
        with mock.patch.object(communityui.community, 'manager_exe', return_value='/x/m.exe'), \
                mock.patch.object(communityui.community, 'game_running', return_value=True), \
                mock.patch.object(communityui.community, 'open_manager') as opened, \
                mock.patch.object(communityui.messagebox, 'showinfo') as said:
            click(self.card('sando-chile-biobio').button)
        opened.assert_not_called()
        self.assertIn("Sando Rally's Stage Manager changes nothing while the game runs", said.call_args.args[1])
        # its download gone: MANAGE offers it again
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=False) as asked, \
                mock.patch.object(communityui, 'threading') as th:
            click(self.card('sando-chile-biobio').button)
        self.assertIn("comes with the stage's download, which isn't on this PC any more", asked.call_args.args[1])
        th.Thread.assert_not_called()

    def test_not_enough_space_downloads_nothing(self):
        a = self.a
        a.open_community()
        self.loaded()
        with mock.patch.object(communityui.community, 'space_needed', return_value=[('C:\\Users\\me\\AppData', 3 << 30)]), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said, \
                mock.patch.object(communityui, 'threading') as th:
            click(self.card('sando-chile-biobio').button)
        self.assertIn('Not enough free space: 3.0 GB more is needed', said.call_args.args[1])
        th.Thread.assert_not_called()

    def test_get_it_opens_the_tools_page(self):
        a = self.a
        a.open_community()
        self.loaded()
        with mock.patch.object(communityui.webbrowser, 'open') as web:
            click(self.card('wrcg-stage-exporter').button)
        web.assert_called_once_with('https://github.com/Faviogames/Stage-Exporter')


class CommunityList(OtherTools):
    """COMMUNITY's lists as a game's server browser (from 0.1.6): the one picked in full over the list, every item a
    row under it; a click picks one, a double click takes its first step (never REMOVE or MANAGE)."""

    def test_a_row_picked_and_a_double_click(self):
        a = self.a
        a.open_community()
        self.loaded({'a.utoc': ['SandoChlBioFull', 'SandoChlBioRevFull']})
        tree = a._community_tree
        self.assertEqual(str(tree.cget('height')), '2')               # (as tall as its rows: the page scrolls)
        self.assertEqual(tree.selection(), ('sando-chile-biobio',))
        tree.selection_set('wrcg-stage-exporter')                     # a click: its card over the list
        a._community_row_picked()
        self.assertEqual(list(a._community_tiles), ['wrcg-stage-exporter'])
        self.assertEqual(a.community_picks['tracks'], 'wrcg-stage-exporter')
        with mock.patch.object(communityui.webbrowser, 'open') as web:
            a._community_row_go()                                     # Enter (or a double click): GET IT
        web.assert_called_once_with('https://github.com/Faviogames/Stage-Exporter')
        tree.selection_set('sando-chile-biobio')
        a._community_row_picked()
        with mock.patch.object(a, 'community_manager') as manager:
            a._community_row_go()                                     # installed: MANAGE only from its card
        manager.assert_not_called()
        a._render_community()                                         # (drawn again: the one picked stays picked)
        self.assertEqual(a._community_tree.selection(), ('sando-chile-biobio',))


class LiveryUnpack(Liveries):
    def test_a_rar_windows_cant_unpack_offers_its_page(self):
        a = self.a
        self.opened()
        lv = dict(self.data['liveries'][0], link='https://modscloud.net/assetto-corsa-rally/acr-skins/x/')
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked, \
                mock.patch.object(communityui.webbrowser, 'open') as web:
            a._livery_done(lv, [], communityui.liveries.LiveryError('unpack', 'tar failed'))
        self.assertIn("comes as a .rar or .7z file, and Windows on this PC can't unpack it (tar failed)", asked.call_args.args[1])
        web.assert_called_once_with(lv['go'])
