"""eventroom.py: each event's drivers in a room of their own on the live relay (the user, 26 Nov 2026: free practice on
the daily's stage put the practising driver among the daily's, and in WATCH's list)."""
import re
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from acr_daily import eventroom, watch

RELAY_KEEPS = re.compile(r'^[a-z0-9:_-]{1,40}$')      # (live/relay.py room_of: what it leaves of a tag)


def judge(state):
    return NS(state=state)


def app(here=True, target='daily', **kw):
    a = NS(set_up_here=lambda: here, drive_target=target, league_run=None, dailies={}, active=1, tt={}, tt_active=None)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


DAILY = {1: {'ch': {'id': '2026-11-26/1', 'date': '2026-11-26'}, 'judge': judge('idle')},
         2: {'ch': {'id': '2026-11-26/2', 'date': '2026-11-26'}, 'judge': judge('idle')}}
TT = {3: {'ch': {'id': 'tt:2026-W48/3'}, 'judge': judge('idle')}}


class Tags(unittest.TestCase):
    def test_what_the_relay_keeps(self):
        for t in (eventroom.for_challenge('daily', {'id': '2026-11-26/1'}), eventroom.for_challenge('tt', {'id': 'tt:W/3'}),
                  eventroom.for_event({'id': 17}), eventroom.for_event({'eventId': 17}), eventroom.FREE,
                  eventroom.tag('daily', 'X' * 200)):
            self.assertRegex(t, RELAY_KEEPS)
        self.assertEqual(eventroom.for_challenge('daily', {'id': '2026-11-26/1'}), 'daily:2026-11-26-1')
        self.assertEqual(eventroom.for_event({'id': 17}), 'ev:17')
        self.assertEqual(eventroom.for_event({'eventId': 17, 'kind': 'cup'}), 'ev:17')
        self.assertIsNone(eventroom.for_challenge('daily', {}))
        self.assertLessEqual(len(eventroom.tag('daily', 'x' * 200)), eventroom.MAX_LEN)


class Sender(unittest.TestCase):
    def test_the_daily_the_app_took_the_game_to(self):
        self.assertEqual(eventroom.of(app(dailies=DAILY, active=2)), 'daily:2026-11-26-2')

    def test_a_running_daily_is_its_own_slot(self):
        d = {1: dict(DAILY[1]), 2: dict(DAILY[2], judge=judge('running'))}
        self.assertEqual(eventroom.of(app(dailies=d, active=1)), 'daily:2026-11-26-2')

    def test_free_practice_set_up_by_hand_is_not_the_daily(self):
        # the same stage, the game taken there by hand (set_up_here False): not in the daily's room
        d = {1: dict(DAILY[1], judge=judge('running'))}
        self.assertEqual(eventroom.of(app(here=False, dailies=d)), eventroom.FREE)

    def test_a_run_that_does_not_count_is_free(self):
        d = {1: dict(DAILY[1], judge=judge('running'), norally=True)}
        self.assertEqual(eventroom.of(app(here=True, dailies=d)), eventroom.FREE)

    def test_no_mod_to_tell_by_the_run_decides(self):
        self.assertEqual(eventroom.of(app(here=None, dailies=DAILY)), eventroom.FREE)       # (not started: nothing to go by)
        d = {1: dict(DAILY[1], judge=judge('running'))}
        self.assertEqual(eventroom.of(app(here=None, dailies=d)), 'daily:2026-11-26-1')

    def test_a_time_trial_is_not_the_daily(self):
        self.assertEqual(eventroom.of(app(target='tt', dailies=DAILY, tt=TT, tt_active=3)), 'tt:tt-2026-w48-3')
        self.assertNotEqual(eventroom.of(app(target='tt', dailies=DAILY, tt=TT, tt_active=3)),
                            eventroom.of(app(dailies=DAILY)))

    def test_a_league_event_has_its_own(self):
        run = {'ev': {'id': 17, 'kind': 'cup'}, 'judge': judge('idle'), 'over': False}
        self.assertEqual(eventroom.of(app(target='league', league_run=run, dailies=DAILY)), 'ev:17')
        # (followed, but the game is on a stage of the driver's own: free)
        self.assertEqual(eventroom.of(app(here=False, target='league', league_run=run)), eventroom.FREE)
        # (the event over: back to the daily's)
        run['over'] = True
        self.assertEqual(eventroom.of(app(target='league', league_run=run, dailies=DAILY)), 'daily:2026-11-26-1')

    def test_nothing_set_up_is_free(self):
        self.assertEqual(eventroom.of(app(here=None)), eventroom.FREE)
        self.assertEqual(eventroom.of(NS(set_up_here=lambda: 1 / 0)), eventroom.FREE)


class Watcher(unittest.TestCase):
    def test_watching_a_daily_is_its_room(self):
        a = mock.Mock()
        a.dailies = DAILY
        w = watch.Watch(a)
        self.assertIsNone(w.room())                      # (not watching)
        w.start('daily', 1)
        self.assertEqual(w.room(), eventroom.of(app(dailies=DAILY, active=1)))   # (the drivers' own)

    def test_watching_a_time_trial_and_an_event(self):
        a = mock.Mock()
        a.dailies, a.tt = DAILY, TT
        w = watch.Watch(a)
        w.start('tt', 3)
        self.assertEqual(w.room(), eventroom.of(app(target='tt', tt=TT, tt_active=3)))
        w.start('event', 1, event={'eventId': 17, 'kind': 'cup', 'ch': {}})
        run = {'ev': {'id': 17}, 'judge': judge('idle'), 'over': False}
        self.assertEqual(w.room(), eventroom.of(app(target='league', league_run=run)))

    def test_ranked_and_crews_keep_theirs(self):
        w = watch.Watch(mock.Mock())
        w.start('event', 2, event={'eventId': 9, 'kind': 'live', 'ch': {}})
        self.assertEqual(w.room(), 'live:9')
        w.start('event', 1, event={'eventId': 4, 'kind': 'copilot', 'ch': {}})
        self.assertEqual(w.room(), 'cp:4')


if __name__ == '__main__':
    unittest.main()
