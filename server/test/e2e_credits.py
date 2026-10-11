"""End-to-end test of credits (a prototype) against a local server with them on:

  npx wrangler dev --port 8794 --ip 127.0.0.1 --local-upstream 127.0.0.1:8794 --persist-to <fresh dir> --var CREDITS_FROM:2000-01-01
  python test/e2e_credits.py http://127.0.0.1:8794 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars). The daily bonus, stakes on the wager daily and a settlement with refunds, a league event's
entry fee (paid before the start, refunded when the event is deleted).
"""
import http.cookiejar
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
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else '  ' + str(info)[:300]))
    if not cond:
        fails += 1


def call(path, body=None, token=None, op=None, admin=False):
    h = {'User-Agent': APP_UA}
    if token:
        h['Authorization'] = 'Bearer ' + token
    if admin:
        h['Authorization'] = 'Bearer ' + KEY
    data = None
    if body is not None:
        data, h['Content-Type'] = json.dumps(body).encode(), 'application/json'
    req = urllib.request.Request(BASE + path, data=data, headers=h, method='POST' if body is not None else 'GET')
    try:
        with (op or urllib.request.build_opener()).open(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def app_user(steam_id, name):
    state = uuid.uuid4().hex
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name)).read()
    return json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())['token']


# today's dailies: three Wales stages in the pool
route = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))['route']
for track, sid in (('Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'), ('Wales Severn', 'WelesS4HafrenSouthFullReverse'),
                   ('Wales Cwmbiga', 'WelesS3HafrenNorthFullForward')):
    call('/api/admin/route', {'track': track, 'points': route, 'stageId': sid}, admin=True)
    call('/api/admin/pool', {'track': track, 'car': 'Hyundai i20 N Rally2'}, admin=True)
st, today = call('/api/challenges/today')
chs = {c['slot']: c for c in today['challenges']}
check('two dailies today', sorted(chs) == [1, 2], today)
check('SS2 is the wager daily, SS1 is free', chs[2].get('wager') == {'stake': 10} and 'wager' not in chs[1], chs.get(2, {}).get('wager'))
date = today['date']

a, b, c = app_user('76561190000000101', 'Ann'), app_user('76561190000000102', 'Ben'), app_user('76561190000000103', 'Cy')
st, r = call('/api/credits')
check('signed out: on, today\'s wager', r['enabled'] and r['wager']['stake'] == 10 and r['wager']['entrants'] == 0, r)
st, r = call('/api/credits', token=a)
check('a new driver: nothing yet, the welcome to claim', (r['balance'], r['claimable'], r['nextBonus']) == (0, True, 110), r)
st, r = call('/api/credits/claim', {}, token=a)
check('claimed: 100 + 10', r['claimed'] and r['amount'] == 110 and r['balance'] == 110 and r['streak'] == 1, r)
st, r = call('/api/credits/claim', {}, token=a)
check('once a day', not r['claimed'] and r['balance'] == 110, r)
call('/api/credits/claim', {}, token=b)

st, r = call('/api/credits/wager', {'slot': 1}, token=a)
check('no stakes on the free daily', st == 409, r)
st, r = call('/api/credits/wager', {'slot': 2}, token=c)
check('no credits, no stake', st == 402, r)
st, r = call('/api/credits/wager', {'slot': 2}, token=a)
check('Ann stakes 10', st == 200 and r['entered'] and r['balance'] == 100 and r['pot'] == 10, r)
st, r = call('/api/credits/wager', {'slot': 2}, token=a)
check('...once', r.get('already') and r['balance'] == 100 and r['pot'] == 10, r)
call('/api/credits/wager', {'slot': 2}, token=b)
st, r = call('/api/credits/wager?date=%s&slot=2' % date)
check('the website\'s wager line: two in, pot 20', (r['entrants'], r['pot']) == (2, 20), r)
# Cy claims, then starts SS2 (a live position from the app): too late to stake
call('/api/credits/claim', {}, token=c)
st, _ = call('/api/live', {'challengeId': chs[2]['id'], 'x': 1, 'z': 1, 'progress': 0.01, 'totalMs': 1000, 'resets': 0,
                           'state': 'live', 'startedAt': time.time()}, token=c)
st, r = call('/api/credits/wager', {'slot': 2}, token=c)
check('no stake once the daily is started', st == 409 and 'started' in r.get('error', ''), (st, r))

# settled now (a local server's admin): nobody of the two finished, so both get their stake back
st, r = call('/api/admin/credits-settle', {'date': date, 'slot': 2}, admin=True)
check('settled: refunds', st == 200 and r.get('payouts') == {'76561190000000101': 10, '76561190000000102': 10}, r)
st, r = call('/api/admin/credits-settle', {'date': date, 'slot': 2}, admin=True)
check('...once', r == {'done': True}, r)
st, r = call('/api/credits', token=a)
check('Ann has her stake back', r['balance'] == 110 and r['ledger'][0]['kind'] == 'wager-refund', r['ledger'][:2])

# ---- a league event's entry fee
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
op.open(BASE + '/login?next=/leagues&dev=76561190000000100&name=Boss').read()
st, lg = call('/api/leagues', {'name': 'Fee League', 'public': True}, op=op)
call('/api/leagues/%s/join' % lg['id'], {}, token=a)
cat = call('/api/catalog')[1]
check('the builder knows credits are on', cat['credits'] is True)
wales = [s['track'] for s in next(x for x in cat['rallies'] if x['name'] == 'Wales')['stages']]
now = int(time.time() * 1000)
ev = {'name': 'Paid Round', 'rally': 'Wales', 'car': 'Hyundai i20 N Rally2', 'stages': [{'track': wales[0], 'day': 1, 'weather': 'Clear', 'time': '09:00'}],
      'opens': now - 60000, 'closes': now + 86400000, 'fee': 25}
st, e = call('/api/leagues/%s/events' % lg['id'], ev, op=op)
eid = e['id']
st, r = call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'}, token=a)
check('no start before the fee is paid', st == 402, r)
st, r = call('/api/events/%d/enter' % eid, {}, token=a)
check('Ann pays 25', st == 200 and r['paid'] and r['pot'] == 25 and r['balance'] == 85, r)
st, r = call('/api/events/%d/enter' % eid, {}, token=a)
check('...once', r.get('already') and r['pot'] == 25, r)
st, r = call('/api/me/events', token=a)
mine = next(x for x in r['events'] if x['id'] == eid)
check('the app sees the fee, the pot and that it is paid', (mine['fee'], mine['pot'], mine['paid']) == (25, 25, True), mine)
check('then the start', call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'}, token=a)[1].get('started'))
st, r = call('/api/events/%d/edit' % eid, dict(ev, fee=50), op=op)
check('no fee change once paid (or started)', st == 200 and r.get('limited') or st == 400, r)
st, r = call('/api/events/%d/delete' % eid, {}, op=op)
check('the event deleted: fees refunded', r == {'deleted': True, 'refunded': 1}, r)
check('Ann has her 25 back', call('/api/credits', token=a)[1]['balance'] == 110)

print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
