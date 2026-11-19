"""The displays in the game (ingamehud.py): what the timer window, RANKED's turn window and the stage strip say, as
displays the game mod lays out itself (mod/ACRDailyGhosts/Scripts/hud.lua), the file it reads, and when the app's own
windows over the game stand down."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import app as app_mod, ingamehud as hud, modinstall  # noqa: E402

LIVE = {'status': 'live', 'badge': ('● LIVE', '#FFFFFF', '#E10600'), 'title': 'TT3 · LONDON', 'time': ('1:23.45', '#F4F4F5'),
        'ms': 83450, 'running': True, 'pen': '+10 s', 'line': ('−0.84 to P1 · gaining', '#30D158'), 'alert': None,
        'panel': None, 'progress': None}
GATE = {'mode': 'wait', 'no': 0, 'edge': '#FF453A', 'kicker': 'RANKED · RALLY2', 'stage': 'SS1 · ELATIA', 'head': 'WAIT',
        'big': '1:20', 'line': '2 drivers before you: your turn in 1:20 at the latest.',
        'short': '2 drivers before you  ·  Turn: Ben · 0:12', 'now': 'Turn: Ben · 0:12', 'left': 80000, 'span': 120000,
        'rule': 'Started on red: the seconds you jump are added.', 'drive': False,
        'rows': [('1', 'Ben', 'TURN', 'turn', False), ('2', 'Ann', '≤ 0:20', 'waiting', False),
                 ('3', 'YOU', '≤ 0:40', 'waiting', True), ('4', 'Carl', '≤ 1:00', 'waiting', False),
                 ('5', 'Dan', '≤ 1:20', 'waiting', False)]}


def lines(panels):
    return hud.encode(1, 10.0, panels).splitlines()


class Displays(unittest.TestCase):
    def test_the_acr_strip_says_how_the_run_stands_never_a_second_clock(self):
        a = hud.acr(LIVE, pos='P3 / 18')
        self.assertEqual((a['chip'], a['chip_bg'], a['chip_fg'], a['dot'], a['kind']), ('LIVE', 'E10600', 'FFFFFF', 1, 'good'))
        self.assertEqual((a['pos'], a['line'], a['line_c']), ('P3 / 18', '−0.84 to P1 · gaining', '30D158'))
        self.assertNotIn('time', a)                              # (the game's own clock is right above it)
        self.assertNotIn('run', a)
        c = hud.acr(LIVE, clock=True)                            # (asked for: the driver hides the game's HUD)
        self.assertEqual((c['time'], c['run']), ('1:23.45', 83450))
        self.assertNotIn('logo', a)
        self.assertEqual(hud.acr(LIVE, logo='C:\\x\\acrdaily-d.png')['logo'], 'C:\\x\\acrdaily-d.png')   # (ACR Daily's D)
        self.assertIsNone(hud.acr(dict(LIVE, status='standby')))   # (waiting for the game: nothing to say)
        self.assertIsNone(hud.acr(dict(LIVE, status='wait')))      # (RANKED's own states: on its start board)
        self.assertEqual(hud.acr(dict(LIVE, status='live_off', badge=('NOT COUNTING', '#D4D4D8', '#1C1C21')))['kind'], 'off')

    def test_the_note_its_points_and_its_bar_while_the_time_comes(self):
        ov = dict(LIVE, status='finished', alert={'head': 'SAVE YOUR TIME', 'lines': ['Go on', '', 'Restarting loses it'],
                                                  'bg': '#1C1C21', 'head_fg': '#FF9F0A', 'fg': '#F4F4F5', 'dot_fg': '#FF9F0A',
                                                  'bar': '#FF9F0A'}, progress=('wait', 0, '#FF9F0A'))
        n = hud.note(ov)
        self.assertEqual((n['head'], n['point'], n['edge'], n['bar'], n['bar_c']),
                         ('SAVE YOUR TIME', ['Go on', 'Restarting loses it'], 'FF9F0A', 'wait', 'FF9F0A'))
        self.assertEqual(hud.note(dict(ov, progress=('frac', 0.4, '#FF4655')))['bar'], '0.4000')
        self.assertNotIn('bar', hud.note(dict(ov, progress=('frac', 1.0, '#30D158'))))    # (full: says nothing more)
        self.assertIsNone(hud.note(LIVE))

    def test_the_splits_standings_my_row_marked(self):
        b = hud.board(dict(LIVE, panel={'title': 'SPLIT 2', 'pos': 'P3 / 18', 'pb': ('vs your best today −0.830', '#30D158'),
                                        'rows': [('1', 'blah_walt', '', False), ('3', 'Me', '+2.010', True)]}))
        self.assertEqual(b['row'], ['1\tblah_walt\t\t0', '3\tMe\t+2.010\t1'])
        self.assertEqual((b['pos'], b['pb'], b['pb_c']), ('P3 / 18', 'vs your best today −0.830', '30D158'))

    def test_the_start_board_the_logo_one_line_three_of_the_queue(self):
        g = hud.gate(dict(GATE, series='rally2'), logo='C:\\x\\rally2-logo.png')
        self.assertEqual((g['mode'], g['head'], g['left'], g['span'], g['logo']), ('wait', 'WAIT', 80000, 120000, 'C:\\x\\rally2-logo.png'))
        self.assertEqual(g['line'], '2 drivers before you · Turn: Ben · 0:12')    # (the short one: the time said once)
        self.assertEqual([r.split('\t')[1] for r in g['row']], ['Ben', 'YOU', 'Carl'])   # (the turn, me, the next)
        self.assertEqual(g['row'][1].split('\t')[4], '1')
        self.assertEqual(g['rule'], 'Started on red: the seconds you jump are added.')
        late = hud.gate(dict(GATE, mode='late', big='', left=None))
        self.assertNotIn('left', late)
        self.assertEqual(hud.pick_rows(GATE['rows'][:2]), [r[:4] + (0,) for r in GATE['rows'][:2]])

    def test_the_others_and_the_ghosts_as_ticks(self):
        v = {'progress': 0.42, 'splits': [0.33], 'others_prog': [('Ann', '#5AC8FA', 0.55, None)],
             'ghosts': [('P1', 'p1', 0.47, -1240), ('Late', 'field', None, None)]}
        t = hud.track(v)
        self.assertEqual((t['me'], t['split'], t['other']), ('0.4200', ['0.3300'], ['Ann\t5AC8FA\t0.5500']))
        self.assertEqual(t['ghost'], ['P1\tF4F4F5\t0.4700'])                    # (one not on the stage yet: none)
        self.assertIsNone(hud.track({'progress': 0.2, 'others_prog': [], 'ghosts': []}))   # (nobody else: nothing)

    def test_everything_in_one_update(self):
        p = hud.panels(LIVE, GATE, None, None, 'left', 9.0, 'P3 / 18')
        self.assertEqual([n for n, _f in p], ['hud', 'acr', 'gate'])
        self.assertEqual(p[0][1], {'place': 'dock', 'scale': '3.00'})     # (an old place: by the timer; at most 3x)


class File(unittest.TestCase):
    def test_the_text_the_mod_reads(self):
        t = lines([('hud', {'place': 'dock', 'scale': '1.00'}), ('note', {'head': 'SAVE YOUR TIME', 'point': ['a b', 'c']})])
        self.assertEqual(t, ['ACRHUD 2 1 10.0000', '1 hud on 1', '1 hud place dock', '1 hud scale 1.00', '1 note on 1',
                             '1 note head SAVE YOUR TIME', '1 note point a b', '1 note point c', 'end 1'])
        one = hud.encode(2, 1.0, [('acr', {'line': 'two\nlines\tand a tab'})]).splitlines()
        self.assertIn('2 acr line two lines\tand a tab', one)                # (one line a value, whatever it was given)

    def test_written_when_it_changes_a_clock_that_only_runs_on_is_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            f = hud.Feed(os.path.join(d, 'x', hud.FILE))
            at = lambda ms: [('acr', {'chip': 'LIVE', 'time': hud.acr(dict(LIVE, ms=ms), clock=True)['time'],  # noqa: E731
                                      'run': ms})]
            self.assertTrue(f.write(at(1000), now=0.0))
            self.assertFalse(f.write(at(1100), now=0.1))       # (ran on as the clock did: the mod moves it itself)
            self.assertTrue(f.write(at(1100), now=0.3))        # (stood still for 200 ms: a pause, said)
            self.assertTrue(f.write(at(1900), now=0.9))        # (and at least twice a second)
            long_ = [('note', {'head': 'a long line ' * 5})]
            self.assertTrue(f.write(long_, now=1.0))
            self.assertTrue(f.write([('note', {'head': 'short'})], now=1.1))
            f.close()
            with open(os.path.join(d, 'x', hud.FILE), 'rb') as fh:
                data = fh.read().decode('utf-8')
            head, _, rest = data.partition('end %d\n' % f.seq)
            self.assertTrue(head.startswith('ACRHUD 2 %d ' % f.seq) and 'short' in head)
            self.assertEqual(rest.strip(), '')                 # (the longer one before: blanked)

    def test_a_series_logo_copied_where_the_mod_reads_it(self):
        with tempfile.TemporaryDirectory() as d:
            series = os.path.join(d, 'series')
            os.makedirs(series)
            with open(os.path.join(series, 'rally2-logo.png'), 'wb') as fh:
                fh.write(b'png')
            p = hud.logo_file(os.path.join(d, 'set'), series, 'rally2')
            self.assertEqual(p, os.path.join(d, 'set', hud.LOGO_DIR, 'rally2-logo.png'))
            self.assertTrue(os.path.isfile(p))
            self.assertIsNone(hud.logo_file(d, series, 'nope'))
            self.assertIsNone(hud.logo_file(d, series, None))
            b = hud.brand_file(os.path.join(d, 'set'))                # ACR Daily's red D, from the app's files
            self.assertEqual(b, os.path.join(d, 'set', hud.LOGO_DIR, 'acrdaily-d.png'))
            self.assertEqual(os.path.getsize(b), os.path.getsize(hud.BRAND))

    def test_the_mod_seen_running_while_its_camera_file_moves_on(self):
        with tempfile.TemporaryDirectory() as d:
            cam = os.path.join(d, hud.CAMERA_FILE)
            pulse = hud.ModPulse(cam)
            self.assertFalse(pulse.alive(now=0.0))             # (no file: no mod)
            with open(cam, 'w') as fh:
                fh.write('CAM 1 0 0 0')
            self.assertTrue(pulse.alive(now=1.0))
            self.assertTrue(pulse.alive(now=2.5))              # (within ALIVE_S of its last move)
            self.assertFalse(pulse.alive(now=4.0))             # (not moving on: the game or the mod stopped)
            pulse.close()                                      # (Windows: a file kept open can't be written over)
            with open(cam, 'w') as fh:
                fh.write('CAM 2 0 0 0')
            self.assertTrue(pulse.alive(now=5.0))
            pulse.close()


class Cards(unittest.TestCase):
    """The cards that take keys in the game (a comment on a run, the next daily / time trial): what the game draws,
    and the keys pressed there coming back (ingame-actions.txt)."""

    COMMENT = {'id': 'c0ffee', 'kind': 'comment', 'title': 'SS1 FINISHED · P3 TODAY', 'title_c': '#F4F4F5',
               'what': 'SS1 · Peïra Cava · 3:21.456', 'line': 'How did it go? One line.', 'note': 'Shown...', 'text': '',
               'max': 200, 'msg': ('Sending...', '#A1A1AA'), 'left': 12000, 'span': 30000,
               'keys': [('F8', 'DRIVE SS2 ›  restarts the game', True), ('F9', 'COMMENT', False), ('F10', 'CLOSE', False)]}

    def test_what_the_game_draws(self):
        c = hud.card(self.COMMENT)
        self.assertEqual((c['id'], c['kind'], c['text'], c['max'], c['msg'], c['left'], c['span']),
                         ('c0ffee', 'comment', '-', 200, 'Sending...', 12000, 30000))      # ('-': an empty box)
        self.assertEqual(c['key'], ['F8\tDRIVE SS2 › restarts the game\t1', 'F9\tCOMMENT\t0', 'F10\tCLOSE\t0'])
        n = hud.card(dict(self.COMMENT, kind='next', text=None, msg=None, left=None))
        self.assertNotIn('text', n)                              # (no box on the next daily's card)
        self.assertNotIn('left', n)
        p = dict(hud.panels(LIVE, cards=[self.COMMENT, dict(self.COMMENT, id='other')]))
        self.assertEqual(p['card']['id'], 'c0ffee')              # (one at a time: the first)
        self.assertNotIn('card', dict(hud.panels(LIVE)))

    def test_the_keys_pressed_come_back(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, hud.ACTIONS_FILE)
            acts = hud.Actions(path)
            self.assertEqual(acts.poll(), [])                    # (no file yet: nothing; the first one written is new)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('ACRACT 99.1 c0ffee typing \n' + ' ' * 40 + '\n')
            self.assertEqual(acts.poll(), [('c0ffee', 'typing', '')])
            self.assertEqual(acts.poll(), [])                    # (the same one: once)
            acts.close()
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('ACRACT 99.2 c0ffee comment lost the rear · zażółć\n')
            self.assertEqual(acts.poll(), [('c0ffee', 'comment', 'lost the rear · zażółć')])
            acts.close()
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('ACRACT 99.3 c0ffee boom x\n')
            self.assertEqual(acts.poll(), [])                    # (not an action)
            acts.close()
            late = hud.Actions(path)                             # (an app started after it: an old one, not done)
            self.assertEqual(late.poll(), [])
            late.close()

    def test_the_mode_chip(self):
        a = hud.acr(dict(LIVE, mode=('RALLY WEEKEND', '#30D158')))
        self.assertEqual((a['mode'], a['mode_c']), ('RALLY WEEKEND', '30D158'))
        self.assertNotIn('mode', hud.acr(LIVE))


class CardsInTheApp(unittest.TestCase):
    """While the game draws them the cards' windows are put away, and a key pressed in the game does their button."""

    def test_keys_in_the_game_do_the_buttons(self):
        import tkinter as tk
        from acr_daily import commentui, nextcard, settings
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()
        try:
            drove, sent = [], []
            nxt = nextcard.NextCard(root, (0, 0), 'SS1 FINISHED', 'Next: SS2 · X', 'Car · Clear', 'DRIVE SS2 ›  restarts the game',
                                    lambda: drove.append(2))
            s = nxt.snapshot()
            self.assertEqual((s['kind'], [k for k, _w, _m in s['keys']]), ('next', ['F8', 'F10']))
            self.assertTrue(0 < s['left'] <= 30000)
            a = app_mod.App.__new__(app_mod.App)
            a.next_card, a.comment_card, a.tt_next_card = nxt, None, None
            with tempfile.TemporaryDirectory() as d, mock.patch.object(settings, 'DIR', d), \
                    mock.patch.object(app_mod.ghostui, 'open_kept', lambda p, write=False, binary=False: open(p, 'rb')):
                a._ingame_actions(True)                          # (the game draws it: its window put away)
                self.assertEqual(nxt.win.state(), 'withdrawn')
                a._ingame_actions(False)                         # (and back when it stops)
                self.assertEqual(nxt.win.state(), 'normal')
                a._hud_actions.close()
                with open(os.path.join(d, hud.ACTIONS_FILE), 'w') as fh:
                    fh.write('ACRACT 5.1 %s drive\n' % s['id'])
                a._ingame_actions(True)                          # F8 in the game: its DRIVE
                self.assertEqual(drove, [2])
                self.assertFalse(nxt.alive)
                card = commentui.CommentCard(root, (0, 0), 'SS1 · YOUR RUN', 'SS1 · X · 3:21.456', 'Shown...', '',
                                             lambda text: sent.append(text))
                a.comment_card = card
                c = card.snapshot()
                self.assertEqual([k for k, _w, _m in c['keys']], ['F9', 'F10'])      # (no DRIVE: no other daily)
                self.assertEqual((c['text'], c['max']), ('', commentui.MAX))
                a._hud_actions.close()
                with open(os.path.join(d, hud.ACTIONS_FILE), 'w') as fh:
                    fh.write('ACRACT 5.2 %s typing\n' % c['id'])
                a._ingame_actions(True)
                self.assertTrue(card.writing)                    # (typing in the game: the card stays)
                a._hud_actions.close()
                with open(os.path.join(d, hud.ACTIONS_FILE), 'w', encoding='utf-8') as fh:
                    fh.write('ACRACT 5.3 %s comment lost   the rear\n' % c['id'])
                a._ingame_actions(True)
                self.assertEqual(sent, ['lost the rear'])
                a._hud_actions.close()
                with open(os.path.join(d, hud.ACTIONS_FILE), 'w') as fh:
                    fh.write('ACRACT 5.4 deadbeef close\n')      # (another card's key: nothing)
                a._ingame_actions(True)
                self.assertTrue(card.alive)
                a._hud_actions.close()
                card.close()
        finally:
            root.destroy()
            root = None
            import gc
            gc.collect()


