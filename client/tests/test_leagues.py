"""League events in the app: what DRIVE does with the game's save (set up, resume, set aside, put back), results still
waiting to be sent, and the app following a driver through an event's stages (on made-up saves laid out as the
game's, test_rallyweekend.fake_save)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import leagues, rallyweekend as rw, saveslot  # noqa: E402
from acr_daily.app import App  # noqa: E402
from test_rallyweekend import THREE_DAYS, entry, fake_save, run  # noqa: E402

CAR = {'name': 'Hyundai i20 N Rally2', 'id': 'HyundaiI20NRally2', 'cls': 'Rally2/R5', 'aliases': ['Hyundai i20 N Rally2']}
ROUTE = [[0.0, float(z)] for z in range(0, 2000, 20)]


def event(eid, stage_ids, entry=None, days=None):
    """An event as the server sends it (/api/me/events), on Wales stages."""
    days = days or [0] * len(stage_ids)
    stages = [{'no': k + 1, 'day': d + 1, 'service': k == 0 or d != days[k - 1], 'track': 'Wales %d' % k, 'stageId': sid,
               'name': 'Stage %d' % (k + 1), 'lengthM': 2000, 'weather': 'Clear', 'weatherLabel': 'Clear',
               'weatherGame': 'WT_CLEAR', 'time': '%02d:00' % (8 + k), 'startSeconds': (8 + k) * 3600}
              for k, (sid, d) in enumerate(zip(stage_ids, days))]
    return {'id': eid, 'name': 'Round %d' % eid, 'league': 'Test', 'rally': 'Wales', 'car': CAR['name'], 'carClass': None,
            'cars': [CAR], 'rules': {'damageIntensity': 'severe'}, 'stages': stages, 'days': days[-1] + 1,
            'status': 'open', 'opens': 0, 'closes': 9e12, 'entry': entry}


A_IDS = [s[1] for s in THREE_DAYS]
A_DAYS = [s[0] for s in THREE_DAYS]
B_IDS = ['WelesS4HafrenSouthFullReverse', 'WelesS3HafrenNorthFullForward']


def running(done):
    return {'status': 'running', 'done': done, 'totalMs': 1000 * done, 'car': CAR['name'], 'reason': ''}


class TempDirs(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        for name, value in (('PARK_DIR', os.path.join(d, 'league-rallies')), ('PENDING', os.path.join(d, 'pending.json'))):
            p = mock.patch.object(leagues, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch('acr_daily.settings.DIR', d)
        p.start()
        self.addCleanup(p.stop)


class Plan(TempDirs):
    def test_the_itinerary_as_the_game_takes_it(self):
        ev = event(1, A_IDS, days=A_DAYS)
        cal = leagues.calendar(ev)
        self.assertEqual([(c['day'], c['service']) for c in cal], [(0, True), (0, False), (0, False), (1, True), (1, False),
                                                                    (2, True)])
        self.assertEqual(rw.check_itinerary(cal), 'WalesWeekendLong')
        self.assertTrue(leagues.same_calendar(rw.read_weekend(fake_save(THREE_DAYS))['stages'], ev))
        self.assertFalse(leagues.same_calendar(rw.read_weekend(fake_save(THREE_DAYS))['stages'], event(2, B_IDS)))

    def test_not_started_sets_the_rally_up(self):
        ev = event(2, B_IDS)
        b = fake_save(THREE_DAYS)
        self.assertEqual(leagues.plan(ev, b), ('setup', None))
        new = leagues.apply_plan(ev, CAR, 'setup', None, b)
        w = rw.read_weekend(new)
        self.assertTrue(leagues.same_calendar(w['stages'], ev))
        self.assertEqual((w['intensity'], saveslot.read_setup(new)['car'][1]), (2, b'HyundaiI20NRally2'))
        # its rally begun in the game as set up, no stage driven yet: just start the game
        ev0 = dict(ev, rules={})                                       # (what fake_save() holds)
        as_set = [(s['day'] - 1, s['stageId'], s['startSeconds'], 'ServiceParkDefault' if s['service'] else 'NoZone')
                  for s in ev0['stages']]
        self.assertEqual(leagues.plan(ev0, fake_save(as_set, done=0)), ('resume', 0))
        # ...but with stages driven without the app (they can't count), or set up otherwise in the game's menus: thrown
        # away and set up again
        driven = fake_save([(0, s, 28800, 'ServiceParkDefault') for s in B_IDS], done=1)
        self.assertEqual(leagues.plan(ev, driven), ('reset', None))
        fresh = leagues.apply_plan(ev, CAR, 'reset', None, driven)
        self.assertIsNone(rw.progress(fresh))
        self.assertEqual(leagues.changed_in_game(rw.read_weekend(fresh), ev), [])

    def test_a_driver_who_never_started_a_rally_weekend(self):
        ev = event(2, B_IDS)
        b = fake_save(THREE_DAYS, rally=False)          # only Single Rally Stages driven: no Rally Weekend settings yet
        self.assertEqual(leagues.plan(ev, b), ('setup', None))
        new = leagues.apply_plan(ev, CAR, 'setup', None, b)
        self.assertTrue(leagues.same_calendar(rw.read_weekend(new)['stages'], ev))
        self.assertEqual(saveslot.read_setup(new)['car'][1], CAR['id'].encode())

    def test_a_started_event_resumes_where_the_entry_is(self):
        ev = event(1, A_IDS, running(2), A_DAYS)
        self.assertEqual(leagues.plan(ev, fake_save(THREE_DAYS, done=2)), ('resume', 2))
        self.assertIsNone(leagues.apply_plan(ev, CAR, 'resume', 2, fake_save(THREE_DAYS, done=2)))
        with self.assertRaisesRegex(leagues.Gone, 'without ACR Daily'):
            leagues.plan(ev, fake_save(THREE_DAYS, done=3))
        with self.assertRaisesRegex(leagues.Gone, 'no longer in the game'):
            leagues.plan(ev, fake_save(THREE_DAYS))                    # retired from it in the game

    def test_finished_or_out_of_it(self):
        for status in ('finished', 'dnf'):
            with self.assertRaises(saveslot.SaveError):
                leagues.plan(event(1, A_IDS, dict(running(6), status=status), A_DAYS), fake_save(THREE_DAYS))
        with self.assertRaisesRegex(saveslot.SaveError, 'disqualified you from this event: wrong car'):
            leagues.plan(event(1, A_IDS, dict(running(2), status='dsq', reason='wrong car'), A_DAYS), fake_save(THREE_DAYS, done=2))

    def test_another_rally_in_the_game(self):
        a = event(1, A_IDS, running(2), A_DAYS)
        b_ev = event(2, B_IDS)
        busy = fake_save(THREE_DAYS, done=2)
        # the rally of another started event: set aside, then this one set up
        self.assertEqual(leagues.plan(b_ev, busy, [a, b_ev]), ('park-other', a))
        parked = leagues.apply_plan(b_ev, CAR, 'park-other', a, busy)
        self.assertTrue(leagues.is_parked(1))
        self.assertEqual(leagues.plan(b_ev, parked, [a, b_ev]), ('setup', None))
        # a rally of the player's own (no event of theirs): set aside too, kept until they put it back
        self.assertEqual(leagues.plan(b_ev, busy, [b_ev]), ('park-own', {'location': 'Wales', 'stages': 6, 'done': 2}))
        own = leagues.apply_plan(b_ev, CAR, 'park-own', None, busy)
        self.assertEqual(leagues.plan(b_ev, own, [b_ev]), ('setup', None))
        self.assertEqual([(x['location'], x['stages'], x['done']) for x in leagues.own_parked()], [('Wales', 6, 2)])

    def test_the_players_own_rally_comes_back_as_it_was(self):
        a = event(1, A_IDS, running(1), A_DAYS)
        busy = fake_save(THREE_DAYS, done=2)                          # (no event of theirs: their own rally)
        daily = rw.apply_weekend(leagues.park_own(busy), 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600,
                                 'WT_CLEAR')
        path = leagues.own_parked()[0]['path']
        back, moved = leagues.put_back(daily, path, [a])
        self.assertEqual((rw.progress(back)['done'], moved), (2, None))
        self.assertEqual(rw.read_weekend(back)['stages'], rw.read_weekend(busy)['stages'])   # its own calendar again
        leagues.forget_own(path)
        self.assertEqual(leagues.own_parked(), [])
        # put back over a league rally in progress: that one is set aside as its event's
        league = fake_save(THREE_DAYS, done=1)                        # event 1's rally, 1 stage done
        leagues.park_own(busy)
        back2, moved2 = leagues.put_back(league, leagues.own_parked()[0]['path'], [a])
        self.assertEqual((rw.progress(back2)['done'], moved2), (2, a))
        self.assertTrue(leagues.is_parked(1))

    def test_a_rally_set_aside_comes_back_as_it_was(self):
        a = event(1, A_IDS, running(2), A_DAYS)
        busy = fake_save(THREE_DAYS, done=2)
        daily = rw.apply_weekend(leagues.park(busy, 1), 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600,
                                 'WT_CLEAR')
        self.assertEqual(leagues.plan(a, daily, [a]), ('unpark', None))
        back = leagues.apply_plan(a, CAR, 'unpark', None, daily)
        self.assertEqual(rw.progress(back)['done'], 2)
        self.assertEqual(leagues.plan(a, back, [a]), ('resume', 2))   # (an older copy set aside: the game's is newer)
        with self.assertRaisesRegex(leagues.Gone, 'set aside has 2'):
            leagues.apply_plan(event(1, A_IDS, running(1), A_DAYS), CAR, 'unpark', None, daily)

    def test_whose_rally_is_in_the_game(self):
        a, a2 = event(1, A_IDS, None, A_DAYS), event(3, A_IDS, running(1), A_DAYS)   # two events on the same stages
        self.assertIs(leagues.owner_of(fake_save(THREE_DAYS, done=1), [a, a2]), a2)    # the started one
        self.assertIs(leagues.owner_of(fake_save(THREE_DAYS, done=0), [a]), a)         # begun, nothing driven
        self.assertIsNone(leagues.owner_of(fake_save(THREE_DAYS, done=1), [a]))
        self.assertIsNone(leagues.owner_of(fake_save(THREE_DAYS), [a, a2]))           # no rally in progress


class ChangedInGame(TempDirs):
    """The event's settings or calendar changed in the game's own menus before START RALLY (the game writes them into
    its save as the rally starts)."""

    def test_as_set_up_nothing_changed(self):
        ev = event(2, B_IDS)
        b = leagues.apply_plan(ev, CAR, 'setup', None, fake_save(THREE_DAYS))
        self.assertEqual(leagues.changed_in_game(rw.read_weekend(b), ev), [])

    def test_a_setting_or_the_weather_changed(self):
        ev = event(2, B_IDS)
        b = bytearray(leagues.apply_plan(ev, CAR, 'setup', None, fake_save(THREE_DAYS)))
        w = rw.read_weekend(bytes(b))
        b[w['data'] + rw.DAMAGE] = 0                               # damage off in the game's Race Settings
        b[w['data'] + rw.PENALTY_AT] = 2                           # realistic penalties
        self.assertEqual(leagues.changed_in_game(rw.read_weekend(bytes(b)), ev), ['damage', 'penalties'])
        ev2 = dict(ev, stages=[dict(s, weatherGame='WT_HEAVY_RAIN') if s['no'] == 2 else s for s in ev['stages']])
        self.assertEqual(leagues.changed_in_game(rw.read_weekend(bytes(b)), ev2), ['damage', 'penalties', 'weather'])
        self.assertEqual(leagues.changed_in_game(rw.read_weekend(fake_save(THREE_DAYS)), ev)[-1], 'stages')


class OfficialResult(unittest.TestCase):
    def test_a_later_stage_found_whatever_its_stamp(self):
        T = 1791482963.0
        ss1 = entry(B_IDS[0], [run(CAR['id'], [50.0, 100.2], 12)], T)
        before = leagues.known(fake_save(THREE_DAYS, results=[ss1]))
        # SS2 with the stamp of the rally's set-up (the same as SS1's), driven a day later
        ss2 = entry(B_IDS[1], [run('Hyundaii20NRally2', [61.5, 130.25], 0)], T)
        o = leagues.official(fake_save(THREE_DAYS, results=[ss1, ss2]), B_IDS[1], CAR['id'], before)
        self.assertEqual((o['time'], o['penalty'], o['total']), (130.25, 0, 130.25))
        self.assertIsNone(leagues.official(fake_save(THREE_DAYS, results=[ss1]), B_IDS[0], CAR['id'], before))
        self.assertIsNone(leagues.official(fake_save(THREE_DAYS, results=[ss1, ss2]), B_IDS[1], 'SkodaFabiaRSRally2', before))


class Pending(TempDirs):
    def test_waiting_results_count_already(self):
        evs = [event(1, B_IDS), event(2, B_IDS, running(0)), event(3, B_IDS, running(1))]
        leagues.save_pending([{'kind': 'start', 'eventId': 1, 'car': CAR['name']},
                              {'kind': 'stage', 'eventId': 1, 'no': 0, 'timeMs': 1000, 'penaltyMs': 500},
                              {'kind': 'begin', 'eventId': 2, 'no': 0},
                              {'kind': 'stage', 'eventId': 2, 'no': 0, 'timeMs': 1000, 'penaltyMs': 0},
                              {'kind': 'stage', 'eventId': 2, 'no': 1, 'timeMs': 2000, 'penaltyMs': 0},
                              {'kind': 'stage', 'eventId': 3, 'no': 0, 'timeMs': 1, 'penaltyMs': 0},   # had it already
                              {'kind': 'dnf', 'eventId': 3, 'no': 1, 'reason': 'restarted'}])
        leagues.with_pending(evs, leagues.pending())
        self.assertEqual([(e['entry']['status'], e['entry']['done'], e['entry']['totalMs']) for e in evs],
                         [('running', 1, 1500), ('finished', 2, 3000), ('dnf', 1, 1000)])
        self.assertEqual(evs[2]['entry']['reason'], 'restarted')


class Following(TempDirs):
    """The app following a driver through an event (App.__new__: no window)."""

    def setUp(self):
        super().setUp()
        self.save = os.path.join(tempfile.mkdtemp(), 'PlayerDataSaveSlot.sav')
        p = mock.patch('acr_daily.saveslot.SAVE', self.save)
        p.start()
        self.addCleanup(p.stop)
        self.ev = event(2, B_IDS)
        self.ev['rules'] = {}                     # the default rules: what fake_save() holds
        self.cal = [(s['day'] - 1, s['stageId'], s['startSeconds'], 'ServiceParkDefault' if s['service'] else 'NoZone')
                    for s in self.ev['stages']]   # the event's calendar as the game keeps it
        a = App.__new__(App)
        a.s, a.api, a.root, a.sub_l = {'token': 't' * 64}, mock.Mock(), mock.Mock(), mock.Mock()
        a.dailies = {}
        a._league_init()
        a.league_events = [self.ev]
        a._render_leagues = a.refresh_league_board = a.refresh_leagues = a.toggle_league_view = mock.Mock()
        a._league_send = mock.Mock()
        self.a = a
        for s in self.ev['stages']:
            s['route'] = ROUTE
        a._follow(self.ev, CAR)

    def write(self, done=None, results=()):
        with open(self.save, 'wb') as f:
            f.write(fake_save(self.cal, done=done, results=list(results)))

    def sent(self):
        return [c.args[0] for c in self.a._league_send.call_args_list]

    def test_each_stage_sent_with_the_games_result_then_the_next_one(self):
        a, run_ = self.a, self.a.league_run
        self.assertEqual((a.drive_target, run_['no'], run_['judge'].ch['stageId']), ('league', 0, B_IDS[0]))
        self.write()
        a._league_started(run_)                                       # SS1's clock started: the entry
        self.assertEqual(self.sent(), [{'kind': 'start', 'eventId': 2, 'car': CAR['name']}])
        run_['judge'].result = {'clockMs': 100000, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        self.assertTrue(run_['wait'])
        self.write(done=1, results=[entry(B_IDS[0], [run(CAR['id'], [50.0, 100.2], 12)], 1791482963.0 + 5)])
        with mock.patch('acr_daily.saveslot.game_running', return_value=True), \
                mock.patch('acr_daily.settings.append_result'):
            a._league_check_official()
        st = self.sent()[-1]
        self.assertEqual((st['kind'], st['no'], st['timeMs'], st['penaltyMs']), ('stage', 0, 100200, 12000))
        self.assertEqual((run_['no'], run_['judge'].ch['stageId'], self.ev['entry']['done']), (1, B_IDS[1], 1))
        a._league_started(run_)                                       # SS2: in the event's rally, 1 stage done
        self.assertEqual(self.sent()[-1], {'kind': 'begin', 'eventId': 2, 'no': 1})
        self.assertIsNone(run_['ignore'])

    def test_a_stage_outside_the_events_rally_does_not_count(self):
        a, run_ = self.a, self.a.league_run
        with open(self.save, 'wb') as f:
            f.write(fake_save(THREE_DAYS))                            # another calendar in the game
        a._league_started(run_)
        self.assertIn('does not count', run_['ignore'])
        self.assertEqual(self.sent(), [])
        a._league_failed(run_, 'restarted')                           # nothing ends: the same stage again
        self.assertEqual((run_['no'], run_['ignore'], run_.get('over')), (0, None, None))

    def test_settings_changed_in_the_game(self):
        a, run_ = self.a, self.a.league_run
        b = bytearray(leagues.apply_plan(self.ev, CAR, 'setup', None, fake_save(self.cal)))
        b[rw.read_weekend(bytes(b))['data'] + rw.DAMAGE] = 0
        with open(self.save, 'wb') as f:
            f.write(bytes(b))
        a._league_started(run_)                                       # SS1: it doesn't count, no entry
        self.assertIn('damage changed in the game', run_['ignore'])
        self.assertEqual(self.sent(), [])
        # a later stage of a started entry with other settings than the event's: the entry ends
        self.ev['entry'] = running(1)
        run_['no'], run_['ignore'] = 1, None
        b2 = bytearray(fake_save(self.cal, done=1))
        b2[rw.read_weekend(bytes(b2))['data'] + rw.DAMAGE] = 0
        with open(self.save, 'wb') as f:
            f.write(bytes(b2))
        a._league_started(run_)
        self.assertEqual(self.sent()[-1]['kind'], 'dnf')
        self.assertIn('damage', self.sent()[-1]['reason'])
        self.assertTrue(run_['over'])

    def test_a_restart_on_a_stage_is_a_dnf(self):
        a, run_ = self.a, self.a.league_run
        self.write()
        a._league_started(run_)
        a._league_failed(run_, 'restarted')
        self.assertEqual(self.sent()[-1], {'kind': 'dnf', 'eventId': 2, 'no': 0, 'reason': 'restarted'})
        self.assertEqual((self.ev['entry']['status'], run_['over'], a.drive_target), ('dnf', True, 'daily'))

    def test_the_server_ends_an_entry_for_a_stage_started_again(self):
        a = self.a
        leagues.save_pending([{'kind': 'begin', 'eventId': 2, 'no': 1}])
        a.api.league_begin.return_value = {'status': 'dnf', 'reason': 'SS2 started again'}
        with mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)):
            a.flush_leagues()
        self.assertEqual(leagues.pending(), [])
        self.assertEqual((a.league_run['over'], a.drive_target, self.ev['entry']['reason']), (True, 'daily', 'SS2 started again'))

    def test_a_daily_sets_the_league_rally_aside(self):
        a = self.a
        self.ev['entry'] = running(1)
        self.write(done=1)
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=True), \
                mock.patch('acr_daily.saveslot.backup_dir', return_value=tempfile.mkdtemp()):
            self.assertTrue(a._league_park_for_daily())
        with open(self.save, 'rb') as f:
            self.assertIsNone(rw.progress(f.read()))
        self.assertTrue(leagues.is_parked(2))
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=False):
            self.write(done=1)
            self.assertFalse(a._league_park_for_daily())             # said no: the daily is not set up

    def test_drive_on_a_daily_says_it_once_and_never_during_a_league_stage(self):
        a = self.a
        self.ev['entry'] = running(1)
        self.write(done=1)
        a.league_run['judge'].state = 'running'                      # on a league stage: the daily waits
        with mock.patch('acr_daily.leagueui.messagebox.showinfo') as info:
            self.assertIsNone(a._league_before_daily(True))
        self.assertIn('would be a DNF', info.call_args.args[1])
        a.league_run['judge'].state = 'waiting'
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=False), \
                mock.patch('acr_daily.saveslot.game_running', return_value=False):
            self.assertIsNone(a._league_before_daily(True))         # said no
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=True) as ask, \
                mock.patch('acr_daily.saveslot.game_running', return_value=True):
            self.assertTrue(a._league_before_daily(True))
        self.assertIn('Nothing is lost', ask.call_args.args[1])
        self.assertIn('closes it', ask.call_args.args[1])
        with mock.patch('acr_daily.leagueui.messagebox.askyesno') as ask, \
                mock.patch('acr_daily.saveslot.backup_dir', return_value=tempfile.mkdtemp()):
            self.assertTrue(a._league_park_for_daily())              # set aside without asking again
        ask.assert_not_called()
        self.assertTrue(leagues.is_parked(2))
        self.assertFalse(a._league_before_daily(False))            # a single-stage daily: the rally stays

    def test_a_daily_sets_the_players_own_rally_aside_and_put_back_returns_it(self):
        a = self.a
        with open(self.save, 'wb') as f:
            f.write(fake_save(THREE_DAYS, done=2))                    # a rally of their own: 2 of its 6 stages done
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=True) as ask, \
                mock.patch('acr_daily.saveslot.game_running', return_value=False):
            self.assertTrue(a._league_before_daily(True))
        self.assertIn('of your own is in progress in the game (Wales, 2 of 6 stages done)', ask.call_args.args[1])
        with mock.patch('acr_daily.leagueui.messagebox.askyesno') as ask, \
                mock.patch('acr_daily.saveslot.backup_dir', return_value=tempfile.mkdtemp()):
            self.assertTrue(a._league_park_for_daily())              # said once: set aside without asking again
        ask.assert_not_called()
        with open(self.save, 'rb') as f:
            self.assertIsNone(rw.progress(f.read()))
        own = leagues.own_parked()
        self.assertEqual([(x['location'], x['done']) for x in own], [('Wales', 2)])
        # PUT BACK (the game closed): the rally in the game again, its copy set aside gone, the game started
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.saveslot.launch_game') as launch, \
                mock.patch('acr_daily.saveslot.backup_dir', return_value=tempfile.mkdtemp()):
            a.put_back_own(own[0]['path'])
        with open(self.save, 'rb') as f:
            self.assertEqual(rw.progress(f.read())['done'], 2)
        self.assertEqual(leagues.own_parked(), [])
        launch.assert_called_once()

    def test_the_rally_in_progress_is_shown_first(self):
        a = self.a
        other = event(3, A_IDS, days=A_DAYS)
        a.league_events = [other, self.ev, event(4, B_IDS, entry={'status': 'finished', 'done': 2, 'totalMs': 1})]
        self.assertEqual(a._league_in_progress(), [])
        self.ev['entry'] = running(1)
        self.assertEqual([e['id'] for e in a._league_in_progress()], [2])
        self.assertIn('RESUME', a._held_hint(self.ev))
        leagues.park(fake_save(self.cal, done=1), 2)
        self.assertIn('CONTINUE puts it back', a._held_hint(self.ev))
        self.assertEqual(a._progress_text(self.ev, 0)[:24], 'SS2 of 2 next · 0:01.000')


if __name__ == '__main__':
    unittest.main()
