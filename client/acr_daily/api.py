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
from . import i18n
from .i18n import _


class ApiError(Exception):
    def __init__(self, msg, code=None, unreachable=False, why=''):
        super().__init__(msg)
        self.code = code        # HTTP status, when the server answered
        self.unreachable = unreachable   # no answer at all (no connection, the server down): say so in words
        self.why = why          # ... and the system's own reason ([Errno 111] ...), for the app's notes only


TOO_OLD = 426   # the server takes runs only from recent versions of the app (MIN_APP_VERSION): update first
SIGNIN_WAIT_S = 300


def _signin_page(title, text):
    """What the browser shows once it is back at the app (dark, like the website's pages)."""
    return ('<!doctype html><meta charset="utf-8"><title>ACR Daily</title><body style="background:#0A0A0C;color:#FFFFFF;'
            'font:18px system-ui;display:grid;place-items:center;height:100vh;margin:0"><div style="text-align:center;'
            'padding:16px;border-top:4px solid #E30613"><h1 style="margin:16px 0 8px">%s</h1><p style="color:#D8D8DE">%s'
            '</p></div>' % (html.escape(title), html.escape(text))).encode('utf-8')


def steam_running():
    """The Steam client is running on this PC (False away from Windows)."""
    try:
        from .modinstall import _game_pids, _kernel32
        return bool(_game_pids(_kernel32(), 'steam.exe'))
    except Exception:
        return False


