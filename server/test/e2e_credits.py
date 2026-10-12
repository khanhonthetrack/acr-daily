"""End-to-end test of credits (a prototype) against a local server with them on:

  npx wrangler dev --port 8794 --ip 127.0.0.1 --local-upstream 127.0.0.1:8794 --persist-to <fresh dir> --var CREDITS_FROM:2000-01-01 --var OFFICIAL_FROM:
  python test/e2e_credits.py http://127.0.0.1:8794 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars; OFFICIAL_FROM empty: the app's own times count, so a test run needs no game save).
The daily and welcome bonus (for every driver signed in), the free daily's bonus as its run
comes in (and back when an admin rejects it), the wager daily driven only with a stake (runs and live positions without
one refused, old apps told to update) and its settlement with the house's stake and refunds, leagues taking no credits,
and the shop (looks bought and worn, shown on the timing sheets and the live map).
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


def call(path, body=None, token=None, op=None, admin=False, ua=APP_UA):
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
        with (op or urllib.request.build_opener()).open(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def app_user(steam_id, name):
    state = uuid.uuid4().hex
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name)).read()
    return json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())['token']


# today's dailies: three Wales stages in the pool
fx = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))
route = fx['route']
for track, sid in (('Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'), ('Wales Severn', 'WelesS4HafrenSouthFullReverse'),
                   ('Wales Cwmbiga', 'WelesS3HafrenNorthFullForward')):
    call('/api/admin/route', {'track': track, 'points': route, 'stageId': sid}, admin=True)
    call('/api/admin/pool', {'track': track, 'car': 'Hyundai i20 N Rally2'}, admin=True)
st, today = call('/api/challenges/today')
chs = {c['slot']: c for c in today['challenges']}
check('two dailies today', sorted(chs) == [1, 2], today)
check('SS2 is the wager daily, SS1 is free', chs[2].get('wager') == {'stake': 100} and 'wager' not in chs[1], chs.get(2, {}).get('wager'))
date = today['date']

a, b, c = app_user('76561190000000101', 'Ann'), app_user('76561190000000102', 'Ben'), app_user('76561190000000103', 'Cy')


def run(token, slot, status='finished', total=None, started=None, ua=APP_UA):
    """A run on today's daily, as the app sends it (the app's own time: OFFICIAL_FROM is empty)."""
    ch = chs[slot]
    times = {'clockMs': total - 60000, 'totalMs': total} if total else {}   # (the fixture's run has one reset: +60 s)
    return call('/api/runs', dict(fx['result'], challengeId='%s/%d' % (date, slot), track=ch['track'], car=ch['car'], status=status,
                                  reason='' if status == 'finished' else 'retired', startedAt=started or time.time(), **times),
                token=token, ua=ua)


def live(token, slot, started=None, ua=APP_UA):
    """The app's live position on a daily: the server's record of the driver starting it."""
    return call('/api/live', {'challengeId': chs[slot]['id'], 'x': 1, 'z': 1, 'progress': 0.01, 'totalMs': 1000, 'resets': 0,
                              'state': 'live', 'startedAt': started or time.time()}, token=token, ua=ua)


def report(run_id, token):
    """A driver's report of a run (a note for the admin: it changes nothing by itself)."""
    return call('/api/runs/%d/report' % run_id, {'reason': 'test'}, token=token)


def settle(slot):
    return call('/api/admin/credits-settle', {'date': date, 'slot': slot}, admin=True)


ANN, BEN, CY, DEE, EVE, FAY = ('76561190000000101', '76561190000000102', '76561190000000103', '76561190000000104',
                                '76561190000000105', '76561190000000106')
OLD_UA = 'ACR-Daily/0.0.8 public'          # older than CREDITS_MIN_APP (wrangler.toml): it doesn't know about stakes


