"""DRIVE's set-up screen in the game (0.2, the user, 21 Nov 2026: "if you press DRIVE, then there is a selection window
regarding CAR, TYRES, LIVERY and start, just to keep the main menu clean"). DRIVE on a daily, a time trial or an event
opens it over the pages; START does what DRIVE did before (its questions, the stake, the in-game set-up).

    ig.prep = {'kind': 'daily' | 'tt' | 'event', 'key': the slot or the event's id}
"""
from . import gear, i18n, settings
from .i18n import _
from .ingamekit import (BG, FOCUS, LINE2, MUTED, PANEL, PANEL2, SOFT, WHITE, banner, box, btn, col, kicker, primary,
                        quiet, row, size, sp, stack, tab_id, txt)

TAB = 'prep'
W = 1180                                 # the screen's width (the page's middle)
TILE_W, TILE_H = 260, 146                # a livery's / a car's tile
PER_ROW = 4
COUNT_W = 34


def open_(ig, kind, key):
    ig.prep = {'kind': kind, 'key': key}
    ig.dialog = None


def _what(ig):
    """-> (title kicker, name, stage id for the banner, the car {id, name} or None, the event or None, its cars to pick)"""
    a, p = ig.app, ig.prep
    if p['kind'] == 'daily':
        ch = (a.dailies.get(p['key']) or {}).get('ch') or {}
        return (_('DAILY · SS%d') % p['key'], i18n.data(ch.get('menuName') or ch.get('track') or ''), ch.get('stageId'),
                {'id': ch.get('carId'), 'name': ch.get('car')} if ch.get('carId') else None, None, [])
    if p['kind'] == 'tt':
        ch = ((getattr(a, 'tt', None) or {}).get(p['key']) or {}).get('ch') or {}
        return (_('TIME TRIAL · TT%d') % p['key'], i18n.data(ch.get('menuName') or ch.get('track') or ''),
                ch.get('stageId'), {'id': ch.get('carId'), 'name': ch.get('car')} if ch.get('carId') else None, None, [])
    ev = a._league_event(p['key']) or {}
    entry = ev.get('entry') or {}
    from . import leagues
    car = (leagues.car_of(ev, entry.get('car')) if entry.get('car') else None) or a._league_car(ev)
    cars = [] if ev.get('car') or entry.get('status') else (ev.get('cars') or [])
    first = next((s.get('stageId') for s in ev.get('stages') or [] if s.get('stageId')), None)
    return (a._event_of(ev).upper(), ev.get('name') or '', first, car, ev, cars)


def tile(id_, pic, words, on, sub=None):
    """A picture tile with its words under it; the one picked outlined in white."""
    face = stack(size(box(None, bg=PANEL2), w=TILE_W, h=TILE_H),
                 _pic(pic, TILE_W, TILE_H) if pic else txt(words, 18, 'bold', SOFT, al='c', va='c'))
    words_row = col(txt(words, 16, 'bold', WHITE if on else SOFT), txt(sub, 14, 'medium', MUTED) if sub else None,
                    pad=[2, 6, 2, 0])
    return btn(id_, c=col(face, words_row), bg='-', hov=PANEL2, foc=FOCUS, ol=WHITE if on else LINE2,
               olw=2 if on else 1, p=[6, 6, 6, 8], r=3)


def _pic(src, w, h):
    # (a car's picture whole, as CHANGE CAR shows it; a livery's paint or a photo cut to fill the tile)
    return dict(t='img', src=src, w=w, h=h, fill_crop=not str(src).startswith('ue:car:'))


def _grid(tiles):
    rows = []
    for i in range(0, len(tiles), PER_ROW):
        rows.append(row(*[dict(t, pad=[0 if j == 0 else 12, 0, 0, 0]) for j, t in enumerate(tiles[i:i + PER_ROW])],
                        pad=[0, 0 if i == 0 else 12, 0, 0]))
    return col(*rows)


