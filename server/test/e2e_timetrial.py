"""End-to-end test of the weekly time trial (src/timetrial.js) against a local server with it and credits on:

  npx wrangler dev --port 8795 --ip 127.0.0.1 --local-upstream 127.0.0.1:8795 --persist-to <fresh dir> \
      --var TIME_TRIAL_FROM:2000-01-03 --var CREDITS_FROM:2000-01-01
  python test/e2e_timetrial.py http://127.0.0.1:8795 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars.) This week's two stages; runs refused without an entry; the entry fee taken once; as many
runs as one likes, the best on the board with the prize it pays now; the leader's trace for the app's ghost; the page;
an admin taking a run off; the week settled once (prizes, a refund, the notices in the inbox).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE, KEY = sys.argv[1].rstrip('/'), sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
APP_UA = 'ACR-Daily/9.9.9 public'
fails = 0


def check(name, cond, info=''):
    global fails
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else '  ' + str(info)[:400]))
    if not cond:
        fails += 1


def call(path, body=None, token=None, admin=False, ua=APP_UA):
    h = {'User-Agent': ua}
    if token:
        h['Authorization'] = 'Bearer ' + token
    if admin:
        h['Authorization'] = 'Bearer ' + KEY
    data = None
    if body is not None:
        data, h['Content-Type'] = json.dumps(body).encode(), 'application/json'
    req = urllib.request.Request(BASE + path, data=data, headers=h, method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw or 'null') if 'json' in r.headers.get('Content-Type', '') else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def app_user(steam_id, name):
    state = uuid.uuid4().hex
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name)).read()
    return json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())['token']


fx = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))
route = fx['route']
for track, sid in (('Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'), ('Wales Severn', 'WelesS4HafrenSouthFullReverse'),
                   ('Wales Cwmbiga', 'WelesS3HafrenNorthFullForward'), ('Wales Dyfi', 'WelesS3HafrenNorthFullReverse')):
    call('/api/admin/route', {'track': track, 'points': route, 'stageId': sid}, admin=True)
    call('/api/admin/pool', {'track': track}, admin=True)

ids = ['76561190000000201', '76561190000000202', '76561190000000203', '76561190000000204']
a, b, c, d = (app_user(s, n) for s, n in zip(ids, ('Ann', 'Ben', 'Cy', 'Dee')))
for t in (a, b, c, d):
    call('/api/credits/claim', {}, token=t)                  # (the welcome and daily bonus: 100 each)

print('this week\'s stages')
st, tt = call('/api/tt', token=a)
check('/api/tt answers', st == 200 and tt.get('on') is True, (st, tt))
stages = {s['slot']: s for s in tt.get('stages') or []}
check('two stages, each with its route, the Rally Weekend rules and the fee', sorted(stages) == [1, 2] and
      all(s.get('route') and s['mode'] == 'weekend' and s['fee'] == 20 for s in stages.values()), tt)
check('two different stages and cars', stages[1]['track'] != stages[2]['track'] and stages[1]['car'] != stages[2]['car'])
check('the week: Monday to Monday', tt['endsAt'] - tt['startsAt'] == 7 * 86400000 and
      time.gmtime(tt['startsAt'] / 1000).tm_wday == 0, tt)
check('not entered yet', stages[1]['me'] == {'entered': False, 'bestMs': None, 'runs': 0}, stages[1].get('me'))
st, lite = call('/api/tt?lite=1')
check('lite: no routes', st == 200 and all('route' not in s for s in lite['stages']), st)
s1 = stages[1]


def run(token, total, slot=1, pen=0, started=None, **kw):
    s = stages[slot]
    body = dict(fx['result'], challengeId=s['id'], track=s['track'], car=s['car'], status='finished', resets=0, penaltyMs=0,
                clockMs=total - pen, totalMs=total, official={'timeMs': total - pen, 'penaltyMs': pen},
                startedAt=started or time.time())
    body.update(kw)
    return call('/api/tt/runs', body, token=token)


print('entering')
st, r = run(a, 200000)
check('a run without an entry is refused ("invalid": the app drops it)', st == 402 and r['error'].startswith('invalid run'), (st, r))
st, r = call('/api/tt/enter', {'slot': 1}, token=a)
check('entered: the fee taken', st == 200 and r['entered'] and r['balance'] == 80 and r['pot'] == 20, (st, r))
st, r = call('/api/tt/enter', {'slot': 1}, token=a)
check('entering again takes nothing', st == 200 and r.get('already') and r['balance'] == 80, (st, r))
for t in (b, c, d):
    call('/api/tt/enter', {'slot': 1}, token=t)
st, r = call('/api/tt/enter', {'slot': 1, 'week': '2000-01-03'}, token=a)
check('only this week takes entries', st == 409, (st, r))
st, cr = call('/api/credits', token=a)
check('the credits history says so', any(x['kind'] == 'tt-fee' and x['label'] == 'Time trial entry' and x['delta'] == -20
                                         for x in cr.get('ledger') or []), cr.get('ledger'))

print('hotlapping')
time.sleep(1)
st, r = run(a, 200000)
check('a first time: on the board', st == 200 and r['best'] and r['rank'] == 1, (st, r))
st, r = run(a, 205000)
check('a slower one changes nothing', st == 200 and not r['best'] and r['bestMs'] == 200000 and r['runs'] == 2, (st, r))
st, r = run(a, 196000, pen=2000)
check('a faster one is the new best', st == 200 and r['best'] and r['improvedMs'] == 4000, (st, r))
best_a = r.get('id')
check('B and C set times', run(b, 190000)[0] == 200 and run(c, 230000)[0] == 200)
st, r = run(b, 150000, car='Not The Car')
check('another car is refused', st == 422, (st, r))
st, r = run(b, 150000, status='dnf', official=None)
check('a DNF is not taken', st == 422, (st, r))
st, r = run(b, 150000, slot=2)
check('TT2 is entered on its own', st == 402, (st, r))
st, board = call('/api/tt/board?week=%s&slot=1' % tt['week'])
check('the board: each driver\'s best, fastest first', st == 200 and [(e['name'], e['totalMs']) for e in board['entries']] ==
      [('Ben', 190000), ('Ann', 196000), ('Cy', 230000)], board)
check('with their runs and penalties', [e['runs'] for e in board['entries']] == [1, 3, 1] and
      board['entries'][1]['clockMs'] == 194000, board.get('entries'))
check('the prizes as the pot stands: 2 places of 3 (Dee, no time, not in the field)',
      [e['prize'] for e in board['entries']] == [34, 26, 0] and board['stats']['pot'] == 80 and board['stats']['paidPlaces'] == 2, board)
check('splits for the split standings', all(isinstance(e.get('splits'), list) and len(e['splits']) == 3 for e in board['entries']))
st, tr = call('/api/tt/runs/%s/trace' % board['entries'][0]['runId'])
check('the leader\'s trace, for the app\'s ghost', st == 200 and len(tr.get('trace') or []) > 100, st)
st, me = call('/api/tt?lite=1', token=a)
check('my side: entered, my best, my runs', me['stages'][0]['me'] == {'entered': True, 'bestMs': 196000, 'runs': 3}, me['stages'][0])

print('the page')
st, page = call('/tt', ua='Mozilla/5.0')
check('/tt is a page', st == 200 and 'Time trial' in page and '/api/tt' in page, st)
st, home = call('/', ua='Mozilla/5.0')
check('the home page links to it', st == 200 and 'href="/tt"' in home, st)

print('an admin takes a run off')
st, r = call('/api/admin/tt/runs/%s/reject' % best_a, {'reason': 'checking'}, admin=True)
check('rejected', st == 200, (st, r))
st, board = call('/api/tt/board?week=%s&slot=1' % tt['week'])
check('Ann\'s next best counts', [e['totalMs'] for e in board['entries'] if e['name'] == 'Ann'] == [200000], board)
st, r = call('/api/admin/tt/runs/999999/reject', {}, admin=True)
check('an unknown run: 404', st == 404, (st, r))

print('the week settles')
end = tt['endsAt']
st, r = call('/api/admin/tt-tick', {'now': end + 30 * 60000}, admin=True)
check('not before an hour after the close', st == 200 and [x for x in r['settled'] if x['week'] == tt['week']] == [], r)
st, r = call('/api/admin/tt-tick', {'now': end + 2 * 3600000}, admin=True)
mine = [x for x in r.get('settled') or [] if x['week'] == tt['week']]
check('settled: both stages', st == 200 and sorted(x['slot'] for x in mine) == [1, 2], r)
paid = (mine[0] if mine and mine[0]['slot'] == 1 else (mine[1] if len(mine) > 1 else {})).get('paid') or {}
check('prizes and the refund', paid == {ids[1]: 34, ids[0]: 26, ids[3]: 20}, paid)
bal = [call('/api/credits', token=t)[1]['balance'] for t in (a, b, c, d)]
check('the balances', bal == [106, 114, 80, 100], bal)
st, r = call('/api/admin/tt-tick', {'now': end + 3 * 3600000}, admin=True)
check('once only', [x for x in r['settled'] if x['week'] == tt['week']] == [], r)
st, inbox = call('/api/inbox', token=a)
note = next((n for n in inbox.get('notices') or [] if n['kind'] == 'tt'), None)
check('a notice in the inbox, to the week\'s page', note and note['ref'] == 'tt:' + tt['week'] and 'P2 of 3' in note['body'] and
      'Prize: 26 credits' in note['body'], note)
st, inbox = call('/api/inbox', token=d)
note = next((n for n in inbox.get('notices') or [] if n['kind'] == 'tt'), None)
check('no time set: the fee is back', note and 'entry fee of 20 credits is back' in note['body'], note)
st, board = call('/api/tt/board?week=%s&slot=1' % tt['week'])
check('the board says what was paid', board.get('settled') and [e['prize'] for e in board['entries']] == [34, 26, 0], board)

print('FAILED: %d' % fails if fails else 'all passed')
sys.exit(1 if fails else 0)
