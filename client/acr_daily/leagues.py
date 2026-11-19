"""League events in the app (server: src/leagues.js; website: /leagues).

An event is a Rally Weekend in the game: several stages over one or more days, service parks, the damage carried from
stage to stage. DRIVE sets the whole rally up in the game's save (rallyweekend.apply_event); the game keeps it between
stages and sessions (Rally Weekend > Resume). The app follows the driver through it: each stage is judged like a daily
(judge.py: on its stage and car, from the clock's start, a restart or leaving the stage = DNF), then sent with the game's
own result (stage time + the game's penalties) read from the save after the finish. The first start counts; retiring,
restarting, or a stage driven outside the event's rally (or without the app watching) ends the entry: DNF.

A Rally Weekend in the game holds at most 9 stages over 3 days (the most its own menus make: its Long preset); from
the 10th stage of a longer one the game crashes between a stage's end and the service park (RALLY MONTECARLO 2026, 14
stages, Nov 2026). So an event longer than that is driven in legs (legs()): whole days, at most LEG_STAGES stages and
LEG_DAYS days each, each its own Rally Weekend in the game opening with a service park. DRIVE / CONTINUE sets up the leg
the entry is on; the game ends a leg's rally after its last stage, and CONTINUE then sets up the next one. The game's
progress in a leg is the event's from that leg's first stage (rally_state).

The game keeps one Rally Weekend at a time, and since 2026-10-09 the dailies are one-stage Rally Weekends too: a league
rally in progress is set aside (park) while a daily is set up, and put back (unpark) when DRIVE is pressed on its event
again. The parked rally waits in %APPDATA%\\ACR Daily\\league-rallies. So does a Rally Weekend of the player's own
(park_own), until they put it back from the app (put_back).
"""
import json
import os
import re
import struct
import time

from . import rallyweekend, saveslot, settings
from .i18n import N_, _, said, said_n
from .names import norm

SPLITS = [0.25, 0.5, 0.75]
LEG_STAGES, LEG_DAYS = 9, 3      # a leg: the most one Rally Weekend in the game takes (its Long preset)
PARK_DIR = os.path.join(settings.DIR, 'league-rallies')
PENDING = os.path.join(settings.DIR, 'league-pending.json')


def legs(ev):
    """The event's stages in the legs the game is given one at a time: [(first, end)] (stage indexes, end excluded), in
    order. Whole days, packed while a leg has at most LEG_STAGES stages and LEG_DAYS days; a day longer than LEG_STAGES
    (the server allows 8 a day: never) cut in parts. One leg for an event the game takes at once."""
    days = []
    for k, st in enumerate(ev['stages']):
        if days and days[-1][2] == st['day']:
            days[-1][1] = k + 1
        else:
            days.append([k, k + 1, st['day']])
    out = []
    for a, b, _day in days:
        for c in range(a, b, LEG_STAGES):          # (a day too long for one leg: in parts)
            d = min(b, c + LEG_STAGES)
            if out and c == a and d - out[-1][0] <= LEG_STAGES and out[-1][2] < LEG_DAYS:
                out[-1][1], out[-1][2] = d, out[-1][2] + 1
            else:
                out.append([c, d, 1])
    return [(a, b) for a, b, _n in out]


def leg_of(ev, k):
    """The leg (an index of legs()) stage k is in; past the last stage, the last leg."""
    ls = legs(ev)
    return next((i for i, (a, b) in enumerate(ls) if a <= k < b), len(ls) - 1)


def leg_starts(ev, k):
    """Stage k is a leg's first (each one's: a Rally Weekend of its own, from its service park)."""
    return any(a == k for a, _b in legs(ev))


def calendar(ev, leg=0):
    """A leg of the event (server: /api/me/events) as the game's calendar takes it (rallyweekend.check_itinerary): its
    days from day 1, a service park before its first stage."""
    a, b = legs(ev)[leg]
    first = ev['stages'][a]['day']
    return [{'stage': s['stageId'], 'weather': s['weatherGame'], 'start': s['startSeconds'], 'day': s['day'] - first,
             'service': bool(s['service']) or k == a} for k, s in enumerate(ev['stages'][a:b], start=a)]


def leg_in(stages, ev):
    """The event's leg a calendar from the save (rallyweekend stages) is: the same stages, in order, on the same days.
    -> its index, or None."""
    have = [(s['stage'].lower(), s['day']) for s in stages]
    for i in range(len(legs(ev))):
        if have == [(str(c['stage']).lower(), c['day']) for c in calendar(ev, i)]:
            return i
    return None


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


