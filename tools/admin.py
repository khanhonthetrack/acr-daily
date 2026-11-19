"""ACR Daily admin tool (needs the server URL and ADMIN_KEY).

  set ACR_DAILY_SERVER=https://acr-daily.you.workers.dev
  set ACR_DAILY_ADMIN_KEY=...

  python admin.py state                                  routes, pool, the next 30 days, flagged runs
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
  python admin.py cup new cups\\inaugural-cup.json         an official cup (ACR Daily's own): its settings, what every
                                                         match races and its banner from the file (see cups\\)
                                                         (its "event" may have "hide": {"weather", "times", "stages"}
                                                         true / false; left out: all three hidden until the cup is over)
  python admin.py cup set k7q2m9xp cups\\inaugural-cup.json
                                                         change an official cup before it starts (what the file has)
  python admin.py cup off k7q2m9xp                       call an official cup off (every fee back, drivers told)
  python admin.py tcup new tcups\\autumn-team-cup.json   an official team cup (ACR Daily's own): its settings, how a match
                                                         is scored (scoring, lineupFor, rosterMin, rosterMax), what every
                                                         match races and its banner from the file (see tcups\\)
  python admin.py tcup set k7q2m9xp tcups\\autumn-team-cup.json
                                                         change an official team cup before it starts (what the file has)
  python admin.py tcup off k7q2m9xp                      call an official team cup off (every team told)
  python admin.py league new leagues\\exr-rally-championship.json
                                                         an official league (ACR Daily's own): its settings, banner, admins
                                                         (Steam ids: they run it on the website), its season and its rounds
                                                         (one a week from "starts", each in the next rally of the list, its stages and
                                                         weather drawn by the server and hidden until the round ends);
                                                         (a private one: drivers ask to join on its page, its admins
                                                         accept them)
  python admin.py league set k7q2m9xp leagues\\exr-rally-championship.json
                                                         change it from the file ("public": true: anyone joins); rounds the
                                                         file has that aren't made yet are added (more "weeks": more rounds)
  python admin.py ahead [--repick]                      fix the coming 30 days' dailies now (the server does it every
                                                         hour by itself); --repick: pick the days not started yet
                                                         again from the pool as it is now (after changing the pool)
  python admin.py run 123                               a run's realism checks, flags and reports
                                                         (or open https://<server>/run/123)
  python admin.py reject 123 "reason"                    remove a run from the board
  python admin.py tt-reject 45 "reason"                  remove a time trial run from its board (the driver's next best counts)
  python admin.py tt-schedule 2026-11-16 1 "London Westminster" "*" Clear midday
                                                         fix a coming week's time trial stage 1 or 2 (the week's Monday;
                                                         the stage's telemetry name, which needs its route; a car or "*"
                                                         for one drawn; weather / time optional); --remove to undo
  python admin.py tt-private "<track>|<car>[|weather|time]" ... [--title "..."] [--days 7] [--min-app 0.1.5.42]
                                                         a private time trial page: its stages (each the telemetry name,
                                                         which needs its route, and a car; weather / time optional), open
                                                         from now for --days, seen by apps from --min-app on; prints its
                                                         link (/tt/p/<code>: share it, nothing links to it)
  python admin.py tt-private <code> [--title ...] [--min-app V | --min-app ""] [--ends 2026-11-25T18:00]
                                                         a private page changed: its title, its apps, its close (UTC)
  python admin.py comments [days]                       the drivers' comments of the last 7 days (or `days`), every
                                                         kind: dailies, time trial, league events, cup and 1V1 matches
  python admin.py comment-hide 12 [--show]               take a comment down (off the boards and pages; its driver still
                                                         sees it), or put it back
  python admin.py reinstate 123 [7.5]                    a daily DNF whose result the game lost ("the game closed before
                                                         saving...", case by case) on the board, flagged (and the free
                                                         daily's finish bonus): the app's stage clock + the game's penalty
                                                         in seconds when you know it (e.g. from the driver); without it,
                                                         + 10 s a respawn
  python admin.py fix-run 123 1 2:57.670 [--dry-run]     set a finished run's resets (+60 s each) and its total;
                                                         give the stage clock of each reset and its split times
                                                         follow too (--dry-run: show the change, write nothing)
  python admin.py resets 123                             where a run's trace shows resets (to use with fix-run)
  python admin.py discord [force]                        run the Discord bot now (it runs every 5 minutes);
                                                         force re-sends the live board (re-posts it if it was deleted)
  python admin.py ban 7656119xxxxxxxxxx  [--unban]
  python admin.py organizer 7656119xxxxxxxxxx [--off]    a Community organizer: makes championships (anyone makes
                                                         rallies); --off: no longer one (their championships stay)
  python admin.py league-banner k7q2m9xp                 take down a league's banner (the id is in its address /l/<id>)
  python admin.py driver-reset 7656119xxxxxxxxxx [--name|--picture]
                                                         a driver's own name and picture (or just one) back to Steam's
  python admin.py team-delete k7q2m9xp                   close a team (an offensive name or tag; its address /t/<id>)
  python admin.py rally-delete 123                       take a rally down (an offensive name or words; its page /e/<id>)
  python admin.py move-traces                            the traces still kept as plain JSON: gzipped where they are,
                                                         or (once the server has an R2 bucket) all of them into R2
  python admin.py liveries [pending|flagged|published|rejected|hidden|all]
                                                         the liveries drivers sent (default: waiting to be published)
                                                         with their link; or look at them on the /admin page
  python admin.py livery 12 publish|reject|hide|clear|delete ["note for the sender"] [--link https://...]
                                                         publish one (it shows on /liveries and in the app), turn it
                                                         down or take it off (the sender is told, with the note),
                                                         clear its "link not working" reports, mend its link, delete it
  python admin.py livery-import liveries\found.json [--pending]
                                                         liveries found on the web, put on /liveries and in the app at
                                                         once (--pending: to look at them on /admin first). The file: a
                                                         list of {car (its id: src/cars.js), title, author, link (the
                                                         author's own page: the file stays there), description, image
                                                         (the preview: an address or a file beside the list)}. A link
                                                         already on the page is left as it is: run it again safely

Routes come from the app's admin mode ("Record route", saved in %APPDATA%\\ACR Daily\\routes) or from
import_routes.py. Stage and car names must be exactly what the game reports (the app shows them).
"""
import base64
import datetime
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


