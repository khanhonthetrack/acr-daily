"""League events in the app (server: src/leagues.js; website: /leagues).

An event is a Rally Weekend in the game: several stages over one or more days, service parks, the damage carried from
stage to stage. DRIVE sets the whole rally up in the game's save (rallyweekend.apply_event); the game keeps it between
stages and sessions (Rally Weekend > Resume). The app follows the driver through it: each stage is judged like a daily
(judge.py: on its stage and car, from the clock's start, a restart or leaving the stage = DNF), then sent with the game's
own result (stage time + the game's penalties) read from the save after the finish. The first start counts; retiring,
restarting, or a stage driven outside the event's rally (or without the app watching) ends the entry: DNF.

The game keeps one Rally Weekend at a time, and since 2026-10-09 the dailies are one-stage Rally Weekends too: a league
rally in progress is set aside (park) while a daily is set up, and put back (unpark) when DRIVE is pressed on its event
again. The parked rally waits in %APPDATA%\\ACR Daily\\league-rallies. So does a Rally Weekend of the player's own
(park_own), until they put it back from the app (put_back).
"""
import json
import os
import re
import time

from . import rallyweekend, saveslot, settings
from .names import norm

SPLITS = [0.25, 0.5, 0.75]
PARK_DIR = os.path.join(settings.DIR, 'league-rallies')
PENDING = os.path.join(settings.DIR, 'league-pending.json')


def calendar(ev):
    """The event's stages (server: /api/me/events) as the game's calendar takes them (rallyweekend.check_itinerary)."""
    return [{'stage': s['stageId'], 'weather': s['weatherGame'], 'start': s['startSeconds'], 'day': s['day'] - 1,
             'service': bool(s['service'])} for s in ev['stages']]


def car_of(ev, name):
    """The event's car, or the car of its class the driver picked (by name or game id) -> its dict, or None."""
    for c in ev.get('cars') or []:
        if name and (name in (c['name'], c['id']) or norm(name) == norm(c['name'])):
            return c
    return None


def stage_ch(ev, k, car):
    """Stage k (0 = SS1) of an event as the judge takes a daily (judge.py, names.same_track / same_car)."""
    st = ev['stages'][k]
    return {'id': 'league:%d:%d' % (ev['id'], k), 'track': st['track'], 'menuName': st['name'], 'stageId': st['stageId'],
            'car': car['name'], 'carId': car['id'], 'carAliases': car.get('aliases') or [], 'route': st.get('route'),
            'penaltyMs': 0, 'splits': SPLITS, 'mode': 'weekend', 'eventId': ev['id'], 'stageNo': k,
            'weatherGame': st['weatherGame'], 'startSeconds': st['startSeconds'], 'weatherLabel': st.get('weatherLabel'),
            'timeLabel': st.get('time')}


RULE_NAMES = {'respawn': 'manual respawn', 'damage': 'damage', 'intensity': 'damage intensity', 'wear': 'wear',
              'failures': 'mechanical failures', 'penalty': 'penalties'}


def changed_in_game(w, ev):
    """What of the event's set-up the game's save no longer holds: changed in the game's own menus before START RALLY
    (the game writes its save when a rally starts, and after each stage). w: rallyweekend.read_weekend(). -> [what],
    empty when nothing changed. Driving assists are the player's own and not part of an event."""
    at = {rallyweekend.RESPAWN: 'respawn', rallyweekend.DAMAGE: 'damage', rallyweekend.INTENSITY: 'intensity',
          rallyweekend.WEAR: 'wear', rallyweekend.FAILURES: 'failures', rallyweekend.PENALTY_AT: 'penalty'}
    out = [RULE_NAMES[at[o]] for o, v in rallyweekend._rules(ev.get('rules')).items() if w[at[o]] != v]
    cal, have = calendar(ev), w['stages']
    if len(have) != len(cal) or any(s['stage'].lower() != c['stage'].lower() or s['day'] != c['day'] for s, c in zip(have, cal)):
        out.append('stages')
    else:
        if any(s['weather'] != rallyweekend.WEATHERS.index(c['weather']) for s, c in zip(have, cal) if c['weather'] in rallyweekend.WEATHERS):
            out.append('weather')
        if any(abs(s['start'] - c['start']) > 60 for s, c in zip(have, cal)):
            out.append('start times')
        if any((s['zone'] == rallyweekend.SERVICE) != bool(c['service']) for s, c in zip(have, cal)):
            out.append('service parks')
    return out


