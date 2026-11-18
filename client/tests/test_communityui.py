"""The COMMUNITY page (communityui.py): in the nav and on HOME, its categories, an item's card saying where it stands
in this game, INSTALL putting it in (the download shown as it comes), REMOVE taking it out. On a Tk window that is never
shown; the game's folder, the downloads and the server faked."""
import os
import sys
import tempfile
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
_SAVE = mock.patch.object(communityui.saveslot, 'SAVE', os.path.join(tempfile.mkdtemp(), 'PlayerDataSaveSlot.sav'))


def setUpModule():
    """The game's save never the player's own here (the page sets a Rally Weekend on a hidden set's calendar back)."""
    _SAVE.start()


def tearDownModule():
    _SAVE.stop()


class RallyWeekendGuard(unittest.TestCase):
    """A Rally Weekend on a calendar of a set the switch just hid is set back to one of the game's own (the game's
    calendar editor crashes on it); one on a set still shown, the game's own, or one in progress: left alone."""

    def test_set_back_only_when_its_calendar_is_gone(self):
        from test_rallyweekend import fake_save
        page = mock.Mock(_community_game='/games/ACR')
        london = fake_save([(0, 'AcrXsLn02r0FullForward', 43200, 'ServiceParkDefault')], preset='AcrXsLnWeekendShort')
        written = []
        with mock.patch.object(communityui.community, 'game_running', return_value=False), \
                mock.patch.object(communityui.saveslot, 'read_save', return_value=london), \
                mock.patch.object(communityui.saveslot, 'replace', side_effect=written.append), \
                mock.patch.object(communityui.stagecalendars, 'present', return_value=[]):
            with mock.patch.object(communityui.stageswitch, 'state', return_value={'acrdaily': 'on', 'wrcg': 'off'}):
                communityui.CommunityUI._rally_weekend_guard(page)
            self.assertEqual(written, [])                                      # (London shown: its calendar is there)
            with mock.patch.object(communityui.stageswitch, 'state', return_value={'acrdaily': 'off', 'wrcg': 'on'}):
                communityui.CommunityUI._rally_weekend_guard(page)
            self.assertEqual(len(written), 1)
            w = communityui.rallyweekend.read_weekend(written[0])
            self.assertEqual(w['preset'], 'WalesWeekendShort')                 # (one of the game's own)


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

        during = []

        def install(game, man, path, force=False, progress=None):
            seen.append((game, man['id'], path, force))
            progress('install', 0.5)                          # how far: said on the card, with a bar
            self.root.update()
            during.append((self.words(self.card()), self.card().spec.get('progress')))
            self.status = 'installed'
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.community, 'download', side_effect=download), \
                mock.patch.object(communityui.community, 'install', side_effect=install), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said:
            click(self.card().button)
            self.root.update()
        self.assertEqual(seen, [('/games/ACR', 'acrdaily-london', '/cache/London.zip', False)])
        steps = 3 if (self.a._community_man or {}).get('acrdaily-london', {}).get('assemble') else 2
        self.assertIn('Step %d of %d · putting it into the game · 50%%' % (steps, steps), during[0][0])
        self.assertEqual(during[0][1], 0.5)
        self.assertIsNone(self.card().spec.get('progress'))   # (done: no bar)
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

    def test_its_authors_page_a_link_on_its_card(self):
        """An item's `support` (Hattori Rally's Patreon post for Lousã): a link under its words that opens that page,
        its credits a line of their own. No link without one, nor for an address that isn't https."""
        a = self.a
        a.open_community()
        self.loaded()
        self.assertIsNone(getattr(self.card(), '_support', None))
        url = 'https://www.patreon.com/x/posts/lousa-1'

        def with_item(**extra):
            item = dict(LONDON, author='Hattori Rally', credits='By Hattori Rally.', **extra)
            a._set_community({'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [item]},
                                             {'id': 'cars', 'name': 'Cars', 'items': []}]},
                             {'acrdaily-london': dict(MAN)}, '', '/games/ACR', '25170642', [])
            self.root.update()
            return self.card()
        t = with_item(support={'name': 'Patreon', 'url': url})
        self.assertIn('Credits: By Hattori Rally.', self.words(t))
        self.assertEqual(t._support.cget('text'), 'Hattori Rally on Patreon  ›')
        self.assertIn('Hattori Rally on Patreon  ›', self.words(t) + texts(t.cv))    # (drawn on the card)
        with mock.patch.object(communityui.webbrowser, 'open') as web:
            t._support._cmd()
        web.assert_called_once_with(url)
        self.assertIsNone(getattr(with_item(support={'name': 'Patreon', 'url': 'http://x'}), '_support', None))
        self.assertIsNone(getattr(with_item(), '_support', None))


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
STUDIO_PAGE = 'https://www.patreon.com/AlbertPalahi/posts/wrc-generations-175220013'
EXPORTER_PAGE = 'https://github.com/Faviogames/Stage-Exporter'
WRCG = {'id': 'wrcg-stages', 'kind': 'track', 'install': 'link', 'group': 'wrcg', 'name': 'WRC Generations stages',
        'tool': 'Stage Studio / Stage-Exporter',
        'tools': [{'id': 'stage-studio', 'name': 'Stage Studio', 'author': 'Albert Palahi', 'stages': 2, 'page': STUDIO_PAGE},
                  {'id': 'stage-exporter', 'name': 'Stage-Exporter', 'author': 'Faviogames', 'stages': 3,
                   'page': EXPORTER_PAGE}],
        'subtitle': 'Stage Studio or Stage-Exporter', 'description': 'From your own WRC Generations.',
        'author': 'Albert Palahi, Faviogames',
        'stages': [{'stageId': 'WrcgEsSS1Full'}, {'stageId': 'WrcgEsSS1RFull'}, {'stageId': 'WrcgSeSS3Full'}],
        'page': STUDIO_PAGE}
TOOLS = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [SANDO, WRCG]}, {'id': 'cars', 'name': 'Cars', 'items': []}]}


