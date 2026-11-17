"""RANKED's turn window (liverallyui.py): my place in a ranked rally's queue, over the game, from the moment the rally
is out until I start, and again between stages. It can't be closed (no close button, no LATER: it goes by itself when
I start, and comes back on the break); it can be moved (its place is kept). As a real rally's start, lights:

    RANKED · RALLY2                                     SS1 · ELATIA
    ( ● )( ● )( ● )( ● )( ● )          red: WAIT · green: GO ("It is your turn. You have 20 seconds") · amber: BREAK
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
import tkinter as tk

from .nextcard import BG, FG2, FONT, FONT_C, LINE2, MUTED, PANEL2, SOFT, WHITE, NextCard, px
from .widgets import ON_TOP_S, fit_on_screen, keep_on_top
from .i18n import _

RED, GREEN, AMBER, ORANGE = '#FF453A', '#30D158', '#FFD60A', '#FF9F0A'
DARK = '#2A1214'               # a light that is off
LIGHTS = 5
STEP_MS = 500                  # (keep_on_top's beat)
MODE = {                       # mode -> (lights' colour, the border and the head's)
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
        d = px(w, 34)
        self._d = d
        self.lights = tk.Canvas(body, height=d + 8, width=LIGHTS * (d + 10), bg=BG, highlightthickness=0)
        self.lights.pack(anchor='w', pady=(8, 2))
        mid = tk.Frame(body, bg=BG)
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
        for x in (w, body, top, mid, self.kicker, self.stage, self.lights, self.head, self.big, self.line, self.now,
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
    def show(self, g):
        """g: liverally.gate's answer. Drawn again only when what it says has changed (its countdowns: each second)."""
        if not self.alive:
            return
        key = (g['mode'], g['kicker'], g['stage'], g['head'], g['big'], g['line'], g['now'], tuple(g['rows']), g['drive'])
        if self.win.state() == 'withdrawn':
            self.win.deiconify()
            keep_on_top(self.win)
        if key == self._key:
            return
        mode_was = self._key[0] if self._key else None
        self._key = key
        light, edge = MODE.get(g['mode'], (RED, RED))
        self.win.configure(highlightbackground=edge)
        self.strip.configure(bg=edge)
        self.kicker.configure(text=g['kicker'])
        self.stage.configure(text=g['stage'])
        self.head.configure(text=g['head'], fg=edge)
        self.big.configure(text=g['big'], fg=edge if g['mode'] in ('turn', 'late') else WHITE)
        self.line.configure(text=g['line'], fg=WHITE if g['mode'] != 'ready' else SOFT)
        self.now.configure(text=g['now'])
        if mode_was != g['mode']:
            self._lights(light, g['mode'])
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

    def _lights(self, colour, mode):
        c, d = self.lights, self._d
        c.delete('all')
        lit = LIGHTS if mode in ('wait', 'turn', 'break', 'late') else 0
        for i in range(LIGHTS):
            x = 4 + i * (d + 10)
            c.create_oval(x, 4, x + d, 4 + d, fill=colour if i < lit else DARK, outline=PANEL2, width=2)

    # ------------------------------------------------------------------ the window
    def hide(self):
        if self.alive and self.win.state() != 'withdrawn':
            self.win.withdraw()

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
