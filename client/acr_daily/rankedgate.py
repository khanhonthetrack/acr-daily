"""RANKED's turn window (liverallyui.py): my place in a ranked rally's queue, over the game, from the moment the rally
is out until I start, and again between stages. It can't be closed (no close button, no LATER: it goes by itself when
I start, and comes back on the break); it can be moved (its place is kept). The series' logo on it (its lights said
nothing the colour didn't: a UI review, Nov 2026); red: WAIT, green: GO, amber: BREAK. With the displays in the game
on and the mod running, the game draws it instead (ingamehud.py) and this window stays put away (show(visible=False)).

    RANKED · RALLY2                                     SS1 · ELATIA
    [ the series' logo ]
    WAIT                                                        1:20
    3 drivers before you: your turn in 1:20 at the latest.
    Turn: Ben · 0:12
    ───────────────────────────────────────────────
    1  Ben                                                      TURN
    2  Ann                                                    ≤ 0:20
    3  YOU                                                    ≤ 0:40
    [ DRIVE › ]                          (the rally out, the app not set up for it yet)

Nothing else on it: the rules are on the RANKED page. What it says comes from liverally.gate (the server's queue, moved on by the clock between two looks).
"""
import time
import tkinter as tk

from .nextcard import BG, FG2, FONT, FONT_C, LINE2, MUTED, SOFT, WHITE, NextCard, px
from .widgets import ON_TOP_S, fit_on_screen, keep_on_top, born, show_window, hide_window
from . import photos
from .i18n import _

RED, GREEN, AMBER, ORANGE = '#FF453A', '#30D158', '#FFD60A', '#FF9F0A'
STEP_MS = 500                  # (keep_on_top's beat)
LOGO = (160, 90)               # the series' logo, at 96 dpi
MODE = {                       # mode -> (its colour, the border and the head's)
    'ready': ('#FF375F', '#FF375F'),
    'wait': (RED, RED),
    'turn': (GREEN, GREEN),
    'break': (AMBER, AMBER),
    'late': (ORANGE, ORANGE),
}


