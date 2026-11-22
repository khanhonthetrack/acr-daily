"""WATCH's broadcast over the stage, as a rally's TV graphics (watch.py says what WATCH is; the mod draws it: appui.lua's
overlay, never taking a key or a click). The user, 21 Nov 2026: "more professional and more with broadcast soul ...
Make it look like real broadcast. LIVE stuff. Like WRC broadcast" (examples: the WRC TV graphics, Rally.TV).

    top left     the standings tower: the stage, today's best (place, a three-letter code, the gap), then ON STAGE: the
                 drivers on the stage now, with where their time puts them; the one followed lit
    top right    the LIVE bug; the camera on (a moment after each cut); the split times, the followed driver against
                 the day's #1 (SPLITS)
    bottom       the dash (revs, speed, gear, brake and throttle) and the driver bar: the stage line with its splits and
                 where they are, their name, flag, car, the gap to #1 and their time; a split's time a moment as they
                 pass it
    middle left  the spectator menu (Select / Enter): the driver, the camera, AUTO driver, the graphics, the splits

The parts that move many times a second (bars, the dot on the stage line, colours) are marked lv: the mod sets them in
place (appui.lua set_lives), the widgets made once."""
import os
import time

from . import watch as watch_mod
from .i18n import _
from .ingamekit import (MUTED, SOFT, WHITE, box, col, fmt_ms, img, kicker, row, size, sp, stage_name, stack, txt)

# the broadcast's look: deep navy panels, the app's red, white words
NAVY, NAVY2, NAVY3 = '0A1428', '13213D', '1C2D4F'
RED, RED2 = 'E30613', 'FF2D3A'
GREEN, AMBER, GREY = '2BD96B', 'FFB020', '5C6A84'
FAST, SLOW = '2BD96B', 'FF453A'
NA = 0.88                          # the panels' alpha
TOWER_W, TOWER_TOP, TOWER_LIVE = 250, 10, 6
BAR_W, DASH_W = 920, 380
SPLITS_W = 430
LINE_W = 580                       # the stage line's width in the driver bar
SPLIT_SHOW_S = 8.0                 # a split's time shown this long after it is passed
SHOT_SHOW_S = 4.0                  # the camera's name shown this long after a cut
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo-96.png')   # (79 x 96: ACR and the car)


def _code(name, taken):
    """A driver's three letters (as the TV's tower: OGI, EVA...), not one already taken."""
    letters = ''.join(ch for ch in (name or '').upper() if ch.isalnum()) or 'DRV'
    for c in (letters[:3], letters[:2] + letters[-1:], letters[:1] + letters[2:4]):
        c = (c + 'XXX')[:3]
        if c not in taken:
            taken.add(c)
            return c
    return letters[:3]


def _gap_s(ms, dec=1):
    if ms is None:
        return ''
    return ('+' if ms > 0 else '−') + ('%.*f' % (dec, abs(ms) / 1000.0))


def _clock(ms):
    """A running time as the TV shows it: 4:43.9 (tenths)."""
    if ms is None or ms < 0:
        return '–:––.–'
    ms = int(ms)
    m, s = divmod(ms, 60000)
    return '%d:%04.1f' % (m, int(s / 100) / 10.0)


def _slash(colour=RED, h=30, w=6):
    return size(box(None, bg=colour), w=w, h=h, sk=-18, pad=[4, 0, 4, 0], va='c')


def _flag(code, w=36, h=24):
    if not code:
        return None
    try:
        from .ig_ranked import flag_png
        p = flag_png(code)
    except Exception:
        p = None
    return img(p, w, h, va='c') if p else None


