"""Live ghost cars: the relay (live/relay.py) and the app's link to it (acr_daily/livelink.py), on this PC."""
import asyncio
import math
import os
import random
import socket
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'live'))
from acr_daily import livelink  # noqa: E402
from acr_daily.telemetry import Frame  # noqa: E402
import relay  # noqa: E402

TRACK = 'Monte Carlo St. Geniez - Mézien'


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def frame(clock, x, z, track=TRACK, car='Skoda Fabia RS Rally2'):
    return Frame(time.monotonic(), 0, clock, x, z, 80.0, car, track, y=100.0, heading=0.0)


def wait(cond, timeout=5.0):
    t = time.time()
    while time.time() - t < timeout:
        if cond():
            return True
        time.sleep(0.02)
    return False


def circle_run(seconds=12.0, every_ms=50, speed=30.0, radius=60.0):
    """A driver going round a circle (radius m) at speed m/s, its samples [clockMs, x, y, z, heading, pitch, roll]
    every every_ms; and the truth: where it is at a clock ms."""
    w = speed / radius

    def at(ms):
        a = w * ms / 1000.0
        return (radius * math.sin(a), 0.0, radius - radius * math.cos(a), -a)    # (heading: the way it drives)
    samples = []
    for ms in range(0, int(seconds * 1000) + 1, every_ms):
        x, y, z, h = at(ms)
        samples.append([ms, x, y, z, math.atan2(math.sin(h), math.cos(h)), 0.0, 0.0])
    return samples, at


def play(d, samples, send_s, frames_hz=144, seconds=10.0, late=(0.02, 0.09), seed=1):
    """Samples sent every send_s (as livelink does), each batch arriving 20 to 90 ms late at random; the driver drawn
    at frames_hz. -> [(now, pose, rate, their clock drawn)] once the playback has settled (after 2 s)."""
    rnd = random.Random(seed)
    batches, sent = [], 0
    t = send_s
    while sent < len(samples):
        upto = [s for s in samples[sent:] if s[0] <= t * 1000.0]
        if upto:
            batches.append((t + rnd.uniform(*late), upto))
            sent += len(upto)
        t += send_s
    batches.sort(key=lambda b: b[0])
    out, b = [], 0
    for i in range(int(seconds * frames_hz)):
        now = i / float(frames_hz)
        while b < len(batches) and batches[b][0] <= now:
            d.add(batches[b][1], batches[b][0])
            b += 1
        m = d.motion(now)
        if m and now > 2.0:
            out.append((now, m[0], m[1], d.play_ms))
    return out


