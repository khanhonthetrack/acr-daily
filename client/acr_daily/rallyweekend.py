"""A daily as a one-stage Rally Weekend in Assetto Corsa Rally's save, and the game's own result of it read back.

Why a Rally Weekend: after each Rally Weekend stage the game writes its official result into the save (stage time,
penalty and splits, in seconds); after a Single Rally Stage it keeps nothing.

The set-up (read from the game's menus, one change at a time, game v0.6.0.100866) is one binary component in the save's
"DefaultRally" settings: the FString RaceEventRaceSettingsRallyWeekendComponent, then int32 size and `size` bytes:

    offset (from the size field)
      9  u8     manual respawn          0 off, 1 on
     14  u8     car damage              0 off, 1 on
     22  u8     damage intensity        0 off, 1 light, 2 severe, 3 realistic (LEVELS)
     23  u8     wear intensity          the same
     24  u8     mechanical failures     the same
     25  42 B   weather block of the stage to be driven next (below)
     67  u8     Hardcore Mode           not used yet: see docs/hardcore-and-assists.md
     71  int32  number of opponents     1..
     90  u8     penalty                 1 light, 2 realistic
     91  u8     running order           0 random, 1 custom (start position below)
     92  int32  start position          1 = first on the road
    100  FString calendar preset        e.g. WalesWeekendShort (the location: Alsace / Greece / Montecarlo / Wales;
                                        Short / Medium / Long = the game's 1, 2 and 3 day calendars)
         int32 stages
         per stage: int32 day (0 = day 1), FString stage id, weather block x 2 (as set, and the default the menu's
                    RESET goes back to), FString zone before the stage (ServiceParkDefault / NoZone; each day starts
                    with a service park)
         int32 0, int32 edited (0 = a preset as loaded, 1 = changed in the menu), 16 bytes

    weather block (42 bytes)
      0  u8     starting weather        0 Clear, 1 Light clouds, ... (WEATHERS, the menu's order)
      1  float  the game's random roll (re-rolled by the game each time it starts)
     10  float  another one
     24  float  start time, seconds since midnight
     28  int32  seed
     32  float  starting road wetness   0..1 (the menu sets 0.2 for light rain, 0.25 for rain and storm, else 0)
     36  float  starting snow level     0..1 (the menu leaves it at 0, snow included)
     40  u8     time acceleration       0 fixed, 1 realistic (1x), ...
     41  u8     starting grip level     0 dirty .. 4 optimal

A rally in progress (the game writes it after each stage, so a rally can be resumed after a restart of the game) adds
a second context to the same "DefaultRally" entry, right after the component: FString
ERaceEventSerializableContext::RaceEventState, int32 0, int32 4, then four components (FString name, int32 size, data):
RaceEventRallyWeekendDataComponent (int32: the stages finished so far), ...ResultsComponent (every driver's times),
RaceEventSnapshotComponent (the player's car: setup, tyres, damage) and RaceEventParticipantsDataSerializable. The entry
starts with its number of contexts (1, or 2 with a rally in progress). The game removes the state when the rally ends
(the last stage finished, or retired from).

The game's results: a map from mode ("DefaultRally", "DefaultTimeAttack", ...) to entries appended as they come:
    FString stage, int32 count, count x {int32 index, FString car, int32 n, n x (int32 split, float time, float section),
    float penalty, 8 bytes}, int64 start time (UTC ticks of 100 ns since 0001-01-01).
The time is the stage clock at the finish; the official total is time + penalty.

As in saveslot.py: anything not exactly as expected = nothing is written; every write keeps a backup first. (The layout
has changed once: saves from before a game update on 2026-10-06 have a 38-byte weather block. Nothing in the save's
header tells the versions apart, so read_weekend() checks the whole structure instead.)
"""
import datetime
import math
import re
import struct

from . import saveslot
from .saveslot import SaveError