class NextTimeTrial(unittest.TestCase):
    def test_after_a_run_on_the_board_the_other_stage_offered_once_a_week(self):
        from acr_daily.ttui import TimeTrialUI

        class Stub(TimeTrialUI):
            tt = None
        a = Stub.__new__(Stub)
        ch = lambda name: {'week': '2026-W47', 'menuName': name, 'car': 'Skoda', 'stageId': name}    # noqa: E731
        judge = lambda: mock.Mock(state='finished')                                                    # noqa: E731
        a.tt = {1: {'ch': ch('A'), 'judge': judge()}, 2: {'ch': ch('B'), 'judge': judge()}, 3: {'ch': ch('C')}}
        a.dailies, a.root = {}, mock.Mock()
        a._card_at = lambda: (0, 0)
        a._tt_entered = lambda slot: True
        a.tt_drive = mock.Mock()
        with mock.patch('acr_daily.ttui.nextcard.NextCard') as card:
            a._tt_offer_next(1, 'NEW BEST · P3 OF 18')
            args = card.call_args.args
            self.assertEqual((args[2], args[5]), ('NEW BEST · P3 OF 18', 'DRIVE TT2 ›  restarts the game'))
            args[6]()
            a.tt_drive.assert_called_once_with(2, confirm=False)
            card.reset_mock()
            a._tt_offer_next(1)                                  # (once a week for that pair)
            card.assert_not_called()
            a._tt_offer_next(2)                                  # (TT3 has no route: back to TT1)
            self.assertIn('TT1', card.call_args.args[3])


