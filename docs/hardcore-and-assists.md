# Hardcore Mode and driving assists: shelved (2026-10-09)

League rules for the game's **Hardcore Mode** and for **driving assists** were worked out and then put aside to keep
the leagues simple. Nothing of it is in the app or on the server. This file has what was learned in the game and
the code, ready to bring back.

## What the game does (v0.6.0.100866, checked in the game on 2026-10-09)

- **When it writes its save:** at CONFIRM AND START RALLY (after the tyre page), after each stage, and when it exits.
  Not when leaving the Race Settings or Driving Assists pages, and not at the START RALLY button itself.
  The quickest way to make it write: change a setting, START RALLY › J › CONFIRM AND START RALLY, then back to the
  main menu from the service park (Esc › QUIT).
- **Hardcore Mode** (Rally Weekend › Race Settings, under Manual Respawn): "all influenced options are locked to the
  most realistic and challenging value". Turned on, the menu locks Car Damage on, Damage intensity, Wear and Mechanical
  failures at Realistic and Penalty at Realistic, greys out Manual Respawn (kept as it was), and **writes those
  values** into the save. Turned off, they stay at Realistic.
  - In the Rally Weekend component (`rallyweekend.py`, offsets from the size field): **67 = Hardcore Mode** (0/1).
    Turning it on also set **4** and **10** to 1, and they stayed 1 after turning it off (meaning unknown).
- **Driving Assists** (Rally Weekend › Driving Assists): Transmission, Clutch Control, Anti-Lock Braking System,
  Traction Control, Starting Handbrake Assist, Engine Starter, Start Sequence Type (Complete / Quick), Unwanted
  Downshift protection. Automatic transmission locks the clutch at automatic. The game's own help says traction
  control "can still be re-enabled during the race ... through direct inputs or in-game controls".
  - They are the **player's own settings, one set for every mode**, not part of a rally: in the save's game data,
    after the culture FString (e.g. `en-US`), 24 bytes and two FStrings (`English`, `Normal`), a fixed 331-byte
    block runs up to the next FString (`Medium`). From the end of the second FString:

    | offset | type | setting | values |
    |---|---|---|---|
    | 229 | u8 | transmission | 0 manual, 1 automatic |
    | 230 | int32 | ABS | 0 off, 1 on |
    | 234 | int32 | traction control | 0 off, 1 on |
    | 238 | int32 | starting handbrake assist | 0 off, 1 on |
    | 242 | int32 | clutch | 0 manual, 1 automatic |
    | 246 | u8 | engine starter | 0 manual, 1 automatic |
    | 247 | u8 | start sequence | 0 quick, 1 complete |
    | 248 | u8 | unwanted downshift protection | 0 off, 1 on |

    The same layout was found in all 38 saves on the developer's PC (2026-10-05 onwards, across the 2026-10-06 game
    update; all en-US / English, so other languages are unchecked).
- **Telemetry doesn't show the aids:** with traction control on and full throttle from a standstill, the ACC-layout
  fields (physics `tc`@204, `abs`@252, `autoShifterOn`@264; graphics `TC`@1268, `ABS`@1280; the static `aid*`
  fields) all stayed 0.

## The design that was ready

- Event rules (server `leagues.js`): `hardcore: false` and `assists: 'any' | 'off'` added to `DEFAULT_RULES`;
  `checkEvent` with `hardcore` forces `damage: true`, the three levels and the penalty to `'realistic'` (what the game
  locks); an `ASSISTS` list in the catalog; `fullRules()` in `eventOut` so older events get the defaults.
  "off" = no ABS, traction control or starting handbrake assist (the aids that make a driver faster); gears, clutch,
  starter, start sequence and the downshift protection stay the driver's choice.
- Website: a Hardcore Mode select at the top of the builder's Settings (when on, the locked selects are hidden), a
  "Driving aids" select (each driver's choice / off); chips "Hardcore Mode" and "No driving aids" / "Driving aids: your
  choice" on the event page, and a line for each in its rules.
- App, Hardcore: `rallyweekend.HARDCORE = 67`, read in `read_weekend` (check 0/1), written by `_rules` (with the
  locked values when on), `RULES['hardcore'] = False`; `leagues.changed_in_game` then reports it like the rest. Writing
  67 = 0 for the dailies too would stop a player's own Hardcore Mode carrying into a daily (today the app leaves the
  byte as the player had it).
