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


def refused(e):
    """The server answered that it will never take this run ("invalid ...": not the daily's stage, the wager daily
    without a stake...): sending it again would change nothing."""
    return e.code is not None and e.code < 500 and 'invalid' in str(e).lower()


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
            if e.code != TOO_OLD and not refused(e):   # a run the server won't take now never will be
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

    def flush(self, on_sent=None):
        """Retry queued runs; on_sent() once some got there. Returns how many are still waiting."""
        if not self.s.get('token'):
            return len(self._pending())
        sent = 0
        with self.lock:
            q, left = self._pending(), []
            for body in q:
                try:
                    self._req('POST', '/api/runs', body, auth=True)
                    sent += 1
                except ApiError as e:
                    if 'too late' in str(e) or 'invalid' in str(e).lower() or e.code == TOO_OLD:
                        continue   # the server will never take it, drop it
                    left.append(body)
            with open(settings.PENDING, 'w', encoding='utf-8') as f:
                json.dump(left, f)
        if sent and on_sent:
            on_sent()
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

    # ---------------------------------------------------------------- credits (a prototype: server src/credits.js)

    def credits(self):
        """{enabled, signedIn, balance, streak, claimable, nextBonus, wager: {slot, stake, entrants, pot, entered}}."""
        return self._req('GET', '/api/credits', auth=True)

    def claim_credits(self):
        """Today's bonus: {claimed, amount, balance, streak}."""
        return self._req('POST', '/api/credits/claim', {}, auth=True)

    def wager(self, slot, date=None):
        """Stake on today's wager daily, before the first run on it: {entered, balance, entrants, pot}. With the
        daily's date: a 409 if it is not today's any more (the day turned while DRIVE was clicked)."""
        return self._req('POST', '/api/credits/wager', {'slot': slot, 'date': date} if date else {'slot': slot}, auth=True)

    def league_dnf(self, event_id, no, reason):
        return self._req('POST', '/api/events/%d/dnf' % int(event_id), {'no': no, 'reason': reason}, auth=True)

    # ---------------------------------------------------------------- the inbox (server src/social.js)

    def inbox(self):
        """{unread, notices: [{id, kind, body, ref, created, read}], threads: [{with: {steamId, name, avatar, country},
        last: {body, created, mine}, unread, blocked}]}, the newest first."""
        return self._req('GET', '/api/inbox', auth=True)

    def inbox_unread(self):
        """How many notices and messages are unread (the INBOX button's count)."""
        return int((self._req('GET', '/api/inbox/unread', auth=True) or {}).get('unread') or 0)

    def inbox_with(self, steam_id):
        """The conversation with a driver, oldest first: {with, blocked, messages: [{id, mine, body, created}]}. Their
        messages to me are read from then on."""
        return self._req('GET', '/api/inbox/with/%s' % urllib.parse.quote(str(steam_id)), auth=True)

    def inbox_send(self, to, body):
        """A message to a driver (500 characters at most): {id}. A 429 past 30 an hour, a 403 if they block me."""
        return self._req('POST', '/api/inbox/send', {'to': str(to), 'body': body}, auth=True)

    def inbox_read(self, ids=None):
        """Notices read: these, or all of them."""
        return self._req('POST', '/api/inbox/read', {'ids': list(ids)} if ids else {}, auth=True)

    # ---------------------------------------------------------------- 1V1s, cups, a driver (server src/h2h.js, cups.js, drivers.js)

    def h2h(self):
        """My 1V1s: {incoming, outgoing, active, past: [{id, status, stake, mine, challenger, opponent, name, rally, car,
        carClass, opens, closes, stages, answerBy, eventId, winner, note}], credits, maxStake}."""
        return self._req('GET', '/api/h2h', auth=True)

    def h2h_answer(self, h2h_id, action):
        """A 1V1 challenge accepted or declined (the challenged driver), or cancelled (the challenger): {status,
        eventId?}. Accepting takes the stake: a 402 without the credits."""
        if action not in ('accept', 'decline', 'cancel'):
            raise ValueError(action)
        return self._req('POST', '/api/h2h/%d/%s' % (int(h2h_id), action), {}, auth=True)

    def cups(self):
        """{open, running, finished: [cup], mine: [ids of the cups I'm in], credits}: a cup {id, name, official, owner,
        size, fee, prize, pot, starts, roundHours, status, round, entrants, rally, car, carClass, stages, draw}."""
        return self._req('GET', '/api/cups', auth=True)

    def cup_entry(self, cup_id, action):
        """Join or leave a cup before its start: {entered}. Joining takes the entry fee: a 402 without the credits."""
        if action not in ('join', 'leave'):
            raise ValueError(action)
        return self._req('POST', '/api/cups/%s/%s' % (urllib.parse.quote(str(cup_id)), action), {}, auth=True)

    def driver(self, steam_id):
        """A driver's page: {name, team, look, rating: {rating, rank, of, races, peak} or None (not rated yet),
        ratingOn, stats, ...}."""
        return self._req('GET', '/api/drivers/%s' % urllib.parse.quote(str(steam_id)), auth=True)

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
