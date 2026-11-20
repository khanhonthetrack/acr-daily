"""DAILIES in the game (ingamekit.py says how a page is made): the day's stages as cards, each with its photo, car and
conditions, DRIVE, and today's times (mine pinned). DRIVE asks in the game (the stake too, on the wager daily), then
does the window's DRIVE (app.drive_click)."""
from . import photos
from .i18n import _
from .ingamekit import (ACC, BG, FG2, GOOD, MUTED, PAGE_W, PANEL, PANEL2, SOFT, WHITE, board, box, chip, col, conditions,
                        fmt_ms, img, kicker, picture, primary, row, set_by, sp, stack, stage_name, tab_id, txt)

TAB = 'daily'


def opened(ig):
    ig.app.refresh_board()


def page(ig):
    a = ig.app
    if not a.dailies:
        msg = getattr(a, 'net_msg', '') or _('Loading today\'s dailies…')
        return col(kicker(_('Today')), txt(msg, 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    slots = sorted(a.dailies)
    gap = 28
    w = int((PAGE_W - gap * (len(slots) - 1)) / len(slots))
    return row(*[card(ig, s, w, pad=[0 if i == 0 else gap, 0, 0, 0]) for i, s in enumerate(slots)])


def card(ig, slot, w, **o):
    a = ig.app
    d = a.dailies[slot]
    ch = d['ch']
    km = '%.1f KM' % (ch['lengthM'] / 1000) if ch.get('lengthM') else ''
    photo = picture(photos.for_rally(ch.get('rally')) or 'dailies', w, 300)
    top = col(row(chip('SS%d' % slot), sp(10),
                  txt((ch.get('rally') or '').upper(), 16, 'bold', WHITE, sp=80, va='c', sh=True)),
              sp(h=1, fill=1),
              txt(stage_name(ch).upper(), 30, 'bold', WHITE, sh=True, wrap=True),
              txt(' · '.join(x for x in (km, (ch.get('surface') or '').upper()) if x), 16, 'semi', SOFT, sp=60, sh=True),
              pad=[22, 18, 22, 16], al='f', va='f')
    head = stack(img(photo, w, 300), top)
    car = ch.get('car', '') + ('  ·  %s' % ch['carClass'] if ch.get('carClass') else '')
    info = col(txt(car, 20, 'semi', WHITE),
               txt(' · '.join(x for x in (conditions(ch), set_by(ch)) if x), 16, 'medium', FG2, wrap=True,
                   pad=[0, 4, 0, 0]),
               row(primary(tab_id(TAB, 'drive', slot), _('DRIVE  ›')), sp(fill=1), mine(d, a.s.get('steamId')),
                   pad=[0, 16, 0, 0]),
               pad=[22, 16, 22, 18])
    sheet = board(d.get('board'), a.s.get('steamId'))
    return col(head, box(info, bg=PANEL), box(sheet, bg=PANEL2, p=[22, 16, 22, 18]), fill=1, **o)


def mine(d, me):
    """My place on the daily so far, or nothing."""
    entries = [e for e in (d.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
    for i, e in enumerate(entries):
        if e.get('steamId') == me:
            return col(kicker(_('You')), txt('P%d  ·  %s' % (i + 1, fmt_ms(e['totalMs'])), 20, 'bold', WHITE), va='c')
    return None


def click(ig, action, arg):
    if action == 'drive':
        ask_drive(ig, int(arg))


def ask_drive(ig, slot):
    a = ig.app
    d = a.dailies.get(slot)
    if not d:
        return
    ch = d['ch']
    from . import ingamedrive
    words = (_('Straight to the Service Park of SS%d: %s · %s · %s.') if ingamedrive.ready(a) else
             _('The game restarts on SS%d: %s · %s · %s.'))
    lines = [words % (slot, stage_name(ch), ch.get('car', ''), conditions(ch))]
    agreed = False
    try:
        offer = a._stake_offer(slot)
    except Exception:
        offer = None
    if offer and offer[0] != 'no' and (ch.get('wager') or {}).get('stake'):
        w, c = ch['wager'], a.credits or {}
        lines.append(_('Stake %d credits on SS%d? You have %d. The faster half get %d back.')
                     % (w['stake'], slot, c.get('balance') or 0, 2 * w['stake']))
        agreed = True
    ig.ask('SS%d' % slot, lines, _('DRIVE'), lambda: a.drive_click(slot, confirm=False, agreed=agreed))
