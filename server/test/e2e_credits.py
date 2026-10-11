"""End-to-end test of credits (a prototype) against a local server with them on:

  npx wrangler dev --port 8794 --ip 127.0.0.1 --local-upstream 127.0.0.1:8794 --persist-to <fresh dir> --var CREDITS_FROM:2000-01-01 --var OFFICIAL_FROM:
  python test/e2e_credits.py http://127.0.0.1:8794 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars; OFFICIAL_FROM empty: the app's own times count, so a test run needs no game save).
Credits starting with a driver's first finished run, the daily and welcome bonus, the free daily's bonus as its run
comes in (and back when an admin rejects it), the wager daily driven only with a stake (runs and live positions without
one refused, old apps told to update) and its settlement with the house's stake and refunds, a league event's entry fee
(paid before the start, refunded when the event is deleted, its pot paid a day after the close).
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


def report(run_id, ip):
    """A report of a run from somewhere else (three put it under review)."""
    req = urllib.request.Request(BASE + '/api/runs/%d/report' % run_id, data=b'{"reason":"test"}', method='POST',
                                 headers={'Content-Type': 'application/json', 'User-Agent': APP_UA, 'CF-Connecting-IP': ip})
    urllib.request.urlopen(req, timeout=20).read()


def settle(slot=None, pots_at=None):
    body = {'pots': True, 'now': pots_at} if pots_at else {'date': date, 'slot': slot}
    return call('/api/admin/credits-settle', body, admin=True)


ANN, BEN, CY, DEE, EVE, FAY = ('76561190000000101', '76561190000000102', '76561190000000103', '76561190000000104',
                                '76561190000000105', '76561190000000106')
OLD_UA = 'ACR-Daily/0.0.8 public'          # older than CREDITS_MIN_APP (wrangler.toml): it doesn't know about stakes


st, r = call('/api/credits')
check('signed out: on, today\'s wager', r['enabled'] and r['wager']['stake'] == 100 and r['wager']['entrants'] == 0, r)
st, r = call('/api/credits', token=a)
check('a new driver: no credits before a finished run', (r['balance'], r['earning'], r['claimable']) == (0, False, False), r)
st, r = call('/api/credits/claim', {}, token=a)
check('...so no bonus to claim yet', st == 200 and not r['claimed'] and r.get('needsRun') and r['balance'] == 0, r)
st, r = run(a, 1)
check('Ann finishes SS1: +50 as the run comes in', r.get('status') == 'finished' and r.get('credits') == 50, r)
st, r = run(a, 1)
check('...not for a practice run', r.get('counted') is False and 'credits' not in r, r)
st, r = call('/api/credits', token=a)
check('a finished run starts the credits: welcome + daily to claim', (r['balance'], r['earning'], r['claimable'], r['nextBonus']) == (50, True, True, 100), r)
st, r = call('/api/credits/claim', {}, token=a)
check('claimed: 50 + 50', r['claimed'] and r['amount'] == 100 and r['welcome'] == 50 and r['balance'] == 150 and r['streak'] == 1, r)
st, r = call('/api/credits/claim', {}, token=a)
check('once a day', not r['claimed'] and r['balance'] == 150, r)
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
# Cy: a DNF on SS1 starts nothing; a practice run to the finish does (but no SS1 bonus: the DNF is his result)
run(c, 1, 'dnf')
st, r = call('/api/credits/claim', {}, token=c)
check('a DNF is not a finished run: no credits yet', not r['claimed'] and r.get('needsRun'), r)
st, r = run(c, 1)
check('...a practice run to the finish (not on the board, no bonus)', r.get('status') == 'finished' and r.get('counted') is False and 'credits' not in r, r)
st, r = call('/api/credits/claim', {}, token=c)
check('...starts them: welcome + daily, one stake', r['claimed'] and r['balance'] == 100, r)
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
for ip in ('10.0.0.1', '10.0.0.2', '10.0.0.3'):
    report(ann_run, ip)
board2 = call('/api/leaderboard?date=%s&slot=2' % date)[1]
check('three reports: Ann\'s run under review', next(x for x in board2['entries'] if x['steamId'] == ANN)['review'], board2['entries'][:3])
st, r = settle(2)
check('a winning run under review holds the day', r == {'date': date, 'slot': 2, 'held': True}, r)
check('the admin clears it', call('/api/admin/runs/%d/clear' % ann_run, {}, admin=True)[1].get('ok'))
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
check('Ann pays 25', st == 200 and r['paid'] and r['pot'] == 25 and r['balance'] == 225, r)
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
check('Ann has her 25 back', call('/api/credits', token=a)[1]['balance'] == 250)

# ---- a pot paid out: a day after the close, to the league's members; one removed before starting gets the fee back
ev2 = dict(ev, name='Paid Round 2')
st, e2 = call('/api/leagues/%s/events' % lg['id'], ev2, op=op)
eid2 = e2['id']
call('/api/leagues/%s/join' % lg['id'], {}, token=b)
for t in (a, b):
    check('pays 25', call('/api/events/%d/enter' % eid2, {}, token=t)[1].get('paid'))
ben_before = call('/api/credits', token=b)[1]['balance']
st, r = call('/api/leagues/%s/remove' % lg['id'], {'steamId': BEN}, op=op)
st, r = call('/api/credits', token=b)
check('Ben removed before starting: his 25 back', r['balance'] == ben_before + 25 and r['ledger'][0]['kind'] == 'fee-refund', r['ledger'][:2])
check('Ann starts', call('/api/events/%d/start' % eid2, {'car': 'Hyundai i20 N Rally2'}, token=a)[1].get('started'))
st, r = call('/api/events/%d/stage' % eid2, {'no': 0, 'timeMs': 300000, 'penaltyMs': 0}, token=a)
check('...and finishes', r.get('status') == 'finished', r)
st, r = settle(pots_at=ev2['closes'] + 3600000)
check('no pot an hour after the close: the stewards\' day', r == {'pots': []}, r)
st, r = settle(pots_at=ev2['closes'] + 86400000 + 60000)
check('a day after: the pot to the winner', r == {'pots': [{'event': eid2, 'payouts': {ANN: 25}}]}, r)
check('Ann: 250 - 25 + 25', call('/api/credits', token=a)[1]['balance'] == 250)
st, r = settle(pots_at=ev2['closes'] + 86400000 + 120000)
check('...once', r == {'pots': []}, r)
st, r = call('/api/events/%d/dsq' % eid2, {'steamId': ANN, 'reason': 'too late'}, op=op)
check('paid out: the stewards\' decisions are final', st == 409, (st, r))
call('/api/leagues/%s/join' % lg['id'], {}, token=c)
st, r = call('/api/events/%d/enter' % eid2, {}, token=c)
check('no fee into a pot paid out', st == 409, (st, r))
st, r = call('/api/events/%d/edit' % eid2, {'name': ev2['name'], 'closes': ev2['closes'] + 3600000}, op=op)
check('...nor a later close', st == 409, (st, r))
st, r = call('/api/events/%d/delete' % eid2, {}, op=op)
check('deleted after the payout: nothing refunded', r == {'deleted': True, 'refunded': 0} and call('/api/credits', token=a)[1]['balance'] == 250, r)

print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