class Driver(unittest.TestCase):
    def test_where_they_are_now(self):
        d = livelink.LiveDriver(1, 'A', 'Car', 7)
        now = 1000.0
        # they started 30 s ago, along +z at 20 m/s; their samples so far reach 29.8 s
        d.add([[ms, 0.0, 0.0, ms / 50.0, 0.0, 0.0, 0.0] for ms in range(0, 29801, 100)], now - 0.2)
        p = d.pose(now)
        self.assertAlmostEqual(p[2], 600.0 - 20 * d.delay_ms() / 1000.0, delta=1.0)   # played back a little behind
        ahead = d.ahead_s(0.0, 400.0, now)
        self.assertAlmostEqual(ahead, 10.0, delta=0.2)                     # they were here 10 s ago
        self.assertIsNone(d.ahead_s(0.0, 900.0, now))                      # not been there yet
        self.assertIsNone(d.ahead_s(300.0, 400.0, now))                    # nowhere near their road

    def test_never_far_past_the_last_sample(self):
        d = livelink.LiveDriver(1, 'A', 'Car', 7)
        d.add([[0, 0, 0, 0, 0, 0, 0], [100, 0, 0, 2, 0, 0, 0]], 50.0)
        later = d.pose(50.0 + 10)                                          # nothing heard for 10 s
        self.assertLessEqual(later[2], 2 + 2 * livelink.AHEAD_MS / 100.0 + 1e-6)

    def test_smooth_between_late_samples(self):
        """As this app sends (20 a second, 10 batches a second) and as 0.0.29 and before did (10, in 5): drawn at 144
        frames a second, the car is where it really was, and its speed never jumps from one frame to the next."""
        for every_ms, send_s in ((50, 0.1), (100, 0.2)):
            samples, truth = circle_run(every_ms=every_ms)
            d = livelink.LiveDriver(1, 'A', 'Car', 7)
            frames = play(d, samples, send_s)
            self.assertGreater(len(frames), 1000)
            off = []                                   # how far from where it really was at the clock drawn (m)
            for _now, p, _r, played in frames:
                c = truth(played)
                off.append(math.dist((p[0], p[2]), (c[0], c[2])))
            self.assertLess(max(off), 0.15 if every_ms == 50 else 0.6, (every_ms, max(off)))
            speeds = [math.dist((a[1][0], a[1][2]), (b[1][0], b[1][2])) / (b[0] - a[0]) for a, b in zip(frames, frames[1:])]
            self.assertLess(max(abs(v - 30.0) for v in speeds), 30.0 * 0.12, every_ms)     # (8 % warp at most + curve)
            self.assertTrue(all(b[3] >= a[3] for a, b in zip(frames, frames[1:])))
            for _now, p, r, _played in frames:         # the rate given for the mod: the car's speed
                self.assertAlmostEqual(math.hypot(r[0], r[2]), 30.0, delta=3.0)
            # as little behind as their samples allow: a batch's gap + a sample's + how unevenly they come (here up to
            # 70 ms) + the margin (sent every 0.1 s: under 0.3 s; every 0.2 s: more)
            self.assertLess(d.delay_ms(), 300 if every_ms == 50 else 450, every_ms)

    def test_the_playback_clock_never_runs_backwards(self):
        d = livelink.LiveDriver(1, 'A', 'Car', 7)
        samples, _truth = circle_run(seconds=6.0)
        clocks = []
        for i, now in enumerate(x / 100.0 for x in range(0, 600)):
            sent = [s for s in samples if (i - 1) * 10 < s[0] <= i * 10]
            if sent:
                d.add(sent, now + (0.6 if 200 <= i < 210 else 0.03))   # (a batch held up 0.6 s: they come later)
            if d.motion(now):
                clocks.append(d.play_ms)
        self.assertTrue(all(b >= a for a, b in zip(clocks, clocks[1:])))

    def test_a_reset_is_a_jump_not_a_swing(self):
        """Put back on the road 200 m away: no curve through thin air on the way."""
        s = [[ms, 0.0, 0.0, ms / 50.0, 0.0, 0.0, 0.0] for ms in range(0, 1001, 50)]
        s += [[ms, 200.0, 0.0, 20.0 + (ms - 1050) / 50.0, 0.0, 0.0, 0.0] for ms in range(1050, 2001, 50)]
        for ms in range(0, 2001, 5):
            p, _r = livelink.smooth_at(s, ms)
            self.assertLess(min(abs(p[0]), abs(p[0] - 200.0)), 1e-6, (ms, p))

    def test_the_heading_goes_round_smoothly(self):
        """Through the half turn where the heading goes from +180 to -180 degrees: no spin."""
        s = [[ms, 0.0, 0.0, 0.0, math.atan2(math.sin(3.0 + ms / 1000.0), math.cos(3.0 + ms / 1000.0)), 0.0, 0.0]
             for ms in range(0, 501, 50)]
        last = None
        for ms in range(5, 501, 5):                       # (from just after the first sample: no turn rate before it)
            p, r = livelink.smooth_at(s, ms)
            h = p[3]
            if last is not None:
                self.assertLess(abs(math.remainder(h - last, 2 * math.pi)), 0.01)
            self.assertAlmostEqual(r[3], 1.0, delta=0.05)                 # turning at 1 radian a second
            last = h


KEY = bytes(range(32))


def make_ticket(sid, name, exp_ms=None, key=KEY):
    """As the ACR Daily server makes them (server/src/livetickets.js)."""
    import base64
    import hashlib
    import hmac
    import json
    exp_ms = time.time() * 1000 + 3600e3 if exp_ms is None else exp_ms
    payload = base64.urlsafe_b64encode(json.dumps({'k': 'live', 's': sid, 'n': name, 'e': exp_ms}).encode()).decode().rstrip('=')
    sig = base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()).decode().rstrip('=')
    return payload + '.' + sig


