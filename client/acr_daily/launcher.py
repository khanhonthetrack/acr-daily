"""The launcher (0.2): with ACR DAILY inside the game (ingameapp.py), the app's window is only a small one: a picture of
today's rally, who you are (or SIGN IN WITH STEAM), PLAY, WHAT'S NEW and an update when there is one (its settings are in the game's SETTINGS).
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
SIZE = (520, 610)
PIC_H = 198                     # (the ACR DAILY banner, 1640 x 624, at the launcher's width)
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
        # ACR DAILY's banner
        self.cv = tk.Canvas(f, bg=BG, highlightthickness=0, height=PIC_H)
        self.cv.pack(fill='x')
        self.cv.bind('<Configure>', lambda _e: self._draw_picture())
        body = tk.Frame(f, bg=BG)
        body.pack(fill='both', expand=True, padx=28)
        # who you are, or the Steam button
        acct = tk.Frame(body, bg=BG)
        acct.pack(fill='x', pady=(18, 0))
        # (the flag and the team with the name: the user, 22 Nov 2026 "next to the nickname and credits, also show
        # flag and team")
        self.flag = tk.Label(acct, bg=BG, bd=0)             # (packed once known: _show_flag, _show_team)
        self.team = tk.Label(acct, text='', bg=BG, fg=WHITE, font=(cond, 11), padx=6, pady=0)
        self.who = tk.Label(acct, text='', bg=BG, fg=WHITE, font=(cond, 15), anchor='w')
        self.who.pack(side='left')
        self.coins = tk.Label(acct, text='', bg=BG, fg=MUTED, font=(font, 10), anchor='w')
        self.coins.pack(side='left', padx=(10, 0))
        self._flag_key, self._flag_pic = None, None
        self.signin = self._button(acct, _('SIGN IN WITH STEAM'), self.sign_in, primary=True)

        self.play = tk.Label(body, text=_('PLAY'), bg=WHITE, fg=BG, font=(cond, 30), cursor='hand2', pady=14)
        self.play.pack(fill='x', pady=(16, 8))
        self.play.bind('<Button-1>', lambda _e: self.play_click())
        self.play.bind('<Enter>', lambda _e: self.play.configure(bg=ACC, fg=WHITE))
        self.play.bind('<Leave>', lambda _e: self.play.configure(bg=WHITE, fg=BG))
        self.state = tk.Label(body, text='', bg=BG, fg=MUTED, font=(font, 10), wraplength=SIZE[0] - 56, justify='left',
                              anchor='w')
        self.state.pack(fill='x')

        # how to get to it in the game (the user, 22 Nov 2026: the steps, numbered)
        steps = tk.Frame(body, bg=BG)
        steps.pack(fill='x', pady=(14, 0))
        for k, words in enumerate((_('Press PLAY to start the game.'), _('In its main menu, go to MULTIPLAYER.'),
                                   _('Press the ACR DAILY tile.')), start=1):
            line = tk.Frame(steps, bg=BG)
            line.pack(fill='x', pady=(0, 3))
            tk.Label(line, text=str(k), bg=ACC, fg=WHITE, font=(cond, 10), width=2).pack(side='left')
            tk.Label(line, text=words, bg=BG, fg=SOFT, font=(font, 10), anchor='w').pack(side='left', padx=(8, 0))

        low = tk.Frame(f, bg=BG)
        low.pack(side='bottom', fill='x', padx=28, pady=(0, 22))
        self._button(low, _("WHAT'S NEW"), self.whats_new).pack(side='left')
        self.upd = self._button(low, '', self.update, primary=True)

    def _draw_picture(self):
        """ACR DAILY's banner across the top (the user, 22 Nov 2026: "just put the banner of ACR DAILY, your daily
        competitive portal")."""
        cv = self.cv
        w = max(1, cv.winfo_width())
        if self._pic_key != w:
            try:
                import os
                from PIL import Image, ImageTk
                src = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos', 'banner.webp'))
                h = round(src.height * w / src.width)
                self._pic = ImageTk.PhotoImage(src.convert('RGB').resize((w, h), Image.LANCZOS))
                cv.configure(height=h)
                self._pic_key = w
            except Exception:
                self._pic = None
        cv.delete('all')
        if self._pic is not None:
            cv.create_image(0, 0, image=self._pic, anchor='nw')

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
            self._show_flag(drv.get('country'))
            self._show_team((drv.get('look') or {}).get('tag'))
        else:
            self.who.configure(text='')
            self.coins.configure(text='')
            self._show_flag(None)
            self._show_team(None)
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
        a.root.after(EVERY_MS, self._refresh)

    def _show_flag(self, code):
        """The driver's flag before their name (ig_ranked.flag_png: fetched once), none when not set."""
        path = None
        if code:
            try:
                from .ig_ranked import flag_png
                path = flag_png(code)
            except Exception:
                path = None
        if path == self._flag_key:
            return
        self._flag_key = path
        if path:
            try:
                from PIL import Image, ImageTk
                k = self.app.root.winfo_fpixels('1i') / 96
                self._flag_pic = ImageTk.PhotoImage(Image.open(path).convert('RGB').resize((round(27 * k), round(18 * k)),
                                                                                         Image.LANCZOS))
                self.flag.configure(image=self._flag_pic)
                if not self.flag.winfo_ismapped():
                    self.flag.pack(side='left', padx=(0, 8),
                                   before=self.team if self.team.winfo_ismapped() else self.who)
                return
            except Exception:
                self._flag_key = None
        self.flag.configure(image='')
        if self.flag.winfo_ismapped():
            self.flag.pack_forget()

    def _show_team(self, tag):
        """The driver's team tag (its colour behind it) before their name, none when they have no team."""
        text = ''
        if tag and tag.get('text'):
            try:
                from . import tmtext
                text = tmtext.plain(str(tag['text'])).strip()[:8].upper()
            except Exception:
                text = str(tag['text'])[:8].upper()
        if text:
            from .ig_watch import tag_colours
            bg, fg = tag_colours(tag)
            self.team.configure(text=text, bg='#' + bg, fg='#' + fg)   # (white words on a white team: unreadable)
            if not self.team.winfo_ismapped():
                self.team.pack(side='left', padx=(0, 8), before=self.who)
        elif self.team.winfo_ismapped():
            self.team.pack_forget()

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
