"""After a counted run of one daily: a small card under the timer offering the other daily.

    SS1 FINISHED · P3 today
    Next: SS2 · Cwmbiga - Fedw Fain
    Hyundai i20 N Rally2 · Light fog · Midday (12:00)
    [ DRIVE SS2 ›  restarts the game ]   [ NOT NOW ]          closes in 30 s

Unlike the overlays it takes clicks (it is never click-through). It closes by itself after CLOSE_S seconds (the
countdown waits while the mouse is on it); the app shows it at most once per daily and day, and not at all when the
"Offer the next daily" setting is off.
"""
import tkinter as tk

BG, PANEL2, LINE2 = '#0A0A0B', '#1C1C20', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC, BAD = '#E30613', '#FF453A'
FONT, FONT_C = 'Bahnschrift', 'Bahnschrift SemiBold Condensed'
CLOSE_S = 30


class NextCard:
    def __init__(self, root, at, title, next_line, sub_line, drive_label, on_drive, title_fg=WHITE):
        """at: (x, y) of the card's top-left corner on screen; on_drive: called when DRIVE is clicked."""
        self.on_drive = on_drive
        self.left = CLOSE_S
        self.hover = False
        self.win = w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=BG, highlightthickness=1, highlightbackground=ACC)
        tk.Frame(w, bg=ACC, height=2).pack(fill='x')
        body = tk.Frame(w, bg=BG)
        body.pack(fill='both', expand=True, padx=14, pady=(8, 12))
        tk.Label(body, text=title, bg=BG, fg=title_fg, font=(FONT_C, 13), anchor='w').pack(anchor='w')
        tk.Label(body, text=next_line, bg=BG, fg=WHITE, font=(FONT_C, 17), anchor='w').pack(anchor='w', pady=(6, 0))
        tk.Label(body, text=sub_line, bg=BG, fg=FG2, font=(FONT, 9), anchor='w').pack(anchor='w')
        row = tk.Frame(body, bg=BG)
        row.pack(fill='x', pady=(10, 0))
        self.drive_b = self._button(row, drive_label, self._drive, primary=True)
        self.drive_b.pack(side='left')
        self._button(row, 'NOT NOW', self.close).pack(side='left', padx=(8, 0))
        self.count = tk.Label(row, text='', bg=BG, fg=MUTED, font=(FONT, 8))
        self.count.pack(side='right')
        w.bind('<Enter>', lambda _e: setattr(self, 'hover', True))
        w.bind('<Leave>', lambda _e: setattr(self, 'hover', False))
        w.update_idletasks()
        w.geometry('+%d+%d' % at)
        self._tick()

    @staticmethod
    def _button(parent, text, cmd, primary=False):
        b = tk.Label(parent, text=text, font=(FONT_C, 11), padx=12, pady=4, cursor='hand2',
                     bg=ACC if primary else BG, fg=WHITE if primary else SOFT,
                     highlightthickness=0 if primary else 1, highlightbackground=LINE2)
        b.bind('<Button-1>', lambda _e: cmd())
        b.bind('<Enter>', lambda _e: b.configure(bg=WHITE, fg=BG))
        b.bind('<Leave>', lambda _e: b.configure(bg=ACC if primary else BG, fg=WHITE if primary else SOFT))
        return b

    def _tick(self):
        if not self.alive:
            return
        if not self.hover:
            self.left -= 1
        if self.left <= 0:
            self.close()
            return
        self.count.configure(text='closes in %d s' % self.left)
        self.win.attributes('-topmost', True)
        self.win.after(1000, self._tick)

    @property
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def _drive(self):
        self.close()
        self.on_drive()

    def close(self):
        if self.alive:
            self.win.destroy()