class TurnWindow:
    def __init__(self, root, at=None, on_drive=None, on_moved=None, rows=8):
        """at: (x, y) of its top-left corner (where it was left), or None: the top middle of the screen; on_drive: DRIVE
        (shown in mode 'ready'); on_moved(x, y): it was dragged there."""
        self.on_drive = on_drive
        self.on_moved = on_moved
        self._key = None
        self._ticks = 0
        self.win = w = tk.Toplevel(root)
        born(w)                                        # (never over the game in front filling its screen)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.protocol('WM_DELETE_WINDOW', lambda: None)       # (it can't be closed: it goes when I start)
        w.configure(bg=BG, highlightthickness=2, highlightbackground=RED)
        self.strip = tk.Frame(w, bg=RED, height=4)
        self.strip.pack(fill='x')
        body = self.body = tk.Frame(w, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(10, 12))
        top = tk.Frame(body, bg=BG)
        top.pack(fill='x')
        self.kicker = tk.Label(top, text='', bg=BG, fg=FG2, font=(FONT_C, 12), anchor='w')
        self.kicker.pack(side='left')
        self.stage = tk.Label(top, text='', bg=BG, fg=WHITE, font=(FONT_C, 12), anchor='e')
        self.stage.pack(side='right')
        self.logo = tk.Label(body, bg=BG, bd=0)        # (the series' logo: show(series=...))
        self._logo_of = None
        mid = self.mid = tk.Frame(body, bg=BG)
        mid.pack(fill='x')
        self.head = tk.Label(mid, text='', bg=BG, fg=RED, font=(FONT_C, 30), anchor='w')
        self.head.pack(side='left')
        self.big = tk.Label(mid, text='', bg=BG, fg=WHITE, font=(FONT_C, 34), anchor='e')
        self.big.pack(side='right')
        self.line = tk.Label(body, text='', bg=BG, fg=WHITE, font=(FONT, 11), anchor='w', justify='left',
                             wraplength=px(w, 400))
        self.line.pack(anchor='w', fill='x')
        self.now = tk.Label(body, text='', bg=BG, fg=SOFT, font=(FONT_C, 12), anchor='w')
        self.now.pack(anchor='w', pady=(2, 0))
        tk.Frame(body, bg=LINE2, height=1).pack(fill='x', pady=(8, 4))
        self.grid = tk.Frame(body, bg=BG)
        self.grid.pack(fill='x')
        self.grid.columnconfigure(1, weight=1)
        self.rows = []
        for i in range(rows):
            cells = (tk.Label(self.grid, bg=BG, fg=MUTED, font=(FONT_C, 12), anchor='w', width=3),
                     tk.Label(self.grid, bg=BG, fg=SOFT, font=(FONT_C, 12), anchor='w'),
                     tk.Label(self.grid, bg=BG, fg=SOFT, font=(FONT_C, 12), anchor='e'))
            for c, x in enumerate(cells):
                x.grid(row=i, column=c, sticky='ew')
            self.rows.append(cells)
        self.act = tk.Frame(body, bg=BG)
        self.drive_b = NextCard._button(self.act, _('DRIVE  ›'), self._drive, primary=True)
        self.drive_b.configure(font=(FONT_C, 14), padx=18, pady=6)
        self.drive_b.pack(side='left')
        for x in (w, body, top, mid, self.kicker, self.stage, self.logo, self.head, self.big, self.line, self.now,
                  self.grid) + tuple(c for r in self.rows for c in r):
            x.bind('<ButtonPress-1>', self._press)
            x.bind('<B1-Motion>', self._drag)
            x.bind('<ButtonRelease-1>', self._release)
        self._off = (0, 0)
        w.update_idletasks()
        wd = max(w.winfo_reqwidth(), px(w, 440))
        if at is None:
            at = ((w.winfo_screenwidth() - wd) // 2, px(w, 40))
        w.geometry('+%d+%d' % fit_on_screen(at[0], at[1], wd, w.winfo_reqheight()))
        w.minsize(wd, 1)
        self._tick()

    # ------------------------------------------------------------------ what it says
    def show(self, g, visible=True, series=None):
        """g: liverally.gate's answer. Drawn again only when what it says has changed (its countdowns: each second).
        visible=False: said (snapshot: the game draws it, ingamehud.py), the window itself put away. series: the ranked
        series' key (its logo in the game)."""
        if not self.alive:
            return
        now = time.monotonic()
        mode_was = (getattr(self, '_g', None) or {}).get('mode')
        if g.get('left') is not None:                  # the time left as a moment, so the game counts it down itself
            self._end = now + max(0, g['left']) / 1000
            if g['mode'] != mode_was or (g.get('no'), g['mode']) != getattr(self, '_span_of', None) or \
                    g['left'] > getattr(self, '_span', 0):
                self._span, self._span_of = max(1, g['left']), (g.get('no'), g['mode'])    # (its whole length: the bar)
        else:
            self._end = None
        self._g, self.series, self.active = g, series, True
        if not visible:
            self.hide(keep=True)
            return
        key = (g['mode'], g['kicker'], g['stage'], g['head'], g['big'], g['line'], g['now'], tuple(g['rows']), g['drive'],
               series)
        if self.win.state() == 'withdrawn' and show_window(self.win):   # (never over the game in front filling its screen)
            keep_on_top(self.win)
        if key == self._key:
            return
        self._key = key
        _light, edge = MODE.get(g['mode'], (RED, RED))
        if series != self._logo_of:                    # the series' logo, under its name
            self._logo_of = series
            img = photos.logo(self.win, series, px(self.win, LOGO[0]), px(self.win, LOGO[1])) if series else None
            self.logo.configure(image=img or '')
            self.logo.image = img
            if img and not self.logo.winfo_manager():
                self.logo.pack(anchor='w', pady=(8, 2), before=self.mid)
            elif not img and self.logo.winfo_manager():
                self.logo.pack_forget()
        self.win.configure(highlightbackground=edge)
        self.strip.configure(bg=edge)
        self.kicker.configure(text=g['kicker'])
        self.stage.configure(text=g['stage'])
        self.head.configure(text=g['head'], fg=edge)
        self.big.configure(text=g['big'], fg=edge if g['mode'] in ('turn', 'late') else WHITE)
        self.line.configure(text=g['line'], fg=WHITE if g['mode'] != 'ready' else SOFT)
        self.now.configure(text=g['now'])
        for i, cells in enumerate(self.rows):
            if i >= len(g['rows']):
                for x in cells:
                    x.grid_remove()
                continue
            place, name, what, state, mine = g['rows'][i]
            fg = GREEN if state == 'turn' else (AMBER if state == 'break' else SOFT)
            cells[0].configure(text=place, fg=WHITE if mine else MUTED)
            cells[1].configure(text=_('YOU') if mine else name[:24], fg=WHITE if mine else SOFT,
                               font=(FONT_C, 12, 'bold' if mine else 'normal'))
            cells[2].configure(text=what, fg=fg)
            for x in cells:
                x.grid()
        if g['drive'] and not self.act.winfo_manager():
            self.act.pack(anchor='w', pady=(10, 0))
        elif not g['drive'] and self.act.winfo_manager():
            self.act.pack_forget()


    def snapshot(self):
        """What it says while it has something to say (the displays in the game, ingamehud.py: its window shown or not),
        with its colours, the time left now (left, ms) and the whole wait (span); None when there is nothing."""
        g = getattr(self, '_g', None)
        if not g or not getattr(self, 'active', False) or not self.alive:
            return None
        light, edge = MODE.get(g['mode'], (RED, RED))
        rows = [(place, _('YOU') if mine else name[:24], what, state, mine) for place, name, what, state, mine in g['rows']]
        end = getattr(self, '_end', None)
        left = None if end is None else max(0, round((end - time.monotonic()) * 1000))
        return dict(g, light=light, edge=edge, rows=rows, left=left, span=getattr(self, '_span', None),
                    series=getattr(self, 'series', None), drive_words=_('DRIVE  ›'))

    # ------------------------------------------------------------------ the window
    def hide(self, keep=False):
        """Put away; keep: still said in the game (show(..., visible=False))."""
        if not keep:
            self.active = False
        if self.alive:
            hide_window(self.win)

    def _tick(self):
        if not self.alive:
            return
        self._ticks += 1
        if self._ticks % max(1, round(ON_TOP_S * 1000 / STEP_MS)) == 0 and self.win.state() != 'withdrawn':
            keep_on_top(self.win)                      # (back over the game if it came over it)
        self.win.after(STEP_MS, self._tick)

    def _press(self, e):
        self._off = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag(self, e):
        self.win.geometry('+%d+%d' % (e.x_root - self._off[0], e.y_root - self._off[1]))

    def _release(self, _e):
        if self.on_moved is not None:
            self.on_moved(self.win.winfo_x(), self.win.winfo_y())

    def _drive(self):
        if self.on_drive is not None:
            self.on_drive()

    @property
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    @property
    def shown(self):
        return self.alive and self.win.state() != 'withdrawn'

    def close(self):
        if self.alive:
            self.win.destroy()