def open_signin(url):
    """Steam's sign-in page: in the Steam client's own browser when Steam is running (steam://openurl), where the
    player is signed in to Steam already: one click on Steam's own page, no password typed anywhere (a player, Nov
    2026: "wary about signing into steam through some unsigned .exe"); else in the PC's browser. Either way the page
    is Steam's (steamcommunity.com, OpenID), and ACR DAILY gets the Steam ID and name it gives, never a password.
    (settings signInBrowser: always the PC's browser.) -> 'steam' or 'browser'."""
    if os.name == 'nt' and steam_running() and not settings.load().get('signInBrowser'):
        try:
            os.startfile('steam://openurl/' + url)          # noqa: S606  (Steam's own URL handler)
            return 'steam'
        except OSError:
            pass
    webbrowser.open(url)
    return 'browser'


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
                body = _signin_page(_('Signed in as %s') % r.get('name', ''), _('You can close this tab and go back to ACR Daily.'))
            except ApiError as e:
                got.update(error=_('Sign-in failed: %s') % e)
                body = _signin_page(_('Sign-in failed'), _('%s. Sign in again from ACR Daily.') % e)
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
    """Where a run goes: a time trial stage's ('tt:<week>/<slot>', server src/timetrial.js) to /api/tt/runs, a COPILOT
    crew's ('cp:<date>/<lobby>', src/copilot.js) to /api/copilot/runs, a daily's to /api/runs."""
    cid = str((body or {}).get('challengeId') or '')
    return '/api/tt/runs' if cid.startswith('tt:') else '/api/copilot/runs' if cid.startswith('cp:') else '/api/runs'


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
    _pending_n = None      # how many runs wait to be sent, as last read or written (pending_count)

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
            raise ApiError(_('no server set'))
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json', 'X-ACR-Legs': '1',   # (long rallies in legs: leagues.py)
                   'X-ACR-Locked': '1',   # (private rallies listed with a lock, their code asked for: leagueui.py)
                   'Accept-Language': i18n.accept_language()}   # (the server's messages in the app's language)
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
            why = str(getattr(e, 'reason', e))
            raise ApiError(_('server not reachable (%s)') % why, unreachable=True, why=why) from None

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

    def live_ticket(self):
        """A ticket for the live ghost car relay: our driver, signed by the server (src/livetickets.js).
        -> {ticket, steamId, name, expires}; ApiError when not signed in."""
        return self._req('POST', '/api/live/ticket', {}, auth=True, timeout=8)

    def event_live(self, event_id, body):
        """Where we are on a league event's stage (a cup match, a 1V1, a league event): the website follows it live.
        body: {no, x, z, progress, totalMs, state}. -> the server's answer, or None when it didn't get there."""
        try:
            return self._req('POST', '/api/events/%d/live' % int(event_id), body, auth=True, timeout=5)
        except ApiError:
            return None

    def run_trace(self, run_id):
        return self._req('GET', '/api/runs/%s/trace' % run_id)

    # ---------------------------------------------------------------- replays (server src/replays.js, replays.py)

    def replay_begin(self, body):
        """A counted run's start: {kind, ref, track, car, clockMs, key} -> {rid, nonce}."""
        return self._req('POST', '/api/replays/begin', body, auth=True, timeout=8)

    def replay_commit(self, body):
        """The replay's rows so far, hashed: {rid, n, count, hash, clockMs, fin}."""
        return self._req('POST', '/api/replays/commit', body, auth=True, timeout=8)

    def replay_upload(self, data, public=False):
        """A replay file's bytes -> {code, verdict, report, action, why, public, stamp, url}; a refused one: ApiError
        (code 422, its notes in the message)."""
        return self._req('POST', '/api/replays/upload' + ('?public=1' if public else ''), auth=True, timeout=40,
                         raw=(data, 'application/octet-stream'))

    def replay_run(self, rid):
        """Where the server is with a followed run: {have (commits), fin, uploaded, open}."""
        return self._req('GET', '/api/replays/run/%s' % rid, auth=True, timeout=10)

    def replays_wanted(self):
        return self._req('GET', '/api/replays/wanted', auth=True, timeout=10).get('wanted') or []

    def replay_none(self, request_id):
        """A steward's request answered: no replay of that stage on this PC."""
        return self._req('POST', '/api/replays/requests/%d/none' % int(request_id), {}, auth=True, timeout=10)

    def replay_meta(self, code):
        return self._req('GET', '/api/replays/%s' % code, auth=True, timeout=10)

    def replay_share(self, code, public):
        return self._req('POST', '/api/replays/%s/share' % code, {'public': bool(public)}, auth=True, timeout=10)

    def replay_file(self, code):
        """A replay's file from the server (its code) -> bytes; ApiError when not there or not ours to see."""
        if not self.base:
            raise ApiError(_('no server set'))
        headers = {'User-Agent': USER_AGENT}
        if self.s.get('token'):
            headers['Authorization'] = 'Bearer ' + self.s['token']
        req = urllib.request.Request(self.base + '/api/replays/%s/file' % code, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read(8 * 1024 * 1024)
        except urllib.error.HTTPError as e:
            raise ApiError(_('no such replay (private, or no longer kept)') if e.code == 404 else str(e), e.code) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise ApiError(_('server not reachable (%s)') % getattr(e, 'reason', e), unreachable=True) from None

    def version(self):
        return self._req('GET', '/api/version')

    def changelog(self, version, since=None):
        """What's new in a version (server/src/changelog.js): {version, date, title, photo, changes, kinds}; 404 for
        none. since: the version whose what's new was seen last ('0': any), for earlier: the versions out since then,
        newest first, each as the version's (a server before 0.1.6's gives none)."""
        q = '?since=%s' % urllib.parse.quote(str(since)) if since else ''
        return self._req('GET', '/api/changelog/%s%s' % (version, q), timeout=8)

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
            on_done(False, _('Sign-in could not start (%s)') % e)
            return
        srv.timeout = 1                           # (handle_request returns each second: the wait can end)
        open_signin('%s/auth/steam/start?%s' % (self.site, urllib.parse.urlencode({
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
                on_done(False, got.get('error') or _('Steam sign-in timed out'))
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
            raise ApiError(_('older runs are still waiting to be sent'))
        try:
            r = self._req('POST', run_path(body), body, auth=True)
            return r
        except ApiError as e:
            if e.code != TOO_OLD and not refused(e):   # a run the server won't take now never will be
                self._queue(body)
            raise

    def report(self, fields):
        """A bug report (server/src/reports.js), as the website's /report files one: {title, body, area, appVersion,
        eventUrl, happened, system} -> its id. (gamelog.py: a run the game didn't save, with the game's log.)"""
        return int(self._req('POST', '/api/reports', fields, auth=True)['id'])

    def report_file(self, report_id, data, name, kind='log', size=None):
        """A file of that report, within an hour of it: gzipped bytes, as the website packs a log (size: before)."""
        q = urllib.parse.urlencode({'kind': kind, 'name': name, 'size': size or len(data)})
        return self._req('POST', '/api/reports/%d/files?%s' % (int(report_id), q), raw=(data, 'application/gzip'),
                         auth=True, timeout=60)

    def _queue(self, body):
        with self.lock:
            q = self._pending()
            q.append(body)
            os.makedirs(settings.DIR, exist_ok=True)
            with open(settings.PENDING, 'w', encoding='utf-8') as f:
                json.dump(q[-50:], f)
            self._pending_n = len(q[-50:])

    def _pending(self):
        try:
            with open(settings.PENDING, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def pending_count(self):
        """How many runs wait to be sent (the main window's footer, on every tick): the file is read once, then the count
        is kept as _queue and flush change it (it was opened and read 20 times a second)."""
        n = self._pending_n
        if n is None:
            n = self._pending_n = len(self._pending())
        return n

    def flush(self, on_sent=None):
        """Retry queued runs; on_sent() once some got there. Returns how many are still waiting."""
        if not self.s.get('token'):
            self._pending_n = n = len(self._pending())
            return n
        sent = 0
        with self.lock:
            q, left = self._pending(), []
            if not q:                             # nothing waiting: nothing to send, no file to write
                self._pending_n = 0
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
            self._pending_n = len(left)
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

    # ---------------------------------------------------------------- COPILOT (server src/copilot.js)

    def copilot(self):
        """Today's COPILOT: {on, date, ready, revealed, stage (once revealed), tries: {driver, codriver}, lobby (mine),
        lobbies (the open public ones)}."""
        return self._req('GET', '/api/copilot', auth=True, timeout=8)

    def copilot_board(self, date=None):
        """A day's crews: {entries: [{rank, status, totalMs, gapMs, driver: {name...}, codriver: {...}}], stage?}."""
        return self._req('GET', '/api/copilot/board' + ('?date=' + date if date else ''), auth=True, timeout=8)

    def copilot_create(self, role, private=False, langs=None):
        """A new lobby: role 'driver' / 'codriver' -> {lobby}."""
        body = {'role': role, 'private': bool(private)}
        if langs:
            body['langs'] = list(langs)
        return self._req('POST', '/api/copilot/lobbies', body, auth=True)

    def copilot_join(self, lobby_id=None, code=None):
        """Join a lobby: from the list (lobby_id; a private one with its code too), or by its code alone."""
        body = {}
        if lobby_id:
            body['id'] = int(lobby_id)
        if code:
            body['code'] = code
        return self._req('POST', '/api/copilot/join', body, auth=True)

    def copilot_ranking(self, month=None):
        """A month's ranking (this one's by default): {month, drivers: [{rank, name, points, days, wins, best}],
        codrivers: [...]}."""
        return self._req('GET', '/api/copilot/ranking' + ('?month=' + month if month else ''), timeout=8)

    def copilot_lobby(self, lobby_id):
        """My lobby: its state, the other's link details; once started its stage (ch) and, for the co-driver, notes."""
        return self._req('GET', '/api/copilot/lobbies/%d' % int(lobby_id), auth=True, timeout=6)

    def copilot_ready(self, lobby_id, ready=True):
        return self._req('POST', '/api/copilot/lobbies/%d/ready' % int(lobby_id), {'ready': bool(ready)}, auth=True)

    def copilot_leave(self, lobby_id):
        return self._req('POST', '/api/copilot/lobbies/%d/leave' % int(lobby_id), {}, auth=True)

    def copilot_live(self, body):
        """The crew driver's position on the stage, for the website's CODRIVER DAILY map (src/copilot.js postLive)."""
        return self._req('POST', '/api/copilot/live', body, auth=True, timeout=6)

    def copilot_signal(self, lobby_id, data):
        """My side's details for the direct link between the two apps (copilotlink.py)."""
        return self._req('POST', '/api/copilot/lobbies/%d/signal' % int(lobby_id), {'data': data}, auth=True, timeout=6)
    # ---------------------------------------------------------------- CASUAL (server src/casual.js)
    def casual(self):
        """Open lobbies and mine: {'on', 'lobbies', 'lobby'}."""
        return self._req('GET', '/api/casual', auth=True, timeout=8)

    def casual_options(self):
        """What a lobby's host may pick: {'stages', 'cars', 'weather', 'times'}."""
        return self._req('GET', '/api/casual/options', timeout=8)

    def casual_create(self, body):
        return self._req('POST', '/api/casual/lobbies', body, auth=True)

    def casual_join(self, lobby_id=None, code=None):
        body = {}
        if lobby_id:
            body['id'] = int(lobby_id)
        if code:
            body['code'] = str(code)
        return self._req('POST', '/api/casual/join', body, auth=True)

    def casual_lobby(self, lobby_id):
        return self._req('GET', '/api/casual/lobbies/%d' % int(lobby_id), auth=True, timeout=6)

    def casual_ready(self, lobby_id, ready=True):
        return self._req('POST', '/api/casual/lobbies/%d/ready' % int(lobby_id), {'ready': bool(ready)}, auth=True)

    def casual_start(self, lobby_id):
        return self._req('POST', '/api/casual/lobbies/%d/start' % int(lobby_id), {}, auth=True)

    def casual_leave(self, lobby_id):
        return self._req('POST', '/api/casual/lobbies/%d/leave' % int(lobby_id), {}, auth=True)

    def casual_signal(self, lobby_id, to, data):
        """My side's link details for one member (copilotlink.py)."""
        return self._req('POST', '/api/casual/lobbies/%d/signal' % int(lobby_id), {'to': to, 'data': data}, auth=True, timeout=6)

    # ---------------------------------------------------------------- leagues (server src/leagues.js)

    def my_events(self):
        """The events of my leagues, open or coming soon, with my entry: {'now', 'events': [...]}."""
        return self._req('GET', '/api/me/events', auth=True)

    def leagues(self):
        """Every championship and rally, and mine (server src/leaguesapi.js GET /api/leagues): {public: [{id, name, about,
        official, owner, banner, members, events, openEvents, nextOpens}], private: [...] (asked to join), mine: [... with
        role, and the requests waiting in the ones I run], applied: [{id, status, at, again}] (my requests),
        applications: [{leagueId, league, steamId, name, message, at}] (the requests I answer), rallies, ...}."""
        return self._req('GET', '/api/leagues', auth=True)

    def league_join(self, league_id):
        """Join a public championship (POST /api/leagues/<id>/join). -> {id, joined}; ApiError when it refuses (full, banned
        from it, a private one: asked to join instead)."""
        return self._req('POST', '/api/leagues/%s/join' % league_id, {}, auth=True)

    def league_apply(self, league_id, message=''):
        """Ask to join a private championship, with a word to its admins (they answer in the inbox). -> {applied}."""
        return self._req('POST', '/api/leagues/%s/apply' % league_id, {'message': message or ''}, auth=True)

    def league_withdraw(self, league_id):
        """Take my request to join back. -> {withdrawn}."""
        return self._req('POST', '/api/leagues/%s/withdraw' % league_id, {}, auth=True)

    def league_answer(self, league_id, steam_id, accept):
        """A championship I run: a driver's request to join accepted or declined (they are told). -> {accepted} / {declined}."""
        return self._req('POST', '/api/leagues/%s/%s' % (league_id, 'accept' if accept else 'decline'),
                         {'steamId': str(steam_id)}, auth=True)

    def league_add(self, league_id, steam_id):
        """A championship I run: a driver put in straight away (they are told). -> {added}."""
        return self._req('POST', '/api/leagues/%s/add' % league_id, {'steamId': str(steam_id)}, auth=True)

    def rally_code(self, event_id, code):
        """A private rally's code: I'm in it (then it is mine to DRIVE). -> {joined, eventId}; a 403 for a wrong code."""
        return self._req('POST', '/api/events/%d/join' % int(event_id), {'code': code}, auth=True)

    def events_live(self):
        """Everyone on an event's stage now that we may see (WATCH's list): {now, drivers: [{kind, eventId, event,
        league, stageNo, stage, car, cars, rules, rally, steamId, name, country, look, progress, totalMs}]}."""
        return self._req('GET', '/api/events/live', auth=True, timeout=6)

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

    def league_start(self, event_id, car, at=None, server_at=None):
        """SS1 of an event started (the entry): {'started', 'car'}, or {'status': 'dnf', 'reason'} if it was before.
        at: when it started (ms): the same start sent again is no second start. server_at: the same on the server's
        clock (a ranked rally's session: its turn judges it, then {'slot': {startedAt}})."""
        body = dict({'car': car, 'at': at}, **({'serverAt': server_at} if server_at is not None else {}))
        return self._req('POST', '/api/events/%d/start' % int(event_id), body, auth=True)

    def league_begin(self, event_id, no, at=None, server_at=None):
        """Stage `no` (0 = SS1) of an event started: {'status': 'running'}, or 'dnf' if it had been started before
        (not this same start, `at`, sent again). server_at: as league_start's."""
        body = dict({'no': no, 'at': at}, **({'serverAt': server_at} if server_at is not None else {}))
        return self._req('POST', '/api/events/%d/begin' % int(event_id), body, auth=True)

    def league_stage(self, event_id, body):
        return self._req('POST', '/api/events/%d/stage' % int(event_id), body, auth=True)

    # ---------------------------------------------------------------- live rallies (server src/liverallies.js)

    def live_rallies(self):
        """The series and their sessions: {now, on, series: [{key, name, carClass, cars, rally, nextRally}], sessions:
        [{series, starts, signupOpens, firstStart, closes, phase, rally, signups, signedUp, car, eventId, entry}],
        live (the rules), pollS}."""
        return self._req('GET', '/api/liverallies', auth=True, timeout=10)

    def live_session(self, series, starts):
        """One session: its sign-ups, then its rally (event: as /api/me/events gives one), queues (one a stage, SS1's the
        start list), standings, me ({signedUp, car, next: my next slot}), pollS."""
        return self._req('GET', '/api/liverallies/%s/%d' % (series, int(starts)), auth=True, timeout=10)

    def live_signup(self, series, starts, car):
        return self._req('POST', '/api/liverallies/%s/%d/signup' % (series, int(starts)), {'car': car}, auth=True, timeout=10)

    def live_chat(self, series, starts, after=0):
        """A session's chat (its drivers only): {messages: [{id, steamId, name, body, at}], pollS}; after: the newest id
        already had (0: the latest lines)."""
        return self._req('GET', '/api/liverallies/%s/%d/chat?after=%d' % (series, int(starts), int(after or 0)),
                         auth=True, timeout=8)

    def live_chat_send(self, series, starts, body):
        """A line in a session's chat -> {message}; ApiError with the server's words (too long, too fast...)."""
        return self._req('POST', '/api/liverallies/%s/%d/chat' % (series, int(starts)), {'body': body}, auth=True,
                         timeout=8)

    def live_withdraw(self, series, starts):
        return self._req('POST', '/api/liverallies/%s/%d/withdraw' % (series, int(starts)), {}, auth=True, timeout=10)

    def live_queue(self, series, starts, no, finished_at=None):
        """Stage `no` - 1 finished: my slot on stage `no` ({now, slot: {no, at, moved, ...}})."""
        body = dict({'no': int(no)}, **({'finishedAt': finished_at} if finished_at is not None else {}))
        return self._req('POST', '/api/liverallies/%s/%d/queue' % (series, int(starts)), body, auth=True, timeout=10)

    def live_out(self, series, starts, no, reason):
        """A stage of my session driven outside it (before my start, in another mode, settings changed): my entry a
        DNF ({status, reason})."""
        return self._req('POST', '/api/liverallies/%s/%d/dnf' % (series, int(starts)), {'no': int(no), 'reason': reason},
                         auth=True, timeout=10)

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

    def league_missed(self, event_id, no, reason):
        """Stage `no` was driven without the app watching: retired under the event's retirement rule ({'done',
        'status', 'retired'}), or {'status': 'dnf', 'reason'} without it (server leaguesapi.js missed)."""
        return self._req('POST', '/api/events/%d/missed' % int(event_id), {'no': no, 'reason': reason}, auth=True)

    def league_dnf(self, event_id, no, reason, damage=None):
        body = {'no': no, 'reason': reason}
        if isinstance(damage, dict):                 # (the car where it ended: kept for a DNF the stewards take back)
            body['damage'] = damage
        return self._req('POST', '/api/events/%d/dnf' % int(event_id), body, auth=True)

    # ---------------------------------------------------------------- comments on runs (server src/comments.js)

    def comment(self, on, text):
        """My comment on a daily ('2026-11-15/1'), a time trial stage ('tt:2026-11-09/2') or a league event's stage
        ('event:12/0', 0 = SS1): {comment: {on, text, updated} | None}. '' takes it back. 409: not a run of mine, or
        too late."""
        return self._req('POST', '/api/comments', {'on': on, 'text': text}, auth=True)

    def my_comments(self, ons):
        """What I wrote on these: {on: text}."""
        q = urllib.parse.urlencode({'on': ','.join(ons)})
        return (self._req('GET', '/api/comments/mine?' + q, auth=True) or {}).get('comments') or {}

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

    def community(self):
        """The COMMUNITY page's list (community.py): {categories: [{id, name, items: [...]}]}."""
        return self._req('GET', '/api/community')

    def liveries(self):
        """COMMUNITY > LIVERIES (liveries.py, server src/liveries.js): the published liveries, my stars when signed in:
        {liveries: [{id, car, carName, title, author, shot, go, direct, stars, votes, mine, clicks, ...}], cars, limits}."""
        return self._req('GET', '/api/liveries', auth=True)

    def livery_vote(self, livery_id, stars):
        """My stars (1 to 5) for a livery -> {votes, stars, mine}."""
        return self._req('POST', '/api/liveries/%d/vote' % int(livery_id), {'stars': int(stars)}, auth=True)

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
