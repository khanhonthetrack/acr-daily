"""End to end for REPLAYS (not a unit test: run by hand, python tests/e2e_replays.py <dump.jsonl>, with the server's
harness running: node server/test/harness_replays_e2e.mjs <route.json>). The app's own code (Api, replays.Recorder and
its Sender, replayui.ReplayUI's polling, leagues.recover) against the worker's own code, a real run (a telemetry dump of
Wales Afon Bidno) fed at the harness's SPEED, and the ways a finish gets lost:

  A  an online rally's stage: the connection gone for 40 s mid-stage, the game loses the result (DNF "no official
     result"): the replay takes the DNF back, the rally goes on with the car as it crossed the line (leagues.recover)
  B  the daily: the game frozen at the finish line before the app saw its finish (DNF "lost the game"): taken back,
     the run on the board (the server's own reinstate)
  C  an online rally's stage: the finish got to the server, then the app crashed (no result ever sent): 30 minutes on,
     the replay stands in for it

Never the real APPDATA: ACR_DAILY_HOME is a temp folder."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

HOME = tempfile.mkdtemp(prefix='acr-e2e-')
os.environ['ACR_DAILY_HOME'] = HOME
SERVER = os.environ.get('E2E_SERVER', 'http://127.0.0.1:8797')
os.environ['ACR_DAILY_SERVER'] = SERVER
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acr_daily import leagues, replays, replayui  # noqa: E402
from acr_daily.api import Api  # noqa: E402
from acr_daily.telemetry import Replay  # noqa: E402

SPEED = float(os.environ.get('SPEED', 10))
replays.RETRY_S, replays.RETRY_MAX_S = 0.2, 1.0     # (the harness's clock runs SPEED times faster)
RESETS = 1                     # (the recorded run has one respawn, at 1:55: its judge counted it)
DAMAGE = {'Engine': 72.5, 'Bodywork': 55.0, 'Radiator': 100.0}
results = []


def harness(path, body=None):
    req = urllib.request.Request(SERVER + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'}, method='POST' if body is not None else 'GET')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def sql(q, *args):
    return harness('/__sql', {'sql': q, 'args': list(args)})


def check(name, ok, detail=''):
    results.append((name, bool(ok)))
    print(('PASS ' if ok else 'FAIL ') + name + ((': ' + str(detail)) if detail and not ok else ''))


class App(replayui.ReplayUI):
    """The app as far as its replays go (replayui.py): its settings, Api and Recorder; the window's parts stubbed."""

    class Root:
        def after(self, ms, fn=None):
            if fn is not None:
                threading.Thread(target=fn, daemon=True).start()

    def __init__(self):
        self.s = {'token': 'e2e0' * 16, 'steamId': '76561198000000002', 'name': 'Tester'}
        self.api = Api(self.s)
        self.root = self.Root()
        self.notes = []
        self.sub_l = type('L', (), {'configure': lambda _s, **kw: self.notes.append(kw.get('text'))})()
        self.replays = replays.Recorder(self.s, self.api, me=lambda: {'steamId': self.s['steamId'], 'name': 'Tester'},
                                        app_version='0.2.3-e2e', penalty=lambda: (0, False), damage=lambda: dict(DAMAGE))
        self.replay_asks, self._replay_polling = [], False

    def _notify(self, ok, title, text):
        self.notes.append('%s: %s' % (title, text))

    def poll(self):
        """replayui's poll, here and now (catch-up, what the server wants, the uploads)."""
        self._replay_polling = True
        self._replay_poll_bg()


def drive(app, frames, tag, down=None, stop_at=None, freeze_s=0.0):
    """The frames fed at SPEED (their own clock as 'now', the harness's clock as fast); tag(rec) when the stage clock
    starts; down: (from, to) stage clock ms with the connection gone; stop_at: the frames end there (the game frozen),
    the last one fed again for freeze_s of its time."""
    rec = app.replays
    t0, real0 = frames[0].t, time.monotonic()
    tagged, gone = False, False
    last = None
    for f in frames:
        if stop_at is not None and f.clock_ms > stop_at:
            break
        wait = (f.t - t0) / SPEED - (time.monotonic() - real0)
        if wait > 0:
            time.sleep(wait)
        if down:
            want = down[0] <= (f.clock_ms or 0) < down[1]
            if want != gone:
                harness('/__down', {'on': want})
                gone = want
        rec.feed(f, f.t)
        last = f
        if not tagged and rec.run is not None:
            tag(rec)
            tagged = True
    if gone:
        harness('/__down', {'on': False})
    t = last.t
    while freeze_s > 0:                             # (the game frozen: its last frame, again and again)
        t += 0.05
        freeze_s -= 0.05
        time.sleep(0.05 / SPEED)
        rec.feed(last, t)
    return last, t