# (in English: what changed goes to the server with the DNF; the app shows them in its language: N_ marks them)
RULE_NAMES = {'respawn': N_('manual respawn'), 'damage': N_('damage'), 'intensity': N_('damage intensity'),
              'wear': N_('wear'), 'failures': N_('mechanical failures'), 'penalty': N_('penalties'),
              'hardcore': N_('Hardcore Mode'), 'tyres': N_('tyre damage')}
# the driving aids, as the game mod reads them (ingamehud.AIDS / DASH)
AID_NAMES = {'abs': N_('ABS'), 'tc': N_('traction control'), 'handbrake': N_('starting handbrake assist'),
             'gearbox': N_('gearbox'), 'clutch': N_('clutch')}
OFF_AIDS = ('abs', 'tc', 'handbrake')       # what an event without driving aids forbids (rules assists 'off')
_SAVE_AT = {rallyweekend.RESPAWN: 'respawn', rallyweekend.DAMAGE: 'damage', rallyweekend.INTENSITY: 'intensity',
            rallyweekend.WEAR: 'wear', rallyweekend.FAILURES: 'failures', rallyweekend.PENALTY_AT: 'penalty',
            rallyweekend.HARDCORE: 'hardcore'}


def changed_in_game(w, ev):
    """What of the event's set-up the game's save no longer holds: changed in the game's own menus before START RALLY
    (the game writes its save when a rally starts, and after each stage). w: rallyweekend.read_weekend(). -> [what],
    empty when nothing changed. Driving assists are the player's own and not part of an event."""
    at = _SAVE_AT
    out = [RULE_NAMES[at[o]] for o, v in rallyweekend._rules(ev.get('rules')).items() if w.get(at[o], v) != v]
    leg = leg_in(w['stages'], ev)                  # (a long event: the leg the save holds)
    cal, have = calendar(ev, leg or 0), w['stages']
    if len(have) != len(cal) or any(s['stage'].lower() != c['stage'].lower() or s['day'] != c['day'] for s, c in zip(have, cal)):
        out.append(N_('stages'))
    elif not w.get('old'):                         # (a set-up from before the game's update of 2026-10-06: no weather read)
        if any(s['weather'] != rallyweekend.WEATHERS.index(c['weather']) for s, c in zip(have, cal) if c['weather'] in rallyweekend.WEATHERS):
            out.append(N_('weather'))
        if any(abs(s['start'] - c['start']) > 60 for s, c in zip(have, cal)):
            out.append(N_('start times'))
        if any((s['zone'] == rallyweekend.SERVICE) != bool(c['service']) for s, c in zip(have, cal)):
            out.append(N_('service parks'))
        # what the app writes for every stage besides (rallyweekend._put_block), as ACRK checks "track conditions": the
        # game leaves them as written through a run (a daily's save after its stage, report #175: all as written)
        # (the wetness the app writes for the weather, judged where the weather is the event's: a weather changed is
        # 'weather' already, whatever wetness came with it)
        def wet_changed(s, c):
            if c['weather'] not in rallyweekend.WEATHERS or s.get('weather') != rallyweekend.WEATHERS.index(c['weather']):
                return False
            return abs(s.get('wetness', 0) - rallyweekend.WETNESS.get(c['weather'], 0.0)) > 0.01
        if any(s.get('grip', rallyweekend.GRIP) != rallyweekend.GRIP or s.get('snow', 0) > 0.001 or wet_changed(s, c)
               for s, c in zip(have, cal)):
            out.append(N_('track conditions'))
        if any(s.get('accel', 0) != 0 for s in have):
            out.append(N_('time speed'))
        if any(s.get('random') for s in have):
            out.append(N_('random weather'))
    return out


def live_changed(s, rules):
    """changed_in_game for the race as the game runs it now, before the run (the game mod reads it: ingamehud.SETTINGS,
    app.game_settings), against the event's rules (rallyweekend.RULES with the event's over them). -> [what], empty when
    nothing changed. (The save says the same only once the stage is over.)"""
    return [RULE_NAMES[_SAVE_AT[o]] for o, v in rallyweekend._rules(rules).items() if s.get(_SAVE_AT[o], v) != v]


