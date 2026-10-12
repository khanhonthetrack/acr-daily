"""End-to-end test of messages, head-to-heads and cups against a local server with credits on:

  npx wrangler dev --port 8796 --ip 127.0.0.1 --local-upstream 127.0.0.1:8796 --persist-to <fresh dir> --var CREDITS_FROM:2000-01-01 --var OFFICIAL_FROM:
  python test/e2e_social.py http://127.0.0.1:8796 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars). The inbox (messages, block, report, notices), a head-to-head declined, cancelled, expired,
and one accepted, driven as a match (the league event machinery) and settled with its stakes; a cup joined and left,
started with a bye, two rounds driven and its pot shared; an official cup (the admin's: a banner, ACR Daily's prize,
rounds of a week, a two-day rally) run to its end; the coming week's dailies fixed ahead. The cron's part runs through
the dev-only /api/admin/social-tick at the times it would.
"""
import base64
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

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


def call(path, body=None, token=None, admin=False, ua=APP_UA):
    h = {'User-Agent': ua}
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

# ---- Ann's team: its tag by her name in every answer below (src/drivers.js withTeams)
check('Ann makes a team', call('/api/teams', {'name': 'Gravel Foxes', 'tag': '$f00G$fffF$00fX', 'color': '#7BE07B'}, token=A)[0] == 200)
ANN_TEAM = {'tag': 'GFX', 'color': '#7BE07B', 'tagFmt': '$f00G$fffF$00fX'}

# ---- messages
st, r = call('/api/players?q=an')
check('find a driver by name', ids['Ann'] in [p['steamId'] for p in r['players']], r)
check('...with her team\'s tag', [p.get('team') for p in r['players'] if p['steamId'] == ids['Ann']] == [ANN_TEAM], r)
check('a message to Ben', call('/api/inbox/send', {'to': ids['Ben'], 'body': 'Hello Ben'}, token=A)[1].get('id'))
check('Ben has one unread', call('/api/inbox/unread', token=B)[1] == {'unread': 1})
st, r = call('/api/inbox', token=B)
th = r['threads'][0] if r['threads'] else {}
check('...in a conversation with Ann', th.get('with', {}).get('steamId') == ids['Ann'] and th.get('unread') == 1, r)
check('...her tag by her name', th.get('with', {}).get('team') == ANN_TEAM, th)
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
check('...and sees it coming in', [(h['id'], h['challenger'].get('team')) for h in call('/api/h2h', token=B)[1]['incoming']] == [(h1, ANN_TEAM)])
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
      mine['Ben'][0].get('opponent') == {'steamId': ids['Ann'], 'name': 'Ann', 'team': ANN_TEAM}, (mine['Ann'][0].get('opponent'), mine['Ben'][0].get('opponent')))
check('...not in Cy\'s', not mine['Cy'])
check('...and not a league of theirs', not any('1V1' in l['name'] for l in call('/api/leagues', token=A)[1]['mine']))
check('Cy can\'t drive it', call('/api/events/%d/start' % ev4, {'car': CAR}, token=C)[0] == 403)
check('nobody stewards it', call('/api/events/%d/dsq' % ev4, {'steamId': ids['Ben'], 'reason': 'mean'}, token=A)[0] == 403)
closes4 = call('/api/events/%d' % ev4)[1]['closes']
for t, ms in ((A, 300000), (B, 301250)):
    call('/api/events/%d/start' % ev4, {'car': CAR}, token=t)
    st, r = call('/api/events/%d/stage' % ev4, {'no': 0, 'timeMs': ms, 'penaltyMs': 0}, token=t)
    check('a driver finishes the match', r.get('status') == 'finished', r)
    if t == A:
        check('the cron leaves it while Ben has still to drive', not [x for x in tick(int(time.time() * 1000))['h2h'] if x['id'] == h4])
r = tick(int(time.time() * 1000))
check('both have driven: the cron settles it at once, Ann won', {'id': h4, 'status': 'settled', 'winner': ids['Ann']} in r['h2h'], r)
check('...and the match is closed', call('/api/events/%d' % ev4)[1].get('status') == 'closed', call('/api/events/%d' % ev4)[1].get('status'))
check('both told the result', any('won The real one' in n['body'] for n in notices(B)), notices(B)[:2])
r = tick(closes4 + GRACE + 60000)
check('later: the unanswered one expired, the settled one left alone', r['h2h'] == [{'id': h3, 'status': 'expired'}], r)
check('Ann has both stakes, Ben lost his; Cy\'s challenger got hers back', balance(A) == start_bal['Ann'] + 20 and
      balance(B) == start_bal['Ben'] - 20, (balance(A), balance(B)))
