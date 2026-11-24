"""The window that says what is going on while ACR DAILY closes the game to install community stages and starts it
again (COMMUNITY's CLOSE GAME & INSTALL, INSTALL ALL, a stage's own manager): closing the game, installing (how far),
making the one stage list for every set, starting the game. Up from the moment the game is asked to close until its
window is back (or a while after the start). The user, 24 Nov 2026: "When one restarts the game to install a stage, at
least provide some loading progress window. Otherwise it looks like nothing is happening."

    INSTALLING COMMUNITY STAGES
    London
    Step 2 of 3 · putting it into the game · 64%
    ██████████████████████░░░░░░░░░░░░░
    The game starts again by itself when this is done.
"""
import tkinter as tk

from .i18n import _
from .nextcard import ACC, BG, FG2, FONT, FONT_C, PANEL2, WHITE, px
from .widgets import born, keep_on_top

GAME_BACK_S = 120          # after the start: closed once the game's window is up, at the latest this long after
LOOK_MS = 1000


class InstallProgress:
    def __init__(self, root):
        self.root = root
        self.win = None
        self.frac = None
        self._started_at = None

    @property
    def shown(self):
        try:
            return self.win is not None and bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def _make(self):
        w = self.win = tk.Toplevel(self.root)
        born(w)                                     # (never over the game in front: it is closed by now, normally)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=BG, highlightthickness=1, highlightbackground=ACC)
        tk.Frame(w, bg=ACC, height=3).pack(fill='x')
        body = tk.Frame(w, bg=BG)
        body.pack(fill='both', expand=True, padx=22, pady=(14, 18))
        tk.Label(body, text=_('INSTALLING COMMUNITY STAGES'), bg=BG, fg=FG2, font=(FONT_C, 12), anchor='w').pack(anchor='w')
        self.what_l = tk.Label(body, text='', bg=BG, fg=WHITE, font=(FONT_C, 20), anchor='w')
        self.what_l.pack(anchor='w', pady=(4, 0))
        self.step_l = tk.Label(body, text='', bg=BG, fg=WHITE, font=(FONT, 11), anchor='w', justify='left',
                               wraplength=px(w, 460))
        self.step_l.pack(anchor='w', pady=(8, 6))
        self.bar = tk.Canvas(body, width=px(w, 460), height=px(w, 6), bg=PANEL2, highlightthickness=0)
        self.bar.pack(anchor='w')
        tk.Label(body, text=_('The game starts again by itself when this is done.'), bg=BG, fg=FG2, font=(FONT, 9),
                 anchor='w').pack(anchor='w', pady=(10, 0))
        w.update_idletasks()
        x = (w.winfo_screenwidth() - w.winfo_reqwidth()) // 2
        y = (w.winfo_screenheight() - w.winfo_reqheight()) // 3
        w.geometry('+%d+%d' % (x, y))
        self._tick()

    def show(self, what=None, step=None, frac=None):
        """Up (made if need be), saying `what` (the stages' name), `step` (what is being done) and how far (0..1, or
        None: a bar sweeping: not known)."""
        if not self.shown:
            self._make()
        if what is not None:
            self.what_l.configure(text=what)
        if step is not None:
            self.step_l.configure(text=step)
        self.frac = frac
        self._draw()

    def _draw(self):
        if not self.shown:
            return
        try:
            wd = int(self.bar.cget('width'))
            hd = int(self.bar.cget('height'))
            self.bar.delete('all')
            if self.frac is None:                    # (not known: a block sweeping across)
                import time
                seg = wd * 0.25
                x = (time.monotonic() % 1.6) / 1.6 * (wd + seg) - seg
                self.bar.create_rectangle(x, 0, x + seg, hd, fill=ACC, width=0)
            else:
                self.bar.create_rectangle(0, 0, wd * max(0.0, min(1.0, self.frac)), hd, fill=ACC, width=0)
        except tk.TclError:
            pass

    def _tick(self):
        if not self.shown:
            return
        self._draw()
        keep_on_top(self.win)
        if self._started_at is not None:
            import time
            from .ghostui import find_game_window
            if find_game_window() or time.monotonic() - self._started_at > GAME_BACK_S:
                self.close()
                return
        self.win.after(80 if self.frac is None else LOOK_MS // 4, self._tick)

    def game_starting(self):
        """The game is being started: the window goes once the game's own window is up."""
        import time
        self.show(step=_('Starting Assetto Corsa Rally…'), frac=None)
        self._started_at = time.monotonic()

    def close(self):
        if self.shown:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win, self._started_at = None, None
