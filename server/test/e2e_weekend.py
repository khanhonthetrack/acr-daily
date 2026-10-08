"""End-to-end test of Rally Weekend dailies (the game's own time + penalty count) against a local server:

  npx wrangler dev --port 8791 --ip 127.0.0.1 --persist-to <fresh dir> --var OFFICIAL_FROM:2000-01-01
  python test/e2e_weekend.py http://127.0.0.1:8791 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars). test/e2e.py is the same for a server without OFFICIAL_FROM (the app timing the runs).
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
VERSION = re.search(r"__version__ = '([\d.]+)'", open(os.path.join(HERE, '..', '..', 'client', 'acr_daily', '__init__.py'),
                                                      encoding='utf-8').read()).group(1)
fails = 0


def call(method, path, body=None, token=None, admin=False):
    h = {'Content-Type': 'application/json', 'User-Agent': 'ACR-Daily/%s public' % VERSION}
    if token:
        h['Authorization'] = 'Bearer ' + token
    if admin:
        h['Authorization'] = 'Bearer ' + KEY
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=h,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if 'json' in r.headers.get('Content-Type', '') else raw
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def check(name, cond, info=''):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name + ('' if cond else '   ' + str(info)[:400]))
    fails += 0 if cond else 1


def login(steam_id, name):
    state = 'e2e-' + steam_id
    call('GET', '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name.replace(' ', '%20')))
    return call('GET', '/auth/poll?state=' + state)[1].get('token')


fx = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json')))
route, result = fx['route'], fx['result']
today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
check('route uploaded', call('POST', '/api/admin/route', {'track': 'Wales Afon Bidno', 'points': route,
                                                          'stageId': 'WelesS4HafrenSouthFullForward'}, admin=True)[0] == 200)
call('POST', '/api/admin/pool', {'track': 'Wales Afon Bidno', 'car': 'Mini Cooper S 1275'}, admin=True)

s, ch = call('GET', '/api/challenge/today')
check('the daily is a Rally Weekend', s == 200 and ch.get('mode') == 'weekend', ch.get('mode'))
check('...with the rules', ch.get('weekend') == {'penalty': 'light', 'respawn': True, 'damage': True,
                                                 'damageIntensity': 'light', 'wear': 'light', 'failures': 'off'},
      ch.get('weekend'))
check('...and nothing added per reset', ch.get('penaltyMs') == 0, ch.get('penaltyMs'))

t1, t2, t3 = login('76561190000000001', 'Test Driver'), login('76561190000000002', 'Rival Test'), \
    login('76561190000000003', 'Third Test')
# the real Wales run (stage clock 4:13.870, 1 reset), with the game's own result: 4:13.870 + 29 s
run = dict(result, challengeId=today, official={'timeMs': 253870, 'penaltyMs': 29000, 'splitsMs': [80000, 160000, 253870]})
s, r = call('POST', '/api/runs', run, t1)
check('a run with the game\'s result counts as its time + penalty', s == 200 and r.get('totalMs') == 282870, (s, r))
s, r = call('POST', '/api/runs', dict(result, challengeId=today), t2)
check('a finished run without the game\'s result is refused', s == 422 and 'official' in r.get('error', ''), (s, r))
s, r = call('POST', '/api/runs', dict(result, challengeId=today, resets=3, official={'timeMs': 250000, 'penaltyMs': 0}), t3)
check('resets add nothing: 4:10.000', s == 200 and r.get('totalMs') == 250000 and r.get('rank') == 1, (s, r))

s, b = call('GET', '/api/leaderboard')
fin = [e for e in b['entries'] if e.get('status') == 'finished']
check('board: Third 4:10.000, then Test Driver 4:42.870',
      [(e['name'], e['totalMs'], e['clockMs']) for e in fin] == [('Third Test', 250000, 250000), ('Test Driver', 282870, 253870)],
      [(e['name'], e['totalMs'], e['clockMs']) for e in fin])
check('the refused run is the rival\'s DNF on the board',
      any(e['name'] == 'Rival Test' and e['status'] == 'dnf' for e in b['entries']), b['entries'])
rid = [e for e in fin if e['name'] == 'Test Driver'][0]['runId']
check('run page loads', call('GET', '/run/%d' % rid)[0] == 200)
s, d = call('GET', '/api/runs/%d' % rid)
check('run detail: penalty = total - clock, nothing per reset', s == 200 and d['totalMs'] - d['clockMs'] == 29000 and
      d.get('penaltyMs') == 0, {k: d.get(k) for k in ('totalMs', 'clockMs', 'penaltyMs')})
s, r = call('POST', '/api/admin/runs/%d/fix' % rid, {'resets': 2, 'dryRun': True}, admin=True)
check('fix-run refuses a run with the game\'s result', s == 409, (s, r))
s, page = call('GET', '/')
check('website: the Rally Weekend rules, no +60 s', s == 200 and 'Rally Weekend' in page and '+60' not in page, s)
s, page = call('GET', '/guide')
check('guide: the Rally Weekend path, no +60 s', s == 200 and 'Rally Weekend' in page and '+60' not in page, s)
print('\n%d failed' % fails)
sys.exit(1 if fails else 0)