check('...once', tick(closes4 + GRACE + 120000)['h2h'] == [])
past = call('/api/h2h', token=A)[1]['past']
check('Ann\'s past head-to-heads', {h['id']: h['status'] for h in past} == {h1: 'declined', h2: 'cancelled', h3: 'expired', h4: 'settled'}, past)

# a rematch: Ben (who lost) sends the same again, his stake taken; only for a 1V1 that is over, only its drivers
check('no rematch of one not played', call('/api/h2h/%d/rematch' % h1, {}, token=A)[0] == 409)
check('...nor of someone else\'s', call('/api/h2h/%d/rematch' % h4, {}, token=C)[0] == 404)
bal_b = balance(B)
st, r = call('/api/h2h/%d/rematch' % h4, {}, token=B)
h5 = r.get('id')
check('Ben asks for a rematch: sent to Ann, his 20 taken', st == 200 and h5 and balance(B) == bal_b - 20, (st, r))
inc = [h for h in call('/api/h2h', token=A)[1]['incoming'] if h['id'] == h5]
check('...the same stages, car and stake, from now, named as a rematch', inc and inc[0]['name'] == 'Rematch: The real one' and
      inc[0]['stake'] == 20 and inc[0]['car'] == CAR and inc[0]['challenger']['steamId'] == ids['Ben'] and
      [s['name'] for s in inc[0]['stages']] == [s['name'] for s in [h for h in past if h['id'] == h4][0]['stages']] and
      inc[0]['opens'] >= int(time.time() * 1000) - 120000, inc)
check('...a friendly if asked', call('/api/h2h/%d/rematch' % h4, {'stake': 0}, token=A)[0] == 200)
call('/api/h2h/%d/cancel' % h5, {}, token=B)
check('...cancelled: Ben\'s stake back', balance(B) == bal_b)
for h in call('/api/h2h', token=A)[1]['outgoing']:
    call('/api/h2h/%d/cancel' % h['id'], {}, token=A)


# ---- cups
now = int(time.time() * 1000)
cup = {'name': 'Test Cup', 'about': 'four at most', 'size': 4, 'fee': 10, 'prizes': [60, 30, 5], 'roundHours': 12,
       'starts': now + 3600000 + 60000, 'event': {k: v for k, v in spec('x').items() if k not in ('name', 'opens', 'closes')}}
check('a cup starts an hour from now at the earliest', call('/api/cups', dict(cup, starts=now + 60000), token=A)[0] == 400)
st, r = call('/api/cups', dict(cup, prizes=[60, 30, 10]), token=A)
check('prizes of its maker\'s own: 100% in all', st == 400 and '110%' in r.get('error', ''), r)
st, r = call('/api/cups', cup, token=A)
cid = r.get('id')
check('Ann makes a cup', st == 200 and cid, r)
check('...its prizes by place', call('/api/cups/%s' % cid)[1]['prizes'] == [{'places': '1st', 'pct': 60}, {'places': '2nd', 'pct': 30},
      {'places': '3rd–4th', 'pct': 5, 'each': True}])
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
check('the cup: Ann\'s tag by her name', [e.get('team') for e in c['entrants'] if e['steamId'] == ids['Ann']] == [ANN_TEAM] and
      all(m[s].get('team') == ANN_TEAM for m in c['matches'] for s in ('a', 'b') if m.get(s) and m[s]['steamId'] == ids['Ann']), c['entrants'])
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
# followed live: the driver on the stage sends where they are, the cup page and the map read it
ev_live = '/api/events/%d/live' % match['eventId']
check('no position before the start', call(ev_live, {'no': 0, 'x': 1, 'z': 2, 'progress': .1}, token=tok[name_of[hi]])[0] == 409)
call('/api/events/%d/start' % match['eventId'], {'car': CAR}, token=tok[name_of[hi]])
check('nor from someone not in the match', call(ev_live, {'no': 0, 'progress': .1}, token=tok[name_of[bye['a']['steamId']]])[0] == 403)
check('the driver on the stage: shown', call(ev_live, {'no': 0, 'x': 12.34, 'z': -5, 'progress': 0.42, 'totalMs': 61000, 'state': 'live'},
                                           token=tok[name_of[hi]])[1] == {'shown': True})
lv = call(ev_live)[1]['drivers']
check('...on the event\'s live list', len(lv) == 1 and lv[0]['steamId'] == hi and lv[0]['stageNo'] == 0 and lv[0]['progress'] == 0.42 and
      lv[0]['x'] == 12.3 and lv[0]['state'] == 'live', lv)
