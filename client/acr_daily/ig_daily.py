"""DAILIES in the game (ingamekit.py says how a page is made): the day's stages as cards, each with its photo, car and
conditions, DRIVE, and today's times (mine pinned). DRIVE asks in the game (the stake too, on the wager daily), then
does the window's DRIVE (app.drive_click)."""
from . import photos
from .i18n import _
from .ingamekit import (ACC, BG, FG2, GOOD, MUTED, PAGE_W, PANEL, PANEL2, SOFT, WHITE, board, box, chip, col, conditions,
                        banner, fmt_ms, img, kicker, picture, primary, quiet, row, set_by, sp, stack, stage_name, tab_id,
                        txt)

TAB = 'daily'


def opened(ig):
    ig.app.refresh_board()


def page(ig):
    a = ig.app
    if not a.dailies:
        msg = getattr(a, 'net_msg', '') or _('Loading today\'s dailies…')
        return col(kicker(_('Today')), txt(msg, 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    refresh_live(ig, 'daily')
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
    # (the country in the chip: on the picture alone it couldn't be read, 22 Nov 2026)
    top = col(row(chip(' · '.join(x for x in ('SS%d' % slot, (ch.get('rally') or '').upper()) if x))),
              sp(h=1, fill=1),
              txt(stage_name(ch).upper(), 30, 'bold', WHITE, sh=True, wrap=True),
              txt(' · '.join(x for x in (km, (ch.get('surface') or '').upper()) if x), 16, 'semi', SOFT, sp=60, sh=True),
              pad=[22, 18, 22, 16], al='f', va='f')
    head = stack(banner(ch.get('stageId'), w, 300, photo), top)   # (the game's own picture of the stage)
    car = ch.get('car', '') + ('  ·  %s' % ch['carClass'] if ch.get('carClass') else '')
    info = col(txt(car, 20, 'semi', WHITE),
               txt(' · '.join(x for x in (conditions(ch), set_by(ch)) if x), 16, 'medium', FG2, wrap=True,
                   pad=[0, 4, 0, 0]),
               row(primary(tab_id(TAB, 'drive', slot), _('DRIVE  ›')), sp(12), watch_btn(TAB, slot, d.get('live')),
                   sp(fill=1), mine(d, a.s.get('steamId')),
                   pad=[0, 16, 0, 0]),
               pad=[22, 16, 22, 18])
    sheet = board(d.get('board'), a.s.get('steamId'), rows=8, sid='daily:board:%s' % slot)   # (mine pinned on screen)
    return col(head, box(info, bg=PANEL), box(sheet, bg=PANEL2, p=[22, 16, 22, 18]), fill=1, **o)


LIVE_EVERY_S = 8.0                     # who is on each stage now: fetched this often while the page / WATCH is on


def refresh_live(ig, kind):
    """Who is on each daily's (kind 'daily') or time trial's ('tt') stage now, the website's live list, fetched every
    LIVE_EVERY_S (the WATCH · n LIVE buttons, WATCH's broadcast: the user, 21 Nov 2026, "should show live number of
    people on stage, not that I have to leave and return")."""
    import threading
    import time
    a = ig.app
    m = ig.mem('live:' + kind)
    now = time.monotonic()
    if m.get('busy') or now - m.get('at', -1e9) < LIVE_EVERY_S or not a.api.configured:
        return
    m['at'], m['busy'] = now, True
    from .ttui import listed
    held = dict(a.dailies or {}) if kind == 'daily' else listed(getattr(a, 'tt', None))

    def go():
        try:
            for slot, d in held.items():
                ch = d.get('ch') or {}
                try:
                    if kind == 'daily':
                        r = a.api.live_now(ch.get('date'), slot) or {}
                        a.root.after(0, a._take_live, d, r.get('drivers') or [])
                    else:
                        r = a.api.tt_live_now(ch.get('week'), slot) or {}
                        a.root.after(0, a._tt_take_live, d, r.get('drivers') or [])
                    d['live_at'] = time.monotonic()
                except Exception:
                    pass
        finally:
            m['busy'] = False
    threading.Thread(target=go, daemon=True).start()


def watch_btn(tab, slot, live=None):
    """WATCH: the others on this stage now, from the start line (ig_watch.py); how many, when known."""
    n = len([x for x in live or () if x.get('state') == 'live'])
    return quiet(tab_id(tab, 'watch', slot), (_('WATCH · %d LIVE') % n) if n else _('WATCH'), va='c')


def mine(d, me):
    """My place on the daily so far, or room for it."""
    entries = [e for e in (d.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
    for i, e in enumerate(entries):
        if e.get('steamId') == me:
            # (the time only: the place is on the board under it; with it, it ran off the card, the user 22 Nov 2026)
            return col(kicker(_('You')), txt(fmt_ms(e['totalMs']), 20, 'bold', WHITE), va='c')
    return sp(h=48)                            # (as tall: every card's box the same height)


def click(ig, action, arg):
    if action == 'drive':                      # (its set-up screen first: car, tyres, livery, START: ig_prep.py)
        from . import ig_prep
        ig_prep.open_(ig, 'daily', int(arg))
    elif action == 'watch':                    # (WATCH: the others on its stage now, ig_watch.py)
        from . import ig_watch
        ig_watch.start(ig, 'daily', int(arg))


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
