"""Main window details: stage names, cancelling a DRIVE restart, and runs from a too-old app."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import api as api_mod, app as app_mod, waiting  # noqa: E402
from acr_daily.app import App, stage_name  # noqa: E402

LONG = {'track': 'Monte Carlo Peïra Cava', 'stageName': 'Peïra Cava', 'menuName': 'Peïra Cava - La Bollène-Vésubie'}


def tk_root():
    import gc
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    root.withdraw()
    destroy = root.destroy

    def destroy_and_collect():
        # the test's Tk objects (images, variables) freed now, on the main thread: freed later by the garbage collector
        # in another test's thread (test_livelink's relay), they abort Tcl ("async handler deleted by the wrong thread")
        destroy()
        gc.collect()
    root.destroy = destroy_and_collect
    return root


class TimerStandings(unittest.TestCase):
    """The standings under the timer (a daily's split, its finish) belong to that daily."""

    def setUp(self):
        p = mock.patch.object(App, 'board', new_callable=mock.PropertyMock, return_value={'entries': [
            {'steamId': 'ann', 'name': 'Ann', 'rank': 1, 'totalMs': 290000, 'status': 'finished', 'splits': None},
            {'steamId': 'me', 'name': 'Me', 'rank': 2, 'totalMs': 302000, 'status': 'finished', 'splits': None}]})
        p.start()
        self.addCleanup(p.stop)
        a = App.__new__(App)
        a.s, a.overlay = {'steamId': 'me'}, mock.Mock()
        a.active, a.drive_target, a.panel_until, a.panel_slot = 1, 'daily', 0, None
        a._standing('FINISH (official)', 302000, None, hold=None)
        self.assertEqual(a.overlay.show_standing.call_args.args[0], 'FINISH (official)')
        a.overlay.reset_mock()
        self.a = a

    def test_a_finish_stays_while_its_daily_is_the_one(self):
        self.a._drop_stale_standing()
        self.a.overlay.show_standing.assert_not_called()

    def test_gone_once_the_game_is_on_another_stage(self):
        """15 Nov 2026: daily 1's finish still under the timer with daily 2 loaded (before the app made it the one)."""
        self.a.dailies = {1: {'ch': {'track': 'Wales Sweet Lamb'}}, 2: {'ch': {'track': 'Greece Loutraki'}}}
        self.a._drop_stale_standing(mock.Mock(track='Wales Sweet Lamb'))       # (still on daily 1's stage: it stays)
        self.a.overlay.show_standing.assert_not_called()
        self.a._drop_stale_standing(mock.Mock(track=''))                       # (the menus, no stage: it stays)
        self.a.overlay.show_standing.assert_not_called()
        self.a._drop_stale_standing(mock.Mock(track='Greece Loutraki'))        # daily 2's stage loaded: gone
        self.a.overlay.show_standing.assert_called_once_with('', None)
        self.assertIsNone(self.a.panel_slot)

    def test_it_stays_on_its_stage_known_by_its_start_line(self):
        """A daily whose stage the judge took by its start line (the game's name for it not the route's) is still the
        stage of its standings: they went at the first split."""
        self.a.dailies = {1: {'ch': {'track': 'Wales Sweet Lamb'}, 'judge': mock.Mock(_track_alias='Wales Sweet Lamb II')}}
        self.a._drop_stale_standing(mock.Mock(track='Wales Sweet Lamb II'))
        self.a.overlay.show_standing.assert_not_called()
        self.a._drop_stale_standing(mock.Mock(track='Greece Loutraki'))
        self.a.overlay.show_standing.assert_called_once_with('', None)

    def test_gone_once_a_league_event_or_a_match_is_followed(self):
        self.a.drive_target = 'league'                      # (a league event, a 1V1, a cup match: DRIVE / CONTINUE on it)
        self.a._drop_stale_standing()
        self.a.overlay.show_standing.assert_called_once_with('', None)
        self.assertIsNone(self.a.panel_slot)
        self.a._drop_stale_standing()                       # (once)
        self.a.overlay.show_standing.assert_called_once()

    def test_gone_once_the_other_daily_is_the_one(self):
        self.a.active = 2
        self.a._drop_stale_standing()
        self.a.overlay.show_standing.assert_called_once_with('', None)


class StageNames(unittest.TestCase):
    def test_menu_name_first_short_one_for_the_timer(self):
        self.assertEqual(stage_name(LONG), 'Peïra Cava - La Bollène-Vésubie')
        self.assertEqual(stage_name(LONG, short=True), 'Peïra Cava')

    def test_a_daily_bought_in_the_shop_names_its_driver(self):
        self.assertEqual(app_mod.set_by({'setBy': {'steamId': '1', 'name': 'Ann'}}), 'Set by Ann')
        self.assertEqual(app_mod.set_by({'track': 'x'}), '')
        self.assertEqual(app_mod.set_by(None), '')

    def test_older_servers_send_no_menu_name(self):
        ch = {'track': 'Alsace Forêt', 'stageName': 'Forêt'}
        self.assertEqual(stage_name(ch), 'Forêt')
        self.assertEqual(stage_name({'track': 'Alsace Forêt'}), 'Alsace Forêt')
        self.assertEqual(stage_name(None), '')

    def test_long_name_fits_its_card(self):
        from tkinter import font as tkfont
        from acr_daily import tiles
        root = tk_root()
        try:
            tile = tiles.Tile(root)

            def title(name):
                """The card drawn with that name: (its size, its width on the card, the room it has, its lines)."""
                tile.render({'lock': ('SS1', 'MONTE CARLO'), 'title': name}, width=400)
                item = next(i for i in tile.cv.find_all() if tile.cv.type(i) == 'text' and tile.cv.itemcget(i, 'text') == name)
                f = tkfont.Font(root=root, font=tile.cv.itemcget(item, 'font'))
                x0, y0, x1, y1 = tile.cv.bbox(item)
                return int(f.actual('size')), f.measure(name), int(float(tile.cv.itemcget(item, 'width'))), \
                    round((y1 - y0) / f.metrics('linespace'))
            with self.subTest('the longest menu name: one line'):
                # (in the app's condensed font, which ships with Windows: elsewhere Tk draws a wider one in its place)
                fam = app_mod.FONT_C.lower()
                if fam not in {x.lower() for x in tkfont.families(root)} and \
                        tkfont.Font(root=root, family=app_mod.FONT_C).actual('family').lower() != fam:
                    self.skipTest('no %s font' % app_mod.FONT_C)
                size, width, room, lines = title(stage_name(LONG).upper())
                self.assertLessEqual(width, room)
                self.assertEqual(lines, 1)
            self.assertEqual(title('OBERSTEIGEN')[0], 28)
            size, width, room, lines = title('VERY ' * 20)                 # longer than any: smallest size, wrapped
            self.assertEqual(size, 16)
            self.assertGreater(lines, 1)
        finally:
            root.destroy()


class WindowSize(unittest.TestCase):
    """The main window: 16:9 at first; as the user left it after that, but never the narrow window of the layout before
    (440 px wide), and always on the screen."""
    AREA = (0, 0, 1920, 1040)                      # a 1080p screen less the taskbar

    def test_first_start_16_9_in_the_middle(self):
        self.assertEqual(app_mod.window_size(None, (1280, 720), (1120, 640), self.AREA), (1280, 720, None, None))

    def test_the_narrow_window_from_before_is_not_kept(self):
        old = {'w': 440, 'h': 900, 'x': 1400, 'y': 20}         # (saved by an app before this layout)
        self.assertEqual(app_mod.window_size(old, (1280, 720), (1120, 640), self.AREA), (1280, 720, None, None))

    def test_as_the_user_left_it_and_on_the_screen(self):
        saved = {'w': 1500, 'h': 860, 'x': 600, 'y': 300, 'layout': app_mod.LAYOUT}
        self.assertEqual(app_mod.window_size(saved, (1280, 720), (1120, 640), self.AREA), (1500, 860, 420, 140))
        small = dict(saved, w=800, h=500, x=10, y=10)        # (never smaller than the least)
        self.assertEqual(app_mod.window_size(small, (1280, 720), (1120, 640), self.AREA)[:2], (1120, 640))
        big = dict(saved, w=3000, h=2000)                    # (a bigger screen than this one, unplugged)
        self.assertEqual(app_mod.window_size(big, (1280, 720), (1120, 640), self.AREA), (1920, 1000, 0, 0))


class FixedWindow(unittest.TestCase):
    """Settings › Window size (from 0.1.5.13): the window always this size, not resizable, so nothing on its pages moves
    or gets cut off; at the screen's scale, only the sizes that fit; Resizable as before."""
    ROOM = (1920, 1000)                            # a 1080p screen less the taskbar and the title bar

    def test_a_size_at_the_screens_scale(self):
        self.assertEqual(app_mod.fixed_size('1280x720', 1.0, self.ROOM), (1280, 720))
        self.assertEqual(app_mod.fixed_size('1280x720', 1.25, self.ROOM), (1600, 900))      # (125 %)
        self.assertEqual(app_mod.fixed_size('1600x900', 1.0, self.ROOM), (1600, 900))
        self.assertIsNone(app_mod.fixed_size('free', 1.0, self.ROOM))                        # resizable
        self.assertEqual(app_mod.fixed_size('nonsense', 1.0, self.ROOM), (1280, 720))       # (an unknown one: the first)

    def test_too_big_for_the_screen_the_biggest_that_fits(self):
        self.assertEqual(app_mod.fixed_size('1920x1080', 1.0, self.ROOM), (1600, 900))      # (1080 high: 1000 there)
        self.assertEqual(app_mod.fixed_size('1600x900', 1.25, self.ROOM), (1600, 900))      # (2000 wide: no)
        self.assertEqual(app_mod.fixed_size('1280x720', 1.5, self.ROOM), (1920, 1000))      # none fits: the room
        self.assertEqual(app_mod.sizes_that_fit(1.0, self.ROOM), ['1280x720', '1440x810', '1600x900'])
        self.assertEqual(app_mod.sizes_that_fit(1.25, self.ROOM), ['1280x720'])             # (1440 x 810: 1012 high)
        self.assertEqual(app_mod.sizes_that_fit(1.25, (2560, 1300)), ['1280x720', '1440x810', '1600x900'])   # (2400 x 1350: no)
        self.assertEqual(app_mod.sizes_that_fit(1.5, self.ROOM), ['1280x720'])             # (the first always offered)
        for _key, w, h in app_mod.WINDOW_SIZES:                                             # (all wide: one layout)
            self.assertEqual(app_mod.layout_for(w), (False, False))

    def test_picked_in_settings_it_is_put_on_at_once(self):
        import tkinter as tk
        a = App.__new__(App)
        a.root = tk.Tk()
        a.root.withdraw()
        self.addCleanup(a.root.destroy)
        a.s = {}
        a._layout = mock.Mock()
        with mock.patch('acr_daily.app.settings.save'), \
                mock.patch('acr_daily.app.work_area', return_value=(0, 0, 1920, 1040)), \
                mock.patch('acr_daily.app.on_screen', return_value=True), \
                mock.patch.object(a.root, 'winfo_fpixels', return_value=96.0):
            a._place_window()                                     # (nothing picked yet: 1280 x 720, fixed)
            self.assertEqual(a.root.resizable(), (False, False))
            self.assertEqual(a.root.minsize(), (1280, 720))
            a.set_window_size('1600x900')
            self.assertEqual(a.s['windowSize'], '1600x900')
            self.assertEqual((a.root.minsize(), a.root.maxsize()), ((1600, 900), (1600, 900)))
            a.set_window_size('free')                             # Resizable: as before
            self.assertEqual(a.root.resizable(), (True, True))
            self.assertEqual(a.root.minsize(), (app_mod.MIN_W, app_mod.MIN_H))


class NarrowWindow(unittest.TestCase):
    """A window narrower than RaceRoom's 16:9 (a second screen stood on its end): under NARROW_W the header in two rows
    and the driver's panel across the top; under STACK_W the cards and the pages' columns one under the other."""

    def test_the_layout_for_a_width(self):
        self.assertEqual(app_mod.layout_for(1280), (False, False))
        self.assertEqual(app_mod.layout_for(1000), (True, False))
        self.assertEqual(app_mod.layout_for(700), (True, True))
        self.assertEqual(app_mod.layout_for(1400, k=1.25), (False, False))      # (1120 at 96 dpi)
        self.assertEqual(app_mod.layout_for(1080, k=1.25), (True, False))       # a 1080 px screen stood on its end
        self.assertEqual(app_mod.layout_for(1080, k=1.5), (True, True))

    def test_it_fits_a_screen_stood_on_its_end(self):
        for k in (1.0, 1.25, 1.5, 1.75):           # (a 1080p screen turned: 1080 px across; the window's frame ~16 px)
            self.assertLessEqual(round(app_mod.MIN_W * k) + 16, 1080)

    def test_cards_side_by_side_or_one_under_the_other(self):
        import tkinter as tk
        from acr_daily import tiles
        root = tk_root()
        try:
            frame = tk.Frame(root)
            row = tiles.TileRow(frame, 2)
            a, b = row.add(tiles.Tile(frame)), row.add(tiles.Tile(frame))
            where = lambda t: (int(t.frame.grid_info()['row']), int(t.frame.grid_info()['column']))  # noqa: E731
            a.render({'title': 'A', 'lines': [('a line', 'info')] * 6, 'button': False})
            b.render({'title': 'B', 'button': False})
            row.even()
            self.assertEqual((where(a), where(b)), ((0, 0), (0, 1)))
            self.assertEqual(b.min_h, a.natural_h)                              # (as tall as the card beside it)
            row.set_cols(1)
            row.even()
            self.assertEqual((where(a), where(b)), ((0, 0), (1, 0)))
            self.assertEqual(int(frame.grid_columnconfigure(1)['weight']), 0)  # (no empty column taking room)
            self.assertEqual(b.min_h, b.natural_h)                              # (one under the other: its own height)
            row.set_cols(2)
            self.assertEqual((where(a), where(b)), ((0, 0), (0, 1)))
        finally:
            root.destroy()


class UpdateFailed(unittest.TestCase):
    """The one-click update failing (a download cut off, a bad checksum): said in a popup, the bar back to UPDATE."""

    def test_said_in_a_popup(self):
        from acr_daily import updater
        later = []                                 # what the download's thread hands to the Tk thread
        a = App.__new__(App)
        a.root = mock.Mock()
        a.root.after.side_effect = lambda ms, fn: later.append(fn)
        a.update_info, a.update_busy, a._pending_update = {'version': '0.0.25', 'url': 'https://x/ACR-Daily.exe'}, '', None
        a._driving = lambda: False
        with mock.patch('acr_daily.updater.can_self_update', return_value=True), \
                mock.patch('acr_daily.updater.download', side_effect=updater.UpdateError('the checksum does not match')), \
                mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)), \
                mock.patch('acr_daily.app.messagebox.showerror') as err:
            a.do_update()
            self.assertEqual(a.update_busy, '')
            for fn in later:                       # (on the Tk thread, after the thread's except block has ended)
                fn()
        err.assert_called_once_with('ACR Daily', 'Update failed: the checksum does not match')