COMPONENT = saveslot._fstring('RaceEventRaceSettingsRallyWeekendComponent')
RALLY_KEY = saveslot._fstring('DefaultRally')
PRESET_RE = re.compile(rb'^(Alsace|Greece|Montecarlo|Wales)Weekend(Short|Medium|Long)$')
PRESETS = {'Alsace': 'AlsaceWeekendShort', 'Greece': 'GreeceWeekendShort', 'MonteCarlo': 'MontecarloWeekendShort',
           'Weles': 'WalesWeekendShort', 'Wales': 'WalesWeekendShort'}
LENGTHS = ['Short', 'Medium', 'Long']        # the game's presets for 1, 2 and 3 days (more days: Long)
ZONES = (b'ServiceParkDefault', b'NoZone')
SERVICE, NO_ZONE = 'ServiceParkDefault', 'NoZone'
MAX_DAYS, MAX_STAGES = 4, 16                 # what a league event may hold (the game's presets: 3 days, 9 stages)
STATE = saveslot._fstring('ERaceEventSerializableContext::RaceEventState')
DATA = saveslot._fstring('RaceEventRallyWeekendDataComponent')
WEATHERS = ['WT_CLEAR', 'WT_LIGHT_CLOUDS', 'WT_HEAVY_CLOUDS', 'WT_LIGHT_FOG', 'WT_HEAVY_FOG', 'WT_LIGHT_RAIN',
            'WT_HEAVY_RAIN', 'WT_STORM', 'WT_LIGHT_SNOW', 'WT_HEAVY_SNOW', 'WT_BLIZZARD']
WETNESS = {'WT_LIGHT_RAIN': 0.2, 'WT_HEAVY_RAIN': 0.25, 'WT_STORM': 0.25}   # the menu's default per weather (else 0)
PENALTY = {'light': 1, 'realistic': 2}
LEVELS = {'off': 0, 'light': 1, 'severe': 2, 'realistic': 3}
# The daily's rules (the server sends them with each daily as "weekend"; these are what it sends today)
RULES = {'penalty': 'light', 'respawn': True, 'damage': True, 'damageIntensity': 'light', 'wear': 'light',
         'failures': 'off'}

HEADER = 100
RESPAWN, DAMAGE, WEATHER, OPPONENTS, PENALTY_AT, ORDER, START_POS = 9, 14, 25, 71, 90, 91, 92
INTENSITY, WEAR, FAILURES = 22, 23, 24
BLOCK = 42
W_TYPE, W_START, W_WET, W_SNOW, W_ACCEL, W_GRIP = 0, 24, 32, 36, 40, 41
TAIL = 20
TICKS_1970 = 621355968000000000


def _f(b, o):
    return struct.unpack_from('<f', b, o)[0]


def _i(b, o):
    return struct.unpack_from('<i', b, o)[0]


def _block(b, o):
    """A weather block at o -> dict (raises SaveError if a value is out of its range)."""
    w = {'weather': b[o + W_TYPE], 'start': _f(b, o + W_START), 'wetness': _f(b, o + W_WET),
         'snow': _f(b, o + W_SNOW), 'accel': b[o + W_ACCEL], 'grip': b[o + W_GRIP]}
    if not (w['weather'] < len(WEATHERS) + 1 and 0 <= w['start'] < 86400 and 0 <= w['wetness'] <= 1
            and 0 <= w['snow'] <= 1 and w['accel'] <= 5 and w['grip'] <= 4):
        raise SaveError('unexpected Rally Weekend weather values %r' % w)
    return w


