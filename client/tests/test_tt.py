"""The TIME TRIAL tab (ttui.py): its words, the requests, the entry asked for at DRIVE, which judges see the frames, the
tab switching, and a hotlap session: two runs of a stage judged, each sent with the game's official time to the time
trial's board, the second a new best. On a Tk window that is never shown."""
import os
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import api as api_mod, app as app_mod, inboxui, settings, ttui, waiting  # noqa: E402
from acr_daily.api import ApiError  # noqa: E402
from acr_daily.app import App  # noqa: E402
from acr_daily.telemetry import Frame  # noqa: E402
from test_app import tk_root  # noqa: E402

ME, ANN = '76561198000000001', '76561198000000002'
WEEK = '2026-11-09'
ROUTE = [[i * 5.0, 0.0] for i in range(401)]          # a straight 2 km road


def stage(slot=1, **kw):
    ch = {'id': 'tt:%s/%d' % (WEEK, slot), 'kind': 'tt', 'week': WEEK, 'slot': slot, 'track': 'Test Stage %d' % slot,
          'car': 'Test Car', 'stageId': 'TestS1Forward', 'carId': 'TestCar', 'route': ROUTE, 'penaltyMs': 0, 'mode': 'weekend',
          'rally': 'Wales', 'surface': 'Gravel', 'lengthM': 2000, 'menuName': 'Test Stage', 'stageName': 'Test',
          'weatherLabel': 'Clear', 'timeLabel': 'Midday (12:00)', 'weatherGame': 'WT_CLEAR', 'startSeconds': 43200,
          'fee': 20, 'entrants': 3, 'pot': 60, 'me': {'entered': False, 'bestMs': None, 'runs': 0}}
    ch.update(kw)
    return ch


def stage2(**kw):
    """TT2: another stage (its own road) and car."""
    return stage(2, car='Other Car', carId='OtherCar', route=[[x, 5000.0] for x, _ in ROUTE], **kw)


def week(**kw):
    w = {'on': True, 'week': WEEK, 'isoWeek': {'year': 2026, 'no': 46}, 'startsAt': 1794182400000,
         'endsAt': 1794182400000 + 7 * 86400000, 'fee': 20, 'credits': True, 'stages': [stage(1), stage2()]}
    w.update(kw)
    return w


def board(*entries):
    return {'week': WEEK, 'slot': 1, 'entries': [dict(e, rank=i + 1) for i, e in enumerate(entries)],
            'stats': {'drivers': len(entries)}, 'credits': True}


class Words(unittest.TestCase):
    def test_a_stage_id(self):
        self.assertEqual(ttui.parse_id('tt:2026-11-09/2'), 2)
        self.assertIsNone(ttui.parse_id('2026-11-09/2'))
        self.assertIsNone(ttui.parse_id('tt:2026-11-09/3'))
        self.assertIsNone(ttui.parse_id(None))

    def test_a_cards_line(self):
        self.assertEqual(ttui.stage_status(stage(), None, ME), ('ENTRY 20  ·  3 IN  ·  POT 60', True, 'acc'))
        self.assertEqual(ttui.stage_status(stage(me={'entered': True}), None, ME), ('ENTERED  ·  NO TIME YET  ·  POT 60', True, 'good'))
        self.assertEqual(ttui.stage_status(stage(fee=0), None, ME), ('FREE ENTRY  ·  NO TIME YET', False, 'soft'))
        b = board({'steamId': ANN, 'totalMs': 190000, 'runs': 1, 'prize': 34}, {'steamId': ME, 'totalMs': 196000, 'runs': 3, 'prize': 26})
        self.assertEqual(ttui.stage_status(stage(), b, ME), ('BEST 3:16.000  ·  P2 OF 2  ·  3 RUNS  ·  PRIZE 26', True, 'good'))
        self.assertEqual(ttui.stage_status(stage(me={'entered': True, 'bestMs': 201000, 'runs': 1}), None, ME),
                         ('BEST 3:21.000  ·  1 RUN', False, 'good'))     # (the board not in yet)

    def test_the_week_and_what_the_server_said(self):
        w = week()
        self.assertEqual(ttui.week_text(w, w['endsAt'] - (3 * 86400000 + 4 * 3600000)), 'WEEK 46  ·  CLOSES IN 3 D 4 H')
        self.assertEqual(ttui.week_text(w, w['endsAt'] + 1), 'WEEK 46  ·  CLOSED')
        self.assertEqual(ttui.week_text({'on': False}, 0), '')
        self.assertEqual(ttui.result_text(1, {'best': True, 'improvedMs': 4000, 'totalMs': 196000, 'rank': 2, 'drivers': 5, 'prize': 33}),
                         'TT1: new best 3:16.000 (−4.000). P2 of 5. Prize now: 33 credits.')
        self.assertEqual(ttui.result_text(2, {'best': True, 'totalMs': 200000, 'rank': 1, 'drivers': 1}), 'TT2: 3:20.000, your first time. P1 of 1.')
        self.assertEqual(ttui.result_text(1, {'best': False, 'totalMs': 205000, 'bestMs': 196000, 'rank': 2, 'drivers': 5}),
                         'TT1: 3:25.000. Your best stays 3:16.000. P2 of 5.')

    def test_a_notice_of_results_links_to_its_week(self):
        self.assertEqual(inboxui.ref_page('tt:2026-11-09'), ('Time trial  ›', '/tt?week=2026-11-09'))
        self.assertEqual(inboxui.TAB_OF['tt'], ('tt', 'TIME TRIAL'))


