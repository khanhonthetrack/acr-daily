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
  python admin.py fix-run 123 1 2:57.670 [--dry-run]     set a finished run's resets (+60 s each) and its total;
                                                         give the stage clock of each reset and its split times
                                                         follow too (--dry-run: show the change, write nothing)
  python admin.py resets 123                             where a run's trace shows resets (to use with fix-run)
  python admin.py discord [force]                        run the Discord bot's minute now (it runs every minute);
                                                         force re-sends the live board (re-posts it if it was deleted)
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


def clock_ms(text):
    """'2:57.670' or '177670' -> 177670."""
    if ':' in text:
        m, s = text.split(':')
        return int(round((int(m) * 60 + float(s)) * 1000))
    return int(text)


def fmt(ms):
    return '-' if ms is None else '%d:%06.3f' % (ms // 60000, ms % 60000 / 1000)


def trace_resets(trace):
    """Stage clock (ms) of each reset the trace shows, by the app's rules (client/acr_daily/judge.py): a jump no
    car could drive, or standing still in neutral within 0.6 s of driving in gear at 30 km/h or more.
    Sample: [clockMs, x, z, kmh, resets, wallMs, physicsPackets, throttle, brake, steer, gear, rpm, ...]"""
    out, fast_at, last = [], None, -10 ** 9
    for prev, s in zip([None] + trace[:-1], trace):
        gear = s[10] if len(s) > 10 else None
        if s[3] >= 30 and gear is not None and gear > 1:
            fast_at = s[5]
        hit = s[3] < 1 and gear == 1 and fast_at is not None and s[5] - fast_at <= 600
        if prev is not None and not hit:
            d = ((s[1] - prev[1]) ** 2 + (s[2] - prev[2]) ** 2) ** 0.5
            kmh = max(prev[3], s[3])
            hit = d > (3 if kmh < 10 else 15) + kmh / 3.6 * max(s[5] - prev[5], 0) / 1000 * 1.5
        if hit and s[5] - last >= 3000:      # one reset is never counted twice
            out.append(s[0])
            last, fast_at = s[5], None
    return out


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
    elif a[0] == 'resets':
        t = call('GET', '/api/runs/%s/trace' % a[1])
        found = trace_resets(t['trace'])
        print('run #%s %s: %d reset(s) in the trace%s' % (a[1], fmt(t['totalMs']), len(found),
                                                        ''.join('  ' + fmt(x) for x in found)))
        if found:
            print('to set them: python admin.py fix-run %s %d %s --dry-run' % (a[1], len(found), ' '.join(fmt(x) for x in found)))
    elif a[0] == 'discord':
        print(json.dumps(call('POST', '/api/admin/discord', {'force': a[1:2] == ['force']}), indent=1))
    elif a[0] == 'fix-run':
        rest = [x for x in a[1:] if not x.startswith('--')]
        body = {'resets': int(rest[1]), 'dryRun': '--dry-run' in a}
        if len(rest) > 2:
            body['at'] = [clock_ms(x) for x in rest[2:]]
        elif body['resets'] == 0:
            body['at'] = []          # no resets anywhere: the trace and splits lose any set before too
        r = call('POST', '/api/admin/runs/%s/fix' % rest[0], body)
        b, n = r['before'], r['after']
        print('%srun #%s: %d reset(s) %s  ->  %d reset(s) %s   (P%s on the day\'s board)' % (
            'DRY RUN, nothing written. ' if r['dryRun'] else '', r['id'], b['resets'], fmt(b['totalMs']),
            n['resets'], fmt(n['totalMs']), r['rank'] or '-'))
        if n.get('splits') != b.get('splits'):
            print('  splits %s  ->  %s' % (' '.join(fmt(x) for x in b['splits'] or []), ' '.join(fmt(x) for x in n['splits'] or [])))
    elif a[0] == 'ban':
        call('POST', '/api/admin/ban', {'steamId': a[1], 'banned': '--unban' not in a})
        print('unbanned' if '--unban' in a else 'banned', a[1])
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