class GameMode(unittest.TestCase):
    """The game's mode, as the mod writes it on its camera line ("M <mode> <seq>", main.lua race_mode)."""

    def test_the_groups_of_a_camera_line(self):
        parts = 'CAM 7 1 2 3 4 5 6 80 7 M weekend 7 H L3 L12 7'.split()
        self.assertEqual(hud.camera_groups(parts), {'M': ['weekend'], 'H': ['L3', 'L12']})
        self.assertEqual(hud.camera_groups('CAM 7 1 2 3 4 5 6 80 7'.split()), {})
        self.assertEqual(hud.camera_groups('CAM 8 1 2 3 4 5 6 80 8 M single 8 H L3'.split()), {'M': ['single']})   # (cut)

    def test_read_off_the_running_mod(self):
        with tempfile.TemporaryDirectory() as d:
            cam = os.path.join(d, hud.CAMERA_FILE)
            pulse = hud.ModPulse(cam)
            self.assertIsNone(pulse.mode(now=0.0))                    # (no mod)
            for i, (line, want) in enumerate((('CAM 1 1 2 3 4 5 6 80 1 M weekend 1', 'weekend'),
                                              ('CAM 2 1 2 3 4 5 6 80 2 M timeattack 2', 'timeattack'),
                                              ('CAM 2 1 2 3 4 5 6 80 2 M single 2', 'single'),
                                              ('CAM 3 1 2 3 4 5 6 80 2 M weekend 2', 'single'),   # (torn: kept)
                                              ('CAM 4 1 2 3 4 5 6 80 4 M none 4', None),          # (the menus)
                                              ('CAM 5 1 2 3 4 5 6 80 5', None))):                # (an older mod)
                pulse.close()
                with open(cam, 'w') as fh:
                    fh.write(line.ljust(159) + '\n')
                self.assertEqual(pulse.mode(now=1.0 + i), want, line)
            self.assertIsNone(pulse.mode(now=20.0))                   # (stopped moving on: the mod is gone)
            pulse.close()


