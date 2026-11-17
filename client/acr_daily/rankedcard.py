"""RANKED's cards over everything (liverallyui.py), as iRacing's "your session is ready": a window that takes clicks
(never click-through), always on top of the game, in the look of the next-daily card (nextcard.py):

    RANKED · YOUR RALLY IS READY
    Rally2 · Wales
    SS1 Elatia · SS2 Zeli · SS3 Elatia Reverse · Clear
    Your start  SS1 08:06:30                       4:12
    [ DRIVE ›  sets the game up ]   [ LATER ]
    ████████████████████──────────────────   (the time left to the deadline, running down)

Unlike the next-daily card its time is a real deadline (it doesn't wait while the mouse is on it): the countdown and the
bar follow the clock (fn), and at the deadline it closes. Without one it stays until a button is clicked (START SSn).
"""
import time
import tkinter as tk

from .nextcard import ACC, ACC_TEXT, BG, FG2, FONT, FONT_C, PANEL2, WHITE, NextCard, px
from .widgets import ON_TOP_S, fit_on_screen, keep_on_top
from .i18n import _

STEP_MS = 250
BAR_H = 4
GOOD = '#30D158'


class RankedCard:
    def __init__(self, root, at, kicker, title, lines, label, on_go, countdown=None, deadline=None, later=True,
                 colour=ACC):
        """at: (x, y) of its top-left corner, or None: the middle of the screen; lines: [text] under the title;
        countdown(): -> (words on the left, the time big on the right, its colour), called every STEP_MS; deadline: a
        time.monotonic() it closes at (its bar runs down to it), or None; later: a LATER button (it closes)."""
        self.on_go = on_go
        self.countdown = countdown
        self.deadline = deadline
        self._span = max(1.0, (deadline - time.monotonic())) if deadline else None
        self.win = w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=BG, highlightthickness=2, highlightbackground=colour)
        tk.Frame(w, bg=colour, height=3).pack(fill='x')
        body = tk.Frame(w, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(12, 14))
        tk.Label(body, text=kicker, bg=BG, fg=colour if colour != ACC else ACC_TEXT, font=(FONT_C, 13), anchor='w').pack(anchor='w')
        tk.Label(body, text=title, bg=BG, fg=WHITE, font=(FONT_C, 22), anchor='w').pack(anchor='w', pady=(4, 0))
        for text in lines:
            tk.Label(body, text=text, bg=BG, fg=FG2, font=(FONT, 10), anchor='w', justify='left',
                     wraplength=px(w, 440)).pack(anchor='w', pady=(2, 0))
        self.cd = tk.Frame(body, bg=PANEL2)
        self.cd.pack(fill='x', pady=(12, 0))
        self.cd_words = tk.Label(self.cd, text='', bg=PANEL2, fg=WHITE, font=(FONT_C, 14), anchor='w', padx=10, pady=6)
        self.cd_words.pack(side='left')
        self.cd_time = tk.Label(self.cd, text='', bg=PANEL2, fg=WHITE, font=(FONT_C, 26), anchor='e', padx=10)
        self.cd_time.pack(side='right')
        if countdown is None:
            self.cd.pack_forget()
        row = tk.Frame(body, bg=BG)
        row.pack(fill='x', pady=(12, 0))
        self.go_b = NextCard._button(row, label, self._go, primary=True)
        self.go_b.configure(font=(FONT_C, 14), padx=18, pady=7)
        self.go_b.pack(side='left')
        if later:
            NextCard._button(row, _('LATER'), self.close).pack(side='left', padx=(10, 0))
        self.bar = tk.Canvas(w, height=BAR_H, bg=PANEL2, highlightthickness=0)
        if deadline:
            self.bar.pack(side='bottom', fill='x')
        w.update_idletasks()
        if at is None:                                 # (the middle of the screen it is on)
            at = ((w.winfo_screenwidth() - w.winfo_reqwidth()) // 2, (w.winfo_screenheight() - w.winfo_reqheight()) // 3)
        w.geometry('+%d+%d' % fit_on_screen(at[0], at[1], w.winfo_reqwidth(), w.winfo_reqheight()))
        self.go_b.focus_set()
        self._ticks = 0
        self._tick()

    def _tick(self):
        if not self.alive:
            return
        if self.countdown is not None:
            words, big, fg = self.countdown()
            if self.cd_words.cget('text') != words:
                self.cd_words.configure(text=words)
            if self.cd_time.cget('text') != big or self.cd_time.cget('fg') != fg:
                self.cd_time.configure(text=big, fg=fg)
        if self.deadline:
            left = self.deadline - time.monotonic()
            if left <= 0:
                self.close()
                return
            wd = self.bar.winfo_width()
            self.bar.delete('all')
            self.bar.create_rectangle(0, 0, wd * left / self._span, BAR_H, fill=ACC if left < 60 else GOOD, width=0)
        self._ticks += 1
        if self._ticks % max(1, round(ON_TOP_S * 1000 / STEP_MS)) == 0:
            keep_on_top(self.win)                      # (back over the game if it came over it)
        self.win.after(STEP_MS, self._tick)

    @property
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def _go(self):
        self.close()
        self.on_go()

    def close(self):
        if self.alive:
            self.win.destroy()