class Relay(unittest.TestCase):
    KEY = None

    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.loop = asyncio.new_event_loop()
        started = threading.Event()

        def run():
            asyncio.set_event_loop(cls.loop)

            async def go():
                cls.server = await asyncio.start_server(relay.Relay(cls.KEY).handle, '127.0.0.1', cls.port)
                started.set()
            cls.loop.run_until_complete(go())
            cls.loop.run_forever()
        threading.Thread(target=run, daemon=True).start()
        started.wait(5)
        cls.url = 'ws://127.0.0.1:%d/live' % cls.port

    @classmethod
    def tearDownClass(cls):
        async def stop():
            cls.server.close()
            await cls.server.wait_closed()
            for t in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                t.cancel()
        asyncio.run_coroutine_threadsafe(stop(), cls.loop).result(5)
        cls.loop.call_soon_threadsafe(cls.loop.stop)

    def test_health(self):
        import urllib.request
        body = urllib.request.urlopen('http://127.0.0.1:%d/' % self.port, timeout=5).read().decode()
        self.assertIn('live relay', body)

    def test_the_others_on_your_stage_and_nobody_else(self):
        a = livelink.LiveLink(self.url, 'Alice')
        b = livelink.LiveLink(self.url, 'Bob')
        c = livelink.LiveLink(self.url, 'Carol')
        try:
            self.assertTrue(wait(lambda: a.state == b.state == c.state == 'live'))
            a.root = (-0.13, -0.57)
            b.feed(frame(0, 0, 0))                                   # Bob: on the start line of the same stage
            c.feed(frame(0, 0, 0, track='Wales Afon Bidno'))         # Carol: another stage
            time.sleep(0.3)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 1.0:                             # Alice drives along +z
                ms = int((time.monotonic() - t0) * 1000) + 1
                a.feed(frame(ms, 0.0, ms / 50.0))
                b.feed(frame(0, 0, 0))
                c.feed(frame(0, 0, 0, track='Wales Afon Bidno'))
                time.sleep(0.02)
            self.assertTrue(wait(lambda: len(b.others()) == 1))
            d = b.others()[0]
            self.assertEqual((d.name, d.car), ('Alice', 'Skoda Fabia RS Rally2'))
            self.assertEqual(d.root, (-0.13, -0.57))                        # where her car's model sits
            self.assertGreater(d.run, 0)                                    # (her run: numbered by her link)
            self.assertGreater(len(d.trace.s), 5)
            self.assertAlmostEqual(d.pose(time.monotonic())[2], (time.monotonic() - t0 - d.delay_ms() / 1000.0) * 20,
                                   delta=4.0)                               # (played back a little behind)
            self.assertEqual(c.others(), [])                                # another stage hears nothing
            self.assertEqual(a.others(), [])                                # nor does she hear herself
            a.feed(frame(0, 0, 0, track=''))                          # Alice leaves the stage
            self.assertTrue(wait(lambda: b.others() == []))
        finally:
            for x in (a, b, c):
                x.close()

    def test_two_stages_of_the_same_name(self):
        """The game calls both Forêt de Munster and Forêt de Saverne "Alsace Forêt": told apart by where they start."""
        foret = 'Alsace Forêt'
        a = livelink.LiveLink(self.url, 'Munster driver')
        b = livelink.LiveLink(self.url, 'Saverne driver')
        c = livelink.LiveLink(self.url, 'Munster, waiting')
        try:
            self.assertTrue(wait(lambda: a.state == b.state == c.state == 'live'))
            a.feed(frame(0, 0.0, 0.0, track=foret))                      # on their start lines (clock at 0)
            b.feed(frame(0, 20000.0, 5000.0, track=foret))
            c.feed(frame(0, 250.0, -120.0, track=foret))                 # (the time control, 280 m before Munster's)
            time.sleep(0.3)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 1.0:
                ms = int((time.monotonic() - t0) * 1000) + 1
                a.feed(frame(ms, 0.0, ms / 50.0, track=foret))
                b.feed(frame(ms, 20000.0, 5000.0 + ms / 50.0, track=foret))
                c.feed(frame(0, 250.0, -120.0, track=foret))
                time.sleep(0.02)
            self.assertTrue(wait(lambda: len(c.others()) == 1))
            self.assertEqual(c.others()[0].name, 'Munster driver')       # the one on its stage, not the other Forêt
            self.assertEqual([d.name for d in b.others()], [])
            self.assertEqual([d.name for d in a.others()], [])
        finally:
            for x in (a, b, c):
                x.close()

    def test_bad_messages_are_dropped(self):
        ws = livelink.WebSocket(self.url)
        try:
            self.assertIn('welcome', ws.recv())
            ws.send('not json')
            ws.send('{"t": "s", "track": "x", "s": [[1, 2]]}')             # before hello / a bad sample
            ws.send('{"t": "hello", "name": "%s"}' % ('N' * 200))
            ws.send('{"t": "s", "track": "x", "s": [[1, 2, 3]]}')
        finally:
            ws.close()