def aids_broken(aids, dash, rules):
    """The driving aids on that an event without them forbids (rules 'assists': 'off'): the player's, as the race
    applies them (aids: ingamehud.AIDS), or as the car has them now (dash: ABS / TC switched in the car) -> [what]
    (AID_NAMES), empty when none or the event leaves them to each driver."""
    if dict(rallyweekend.RULES, **(rules or {})).get('assists') != 'off':
        return []
    aids, dash = (x if isinstance(x, dict) else {} for x in (aids, dash))
    on = {k for k in OFF_AIDS if aids.get(k) or dash.get(k)}
    return [AID_NAMES[k] for k in OFF_AIDS if k in on]


def changed_during(before, now):
    """What changed in the game since a run's start (its race's settings, the player's driving aids, the car's): two
    {'S': settings, 'A': aids, 'V': dash} (each a dict or None: not read) -> [what] (RULE_NAMES / AID_NAMES), only
    for what was read both times."""
    out = []
    for group, names in (('S', RULE_NAMES), ('A', AID_NAMES), ('V', AID_NAMES)):
        a, b = (before or {}).get(group), (now or {}).get(group)
        if not (isinstance(a, dict) and isinstance(b, dict)):
            continue
        for k in a:
            if k in b and a[k] != b[k] and names.get(k) and names[k] not in out:
                out.append(names[k])
    return out


def daily_changed(w, item):
    """changed_in_game for a daily or a time trial stage: a one-stage Rally Weekend, as DRIVE wrote it (its stage,
    weather, start time and rules: the waiting run's item, app._await_official). -> [what], empty when nothing changed or
    the item doesn't say (one from before 0.1.5.6)."""
    if not item.get('stageId') or item.get('weather') is None or item.get('start') is None:
        return []
    ev = {'rules': item.get('rules'), 'stages': [{'stageId': item['stageId'], 'weatherGame': item['weather'],
                                                 'startSeconds': item['start'], 'day': 1, 'service': True}]}
    return changed_in_game(w, ev)


def same_calendar(stages, ev, leg=None):
    """A calendar from the save (rallyweekend stages) is this event's: one of its legs (leg: that one)."""
    i = leg_in(stages, ev)
    return i is not None and (leg is None or i == leg)


def rally_state(b, ev):
    """What the save holds for an event: ('none', None) no rally in progress; ('other', p) one that is not this
    event's; ('this', p) one of its legs, p['done'] of the event's stages finished (the leg's first stage on, as far as
    the game is in it), p['leg'] that leg. (rallyweekend.progress)"""
    p = rallyweekend.progress(b)
    if p is None:
        return 'none', None
    leg = leg_in(p['stages'], ev)
    if leg is None:
        return 'other', p
    return 'this', dict(p, done=legs(ev)[leg][0] + p['done'], leg=leg, legDone=p['done'])


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
        if not ev.get('entry') and p['done'] == 0 and same_calendar(p['stages'], ev, 0):
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


