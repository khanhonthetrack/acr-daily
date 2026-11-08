"""The LIVE page's cars (glide.py): along the route, played back late and steadily. The same cases as the website's
(server/test/glide.test.mjs), of which glide.py is a port."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily.glide import LivePlayback, RouteTrack  # noqa: E402

# a driver whose app sends every 5 s; the page asks every 3 s and plays back 9 s late
SEND, DELAY, GAP = 5000, 9000, 15000


def drv(t, p, state='live'):
    return {'steamId': '7', 'progress': p, 'state': state, 'updated': t}


class Route(unittest.TestCase):
    def test_a_point_along_the_route_follows_the_road_round_a_corner_by_distance(self):
        trk = RouteTrack([[0, 0], [100, 0], [100, 100]])        # 100 m east, then 100 m north
        self.assertEqual(trk.len, 200)
        self.assertEqual(trk.at(0), (0, 0))
        self.assertEqual(trk.at(1), (100, 100))
        self.assertEqual(trk.at(0.5), (100, 0))                  # halfway is the corner, not across it
        self.assertEqual(trk.at(0.75), (100, 50))
        self.assertEqual(trk.at(-1), (0, 0))
        self.assertEqual(trk.at(2), (100, 100))
        self.assertIsNone(RouteTrack([]).at(0.5))
        self.assertEqual(RouteTrack([[3, 4]]).at(0.5), (3, 4))


class Playback(unittest.TestCase):
    def test_between_two_updates_the_car_moves_steadily_however_the_checks_fall(self):
        pb = LivePlayback(DELAY, GAP)
        ahead, seen, sent = 1000, [], []                         # the server's clock 1 s ahead of this computer's
        for now in range(0, 40001, 100):                         # the driver at 2 % every second (10 % per update)
            srv = now + ahead
            if srv % SEND == 0:
                sent = [drv(srv, srv / 50000)]
            if now % 3000 == 0:
                pb.feed(sent, srv, now)
            st = pb.at('7', now)
            if now >= 20000 and st:
                seen.append(st['p'])
            if now == 30000:
                self.assertAlmostEqual(st['p'], (30000 + ahead - DELAY) / 50000)   # DELAY behind the server
        self.assertEqual(len(seen), 201)
        for a, b in zip(seen, seen[1:]):
            self.assertAlmostEqual(b - a, 0.002, delta=1e-9)     # 100 ms = 0.2 %: never a stop or a jump

    def test_before_its_first_update_is_due_the_car_waits_where_it_was_first_seen(self):
        pb = LivePlayback(DELAY, GAP)
        pb.feed([drv(50000, 0.4)], 50000, 50000)
        self.assertEqual(pb.at('7', 50000), {'p': 0.4, 'state': 'live'})
        self.assertIsNone(pb.at('8', 50000))

    def test_a_finish_shows_when_the_car_gets_there_not_before(self):
        pb = LivePlayback(DELAY, GAP)
        pb.feed([drv(0, 0.9)], 0, 0)
        pb.feed([drv(5000, 1, 'finished')], 5000, 5000)
        self.assertEqual(pb.at('7', 11500)['state'], 'live')     # playing 2.5 s: on its way
        self.assertAlmostEqual(pb.at('7', 11500)['p'], 0.95)
        self.assertEqual(pb.at('7', 14000), {'p': 1, 'state': 'finished'})

    def test_back_along_the_route_or_a_long_silence_is_a_jump_never_a_drive_between(self):
        pb = LivePlayback(DELAY, GAP)
        pb.feed([drv(0, 0.6)], 0, 0)
        pb.feed([drv(5000, 0.05)], 5000, 5000)
        self.assertAlmostEqual(pb.at('7', 9000 + 4000)['p'], 0.6)    # waits...
        self.assertAlmostEqual(pb.at('7', 9000 + 5000)['p'], 0.05)   # ...then is at the new run's place
        pb2 = LivePlayback(DELAY, GAP)
        pb2.feed([drv(0, 0.2)], 0, 0)
        pb2.feed([drv(60000, 0.8)], 60000, 60000)
        self.assertAlmostEqual(pb2.at('7', 9000 + 30000)['p'], 0.2)
        self.assertAlmostEqual(pb2.at('7', 9000 + 60000)['p'], 0.8)

    def test_a_driver_off_the_list_stays_until_all_their_updates_are_shown(self):
        pb = LivePlayback(DELAY, GAP)
        pb.feed([drv(0, 0.1)], 0, 0)
        pb.feed([drv(5000, 0.2)], 5000, 5000)
        pb.feed([], 6000, 6000)                                  # dropped by the server
        self.assertAlmostEqual(pb.at('7', 11500)['p'], 0.15)     # still driven to its last place...
        self.assertTrue(pb.at('7', 13900))
        self.assertIsNone(pb.at('7', 14001))                     # ...then gone
        self.assertIsNone(pb.at('7', 0))                         # for good
        pb.feed([drv(20000, 0.3)], 20000, 20000)                 # back on the list: shown again
        self.assertTrue(pb.at('7', 20000))

    def test_a_slow_answer_does_not_set_the_cars_back(self):
        pb = LivePlayback(DELAY, GAP)
        pb.feed([drv(0, 0.1)], 0, 0)
        pb.feed([drv(5000, 0.2)], 5000, 5000)
        before = pb.at('7', 12000)['p']
        pb.feed([drv(5000, 0.2)], 6000, 8000)                    # took 2 s to come back: the clock is not moved back
        self.assertAlmostEqual(pb.at('7', 12000)['p'], before)
        pb.feed([drv(5000, 0.2)], 3600000, 9000)                 # this computer's clock was an hour out: taken afresh
        self.assertAlmostEqual(pb.at('7', 9000)['p'], 0.2)


if __name__ == '__main__':
    unittest.main()