- App, assists (they are global, so the app asks before touching them):
  - DRIVE on an event with `assists: 'off'`: if the save shows a forbidden aid on, ask "switch them off for you? They
    stay off afterwards, for every mode"; yes = `assists.switch_off` in the same save write.
  - SS1 start (no entry yet): forbidden aid on in the save = the run doesn't count (as settings changed in the menus).
  - After every stage (the save written with the result): forbidden aid on = DNF.
  - Not at the start of later stages: the save can be stale there (changed in the pause menu without a write).

## Code

`client/acr_daily/assists.py` (checked against the five mapping saves: reads every setting as the game showed it;
`switch_off` changes only ABS, TC and the starting handbrake assist):

```python
"""The driving assists in Assetto Corsa Rally's save, for league events run without them (rules "assists": "off").

The game keeps them with the player's own settings, one set for every mode (Rally Weekend › Driving Assists shows
them; so does the pause menu's Settings), and writes them into the save when a rally starts (CONFIRM AND START
RALLY), after each stage and when it exits. In the save's game data: the culture (an FString, e.g. en-US), 24 bytes,
two FStrings (e.g. English, Normal), then a block of BLOCK bytes up to the next FString (e.g. Medium). From the end of
the second FString (found one change at a time in the game's menu, v0.6.0.100866; the same in every save since
2026-10-05):

    229 u8     transmission                    0 manual, 1 automatic (automatic locks the clutch at automatic)
    230 int32  anti-lock brakes (ABS)          0 off, 1 on
    234 int32  traction control                0 off, 1 on
    238 int32  starting handbrake assist       0 off, 1 on
    242 int32  clutch                          0 manual, 1 automatic
    246 u8     engine starter                  0 manual, 1 automatic
    247 u8     start sequence                  0 quick, 1 complete
    248 u8     unwanted downshift protection   0 off, 1 on

An event without driving aids forbids OFF_RULE: the ones that make a driver faster. Gears, clutch, starter, start
sequence and the downshift protection stay each driver's choice. The live telemetry shows none of them, and the game
says traction control can be switched on in the car during a stage: the save, read after each stage, is what counts.
As in saveslot.py: anything not exactly as expected = SaveError, nothing written.
"""
import struct

from . import saveslot
from .saveslot import SaveError

BLOCK = 331
AT = {'transmission': (229, 'B'), 'abs': (230, 'i'), 'tc': (234, 'i'), 'handbrake': (238, 'i'), 'clutch': (242, 'i'),
      'starter': (246, 'B'), 'start': (247, 'B'), 'downshift': (248, 'B')}
OFF_RULE = ('abs', 'tc', 'handbrake')
NAMES = {'abs': 'ABS', 'tc': 'traction control', 'handbrake': 'starting handbrake assist'}


def _block(b):
    """-> offset of the block (the end of the second FString after the culture). Raises SaveError."""
    so = saveslot._payload(b)
    c = saveslot._fstring_at(b, so + 12)
    if not c or not 2 <= len(c[0]) <= 12:
        raise SaveError('the driving assists are not where expected in the save (no culture)')
    for o in range(c[1], c[1] + 64):
        first = saveslot._fstring_at(b, o)
        if first and first[0].isalpha():
            second = saveslot._fstring_at(b, first[1])
            if second and second[0].isalpha() and saveslot._fstring_at(b, second[1] + BLOCK):
                return second[1]
            break
    raise SaveError('the driving assists are not where expected in the save')


def read(b):
    """The assists in the save -> {'transmission', 'abs', ... (AT)}: 0 or 1 each. Raises SaveError."""
    e = _block(b)
    out = {k: struct.unpack_from('<' + f, b, e + o)[0] for k, (o, f) in AT.items()}
    if any(v not in (0, 1) for v in out.values()):
        raise SaveError('unexpected driving assist values %r' % out)
    return out


def breaking(b, rule):
    """The aids on in the save that an event's rule ('any' or 'off') forbids -> their names (NAMES), [] if none."""
    if rule != 'off':
        return []
    a = read(b)
    return [NAMES[k] for k in OFF_RULE if a[k]]


def switch_off(b, rule):
    """-> the save with the aids an event's rule forbids switched off (the rest as they were). Raises SaveError."""
    if rule != 'off':
        return b
    e = _block(b)
    read(b)
    out = bytearray(b)
    for k in OFF_RULE:
        o, f = AT[k]
        struct.pack_into('<' + f, out, e + o, 0)
    out = bytes(out)
    if breaking(out, rule) or {k: v for k, v in read(out).items() if k not in OFF_RULE} != \
            {k: v for k, v in read(b).items() if k not in OFF_RULE}:
        raise SaveError('verification failed')
    return out
```