class Requests(unittest.TestCase):
    def test_the_requests(self):
        a = api_mod.Api({'token': 'x' * 64})
        with mock.patch.object(a, '_req', return_value={}) as req:
            a.time_trial()
            self.assertEqual(req.call_args, mock.call('GET', '/api/tt', auth=True))
            a.time_trial(lite=True)
            self.assertEqual(req.call_args, mock.call('GET', '/api/tt?lite=1', auth=True))
            a.tt_board(WEEK, 2)
            self.assertEqual(req.call_args, mock.call('GET', '/api/tt/board?week=2026-11-09&slot=2'))
            a.tt_trace(17)
            self.assertEqual(req.call_args, mock.call('GET', '/api/tt/runs/17/trace'))
            a.tt_enter(1, WEEK)
            self.assertEqual(req.call_args, mock.call('POST', '/api/tt/enter', {'slot': 1, 'week': WEEK}, auth=True))

    def test_a_time_trial_run_goes_to_its_own_board_queued_or_not(self):
        self.assertEqual(api_mod.run_path({'challengeId': 'tt:2026-11-09/1'}), '/api/tt/runs')
        self.assertEqual(api_mod.run_path({'challengeId': '2026-11-09/1'}), '/api/runs')
        home = tempfile.mkdtemp()
        with mock.patch.object(settings, 'DIR', home), mock.patch.object(settings, 'PENDING', os.path.join(home, 'p.json')):
            a = api_mod.Api({'token': 'x' * 64})
            with mock.patch.object(a, '_req', side_effect=ApiError('server not reachable')):
                with self.assertRaises(ApiError):
                    a.submit({'challengeId': 'tt:2026-11-09/1', 'status': 'finished'})
            self.assertEqual(len(a._pending()), 1)               # (queued: sent later)
            with mock.patch.object(a, '_req', return_value={'ok': True}) as req:
                self.assertEqual(a.flush(), 0)
            self.assertEqual(req.call_args.args[:2], ('POST', '/api/tt/runs'))

    def test_waiting_runs_of_the_time_trial_are_kept(self):
        self.assertIn('tt', waiting.KINDS)


class Harness(unittest.TestCase):
    """A bare App with its tabs and views (the dailies, the time trial, the leagues); requests answered at once, what goes
    to the Tk thread done at once."""

    def setUp(self):
        self.root = tk_root()
        self.addCleanup(self.root.destroy)
        sync = lambda target, daemon: mock.Mock(start=target)
        for p in (mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)),
                  mock.patch('acr_daily.ttui.threading.Thread', side_effect=sync),
                  mock.patch('acr_daily.tabsui.threading.Thread', side_effect=sync),
                  mock.patch('acr_daily.inboxui.threading.Thread', side_effect=sync)):
            p.start()
            self.addCleanup(p.stop)
        a = App.__new__(App)
        a.root, a.api, a.sub_l = self.root, mock.Mock(), mock.Mock()
        a.api.configured = True
        a.api.time_trial.return_value = week()
        a.api.tt_board.return_value = board({'steamId': ANN, 'name': 'Ann', 'runId': 5, 'totalMs': 190000, 'clockMs': 190000, 'runs': 2})
        a.api.tt_trace.return_value = {'trace': []}
        a.api.inbox.return_value = {'unread': 0, 'notices': [], 'threads': []}
        a.api.inbox_unread.return_value = 0
        a.s = {'token': 't' * 64, 'steamId': ME, 'name': 'Me'}
        a.credits = {'enabled': True, 'signedIn': True, 'balance': 100}
        a.dailies, a.awaiting, a.coin_img, a.recorder, a._league_restored = {}, [], None, None, []
        a._league_init()
        a._tt_init()
        a.refresh_leagues, a.refresh_league_board, a.refresh_credits, a.refresh_tab_extras = (mock.Mock() for _ in range(4))
        a._build_tabs(self.root)
        a.daily_box, a.league_box, a.league_strip = tk.Frame(self.root), tk.Frame(self.root), tk.Frame(self.root)
        a.league_rows = tk.Frame(a.league_box)
        a.league_rows.pack(fill='x')
        a.daily_box.pack(fill='x')
        a._build_tt_box()
        a._status_frame = tk.Frame(self.root)
        a._status_frame.pack(fill='x')
        a.board_l = tk.Label(self.root, text='TIMING')
        a.board_l.pack(anchor='w')
        a.tree = mock.Mock()
        a.tree.get_children.return_value = ()
        a._build_inbox_box()
        a._fit_name = lambda label, text: label.configure(text=text)
        a.active = 1
        self.a = a


