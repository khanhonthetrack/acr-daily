"""WATCH's broadcast over the stage (watch.py says what WATCH is; the mod draws it: appui.lua's overlay, never taking a
key or a click). Top left: LIVE, the stage, how many on it. Left: everyone on the stage now, the furthest on first,
with how far they are, their time and the gap to today's #1 at the same place on the road; the one followed lit.
Right: today's best times. Bottom: the driver followed, big; the camera, and the keys."""
import time

from . import watch as watch_mod
from .i18n import _
from .ingamekit import (ACC, BAD, GOOD, MUTED, PANEL, SOFT, WHITE, box, chip, col, fmt_ms, kicker, row, shown_name,
                        size, sp, stage_name, txt)

LIST_W, BOARD_W, CARD_W = 560, 430, 980
ROWS = 12
TOP = 8
LIVE = 'FF4655'


def _gap(ms):
    if ms is None:
        return '', MUTED
    s = abs(ms) / 1000.0
    return ('+' if ms > 0 else '−') + ('%.1f' % s), (BAD if ms > 0 else GOOD)


def _bar(frac, w, colour=WHITE):
    frac = max(0.0, min(1.0, frac or 0.0))
    return size(row(size(box(None, bg=colour), w=max(1, round(w * frac)), h=4), sp(fill=1)), w=w, h=4)


