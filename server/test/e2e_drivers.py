"""End-to-end test of the driver pages, names, pictures, flags, teams and the rating against a local server:

  npx wrangler dev --port 8797 --ip 127.0.0.1 --local-upstream 127.0.0.1:8797 --persist-to <fresh dir> --var CREDITS_FROM:2000-01-01 --var OFFICIAL_FROM: --var RATING_FROM:<today, UTC>
  python test/e2e_drivers.py http://127.0.0.1:8797 <ADMIN_KEY>

(a fresh database each run: `npx wrangler d1 execute acr-daily --local --persist-to <dir> --file=schema.sql`;
DEV_LOGIN=1 in .dev.vars). A name of one's own on the timing sheet and kept through a new sign-in, a lookalike
refused; a picture up and served; a team made and joined, its tag on the timing sheet; the driver page, the world
ranking after today's dailies are taken (the dev-only /api/admin/results-tick as the cron would, the next night); an
admin putting a name back; the pages.
"""
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
WEB = 'Mozilla/5.0 (a browser)'   # the website's driver page (the app gets the light one)
fails = 0


def check(name, cond, info=''):
    global fails
    print(('  ok    ' if cond else '  FAIL  ') + name + ('' if cond else '  ' + str(info)[:400]))
    if not cond:
        fails += 1