class Tab(Harness):
    def shown(self):
        return [n for n, w in (('daily', self.a.daily_box), ('tt', self.a.tt_box), ('league', self.a.league_box)) if w.winfo_manager()]

    def test_the_tab_in_the_place_of_the_dailies_and_back(self):
        a = self.a
        a.show_tab('tt')
        self.assertEqual(self.shown(), ['tt'])
        self.assertEqual(a._tab_parts['tt'][1].cget('bg'), ttui.TT_COLOUR)
        self.assertEqual(sorted(a.tt), [1, 2])
        self.assertTrue(all(t['judge'] for t in a.tt.values()), 'each stage judged with its route')
        a.api.tt_board.assert_called()                           # (both boards: the cards say my place)
        self.assertEqual(a.board_l.cget('text'), ' '.join('BEST TIMES  TT1'))
        rows = [c.kwargs['values'] for c in a.tree.insert.call_args_list]
        self.assertEqual(rows[-1][1:3], ('Ann', '3:10.000'))
        a.show_tab('league')
        self.assertEqual(self.shown(), ['league'])
        self.assertFalse(a.tt_view)
        a.show_tab('tt')
        self.assertEqual(self.shown(), ['tt'])
        self.assertFalse(a.league_view)
        a.show_tab('daily')
        self.assertEqual(self.shown(), ['daily'])

    def test_the_inbox_over_the_tab_gives_it_back(self):
        a = self.a
        a.show_tab('tt')
        a.toggle_inbox_view(True)
        self.assertEqual(self.shown(), [])
        a.toggle_inbox_view(False)
        self.assertEqual(self.shown(), ['tt'])

    def test_a_new_week_brings_its_routes(self):
        a = self.a
        a.show_tab('tt')
        lite = week(week='2026-11-16', stages=[dict(stage(1, id='tt:2026-11-16/1'), route=None)])
        lite['stages'][0].pop('route')
        a.api.time_trial.reset_mock()
        a.api.time_trial.return_value = week()                   # (what the full request answers)
        a._set_tt(lite, '', True)
        a.api.time_trial.assert_called_once_with(lite=False)     # a new stage without its route: asked again in full

    def test_a_stage_with_no_route_at_all_is_not_asked_for_again_and_again(self):
        a = self.a
        bare = stage(1, id='tt:2026-11-16/1')
        bare.pop('route')
        a.api.time_trial.reset_mock()
        a._set_tt(week(week='2026-11-16', stages=[bare]), '', False)   # (the full answer: the server has no route for it)
        a.api.time_trial.assert_not_called()
        self.assertIsNone(a.tt[1]['judge'])                      # shown, not judged ("no route yet")


