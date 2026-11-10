"""The app's SETTINGS tab, mixed into App (app.py) like the views it sits beside (inboxui.py, leagueui.py, ttui.py): every
setting in one place, in panels as RaceRoom's options, in the view's place (its cards and the timing sheet) while open.

    DRIVE              AUTO: through the game's menus after every DRIVE (autodrive.py)
    TIMER              shown or not, move / lock (click-through), its size, only on a stage
    IN-GAME DISPLAYS   the stage strip, the delta trend (widgets.py); ghost cars (a test: ghostui.py, modinstall.py)
    ACCOUNT            the Steam account the runs go under: sign in / out
    GAME SAVE          put back the save from before the last set-up (saveslot.py)
    ABOUT              the version, the guide, the website, Discord, the photos' credits
    ADMIN              (admins only) record a route, upload it

The tab is a block at the right of the header (RaceRoom's options are there too), solid white while open. The controls
are built once; the settings they show are read again whenever one changes (_overlay_buttons, _widget_buttons,
_account_ui in app.py).
"""
import tkinter as tk

from . import __version__, tiles, widgets

TEXT_W = 300       # a setting's words, wrapped (at 96 dpi) until its row knows its width


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


class SettingsUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    settings_view = False
    settings_box = None
    _settings_hid = ()
    _switches = ()                 # (canvas, setting's getter) of each switch on the page

    # -------------------------------------------------------------- the tab
    def _build_settings_button(self, parent):
        """The settings: a gear among the header's icons (RaceRoom's OPTIONS), white on white while open."""
        c = _c()
        f = tk.Frame(parent, bg=c.BG)
        f.pack(side='right', padx=(2, 0))
        top = self._settings_top = tk.Frame(f, bg=c.BG, cursor='hand2')
        top.pack(fill='both', expand=True)
        self.settings_l = tk.Label(top, text='', bg=c.BG, fg=c.SOFT, font=(c.FONT_C, 10), padx=8, pady=7, cursor='hand2')
        self.settings_l.pack()
        self.settings_u = tk.Frame(f, bg=c.BG, height=2)     # the underline while open
        self.settings_u.pack(fill='x')
        for w in (f, top, self.settings_l):
            w.bind('<Button-1>', lambda _e: self.toggle_settings_view())
            w.bind('<Enter>', lambda _e: self._settings_badge(hover=True), add='+')
            w.bind('<Leave>', lambda _e: self._settings_badge(), add='+')
        if hasattr(self, '_tip'):
            self._tip(self.settings_l, 'Settings')
        self._settings_badge()

    def _settings_badge(self, hover=False):
        """The gear: on a white square while open, grey otherwise (white on a lighter square under the mouse)."""
        top = getattr(self, '_settings_top', None)
        if top is None:
            return
        from . import icons
        c = _c()
        on = self.settings_view
        bg = c.WHITE if on else c.PANEL2 if hover else c.BG
        fg = c.BG if on else c.WHITE if hover else c.SOFT
        for w in (top, self.settings_l):
            w.configure(bg=bg)
        img = icons.get(self.settings_l, 'settings', 18, fg)
        self.settings_l.configure(image=img or '', text='' if img else 'SETTINGS', fg=fg)
        self.settings_u.configure(bg=c.WHITE if on else c.BG)

    # -------------------------------------------------------------- opening and closing it
    def _view_box(self):
        """The cards of the view under the page: the events (LEAGUES, 1V1, CUPS), the time trial, or the dailies."""
        return self.league_box if self.league_view else self.tt_box if self.tt_view else self.daily_box

    def toggle_settings_view(self, on=None):
        """The page on (in the place of the view's cards and the timing sheet, or of the inbox) or off (the view back)."""
        on = (not self.settings_view) if on is None else on
        if on == self.settings_view:
            return
        if not on:
            self._settings_leave()
            self._view_box().pack(fill='x', before=self._view_end)
            self._render_strip()
            return
        self._pages_leave()                          # (HOME, the inbox or the driver page give way: app.py)
        self.settings_view = True
        self._settings_hid = self._page_show(self.settings_box)
        self._mark_tabs()                            # (SETTINGS solid white, no other tab: tabsui.py)
        self._overlay_buttons()
        self._account_ui()

    def _settings_leave(self):
        """The page closes: the timing sheet comes back (the cards are the caller's: the view clicked)."""
        if not self.settings_view:
            return
        self.settings_view = False
        self._page_hide(self.settings_box, self._settings_hid)
        self._settings_hid = ()
        self._mark_tabs()

    # -------------------------------------------------------------- the page
    def _settings_layout(self):
        """(app.py _layout, and as the page is built) Its two columns side by side, or one under the other (a narrow
        window)."""
        cols = getattr(self, '_set_cols', None)
        if not cols:
            return
        left, right = cols
        if getattr(self, 'layout_stack', False):
            left.grid(row=0, column=0, columnspan=2, sticky='new', padx=20)
            right.grid(row=1, column=0, columnspan=2, sticky='new', padx=20)
        else:
            left.grid(row=0, column=0, columnspan=1, sticky='new', padx=(20, 6))
            right.grid(row=0, column=1, columnspan=1, sticky='new', padx=(6, 20))

    def _build_settings_box(self):
        """The page, built once (two columns of panels); shown by toggle_settings_view."""
        c = _c()
        self.settings_box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)
        scroll = tiles.ScrollArea(self.settings_box, c.BG)   # (taller than the window, one column on a narrow one: it scrolls)
        scroll.outer.pack(fill='both', expand=True)
        box = scroll.inner
        self._switches = []
        k = self.root.winfo_fpixels('1i') / 96
        self._text_w = round(TEXT_W * k)
        for col in (0, 1):
            box.columnconfigure(col, weight=1, uniform='settings')
        left, right = tk.Frame(box, bg=c.BG), tk.Frame(box, bg=c.BG)
        self._set_cols = (left, right)
        self._settings_layout()                     # (side by side; a narrow window: one under the other)
        o = self.s.setdefault('overlay', {})

        p = self._set_panel(left, 'Drive')
        self._set_row(p, 'Auto-drive', 'After every DRIVE (dailies, leagues, 1V1s, cups) the app goes on through the game\'s '
                      'menus to the Service Park; you press START STAGE. Touch the keyboard or mouse to take over.',
                      lambda r: self._build_auto_switch(r, bg=c.PANEL))

        p = self._set_panel(left, 'Timer')
        self._set_row(p, 'Show the timer', 'The app\'s timer over the game\'s own, with the split standings under it.',
                      lambda r: self._switch(r, lambda: bool(o.get('visible', True)),
                                             lambda: self.toggle_overlay(not o.get('visible', True))))
        self._set_row(p, 'Move the overlays', 'Unlocked, drag the timer (over the game\'s timer) and the displays where you '
                      'want them, then lock them: locked, clicks go through to the game.', self._lock_button)
        self._set_row(p, 'Size', 'How big the timer is (a right-click on it does the same).', self._size_buttons)
        self._set_row(p, 'Only on a stage', 'The timer and the displays show only while a daily\'s, an event\'s or a time trial '
                      'stage is loaded in the game (always while you move them).',
                      lambda r: self._switch(r, lambda: bool(o.get('onlyOnDaily', True)), lambda: self.toggle_only_daily()))

        p = self._set_panel(right, 'In-game displays')
        words = {'strip': 'The stage from the start (bottom) to the finish (top): your car, the ghosts and the drivers on it '
                          'right now.',
                 'delta': 'Your gap to P1, and whether you are gaining or losing over the last 10 s.'}
        for key in widgets.CLASSES:
            self._set_row(p, widgets.LABELS[key], words.get(key, ''),
                          lambda r, key=key: self._switch(r, lambda: self._widget_on(key), lambda: self.toggle_widget(key)))
        self._set_row(p, 'Ghost cars (test)', 'The drivers on your stage right now, as cars in the game. On, the app adds '
                      'the game mod they need (UE4SS) to the game\'s folder; off, it takes it out.', self._ghost_controls)

        p = self._set_panel(right, 'Account')
        row = self._set_row(p, '', 'Your runs go on the boards under the Steam account signed in here.',
                            lambda r: self._btn(r, 'SIGN OUT', lambda: self.login_click(), surface=c.PANEL))
        self.set_acct_l, self.set_acct_b = row

        p = self._set_panel(right, 'Game save')
        self._set_row(p, 'Restore the save', 'DRIVE keeps a backup of the game\'s save before each set-up: this puts back the '
                      'one from before the last.', lambda r: self._btn(r, 'RESTORE', lambda: self.restore_click(), surface=c.PANEL))

        p = self._set_panel(right, 'About')
        self._set_row(p, 'ACR Daily %s (beta)' % __version__, 'Two daily stages, random cars and one leaderboard for Assetto '
                      'Corsa Rally. Open source (MIT licence).', None)
        lr = tk.Frame(p, bg=c.PANEL)
        lr.pack(fill='x', padx=14, pady=(0, 12))
        for text, cmd in (('How to play ›', self.open_guide), ('Website ›', self.open_site), ('Discord ›', self.open_discord),
                          ('Photo credits ›', self.show_credits)):
            ln = self._link(lr, text, cmd)
            ln.configure(bg=c.PANEL)
            ln.pack(side='left', padx=(0, 16))
        self._lbl(p, 'A fan project, not affiliated with the makers of Assetto Corsa Rally. Photos: Wikimedia Commons '
                  '(CC BY, CC0, public domain). Icons: Lucide (ISC licence).', fg=c.MUTED,
                  font=(c.FONT, 8), bg=c.PANEL, wraplength=self._text_w).pack(anchor='w', padx=14, pady=(0, 12))


        if self.s.get('admin'):                      # recording a stage's route by hand (admin.py uploads them too)
            p = self._set_panel(right, 'Admin')
            r = tk.Frame(p, bg=c.PANEL)
            r.pack(fill='x', padx=14, pady=(0, 12))
            self._btn(r, 'RECORD ROUTE', self.record_click, surface=c.PANEL).pack(side='left')
            self._btn(r, 'UPLOAD ROUTE', self.upload_click, surface=c.PANEL).pack(side='left', padx=(8, 0))
            self.adm_l = self._lbl(p, 'Admin', fg=c.MUTED, font=(c.FONT, 8), bg=c.PANEL, wraplength=self._text_w)
            self.adm_l.pack(anchor='w', padx=14, pady=(0, 12))
        self._overlay_buttons()                      # (each control as its setting is)
        self._account_ui()

    def show_credits(self):
        """Who took the photos behind the cards (photos.py) and under which licence, each linked to its page."""
        from . import photos
        c = _c()
        w = tk.Toplevel(self.root, bg=c.BG)
        w.title('Photo credits')
        w.transient(self.root)
        self._lbl(w, 'PHOTO CREDITS', fg=c.WHITE, font=(c.FONT_C, 14)).pack(anchor='w', padx=20, pady=(16, 8))
        for what, title, author, licence, url in photos.credits():
            row = tk.Frame(w, bg=c.BG)
            row.pack(fill='x', padx=20, pady=(0, 6))
            self._lbl(row, what.replace('-', ' ').upper(), fg=c.FG2, font=(c.FONT_C, 10), width=12).pack(side='left', anchor='n')
            text = '%s · %s · %s' % (title.rsplit('.', 1)[0] if title.lower().endswith('.jpg') else title, author, licence)
            self._link(row, text + '  ›', lambda u=url: c.webbrowser.open(u) if u else None).pack(side='left', anchor='w')
        self._lbl(w, 'Cut to size and darkened for the words on them.', fg=c.MUTED, font=(c.FONT, 8)).pack(
            anchor='w', padx=20, pady=(6, 16))
        self._btn(w, 'CLOSE', w.destroy).pack(anchor='e', padx=20, pady=(0, 16))

    def _set_panel(self, col, title):
        """A panel of the page: its title spaced out, a hairline after it (as the status box)."""
        c = _c()
        p = tk.Frame(col, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
        p.pack(fill='x', pady=(0, 10))
        head = tk.Frame(p, bg=c.PANEL)
        head.pack(fill='x', padx=14, pady=(12, 4))
        self._k(head, title, bg=c.PANEL).pack(side='left')
        tk.Frame(head, bg=c.LINE2, height=1).pack(side='left', fill='x', expand=True, padx=(10, 0))
        return p

    def _set_row(self, panel, title, text, control):
        """A setting: its name and what it does on the left, its control (control(parent) makes it) on the right.
        -> (the name's label, the control)."""
        c = _c()
        row = tk.Frame(panel, bg=c.PANEL)
        row.pack(fill='x', padx=14, pady=(6, 8))
        made = control(row) if control else None
        if isinstance(made, tk.Widget) and not made.winfo_manager():
            made.pack(side='right', anchor='n', pady=(2, 0))
        body = tk.Frame(row, bg=c.PANEL)
        body.pack(side='left', fill='x', expand=True)
        name = self._lbl(body, title, font=(c.FONT_C, 13), fg=c.WHITE, bg=c.PANEL)
        name.pack(anchor='w')
        if text:
            words = self._lbl(body, text, font=(c.FONT, 9), fg=c.FG2, bg=c.PANEL, wraplength=self._text_w)
            words.pack(anchor='w', pady=(1, 0))
            # wrapped in the room its control leaves (a wide button: fewer words a line)
            room = lambda e: words.configure(wraplength=max(120, e.width - (made.winfo_reqwidth() + 16 if made else 6)))
            row.bind('<Configure>', room)
        return name, made

    def _lock_button(self, parent):
        self.lock_b = self._btn(parent, '', lambda: self.set_locked(not self.s['overlay'].get('locked')), surface=_c().PANEL)
        return self.lock_b

    def _size_buttons(self, parent):
        """− 100 % +: the timer's size, as its right-click menu's Bigger / Smaller."""
        c = _c()
        f = tk.Frame(parent, bg=c.PANEL)
        self._btn(f, '−', lambda: self.overlay.resize(1 / 1.15), surface=c.PANEL).pack(side='left')
        self.size_l = tk.Label(f, text='', bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, 12), width=6)
        self.size_l.pack(side='left')
        self._btn(f, '+', lambda: self.overlay.resize(1.15), surface=c.PANEL).pack(side='left')
        return f

    def _ghost_controls(self, parent):
        """Ghost cars (ghostui.py): its set-up, and on / off."""
        c = _c()
        f = tk.Frame(parent, bg=c.PANEL)
        self._switch(f, self.ghost_cars_on, self.toggle_ghosts).pack(side='right', anchor='n', pady=(2, 0))
        self._btn(f, 'SET UP', self.open_ghost_setup, surface=c.PANEL).pack(side='right', anchor='n', padx=(0, 10))
        return f

    def _widget_on(self, key):
        """Is that display on (its window's setting, or the saved one before the windows are made)?"""
        ws = getattr(self, 'widgets', None)
        if ws and key in ws:
            return bool(ws[key].cfg.get('visible'))
        return bool(((self.s.get('widgets') or {}).get(key) or {}).get('visible'))

    # -------------------------------------------------------------- switches
    def _switch(self, parent, get, toggle):
        """A switch as AUTO's (app.py _draw_switch): red with the knob on the right while get() is true; a click
        toggles it and the knob slides across."""
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        w, h = round(c.App.AUTO_SW[0] * k), round(c.App.AUTO_SW[1] * k)
        cv = tk.Canvas(parent, width=w, height=h, bg=parent.cget('bg'), highlightthickness=0, cursor='hand2')

        def click(_e):
            toggle()
            self._slide_switch(cv, get())
        cv.bind('<Button-1>', click)
        cv.bind('<Enter>', lambda _e: self._draw_switch(cv, get(), hover=True))
        cv.bind('<Leave>', lambda _e: self._draw_switch(cv, get()))
        self._switches.append((cv, get))
        self._draw_switch(cv, get())
        return cv

    def _draw_switches(self):
        for cv, get in self._switches:
            if cv.winfo_exists():
                self._draw_switch(cv, get())