def own_of_event(b, ev, done):
    """Among the player's own rallies set aside (own_parked), newest first: one that is this event's rally with `done`
    stages driven. The app sets an event's rally aside as the player's own when the entry is a DNF (owner_of only
    knows running entries); if an admin reinstates the entry, that is where its rally is. Each is tried on b in memory.
    -> its path, or None."""
    for x in own_parked():
        try:
            with open(x['path'], 'rb') as f:
                state, p = rally_state(rallyweekend.unpark(b, f.read()), ev)
        except (OSError, saveslot.SaveError, struct.error, IndexError):
            continue
        if state == 'this' and p['done'] == done:
            return x['path']
    return None


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
      ('setup', None)            not started: the event's rally set up from the start (a long event: its first leg;
                                 started: the leg the entry is on)
      ('next-leg', leg)          a long event's earlier leg in the game, its stages all counted: the next leg set up
      ('reset', None)            not started, but its rally in the game was driven or changed without ACR Daily: thrown
                                 away and set up from the start
      ('resume', done)           this event's rally is in the game, `done` stages driven: just start the game. Fewer
                                 than the entry has (the game took its rally back): those are driven again, for nothing
      ('setup', None)            also for a started entry whose rally the game dropped: driven again from SS1
      ('missed', done)           more stages done in the game (`done`) than the entry has, in an event with the
                                 retirement rule: those count as retired (sent as missed), then resume
      ('unpark', None)           this event's rally was set aside for a daily: put it back
      ('unpark-own', path)       this event's rally was set aside as the player's own (while the entry was a DNF, since
                                 reinstated): put it back as the event's
      ('park-other', ev2)        first set aside the rally of another started event (ev2), then go on
      ('park-own', info)         first set aside the player's own rally in progress (describe()), then go on
    Raises Gone when the game's rally has more of this event's stages done than the entry (driven without the app),
    in an event without the retirement rule."""
    entry = ev.get('entry') or {}
    status, done = entry.get('status'), entry.get('done', 0)
    if status == 'dsq':
        raise saveslot.SaveError(_('The stewards disqualified you from this event: %s') % (entry.get('reason') or _('no reason given')))
    if status in ('finished', 'dnf'):
        raise saveslot.SaveError(_('You have finished this event.') if status == 'finished' else
                                 _('You have retired from this event.'))
    state, p = rally_state(b, ev)
    if state == 'other':
        other = owner_of(b, [e for e in events if e['id'] != ev['id']])
        if other:
            return 'park-other', other
        return 'park-own', describe(p, rallyweekend.read_weekend(b)['preset'])
    if status == 'running':
        need = leg_of(ev, done)
        if state == 'this' and p['leg'] < need:
            # the game holds a leg before the entry's (its stages all counted: a long event's rally, legs()): the leg
            # the entry is on set up instead
            return 'next-leg', need
        if is_parked(ev['id']):
            if state == 'this':                 # (both: the one in the game is the newer one)
                return 'resume', p['done']
            return 'unpark', None
        if state == 'this' and p['done'] == done:
            return 'resume', done
        if state == 'this' and p['done'] < done:
            # the game took its rally back (quit away from a service park, a crash...): the stages counted stand, and
            # driven again they count for nothing; the next one counts as usual (from 0.1.5, as ACRK's Real Rally)
            return 'resume', p['done']
        if state == 'this' and (ev.get('rules') or {}).get('retire'):
            # stages driven without the app watching: with the event's retirement rule they count as retired (the
            # slowest time + its minutes) and the entry goes on (from 0.1.5; leagueui sends them as missed)
            return 'missed', p['done']
        if state == 'this':
            raise Gone(said_n('the rally in the game has %d stage done, not %d: a stage was driven without ACR Daily '
                              'watching', 'the rally in the game has %d stages done, not %d: a stage was driven without '
                              'ACR Daily watching', p['done'], p['done'], done))
        own = own_of_event(b, ev, done)          # set aside as the player's own while the entry was a DNF (reinstated)
        if own:
            return 'unpark-own', own
        # the game dropped its rally: set up afresh, the stages counted are driven again (and count for nothing)
        return 'setup', None
    # not started yet: its rally in the game is used as it is only if nothing was driven and nothing changed in the
    # game's menus; otherwise it is thrown away and set up again (nothing of it counted)
    if state == 'this':
        if p['leg'] == 0 and p['done'] == 0 and not changed_in_game(rallyweekend.read_weekend(b), ev):
            return 'resume', 0
        return 'reset', None
    return 'setup', None


def apply_plan(ev, car, action, details, b):
    """-> the new save for plan()'s action (not written), or None when there is nothing to write ('resume').
    'park-other' and 'park-own' only park; call plan() again after them. Raises Gone when the rally put back is not
    where the entry is (stages driven without the app)."""
    done = (ev.get('entry') or {}).get('done', 0)
    if action == 'setup':                     # (the leg the entry is on: the first one for an entry not started)
        return rallyweekend.apply_event(b, calendar(ev, leg_of(ev, done)), car['id'], ev.get('rules'))
    if action == 'reset':                     # the event's rally in the game, unusable: thrown away, set up again
        return rallyweekend.apply_event(rallyweekend.park(b)[0], calendar(ev), car['id'], ev.get('rules'))
    if action == 'next-leg':                  # the leg before, done with: thrown away, the next one set up
        return rallyweekend.apply_event(rallyweekend.park(b)[0], calendar(ev, details), car['id'], ev.get('rules'))
    if action == 'unpark':
        out = unpark(b, ev['id'])
        state, p = rally_state(out, ev)
        if state == 'this' and p['leg'] < leg_of(ev, done):            # (an earlier leg, done with: the next one)
            return rallyweekend.apply_event(rallyweekend.park(out)[0], calendar(ev, leg_of(ev, done)), car['id'],
                                            ev.get('rules'))
        if state != 'this' or p['done'] > done:     # (fewer: driven again, as plan()'s 'resume')
            n = p['done'] if p else 0
            raise Gone(said_n('the rally set aside has %d stage done, not %d', 'the rally set aside has %d stages done, not %d',
                              n, n, done))
        return out
    if action == 'unpark-own':                # the event's rally, set aside as the player's own: back as the event's
        out = unpark_own(b, details)
        state, p = rally_state(out, ev)
        if state != 'this' or p['done'] != done:
            raise Gone(said('the rally set aside is not where the entry is'))
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
