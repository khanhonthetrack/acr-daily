"""League events in the app: what DRIVE does with the game's save (set up, resume, set aside, put back), results still
waiting to be sent, and the app following a driver through an event's stages (on made-up saves laid out as the
game's, test_rallyweekend.fake_save)."""
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acr_daily import leagues, leagueui, rallyweekend as rw, saveslot, waiting  # noqa: E402
from acr_daily.app import App  # noqa: E402
from acr_daily.telemetry import Frame  # noqa: E402
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
        p = mock.patch('acr_daily.saveslot.SETTLE_S', 0)               # (the save written here is read at once)
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
        # with the event's retirement rule, SS3 driven without the app counts as retired, and the entry goes on
        ruled = dict(ev, rules=dict(ev['rules'], retire=5))
        self.assertEqual(leagues.plan(ruled, fake_save(THREE_DAYS, done=3)), ('missed', 3))
        self.assertIsNone(leagues.apply_plan(ruled, CAR, 'missed', 3, fake_save(THREE_DAYS, done=3)))
        # the game took its rally back (quit away from a service park, a crash; 13 Nov 2026, event 8): resumed where
        # the game is, the counted stages driven again for nothing; dropped altogether: set up afresh (from 0.1.5)
        self.assertEqual(leagues.plan(ev, fake_save(THREE_DAYS, done=1)), ('resume', 1))
        self.assertEqual(leagues.plan(ev, fake_save(THREE_DAYS)), ('setup', None))

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

    def test_a_reinstated_entry_finds_its_rally_among_the_players_own(self):
        """Reported 2026-11-08 (a cup quarter-final): while the entry was a DNF, a daily set the event's rally (SS1 driven)
        aside as the player's own (owner_of only knows running entries). An admin reinstated the entry, and CONTINUE
        ended it again: "no longer in the game". Now CONTINUE finds it in PUT BACK's list and puts it back as the event's."""
        busy = fake_save(THREE_DAYS, done=1)                          # the event's rally, SS1 driven
        self.assertIsNone(leagues.owner_of(busy, [event(1, A_IDS, dict(running(1), status='dnf'), A_DAYS)]))
        daily = rw.apply_weekend(leagues.park_own(busy), 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600,
                                 'WT_CLEAR')                          # (the daily set up in its place)
        leagues.park_own(fake_save([(0, s, 28800, 'ServiceParkDefault') for s in B_IDS], done=1))   # another of their own
        ev = event(1, A_IDS, running(1), A_DAYS)                      # reinstated: running, SS1 done
        self.assertEqual(leagues.plan(event(1, A_IDS, running(2), A_DAYS), daily, [ev]),
                         ('setup', None))                             # a copy at another stage is not taken
        action, path = leagues.plan(ev, daily, [ev])
        self.assertEqual(action, 'unpark-own')
        back = leagues.apply_plan(ev, CAR, action, path, daily)
        self.assertEqual(leagues.rally_state(back, ev)[0], 'this')
        self.assertEqual(rw.read_weekend(back)['stages'], rw.read_weekend(busy)['stages'])   # its own calendar again
        self.assertEqual(leagues.plan(ev, back, [ev]), ('resume', 1))
        with self.assertRaisesRegex(leagues.Gone, 'not where the entry is'):
            leagues.apply_plan(event(1, A_IDS, running(2), A_DAYS), CAR, 'unpark-own', path, daily)
        leagues.forget_own(path)
        self.assertEqual([(x['location'], x['done']) for x in leagues.own_parked()], [('Wales', 1)], 'the other one stays')

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
        run_['judge']._start_wall = 1791482963.0
        a._league_started(run_)                                       # SS1's clock started: the entry
        self.assertEqual(self.sent(), [{'kind': 'start', 'eventId': 2, 'car': CAR['name'], 'at': 1791482963000}])
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
        run_['judge']._start_wall = 1791483163.5
        a._league_started(run_)                                       # SS2: in the event's rally, 1 stage done
        self.assertEqual(self.sent()[-1], {'kind': 'begin', 'eventId': 2, 'no': 1, 'at': 1791483163500})
        self.assertIsNone(run_['ignore'])

    def test_a_stage_waiting_when_the_app_closes_is_sent_when_it_opens_again(self):
        a, run_ = self.a, self.a.league_run
        self.write()
        a._league_started(run_)
        run_['judge'].result = {'clockMs': 100000, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        self.assertEqual([(x['kind'], x['no']) for x in waiting.load()], [('league', 0)])
        # the app closes before the game saved the stage's time; it opens again (a new one: what waits on disk)
        b = App.__new__(App)
        b.s, b.api, b.root, b.sub_l, b.dailies = {'token': 't' * 64}, mock.Mock(), mock.Mock(), mock.Mock(), {}
        b._league_init()
        b.league_events = [self.ev]
        b._league_send = mock.Mock()
        self.assertEqual(len(b._league_restored), 1)
        self.assertTrue(b._waiting_text())                            # DRIVE / CONTINUE wait for it
        b._league_autofollow()                                        # not followed: SS1 isn't sent yet
        self.assertIsNone(b.league_run)
        self.write(done=1, results=[entry(B_IDS[0], [run(CAR['id'], [50.0, 100.2], 12)], 1791482963.0 + 5)])
        with mock.patch('acr_daily.saveslot.game_running', return_value=True), \
                mock.patch('acr_daily.settings.append_result'):
            b._league_check_restored()
        st = b._league_send.call_args.args[0]
        self.assertEqual((st['kind'], st['eventId'], st['no'], st['timeMs'], st['penaltyMs']), ('stage', 2, 0, 100200, 12000))
        self.assertEqual((b._league_restored, waiting.load(), b._waiting_text()), ([], [], None))

    def test_a_stage_the_game_never_saved_is_a_dnf_saying_why(self):
        a, run_ = self.a, self.a.league_run
        self.write()
        a._league_started(run_)
        run_['judge'].result = {'clockMs': 100000, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        with mock.patch('acr_daily.saveslot.game_running', return_value=True):
            a._league_check_official()                                # still on the game's results screen
        self.assertEqual(self.sent()[-1]['kind'], 'start')
        # the game stuck on its loading screen, closed from the Task Manager: its save never had the stage's result
        with mock.patch('acr_daily.saveslot.game_running', return_value=False):
            for _ in range(3):
                a._league_check_official()
        st = self.sent()[-1]
        self.assertEqual((st['kind'], st['no'], st['reason']), ('dnf', 0, 'the game closed before saving its official result'))
        self.assertTrue(run_['over'])
        self.assertEqual(waiting.load(), [])

    def test_a_stage_the_game_never_saved_sends_the_games_log(self):
        a, run_ = self.a, self.a.league_run
        a.api.site = 'https://acrdaily.com'
        self.write()
        a._league_started(run_)
        run_['judge'].result = {'clockMs': 100000, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.gamelog.send') as send:
            for _ in range(3):
                a._league_check_official()
        _api, runs, area, url, _context = send.call_args.args
        self.assertEqual((area, url), ('league', 'https://acrdaily.com/e/2'))
        self.assertEqual((runs[0]['what'], runs[0]['stage'], runs[0]['car'], runs[0]['clockMs'], runs[0]['why']),
                         ('%s · SS1' % self.ev['name'], B_IDS[0], CAR['id'], 100000,
                          'the game closed before saving its official result'))

    def test_a_cup_stage_never_saved_found_after_a_restart_sends_its_log(self):
        a, run_ = self.a, self.a.league_run
        self.write()
        a._league_started(run_)
        run_['judge'].result = {'clockMs': 100000, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        b = App.__new__(App)                                          # the app opened again: what waits on disk
        b.s, b.api, b.root, b.sub_l, b.dailies = {}, mock.Mock(site='https://acrdaily.com'), mock.Mock(), mock.Mock(), {}
        b._league_init()
        b.league_events = [dict(self.ev, kind='cup')]
        b._league_send = mock.Mock()
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.gamelog.send') as send:
            for _ in range(3):
                b._league_check_restored()
        self.assertEqual(b._league_send.call_args.args[0]['kind'], 'dnf')
        _api, runs, area, url, _context = send.call_args.args
        self.assertEqual((area, url, runs[0]['stage'], runs[0]['what']),
                         ('cup', 'https://acrdaily.com/e/2', B_IDS[0], '%s · SS1' % self.ev['name']))

    def test_a_result_the_watch_missed_is_found_by_a_last_look_when_the_game_closes(self):
        a, run_ = self.a, self.a.league_run
        self.write()
        a._league_started(run_)
        run_['judge'].result = {'clockMs': 100200, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        self.write(done=1, results=[entry(B_IDS[0], [run(CAR['id'], [50.0, 100.2], 12)], 1791482963.0 + 5)])
        with mock.patch('acr_daily.saveslot.SaveWatch.look', return_value=None), \
                mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.settings.append_result'):
            for _ in range(3):
                a._league_check_official()
        st = self.sent()[-1]
        self.assertEqual((st['kind'], st['no'], st['timeMs'], st['penaltyMs']), ('stage', 0, 100200, 12000))

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

    def test_the_weather_changed_before_ss1_says_so_after_the_finish_too(self):
        # (reported 2026-11-07: the game loaded another weather than the event's; the run didn't count, yet after the
        # finish the timer said only "STANDBY · Next: SS1" and the event's button "FOLLOWING")
        a, run_ = self.a, self.a.league_run
        b = bytearray(leagues.apply_plan(self.ev, CAR, 'setup', None, fake_save(self.cal)))
        w = rw.read_weekend(bytes(b))
        o = saveslot._fstring_at(bytes(b), w['data'] + rw.HEADER)[1] + 4 + 4    # SS1's day, then its stage id
        o = saveslot._fstring_at(bytes(b), o)[1]
        b[o + rw.W_TYPE] = rw.WEATHERS.index('WT_STORM')                        # what the game wrote: a storm
        with open(self.save, 'wb') as f:
            f.write(bytes(b))
        a._league_started(run_)
        self.assertIn('weather changed in the game', run_['ignore'])
        self.assertIn('Click DRIVE AGAIN on the event', run_['ignore'])
        self.assertEqual(self.sent(), [], 'no start: the server never hears of a run that does not count')
        run_['judge'].result = {'clockMs': 139892, 'startedAt': 1791482963.0}
        a._league_finished(run_)                                      # at the finish: SS1 again
        self.assertEqual((run_['no'], run_['ignore'], run_['judge'].state), (0, None, 'waiting'))
        self.assertEqual(run_['missed_short'], 'weather changed in the game')
        from acr_daily.telemetry import Frame
        status, _sub, ov = a._league_overlay_state(Frame(0.0, 1, 0, 0.0, 0.0, 0.0, '', ''))   # (the game in its menus)
        self.assertEqual(ov[0], 'standby')
        self.assertEqual(ov[4], 'NOT COUNTED: weather changed in the game · DRIVE AGAIN on the event')
        self.assertIn('SS1 did not count', status)
        # the next start (set up again): the old reason goes
        with open(self.save, 'wb') as f:
            f.write(leagues.apply_plan(self.ev, CAR, 'setup', None, fake_save(self.cal)))
        a._league_started(run_)
        self.assertIsNone(run_['missed'])
        self.assertEqual(self.sent(), [{'kind': 'start', 'eventId': 2, 'car': CAR['name'], 'at': None}])

    def test_a_restart_on_a_stage_is_a_dnf(self):
        a, run_ = self.a, self.a.league_run
        self.write()
        a._league_started(run_)
        a._league_failed(run_, 'restarted')
        self.assertEqual(self.sent()[-1], {'kind': 'dnf', 'eventId': 2, 'no': 0, 'reason': 'restarted'})
        self.assertEqual((self.ev['entry']['status'], run_['over'], a.drive_target), ('dnf', True, 'daily'))

    def test_each_start_goes_with_when_it_was(self):
        # the same start sent again (a retry after the server had it) is told from a second start by its time
        a = self.a
        leagues.save_pending([{'kind': 'start', 'eventId': 2, 'car': CAR['name'], 'at': 1000},
                              {'kind': 'begin', 'eventId': 2, 'no': 1, 'at': 2000}, {'kind': 'begin', 'eventId': 2, 'no': 1}])
        a.api.league_start.return_value = {'started': True}
        a.api.league_begin.return_value = {'status': 'running'}
        with mock.patch('acr_daily.app.ui', side_effect=lambda w, fn, *x: fn(*x)):
            a.flush_leagues()
        a.api.league_start.assert_called_once_with(2, CAR['name'], 1000)
        self.assertEqual([c.args for c in a.api.league_begin.call_args_list], [(2, 1, 2000), (2, 1, None)])   # (one queued by 0.0.27)

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
        self.assertIn('it will be a DNF', info.call_args.args[1])
        a.league_run['judge'].state = 'waiting'
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=False), \
                mock.patch('acr_daily.saveslot.game_running', return_value=False):
            self.assertIsNone(a._league_before_daily(True))         # said no
        with mock.patch('acr_daily.leagueui.messagebox.askyesno', return_value=True) as ask, \
                mock.patch('acr_daily.saveslot.game_running', return_value=True):
            self.assertTrue(a._league_before_daily(True))
        self.assertIn('Nothing is lost', ask.call_args.args[1])
        self.assertIn('The game will restart', ask.call_args.args[1])
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
        self.assertIn('Your own Rally Weekend is in progress (Wales, 2 of 6 stages)', ask.call_args.args[1])
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

    def test_continue_on_a_reinstated_entry_puts_its_rally_back_and_follows_ss2(self):
        """An entry an admin reinstated, its rally set aside as the player's own meanwhile: CONTINUE puts it back as the
        event's and follows the next stage, rather than ending the entry again."""
        a = self.a
        self.ev['entry'] = running(1)
        leagues.park_own(fake_save(self.cal, done=1))                 # set aside while the entry was a DNF
        with open(self.save, 'wb') as f:                              # a daily's Rally Weekend in its place
            f.write(rw.apply_weekend(fake_save(self.cal), 'AlsaceS4SaverneShort1Forward', 'Peugeot208Rally4', 57600, 'WT_CLEAR'))
        a.league_run = None
        a._render_strip = mock.Mock()
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.saveslot.launch_game') as launch, \
                mock.patch('acr_daily.saveslot.backup_dir', return_value=tempfile.mkdtemp()), \
                mock.patch('acr_daily.leagueui.messagebox') as box:
            a._league_setup_and_launch(self.ev, CAR)
        box.showwarning.assert_not_called()
        self.assertNotIn('dnf', [x['kind'] for x in self.sent()])
        with open(self.save, 'rb') as f:
            self.assertEqual(leagues.rally_state(f.read(), self.ev)[0], 'this')
        self.assertEqual((leagues.own_parked(), a.league_run['no']), ([], 1))   # out of PUT BACK's list; SS2 next
        launch.assert_called_once()
        self.assertIn('RESUME', a.sub_l.configure.call_args.kwargs['text'])

    def test_the_game_took_its_rally_back_the_counted_stages_are_driven_again(self):
        """Gand92, 13 Nov 2026: SS2 counted, the game's rally back at 1 stage done (quit away from a service park, as
        ACRK's guide warns): the entry ended. Now the counted stages are driven again, for nothing, to get to SS3."""
        a = self.a
        self.ev = ev = event(1, A_IDS, running(2), A_DAYS)             # (six stages over three days)
        for s in ev['stages']:
            s['route'] = ROUTE
        a.league_events = [ev]
        with open(self.save, 'wb') as f:
            f.write(fake_save(THREE_DAYS, done=1))
        a.league_run = None
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.saveslot.launch_game'), \
                mock.patch('acr_daily.leagueui.messagebox') as box:
            a._league_setup_and_launch(self.ev, CAR)
        self.assertEqual(self.sent(), [])
        box.showwarning.assert_not_called()
        self.assertIn('took your rally back to SS2. Drive it again to get to SS3', box.showinfo.call_args.args[1])
        self.assertIn('quit the game from a service park', box.showinfo.call_args.args[1])
        run_ = a.league_run
        self.assertEqual((run_['no'], run_['judge'].ch['stageId']), (2, A_IDS[2]))
        self.assertIn('RESUME, then Start Stage (SS2)', a.sub_l.configure.call_args.kwargs['text'])
        # on SS2 again: the timer says it counted already
        on_ss2 = Frame(1.0, 60, 0, 500.0, 500.0, 0.0, CAR['name'], 'Wales 1')
        line = a._league_overlay_state(on_ss2)
        self.assertEqual(line[2][4], 'SS2 counted already · on to SS3')
        # SS2 driven again (were it the same stage as SS3, the judge would start): nothing sent, nothing missed
        a._league_started(run_)
        self.assertTrue(run_['again'])
        self.assertIn('SS2 counted already', run_['ignore'])
        run_['judge'].result = {'clockMs': 100000, 'startedAt': 1791482963.0}
        a._league_finished(run_)
        self.assertEqual((self.sent(), run_.get('missed'), run_['ignore'], run_.get('over')), ([], None, None, None))
        self.assertEqual(run_['judge'].ch['stageId'], A_IDS[2])        # (SS3 next, as before)

    def test_a_stage_driven_without_the_app_counts_as_retired_under_the_retirement_rule(self):
        a = self.a
        self.ev = ev = event(1, A_IDS, running(2), A_DAYS)
        ev['rules']['retire'] = 5
        for s in ev['stages']:
            s['route'] = ROUTE
        a.league_events = [ev]
        with open(self.save, 'wb') as f:
            f.write(fake_save(THREE_DAYS, done=3))                    # SS3 driven while the app was closed
        a.league_run = None
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.saveslot.launch_game'), \
                mock.patch('acr_daily.leagueui.messagebox') as box:
            a._league_setup_and_launch(ev, CAR)
        self.assertEqual(self.sent(), [{'kind': 'missed', 'eventId': 1, 'no': 2,
                                        'reason': 'SS3 was driven without ACR Daily watching'}])
        box.showwarning.assert_not_called()
        self.assertIn('SS3 was driven without ACR Daily watching, so it counts as retired: the slowest time on it + 5 min',
                      box.showinfo.call_args.args[1])
        self.assertEqual((ev['entry']['done'], a.league_run['no'], a.league_run['judge'].ch['stageId']), (3, 3, A_IDS[3]))
        self.assertIn('Start Stage (SS4)', a.sub_l.configure.call_args.kwargs['text'])

    def test_the_game_dropped_its_rally_it_is_set_up_again(self):
        """Geri, 14 Nov 2026, and rzalan, 9 Nov: the event's rally gone from the game. Set up again from SS1 (the
        counted stages driven again for nothing) instead of the entry ending."""
        a = self.a
        self.ev['entry'] = running(1)
        self.write()                                                  # no rally in progress
        a.league_run = None
        with mock.patch('acr_daily.saveslot.game_running', return_value=False), \
                mock.patch('acr_daily.saveslot.launch_game'), \
                mock.patch('acr_daily.saveslot.backup_dir', return_value=tempfile.mkdtemp()), \
                mock.patch('acr_daily.leagueui.messagebox') as box:
            a._league_setup_and_launch(self.ev, CAR)
        self.assertEqual(self.sent(), [])
        self.assertIn('took your rally back to SS1', box.showinfo.call_args.args[1])
        with open(self.save, 'rb') as f:                              # the event's rally, ready for START RALLY
            self.assertTrue(leagues.same_calendar(rw.read_weekend(f.read())['stages'], self.ev))
        self.assertEqual(a.league_run['no'], 1)


def h2h(eid, entry=None):
    """A 1V1's match as the server sends it: an event of a league of its own, no season."""
    return dict(event(eid, B_IDS, entry), kind='h2h', name='Me vs Ann', league='1V1: Me vs Ann', leagueId='h2hA0001',
                seasonId=None)


def cup(eid, entry=None):
    return dict(event(eid, B_IDS, entry), kind='cup', name='Quarter-final: Bob vs Me', league='Autumn Cup', leagueId='abcd1234',
                seasonId=None)


class Matches(TempDirs):
    """1V1s and cup matches in the LEAGUES view (on a Tk window that is never shown): tagged, the other driver
    named, listed before league events, driven as they are."""

    def setUp(self):
        super().setUp()
        from test_app import tk_root
        import tkinter as tk
        self.root = tk_root()
        self.addCleanup(self.root.destroy)
        a = App.__new__(App)
        a.s, a.api, a.root, a.sub_l = {'token': 't' * 64, 'name': 'Me'}, mock.Mock(), self.root, mock.Mock()
        a.dailies = {}
        a._league_init()
        a.league_box, a.league_strip, a.daily_box = tk.Frame(self.root), tk.Frame(self.root), tk.Frame(self.root)
        a.league_rows = tk.Frame(a.league_box)
        a.league_rows.pack(fill='x')
        a._build_browser(a.league_box)                        # (RALLIES: its list, browserui.py)
        a.daily_box.pack()
        a.refresh_league_board = mock.Mock()
        self.a = a

    def said(self, w):
        from test_inbox import texts
        return texts(w)

    def test_after_a_run_that_did_not_count_the_button_says_drive_again(self):
        a = self.a
        ev = event(7, B_IDS)
        a.league_events, a.league_sel, a.drive_target = [ev], 7, 'league'
        a.league_run = {'ev': ev, 'no': 0, 'car': CAR, 'judge': mock.Mock(), 'missed': None}
        a._render_leagues()
        self.assertIn('FOLLOWING', self.said(a.league_rows))
        a.league_run['missed'] = 'the event\'s weather changed in the game\'s menus'
        a._render_leagues()
        said = self.said(a.league_rows)
        self.assertIn('DRIVE AGAIN  ›', said)
        self.assertNotIn('FOLLOWING', said)

    def test_the_other_driver_from_the_names(self):
        self.assertEqual(leagueui.opponent(h2h(1), 'Me'), 'Ann')
        self.assertEqual(leagueui.opponent(cup(1), 'me'), 'Bob')
        self.assertEqual(leagueui.opponent(dict(h2h(1), name='Friday duel'), 'Me'), 'Ann')   # (its league names them)
        self.assertIsNone(leagueui.opponent(cup(1), 'Someone else'))                         # (renamed since)
        self.assertIsNone(leagueui.opponent(event(1, B_IDS), 'Me'))
        # the server names the other driver as they are now: that wins over the names in the match's title
        self.assertEqual(leagueui.opponent(dict(cup(1), opponent={'steamId': '1', 'name': 'Bobby'}), 'Someone else'), 'Bobby')

    def test_each_tab_shows_its_own_kind(self):
        a = self.a
        a.league_view = True
        a.league_events = [dict(event(1, B_IDS), kind='league'), h2h(2), cup(3), event(4, B_IDS)]   # (4: an older server's)
        a._show_board_title = a._fill_tree = mock.Mock()       # (the timing sheet: not on this window)
        a._render_leagues()                                   # RALLIES: the championships' rounds (and rallies) only
        said = self.said(a.league_rows)
        self.assertEqual(a.league_sel, 1)                    # the first listed: picked, in full
        self.assertEqual([x for x in said if x in ('Me vs Ann', 'Quarter-final: Bob vs Me', 'Round 1', 'Round 4')], ['Round 1'])
        self.assertTrue(any(x.startswith('TEST') for x in said))   # a league's event: its league
        self.assertEqual(a.browse_tree.get_children(), ('1', '4'))   # every one in the list under it
        for kind, sel, name, tag in (('h2h', 2, 'Me vs Ann', '1V1 · VS ANN'), ('cup', 3, 'Quarter-final: Bob vs Me', 'CUP · AUTUMN CUP · VS BOB')):
            a.toggle_league_view(True, kind)                  # 1V1, CUPS: their matches, tagged, the other driver named
            said = self.said(a.league_rows)
            self.assertEqual(a.league_sel, sel)
            self.assertIn(name, said)
            self.assertIn(tag, said)
            self.assertNotIn('Round 1', said)
        # a rally in progress first, whatever it is; then what can still be driven
        a.league_events = [dict(event(1, B_IDS), kind='league', entry=running(1)), h2h(2, {'status': 'finished', 'done': 2,
                                                                                         'totalMs': 1}), cup(3)]
        self.assertEqual([e['id'] for e in sorted(a.league_events, key=leagueui.listed_order)], [1, 3, 2])

    def test_rallies_in_a_list_that_scrolls(self):
        """RALLIES (from 0.1.6): the one picked in full and every one in a list under it, as a game's server browser:
        a championship's round and a rally (anyone's) each in its colour, ALL / CHAMPIONSHIPS / RALLIES, the headings
        sort, a click picks one, a double click drives it. Before, the window listed four events: the rest were only on
        the website, where nothing is driven (7 leagues, 9 events open, 2026-11-15)."""
        a = self.a
        a.league_view = True
        a._show_board_title = a._fill_tree = mock.Mock()
        rally = lambda i, who, n: dict(event(i, B_IDS), kind='event', name='Rally %d' % i, organizer=who, drivers=n, closes=9e12 + i)
        a.league_events = [dict(event(1, B_IDS), closes=9e12 + 1, drivers=3), rally(2, 'Ben', 2), dict(event(3, B_IDS), closes=9e12 + 3, drivers=9),
                           rally(4, 'Cat', 4), h2h(5)]
        a._render_leagues()
        t = a.browse_tree
        self.assertEqual(t.get_children(), ('1', '2', '3', '4'))                  # (the 1V1 on its own tab)
        self.assertEqual(list(t.item('2', 'values')[:2]), ['Rally 2', 'Rally by Ben'])
        self.assertEqual(list(t.item('1', 'values')[:2]), ['Round 1', 'Test'])
        self.assertTrue(str(t.item('1', 'values')[6]).startswith('Closes in '))
        self.assertEqual((str(t.item('1', 'image')[0]), str(t.item('2', 'image')[0])), (str(a._kind_img['league']), str(a._kind_img['event'])))
        self.assertEqual(t.selection(), ('1',))                                    # the one picked, shown in full over it
        self.assertEqual([a._browse_tabs[k].cget('text') for k in ('all', 'league', 'event')], ['ALL  4', 'CHAMPIONSHIPS  2', 'RALLIES  2'])
        a.browse_filter('event')
        self.assertEqual(t.get_children(), ('2', '4'))
        a.browse_filter('all')
        for order in (('2', '1', '4', '3'), ('3', '4', '1', '2'), ('1', '2', '3', '4')):   # DRIVERS: up, down, the app's order
            a.browse_sort('drivers')
            self.assertEqual(t.get_children(), order)
        t.selection_set('4')                                                       # a click: picked, in full over the list
        self.root.update()
        self.assertEqual(a.league_sel, 4)
        self.assertIn('RALLY BY CAT', self.said(a.league_rows))
        self.assertEqual(t.selection(), ('4',))
        a.league_drive = mock.Mock()
        a._browse_drive()                                                          # a double click (or Enter): DRIVE
        a.league_drive.assert_called_once_with(4)
        a.league_events[3]['entry'] = {'status': 'finished', 'done': 2, 'totalMs': 1000, 'car': CAR['name']}
        a._render_leagues()
        self.assertEqual(t.item('4', 'values')[6], 'Finished · 0:01.000')
        a._browse_drive()                                                          # (driven already: nothing)
        a.league_drive.assert_called_once_with(4)

    def test_more_matches_than_fit_as_cards(self):
        """1V1 and CUPS keep their cards: more matches than fit (SHOWN), the others slim, LISTED of them, the rest in a
        drop-down after them."""
        import tkinter as tk
        from test_inbox import click, find
        a = self.a
        a.league_view, a.league_kind = True, 'h2h'
        a._show_board_title = a._fill_tree = mock.Mock()
        rounds = lambda: [x for x in self.said(a.league_rows) if x.startswith('Round ')]
        evs = [dict(h2h(i), name='Round %d' % i, closes=9e12 + i) for i in range(1, 11)]
        a.league_events = evs[:4]                             # 4: the cards as ever
        a._render_leagues()
        self.assertEqual(rounds(), ['Round 1', 'Round 2', 'Round 3', 'Round 4'])
        a.league_events = evs[:8]                             # 8: every one of them, the others slim
        a._render_leagues()
        said = self.said(a.league_rows)
        self.assertEqual(rounds(), ['Round %d' % i for i in range(1, 9)])
        self.assertTrue(any(x.startswith('1V1 · VS ANN · Closes in ') for x in said))
        self.assertFalse([x for x in said if 'more event' in x])
        a.league_events = evs                                 # 10: LISTED beside it, the rest in a drop-down
        a._render_leagues()
        self.assertEqual(rounds(), ['Round %d' % i for i in range(1, 2 + leagueui.LISTED)])
        with mock.patch.object(tk.Menu, 'tk_popup', autospec=True) as popup:
            click(find(a.league_rows, '2 more events  ▾'))
        menu = popup.call_args.args[0]
        self.assertEqual([menu.entrycget(i, 'label').split('  ·  ')[0] for i in range(menu.index('end') + 1)], ['Round 9', 'Round 10'])
        menu.invoke(1)
        self.assertEqual(a.league_sel, 10)
        self.assertFalse(a.browse_box.winfo_manager())       # (no list on 1V1)

    def test_one_auto_switch_at_the_top_for_everything(self):
        import time
        import tkinter as tk
        from acr_daily import app as app_mod
        from test_inbox import click
        a = self.a
        a.league_view = True
        a.league_events = [dict(event(1, B_IDS), kind='league'), h2h(2), cup(3)]
        a._show_board_title = a._fill_tree = mock.Mock()
        a.s.update(autoDrive=False, overlay={})
        for kind in ('league', 'h2h', 'cup'):                 # no AUTO by any event's DRIVE
            a.league_kind, a.league_sel = kind, None
            a._render_leagues()
            self.assertNotIn('AUTO', self.said(a.league_rows), kind)
        head = tk.Frame(self.root)
        a._build_auto_switch(head)                            # the one switch (on the settings page: settingsui.py)
        self.assertEqual(self.said(head).count('AUTO'), 1)
        track = lambda: a.auto_sw.itemcget(a.auto_sw.find_all()[0], 'fill')

        def settled():                                        # (the knob's slide: Tk's timers, run)
            for _ in range(20):
                self.root.update()
                time.sleep(0.01)
        self.assertEqual((a.auto_lbl.cget('fg'), track()), (app_mod.FG2, app_mod.BG))           # off
        with mock.patch('acr_daily.autodrive.player_keys', return_value={}), \
                mock.patch('acr_daily.autodrive.describe_keys', return_value='Enter'), \
                mock.patch('acr_daily.app.messagebox.askyesno', return_value=True) as ask:
            click(a.auto_sw)
        self.assertIn('every DRIVE (dailies, leagues, 1V1s, cups)', ask.call_args.args[1])
        settled()
        self.assertTrue(a.s['autoDrive'])
        self.assertEqual((a.auto_lbl.cget('fg'), track()), (app_mod.WHITE, app_mod.ACC))      # on: red
        click(a.auto_lbl)                                     # off again (no question asked)
        settled()
        self.assertFalse(a.s['autoDrive'])
        self.assertEqual(track(), app_mod.BG)

    def test_a_match_in_progress_over_the_dailies(self):
        a = self.a
        a.league_events = [h2h(2, running(1))]
        a._render_strip()
        self.assertTrue(any(x.startswith('MATCH IN PROGRESS · 1V1 · VS ANN') for x in self.said(a.league_strip)))

    def test_its_page_on_the_website(self):
        a = self.a
        a.league_view = True
        a.api.configured, a.api.base = True, 'https://acr-daily.acr-daily-server.workers.dev'
        a.league_events, a.league_kind = [cup(3)], 'cup'
        a._render_leagues()
        from test_inbox import click, find
        with mock.patch('acr_daily.inboxui.webbrowser.open') as web:
            click(find(a.league_rows, 'Cup ›'))
        web.assert_called_once_with('https://acrdaily.com/cup/abcd1234')

    def test_drive_sets_a_match_up_as_any_event(self):
        a = self.a
        ev = h2h(2)
        for s in ev['stages']:
            s['route'] = ROUTE
        a.league_events = [ev]
        a._league_setup_and_launch = mock.Mock()
        with mock.patch('acr_daily.saveslot.game_running', return_value=False):
            a.league_drive(2)
        a._league_setup_and_launch.assert_called_once_with(ev, CAR)


if __name__ == '__main__':
    unittest.main()


class DailyAsSetUp(unittest.TestCase):
    """A daily or a time trial stage: the save with its result checked against the one-stage Rally Weekend DRIVE wrote
    (leagues.daily_changed), as ACRK's challenges check weather, hour, track conditions and rules."""
    STAGE, CAR_ID = 'WelesS4HafrenSouthFullForward', 'HyundaiI20NRally2'

    def item(self, **k):
        return dict({'stageId': self.STAGE, 'weather': 'WT_LIGHT_RAIN', 'start': 43200, 'rules': None}, **k)

    def save(self, weather='WT_LIGHT_RAIN', start=43200, rules=None):
        return rw.apply_weekend(fake_save([(0, self.STAGE, 43200, 'ServiceParkDefault')]), self.STAGE, self.CAR_ID,
                                start, weather, rules)

    def block(self, b):
        """The offset of the stage's weather block in save b."""
        w = rw.read_weekend(b)
        o = saveslot._fstring_at(b, w['data'] + rw.HEADER)[1] + 4 + 4
        return saveslot._fstring_at(b, o)[1]

    def test_as_drive_wrote_it(self):
        self.assertEqual(leagues.daily_changed(rw.read_weekend(self.save()), self.item()), [])

    def test_each_thing_the_menu_can_change(self):
        self.assertEqual(leagues.daily_changed(rw.read_weekend(self.save(weather='WT_STORM')), self.item()), ['weather'])
        self.assertEqual(leagues.daily_changed(rw.read_weekend(self.save(start=64800)), self.item()), ['start times'])
        self.assertEqual(leagues.daily_changed(rw.read_weekend(self.save(rules={'damage': False})), self.item()), ['damage'])
        for at, value, what in ((rw.W_GRIP, 2, 'track conditions'), (rw.W_ACCEL, 3, 'time speed')):
            b = bytearray(self.save())
            b[self.block(bytes(b)) + at] = value
            self.assertEqual(leagues.daily_changed(rw.read_weekend(bytes(b)), self.item()), [what])
        b = bytearray(self.save())
        struct.pack_into('<f', b, self.block(bytes(b)) + rw.W_WET, 0.9)            # the track soaked by hand
        self.assertEqual(leagues.daily_changed(rw.read_weekend(bytes(b)), self.item()), ['track conditions'])

    def test_a_run_from_before_says_nothing(self):
        self.assertEqual(leagues.daily_changed(rw.read_weekend(self.save(weather='WT_STORM')), {'stageId': self.STAGE}), [])