st, r = call('/api/credits')
check('signed out: on, today\'s wager', r['enabled'] and r['wager']['stake'] == 100 and r['wager']['entrants'] == 0, r)
st, r = call('/api/credits', token=a)
check('a new driver: welcome + daily to claim at once (no finished run needed)', (r['balance'], r['earning'], r['claimable'], r['nextBonus']) == (0, True, True, 100), r)
check('...and in the website\'s header', call('/api/me', token=a)[1].get('credits') == {'balance': 0, 'claimable': True})
st, r = run(a, 1)
check('Ann finishes SS1: +50 as the run comes in', r.get('status') == 'finished' and r.get('credits') == 50, r)
st, r = run(a, 1)
check('...not for a practice run', r.get('counted') is False and 'credits' not in r, r)
st, r = call('/api/credits', token=a)
check('the SS1 bonus in, welcome + daily still to claim', (r['balance'], r['earning'], r['claimable'], r['nextBonus']) == (50, True, True, 100), r)
st, r = call('/api/credits/claim', {}, token=a)
check('claimed: 50 + 50', r['claimed'] and r['amount'] == 100 and r['welcome'] == 50 and r['balance'] == 150 and r['streak'] == 1, r)
st, r = call('/api/credits/claim', {}, token=a)
check('once a day', not r['claimed'] and r['balance'] == 150, r)
check('...the header: claimed', call('/api/me', token=a)[1].get('credits') == {'balance': 150, 'claimable': False})
check('the ledger, newest first: welcome, daily, finish',[x['kind'] for x in call('/api/credits', token=a)[1]['ledger']] == ['welcome', 'daily', 'finish'])
run(b, 1)
call('/api/credits/claim', {}, token=b)

st, r = call('/api/credits/wager', {'slot': 1}, token=a)
check('no stakes on the free daily', st == 409, r)
st, r = call('/api/credits/wager', {'slot': 2}, token=c)
check('no credits, no stake', st == 402, r)
st, r = run(a, 2, total=280000)
check('no stake: SS2\'s run refused (and the app drops it)', st == 402 and r['error'].startswith('invalid run'), (st, r))
st, r = live(a, 2)
check('...and its live position', st == 402, (st, r))
st, r = call('/api/credits/wager', {'slot': 2}, token=a)
check('Ann stakes 100', st == 200 and r['entered'] and r['balance'] == 50 and r['pot'] == 100, r)
st, r = call('/api/credits/wager', {'slot': 2}, token=a)
check('...once', r.get('already') and r['balance'] == 50 and r['pot'] == 100, r)
call('/api/credits/wager', {'slot': 2}, token=b)
st, r = call('/api/credits/wager?date=%s&slot=2' % date)
check('the website\'s wager line: two in, pot 200 (the house\'s 100 on top)', (r['entrants'], r['pot'], r['stake']) == (2, 200, 100), r)
st, r = live(a, 2, ua=OLD_UA)
check('an app older than CREDITS_MIN_APP: told to update for SS2', st == 426 and 'wager daily' in r['error'], (st, r))
st, r = run(a, 2, total=280000, ua=OLD_UA)
check('...its run too', st == 426, (st, r))
check('...SS1 as before', run(a, 1, ua=OLD_UA)[0] == 200)
# Cy: a DNF on SS1; the welcome and daily bonus all the same; a practice run after it earns nothing
run(c, 1, 'dnf')
st, r = call('/api/credits/claim', {}, token=c)
check('a DNF: welcome + daily all the same, one stake', r['claimed'] and r['welcome'] == 50 and r['balance'] == 100, r)
st, r = run(c, 1)
check('...a practice run to the finish (not on the board, no bonus)', r.get('status') == 'finished' and r.get('counted') is False and 'credits' not in r, r)
st, r = live(c, 2)
check('Cy on SS2 without a stake: refused, nothing recorded', st == 402, (st, r))
st, r = call('/api/credits/wager', {'slot': 2}, token=c)
check('...so he can still stake (his last 100)', st == 200 and r['balance'] == 0, (st, r))
st, r = call('/api/credits/wager', {'slot': 2, 'date': '2000-01-01'}, token=a)
check('a stake names its day: not today\'s, refused', st == 409, (st, r))

