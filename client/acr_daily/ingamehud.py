"""The app's displays drawn inside the game, by the game itself, through the ACR Daily mod
(mod/ACRDailyGhosts/Scripts/hud.lua, with hudkit.lua).

They are the game's own widgets: nothing sits over the game (no window for Windows to compose with it, so FreeSync /
G-SYNC stay on), and in VR (UEVR) they are in the headset like the game's HUD, where the app's windows never are. With
"Displays in the game" on (SETTINGS › Timer) and the mod seen running (ModPulse), the app's windows over the game
stand down and the game draws these instead:

  - the ACR strip, docked under the game's own timer, in its look (a grey label, a dark value): whether the run counts
    (the timer's badge), the place at the last split, and one line (the gap to P1 and which way it goes, or what to
    do). No second race clock: the game's own is right above it (and ours, with the penalties in it, showed a
    different number: a UI review, Nov 2026); a driver who hides the game's HUD can have ours (clock).
  - under it, a note (what must be done now: save your time, this run won't count) and the split's standings: short
    cards that come and go.
  - RANKED's start board (rankedgate.py), top middle under the game's km bar: the series' logo, one word, one
    countdown, whose turn, at most three of the queue.
  - the other drivers on the stage and the ghosts as ticks under the game's km bar (the stage strip, widgets.py).

The app says WHAT is shown (its words, in the app's language, and its colours); the mod decides how it looks. Its
file, kept open and overwritten in place (as the ghost cars' file: opening a file just changed costs the game a few ms
each time, mod/README.md):

    ACRHUD 2 <seq> <when>                 when: this PC's clock (time.monotonic, s) at this update
    <seq> <panel> <key> <value>           one field (value: the rest of the line; a list's cells: tabs)
    end <seq>
A key that comes more than once (row, point, split, other, ghost) is a list, in order. A clock that runs (run, left) is
in ms at <when>: the mod moves it on every frame itself, so it is smooth at any frame rate.
"""
import os
import shutil
import time

FILE = 'ingame-hud.txt'
CAMERA_FILE = 'ingame-camera.txt'     # the mod writes the game's camera here every frame: it is running (ModPulse)
FEED_S = 0.05                  # how often the app looks
HEARTBEAT_S = 0.5              # written at least this often (the mod hides everything after 3 s of nothing new)
ALIVE_S = 2.0                  # the mod's camera file not moving on for this long: the mod is not running
PLACES = ('dock', 'top', 'bottom')   # the ACR strip: under the game's timer, or top / bottom middle (in VR, where it is
                                     # easiest to glance at depends on how UEVR's plane sits)
QUIET = ('offline', 'standby')       # the timer's states with nothing to say in the game (unless a note)
RUNNING = ('live', 'live_off', 'rec')
COUNTS = {'live': 'good', 'rec': 'good', 'ready': 'good', 'finished': 'soft', 'live_off': 'off', 'ready_off': 'off',
          'dnf': 'bad', 'invalid': 'bad'}
GATE_ROWS = 3
GHOSTS = {'p1': '#F4F4F5', 'ahead': '#5BA8FF', 'me': '#B48CFF', 'field': '#A1A1AA'}   # (as the stage strip's: widgets.GHOST)
LOGO_DIR = 'hud'              # next to the settings: the pictures the mod loads (a series' logo), copied there once


def _c(colour):
    """'#F4F4F5' -> 'F4F4F5'; None / '' -> '-'."""
    c = str(colour or '').lstrip('#')
    return c if len(c) in (6, 8) else '-'


def _t(text):
    """One line, no tabs (a value is the rest of its line; tabs part a list's cells)."""
    return ' '.join(str(text if text is not None else '').split())


def cells(*xs):
    return '\t'.join(_t(x) for x in xs)


# ---------------------------------------------------------------------- the displays
def acr(ov, pos=None, clock=False, logo=None):
    """app.Overlay.snapshot() -> the ACR strip: {logo (ACR Daily's, a file), chip, chip_bg, chip_fg, dot (1: a live
    run), kind (good / off / bad / soft: how the run stands), pos, line, line_c[, time, run]}; None: nothing to say
    (waiting for the game)."""
    if not ov or ov.get('status') in QUIET or ov.get('status') in ('wait', 'go', 'break', 'late'):
        return None                                    # (RANKED's own states: on its start board)
    text, fg, bg = ov['badge']
    out = {'chip': _t(text.replace('●', '').replace('○', '')), 'chip_bg': _c(bg), 'chip_fg': _c(fg),
           'dot': 1 if '●' in text or '○' in text else 0, 'kind': COUNTS.get(ov.get('status'), 'soft')}
    if logo:
        out['logo'] = logo
    if pos:
        out['pos'] = _t(pos)
    if ov.get('line') and _t(ov['line'][0]):
        out['line'], out['line_c'] = _t(ov['line'][0]), _c(ov['line'][1])
    if clock:
        t, tc = ov['time']
        out['time'], out['time_c'] = _t(t), _c(tc)
        if ov.get('status') in RUNNING and ov.get('ms') is not None and ov.get('running'):
            out['run'] = int(ov['ms'])                 # (the mod moves it on itself, a frame at a time)
    return out


