"""The overlay for OBS from this PC (broadcastfeed.py): WATCH's car and dash at /feed.json, / to the overlay of the stage
watched, the website's pages passed through (GET, a few paths only), nothing once WATCH stops."""
import http.server
import json
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
from unittest import mock

from acr_daily import broadcastfeed as bf

_local = urllib.request.build_opener(urllib.request.ProxyHandler({}), )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Feed(unittest.TestCase):
    def setUp(self):
        # (the website: a tiny server of its own on a free port)
        class Site(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = ('site:' + self.path).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Security-Policy', "connect-src 'self'")
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.site = http.server.HTTPServer(('127.0.0.1', 0), Site)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.addCleanup(self.site.server_close)
        self.addCleanup(self.site.shutdown)
        p = mock.patch.object(bf, 'PORT', 0)
        p.start()
        self.addCleanup(p.stop)
        self.assertTrue(bf.start('http://127.0.0.1:%d/' % self.site.server_address[1]))
        self.addCleanup(bf.stop)
        self.base = 'http://127.0.0.1:%d' % bf._server.server_address[1]

    def get(self, path, follow=True):
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}), *([] if follow else [NoRedirect()]))
        try:
            r = op.open(self.base + path, timeout=5)
            return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def test_watch_s_car_its_dash_and_the_page(self):
        self.assertEqual(json.loads(self.get('/feed.json')[1]), {'on': False, 'page': None})
        self.assertIn('feed.json', self.get('/')[1])                     # (WATCH off: a page that waits)
        w = types.SimpleNamespace(on=True, kind='event', slot=2, event={'eventId': 77, 'kind': 'live', 'session': ('skoda', 1795867200000)})
        fol = types.SimpleNamespace(name='Ann')
        bf.publish(w, fol, {'ms': 61000, 'progress': 0.4}, {'kmh': 123.4, 'gear': 4, 'rpm_frac': 0.8, 'gas': 1.0, 'brake': 0.0, 'steer': 3},
                   'fi', {'text': 'ABC', 'color': '336699'})
        f = json.loads(self.get('/feed.json')[1])
        self.assertEqual(f['page'], '/broadcast/ranked/skoda/1795867200000')
        self.assertEqual(f['driver'], {'name': 'Ann', 'country': 'fi', 'team': {'tag': 'ABC', 'color': '336699'}, 'stageNo': 2,
                                       'totalMs': 61000, 'progress': 0.4})
        self.assertEqual(f['dash'], {'kmh': 123.4, 'gear': 4, 'rpm_frac': 0.8, 'gas': 1.0, 'brake': 0.0})
        code, _b, h = self.get('/', follow=False)
        self.assertEqual((code, h.get('Location')), (302, '/broadcast/ranked/skoda/1795867200000?feed=1'))
        self.assertEqual(bf.page_of(types.SimpleNamespace(on=True, kind='daily', slot=1)), '/broadcast/daily/1')
        self.assertEqual(bf.page_of(types.SimpleNamespace(on=True, kind='event', slot=1, event={'eventId': 5})), '/broadcast/event/5')
        with mock.patch.object(bf.time, 'monotonic', return_value=time.monotonic() + bf.STALE_S + 1):
            self.assertEqual(bf.current(), {'on': False, 'page': None})   # (WATCH stopped speaking: nothing followed)

    def test_the_website_passed_through_only_its_pages(self):
        code, body, h = self.get('/broadcast/event/5?feed=1')
        self.assertEqual((code, body), (200, 'site:/broadcast/event/5?feed=1'))
        self.assertEqual(h.get('Content-Security-Policy'), "connect-src 'self'")
        self.assertEqual(self.get('/api/v1/events/5')[0], 200)
        self.assertEqual(self.get('/admin')[0], 404)
        self.assertEqual(self.get('/api/admin/review')[0], 404)
        self.assertEqual(bf._server.server_address[0], '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