# Dee drove SS2 before staking (no live position taken without a stake), then her start and her fast run arrive:
# refused. Eve stakes and never drives. Fay stakes and drives with the app offline: the server never saw her on stage.
d, e, f = app_user(DEE, 'Dee'), app_user(EVE, 'Eve'), app_user(FAY, 'Fay')
for t in (d, e, f):
    run(t, 1)
    call('/api/credits/claim', {}, token=t)
    check('stakes', call('/api/credits/wager', {'slot': 2}, token=t)[1].get('entered'))
st, r = live(d, 2, time.time() - 600)
check('Dee\'s start from before her stake: refused', st == 409 and 'before your stake' in r['error'], (st, r))
st, r = run(d, 2, total=240000, started=time.time() - 600)
check('...her run too', st == 409 and r['error'].startswith('invalid run'), (st, r))
st, r = run(f, 2, total=200000)
check('Fay\'s run the server never saw on stage: refused', st == 409 and 'did not see this run' in r['error'], (st, r))
# Ann and Ben start SS2 after staking and finish: Ann 5:00, Ben 5:10; Cy retires
for t in (a, b, c):
    check('live on SS2 with a stake', live(t, 2)[0] == 200)
for t, total, status in ((a, 300000, 'finished'), (b, 310000, 'finished'), (c, None, 'dnf')):
    check('SS2 run in', run(t, 2, status, total=total)[1].get('status') == status)
board2 = call('/api/leaderboard?date=%s&slot=2' % date)[1]
check('SS2\'s board: only the drivers who staked', [x['steamId'] for x in board2['entries']] == [ANN, BEN, CY], board2['entries'])
ann_run = next(x for x in board2['entries'] if x['steamId'] == ANN)['runId']
for t in (d, e, f):                       # (drivers who finished SS1)
    check('a driver reports Ann\'s run', report(ann_run, t)[0] == 200)
board2 = call('/api/leaderboard?date=%s&slot=2' % date)[1]
check('reports change nothing: no "under review" on the board',
      all('review' not in x for x in board2['entries']) and [x['steamId'] for x in board2['entries']] == [ANN, BEN, CY], board2['entries'][:3])
st, r = settle(2)
# three stakes count, the house's makes four: the top two get 200; Dee, Eve and Fay never drove it: theirs back
check('settled: Ann and Ben 200 each, Cy (DNF) 0; the stakes never driven back',
      r.get('payouts') == {ANN: 200, BEN: 200, CY: 0, DEE: 100, EVE: 100, FAY: 100}, r)
st, r = settle(2)
check('...once', r == {'done': True}, r)
st, r = settle(1)
check('the free daily has nothing to settle (paid as its runs came in)', r == {'done': True}, r)
st, r = call('/api/credits', token=a)
check('Ann: 150 - 100 + 200', r['balance'] == 250 and r['ledger'][0]['kind'] == 'wager-win', r['ledger'][:2])
notes = {who: call('/api/credits', token=t)[1]['ledger'][0] for who, t in (('Dee', d), ('Eve', e), ('Fay', f))}
check('the refunds say why', [n['note'] for n in notes.values()] == ['not started'] * 3, notes)

# an admin rejects Ben's SS1 run (his result): its bonus goes back, once
board1 = call('/api/leaderboard?date=%s&slot=1' % date)[1]
ben_run = next(x for x in board1['entries'] if x['steamId'] == BEN)['runId']
for _ in range(2):
    call('/api/admin/runs/%d/reject' % ben_run, {'reason': 'test'}, admin=True)
st, r = call('/api/credits', token=b)
check('Ben\'s SS1 run rejected: its 50 taken back, once', r['balance'] == 200 and [(x['kind'], x['delta']) for x in r['ledger'][:2]] ==
      [('finish-back', -50), ('wager-win', 200)], r['ledger'][:3])