class CheckedNames(Relay):
    """The relay as it runs for everyone: only drivers with the server's ticket, under the ticket's name."""
    KEY = KEY

    def test_health(self):
        pass

    def test_bad_messages_are_dropped(self):
        pass

    def test_the_others_on_your_stage_and_nobody_else(self):
        pass

    def test_two_stages_of_the_same_name(self):
        pass

    def test_tickets(self):
        t = time.time() * 1000
        self.assertEqual(relay.read_ticket(KEY, make_ticket('7656', 'Ana'))['n'], 'Ana')
        self.assertIsNone(relay.read_ticket(KEY, make_ticket('7656', 'Ana', exp_ms=t - 1)))         # out of date
        self.assertIsNone(relay.read_ticket(KEY, make_ticket('7656', 'Ana', key=bytes(32))))        # another key
        good = make_ticket('7656', 'Ana')
        forged = make_ticket('1111', 'Mallory', key=bytes(32)).split('.')[0] + '.' + good.split('.')[1]
        self.assertIsNone(relay.read_ticket(KEY, forged))                                           # changed
        for bad in ('', 'x', good + '.x', None):
            self.assertIsNone(relay.read_ticket(KEY, bad))

    def test_no_ticket_no_entry(self):
        ws = livelink.WebSocket(self.url)
        try:
            self.assertIn('welcome', ws.recv())
            ws.send('{"t": "hello", "name": "Somebody Else"}')
            self.assertIn('"ticket"', ws.recv())
            with self.assertRaises(ConnectionError):
                ws.recv()
        finally:
            ws.close()
        link = livelink.LiveLink(self.url, 'Nobody', ticket=lambda: None)              # not signed in to the app
        try:
            self.assertTrue(wait(lambda: link.state == 'signin'))
        finally:
            link.close()

    def test_the_tickets_name_and_one_connection_a_driver(self):
        tk = lambda sid, name: (lambda: {'ticket': make_ticket(sid, name), 'name': name, 'expires': time.time() * 1000 + 3600e3})
        a = livelink.LiveLink(self.url, 'I am Bob really', ticket=tk('76561198000000001', 'Alice'))
        b = livelink.LiveLink(self.url, 'Bob', ticket=tk('76561198000000002', 'Bob'))
        a2 = None
        try:
            self.assertTrue(wait(lambda: a.state == b.state == 'live'))
            b.feed(frame(0, 0, 0))
            time.sleep(0.3)
            for ms in range(1, 600, 20):
                a.feed(frame(ms, 0.0, ms / 50.0))
                time.sleep(0.02)
            self.assertTrue(wait(lambda: len(b.others()) == 1))
            d = b.others()[0]
            self.assertEqual((d.name, d.sid), ('Alice', '76561198000000001'))   # the ticket's name, not the one it said
            a2 = livelink.LiveLink(self.url, 'Alice', ticket=tk('76561198000000001', 'Alice'))   # Alice again
            self.assertTrue(wait(lambda: a2.state == 'live'))
            self.assertTrue(wait(lambda: a.state != 'live'))                      # her first connection is closed
        finally:
            for x in (a, b, a2):
                if x:
                    x.close()


if __name__ == '__main__':
    unittest.main()
