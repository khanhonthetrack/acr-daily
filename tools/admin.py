"""ACR Daily admin tool (needs the server URL and ADMIN_KEY).

  set ACR_DAILY_SERVER=https://acr-daily.you.workers.dev
  set ACR_DAILY_ADMIN_KEY=...

  python admin.py state                                  routes, pool, the next 7 days, flagged runs
  python admin.py route  routes\\Wales Afon Bidno.json    upload one reference route
  python admin.py routes routes                           upload every route in a folder
  python admin.py pool "Wales Afon Bidno"                 add a stage to the rotation (a random car each day)
  python admin.py pool "Wales Afon Bidno" "Mini Cooper S 1275"   ...or always with this car
  python admin.py pool "Wales Afon Bidno" --off            take it out
  python admin.py cars                                    the cars the random pick chooses from
  python admin.py stageid "Alsace Forêt" AlsaceS4SaverneFullForward
                                                          the game's id of a stage (for the app's "Drive daily")
  python admin.py schedule 2026-10-10 2 "Alsace Forêt" "Peugeot 208 Rally4" [LightRain] [evening]
                                                          fix daily 1 or 2 of a day (--remove to undo);
                                                          weather/time optional (random if left out)
  python admin.py run 123                                a run's realism checks, flags and reports
                                                         (or open https://<server>/run/123)
  python admin.py reject 123 "reason"                    remove a run from the board
  python admin.py ban 7656119xxxxxxxxxx  [--unban]

Routes come from the app's admin mode ("Record route", saved in %APPDATA%\\ACR Daily\\routes) or from
import_routes.py. Stage and car names must be exactly what the game reports (the app shows them).
"""
import glob
import json
import os
import sys
import urllib.error
import urllib.request

SERVER = os.environ.get('ACR_DAILY_SERVER', '').rstrip('/')
KEY = os.environ.get('ACR_DAILY_ADMIN_KEY', '')


def call(method, path, body=None):
    req = urllib.request.Request(SERVER + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY,
                                          # Cloudflare blocks the default "Python-urllib" user agent (error 1010)
                                          'User-Agent': 'ACR-Daily-admin/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit('error %d: %s' % (e.code, e.read().decode()))


def upload(path):
    with open(path, encoding='utf-8') as f:
        r = json.load(f)
    res = call('POST', '/api/admin/route', {'track': r['track'], 'points': r['points']})
    print('route %-28s %5.1f km  %3d checkpoints' % (res['track'], res['length'] / 1000, res['checkpoints']))


def main(a):
    if not SERVER or not KEY:
        sys.exit('set ACR_DAILY_SERVER and ACR_DAILY_ADMIN_KEY first (see SETUP.md)')
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
    elif a[0] == 'state':
        s = call('GET', '/api/admin/state')
        print('ROUTES')
        for r in s['routes']:
            print('  %-28s %5.1f km   %s' % (r['track'], r['length'] / 1000, r.get('stage_id') or '(no game stage id: set it with stageid)'))
        print('POOL')
        for p in s['pool']:
            print('  %-28s %-26s %s' % (p['track'], p['car'], 'on' if p['enabled'] else 'off'))
        print('NEXT 7 DAYS (UTC)')
        for d in s['next']:
            print('  %s  daily %s  %-22s %-30s %s · %s' % (d['date'], d.get('slot', 1), d['track'], d['car'],
                                                        d.get('weather') or '', d.get('time') or ''))
        if s['flagged']:
            print('RUNS TO REVIEW (look: admin.py run <id> or %s/run/<id>; remove: admin.py reject <id>)' % SERVER)
            for r in s['flagged']:
                print('  #%s %s %s %s ms  %s  %d report(s)' % (r['id'], r['date'], r['steam_id'], r['total_ms'],
                                                              ', '.join(json.loads(r['flags'] or '[]')) or '-', r['reports']))
    elif a[0] == 'run':
        d = call('GET', '/api/runs/%s' % a[1])
        print('#%s  %s  %s · %s  %s  %s ms (clock %s, %s reset(s))  %s' % (
            d['id'], d['date'], d['track'], d['car'], d['name'], d['totalMs'], d['clockMs'], d['resets'], d['status']))
        print('flags:   ', ', '.join(d['flags']) or '-')
        print('reports: ', d['reports'])
        for k, v in (d.get('checks') or {}).items():
            print('  %-20s %s' % (k, v))
        print('viewer:  %s/run/%s' % (SERVER, d['id']))
    elif a[0] == 'route':
        upload(a[1])
    elif a[0] == 'routes':
        for p in sorted(glob.glob(os.path.join(a[1], '*.json'))):
            upload(p)
    elif a[0] == 'pool':
        rest = [x for x in a[2:] if not x.startswith('--')]
        car = rest[0] if rest else '*'
        call('POST', '/api/admin/pool', {'track': a[1], 'car': car, 'enabled': '--off' not in a})
        print('pool:', a[1], '·', 'random car' if car == '*' else car, 'off' if '--off' in a else 'on')
    elif a[0] == 'stageid':
        call('POST', '/api/admin/stage-id', {'track': a[1], 'stageId': a[2]})
        print('stage id:', a[1], '=', a[2])
    elif a[0] == 'cars':
        for c in call('GET', '/api/cars'):
            print('  %-10s %s' % (c['cls'], c['name']))
    elif a[0] == 'schedule':
        rest = [x for x in a[1:] if not x.startswith('--')]
        body = {'date': rest[0], 'slot': int(rest[1]), 'remove': '--remove' in a}
        if not body['remove']:
            body.update(track=rest[2], car=rest[3])
            if len(rest) > 4:
                body['weather'] = rest[4]
            if len(rest) > 5:
                body['time'] = rest[5]
        call('POST', '/api/admin/schedule', body)
        print('schedule:', ' '.join(rest), '(removed)' if body['remove'] else '')
    elif a[0] == 'reject':
        call('POST', '/api/admin/runs/%s/reject' % a[1], {'reason': a[2] if len(a) > 2 else 'rejected by admin'})
        print('rejected run', a[1])
    elif a[0] == 'ban':
        call('POST', '/api/admin/ban', {'steamId': a[1], 'banned': '--unban' not in a})
        print('unbanned' if '--unban' in a else 'banned', a[1])
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
