"""Fill a local test server with leagues to click through: a public league with a banner and a season (Power Stage, worst
round dropped), a finished round with results and a steward's penalty, an open one under way, an open one-off class event
and a round coming up; an admin; a private league; made-up drivers. The stages: every one of the game's, with the
routes the live site has (read from acrdaily.com; three test stages when it can't be reached).

  npx wrangler d1 execute acr-daily --local --persist-to .wrangler/test-site --file=schema.sql
  npx wrangler dev --port 8795 --ip 127.0.0.1 --local-upstream 127.0.0.1:8795 --persist-to .wrangler/test-site
  python test/seed_leagues.py http://127.0.0.1:8795 <ADMIN_KEY>

Then open http://127.0.0.1:8795/leagues. Sign in with Steam as usual, or as a made-up driver:
http://127.0.0.1:8795/login?next=/leagues&dev=76561190000000099&name=Tester (DEV_LOGIN=1 in .dev.vars).
The finished round is made as an open one, then moved into the past in the database (the API only makes events that
are still to come): this script prints the command for that, run it while the server runs.
"""
import http.cookiejar
import json
import os
import struct
import sys
import time
import urllib.request
import uuid
import zlib

BASE, KEY = sys.argv[1].rstrip('/'), sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
APP = 'ACR-Daily/9.9.9 public'           # an app new enough for leagues
H = 3600000
DAY = 24 * H


def call(op, path, body=None, token=None, raw=None, ctype=None, ua='Mozilla/5.0'):
    h = {'User-Agent': ua}
    if token:
        h['Authorization'] = 'Bearer ' + token
    data = raw
    if body is not None:
        data, h['Content-Type'] = json.dumps(body).encode(), 'application/json'
    elif raw is not None:
        h['Content-Type'] = ctype
    with op.open(urllib.request.Request(BASE + path, data=data, headers=h, method='POST' if data is not None else 'GET')) as r:
        return json.loads(r.read().decode())


def web(steam_id, name):
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(BASE + '/login?next=/leagues&dev=%s&name=%s' % (steam_id, urllib.request.quote(name))).read()
    return op


def app(steam_id, name):
    state = uuid.uuid4().hex
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, urllib.request.quote(name))).read()
    return json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())['token']


def banner(w=1200, h=400):
    """A dusk-gravel gradient as a PNG (no image library needed)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = []
    for y in range(h):
        t = y / (h - 1)
        sky = (int(40 + 180 * (1 - t)), int(20 + 60 * (1 - t)), int(30 + 20 * t))
        row = bytearray()
        for x in range(w):
            hill = y > h * (0.62 + 0.12 * ((x / w - 0.5) ** 2) * 4)
            row += bytes((70, 52, 38) if hill else sky)
        rows.append(b'\0' + bytes(row))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))


LIVE = 'https://acrdaily.com'


def admin_post(path, body):
    urllib.request.urlopen(urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method='POST',
                                                  headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY})).read()


def live_routes():
    """Every stage the live site has a route for (all of the game's: 44), copied here. -> how many, or 0 offline."""
    get = lambda p: json.loads(urllib.request.urlopen(urllib.request.Request(LIVE + p, headers={'User-Agent': 'Mozilla/5.0'}),
                                                      timeout=20).read())
    try:
        routes = get('/api/routes')
        for r in routes:
            if r.get('stageId'):
                pts = get('/api/route?track=' + urllib.request.quote(r['track']))['route']
                admin_post('/api/admin/route', {'track': r['track'], 'points': pts, 'stageId': r['stageId']})
        return len(routes)
    except (OSError, ValueError, KeyError):
        return 0


# the stages: every one of the game's from the live site, else three Wales ones with the test fixtures' route
copied = live_routes()
print('stages copied from %s: %d' % (LIVE, copied) if copied else 'live site not reachable: three test stages')
route = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))['route']
for track, sid in (('Wales Afon Bidno', 'WelesS4HafrenSouthFullForward'), ('Wales Severn', 'WelesS4HafrenSouthFullReverse'),
                   ('Wales Cwmbiga', 'WelesS3HafrenNorthFullForward')):
    if not copied:
        admin_post('/api/admin/route', {'track': track, 'points': route, 'stageId': sid})
    admin_post('/api/admin/pool', {'track': track, 'car': 'Hyundai i20 N Rally2'})      # today's dailies: these three

boss = web('76561190000000011', 'Gravel Boss')
lg = call(boss, '/api/leagues', {'name': 'Sunday Gravel Club', 'public': True,
                                 'about': 'Weekly gravel rallies, one round every weekend.\nAll welcome, be fair, no restarts.'})
