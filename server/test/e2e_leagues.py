"""End-to-end test of leagues against a local server: a private league and its invite, an event, drivers' runs through
it (the app's start / begin / stage / DNF), standings, the championship, website sign-in and the pages.

  npx wrangler dev --port 8792 --ip 127.0.0.1 --local-upstream 127.0.0.1:8792 --persist-to <fresh dir>
  python test/e2e_leagues.py http://127.0.0.1:8792 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars). The app's User-Agent is LEAGUES_MIN_APP's (wrangler.toml), the oldest app taken.
"""
import http.cookiejar
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import zlib

BASE, KEY = sys.argv[1].rstrip('/'), sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
MIN = re.search(r'LEAGUES_MIN_APP = "([\d.]+)"', open(os.path.join(HERE, '..', 'wrangler.toml'), encoding='utf-8').read()).group(1)
APP_UA = 'ACR-Daily/%s public' % MIN
OLD_UA = 'ACR-Daily/0.0.4 public'
fails = 0


def check(name, cond, info=''):
    global fails
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else '  ' + str(info)[:300]))
    if not cond:
        fails += 1


class Client:
    """A browser (the website's session cookie) or the app (Bearer token, its User-Agent)."""

    def __init__(self, token=None, ua='Mozilla/5.0'):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.token, self.ua = token, ua

    def call(self, path, body=None, origin=None, ua=None):
        h = {'User-Agent': ua or self.ua}
        if self.token:
            h['Authorization'] = 'Bearer ' + self.token
        if origin:
            h['Origin'] = origin
        data = None
        if body is not None:
            data, h['Content-Type'] = json.dumps(body).encode(), 'application/json'
        req = urllib.request.Request(BASE + path, data=data, headers=h, method='POST' if body is not None else 'GET')
        try:
            with self.op.open(req, timeout=20) as r:
                raw = r.read().decode()
                return r.status, json.loads(raw) if raw.startswith(('{', '[')) else raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            return e.code, json.loads(raw) if raw.startswith('{') else raw

    def raw(self, path, data, ctype, origin=None):
        """POST bytes (a banner) -> (status, json); GET when data is None -> (status, bytes, headers)."""
        h = {'User-Agent': self.ua}
        if self.token:
            h['Authorization'] = 'Bearer ' + self.token
        if origin:
            h['Origin'] = origin
        if data is not None:
            h['Content-Type'] = ctype
        req = urllib.request.Request(BASE + path, data=data, headers=h, method='GET' if data is None else 'POST')
        try:
            with self.op.open(req, timeout=20) as r:
                body = r.read()
                return (r.status, body, r.headers) if data is None else (r.status, json.loads(body.decode()))
        except urllib.error.HTTPError as e:
            body = e.read()
            return (e.code, body, e.headers) if data is None else (e.code, json.loads(body.decode() or '{}'))