class WhatsNew(unittest.TestCase):
    """Just updated: the bar says so and opens what's new in this version on the website (server/src/changelog.js)."""

    def app(self):
        a = App.__new__(App)
        a.root, a.upd, a.state_l = mock.Mock(), mock.Mock(), mock.Mock()
        a.api = mock.Mock(site='https://acrdaily.com')
        a.update_info, a.update_busy, a._pending_update = None, '', None
        a._driving = lambda: False
        return a

    def test_the_bar_after_an_update_opens_the_changelog(self):
        from acr_daily import __version__
        a = self.app()
        a.just_updated()
        text = a.upd.configure.call_args.kwargs['text']
        self.assertIn(__version__, text)
        self.assertIn("WHAT'S NEW", text)
        with mock.patch('acr_daily.app.webbrowser.open') as op:
            a.do_update()
        op.assert_called_once_with('https://acrdaily.com/changelog#v%s' % __version__)

    def test_once_it_is_gone_a_click_opens_nothing(self):
        a = self.app()
        later = []
        a.root.after.side_effect = lambda ms, fn=None: later.append(fn) if fn else None
        a.just_updated()
        for fn in later:
            fn()
        with mock.patch('acr_daily.app.webbrowser.open') as op:
            a.do_update()
        op.assert_not_called()


class TimerLine(unittest.TestCase):
    """The line under the time on the timer window after a finish."""

    def app(self, practice):
        a = App.__new__(App)
        ch = {'slot': 2, 'track': 'Greece Loutraki - Aghii Theodori', 'car': 'Citroen Xsara WRC'}
        a.active, a.recorder, a.awaiting, a.s, a.net_msg = 2, None, [], {'token': 't', 'steamId': '7656'}, ''
        a.dailies = {2: {'ch': ch, 'practice': practice,      # (the active daily: its challenge, judge and board)
                         'judge': mock.Mock(state='finished', message='FINISHED', total_ms=384200, resets=0,
                                            result={'startedAt': 1.0}),
                         'board': {'entries': [{'steamId': '7656', 'rank': None, 'status': 'dnf'}]}}}
        a._league_overlay_state = a._tt_overlay_state = lambda f: None
        return a

    def test_a_practice_finish_says_so_instead_of_sending_for_ever(self):
        """13 Nov 2026 (report #9): a new driver's first SS2 run was a restart, their 6:24.2 practice; the timer said
        "Sending..." for good, as a practice run never gets a place on the board."""
        line = self.app(True)._overlay_state(None)[2][4]
        self.assertIn('PRACTICE', line)
        self.assertEqual(self.app(False)._overlay_state(None)[2][4], 'Sending...')   # (the first run: until its place)


    def test_the_first_run_says_loudly_that_it_counts(self):
        """A restart in a run's first minute was the most common DNF (Nov 2026): on the start line, and in the counted
        run's first 20 s, the timer says in orange that this run counts and a restart is a DNF (from 0.1.5)."""
        from acr_daily import app as appmod
        a = self.app(False)
        a._needs_stake = lambda slot: False
        a._driven = lambda slot: False
        a.dailies[2]['committed'] = {'date': None}          # (START OFFICIAL RALLY pressed: CommitToOfficialRally)
        j = a.dailies[2]['judge']
        j.state, j.paused, j.gap_ms, j.progress = 'armed', False, None, 0.0
        self.assertEqual(a._overlay_state(None)[2][4:], ('THIS RUN COUNTS · a restart is a DNF', appmod.SLOW))
        j.state, j.total_ms = 'running', 5000
        self.assertEqual(a._overlay_state(None)[2][4:], ('THIS RUN COUNTS · a restart is a DNF', appmod.SLOW))
        j.total_ms = 25000                                  # (then the usual line)
        self.assertEqual(a._overlay_state(None)[2][4], 'On stage · 0%')
        b = self.app(True)                                  # practice: nothing counts, nothing said
        b._needs_stake, b._driven = (lambda slot: False), (lambda slot: True)
        jb = b.dailies[2]['judge']
        jb.state, jb.paused, jb.gap_ms, jb.progress, jb.total_ms = 'running', False, None, 0.0, 5000
        self.assertEqual(b._overlay_state(None)[2][4], 'PRACTICE · On stage · 0%')
        jb.state = 'armed'
        self.assertIn('PRACTICE', b._overlay_state(None)[2][4])

    def test_a_run_outside_the_rally_weekend_says_practice(self):
        from acr_daily import app as appmod
        a = self.app(False)
        a._needs_stake, a._driven = (lambda slot: False), (lambda slot: False)
        j = a.dailies[2]['judge']
        j.state, j.paused, j.gap_ms, j.progress, j.total_ms = 'running', False, None, 0.0, 5000
        a.dailies[2]['norally'] = True
        self.assertEqual(a._overlay_state(None)[2][4:], ('PRACTICE · not in the Rally Weekend', appmod.MUTED))
        j.state, j.result = 'dnf', {'clockMs': 30000, 'resets': 0, 'reason': 'restarted'}
        self.assertEqual(a._overlay_state(None)[2][0], 'standby', 'no DNF for a practice run')
        a.dailies[2]['norally'] = False
        j.state, a.dailies[2]['rw_pre'] = 'armed', False      # on the start line, the save says: not the Rally Weekend
        self.assertEqual(a._overlay_state(None)[2][4], 'PRACTICE · not in the Rally Weekend')