cl = call('/api/cups/%s/live' % cid)[1]['drivers']
check('...and the cup\'s', [(d['eventId'], d['steamId']) for d in cl] == [(match['eventId'], hi)], cl)
# the lower seed wins round 1
for sid, ms in ((hi, 320000), (lo, 310000)):
    if sid != hi:
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
check('the pot (30) shared 60 / 30 / 5: 18 + the 4th place\'s and the rounding = 20, 9, 1 (fees 10 each)',
      paid == {name_of[f2]: 10, name_of[f1]: -1, name_of[hi]: -9}, paid)
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


# ---- an official cup: ACR Daily's own (the admin makes it), with a prize of its own, rounds of a week and a banner
def png(w, h, rgb=(10, 10, 11)):
    """A plain PNG picture of w x h."""
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


now = int(time.time() * 1000)
rally = {'rally': 'Wales', 'car': CAR, 'stages': [{'track': wales[0], 'day': 1, 'weather': 'Clear', 'time': '09:00'},
                                                   {'track': wales[1], 'day': 1, 'weather': 'LightCloud', 'time': '13:00'},
                                                   {'track': wales[2], 'day': 2, 'weather': 'Clear', 'time': '19:00'}]}
ocup = {'name': 'Official Test Cup', 'about': 'Run by ACR Daily.', 'size': 128, 'fee': 0, 'prize': 1000, 'split': 'four',
        'roundHours': 168, 'starts': now + 7 * 86400000, 'event': rally, 'banner': base64.b64encode(png(1200, 400)).decode()}
check('only the site\'s admin makes an official cup', call('/api/admin/cup', ocup, token=A)[0] == 403)
check('...with a banner of about 3:1', call('/api/admin/cup', dict(ocup, banner=base64.b64encode(png(600, 600)).decode()), admin=True)[0] == 422)
st, r = call('/api/admin/cup', ocup, admin=True)
oid = r.get('id')
check('the admin makes one', st == 200 and oid, r)
first = call('/api/cups')[1]['open'][0]
check('listed first: official, run by ACR Daily, its prize the pot', (first['id'], first['official'], first['owner']['name'], first['prize'], first['pot'])
      == (oid, True, 'ACR Daily', 1000, 1000), first)
check('...and on the home page\'s strip', [c['id'] for c in call('/api/cups/official')[1]['cups']] == [oid])
oc = call('/api/cups/%s' % oid)[1]
check('a rally of two days, rounds of a week', [s['day'] for s in oc['stages']] == [1, 1, 2] and oc['roundHours'] == 168, oc['stages'])
with urllib.request.urlopen(BASE + oc['banner']) as resp:
    check('its banner', resp.headers.get('Content-Type') == 'image/png' and resp.read()[:4] == b'\x89PNG')
check('a driver can\'t call it off', call('/api/cups/%s/cancel' % oid, {}, token=A)[0] == 403)
check('a week-long round is for official cups only', call('/api/cups', dict(cup, roundHours=168, starts=now + 2 * 3600000), token=A)[0] == 400)
# the admin moves its start (an hour from now, so this test can run it); two drivers join, free
st, r = call('/api/admin/cup', {'id': oid, 'starts': now + 3600000 + 60000}, admin=True)
check('the admin changes it before the start', st == 200 and call('/api/cups/%s' % oid)[1]['starts'] == now + 3600000 + 60000, r)
before = {k: balance(tok[k]) for k in ('Ann', 'Ben')}
for t in (A, B):
    call('/api/cups/%s/join' % oid, {}, token=t)
r = tick(now + 3600000 + 120000)
check('it starts', {'cup': oid, 'did': 'started'} in r['cups'], r)
check('...and can\'t change any more', call('/api/admin/cup', {'id': oid, 'prize': 5}, admin=True)[0] == 409)
fin = next(m for m in call('/api/cups/%s' % oid)[1]['matches'] if m['round'] == 1)
check('two drivers: the final at once', fin['name'] == 'Final' and fin['eventId'])
for t, ms in ((A, 100000), (B, 101000)):                 # each stage of the rally, Ann the faster
    call('/api/events/%d/start' % fin['eventId'], {'car': CAR}, token=t)
    for no in range(3):
        call('/api/events/%d/stage' % fin['eventId'], {'no': no, 'timeMs': ms, 'penaltyMs': 0}, token=t)
closes3 = call('/api/events/%d' % fin['eventId'])[1]['closes']
check('the round is open a week', closes3 >= now + 3600000 + 167 * 3600000, closes3)
r = tick(closes3 + GRACE + 60000)
check('the cup over: Ann won', {'cup': oid, 'did': 'finished', 'winner': ids['Ann']} in r['cups'], r)
paid = {k: balance(tok[k]) - before[k] for k in ('Ann', 'Ben')}
check('ACR Daily\'s prize shared 60 / 30 (and the semi-finalists\' 5 + 5 to the winner): 700 and 300', paid == {'Ann': 700, 'Ben': 300}, paid)
st, r = call('/api/admin/cup', dict(ocup, name='Second Official', starts=now + 3 * 86400000), admin=True)
check('the admin calls an official cup off', call('/api/admin/cup', {'id': r['id'], 'cancel': True}, admin=True)[1].get('cancelled'))

