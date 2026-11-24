"""DRIVE inside the game (0.2): with the game running in its menus and the mod in, DRIVE no longer closes and restarts
the game. The set-up (a daily, a time trial, an event's leg) goes to the mod, which makes it in the running game through
the game's own calls and sends the game on to the Service Park (mod/ACRDailyGhosts/Scripts/drive.lua; probed in the game
20 Nov 2026, docs/ingame-app.md). The player presses START STAGE there; everything after is as before (the judge, the
game's own result in its save).

What the game gets is what the save's set-up holds (rallyweekend.apply_event): the calendar's preset, its stages with
their day, service park, weather (as set, not drawn at random), start time standing still, wetness and grip; the rules
(rallyweekend.rule_values); one opponent, a custom running order, the player first on the road; the car.

When it can't be done in the game (the mod not answering, a rally of the player's own in progress, not in the main
menu, anything the game refused) the caller is told why, and offers the old way: close the game, set it up in the save,
start it again.
"""
import time

from . import rallyweekend, saveslot
from .i18n import _

ANSWER_S = 30.0        # the mod's last word on a DRIVE at most this long after the one before


def setup_of(stages, car_id, rules=None, tail=False):
    """stages as rallyweekend.check_itinerary takes them ([{stage, weather, start, day, service}]) -> the set-up the mod
    makes (drive.lua). Raises saveslot.SaveError (the same checks as the save's set-up). tail: a leg from a later stage
    on (leagues.recover: its first stage may have no service park)."""
    preset = rallyweekend.check_itinerary(stages, tail=tail)
    if not car_id or not str(car_id).replace('_', '').isalnum():
        raise saveslot.SaveError('unexpected car id %r' % (car_id,))
    out = []
    for st in stages:
        out.append({'track': st['stage'], 'day': int(st['day']), 'service': bool(st.get('service')),
                    'weather': rallyweekend.WEATHERS.index(st['weather']), 'start': float(st['start']),
                    'wet': rallyweekend.WETNESS.get(st['weather'], 0.0)})
    return {'preset': preset, 'car': str(car_id), 'stages': out, 'rules': rallyweekend.rule_values(rules),
            'opponents': 1, 'order_type': 1, 'order': 1}


def daily_stages(ch):
    """A daily's (or a time trial's) one stage, as the save's set-up has it (rallyweekend.apply_weekend)."""
    return [{'stage': ch['stageId'], 'weather': ch['weatherGame'], 'start': ch['startSeconds'], 'day': 0,
             'service': True}]


def ready(app, allow_rally=False):
    """Can DRIVE be done in the running game now? The game running, the mod in it (its pulse) and the pages' link up.
    (Whether the game is in its main menu, the mod checks itself: it says so if not.) allow_rally: a rally in progress
    in the save doesn't stop it (a recovery of that same event's rally: leagues.recover)."""
    ig = getattr(app, 'ingame_app', None)
    if ig is None or not saveslot.game_running():
        return False
    try:
        if not app._pulse().alive():
            return False
    except Exception:
        return False
    if packages_changed_since_start():
        return False                    # (the old way: the game started again, with the packages as they are now)
    return allow_rally or not rally_in_progress()


def packages_changed_since_start(game=None, started=None):
    """Has a package in the game's ~mods changed (a stage set installed, the one stage list for all the sets made again)
    since the running game started? The game reads them as it starts: DRIVE in that game would set up a stage it has no
    rows for. It CRASHED the game on the tyre allocation (the user, 24 Nov 2026: London installed from the game's own
    COMMUNITY page, the game started again 30 s before the stage list was made, then DRIVE on TT3 London). True: DRIVE
    goes the old way (the game started again)."""
    import os
    global _game
    started = saveslot.game_started_at() if started is None else started
    if not started:
        return False
    try:
        if game is None:
            if _game is None:
                from .modinstall import game_dir
                _game = game_dir() or ''
            game = _game
        mods = os.path.join(game, 'acr', 'Content', 'Paks', '~mods') if game else None
        if not mods or not os.path.isdir(mods):
            return False
        for name in os.listdir(mods):
            if name.lower().endswith(('.pak', '.ucas', '.utoc')):
                p = os.path.join(mods, name)
                if max(os.path.getmtime(p), os.path.getctime(p)) > started + 2:
                    return True
    except OSError:
        return False
    return False