call(boss, '/api/leagues/%s/banner' % lg['id'], raw=banner(), ctype='image/png')
priv = call(boss, '/api/leagues', {'name': 'Friday Night Crew', 'public': False, 'about': 'Invite only.'})
cat = call(boss, '/api/catalog')
wales = [s['track'] for s in next(r for r in cat['rallies'] if r['name'] == 'Wales')['stages']]
now = int(time.time() * 1000)


season = call(boss, '/api/leagues/%s/seasons' % lg['id'], {'name': 'Autumn 2026', 'points': {'table': [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
                                                     'finisher': 1}, 'power': [5, 4, 3, 2, 1], 'drop': 1})['id']


def event(name, stages, opens, closes, car='Hyundai i20 N Rally2', cls=None, rules=None, season_id=season):
    body = {'name': name, 'rally': 'Wales', 'rules': rules or {}, 'stages': stages, 'opens': opens, 'closes': closes,
            'seasonId': season_id}
    body.update({'carClass': cls} if cls else {'car': car})
    return call(boss, '/api/leagues/%s/events' % lg['id'], body)['id']


three = [{'track': wales[0], 'day': 1, 'weather': 'Clear', 'time': '09:00'},
         {'track': wales[1], 'day': 1, 'service': True, 'weather': 'LightRain', 'time': '13:00'},
         {'track': wales[2], 'day': 2, 'weather': 'HeavyCloud', 'time': '10:00'}]
past = event('Round 1 · Rally of Wales', three, now - 60000, now + 2 * H)
cur = event('Round 2 · Wet Wales', [dict(s, weather='HeavyRain') for s in three], now - 60000, now + 3 * DAY,
            rules={'damageIntensity': 'severe', 'penalty': 'realistic'})
event('Night Sprint', [{'track': wales[2], 'day': 1, 'weather': 'Clear', 'time': '21:00'}], now - 60000, now + 2 * DAY,
      car=None, cls='Rally2/R5', season_id=None)
event('Round 3 · Long Weekend', three + [{'track': wales[0], 'day': 2, 'service': True, 'weather': 'Clear', 'time': '15:00'}],
      now + 2 * DAY, now + 6 * DAY)

drivers = [('76561190000000031', 'Ana Kowalska'), ('76561190000000032', 'Bo Lindqvist'), ('76561190000000033', 'Kalle R.'),
           ('76561190000000034', 'Sami P.'), ('76561190000000035', 'Ott T.')]
tokens = {}
for sid, name in drivers:
    tokens[sid] = app(sid, name)
    call(urllib.request.build_opener(), '/api/leagues/%s/join' % lg['id'], {}, token=tokens[sid])


def drive(eid, sid, times, dnf=None):
    op, t = urllib.request.build_opener(), tokens[sid]
    call(op, '/api/events/%d/start' % eid, {'car': 'Hyundai i20 N Rally2'}, token=t, ua=APP)
    for k, (ms, pen) in enumerate(times):
        if k:
            call(op, '/api/events/%d/begin' % eid, {'no': k}, token=t, ua=APP)
        call(op, '/api/events/%d/stage' % eid, {'no': k, 'timeMs': ms, 'penaltyMs': pen,
                                               'splitsMs': [ms // 3, 2 * ms // 3]}, token=t, ua=APP)
    if dnf:
        call(op, '/api/events/%d/dnf' % eid, {'no': len(times), 'reason': dnf}, token=t, ua=APP)


drive(past, drivers[0][0], [(201230, 0), (176400, 10000), (241900, 0)])
drive(past, drivers[1][0], [(199870, 0), (180100, 0), (243450, 20000)])
drive(past, drivers[2][0], [(205100, 0), (174900, 0), (238800, 0)])
drive(past, drivers[3][0], [(203300, 30000)], dnf='retired on SS2')
drive(cur, drivers[0][0], [(214500, 0), (190020, 10000)])
drive(cur, drivers[2][0], [(209800, 0), (187700, 0), (252100, 0)])
drive(cur, drivers[4][0], [(219000, 60000)], dnf='SS2 started again')
# the stewards: Ana is an admin; Bo gets 10 s for a cut on Round 1's SS2
call(boss, '/api/leagues/%s/role' % lg['id'], {'steamId': drivers[0][0], 'role': 'admin'})
call(boss, '/api/events/%d/penalty' % past, {'steamId': drivers[1][0], 'stage': 2, 'seconds': 10,
                                             'reason': 'cut at the junction after split 2 (video from Kalle R.)'})
print('league', lg['id'], '(private: %s, invite /join/%s)' % (priv['id'], priv['code'].replace('-', '')))
print('to move Round 1 into the past, run (from server/):')
print('  npx wrangler d1 execute acr-daily --local --persist-to .wrangler/test-site --command "UPDATE league_events SET '
      'opens = %d, closes = %d WHERE id = %d"' % (now - 7 * DAY, now - 4 * DAY, past))
