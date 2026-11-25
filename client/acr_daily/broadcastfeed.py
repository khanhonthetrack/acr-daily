"""The broadcast overlay for a stream, served from this PC while WATCH runs (the user, 25 Nov 2026: "For overlays, did you
forget to also include the gauge?"). The website's overlay (server src/broadcast.js) has the stage's times and who is
on it, but not a car's revs, speed, gear or pedals: those come only to the apps watching, through the live relay
(livelink.py). So the app serves the website's overlay itself, at http://127.0.0.1:PORT/ (OBS: a browser source,
1920 x 1080), with the car WATCH follows and its dash at /feed.json: the page (feed=1) draws the gauge as the game's
WATCH does and follows WATCH from stage to stage.

    /              the overlay of the stage WATCH watches (a page that waits, when it watches none)
    /feed.json     {on, page, driver: {name, country, team, totalMs, progress, stageNo}, dash: {kmh, gear, rpm_frac,
                   gas, brake}}: written by WATCH's broadcast each frame (ig_watch.overlay: publish), read 10 times a second
    /broadcast/..., /api/v1/..., /api/liverallies..., /series/...   the website's, passed through (GET only)

Only on 127.0.0.1 (nothing from another PC), and only while SETTINGS > Streaming overlay is on (settings
streamOverlay)."""
import http.server
import json
import threading
import time
import urllib.error
import urllib.request

from . import USER_AGENT

PORT = 8833
PASS = ('/broadcast/', '/api/v1/', '/api/liverallies', '/series/')
STALE_S = 2.0                     # WATCH's last word older than this: nothing followed (WATCH ended, the game closed)

_state = {'at': 0.0, 'feed': {'on': False}}
_server = None


def url():
    return 'http://127.0.0.1:%d/' % PORT


def page_of(w):
    """The overlay's path for what WATCH watches (watch.Watch), or None."""
    if w is None or not getattr(w, 'on', False):
        return None
    if w.kind in ('daily', 'tt'):
        return '/broadcast/%s/%d' % (w.kind, int(w.slot))
    ev = getattr(w, 'event', None) or {}
    ses = ev.get('session')
    if ev.get('kind') == 'live' and ses:
        return '/broadcast/ranked/%s/%d' % (ses[0], int(ses[1]))
    return '/broadcast/event/%d' % int(ev['eventId']) if ev.get('eventId') else None


def publish(w, fol, at, dash, country=None, team=None):
    """WATCH's broadcast, this frame: what it follows (fol: livelink.LiveDriver or None; at: watch.where(); dash:
    LiveDriver.dash_at())."""
    feed = {'on': fol is not None, 'page': page_of(w)}
    if fol is not None:
        t = None
        if isinstance(team, dict) and team.get('text'):
            t = {'tag': team.get('text'), 'color': team.get('color')}
        feed['driver'] = {'name': fol.name or '', 'country': country, 'team': t, 'stageNo': getattr(w, 'slot', None),
                          'totalMs': (at or {}).get('ms'), 'progress': (at or {}).get('progress')}
        if dash:
            feed['dash'] = {k: dash.get(k) for k in ('kmh', 'gear', 'rpm_frac', 'gas', 'brake')}
    _state['feed'], _state['at'] = feed, time.monotonic()


def current():
    if time.monotonic() - _state['at'] > STALE_S:
        return {'on': False, 'page': None}
    return _state['feed']


WAITING = ('<!doctype html><meta charset="utf-8"><title>ACR Daily · broadcast</title><body style="margin:0;background:'
           'transparent"><script>setInterval(function(){fetch("/feed.json",{cache:"no-store"}).then(function(r){return '
           'r.json()}).then(function(j){if(j&&j.page)location.replace(j.page+"?feed=1")}).catch(function(){})},1000)'
           '</script>').encode('utf-8')


def _handler(site):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('#')[0]
            if path in ('/', '/index.html'):
                f = current()
                if f.get('page'):
                    self.send_response(302)
                    self.send_header('Location', f['page'] + '?feed=1')
                    self.end_headers()
                    return
                return self._send(200, WAITING, 'text/html; charset=utf-8')
            if path.startswith('/feed.json'):
                return self._send(200, json.dumps(current()).encode('utf-8'), 'application/json')
            if not path.startswith(PASS):
                return self._send(404, b'not found', 'text/plain')
            try:
                with urllib.request.urlopen(urllib.request.Request(site + path, headers={'User-Agent': USER_AGENT}),
                                            timeout=15) as r:
                    keep = {k: r.headers[k] for k in ('Content-Security-Policy',) if r.headers.get(k)}
                    return self._send(r.status, r.read(), r.headers.get('Content-Type') or 'application/octet-stream', keep)
            except urllib.error.HTTPError as e:
                return self._send(e.code, e.read() or b'', e.headers.get('Content-Type') or 'text/plain')
            except (OSError, ValueError) as e:
                return self._send(502, str(e).encode('utf-8'), 'text/plain')
    return H


def start(site):
    """Serving (once): -> True when it is (the port taken by another program: False)."""
    global _server
    if _server is not None:
        return True
    try:
        _server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), _handler(site.rstrip('/')))
    except OSError:
        _server = None
        return False
    _server.daemon_threads = True
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    return True


def stop():
    global _server
    s, _server = _server, None
    if s is not None:
        s.shutdown()
        s.server_close()


def running():
    return _server is not None