# ---------------------------------------------------------------------- the parts
def _tower(w, rows, fol, now, board_entries, codes):
    ch = w.ch() or {}
    # (the stage's name smaller the longer it is: "YXTJÄRNSHÖJDEN WEST" ran past the box, the user 22 Nov 2026)
    name = stage_name(ch, short=True).upper()
    nsz = 18 if len(name) <= 14 else (15 if len(name) <= 18 else 13)
    if len(name) > 24:
        name = name[:23].rstrip() + '…'
    head = box(row(txt(('TT%d' % w.slot) if w.kind == 'tt' else ('SS%d' % w.slot), 20, 'bold', WHITE, va='c'),
                   _slash(WHITE, 20, 3),
                   txt(name, nsz, 'bold', WHITE, va='c', fill=1)),
               bg=RED, p=[12, 5, 12, 5])
    best = {'daily': _("TODAY'S BEST"), 'tt': _("THIS WEEK'S BEST")}.get(w.kind) or _('STAGE BEST')
    lines = [head, box(txt(best, 13, 'bold', SOFT, sp=140, j=1), bg=NAVY, a=NA, p=[8, 5, 8, 4])] if board_entries else [head]
    lead = board_entries[0]['totalMs'] if board_entries else None
    for i, e in enumerate(board_entries[:TOWER_TOP]):
        code = codes.get(('b', i)) or '???'
        right = fmt_ms(e['totalMs'], 1) if i == 0 else _gap_s(e['totalMs'] - lead, 1)
        lines.append(box(row(size(box(txt('%d' % (i + 1), 16, 'bold', NAVY, j=1), bg=WHITE, al='c', va='c'), w=28, h=26,
                                  va='c'),
                             _slash(RED, 24, 4),
                             txt(code, 19, 'bold', WHITE, va='c', sp=40), sp(fill=1),
                             txt(right, 15, 'semi', SOFT if i else WHITE, va='c')),
                         bg=NAVY, a=NA, p=[8, 3, 10, 3]))
    if rows:
        lines.append(box(txt(_('ON STAGE'), 13, 'bold', SOFT, sp=140, j=1), bg=NAVY, a=NA, p=[8, 6, 8, 4]))
        for k, r in enumerate(rows[:TOWER_LIVE]):
            d = r['driver']
            at = r['at'] or {}
            on = fol is not None and d is not None and d.id == fol.id
            place = w.running_place(at.get('gap'))
            g = at.get('gap')
            lines.append(box(row(size(box(txt('%d' % place if place else '–', 16, 'bold', WHITE if on else NAVY, j=1),
                                          bg=NAVY if on else 'C9D1E0', al='c', va='c'), w=28, h=26, va='c'),
                                 _slash(WHITE if on else RED, 24, 4),
                                 txt(codes.get(('l', k)) or '???', 19, 'bold', WHITE, va='c', sp=40), sp(fill=1),
                                 txt(_gap_s(g) if g is not None else ('%.1f km' % at['km'] if at.get('km') else ''), 15,
                                     'semi', WHITE if on else (SLOW if (g or 0) > 0 else FAST) if g is not None else SOFT,
                                     va='c', lv=True)),
                             bg=RED if on else NAVY, a=1.0 if on else NA, p=[8, 3, 10, 3]))
        lines.append(size(box(None, bg=RED), h=3))
    return size(col(*lines), w=TOWER_W)


def _bug(w, now, following=True, anyone=True):
    """The LIVE bug top right (STANDBY, grey, with nobody on the stage), and under it the camera on (a moment after
    each cut, or while the menu is open). ACR DAILY's own mark is in the corner, bottom left."""
    if anyone:
        live = box(row(size(box(None, bg=WHITE, r=5), w=10, h=10, va='c'), sp(8),
                       txt(_('LIVE'), 18, 'bold', WHITE, sp=120, va='c')), bg=RED, p=[12, 5, 14, 5])
    else:
        live = box(txt(_('STANDBY'), 18, 'bold', WHITE, sp=120, va='c'), bg=GREY, p=[12, 5, 14, 5])
    if w.kind == 'event':
        ev = w.held()
        what = '%s · SS%d' % (_fit(ev.get('name') or _('EVENT'), 26), w.slot)
    else:
        what = (_('DAILY · SS%d') % w.slot) if w.kind == 'daily' else (_('TIME TRIAL · TT%d') % w.slot)
    name = box(txt(what, 15, 'bold', WHITE, sp=100, va='c'), bg=NAVY, a=NA, p=[12, 6, 14, 6])
    shot = w.shot if w.shot and following else None    # (nobody followed: no camera on anyone)
    show = shot and (now - w.shot_at < SHOT_SHOW_S or w.menu is not None)
    cam_word = watch_mod.CAM_NAMES.get(shot, (shot or '').upper()) if shot else ''
    if w.cam_name() == 'auto' and shot:
        cam_word = _('AUTO · %s') % cam_word
    cam = box(txt(cam_word if show else '', 14, 'bold', WHITE, sp=120), bg=NAVY, a=NA if show else 0.0, lv=True,
              p=[12, 4, 12, 4], al='r')
    return col(row(sp(fill=1), live, name), row(sp(fill=1), cam, pad=[0, 6, 0, 0]), al='r')


