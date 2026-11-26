"""Which room on the live relay a driver is in: one per EVENT, not per stage.

The relay (live/relay.py) puts everyone whose game reports the same stage name in one room, unless they send a room tag.
So a driver in free practice or a time attack on the daily's stage was in the daily's room: their car on the stage, in
WATCH's list, in the ghost cars of the daily's drivers (the user, 26 Nov 2026: "one should only see ghosts with respect
to that event: for the daily, anyone doing the daily ONLY. Same with leagues, cups, etc.").

The tags (the relay lowercases them and keeps [a-z0-9:_-], 40 characters):

    daily:<challenge>   a daily's stage (the Rally Weekend ACR DAILY took the game to)
    tt:<challenge>      a time trial stage
    ev:<event id>       a league / cup / 1V1 / championship event's stage
    live:<event id>     a ranked session's (liverallyui.py, as before)    cp:<lobby>  a COPILOT crew's (copilot.py)
    free                anything else: free practice, a single stage, a Rally Weekend set up by hand in the game

An app from before this sent no tag at all: its drivers are in the stage's old shared room, apart from every tag above.
"""
import re

FREE = 'free'
MAX_LEN = 40


def tag(prefix, ident):
    """'<prefix>:<ident>' as the relay keeps it (lowercase, [a-z0-9:_-], at most MAX_LEN), or None without an ident."""
    ident = re.sub(r'[^a-z0-9_-]+', '-', str(ident if ident is not None else '').lower()).strip('-')
    return ('%s:%s' % (prefix, ident))[:MAX_LEN] if ident else None


def for_challenge(kind, ch):
    """The room of a daily's ('daily') or a time trial stage's ('tt') challenge dict, or None."""
    ch = ch or {}
    return tag(kind, ch.get('id') or ch.get('date'))


def for_event(ev):
    """The room of a league / cup / 1V1 / championship event (its dict: 'id', or WATCH's 'eventId'), or None."""
    ev = ev or {}
    return tag('ev', ev.get('id') if ev.get('id') is not None else ev.get('eventId'))


def _held(held, slot, kind, here):
    """The room for the daily / time trial stage `slot` of `held` ({slot: {'ch', 'judge', 'norally'}}), as the game is:
    its counted run on (its judge running), or its stage waiting there (`here`: the game was taken to it by ACR DAILY)."""
    d = (held or {}).get(slot) or {}
    j = d.get('judge')
    running = j is not None and getattr(j, 'state', None) == 'running'
    if running and d.get('norally'):
        return FREE                      # (a run that doesn't count: not the Rally Weekend, its settings changed, WATCH)
    if running or here:
        return for_challenge(kind, d.get('ch')) or FREE
    return FREE


def of(app):
    """The room the app's driver is in now, as far as the app can tell (not a ranked session's or a crew's: liverallyui.
    _lr_room asks those first). `app`: drive_target, league_run, dailies, active, tt, tt_active, set_up_here()."""
    try:
        here = app.set_up_here()         # True: ACR DAILY took the game to the stage loaded; False: set up by hand; None: unknown
    except Exception:
        here = None
    if here is False:
        return FREE                      # (free practice, a single stage, a Rally Weekend of the driver's own)
    target = getattr(app, 'drive_target', 'daily')
    run = getattr(app, 'league_run', None)
    if target == 'league' and run and not run.get('over'):
        j = run.get('judge')
        if here or (j is not None and getattr(j, 'state', None) == 'running'):
            return for_event(run.get('ev')) or FREE
        return FREE
    if target == 'tt':
        held = getattr(app, 'tt', None) or {}
        slot = next((s for s, t in held.items() if t.get('judge') is not None and t['judge'].state == 'running'), None)
        return _held(held, slot if slot is not None else getattr(app, 'tt_active', None), 'tt', bool(here))
    held = getattr(app, 'dailies', None) or {}
    slot = next((s for s, d in held.items() if d.get('judge') is not None and d['judge'].state == 'running'), None)
    return _held(held, slot if slot is not None else getattr(app, 'active', None), 'daily', bool(here))
