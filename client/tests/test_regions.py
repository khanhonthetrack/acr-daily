"""Tests for automatic RTT best-region selection, mid-stage stability, and Raspberry Pi fallback."""
import asyncio
import http.server
import json
import os
import socket
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'live'))

from acr_daily import api as api_mod, livelink, regions  # noqa: E402
import relay  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait(cond, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


class RegionSelectorTests(unittest.TestCase):
    def setUp(self):
        self.regs = (
            {'id': 'eu', 'label': 'EU', 'api': 'http://eu.test', 'relay': 'ws://eu.test/live'},
            {'id': 'uk', 'label': 'UK', 'api': 'http://uk.test', 'relay': 'ws://uk.test/live'},
            {'id': 'jp', 'label': 'JP', 'api': 'http://jp.test', 'relay': 'ws://jp.test/live'},
        )

    def test_auto_picks_lowest_rtt_with_hysteresis_and_pi_fallback(self):
        latencies = {'http://eu.test': 185.0, 'http://uk.test': 210.0, 'http://jp.test': 14.0}
        sel = regions.RegionSelector(regions=self.regs, probe_fn=lambda u: latencies.get(u))
        rtts = sel.probe_sync()
        self.assertEqual(rtts['jp'], 14.0)
        cands = sel.relay_candidates(mode='auto', default_pi_relay='wss://pi.test/live', background_probe=False)
        self.assertEqual(cands, ['ws://jp.test/live', 'ws://eu.test/live', 'ws://uk.test/live', 'wss://pi.test/live'])
        self.assertEqual(sel.summary_for_url('ws://jp.test/live'), 'JP (14 ms)')

        # Minor jitter (< HYSTERESIS_MS = 12 ms) does not flip the sticky auto choice
        latencies['http://eu.test'] = 10.0   # only 4 ms faster than JP's 14 ms
        sel.probe_sync()
        cands2 = sel.relay_candidates(mode='auto', default_pi_relay='wss://pi.test/live', background_probe=False)
        self.assertEqual(cands2[0], 'ws://jp.test/live')

        # Large shift (> 12 ms) switches to EU
        latencies['http://jp.test'] = 80.0
        sel.probe_sync()
        cands3 = sel.relay_candidates(mode='auto', default_pi_relay='wss://pi.test/live', background_probe=False)
        self.assertEqual(cands3[0], 'ws://eu.test/live')

    def test_manual_region_override_and_custom_live_server(self):
        sel = regions.RegionSelector(regions=self.regs, probe_fn=lambda _u: 20.0)
        sel.probe_sync()
        self.assertEqual(sel.relay_candidates(mode='uk', default_pi_relay='wss://pi.test/live', background_probe=False)[0],
                         'ws://uk.test/live')
        # Custom non-default liveServer overrides region list completely
        self.assertEqual(sel.relay_candidates(mode='auto', custom_relay='ws://127.0.0.1:9999/live',
                                              default_pi_relay='wss://pi.test/live', background_probe=False),
                         ['ws://127.0.0.1:9999/live'])

    def test_warm_keepalive_probe_rtt_ms(self):
        class HealthHandler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_GET(self):
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), HealthHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            ms = regions.probe_rtt_ms('http://127.0.0.1:%d' % srv.server_address[1])
            self.assertIsNotNone(ms)
            self.assertGreaterEqual(ms, 0.0)
            self.assertLess(ms, 500.0)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_livelink_falls_back_to_raspberry_pi_when_cloud_vms_down(self):
        dead_eu = free_port()
        dead_uk = free_port()
        dead_jp = free_port()
        pi_port = free_port()
        loop = asyncio.new_event_loop()
        started = threading.Event()
        holder = {}

        def run():
            asyncio.set_event_loop(loop)

            async def go():
                holder['srv'] = await asyncio.start_server(relay.Relay(node_id=99).handle, '127.0.0.1', pi_port)
                started.set()

            loop.run_until_complete(go())
            loop.run_forever()

        threading.Thread(target=run, daemon=True).start()
        started.wait(5)
        failed = []
        pi_url = 'ws://127.0.0.1:%d/live' % pi_port
        cands = [
            'ws://127.0.0.1:%d/live' % dead_eu,
            'ws://127.0.0.1:%d/live' % dead_uk,
            'ws://127.0.0.1:%d/live' % dead_jp,
            pi_url,
        ]
        link = livelink.LiveLink(cands[0], 'FallbackDriver', urls=cands, on_fail=failed.append)
        try:
            self.assertTrue(wait(lambda: link.state == 'live', timeout=6.0))
            self.assertEqual(link.active_url, pi_url)
            self.assertEqual(len(failed), 3)
        finally:
            link.close()
            asyncio.run_coroutine_threadsafe(
                (lambda s=holder['srv']: (s.close(), s.wait_closed())[1])(), loop
            ).result(5)
            loop.call_soon_threadsafe(loop.stop)

    def test_api_failover_across_regions_on_unreachable_get_only(self):
        dead_port = free_port()

        class ApiHandler(http.server.BaseHTTPRequestHandler):
            calls = 0

            def do_GET(self):
                ApiHandler.calls += 1
                body = json.dumps({'latest': '0.2.0'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), ApiHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        good_url = 'http://127.0.0.1:%d' % srv.server_address[1]
        dead_url = 'http://127.0.0.1:%d' % dead_port
        test_regs = (
            {'id': 'jp', 'label': 'JP', 'api': dead_url, 'relay': ''},
            {'id': 'eu', 'label': 'EU', 'api': good_url, 'relay': ''},
        )
        sel = regions.RegionSelector(regions=test_regs, probe_fn=lambda _u: 10.0)
        sel._rtts = {'jp': 5.0, 'eu': 50.0}
        sel._chosen_auto = 'jp'
        sel._last_probe = time.monotonic()
        try:
            with mock.patch.dict(os.environ, {'ACR_DAILY_SERVER': ''}), \
                 mock.patch.object(regions, 'DEFAULT_SELECTOR', sel):
                a = api_mod.Api({'useRegionalApi': True, 'region': 'auto'})
                v = a.version()
                self.assertEqual(v['latest'], '0.2.0')
                # Dead JP was marked failed, so next call goes straight to healthy EU
                self.assertEqual(sel.api_candidates(a.s, background_probe=False)[0], good_url)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == '__main__':
    unittest.main()