# ---- an official cup that draws its stages each round (the test's rally has 2 roads: Hafren South both ways, Hafren North)
dstart = int(time.time() * 1000) + 3600000 + 60000
dcup = {k: v for k, v in ocup.items() if k != 'banner'}
dcup.update(name='Draw Cup', size=4, prize=0, roundHours=24, starts=dstart, draw={'maxKm': 40},
            event=dict(rally, stages=[{'day': 1, 'weather': 'Clear', 'time': '09:00'}]))
check('a draw of 3 stages needs 3 roads', call('/api/admin/cup', dict(dcup, event=rally), admin=True)[0] == 400)
st, r = call('/api/admin/cup', dcup, admin=True)
did = r.get('id')
dc = call('/api/cups/%s' % did)[1]
check('a cup that draws: its slots, no stage named yet', st == 200 and dc['draw'] == {'maxKm': 40} and dc['stages'][0]['name'] is None, dc.get('stages'))
for t in (A, B, C, D):
    call('/api/cups/%s/join' % did, {}, token=t)
r = tick(dstart + 60000)
check('it starts', {'cup': did, 'did': 'started'} in r['cups'], r)
dc = call('/api/cups/%s' % did)[1]
r1 = [m for m in dc['matches'] if m['round'] == 1]
check('round 1 drawn: one stage', len(dc['roundStages']) == 1 and len(dc['roundStages'][0]['stages']) == 1, dc['roundStages'])
check('the drivers are told the stage', any('The stages: ' + dc['roundStages'][0]['stages'][0]['name'] in n['body'] for n in notices(A)), notices(A)[:1])
for m in r1:
    for side, ms in ((m['a'], 100000), (m['b'], 101000)):
        call('/api/events/%d/start' % m['eventId'], {'car': CAR}, token=tok[name_of[side['steamId']]])
        call('/api/events/%d/stage' % m['eventId'], {'no': 0, 'timeMs': ms, 'penaltyMs': 0}, token=tok[name_of[side['steamId']]])
dclose = call('/api/events/%d' % r1[0]['eventId'])[1]['closes']
r = tick(dclose + GRACE + 60000)
check('round 1 decided, the final opened', {'cup': did, 'did': 'round 2'} in r['cups'], r)
rs = call('/api/cups/%s' % did)[1]['roundStages']
check('the final drew another stage (one round 1 didn\'t race)', len(rs) == 2 and rs[0]['stages'][0]['name'] != rs[1]['stages'][0]['name'] and
      rs[1]['name'] == 'Final', rs)

# ---- the coming week's dailies fixed ahead of time (the cron does it once an hour; the admin any time)
nxt = call('/api/admin/state', admin=True)[1]['next']
st, r = call('/api/admin/schedule-ahead', {}, admin=True)
check('the coming week fixed: two dailies a day', st == 200 and len(r['fixed']) >= 7 and all(len(d['picks']) == 2 for d in r['fixed']), r)
check('...the picks as they were', call('/api/admin/state', admin=True)[1]['next'] == nxt)
check('...once', call('/api/admin/schedule-ahead', {}, admin=True)[1]['fixed'] == [])
check('a re-pick fixes the days not started again', len(call('/api/admin/schedule-ahead', {'repick': True}, admin=True)[1]['fixed']) >= 7)

# ---- achievements: everyone checked by the admin (as the cron does the active ones); the cup's winner has one
st, r = call('/api/admin/achievements', {}, admin=True)
check('the admin checks every driver\'s achievements', st == 200 and r['checked'] >= 5 and r['next'] is None, r)
WEB = 'Mozilla/5.0 (a browser)'
pg = call('/api/drivers/' + f2, ua=WEB)[1]
got = {a['id'] for a in pg['achievements'] if a['at']}
check('the first cup\'s winner: Cup winner and Finalist', {'cup-winner', 'finalist'} <= got, got)
check('Ann won a 1V1: Duellist', 'duellist' in {a['id'] for a in call('/api/drivers/' + ids['Ann'], ua=WEB)[1]['achievements'] if a['at']})
check('...and was told', any(n['ref'] == 'ach:' + ids['Ann'] for n in notices(A)), notices(A)[:2])
check('the app gets the light page', call('/api/drivers/' + ids['Ann'], token=A)[1].get('lite') is True)
check('one ranking, no seasons', 'season' not in call('/api/ranking')[1])

print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