def read_weekend(b):
    """The Rally Weekend set-up in the save -> dict with the settings, 'preset', 'stages' and the offsets used to
    rewrite it ('data': offset of the size field, 'end': end of the component)."""
    saveslot._payload(b)
    i = b.find(COMPONENT)
    if i < 0 or b.find(COMPONENT, i + 1) >= 0:
        raise SaveError('no Rally Weekend set-up in the save (open Rally Weekend in the game once)')
    d = i + len(COMPONENT)
    size = _i(b, d)
    end = d + 4 + size
    if not HEADER + 20 < size + 4 <= len(b) - d or saveslot._fstring_at(b, end) is None:
        raise SaveError('the Rally Weekend set-up does not look as expected (size %d)' % size)
    w = {'data': d, 'end': end, 'respawn': b[d + RESPAWN], 'damage': b[d + DAMAGE], 'intensity': b[d + INTENSITY],
         'wear': b[d + WEAR], 'failures': b[d + FAILURES], 'next': _block(b, d + WEATHER),
         'opponents': _i(b, d + OPPONENTS), 'penalty': b[d + PENALTY_AT], 'order': b[d + ORDER],
         'start_position': _i(b, d + START_POS)}
    if not (w['respawn'] in (0, 1) and w['damage'] in (0, 1) and max(w['intensity'], w['wear'], w['failures']) <= 3
            and 1 <= w['opponents'] <= 100 and w['penalty'] in (1, 2) and w['order'] <= 3
            and 1 <= w['start_position'] <= 101):
        raise SaveError('unexpected Rally Weekend settings %r' % {k: v for k, v in w.items() if k != 'next'})
    p = saveslot._fstring_at(b, d + HEADER)
    if not p or not PRESET_RE.match(p[0]):
        raise SaveError('the Rally Weekend set-up does not look as expected (no calendar at %d)' % HEADER)
    w['preset'] = p[0].decode()
    o = p[1]
    n = _i(b, o)
    if not 1 <= n <= 40:
        raise SaveError('unexpected Rally Weekend calendar (%d stages)' % n)
    o += 4
    stages = []
    for _k in range(n):
        day = _i(b, o)
        last = stages[-1]['day'] if stages else 0
        if day not in (last, last + 1):              # day 1 first, then the same day or the next
            raise SaveError('unexpected day in the Rally Weekend calendar at %d' % (o - d))
        o += 4
        s = saveslot._fstring_at(b, o)
        if not s or not saveslot.STAGE_RE.match(s[0]):
            raise SaveError('unexpected stage in the Rally Weekend calendar at %d' % (o - d))
        o = s[1]
        st = {'stage': s[0].decode(), 'day': day}
        st.update(_block(b, o))
        _block(b, o + BLOCK)
        o += 2 * BLOCK
        z = saveslot._fstring_at(b, o)
        if not z or z[0] not in ZONES:
            raise SaveError('unexpected zone in the Rally Weekend calendar at %d' % (o - d))
        st['zone'] = z[0].decode()
        o = z[1]
        stages.append(st)
    if _i(b, o) != 0:
        raise SaveError('the Rally Weekend calendar does not end as expected (%d)' % (o - d))
    o += 4
    if o + TAIL != end:
        raise SaveError('the Rally Weekend calendar does not end where expected (%d, %d)' % (o + TAIL - d, end - d))
    w['stages'] = stages
    w['tail'] = o
    w['in_progress'] = b'ERaceEventSerializableContext::RaceEventState' in b[end:end + 60]
    return w


def _put_block(blk, weather_game, start_seconds):
    blk = bytearray(blk)
    blk[W_TYPE] = WEATHERS.index(weather_game)
    struct.pack_into('<f', blk, W_START, float(start_seconds))
    struct.pack_into('<f', blk, W_WET, WETNESS.get(weather_game, 0.0))
    struct.pack_into('<f', blk, W_SNOW, 0.0)             # 0 whatever the weather, as the menu sets it
    blk[W_ACCEL] = 0          # time stands still: the same light for everyone, as the single stage dailies
    blk[W_GRIP] = 4           # optimal
    return bytes(blk)


def _rules(rules):
    """The daily's rules (RULES, with what the server sent over them) -> the bytes to write. Raises SaveError."""
    r = dict(RULES, **(rules or {}))
    try:
        return {RESPAWN: 1 if r['respawn'] else 0, DAMAGE: 1 if r['damage'] else 0,
                INTENSITY: LEVELS[r['damageIntensity']], WEAR: LEVELS[r['wear']], FAILURES: LEVELS[r['failures']],
                PENALTY_AT: PENALTY[r['penalty']]}
    except (KeyError, TypeError):
        raise SaveError('unexpected Rally Weekend rules %r' % (rules,)) from None