def wait_sender(app, s=30):
    end = time.time() + s
    while time.time() < end and not app.replays.sender.idle():
        time.sleep(0.05)
    return app.replays.sender.idle()


def finish_of(frames):
    return max(f.clock_ms or 0 for f in frames)


def scenario_a(frames, ev_id):
    print('\nA: an online rally, the connection gone 40 s mid-stage, the game loses the result')
    app = App()
    ref = 'event:%d:0' % ev_id
    last, t = drive(app, frames, lambda rec: rec.tag('event', ref, 'E2E SS1', True), down=(60000, 100000))
    fin = finish_of(frames)
    app.replays.outcome('finished', {'clockMs': fin, 'resets': RESETS, 'totalMs': fin})
    app.replays.feed(None, t + 1)
    check('A: every commit reached the server, in order', wait_sender(app), '%d still queued' % len(app.replays.sender.q))
    check('A: the sender met the connection gone', app.replays.sender.failures > 0, app.replays.sender.failures)
    app.api.league_dnf(ev_id, 0, 'no official result from the game')   # (the app's own DNF: the game lost it)
    app.poll()
    e = sql('SELECT status, done, total_ms, damage FROM league_entries WHERE event_id = ? AND steam_id = ?', ev_id, app.s['steamId'])[0]
    check('A: the DNF taken back, the rally goes on at SS2', (e['status'], e['done']) == ('running', 1), e)
    check('A: its time: the finish (no penalty)', e['total_ms'] == fin, (e['total_ms'], fin))
    dmg = json.loads(e['damage'] or 'null')
    check('A: the car as it crossed the line kept', dmg == {'no': 0, 'parts': {'Engine': 72.5, 'Bodywork': 55}}, dmg)
    dec = sql('SELECT op, by FROM league_decisions WHERE event_id = ?', ev_id)
    check('A: the decision shown, by the replay check', [(d['op'], d['by']) for d in dec] == [('time', 'replay')], dec)
    check('A: the app told the driver', any('DNF taken back' in str(n) for n in app.notes), app.notes)
    # CONTINUE: the app's own recovery from the next stage with that car (the rally in the game gone: 'none')
    mine = next(x for x in app.api._req('GET', '/api/me/events', auth=True)['events'] if x['id'] == ev_id)
    rec = leagues.recover(mine, 'none', None)
    check('A: CONTINUE goes on from SS2 with that car', rec and rec['start'] == 1 and rec['damage'] == {'Engine': 72.5, 'Bodywork': 55}, rec)


def scenario_b(frames, today):
    print('\nB: the daily, the game frozen at the finish line before the app saw its finish')
    app = App()
    ref = '%s/1' % today
    fin = finish_of(frames)
    last, t = drive(app, frames, lambda rec: rec.tag('daily', ref, 'SS1', True), stop_at=fin, freeze_s=3.0)
    app.replays.outcome('dnf', {'clockMs': last.clock_ms, 'resets': RESETS, 'reason': 'lost the game (closed or frozen)'})
    app.replays.feed(None, t + 1)
    check('B: every commit reached the server', wait_sender(app))
    now = harness('/__now')['now']
    sql("""INSERT INTO runs (date, slot, steam_id, track, car, status, reason, clock_ms, resets, created, app_version)
           VALUES (?, 1, ?, 'Wales Afon Bidno', 'Mini Cooper S 1275', 'dnf', 'lost the game (closed or frozen)', ?, 0, ?, '0.2.3')""",
        today, app.s['steamId'], last.clock_ms, now)
    app.poll()
    r = sql("SELECT status, total_ms, clock_ms, flags FROM runs WHERE steam_id = ? AND date = ?", app.s['steamId'], today)[0]
    check('B: the run on the board', r['status'] == 'finished', r)
    check('B: its time: the clock where the game froze', r['total_ms'] == last.clock_ms, (r['total_ms'], last.clock_ms))
    check('B: flagged as the replay\'s', 'reinstated by replay' in (r['flags'] or ''), r['flags'])
    f = sql("SELECT verdict, action, report FROM replay_files WHERE kind = 'daily'")[0]
    check('B: the road says the line was reached', 'finish line reached as the road says' in f['report'], f['report'][:300])


