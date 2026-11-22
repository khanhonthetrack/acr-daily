"""The drivers' liveries on their cars in WATCH (0.2, the user, 22 Nov 2026: "for ghosts, we should be able to see THEIR
LIVERY ... something like Trading Paints on iRacing").

    mine(app)          your car's livery as the game has it on (the mod's ingame-livery.txt: its AcrLivery ID, the
                       official row or "usergen_<folder>"), and its ACR Daily catalogue id when it came from there:
                       sent to the relay with your car (livelink.set_livery)
    ready(app, d)      the livery the driver d (a livelink.LiveDriver) has on, by the name the game paints it with, if
                       it is in this game: an official one always; one of the driver's own if a folder of that name is
                       here; a catalogue one not here yet is fetched and installed (once, in a thread) and the game
                       reads its liveries again. None meanwhile, or for a livery only its driver has.

The mod paints it on the car followed (main.lua livery_tick)."""
import os
import threading
import time

from . import liveries, settings

LIVERY_FILE = 'ingame-livery.txt'
READ_EVERY_S = 2.0
_mine = {'at': -1e9, 'v': (None, None)}
_fetching = {}                  # catalogue id -> 'busy' / 'done' / 'failed'
_folders = {'at': -1e9, 'set': set()}


def mine(app):
    """(your livery's name, its catalogue id or None), or (None, None) before the game said."""
    now = time.monotonic()
    if now - _mine['at'] < READ_EVERY_S:
        return _mine['v']
    _mine['at'] = now
    try:
        with open(os.path.join(settings.DIR, LIVERY_FILE), encoding='utf-8') as f:
            name = f.read().strip()[:80] or None
    except OSError:
        name = None
    lid = None
    if name and name.startswith('usergen_'):
        folder = name[len('usergen_'):]
        for k, v in liveries.installed().items():
            if any(os.path.basename(os.path.normpath(p)) == folder for p in v.get('dirs') or []):
                try:
                    lid = int(k)
                except ValueError:
                    lid = None
                break
    _mine['v'] = (name, lid)
    return _mine['v']


def _local_folders():
    """The folder names under the game's liveries folder (any car), looked at again every few seconds."""
    now = time.monotonic()
    if now - _folders['at'] > 5.0:
        _folders['at'] = now
        out = set()
        try:
            base = liveries.root()
            for car in os.listdir(base):
                p = os.path.join(base, car)
                if os.path.isdir(p):
                    out.update(os.listdir(p))
        except OSError:
            pass
        _folders['set'] = out
    return _folders['set']


def ready(app, d):
    name = getattr(d, 'livery', None)
    if not name:
        return None
    if not name.startswith('usergen_'):
        return name                                   # (the game's own: every game has it)
    if name[len('usergen_'):] in _local_folders():
        return name
    lid = getattr(d, 'livery_id', None)
    if lid and _fetching.get(lid) is None:
        _fetching[lid] = 'busy'
        threading.Thread(target=_fetch, args=(app, lid), daemon=True).start()
    return None


def _fetch(app, lid):
    """A catalogue livery a driver on the stage has on: downloaded and installed, then the game told to read its
    liveries again (appui cmd 'liveries': drive.lua rescan_liveries)."""
    try:
        cat = app.api.liveries() or {}
        lv = next((x for x in cat.get('liveries') or [] if x.get('id') == lid), None)
        if not lv or not lv.get('direct'):
            _fetching[lid] = 'failed'
            return
        path = liveries.download(lv)
        liveries.install(lv, path, cat.get('cars') or [])
        _folders['at'] = -1e9
        _fetching[lid] = 'done'
        ig = getattr(app, 'ingame_app', None)
        if ig is not None:
            app.root.after(0, lambda: setattr(ig, 'cmd', {'n': ig.cmd['n'] + 1, 'do': 'liveries'}))
    except Exception:
        _fetching[lid] = 'failed'