def check_itinerary(stages):
    """A league event's stages in driving order: [{'stage': game id, 'weather': 'WT_...', 'start': seconds since
    midnight, 'day': 0.., 'service': a service park before it}]. -> the calendar preset's name. Raises SaveError
    unless it is a calendar the game's menu could have made: one location, days in order starting with day 1, each day
    opening with a service park, at most MAX_DAYS days and MAX_STAGES stages."""
    if not stages or len(stages) > MAX_STAGES:
        raise SaveError('a Rally Weekend holds 1 to %d stages' % MAX_STAGES)
    rally = None
    for k, st in enumerate(stages):
        m = saveslot.STAGE_RE.match(str(st.get('stage', '')).encode('ascii', 'replace'))
        if not m or m.group(1).decode() not in PRESETS:
            raise SaveError('unexpected stage id %r' % st.get('stage'))
        r = PRESETS[m.group(1).decode()]
        if rally and r != rally:
            raise SaveError('a Rally Weekend is held in one location: %s is not in %s' % (st['stage'], rally))
        rally = r
        if st.get('weather') not in WEATHERS:
            raise SaveError('unexpected weather %r' % st.get('weather'))
        if not isinstance(st.get('start'), (int, float)) or not 0 <= st['start'] < 86400:
            raise SaveError('unexpected start time %r' % st.get('start'))
        day, prev = st.get('day'), stages[k - 1]['day'] if k else -1
        if not isinstance(day, int) or day not in (prev, prev + 1) or (k == 0 and day != 0):
            raise SaveError('the days of a Rally Weekend come in order, from day 1')
        if day != prev and not st.get('service'):
            raise SaveError('each day of a Rally Weekend starts with a service park')
    days = stages[-1]['day'] + 1
    if days > MAX_DAYS:
        raise SaveError('a Rally Weekend lasts at most %d days' % MAX_DAYS)
    return rally.replace('Short', LENGTHS[min(days, len(LENGTHS)) - 1])


def apply_event(b, stages, car_id, rules=None):
    """-> new save bytes with a Rally Weekend of `stages` (see check_itinerary) driven in car_id; the player first on
    the road (one opponent, custom running order), time standing still; rules: see RULES. The car is the game's
    current selection (saveslot.apply_daily writes it; a new player's save has one too, with no Single Rally Stage
    weather options, which a Rally Weekend doesn't need). Raises SaveError."""
    preset = check_itinerary(stages)
    settings = _rules(rules)
    first = stages[0]
    b = saveslot.apply_daily(b, first['stage'], car_id, first['start'], first['weather'], options=False)
    w = read_weekend(b)
    if w['in_progress']:
        raise SaveError('A Rally Weekend is in progress in the game. Finish it or retire from it first.')
    d = w['data']
    head = bytearray(b[d:d + HEADER])
    template = head[WEATHER:WEATHER + BLOCK]
    head[WEATHER:WEATHER + BLOCK] = _put_block(template, first['weather'], first['start'])
    for at, v in settings.items():
        head[at] = v
    struct.pack_into('<i', head, OPPONENTS, 1)
    head[ORDER] = 1
    struct.pack_into('<i', head, START_POS, 1)
    tail = bytearray(b[w['tail']:w['end']])
    struct.pack_into('<i', tail, 0, 1)            # "edited": a calendar of its own, not one of the game's presets
    calendar = b''
    for st in stages:
        blk = _put_block(template, st['weather'], st['start'])
        calendar += (struct.pack('<i', st['day']) + saveslot._fstring(st['stage']) + blk + blk
                     + saveslot._fstring(SERVICE if st.get('service') else NO_ZONE))
    body = (bytes(head[4:]) + saveslot._fstring(preset) + struct.pack('<i', len(stages)) + calendar
            + struct.pack('<i', 0) + bytes(tail))
    out = bytearray(b[:d]) + struct.pack('<i', len(body)) + body + b[w['end']:]
    so = saveslot._payload(b)
    struct.pack_into('<i', out, so, len(out) - so - 4)
    out = bytes(out)
    back = read_weekend(out)                       # check: it reads back with exactly the new values
    want = {'preset': preset, 'opponents': 1, 'order': 1, 'start_position': 1}
    got = [(s['stage'], s['day'], s['weather'], s['start'], s['zone']) for s in back['stages']]
    if any(back[k] != v for k, v in want.items()) or any(out[d + at] != v for at, v in settings.items()) or \
            got != [(s['stage'], s['day'], WEATHERS.index(s['weather']), float(s['start']),
                     SERVICE if s.get('service') else NO_ZONE) for s in stages] or \
            saveslot.read_setup(out)['car'][1].decode() != car_id:
        raise SaveError('verification failed')
    return out