class InRally(unittest.TestCase):
    """Only a run in the daily's Rally Weekend counts (from 0.1.5): told from the save as the stage clock starts."""

    def test_the_rally_started_on_the_dailys_stage_nothing_driven(self):
        from acr_daily.app import in_rally
        from test_rallyweekend import fake_save
        ch, cal = {'stageId': 'WelesS4HafrenSouthFullReverse'}, [(0, 'WelesS4HafrenSouthFullReverse', 43200, 'ServiceParkDefault')]
        self.assertIs(in_rally(ch, fake_save(cal, done=0)), True)                  # START RALLY pressed
        self.assertIs(in_rally(ch, fake_save(cal)), False)                         # set up by DRIVE, not started: Practice, say
        self.assertIs(in_rally(ch, fake_save(cal, done=1)), False)                 # driven already (the finish screen of it)
        self.assertIs(in_rally(ch, fake_save([(0, 'WelesS3HafrenNorthFullForward', 43200, 'ServiceParkDefault')], done=0)), False)
        self.assertIs(in_rally(ch, fake_save(cal, rally=False)), False)            # never a Rally Weekend on this PC
        self.assertIsNone(in_rally(ch, None))                                       # no save read: counts, as before
        self.assertIsNone(in_rally({}, fake_save(cal, done=0)))

class PracticeThenTheRally(unittest.TestCase):
    """A run outside the daily's Rally Weekend is practice: it is no start, so the real run after it still counts and
    the timer says so (it said "PRACTICE · your first run is your result": a driver who believed it could restart the
    run that counted, a DNF)."""

    def app(self):
        a = App.__new__(App)
        a.s, a.local_runs, a.awaiting = {'steamId': '7656'}, [], []
        a.dailies = {1: {'ch': {'id': '2026-11-15/1', 'mode': 'weekend', 'stageId': 'WelesS4HafrenSouthFullForward'},
                         'judge': mock.Mock(state='running'), 'board': {'entries': []}}}
        a._needs_stake = lambda slot: False
        a._game_save = lambda: b'save'
        a._game_results = lambda b: set()
        a._started_again = mock.Mock()
        return a

    def start(self, a, in_rally):
        # (the PRACTICE_CHECK machinery alone: START OFFICIAL RALLY not asked for, CommitToOfficialRally has that)
        with mock.patch('acr_daily.app.PRACTICE_CHECK', True), mock.patch('acr_daily.app.COMMIT_REQUIRED', False), \
                mock.patch('acr_daily.app.in_rally', return_value=in_rally), \
                mock.patch('acr_daily.app.steam_account', return_value='7656'), mock.patch('acr_daily.app.waiting.note'):
            a.dailies[1]['judge'].state = 'running'          # (the judge has just said 'start')
            a._daily_started(1, a.dailies[1])
        return a.dailies[1]

    def test_the_rally_after_a_practice_run_counts(self):
        a = self.app()
        d = self.start(a, False)                             # Practice, or Single Rally Stage
        self.assertTrue(d['norally'])
        d['judge'].state = 'finished'
        a.awaiting.append({'kind': 'daily', 'slot': 1, 'practice': True,      # (its result waited for, just in case)
                           'result': {'challengeId': '2026-11-15/1', 'startedAt': 1.0}})
        d = self.start(a, True)                              # then START RALLY: the run that counts
        self.assertFalse(d['norally'])
        self.assertFalse(d['practice'], 'the first run in the Rally Weekend is the one that counts')
        d['judge'].state = 'dnf'
        d = self.start(a, True)                              # a restart of it: that one is practice
        self.assertTrue(d['practice'])

    def test_with_the_check_off_every_run_counts_from_its_start(self):
        """PRACTICE_CHECK off (the default): the save at the start says "not in the Rally Weekend" for a real START RALLY
        run too (15 Nov 2026, report #175), so nothing is judged practice from it: the first start counts, as up to
        0.1.5, and the wager daily's run is live on the map (the server takes no run of it it didn't see start)."""
        from acr_daily import app as appmod
        self.assertFalse(appmod.PRACTICE_CHECK)
        a = self.app()
        d = a.dailies[1]
        d['committed'] = {'date': d['ch'].get('date')}      # (START OFFICIAL RALLY pressed)
        with mock.patch('acr_daily.app.in_rally', return_value=False), \
                mock.patch('acr_daily.app.steam_account', return_value='7656'), mock.patch('acr_daily.app.waiting.note') as note:
            a._daily_started(1, d)
        self.assertFalse(d['norally'])
        self.assertFalse(d['practice'])
        self.assertIn('not used', note.call_args_list[0].args[0])

    def test_a_daily_driven_in_its_rally_weekend_stays_driven(self):
        a = self.app()
        self.assertFalse(self.start(a, True)['practice'])
        self.assertTrue(self.start(a, False)['practice'])    # (a practice run after it: practice either way)
        self.assertTrue(self.start(a, None)['practice'])


