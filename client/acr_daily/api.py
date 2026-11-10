"""Talks to the ACR Daily server."""
import hashlib
import html
import http.server
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
SIGNIN_WAIT_S = 300


def _signin_page(title, text):
    """What the browser shows once it is back at the app (dark, like the website's pages)."""
    return ('<!doctype html><meta charset="utf-8"><title>ACR Daily</title><body style="background:#0A0A0C;color:#FFFFFF;'
            'font:18px system-ui;display:grid;place-items:center;height:100vh;margin:0"><div style="text-align:center;'
            'padding:16px;border-top:4px solid #E30613"><h1 style="margin:16px 0 8px">%s</h1><p style="color:#D8D8DE">%s'
            '</p></div>' % (html.escape(title), html.escape(text))).encode('utf-8')


def _signin_handler(api, state, verifier, got):
    """The request handler for the browser coming back after Steam: /signed-in?state&code -> the token (into got)."""

    class Back(http.server.BaseHTTPRequestHandler):
        timeout = 5                               # (a browser's spare connection never blocks the wait)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path != '/signed-in' or q.get('state', [''])[0] != state or 'done' in got:
                self.send_response(404)
                self.end_headers()
                return
            try:
                r = api._req('POST', '/auth/exchange', {'state': state, 'code': q.get('code', [''])[0], 'verifier': verifier})
                got.update(r=r)
                body = _signin_page('Signed in as %s' % r.get('name', ''), 'You can close this tab and go back to ACR Daily.')
            except ApiError as e:
                got.update(error='Sign-in failed: %s' % e)
                body = _signin_page('Sign-in failed', '%s. Sign in again from ACR Daily.' % e)
            got['done'] = True
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):              # (nothing on a console the exe doesn't have)
            pass
    return Back


def run_path(body):
    """Where a run goes: a time trial stage's ('tt:<week>/<slot>', server src/timetrial.js) to /api/tt/runs, a
    daily's to /api/runs."""
    return '/api/tt/runs' if str((body or {}).get('challengeId') or '').startswith('tt:') else '/api/runs'


def refused(e):
    """The server answered that it will never take this run ("invalid ...": not the daily's stage, the wager daily
    without a stake...): sending it again would change nothing."""
    return e.code is not None and e.code < 500 and 'invalid' in str(e).lower()


OFFICIAL_WORKER, WEBSITE = '://acr-daily.acr-daily-server.workers.dev', '://acrdaily.com'


def site_of(base):
    """The website's address for a server's: the official server's workers.dev name (the app's requests go there) is
    acrdaily.com to people, the same Worker; another server (your own: SETUP.md) as it is."""
    return (base or '').rstrip('/').replace(OFFICIAL_WORKER, WEBSITE)