def same_calendar(stages, ev):
    """A calendar from the save (rallyweekend stages) is this event's: the same stages, in order, on the same days."""
    return [(s['stage'].lower(), s['day']) for s in stages] == \
        [(str(s['stageId']).lower(), s['day'] - 1) for s in ev['stages']]


def rally_state(b, ev):
    """What the save holds for an event: ('none', None) no rally in progress; ('other', p) one that is not this
    event's; ('this', p) this event's, p['done'] of its stages finished. (rallyweekend.progress)"""
    p = rallyweekend.progress(b)
    if p is None:
        return 'none', None
    return ('this' if same_calendar(p['stages'], ev) else 'other'), p


def owner_of(b, events):
    """The league event whose rally is in progress in the save: an entry of the driver's still running, else an event
    not started yet whose rally the game began with no stage driven. -> the event, or None."""
    p = rallyweekend.progress(b)
    if p is None:
        return None
    mine = [ev for ev in events if same_calendar(p['stages'], ev)]
    for ev in mine:
        if (ev.get('entry') or {}).get('status') == 'running':
            return ev
    for ev in mine:
        if not ev.get('entry') and p['done'] == 0:
            return ev
    return None


def with_pending(events, items):
    """The events (server: /api/me/events) with the results still waiting to be sent (pending()) on top of their
    entries, so the app goes on from where the driver really is."""
    by_id = {ev['id']: ev for ev in events}
    for it in items:
        ev = by_id.get(it.get('eventId'))
        if not ev:
            continue
        e = ev.get('entry')
        if it['kind'] == 'start' and not e:
            ev['entry'] = {'status': 'running', 'done': 0, 'totalMs': 0, 'car': it.get('car'), 'reason': ''}
        elif e and e.get('status') == 'running' and it['kind'] == 'stage' and it.get('no') == e.get('done', 0):
            e['done'] = e.get('done', 0) + 1
            e['totalMs'] = (e.get('totalMs') or 0) + it['timeMs'] + it['penaltyMs']
            if e['done'] >= len(ev['stages']):
                e['status'] = 'finished'
        elif e and e.get('status') == 'running' and it['kind'] == 'dnf':
            e['status'], e['reason'] = 'dnf', it.get('reason') or 'retired'
    return events


# ---- the game's own result of a stage (its time + its penalties)
def _key(e):
    return (e['started'], e['stage'].lower(),
            tuple((r['car'].lower(), round(r['time'], 3), round(r['penalty'], 3)) for r in e['runs']))


def known(b):
    """The game's results in the save now: official() then finds only a new one. Told apart by their stamp, stage and
    times, not their stamp alone as a daily's (rallyweekend.known): a rally's later stages may carry the stamp of its
    set-up, and a stage may be driven days after it."""
    return {_key(e) for e in rallyweekend.results(b)}


def known_to_json(known):
    """known() as JSON can keep it (waiting.py) -> list."""
    return [[k[0], k[1], [list(r) for r in k[2]]] for k in sorted(known or (), key=repr)]


def known_from_json(items):
    return {(k[0], k[1], tuple(tuple(r) for r in k[2])) for k in items or ()}


def official(b, stage_id, car_id, before):
    """The game's result of the stage just driven: a new one (not in `before` = known() at its start) on stage_id with
    car_id -> {'time', 'penalty', 'total', 'splits', 'started'}, or None. The latest one if there are several."""
    for e in reversed(rallyweekend.results(b)):
        if _key(e) not in before and e['stage'].lower() == stage_id.lower() and len(e['runs']) == 1 and \
                e['runs'][0]['car'].lower() == car_id.lower():
            r = e['runs'][0]
            return {'time': r['time'], 'penalty': r['penalty'], 'total': round(r['time'] + r['penalty'], 3),
                    'splits': r['splits'], 'started': e['started']}
    return None


