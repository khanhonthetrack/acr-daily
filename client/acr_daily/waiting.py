"""Finished runs waiting for the game's official result, kept on disk, so closing ACR Daily (or a crash) loses none.

The game writes a Rally Weekend stage's result (its stage time + its penalties) into its save once the driver goes on
from its results screen, not at the finish line (seen in the game 2026-10-09), so a run can wait a while. Each run
waiting is kept in awaiting.json, next to the send queues, and looked for again in the game's save when the app
starts: a daily's by app.py (_await_official), a league stage's by leagueui.py.

    {'id', 'kind': 'daily' | 'league', 'result': the app's run, 'stageId', 'carId', 'known': the game's results
     before it, 'until': unix time it is waited for at most, ...}   ('slot' for a daily; 'eventId', 'no', 'event'
                                                                      (its rules and stages) for a league stage)
"""
import json
import os

from . import settings

KINDS = ('daily', 'league')
HINT = 'Go on from the game\'s results screen (keep ACR Daily open): the game saves its official time then.'


def _file():
    return os.path.join(settings.DIR, 'awaiting.json')


def load(kind=None):
    """The runs waiting, oldest first (only those of `kind` if given)."""
    try:
        with open(_file(), encoding='utf-8') as f:
            items = json.load(f)
    except (OSError, ValueError):
        return []
    return [x for x in items if isinstance(x, dict) and x.get('kind') in KINDS and x.get('id')
            and (kind is None or x['kind'] == kind)]


def _save(items):
    os.makedirs(settings.DIR, exist_ok=True)
    tmp = _file() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f)
    os.replace(tmp, _file())


def add(item):
    """Keep a run waiting (item: see above; replaces one with the same id)."""
    _save([x for x in load() if x['id'] != item['id']] + [item])


def remove(item_id):
    """The wait for this run is over (sent with its result, or as a DNF)."""
    items = load()
    if any(x['id'] == item_id for x in items):
        _save([x for x in items if x['id'] != item_id])
