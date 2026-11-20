"""The launcher (0.2, a private build for now): with ACR DAILY inside the game (ingameapp.py), the app's window is only a
small one: a few settings and PLAY. PLAY starts the game (or brings it to the front); ACR DAILY is then a tile on the
game's MULTIPLAYER page. FULL WINDOW (and the in-game pages not moved to the game yet) bring the whole window back.

It sits over the app's window (placed over everything in it) and makes the window small; put away, the window is as it
was."""
import ctypes
import tkinter as tk

from . import ghostui, saveslot
from .i18n import _

BG, PANEL, LINE2 = '#0A0A0B', '#141417', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#85858E'
ACC, GOOD = '#E30613', '#30D158'
SIZE = (460, 560)
EVERY_MS = 1500


class Launcher:
    def __init__(self, app):
        self.app = app
        self.f = None
        self.on = False
        self._geom = None
        self._loop = False            # (its look kept up to date while it is on)

    # ---- on and off
    def show(self):
        a = self.app
        if self.f is None:
            self._build()
        if not self.on:
            self._geom = a.root.geometry()
            self._min = a.root.minsize()
            self._zoomed = a.root.state() == 'zoomed'
        self.on = True
        self.f.place(x=0, y=0, relwidth=1, relheight=1)
        self.f.lift()
        if self._zoomed:
            a.root.state('normal')
        k = a.root.winfo_fpixels('1i') / 96                  # (the screen's scale: 150 % is 1.5)
        w, h = round(SIZE[0] * k), round(SIZE[1] * k)
        a.root.minsize(w, h)
        # (the app puts its saved size back as it starts: the launcher's size set again once that is done)
        for ms in (0, 600, 1500):
            a.root.after(ms, lambda: self.on and a.root.geometry('%dx%d' % (w, h)))
        if not self._loop:
            self._loop = True
            self._refresh()

    def hide(self):
        """The whole window back, its size as it was."""
        if not self.on:
            return
        self.on = False
        self.f.place_forget()
        r = self.app.root
        if getattr(self, '_min', None):
            r.minsize(*self._min)
        if self._geom:
            r.geometry(self._geom)
        if getattr(self, '_zoomed', False):
            r.state('zoomed')

    # ---- the window
    def _build(self):
        a = self.app
        f = self.f = tk.Frame(a.root, bg=BG)
        font, cond = getattr(a, '_font', None), None
        try:
            from . import app as app_mod
            font, cond = app_mod.FONT, app_mod.FONT_C
        except Exception:
            font, cond = 'Segoe UI', 'Segoe UI'
        top = tk.Frame(f, bg=BG)
        top.pack(fill='x', padx=28, pady=(28, 0))
        tk.Label(top, text=' ACR DAILY ', bg=ACC, fg=WHITE, font=(cond, 20)).pack(side='left')
        self.who = tk.Label(top, text='', bg=BG, fg=FG2, font=(font, 10), anchor='e')
        self.who.pack(side='right')

        self.play = tk.Label(f, text=_('PLAY'), bg=WHITE, fg=BG, font=(cond, 30), cursor='hand2', pady=14)
        self.play.pack(fill='x', padx=28, pady=(36, 8))
        self.play.bind('<Button-1>', lambda _e: self.play_click())
        self.play.bind('<Enter>', lambda _e: self.play.configure(bg=ACC, fg=WHITE))
        self.play.bind('<Leave>', lambda _e: self.play.configure(bg=WHITE, fg=BG))
        self.state = tk.Label(f, text='', bg=BG, fg=MUTED, font=(font, 10), wraplength=SIZE[0] - 56, justify='left',
                              anchor='w')
        self.state.pack(fill='x', padx=28)

        tk.Frame(f, bg=LINE2, height=1).pack(fill='x', padx=28, pady=(26, 10))
        tk.Label(f, text=_('SETTINGS'), bg=BG, fg=MUTED, font=(font, 8, 'bold'), anchor='w').pack(fill='x', padx=28)
        self.switches = {}
        for key, label in (('timer', _('Timer in the game')), ('ghosts', _('Ghost cars')),
                           ('auto', _('AUTO: through the game\'s menus after DRIVE'))):
            r = tk.Frame(f, bg=BG, cursor='hand2')
            r.pack(fill='x', padx=28, pady=(8, 0))
            l = tk.Label(r, text=label, bg=BG, fg=SOFT, font=(font, 11), anchor='w', cursor='hand2')
            l.pack(side='left')
            s = tk.Label(r, text='', bg=BG, font=(cond, 11), width=4, cursor='hand2')
            s.pack(side='right')
            for w in (r, l, s):
                w.bind('<Button-1>', lambda _e, k=key: self.toggle(k))
            self.switches[key] = s

        low = tk.Frame(f, bg=BG)
        low.pack(side='bottom', fill='x', padx=28, pady=(0, 22))
        for text, cmd in ((_('ALL SETTINGS'), self.all_settings), (_('FULL WINDOW'), self.hide)):
            b = tk.Label(low, text=text, bg=BG, fg=SOFT, font=(cond, 11), padx=12, pady=4, cursor='hand2',
                         highlightthickness=1, highlightbackground=LINE2)
            b.pack(side='left', padx=(0, 8))
            b.bind('<Button-1>', lambda _e, c=cmd: c())
            b.bind('<Enter>', lambda _e, b=b: b.configure(bg=WHITE, fg=BG))
            b.bind('<Leave>', lambda _e, b=b: b.configure(bg=BG, fg=SOFT))

    def _refresh(self):
        if not self.on or self.f is None:
            self._loop = False
            return
        a = self.app
        try:
            running = saveslot.game_running()
        except Exception:
            running = False
        drv = getattr(a, 'driver', None) or {}
        self.who.configure(text=drv.get('name') or a.s.get('name') or '')
        self.play.configure(text=_('TO THE GAME') if running else _('PLAY'))
        self.state.configure(text=_('The game is running. ACR DAILY is a tile on its MULTIPLAYER page.') if running else
                             _('Starts the game. ACR DAILY is a tile on its MULTIPLAYER page.'))
        o = a.s.get('overlay') or {}
        on = {'timer': o.get('visible', True), 'ghosts': a.ghost_cars_on(), 'auto': bool(a.s.get('autoDrive'))}
        for k, s in self.switches.items():
            s.configure(text=_('ON') if on[k] else _('OFF'), fg=GOOD if on[k] else MUTED)
        a.root.after(EVERY_MS, self._refresh)

    # ---- what it does
    def play_click(self):
        if saveslot.game_running():
            h = ghostui.find_game_window()
            if h:
                try:
                    ctypes.windll.user32.ShowWindow(h, 9)          # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(h)
                except Exception:
                    pass
            return
        saveslot.launch_game()
        self.state.configure(text=_('Starting the game…'))

    def toggle(self, key):
        a = self.app
        if key == 'timer':
            a.toggle_overlay(not (a.s.get('overlay') or {}).get('visible', True))
        elif key == 'ghosts':
            a.toggle_ghosts()
        elif key == 'auto':
            a.toggle_auto_drive()
        self.f.after(50, self._refresh_once)

    def _refresh_once(self):
        o = self.app.s.get('overlay') or {}
        on = {'timer': o.get('visible', True), 'ghosts': self.app.ghost_cars_on(), 'auto': bool(self.app.s.get('autoDrive'))}
        for k, s in self.switches.items():
            s.configure(text=_('ON') if on[k] else _('OFF'), fg=GOOD if on[k] else MUTED)

    def all_settings(self):
        self.hide()
        try:
            self.app.toggle_settings_view(True)
        except Exception:
            pass
