"""Tests for the hardened 3-node multi-region live relay mesh (EU <-> UK <-> JP)."""
import asyncio
import json
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

KEY = bytes(range(32))
TRACK = 'Monte Carlo St. Geniez - Mézien'


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait(cond, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def frame(clock, x, z, track=TRACK, car='Skoda Fabia RS Rally2', speed=120.0, gear=4, rpm=6500):
    f = Frame(time.monotonic(), 0, clock, x, z, speed, car, track, y=100.0, heading=0.1)
    f.gear, f.rpm, f.gas, f.brake, f.steer = gear, rpm, 0.85, 0.0, -0.1
    return f


def make_ticket(sid, name, exp_ms=None, key=KEY):
    import base64
    import hashlib
    import hmac
    exp_ms = time.time() * 1000 + 3600e3 if exp_ms is None else exp_ms
    payload = base64.urlsafe_b64encode(json.dumps({'k': 'live', 's': sid, 'n': name, 'e': exp_ms}).encode()).decode().rstrip('=')
    sig = base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()).decode().rstrip('=')
    return payload + '.' + sig


def tk_fn(sid, name):
    return lambda: {'ticket': make_ticket(sid, name), 'name': name, 'expires': time.time() * 1000 + 3600e3}


class RelayMeshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ports = {1: free_port(), 2: free_port(), 3: free_port()}
        cls.peer_ports = {1: free_port(), 2: free_port(), 3: free_port()}
        cls.urls = {nid: 'ws://127.0.0.1:%d/live' % p for nid, p in cls.ports.items()}
        cls.peer_urls = {nid: 'ws://127.0.0.1:%d/live' % p for nid, p in cls.peer_ports.items()}
        cls.loop = asyncio.new_event_loop()
        cls.relays = {}
        cls.servers = []
        started = threading.Event()

        def run():
            asyncio.set_event_loop(cls.loop)

            async def go():
                for nid in (1, 2, 3):
                    peers = [u for other, u in cls.peer_urls.items() if other != nid]
                    r = relay.Relay(KEY, node_id=nid, peers=peers, separate_peer_port=True)
                    cls.relays[nid] = r
                    cls.servers.append(await asyncio.start_server(r.handle, '127.0.0.1', cls.ports[nid]))
                    cls.servers.append(await asyncio.start_server(r.handle_peer, '127.0.0.1', cls.peer_ports[nid]))
                for r in cls.relays.values():
                    r.start_peers()
                started.set()

            cls.loop.run_until_complete(go())
            cls.loop.run_forever()

        threading.Thread(target=run, daemon=True).start()
        started.wait(5)
        assert wait(lambda: all(all(p.connected for p in r.peer_outs) for r in cls.relays.values()), timeout=5.0)

    @classmethod
    def tearDownClass(cls):
        async def stop():
            for r in cls.relays.values():
                r.stop_peers()
            for s in cls.servers:
                s.close()
                await s.wait_closed()
            for t in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                t.cancel()

        asyncio.run_coroutine_threadsafe(stop(), cls.loop).result(5)
        cls.loop.call_soon_threadsafe(cls.loop.stop)

    def test_cross_region_eu_uk_jp_ghosts_dash_and_follow(self):
        eu = livelink.LiveLink(self.urls[1], 'Piotr', ticket=tk_fn('76561198000000101', 'Piotr'))
        uk = livelink.LiveLink(self.urls[2], 'Callum', ticket=tk_fn('76561198000000102', 'Callum'))
        jp = livelink.LiveLink(self.urls[3], 'Takumi', ticket=tk_fn('76561198000000103', 'Takumi'))
        try:
            self.assertTrue(wait(lambda: eu.state == uk.state == jp.state == 'live'))
            # Globally unique node-prefixed IDs (node_id * 10_000_000 + offset)
            self.assertEqual(eu.my_id // 10_000_000, 1)
            self.assertEqual(uk.my_id // 10_000_000, 2)
            self.assertEqual(jp.my_id // 10_000_000, 3)

            eu.spectating = True
            uk.spectating = True
            eu.feed(frame(0, 0.0, 0.0))
            uk.feed(frame(0, 0.0, 0.0))
            jp.feed(frame(0, 0.0, 0.0))
            jp.set_livery('Castrol', 42)
            jp.root = (-0.13, -0.57)
            time.sleep(0.25)

            # Takumi in JP is 2500 m into the same stage (> NEAR_M = 600 m), while EU follows Takumi in WATCH mode
            eu.set_follow(jp.my_id)
            time.sleep(0.15)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 1.2:
                ms = 50_000 + int((time.monotonic() - t0) * 1000) + 1
                jp.feed(frame(ms, 0.0, 2500.0 + (ms - 50_000) / 50.0))
                eu.feed(frame(0, 0.0, 0.0))
                uk.feed(frame(0, 0.0, 0.0))
                time.sleep(0.02)

            self.assertTrue(wait(lambda: len(eu.others()) == 1 and len(uk.others()) == 1))
            d_eu = eu.others()[0]
            self.assertEqual((d_eu.id, d_eu.name, d_eu.sid), (jp.my_id, 'Takumi', '76561198000000103'))
            self.assertEqual((d_eu.livery, d_eu.livery_id, d_eu.root), ('Castrol', 42, (-0.13, -0.57)))
            self.assertGreater(len(d_eu.trace.s), 15)
            self.assertTrue(getattr(d_eu, 'dash', None))

            jp.feed(frame(0, 0.0, 0.0, track=''))
            self.assertTrue(wait(lambda: eu.others() == [] and uk.others() == []))
        finally:
            for x in (eu, uk, jp):
                x.close()

    def test_cross_region_room_isolation_and_same_driver_reconnect(self):
        uk_sess = livelink.LiveLink(self.urls[2], 'UK Ranked', ticket=tk_fn('76561198000000201', 'UK Ranked'))
        jp_sess = livelink.LiveLink(self.urls[3], 'JP Ranked', ticket=tk_fn('76561198000000202', 'JP Ranked'))
        eu_daily = livelink.LiveLink(self.urls[1], 'EU Daily', ticket=tk_fn('76561198000000203', 'EU Daily'))
        eu_reconn = None
        try:
            self.assertTrue(wait(lambda: uk_sess.state == jp_sess.state == eu_daily.state == 'live'))
            uk_sess.room = jp_sess.room = 'live:99'
            uk_sess.feed(frame(0, 0.0, 0.0))
            jp_sess.feed(frame(0, 0.0, 0.0))
            eu_daily.feed(frame(0, 0.0, 0.0))
            time.sleep(0.25)
            for i in range(25):
                jp_sess.feed(frame(1 + i * 25, 0.0, i * 1.0))
                time.sleep(0.02)
            self.assertTrue(wait(lambda: [d.name for d in uk_sess.others()] == ['JP Ranked']))
            self.assertEqual(eu_daily.others(), [])

            # Same Steam ID reconnects on EU -> stale UK connection is closed across the mesh
            eu_reconn = livelink.LiveLink(self.urls[1], 'UK Ranked', ticket=tk_fn('76561198000000201', 'UK Ranked'))
            self.assertTrue(wait(lambda: eu_reconn.state == 'live'))
            self.assertTrue(wait(lambda: uk_sess.state != 'live'))
        finally:
            for x in (uk_sess, jp_sess, eu_daily, eu_reconn):
                if x:
                    x.close()

    def test_cross_region_copilot_crew_voice_relay(self):
        received_jp = []
        received_uk = []
        eu_driver = livelink.LiveLink(self.urls[1], 'DriverEU', ticket=tk_fn('76561198000000401', 'DriverEU'))
        jp_codriver = livelink.LiveLink(self.urls[3], 'CoDriverJP', ticket=tk_fn('76561198000000402', 'CoDriverJP'))
        uk_other = livelink.LiveLink(self.urls[2], 'OtherCrewUK', ticket=tk_fn('76561198000000403', 'OtherCrewUK'))
        jp_codriver.on_crew = lambda sid, b: received_jp.append((sid, b))
        uk_other.on_crew = lambda sid, b: received_uk.append((sid, b))
        try:
            self.assertTrue(wait(lambda: eu_driver.state == jp_codriver.state == uk_other.state == 'live'))
            eu_driver.room = jp_codriver.room = 'cp:lobby777'
            uk_other.room = 'cp:lobby999'
            eu_driver.feed(frame(0, 0.0, 0.0))
            jp_codriver.feed(frame(0, 0.0, 0.0))
            uk_other.feed(frame(0, 0.0, 0.0))
            time.sleep(0.2)
            self.assertTrue(eu_driver.send_crew('left5_over_crest'))
            self.assertTrue(wait(lambda: received_jp == [('76561198000000401', 'left5_over_crest')]))
            self.assertEqual(received_uk, [])
        finally:
            for x in (eu_driver, jp_codriver, uk_other):
                x.close()

    def test_cross_region_casual_4player_menu_and_stage_crew_voice(self):
        eu_host = livelink.LiveLink(self.urls[1], 'EUHost', ticket=tk_fn('76561198000000401', 'EUHost'), watch=False)
        uk_co1 = livelink.LiveLink(self.urls[2], 'UKCo1', ticket=tk_fn('76561198000000402', 'UKCo1'), watch=False)
        jp_co2 = livelink.LiveLink(self.urls[3], 'JPCo2', ticket=tk_fn('76561198000000403', 'JPCo2'), watch=False)
        uk_stranger = livelink.LiveLink(self.urls[2], 'UKStranger', ticket=tk_fn('76561198000000404', 'UKStranger'), watch=False)
        got_eu, got_uk, got_jp, got_stranger = [], [], [], []
        eu_host.on_crew = lambda sid, b: got_eu.append((sid, b))
        uk_co1.on_crew = lambda sid, b: got_uk.append((sid, b))
        jp_co2.on_crew = lambda sid, b: got_jp.append((sid, b))
        uk_stranger.on_crew = lambda sid, b: got_stranger.append((sid, b))
        try:
            self.assertTrue(wait(lambda: (
                eu_host.state == uk_co1.state == jp_co2.state == uk_stranger.state == 'live'
            )))
            # 1. Menu / lobby phase (no stage loaded yet!): crew joins cp:1000042 via set_crew
            eu_host.set_crew('cp:1000042')
            uk_co1.set_crew('cp:1000042')
            jp_co2.set_crew('cp:1000042')
            uk_stranger.set_crew('cp:1000099')
            time.sleep(0.2)

            self.assertTrue(uk_co1.send_crew('v_co1_ready_in_menu'))
            self.assertTrue(wait(lambda: got_eu == [('76561198000000402', 'v_co1_ready_in_menu')]))
            self.assertTrue(wait(lambda: got_jp == [('76561198000000402', 'v_co1_ready_in_menu')]))
            self.assertEqual(got_stranger, [])

            # 2. On-stage phase (both set_crew AND stage room cp:1000042 active): delivered strictly once (no dupes!)
            got_eu.clear()
            got_uk.clear()
            got_jp.clear()
            for lnk in (eu_host, uk_co1, jp_co2):
                lnk.room = 'cp:1000042'
                lnk.feed(frame(1000, 5.0, 5.0))
            time.sleep(0.2)

            self.assertTrue(eu_host.send_crew('v_host_fanout_voice'))
            self.assertTrue(wait(lambda: got_uk == [('76561198000000401', 'v_host_fanout_voice')]))
            self.assertTrue(wait(lambda: got_jp == [('76561198000000401', 'v_host_fanout_voice')]))
            time.sleep(0.15)
            self.assertEqual(len(got_uk), 1)
            self.assertEqual(len(got_jp), 1)
            self.assertEqual(got_stranger, [])
        finally:
            for x in (eu_host, uk_co1, jp_co2, uk_stranger):
                x.close()

    def test_public_port_rejects_peer_hello_and_peer_port_enforces_hmac_and_replay(self):
        # 1. Public player port refuses peer_hello even with valid HMAC!
        ws_pub = livelink.WebSocket(self.urls[1])
        try:
            self.assertIn('welcome', ws_pub.recv())
            ws_pub.send(json.dumps(relay.make_peer_hello(KEY, node_id=7)))
            self.assertIn('peer_port_only', ws_pub.recv())
        finally:
            ws_pub.close()

        # 2. Dedicated peer port rejects wrong HMAC key
        ws_bad = livelink.WebSocket(self.peer_urls[1])
        try:
            self.assertIn('welcome', ws_bad.recv())
            ws_bad.send(json.dumps(relay.make_peer_hello(bytes(32), node_id=9)))
            self.assertIn('peer_auth', ws_bad.recv())
        finally:
            ws_bad.close()

        # 3. Dedicated peer port rejects replayed nonce
        replayed = relay.make_peer_hello(KEY, node_id=8)
        ws1 = livelink.WebSocket(self.peer_urls[1])
        ws2 = livelink.WebSocket(self.peer_urls[1])
        try:
            ws1.recv()
            ws1.send(json.dumps(replayed))
            self.assertIn('peer_welcome', ws1.recv())

            ws2.recv()
            ws2.send(json.dumps(replayed))
            self.assertIn('peer_auth', ws2.recv())
        finally:
            ws1.close()
            ws2.close()

    def test_zero_drop_rollout_drain_bridges_mid_stage_drivers(self):
        import urllib.error
        import urllib.request

        p1, pp1 = free_port(), free_port()
        p2, pp2 = free_port(), free_port()
        v2_peer_url = 'ws://127.0.0.1:%d/live' % pp2
        r1 = relay.Relay(KEY, node_id=11, separate_peer_port=True, drain_peer=v2_peer_url)
        r2 = relay.Relay(KEY, node_id=21, separate_peer_port=True)
        extra_servers = []

        async def boot():
            extra_servers.append(await asyncio.start_server(r1.handle, '127.0.0.1', p1))
            extra_servers.append(await asyncio.start_server(r1.handle_peer, '127.0.0.1', pp1))
            extra_servers.append(await asyncio.start_server(r2.handle, '127.0.0.1', p2))
            extra_servers.append(await asyncio.start_server(r2.handle_peer, '127.0.0.1', pp2))
            r1.start_peers()
            r2.start_peers()

        asyncio.run_coroutine_threadsafe(boot(), self.loop).result(5)
        old_drv = livelink.LiveLink('ws://127.0.0.1:%d/live' % p1, 'MidStageOld',
                                    ticket=tk_fn('76561198000000401', 'MidStageOld'))
        new_drv = None
        try:
            self.assertTrue(wait(lambda: old_drv.state == 'live'))
            old_id = old_drv.my_id
            old_drv.feed(frame(120_000, 10.0, 20.0))
            time.sleep(0.1)

            with urllib.request.urlopen('http://127.0.0.1:%d/readyz' % p1, timeout=2) as resp:
                self.assertEqual(resp.status, 200)

            # Trigger rollout drain on r1 while MidStageOld is mid-stage!
            asyncio.run_coroutine_threadsafe(
                asyncio.coroutine(lambda: r1.begin_drain(settle_s=0.15, timeout_s=8.0))()
                if False else self._start_drain(r1),
                self.loop,
            ).result(3)

            with self.assertRaises(urllib.error.HTTPError) as ctx_err:
                urllib.request.urlopen('http://127.0.0.1:%d/readyz' % p1, timeout=2)
            self.assertEqual(ctx_err.exception.code, 503)
            # Liveness stays 200 OK while draining!
            with urllib.request.urlopen('http://127.0.0.1:%d/healthz' % p1, timeout=2) as resp:
                self.assertEqual(resp.status, 200)

            time.sleep(0.35)
            # Mid-stage driver was NOT disconnected and kept the exact same session ID!
            self.assertEqual(old_drv.state, 'live')
            self.assertEqual(old_drv.my_id, old_id)
            self.assertFalse(r1.drain_done.is_set())

            # A brand-new driver joins the new pod r2 on the same stage -> both see each other across the drain bridge!
            new_drv = livelink.LiveLink('ws://127.0.0.1:%d/live' % p2, 'NewPodDriver',
                                        ticket=tk_fn('76561198000000402', 'NewPodDriver'))
            self.assertTrue(wait(lambda: new_drv.state == 'live'))
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.8:
                ms = 125_000 + int((time.monotonic() - t0) * 1000)
                old_drv.feed(frame(ms, 12.0, 22.0))
                new_drv.feed(frame(ms, 14.0, 24.0))
                time.sleep(0.03)

            self.assertTrue(wait(lambda: len(old_drv.others()) == 1 and len(new_drv.others()) == 1))
            self.assertEqual(old_drv.others()[0].name, 'NewPodDriver')
            self.assertEqual(new_drv.others()[0].name, 'MidStageOld')

            # As soon as MidStageOld crosses the finish line (leaves stage), r1 hands off and finishes draining!
            old_drv.feed(frame(0, 0.0, 0.0, track=''))
            self.assertTrue(wait(lambda: r1.drain_done.is_set(), timeout=2.5))
        finally:
            old_drv.close()
            if new_drv is not None:
                new_drv.close()

            async def clean():
                r1.stop_peers()
                r2.stop_peers()
                for s in extra_servers:
                    s.close()
                    await s.wait_closed()

            asyncio.run_coroutine_threadsafe(clean(), self.loop).result(5)

    @staticmethod
    async def _start_drain(r):
        r.begin_drain(settle_s=0.15, timeout_s=8.0)


if __name__ == '__main__':
    unittest.main()