def overlay(ig):
    """-> the broadcast's tree, or None (not watching)."""
    a = ig.app
    w = getattr(a, 'watch', None)
    if w is None or not w.on:
        return None
    ch = w.ch() or {}
    from . import ig_daily
    ig_daily.refresh_live(ig, w.kind)            # (the website's list too: the drivers with no car on the relay)
    now = time.monotonic()
    rows = w.rows(now)
    fol = w.followed()
    title = (_('DAILY · SS%d') % w.slot) if w.kind == 'daily' else (_('TIME TRIAL · TT%d') % w.slot)
    head = box(row(chip(_('LIVE'), bg=LIVE), sp(12),
                   col(txt(title, 14, 'bold', SOFT, sp=100), txt(stage_name(ch).upper(), 24, 'bold', WHITE)),
                   sp(18), col(txt('%d' % len(rows), 24, 'bold', WHITE, j=2), kicker(_('on stage')), va='c')),
               bg='000000', a=0.62, p=[14, 10, 18, 10], r=3)
    # everyone on the stage now
    lines = [row(kicker(_('On stage')), sp(fill=1), kicker(_('gap to #1')), pad=[0, 0, 0, 6])]
    for i, r in enumerate(rows[:ROWS]):
        d = r['driver']
        at = r['at'] or {}
        on = fol is not None and d is not None and d.id == fol.id
        g, gfg = _gap(at.get('gap'))
        lines.append(box(col(row(txt('%d' % (i + 1), 16, 'bold', MUTED, j=2), sp(10),
                                 txt(r['name'], 17, 'bold' if on else 'semi', WHITE if on else SOFT, fill=1),
                                 txt(_('MAP ONLY'), 12, 'bold', MUTED, sp=60, va='c', pad=[0, 0, 10, 0])
                                 if d is None else None,
                                 txt(fmt_ms(at['ms']) if at.get('ms') else '', 16, 'semi', SOFT, j=2), sp(12),
                                 size(txt(g, 16, 'bold', gfg, j=2), w=64)),
                             _bar(at.get('progress'), LIST_W - 40, ACC if on else '6B6B75'), sp(h=2)),
                         bg=('2A2A31' if on else '000000'), a=0.7 if on else 0.55, p=[10, 5, 10, 5],
                         pad=[0, 3, 0, 0]))
    if not rows:
        lines.append(box(txt(_('Nobody on the stage right now. Their cars come as they start.'), 16, 'medium', SOFT,
                             wrap=True), bg='000000', a=0.55, p=[10, 8, 10, 8]))
    left = size(col(*lines), w=LIST_W)
    # today's best times
    board = (((a.dailies or {}).get(w.slot) or {}) if w.kind == 'daily' else
             ((getattr(a, 'tt', None) or {}).get(w.slot) or {})).get('board') or {}
    entries = [e for e in board.get('entries', []) if e.get('totalMs') is not None][:TOP]
    best = [row(kicker(_("Today's best") if w.kind == 'daily' else _("This week's best")), pad=[0, 0, 0, 6])]
    for i, e in enumerate(entries):
        best.append(box(row(txt('%d' % (i + 1), 16, 'bold', ACC if i == 0 else MUTED), sp(10),
                            txt(shown_name(e), 16, 'semi', SOFT, fill=1), txt(fmt_ms(e['totalMs']), 16, 'semi', WHITE)),
                        bg='000000', a=0.55, p=[10, 5, 10, 5], pad=[0, 3, 0, 0]))
    right = size(col(*best), w=BOARD_W)
    # the driver followed
    if fol is not None:
        at = w.where(fol, now) or {}
        g, gfg = _gap(at.get('gap'))
        card = box(col(row(col(kicker(_('Following')), txt(fol.name, 34, 'bold', WHITE),
                               txt(fol.car or '', 16, 'medium', SOFT)), sp(fill=1),
                           col(kicker(_('Time')), txt(fmt_ms(at['ms']) if at.get('ms') else '–', 34, 'bold', WHITE),
                               al='r'), sp(30),
                           col(kicker(_('to #1')), txt(g or '–', 34, 'bold', gfg if g else MUTED), al='r')),
                       _bar(at.get('progress'), CARD_W - 40, ACC),
                       row(txt('%.1f km' % at['km'] if at.get('km') is not None else '', 14, 'medium', MUTED), sp(fill=1),
                           txt(_('CAMERA: %s   ·   LEFT / RIGHT: driver   ·   UP / DOWN: camera   ·   Esc: leave')
                               % watch_mod.CAM_NAMES.get(w.cam_name(), ''), 14, 'medium', MUTED), pad=[0, 6, 0, 0])),
                   bg='000000', a=0.66, p=[22, 14, 22, 14], r=3)
    elif rows:                                   # (on the map, none with a car to watch: they send none to the relay)
        card = box(txt(_("%d on the stage, but their game doesn't send their car: nothing to watch yet.") % len(rows),
                       20, 'semi', SOFT), bg='000000', a=0.6, p=[22, 14, 22, 14])
    else:
        card = box(txt(_('Waiting for a driver on the stage…'), 20, 'semi', SOFT), bg='000000', a=0.6, p=[22, 14, 22, 14])
    return col(row(col(head, sp(h=12), left), sp(fill=1), right),
               sp(fill=1),
               row(sp(fill=1), size(card, w=CARD_W), sp(fill=1)))


def start(ig, kind, slot):
    """WATCH on a daily / a time trial: its stage set up in the game, the game on to the Service Park; at the start line
    the camera goes to the others (watch.py)."""
    a = ig.app
    from . import ingamedrive, saveslot
    ch = ((a.dailies or {}).get(slot) or {}).get('ch') if kind == 'daily' else \
        ((getattr(a, 'tt', None) or {}).get(slot) or {}).get('ch')
    if not ch:
        return
    if not ingamedrive.ready(a):
        ig.say(_('WATCH'), [_("Go to the game's main menu first (no rally of yours in progress).")])
        return
    try:
        setup = ingamedrive.setup_of(ingamedrive.daily_stages(ch), ch['carId'], ch.get('weekend'))
    except (saveslot.SaveError, KeyError):
        return
    a.watch.start(kind, slot)

    def ok():
        a.sub_l.configure(text=_('At the Service Park: START STAGE, then you watch from the start line.'))

    def old_way():
        a.watch.stop()
    a.sub_l.configure(text=_('Taking you to %s to watch...') % stage_name(ch))
    a.ingame_drive(setup, ok, 'WATCH', old_way, offer_restart=False)
