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


def setup_of(stages, car_id, rules=None):
    """stages as rallyweekend.check_itinerary takes them ([{stage, weather, start, day, service}]) -> the set-up the mod
    makes (drive.lua). Raises saveslot.SaveError (the same checks as the save's set-up)."""
    preset = rallyweekend.check_itinerary(stages)
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


def ready(app):
    """Can DRIVE be done in the running game now? The game running, the mod in it (its pulse) and the pages' link up.
    (Whether the game is in its main menu, the mod checks itself: it says so if not.)"""
    ig = getattr(app, 'ingame_app', None)
    if ig is None or not saveslot.game_running():
        return False
    try:
        if not app._pulse().alive():
            return False
    except Exception:
        return False
    return not rally_in_progress()


def rally_in_progress():
    """A Rally Weekend of the player's in progress in the game's save (the game writes its state after each stage; the
    game's own IsRallyInProgress says yes to any Rally Weekend set up in its menu). It is the save's to set aside first
    (the old way: the app parks it with the game closed). Unreadable: taken as one in progress."""
    try:
        return bool(rallyweekend.read_weekend(saveslot.read_save())['in_progress'])
    except (OSError, saveslot.SaveError, KeyError):
        return True


WHY = {'rally in progress': _('a Rally Weekend of yours is in progress in the game'),
       "not in the game's main menu": _('the game is not in its main menu'),
       'busy': _('the game is still setting up the last one'),
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

    def send(self, n, on_ok, on_fail, now=None):
        self.waiting[n] = {'ok': on_ok, 'fail': on_fail, 'at': time.monotonic() if now is None else now, 'step': ''}
        return n

    def answer(self, rest, now=None):
        """The mod's "drive" event: '<n> ok' / '<n> error <why>' / '<n> step <what>'."""
        parts = (rest or '').split(' ', 2)
        if len(parts) < 2 or not parts[0].isdigit():
            return
        w = self.waiting.get(int(parts[0]))
        if w is None:
            return
        w['at'] = time.monotonic() if now is None else now
        if parts[1] == 'step':
            w['step'] = parts[2] if len(parts) > 2 else ''
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
