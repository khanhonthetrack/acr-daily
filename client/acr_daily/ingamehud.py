"""The timer in the game, for VR: what the timer window (app.Overlay) and RANKED's turn window (rankedgate.py) say,
drawn by the game itself through the ACR Daily mod (mod/ACRDailyGhosts/Scripts/hud.lua).

With UEVR the game is in the headset, and its own displays on a plane in front of you; the app's windows over the game
never reach it (a driver in VR, Nov 2026: the runs counted, but no timer). With "Timer in the game" on (SETTINGS ›
Timer), the app writes what its timer says to ingame-hud.txt next to its settings, FEED_S apart (and when it changes),
in rows of coloured text; the mod puts them on the game's screen, so they are in the headset like the game's own. The
same mod as the ghost cars (modinstall.py), installed while either is on.

The file, kept open and overwritten in place (as the ghost cars' file: opening a file just changed costs the game
a few ms each time, mod/README.md):
    ACRHUD 1 <seq> <anchor x> <anchor y> <align x> <align y> <width> <shown 0/1> <panel colour>
    R <seq> <row colour or ->
    S <seq> <colour> <background or -> <size> <b/r>[f] <text>
    end <seq>
(f: the piece takes the row's width left over, and wraps in it: what follows it sits at the right, as a name and its gap
on the timing sheet; a row without one: its last piece without a background.)
"""
import os
import time

FILE = 'ingame-hud.txt'
FEED_S = 0.05                  # how often the app looks (its time runs on in hundredths)
HEARTBEAT_S = 0.5              # written at least this often (the mod hides it after 3 s of nothing new)
WIDTH = 340                    # the panel's width at size 1 (the game's units: 1080p's pixels)
PANEL = '0A0A0BE6'
# where on the game's screen: (anchor x, anchor y, align x, align y): left under the game's own timer, top middle,
# bottom middle (in VR, where it is easiest to glance at depends on how UEVR's plane sits)
PLACES = {'left': (0.015, 0.2, 0.0, 0.0), 'top': (0.5, 0.03, 0.5, 0.0), 'bottom': (0.5, 0.97, 0.5, 1.0)}
QUIET = ('offline', 'standby')     # the timer's states with nothing to show in the game (unless a note or RANKED's turn)
GATE_ROWS = 6


def _c(colour):
    """'#F4F4F5' -> 'F4F4F5'; None / '' -> '-'."""
    c = str(colour or '').lstrip('#')
    return c if len(c) in (6, 8) else '-'


def _t(text):
    return ' '.join(str(text or '').split())