def call(path, body=None, token=None, admin=False, raw=None, ctype=None, ua=APP_UA):
    h = {'User-Agent': ua}
    if token or admin:
        h['Authorization'] = 'Bearer ' + (KEY if admin else token)
    data = None
    if raw is not None:
        data, h['Content-Type'] = raw, ctype
    elif body is not None:
        data, h['Content-Type'] = json.dumps(body).encode(), 'application/json'
    req = urllib.request.Request(BASE + path, data=data, headers=h, method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def get(path):
    """A page or a file: (status, content type, bytes), redirects not followed."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(BASE + path, timeout=30) as r:
            return r.status, r.headers.get('Content-Type'), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type'), e.headers.get('Location') or b''


def app_user(steam_id, name):
    state = 'dr-%s-%d' % (steam_id, time.time() * 1000)
    urllib.request.urlopen(BASE + '/auth/dev?state=%s&steamId=%s&name=%s' % (state, steam_id, name)).read()
    return json.loads(urllib.request.urlopen(BASE + '/auth/poll?state=' + state).read())


def png(w, h):
    """A plain PNG picture, w x h."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + b'\xe3\x06\x13' * w for _ in range(h))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def board_entry(steam_id):
    return next((e for e in call('/api/leaderboard?slot=1')[1]['entries'] if e['steamId'] == steam_id), {})


# a stage, and three drivers with a run each on today's daily 1
fx = json.load(open(os.path.join(HERE, 'fixtures', 'wales.json'), encoding='utf-8'))
call('/api/admin/route', {'track': 'Wales Afon Bidno', 'points': fx['route'], 'stageId': 'WelesS4HafrenSouthFullForward'}, admin=True)
call('/api/admin/pool', {'track': 'Wales Afon Bidno', 'car': 'Hyundai i20 N Rally2'}, admin=True)
chs = {c['slot']: c for c in call('/api/challenges/today')[1]['challenges']}
date = chs[1]['date']
ids = {k: '765611900000004%02d' % i for i, k in enumerate(['Ann', 'Ben', 'Cy'])}
tok = {k: app_user(v, k)['token'] for k, v in ids.items()}
for k in ('Ann', 'Ben'):
    ch = chs[1]
    st, r = call('/api/runs', dict(fx['result'], challengeId='%s/1' % date, track=ch['track'], car=ch['car'], startedAt=time.time()),
                 token=tok[k])
check('two runs on today\'s daily', len(call('/api/leaderboard?slot=1')[1]['entries']) == 2)
A, B, C = tok['Ann'], tok['Ben'], tok['Cy']

# ---- a name of one's own
st, r = call('/api/me/name', {'name': '  Speedy   Ann '}, token=A)
check('Ann takes a name of her own', (st, r) == (200, {'name': 'Speedy Ann', 'custom': True}), (st, r))
check('...on the timing sheet at once', board_entry(ids['Ann']).get('name') == 'Speedy Ann', board_entry(ids['Ann']))
check('...and in the app\'s credits line', call('/api/credits', token=A)[1].get('name') == 'Speedy Ann')
check('a lookalike is refused', call('/api/me/name', {'name': 'speedy.ann'}, token=B)[0] == 409)
check('another driver\'s name is refused', call('/api/me/name', {'name': 'cy'}, token=B)[0] in (400, 409))
check('one change a week', call('/api/me/name', {'name': 'Speedy Ann Two'}, token=A)[0] == 429)
check('names need a sign-in', call('/api/me/name', {'name': 'Nobody'})[0] == 401)
again = app_user(ids['Ann'], 'Ann')
check('a new sign-in keeps it (Steam\'s name is kept apart)', again['name'] == 'Speedy Ann', again)
A = again['token']

# ---- a picture
pic = png(256, 256)
st, r = call('/api/me/avatar', raw=pic, ctype='image/png', token=A)
check('Ann puts up a picture', st == 200 and '/avatar/%s?v=' % ids['Ann'] in (r.get('avatar') or ''), (st, r))
url = r.get('avatar') or ''
st, ct, body = get(url[url.index('/avatar/'):]) if url else (0, '', b'')
check('...served as it was sent', (st, ct, body) == (200, 'image/png', pic), (st, ct, len(body or b'')))
check('...on the timing sheet', board_entry(ids['Ann']).get('avatar') == url)
check('a wide picture is refused', call('/api/me/avatar', raw=png(600, 200), ctype='image/png', token=B)[0] == 422)
check('not a picture: refused', call('/api/me/avatar', raw=b'hello' * 20, ctype='image/png', token=B)[0] == 415)

# ---- a flag: the app's in-game country until the driver picks one on their page
def live(country):   # Ann on daily 1 again (a position from the app, which sends the in-game country with it)
    return call('/api/live', {'challengeId': '%s/1' % date, 'x': 0, 'z': 0, 'progress': 0.5, 'totalMs': 1000, 'resets': 0,
                              'state': 'live', 'startedAt': time.time(), 'country': country}, token=A)[0]
def flag_of(sid):
    return call('/api/drivers/%s' % sid)[1].get('country')
check('the app sends Italy', live('Italy') == 200 and flag_of(ids['Ann']) == 'it', flag_of(ids['Ann']))
st, r = call('/api/me/country', {'country': 'gb-sct'}, token=A)
check('Ann picks Scotland', (st, r) == (200, {'country': 'gb-sct'}), (st, r))
check('...on the timing sheet at once', board_entry(ids['Ann']).get('country') == 'gb-sct', board_entry(ids['Ann']))
check('...and the app\'s Italy no longer changes it', live('Italy') == 200 and flag_of(ids['Ann']) == 'gb-sct')
check('a country not on the list is refused', call('/api/me/country', {'country': 'zz'}, token=B)[0] == 400)
check('flags need a sign-in', call('/api/me/country', {'country': 'pl'})[0] == 401)
me = call('/api/drivers/%s' % ids['Ann'], token=A, ua=WEB)[1]
check('her page: Scotland, picked', me.get('country') == 'gb-sct' and (me.get('me') or {}).get('countrySet') is True, me.get('me'))

# ---- a team
st, r = call('/api/teams', {'name': 'Gravel Foxes', 'tag': 'gfx', 'color': '#7BE07B'}, token=A)
check('Ann makes a team', st == 200 and r.get('id'), (st, r))
team = r.get('id')
t = call('/api/teams/%s' % team, token=A)[1]
check('...its code for its members', t.get('code') and call('/api/teams/%s' % team, token=C)[1].get('code') is None, t)
check('Ben joins with the code', call('/api/teams/join', {'code': t.get('code')}, token=B)[0] == 200)
check('a wrong code', call('/api/teams/join', {'code': 'ZZZZ-ZZZZ'}, token=C)[0] == 404)
check('the tag is the team\'s', call('/api/teams', {'name': 'Copies', 'tag': 'GFX', 'color': '#5BA8FF'}, token=C)[0] == 409)
e = board_entry(ids['Ben'])
check('the tag by Ben\'s name on the timing sheet', (e.get('look') or {}).get('tag') == {'text': 'GFX', 'color': '#7BE07B'}, e)
check('the teams', [x['tag'] for x in call('/api/teams')[1]['teams']] == ['GFX'])
# styled like Trackmania: the captain colours each letter; the timing sheet and the app's strip get the codes
st, r = call('/api/teams/%s/edit' % team, {'name': '$f90Gravel $fffFoxes', 'tag': '$f00G$fffF$00fX', 'color': '#7BE07B'}, token=A)
check('Ann styles the name and tag', st == 200, (st, r))
check('...on the timing sheet', (board_entry(ids['Ben']).get('look') or {}).get('tag') == {'text': 'GFX', 'color': '#7BE07B', 'fmt': '$f00G$fffF$00fX'})
lt = (call('/api/drivers/%s' % ids['Ben'])[1].get('team') or {})
check('...in the app\'s driver strip', (lt.get('tag'), lt.get('tagFmt')) == ('GFX', '$f00G$fffF$00fX'), lt)
check('...a copy styled otherwise still taken', call('/api/teams', {'name': 'Copies', 'tag': '$o$0f0gfx', 'color': '#5BA8FF'}, token=C)[0] == 409)

# ---- the driver page; the rating once the day is taken (as the cron would, the next night)
p = call('/api/drivers/%s' % ids['Ann'], ua=WEB)[1]
check('Ann\'s page', p.get('name') == 'Speedy Ann' and p.get('steamName') == 'Ann' and (p.get('team') or {}).get('tag') == 'GFX'
      and p['stats']['runs'] == 1 and p['rating'] is None, p)
tomorrow2am = (int(time.time() // 86400) + 1) * 86400000 + 2 * 3600000
st, r = call('/api/admin/results-tick', {'now': tomorrow2am, 'first': date, 'perRun': 4}, admin=True)
check('today\'s dailies taken and rated', st == 200 and [(x['date'], x['slot'], x['rated']) for x in r] == [(date, 1, True), (date, 2, False)], r)
check('...once', call('/api/admin/results-tick', {'now': tomorrow2am, 'first': date, 'perRun': 4}, admin=True)[1] == [])
p = call('/api/drivers/%s' % ids['Ann'], ua=WEB)[1]
check('Ann rated, in the world ranking', p['rating'] and p['rating']['of'] == 2 and p['recent'][0]['date'] == date
      and p['recent'][0]['place'] in (1, 2), p)
rk = call('/api/ranking', token=B)[1]
check('the ranking: both, Ben\'s place', len(rk['rows']) == 2 and rk['me']['rank'] in (1, 2) and rk['ratingOn'], rk)

# ---- an admin puts a name back; the pages
check('an admin puts Ann\'s name back', call('/api/admin/driver', {'steamId': ids['Ann'], 'avatar': False}, admin=True)[0] == 200
      and board_entry(ids['Ann']).get('name') == 'Ann' and board_entry(ids['Ann']).get('avatar') == url)
for path in ('/d/%s' % ids['Ann'], '/ranking', '/teams', '/t/%s' % team, '/inbox'):
    st, ct, body = get(path)
    check('the page ' + path, st == 200 and 'text/html' in ct and b'<script>' in body, (st, ct))
st, ct, loc = get('/me')
check('/me signed out: the sign-in first', st == 302 and '/login?next=/me' in loc, (st, loc))
check('the inbox says messages are not private', b"Messages aren't private" in get('/inbox')[2])

print('\nALL PASSED' if not fails else '\n%d FAILED' % fails)
sys.exit(1 if fails else 0)