# ---- leagues are free: an event made with a fee in its request asks for none
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
op.open(BASE + '/login?next=/leagues&dev=76561190000000100&name=Boss').read()
st, lg = call('/api/leagues', {'name': 'Free League', 'public': True}, op=op)
call('/api/leagues/%s/join' % lg['id'], {}, token=a)
cat = call('/api/catalog')[1]
check('the event builder offers no entry fee', 'credits' not in cat, list(cat))
wales = [s['track'] for s in next(x for x in cat['rallies'] if x['name'] == 'Wales')['stages']]
now = int(time.time() * 1000)
ev = {'name': 'Free Round', 'rally': 'Wales', 'car': 'Hyundai i20 N Rally2', 'stages': [{'track': wales[0], 'day': 1, 'weather': 'Clear', 'time': '09:00'}],
      'opens': now - 60000, 'closes': now + 86400000, 'fee': 25}
st, e = call('/api/leagues/%s/events' % lg['id'], ev, op=op)
st, r = call('/api/events/%d/start' % e['id'], {'car': 'Hyundai i20 N Rally2'}, token=a)
check('a league event starts with no fee, and takes no credits', r.get('started') and call('/api/credits', token=a)[1]['balance'] == 250, r)
check('...nor shows one', 'fee' not in call('/api/events/%d' % e['id'], op=op)[1])

# ---- the shop: looks bought with credits, worn on the timing sheets and the live map (Ann 250, Ben 200 by now)
st, r = call('/api/shop')
check('the shop: open, its looks, nobody signed in', r['enabled'] and not r['signedIn'] and len(r['items']) > 20, r.get('enabled'))
st, r = call('/api/shop/buy', {'item': 'color:gold'}, token=a)
check('Gold is 400: Ann has 250', st == 402 and 'you have 250' in r['error'], (st, r))
st, r = call('/api/shop/buy', {'item': 'color:sky'}, token=a)
check('Ann buys Sky (250), worn at once', st == 200 and r['balance'] == 0 and r['worn']['color'] == 'color:sky', r)
st, r = call('/api/shop/buy', {'item': 'color:sky'}, token=a)
check('...once', r.get('already') and r['balance'] == 0, r)
mine = call('/api/credits', token=a)[1]['ledger'][0]
check('...in her history', (mine['kind'], mine['delta'], mine['note'], mine['label']) == ('shop', -250, 'Sky', 'Shop'), mine)
ann_on = lambda b: next(x for x in b['entries'] if x['steamId'] == ANN)
board1 = call('/api/leaderboard?date=%s&slot=1' % date)[1]
check('the timing sheet shows her colour at once', ann_on(board1).get('look') == {'color': '#5BA8FF'}, ann_on(board1))
st, r = call('/api/shop/wear', {'kind': 'frame', 'item': 'frame:gold'}, token=a)
check('nothing worn that was not bought', st == 403, (st, r))
st, r = call('/api/shop/buy', {'item': 'badge:fire'}, token=b)
check('Ben buys a badge with his last 200', st == 200 and r['balance'] == 0 and r['worn']['badge'] == 'badge:fire', r)
live(b, 2)
drivers = call('/api/live?date=%s&slot=2' % date)[1]['drivers']
check('the live map shows his badge', next(x for x in drivers if x['steamId'] == BEN).get('look') == {'badge': '🔥'}, drivers)
st, r = call('/api/shop/wear', {'kind': 'color', 'item': None}, token=a)
check('Ann takes her colour off', st == 200 and r['worn']['color'] is None, r)
check('...and the sheet is plain again', 'look' not in ann_on(call('/api/leaderboard?date=%s&slot=1' % date)[1]))
st, r = call('/api/shop/wear', {'kind': 'color', 'item': 'color:sky'}, token=a)
check('...and back on: bought for good', st == 200 and r['worn']['color'] == 'color:sky', r)

print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
