"""Live ghost cars: the relay (live/relay.py) and the app's link to it (acr_daily/livelink.py), on this PC."""
import asyncio
import os
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


class Driver(unittest.TestCase):
    def test_where_they_are_now(self):
        d = livelink.LiveDriver(1, 'A', 'Car', 7)
        now = 1000.0
        # they started 30 s ago, along +z at 20 m/s; their samples so far reach 29.8 s
        d.add([[ms, 0.0, 0.0, ms / 50.0, 0.0, 0.0, 0.0] for ms in range(0, 29801, 100)], now - 0.2)
        p = d.pose(now)
        self.assertAlmostEqual(p[2], 600.0 - 20 * livelink.DELAY_MS / 1000.0, delta=1.0)   # carried on at their speed
        ahead = d.ahead_s(0.0, 400.0, now)
        self.assertAlmostEqual(ahead, 10.0, delta=0.2)                     # they were here 10 s ago
        self.assertIsNone(d.ahead_s(0.0, 900.0, now))                      # not been there yet
        self.assertIsNone(d.ahead_s(300.0, 400.0, now))                    # nowhere near their road

    def test_never_far_past_the_last_sample(self):
        d = livelink.LiveDriver(1, 'A', 'Car', 7)
        d.add([[0, 0, 0, 0, 0, 0, 0], [100, 0, 0, 2, 0, 0, 0]], 50.0)
        later = d.pose(50.0 + 10)                                          # nothing heard for 10 s
        self.assertLessEqual(later[2], 2 + 2 * livelink.AHEAD_MS / 100.0 + 1e-6)


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
            self.assertAlmostEqual(d.pose(time.monotonic())[2], (time.monotonic() - t0) * 20, delta=4.0)
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