_game = None                            # (the game's folder, looked up once: packages_changed_since_start)


def held_by_rally(app):
    """Is the only thing keeping a set-up from the running game a Rally Weekend in progress in the save (the game and
    the mod there)? -> its progress ({'done', 'stages'}) when so, else None. (WATCH asks to go on over it: it only
    watches, the user 22 Nov 2026 met "go to the main menu first" there with a ranked rally left half-driven.)"""
    ig = getattr(app, 'ingame_app', None)
    if ig is None or not saveslot.game_running():
        return None
    try:
        if not app._pulse().alive() or not rally_in_progress():
            return None
        p = rallyweekend.progress(saveslot.read_save())
    except Exception:
        return None
    return p or {'done': 0, 'stages': []}


def can_resume(app):
    """Can a CONTINUE be done in the running game (its own RESUME, from its main menu: drive.lua)? The game running
    with the mod in it, in its menus."""
    if getattr(app, 'ingame_app', None) is None or not saveslot.game_running():
        return False
    try:
        return bool(app._pulse().in_menus())
    except Exception:
        return False


def rally_in_progress():
    """A Rally Weekend of the player's in progress in the game's save with something to keep: some of its stages
    finished, some still to drive (the game writes its state after each stage; the game's own IsRallyInProgress says
    yes to any Rally Weekend set up in its menu). It is the save's to set aside first (the old way: the app parks it
    with the game closed). One with no stage finished, or all of them (a daily's left behind: the user, 21 Nov 2026,
    whose next DRIVE then restarted the game), holds nothing: the set-up made in the game takes its place.
    Unreadable: taken as one to keep."""
    try:
        b = saveslot.read_save()
        if not rallyweekend.read_weekend(b)['in_progress']:
            return False
        p = rallyweekend.progress(b)
        # (every stage done: a one-stage daily's rally left "in progress" when its results screen was left by MAIN
        # MENU, 21 Nov 2026: nothing left in it to drive either)
        return p is None or 0 < p['done'] < len(p['stages'])
    except (OSError, saveslot.SaveError, KeyError):
        return True


DAMAGE_FILE = 'ingame-damage.txt'    # your car's damage now (main.lua write_damage)


def read_damage(path=None):
    """Your car's damage as the game has it now (the mod's ingame-damage.txt) -> {part: life points}, only the parts
    below 100 (an intact car: {}), or None (no car of yours, no file, an older mod, half written). Read at the finish
    line and sent with the stage: after a crash past the line the next stage starts with the car as it finished there
    (leagues.recover, drive.lua)."""
    import os
    from . import settings
    try:
        with open(path or os.path.join(settings.DIR, DAMAGE_FILE), encoding='ascii', errors='replace') as f:
            words = f.read(4000).split()
    except OSError:
        return None
    if len(words) < 4 or words[0] != 'ACRDMG' or words[-2] != 'end' or words[-1] != words[1]:
        return None
    body = words[2:-2]
    if body == ['none']:
        return None
    out = {}
    for w in body:
        k, _sep, v = w.partition('=')
        try:
            lp = float(v)
        except ValueError:
            return None
        if k and 0 <= lp < 100:
            out[k] = round(lp, 1)
    return out


SETUP_FILE = 'ingame-setup.txt'      # the stage being driven as the game runs it (main.lua read_setup)


def live_setup(path=None):
    """The Rally Weekend stage being driven, as the game runs it (the mod's ingame-setup.txt) -> {'track', 'weather',
    'start', 'speed', 'wet', 'grip', 'random', 'dynamic', 'index'}, or None (no file, an older mod, not a Rally
    Weekend's stage, half written)."""
    import os
    from . import settings
    try:
        with open(path or os.path.join(settings.DIR, SETUP_FILE), encoding='ascii', errors='replace') as f:
            text = f.read()
    except OSError:
        return None
    lines = text.split('\n')
    head = lines[0].split() if lines else []
    if len(head) < 3 or head[0] != 'ACRSETUP' or len(lines) < 2 or lines[1].strip() != 'end %s' % head[1]:
        return None
    if head[2] == 'none' or len(head) < 11:
        return None
    try:
        n = [int(x) for x in head[3:11]]
    except ValueError:
        return None
    # ours: did ACR DAILY take the game to this stage (appui.lua)? None: can't be told (an older mod, no appui)
    ours = {'1': True, '0': False}.get(head[11]) if len(head) > 11 else None
    return {'track': head[2], 'weather': n[0], 'start': n[1], 'speed': n[2], 'wet': n[3] / 100.0, 'grip': n[4],
            'random': bool(n[5]), 'dynamic': bool(n[6]), 'index': n[7], 'ours': ours}