class ToolsHarness(Harness):
    """The COMMUNITY page with other tools' stages (the test builds) in its catalogue."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(communityui.settings, 'DIR', tempfile.mkdtemp())     # (never the real settings)
        p.start()
        self.addCleanup(p.stop)
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
        mans = {'sando-chile-biobio': communityui.community.manifest(SANDO), 'wrcg-stages': None}
        a._set_community(TOOLS, mans, '', '/games/ACR', '25170642', [], packs or {})
        self.root.update()

    def card(self, item_id):
        """That item picked in the list: the card over it (one card: the one picked)."""
        self.a.community_pick(item_id)
        return self.a._community_tiles[item_id]

    def words(self, t):
        return [t.cv.itemcget(i, 'text') for i in t.cv.find_all() if t.cv.type(i) == 'text']



class OtherTools(ToolsHarness):
    """Other tools' stages (the test builds): Sando's (INSTALL: the official download, unpacked, Sando's Stage Manager
    opened; MANAGE: it again) and a card of tools' links (GET IT: which tool, then its page). Only one tool's stages
    show at a time: said."""

    def test_the_cards_where_they_stand(self):
        a = self.a
        a.open_community()
        self.loaded()
        self.assertEqual(list(a._community_tree.get_children()), ['sando-chile-biobio', 'wrcg-stages'])
        self.assertEqual(a._community_tree.item('sando-chile-biobio', 'values')[3:], ('4.0 GB', 'Not installed'))
        sando = self.card('sando-chile-biobio')
        self.assertEqual(sando.button.cget('text'), 'INSTALL  ›')
        self.assertTrue(any("INSTALL downloads it from dl.sandorally.com (4.0 GB), and Sando Rally's Stage Manager "
                            'installs it.' in w for w in self.words(sando)))
        self.assertEqual(self.card('wrcg-stages').button.cget('text'), 'GET IT  ›')
        self.assertTrue(any('One of its tools builds it on your PC from a game you own: GET IT picks one' in w
                            for w in self.words(self.card('wrcg-stages'))))
        self.assertEqual(a._home_spec('community')['badge'][0], '1 NEW')      # (Sando's: one to install)
        self.loaded({'a.utoc': ['SandoChlBioFull', 'SandoChlBioRevFull'], 'b.utoc': ['WrcgSeSS3Full']})
        self.assertEqual(a._community_tree.item('wrcg-stages', 'values')[4], 'Installed')
        wrcg = self.card('wrcg-stages')
        self.assertEqual(wrcg.button.cget('text'), 'OPEN PAGE')
        self.assertTrue(any('1 of its 3 stages is in your game.' in w for w in self.words(wrcg)))
        sando = self.card('sando-chile-biobio')
        self.assertEqual((sando.button.cget('text'), sando.spec['badge'][0]), ('MANAGE', 'INSTALLED'))
        # both in the game: only one tool's show, said over the cards and on them
        said = texts(a._community_page)
        self.assertTrue(any("Only one tool's stages show in the game at a time" in w and "stages from Sando Rally's "
                            'Stage Manager and Stage Studio / Stage-Exporter' in w for w in said), said)
        self.assertTrue(any("Another tool's stages are in the game too" in w for w in self.words(sando)))
        self.loaded({'a.utoc': ['SandoChlBioFull']})
        self.assertFalse(any("Only one tool's stages" in w for w in texts(a._community_page)))

    def test_install_downloads_unpacks_and_its_manager_installs_it(self):
        """INSTALL: the official download, unpacked, and Sando's own Stage Manager run to install it (its window shows
        it working, community.manager_install): nothing for the player to click."""
        a = self.a
        a.open_community()
        self.loaded()
        steps = []

        def download(man, progress=None, cancel=None):
            progress(2 << 30, 4 << 30)
            steps.append('download')
            return '/cache/Sando.zip'

        def unpack(man, path, progress=None):
            progress(50, 100)
            steps.append(('unpack', path))

        def manager_install(man, game, it):
            steps.append(('manager installs it', game))
        installed = {'a.utoc': ['SandoChlBioFull', 'SandoChlBioRevFull']}
        with mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.community, 'download', side_effect=download), \
                mock.patch.object(communityui.community, 'unpack', side_effect=unpack), \
                mock.patch.object(communityui.community, 'open_manager') as opened, \
                mock.patch.object(communityui.community, 'manager_install', side_effect=manager_install), \
                mock.patch.object(communityui.community, 'stage_packs', return_value=installed), \
                mock.patch.object(communityui.community, 'manager_exe',
                                  side_effect=lambda man: '/x/m.exe' if len(steps) > 1 else None), \
                mock.patch.object(communityui.community, 'delete_download') as gone, \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            click(self.card('sando-chile-biobio').button)
            self.root.update()
        self.assertEqual(steps, ['download', ('unpack', '/cache/Sando.zip'), ('manager installs it', '/games/ACR')])
        opened.assert_not_called()                            # (not left for the player to click Install)
        self.assertIn('Free for personal play.', asked.call_args_list[0].args[1])       # (its terms, before anything)
        self.assertEqual(asked.call_count, 1)                 # (nothing more asked: its download kept for the manager)
        gone.assert_not_called()
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

    def test_get_it_asks_which_tool_then_opens_its_page(self):
        a = self.a
        a.open_community()
        self.loaded()
        button = self.card('wrcg-stages').button
        with mock.patch.object(communityui.tk.Menu, 'tk_popup') as popup, \
                mock.patch.object(communityui.webbrowser, 'open') as web:
            menus = []
            real = a._community_page_open
            with mock.patch.object(a, '_community_page_open', side_effect=lambda *x: menus.append(real(*x))):
                click(button)
        web.assert_not_called()                                       # (not yet: which tool?)
        m = menus[0]
        self.assertEqual([m.entrycget(i, 'label') for i in range(m.index('end') + 1)],
                         ['Stage Studio  ·  by Albert Palahi  ·  2 stages  ·  patreon.com',
                          'Stage-Exporter  ·  by Faviogames  ·  3 stages  ·  github.com'])
        self.assertEqual(popup.call_args.args, (button.winfo_rootx(), button.winfo_rooty() + button.winfo_height()))
        with mock.patch.object(communityui.webbrowser, 'open') as web:
            m.invoke(0)
        web.assert_called_once_with(STUDIO_PAGE)
        with mock.patch.object(communityui.webbrowser, 'open') as web:
            m.invoke(1)
        web.assert_called_once_with(EXPORTER_PAGE)

    def test_a_card_of_one_tool_opens_its_page_at_once(self):
        a = self.a
        one = dict(WRCG, tools=WRCG['tools'][1:])
        with mock.patch.object(communityui.tk.Menu, 'tk_popup') as popup, \
                mock.patch.object(communityui.webbrowser, 'open') as web:
            self.assertIsNone(a._community_page_open(one))
            a._community_page_open({k: v for k, v in WRCG.items() if k != 'tools'})   # (an older server: its page)
        popup.assert_not_called()
        self.assertEqual([c.args[0] for c in web.call_args_list], [EXPORTER_PAGE, STUDIO_PAGE])


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
        tree.selection_set('wrcg-stages')                     # a click: its card over the list
        a._community_row_picked()
        self.assertEqual(list(a._community_tiles), ['wrcg-stages'])
        self.assertEqual(a.community_picks['tracks'], 'wrcg-stages')
        with mock.patch.object(communityui.tk.Menu, 'tk_popup') as popup, \
                mock.patch.object(communityui.webbrowser, 'open') as web:
            a._community_row_go()                                     # Enter (or a double click): GET IT, which tool
        popup.assert_called_once()
        web.assert_not_called()
        tree.selection_set('sando-chile-biobio')
        a._community_row_picked()
        with mock.patch.object(a, 'community_manager') as manager:
            a._community_row_go()                                     # installed: MANAGE only from its card
        manager.assert_not_called()
        a._render_community()                                         # (drawn again: the one picked stays picked)
        self.assertEqual(a._community_tree.selection(), ('sando-chile-biobio',))


EXPORTER = {'id': 'stage-exporter', 'name': 'Stage Exporter', 'author': 'Albert Palahi', 'version': '1.0.0',
            'commit': 'a' * 40, 'url': 'https://codeload.github.com/Faviogames/Stage-Exporter/zip/' + 'a' * 40,
            'files': 67, 'payloadSha256': 'b' * 64, 'minutes': 40,
            'base': {'name': 'Sando Rally Stage Export Tool', 'version': '0.3.7'}}


def wrcg_item(slug, stage_id, name):
    return {'id': 'wrcg-' + slug.replace('_', '-'), 'kind': 'track', 'install': 'export', 'exporter': 'stage-exporter',
            'slug': slug, 'group': 'wrcg', 'tool': 'Stage Exporter', 'name': name,
            'subtitle': 'WRC Generations · Spain · tarmac', 'description': 'Made on your PC.', 'author': 'Albert Palahi',
            'stages': [{'stageId': stage_id, 'name': name}], 'terms': 'For your own play: never share it.'}


RIUDECANYES, SAVALLA = wrcg_item('es_ss1', 'WrcgEsSS1Full', 'Riudecanyes'), wrcg_item('es_ss4', 'WrcgEsSS4Full', 'Savallà')
MADE = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [SANDO, RIUDECANYES, SAVALLA]},
                       {'id': 'cars', 'name': 'Cars', 'items': []}], 'tools': {'stage-exporter': EXPORTER}}


class FakeJob(object):
    """stageexport.Job: wait() hands its lines to on_line, as a run prints them."""

    def __init__(self, lines, ok=True, on_line=None):
        self.lines, self.ok, self.on_line = lines, ok, on_line
        self.cancelled, self.log, self.no_space = False, '/app/logs/stage-export-1.log', None
        self.cancel = mock.Mock(side_effect=lambda: setattr(self, 'cancelled', True))

    def wait(self):
        for line in self.lines:
            self.on_line(line) if self.on_line else None
        return self.ok and not self.cancelled

    def last(self, n=3):
        return self.lines[-n:]


class MadeOnThisPC(ToolsHarness):
    """WRC Generations' stages, one row each: INSTALL finds what it needs, puts Stage Exporter in the first time, makes
    the stage (its progress said) and it is INSTALLED; more wait their turn; CANCEL stops one; REMOVE takes it out;
    FIND TOOL shows where Sando's tool is."""

    def setUp(self):
        super().setUp()
        self.home = tempfile.mkdtemp()
        for p in (mock.patch.object(communityui.settings, 'DIR', self.home),
                  mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)),
                  mock.patch.object(communityui.stageexport, 'current_run', return_value=None)):
            p.start()
            self.addCleanup(p.stop)
        self.env = {'wrcg': '/games/WRCG', 'tool': '/tools/Sando', 'ready': False, 'pack': []}

    def loaded(self, packs=None, env=None):
        a = self.a
        a._set_community(MADE, {'sando-chile-biobio': communityui.community.manifest(SANDO)}, '', '/games/ACR',
                         '25170642', [], packs or {}, env or self.env)
        self.root.update()

    def row(self, item_id):
        return self.a._community_tree.item(item_id, 'values')[4]

    def test_where_each_stands(self):
        a = self.a
        a.open_community()
        self.loaded()
        self.assertEqual(self.row('wrcg-es-ss1'), 'Not installed')
        card = self.card('wrcg-es-ss1')
        self.assertEqual(card.button.cget('text'), 'INSTALL  ›')
        self.assertTrue(any('INSTALL makes it on your PC from your WRC Generations: about 40 minutes' in w
                            for w in self.words(card)))
        self.assertEqual(a._home_spec('community')['badge'][0], '1 NEW')      # (Sando's only: made ones aren't "new")
        self.loaded(env=dict(self.env, tool=None))
        self.assertEqual(self.row('wrcg-es-ss1'), 'Needs the export tool')
        card = self.card('wrcg-es-ss1')
        self.assertEqual(card.button.cget('text'), 'FIND TOOL  ›')
        self.assertTrue(any('Sando no longer offers it: if you have it (its folder or its zip), FIND TOOL' in w
                            for w in self.words(card)))
        self.loaded(env=dict(self.env, wrcg=None))
        self.assertEqual(self.row('wrcg-es-ss1'), 'Needs WRC Generations')
        card = self.card('wrcg-es-ss1')
        self.assertEqual(card.button.cget('text'), 'FIND GAME  ›')
        self.assertTrue(any("isn't found on this PC (Steam or Epic Games). If it is somewhere else, FIND GAME" in w
                            for w in self.words(card)))
        self.loaded({'x.utoc': ['WrcgEsSS1Full']}, env=dict(self.env, pack=['es_ss1']))
        card = self.card('wrcg-es-ss1')
        self.assertEqual((card.button.cget('text'), card.spec['badge'][0]), ('REMOVE', 'INSTALLED'))
        self.assertTrue(any('Installed. REMOVE takes it out; the other stages stay.' in w for w in self.words(card)))

    def test_install_makes_it_and_it_is_installed(self):
        a = self.a
        a.open_community()
        self.loaded()
        said, jobs = [], []
        real_say = a._community_say
        lines = ['wr export es_ss1', 'WRCG files: x', '[es_ss1] WRCG export', '[es_ss1] WRCG export done',
                 'building es_ss1 (1/1)', '[es_ss1] built in 30 s', 'pack: es_ss1 (es_ss1 exported again) in 41 min']

        def start(tool, args, on_line=None, watch=()):
            jobs.append((tool, args))
            return FakeJob(lines, on_line=on_line)
        clock = iter(range(0, 1000, 5))
        with mock.patch.object(communityui.stageexport, 'ensure_addon',
                               side_effect=lambda tool, ex, game, wrcg, say: [say('get'), say('setup')]) as addon, \
                mock.patch.object(communityui.stageexport, 'start', side_effect=start), \
                mock.patch.object(communityui.stageexport, 'environment',
                                  return_value=dict(self.env, ready=True, pack=['es_ss1'])), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={'x.utoc': ['WrcgEsSS1Full']}), \
                mock.patch.object(communityui.time, 'time', side_effect=lambda: next(clock)), \
                mock.patch.object(a, '_community_say', side_effect=lambda i, t: [said.append(t), real_say(i, t)]), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            click(self.card('wrcg-es-ss1').button)
            self.root.update()
        ask = asked.call_args.args[1]
        self.assertIn('Riudecanyes is made on your PC from your own WRC Generations with Stage Exporter (by Albert '
                      'Palahi) and Sando Rally Stage Export Tool 0.3.7', ask)
        self.assertIn('Its terms: For your own play: never share it.', ask)
        self.assertEqual(addon.call_args.args[:4], ('/tools/Sando', EXPORTER, '/games/ACR', '/games/WRCG'))
        self.assertEqual(jobs, [('/tools/Sando', ['export', 'es_ss1'])])
        self.assertIn('Getting Stage Exporter…', said)
        self.assertIn('Setting up Stage Exporter…', said)
        self.assertTrue(any(t and t.startswith('Taking it from WRC Generations…') for t in said), said)
        self.assertTrue(any(t and t.startswith('Building it for Assetto Corsa Rally…') for t in said), said)
        self.assertEqual(said[-1], None)
        card = self.card('wrcg-es-ss1')
        self.assertEqual((card.button.cget('text'), card.spec['badge'][0]), ('REMOVE', 'INSTALLED'))
        self.assertEqual(self.row('wrcg-es-ss1'), 'Installed')
        self.assertTrue(communityui.settings.load()[communityui.stageexport.OK_SETTING])
        asked.reset_mock()
        with mock.patch.object(communityui.stageexport, 'ensure_addon'), \
                mock.patch.object(communityui.stageexport, 'start', side_effect=start), \
                mock.patch.object(communityui.stageexport, 'environment', return_value=self.env), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={}), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            a.community_export(SAVALLA)
        asked.assert_not_called()                                     # (its terms: asked once)

    def test_more_wait_their_turn_and_cancel(self):
        a = self.a
        a.open_community()
        self.loaded()
        held = FakeJob(['wr export es_ss1'])
        held.wait = mock.Mock(return_value=True)
        started = []

        def start(tool, args, on_line=None, watch=()):
            started.append(args)
            return held if len(started) == 1 else FakeJob(['pack: es_ss4'], on_line=on_line)
        # the first one being made: the thread of its run held (its _export_wait returns later)
        waits = []
        with mock.patch.object(communityui.stageexport, 'ensure_addon'), \
                mock.patch.object(communityui.stageexport, 'start', side_effect=start), \
                mock.patch.object(type(a), '_export_wait', staticmethod(lambda job, game: waits.append(job))), \
                mock.patch.object(communityui.stageexport, 'environment', return_value=self.env), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={}):
            a.community_export(RIUDECANYES)
        # (the run's thread came back at once with nothing: as though still going, it is put back as going)
        a._export_now = {'it': RIUDECANYES, 'job': held, 'progress': communityui.stageexport.Progress('es_ss1'),
                         'stop': False}
        a._community_say('wrcg-es-ss1', 'Taking it from WRC Generations…  20%')
        a.community_export(SAVALLA)
        card = self.card('wrcg-es-ss4')
        self.assertEqual(card.button.cget('text'), 'CANCEL')
        self.assertTrue(any('Next in line: it starts when Riudecanyes is done.' in w for w in self.words(card)))
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'CANCEL')
        # Riudecanyes stopped: the game's pack put back; Savallà, next, starts by itself
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=True):
            a.community_export_cancel(RIUDECANYES)
        held.cancel.assert_called_once()
        with mock.patch.object(communityui.stageexport, 'ensure_addon'), \
                mock.patch.object(communityui.stageexport, 'start', side_effect=start), \
                mock.patch.object(communityui.stageexport, 'restore_aside') as back, \
                mock.patch.object(communityui.stageexport, 'environment', return_value=self.env), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={'x.utoc': ['WrcgEsSS4Full']}):
            a._export_done(RIUDECANYES, a._export_wait(held, '/games/ACR'), {}, self.env, held.log)
            back.assert_called_once_with('/games/ACR')
        self.assertEqual(started, [['export', 'es_ss1'], ['export', 'es_ss4']])
        self.assertIsNone(a._export_now)
        self.assertEqual(self.card('wrcg-es-ss4').spec['badge'][0], 'INSTALLED')
        self.warn.assert_not_called()                                 # (stopped: nothing to say)

    def test_a_run_that_fails_is_said_and_the_line_cleared(self):
        a = self.a
        a.open_community()
        self.loaded()
        a._export_now = {'it': RIUDECANYES, 'job': None, 'progress': None, 'stop': False}
        a._export_queue = [SAVALLA]
        err = communityui.stageexport.ExportError('export', 'ERROR: stage build failed')
        with mock.patch.object(communityui.messagebox, 'showwarning') as warned, \
                mock.patch.object(a, 'community_export') as next_one:
            a._export_done(RIUDECANYES, err, {}, self.env, '/app/logs/stage-export-1.log')
        self.assertIn("Couldn't finish Riudecanyes: ERROR: stage build failed", warned.call_args.args[1])
        self.assertIn('What happened is in /app/logs/stage-export-1.log.', warned.call_args.args[1])
        next_one.assert_not_called()
        self.assertEqual(a._export_queue, [])

    def test_a_stage_the_tool_cant_convert_lets_the_line_go_on(self):
        """ZonneBeke (2026-11-17): the tool can't convert a part of it. The next stage in line goes on; said once at
        the end; its card says it can't be made yet, TRY AGAIN, and INSTALL ALL leaves it out."""
        a = self.a
        a.open_community()
        self.loaded()
        a._export_now = {'it': RIUDECANYES, 'job': None, 'progress': None, 'stop': False, 'args': ['export', 'es_ss1']}
        a._export_queue = [SAVALLA]
        why = {'kind': 'turned', 'part': 'BE_SS1_BoucleVille_Road_0'}
        err = communityui.stageexport.ExportError('cantmake', why['part'], why=why)
        failed_env = dict(self.env, failed={'es_ss1': why})
        with mock.patch.object(communityui.messagebox, 'showwarning') as warned, \
                mock.patch.object(a, 'community_export', side_effect=lambda it: setattr(a, '_export_now', {'it': it})) as next_one:
            a._export_done(RIUDECANYES, err, {}, failed_env, '/app/logs/stage-export-1.log')
            next_one.assert_called_once_with(SAVALLA)              # (the line went on)
            warned.assert_not_called()                             # (said when the line is done)
            a._export_done(SAVALLA, None, {}, failed_env, 'log')
        self.assertIn("Riudecanyes can't be made", warned.call_args.args[1])
        self.assertEqual(self.card('wrcg-es-ss1').spec['badge'][0], "CAN'T BE MADE")
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'TRY AGAIN  ›')
        self.assertTrue(any("Can't be made yet" in w for w in self.words(self.card('wrcg-es-ss1'))))
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=False) as asked:
            a.community_export_all()
        self.assertNotIn('Riudecanyes', str(asked.call_args))   # (INSTALL ALL: not counted in)

    def test_remove_takes_it_out(self):
        a = self.a
        a.open_community()
        env = dict(self.env, pack=['es_ss1'])
        self.loaded({'x.utoc': ['WrcgEsSS1Full']}, env=env)
        jobs = []
        with mock.patch.object(communityui.stageexport, 'start',
                               side_effect=lambda tool, args, on_line=None, watch=(): jobs.append(args) or FakeJob(['pack: none'])), \
                mock.patch.object(communityui.stageexport, 'environment', return_value=dict(env, pack=[])), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={}), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            click(self.card('wrcg-es-ss1').button)
        self.assertIn('Take Riudecanyes out of the game?', asked.call_args.args[1])
        self.assertEqual(jobs, [['remove', 'es_ss1']])
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'INSTALL  ›')
        # one another copy of the tool put in: not this one's to take out
        self.loaded({'x.utoc': ['WrcgEsSS1Full']}, env=dict(self.env, pack=[]))
        with mock.patch.object(communityui.messagebox, 'showinfo') as said, \
                mock.patch.object(communityui.stageexport, 'start') as start:
            click(self.card('wrcg-es-ss1').button)
        start.assert_not_called()
        self.assertIn('Riudecanyes was put in the game by another copy of the export tool', said.call_args.args[1])

    def test_find_tool_keeps_its_folder(self):
        a = self.a
        a.open_community()
        self.loaded(env=dict(self.env, tool=None))
        tool = os.path.join(self.home, 'Sando-Rally-Stage-Export-Tool-0.3.7')
        os.makedirs(os.path.join(tool, '_internal'))
        open(os.path.join(tool, communityui.stageexport.WORKER), 'wb').close()
        open(os.path.join(tool, communityui.stageexport.TOOL_EXE), 'wb').close()
        with mock.patch('tkinter.filedialog.askopenfilename',
                        return_value=os.path.join(tool, communityui.stageexport.TOOL_EXE)) as picked:
            click(self.card('wrcg-es-ss1').button)
        self.assertIn('*.zip', str(picked.call_args.kwargs['filetypes']))                 # (or the zip it came in)
        self.assertEqual(communityui.settings.load()[communityui.stageexport.SETTING], tool)
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'INSTALL  ›')
        with mock.patch('tkinter.filedialog.askopenfilename', return_value=os.path.join(self.home, 'Games', 'other.exe')), \
                mock.patch.object(communityui.messagebox, 'showwarning') as warned:
            a.community_find_tool()
        self.assertIn("There's no Stage Export Tool there", warned.call_args.args[1])

    def test_find_tool_takes_the_zip_it_came_in(self):
        a = self.a
        a.open_community()
        self.loaded(env=dict(self.env, tool=None))
        said, real_say = [], a._community_say

        def unpack(path, progress):
            progress(50, 100)
            return '/app/tools/Sando/Sando'
        with mock.patch('tkinter.filedialog.askopenfilename', return_value='/downloads/Sando-Rally-Stage-Export-Tool-0.3.7.zip'), \
                mock.patch.object(communityui.stageexport, 'unpack_tool', side_effect=unpack) as unpacked, \
                mock.patch.object(communityui.stageexport, 'pack', return_value=[]), \
                mock.patch.object(a, '_community_say', side_effect=lambda i, t: [said.append(t), real_say(i, t)]):
            click(self.card('wrcg-es-ss1').button)
        self.assertEqual(unpacked.call_args.args[0], '/downloads/Sando-Rally-Stage-Export-Tool-0.3.7.zip')
        self.assertIn('Unpacking 50%…', said)
        self.assertEqual(communityui.settings.load()[communityui.stageexport.SETTING], '/app/tools/Sando/Sando')
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'INSTALL  ›')
        self.loaded(env=dict(self.env, tool=None))
        with mock.patch('tkinter.filedialog.askopenfilename', return_value='/downloads/photos.zip'), \
                mock.patch.object(communityui.stageexport, 'unpack_tool',
                                  side_effect=communityui.stageexport.ExportError('notool', 'no tool in it')), \
                mock.patch.object(communityui.messagebox, 'showwarning') as warned:
            click(self.card('wrcg-es-ss1').button)
        self.assertIn("There's no Stage Export Tool there", warned.call_args.args[1])

    def test_the_tools_zip_in_downloads_is_unpacked_by_install(self):
        a = self.a
        a.open_community()
        env = dict(self.env, tool=None, toolZip='/downloads/Sando-Rally-Stage-Export-Tool-0.3.7.zip')
        self.loaded(env=env)
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'INSTALL  ›')     # (no FIND TOOL: its zip is there)
        said, real_say = [], a._community_say

        def unpack(path, progress):
            progress(30, 100)
            return '/app/tools/Sando/Sando-Rally-Stage-Export-Tool'
        after = dict(self.env, tool='/app/tools/Sando/Sando-Rally-Stage-Export-Tool', toolZip=None, pack=['es_ss1'])
        with mock.patch.object(communityui.stageexport, 'unpack_tool', side_effect=unpack) as unpacked, \
                mock.patch.object(communityui.stageexport, 'ensure_addon') as addon, \
                mock.patch.object(communityui.stageexport, 'start',
                                  side_effect=lambda tool, args, on_line=None, watch=(): FakeJob(['pack: es_ss1'])) as start, \
                mock.patch.object(communityui.stageexport, 'environment', return_value=after), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={'x.utoc': ['WrcgEsSS1Full']}), \
                mock.patch.object(a, '_community_say', side_effect=lambda i, t: [said.append(t), real_say(i, t)]), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True):
            click(self.card('wrcg-es-ss1').button)
        self.assertEqual(unpacked.call_args.args[0], '/downloads/Sando-Rally-Stage-Export-Tool-0.3.7.zip')
        self.assertIn('Unpacking the Stage Export Tool…  30%', said)
        self.assertEqual(addon.call_args.args[0], '/app/tools/Sando/Sando-Rally-Stage-Export-Tool')
        self.assertEqual(start.call_args.args[:2], ('/app/tools/Sando/Sando-Rally-Stage-Export-Tool', ['export', 'es_ss1']))
        self.assertEqual(communityui.settings.load()[communityui.stageexport.SETTING],
                         '/app/tools/Sando/Sando-Rally-Stage-Export-Tool')            # (kept: found next time)
        self.assertEqual(self.card('wrcg-es-ss1').spec['badge'][0], 'INSTALLED')

    def test_without_the_tool_or_its_zip_install_downloads_it(self):
        """Neither Sando's tool nor its zip on the PC, and the catalogue has a copy of it: INSTALL (no FIND TOOL)
        downloads it, unpacks it here, deletes the download and makes the stage."""
        a = self.a
        a.open_community()
        dl = {'name': 'Sando-Rally-Stage-Export-Tool-0.3.7.zip', 'url': 'https://web.archive.org/web/1id_/x.zip',
              'size': 84427633, 'sha256': 'c' * 64}
        data = dict(MADE, tools={'stage-exporter': dict(EXPORTER, base=dict(EXPORTER['base'], download=dl))})
        a._set_community(data, {}, '', '/games/ACR', '25170642', [], {}, dict(self.env, tool=None, toolZip=None))
        self.root.update()
        self.assertEqual(self.row('wrcg-es-ss1'), 'Not installed')
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'INSTALL  ›')
        said, real_say = [], a._community_say
        zip_path = os.path.join(self.home, 'community', 'Sando-Rally-Stage-Export-Tool-0.3.7.zip')

        def fetch(d, progress):
            os.makedirs(os.path.dirname(zip_path), exist_ok=True)
            open(zip_path, 'wb').close()
            progress(42, 100)
            return zip_path
        after = dict(self.env, tool='/app/tools/Sando/Sando-Rally-Stage-Export-Tool', toolZip=None, pack=['es_ss1'])
        with mock.patch.object(communityui.stageexport, 'fetch_tool', side_effect=fetch) as fetched, \
                mock.patch.object(communityui.stageexport, 'unpack_tool',
                                  return_value='/app/tools/Sando/Sando-Rally-Stage-Export-Tool') as unpacked, \
                mock.patch.object(communityui.stageexport, 'ensure_addon') as addon, \
                mock.patch.object(communityui.stageexport, 'start',
                                  side_effect=lambda tool, args, on_line=None, watch=(): FakeJob(['pack: es_ss1'])), \
                mock.patch.object(communityui.stageexport, 'environment', return_value=after), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={'x.utoc': ['WrcgEsSS1Full']}), \
                mock.patch.object(a, '_community_say', side_effect=lambda i, t: [said.append(t), real_say(i, t)]), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            click(self.card('wrcg-es-ss1').button)
        self.assertIn("Stage Export Tool isn't on this PC: ACR Daily downloads it first (80 MB", asked.call_args.args[1])
        self.assertEqual(fetched.call_args.args[0], dl)
        self.assertIn('Downloading the Stage Export Tool…  42%', said)
        self.assertEqual(unpacked.call_args.args[0], zip_path)
        self.assertFalse(os.path.exists(zip_path))                                       # (unpacked: not kept)
        self.assertEqual(addon.call_args.args[0], '/app/tools/Sando/Sando-Rally-Stage-Export-Tool')
        self.assertEqual(self.card('wrcg-es-ss1').spec['badge'][0], 'INSTALLED')

    def test_with_the_game_open_it_waits_and_starts_by_itself(self):
        a = self.a
        a.open_community()
        self.loaded()
        started = []
        later = []
        with mock.patch.object(communityui.community, 'game_running', return_value=True), \
                mock.patch.object(self.root, 'after', side_effect=lambda ms, fn: later.append(fn)), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said, \
                mock.patch.object(a, '_export_go', side_effect=lambda it, args, *x: started.append(args)):
            click(self.card('wrcg-es-ss1').button)
            a.community_export(SAVALLA)                                # (another: after it)
            said.assert_not_called()                                   # (no "close the game first")
            self.assertEqual(started, [])
            self.assertEqual(self.row('wrcg-es-ss1'), 'Waiting for the game to close')
            card = self.card('wrcg-es-ss1')
            self.assertEqual(card.button.cget('text'), 'CANCEL')
            self.assertTrue(any('Waiting for Assetto Corsa Rally to close: it starts by itself then.' in w
                                for w in self.words(card)))
            self.assertEqual(self.row('wrcg-es-ss4'), 'Next in line')
            later.pop()()                                              # (still open: it looks again later)
            self.assertEqual((started, len(later)), ([], 1))
        with mock.patch.object(communityui.community, 'game_running', return_value=False), \
                mock.patch.object(a, '_export_go', side_effect=lambda it, args, *x: started.append(args)):
            later.pop()()                                              # (closed: it starts)
        self.assertEqual(started, [['export', 'es_ss1']])
        self.assertIsNone(a._export_waiting)

    def test_install_all_one_after_another_with_a_bar(self):
        """INSTALL ALL: every track not in the game, one question first: Sando's (his manager installs it), then the
        WRC Generations stages made one after another, with a bar."""
        a = self.a
        a.open_community()
        self.loaded()
        u = a._export_ui
        self.assertEqual(u['title'].cget('text'), 'ALL TRACKS')
        self.assertEqual(u['count'].cget('text'), '0 of 3 installed')
        self.assertEqual(u['button'].cget('text'), 'INSTALL ALL  (3)  ›')
        self.assertFalse(u['bar'].winfo_ismapped())                   # (nothing being made: no bar)
        jobs, managed = [], []

        def go(it, args, env, ex, game):                              # (a run started, not finished yet)
            jobs.append(args)
            a._export_now = {'it': it, 'job': mock.Mock(), 'progress': communityui.stageexport.Progress(it['slug']),
                             'stop': False, 't0': 0, 'args': args}
            a._community_say(it['id'], 'Preparing…')

        def manager(it, man, auto=False):                             # (Sando's: installed by his manager, asked nothing)
            managed.append((it['id'], auto))
            self.assertEqual(a._export_ui['words'].cget('text'), 'Installing Chile BioBio   ·   track 1 of 3')
            a._manager_closed(it, man, {'a.utoc': ['SandoChlBioFull']})
        with mock.patch.object(a, '_export_go', side_effect=go), \
                mock.patch.object(a, 'community_manager', side_effect=manager), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True) as asked:
            click(u['button'])
            self.assertEqual(asked.call_count, 1)                     # (one question for all of them)
            self.assertIn('Install these 3 tracks?', asked.call_args_list[0].args[1])
            self.assertIn('·  Chile BioBio\n·  Riudecanyes\n·  Savallà', asked.call_args_list[0].args[1])
            self.assertIn('about 1 h 20 min for them', asked.call_args_list[0].args[1])
            self.assertEqual(managed, [('sando-chile-biobio', True)])
            self.assertEqual(jobs, [['export', 'es_ss1']])
            self.assertEqual([x['id'] for x in a._export_queue], ['wrcg-es-ss4'])
            u = a._export_ui
            self.root.update()
            self.assertTrue(u['bar'].winfo_ismapped())
            self.assertEqual(u['button'].cget('text'), 'STOP ALL')
            prog = a._export_now['progress']
            for line in ('WRCG files: x', '[es_ss1] WRCG export done', 'building es_ss1 (1/1)'):
                prog.feed(line)
            a._community_say('wrcg-es-ss1', 'Building it for Assetto Corsa Rally…')
            said = u['words'].cget('text')
            self.assertTrue(said.startswith('Riudecanyes  '), said)      # (its step is said on its card, not here)
            self.assertNotIn('Building', said)
            self.assertIn('stage 1 of 2', said)
            self.assertIn('% in all', said)
            self.assertTrue(u['bar'].find_all())                      # (drawn)
            # the first one done: the next starts, counted as the second of two
            both = {'a.utoc': ['SandoChlBioFull'], 'x.utoc': ['WrcgEsSS1Full']}    # (the game: Chile in, and it)
            with mock.patch.object(communityui.community, 'stage_packs', return_value=both):
                a._export_done(RIUDECANYES, None, both, dict(self.env, pack=['es_ss1']), 'log')
            self.assertEqual(jobs, [['export', 'es_ss1'], ['export', 'es_ss4']])
            u = a._export_ui
            self.assertEqual(u['count'].cget('text'), '2 of 3 installed')
            self.assertIn('stage 2 of 2', u['words'].cget('text'))
            self.assertIn('Savallà', u['words'].cget('text'))
            # STOP ALL: the one being made stops
            job = a._export_now['job']
            click(u['button'])
        job.cancel.assert_called_once()
        self.assertTrue(a._export_now['stop'])

    def test_stop_all_takes_the_waiting_ones_off(self):
        a = self.a
        a.open_community()
        self.loaded()
        a._export_waiting = RIUDECANYES
        a._export_queue = [SAVALLA]
        a._render_community()
        self.assertIn('Riudecanyes: Waiting for the game to close', a._export_ui['words'].cget('text'))
        with mock.patch.object(communityui.messagebox, 'askyesno', return_value=True):
            click(a._export_ui['button'])
        self.assertEqual((a._export_waiting, a._export_queue), (None, []))
        self.assertEqual(a._export_ui['button'].cget('text'), 'INSTALL ALL  (3)  ›')

    def test_the_time_left_as_people_say_it(self):
        self.assertEqual(communityui._span(25), '1 minute')
        self.assertEqual(communityui._span(25 * 60), '25 minutes')
        self.assertEqual(communityui._span(200 * 60), '3 h 20 min')

    def test_find_game_for_a_copy_steam_and_epic_dont_list(self):
        a = self.a
        a.open_community()
        self.loaded(env=dict(self.env, wrcg=None))
        game = os.path.join(self.home, 'Games', 'WRC Generations')
        os.makedirs(game)
        with mock.patch('tkinter.filedialog.askdirectory', return_value=game):
            click(self.card('wrcg-es-ss1').button)
        self.assertEqual(communityui.settings.load()[communityui.stageexport.WRCG_SETTING], os.path.normpath(game))
        self.assertEqual(a._export_env['wrcg'], os.path.normpath(game))
        self.assertEqual(self.card('wrcg-es-ss1').button.cget('text'), 'INSTALL  ›')
        odd = os.path.join(self.home, 'Games', 'Rally')
        os.makedirs(odd)
        with mock.patch('tkinter.filedialog.askdirectory', return_value=odd), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=False) as asked:
            a.community_find_wrcg()
        self.assertIn("doesn't look like WRC Generations", asked.call_args.args[1])
        self.assertEqual(communityui.settings.load()[communityui.stageexport.WRCG_SETTING], os.path.normpath(game))   # (no: kept)

    def test_closed_and_opened_again_while_one_is_made(self):
        a = self.a
        a.open_community()
        run = {'args': ['export', 'es_ss1'], 'log': '/app/logs/stage-export-1.log', 'pid': 7}
        lines = ['building es_ss1 (1/1)', 'pack: es_ss1 (es_ss1 exported again) in 40 min']
        with mock.patch.object(communityui.stageexport, 'current_run', return_value=run), \
                mock.patch.object(communityui.stageexport, 'Job',
                                  side_effect=lambda attach, on_line: FakeJob(lines, on_line=on_line)) as job, \
                mock.patch.object(communityui.stageexport, 'environment', return_value=dict(self.env, pack=['es_ss1'])), \
                mock.patch.object(communityui.community, 'stage_packs', return_value={'x.utoc': ['WrcgEsSS1Full']}):
            self.loaded()
        self.assertEqual(job.call_args.kwargs['attach'], run)
        self.assertIsNone(a._export_now)
        self.assertEqual(self.card('wrcg-es-ss1').spec['badge'][0], 'INSTALLED')