class Settings(unittest.TestCase):
    def test_the_game_mod_goes_in_for_the_displays_too(self):
        a = mock.Mock()
        for ghosts, shown, want in (({'on': True}, False, True), ({'on': False}, False, False), ({'on': False}, True, True),
                                    ({'on': True, 'ingame': False}, False, False)):
            a.s = {'ghostCars': ghosts, 'overlay': {'inGame': shown}}
            self.assertEqual(app_mod.App.want_game_mod(a), want, (ghosts, shown))
        self.assertTrue({'hud.lua', 'hudkit.lua'} <= set(modinstall.MOD_FILES))
        self.assertEqual(set(hud.PLACES), {'dock', 'top', 'bottom'})

    def test_on_by_default_in_a_test_build_only(self):
        a = mock.Mock()
        a.s = {'overlay': {}}
        with mock.patch.object(app_mod.liverally, 'ON', True):
            self.assertTrue(app_mod.App.ingame_on(a))
        with mock.patch.object(app_mod.liverally, 'ON', False):
            self.assertFalse(app_mod.App.ingame_on(a))
            a.s = {'overlay': {'inGame': True}}
            self.assertTrue(app_mod.App.ingame_on(a))
        for old, now in (('left', 'dock'), ('top', 'top'), ('bottom', 'bottom'), ('x', 'dock'), (None, 'dock')):
            a.s = {'overlay': {'inGamePlace': old} if old else {}}
            self.assertEqual(app_mod.App.ingame_place(a), now)

    def test_the_windows_over_the_game_stand_down_while_the_game_draws_them(self):
        a = mock.Mock()
        a.s = {'overlay': {'inGame': True}}
        a.ingame_on = lambda: True
        a._mod_pulse = mock.Mock()
        a._pulse = lambda: a._mod_pulse
        a._mod_pulse.alive.return_value = True
        self.assertTrue(app_mod.App.ingame_drawn(a))
        a._mod_pulse.alive.return_value = False                  # (the mod not running: the windows as before)
        self.assertFalse(app_mod.App.ingame_drawn(a))
        a.ingame_on = lambda: False
        a._mod_pulse.alive.return_value = True
        self.assertFalse(app_mod.App.ingame_drawn(a))