def setup_changed(stage, live):
    """A stage of the set-up DRIVE made in the running game (setup_of's stages[k]) against the stage driven as the game
    runs it (live_setup) -> [what changed] in the words the save's check uses (leagues.changed_in_game), empty when
    nothing did. (The rules are checked live on the start line already: app.settings_changed.)"""
    out = []
    if live['track'].lower() != stage['track'].lower():
        out.append('stages')
    if live['weather'] != stage['weather']:
        out.append('weather')
    if abs(live['start'] - stage['start']) > 60:
        out.append('start times')
    if live['grip'] != rallyweekend.GRIP or (live['weather'] == stage['weather'] and abs(live['wet'] - stage['wet']) > 0.011):
        out.append('track conditions')
    if live['speed'] != 0:
        out.append('time speed')
    if live['random'] or live['dynamic']:
        out.append('random weather')
    return out


WHY = {'rally in progress': _('a Rally Weekend of yours is in progress in the game'),
       "not in the game's main menu": _('the game is not in its main menu'),
       'busy': _('the game is still setting up the last one'),
       'no rally in progress': _('the game has no Rally Weekend in progress'),
       'no answer': _('the game did not answer'),
       'no drive.lua': _('the game mod is too old'),
       'bad set-up': _('the set-up was refused')}


def why_words(why):
    """The mod's reason -> words for the player."""
    for k, v in WHY.items():
        if why.startswith(k):
            return v
    return why


class Drives:
    """The DRIVEs sent to the mod and its answers (InGameApp keeps one): send() -> its number; answer(n, rest) with the
    mod's event; check() fails one with no answer in ANSWER_S."""

    def __init__(self):
        self.waiting = {}            # n (the command's number) -> {'ok': fn, 'fail': fn(why), 'at': t, 'step': str}

    said = ''                        # the last DRIVE's tyres / livery that didn't take ('tyres auto <why>'), else ''

    def send(self, n, on_ok, on_fail, now=None):
        self.said = ''
        self.waiting[n] = {'ok': on_ok, 'fail': on_fail, 'at': time.monotonic() if now is None else now, 'step': ''}
        return n

    def answer(self, rest, now=None):
        """The mod's "drive" event: '<n> ok' / '<n> error <why>' / '<n> step <what>'."""
        parts = (rest or '').split(' ', 2)
        if len(parts) < 2 or not parts[0].isdigit():
            return
        if parts[1] == 'damage':                   # (after its "ok": the car's damage put back at the Service Park)
            self.damage_said = parts[2] if len(parts) > 2 else ''
            try:
                from . import waiting
                waiting.note('in-game DRIVE %s: the car\'s damage put back: %s' % (parts[0], self.damage_said))
            except Exception:
                pass
            return
        w = self.waiting.get(int(parts[0]))
        if w is None:
            return
        w['at'] = time.monotonic() if now is None else now
        if parts[1] == 'step':
            w['step'] = parts[2] if len(parts) > 2 else ''
            if w['step'].startswith('tyres auto'):
                self.said = w['step']              # (the tyres picked didn't fit: the caller says so)
        elif parts[1] == 'ok':
            del self.waiting[int(parts[0])]
            w['ok']()
        elif parts[1] == 'error':
            del self.waiting[int(parts[0])]
            w['fail'](parts[2] if len(parts) > 2 else '')

    def check(self, now=None):
        now = time.monotonic() if now is None else now
        for n, w in list(self.waiting.items()):
            if now - w['at'] > ANSWER_S:
                del self.waiting[n]
                w['fail']('no answer')

    def busy(self):
        return bool(self.waiting)
