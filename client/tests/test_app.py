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
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    root.withdraw()
    return root


class StageNames(unittest.TestCase):
    def test_menu_name_first_short_one_for_the_timer(self):
        self.assertEqual(stage_name(LONG), 'Peïra Cava - La Bollène-Vésubie')
        self.assertEqual(stage_name(LONG, short=True), 'Peïra Cava')

    def test_older_servers_send_no_menu_name(self):
        ch = {'track': 'Alsace Forêt', 'stageName': 'Forêt'}
        self.assertEqual(stage_name(ch), 'Forêt')
        self.assertEqual(stage_name({'track': 'Alsace Forêt'}), 'Alsace Forêt')
        self.assertEqual(stage_name(None), '')

    def test_long_name_fits_its_card(self):
        import tkinter as tk
        from tkinter import font as tkfont
        root = tk_root()
        try:
            a = App.__new__(App)
            a.root = root
            label = tk.Label(root)
            a._fit_name(label, stage_name(LONG).upper())     # the longest menu name: one line
            font = tkfont.Font(font=label.cget('font'))
            self.assertLessEqual(font.measure(label.cget('text')), int(label.cget('wraplength')))
            a._fit_name(label, 'OBERSTEIGEN')
            self.assertEqual(int(tkfont.Font(font=label.cget('font')).actual('size')), 24)
            a._fit_name(label, 'VERY ' * 20)                # longer than any: smallest size, wrapped
            self.assertEqual(int(tkfont.Font(font=label.cget('font')).actual('size')), 16)
            self.assertGreater(int(label.cget('wraplength')), 0)
        finally:
            root.destroy()


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

    def test_a_run_the_game_never_saved_ends_as_a_dnf_after_a_restart(self):
        self.finish()
        b = self.restart()
        for _ in range(3):
            with mock.patch('acr_daily.saveslot.game_running', return_value=False):
                b._check_official()
        r = b.on_result.call_args.args[0]
        self.assertEqual((r['status'], waiting.load()), ('dnf', []))
        self.assertIn('closed', r['reason'])

    def test_closing_the_app_while_a_run_waits_asks_first(self):
        self.finish()
        self.a._save_window, self.a.shm = mock.Mock(), mock.Mock()
        with mock.patch('acr_daily.app.messagebox.askyesno', return_value=False) as ask:
            self.a.quit()
        self.assertIn('It is kept', ask.call_args.args[1])
        self.a.root.destroy.assert_not_called()
        with mock.patch('acr_daily.app.messagebox.askyesno', return_value=True):
            self.a.quit()
        self.a.root.destroy.assert_called_once()

    def test_no_result_from_the_game_is_a_dnf(self):
        self.finish()
        for _ in range(3):
            self.check(running=False)                            # the game closed and saved nothing new
        r = self.a.on_result.call_args.args[0]
        self.assertEqual((r['status'], r['totalMs']), ('dnf', None))
        self.assertIn('closed', r['reason'])
        self.assertEqual(self.a.awaiting, [])

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
    return dict({'enabled': enabled, 'signedIn': True, 'earning': True, 'balance': 120, 'claimable': False,
                 'wager': {'date': date, 'slot': 2, 'stake': 10, 'entered': entered}}, **kw)