class CommitToOfficialRally(unittest.TestCase):
    """A daily counts only from a run the driver commits to: START OFFICIAL RALLY, pressed before its stage clock
    starts (COMMIT_REQUIRED, the 0.1.5.x test builds on). Not pressed, or pressed once the clock runs: practice, ignored."""

    def app(self):
        a = App.__new__(App)
        a.s, a.local_runs, a.awaiting, a.sub_l = {'steamId': '7656'}, [], [], mock.Mock()
        a.dailies = {1: {'ch': {'id': '2026-11-15/1', 'date': '2026-11-15', 'mode': 'weekend', 'track': 'Alsace Obersteigen',
                                'car': 'Peugeot 208 Rally4', 'stageId': 'AlsaceS4SaverneShort1Forward'},
                         'judge': mock.Mock(state='waiting', approaching=False), 'board': {'entries': []}}}
        a._needs_stake = lambda slot: False
        a._game_save = lambda: b'save'
        a._game_results = lambda b: set()
        a._started_again = mock.Mock()
        return a

    def start(self, a):
        with mock.patch('acr_daily.app.steam_account', return_value='7656'), mock.patch('acr_daily.app.waiting.note'):
            a.dailies[1]['judge'].state = 'running'
            a._daily_started(1, a.dailies[1])
        return a.dailies[1]

    def test_not_pressed_practice_ignored(self):
        from acr_daily import app as appmod
        self.assertTrue(appmod.COMMIT_REQUIRED)
        a = self.app()
        d = self.start(a)
        self.assertTrue(d['norally'])
        self.assertEqual(d['practice_why'], 'uncommitted')
        self.assertFalse(d['practice'], 'an ignored run is no start: the official one is still to come')

    def test_pressed_the_next_run_counts_and_uses_it_up(self):
        a = self.app()
        with mock.patch('acr_daily.app.waiting.note'):
            self.assertTrue(a.commit(1))
        self.assertTrue(a._committed(1))
        d = self.start(a)
        self.assertFalse(d['norally'])
        self.assertIsNone(d['committed'])
        d['judge'].state = 'dnf'                               # a restart: the next one is practice (driven now)
        self.assertFalse(a.commit(1), 'driven: nothing to commit to')

    def test_too_late_once_the_clock_runs(self):
        a = self.app()
        a.dailies[1]['judge'].state = 'running'
        self.assertFalse(a.commit(1))
        self.assertFalse(a._committed(1))
        self.assertIn('Too late', a.sub_l.configure.call_args.kwargs['text'])

    def test_yesterdays_press_is_no_press_today(self):
        a = self.app()
        a.dailies[1]['committed'] = {'date': '2026-11-14'}
        self.assertFalse(a._committed(1))
        self.assertEqual(self.start(a)['practice_why'], 'uncommitted')

    def test_the_card_offered_until_pressed_or_driven(self):
        a = self.app()
        a.overlay, a.root = None, mock.Mock()
        with mock.patch('acr_daily.app.nextcard.NextCard') as card:
            card.return_value.alive = False
            self.assertIsNotNone(a.commit_offer(1))
            self.assertEqual(card.call_args.args[5], 'START OFFICIAL RALLY  ›')
            self.assertIsNone(card.call_args.kwargs['close_s'], 'up until a button is clicked')
            a.dailies[1]['committed'] = {'date': '2026-11-15'}
            card.reset_mock()
            self.assertIsNone(a.commit_offer(1))
            card.assert_not_called()

    def test_the_card_screams_the_two_rules(self):
        """(RULES_LOUD) The commit card: a red banner, the rules in white, the title in red."""
        a = self.app()
        a.overlay, a.root = None, mock.Mock()
        with mock.patch('acr_daily.app.nextcard.NextCard') as card:
            card.return_value.alive = False
            a.commit_offer(1)
        kw = card.call_args.kwargs
        self.assertEqual((kw['banner'], kw['note'], kw['loud']), (app_mod.COMMIT_BANNER, app_mod.COMMIT_RULES, True))
        self.assertIn('RALLY WEEKEND MODE', kw['banner'])
        self.assertIn("Single Rally Stage don't count", kw['note'])
        with mock.patch('acr_daily.app.waiting.note'):
            a.commit(1)
        self.assertIn('SS1 will count. Start it in Rally Weekend mode', a.sub_l.configure.call_args.kwargs['text'])

    def test_drive_warns_once_for_each_daily(self):
        """(RULES_LOUD) DRIVE on a Rally Weekend daily not committed or driven: the two rules in a warning box, once a
        daily while the app runs; not for a Single Rally Stage daily, nor once pressed or driven."""
        a = self.app()
        a._driven = lambda slot: False
        with mock.patch('acr_daily.app.messagebox.showwarning') as warn:
            self.assertTrue(a._rules_warning(1))
            self.assertTrue(a._rules_warning(1))                  # (said already)
        warn.assert_called_once()
        self.assertIn('SS1 only counts if you do both of these', warn.call_args.args[1])
        self.assertIn('Rally Weekend mode', warn.call_args.args[1])
        self.assertEqual(warn.call_args.args[0], app_mod.RULES_WARNING_TITLE)
        self.assertIn('START OFFICIAL RALLY', warn.call_args.args[1])
        for change in ({'mode': 'single'}, {'id': '2026-11-15/9'}):
            a = self.app()
            a._driven = lambda slot: False
            a.dailies[1]['ch'].update(change)
            if 'id' in change:
                a.dailies[1]['committed'] = {'date': '2026-11-15'}
            with mock.patch('acr_daily.app.messagebox.showwarning') as warn:
                a._rules_warning(1)
            warn.assert_not_called()

    def test_drive_warns_before_anything_else_is_asked(self):
        a = self.app()
        a._driven, a._drive_wait, a._waiting_text = (lambda slot: False), None, (lambda: None)
        a.community_missing = lambda ch, label: False
        a._league_before_daily = lambda weekend: False
        a._tt_running = lambda: False
        order = []
        with mock.patch('acr_daily.app.messagebox.showwarning', side_effect=lambda *x: order.append('rules')), \
                mock.patch('acr_daily.app.saveslot.game_running', return_value=True), \
                mock.patch('acr_daily.app.messagebox.askyesno', side_effect=lambda *x: order.append('restart') and False):
            a.drive_click(1)
        self.assertEqual(order, ['rules', 'restart'])

    def test_the_timer_window_screams_on_the_start_line(self):
        """(RULES_LOUD) On a Rally Weekend daily's start line, not driven yet: red until START OFFICIAL RALLY is pressed,
        then orange (Rally Weekend only); nothing once it is driven, nor while following a league event."""
        a = self.app()
        a.drive_target = 'daily'
        driven = []
        a._driven = lambda slot: bool(driven)
        j = a.dailies[1]['judge']
        self.assertIsNone(a._rules_alert())                       # (not on its start line)
        j.state = 'armed'
        self.assertEqual(a._rules_alert(), (app_mod.START_LINE_UNCOMMITTED, app_mod.ACC, app_mod.WHITE))
        a.dailies[1]['committed'] = {'date': '2026-11-15'}
        self.assertEqual(a._rules_alert()[:2], (app_mod.START_LINE_COMMITTED, app_mod.SLOW))
        a.drive_target = 'league'
        self.assertIsNone(a._rules_alert())
        a.drive_target = 'daily'
        driven.append(1)
        self.assertIsNone(a._rules_alert())
        a.overlay, a._saved_at, a._saving = mock.Mock(), None, lambda: None
        driven.clear()
        a._render_saving()
        self.assertEqual(a.overlay.set_alert.call_args.args[0], app_mod.START_LINE_COMMITTED)

    def test_after_start_official_rally_a_restart_or_quitting_is_a_dnf(self):
        """Committed, a restart or quitting is a DNF whatever the mode; only a finish without the game's time is ignored
        (OfficialResult: sent as 'void')."""
        from acr_daily.i18n import said
        a = self.app()
        a.on_result, a._await_official = mock.Mock(), mock.Mock()
        for why in ('restarted', 'left the stage'):
            r = {'status': 'dnf', 'reason': said(why), 'clockMs': 50869, 'startedAt': 1000.0}
            a._daily_ended(1, a.dailies[1], 'dnf', r)
            self.assertEqual(a.on_result.call_args.args[0]['status'], 'dnf')
        a._await_official.assert_not_called()
        a._daily_ended(1, a.dailies[1], 'finished', {'status': 'finished', 'clockMs': 203284})
        a._await_official.assert_called_once()                 # (the game's time, or none: ignored)

    def test_the_timer_on_the_start_line(self):
        from acr_daily import app as appmod
        a = self.app()
        a.active, a.recorder, a.net_msg = 1, None, ''
        a._league_overlay_state = a._tt_overlay_state = lambda f: None
        a._driven = lambda slot: False
        j = a.dailies[1]['judge']
        j.state, j.message = 'armed', ''
        self.assertEqual(a._overlay_state(None)[2][4], appmod.UNCOMMITTED_LINE)
        a.dailies[1]['committed'] = {'date': '2026-11-15'}
        self.assertEqual(a._overlay_state(None)[2][4], appmod.COUNTS_LINE)


class SetUpChangedInTheGame(unittest.TestCase):
    """The game's result of a daily or a time trial stage counts only if the save still holds what DRIVE wrote
    (app._official_found, leagues.daily_changed): its weather, hour, track conditions, time speed and rules."""

    def app(self, changed):
        a = App.__new__(App)
        a.sub_l, a.awaiting = mock.Mock(), []
        a._official_in = mock.Mock()
        p = mock.patch('acr_daily.app.leagues.daily_changed', return_value=changed)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.app.rallyweekend.read_weekend', return_value={})
        p.start()
        self.addCleanup(p.stop)
        return a

    def test_as_set_up_it_counts(self):
        a = self.app([])
        item, o = {'id': 'daily:x', 'kind': 'daily', 'slot': 1}, {'time': 100.0}
        a._official_found(item, o, b'save')
        a._official_in.assert_called_once_with(item, o)

    def test_a_daily_changed_is_a_dnf_saying_what(self):
        a = self.app(['weather', 'track conditions'])
        item = {'id': 'daily:x', 'kind': 'daily', 'slot': 1}
        with mock.patch('acr_daily.app.waiting.note'):
            a._official_found(item, {'time': 100.0}, b'save')
        args = a._official_in.call_args.args
        self.assertIsNone(args[1])
        self.assertEqual(str(args[2]), "the daily's weather, track conditions changed in the game")

    def test_a_time_trial_run_changed_is_not_counted(self):
        a = self.app(['start times'])
        item = {'id': 'tt:x', 'kind': 'tt', 'slot': 2}
        a.awaiting = [item]
        with mock.patch('acr_daily.app.waiting.note'), mock.patch('acr_daily.app.waiting.remove'):
            a._official_found(item, {'time': 100.0}, b'save')
        a._official_in.assert_not_called()
        self.assertEqual(a.awaiting, [])
        self.assertIn('TT2: not counted', a.sub_l.configure.call_args.kwargs['text'])


class CancelDrive(unittest.TestCase):
    """DRIVE with the game open waits for the game to close; the same button then reads CANCEL and goes back."""

    def app(self):
        a = App.__new__(App)
        a.root = mock.Mock()
        a.root.after.return_value = 'job-1'
        a.cards = {1: {'drive': mock.Mock()}, 2: {'drive': mock.Mock()}}
        a.sub_l = mock.Mock()
        a.dailies = {1: {'ch': {'track': 'Alsace Forêt', 'car': 'Hyundai i20 N Rally2'}},
                     2: {'ch': {'track': 'Wales Severn', 'car': 'VW Polo GTI R5'}}}
        return a

    def test_cancel_while_the_game_closes(self):
        a = self.app()
        with mock.patch('acr_daily.saveslot.ask_game_to_quit'):
            a._restart_into(1)
        a.cards[1]['drive'].configure.assert_called_with(text='CANCEL  ✕')
        with mock.patch('acr_daily.saveslot.game_running', return_value=True):
            a.drive_click(2)                       # the other daily's button does nothing meanwhile
            self.assertEqual(a._restarting, 1)
            a.drive_click(1)                       # CANCEL
        self.assertFalse(a._restarting)
        a.root.after_cancel.assert_called_with('job-1')
        a.cards[1]['drive'].configure.assert_called_with(text='DRIVE  ›')
        self.assertIn('Cancelled', a.sub_l.configure.call_args.kwargs['text'])


