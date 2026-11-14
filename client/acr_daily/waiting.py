"""Finished runs waiting for the game's official result, kept on disk, so closing ACR Daily (or a crash) loses none.

The game writes a Rally Weekend stage's result (its stage time + its penalties) into its save once the driver goes on
from its results screen, not at the finish line (seen in the game 2026-10-09), so a run can wait a while. Each run
waiting is kept in awaiting.json, next to the send queues, and looked for again in the game's save when the app
starts: a daily's and a time trial stage's by app.py (_await_official), a league stage's by leagueui.py.

    {'id', 'kind': 'daily' | 'tt' | 'league', 'result': the app's run, 'stageId', 'carId', 'known': the game's results
     before it, 'until': unix time it is waited for at most, ...}   ('slot' for a daily or a time trial stage; 'eventId', 'no', 'event'
                                                                      (its rules and stages) for a league stage)
"""
import json
import os

from . import settings
from .i18n import _

KINDS = ('daily', 'league', 'tt')
HINT = _('Leave the game\'s results screen to save your official time.')
# A lost result whose save the game wrote after the finish yet holds no Rally Weekend result at all: the stage was most
# likely driven as a Single Rally Stage, which keeps no time (14 Nov 2026: reports #17 and #21). The driver is told
# (app.py _lost_save, with the server's answer; ttui.py).
SINGLE_STAGE_HINT = _("The game kept no time for this run: it was likely driven as a Single Rally Stage. Only a Rally "
                      "Weekend keeps the game's time: start the daily with DRIVE in ACR Daily.")


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


LOG_MAX = 256 * 1024     # official.log is cut to its newer half past this


def note(text):
    """A line in official.log (next to awaiting.json): what each look at the game's save found while a run waited, and
    how the wait ended, so a run the game saved but the app sent as a DNF can be explained afterwards. Never raises."""
    try:
        import time
        path = os.path.join(settings.DIR, 'official.log')
        os.makedirs(settings.DIR, exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX:
            with open(path, 'rb') as f:
                f.seek(-LOG_MAX // 2, os.SEEK_END)
                keep = f.read().split(b'\n', 1)[-1]
            with open(path, 'wb') as f:
                f.write(keep)
        with open(path, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text))
    except Exception:
        pass
