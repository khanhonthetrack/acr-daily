"""The update screen: an app too old for the server (below its MIN_APP_VERSION from MIN_APP_FROM on) updates itself at
once, no click (the user, 26 Nov 2026), and this covers the app meanwhile: ACR DAILY, "Updating to <version>", what it
is doing (downloading, installing) and a bar filling up as the download goes. Drawn inside the app's own window over
everything in it (as whatsnew.py), so nothing under it is clicked half-way through. The app closes when the new one
starts (App._install_update); a failed update takes it away and its message says why (the UPDATE bar stays).
"""
import re
import tkinter as tk

from . import i18n
from .i18n import _

BACK = '#050506'
WHITE, FG2, MUTED, LINE2 = '#F4F4F5', '#A1A1AA', '#6B6B74', '#2B2B31'
ACC = '#E30613'
FONT = i18n.font('Bahnschrift')
BAR_W, BAR_H = 360, 6


def percent(text):
    """'DOWNLOADING 0.2.3  ·  42 %' -> 0.42; None while no share is known (starting, installing)."""
    m = re.search(r'(\d{1,3})\s*%', text or '')
    return max(0, min(100, int(m.group(1)))) / 100.0 if m else None


class UpdateScreen:
    def __init__(self, app, version):
        self.app = app
        root = app.root
        self.f = tk.Frame(root, bg=BACK)
        self.f.place(x=0, y=0, relwidth=1, relheight=1)
        self.f.lift()
        mid = tk.Frame(self.f, bg=BACK)
        mid.place(relx=0.5, rely=0.5, anchor='center')
        tk.Label(mid, text='ACR DAILY', bg=ACC, fg=WHITE, font=(FONT, 20, 'bold'), padx=14, pady=2).pack()
        tk.Label(mid, text=_('Updating to %s') % version, bg=BACK, fg=WHITE, font=(FONT, 18, 'bold')).pack(pady=(22, 4))
        self.what = tk.Label(mid, text='', bg=BACK, fg=FG2, font=(FONT, 11))
        self.what.pack()
        self.bar = tk.Canvas(mid, width=BAR_W, height=BAR_H, bg=LINE2, highlightthickness=0, bd=0)
        self.bar.pack(pady=(18, 10))
        self.fill = self.bar.create_rectangle(0, 0, 0, BAR_H, fill=ACC, width=0)
        self._sweep = 0
        tk.Label(mid, text=_('This version is too old for ACR DAILY: it updates by itself.'), bg=BACK, fg=MUTED,
                 font=(FONT, 10)).pack()

    def set(self, busy):
        """What the app's update says now (App.update_busy)."""
        try:
            self.what.configure(text=busy or '')
            p = percent(busy)
            if p is None:                              # (no share known: a piece going across)
                self._sweep = (self._sweep + 8) % (BAR_W + 80)
                x = self._sweep - 80
                self.bar.coords(self.fill, max(0, x), 0, min(BAR_W, x + 80), BAR_H)
            else:
                self.bar.coords(self.fill, 0, 0, BAR_W * p, BAR_H)
            self.f.lift()
        except tk.TclError:
            pass

    def close(self):
        try:
            self.f.destroy()
        except tk.TclError:
            pass


def show(app, version):
    try:
        app.root.deiconify()                           # (the window up, if the app sat hidden behind the game)
    except Exception:
        pass
    return UpdateScreen(app, version)