class Entry(Harness):
    def drive(self, answer=True):
        a = self.a
        a._set_tt(week(), '')
        a._tt_setup_and_launch = mock.Mock()
        a._league_before_daily = mock.Mock(return_value=False)
        with mock.patch('acr_daily.ttui.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.ttui.messagebox.askyesno', return_value=answer) as ask, \
                mock.patch('acr_daily.ttui.messagebox.showinfo') as info:
            a.tt_drive(1)
        return ask, info

    def test_drive_asks_for_the_entry_then_goes_on(self):
        a = self.a
        a.api.tt_enter.return_value = {'entered': True, 'balance': 80}
        ask, _ = self.drive()
        self.assertIn('Enter TT1 (Test Stage) for 20 credits? You have 100.', ask.call_args.args[1])
        a.api.tt_enter.assert_called_once_with(1, WEEK)
        a._tt_setup_and_launch.assert_called_once_with(1)
        self.assertTrue(a._tt_entered(1))
        self.assertIsNone(a._drive_wait)

    def test_declined_or_short_of_credits_nothing_is_taken(self):
        a = self.a
        self.drive(answer=False)
        a.api.tt_enter.assert_not_called()
        a._tt_setup_and_launch.assert_not_called()
        a.credits['balance'] = 10
        ask, info = self.drive()
        ask.assert_not_called()
        self.assertIn('entry fee is 20 credits and you have 10', info.call_args.args[1])
        a.api.tt_enter.assert_not_called()

    def test_entered_already_or_free_no_question(self):
        a = self.a
        a.api.time_trial.return_value = week(stages=[stage(1, me={'entered': True}), stage2(fee=0)])
        a._set_tt(a.api.time_trial.return_value, '')
        a._tt_setup_and_launch, a._league_before_daily = mock.Mock(), mock.Mock(return_value=False)
        with mock.patch('acr_daily.ttui.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.ttui.messagebox.askyesno') as ask:
            a.tt_drive(1)
            a.tt_drive(2)
        ask.assert_not_called()
        self.assertEqual(a._tt_setup_and_launch.call_args_list, [mock.call(1), mock.call(2)])

    def test_the_set_up_judges_the_frames_for_the_time_trial(self):
        a = self.a
        a._set_tt(week(), '')
        a._league_park_for_daily = mock.Mock(return_value=True)
        a.s['autoDrive'] = False
        with mock.patch('acr_daily.ttui.rallyweekend.write_daily') as write, mock.patch('acr_daily.ttui.saveslot.launch_game'):
            a._tt_setup_and_launch(2)
        self.assertEqual(write.call_args.args[0]['id'], 'tt:%s/2' % WEEK)
        self.assertEqual((a.drive_target, a.tt_active, a.tt_sel), ('tt', 2, 2))
        self.assertIn('START RALLY again for another go', a.sub_l.configure.call_args.kwargs['text'])


class Judges(Harness):
    def test_one_run_never_counts_for_a_daily_and_the_time_trial(self):
        a = self.a
        a._set_tt(week(), '')
        a.dailies = {1: {'ch': {'track': 'Some Daily', 'car': 'Test Car'}}}
        for target, both in (('daily', (True, True)), ('tt', (True, True)), ('league', (False, False))):
            a.drive_target = target
            self.assertEqual((a._dailies_judged(), a._tt_judged()), both, target)
        a.dailies = {1: {'ch': {'track': 'Test Stage 1', 'car': 'Test Car'}}}   # today's SS1 is TT1's stage and car
        self.assertTrue(a._tt_clash())
        a.drive_target = 'daily'
        self.assertEqual((a._dailies_judged(), a._tt_judged()), (True, False))
        a.drive_target = 'tt'
        self.assertEqual((a._dailies_judged(), a._tt_judged()), (False, True))


