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
BAR_W, DASH_W = 860, 380
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
    head = box(row(txt(('SS%d' % w.slot) if w.kind == 'daily' else ('TT%d' % w.slot), 20, 'bold', WHITE, va='c'),
                   _slash(WHITE, 20, 3),
                   txt(name, nsz, 'bold', WHITE, va='c', fill=1)),
               bg=RED, p=[12, 5, 12, 5])
    lines = [head, box(txt(_("TODAY'S BEST") if w.kind == 'daily' else _("THIS WEEK'S BEST"), 13, 'bold', SOFT, sp=140,
                           j=1), bg=NAVY, a=NA, p=[8, 5, 8, 4])]
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
    name = box(txt((_('DAILY · SS%d') % w.slot) if w.kind == 'daily' else (_('TIME TRIAL · TT%d') % w.slot), 15,
                   'bold', WHITE, sp=100, va='c'), bg=NAVY, a=NA, p=[12, 6, 14, 6])
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
                   txt(_('TODAY\'S #1') if w.kind == 'daily' else _('THE WEEK\'S #1'), 12, 'bold', SOFT, sp=100, va='c')),
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
# (the user, 22 Nov 2026: "couldn't you make a gauge like in WRC broadcast?"): a rounded body with a window for the
# speed, the revs along a curve over it (green, then amber, then red), brake (left) and throttle (right) as segments
# along a curve under it, the gear with the ones either side. The body is a picture drawn once (curves and rounded
# frames: the game's flat boxes can't); the segments and words over it are set in place as they move (lv).
GW, GH = 470, 176
REV_N, PED_N = 30, 12
SPEED_BOX = (158, 40, 154, 90)            # x, y, w, h of the speed's window in the body
SLOT_BOX = (44, 56, 60, 56)               # the small square left of it


def _arc_y(x, top, depth, ends_up):
    """A gentle curve across the gauge: y at x (the middle at `top`, the ends `depth` lower, or higher)."""
    u = (x - GW / 2.0) / (GW / 2.0 - 50)
    return top + (-1 if ends_up else 1) * depth * u * u


def gauge_png():
    """The gauge's body, drawn once with PIL (3x, then scaled down: smooth edges) -> its PNG's path, or None."""
    try:
        from PIL import Image, ImageDraw
        from . import settings
    except ImportError:
        return None
    out = os.path.join(settings.DIR, 'hud', 'app', 'wrc-gauge-%dx%d-v2.png' % (GW, GH))
    if os.path.exists(out):
        return out
    s = 3
    W, H = GW * s, GH * s
    grad = Image.new('RGBA', (W, H))
    top, bot = (28, 44, 78), (9, 18, 38)
    for y in range(H):
        k = y / float(H - 1)
        c = tuple(round(top[i] + (bot[i] - top[i]) * k) for i in range(3))
        ImageDraw.Draw(grad).line([(0, y), (W, y)], fill=c + (236,))
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=46 * s, fill=255)
    body = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    body.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(body)
    d.rounded_rectangle([s, s, W - 1 - s, H - 1 - s], radius=45 * s, outline=(92, 116, 160, 210), width=2 * s)
    x, y, w, h = SPEED_BOX
    d.rounded_rectangle([x * s, y * s, (x + w) * s, (y + h) * s], radius=16 * s, fill=(7, 13, 27, 255),
                        outline=(132, 152, 196, 255), width=2 * s)
    x, y, w, h = SLOT_BOX
    d.rounded_rectangle([x * s, y * s, (x + w) * s, (y + h) * s], radius=12 * s, fill=(12, 20, 38, 255),
                        outline=(72, 92, 134, 255), width=2 * s)
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        body.resize((GW, GH), Image.LANCZOS).save(out + '.tmp', 'PNG')
        os.replace(out + '.tmp', out)
        return out
    except OSError:
        return None


def _segments(n, x0, x1, top, depth, ends_up, w, h, colour_of):
    """n segments evenly from x0 to x1 along a curve: a row of columns, each pushed down to its place on it."""
    step = (x1 - x0) / float(n)
    cells = []
    for i in range(n):
        x = x0 + step * i
        y = _arc_y(x + w / 2.0, top, depth, ends_up)
        cells.append(col(sp(h=max(0, round(y))), size(box(None, bg=colour_of(i), lv=True), w=w, h=h),
                         pad=[0 if not cells else round(step - w), 0, 0, 0]))
    return row(*cells, pad=[round(x0), 0, 0, 0], al='l', va='t')