def _splits_panel(w, fol, now, leader_name, codes):
    """The followed driver against today's #1 at each split (Rally.TV's head to head): their time there, the #1's,
    the gap; on top, NOW: the gap where they are this moment (it moves as they drive)."""
    if fol is None:
        return None
    sp_rows = w.splits_of(fol, now)
    if not sp_rows or all(s['best'] is None for s in sp_rows):
        return None
    me = codes.get('fol') or ''
    # (both in three letters, as the tower has them: "KOW VS BVR_TAMA64" mixed a code and a name)
    lead = codes.get(('b', 0)) or (leader_name or '').upper()[:3]
    head = box(row(txt(me, 18, 'bold', WHITE, va='c'), sp(8), txt(_('VS'), 13, 'bold', SOFT, va='c'),
                   sp(8), txt(lead, 18, 'bold', WHITE, va='c'), sp(fill=1),
                   txt({'daily': _('TODAY\'S #1'), 'tt': _('THE WEEK\'S #1')}.get(w.kind) or _('#1'), 12, 'bold', SOFT,
                       sp=100, va='c')),
               bg=NAVY2, a=NA, p=[12, 6, 12, 6])
    g_now = (w.where(fol, now) or {}).get('gap')
    now_row = box(row(size(txt(_('NOW'), 15, 'bold', WHITE, va='c'), w=70),
                      txt(_clock(fol.clock_now(now)), 15, 'semi', WHITE, va='c', fill=1),
                      size(box(txt(_gap_s(g_now) if g_now is not None else '', 15, 'bold', WHITE, j=1),
                               bg=(SLOW if (g_now or 0) > 0 else FAST) if g_now is not None else NAVY,
                               a=1.0 if g_now is not None else 0.0, p=[8, 1, 8, 1], lv=True), minw=64)),
                  bg=NAVY3, a=0.95, p=[12, 4, 12, 4])
    lines = [head, now_row, box(row(size(kicker(_('split')), w=70), size(kicker(me), w=88), size(kicker(_('#1')), w=88),
                                    sp(fill=1), kicker(_('gap'))), bg=NAVY, a=NA, p=[12, 4, 12, 2])]
    for k, s in enumerate(sp_rows):
        last = k == len(sp_rows) - 1
        where = _('FINISH') if last else '%.1f km' % s['km']
        g = s['gap']
        lines.append(box(row(size(txt(where, 15, 'semi', SOFT, va='c'), w=70),
                             size(txt(fmt_ms(s['ms'], 1) if s['ms'] is not None else '–', 15, 'semi',
                                      WHITE if s['ms'] is not None else GREY, va='c', lv=True), w=88),
                             size(txt(fmt_ms(s['best'], 1) if s['best'] is not None else '–', 15, 'semi', SOFT, va='c'),
                                  w=88),
                             sp(fill=1),
                             size(box(txt(_gap_s(g) if g is not None else '', 15, 'bold', WHITE, j=1),
                                      bg=(SLOW if (g or 0) > 0 else FAST) if g is not None else NAVY,
                                      a=1.0 if g is not None else 0.0, p=[8, 1, 8, 1], lv=True), minw=64)),
                         bg=NAVY, a=NA, p=[12, 3, 12, 3]))
    return size(col(*lines), w=SPLITS_W)

# ---------------------------------------------------------------------- the gauge, as the WRC broadcast's
# (the user, 22 Nov 2026: "couldn't you make a gauge like in WRC broadcast?", then a WRC TV dash for reference: a round
# dial, the revs in segments round its right, a thin arc on its left, the speed big in the middle over a "Km/h" line,
# under it the maker's badge, two bars and the gear). The dial and every state of its two arcs are pictures drawn once
# (curves the game's flat boxes can't draw); the mod swaps the arcs' pictures in place as they move (lv src), the
# words and bars set in place too.
GD = 300                                   # the dial's size (square)
REV_N, THR_N = 28, 14                      # the revs' segments; the throttle arc's steps
REV_A = (-16.0, 98.0)                      # the revs' arc: from just under the line on the right round to the top (degrees)
THR_A = (214.0, 146.0)                     # the throttle's arc on the left: from low round to up
LINE_Y = 176                               # the Km/h line
BADGE = (82, 226, 58)                      # the maker's badge: its middle (x, y) and size in the dial
BAR_X = 116                                # the brake / throttle bars' left
DIAL_V = 'v5'


def _gauge_dir():
    from . import settings
    return os.path.join(settings.DIR, 'hud', 'app', 'dial-%s' % DIAL_V)