class WagerDaily(unittest.TestCase):
    """Credits (a prototype): DRIVE on the wager daily offers the stake last, once, before the first run; DRIVE goes on
    once it is in, without asking its questions again."""

    def setUp(self):
        self.later = []                            # what ui() hands to the Tk thread (run_ui runs it)
        self.threads = []                          # threads started (run_threads runs them)

    def app(self, entered=False, enabled=True, date=DAY):
        a = App.__new__(App)
        a.root, a.api, a.sub_l = mock.Mock(), mock.Mock(), mock.Mock()
        a.root.after.side_effect = lambda ms, fn: self.later.append(fn)
        a.acct_l, a.acct_b, a.steam_b = mock.Mock(), mock.Mock(), mock.Mock()
        a.s = {'steamId': '7', 'token': 't' * 64, 'name': 'me'}
        a._wager_asked, a.recorder, a.cards = set(), None, {}
        a.credits = credits(entered, enabled, date)
        a.dailies = {2: {'ch': {'id': DAY + '/2', 'date': DAY, 'slot': 2, 'wager': {'stake': 10}, 'car': 'C'},
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
        return mock.patch('acr_daily.app.messagebox.askyesnocancel', return_value=answer), \
            mock.patch('acr_daily.app.threading.Thread', side_effect=start)

    def ask(self, a, answer, then=None):
        q, t = self.patches(answer)
        with q as q, t, mock.patch('acr_daily.app.messagebox.showwarning'):
            go = a._wager_first(2, then or mock.Mock())
        return go, q.call_count

    def test_staked_then_drives(self):
        a = self.app()
        then = mock.Mock()
        self.assertEqual(self.ask(a, True, then), (False, 1))    # DRIVE goes on once the stake is in
        a.api.wager.assert_called_once_with(2, DAY)              # (with the daily's date: today's only)
        a.refresh_credits = mock.Mock()
        self.run_ui()
        then.assert_called_once()
        a.refresh_credits.assert_called_once()
        self.assertIsNone(a._drive_wait)
        self.assertEqual(self.ask(a, True), (True, 0))           # asked once a session

    def test_without_a_stake_or_cancelled(self):
        a = self.app()
        self.assertEqual(self.ask(a, None), (False, 1))          # cancel: nothing happens, asked again next time
        self.assertEqual(self.ask(a, False), (True, 1))          # no: drive without a stake
        a.api.wager.assert_not_called()

    def test_not_asked(self):
        for a in (self.app(entered=True), self.app(enabled=False)):
            self.assertEqual(self.ask(a, True), (True, 0))
        a = self.app()
        a.dailies[2]['ch'].pop('wager')                         # the free daily
        self.assertEqual(self.ask(a, True), (True, 0))
        a = self.app()
        a.credits['earning'] = False                            # no finished run yet: nothing to stake
        self.assertEqual(self.ask(a, True), (True, 0))

    def drive(self, a, restart_answer=True):
        """DRIVE on SS2 with the game running: the restart question, then the stake (its request left on its way)."""
        q, t = self.patches(True, sync=False)
        with q as stake_q, t, mock.patch('acr_daily.app.saveslot.game_running', return_value=True), \
                mock.patch('acr_daily.app.messagebox.askyesno', return_value=restart_answer) as restart_q:
            a.drive_click(2)
        return stake_q.call_count, restart_q.call_count

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
        self.assertIn('stake on SS2 stands', a.sub_l.configure.call_args.kwargs['text'])

    def test_yesterdays_stake_is_not_todays(self):
        a = self.app(entered=True, date='2026-10-08')            # after midnight UTC, the credits not fetched again yet
        self.assertEqual(self.ask(a, False), (True, 1))          # today's stake is offered
        where = mock.Mock()
        where.cget.return_value = 'MONTE CARLO  ·  WAGER STAKED'
        a.cards = {2: {'where': where}}
        a._wager_marks()
        where.configure.assert_called_with(text='MONTE CARLO  ·  WAGER 10 CR')
        a.credits['wager']['date'] = DAY
        where.cget.return_value = 'MONTE CARLO'
        a._wager_marks()
        where.configure.assert_called_with(text='MONTE CARLO  ·  WAGER STAKED')

    def test_new_dailies_of_a_new_day_fetch_the_credits_again(self):
        a = self.app()
        a.dailies[2]['ch'].update(id='2026-10-08/2', date='2026-10-08')      # yesterday's, still on screen
        a.date_l, a._show_active, a.refresh_board, a.refresh_credits = mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock()
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
        q, t = self.patches(False)
        with q as q, t:
            self.run_ui()
        self.assertEqual(q.call_count, 1)                        # then the stake offered, here declined
        then.assert_called_once()
        self.assertEqual(a.credits['balance'], 120)

    def test_credits_not_reachable_at_drive_asks_to_drive_without_a_stake(self):
        for answer, calls in ((False, 0), (True, 1)):
            a = self.app()
            a.credits = None
            a.api.credits.side_effect = api_mod.ApiError('server not reachable')
            then = mock.Mock()
            self.ask(a, True, then)
            with mock.patch('acr_daily.app.messagebox.askyesno', return_value=answer) as q:
                self.run_ui()
            self.assertIn('could not be loaded', q.call_args.args[1])
            self.assertEqual(then.call_count, calls)
            self.assertIsNone(a._drive_wait)
            a.api.wager.assert_not_called()

    def test_a_failed_claim_keeps_the_balance(self):
        a = self.app()
        a.api.credits.return_value = credits(claimable=True)
        a.api.claim_credits.side_effect = api_mod.ApiError('server not reachable')
        self.assertEqual(a._fetch_credits(), (credits(claimable=True), ''))
        a.api.claim_credits.side_effect = None
        a.api.claim_credits.return_value = {'claimed': True, 'amount': 12, 'balance': 132, 'streak': 2}
        c, msg = a._fetch_credits()
        self.assertEqual((c['balance'], c['claimable']), (132, False))
        self.assertIn('+12 credits (2 days in a row)', msg)

    def stake_fails(self, a, err):
        a.api.wager.side_effect = err
        a.refresh_credits = mock.Mock()
        with mock.patch('acr_daily.app.messagebox.showwarning') as warn:
            self.ask(a, True)
            self.run_ui()
        a.refresh_credits.assert_called_once()
        self.assertIsNone(a._drive_wait)
        return warn.call_args.args[1]

    def test_no_answer_to_the_stake_may_have_taken_it_and_offers_it_again(self):
        a = self.app()
        self.assertIn('may have gone through', self.stake_fails(a, api_mod.ApiError('server not reachable (timed out)')))
        self.assertEqual(self.ask(a, False), (True, 1))          # offered again
        a.credits['wager']['entered'] = True                     # ...unless the credits show it went in
        a._wager_asked.clear()
        self.assertEqual(self.ask(a, True), (True, 0))

    def test_a_stake_refused_is_not_offered_again(self):
        a = self.app()
        self.assertIn('Not staked', self.stake_fails(a, api_mod.ApiError('the stake is 10 credits: you have 4', 402)))
        self.assertEqual(self.ask(a, True), (True, 0))

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
        self.assertEqual(self.ask(a, True), (True, 0))            # no stake after it
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
        where = mock.Mock()
        where.cget.return_value = 'MONTE CARLO  ·  WAGER STAKED'
        a.cards = {2: {'where': where}}
        a.login_click()
        self.assertIsNone(a.credits)
        where.configure.assert_called_with(text='MONTE CARLO')
        self.assertIn('Not signed in', a.acct_l.configure.call_args.kwargs['text'])
        self.assertEqual(self.ask(a, True), (True, 0))            # no stake offered
        a._set_credits(credits())                                 # an answer asked for before the sign-out
        self.assertIsNone(a.credits)


class CreditsApi(unittest.TestCase):
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


class LeagueFee(unittest.TestCase):
    """Credits (a prototype): an event's entry fee is asked for once DRIVE's own checks have passed."""

    def app(self, enabled=True):
        a = App.__new__(App)
        self.later = []
        a.root, a.api, a.sub_l = mock.Mock(), mock.Mock(), mock.Mock()
        a.root.after.side_effect = lambda ms, fn: self.later.append(fn)
        a.s = {'steamId': '7', 'token': 't' * 64}
        a.credits = credits(enabled=enabled)
        a.dailies, a.awaiting, a.recorder = {}, [], None
        self.ev = {'id': 3, 'name': 'Rally Kraków', 'rally': 'Poland', 'fee': 10, 'pot': 20, 'entry': None, 'stages': [{}]}
        a.league_events = [self.ev]
        a._league_car = mock.Mock(return_value={'name': 'C', 'id': 'c'})
        a._fill_routes = mock.Mock(return_value=True)
        for name in ('_render_leagues', 'refresh_credits', 'refresh_leagues', '_league_setup_and_launch', '_restart_into_league'):
            setattr(a, name, mock.Mock())
        a.api.league_enter.return_value = {'paid': True, 'fee': 10, 'pot': 30, 'balance': 110}
        return a

    def drive(self, a, running=False, answer=True):
        import tempfile
        with mock.patch('acr_daily.leagueui.saveslot.game_running', return_value=running), \
                mock.patch('acr_daily.leagueui.saveslot.SAVE', os.path.join(tempfile.mkdtemp(), 'none.sav')), \
                mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=answer) as q, \
                mock.patch('acr_daily.leagueui.messagebox.showinfo') as info, \
                mock.patch('acr_daily.leagueui.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)):
            a.league_drive(3)
            while self.later:
                self.later.pop(0)()
        return q, info

    def test_paid_then_drives(self):
        a = self.app()
        q, _ = self.drive(a)
        self.assertIn('entry fee of 10 credits', q.call_args.args[1])
        a.api.league_enter.assert_called_once_with(3)
        a._league_setup_and_launch.assert_called_once()
        a._render_leagues.assert_called()                          # the card says paid
        a.refresh_credits.assert_called_once()
        self.assertEqual((self.ev['paid'], self.ev['pot']), (True, 30))

    def test_not_charged_when_drive_stops_first(self):
        a = self.app()
        a.dailies = {1: {'judge': mock.Mock(state='running')}}     # on a stage
        b = self.app()
        b.awaiting = [{'slot': 1, 'result': {}}]                    # a run waiting for the game's official time
        for x in (a, b):
            q, info = self.drive(x)
            q.assert_not_called()
            info.assert_called_once()
            x.api.league_enter.assert_not_called()
        c = self.app()
        q, _ = self.drive(c, running=True, answer=False)           # "close the game?" No
        self.assertEqual(q.call_count, 1)
        self.assertIn('is running', q.call_args.args[1])
        c.api.league_enter.assert_not_called()
        c._restart_into_league.assert_not_called()

    def test_no_fee_while_credits_are_off(self):
        a = self.app(enabled=False)
        q, _ = self.drive(a)
        q.assert_not_called()
        a.api.league_enter.assert_not_called()
        a._league_setup_and_launch.assert_called_once()


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