# ---- a league rally set aside while a daily is driven
def park_path(event_id):
    return os.path.join(PARK_DIR, 'event-%d.bin' % int(event_id))


def is_parked(event_id):
    return os.path.exists(park_path(event_id))


def park(b, event_id):
    """Set the event's rally aside: -> the save without it (to write); the rally waits in a file for unpark()."""
    out, value = rallyweekend.park(b)
    os.makedirs(PARK_DIR, exist_ok=True)
    tmp = park_path(event_id) + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(value)
    os.replace(tmp, park_path(event_id))
    return out


def unpark(b, event_id):
    """-> the save with the event's parked rally back in it (forget_parked() once that is written)."""
    with open(park_path(event_id), 'rb') as f:
        return rallyweekend.unpark(b, f.read())


def forget_parked(event_id):
    try:
        os.remove(park_path(event_id))
    except OSError:
        pass


# ---- the player's own Rally Weekend in progress (one no league event of theirs holds): set aside the same way for a
# daily or an event, kept until the player puts it back from the app (PUT BACK over the dailies), newest first
LOCATIONS = {'Montecarlo': 'Monte Carlo'}


def describe(p, preset):
    """rallyweekend.progress() of a rally and its calendar preset -> {'location', 'stages', 'done'}."""
    loc = re.match(r'^([A-Za-z]+?)Weekend', preset or '')
    loc = loc.group(1) if loc else 'Rally Weekend'
    return {'location': LOCATIONS.get(loc, loc), 'stages': len(p['stages']), 'done': p['done']}


def own_parked():
    """The player's own rallies set aside, newest first: [{'path', 'location', 'stages', 'done', 'at'}]."""
    try:
        names = sorted((n for n in os.listdir(PARK_DIR) if n.startswith('own-') and n.endswith('.bin')), reverse=True)
    except OSError:
        return []
    out = []
    for n in names:
        path = os.path.join(PARK_DIR, n)
        try:
            with open(path[:-4] + '.json', encoding='utf-8') as f:
                info = json.load(f)
        except (OSError, ValueError):
            info = {'location': 'Rally Weekend', 'stages': 0, 'done': 0, 'at': os.path.getmtime(path)}
        out.append(dict(info, path=path))
    return out