def _dash(dash):
    """The gauge (gauge_png), the followed car's revs, speed, gear and pedals over it."""
    dash = dash or {}
    frac = dash.get('rpm_frac')
    lit = round(REV_N * max(0.0, min(1.0, frac or 0.0))) if frac is not None else 0

    def rev_colour(i):
        if i >= lit:
            return '1E2B46'
        k = i / float(REV_N)
        return GREEN if k < 0.62 else (AMBER if k < 0.85 else RED2)
    revs = _segments(REV_N, 64, GW - 64, 16, 9, False, 8, 5, rev_colour)
    brake, gas = dash.get('brake'), dash.get('gas')
    nb = round(PED_N * max(0.0, min(1.0, brake or 0.0)))
    ng = round(PED_N * max(0.0, min(1.0, gas or 0.0)))
    # (brake: lit from the middle out to the left; throttle: from the middle out to the right)
    brakes = _segments(PED_N, 70, GW / 2.0 - 8, GH - 30, 12, True, 9, 13,
                       lambda i: 'FF2D3A' if i >= PED_N - nb else '3B1A22')
    gases = _segments(PED_N, GW / 2.0 + 8, GW - 70, GH - 30, 12, True, 9, 13,
                      lambda i: '2BD96B' if i < ng else '173A28')
    kmh = dash.get('kmh')
    x, y, w, h = SPEED_BOX
    # (the number in the window's middle, km/h on its floor: a column of both ran out of the window, its words' boxes
    # being taller than they look)
    speed = row(sp(w=x), size(stack(txt('%d' % round(kmh) if kmh is not None else '–', 46, 'bold', WHITE, j=1,
                                        al='c', va='c', pad=[0, 0, 0, 10]),
                                    txt('km/h', 12, 'semi', SOFT, j=1, al='c', va='b', pad=[0, 0, 0, 6])), w=w, h=h),
                pad=[0, y, 0, 0], al='l', va='t')
    sx, sy, sw, sh = SLOT_BOX
    slot = row(sp(w=sx), size(box(img(LOGO, 26, 32), al='c', va='c'), w=sw, h=sh), pad=[0, sy, 0, 0], al='l', va='t')
    g = dash.get('gear')
    if g is None:
        cur, lo, hi = '–', '', ''
    else:
        cur = 'R' if g == 0 else ('N' if g == 1 else '%d' % (g - 1))
        lo = '' if g <= 1 else ('N' if g == 2 else '%d' % (g - 2))
        hi = '' if g == 0 else '%d' % g
    gear = row(sp(w=x + w + 22), size(row(txt(lo, 20, 'semi', GREY, va='c'), sp(10), txt(cur, 46, 'bold', WHITE, va='c'),
                                          sp(10), txt(hi, 20, 'semi', GREY, va='c'), al='c'), w=GW - (x + w + 22) - 30, h=h),
               pad=[0, y, 0, 0], al='l', va='t')
    layers = [img(gauge_png(), GW, GH) if gauge_png() else box(None, bg=NAVY, a=NA, r=24), revs, brakes, gases, slot,
              speed, gear]
    return size(stack(*layers), w=GW, h=GH)

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


def _driver_bar(w, fol, now, codes, country):
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
    name = row(size(box(None, bg=RED), w=10, h=44, sk=-18, va='c'), sp(14),
               txt((fol.name or '').upper(), 30, 'bold', WHITE, va='c', sp=30),
               sp(16), _flag(country), sp(fill=1),
               txt(fol.car or '', 15, 'semi', SOFT, va='c'), sp(16), gap_box, sp(8),
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
    from . import ig_daily
    ig_daily.refresh_live(ig, w.kind)            # (the website's list too: the drivers with no car on the relay)
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
    country = None
    if fol is not None:
        n = (fol.name or '').strip().lower()
        codes['fol'] = by_name.get(n) or _code(fol.name, taken)
        for e in entries:
            if (e.get('steamId') and e.get('steamId') == getattr(fol, 'sid', None)) or (e.get('name') or '').strip().lower() == n:
                country = e.get('country')
                break
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
        bottom = row(corner, sp(fill=1), _dash(dash), sp(24), _driver_bar(w, fol, now, codes, country), va='b')
    else:
        waiting = _('Waiting for the next car…') if rows else _('Waiting for a driver on the stage…')
        wait_box = box(row(size(box(None, bg=RED, r=5), w=10, h=10, va='c'), sp(10), txt(waiting, 20, 'semi', WHITE, va='c')),
                       bg=NAVY, a=NA, p=[22, 14, 22, 14], va='b')
        # (in the middle of the screen, the corner beside it not pushing it over)
        bottom = stack(row(corner, sp(fill=1), va='b', al='f'), row(sp(fill=1), wait_box, sp(fill=1), va='b', al='f'))
    return col(top, sp(fill=1), bottom)

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