def _arc_points(cx, cy, r, a0, a1):
    import math
    n = max(2, int(abs(a1 - a0) / 2))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy - r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def gauge_pictures():
    """The dial's pictures, drawn once with PIL (3x, then scaled down: smooth edges) -> {'body', 'rev': [path for 0..REV_N
    lit], 'thr': [path for 0..THR_N]}, or None (no PIL)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    import math
    d0 = _gauge_dir()
    out = {'body': os.path.join(d0, 'body.png'), 'rev': [os.path.join(d0, 'rev-%d.png' % k) for k in range(REV_N + 1)],
           'thr': [os.path.join(d0, 'thr-%d.png' % k) for k in range(THR_N + 1)]}
    if all(os.path.exists(p) for p in [out['body']] + out['rev'] + out['thr']):
        return out
    os.makedirs(d0, exist_ok=True)
    s = 3
    W = GD * s
    c = W / 2.0

    def save(im, path):
        im.resize((GD, GD), Image.LANCZOS).save(path + '.tmp', 'PNG')
        os.replace(path + '.tmp', path)
    # the dial: a dark disc, lighter at its middle, its rings, the Km/h line with a gap for the words
    body = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    disc = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    R = c - 2 * s
    for i in range(60, 0, -1):
        k = i / 60.0
        col = (round(14 + 26 * (1 - k)), round(24 + 36 * (1 - k)), round(44 + 52 * (1 - k)), 232)
        dd.ellipse([c - R * k, c - R * k, c + R * k, c + R * k], fill=col)
    body.alpha_composite(disc)
    d = ImageDraw.Draw(body)
    d.ellipse([c - R, c - R, c + R, c + R], outline=(150, 175, 215, 200), width=2 * s)
    r2 = R - 30 * s
    d.ellipse([c - r2, c - r2, c + r2, c + r2], outline=(120, 150, 200, 70), width=s)
    ly = LINE_Y * s
    d.line([(c - R * 0.80, ly), (c - 34 * s, ly)], fill=(225, 232, 245, 230), width=2 * s)
    d.line([(c + 34 * s, ly), (c + R * 0.80, ly)], fill=(225, 232, 245, 230), width=2 * s)
    d.ellipse([c - R * 0.80 - 5 * s, ly - 5 * s, c - R * 0.80 + 5 * s, ly + 5 * s], outline=(225, 232, 245, 230), width=2 * s)
    # the maker's badge ring (BADGE: bigger, the user 22 Nov 2026 "the logos of cars are super small"), the bars' tracks
    bx, by, br = BADGE[0] * s, BADGE[1] * s, (BADGE[2] // 2 + 2) * s
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=(92, 106, 132, 255), outline=(70, 200, 220, 255), width=2 * s)
    for y in (204, 222):
        d.rounded_rectangle([BAR_X * s, y * s, (BAR_X + 82) * s, (y + 10) * s], radius=4 * s, fill=(8, 14, 28, 255),
                            outline=(210, 220, 240, 200), width=s)
    save(body, out['body'])
    # the revs: REV_N segments round the right, lime, the last ones red
    for k in range(REV_N + 1):
        im = Image.new('RGBA', (W, W), (0, 0, 0, 0))
        g = ImageDraw.Draw(im)
        for i in range(REV_N):
            a = math.radians(REV_A[0] + (REV_A[1] - REV_A[0]) * (i + 0.5) / REV_N)
            r_in, r_out = R - 31 * s, R - 6 * s
            half = math.radians((REV_A[1] - REV_A[0]) / REV_N * 0.32)
            pts = [(c + r * math.cos(a + h), c - r * math.sin(a + h)) for r, h in
                   ((r_in, -half), (r_out, -half), (r_out, half), (r_in, half))]
            hot = i >= REV_N - 4
            if i < k:
                fill = (255, 60, 70, 255) if hot else (176, 238, 40, 255)
            else:
                fill = (60, 30, 36, 150) if hot else (40, 60, 40, 130)
            g.polygon(pts, fill=fill)
        save(im, out['rev'][k])
    # the throttle: a thin arc on the left, filled from low up
    for k in range(THR_N + 1):
        im = Image.new('RGBA', (W, W), (0, 0, 0, 0))
        g = ImageDraw.Draw(im)
        r = R - 14 * s
        g.line(_arc_points(c, c, r, THR_A[0], THR_A[1]), fill=(40, 70, 50, 150), width=6 * s, joint='curve')
        if k:
            end = THR_A[0] + (THR_A[1] - THR_A[0]) * k / THR_N
            g.line(_arc_points(c, c, r, THR_A[0], end), fill=(64, 210, 110, 255), width=6 * s, joint='curve')
        save(im, out['thr'][k])
    return out


def _at(x, y, node, w=None, h=None):
    """A node placed at (x, y) in the dial's square (its own size, or w x h)."""
    inner = size(node, w=w, h=h) if (w or h) else node
    return row(sp(w=x), col(sp(h=y), inner, al='l', va='t'), al='l', va='t')


