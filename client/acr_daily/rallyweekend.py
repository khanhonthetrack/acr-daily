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
     71  int32  number of opponents     1..
     90  u8     penalty                 1 light, 2 realistic
     91  u8     running order           0 random, 1 custom (start position below)
     92  int32  start position          1 = first on the road
    100  FString calendar preset        e.g. WalesWeekendShort (the location: Alsace / Greece / Montecarlo / Wales)
         int32 stages, int32 0
         per stage: FString stage id, weather block x 2 (as set, and the default the menu's RESET goes back to),
                    FString zone before the stage (ServiceParkDefault / NoZone), int32 0
         int32 1, 16 bytes

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
ZONES = (b'ServiceParkDefault', b'NoZone')
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
    n, zero = _i(b, o), _i(b, o + 4)
    if not 1 <= n <= 40 or zero != 0:
        raise SaveError('unexpected Rally Weekend calendar (%d stages)' % n)
    o += 8
    stages = []
    for _k in range(n):
        s = saveslot._fstring_at(b, o)
        if not s or not saveslot.STAGE_RE.match(s[0]):
            raise SaveError('unexpected stage in the Rally Weekend calendar at %d' % (o - d))
        o = s[1]
        st = {'stage': s[0].decode()}
        st.update(_block(b, o))
        _block(b, o + BLOCK)
        o += 2 * BLOCK
        z = saveslot._fstring_at(b, o)
        if not z or z[0] not in ZONES or _i(b, z[1]) != 0:
            raise SaveError('unexpected zone in the Rally Weekend calendar at %d' % (o - d))
        st['zone'] = z[0].decode()
        o = z[1] + 4
        stages.append(st)
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


def apply_weekend(b, stage_id, car_id, start_seconds, weather_game, rules=None):
    """-> new save bytes with a one-stage Rally Weekend on stage_id: the service park, then the stage; the player
    first on the road (one opponent, custom running order); rules: see RULES. The car is the game's current car,
    which the online single stage set-up holds (saveslot.apply_daily writes it, and the single stage too).
    Raises SaveError."""
    m = saveslot.STAGE_RE.match(stage_id.encode('ascii'))
    if not m:
        raise SaveError('unexpected stage id %r' % stage_id)
    preset = PRESETS[m.group(1).decode()]
    if weather_game not in WEATHERS:
        raise SaveError('unexpected weather %r' % weather_game)
    settings = _rules(rules)
    b = saveslot.apply_daily(b, stage_id, car_id, start_seconds, weather_game)
    w = read_weekend(b)
    if w['in_progress']:
        raise SaveError('A Rally Weekend is in progress in the game. Finish it or retire from it first.')
    d = w['data']
    head = bytearray(b[d:d + HEADER])
    blk = _put_block(head[WEATHER:WEATHER + BLOCK], weather_game, start_seconds)
    head[WEATHER:WEATHER + BLOCK] = blk
    for at, v in settings.items():
        head[at] = v
    struct.pack_into('<i', head, OPPONENTS, 1)
    head[ORDER] = 1
    struct.pack_into('<i', head, START_POS, 1)
    tail = bytearray(b[w['tail']:w['end']])
    struct.pack_into('<i', tail, 0, 1)
    body = (bytes(head[4:]) + saveslot._fstring(preset) + struct.pack('<ii', 1, 0)
            + saveslot._fstring(stage_id) + blk + blk + saveslot._fstring('ServiceParkDefault') + struct.pack('<i', 0)
            + bytes(tail))
    out = bytearray(b[:d]) + struct.pack('<i', len(body)) + body + b[w['end']:]
    so = saveslot._payload(b)
    struct.pack_into('<i', out, so, len(out) - so - 4)
    out = bytes(out)
    back = read_weekend(out)                       # check: it reads back with exactly the new values
    want = {'preset': preset, 'opponents': 1, 'order': 1, 'start_position': 1}
    st = back['stages'][0] if len(back['stages']) == 1 else {}
    if any(back[k] != v for k, v in want.items()) or any(out[d + at] != v for at, v in settings.items()) or \
            st.get('stage') != stage_id or \
            st.get('weather') != WEATHERS.index(weather_game) or st.get('start') != float(start_seconds) or \
            saveslot.read_setup(out)['car'][1].decode() != car_id:
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