def note(ov):
    """The timer's alert (save your time, this run won't count...) with its bar -> a note under the strip."""
    a = (ov or {}).get('alert')
    if not a or not _t(a.get('head')):
        return None
    out = {'head': _t(a['head']), 'head_c': _c(a['head_fg']), 'bg': _c(a['bg']), 'fg': _c(a['fg']),
           'dot_c': _c(a['dot_fg']), 'edge': _c(a.get('bar')), 'point': [_t(x) for x in a.get('lines') or [] if _t(x)]}
    prog = (ov or {}).get('progress')
    if prog and (prog[0] == 'wait' or (prog[1] or 0) < 1):      # (a full one says nothing the note doesn't)
        mode, frac, colour = prog
        out['bar'] = 'wait' if mode == 'wait' else '%.4f' % max(0.0, min(1.0, frac or 0.0))
        out['bar_c'] = _c(colour)
    return out


def board(ov):
    """The split's (or the finish's) standings -> a card under the strip."""
    p = (ov or {}).get('panel')
    if not p:
        return None
    out = {'title': _t(p['title']), 'pos': _t(p['pos']),
           'row': [cells(pos, name, gap, 1 if me else 0) for pos, name, gap, me in p.get('rows') or []]}
    if p.get('pb') and _t(p['pb'][0]):
        out['pb'], out['pb_c'] = _t(p['pb'][0]), _c(p['pb'][1])
    return out


def gate(g, logo=None):
    """rankedgate.TurnWindow.snapshot() -> RANKED's start board: the series' logo (a file), one word, the time left
    (left ms, counted down by the mod; span: the whole wait, for its bar), one line, at most GATE_ROWS of the queue
    (the turn, me, the next one), the rule a start on red breaks."""
    if not g:
        return None
    out = {'mode': g.get('mode') or 'wait', 'accent': _c(g.get('edge')), 'series': _t(g.get('series_name') or g.get('kicker')),
           'stage': _t(g.get('stage')), 'head': _t(g.get('head')), 'big': _t(g.get('big')),
           'line': _t(g.get('short') or g.get('line')), 'row': [cells(*r) for r in pick_rows(g.get('rows') or [])]}
    if logo:
        out['logo'] = logo
    if g.get('left') is not None and g.get('big'):
        out['left'] = int(max(0, g['left']))
        out['span'] = int(max(g.get('span') or 0, g['left'], 1))
    if g.get('rule'):
        out['rule'] = _t(g['rule'])
    if g.get('drive'):
        out['drive'] = _t(g.get('drive_words'))
    return out


def pick_rows(rows):
    """The queue's rows the start board shows: the one on turn, mine, and the one after mine (or the next ones), in
    the queue's order -> [(place, name, what, state, 1 / 0)]."""
    if len(rows) <= GATE_ROWS:
        keep = list(range(len(rows)))
    else:
        mine = next((i for i, r in enumerate(rows) if r[4]), None)
        turn = next((i for i, r in enumerate(rows) if r[3] == 'turn'), 0)
        keep = {turn}
        if mine is not None:
            keep |= {mine, mine + 1}
        i = 0
        while len(keep) < GATE_ROWS and i < len(rows):
            keep.add(i)
            i += 1
        keep = sorted(k for k in keep if k < len(rows))[:GATE_ROWS]
    return [(rows[i][0], rows[i][1], rows[i][2], rows[i][3], 1 if rows[i][4] else 0) for i in keep]


def track(v):
    """The stage strip's view (widgets.StageStrip) -> ticks under the game's km bar: the other drivers on the stage now
    (their colour, as the website's), the ghosts, the splits; None when nobody else is on it."""
    if not v or not (v.get('others_prog') or [g for g in v.get('ghosts') or [] if g[2] is not None]):
        return None
    pct = lambda f: '%.4f' % max(0.0, min(1.0, f))                         # noqa: E731
    ghost_c = dict(GHOSTS, **(v.get('ghost_colours') or {}))
    return {'me': '-' if v.get('progress') is None else pct(v['progress']),
            'split': [pct(f) for f in v.get('splits') or []],
            'other': [cells(name, _c(col), pct(prog)) for name, col, prog, *_a in v.get('others_prog') or []],
            'ghost': [cells(label, _c(ghost_c.get(kind) or '#A1A1AA'), pct(prog))
                      for label, kind, prog, *_g in v.get('ghosts') or [] if prog is not None]}


