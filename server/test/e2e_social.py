"""End-to-end test of messages, head-to-heads and cups against a local server with credits on:

  npx wrangler dev --port 8796 --ip 127.0.0.1 --local-upstream 127.0.0.1:8796 --persist-to <fresh dir> --var CREDITS_FROM:2000-01-01 --var OFFICIAL_FROM:
  python test/e2e_social.py http://127.0.0.1:8796 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars). The inbox (messages, block, report, notices), a head-to-head declined, cancelled, expired,
and one accepted, driven as a match (the league event machinery) and settled with its stakes; a cup joined and left,
started with a bye, two rounds driven and its pot shared. The cron's part runs through the dev-only
/api/admin/social-tick at the times it would.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE, KEY = sys.argv[1].rstrip('/'), sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
APP_UA = 'ACR-Daily/9.9.9 public'
GRACE = 30 * 60000
fails = 0


def check(name, cond, info=''):
    global fails
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else '  ' + str(info)[:400]))
    if not cond:
        fails += 1


def call(path, body=None, token=None, admin=False):
    h = {'User-Agent': APP_UA}
    if token or admin:
        h['Authorization'] = 'Bearer ' + (KEY if admin else token)
    data = None
    if body is not None:
        data, h['Content-Type'] = json.dumps(body).encode(), 'application/json'
    req = urllib.request.Request(BASE + path, data=data, headers=h, method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def app_user(steam_id, name):
    state = 'so-' + steam_id
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name)).read()
    return json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())['token']


def tick(at):
    return call('/api/admin/social-tick', {'now': at}, admin=True)[1]


def balance(token):
    return call('/api/credits', token=token)[1]['balance']


def notices(token):
    return call('/api/inbox', token=token)[1]['notices']


# stages, and drivers with credits (a finished run starts them: welcome + daily bonus + the free daily's bonus)
fx = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))
for track, sid in (('Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'), ('Wales Severn', 'WelesS4HafrenSouthFullReverse'),
                   ('Wales Cwmbiga', 'WelesS3HafrenNorthFullForward')):
    call('/api/admin/route', {'track': track, 'points': fx['route'], 'stageId': sid}, admin=True)
    call('/api/admin/pool', {'track': track, 'car': 'Hyundai i20 N Rally2'}, admin=True)
chs = {c['slot']: c for c in call('/api/challenges/today')[1]['challenges']}
date = chs[1]['date']
ids = {k: '765611900000003%02d' % i for i, k in enumerate(['Ann', 'Ben', 'Cy', 'Dee', 'Eve'])}
tok = {k: app_user(v, k) for k, v in ids.items()}
for k in tok:
    ch = chs[1]
    call('/api/runs', dict(fx['result'], challengeId='%s/1' % date, track=ch['track'], car=ch['car'], startedAt=time.time()), token=tok[k])
    call('/api/credits/claim', {}, token=tok[k])
start_bal = {k: balance(t) for k, t in tok.items()}
check('drivers with credits', all(v >= 100 for v in start_bal.values()), start_bal)
A, B, C, D, E = (tok[k] for k in ['Ann', 'Ben', 'Cy', 'Dee', 'Eve'])
cat = call('/api/catalog')[1]
wales = [s['track'] for s in next(x for x in cat['rallies'] if x['name'] == 'Wales')['stages']]
CAR = 'Hyundai i20 N Rally2'

# ---- messages
st, r = call('/api/players?q=an')
check('find a driver by name', ids['Ann'] in [p['steamId'] for p in r['players']], r)
check('a message to Ben', call('/api/inbox/send', {'to': ids['Ben'], 'body': 'Hello Ben'}, token=A)[1].get('id'))
check('Ben has one unread', call('/api/inbox/unread', token=B)[1] == {'unread': 1})
st, r = call('/api/inbox', token=B)
th = r['threads'][0] if r['threads'] else {}
check('...in a conversation with Ann', th.get('with', {}).get('steamId') == ids['Ann'] and th.get('unread') == 1, r)
st, r = call('/api/inbox/with/%s' % ids['Ann'], token=B)
msg_id = r['messages'][0]['id']
check('opened: the message, and read now', [m['body'] for m in r['messages']] == ['Hello Ben'] and
      call('/api/inbox/unread', token=B)[1]['unread'] == 0, r)
check('a reply', call('/api/inbox/send', {'to': ids['Ann'], 'body': 'Hi Ann'}, token=B)[1].get('id'))
check('nothing empty, nothing to yourself', call('/api/inbox/send', {'to': ids['Ben'], 'body': '  '}, token=A)[0] == 400 and
      call('/api/inbox/send', {'to': ids['Ann'], 'body': 'me'}, token=A)[0] == 400)
call('/api/inbox/block', {'steamId': ids['Ann']}, token=B)
check('Ben blocks Ann: no more messages from her', call('/api/inbox/send', {'to': ids['Ben'], 'body': 'hey?'}, token=A)[0] == 403)
call('/api/inbox/block', {'steamId': ids['Ann'], 'block': False}, token=B)
check('...unblocked', call('/api/inbox/send', {'to': ids['Ben'], 'body': 'sorry'}, token=A)[0] == 200)
check('Ben reports Ann\'s message', call('/api/inbox/report', {'id': msg_id, 'reason': 'test'}, token=B)[1].get('reported'))
check('...nobody else\'s', call('/api/inbox/report', {'id': msg_id}, token=C)[0] == 404)
check('the inbox needs sign-in', call('/api/inbox')[0] == 401)


# ---- head-to-heads
def spec(name, hours=3):
    now = int(time.time() * 1000)
    return {'name': name, 'rally': 'Wales', 'car': CAR, 'stages': [{'track': wales[0], 'day': 1, 'weather': 'Clear', 'time': '09:00'}],
            'opens': now - 60000, 'closes': now + hours * 3600000}


st, r = call('/api/h2h', {'opponent': ids['Ben'], 'stake': 20, 'event': spec('Duel one')}, token=A)
h1 = r.get('id')
check('Ann challenges Ben for 20 each', st == 200 and h1 and balance(A) == start_bal['Ann'] - 20, (st, r))
check('Ben is told', any(n['ref'] == 'h2h:%d' % h1 for n in notices(B)), notices(B)[:2])
check('...and sees it coming in', [h['id'] for h in call('/api/h2h', token=B)[1]['incoming']] == [h1])
check('only Ben answers it', call('/api/h2h/%d/accept' % h1, {}, token=C)[0] == 404 and call('/api/h2h/%d/accept' % h1, {}, token=A)[0] == 403)
check('Ben declines', call('/api/h2h/%d/decline' % h1, {}, token=B)[1] == {'status': 'declined'})
check('...Ann\'s stake back', balance(A) == start_bal['Ann'])
check('...and no second answer', call('/api/h2h/%d/accept' % h1, {}, token=B)[0] == 409)

st, r = call('/api/h2h', {'opponent': ids['Ben'], 'stake': 20, 'event': spec('Duel two')}, token=A)
h2 = r['id']
check('Ann cancels a challenge before it is answered', call('/api/h2h/%d/cancel' % h2, {}, token=A)[1] == {'status': 'cancelled'} and
      balance(A) == start_bal['Ann'])
check('a stake more than you have', call('/api/h2h', {'opponent': ids['Ben'], 'stake': 999, 'event': spec('Too rich')}, token=A)[0] == 402)
call('/api/inbox/block', {'steamId': ids['Ann']}, token=E)
check('no challenges from a driver you blocked', call('/api/h2h', {'opponent': ids['Eve'], 'stake': 0, 'event': spec('Blocked')}, token=A)[0] == 403)

st, r = call('/api/h2h', {'opponent': ids['Cy'], 'stake': 10, 'event': spec('Never answered')}, token=A)
h3 = r['id']
st, r = call('/api/h2h', {'opponent': ids['Ben'], 'stake': 20, 'event': spec('The real one')}, token=A)
h4 = r['id']
st, r = call('/api/h2h/%d/accept' % h4, {}, token=B)
ev4 = r.get('eventId')
check('Ben accepts: his 20 taken, the match made', st == 200 and ev4 and balance(B) == start_bal['Ben'] - 20, (st, r))
mine = {k: [e for e in call('/api/me/events', token=tok[k])[1]['events'] if e['id'] == ev4] for k in ['Ann', 'Ben', 'Cy']}
check('the match is in Ann\'s and Ben\'s LEAGUES view, as a head-to-head', mine['Ann'] and mine['Ben'] and mine['Ann'][0]['kind'] == 'h2h', mine)
check('...each told who the other is', mine['Ann'][0].get('opponent') == {'steamId': ids['Ben'], 'name': 'Ben'} and
      mine['Ben'][0].get('opponent') == {'steamId': ids['Ann'], 'name': 'Ann'}, (mine['Ann'][0].get('opponent'), mine['Ben'][0].get('opponent')))
check('...not in Cy\'s', not mine['Cy'])
check('...and not a league of theirs', not any('1V1' in l['name'] for l in call('/api/leagues', token=A)[1]['mine']))
check('Cy can\'t drive it', call('/api/events/%d/start' % ev4, {'car': CAR}, token=C)[0] == 403)
check('nobody stewards it', call('/api/events/%d/dsq' % ev4, {'steamId': ids['Ben'], 'reason': 'mean'}, token=A)[0] == 403)
for t, ms in ((A, 300000), (B, 301250)):
    call('/api/events/%d/start' % ev4, {'car': CAR}, token=t)
    st, r = call('/api/events/%d/stage' % ev4, {'no': 0, 'timeMs': ms, 'penaltyMs': 0}, token=t)
    check('a driver finishes the match', r.get('status') == 'finished', r)
closes4 = call('/api/events/%d' % ev4)[1]['closes']
check('the cron leaves it while the window is open', not [x for x in tick(int(time.time() * 1000))['h2h'] if x['id'] == h4])
r = tick(closes4 + GRACE + 60000)
check('the cron: settled, Ann won; the unanswered one expired', {'id': h4, 'status': 'settled', 'winner': ids['Ann']} in r['h2h'] and
      {'id': h3, 'status': 'expired'} in r['h2h'], r)
check('Ann has both stakes, Ben lost his; Cy\'s challenger got hers back', balance(A) == start_bal['Ann'] + 20 and
      balance(B) == start_bal['Ben'] - 20, (balance(A), balance(B)))
check('both told the result', any('won The real one' in n['body'] for n in notices(B)), notices(B)[:2])
check('...once', tick(closes4 + GRACE + 120000)['h2h'] == [])
past = call('/api/h2h', token=A)[1]['past']
check('Ann\'s past head-to-heads', {h['id']: h['status'] for h in past} == {h1: 'declined', h2: 'cancelled', h3: 'expired', h4: 'settled'}, past)


# ---- cups
now = int(time.time() * 1000)
cup = {'name': 'Test Cup', 'about': 'four at most', 'size': 4, 'fee': 10, 'split': 'two', 'roundHours': 12,
       'starts': now + 3600000 + 60000, 'event': {k: v for k, v in spec('x').items() if k not in ('name', 'opens', 'closes')}}
check('a cup starts an hour from now at the earliest', call('/api/cups', dict(cup, starts=now + 60000), token=A)[0] == 400)
st, r = call('/api/cups', cup, token=A)
cid = r.get('id')
check('Ann makes a cup', st == 200 and cid, r)
before = {k: balance(t) for k, t in tok.items()}
for t in (A, B, C, D):
    check('joins (10)', call('/api/cups/%s/join' % cid, {}, token=t)[1].get('entered'))
check('the fifth: full', call('/api/cups/%s/join' % cid, {}, token=E)[0] == 409)
check('Dee leaves before the start: her 10 back', call('/api/cups/%s/leave' % cid, {}, token=D)[1] == {'entered': False} and
      balance(D) == before['Dee'])
check('only its maker calls it off', call('/api/cups/%s/cancel' % cid, {}, token=B)[0] == 403)
check('the cup is listed as open, with its pot', any(c['id'] == cid and c['pot'] == 30 for c in call('/api/cups')[1]['open']))
r = tick(cup['starts'] + 60000)
check('the cron starts it', {'cup': cid, 'did': 'started'} in r['cups'], r)
check('no joining once it runs', call('/api/cups/%s/join' % cid, {}, token=E)[0] == 409)
c = call('/api/cups/%s' % cid, token=A)[1]
r1 = [m for m in c['matches'] if m['round'] == 1]
bye = next(m for m in r1 if not m['b'])
match = next(m for m in r1 if m['b'])
check('three in a bracket of four: the top seed\'s bye, one match', len(r1) == 2 and bye['a']['seed'] == 1 and bye['winner'] == bye['a']['steamId'] and
      match['eventId'] and c['rounds'] == 2, c['matches'])
name_of = {v: k for k, v in ids.items()}
hi, lo = match['a']['steamId'], match['b']['steamId']          # a: the higher seed
check('the match is in its drivers\' LEAGUES view, as a cup match', any(e['id'] == match['eventId'] and e['kind'] == 'cup'
      for e in call('/api/me/events', token=tok[name_of[hi]])[1]['events']))
check('...not the bye\'s driver\'s', not any(e['id'] == match['eventId'] for e in call('/api/me/events', token=tok[name_of[bye['a']['steamId']]])[1]['events']))
# the lower seed wins round 1
for sid, ms in ((hi, 320000), (lo, 310000)):
    call('/api/events/%d/start' % match['eventId'], {'car': CAR}, token=tok[name_of[sid]])
    call('/api/events/%d/stage' % match['eventId'], {'no': 0, 'timeMs': ms, 'penaltyMs': 0}, token=tok[name_of[sid]])
closes1 = call('/api/events/%d' % match['eventId'])[1]['closes']
r = tick(closes1 + GRACE + 60000)
check('the cron: round 1 decided, the final opened', {'cup': cid, 'did': 'round 2'} in r['cups'], r)
c = call('/api/cups/%s' % cid, token=A)[1]
m1 = next(m for m in c['matches'] if m['id'] == match['id'])
final = next(m for m in c['matches'] if m['round'] == 2)
check('the faster went through', m1['winner'] == lo and m1['note'].startswith('by 10.000'), m1)
check('the final: the bye\'s driver against the winner', {final['a']['steamId'], final['b']['steamId']} == {bye['a']['steamId'], lo} and
      final['name'] == 'Final', final)
# the final: one retires, the other finishes
f1, f2 = final['a']['steamId'], final['b']['steamId']
call('/api/events/%d/start' % final['eventId'], {'car': CAR}, token=tok[name_of[f1]])
call('/api/events/%d/dnf' % final['eventId'], {'reason': 'crashed'}, token=tok[name_of[f1]])
call('/api/events/%d/start' % final['eventId'], {'car': CAR}, token=tok[name_of[f2]])
call('/api/events/%d/stage' % final['eventId'], {'no': 0, 'timeMs': 330000, 'penaltyMs': 0}, token=tok[name_of[f2]])
closes2 = call('/api/events/%d' % final['eventId'])[1]['closes']
r = tick(closes2 + GRACE + 60000)
check('the cron: the final decided, the cup over', {'cup': cid, 'did': 'finished', 'winner': f2} in r['cups'], r)
c = call('/api/cups/%s' % cid, token=A)[1]
pl = {e['steamId']: e['place'] for e in c['entrants']}
check('places: the winner 1, the runner-up 2, the round-1 loser 3', pl == {f2: 1, f1: 2, hi: 3}, pl)
paid = {name_of[s]: balance(tok[name_of[s]]) - before[name_of[s]] for s in pl}
check('the pot (30) shared 70 / 30: 21 and 9, the third nothing (fees 10 each)', paid == {name_of[f2]: 11, name_of[f1]: -1, name_of[hi]: -10}, paid)
check('everyone told', all(any('Test Cup is over' in n['body'] for n in notices(tok[name_of[s]])) for s in pl))
check('...once', tick(closes2 + GRACE + 120000)['cups'] == [])

# a cup nobody joins is called off; one called off by its maker gives the fees back
later = int(time.time() * 1000) + 3600000 + 60000
st, r = call('/api/cups', dict(cup, name='Empty Cup', starts=later), token=B)
empty = r.get('id')
r = tick(later + 60000)
check('fewer than two at the start: called off', {'cup': empty, 'did': 'called off'} in r['cups'], r)
st, r = call('/api/cups', dict(cup, name='Called Off', starts=int(time.time() * 1000) + 3600000 + 60000), token=B)
off = r['id']
b0 = balance(E)
call('/api/cups/%s/join' % off, {}, token=E)
check('its maker calls it off: the fee back', call('/api/cups/%s/cancel' % off, {}, token=B)[1].get('cancelled') and balance(E) == b0)

print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