class OfficialResult(unittest.TestCase):
    """A Rally Weekend daily: a finished run is sent with the game's own result from its save, or as a DNF."""

    def setUp(self):
        import tempfile
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_rallyweekend as t
        self.t = t
        self.T0 = t.T0
        self.save = os.path.join(tempfile.mkdtemp(), 'PlayerDataSaveSlot.sav')
        self.old = t.entry('WelesS4HafrenSouthFullForward', [t.run('HyundaiI20NRally2', [80.0, 156.1, 213.597], 29)],
                           self.T0 - 1428)
        self.write([self.old])
        a = App.__new__(App)
        a.root, a.sub_l, a.awaiting, a.active = mock.Mock(), mock.Mock(), [], 1
        a.dailies = {1: {'ch': {'mode': 'weekend', 'stageId': 'WelesS4HafrenSouthFullForward', 'carId': 'HyundaiI20NRally2'},
                         'judge': None}}
        a.on_result = mock.Mock()
        a._standing = mock.Mock()
        self.a = a
        p = mock.patch('acr_daily.saveslot.SAVE', self.save)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.saveslot.SETTLE_S', 0)               # (the save written here is read at once)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch('acr_daily.settings.DIR', tempfile.mkdtemp())     # (awaiting.json: waiting.py)
        p.start()
        self.addCleanup(p.stop)

    def write(self, entries):
        with open(self.save, 'wb') as f:
            f.write(b'junk' + self.t.results_list('DefaultRally', entries))

    def finish(self, clock_ms=203284):
        known = self.a._game_results()
        r = {'status': 'finished', 'reason': '', 'clockMs': clock_ms, 'resets': 1, 'totalMs': clock_ms,
             'startedAt': self.T0 + 40}
        self.a._await_official(1, r, known)
        return r

    def check(self, running=True):
        with mock.patch('acr_daily.saveslot.game_running', return_value=running):
            self.a._check_official()

    def test_sent_with_the_games_time_and_penalty(self):
        self.finish()
        self.check()
        self.a.on_result.assert_not_called()                     # not saved by the game yet
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        self.check()
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs'], r['official']['timeMs'], r['official']['penaltyMs']),
                         ('finished', 293284, 203284, 90000))
        self.assertEqual(r['official']['splitsMs'], [87618, 160034, 203284])
        self.assertEqual(self.a.awaiting, [])

    def restart(self):
        """The app closed and opened again: a new one, with what waits on disk (today's dailies not loaded yet)."""
        b = App.__new__(App)
        b.root, b.sub_l, b.active, b.dailies = mock.Mock(), mock.Mock(), 1, {}
        b.awaiting = app_mod.daily_waits()
        b.on_result, b._standing = mock.Mock(), mock.Mock()
        return b

    def test_a_run_waiting_when_the_app_closes_is_sent_when_it_opens_again(self):
        self.finish()
        self.assertEqual([x['kind'] for x in waiting.load()], ['daily'])         # on disk at once
        self.assertIn('results screen', self.a._waiting_text())                  # DRIVE waits for it too
        b = self.restart()                       # closed before the game saved the time, which it did after
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        b._resume_waiting()
        self.assertIn('still waiting', b.sub_l.configure.call_args.kwargs['text'])
        with mock.patch('acr_daily.saveslot.game_running', return_value=True):
            b._check_official()
        r = b.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs'], r['official']['timeMs']), ('finished', 293284, 203284))
        self.assertEqual((b.awaiting, waiting.load()), ([], []))

    def test_a_run_the_game_never_saved_does_not_count_after_a_restart(self):
        self.finish()
        b = self.restart()
        for _ in range(3):
            with mock.patch('acr_daily.saveslot.game_running', return_value=False):
                b._check_official()
        b.on_result.assert_not_called()                          # (no app's time, no DNF: OFFICIAL_ONLY)
        self.assertEqual((b.awaiting, waiting.load()), ([], []))
        self.assertIn("SS1 didn't count: the game closed before saving", b.sub_l.configure.call_args.kwargs['text'])

    def test_closing_the_app_while_a_run_waits_asks_first(self):
        self.finish()
        self.a._save_window, self.a.shm = mock.Mock(), mock.Mock()
        with mock.patch('acr_daily.app.messagebox.askyesno', return_value=False) as ask:
            self.a.quit()
        self.assertIn('picked up next time', ask.call_args.args[1])
        self.a.root.destroy.assert_not_called()
        with mock.patch('acr_daily.app.messagebox.askyesno', return_value=True):
            self.a.quit()
        self.a.root.destroy.assert_called_once()

    def test_the_timer_window_says_what_saves_the_time_while_it_waits(self):
        self.a.league_run = None
        self.assertFalse(self.a._official_pending())
        self.finish()
        self.assertTrue(self.a._official_pending())
        self.assertIn('results screen', app_mod.OFFICIAL_ALERT)

    def test_started_again_after_the_game_saved_the_time_sends_it_at_once(self):
        self.finish()
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        self.a._started_again('daily', 1, self.a._game_save())   # (the watch hadn't read it yet)
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs']), ('finished', 293284))
        self.assertEqual((self.a.awaiting, waiting.load()), ([], []))

    def test_started_again_from_the_results_screen_does_not_count_saying_so(self):
        """12 Nov 2026: a finished first run waited 10 minutes while its driver started the stage again and again, and
        went as "the game closed before saving its official result" when the game was closed. Only the game's official
        time counts (OFFICIAL_ONLY): the game saved none, so the run doesn't count (no DNF), saying why, at once."""
        self.finish()
        self.a._started_again('daily', 1, self.a._game_save())   # the save has no result of it
        self.a.on_result.assert_not_called()
        self.assertTrue(self.a.dailies[1]['voided'])
        self.assertEqual((self.a.awaiting, waiting.load()), ([], []))
        self.assertIn("because you restarted from the results screen, so that run doesn't count",
                      self.a.sub_l.configure.call_args.kwargs['text'])

    def test_without_official_only_the_apps_time_goes_in(self):
        """Up to 0.1.5 (OFFICIAL_ONLY off): a run whose time the game lost went with the app's clock, the server
        deciding (server/src/apptime.js)."""
        self.finish()
        with mock.patch.object(app_mod, 'OFFICIAL_ONLY', False):
            self.a._started_again('daily', 1, self.a._game_save())
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs'], r['appTime']), ('finished', 203284, True))
        self.assertIn('results screen', r['lost'])
        self.assertIn("The app's time goes in instead", self.a.sub_l.configure.call_args.kwargs['text'])

    def test_started_again_without_reading_the_save_or_on_another_stage_waits_on(self):
        self.finish()
        self.a._started_again('daily', 1, None)                  # the save could not be read
        self.a._started_again('daily', 2, self.a._game_save())   # the other daily
        self.a._started_again('tt', 1, self.a._game_save())      # a time trial stage
        self.a.on_result.assert_not_called()
        self.assertEqual(len(self.a.awaiting), 1)

    def test_no_result_from_the_game_does_not_count(self):
        self.finish()
        for _ in range(3):
            self.check(running=False)                            # the game closed and saved nothing new
        self.a.on_result.assert_not_called()                     # (no app's time, and no DNF)
        self.assertEqual(self.a.awaiting, [])
        self.assertIn("SS1 didn't count: the game closed before saving its official result. Press START OFFICIAL RALLY",
                      self.a.sub_l.configure.call_args.kwargs['text'])

    def test_a_run_that_does_not_count_is_sent_as_void_and_the_daily_is_open_again(self):
        """No DNF for a committed run without the game's time: the server is told it doesn't count (status 'void': it
        forgets that start, server/src/voids.js), and here the daily isn't driven, so START OFFICIAL RALLY works again
        and the next run counts."""
        a = self.a
        a.api, a.s, a.local_runs = mock.Mock(configured=True), {'token': 't', 'steamId': '7656'}, []
        a.api.submit.return_value = {'ok': True, 'status': 'void', 'counted': False}
        self.finish()
        with mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            for _ in range(3):
                self.check(running=False)
        body = a.api.submit.call_args.args[0]
        self.assertEqual((body['status'], body['totalMs'], body['clockMs']), ('void', None, 203284))
        self.assertIn('closed', body['reason'])
        a.on_result.assert_not_called()
        d = a.dailies[1]
        self.assertEqual((d['voided'], d['norally'], d['started_once']), (True, True, False))
        self.assertFalse(a._driven(1))
        with mock.patch('acr_daily.app.waiting.note'):
            self.assertTrue(a.commit(1), 'START OFFICIAL RALLY again')

    def new(self):
        t = self.t
        return t.entry('WelesS4HafrenSouthFullForward', [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)],
                       self.T0)

    def test_a_result_already_in_the_save_at_the_start_counts_when_its_time_is_the_runs(self):
        # 11 Nov 2026: two dailies the game had saved went as DNFs; their results matched the app's clock to the ms
        self.write([self.old, self.new()])
        self.finish()                                            # (the save at the start: the result in it already)
        self.check()
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs']), ('finished', 293284))

    def test_a_result_there_at_the_start_with_another_time_is_not_this_run(self):
        self.write([self.old, self.new()])
        self.finish(clock_ms=203284 + 2000)                      # within 5 s, but it was there before the run
        for _ in range(3):
            self.check(running=False)
        self.a.on_result.assert_not_called()                     # (nothing new saved: it doesn't count)
        self.assertTrue(self.a.dailies[1]['voided'])

    def test_a_result_the_watch_missed_is_found_by_a_last_look(self):
        self.finish()
        self.write([self.old, self.new()])
        with mock.patch('acr_daily.saveslot.SaveWatch.look', return_value=None):
            for _ in range(3):
                self.check(running=False)
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs']), ('finished', 293284))

    def test_the_wait_is_logged(self):
        self.finish()
        for _ in range(3):
            self.check(running=False)
        with open(os.path.join(app_mod.settings.DIR, 'official.log'), encoding='utf-8') as f:
            log = f.read()
        self.assertIn('finished (WelesS4HafrenSouthFullForward, HyundaiI20NRally2), clock 203284 ms', log)
        self.assertIn('last look (game closed)', log)
        self.assertIn('no official time: the game closed before saving its official result', log)
        self.assertIn('not counted (no official time): the game closed before saving its official result', log)

    def test_a_run_the_game_lost_sends_the_games_log(self):
        """13 Nov 2026: stuck on the loading screen after SS1, the game closed 12 minutes later, its save untouched from
        3 s after the finish: what the game's own log says goes to the admin with the run (gamelog.py)."""
        self.a.api, self.a.s = mock.Mock(site='https://acrdaily.com'), {'ghostCars': {'on': True}}
        self.a.dailies[1]['ch']['id'] = '2026-11-13/1'
        r = self.finish()
        with mock.patch('acr_daily.gamelog.send') as send:
            for _ in range(3):
                self.check(running=False)
        self.assertEqual(self.a.api._queue.call_args.args[0]['status'], 'void')   # (signed out: it waits to be sent)
        api, runs, area, url, context = send.call_args.args
        self.assertEqual((api, area, url), (self.a.api, 'daily', None))
        self.assertEqual(runs, [{'id': 'daily:2026-11-13/1:%s' % r['startedAt'], 'what': 'SS1 2026-11-13',
                                 'stage': 'WelesS4HafrenSouthFullForward', 'car': 'HyundaiI20NRally2',
                                 'why': 'the game closed before saving its official result',
                                 'startedAt': r['startedAt'], 'clockMs': 203284, 'resets': 1, 'noRallyWeekend': False}])
        self.assertIn('ghost cars on, in the game', context)
        send.call_args.kwargs['on_sent'](41)                     # (its thread: the driver is told on the Tk one)
        self.a.root.after.call_args.args[1]()
        self.assertIn('#41', self.a.sub_l.configure.call_args.args[0]['text'])

    def test_the_report_gets_what_the_game_did_while_the_run_waited(self):
        """13 Nov 2026: no game log on players' PCs. While a run waits, the app keeps what the game does (gamewatch.py:
        the stage left or not, "Not Responding", how its process ended) and the report carries it."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from test_gamewatch import FakeWin
        win = FakeWin()
        self.a.api, self.a.s, self.a.league_run = mock.Mock(site='https://acrdaily.com'), {}, None
        self.a.dailies[1]['ch']['id'] = '2026-11-13/1'
        with mock.patch('acr_daily.gamewatch._win', return_value=win), \
                mock.patch('acr_daily.saveslot.game_pids', return_value=[4242]):
            self.finish()
            self.a._game_watch_on().telemetry('stage')           # (each tick: the results screen)
            win.hung_now = True
            self.check()
            self.a._game_watch_on().telemetry('none')
            win.code = 1                                         # ended from the Task Manager
            with mock.patch('acr_daily.gamelog.send') as send:
                for _ in range(3):
                    self.check(running=False)
        seen = [x for _t, x in send.call_args.kwargs['watch']['events']]
        self.assertIn('Windows: the game is "Not Responding"', seen)
        self.assertIn('the game ended: ' + app_mod.gamewatch.exit_words(1), seen)
        self.check(running=False)                                # (nothing waits now: the watch let go)
        self.assertIsNone(self.a._game_watch_on())

    def test_a_lost_result_whose_save_holds_no_rally_weekend_result_says_single_rally_stage(self):
        """14 Nov 2026 (reports #17, #21): the game wrote its save after the finish, yet it held no Rally Weekend result
        at all: a Single Rally Stage, which keeps no time. The driver is told; the save goes with the report."""
        self.a.api, self.a.s, self.a.league_run = mock.Mock(site='https://acrdaily.com'), {}, None
        self.a.dailies[1]['ch']['id'] = '2026-11-14/1'
        self.write([])                                           # (the save as a Single Rally Stage leaves it)
        self.finish()
        os.utime(self.save, (self.T0 + 600, self.T0 + 600))      # written after the finish
        with mock.patch('acr_daily.gamelog.send') as send:
            for _ in range(3):
                self.check(running=False)
        r = self.a.api._queue.call_args.args[0]                  # (sent as a run that doesn't count)
        self.assertTrue(r['noRallyWeekend'])
        self.assertEqual((r['status'], r['reason']), ('void', app_mod.NO_RALLY_WEEKEND))   # (the reason: no Rally Weekend)
        self.assertTrue(send.call_args.args[1][0]['noRallyWeekend'])
        self.assertIsNotNone(send.call_args.kwargs['save'])
        # a restart from the results screen is the reason itself: no hint
        self.write([])
        self.finish()
        self.a._started_again('daily', 1, self.a._game_save())
        self.assertNotIn('noRallyWeekend', self.a.api._queue.call_args.args[0])

    def test_the_driver_hears_and_sees_how_the_wait_ended(self):
        """ACRK's way (14 Nov 2026): a sound and a notification once the game's time is in, or lost, so the driver knows
        when it is safe to go on (notify.py)."""
        self.a.s, self.a.league_run = {}, None
        self.finish()
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        self.check()
        self.assertEqual(self.a.notifier.sent[-1], (True, 'Official time saved', 'SS1: 4:53.284 (3:23.284 + 90 s penalty)'))
        self.write([self.old])
        self.finish()
        for _ in range(3):
            self.check(running=False)
        self.assertEqual(self.a.notifier.sent[-1][:2], (False, 'No official time'))

    def test_another_runs_time_or_a_failing_report_changes_nothing(self):
        self.a.api = mock.Mock(site='https://acrdaily.com')
        self.finish(clock_ms=150000)
        self.write([self.old, self.new()])                       # the game saved another run's time: no log
        with mock.patch('acr_daily.gamelog.send') as send:
            for _ in range(3):
                self.check(running=False)
        send.assert_not_called()
        r = self.a.on_result.call_args.args[0]                   # (a time the game saved, not this run's: a DNF)
        self.assertEqual((r['status'], 'appTime' in r), ('dnf', False))
        self.write([self.old])                                   # another run, which the game never saved
        self.finish()
        with mock.patch('acr_daily.gamelog.send', side_effect=RuntimeError('boom')):
            for _ in range(3):
                self.check(running=False)                        # (the report failing never stops the wait)
        self.assertEqual((self.a.api._queue.call_args.args[0]['status'], self.a.awaiting), ('void', []))

    def test_a_result_with_another_time_is_not_this_run(self):
        self.finish(clock_ms=150000)
        t = self.t
        self.write([self.old, t.entry('WelesS4HafrenSouthFullForward',
                                      [t.run('HyundaiI20NRally2', [87.618, 160.034, 203.284], 90)], self.T0)])
        self.check()
        self.a.on_result.assert_not_called()
        for _ in range(3):
            self.check(running=False)
        r = self.a.on_result.call_args.args[0]
        self.assertEqual(r['status'], 'dnf')
        self.assertIn('3:23.284', r['reason'])


DAY = '2026-10-09'


def credits(entered=False, enabled=True, date=DAY, **kw):
    return dict({'enabled': enabled, 'signedIn': True, 'earning': True, 'balance': 150, 'claimable': False,
                 'wager': {'date': date, 'slot': 2, 'stake': 100, 'entered': entered}}, **kw)


class WagerDaily(unittest.TestCase):
    """Credits (a prototype): the wager daily is driven with a stake. DRIVE asks for it last, before the first run, and
    goes on once it is in without asking its questions again; without one DRIVE stops, and a run started anyway (from
    the game's menu) is not counted."""

    def setUp(self):
        self.later = []                            # what ui() hands to the Tk thread (run_ui runs it)
        self.threads = []                          # threads started (run_threads runs them)

    def app(self, entered=False, enabled=True, date=DAY):
        a = App.__new__(App)
        a.root, a.api, a.sub_l = mock.Mock(), mock.Mock(), mock.Mock()
        a.root.after.side_effect = lambda ms, fn: self.later.append(fn)
        a.acct_l, a.acct_b, a.steam_b = mock.Mock(), mock.Mock(), mock.Mock()
        a.s = {'steamId': '7', 'token': 't' * 64, 'name': 'me'}
        a.recorder, a.cards = None, {}
        a.credits = credits(entered, enabled, date)
        a.dailies = {2: {'ch': {'id': DAY + '/2', 'date': DAY, 'slot': 2, 'wager': {'stake': 100}, 'car': 'C'},
                         'board': {'entries': []}}}
        return a

    def run_ui(self):
        while self.later:
            self.later.pop(0)()

    def run_threads(self):
        while self.threads:
            self.threads.pop(0)()

    def patches(self, answer=True, sync=True):
        """The stake question answered `answer`; threads run at once (sync) or when run_threads() says."""
        start = (lambda target, daemon: mock.Mock(start=target)) if sync else \
            (lambda target, daemon: mock.Mock(start=lambda: self.threads.append(target)))
        return mock.patch('acr_daily.app.messagebox.askyesno', return_value=answer), \
            mock.patch('acr_daily.app.threading.Thread', side_effect=start)

    def ask(self, a, answer, then=None):
        """_wager_first answered `answer` -> (go on now?, stake questions asked); self.question: its text,
        self.info: the notes shown instead."""
        q, t = self.patches(answer)
        with q as q, t, mock.patch('acr_daily.app.messagebox.showwarning'), \
                mock.patch('acr_daily.app.messagebox.showinfo') as self.info:
            go = a._wager_first(2, then or mock.Mock())
        self.question = q.call_args.args[1] if q.called else ''
        return go, q.call_count

    def test_staked_then_drives(self):
        a = self.app()
        then = mock.Mock()
        self.assertEqual(self.ask(a, True, then), (False, 1))    # DRIVE goes on once the stake is in
        self.assertIn('Stake 100 credits on SS2? You have 150', self.question)
        a.api.wager.assert_called_once_with(2, DAY)              # (with the daily's date: today's only)
        a.refresh_credits = mock.Mock()
        self.run_ui()
        then.assert_called_once()
        a.refresh_credits.assert_called_once()
        self.assertIsNone(a._drive_wait)
        self.assertEqual(self.ask(a, True), (True, 0))           # staked: not asked again

    def test_no_stake_no_drive(self):
        a = self.app()
        self.assertEqual(self.ask(a, False), (False, 1))         # no: DRIVE stops, nothing staked
        self.assertEqual(self.ask(a, False), (False, 1))         # asked again at the next DRIVE
        a.api.wager.assert_not_called()

    def test_not_asked(self):
        for a in (self.app(entered=True), self.app(enabled=False)):
            self.assertEqual(self.ask(a, True), (True, 0))
        a = self.app()
        a.dailies[2]['ch'].pop('wager')                         # the free daily
        self.assertEqual(self.ask(a, True), (True, 0))

    def test_drive_stops_and_says_why_when_there_is_no_stake_to_give(self):
        a = self.app()
        a.credits['balance'] = 40
        self.assertEqual(self.ask(a, True), (False, 0))
        self.assertIn('you have 40', self.info.call_args.args[1])
        a.credits['earning'] = False                            # no finished run yet: no credits at all
        self.assertEqual(self.ask(a, True), (False, 0))
        self.assertIn('Finish SS1 first', self.info.call_args.args[1])
        a = self.app()
        a.credits['signedIn'] = False                           # (the sign-in ran out)
        self.assertEqual(self.ask(a, True), (False, 0))
        self.assertIn('Sign in with Steam', self.info.call_args.args[1])
        a.s['token'] = ''
        self.assertEqual(self.ask(a, True), (False, 0))
        a.api.wager.assert_not_called()

    def drive(self, a, restart_answer=True):
        """DRIVE on SS2 with the game running: the restart question, then the stake (its request left on its way).
        -> (stake questions, restart questions)"""
        _, t = self.patches(True, sync=False)
        with t, mock.patch('acr_daily.app.saveslot.game_running', return_value=True), \
                mock.patch('acr_daily.app.messagebox.askyesno', side_effect=[restart_answer, True]) as q:
            a.drive_click(2)
        texts = [c.args[1] for c in q.call_args_list]
        return sum('Stake' in x for x in texts), sum('is running' in x for x in texts)

    def bare_drive(self, a):
        a._league_before_daily = mock.Mock(return_value=False)
        a._restart_into, a._setup_and_launch = mock.Mock(), mock.Mock()

    def test_drive_clicks_while_the_stake_is_on_its_way_wait_and_nothing_is_asked_twice(self):
        a = self.app()
        self.bare_drive(a)
        self.assertEqual(self.drive(a), (1, 1))                  # restart question, then the stake
        self.assertEqual(self.drive(a), (0, 0))                  # clicked again meanwhile: nothing asked, nothing done
        self.assertIn('Staking on SS2', a.sub_l.configure.call_args.kwargs['text'])
        a._league_before_daily.assert_called_once()              # ("set your rally aside?" said once)
        a._restart_into.assert_not_called()
        a.refresh_credits = mock.Mock()
        with mock.patch('acr_daily.app.saveslot.game_running', return_value=True):
            self.run_threads()
            self.run_ui()
        a.api.wager.assert_called_once_with(2, DAY)
        a._restart_into.assert_called_once_with(2)               # DRIVE goes on, without its questions again
        a._league_before_daily.assert_called_once()

    def test_declining_the_restart_takes_no_stake(self):
        a = self.app()
        self.bare_drive(a)
        self.assertEqual(self.drive(a, restart_answer=False), (0, 1))
        a.api.wager.assert_not_called()

    def test_a_drive_stopped_after_the_stake_says_it_stands(self):
        a = self.app()
        self.bare_drive(a)
        self.drive(a)
        a.dailies[2]['judge'] = mock.Mock(state='running')       # a run started in the game meanwhile
        a.refresh_credits = mock.Mock()
        self.run_threads()
        self.run_ui()
        a._restart_into.assert_not_called()                      # never closed under a run
        self.assertIn('SS2 stake is in', a.sub_l.configure.call_args.kwargs['text'])

    def test_yesterdays_stake_is_not_todays(self):
        a = self.app(entered=True, date='2026-10-08')            # after midnight UTC, the credits not fetched again yet
        self.assertEqual(self.ask(a, False), (False, 1))         # today's stake is asked for
        a.coin_img = 'coin'
        wager = mock.Mock()
        wager.cget.return_value = 'WAGER DAILY  ·  STAKED: 100'
        wager.winfo_manager.return_value = ''                     # (not shown yet: it gets its line)
        a.cards = {2: {'wager': wager}}
        a._wager_marks()
        wager.configure.assert_called_with(text='WAGER DAILY  ·  STAKE TO DRIVE: 100', fg=app_mod.ACC, image='coin')
        wager.pack.assert_called_once()
        a.credits['wager']['date'] = DAY
        wager.cget.return_value = 'WAGER DAILY  ·  STAKE TO DRIVE: 100'
        a._wager_marks()
        wager.configure.assert_called_with(text='WAGER DAILY  ·  STAKED: 100', fg=app_mod.GOOD, image='coin')

    def test_new_dailies_of_a_new_day_fetch_the_credits_again(self):
        a = self.app()
        a.dailies[2]['ch'].update(id='2026-10-08/2', date='2026-10-08')      # yesterday's, still on screen
        a._show_active, a.refresh_board, a.refresh_credits = mock.Mock(), mock.Mock(), mock.Mock()
        chs = [{'id': DAY + '/2', 'date': DAY, 'slot': 2, 'car': 'C'}]
        a._set_challenges(chs)
        a.refresh_credits.assert_called_once()
        a._set_challenges(chs)                                    # the same day again: not again
        a.refresh_credits.assert_called_once()

    def test_drive_before_the_credits_came_in_gets_them_first(self):
        a = self.app()
        a.credits = None
        a.api.credits.return_value = credits()
        then = mock.Mock()
        self.assertEqual(self.ask(a, False, then), (False, 0))   # (the credits asked for first)
        self.assertIn('Getting your credits', a.sub_l.configure.call_args.kwargs['text'])
        q, t = self.patches(True)
        with q as q, t:
            self.run_ui()                                        # the credits in: the stake asked for, and taken
            self.run_ui()                                        # the stake in: DRIVE goes on
        self.assertEqual(q.call_count, 1)
        a.api.wager.assert_called_once_with(2, DAY)
        then.assert_called_once()
        self.assertEqual(a.credits['balance'], 150)

    def test_credits_not_reachable_at_drive_stop_it(self):
        a = self.app()
        a.credits = None
        a.api.credits.side_effect = api_mod.ApiError('server not reachable')
        then = mock.Mock()
        self.ask(a, True, then)
        with mock.patch('acr_daily.app.messagebox.showwarning') as warn:
            self.run_ui()
        self.assertIn('Couldn\'t load your credits', warn.call_args.args[1])
        then.assert_not_called()                                 # (SS2 is driven with a stake: none without them)
        self.assertIsNone(a._drive_wait)
        a.api.wager.assert_not_called()

    def test_a_failed_claim_keeps_the_balance(self):
        a = self.app()
        a.api.credits.return_value = credits(claimable=True)
        a.api.claim_credits.side_effect = api_mod.ApiError('server not reachable')
        self.assertEqual(a._fetch_credits(), (credits(claimable=True), ''))
        a.api.claim_credits.side_effect = None
        a.api.claim_credits.return_value = {'claimed': True, 'amount': 50, 'balance': 200, 'streak': 2}
        c, msg = a._fetch_credits()
        self.assertEqual((c['balance'], c['claimable']), (200, False))
        self.assertEqual(msg, 'Daily bonus: +50 credits. You have 200.')
        a.api.claim_credits.return_value = {'claimed': True, 'amount': 100, 'welcome': 50, 'balance': 100, 'streak': 1}
        self.assertEqual(a._fetch_credits()[1], 'Welcome and daily bonus: +100 credits. You have 100.')

    def stake_fails(self, a, err):
        a.api.wager.side_effect = err
        a.refresh_credits = mock.Mock()
        with mock.patch('acr_daily.app.messagebox.showwarning') as warn:
            self.ask(a, True)
            self.run_ui()
        a.refresh_credits.assert_called_once()
        self.assertIsNone(a._drive_wait)
        return warn.call_args.args[1]

    def test_no_answer_to_the_stake_may_have_taken_it_and_asks_again(self):
        a = self.app()
        self.assertIn('may have gone through', self.stake_fails(a, api_mod.ApiError('server not reachable (timed out)')))
        self.assertEqual(self.ask(a, False), (False, 1))         # asked again
        a.credits['wager']['entered'] = True                     # ...unless the credits show it went in
        self.assertEqual(self.ask(a, True), (True, 0))

    def test_a_stake_refused_says_why_and_drive_stops(self):
        a = self.app()
        text = self.stake_fails(a, api_mod.ApiError('the stake is 100 credits: you have 40', 402))
        self.assertIn('Not staked: the stake is 100 credits', text)
        self.assertIn('Not staked', text)

    def test_a_run_on_this_pc_not_sent_yet_counts_as_started(self):
        import tempfile
        a = self.app()
        self.assertFalse(a._driven(2))
        a.dailies[2].pop('started_once', None)
        f = os.path.join(tempfile.mkdtemp(), 'results.jsonl')
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write('{"challengeId": "%s/2", "gameSteamIds": ["7"]}\nnot json\n{"challengeId": "league:3:0"}\n' % DAY)
        with mock.patch('acr_daily.settings.RESULTS', f):
            a.local_runs = app_mod.local_runs()
        self.assertEqual(a.local_runs, ((DAY + '/2', ('7',)),))
        self.assertTrue(a._driven(2))
        b = self.app()
        b.local_runs = ((DAY + '/2', ('8',)),)                    # another Steam account's run on this PC
        self.assertFalse(b._driven(2))
        b.dailies[2].pop('started_once', None)
        b.awaiting = [{'slot': 2, 'result': {'challengeId': DAY + '/2'}}]   # waiting for the game's official time
        self.assertTrue(b._driven(2))

    def test_sign_out_forgets_the_credits(self):
        a = self.app(entered=True)
        a.api.logout.side_effect = lambda: a.s.update(token='', steamId='', name='')
        a.refresh_leagues = mock.Mock()
        wager = mock.Mock()
        wager.cget.return_value = 'WAGER DAILY  ·  STAKED: 100'
        wager.winfo_manager.return_value = 'pack'
        a.cards = {2: {'wager': wager}}
        a.login_click()
        self.assertIsNone(a.credits)
        wager.configure.assert_called_with(text='', fg=app_mod.ACC, image='')
        wager.pack_forget.assert_called_once()                    # (its line goes)
        self.assertIn('Not signed in', a.acct_l.configure.call_args.kwargs['text'])
        self.assertEqual(self.ask(a, True), (False, 0))           # no stake asked for: sign in first
        self.assertIn('Sign in with Steam', self.info.call_args.args[1])
        a._set_credits(credits())                                 # an answer asked for before the sign-out
        self.assertIsNone(a.credits)

    def test_signed_in_the_account_row_gives_way_to_the_driver_card(self):
        a = self.app()                                            # (the name, the balance, Sign out: on the card, tabsui.py)
        a._acct_row, a._head_rule = mock.Mock(), mock.Mock()
        a._account_ui()
        a._acct_row.pack_forget.assert_called_once()
        a.acct_l.configure.assert_not_called()
        a.s['token'] = ''                                         # signed out: in the card's place, with the Steam button
        a._acct_row.winfo_manager.return_value = ''
        a._account_ui()
        self.assertEqual(a._acct_row.pack.call_args.kwargs['after'], a._head_rule)
        self.assertIn('Not signed in', a.acct_l.configure.call_args.kwargs['text'])
        a.steam_b.pack.assert_called_once()

    def test_a_run_without_a_stake_is_not_counted(self):
        a = self.app()
        self.assertTrue(a._needs_stake(2))
        for b in (self.app(entered=True), self.app(enabled=False)):
            self.assertFalse(b._needs_stake(2))
        b = self.app()
        b.credits = None                                         # not known: it may count (the server decides)
        self.assertFalse(b._needs_stake(2))
        d = a.dailies[2]
        d['unstaked'], d['judge'] = True, mock.Mock(state='finished')
        self.assertFalse(a._driven(2))                           # it never counted: not a first start
        self.assertFalse(d.get('started_once'))
        with mock.patch('acr_daily.app.threading.Thread') as t:
            a._send_live(2, d['judge'], mock.Mock(), 'live')      # (no live position: the server takes it only staked)
        t.assert_not_called()
        d['staked'] = True                                       # staked since: the next run is the first
        self.assertFalse(a._needs_stake(2))
        d['unstaked'], d['judge'] = False, mock.Mock(state='running')
        self.assertFalse(a._driven(2))
        self.assertTrue(d['started_once'])

    def test_the_free_dailys_bonus_is_said_when_the_run_is_in(self):
        a = self.app()
        a.refresh_board, a.refresh_credits = mock.Mock(), mock.Mock()
        a.api.submit.return_value = {'ok': True, 'counted': True, 'rank': 3, 'credits': 50}
        with mock.patch('acr_daily.app.settings.append_result'), \
                mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            a.on_result({'challengeId': DAY + '/1'})
            self.run_ui()
        self.assertIn('Rank 3 today. +50 credits for finishing it.', a.sub_l.configure.call_args.args[0]['text'])
        a.api.submit.side_effect = api_mod.ApiError('invalid run: SS2 is the wager daily, driven with a stake', 402)
        with mock.patch('acr_daily.app.settings.append_result'), \
                mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            a.on_result({'challengeId': DAY + '/2'})
            self.run_ui()
        self.assertIn('Not counted: invalid run: SS2', a.sub_l.configure.call_args.args[0]['text'])

    def test_a_dnf_from_the_server_is_said_as_one(self):
        """14 Nov 2026: the game lost two first runs with respawns; the server makes them DNFs (server/src/apptime.js),
        and the driver is told so, not "Submitted.\""""
        a = self.app()
        a.refresh_board, a.refresh_credits = mock.Mock(), mock.Mock()
        a.api.submit.return_value = {'ok': True, 'status': 'dnf', 'counted': True, 'reason': "the game closed before "
                                     "saving its official result, and the app's time only counts without respawns (1 seen)"}
        with mock.patch('acr_daily.app.settings.append_result'), \
                mock.patch('acr_daily.app.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            a.on_result({'challengeId': DAY + '/1', 'appTime': True, 'resets': 1})
            self.run_ui()
        said = a.sub_l.configure.call_args.args[0]['text']
        self.assertTrue(said.startswith('DNF: the game closed before saving'), said)
        self.assertNotIn('Submitted', said)


class CreditsApi(unittest.TestCase):
    def test_a_run_the_server_refused_is_not_queued(self):
        import tempfile
        a = api_mod.Api({'token': 'x' * 64})
        pending = os.path.join(tempfile.mkdtemp(), 'pending.json')
        with mock.patch('acr_daily.settings.PENDING', pending), mock.patch('acr_daily.settings.DIR', os.path.dirname(pending)):
            for err, queued in ((api_mod.ApiError('invalid run: SS2 is the wager daily', 402), 0),
                                (api_mod.ApiError('invalid run: it started before your stake', 409), 0),
                                (api_mod.ApiError('server not reachable'), 1), (api_mod.ApiError('error 503', 503), 2)):
                with mock.patch.object(a, '_req', side_effect=err), self.assertRaises(api_mod.ApiError):
                    a.submit({'challengeId': DAY + '/2'})
                self.assertEqual(len(a._pending()), queued)

    def test_runs_reach_the_server_in_the_order_driven(self):
        """The server counts each daily's first run to arrive: a new run never overtakes one still queued."""
        import tempfile
        a = api_mod.Api({'token': 'x' * 64})
        pending = os.path.join(tempfile.mkdtemp(), 'pending.json')
        sent = []
        with mock.patch('acr_daily.settings.PENDING', pending), mock.patch('acr_daily.settings.DIR', os.path.dirname(pending)):
            with mock.patch.object(a, '_req', side_effect=api_mod.ApiError('server not reachable')), self.assertRaises(api_mod.ApiError):
                a.submit({'challengeId': DAY + '/1', 'n': 1})                 # offline: queued
            with mock.patch.object(a, '_req', side_effect=api_mod.ApiError('server not reachable')), \
                    self.assertRaisesRegex(api_mod.ApiError, 'older runs'):
                a.submit({'challengeId': DAY + '/1', 'n': 2})                 # still offline: behind it, not sent
            self.assertEqual([b['n'] for b in a._pending()], [1, 2])
            with mock.patch.object(a, '_req', side_effect=lambda m, p, body, **k: sent.append(body['n']) or {'counted': False}):
                a.submit({'challengeId': DAY + '/1', 'n': 3})                 # back online: 1, 2, then 3
        self.assertEqual(sent, [1, 2, 3])
        self.assertEqual(a._pending() if os.path.exists(pending) else [], [])

    def test_the_stake_names_its_daily_and_runs_sent_later_bring_the_credits(self):
        import json
        import tempfile
        a = api_mod.Api({'token': 'x' * 64})
        with mock.patch.object(a, '_req') as req:
            a.wager(2, DAY)
        self.assertEqual(req.call_args.args[2], {'slot': 2, 'date': DAY})
        pending = os.path.join(tempfile.mkdtemp(), 'pending.json')
        with open(pending, 'w', encoding='utf-8') as f:
            json.dump([{'challengeId': DAY + '/1'}], f)
        sent = mock.Mock()
        with mock.patch('acr_daily.settings.PENDING', pending), mock.patch.object(a, '_req'):
            self.assertEqual(a.flush(sent), 0)
            sent.assert_called_once()
            a.flush(sent)                                       # nothing left to send: not again
        sent.assert_called_once()


class TooOldForTheServer(unittest.TestCase):
    def test_refused_run_is_not_queued_and_queued_ones_are_dropped(self):
        a = api_mod.Api({'token': 'x' * 64})
        refuse = api_mod.ApiError('invalid: ACR Daily 0.14.1 is too old', api_mod.TOO_OLD)
        with mock.patch.object(a, '_req', side_effect=refuse), mock.patch.object(a, '_queue') as q:
            with self.assertRaises(api_mod.ApiError):
                a.submit({'challengeId': '2026-10-06/1'})
            q.assert_not_called()
        offline = api_mod.ApiError('server not reachable')
        with mock.patch.object(a, '_req', side_effect=offline), mock.patch.object(a, '_queue') as q:
            with self.assertRaises(api_mod.ApiError):
                a.submit({'challengeId': '2026-10-06/1'})
            q.assert_called_once()


if __name__ == '__main__':
    unittest.main()


class OnScreen(unittest.TestCase):
    """The in-game displays and the timer land on a screen, whatever its size (defaults set on a 3440 x 1440 one)."""

    def test_a_position_off_the_screen_comes_into_view(self):
        from acr_daily import widgets
        hd = (0, 0, 1920, 1032)                                        # 1920 x 1080 without the taskbar
        self.assertEqual(widgets.clamp(24, 1080, 260, 190, hd), (24, 842))   # the map's old default
        self.assertEqual(widgets.clamp(4000, -20, 300, 120, hd), (1620, 0))  # left on a screen unplugged since
        self.assertEqual(widgets.clamp(60, 60, 300, 120, hd), (60, 60))      # on screen: left alone

    def test_the_defaults_fit_a_full_hd_screen(self):
        from acr_daily import widgets
        for k, d in widgets.DEFAULTS.items():
            cls = widgets.CLASSES[k]
            self.assertLessEqual(d['x'] + cls.W, 1920, k)
            self.assertLessEqual(d['y'] + cls.H, 1032, k)            # above the taskbar