def apply_weekend(b, stage_id, car_id, start_seconds, weather_game, rules=None):
    """-> new save bytes with a one-stage Rally Weekend on stage_id (the daily): the service park, then the stage.
    See apply_event. Raises SaveError."""
    return apply_event(b, [{'stage': stage_id, 'weather': weather_game, 'start': start_seconds, 'day': 0,
                            'service': True}], car_id, rules)


def write_event(stages, car_id, rules=None):
    """Set the game's save to a league event (stages: see check_itinerary). -> message."""
    b = saveslot.read_for_daily({'stageId': stages[0]['stage'], 'carId': car_id, 'weatherGame': stages[0]['weather'],
                                 'startSeconds': stages[0]['start']})
    saveslot.replace(apply_event(b, stages, car_id, rules))
    return 'Set up as a Rally Weekend: %d stages · %s' % (len(stages), car_id)


# ---- a rally in progress: how far it is, and setting it aside (a league rally parked while the daily is driven)
def _entry(b, w):
    """(start, end) of the save's "DefaultRally" settings entry, its number of contexts first (saveslot.modes: it may
    be the only entry, in a new player's save)."""
    rally = [m for m in saveslot.modes(b) if m[0] == 'DefaultRally']
    if len(rally) != 1 or not rally[0][2] < w['data'] < rally[0][3]:
        raise SaveError('the save does not look as expected (no DefaultRally entry)')
    _name, _at, start, end = rally[0]
    if _i(b, start) != (2 if w['in_progress'] else 1) or (not w['in_progress'] and end != w['end']):
        raise SaveError('the save does not look as expected (the DefaultRally entry)')
    return start, end


def progress(b):
    """The rally in progress in the save: {'stages': its calendar, 'done': stages finished so far}, or None."""
    w = read_weekend(b)
    if not w['in_progress']:
        return None
    i = b.find(DATA, w['end'], w['end'] + 200)
    if i < 0:
        raise SaveError('the rally in progress does not look as expected')
    size, done = struct.unpack_from('<ii', b, i + len(DATA))
    if size != 4 or not 0 <= done <= len(w['stages']):
        raise SaveError('the rally in progress does not look as expected (%d of %d)' % (done, len(w['stages'])))
    return {'stages': w['stages'], 'done': done}


def _put_entry(b, start, end, value):
    out = bytearray(b[:start]) + value + b[end:]
    so = saveslot._payload(b)
    struct.pack_into('<i', out, so, len(out) - so - 4)
    return bytes(out)


def park(b):
    """Set the rally in progress aside: -> (the save without it, the entry to put back with unpark()). The game then
    has no rally to resume and a new one can be set up (a daily); the parked one keeps its stages, times and damage."""
    w = read_weekend(b)
    if not w['in_progress']:
        raise SaveError('no rally in progress to set aside')
    start, end = _entry(b, w)
    value = b[start:end]
    out = _put_entry(b, start, end, struct.pack('<i', 1) + b[start + 4:w['end']])
    back = read_weekend(out)
    if back['in_progress'] or [s['stage'] for s in back['stages']] != [s['stage'] for s in w['stages']]:
        raise SaveError('verification failed')
    return out, value


def unpark(b, value):
    """Put a rally set aside by park() back (replacing the Rally Weekend set-up and any rally in its place)."""
    w = read_weekend(b)
    start, end = _entry(b, w)
    if _i(value, 0) != 2 or STATE not in value:
        raise SaveError('not a rally set aside')
    out = _put_entry(b, start, end, value)
    if progress(out) is None:
        raise SaveError('verification failed')
    return out