class Feed(unittest.TestCase):
    """App._ingame_feed: what the app's windows say -> the file the mod reads, the series' logo where it reads it."""

    def test_the_apps_words_to_the_game(self):
        from acr_daily import settings
        with tempfile.TemporaryDirectory() as d, mock.patch.object(settings, 'DIR', d), \
                mock.patch.object(app_mod.ghostui, 'open_kept', lambda p, write=False, binary=False: open(p, 'w+b')):
            a = app_mod.App.__new__(app_mod.App)
            a.s = {'overlay': {'inGame': True, 'scale': 1.2, 'inGamePlace': 'left'}}
            a.overlay = mock.Mock(snapshot=mock.Mock(return_value=dict(LIVE, panel={'title': 'SPLIT 1', 'pos': 'P2 / 9',
                                                                                     'rows': [], 'pb': None})))
            a._lr_gate = mock.Mock(snapshot=mock.Mock(return_value=dict(GATE, series='rally2')))
            a._overlays_allowed = lambda f: True
            a._widget_on = lambda k: False
            a._mod_pulse = mock.Mock(alive=mock.Mock(return_value=True))
            a._ingame_feed(now=1.0)
            a._hud_feed.close()
            with open(os.path.join(d, hud.FILE), encoding='utf-8') as f:
                text = f.read().splitlines()
            self.assertEqual(text[0], 'ACRHUD 2 1 1.0000')
            for line in ('1 hud place dock', '1 hud scale 1.20', '1 acr chip LIVE', '1 acr pos P2 / 9', '1 gate head WAIT',
                         '1 gate logo ' + os.path.join(d, hud.LOGO_DIR, 'rally2-logo.png'),
                         '1 acr logo ' + os.path.join(d, hud.LOGO_DIR, 'acrdaily-d.png')):
                self.assertIn(line, text)
            self.assertTrue(os.path.isfile(os.path.join(d, hud.LOGO_DIR, 'rally2-logo.png')))
            self.assertTrue(a._ingame_was)                     # (the game draws them: the windows stand down)
            a.s['overlay']['inGame'] = False                   # switched off: an empty update, then nothing
            a._ingame_feed(now=2.0)
            self.assertIsNone(a._hud_feed)
            a._hud_actions.close()
            with open(os.path.join(d, hud.FILE), encoding='utf-8') as f:
                self.assertEqual(f.read().split(), ['ACRHUD', '2', '2', '2.0000', 'end', '2'])