def page(ig):
    a = ig.app
    head, name, stage_id, car, ev, cars = _what(ig)
    out = [stack(banner(stage_id, W, 220), col(sp(h=1, fill=1), txt(head, 15, 'bold', WHITE, sp=120, sh=True),
                                                txt(name.upper(), 34, 'bold', WHITE, sh=True, wrap=True),
                                                pad=[26, 18, 26, 18], al='f', va='f'))]
    body = []
    # CAR
    body.append(kicker(_('Car'), pad=[0, 0, 0, 8]))
    if cars:
        cur = (car or {}).get('name')
        body.append(_grid([tile(tab_id(TAB, 'car', i), 'ue:car:%s' % c.get('id'),
                                c['name'], c['name'] == cur) for i, c in enumerate(cars)]))
    elif car:
        body.append(_grid([tile(tab_id(TAB, 'nop', 'car'), 'ue:car:%s' % car['id'],
                                car['name'], True)]))
    # TYRES
    rows_ = gear.compounds(ev) if ev and ev.get('kind') != 'live' else ()
    body.append(kicker(_('Tyres'), pad=[0, 22, 0, 8]))
    if len(rows_) > 1:
        mine = gear.tyres_of(a.s, ev)
        counts = mine or gear.start_counts(ev)
        cells = [btn(tab_id(TAB, 'tyreauto'), _('AUTO'), bg=WHITE if not mine else '-', hov=WHITE, foc=FOCUS,
                     fg=BG if not mine else SOFT, hfg=BG, sz=16, f='bold', p=[16, 6, 16, 6], r=2,
                     ol=None if not mine else LINE2, va='c')]
        for r in rows_:
            cells.append(row(txt(gear.NAMES.get(r, r), 17, 'semi', SOFT, va='c'), sp(10),
                             quiet(tab_id(TAB, 'tyre', '%s:-1' % r), '‹', p=[12, 4, 12, 4], va='c'),
                             size(txt('%d' % counts.get(r, 0), 20, 'bold', WHITE if mine else MUTED, j=1, va='c'),
                                  w=COUNT_W),
                             quiet(tab_id(TAB, 'tyre', '%s:1' % r), '›', p=[12, 4, 12, 4], va='c'),
                             pad=[26, 0, 0, 0], va='c'))
        body.append(row(*cells))
        body.append(txt(_('%d tyres in all') % gear.TYRES, 15, 'medium', MUTED, pad=[0, 6, 0, 0]))
    else:
        body.append(txt(_('The game picks them, the same for everyone.'), 17, 'medium', MUTED))
    # LIVERY
    if car:
        picked = gear.livery_of(a.s, car['id'])
        opts = [('', _("GAME'S PICK"))] + gear.choices(car['id'])
        body.append(kicker(_('Livery'), pad=[0, 22, 0, 8]))
        body.append(_grid([tile(tab_id(TAB, 'livery', i), gear.preview(car['id'], n, TILE_W, TILE_H) if n else None,
                                words, (n or None) == picked,
                                _('as set in the garage') if not n else None)
                           for i, (n, words) in enumerate(opts)]))
    # START
    body.append(row(primary(tab_id(TAB, 'start'), _('START  ›'), p=[40, 12, 40, 12]), sp(14),
                    quiet(tab_id(TAB, 'back'), _('BACK'), va='c'), pad=[0, 28, 0, 0]))
    out.append(box(col(*body), bg=PANEL, p=[26, 22, 26, 26]))
    return row(sp(fill=1), size(col(*out), w=W), sp(fill=1))


def click(ig, action, arg):
    a, p = ig.app, ig.prep
    if not p:
        return
    _head, _name, _stage, car, ev, cars = _what(ig)
    if action == 'back':
        ig.prep = None
    elif action == 'car' and arg is not None and ev:
        try:
            a._pick_car(ev, cars[int(arg)]['name'])
        except (ValueError, IndexError, KeyError):
            pass
    elif action == 'tyre' and arg and ev:
        r, _sep, d = arg.rpartition(':')
        gear.step_tyres(a.s, ev, r, 1 if d == '1' else -1)
    elif action == 'tyreauto' and ev:
        gear.auto_tyres(a.s, ev)
    elif action == 'livery' and arg is not None and car:
        opts = [''] + [n for n, _w in gear.choices(car['id'])]
        try:
            name = opts[int(arg)]
        except (ValueError, IndexError):
            return
        if name:
            gear.pick_livery(a.s, car['id'], name)
        else:
            (a.s.get('carLivery') or {}).pop(car['id'], None)
            settings.save(a.s)
    elif action == 'start':
        if cars and not car:
            ig.say(_('Pick your car'), [_('Pick one of the cars first.')])
            return
        ig.prep = None
        kind, key = p['kind'], p['key']
        if kind == 'daily':
            from . import ig_daily
            ig_daily.ask_drive(ig, key)
        elif kind == 'tt':
            from . import ig_tt
            ig_tt.ask_drive(ig, key)
        else:
            from . import ig_comp
            ig_comp.drive(ig, key)