def _dash(dash, car_id=None):
    """The dial (gauge_pictures), the followed car's revs, throttle, speed, brake and gear on it."""
    dash = dash or {}
    pics = gauge_pictures()
    frac = dash.get('rpm_frac')
    gas, brake = dash.get('gas'), dash.get('brake')
    kmh = dash.get('kmh')
    g = dash.get('gear')
    if g is None:
        cur, lo = '–', ''
    else:
        cur = 'R' if g == 0 else ('N' if g == 1 else '%d' % (g - 1))
        lo = '' if g <= 1 else ('N' if g == 2 else '%d' % (g - 2))
    layers = []
    if pics:
        nrev = round(REV_N * max(0.0, min(1.0, frac or 0.0)))
        nthr = round(THR_N * max(0.0, min(1.0, gas or 0.0)))
        layers += [img(pics['body'], GD, GD), img(pics['rev'][nrev], GD, GD, lv=True), img(pics['thr'][nthr], GD, GD, lv=True)]
    else:
        layers.append(box(None, bg=NAVY, a=NA, r=GD // 2))
    layers += [
        _at(50, 74, txt('%d' % round(kmh) if kmh is not None else '–', 66, 'bold', WHITE, j=1), w=200, h=90),
        _at(116, LINE_Y - 11, txt('Km/h', 14, 'bold', WHITE, j=1), w=68, h=22),
        _at(BADGE[0] - BADGE[2] // 2, BADGE[1] - BADGE[2] // 2, _badge(car_id, BADGE[2]) if car_id else sp(),
            w=BADGE[2], h=BADGE[2]),
        _at(BAR_X + 2, 206, row(size(box(None, bg='FF3B47', lv=True),
                                     w=max(1, round(78 * max(0.0, min(1.0, brake or 0.0)))), h=6, lv=True), sp(fill=1)),
            w=78, h=6),
        _at(BAR_X + 2, 224, row(size(box(None, bg='40D26E', lv=True),
                                     w=max(1, round(78 * max(0.0, min(1.0, gas or 0.0)))), h=6, lv=True), sp(fill=1)),
            w=78, h=6),
        _at(202, 196, row(txt(lo, 20, 'bold', GREY, va='b', pad=[0, 0, 6, 8]), txt(cur, 44, 'bold', WHITE, va='b')),
            w=64, h=56),
    ]
    return size(stack(*layers), w=GD, h=GD)

def _stage_line(w, fol, at, splits):
    """The stage across: its splits (km under each), the part driven red, a dot where they are."""
    marks = w.split_marks()
    j = w.judge()
    length_km = (j.route.length / 1000.0) if j is not None and getattr(j, 'route', None) else None
    prog = max(0.0, min(1.0, (at or {}).get('progress') or 0.0))
    done = round(LINE_W * prog)
    line = size(stack(box(None, bg='3A4F78'),
                      row(size(box(None, bg=RED, lv=True), w=done, h=3, lv=True), sp(fill=1))),
                w=LINE_W, h=3)
    ticks, labels, x = [], [], 0
    for k, (idx, km) in enumerate(marks):
        px = round(LINE_W * km / length_km) if length_km else 0
        passed = splits[k]['ms'] is not None if k < len(splits) else False
        ticks.append(sp(max(0, px - x - 5)))
        ticks.append(size(box(None, bg=RED if passed else '8FA0C0', r=4), w=10, h=10, va='c'))
        x = px + 5
        lab = ('%.1f' % km) + (' km' if k == len(marks) - 1 else '')
        labels.append((px, lab))
    dot = row(sp(max(0, done - 7), lv=True), size(box(None, bg=WHITE, r=7, ol=RED, olw=3), w=14, h=14, va='c'))
    lab_row, x = [], 0
    for px, lab in labels:
        lw = 64
        left = max(0, px - lw // 2 - x)
        lab_row.append(sp(left))
        lab_row.append(size(txt(lab, 13, 'semi', SOFT, j=1), w=lw))
        x += left + lw
    return col(size(stack(col(sp(h=6), line, va='c'), row(*ticks), dot), w=LINE_W, h=16),
               row(*lab_row, pad=[0, 4, 0, 0]))


# cars the game has no maker's logo for (seen in the game, 22 Nov 2026): another car of the same maker's, or the
# maker's letters
NO_LOGO = {'LanciaDeltaHFIntegraleEvo': 'LanciaStratosHF', 'LanciaDeltaS4Evo2GroupS': 'LanciaStratosHF',
           'LanciaDeltaS4GroupB': 'LanciaStratosHF', 'LanciaFulviaCoupeHF': 'LanciaStratosHF',
           'Peugeot206WRC': 'Peugeot208Rally4', 'Peugeot306IIMaxi': 'Peugeot208Rally4',
           'AlfaRomeoGiuliaGTAJunior1300': None}
BADGE_BG, BADGE_RING = '5C6A84', 'C9D1E0'   # (slate: the game's logos are white, black and coloured; all read on it)


def _badge(car_id, s):
    """The car maker's logo (the game's own: ue:brand) on a round slate badge: most of the game's logos are white (they
    were lost on the white badge, the user 22 Nov 2026 "barely visible"), some black; every one reads on slate."""
    inner = s - max(6, s // 8)                  # (the logo nearly the badge's size: they were too small, 22 Nov 2026)
    cid = NO_LOGO.get(car_id, car_id)
    if cid:
        face = img('ue:brand:%s' % cid, inner, inner)
    else:                                       # (no logo of its maker in the game: its letters)
        face = txt(''.join(w[0] for w in ('Alfa Romeo' if car_id.startswith('Alfa') else car_id[:2]).split())[:2],
                   max(12, s // 3), 'bold', WHITE, j=1)
    return size(box(face, bg=BADGE_BG, r=s // 2, ol=BADGE_RING, olw=2, al='c', va='c'), w=s, h=s, va='c')


def tag_colours(tag):
    """A team tag's colours: (its own colour, the words' colour: dark on a light one, white on a dark one), as hex."""
    bg = str((tag or {}).get('color') or '3A4F78').lstrip('#')[:6]
    try:
        r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    except (ValueError, IndexError):
        bg, (r, g, b) = '3A4F78', (0x3A, 0x4F, 0x78)
    light = 0.299 * r + 0.587 * g + 0.114 * b > 150
    return bg.upper(), ('0A1428' if light else 'FFFFFF')


def team_text(tag, most=6):
    """A team tag's words as read (its Trackmania $-codes gone: tmtext.py), in capitals."""
    raw = str((tag or {}).get('text') or '')
    try:
        from . import tmtext
        raw = tmtext.plain(raw)
    except Exception:
        pass
    return raw.strip()[:most].upper()


def _fit(name, most=18):
    name = (name or '').upper()
    return name if len(name) <= most else name[:most - 1].rstrip() + '…'


def _driver_bar(w, fol, now, codes, country, team=None, car_id=None):
    at = w.where(fol, now) or {}
    splits = w.splits_of(fol, now)
    g = at.get('gap')
    place = w.running_place(g)
    ch = w.ch() or {}
    top = row(_stage_line(w, fol, at, splits), sp(fill=1),
              txt(stage_name(ch, short=True).upper(), 15, 'bold', WHITE, va='t', sp=60), pad=[16, 10, 16, 0])
    gap_box = box(row(txt(_gap_s(g) if g is not None else '', 22, 'bold', WHITE, va='c'),
                      txt(('  P%d' % place) if place else '', 18, 'bold', WHITE, va='c')),
                  bg=(SLOW if (g or 0) > 0 else FAST) if g is not None else NAVY, a=1.0 if g is not None else 0.0, lv=True,
                  p=[12, 4, 12, 4], va='c')
    # (as the WRC's: the team, the driver, the flag, the maker's badge; the user, 22 Nov 2026 "their TEAM, their
    # NATIONALITY (if set) and the logo of the car")
    team_box = None
    if team and team.get('text'):
        tbg, tfg = tag_colours(team)
        team_box = box(txt(team_text(team), 15, 'bold', tfg, sp=40), bg=tbg, p=[8, 2, 8, 2], va='c',
                       pad=[0, 0, 12, 0])
    name = row(size(box(None, bg=RED), w=10, h=44, sk=-18, va='c'), sp(14), team_box,
               # (a long name smaller, then cut: SARUKAISEKI031 pushed the time off the bar, 22 Nov 2026)
               txt(_fit(fol.name), 30 if len(fol.name or '') <= 12 else 24, 'bold', WHITE, va='c', sp=30),
               sp(14), _flag(country), sp(fill=1),
               _badge(car_id, 56) if car_id else None, sp(12),
               txt((fol.car or '')[:18], 14, 'semi', SOFT, va='c'), sp(14), gap_box, sp(8),
               size(box(txt(_clock(at.get('ms')), 34, 'bold', WHITE, j=1), bg=RED, p=[14, 0, 14, 0], va='c', al='c', sk=-8),
                    w=190, h=50),
               pad=[16, 8, 16, 10])
    bar = box(col(top, name), bg=NAVY, a=NA, r=4)
    # a split just passed: its time a moment over the bar
    pop = None
    for k, s in enumerate(splits):
        if s['ms'] is None:
            continue
        clock = fol.clock_now(now)
        if clock is not None and 0 <= clock - s['ms'] <= SPLIT_SHOW_S * 1000 and s['gap'] is not None:
            last = k == len(splits) - 1
            pop = box(row(txt(_('FINISH') if last else (_('SPLIT %d') % (k + 1)), 17, 'bold', SOFT, sp=100, va='c'), sp(12),
                          txt(fmt_ms(s['ms'], 1), 22, 'bold', WHITE, va='c'), sp(12),
                          box(txt(_gap_s(s['gap']), 20, 'bold', WHITE), bg=SLOW if s['gap'] > 0 else FAST, p=[10, 1, 10, 1],
                              va='c')),
                      bg=NAVY2, a=0.95, p=[14, 6, 10, 6], al='r')
    return size(col(row(sp(fill=1), pop, pad=[0, 0, 0, 6]) if pop else None, bar), w=BAR_W)


def _menu(w, fol):
    """The spectator menu: its lines, the one on lit (Up / Down), each changed with Left / Right."""
    vals = {
        'driver': (_('DRIVER'), (fol.name if fol is not None else '–')),
        'camera': (_('CAMERA'), watch_mod.CAM_NAMES.get(w.cam_name(), w.cam_name().upper())),
        'auto_driver': (_('AUTO DRIVER'), _('ON') if w.auto_driver else _('OFF')),
        'graphics': (_('GRAPHICS'), watch_mod.GRAPHICS_NAMES.get(w.graphics, w.graphics.upper())),
        'splits': (_('SPLITS'), _('ON') if w.splits else _('OFF')),
    }
    close = box(row(txt('✕', 16, 'bold', WHITE, va='c'), sp(6), txt(_('BACK'), 12, 'bold', WHITE, sp=100, va='c')),
                bg='000000', a=0.25, p=[8, 2, 8, 2], r=3, va='c')
    lines = [box(row(txt(_('SPECTATOR'), 20, 'bold', WHITE, sp=120, va='c'), sp(fill=1), close),
                 bg=RED, p=[16, 8, 10, 8])]
    for i, key in enumerate(watch_mod.MENU):
        label, value = vals[key]
        on = i == w.menu
        lines.append(box(row(size(box(None, bg=RED if on else NAVY), w=5, h=30, va='c'), sp(12),
                             txt(label, 16, 'bold', WHITE if on else SOFT, sp=100, va='c', fill=1),
                             txt('‹', 22, 'bold', WHITE if on else GREY, va='c'), sp(10),
                             size(txt(str(value)[:22], 18, 'bold', WHITE, j=1, va='c'), w=170),
                             sp(10), txt('›', 22, 'bold', WHITE if on else GREY, va='c')),
                         bg=NAVY3 if on else NAVY, a=0.95, p=[0, 4, 14, 4]))
    lines.append(box(txt(_('UP / DOWN choose  ·  LEFT / RIGHT change  ·  BACK close'), 13, 'semi', MUTED, j=1),
                     bg=NAVY, a=0.95, p=[12, 8, 12, 8]))
    return size(col(*lines), w=460)


# ---------------------------------------------------------------------- the whole
def overlay(ig):
    """-> the broadcast's tree, or None (not watching)."""
    a = ig.app
    w = getattr(a, 'watch', None)
    if w is None or not w.on:
        return None
    if w.kind == 'event':                        # (an event's stage: WATCH's list, its drivers on this stage)
        from . import ig_watchlist
        ig_watchlist.refresh(ig)
        held = w.held()
        if held:
            m = ig.mem(ig_watchlist.TAB)
            held['live'] = [dict(x, state='live') for x in m.get('events') or []
                            if x.get('eventId') == held.get('eventId') and x.get('stageNo') == w.slot]
            held['live_at'] = m.get('events_at', time.monotonic())
    else:
        from . import ig_daily
        ig_daily.refresh_live(ig, w.kind)        # (the website's list too: the drivers with no car on the relay)
    now = time.monotonic()
    rows = w.rows(now)
    fol = w.followed()
    held = w.held()
    entries = [e for e in (held.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
    # three letters each, the board's first, then those on the stage (a driver on both: the same letters)
    taken, codes, by_name = set(), {}, {}
    for i, e in enumerate(entries[:TOWER_TOP]):
        n = (e.get('name') or '').strip().lower()
        codes[('b', i)] = by_name.get(n) or _code(e.get('name'), taken)
        by_name[n] = codes[('b', i)]
    for k, r in enumerate(rows[:TOWER_LIVE]):
        n = (r['name'] or '').strip().lower()
        codes[('l', k)] = by_name.get(n) or _code(r['name'], taken)
        by_name[n] = codes[('l', k)]
    country, team = None, None
    if fol is not None:
        n = (fol.name or '').strip().lower()
        codes['fol'] = by_name.get(n) or _code(fol.name, taken)
        for e in entries:
            if (e.get('steamId') and e.get('steamId') == getattr(fol, 'sid', None)) or (e.get('name') or '').strip().lower() == n:
                country = e.get('country')
                team = ((e.get('look') or {}).get('tag')) or None
                break
        prof = w.profile(getattr(fol, 'sid', None))      # (their driver page, fetched once: team and flag)
        if prof:
            country = country or prof.get('country')
            team = team or ((prof.get('look') or {}).get('tag')) or None
        if not country:
            for x in held.get('live') or ():
                if (x.get('name') or '').strip().lower() == n:
                    country = x.get('country')
                    break

    g = w.graphics
    menu = _menu(w, fol) if w.menu is not None else None
    if g == 'off':
        return col(sp(fill=1), row(menu, sp(fill=1)) if menu else None)
    full = g == 'full'
    left = _tower(w, rows, fol, now, entries, codes) if full else None
    right = col(_bug(w, now, fol is not None, bool(rows)), sp(h=14),
                _splits_panel(w, fol, now, entries[0].get('name') if entries else '', codes)
                if full and w.splits else None, al='r')
    top = row(left, sp(fill=1), right)
    # bottom left: the spectator menu when open (the user, 21 Nov 2026: "bottom left with a X to close"), and the
    # ACR DAILY mark, as a TV channel's in its corner
    mark = row(img(LOGO, 40, 48, va='c'), sp(10),
               col(txt('ACR DAILY', 22, 'bold', WHITE, sp=60), txt(_('LIVE COVERAGE'), 11, 'bold', SOFT, sp=160)),
               va='b', al='l')
    corner = col(menu, sp(h=14) if menu else None, mark, va='b')
    if fol is not None:
        dash = w and fol.dash_at(now)
        car_id = (w.ch() or {}).get('carId')
        for c in held.get('cars') or ():           # (an event of many cars: the followed one's own)
            if fol.car and (c.get('name') or '').lower() == fol.car.lower():
                car_id = c.get('id') or car_id
        bottom = row(corner, sp(fill=1), _dash(dash, car_id), sp(20), _driver_bar(w, fol, now, codes, country, team, car_id),
                     va='b')
    else:
        waiting = _('Waiting for the next car…') if rows else _('Waiting for a driver on the stage…')
        wait_box = box(row(size(box(None, bg=RED, r=5), w=10, h=10, va='c'), sp(10), txt(waiting, 20, 'semi', WHITE, va='c')),
                       bg=NAVY, a=NA, p=[22, 14, 22, 14], va='b')
        # (in the middle of the screen, the corner beside it not pushing it over)
        bottom = stack(row(corner, sp(fill=1), va='b', al='f'), row(sp(fill=1), wait_box, sp(fill=1), va='b', al='f'))
    return col(top, sp(fill=1), bottom)

def start(ig, kind, slot, prefer=None):
    """WATCH on a daily / a time trial: its stage set up in the game, the game on to the Service Park; at the start line
    the camera goes to the others (watch.py). prefer: the Steam id of the driver to follow first (WATCH's list)."""
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
    a.watch.start(kind, slot, prefer=prefer)

    def ok():
        a.sub_l.configure(text=_('At the Service Park: START STAGE, then you watch from the start line.'))

    def old_way():
        a.watch.stop()
    a.sub_l.configure(text=_('Taking you to %s to watch...') % stage_name(ch))
    a.ingame_drive(setup, ok, 'WATCH', old_way, offer_restart=False)


def event_held(x):
    """An event's stage to watch, from a line of WATCH's list (api.events_live): {'ch', 'judge', 'live', 'board', 'name',
    'eventId', 'kind', 'cars'}, or None (its stage not known well enough to set it up)."""
    st = x.get('stage') or {}
    cars = [c for c in (x.get('cars') or []) if c and c.get('id')] or ([x['car']] if (x.get('car') or {}).get('id') else [])
    if not st.get('stageId') or not cars:
        return None
    no = int(x.get('stageNo') or 1)
    car = cars[0]
    from .rallyweekend import WEATHERS
    if st.get('weatherGame') not in WEATHERS:
        st = dict(st, weatherGame=None)
    if not isinstance(st.get('startSeconds'), (int, float)):
        st = dict(st, startSeconds=None)
    ch = {'id': 'league:%d:%d' % (int(x['eventId']), no - 1), 'track': st.get('track'), 'menuName': st.get('name'),
          'stageId': st['stageId'], 'car': car.get('name'), 'carId': car['id'], 'carAliases': car.get('aliases') or [],
          'route': st.get('route'), 'penaltyMs': 0, 'mode': 'weekend', 'eventId': x['eventId'], 'stageNo': no - 1,
          # (its weather / start time kept from this viewer: the game's own, any, as the car just watches)
          'weatherGame': st.get('weatherGame') or 'WT_CLEAR', 'startSeconds': st.get('startSeconds') or 12 * 3600,
          'weekend': None}           # (the game's default rules: only watching, nothing driven)
    judge = None
    if ch.get('route'):
        try:
            from .judge import Judge
            judge = Judge(ch)
        except Exception:
            judge = None
    return {'ch': ch, 'judge': judge, 'live': [], 'board': None, 'name': x.get('event') or '', 'eventId': x['eventId'],
            'kind': x.get('kind'), 'cars': cars}


def start_event(ig, x):
    """WATCH on an event's stage (a line of WATCH's list), following that driver first."""
    a = ig.app
    from . import ingamedrive, saveslot
    held = event_held(x)
    if held is None:
        ig.say(_('WATCH'), [_("This stage can't be watched from here.")])
        return
    if not ingamedrive.ready(a):
        ig.say(_('WATCH'), [_("Go to the game's main menu first (no rally of yours in progress).")])
        return
    ch = held['ch']
    try:
        setup = ingamedrive.setup_of(ingamedrive.daily_stages(ch), ch['carId'], ch.get('weekend'))
    except (saveslot.SaveError, KeyError, ValueError):
        ig.say(_('WATCH'), [_("This stage can't be watched from here.")])
        return
    a.watch.start('event', int(x.get('stageNo') or 1), event=held, prefer=x.get('steamId'))

    def ok():
        a.sub_l.configure(text=_('At the Service Park: START STAGE, then you watch from the start line.'))

    def old_way():
        a.watch.stop()
    a.sub_l.configure(text=_('Taking you to %s to watch...') % stage_name(ch))
    a.ingame_drive(setup, ok, 'WATCH', old_way, offer_restart=False)