def png(w, h, rgb=(200, 20, 30)):
    """A one-colour PNG (made here: no image library needed)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\0' + bytes(rgb) * w for _ in range(h))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def web_user(steam_id, name):
    c = Client()
    st, _ = c.call('/login?next=/leagues&dev=%s&name=%s' % (steam_id, name))
    check('website sign-in sets the session cookie (%s)' % name, st == 200 and any(k.name == 'acr_session' for k in c.jar))
    return c


def app_user(steam_id, name):
    state = uuid.uuid4().hex
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name)).read()
    tok = json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())['token']
    return Client(token=tok, ua=APP_UA)


# ---- the stages an event can use: routes with the game's stage id
route = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))['route']
for track, sid in (('Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'), ('Wales Severn', 'WelesS4HafrenSouthFullReverse'),
                   ('Wales Cwmbiga', 'WelesS3HafrenNorthFullForward')):
    req = urllib.request.Request(BASE + '/api/admin/route', data=json.dumps({'track': track, 'points': route, 'stageId': sid}).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}, method='POST')
    check('route of %s' % track, urllib.request.urlopen(req).status == 200)

owner = web_user('76561198000000001', 'Owner')
member = app_user('76561198000000002', 'Member')
third = app_user('76561198000000003', 'Third')
anon = Client()

st, me = owner.call('/api/me')
check('/api/me knows the website session', st == 200 and me.get('name') == 'Owner', me)
check('/api/me: signed out', anon.call('/api/me')[1] == {'signedIn': False})

# ---- a private league and its invite
st, lg = owner.call('/api/leagues', {'name': 'Test League', 'about': 'e2e', 'public': False})
check('create a private league -> id + code', st == 200 and len(lg.get('id', '')) == 8 and len(lg.get('code', '')) == 9, lg)
lid, code = lg['id'], lg['code']
check('a private league is not listed', all(x['id'] != lid for x in anon.call('/api/leagues')[1]['public']))
check('a private league is hidden from non-members', member.call('/api/leagues/' + lid)[0] == 404)
st, by = member.call('/api/leagues/code?code=' + code.lower())
check('the invite code opens it (any case)', st == 200 and by['id'] == lid and not by['member'], by)
check('a private league: no joining without the code', member.call('/api/leagues/%s/join' % lid, {})[0] == 403)
check('join with the code', member.call('/api/leagues/join', {'code': code})[1].get('joined'))
check('join with the code (third)', third.call('/api/leagues/join', {'code': code})[1].get('joined'))
check('a cookie request from another site is refused',
      owner.call('/api/leagues/join', {'code': code}, origin='https://evil.example')[0] == 403)

# ---- the league's banner
pic = png(1200, 400)
bpath = '/api/leagues/%s/banner' % lid
check('a banner: not from a member', member.raw(bpath, pic, 'image/png')[0] == 403)
check('a banner: not signed out', anon.raw(bpath, pic, 'image/png')[0] == 401)
check('a banner: not from another site', owner.raw(bpath, pic, 'image/png', origin='https://evil.example')[0] == 403)
check('a banner: no SVG', owner.raw(bpath, b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>' + b' ' * 40,
                                   'image/svg+xml')[0] == 415)
check('a banner: wide', owner.raw(bpath, png(800, 800), 'image/png')[0] == 422)
check('a banner: not too big', owner.raw(bpath, pic + b'\0' * 260000, 'image/png')[0] == 413)
st, r = owner.raw(bpath, pic, 'image/png')
check('a banner: the owner sets it', st == 200 and r['banner'].startswith('/l/%s/banner?v=' % lid), r)
burl = r['banner']
st, body, hd = anon.raw(burl, None, None)
check('the banner served as sent, with its type, kept by browsers', st == 200 and body == pic and hd['Content-Type'] == 'image/png'
      and hd['X-Content-Type-Options'] == 'nosniff' and 'immutable' in hd['Cache-Control'], (st, dict(hd)))
check('the banner on the league page data', owner.call('/api/leagues/' + lid)[1]['banner'] == burl)
check('the banner on the invite page data', anon.call('/api/leagues/code?code=' + code)[1]['banner'] == burl)
st, r = owner.call(bpath, {'remove': True})
check('the owner removes it', st == 200 and r['banner'] is None and anon.raw(burl, None, None)[0] == 404, r)
owner.raw(bpath, pic, 'image/png')
req = urllib.request.Request(BASE + '/api/admin/league-banner', data=json.dumps({'league': lid}).encode(),
                             headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}, method='POST')
check('an admin takes a banner down', urllib.request.urlopen(req).status == 200 and owner.call('/api/leagues/' + lid)[1]['banner'] is None)
owner.raw(bpath, pic, 'image/png')                         # (it stays for the pages below)

# ---- an event
cat = anon.call('/api/catalog')[1]
wales = [s['track'] for s in next(r for r in cat['rallies'] if r['name'] == 'Wales')['stages']]
check('the catalog offers the stages with a game id', len(wales) == 3, wales)
now = int(time.time() * 1000)
event = {'name': 'Round 1', 'rally': 'Wales', 'car': 'Hyundai i20 N Rally2',
         'rules': {'damageIntensity': 'severe', 'penalty': 'realistic'},
         'stages': [{'track': wales[0], 'day': 1, 'weather': 'Clear', 'time': '09:00'},
                    {'track': wales[1], 'day': 1, 'service': True, 'weather': 'LightRain', 'time': '13:00'},
                    {'track': wales[2], 'day': 2, 'weather': 'HeavyCloud', 'time': '10:00'}],
         'opens': now - 60000, 'closes': now + 3 * 86400000}
check('a member makes no events', member.call('/api/leagues/%s/events' % lid, event)[0] == 403)
st, e = owner.call('/api/leagues/%s/events' % lid, dict(event, stages=event['stages'][:1] + [dict(event['stages'][1], day=3)]))
check('a calendar the game could not run is refused', st == 400 and 'days' in e.get('error', ''), e)
st, e = owner.call('/api/leagues/%s/events' % lid, dict(event, seasonId='new'))
check('create an event, and its season with it', st == 200 and e.get('id') and e.get('seasonId'), e)
eid = e['id']

# ---- the app: the event, then a run through it
st, mine = member.call('/api/me/events')
ev = next(x for x in mine['events'] if x['id'] == eid)
check('/api/me/events: open, not started', ev['entry'] is None and ev['status'] == 'open', ev)
check('the itinerary as the app writes it into the game',
      [(s['day'], s['service'], s['weatherGame'], s['startSeconds'], s['stageId']) for s in ev['stages']] ==
      [(1, True, 'WT_CLEAR', 32400, 'WelesS4HafrenSouthFullForward'), (1, True, 'WT_LIGHT_RAIN', 46800, 'WelesS3HafrenNorthFullForward'),
       (2, True, 'WT_HEAVY_CLOUDS', 36000, 'WelesS4HafrenSouthFullReverse')], ev['stages'])   # (the catalog: A-Z)
check('the car with its game id', ev['cars'][0]['id'] == 'HyundaiI20NRally2', ev['cars'])
check('the stage routes for the app', member.call('/api/route?track=' + urllib.request.quote(wales[0]))[1].get('route'))
check('an older app is told to update', member.call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'}, ua=OLD_UA)[0] == 426)
check('not the event\'s car', member.call('/api/events/%d/start' % eid, {'car': 'Skoda Fabia RS Rally2'})[0] == 422)
check('no stage before the start', member.call('/api/events/%d/stage' % eid, {'no': 0, 'timeMs': 1, 'penaltyMs': 0})[0] == 409)
st, r = member.call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'})
check('start (SS1 begun)', st == 200 and r.get('started') and r.get('status') == 'running', r)
check('stages in order', member.call('/api/events/%d/stage' % eid, {'no': 1, 'timeMs': 200000, 'penaltyMs': 0})[0] == 409)
for k, (t, p) in enumerate([(213597, 29000), (180400, 0), (250100, 10000)]):
    if k:
        st, r = member.call('/api/events/%d/begin' % eid, {'no': k})
        check('SS%d begun' % (k + 1), st == 200 and r.get('status') == 'running', r)
    st, r = member.call('/api/events/%d/stage' % eid, {'no': k, 'timeMs': t, 'penaltyMs': p, 'splitsMs': [60000, 120000],
                                                     'startedAt': now})
    check('SS%d sent' % (k + 1), st == 200 and r.get('done') == k + 1, r)
check('the last stage finishes the entry', r.get('status') == 'finished', r)
check('nothing after the finish', member.call('/api/events/%d/stage' % eid, {'no': 3, 'timeMs': 1, 'penaltyMs': 0})[0] == 409)
check('a start after the finish changes nothing', member.call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'})[0] == 409)

# ---- the first start of each stage counts: a stage started again ends the entry
st, r = third.call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'})
check('third: start', r.get('started'), r)
check('third: SS1', third.call('/api/events/%d/stage' % eid, {'no': 0, 'timeMs': 230000, 'penaltyMs': 0})[1].get('done') == 1)
check('third: SS2 begun', third.call('/api/events/%d/begin' % eid, {'no': 1})[1].get('status') == 'running')
st, r = third.call('/api/events/%d/begin' % eid, {'no': 1})
check('third: SS2 begun a second time = DNF', st == 200 and r == {'status': 'dnf', 'reason': 'SS2 started again'}, r)
check('third: no stage after the DNF', third.call('/api/events/%d/stage' % eid, {'no': 1, 'timeMs': 1, 'penaltyMs': 0})[0] == 409)

# ---- the owner (a member too, through the website session) starts SS1 twice: DNF; then a retire changes nothing
own_app = Client(ua=APP_UA)
own_app.jar, own_app.op = owner.jar, owner.op
check('owner starts', own_app.call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'})[1].get('started'))
st, r = own_app.call('/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'})
check('owner: SS1 started again = DNF', r == {'status': 'dnf', 'reason': 'SS1 started again'}, r)
check('a DNF after the DNF keeps the first reason',
      own_app.call('/api/events/%d/dnf' % eid, {'no': 0, 'reason': 'retired'})[1] == {'status': 'dnf'})

# ---- standings and championship
st, evd = owner.call('/api/events/%d' % eid)
rows = evd['standings']
check('event standings: the finisher, then the DNFs (most stages first)',
      [(x['name'], x['status'], x.get('rank'), x['totalMs']) for x in rows] ==
      [('Member', 'finished', 1, 213597 + 29000 + 180400 + 250100 + 10000), ('Third', 'dnf', None, 230000),
       ('Owner', 'dnf', None, 0)], rows)
check('stage positions count the penalties', rows[0]['stages'][0]['pos'] == 2 and rows[1]['stages'][0]['pos'] == 1)
check('the DNF reasons', [x['reason'] for x in rows[1:]] == ['SS2 started again', 'SS1 started again'], rows)
st, lgd = owner.call('/api/leagues/' + lid)
check('the league page data (the owner sees the code)', lgd['code'] == code and lgd['me']['owner'] and len(lgd['members']) == 3, lgd)
s1 = lgd['seasons'][0]
check('the season made with the event, its championship', s1['name'] == 'Season 1' and s1['events'] == [eid] and
      [(p['name'], p['points']) for p in s1['standings']][:1] == [('Member', 25)], lgd['seasons'])
check('a member of a private league does not see the code', member.call('/api/leagues/' + lid)[1]['code'] is None)
st, mine = member.call('/api/me/events')
check('/api/me/events: my entry', next(x for x in mine['events'] if x['id'] == eid)['entry']['status'] == 'finished')

# ---- editing once drivers have started: only the name and a later close
st, r = owner.call('/api/events/%d/edit' % eid, dict(event, stages=event['stages'][:1]))
check('an edit after the start only takes the name and closing time', st == 200 and r.get('limited'), r)
check('an event of a private league is hidden from strangers', anon.call('/api/events/%d' % eid)[0] == 404)
st, r = owner.call('/api/leagues/%s/code' % lid, {})
check('a new invite code', st == 200 and r['code'] != code, r)
check('the old invite code stops working', anon.call('/api/leagues/code?code=' + code)[0] == 404)

# ---- seasons
OWNER_ID, MEMBER_ID, THIRD_ID = '76561198000000001', '76561198000000002', '76561198000000003'
cur_code = owner.call('/api/leagues/' + lid)[1]['code']      # (renewed above)
st, r = owner.call('/api/leagues/%s/seasons' % lid, {'name': 'Spring', 'points': {'table': '10, 6, 4', 'finisher': 1},
                                                    'power': [3, 2, 1], 'drop': 0})
check('a season of its own points, with a Power Stage', st == 200 and r.get('id'), r)
sid = r['id']
check('a member makes no season', third.call('/api/leagues/%s/seasons' % lid, {'name': 'Mine', 'points': {'table': '1'}})[0] == 403)
D = 86400000
rounds = []
for k in range(3):                                         # three rounds, each opening when the one before closes
    st, r = owner.call('/api/leagues/%s/events' % lid, dict(event, name='Spring %d' % (k + 1), seasonId=sid,
                                                            opens=event['opens'] + 3 * D * k, closes=event['closes'] + 3 * D * k))
    rounds.append(r.get('id'))
check('three rounds in the season', all(rounds), rounds)
lgd = owner.call('/api/leagues/' + lid)[1]
check('...in it', [e['seasonId'] for e in lgd['events'] if e['id'] in rounds] == [sid] * 3)
check('the rounds not open yet count for nothing', next(s for s in lgd['seasons'] if s['id'] == sid)['standings'] == [])
# ---- roles: the owner makes an admin; admins run events, seasons, members and the stewarding
role = '/api/leagues/%s/role' % lid
check('only the owner makes admins', member.call(role, {'steamId': THIRD_ID, 'role': 'admin'})[0] == 403)
check('the owner makes Member an admin', owner.call(role, {'steamId': MEMBER_ID, 'role': 'admin'})[1] == {'role': 'admin'})
st, lgd = member.call('/api/leagues/' + lid)
check('an admin sees the invite code and the bans', lgd['me']['role'] == 'admin' and lgd['code'] and lgd['bans'] == [] and
      'discord' not in lgd, lgd['me'])
check('...the roles on the drivers list', sorted((m['name'], m['role']) for m in lgd['members']) ==
      [('Member', 'admin'), ('Owner', 'owner'), ('Third', 'member')])
st, r = member.call('/api/seasons/%d/edit' % sid, {'name': 'Spring 2026', 'points': {'table': '10, 6, 4', 'finisher': 1},
                                                   'power': [3, 2, 1], 'drop': 1})
check('an admin edits a season', st == 200, r)
check('an admin makes no admins', member.call(role, {'steamId': THIRD_ID, 'role': 'admin'})[0] == 403)
check('an admin can\'t remove the owner', member.call('/api/leagues/%s/remove' % lid, {'steamId': OWNER_ID})[0] == 409)

# ---- the stewards: on the first event (Member finished; Third DNF on SS2)
pen = '/api/events/%d/penalty' % eid
check('a member gives no penalties', third.call(pen, {'steamId': MEMBER_ID, 'seconds': 10, 'reason': 'no'})[0] == 403)
check('a penalty needs a reason', member.call(pen, {'steamId': THIRD_ID, 'seconds': 10, 'reason': ''})[0] == 400)
st, r = member.call(pen, {'steamId': THIRD_ID, 'stage': 1, 'seconds': 30, 'reason': 'cut at the hairpin'})
check('an admin gives Third +30 s on SS1', st == 200 and r.get('id'), r)
pid = r['id']
st, r = owner.call(pen, {'steamId': MEMBER_ID, 'stage': '', 'seconds': '-2.5', 'reason': 'game glitch at the start'})
check('the owner gives Member 2.5 s back on the total', st == 200, r)
evd = member.call('/api/events/%d' % eid)[1]
third_row = next(x for x in evd['standings'] if x['steamId'] == THIRD_ID)
member_row = next(x for x in evd['standings'] if x['steamId'] == MEMBER_ID)
check('the penalties in the standings', third_row['stages'][0]['stewardMs'] == 30000 and third_row['stages'][0]['totalMs'] == 260000 and
      member_row['totalMs'] == 213597 + 29000 + 180400 + 250100 + 10000 - 2500 and member_row['stewardMs'] == -2500,
      (third_row['stages'][0], member_row['totalMs']))
check('SS1 positions move with the penalty', member_row['stages'][0]['pos'] == 1 and third_row['stages'][0]['pos'] == 2)
check('the decisions, with who made them', [(d['kind'], d['driver'], d['stage'], d['ms'], d['by']) for d in evd['decisions']] ==
      [('time', 'Third', 1, 30000, 'Member'), ('time', 'Member', None, -2500, 'Owner')], evd['decisions'])
check('a penalty taken back', member.call(pen, {'remove': pid})[1] == {'removed': True} and
      len(member.call('/api/events/%d' % eid)[1]['decisions']) == 1)
dsq = '/api/events/%d/dsq' % eid
check('a DSQ needs a reason', member.call(dsq, {'steamId': MEMBER_ID, 'reason': ''})[0] == 400)
check('an admin disqualifies Member (themselves, here)', member.call(dsq, {'steamId': MEMBER_ID, 'reason': 'wrong tyres'})[0] == 200)
evd = owner.call('/api/events/%d' % eid)[1]
mrow = next(x for x in evd['standings'] if x['steamId'] == MEMBER_ID)
check('a DSQ: no position, the reason shown, listed last', mrow['status'] == 'dsq' and mrow['reason'] == 'wrong tyres' and
      mrow.get('rank') is None and evd['standings'][-1]['steamId'] == MEMBER_ID, evd['standings'])
s1 = next(s for s in owner.call('/api/leagues/' + lid)[1]['seasons'] if s['name'] == 'Season 1')
mcell = next(p for p in s1['standings'] if p['steamId'] == MEMBER_ID)
check('...and no points', mcell['points'] == 0 and mcell['cells'][str(eid)]['dsq'] is True, s1['standings'])
check('...and the app is told', next(x for x in member.call('/api/me/events')[1]['events'] if x['id'] == eid)['entry']['status'] == 'dsq')
check('reinstated', owner.call(dsq, {'steamId': MEMBER_ID, 'remove': True})[0] == 200 and
      next(x for x in owner.call('/api/events/%d' % eid)[1]['standings'] if x['steamId'] == MEMBER_ID)['status'] == 'finished')

# ---- removing and banning
rm = '/api/leagues/%s/remove' % lid
st, r = third.call('/api/events/%d/start' % rounds[0], {'car': 'Hyundai i20 N Rally2'})
check('Third starts Spring 1 (open now)', st == 200 and r.get('started'), r)
st, r = member.call(rm, {'steamId': THIRD_ID, 'ban': True, 'reason': 'unsporting'})
check('an admin bans Third', st == 200 and r == {'removed': True, 'banned': True}, r)
check('...who can\'t come back with the code', third.call('/api/leagues/join', {'code': cur_code})[0] == 403)
check('...and is out of the league\'s events', third.call('/api/events/%d/begin' % rounds[0], {'no': 1})[0] == 403)
trow = next(x for x in owner.call('/api/events/%d' % rounds[0])[1]['standings'] if x['steamId'] == THIRD_ID)
check('...the event under way ending for them (DNF)', (trow['status'], trow['reason']) == ('dnf', 'removed from the league'), trow)
lgd = member.call('/api/leagues/' + lid)[1]
check('the ban listed for the staff', [(b['name'], b['reason']) for b in lgd['bans']] == [('Third', 'unsporting')], lgd['bans'])
check('unbanned', member.call('/api/leagues/%s/unban' % lid, {'steamId': THIRD_ID})[0] == 200 and
      third.call('/api/leagues/join', {'code': cur_code})[1].get('joined'))
check('the owner makes Member a member again', owner.call(role, {'steamId': MEMBER_ID, 'role': 'member'})[1] == {'role': 'member'})
check('a member removes nobody', member.call(rm, {'steamId': THIRD_ID})[0] == 403)

# ---- the league's Discord: a stand-in for Discord on this PC (the local server takes 127.0.0.1 webhooks)
import http.server  # noqa: E402
import threading  # noqa: E402
posts = []


class Hook(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        posts.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
        out = json.dumps({'id': str(len(posts))}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(('127.0.0.1', 0), Hook)
threading.Thread(target=srv.serve_forever, daemon=True).start()
hook_url = 'http://127.0.0.1:%d/api/webhooks/123456/test-token-ab12' % srv.server_address[1]
dc = '/api/leagues/%s/discord' % lid
check('only the owner connects Discord', member.call(dc, {'webhook': hook_url})[0] == 403)
check('a Discord webhook address only', owner.call(dc, {'webhook': 'https://example.com/hook'})[0] == 400)
st, r = owner.call(dc, {'webhook': hook_url})
check('the owner connects the league\'s channel', st == 200 and r == {'discord': {'set': True, 'hint': 'ab12'}}, r)
check('...never shown back whole', owner.call('/api/leagues/' + lid)[1]['discord'] == {'set': True, 'hint': 'ab12'})
check('a test message', owner.call(dc, {'test': True})[1] == {'sent': True} and posts and
      posts[-1][1]['embeds'][0]['title'] == 'ACR Daily is connected', posts[-1:] if posts else posts)
n0 = len(posts)
urllib.request.urlopen(BASE + '/cdn-cgi/local/scheduled').read()
for _ in range(40):
    if len(posts) > n0:
        break
    time.sleep(0.25)
time.sleep(1)
titles = [p[1]['embeds'][0]['title'] for p in posts[n0:]]
check('the cron posts the open events once', sorted(titles) == ['Round 1 is open', 'Spring 1 is open'], titles)
urllib.request.urlopen(BASE + '/cdn-cgi/local/scheduled').read()
time.sleep(1.5)
check('...and not again', len(posts) == n0 + 2, [p[1]['embeds'][0]['title'] for p in posts[n0:]])
check('nothing mentions anyone', all(p[1].get('allowed_mentions') == {'parse': []} for p in posts))
check('the owner disconnects it', owner.call(dc, {'remove': True})[1] == {'discord': {'set': False}})
srv.shutdown()

# ---- pages
for p in ['/leagues', '/l/' + lid, '/l/%s/new' % lid, '/e/%d' % eid, '/e/%d/edit' % eid, '/join/' + cur_code]:
    st, body = anon.call(p)
    check('page ' + p, st == 200 and '<script>' in body)
st, _ = owner.call('/logout?next=/leagues', {})
check('sign out of the website', owner.call('/api/me')[1] == {'signedIn': False})

print('\n%s' % ('ALL PASSED' if not fails else '%d FAILED' % fails))
sys.exit(1 if fails else 0)