class Api:
    def __init__(self, s):
        self.s = s
        self.lock = threading.Lock()

    @property
    def base(self):
        return settings.server_url(self.s)

    @property
    def site(self):
        """Where the browser goes (the guide, the website's pages, Steam's sign-in): acrdaily.com (site_of)."""
        return site_of(self.base)

    @property
    def configured(self):
        return bool(self.base)

    def _req(self, method, path, body=None, auth=False, admin=False, timeout=15, raw=None):
        """raw: (bytes, content type) sent as they are instead of a JSON body (a picture)."""
        if not self.base:
            raise ApiError('no server set')
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        data = None
        if raw is not None:
            data, headers['Content-Type'] = raw
        elif body is not None:
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

    def event_live(self, event_id, body):
        """Where we are on a league event's stage (a cup match, a 1V1, a league event): the website follows it live.
        body: {no, x, z, progress, totalMs, state}. -> the server's answer, or None when it didn't get there."""
        try:
            return self._req('POST', '/api/events/%d/live' % int(event_id), body, auth=True, timeout=5)
        except ApiError:
            return None

    def run_trace(self, run_id):
        return self._req('GET', '/api/runs/%s/trace' % run_id)

    def version(self):
        return self._req('GET', '/api/version')

    # ---------------------------------------------------------------- Steam login

    def login(self, on_done):
        """Steam sign-in in the browser, back to this app on this PC (RFC 8252 loopback): the app listens on 127.0.0.1
        (a free port), the server sends the browser there after Steam with a one-time code, and the app swaps it for its
        token with a secret only it knows (the verifier). Whoever has the sign-in link gets nothing. on_done(ok, name or
        why not), from a thread."""
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        got = {}
        try:
            srv = http.server.HTTPServer(('127.0.0.1', 0), _signin_handler(self, state, verifier, got))
        except OSError as e:
            on_done(False, 'Sign-in could not start (%s)' % e)
            return
        srv.timeout = 1                           # (handle_request returns each second: the wait can end)
        webbrowser.open('%s/auth/steam/start?%s' % (self.site, urllib.parse.urlencode({
            'state': state, 'port': srv.server_address[1], 'challenge': hashlib.sha256(verifier.encode()).hexdigest()})))

        def wait():
            end = time.time() + SIGNIN_WAIT_S
            try:
                while time.time() < end and 'done' not in got:
                    srv.handle_request()
            finally:
                srv.server_close()
            r = got.get('r')
            if r and r.get('token'):
                self.s.update(token=r['token'], steamId=r['steamId'], name=r['name'])
                settings.save(self.s)
                on_done(True, r['name'])
            else:
                on_done(False, got.get('error') or 'Steam sign-in timed out')
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
        """Send a run; if that fails it is queued and sent later by flush(). Runs reach the server in the order they were
        driven (it counts each daily's first run to arrive): older ones still queued go first, and while they can't, this
        one waits behind them."""
        body = dict(result, appVersion=__version__)
        if self.flush():
            self._queue(body)
            raise ApiError('older runs are still waiting to be sent')
        try:
            r = self._req('POST', run_path(body), body, auth=True)
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
            if not q:                             # nothing waiting: nothing to send, no file to write
                return 0
            for body in q:
                try:
                    self._req('POST', run_path(body), body, auth=True)
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

    # ---------------------------------------------------------------- the time trial (server src/timetrial.js)

    def time_trial(self, week=None, lite=False):
        """This week's time trial (or `week`'s, its Monday): {on, week, isoWeek, startsAt, endsAt, credits,
        stages: [a challenge as a daily's, with id 'tt:<week>/<slot>', fee (0: free), entrants, pot, me: {entered,
        bestMs, runs}]}; lite: without the routes. {on: False} when there is none."""
        q = '&'.join(x for x in ('week=' + week if week else '', 'lite=1' if lite else '') if x)
        return self._req('GET', '/api/tt' + ('?' + q if q else ''), auth=True)

    def tt_board(self, week, slot):
        """A time trial stage's board: {entries: [{rank, runId, steamId, name, totalMs, clockMs, gapMs, runs, prize,
        splits}], stats: {drivers, runs, entrants, pot, paidPlaces}, credits, settled}."""
        return self._req('GET', '/api/tt/board?week=%s&slot=%d' % (urllib.parse.quote(str(week)), int(slot)))

    def tt_trace(self, run_id):
        """A driver's best run on a time trial stage: its trace (the ghost of the leader)."""
        return self._req('GET', '/api/tt/runs/%s/trace' % int(run_id))

    def tt_live(self, body):
        """Where we are on a time trial stage (the /tt page's live map): body {challengeId, x, z, progress, totalMs,
        state, others}. -> the server's answer (with the other drivers on the stage when body['others']), or None."""
        try:
            return self._req('POST', '/api/tt/live', body, auth=True, timeout=5)
        except ApiError:
            return None

    def tt_live_now(self, week, slot):
        """Who is on a time trial stage right now: {drivers: [{steamId, name, progress, state, ...}]}."""
        return self._req('GET', '/api/tt/live?week=%s&slot=%d' % (urllib.parse.quote(str(week)), int(slot)), timeout=5)

    def tt_enter(self, slot, week=None):
        """Enter this week's TT<slot>: {entered, fee, balance, entrants, pot}; a 402 without the credits, a 409 if
        the week has turned since it was shown."""
        return self._req('POST', '/api/tt/enter', dict({'slot': int(slot)}, **({'week': week} if week else {})), auth=True)

    # ---------------------------------------------------------------- leagues (server src/leagues.js)

    def my_events(self):
        """The events of my leagues, open or coming soon, with my entry: {'now', 'events': [...]}."""
        return self._req('GET', '/api/me/events', auth=True)

    def event(self, event_id):
        """One event with its standings."""
        return self._req('GET', '/api/events/%d' % int(event_id), auth=True)

    def reveal(self, event_id):
        """A hidden event's set-up (its stages, weather and start times: server src/hidden.js), asked for on DRIVE:
        the event as /api/me/events lists it, in full. The server keeps that it was asked."""
        return self._req('POST', '/api/events/%d/reveal' % int(event_id), {}, auth=True)

    def route(self, track):
        """A stage's route (to judge a league stage like a daily): [[x, z]...]."""
        return self._req('GET', '/api/route?track=' + urllib.parse.quote(track))['route']

    def league_start(self, event_id, car, at=None):
        """SS1 of an event started (the entry): {'started', 'car'}, or {'status': 'dnf', 'reason'} if it was before.
        at: when it started (ms): the same start sent again is no second start."""
        return self._req('POST', '/api/events/%d/start' % int(event_id), {'car': car, 'at': at}, auth=True)

    def league_begin(self, event_id, no, at=None):
        """Stage `no` (0 = SS1) of an event started: {'status': 'running'}, or 'dnf' if it had been started before
        (not this same start, `at`, sent again)."""
        return self._req('POST', '/api/events/%d/begin' % int(event_id), {'no': no, 'at': at}, auth=True)

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

    def h2h_rematch(self, h2h_id, stake=None):
        """A 1V1 that is over sent again to the other driver (the same stages, car, rules; its stake unless `stake`), open
        as long as it was, from now: {id, status}. A 402 without the credits for the stake."""
        return self._req('POST', '/api/h2h/%d/rematch' % int(h2h_id), {} if stake is None else {'stake': int(stake)}, auth=True)

    def h2h_challenge(self, opponent, stake, event):
        """A new 1V1: opponent (steam id), stake (0: a friendly), event {name?, rally, car | carClass, rules, stages:
        [{track, day, weather, time}], opens, closes (ms)}. -> {id, status}."""
        return self._req('POST', '/api/h2h', {'opponent': str(opponent), 'stake': int(stake), 'event': event}, auth=True)

    def players(self, q):
        """Drivers whose name has q (2 characters at least): [{steamId, name, avatar, country}]."""
        return (self._req('GET', '/api/players?q=%s' % urllib.parse.quote(q)) or {}).get('players') or []

    def catalog(self):
        """What an event can race: {rallies: [{name, surface, stages: [{track, stageId, name, lengthM}]}], cars: [{name,
        id, cls, group}], classes: [{cls, group}], weathers: [{id, label, game}], rules: {defaults, ...}, limits}."""
        return self._req('GET', '/api/catalog')

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

    # ---------------------------------------------------------------- my driver page, the shop (profileui.py)

    def driver_page(self, steam_id):
        """A driver's whole page, as the website's (the app's own driver page): the profile, the rating's history, the
        career numbers, the recent results, the achievements (each with what it is), and mine: what I can change."""
        return self._req('GET', '/api/drivers/%s?full=1' % urllib.parse.quote(str(steam_id)), auth=True)

    def countries(self):
        """The flags a driver can pick: [[code, name], ...]."""
        return self._req('GET', '/api/countries')

    def set_name(self, name):
        """A name of my own (None / '': my Steam name again); one change a week."""
        return self._req('POST', '/api/me/name', {'name': name or None}, auth=True)

    def set_country(self, code):
        """My flag (a code of /api/countries; None: none)."""
        return self._req('POST', '/api/me/country', {'country': code or None}, auth=True)

    def set_avatar(self, data, content_type):
        """A picture of my own: a square PNG, JPEG or WebP, 64 to 512 px, 60 KB at most."""
        return self._req('POST', '/api/me/avatar', auth=True, raw=(data, content_type))

    def remove_avatar(self):
        """My Steam picture again."""
        return self._req('POST', '/api/me/avatar', {'remove': True}, auth=True)

    def shop(self):
        """The shop: {enabled, balance, worn: {color, badge, frame}, items: [{id, kind, name, price, owned, color / badge
        / ring...}], daily: {price, from, to, tracks, cars, weathers, times, mine}}."""
        return self._req('GET', '/api/shop', auth=True)

    def shop_buy(self, item):
        """Buy a look (once; worn at once)."""
        return self._req('POST', '/api/shop/buy', {'item': item}, auth=True)

    def shop_wear(self, kind, item):
        """Wear a look bought (item None: none of that kind)."""
        return self._req('POST', '/api/shop/wear', {'kind': kind, 'item': item}, auth=True)

    def shop_daily(self, body):
        """A daily of my own: {date, track, car, weather, time}."""
        return self._req('POST', '/api/shop/daily', body, auth=True)

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
