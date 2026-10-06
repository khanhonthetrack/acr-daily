"""End-to-end test against a running server (local `npx wrangler dev` with DEV_LOGIN=1 in .dev.vars).

  python test/e2e.py http://127.0.0.1:8790 <ADMIN_KEY>

Uploads the Wales route from fixtures, puts it in the pool as the only challenge, signs in two dev
players, submits the real Wales run (clock 4:13.870 + 1 reset = 5:13.870) and checks the board.
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE, KEY = sys.argv[1].rstrip('/'), sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
# talks to the server as the current app does (the server takes runs only from MIN_APP_VERSION on)
VERSION = re.search(r"__version__ = '([\d.]+)'", open(os.path.join(HERE, '..', '..', 'client', 'acr_daily', '__init__.py'),
                                                      encoding='utf-8').read()).group(1)
fails = 0


def call(method, path, body=None, token=None, ua=None):
    h = {'Content-Type': 'application/json', 'User-Agent': ua or 'ACR-Daily/' + VERSION}
    if token:
        h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ct = r.headers.get('Content-Type', '')
            raw = r.read().decode()
            return r.status, json.loads(raw) if 'json' in ct else raw
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '   ' + str(info)[:300]))
    fails += 0 if cond else 1


def login(steam_id, name):
    state = 'e2e-' + steam_id
    call('GET', '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name.replace(' ', '%20')))
    s, r = call('GET', '/auth/poll?state=' + state)
    return r.get('token')


fx = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json')))
route, result = fx['route'], fx['result']
today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')

s, r = call('POST', '/api/admin/route', {'track': 'Wales Afon Bidno', 'points': route})
check('admin needs the key', s == 403, r)
req = urllib.request.Request(BASE + '/api/admin/route', data=json.dumps({'track': 'Wales Afon Bidno', 'points': route}).encode(),
                             headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}, method='POST')
with urllib.request.urlopen(req) as resp:
    r = json.loads(resp.read())
check('route uploaded', r.get('ok') and r['checkpoints'] > 10, r)
req = urllib.request.Request(BASE + '/api/admin/pool', data=json.dumps({'track': 'Wales Afon Bidno', 'car': 'Mini Cooper S 1275'}).encode(),
                             headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}, method='POST')
urllib.request.urlopen(req).close()

s, ch = call('GET', '/api/challenge/today')
check('today = Wales / Mini', s == 200 and ch['track'] == 'Wales Afon Bidno' and ch['car'] == 'Mini Cooper S 1275', ch)
check('challenge has the route and +60 s', len(ch.get('route') or []) == len(route) and ch['penaltyMs'] == 60000, ch.get('penaltyMs'))
def admin(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


s, r = admin('/api/admin/pool', {'track': 'Wales Afon Bidno', 'car': 'Other Car'})
check('pool refuses a car that is not in the game', s == 400, r)
# a second stage (random car) -> two dailies; today's daily 1 must not change
ober = json.load(open(os.path.join(HERE, 'fixtures', 'obersteigen.json')))
admin('/api/admin/route', {'track': 'Alsace Obersteigen', 'points': ober['route']})
s, r = admin('/api/admin/pool', {'track': 'Alsace Obersteigen'})
check('stage added with a random car', s == 200, r)
s, two = call('GET', '/api/challenges/today')
chs = two.get('challenges', [])
check('two dailies today, on different stages', len(chs) == 2 and chs[0]['track'] != chs[1]['track'], [c.get('track') for c in chs])
check('changing the pool does not swap a running daily', chs and chs[0]['track'] == 'Wales Afon Bidno' and chs[0]['car'] == 'Mini Cooper S 1275', chs[:1])
s, cars = call('GET', '/api/cars')
check('daily 2 has a random car from the game', len(chs) == 2 and chs[1]['car'] in [c['name'] for c in cars] and chs[1]['carId'], chs[1:] and chs[1]['car'])
check('every daily sets weather + time of day', all(c.get('weatherLabel') and c.get('timeLabel') for c in chs), [(c.get('weatherLabel'), c.get('timeLabel')) for c in chs])
s, again = call('GET', '/api/challenges/today')
check('dailies are stable', [(c['track'], c['car'], c['weather'], c['time']) for c in again['challenges']] ==
      [(c['track'], c['car'], c['weather'], c['time']) for c in chs], again)
s, r = call('GET', '/api/challenge?date=2099-01-01')
check('no peeking at future days', s == 403, r)

s, r = call('POST', '/api/runs', dict(result, challengeId=today))
check('submitting needs sign-in', s == 401, r)

t1 = login('76561190000000001', 'Test Driver')
t2 = login('76561190000000002', 'Rival Test')
check('dev sign-in gives tokens', bool(t1 and t2), (t1, t2))

s, r = call('POST', '/api/runs', dict(result, challengeId=today), t1)
check('real Wales run accepted', s == 200 and r.get('status') == 'finished' and r.get('totalMs') == 313870, r)
check('rank 1', r.get('rank') == 1, r)

# (the server takes the app's result as sent: its run checks DNF'd and flagged real runs, so they were removed)
s, r = call('POST', '/api/runs', {'challengeId': today, 'track': 'Wales Afon Bidno', 'car': 'Mini Cooper S 1275',
                                  'status': 'dnf', 'reason': 'restarted', 'clockMs': 30000, 'resets': 0}, t2)
check('DNF stored', s == 200 and r.get('status') == 'dnf', r)

s, r = call('POST', '/api/runs', dict(result, challengeId='2020-01-01'), t1)
check('old challenge refused', s == 409, r)

s, b = call('GET', '/api/leaderboard')
fin = [e for e in b['entries'] if e.get('status') == 'finished']
check('board: one valid entry, Test Driver 5:13.870',
      s == 200 and len(fin) == 1 and fin[0]['name'] == 'Test Driver' and fin[0]['totalMs'] == 313870, b)
check('first run counts: the rival''s first run (a DNF) is on the board',
      any(e['name'] == 'Rival Test' and e['status'] == 'dnf' for e in b['entries']), b['entries'])
check('stats count attempts and DNFs', b['stats']['attempts'] == 2 and b['stats']['dnfs'] == 1 and b['stats']['drivers'] == 2, b['stats'])

s, tr = call('GET', '/api/runs/%d/trace' % b['entries'][0]['runId'])
check('trace served for the live gap', s == 200 and len(tr['trace']) == len(result['trace']), s)

s, page = call('GET', '/')
check('website served, with the logo', s == 200 and 'aria-label="ACR Daily"' in page and 'Timing' in page, str(page)[:100])
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


try:
    resp = urllib.request.build_opener(_NoRedirect).open(BASE + '/discord', timeout=20)
    s, loc, body = resp.status, '', resp.read().decode()
except urllib.error.HTTPError as e:
    s, loc, body = e.code, e.headers.get('Location', ''), ''
check('/discord sends the app to the Discord invite (or says it opens soon)',
      (s == 302 and loc.startswith('https://discord.')) or (s == 200 and 'opens soon' in body), (s, loc))

# ---- run viewer, reports
run_id = b['entries'][0]['runId']
s, d = call('GET', '/api/runs/%d' % run_id)
check('run detail has sections and the menu name', s == 200 and len(d['sections']) == 10 and d.get('menuName'), d.get('menuName'))
check('real run is not under review', d['review'] is False and d['flags'] == [], d.get('flags'))
s, page = call('GET', '/run/%d' % run_id)
check('run viewer page served', s == 200 and '<html' in page.lower(), str(page)[:80])

s, r = call('POST', '/api/runs', dict(result, challengeId=today), t2)
check('the rival\'s later run is practice', s == 200 and r.get('counted') is False, r)
s, b2 = call('GET', '/api/leaderboard')
rival = [e for e in b2['entries'] if e['name'] == 'Rival Test']
check('a later run does not replace the first (rival stays DNF)', rival and rival[0]['status'] == 'dnf', rival)

for i in range(3):
    req = urllib.request.Request(BASE + '/api/runs/%d/report' % run_id, data=b'{"reason":"test"}',
                                 headers={'Content-Type': 'application/json', 'CF-Connecting-IP': '10.0.0.%d' % i}, method='POST')
    with urllib.request.urlopen(req) as resp:
        rep = json.loads(resp.read())
check('reports counted (one per person)', rep.get('reports') in (1, 3), rep)

# ---- live positions on the website map
s, r = call('POST', '/api/live', {'challengeId': today + '/1', 'x': -900.5, 'z': 1200.25, 'progress': 0.42,
                                  'totalMs': 95000, 'resets': 0, 'state': 'live'}, t1)
check('app can post its live position', s == 200, r)
s, r = call('POST', '/api/live', {'challengeId': today + '/1', 'x': 0, 'z': 0, 'progress': 0, 'totalMs': 0, 'state': 'live'})
check('live position needs sign-in', s == 401, r)
s, lv = call('GET', '/api/live?slot=1')
drv = [d for d in lv.get('drivers', []) if d['name'] == 'Test Driver']
check('website sees the driver on the stage', drv and drv[0]['progress'] == 0.42 and drv[0]['state'] == 'live', lv)
s, lv2 = call('GET', '/api/live?slot=2')
check('daily 2 map is separate', s == 200 and not [d for d in lv2['drivers'] if d['name'] == 'Test Driver'], lv2)
s, r = call('POST', '/api/runs', dict(result, challengeId=today + '/2'), t1)
check('a daily 1 run is refused on daily 2', s == 422, r)

# ---- first run counts: a second finished run is practice, an abandoned start is a DNF
s, r = call('POST', '/api/runs', dict(result, challengeId=today + '/1'), t1)
check('a second finished run is practice (not counted)', s == 200 and r.get('counted') is False, r)
t3 = login('76561190000000003', 'Gone Test')
import time as _t
s, r = call('POST', '/api/live', {'challengeId': today + '/1', 'x': 0.0, 'z': 0.0, 'progress': 0.1, 'totalMs': 9000, 'resets': 0,
                                  'state': 'live', 'startedAt': _t.time() - 7200, 'country': 'Vietnam'}, t3)
s, b3 = call('GET', '/api/leaderboard?slot=1')
gone = [e for e in b3['entries'] if e['name'] == 'Gone Test']
check('started and never finished (over an hour ago) = DNF', gone and gone[0]['status'] == 'dnf', gone)
check('country flag from the in-game nationality', gone and gone[0]['country'] == 'vn', gone)

# ---- stats page
s, st = call('GET', '/api/stats?date=%s&slot=1' % today)
check('stats: records and speed map', s == 200 and st['records']['topSpeed']['kmh'] > 100 and len(st['speedMap']) == 80, s)
s, pg = call('GET', '/stage/%s/1' % today)
check('stats page served', s == 200 and 'Stage Statistics' in pg, str(pg)[:60])

# ---- routes recorded automatically by players
forest = {'track': 'Alsace Forêt', 'car': 'Peugeot 208 Rally4', 'clockMs': 368568,
          'points': json.load(open(os.path.join(HERE, '..', '..', 'routes', 'Alsace Forêt.json')))['points']}
s, r = call('POST', '/api/routes/contribute', forest)
check('contributing needs sign-in', s == 401, r)
s, r = call('POST', '/api/routes/contribute', forest, t2)
check('a new stage is added from a clean run', s == 200 and r.get('added') is True, r)
s, r = call('POST', '/api/routes/contribute', forest, t1)
check('a second route for the same stage is ignored', s == 200 and r.get('added') is False, r)
s, routes = call('GET', '/api/routes')
check('the stage is listed', any(x['track'] == 'Alsace Forêt' for x in routes), routes)
bad = dict(forest, track='Alsace Saverne Test')
bad['points'] = [list(p) for p in forest['points']]
bad['points'][500][0] += 100
s, r = call('POST', '/api/routes/contribute', bad, t2)
check('a route with a reset jump is refused', s == 422, r)
s, r = call('POST', '/api/routes/contribute', dict(forest, track='Alsace Forêt de Saverne'), t2)
s2, routes = call('GET', '/api/routes')
check('the same stage reported under another name is not a second stage',
      s == 200 and r.get('added') is False and not any(x['track'] == 'Alsace Forêt de Saverne' for x in routes), r)

# ---- apps older than MIN_APP_VERSION (wrangler.toml)
s, r = call('POST', '/api/routes/contribute', dict(forest, track='Alsace Old App'), t2, ua='ACR-Daily/0.14.1')
check('an app older than the minimum is refused (426)', s == 426 and 'too old' in r.get('error', ''), r)

# ---- menu names
s, two = call('GET', '/api/challenges/today')
check('dailies carry the menu name', s == 200 and all(c.get('menuName') for c in two['challenges']),
      [c.get('menuName') for c in two.get('challenges', [])])

# ---- admin: a run's resets corrected
s, r = admin('/api/admin/runs/%d/fix' % run_id, {'resets': 2, 'dryRun': True})
s2, d = call('GET', '/api/runs/%d' % run_id)
check('fix-run --dry-run shows the change and writes nothing',
      s == 200 and r['after']['totalMs'] == 253870 + 120000 and d['resets'] == 1, (r, d.get('resets')))
# the stage clock at each reset: the small one an old app missed (put down 11 m on), and a jump
s, r = admin('/api/admin/runs/%d/fix' % run_id, {'resets': 2, 'at': [40368, 115851]})
s2, d = call('GET', '/api/runs/%d' % run_id)
check('fix-run sets resets, total and splits', s == 200 and d['resets'] == 2 and d['totalMs'] == 373870 and
      r['after']['splits'] != r['before']['splits'], (r, d.get('resets'), d.get('totalMs')))
check('...and the splits after the first reset include it', r.get('after', {}).get('splits', [0])[0] == r['before']['splits'][0] + 60000, r)
admin('/api/admin/runs/%d/fix' % run_id, {'resets': 1, 'at': [115851]})
s, r = admin('/api/admin/runs/%d/fix' % run_id, {'resets': 2, 'at': [5]})
check('fix-run refuses reset times that do not match', s == 400, r)

# ---- the daily report (no Claude key on a local server: the plain report from the same facts)
s, r = admin('/api/admin/recap', {'date': today, 'dryRun': True})
check('daily report preview from the day\'s facts', s == 200 and r.get('title') and 'Test Driver' in r.get('text', '') and
      r['facts']['stages'][0]['results'][0]['driver'] == 'Test Driver', r)
s, r = admin('/api/admin/recap', {'date': today})
check('no report is stored for a day that is not over', s == 400, r)
s, r = call('GET', '/api/recap?date=' + today)
check('...so there is none to read yet', s == 404, r)

print('\n%d failure(s)' % fails)
sys.exit(1 if fails else 0)