def panels(ov=None, gate_=None, logo=None, view=None, place='dock', scale=1.0, pos=None, clock=False, brand=None):
    """Everything the game draws now: [(panel, fields)], the hud's own first. logo: the series' (the start board);
    brand: ACR Daily's (the strip), both files (logo_file, brand_file)."""
    out = [('hud', {'place': place if place in PLACES else 'dock',
                    'scale': '%.2f' % max(0.6, min(3.0, float(scale or 1.0)))})]
    for name, fields in (('acr', acr(ov, pos, clock, brand)), ('note', note(ov)), ('board', board(ov)),
                         ('gate', gate(gate_, logo)), ('track', track(view))):
        if fields:
            out.append((name, fields))
    return out


def encode(seq, when, panels_):
    """The file's text for one update (see the top)."""
    lines = ['ACRHUD 2 %d %.4f' % (seq, when)]
    for name, fields in panels_:
        lines.append('%d %s on 1' % (seq, name))
        for k, v in fields.items():
            for x in (v if isinstance(v, list) else [v]):        # (one line a value, whatever came: its cells' tabs kept)
                x = ' '.join(x.splitlines()) if isinstance(x, str) else _t(x)
                lines.append('%d %s %s %s' % (seq, name, k, x))
    lines.append('end %d' % seq)
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------- pictures the mod loads
BRAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo-96.png')   # ACR Daily's logo (the app's own)


def brand_file(settings_dir, src=BRAND):
    """ACR Daily's logo, copied where the mod reads it (as logo_file) -> its path, or None."""
    return _copied(src, os.path.join(settings_dir, LOGO_DIR, 'acrdaily-logo.png'))


def logo_file(settings_dir, series_dir, key):
    """A ranked series' logo, copied next to the settings (the mod reads it from there: a one-file app's own files sit
    in a folder that goes when it closes) -> its path, or None."""
    if not key:
        return None
    return _copied(os.path.join(series_dir, key + '-logo.png'), os.path.join(settings_dir, LOGO_DIR, key + '-logo.png'))


def _copied(src, dst):
    """src copied to dst unless it is there already (the same size) -> dst, or None (src missing, or can't write)."""
    dst_dir = os.path.dirname(dst)
    try:
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copyfile(src, dst)
        return dst
    except OSError:
        return None


# ---------------------------------------------------------------------- the file, and is the mod there?
class Feed:
    """The file the mod reads, kept open (ghostui.open_kept); written when what it says changes, and at least each
    HEARTBEAT_S (the mod hides it when nothing new comes). A running clock is in it as ms at <when>; one that only
    runs on is no change (the mod moves it on), so a running timer costs a write each HEARTBEAT_S."""

    def __init__(self, path, opener=None):
        self.path = path
        self.opener = opener
        self.fh = None
        self.seq = 0
        self.last = None
        self.last_t = -1e9
        self.size = 0

    @staticmethod
    def _key(panels_, now):
        """What decides a write: the fields, a running clock taken back to where it stood at 0 (to 40 ms: a jump is a
        change), the words that only count it on left out."""
        out = []
        for name, f in panels_:
            g = dict(f)
            if 'run' in g:
                g['run'] = round(g['run'] - now * 1000) // 40
                g.pop('time', None)
            if 'left' in g:
                g['left'] = round(g['left'] + now * 1000) // 40
                g.pop('big', None)
            out.append((name, repr(sorted(g.items()))))
        return out

    def write(self, panels_, now=None):
        """-> whether it was written."""
        now = time.monotonic() if now is None else now
        key = self._key(panels_, now)
        if key == self.last and now - self.last_t < HEARTBEAT_S:
            return False
        self.seq += 1
        data = encode(self.seq, now, panels_).encode('utf-8')
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


class ModPulse:
    """Is the mod running in the game now? Its camera file (written every frame) moved on in the last ALIVE_S: read
    through a file kept open, at most twice a second."""

    def __init__(self, path, opener=None):
        self.path = path
        self.opener = opener
        self.fh = None
        self.seen = None
        self.moved_at = -1e9
        self.looked_at = -1e9

    def alive(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self.looked_at >= 0.5:
            self.looked_at = now
            try:
                if self.fh is None:
                    self.fh = self.opener(self.path) if self.opener else open(self.path, 'rb')
                self.fh.seek(0)
                head = self.fh.read(40)
                if head and head != self.seen:
                    self.seen, self.moved_at = head, now
            except (OSError, ValueError):
                self.close()
            if self.fh is not None and now - self.moved_at > ALIVE_S:
                self.close()                           # (the mod makes it again on a restart: opened again)
        return now - self.moved_at < ALIVE_S

    def close(self):
        if self.fh is not None:
            try:
                self.fh.close()
            except OSError:
                pass
        self.fh = None