class Hotlap(Harness):
    """Two runs of TT1 in a row: each judged, waiting for the game's official time, then sent; the second a new best."""

    def setUp(self):
        super().setUp()
        home = tempfile.mkdtemp()
        save = os.path.join(home, 'save.sav')
        with open(save, 'wb') as f:
            f.write(b'not a real save')
        for p in (mock.patch.object(settings, 'DIR', home), mock.patch.object(settings, 'RESULTS', os.path.join(home, 'r.jsonl')),
                  mock.patch.object(waiting, '_file', lambda: os.path.join(home, 'awaiting.json')),
                  mock.patch.object(app_mod.saveslot, 'SAVE', save),
                  mock.patch.object(app_mod.saveslot, 'game_running', return_value=True)):
            p.start()
            self.addCleanup(p.stop)
        a = self.a
        a.api.time_trial.return_value = week(stages=[stage(1, me={'entered': True}), stage2()])
        a._set_tt(a.api.time_trial.return_value, '')
        a.overlay, a.country, a.panel_until, a.panel_slot, a.drive_target = mock.Mock(), None, 0, None, 'tt'
        self.t = [0.0]
        a.tt[1]['judge'].now = lambda: self.t[0]

    def lap(self, t0, seconds):
        """Frames: on the start line, the clock running for `seconds` over 2 km, then stopped as the car rolls on."""
        frames, t, pkt = [], t0, int(t0 * 100)
        for _ in range(10):
            frames.append(Frame(t, pkt, 0, 0.0, 0.0, 0.0, 'Test Car', 'Test Stage 1')); t += .05; pkt += 1
        steps = int(seconds / .05)
        for k in range(1, steps + 1):
            frames.append(Frame(t, pkt, k * 50, 2000.0 * k / steps, 0.0, 2000 / seconds * 3.6, 'Test Car', 'Test Stage 1')); t += .05; pkt += 1
        for k in range(30):
            frames.append(Frame(t, pkt, steps * 50, 2000.0 + k * .25, 0.0, 18.0, 'Test Car', 'Test Stage 1')); t += .05; pkt += 1
        return frames, t

    def drive(self, t0, seconds, answer):
        a = self.a
        frames, t = self.lap(t0, seconds)
        for f in frames:
            self.t[0] = f.t
            a._tt_tick(f, False)
        self.assertEqual(a.tt[1]['judge'].state, 'finished')
        self.assertEqual(len(a.awaiting), 1)
        self.assertEqual(a.awaiting[0]['kind'], 'tt')
        self.assertTrue(a._waiting_text(), 'DRIVE waits for the official time')
        self.assertEqual(a._tt_focus(frames[-1]), 1)
        a.api.submit.return_value = answer
        clock = a.tt[1]['judge'].result['clockMs']
        with mock.patch.object(app_mod.rallyweekend, 'official',
                               return_value={'time': clock / 1000, 'penalty': 1.0, 'splits': [10.0, 20.0, 30.0]}):
            a._check_official()
        self.assertEqual(a.awaiting, [])
        return clock, t

    def test_two_runs_each_sent_the_best_on_the_board(self):
        a = self.a
        clock1, t = self.drive(100.0, 80.0, {'ok': True, 'best': True, 'totalMs': 81000, 'rank': 2, 'drivers': 2})
        sent = a.api.submit.call_args.args[0]
        self.assertEqual(sent['challengeId'], 'tt:%s/1' % WEEK)
        self.assertEqual(sent['official'], {'timeMs': clock1, 'penaltyMs': 1000, 'splitsMs': [10000, 20000, 30000]})
        self.assertEqual(sent['totalMs'], clock1 + 1000)
        self.assertEqual(a.tt[1]['said'], 'NEW BEST · P2 OF 2')
        self.assertIn('your first time', a.sub_l.configure.call_args.kwargs['text'])
        a.overlay.show_standing.assert_called()                     # the finish against the time trial's board
        self.assertEqual(a.panel_slot, ('tt', 1))
        # START RALLY again: back on the line, another run
        clock2, _ = self.drive(t + 5, 78.0, {'ok': True, 'best': True, 'improvedMs': 2000, 'totalMs': 79000, 'rank': 1, 'drivers': 2})
        self.assertEqual(a.api.submit.call_count, 2)
        self.assertLess(clock2, clock1)
        self.assertIn('new best', a.sub_l.configure.call_args.kwargs['text'])

    def test_a_restart_is_not_sent_and_the_next_run_counts(self):
        a = self.a
        frames, t = self.lap(100.0, 80.0)
        half = len(frames) // 2
        for f in frames[:half] + [Frame(frames[half].t, frames[half].packet, 0, 0.0, 0.0, 0.0, 'Test Car', 'Test Stage 1')]:
            self.t[0] = f.t
            a._tt_tick(f, False)
        self.assertEqual(a.tt[1]['judge'].state, 'dnf')
        self.assertEqual(a.awaiting, [])
        a.api.submit.assert_not_called()
        self.assertIn('Not sent: only finished runs count', a.sub_l.configure.call_args.kwargs['text'])
        self.drive(t + 5, 80.0, {'ok': True, 'best': True, 'totalMs': 81000, 'rank': 1, 'drivers': 1})
        a.api.submit.assert_called_once()

    def test_a_run_without_the_entry_is_not_sent(self):
        a = self.a
        a.tt[1]['ch']['me'] = {'entered': False}
        frames, _ = self.lap(100.0, 80.0)
        for f in frames:
            self.t[0] = f.t
            a._tt_tick(f, False)
        self.assertEqual(a.awaiting, [])
        self.assertIn('TT1: not counted', a.sub_l.configure.call_args.kwargs['text'])
        state = a._tt_overlay_state(frames[-1])
        self.assertIn('Not counted', state[2][4])

    def test_following_a_league_event_the_time_trial_sees_nothing(self):
        a = self.a
        a.drive_target = 'league'
        frames, _ = self.lap(100.0, 80.0)
        for f in frames[:40]:
            self.t[0] = f.t
            a._tt_tick(f, False)
        self.assertEqual(a.tt[1]['judge'].state, 'waiting')
        self.assertIsNone(a._tt_focus(frames[39]))


if __name__ == '__main__':
    unittest.main()
