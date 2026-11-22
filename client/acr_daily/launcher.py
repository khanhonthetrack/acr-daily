"""The launcher (0.2): with ACR DAILY inside the game (ingameapp.py), the app's window is only a small one: a picture of
today's rally, who you are (or SIGN IN WITH STEAM), PLAY, two switches, WHAT'S NEW and an update when there is one.
PLAY starts the game (or brings it to the front); ACR DAILY is then a tile on the game's MULTIPLAYER page, where all
the rest is (the user, 21 Nov 2026: "minimalistic: sign in, what's new and play, and some small settings").

It sits over the app's window (placed over everything in it) and makes the window small; the in-game pages' few
desktop-only things (a file to pick) put it away for a moment (hide)."""
import ctypes
import tkinter as tk

from . import ghostui, saveslot
from .i18n import _

BG, PANEL, LINE2 = '#0A0A0B', '#141417', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#85858E'
ACC, GOOD = '#E30613', '#30D158'
SIZE = (520, 700)
PIC_H = 240
EVERY_MS = 1500


class Launcher:
    def __init__(self, app):
        self.app = app
        self.f = None
        self.on = False
        self._geom = None
        self._loop = False            # (its look kept up to date while it is on)
        self._pic_key = None
        self._pic = None              # (the PhotoImage kept: Tk drops one nobody holds)

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
        if getattr(a, '_gate', None) is not None:          # (the window's own sign-in screen: the launcher has its own)
            try:
                a._hide_gate()
            except Exception:
                pass
        if self._zoomed:
            a.root.state('normal')
        k = a.root.winfo_fpixels('1i') / 96                  # (the screen's scale: 150 % is 1.5)
        w, h = round(SIZE[0] * k), round(SIZE[1] * k)
        a.root.minsize(w, h)
        # (the app puts its saved size back as it starts: the launcher's size set again once that is done)
        for ms in (0, 600, 1500):
            a.root.after(ms, lambda: self.on and a.root.geometry('%dx%d' % (w, h)))
        a.root.bind('<Return>', lambda _e: self.on and self.play_click())
        if not self._loop:
            self._loop = True
            self._refresh()

    def hide(self):
        """The whole window back, its size as it was (a desktop-only thing from the in-game pages)."""
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
    def _fonts(self):
        try:
            from . import app as app_mod
            return app_mod.FONT, app_mod.FONT_C
        except Exception:
            return 'Segoe UI', 'Segoe UI'

    def _button(self, parent, text, cmd, primary=False, size=11):
        font, cond = self._fonts()
        bg, fg = (WHITE, BG) if primary else (BG, SOFT)
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=(cond, size), padx=14, pady=5, cursor='hand2',
                     highlightthickness=0 if primary else 1, highlightbackground=LINE2)
        b.bind('<Button-1>', lambda _e: cmd())
        b.bind('<Enter>', lambda _e: b.configure(bg=ACC, fg=WHITE))
        b.bind('<Leave>', lambda _e: b.configure(bg=bg, fg=fg))
        return b

    def _build(self):
        a = self.app
        font, cond = self._fonts()
        f = self.f = tk.Frame(a.root, bg=BG)
        # today's rally, the ACR DAILY mark on it, today's stages along its bottom
        self.cv = tk.Canvas(f, bg=BG, highlightthickness=0, height=PIC_H)
        self.cv.pack(fill='x')
        self.cv.bind('<Configure>', lambda _e: self._draw_picture())
        body = tk.Frame(f, bg=BG)
        body.pack(fill='both', expand=True, padx=28)
        # who you are, or the Steam button
        acct = tk.Frame(body, bg=BG)
        acct.pack(fill='x', pady=(18, 0))
        self.who = tk.Label(acct, text='', bg=BG, fg=WHITE, font=(cond, 15), anchor='w')
        self.who.pack(side='left')
        self.coins = tk.Label(acct, text='', bg=BG, fg=MUTED, font=(font, 10), anchor='w')
        self.coins.pack(side='left', padx=(10, 0))
        self.signin = self._button(acct, _('SIGN IN WITH STEAM'), self.sign_in, primary=True)

        self.play = tk.Label(body, text=_('PLAY'), bg=WHITE, fg=BG, font=(cond, 30), cursor='hand2', pady=14)
        self.play.pack(fill='x', pady=(16, 8))
        self.play.bind('<Button-1>', lambda _e: self.play_click())
        self.play.bind('<Enter>', lambda _e: self.play.configure(bg=ACC, fg=WHITE))
        self.play.bind('<Leave>', lambda _e: self.play.configure(bg=WHITE, fg=BG))
        self.state = tk.Label(body, text='', bg=BG, fg=MUTED, font=(font, 10), wraplength=SIZE[0] - 56, justify='left',
                              anchor='w')
        self.state.pack(fill='x')

        tk.Frame(body, bg=LINE2, height=1).pack(fill='x', pady=(18, 4))
        self.switches = {}
        for key, label in (('timer', _('Timer in the game')), ('ghosts', _('Ghost cars'))):
            r = tk.Frame(body, bg=BG, cursor='hand2')
            r.pack(fill='x', pady=(8, 0))
            l = tk.Label(r, text=label, bg=BG, fg=SOFT, font=(font, 11), anchor='w', cursor='hand2')
            l.pack(side='left')
            s = tk.Label(r, text='', bg=BG, font=(cond, 11), width=4, cursor='hand2')
            s.pack(side='right')
            for w in (r, l, s):
                w.bind('<Button-1>', lambda _e, k=key: self.toggle(k))
            self.switches[key] = s
        tk.Label(body, text=_('Everything else is in the game: MULTIPLAYER › ACR DAILY.'), bg=BG, fg=MUTED,
                 font=(font, 9), anchor='w').pack(fill='x', pady=(12, 0))

        low = tk.Frame(f, bg=BG)
        low.pack(side='bottom', fill='x', padx=28, pady=(0, 22))
        self._button(low, _("WHAT'S NEW"), self.whats_new).pack(side='left')
        self.upd = self._button(low, '', self.update, primary=True)

    def _picture_key(self):
        """Today's first daily's rally photo, else any the app has."""
        from . import photos
        a = self.app
        try:
            ch = ((a.dailies or {}).get(1) or {}).get('ch') or {}
            key = photos.for_rally(ch.get('rally'))
        except Exception:
            key = None
        if not key:
            try:
                key = next(iter(photos.meta()), None)
            except Exception:
                key = None
        return key

    def _stages_line(self):
        a = self.app
        try:
            from . import app as app_mod
            parts = []
            for slot in sorted(a.dailies or {}):
                ch = (a.dailies[slot] or {}).get('ch')
                if ch:
                    parts.append('SS%d  %s' % (slot, app_mod.stage_name(ch)))
            return '   ·   '.join(parts)
        except Exception:
            return ''

    def _draw_picture(self):
        font, cond = self._fonts()
        cv = self.cv
        w = max(1, cv.winfo_width())
        key = self._picture_key()
        if key and (key, w) != self._pic_key:
            try:
                from PIL import Image, ImageTk
                from .ingamekit import picture
                path = picture(key, w, PIC_H, fade=True)
                self._pic = ImageTk.PhotoImage(Image.open(path)) if path else None
                self._pic_key = (key, w)
            except Exception:
                self._pic = None
        cv.delete('all')
        if self._pic is not None:
            cv.create_image(0, 0, image=self._pic, anchor='nw')
        cv.create_rectangle(28, 26, 28 + 150, 26 + 40, fill=ACC, outline='')
        cv.create_text(28 + 75, 26 + 20, text='ACR DAILY', fill=WHITE, font=(cond, 20))
        cv.create_text(28, PIC_H - 22, text=self._stages_line(), fill=WHITE, font=(font, 10, 'bold'), anchor='w')

    def _refresh(self):
        if not self.on or self.f is None:
            self._loop = False
            return
        a = self.app
        try:
            running = saveslot.game_running()
        except Exception:
            running = False
        signed = bool(a.s.get('token'))
        if signed:
            self.signin.pack_forget()
            drv = getattr(a, 'driver', None) or {}
            self.who.configure(text=drv.get('name') or a.s.get('name') or '')
            bal = (getattr(a, 'credits', None) or {}).get('balance')
            self.coins.configure(text=(_('%d credits') % bal) if bal is not None else '')
        else:
            self.who.configure(text='')
            self.coins.configure(text='')
            if not self.signin.winfo_ismapped():
                self.signin.pack(side='left')
        self.play.configure(text=_('TO THE GAME') if running else _('PLAY'))
        busy = getattr(a, 'update_busy', '')
        self.state.configure(text=busy or (_('Sign in to use ACR DAILY in the game.') if not signed else ''))
        info = getattr(a, 'update_info', None)
        if info and not busy:
            self.upd.configure(text=_('UPDATE TO %s') % info.get('version', ''))
            if not self.upd.winfo_ismapped():
                self.upd.pack(side='right')
        elif self.upd.winfo_ismapped():
            self.upd.pack_forget()
        self._switches()
        if self._pic_key is None or self._pic_key[0] != self._picture_key():
            self._draw_picture()
        a.root.after(EVERY_MS, self._refresh)

    def _switches(self):
        a = self.app
        o = a.s.get('overlay') or {}
        on = {'timer': o.get('visible', True), 'ghosts': a.ghost_cars_on()}
        for k, s in self.switches.items():
            s.configure(text=_('ON') if on[k] else _('OFF'), fg=GOOD if on[k] else MUTED)

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

    def sign_in(self):
        try:
            self.app.sign_in()
        except Exception:
            pass

    def whats_new(self):
        from . import whatsnew
        whatsnew.reopen(self.app)

    def update(self):
        try:
            self.app.do_update()
        except Exception:
            pass

    def toggle(self, key):
        a = self.app
        if key == 'timer':
            a.toggle_overlay(not (a.s.get('overlay') or {}).get('visible', True))
        elif key == 'ghosts':
            from . import ig_settings                         # (the game's own way: not the old set-up window)
            ig_settings.set_ghosts(a, not a.ghost_cars_on())
        self.f.after(50, self._switches)