def rows(ov, gate=None, scale=1.0):
    """What the game draws: ov, app.Overlay.snapshot(); gate, rankedgate.TurnWindow.snapshot() (None: not shown).
    -> [(row colour, [(colour, background, size, bold, text[, fill])])], top to bottom; [] when there is nothing to
    show. (fill: see the top.)"""
    k = max(0.6, min(3.0, float(scale or 1.0)))
    z = lambda n: max(8, int(round(n * k)))           # noqa: E731
    out = []
    quiet = (ov or {}).get('status') in QUIET and not (ov or {}).get('alert')
    if ov and not quiet:
        text, fg, bg = ov['badge']
        out.append(('-', [(_c(fg), _c(bg), z(13), True, _t(text)), ('D4D4D8', '-', z(13), False, _t(ov['title']))]))
        t, tc = ov['time']
        row = [(_c(tc), '-', z(36), True, _t(t))]
        if ov.get('pen'):
            row.append(('0A0A0C', 'FF9F0A', z(16), True, _t(ov['pen'])))
        out.append(('-', row))
        if ov.get('line') and _t(ov['line'][0]):
            out.append(('-', [(_c(ov['line'][1]), '-', z(14), False, _t(ov['line'][0]))]))
        a = ov.get('alert')
        if a and _t(a['head']):
            out.append((_c(a['bg']), [(_c(a['head_fg']), '-', z(15), True, _t(a['head']))]))
            for line in a.get('lines') or []:
                out.append((_c(a['bg']), [(_c(a['dot_fg']), '-', z(13), False, '•'), (_c(a['fg']), '-', z(13), False, _t(line))]))
        p = ov.get('panel')
        if p:
            out.append(('-', [('85858E', '-', z(12), False, _t(p['title']), True), ('F4F4F5', '-', z(16), True, _t(p['pos']))]))
            for pos, name, gap, me in p.get('rows') or []:
                fg = 'FF4655' if me else 'D4D4D8'
                out.append(('-', [(fg, '-', z(13), me, _t(pos)), (fg, '-', z(13), me, _t(name), True), (fg, '-', z(13), me, _t(gap))]))
            if p.get('pb') and _t(p['pb'][0]):
                out.append(('-', [(_c(p['pb'][1]), '-', z(12), False, _t(p['pb'][0]))]))
    if gate:
        edge = _c(gate.get('edge'))
        if out:
            out.append(('-', [('2B2B31', '-', z(8), False, ' ')]))           # (a gap between the two)
        out.append(('-', [('A1A1AA', '-', z(12), False, _t(gate.get('kicker')), True), ('F4F4F5', '-', z(12), False, _t(gate.get('stage')))]))
        if gate.get('lit'):
            out.append(('-', [(_c(gate.get('light')), '-', z(24), True, '● ● ● ● ●')]))
        out.append(('-', [(edge, '-', z(28), True, _t(gate.get('head')), True),
                          (edge if gate.get('mode') in ('turn', 'late') else 'F4F4F5', '-', z(30), True, _t(gate.get('big')))]))
        for key, fg in (('line', 'F4F4F5'), ('now', 'D4D4D8')):
            if _t(gate.get(key)):
                out.append(('-', [(fg, '-', z(12), False, _t(gate.get(key)))]))
        for place, name, what, state, mine in (gate.get('rows') or [])[:GATE_ROWS]:
            col = '30D158' if state == 'turn' else 'FFD60A' if state == 'break' else 'D4D4D8'
            out.append(('-', [('F4F4F5' if mine else '85858E', '-', z(12), mine, _t(place)),
                              ('F4F4F5' if mine else 'D4D4D8', '-', z(12), mine, _t(name), True), (col, '-', z(12), False, _t(what))]))
    return out


def encode(seq, place, scale, shown, rows_):
    """The file's text for one update (see the top)."""
    ax, ay, alx, aly = PLACES.get(place) or PLACES['left']
    k = max(0.6, min(3.0, float(scale or 1.0)))
    lines = ['ACRHUD 1 %d %g %g %g %g %d %d %s' % (seq, ax, ay, alx, aly, round(WIDTH * k), 1 if shown and rows_ else 0, PANEL)]
    for bg, segs in rows_:
        lines.append('R %d %s' % (seq, bg))
        for fg, sbg, size, bold, text, *fill in segs:
            lines.append('S %d %s %s %d %s%s %s' % (seq, fg, sbg, size, 'b' if bold else 'r', 'f' if fill and fill[0] else '', text))
    lines.append('end %d' % seq)
    return '\n'.join(lines) + '\n'


class Feed:
    """The file the mod reads, kept open (ghostui.open_kept); written when what it says changes, and at least each
    HEARTBEAT_S (the mod hides it when nothing new comes)."""

    def __init__(self, path, opener=None):
        self.path = path
        self.opener = opener
        self.fh = None
        self.seq = 0
        self.last = None
        self.last_t = -1e9
        self.size = 0

    def write(self, place, scale, shown, rows_, now=None):
        """-> whether it was written."""
        now = time.monotonic() if now is None else now
        key = (place, scale, bool(shown), repr(rows_))
        if key == self.last and now - self.last_t < HEARTBEAT_S:
            return False
        self.seq += 1
        data = encode(self.seq, place, scale, shown, rows_).encode('utf-8')
        if self.fh is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.fh = self.opener(self.path) if self.opener else open(self.path, 'w+b')
        self.fh.seek(0)
        self.fh.write(data + b' ' * max(0, self.size - len(data)))     # (what's left of a longer one: blanked)
        self.fh.flush()
        self.size = len(data)
        self.last, self.last_t = key, now
        return True

    def close(self):
        if self.fh is not None:
            try:
                self.fh.close()
            except OSError:
                pass
        self.fh = None
        self.last = None