def scenario_c(frames, ev_id):
    print('\nC: an online rally, the finish on the server, then the app crashed: no result ever sent')
    app = App()
    ref = 'event:%d:0' % ev_id
    last, t = drive(app, frames, lambda rec: rec.tag('event', ref, 'E2E SS1', True))
    fin = finish_of(frames)
    app.replays.outcome('finished', {'clockMs': fin, 'resets': RESETS, 'totalMs': fin})
    app.replays.feed(None, t + 1)
    wait_sender(app)
    # (the app gone; started again later: a new app, the replay on disk)
    app2 = App()
    app2.poll()
    e = sql('SELECT status, done FROM league_entries WHERE event_id = ?', ev_id)[0]
    check('C: nothing stands in before 30 minutes (its own result may still come)', (e['status'], e['done']) == ('running', 0), e)
    harness('/__skip', {'ms': 31 * 60000})
    app2.poll()
    e = sql('SELECT status, done, total_ms, damage FROM league_entries WHERE event_id = ?', ev_id)[0]
    check('C: the replay stood in: SS1 counted, the rally goes on', (e['status'], e['done'], e['total_ms']) == ('running', 1, fin), e)
    check('C: with the car as it crossed the line', json.loads(e['damage'] or '{}').get('no') == 0, e['damage'])



def scenario_d(frames, ev_id):
    print('\nD: an online rally, the connection down for the first 30 s of the stage, the game loses the result')
    app = App()
    ref = 'event:%d:0' % ev_id
    harness('/__down', {'on': True})
    last, t = drive(app, frames, lambda rec: rec.tag('event', ref, 'E2E SS1', True), down=(0, 30000))
    fin = finish_of(frames)
    app.replays.outcome('finished', {'clockMs': fin, 'resets': RESETS, 'totalMs': fin})
    app.replays.feed(None, t + 1)
    wait_sender(app)
    began = sql('SELECT begin_clock FROM replay_runs WHERE ref = ?', ref)[0]['begin_clock']
    check('D: followed from when the connection came back', 25000 <= began <= 40000, began)
    app.api.league_dnf(ev_id, 0, 'the game closed before saving its official result')
    app.poll()
    e = sql('SELECT status, done FROM league_entries WHERE event_id = ?', ev_id)[0]
    check('D: taken back by itself all the same', (e['status'], e['done']) == ('running', 1), e)


def scenario_e(frames, ev_id):
    print('\nE: an online rally, the connection down from 3:20 through the finish, the app closed; back 10 minutes later')
    app = App()
    ref = 'event:%d:0' % ev_id
    last, t = drive(app, frames, lambda rec: rec.tag('event', ref, 'E2E SS1', True), down=(200000, 10 ** 9))
    harness('/__down', {'on': True})
    fin = finish_of(frames)
    app.replays.outcome('finished', {'clockMs': fin, 'resets': RESETS, 'totalMs': fin})
    app.replays.feed(None, t + 1)
    time.sleep(0.5)
    app.replays.sender.q.clear()                        # (the app closed: its queue gone, the replay on disk)
    harness('/__down', {'on': False})
    harness('/__skip', {'ms': 10 * 60000})
    app2 = App()
    app2.api.league_dnf(ev_id, 0, 'no official result from the game')
    app2.poll()                                         # (catch-up from the file, then what the server wants)
    run = sql('SELECT fin_ms, json_array_length(commits) AS n FROM replay_runs WHERE ref = ?', ref)[0]
    check('E: the commits never sent went from the file, the finish with them', run['fin_ms'] == fin, run)
    f = sql('SELECT verdict, action, report FROM replay_files WHERE ref = ?', ref)
    check('E: its checks clean, but the finish came too late to take it back by itself',
          f and f[0]['verdict'] == 'clean' and f[0]['action'] == 'sent to review', f and (f[0]['verdict'], f[0]['action']))
    e = sql('SELECT status FROM league_entries WHERE event_id = ?', ev_id)[0]
    check('E: the DNF stays until the stewards decide', e['status'] == 'dnf', e)
    told = sql("SELECT body FROM messages WHERE kind = 'replay' AND ref = ?", 'event:%d' % ev_id)
    check('E: the stewards told, with the replay to watch', any('/r/' in m['body'] for m in told), told)


def main():
    dump = sys.argv[1]
    frames = Replay(dump).frames
    info = harness('/__now')
    print('harness:', info, '· frames:', len(frames), '· home:', HOME)
    scenario_a(frames, info['events']['lost'])
    scenario_b(frames, info['today'])
    scenario_c(frames, info['events']['missing'])
    scenario_d(frames, info['events']['start'])
    scenario_e(frames, info['events']['late'])
    bad = [n for n, ok in results if not ok]
    print('\n%d checks, %d failed%s' % (len(results), len(bad), (': ' + ', '.join(bad)) if bad else ''))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