class SwitchSets(ToolsHarness):
    """London or WRC Generations shown: the other parked by renaming (stageswitch.py), so a switch is a second each way
    and nothing is made again; SHOW on a hidden one; SHOW ONLY on the banner when both are in."""

    def setUp(self):
        super().setUp()
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_stageswitch import game_with_both
        self.game, self.paks = game_with_both()
        self.london = dict(LONDON, group='acrdaily', stages=[{'stageId': 'AcrXsLn02r0FullForward'}])
        communityui.community._save_installed(self.game, {'acrdaily-london': {
            'version': '1', 'acrBuild': '25170642', 'files': ['zz_acrxs_registry_P.utoc', 'zz_acrxs_registry_P.ucas',
                                                              'zz_acrxs_registry_P.pak']}})
        self.cat = {'categories': [{'id': 'tracks', 'name': 'Tracks', 'items': [self.london, RIUDECANYES, SAVALLA]},
                                   {'id': 'cars', 'name': 'Cars', 'items': []}], 'tools': {'stage-exporter': EXPORTER}}
        for p in (mock.patch.object(communityui.stageexport, 'current_run', return_value=None),
                  mock.patch.object(communityui.community, 'game_build', return_value='25170642')):
            p.start()
            self.addCleanup(p.stop)

    def loaded(self):
        a = self.a
        ids = [s['stageId'] for it in self.cat['categories'][0]['items'] for s in it['stages']]
        a._set_community(self.cat, {'acrdaily-london': MAN}, '', self.game, '25170642', [],
                         communityui.community.stage_packs(self.game, ids),
                         {'wrcg': '/games/WRCG', 'tool': '/tools/Sando', 'ready': True, 'pack': ['es_ss1']},
                         communityui.stageswitch.state(self.game), communityui.stageswitch.parked_packs(self.game, ids))
        self.root.update()

    def test_both_in_show_only_one_then_back_in_a_second(self):
        a = self.a
        a.open_community()
        self.loaded()
        said = texts(a._community_page)
        self.assertTrue(any('The game has London and WRC Generations in it, and it shows only one set of stages at a time. '
                            'Pick the one to show' in w for w in said))
        self.assertIn('SHOW ONLY LONDON', said)
        self.assertIn('SHOW ONLY WRC GENERATIONS', said)
        button = next(w for w in a._community_page.winfo_children()[3].winfo_children()
                      if w.cget('text') == 'SHOW ONLY WRC GENERATIONS')
        click(button)                                                  # London parked, WRC Generations shown
        self.assertIn('zz_acrxs_registry_P.utoc.acrdaily-off', os.listdir(os.path.join(self.paks, '~mods')))
        self.assertFalse(any('both in the game' in w for w in texts(a._community_page)))
        london = self.card('acrdaily-london')
        self.assertEqual((london.button.cget('text'), london.spec['badge'][0]), ('SHOW  ›', 'HIDDEN'))
        self.assertTrue(any('In your game, but hidden: the game shows another set of stages now. SHOW swaps these back'
                            in w for w in self.words(london)))
        self.assertEqual(a._community_tree.item('acrdaily-london', 'values')[4], 'Hidden')
        self.assertEqual(self.card('wrcg-es-ss1').spec['badge'][0], 'INSTALLED')
        click(self.card('acrdaily-london').button)                     # SHOW: London back, WRC Generations parked
        self.assertIn('pakchunk99-WrcgStages_P.utoc.acrdaily-off', os.listdir(self.paks))
        self.assertEqual(self.card('acrdaily-london').spec['badge'][0], 'INSTALLED')
        wrcg = self.card('wrcg-es-ss1')
        self.assertEqual((wrcg.button.cget('text'), wrcg.spec['badge'][0]), ('SHOW  ›', 'HIDDEN'))
        u = a._export_ui
        self.assertEqual(u['count'].cget('text'), '2 of 3 installed   ·   Hidden')
        self.assertEqual(u['button'].cget('text'), 'SHOW  ›')
        click(u['button'])                                             # and back again from the strip
        self.assertEqual(communityui.stageswitch.state(self.game), {'acrdaily': 'off', 'wrcg': 'on'})
        self.assertEqual(self.card('wrcg-es-ss1').spec['badge'][0], 'INSTALLED')

    def test_the_game_open_changes_nothing(self):
        a = self.a
        a.open_community()
        self.loaded()
        with mock.patch.object(communityui.community, 'game_running', return_value=True), \
                mock.patch.object(communityui.messagebox, 'showinfo') as said:
            a._community_show_group('wrcg')
        self.assertIn('Close Assetto Corsa Rally first', said.call_args.args[1])
        self.assertEqual(communityui.stageswitch.state(self.game), {'acrdaily': 'on', 'wrcg': 'on'})

    def test_a_stage_made_shows_its_set(self):
        a = self.a
        a.open_community()
        self.loaded()
        a._export_now = {'it': SAVALLA, 'job': None, 'progress': communityui.stageexport.Progress('es_ss4'), 'stop': False,
                         't0': 0, 'args': ['export', 'es_ss4']}
        a._export_done(SAVALLA, None, {}, {'wrcg': '/games/WRCG', 'tool': '/tools/Sando', 'pack': ['es_ss1', 'es_ss4']}, 'log')
        self.assertEqual(communityui.stageswitch.state(self.game), {'acrdaily': 'off', 'wrcg': 'on'})   # (just made: shown)

    def test_a_wrcg_stage_is_made_with_the_other_sets_out_and_they_come_back_if_it_fails(self):
        a = self.a
        a.open_community()
        from test_stageswitch import game_with_three
        self.game, self.paks = game_with_three()
        self.loaded()
        seen = []

        def start(tool, args, on_line=None, watch=()):
            seen.append((communityui.stageswitch.state(self.game), watch))
            return FakeJob(['ERROR: stage build failed'], ok=False)
        with mock.patch.object(communityui.stageexport, 'ensure_addon'), \
                mock.patch.object(communityui.stageexport, 'start', side_effect=start), \
                mock.patch.object(communityui.stageexport, 'environment', return_value=dict(self.env_ready(), pack=[])), \
                mock.patch.object(communityui, 'threading', mock.Mock(Thread=Now)), \
                mock.patch.object(communityui.messagebox, 'askyesno', return_value=True), \
                mock.patch.object(communityui.messagebox, 'showwarning') as warned:
            a.community_export(SAVALLA)
        state, watch = seen[0]
        self.assertEqual(state, {'acrdaily': 'off', 'wrcg': 'on', 'sando': 'off'})   # (made with no other set in Paks)
        self.assertEqual(watch, ['/tools/Sando', os.path.join(self.game, 'acr', 'Content', 'Paks')])
        self.assertIn("Couldn't finish Savallà", warned.call_args.args[1])
        self.assertEqual(communityui.stageswitch.state(self.game), {'acrdaily': 'on', 'wrcg': 'on', 'sando': 'on'})

    def env_ready(self):
        return {'wrcg': '/games/WRCG', 'tool': '/tools/Sando', 'ready': True, 'pack': ['es_ss1']}

    def test_a_full_drive_stops_it_and_says_which(self):
        a = self.a
        a.open_community()
        self.loaded()
        a._export_now = {'it': SAVALLA, 'job': None, 'progress': None, 'stop': False, 'args': ['export', 'es_ss4']}
        with mock.patch.object(communityui.messagebox, 'showwarning') as warned:
            a._export_done(SAVALLA, communityui.stageexport.ExportError('space', 'D:\\Sando'), {}, self.env_ready(), 'log')
        self.assertIn('The drive of D:\\Sando is full, so Savallà was stopped. Free some space there, then INSTALL again.',
                      warned.call_args.args[1])

    def test_chile_installed_by_sandos_manager_is_the_set_shown(self):
        a = self.a
        a.open_community()
        from test_stageswitch import game_with_three
        self.game, self.paks = game_with_three()
        self.cat['categories'][0]['items'].append(SANDO)
        self.loaded()
        a._community_show_group('wrcg')
        sando = self.card('sando-chile-biobio')
        self.assertEqual((sando.button.cget('text'), sando.spec['badge'][0]), ('SHOW  ›', 'HIDDEN'))
        with mock.patch.object(communityui.community, 'open_manager', return_value=mock.Mock()) as opened, \
                mock.patch.object(communityui, 'threading', mock.Mock(Thread=lambda target, daemon: mock.Mock())):
            a._manager_open(SANDO, {})
        opened.assert_called_once()
        self.assertTrue(os.path.exists(os.path.join(self.paks, 'pakchunk99-ChileBioBio_P.ucas')))  # (back before it looks)
        packs = communityui.community.stage_packs(self.game, ['SandoChlBioFull'])
        a._manager_closed(SANDO, {}, packs)
        self.assertEqual(communityui.stageswitch.state(self.game), {'acrdaily': 'off', 'wrcg': 'off', 'sando': 'on'})

    def test_after_a_game_update_the_sets_made_for_the_version_before_are_hidden_until_rebuilt(self):
        a = self.a
        a.open_community()
        from test_stageswitch import game_with_three
        self.game, self.paks = game_with_three()
        self.cat['categories'][0]['items'].append(SANDO)
        a._community_show_group = mock.Mock()                          # (as installed: all in, no switching here)
        self.loaded()                                                  # build 25170642: kept as theirs
        self.assertEqual(communityui.settings.load()['stageSetBuilds'], {'wrcg': '25170642', 'sando': '25170642'})
        ids = ['WrcgEsSS1Full', 'WrcgEsSS4Full', 'SandoChlBioFull', 'AcrXsLn02r0FullForward']
        with mock.patch.object(communityui.messagebox, 'showinfo') as said:     # the game updated
            a._set_community(self.cat, {'acrdaily-london': MAN}, '', self.game, '25300000', [],
                             communityui.community.stage_packs(self.game, ids),
                             {'wrcg': '/games/WRCG', 'tool': '/tools/Sando', 'ready': True, 'pack': ['es_ss1']},
                             communityui.stageswitch.state(self.game), communityui.stageswitch.parked_packs(self.game, ids))
        self.assertIn('Assetto Corsa Rally was updated, so WRC Generations and Sando Rally are hidden for now',
                      said.call_args.args[1])
        self.assertEqual(communityui.stageswitch.state(self.game), {'acrdaily': 'on', 'wrcg': 'off', 'sando': 'off'})
        wrcg = self.card('wrcg-es-ss1')
        self.assertEqual((wrcg.button.cget('text'), wrcg.spec['badge'][0]), ('REBUILD  ›', 'GAME UPDATED'))
        self.assertTrue(any("REBUILD makes it for this version in about 2 minutes; no stage is made again" in w
                            for w in self.words(wrcg)))
        self.assertEqual(a._export_ui['button'].cget('text'), 'REBUILD  ›')
        sando = self.card('sando-chile-biobio')
        self.assertEqual(sando.button.cget('text'), 'MANAGE  ›')
        self.assertEqual(a._community_tree.item('wrcg-es-ss1', 'values')[4], 'Needs a rebuild')
        with mock.patch.object(a, '_export_go') as go:
            click(self.card('wrcg-es-ss1').button)                    # (the one card: its again)
        self.assertEqual(go.call_args.args[1], ['repack'])            # (its list made again: no stage made again)
        a._export_now = {'it': RIUDECANYES, 'job': None, 'progress': None, 'stop': False, 'args': ['repack']}
        a._export_done(RIUDECANYES, None, {}, self.env_ready(), 'log')
        self.assertNotIn('wrcg', a._stale_sets())
        self.assertEqual(communityui.settings.load()['stageSetBuilds']['wrcg'], '25300000')
        self.assertEqual(communityui.settings.load()['stageSetStale'], ['sando'])

    def test_london_removed_while_hidden_takes_its_parked_copies(self):
        a = self.a
        a.open_community()
        self.loaded()
        a._community_show_group('wrcg')
        communityui.community.uninstall(self.game, 'acrdaily-london')
        self.assertFalse(any(n.startswith('zz_acrxs_registry') for n in os.listdir(os.path.join(self.paks, '~mods'))))


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