def park_own(b):
    """Set the player's own rally in progress aside: -> the save without it (to write); the rally waits in a file
    (own_parked) for unpark_own()."""
    p = rallyweekend.progress(b)
    if p is None:
        raise saveslot.SaveError('no rally in progress to set aside')
    info = dict(describe(p, rallyweekend.read_weekend(b)['preset']), at=time.time())
    out, value = rallyweekend.park(b)
    os.makedirs(PARK_DIR, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    path = os.path.join(PARK_DIR, 'own-%s.bin' % stamp)
    k = 1
    while os.path.exists(path):
        k += 1
        path = os.path.join(PARK_DIR, 'own-%s-%d.bin' % (stamp, k))
    with open(path[:-4] + '.json', 'w', encoding='utf-8') as f:
        json.dump(info, f)
    with open(path + '.tmp', 'wb') as f:
        f.write(value)
    os.replace(path + '.tmp', path)
    return out


def unpark_own(b, path):
    """-> the save with the player's own rally from `path` back in it (forget_own() once that is written)."""
    with open(path, 'rb') as f:
        return rallyweekend.unpark(b, f.read())


def forget_own(path):
    for p in (path, path[:-4] + '.json'):
        try:
            os.remove(p)
        except OSError:
            pass


def put_back(b, path, events=()):
    """The player's own rally from `path` back in the save b. The rally in progress there now, if any, is set aside
    first: a league event's as that event's, any other as the player's own. -> (the save, what was set aside: the
    event, 'own' or None)."""
    moved = None
    if rallyweekend.progress(b) is not None:
        ev = owner_of(b, events)
        b, moved = (park(b, ev['id']), ev) if ev else (park_own(b), 'own')
    return unpark_own(b, path), moved


# ---- DRIVE on an event: what to do with the game's save
class Gone(Exception):
    """The event's rally is no longer in the game (retired, finished elsewhere, replaced): the entry is a DNF."""


def plan(ev, b, events=()):
    """What DRIVE on an event does with the save b (the game closed). -> (action, details):
      ('setup', None)            not started: the event's rally set up from the start
      ('reset', None)            not started, but its rally in the game was driven or changed without ACR Daily: thrown
                                 away and set up from the start
      ('resume', done)           this event's rally is in the game, `done` stages driven: just start the game
      ('unpark', None)           this event's rally was set aside for a daily: put it back
      ('park-other', ev2)        first set aside the rally of another started event (ev2), then go on
      ('park-own', info)         first set aside the player's own rally in progress (describe()), then go on
    Raises Gone when this event's started rally is not in the game any more."""
    entry = ev.get('entry') or {}
    status, done = entry.get('status'), entry.get('done', 0)
    if status == 'dsq':
        raise saveslot.SaveError('The stewards disqualified you from this event: %s' % (entry.get('reason') or 'no reason given'))
    if status in ('finished', 'dnf'):
        raise saveslot.SaveError('You have %s this event.' % ('finished' if status == 'finished' else 'retired from'))
    state, p = rally_state(b, ev)
    if state == 'other':
        other = owner_of(b, [e for e in events if e['id'] != ev['id']])
        if other:
            return 'park-other', other
        return 'park-own', describe(p, rallyweekend.read_weekend(b)['preset'])
    if status == 'running':
        if is_parked(ev['id']):
            if state == 'this':                 # (both: the one in the game is the newer one)
                return 'resume', p['done']
            return 'unpark', None
        if state == 'this' and p['done'] == done:
            return 'resume', done
        if state == 'this':
            raise Gone('the rally in the game has %d stage%s done, not %d: a stage was driven without ACR Daily watching'
                       % (p['done'], '' if p['done'] == 1 else 's', done))
        raise Gone('the event\'s rally is no longer in the game (retired, or another rally replaced it)')
    # not started yet: its rally in the game is used as it is only if nothing was driven and nothing changed in the
    # game's menus; otherwise it is thrown away and set up again (nothing of it counted)
    if state == 'this':
        if p['done'] == 0 and not changed_in_game(rallyweekend.read_weekend(b), ev):
            return 'resume', 0
        return 'reset', None
    return 'setup', None


def apply_plan(ev, car, action, details, b):
    """-> the new save for plan()'s action (not written), or None when there is nothing to write ('resume').
    'park-other' and 'park-own' only park; call plan() again after them. Raises Gone when the rally put back is not
    where the entry is (stages driven without the app)."""
    if action == 'setup':
        return rallyweekend.apply_event(b, calendar(ev), car['id'], ev.get('rules'))
    if action == 'reset':                     # the event's rally in the game, unusable: thrown away, set up again
        return rallyweekend.apply_event(rallyweekend.park(b)[0], calendar(ev), car['id'], ev.get('rules'))
    if action == 'unpark':
        out = unpark(b, ev['id'])
        p = rallyweekend.progress(out)
        done = (ev.get('entry') or {}).get('done', 0)
        if not same_calendar(p['stages'], ev) or p['done'] != done:
            raise Gone('the rally set aside has %d stage%s done, not %d' % (p['done'], '' if p['done'] == 1 else 's', done))
        return out
    if action == 'park-other':
        return park(b, details['id'])
    if action == 'park-own':
        return park_own(b)
    return None


# ---- stage results waiting to be sent (offline, or the server busy): sent in order, oldest first
def pending():
    try:
        with open(PENDING, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save_pending(items):
    os.makedirs(settings.DIR, exist_ok=True)
    tmp = PENDING + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items[-50:], f)
    os.replace(tmp, PENDING)