def utc(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime('%a %d %b %H:%M UTC')


SHOT_W, SHOT_BYTES = 1600, 1000000      # a livery's preview, as the website's form makes it (src/liveries.js LIVERY)


def preview(image, base):
    """A livery's preview as a data URL: the picture at an address or in a file (beside the list), made a JPEG at
    most SHOT_W wide and SHOT_BYTES big (with Pillow; without it, sent as it is when it fits)."""
    if image.startswith('https://') or image.startswith('http://'):
        req = urllib.request.Request(image, headers={'User-Agent': 'ACR-Daily-admin/1.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    else:
        with open(os.path.join(base, image), 'rb') as f:
            raw = f.read()
    try:
        import io
        from PIL import Image
    except ImportError:
        kind = 'jpeg' if raw[:3] == b'\xff\xd8\xff' else 'png' if raw[:8] == b'\x89PNG\r\n\x1a\n' else \
            'webp' if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP' else None
        if not kind or len(raw) > SHOT_BYTES:
            raise ValueError('pip install pillow (the picture has to be made a JPEG of 1 MB at most)')
        return 'data:image/%s;base64,%s' % (kind, base64.b64encode(raw).decode())
    img = Image.open(io.BytesIO(raw)).convert('RGB')
    if img.width > SHOT_W:
        img = img.resize((SHOT_W, round(img.height * SHOT_W / img.width)), Image.LANCZOS)
    for quality in (88, 80, 72, 64, 56):
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=quality, optimize=True)
        if out.tell() <= SHOT_BYTES:
            return 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode()
    raise ValueError('the picture is too big even as a small JPEG')


def import_liveries(path, pending=False):
    """livery-import: each livery of the list on the page (or waiting, pending); a failed one said and skipped."""
    with open(path, encoding='utf-8') as f:
        found = json.load(f)
    base, added, there, failed = os.path.dirname(os.path.abspath(path)), 0, 0, 0
    for l in found:
        name = '%s (%s)' % (l.get('title'), l.get('car'))
        try:
            body = {k: l.get(k) for k in ('car', 'title', 'author', 'link', 'description')}
            body['shot'] = preview(l['image'], base)
            if pending:
                body['status'] = 'pending'
            req = urllib.request.Request(SERVER + '/api/admin/liveries', method='POST', data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY,
                                                  'User-Agent': 'ACR-Daily-admin/1.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            failed += 1
            print('  not added  %s: error %d %s' % (name, e.code, e.read().decode()[:200]))
            continue
        except (KeyError, OSError, ValueError) as e:
            failed += 1
            print('  not added  %s: %s' % (name, e))
            continue
        if res.get('existing'):
            there += 1
            print('  there      #%-4s %s (%s)' % (res['id'], name, res['status']))
        else:
            added += 1
            print('  added      #%-4s %s (%s)' % (res['id'], name, res['status']))
    print('%d added, %d already there, %d not added' % (added, there, failed))


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
        print('NEXT %d DAYS (UTC)' % len({d['date'] for d in s['next']}))
        for d in s['next']:
            print('  %s  daily %s  %-34s %-34s %s · %s%s' % (d['date'], d.get('slot', 1), d['track'], d['car'],
                                                          d.get('weather') or '', d.get('time') or '',
                                                          '   set by ' + d['setBy'] if d.get('setBy') else ''))
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
    elif a[0] == 'cup':
        if a[1] == 'off':
            r = call('POST', '/api/admin/cup', {'id': a[2], 'cancel': True})
            print('called off: %s (%d fee(s) back)' % (a[2], r.get('refunded', 0)))
            return
        path = a[2] if a[1] == 'new' else a[3]
        with open(path, encoding='utf-8-sig') as f:       # (Notepad may save it with a BOM)
            body = json.load(f)
        if isinstance(body.get('starts'), str):            # "2026-10-18T18:00:00Z" -> ms
            body['starts'] = int(datetime.datetime.fromisoformat(body['starts'].replace('Z', '+00:00')).timestamp() * 1000)
        if body.get('banner'):                             # a picture next to the file -> base64
            with open(os.path.join(os.path.dirname(path), body['banner']), 'rb') as f:
                body['banner'] = base64.b64encode(f.read()).decode()
        if a[1] == 'set':
            body['id'] = a[2]
        r = call('POST', '/api/admin/cup', body)
        print('%s: %s/cup/%s' % ('made' if a[1] == 'new' else 'changed', SERVER, r['id']))
    elif a[0] == 'tcup':
        if len(a) < 3 or a[1] not in ('new', 'set', 'off') or (a[1] == 'set' and len(a) < 4):
            sys.exit('python admin.py tcup new <file.json>   or   tcup set <id> <file.json>   or   tcup off <id>')
        if a[1] == 'off':
            call('POST', '/api/admin/tcup', {'id': a[2], 'cancel': True})
            print('called off: %s (its teams told)' % a[2])
            return
        path = a[2] if a[1] == 'new' else a[3]
        with open(path, encoding='utf-8-sig') as f:       # (Notepad may save it with a BOM)
            body = json.load(f)
        if isinstance(body.get('starts'), str):            # "2026-12-04T18:00:00Z" -> ms
            body['starts'] = int(datetime.datetime.fromisoformat(body['starts'].replace('Z', '+00:00')).timestamp() * 1000)
        if body.get('banner'):                             # a picture next to the file -> base64
            with open(os.path.join(os.path.dirname(path), body['banner']), 'rb') as f:
                body['banner'] = base64.b64encode(f.read()).decode()
        if a[1] == 'set':
            body['id'] = a[2]
        r = call('POST', '/api/admin/tcup', body)
        print('%s: %s/tcup/%s' % ('made' if a[1] == 'new' else 'changed', SERVER, r['id']))
    elif a[0] == 'league':
        if len(a) < 3 or a[1] not in ('new', 'set') or (a[1] == 'set' and len(a) < 4):
            sys.exit('python admin.py league new <file.json>   or   python admin.py league set <id> <file.json>')
        path = a[2] if a[1] == 'new' else a[3]
        with open(path, encoding='utf-8-sig') as f:       # (Notepad may save it with a BOM)
            body = json.load(f)
        rounds = body.get('rounds')
        if rounds and isinstance(rounds.get('starts'), str):   # "2026-11-16T00:00:00Z" -> ms
            rounds['starts'] = int(datetime.datetime.fromisoformat(rounds['starts'].replace('Z', '+00:00')).timestamp() * 1000)
        if body.get('banner'):                             # a picture next to the file -> base64
            with open(os.path.join(os.path.dirname(path), body['banner']), 'rb') as f:
                body['banner'] = base64.b64encode(f.read()).decode()
        if a[1] == 'set':
            body['id'] = a[2]
        r = call('POST', '/api/admin/league', body)
        print('%s: %s/l/%s  (%s)' % ('made' if a[1] == 'new' else 'changed', SERVER, r['id'],
                                     'public' if r['public'] else 'private: drivers ask to join, its admins accept them'))
        for e in r['rounds']:                              # (not the stages: they stay hidden, from you too)
            print('  %s  %s .. %s  %d stages' % (e['name'], utc(e['opens']), utc(e['closes']), e['stages']))
        if not r['rounds']:
            print('  no new rounds')
    elif a[0] == 'ahead':
        r = call('POST', '/api/admin/schedule-ahead', {'repick': '--repick' in a})
        for d in r['fixed']:
            print('  %s  %s' % (d['date'], '   '.join(d['picks']) or 'NO STAGES: add some to the pool'))
        days = r.get('days', 8)
        print('the coming %d days are fixed' % days if r['fixed'] else
              'the coming %d days were fixed already (admin.py state shows them)' % days)
    elif a[0] == 'comments':
        r = call('GET', '/api/admin/comments?days=%d' % (int(a[1]) if len(a) > 1 else 7))
        for c in reversed(r['comments']):                  # (oldest first, the newest last: above the prompt)
            where = c['on'] if not c.get('event') else '%s · %s (%s) SS%s' % (
                c['league'] if c.get('leagueKind') == 'league' else c.get('leagueKind'), c['event'], c['leagueId'],
                int(c['on'].split('/')[1]) + 1)
            print('#%-5d %s  %-20s %-34s %s%s%s' % (c['id'], utc(c['updated']), c['name'][:20], where[:34], c['text'],
                                                 '  [taken down]' if c['hidden'] else '', '  [banned]' if c['banned'] else ''))
        print('%d comment(s) in the last %d days' % (len(r['comments']), r['days']))
    elif a[0] == 'comment-hide':
        r = call('POST', '/api/admin/comments/%s' % a[1], {'action': 'show' if '--show' in a else 'hide'})
        print('comment #%s %s' % (r['id'], 'taken down' if r['hidden'] else 'shown again'))
    elif a[0] == 'tt-schedule':
        rest = [x for x in a[1:] if not x.startswith('--')]
        body = {'week': rest[0], 'slot': int(rest[1]), 'remove': '--remove' in a}
        if not body['remove']:
            body.update(track=rest[2], car=rest[3] if len(rest) > 3 else '*')
            if len(rest) > 4:
                body['weather'] = rest[4]
            if len(rest) > 5:
                body['time'] = rest[5]
        r = call('POST', '/api/admin/tt-schedule', body)
        print('time trial %s TT%d:' % (body['week'], body['slot']),
              'removed' if r.get('removed') else '%s, %s, %s %s' % (r['track'], r['car'], r['weather'], r['time']))
        if r.get('warning'):
            print('  warning:', r['warning'])
    elif a[0] == 'tt-private':
        opts, rest, i = {}, [], 1
        while i < len(a):
            if a[i] in ('--title', '--days', '--min-app', '--ends') and i + 1 < len(a):
                opts[a[i][2:]] = a[i + 1]
                i += 2
            else:
                rest.append(a[i])
                i += 1
        body = {k: v for k, v in (('title', opts.get('title')), ('minApp', opts.get('min-app'))) if v is not None}
        if len(rest) == 1 and '|' not in rest[0]:            # a page there is: changed
            body['page'] = rest[0]
            if 'ends' in opts:
                body['endsAt'] = int(datetime.datetime.fromisoformat(opts['ends']).replace(
                    tzinfo=datetime.timezone.utc).timestamp() * 1000)
        else:
            stages = []
            for s in rest:
                p = s.split('|')
                stages.append(dict(zip(('track', 'car', 'weather', 'time'), p)))
            body.update(stages=stages, days=float(opts.get('days', 7)))
        r = call('POST', '/api/admin/tt-private', body)
        print('private time trial: %s%s  (%s)' % (SERVER, r['page'], r.get('title') or 'no title'))
        print('  open %s to %s UTC, apps %s' % (
            datetime.datetime.fromtimestamp(r['startsAt'] / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M'),
            datetime.datetime.fromtimestamp(r['endsAt'] / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M'),
            ('from ' + r['minApp']) if r.get('minApp') else 'every version'))
        for s in r['stages']:
            print('  TT%d  %s · %s · %s %s%s' % (s['slot'], s['track'], s['car'], s['weather'], s['time'],
                                               '  WARNING: ' + s['warning'] if s.get('warning') else ''))
    elif a[0] == 'tt-reject':
        call('POST', '/api/admin/tt/runs/%s/reject' % a[1], {'reason': a[2] if len(a) > 2 else 'rejected by admin'})
        print('rejected time trial run', a[1])
    elif a[0] == 'reinstate':
        body = {'penaltyMs': round(float(a[2]) * 1000)} if len(a) > 2 else {}      # (the game's own, when known)
        r = call('POST', '/api/admin/runs/%s/reinstate' % a[1], body)
        print('run #%s on the board: %s%s%s' % (r['id'], fmt(r['totalMs']), ', P%s' % r['rank'] if r.get('rank') else '',
                                                 ', +%d credits' % r['credits'] if r.get('credits') else ''))
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
    elif a[0] == 'organizer':                             # a Community organizer (README, Rallies), or no more
        r = call('POST', '/api/admin/organizer', {'steamId': a[1], 'on': '--off' not in a})
        print('%s: %s' % (r.get('name') or a[1], 'a Community organizer' if r.get('organizer') else 'no longer a Community organizer'))
    elif a[0] == 'league-banner':
        call('POST', '/api/admin/league-banner', {'league': a[1]})
        print('banner taken down:', a[1])
    elif a[0] == 'driver-reset':                          # a driver's own name / picture back to Steam's
        call('POST', '/api/admin/driver', {'steamId': a[1], 'name': '--picture' not in a, 'avatar': '--name' not in a})
        print('put back to Steam\'s:', a[1])
    elif a[0] == 'rally-delete':
        r = call('POST', '/api/admin/rally-delete', {'event': int(a[1])})
        print('rally %s taken down' % r.get('deleted'))
    elif a[0] == 'team-delete':
        call('POST', '/api/admin/team-delete', {'team': a[1]})
        print('team closed:', a[1])
    elif a[0] == 'liveries':                              # (their previews: the /admin page's Liveries tab)
        which = a[1] if len(a) > 1 else 'pending'
        for l in call('GET', '/api/admin/liveries?status=%s' % which)['liveries']:
            print('#%-4s %-9s %-26s %-24s by %s (sent by %s, %s)' % (l['id'], l['status'], l['title'], l['carName'], l['author'],
                                                                  (l.get('by') or {}).get('name') or (l.get('by') or {}).get('steamId'),
                                                                  utc(l['created'])))
            print('      %s%s' % (l['link'] or '(no link: shown only)', '   (the app installs it)' if l.get('direct') else ''))
            if l.get('flags'):
                print('      %d driver(s) say the link is not working' % l['flags'])
            if l['status'] != 'pending':
                print('      %d vote(s), %s stars, %d download(s)' % (l['votes'], l['stars'], l['clicks']))
    elif a[0] == 'livery':
        body, rest = {'action': a[2]}, a[3:]
        while rest:
            x = rest.pop(0)
            if x == '--link' and rest:
                body['link'] = rest.pop(0)
            else:
                body['note'] = x
        r = call('POST', '/api/admin/liveries/%s' % a[1], body)
        print('livery #%s: %s%s' % (r['id'], 'deleted' if r.get('deleted') else r['status'], ' (the sender is told)' if r.get('told') else ''))
    elif a[0] == 'livery-import':
        import_liveries(a[1], pending='--pending' in a[2:])
    elif a[0] == 'move-traces':
        while True:
            r = call('POST', '/api/admin/move-traces', {'limit': 20})
            print('%d trace(s) to %s, %d left' % (r['moved'], r.get('to', 'R2'), r['left']))
            if not r['left'] or not r['moved']:
                break
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
