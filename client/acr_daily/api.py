"""Talks to the ACR Daily server."""
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from . import USER_AGENT, __version__, settings


class ApiError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code        # HTTP status, when the server answered


TOO_OLD = 426   # the server takes runs only from recent versions of the app (MIN_APP_VERSION): update first


class Api:
    def __init__(self, s):
        self.s = s
        self.lock = threading.Lock()

    @property
    def base(self):
        return settings.server_url(self.s)

    @property
    def configured(self):
        return bool(self.base)

    def _req(self, method, path, body=None, auth=False, admin=False, timeout=15):
        if not self.base:
            raise ApiError('no server set')
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        if auth and self.s.get('token'):
            headers['Authorization'] = 'Bearer ' + self.s['token']
        if admin:
            headers['Authorization'] = 'Bearer ' + (self.s.get('adminKey') or '')
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8') or 'null')
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode('utf-8')).get('error') or str(e)
            except Exception:
                msg = str(e)
            if e.code == 401 and auth:
                self.s['token'] = ''
                settings.save(self.s)
            raise ApiError(msg, e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ApiError('server not reachable (%s)' % getattr(e, 'reason', e)) from None

    # ---------------------------------------------------------------- public data

    def today(self):
        """Today's dailies: a list of challenges (slot 1 and 2)."""
        return self._req('GET', '/api/challenges/today')['challenges']

    def leaderboard(self, date=None, slot=1):
        return self._req('GET', '/api/leaderboard?slot=%d' % slot + ('&date=' + date if date else ''))

    def week(self, date=None):
        """The weekly results (Monday to Sunday) that the date is in."""
        return self._req('GET', '/api/week' + ('?date=' + date if date else ''), timeout=20)

    def live_now(self, date, slot):
        """Who is on a daily's stage right now (the website's live map)."""
        return self._req('GET', '/api/live?date=%s&slot=%d' % (date, slot), timeout=5)

    def live(self, body):
        """Where we are on the stage (the website draws it on the map). -> the server's answer (with the other drivers
        on the stage when body['others']), or None when it didn't get there."""
        try:
            return self._req('POST', '/api/live', body, auth=True, timeout=5)
        except ApiError:
            return None

    def run_trace(self, run_id):
        return self._req('GET', '/api/runs/%s/trace' % run_id)

    def version(self):
        return self._req('GET', '/api/version')

    # ---------------------------------------------------------------- Steam login

    def login(self, on_done):
        """Opens the browser on Steam's sign-in page and waits (in a thread) for the server to confirm."""
        state = secrets.token_urlsafe(24)
        webbrowser.open(self.base + '/auth/steam/start?state=' + urllib.parse.quote(state))

        def wait():
            end = time.time() + 300
            while time.time() < end:
                time.sleep(2)
                try:
                    r = self._req('GET', '/auth/poll?state=' + urllib.parse.quote(state), timeout=10)
                except ApiError:
                    continue
                if r and r.get('token'):
                    self.s.update(token=r['token'], steamId=r['steamId'], name=r['name'])
                    settings.save(self.s)
                    on_done(True, r['name'])
                    return
            on_done(False, 'Steam sign-in timed out')
        threading.Thread(target=wait, daemon=True).start()

    def logout(self):
        try:
            self._req('POST', '/auth/logout', {}, auth=True)
        except ApiError:
            pass
        self.s.update(token='', steamId='', name='')
        settings.save(self.s)

    # ---------------------------------------------------------------- runs

    def submit(self, result):
        """Send a run; if that fails it is queued and sent later by flush()."""
        body = dict(result, appVersion=__version__)
        try:
            r = self._req('POST', '/api/runs', body, auth=True)
            return r
        except ApiError as e:
            if e.code != TOO_OLD:     # a run from a version the server no longer takes never will be
                self._queue(body)
            raise

    def _queue(self, body):
        with self.lock:
            q = self._pending()
            q.append(body)
            os.makedirs(settings.DIR, exist_ok=True)
            with open(settings.PENDING, 'w', encoding='utf-8') as f:
                json.dump(q[-50:], f)

    def _pending(self):
        try:
            with open(settings.PENDING, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def flush(self):
        """Retry queued runs. Returns how many are still waiting."""
        if not self.s.get('token'):
            return len(self._pending())
        with self.lock:
            q, left = self._pending(), []
            for body in q:
                try:
                    self._req('POST', '/api/runs', body, auth=True)
                except ApiError as e:
                    if 'too late' in str(e) or 'invalid' in str(e).lower() or e.code == TOO_OLD:
                        continue   # the server will never take it, drop it
                    left.append(body)
            with open(settings.PENDING, 'w', encoding='utf-8') as f:
                json.dump(left, f)
        return len(left)

    # ---------------------------------------------------------------- leagues (server src/leagues.js)

    def my_events(self):
        """The events of my leagues, open or coming soon, with my entry: {'now', 'events': [...]}."""
        return self._req('GET', '/api/me/events', auth=True)

    def event(self, event_id):
        """One event with its standings."""
        return self._req('GET', '/api/events/%d' % int(event_id), auth=True)

    def route(self, track):
        """A stage's route (to judge a league stage like a daily): [[x, z]...]."""
        return self._req('GET', '/api/route?track=' + urllib.parse.quote(track))['route']

    def league_start(self, event_id, car):
        """SS1 of an event started (the entry): {'started', 'car'}, or {'status': 'dnf', 'reason'} if it was before."""
        return self._req('POST', '/api/events/%d/start' % int(event_id), {'car': car}, auth=True)

    def league_begin(self, event_id, no):
        """Stage `no` (0 = SS1) of an event started: {'status': 'running'}, or 'dnf' if it had been started before."""
        return self._req('POST', '/api/events/%d/begin' % int(event_id), {'no': no}, auth=True)

    def league_stage(self, event_id, body):
        return self._req('POST', '/api/events/%d/stage' % int(event_id), body, auth=True)

    def league_dnf(self, event_id, no, reason):
        return self._req('POST', '/api/events/%d/dnf' % int(event_id), {'no': no, 'reason': reason}, auth=True)

    def routes(self):
        """Stages that already have a route: [{track, stageId, length}]."""
        return self._req('GET', '/api/routes')

    def contribute_route(self, rec, stage_id=None):
        """Send a clean run's route for a stage without one. -> {added, ...}"""
        body = {'track': rec['track'], 'car': rec['car'], 'clockMs': rec['clockMs'], 'points': rec['points']}
        if stage_id:
            body['stageId'] = stage_id
        return self._req('POST', '/api/routes/contribute', body, auth=True, timeout=30)

    # ---------------------------------------------------------------- admin

    def upload_route(self, track, points):
        return self._req('POST', '/api/admin/route', {'track': track, 'points': points}, admin=True)
