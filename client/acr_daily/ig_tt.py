"""TIME TRIAL in the game (ingamekit.py says how a page is made): the week's stages as cards with this week's times
(mine pinned), DRIVE asked in the game, then the window's (app.tt_drive)."""
from . import ig_daily, photos
from .i18n import _
from .ingamekit import (COLOUR, FG2, MUTED, PAGE_W, PANEL, PANEL2, SOFT, WHITE, board, box, chip, col, conditions, img,
                        kicker, picture, primary, row, sp, stack, stage_name, tab_id, txt)

TAB = 'tt'


def opened(ig):
    ig.app.refresh_tt()


def page(ig):
    a = ig.app
    tt = getattr(a, 'tt', None) or {}
    if not tt:
        info = getattr(a, 'tt_info', None) or {}
        msg = _('No time trial this week.') if info and not info.get('on') else _('Loading the time trial…')
        return col(kicker(_('Time trial')), txt(msg, 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    slots = sorted(tt)
    gap = 28
    w = int((PAGE_W - gap * (len(slots) - 1)) / len(slots))
    cards = []
    for i, slot in enumerate(slots):
        t = tt[slot]
        ch = t['ch']
        photo = picture(photos.for_rally(ch.get('rally')) or 'tt', w, 300)
        top = col(row(chip('TT%d' % slot, bg=COLOUR['tt']), sp(10),
                      txt((ch.get('rally') or '').upper(), 16, 'bold', WHITE, sp=80, va='c', sh=True)),
                  sp(h=1, fill=1),
                  txt(stage_name(ch).upper(), 30, 'bold', WHITE, sh=True, wrap=True),
                  pad=[22, 18, 22, 16], al='f', va='f')
        info = col(txt(ch.get('car', ''), 20, 'semi', WHITE),
                   txt(conditions(ch), 16, 'medium', FG2, wrap=True, pad=[0, 4, 0, 0]),
                   row(primary(tab_id(TAB, 'drive', slot), _('DRIVE  ›')), sp(fill=1),
                       ig_daily.mine(t, a.s.get('steamId')), pad=[0, 16, 0, 0]),
                   pad=[22, 16, 22, 18])
        sheet = board(t.get('board'), a.s.get('steamId'), title=_('This week\'s times'), sid='tt:board:%s' % slot)
        cards.append(col(stack(img(photo, w, 300), top), box(info, bg=PANEL), box(sheet, bg=PANEL2, p=[22, 16, 22, 18]),
                         fill=1, pad=[0 if i == 0 else gap, 0, 0, 0]))
    return row(*cards)


def click(ig, action, arg):
    if action == 'drive':
        a = ig.app
        slot = int(arg)
        t = a.tt.get(slot)
        if not t:
            return
        ch = t['ch']
        from . import ingamedrive
        words = (_('Straight to the Service Park of TT%d: %s · %s · %s.') if ingamedrive.ready(a) else
                 _('The game restarts on TT%d: %s · %s · %s.'))
        ig.ask('TT%d' % slot, [words % (slot, stage_name(ch), ch.get('car', ''),
                                                                             conditions(ch))],
               _('DRIVE'), lambda: a.tt_drive(slot, confirm=False))