class Snapshot(unittest.TestCase):
    """The timer window as it draws itself -> the same words and colours in the game."""

    def test_the_timer_windows_words_and_colours(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        root.withdraw()
        try:
            app = mock.Mock()
            app.root = root
            app.s = {'overlay': {'x': 10, 'y': 10, 'scale': 1.0, 'visible': True, 'locked': True}}
            app.penalty_s.return_value = 10
            ov = app_mod.Overlay(app)
            ov.render('live', 'TT3 · LONDON', 83450, 0, '−0.84 to P1', app_mod.GOOD)
            s = ov.snapshot()
            self.assertEqual((s['ms'], s['running']), (83450, True))
            ov.render('finished', 'TT3 · LONDON', 251320, 1, '')
            ov.set_alert('Waiting for the official time', ['Go on from the results screen'], 'warn')
            ov.set_progress('wait', 0.0, app_mod.SLOW)
            root.update_idletasks()
            s = ov.snapshot()
            self.assertEqual((s['status'], s['title'], s['time'][0], s['pen']), ('finished', 'TT3 · LONDON', '4:11.320', '+10 s'))
            self.assertFalse(s['running'])
            self.assertEqual(s['alert']['head'], 'Waiting for the official time')
            self.assertEqual((s['alert']['head_fg'], s['alert']['bar']), app_mod.ALERT_KINDS['warn'][1:5:3])
            self.assertEqual(s['progress'][0], 'wait')
            self.assertIsNone(s['panel'])
            p = dict(hud.panels(s))
            self.assertEqual((p['acr']['chip'], p['note']['head'], p['note']['bar']), ('FINISHED', 'Waiting for the official time', 'wait'))
            ov.win.destroy()
        finally:
            root.destroy()
            # (nothing of Tk left for another test's thread to collect: "Tcl_AsyncDelete: async handler deleted by the
            # wrong thread" took the whole run down)
            app = ov = root = None
            import gc
            gc.collect()


if __name__ == '__main__':
    unittest.main()