def write_daily(ch):
    """Set the game's save to the daily `ch` as a one-stage Rally Weekend (its rules: ch['weekend']). -> message."""
    b = saveslot.read_for_daily(ch)
    saveslot.replace(apply_weekend(b, ch['stageId'], ch['carId'], ch['startSeconds'], ch['weatherGame'],
                                   ch.get('weekend')))
    return 'Set up as a Rally Weekend: %s · %s · %s' % (ch['stageId'], ch['carId'],
                                                        ch.get('weatherLabel') or ch['weatherGame'])


# ---- the game's results
def _entries(b, o):
    """Parse the entries of one results list starting at its count. -> (entries, end) or None if it isn't one."""
    n = _i(b, o)
    if not 0 <= n <= 10000:
        return None
    o += 4
    out = []
    for _k in range(n):
        s = saveslot._fstring_at(b, o)
        if not s or not saveslot.STAGE_RE.match(s[0]):
            return None
        o = s[1]
        count = _i(b, o)
        if not 1 <= count <= 40:
            return None
        o += 4
        runs = []
        for _r in range(count):
            idx = _i(b, o)
            c = saveslot._fstring_at(b, o + 4)
            if not c or not re.match(rb'^[A-Za-z0-9]+$', c[0]):
                return None
            o = c[1]
            nsplit = _i(b, o)
            if not 1 <= nsplit <= 20 or o + 4 + nsplit * 12 + 12 > len(b):
                return None
            splits = [(_i(b, o + 4 + 12 * k), _f(b, o + 8 + 12 * k), _f(b, o + 12 + 12 * k)) for k in range(nsplit)]
            o += 4 + nsplit * 12
            pen = _f(b, o)
            if not all(math.isfinite(x) and 0 <= x < 100000 for _s, t, sec in splits for x in (t, sec)) or \
                    not (math.isfinite(pen) and 0 <= pen < 100000):
                return None
            runs.append({'index': idx, 'car': c[0].decode(), 'time': splits[-1][1],
                         'splits': [t for _s, t, _sec in splits[1:]], 'penalty': pen})
            o += 12
        ticks = struct.unpack_from('<q', b, o)[0]
        started = (ticks - TICKS_1970) / 1e7
        if not 1.6e9 < started < 4.2e9:             # 2020 .. 2103
            return None
        out.append({'stage': s[0].decode(), 'runs': runs, 'started': started})
        o += 8
    return out, o


def results(b, mode='DefaultRally'):
    """The game's own results for a mode, oldest first: [{'stage', 'started' (unix time, UTC), 'runs': [{'car',
    'time', 'penalty', 'splits'}]}]. Empty when the save holds none."""
    o = b.find(saveslot._fstring(mode))
    while o >= 0:
        try:
            got = _entries(b, o + len(saveslot._fstring(mode)))
        except (struct.error, IndexError):         # cut short (e.g. read while the game was writing it)
            got = None
        if got is not None:
            return got[0]
        o = b.find(saveslot._fstring(mode), o + 1)
    return []


def known(b):
    """The results already in the save (their start times): official() then finds only a new one."""
    return {e['started'] for e in results(b)}


def official(b, stage_id, car_id, before=(), since=None):
    """The game's result of a one-stage Rally Weekend on stage_id with car_id that was not in the save before
    (`before` = known() then) and, with `since` (unix time), started at most an hour before it:
    {'time', 'penalty', 'total', 'splits', 'started'}, or None. The latest one if there are several.
    (The game stamps a result with the time the stage was set up, which comes before its clock starts. Ids are
    compared ignoring case: the game's names do, and one save can spell the same car HyundaiI20NRally2 and
    Hyundaii20NRally2.)"""
    for e in reversed(results(b)):
        if e['started'] not in before and (since is None or e['started'] >= since - 3600) and \
                e['stage'].lower() == stage_id.lower() and len(e['runs']) == 1 and \
                e['runs'][0]['car'].lower() == car_id.lower():
            r = e['runs'][0]
            return {'time': r['time'], 'penalty': r['penalty'], 'total': round(r['time'] + r['penalty'], 3),
                    'splits': r['splits'], 'started': e['started']}
    return None


def started_text(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