`client/acr_daily/rallyweekend.py`:

```python
RULES = {..., 'failures': 'off', 'hardcore': False}
INTENSITY, WEAR, FAILURES, HARDCORE = 22, 23, 24, 67

# read_weekend(): 'hardcore': b[d + HARDCORE], and w['hardcore'] in (0, 1) in the check

def _rules(rules):
    r = dict(RULES, **(rules or {}))
    if r['hardcore']:                 # as the game's menu locks and writes them in Hardcore Mode
        r.update(damage=True, damageIntensity='realistic', wear='realistic', failures='realistic', penalty='realistic')
    try:
        return {RESPAWN: ..., DAMAGE: ..., INTENSITY: ..., WEAR: ..., FAILURES: ..., PENALTY_AT: ...,
                HARDCORE: 1 if r['hardcore'] else 0}
    ...
```

`client/acr_daily/leagues.py`: `RULE_NAMES['hardcore'] = 'Hardcore Mode'` and
`rallyweekend.HARDCORE: 'hardcore'` in `changed_in_game`'s offset map.

`server/src/leagues.js`:

```js
export const ASSISTS = ['any', 'off'];            // the driving aids: the driver's choice, or none (ABS, TC, start assist)
export const DEFAULT_RULES = { penalty: 'light', respawn: true, damage: true, damageIntensity: 'light', wear: 'light',
  failures: 'off', hardcore: false, assists: 'any' };
export const fullRules = (r) => ({ ...DEFAULT_RULES, ...(r || {}) });
// catalog(): rules: { penalty: PENALTIES, levels: LEVELS, assists: ASSISTS, defaults: DEFAULT_RULES }
// checkEvent():
    hardcore: !!r.hardcore,
    assists: ASSISTS.includes(r.assists) ? r.assists : DEFAULT_RULES.assists,
  ...
  if (rules.hardcore) {   // what the game itself locks them at (and writes into its save) in Hardcore Mode
    Object.assign(rules, { damage: true, damageIntensity: 'realistic', wear: 'realistic', failures: 'realistic', penalty: 'realistic' });
  }
```

`server/src/leaguepages.js`, the builder's `rules(b)`:

```js
  function rules(b){add(b,el('h3',null,'Settings'));var g=el('div','twocol');S.rules=Object.assign({},CAT.rules.defaults,S.rules);
    g.appendChild(sel('Hardcore Mode (the game\\'s own)','hardcore',['false','true'],['Off','On: damage, wear, failures and penalties locked at Realistic']));
    if(S.rules.hardcore)Object.assign(S.rules,{damage:true,damageIntensity:'realistic',wear:'realistic',failures:'realistic',penalty:'realistic'});
    else{g.appendChild(sel('Damage','damage',['true','false'],['On (repair it in the service parks)','Off']));
      if(S.rules.damage)g.appendChild(sel('Damage intensity','damageIntensity',['light','severe','realistic']));
      g.appendChild(sel('Wear','wear',CAT.rules.levels));g.appendChild(sel('Mechanical failures','failures',CAT.rules.levels))}
    g.appendChild(sel('Manual respawn','respawn',['true','false'],['On','Off (stuck = retire)']));
    if(!S.rules.hardcore)g.appendChild(sel('Penalties (cuts, respawns, jump starts...)','penalty',CAT.rules.penalty));
    g.appendChild(sel('Driving aids','assists',CAT.rules.assists||['any','off'],['Each driver\\'s choice','Off: no ABS, traction control or starting handbrake assist']));
    b.appendChild(g)}
```

Test (server `leagues.test.mjs`):

```js
  const hc = checkEvent(ev({ rules: { hardcore: 1, damage: false, wear: 'off', penalty: 'light', respawn: false, assists: 'off' } }), CAT, NOW).value;
  assert.deepEqual(hc.rules, { penalty: 'realistic', respawn: false, damage: true, damageIntensity: 'realistic', wear: 'realistic',
    failures: 'realistic', hardcore: true, assists: 'off' });
```
