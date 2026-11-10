"""The app's tabs, mixed into App (app.py) like the views they switch (leagueui.py, inboxui.py, ttui.py): DAILIES,
TIME TRIAL, LEAGUES, 1V1 and CUPS, each in its colour as on the website, and the inbox's letter on the right
(inboxui.py). As RaceRoom's: blocks along the header, the one on screen solid white, underlined in its colour. TIME TRIAL is the week's two time trial stages (ttui.py). LEAGUES, 1V1 and CUPS are one view of my
events (leagueui.py) showing one kind each, DRIVE the same for all; 1V1 adds the challenges (accept, decline, cancel, a
rematch of one that is over: server src/h2h.js; a new one: challengeui.py), CUPS the cups I'm in and the ones open for
entries (join, leave: src/cups.js). Making a cup stays on the website.

On the left, the driver's card (RaceRoom's profile panel): their picture on a red banner (their initials until it is in),
their team's tag and their name, their team's name in its colour, their figures: rating and world rank (server
src/rating.js, from their page src/drivers.js) and credits with the coin (the shop a click away); their team (or all
teams); their driver page and the shop in the app (profileui.py). Signing out: SETTINGS (settingsui.py).
"""
import threading
import time
import tkinter as tk
from tkinter import messagebox

from . import avatars, icons, photos, tmtext
from .api import ApiError
from .leagueui import _left

# (kind, tab, colour): the website's colours for each part of the game (server src/site.js); the dailies in white
TABS = (('daily', 'DAILIES', None), ('tt', 'TIME TRIAL', '#BF5AF2'), ('league', 'LEAGUES', '#5BA8FF'), ('h2h', '1V1', '#FF9F43'),
        ('cup', 'CUPS', '#FFD60A'))
COLOUR = {k: col for k, _t, col in TABS}
# the header's nav, as RaceRoom's (HOME its house; COMPETITIONS: the leagues, 1V1s and cups, their own tabs under it);
# PROFILE after them (profileui.py)
NAV = (('home', ''), ('daily', 'DAILIES'), ('tt', 'TIME TRIAL'), ('comp', 'COMPETITIONS'))
NAV_COLOUR = {'home': None, 'daily': None, 'tt': '#BF5AF2'}
COMP = (('league', 'LEAGUES'), ('h2h', '1V1'), ('cup', 'CUPS'))
DRIVER_EVERY_MIN = 15          # the rating moves once a day (and with a cup match): the driver strip now and then
EXTRAS_EVERY_MIN = 5           # the challenges / the cups while their tab is open
SHOWN = 3                      # challenges, cups listed in each part (the rest: the website)


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def rating_cells(d):
    """The driver card's figures: (rating, world rank) as ('1512', '#3 OF 40'), ('–', 'NOT RATED YET'), or None (no
    rating on the server)."""
    if not d or not d.get('ratingOn'):
        return None
    r = d.get('rating')
    if not r:
        return '–', 'NOT RATED YET'
    return '%d' % r['rating'], '#%d OF %d' % (r['rank'], r['of'])


def initials(name):
    """'MaybeIWill' -> 'MA', 'Kalle Rovanperä' -> 'KR': on the driver card until their picture is in."""
    words = [w for w in (name or '').replace('_', ' ').split() if w[:1].isalnum()]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else '?').upper()


def challenge_text(h, mine):
    """A challenge in one line: 'Ann · Monte Carlo · 3 stages · 50 each' (mine: 'challenger' / 'opponent')."""
    other = h['opponent'] if mine == 'challenger' else h['challenger']
    n = len(h.get('stages') or [])
    return '%s · %s · %d stage%s · %s' % (tmtext.tagged(other, other.get('name') or 'a driver'), h.get('rally') or '', n, '' if n == 1 else 's',
                                          ('%d each' % h['stake']) if h.get('stake') else 'friendly')


def result_text(h, me):
    """A settled 1V1: 'WON vs Bob (by 1.250 s)', 'LOST vs Bob', 'NO CONTEST vs Bob (nobody finished)'."""
    other = h['opponent'] if h['challenger']['steamId'] == me else h['challenger']
    if h.get('status') != 'settled':
        return '%s · %s' % (h.get('status', '').upper(), tmtext.tagged(other))
    word = 'NO CONTEST' if not h.get('winner') else 'WON' if h['winner'] == me else 'LOST'
    return '%s vs %s%s' % (word, tmtext.tagged(other, other.get('name') or 'a driver'), (' (%s)' % h['note']) if h.get('note') else '')


class TabsUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    league_kind = 'league'         # what the events view shows: 'league', 'h2h' (1V1) or 'cup'
    driver = None                  # /api/drivers/<me>: the driver strip's rating
    h2h_data = None                # /api/h2h: my challenges
    cups_data = None               # /api/cups: the cups, mine among them
    tab_msg = ''                   # why the challenges / the cups could not be loaded
    _tab_parts = None              # kind -> (label, underline)
    _tab_on = None                 # the tab on screen
    _tag_shown = None              # (tag, its $ codes, colour) drawn on the driver's card
    _avatar_tries = 0              # the driver's picture: looked for again a few times while it downloads

    # -------------------------------------------------------------- layout
    def _build_tabs(self, parent):
        """The header, as RaceRoom's: the nav after the logo (HOME, DAILIES, TIME TRIAL, COMPETITIONS, PROFILE),
        blocks side by side, the one on screen solid white; on the right, icons: the inbox (inboxui.py), the shop,
        Discord, the settings (settingsui.py), the guide, quit; each says what it is under the mouse."""
        c = _c()
        row = self._nav_row = tk.Frame(parent, bg=c.BG)
        row.pack(side='left', padx=(36, 0))
        self._tab_parts = {}
        for kind, text in NAV:
            f = tk.Frame(row, bg=c.BG)
            f.pack(side='left', padx=(0, 2))
            l = tk.Label(f, text=text, bg=c.PANEL, fg=c.SOFT, font=(c.FONT_C, 12), padx=20 if text else 14, pady=7,
                         cursor='hand2', compound='center')
            l.pack(fill='both', expand=True)
            u = tk.Frame(f, bg=c.BG, height=3)       # its colour under it while on screen
            u.pack(fill='x')
            for w in (f, l):
                w.bind('<Button-1>', lambda _e, k=kind: self.nav(k))
            l.bind('<Enter>', lambda _e, k=kind: self._paint_tab(k, hover=True))
            l.bind('<Leave>', lambda _e, k=kind: self._paint_tab(k))
            if kind == 'home':
                self._tip(l, 'Home')
            self._tab_parts[kind] = (l, u)
        self._build_profile_button(row)           # PROFILE: their picture, their driver page (profileui.py)
        side = tk.Frame(parent, bg=c.BG)          # the icons, right to left
        side.pack(side='right', padx=(0, 16))
        self._icon_btn(side, 'quit', 'Quit ACR Daily', lambda: self.quit())
        self._icon_btn(side, 'help', 'How to play', lambda: self.open_guide())
        self._build_settings_button(side)         # (settingsui.py)
        self._icon_btn(side, 'discord', 'ACR Daily on Discord', lambda: self.open_discord())
        self._icon_btn(side, 'shop', 'Shop', lambda: self.open_profile('shop'))
        self._build_inbox_button(side)            # the letter (inboxui.py)
        self._mark_tabs()

    def _header_layout(self):
        """(app.py _layout) The header for the window's width: one row (a wide window); else the logo and the icons on
        top, the nav on a row of its own under them, its blocks closer, and the day and the time left out."""
        head = getattr(self, '_head', None)
        if head is None:
            return
        narrow = self.layout_narrow
        for w, _info in self._head_wide:
            w.pack_forget()
        if narrow:                                   # (packed first, at the bottom: the whole width is its)
            self._nav_row.pack(side='bottom', anchor='w', pady=(12, 0))
        for w, info in self._head_wide:
            if not (narrow and w in (self._nav_row, self.date_l, self.clock_l)):
                w.pack(**info)
        for kind, text in NAV:
            if text:
                self._tab_parts[kind][0].configure(padx=12 if narrow else 20)
        self._profile_badge()                        # (the name shorter)

    def nav(self, kind):
        """A block of the nav clicked: HOME, or a part (COMPETITIONS: the kind of events last shown)."""
        if kind == 'home':
            self.open_home()
        elif kind == 'comp':
            self.show_tab(self.league_kind)
        else:
            self.show_tab(kind)

    def _paint_tab(self, kind, hover=False):
        """A block of the nav: solid white with black letters while on screen, underlined in its colour; else dark
        (lighter under the mouse)."""
        c = _c()
        l, u = self._tab_parts[kind]
        on = kind == self._tab_on
        if on:
            l.configure(bg=c.WHITE, fg=c.BG)
            u.configure(bg=(COLOUR[self.league_kind] if kind == 'comp' else NAV_COLOUR.get(kind)) or c.WHITE)
        else:
            l.configure(bg=c.PANEL2 if hover else c.PANEL, fg=c.WHITE if hover else c.SOFT)
            u.configure(bg=c.BG)
        if kind == 'home':                           # (its house, black on white while on screen; as tall as the words)
            img = icons.get(l, 'home', 18, c.BG if on else c.WHITE if hover else c.SOFT)
            if img:
                ref = self._tab_parts['daily'][0]
                edge = 2 * (int(l.cget('bd')) + int(l.cget('highlightthickness')))
                l.configure(image=img, text='', pady=0, padx=0, height=ref.winfo_reqheight() - edge,
                            width=img.width() + round(28 * l.winfo_fpixels('1i') / 96))
            else:
                l.configure(image='', text='HOME')

    def _icon_btn(self, parent, name, tip, cmd):
        """An icon of the header's right side (RaceRoom's): grey, white on a lighter square under the mouse."""
        c = _c()
        l = tk.Label(parent, bg=c.BG, padx=8, pady=7, cursor='hand2')
        paint = lambda hover=False: l.configure(  # noqa: E731
            image=icons.get(l, name, 18, c.WHITE if hover else c.SOFT) or '', bg=c.PANEL2 if hover else c.BG,
            text='' if icons.get(l, name, 18, c.SOFT) else tip.split()[0].upper(), fg=c.SOFT, font=(c.FONT_C, 10))
        paint()
        l.bind('<Button-1>', lambda _e: cmd())
        l.bind('<Enter>', lambda _e: paint(True), add='+')
        l.bind('<Leave>', lambda _e: paint(), add='+')
        l.pack(side='right', padx=(2, 0))
        self._tip(l, tip)
        self._icons = dict(getattr(self, '_icons', None) or {}, **{name: l})
        return l

    def _tip(self, widget, text):
        """What a widget is, under it after a moment with the mouse on it (RaceRoom's OPTIONS under its gear)."""
        c = _c()
        state = {}

        def show():
            state.pop('job', None)
            if not widget.winfo_exists():
                return
            t = state['win'] = tk.Toplevel(widget)
            t.overrideredirect(True)
            t.attributes('-topmost', True)
            tk.Label(t, text=text.upper(), bg=c.WHITE, fg=c.BG, font=(c.FONT_C, 9), padx=6, pady=2).pack()
            t.update_idletasks()
            t.geometry('+%d+%d' % (widget.winfo_rootx() + (widget.winfo_width() - t.winfo_reqwidth()) // 2,
                                   widget.winfo_rooty() + widget.winfo_height() + 4))

        def enter(_e):
            state['job'] = widget.after(450, show)

        def leave(_e):
            if 'job' in state:
                widget.after_cancel(state.pop('job'))
            if state.get('win') is not None:
                state.pop('win').destroy()
        widget.bind('<Enter>', enter, add='+')
        widget.bind('<Leave>', leave, add='+')
        widget.bind('<Button-1>', leave, add='+')

    def _build_profile_button(self, parent):
        """PROFILE in the nav: the driver's picture and the word (signed out: SIGN IN, with Steam)."""
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96 if hasattr(self, 'root') else 1
        f = tk.Frame(parent, bg=c.BG)
        f.pack(side='left', padx=(14, 0))
        top = self._prof_top = tk.Frame(f, bg=c.BG, cursor='hand2')
        top.pack(fill='both', expand=True)
        self.prof_pic = tk.Canvas(top, width=round(26 * k), height=round(26 * k), bg=c.BG, highlightthickness=0, cursor='hand2')
        self.prof_pic.pack(side='left', padx=(6, 8), pady=4)
        self.prof_l = tk.Label(top, text='PROFILE', bg=c.BG, fg=c.SOFT, font=(c.FONT_C, 12), cursor='hand2')
        self.prof_l.pack(side='left', padx=(0, 12))
        self.prof_u = tk.Frame(f, bg=c.BG, height=3)
        self.prof_u.pack(fill='x')
        for w in (f, top, self.prof_pic, self.prof_l):
            w.bind('<Button-1>', lambda _e: self.open_profile() if self.s.get('token') else self.login_click())
            w.bind('<Enter>', lambda _e: self._profile_badge(hover=True))
            w.bind('<Leave>', lambda _e: self._profile_badge())
        self._profile_badge()

    def _profile_badge(self, hover=False):
        """PROFILE: their ACR Daily picture in a ring (their frame from the shop) and their name, white while the driver
        page is open (a grey figure until the picture has downloaded, or if they have none; signed out: SIGN IN)."""
        top = getattr(self, '_prof_top', None)
        if top is None:
            return
        c = _c()
        on = bool(getattr(self, 'profile_view', False))
        bg = c.WHITE if on else c.PANEL2 if hover else c.BG
        for w in (top, self.prof_pic, self.prof_l):
            w.configure(bg=bg)
        signed = bool(self.s.get('token'))
        d = self.driver or {}
        name = d.get('name') or self.s.get('name') or 'PROFILE'
        most = 14 if getattr(self, 'layout_stack', False) else 18      # (a narrow window: the nav's room)
        self.prof_l.configure(text=(name if len(name) <= most else name[:most - 1] + '…') if signed else 'SIGN IN',
                              fg=c.BG if on else c.WHITE if hover else c.SOFT)
        self.prof_u.configure(bg=c.ACC if on else c.BG)
        cv = self.prof_pic
        size = int(cv.cget('width'))
        cv.delete('all')
        img = avatars.get(d.get('avatar'), size - 4) if signed and d.get('avatar') else None
        ring = ((d.get('look') or {}).get('frame') or {}).get('color')
        if img is not None:
            cv._img = img
            cv.create_oval(0, 0, size - 1, size - 1, fill=ring or c.WHITE, outline='')
            cv.create_image(size / 2, size / 2, image=img)
            return
        if signed:
            cv.create_oval(1, 1, size - 2, size - 2, fill=c.PANEL2, outline=ring or c.LINE2)
        img = icons.get(cv, 'user', 18, c.BG if on else c.SOFT)
        if img is not None:
            cv._img = img
            cv.create_image(size / 2, size / 2, image=img)

    def _build_driver_strip(self, parent):
        """The driver's card (RaceRoom's profile panel), filling the panel's width: the red banner with their picture,
        team tag and name, their team's name, their figures (a grey word on the left, the figure on the right), their
        team and their page."""
        c = _c()
        P = c.PANEL
        k = self.root.winfo_fpixels('1i') / 96 if hasattr(self, 'root') else 1
        self._k_px = k
        self.driver_box = tk.Frame(parent, bg=P, highlightthickness=1, highlightbackground=c.LINE)
        self.driver_box.pack(fill='x')
        self.driver_avatar = tk.Canvas(self.driver_box, height=round(96 * k), bg=c.ACC, highlightthickness=0, cursor='hand2')
        self.driver_avatar.bind('<Button-1>', lambda _e: self.open_profile())      # (their driver page: profileui.py)
        self.driver_avatar.bind('<Configure>', lambda _e: self._render_avatar())
        self.driver_avatar.pack(fill='x')
        inner = self._driver_inner = tk.Frame(self.driver_box, bg=P)
        inner.pack(fill='x', padx=14, pady=(10, 12))
        top = tk.Frame(inner, bg=P)
        top.pack(fill='x')
        # the team's tag in its colours (pieces: _render_tag; a click: the team's page), then the name
        self.driver_tag = tk.Frame(top, bg=P, cursor='hand2')
        self.driver_tag.bind('<Button-1>', lambda _e: self.open_team())
        self._tag_shown = None
        self.driver_name = tk.Label(top, text='', bg=P, fg=c.WHITE, font=(c.FONT_C, 20), anchor='w', cursor='hand2')
        self.driver_name.bind('<Button-1>', lambda _e: self.open_profile())
        self.driver_name.pack(side='left')
        # their team's name in its colour (RaceRoom's red team line), when they are in one
        self.driver_team_name = tk.Label(inner, text='', bg=P, fg=c.ACC, font=(c.FONT, 8, 'bold'), anchor='w', cursor='hand2')
        self.driver_team_name.bind('<Button-1>', lambda _e: self.open_team())
        # the figures, as RaceRoom's: a grey word on the left, the figure in white on the right
        self._driver_figs = figs = tk.Frame(inner, bg=P)
        figs.pack(fill='x', pady=(8, 0))
        self._driver_cells = {}
        for key, word in (('rating', 'RATING'), ('rank', 'WORLD RANK'), ('credits', 'CREDITS')):
            cell = tk.Frame(figs, bg=P)
            tk.Label(cell, text=word, bg=P, fg=c.MUTED, font=(c.FONT, 8, 'bold'), anchor='w').pack(side='left')
            v = tk.Label(cell, text='', bg=P, fg=c.WHITE, font=(c.FONT_C, 13), anchor='e', compound='right')
            v.pack(side='right')
            self._driver_cells[key] = (cell, v)
        self.driver_rating = self._driver_cells['rating'][1]
        self.driver_rank = self._driver_cells['rank'][1]
        self.driver_credits = self._driver_cells['credits'][1]
        self.driver_credits.configure(cursor='hand2')
        self.driver_credits.bind('<Button-1>', lambda _e: self.open_profile('shop'))    # the balance: the shop
        links = tk.Frame(inner, bg=P)
        links.pack(fill='x', pady=(10, 0))
        self.driver_team = self._link(links, 'Teams ›', self.open_team)     # my team's page, or all teams
        # my driver page and the shop, in the app (profileui.py: the profile, achievements, shop, customize)
        self.driver_page = self._link(links, 'Profile ›', lambda: self.open_profile())
        self.driver_shop = self._link(links, 'Shop ›', lambda: self.open_profile('shop'))
        for w in (self.driver_team, self.driver_page, self.driver_shop):
            w.configure(bg=P)
        self.driver_page.pack(side='left')
        self.driver_shop.pack(side='left', padx=(14, 0))
        self.driver_team.pack(side='right')
        self._render_driver()

    def _mark_tabs(self):
        """The block on screen solid white, underlined in its colour; COMPETITIONS' own tab (leagueui.py); the inbox's
        letter, the settings and PROFILE as they are."""
        self._tab_on = 'home' if getattr(self, 'home_view', False) else None if self._page_on() else (
            'comp' if self.league_view else 'tt' if self.tt_view else 'daily')
        for kind in self._tab_parts or {}:
            self._paint_tab(kind)
        self._mark_comp()
        self._inbox_badge()
        self._settings_badge()
        self._profile_badge()

    def _mark_comp(self):
        """COMPETITIONS' own tabs (LEAGUES, 1V1, CUPS: RaceRoom's RUNNING / ENTERED / FINISHED): the one shown red,
        underlined."""
        parts = getattr(self, '_comp_parts', None)
        if not parts:
            return
        c = _c()
        for kind, (l, u) in parts.items():
            on = kind == self.league_kind
            l.configure(fg=c.ACC if on else c.FG2)
            u.configure(bg=c.ACC if on else c.BG)

    def show_tab(self, kind):
        """A tab clicked: the dailies, the time trial (ttui.py), or my events of one kind (and that kind's own parts)."""
        if kind == 'tt':
            self.toggle_tt_view(True)
        elif kind == 'daily' and self.tt_view and not self.inbox_view:
            self.toggle_tt_view(False)
        elif kind == 'daily':
            self._tt_leave()
            self.toggle_league_view(False)
        else:
            self._tt_leave()
            self.toggle_league_view(True, kind)
            self.refresh_tab_extras()

    # -------------------------------------------------------------- the driver strip
    def _render_driver(self):
        self._profile_badge()                         # (PROFILE in the nav: their picture)
        box = getattr(self, 'driver_box', None)
        if box is None:
            return
        c = _c()
        if not self.s.get('token'):
            box.pack_forget()
            return
        if not box.winfo_manager():
            box.pack(fill='x', before=self._head_rule)
        d = self.driver or {}
        team = d.get('team') or {}
        if team.get('tag'):
            self._render_tag(team)
            if not self.driver_tag.winfo_manager():
                self.driver_tag.pack(side='left', padx=(0, 6), before=self.driver_name)
        else:
            self.driver_tag.pack_forget()
        self.driver_team.configure(text='My team ›' if team.get('id') else 'Teams ›')
        look = d.get('look') or {}                   # (their name in their colour from the shop, as on the website)
        self.driver_name.configure(text=d.get('name') or self.s.get('name') or 'Signed in',
                                   fg=look['color'] if look.get('color') and not look.get('grad') else c.WHITE)
        if team.get('name'):
            self.driver_team_name.configure(text=team['name'].upper(), fg=team.get('color') or c.ACC)
            if not self.driver_team_name.winfo_manager():
                self.driver_team_name.pack(fill='x', pady=(1, 0), before=self._driver_figs)
        else:
            self.driver_team_name.pack_forget()
        cells = rating_cells(d)
        self.driver_rating.configure(text=cells[0] if cells else '')
        self.driver_rank.configure(text=cells[1] if cells else '')
        cr = self.credits or {}
        if cr.get('enabled') and cr.get('signedIn') and cr.get('earning', True):
            self.driver_credits.configure(text='%d ' % cr.get('balance', 0), image=self.coin_img or '', font=(c.FONT_C, 13))
        elif cr.get('enabled') and cr.get('signedIn'):           # (credits start with the first finished run)
            self.driver_credits.configure(text='finish a run to earn credits', image='', font=(c.FONT, 8))
        else:
            self.driver_credits.configure(text='', image='')
        narrow = getattr(self, 'layout_narrow', False)            # (a narrow window: side by side, a strip)
        for cell, v in self._driver_cells.values():               # (a figure the server doesn't keep: left out)
            word = cell.winfo_children()[0]
            for w in (cell, word, v):
                w.pack_forget()
            if narrow:                                             # (the word over its figure, columns side by side)
                word.pack(anchor='w')
                v.pack(anchor='w')
            else:                                                  # (the word on the left, the figure on the right)
                word.pack(side='left')
                v.pack(side='right')
            if not v.cget('text'):
                continue
            if narrow:
                cell.pack(side='left', padx=(0, 28), pady=1)
            else:
                cell.pack(fill='x', pady=1)
        self._render_avatar()

    def _driver_layout(self):
        """(app.py _layout) The driver's card: a column (the panel on the left), or a strip across the top (a narrow
        window): their picture on the left of their name, the figures side by side."""
        av = getattr(self, 'driver_avatar', None)
        if av is None:
            return
        av.pack_forget()
        self._driver_inner.pack_forget()
        if self.layout_narrow:
            av.configure(width=round(116 * self._k_px))
            av.pack(side='left', fill='y')
            self._driver_inner.pack(side='left', fill='both', expand=True, padx=14, pady=(10, 12))
        else:
            av.pack(fill='x')
            self._driver_inner.pack(fill='x', padx=14, pady=(10, 12))
        self._render_driver()

    def _render_avatar(self):
        """The red banner: RaceRoom's slashes in a darker red on the right, the driver's ACR Daily picture (theirs, or
        Steam's: as on their driver page) in a ring on the left, in their frame from the shop; a grey figure until it
        has downloaded (looked for again a while, PROFILE in the header with it)."""
        cv = getattr(self, 'driver_avatar', None)
        if cv is None:
            return
        c = _c()
        k = getattr(self, '_k_px', 1)
        d = self.driver or {}
        narrow = getattr(self, 'layout_narrow', False)    # (a strip across the top: a red square, the picture in it)
        w = cv.winfo_width() if narrow and cv.winfo_width() > 1 else max(cv.winfo_width(), round(260 * k))
        h = cv.winfo_height() if cv.winfo_height() > 1 else int(cv.cget('height'))
        cv.delete('all')
        for i in range(0 if narrow else 4):               # the slashes
            x0 = w * 0.52 + i * 30 * k
            cv.create_polygon(x0, h, x0 + 16 * k, h, x0 + 16 * k + h * 0.55, 0, x0 + h * 0.55, 0, fill='#C40411', outline='')
        r = round(32 * k)
        cx, cy = (w / 2 if narrow else round(16 * k) + r), h / 2
        fr = (d.get('look') or {}).get('frame') or {}
        cv.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3, fill='#9E030E', outline=fr.get('color') or c.WHITE,
                       width=max(2, min(5, fr.get('width') or 2)), dash=(4, 3) if fr.get('dash') else None)
        img = avatars.get(d.get('avatar'), 2 * r) if d.get('avatar') else None
        if img is not None:
            cv._img = img                                # (kept: Tk shows nothing of an image Python dropped)
            cv.create_image(cx, cy, image=img)
            self._profile_badge()                        # (the header's too, now that it is here)
            return
        fig = icons.get(cv, 'user', 36, '#F4B4B8')
        if fig is not None:
            cv._img = fig
            cv.create_image(cx, cy, image=fig)
        if d.get('avatar') and avatars.Image is not None and self._avatar_tries < 40:
            self._avatar_tries += 1
            self.root.after(1500, self._render_avatar)

    def _render_tag(self, team):
        """The team's tag as on the website: Trackmania's $ codes (tmtext.py) in pieces, each in its colour (the team's where
        it sets none), bold, italic, capitals. Tk has no letter spacing or shadow: wide, narrow and shadow are left out."""
        c = _c()
        key = (team.get('tag'), team.get('tagFmt'), team.get('color'))
        if key == self._tag_shown:
            return
        self._tag_shown = key
        for w in self.driver_tag.winfo_children():
            w.destroy()
        for x in tmtext.spans(team['tagFmt']) if team.get('tagFmt') else [{'t': team['tag']}]:
            style = ' '.join(s for s, on in (('bold', x.get('b')), ('italic', x.get('i'))) if on)
            l = tk.Label(self.driver_tag, text=x['t'].upper() if x.get('u') else x['t'], bg=c.BG, bd=0, padx=0,
                         fg=x.get('c') or team.get('color') or c.WHITE, font=(c.FONT_C, 12, style) if style else (c.FONT_C, 12),
                         cursor='hand2')
            l.bind('<Button-1>', lambda _e: self.open_team())
            l.pack(side='left')

    def refresh_driver(self):
        """(any thread) The driver's rating and rank, from their page."""
        sid = self.s.get('steamId')
        if not self.api.configured or not self.s.get('token') or not sid:
            self.driver = None
            _c().ui(self.root, self._render_driver)
            return

        def go():
            try:
                d = self.api.driver(sid)
                _c().ui(self.root, self._set_driver, d)
            except ApiError:
                pass
        threading.Thread(target=go, daemon=True).start()

    def _set_driver(self, d):
        if self.s.get('token'):                      # (an answer after a sign-out: dropped)
            if (d or {}).get('avatar') != (self.driver or {}).get('avatar'):
                self._avatar_tries = 0               # (a new picture: looked for afresh)
            self.driver = d
        self._render_driver()

    def open_my_page(self):
        if self.s.get('steamId'):
            self.open_page('/d/%s' % self.s['steamId'])

    def open_team(self):
        """My team's page on the website, or all teams (to make or join one)."""
        tid = ((self.driver or {}).get('team') or {}).get('id')
        self.open_page('/t/%s' % tid if tid else '/teams')

    # -------------------------------------------------------------- 1V1: the challenges; CUPS: the cups
    def refresh_tab_extras(self):
        """The challenges (1V1) or the cups (CUPS), when that tab is on screen."""
        kind = self.league_kind
        if not self.league_view or kind not in ('h2h', 'cup') or not self.api.configured or not self.s.get('token'):
            return

        def go():
            try:
                r = self.api.h2h() if kind == 'h2h' else self.api.cups()
                _c().ui(self.root, self._set_tab_extras, kind, r, '')
            except ApiError as e:
                _c().ui(self.root, self._set_tab_extras, kind, None, ('1V1s: %s' if kind == 'h2h' else 'Cups: %s') % e)
        threading.Thread(target=go, daemon=True).start()

    def _set_tab_extras(self, kind, r, msg):
        self.tab_msg = msg
        if r is not None:
            if kind == 'h2h':
                self.h2h_data = r
            else:
                self.cups_data = r
        if self.league_view and self.league_kind == kind:
            self._render_leagues()

    def _render_tab_extras(self, box):
        """Under the events of the 1V1 or CUPS tab: their own parts."""
        if self.league_kind == 'h2h':
            self._render_challenges(box)
        elif self.league_kind == 'cup':
            self._render_cups(box)

    def _part(self, box, title, link=None, cmd=None):
        c = _c()
        top = tk.Frame(box, bg=c.BG)
        top.pack(fill='x', padx=self._padx(box), pady=(14, 2))
        self._k(top, title).pack(side='left')
        if link:
            self._link(top, link, cmd).pack(side='right')
        return top

    def _line(self, box, text, sub, buttons=(), colour=None, banner=None):
        """One row of a part, a small dark card: its text, a smaller line under it, its buttons on the right; a cup's
        banner (as its admins put it on the website) on the left, once downloaded."""
        c = _c()
        P = c.PANEL
        row = tk.Frame(box, bg=P, highlightthickness=1, highlightbackground=c.LINE)
        row.pack(fill='x', padx=self._padx(box), pady=(6, 0))
        k = self.root.winfo_fpixels('1i') / 96
        img = photos.thumb(row, banner, round(132 * k), round(44 * k)) if banner else None
        if img is not None:                              # (3:1, as the website's)
            pic = tk.Label(row, image=img, bg=P, bd=0)
            pic._img = img
            pic.pack(side='left', padx=(9, 0), pady=9)
        inner = tk.Frame(row, bg=P)
        inner.pack(fill='x', padx=12, pady=9)
        for label, cmd, primary in reversed(buttons):
            self._btn(inner, label, cmd, primary=primary, surface=P).pack(side='right', padx=(6, 0))
        body = tk.Frame(inner, bg=P)
        body.pack(side='left', fill='x', expand=True)
        room = max(150, 340 - 85 * len(buttons) - (140 if img is not None else 0))   # (beside its buttons, never cut off)
        self._lbl(body, text, font=(c.FONT_C, 13), fg=colour or c.WHITE, bg=P, wraplength=room).pack(anchor='w')
        if sub:
            self._lbl(body, sub, font=(c.FONT, 8), fg=c.MUTED, wraplength=room, bg=P).pack(anchor='w')

    def _render_challenges(self, box):
        c = _c()
        self._part(box, 'Challenges', 'Challenge a driver  ›', self.new_challenge)
        r = self.h2h_data
        if r is None:
            self._lbl(box, self.tab_msg or 'Loading…', fg=c.MUTED, font=(c.FONT, 9)).pack(anchor='w', padx=self._padx(box), pady=(4, 8))
            return
        me, now = self.s.get('steamId'), time.time() * 1000
        incoming, outgoing, past = r.get('incoming') or [], r.get('outgoing') or [], (r.get('past') or [])[:SHOWN]
        if not (incoming or outgoing or past):
            self._lbl(box, 'No challenges yet: challenge a driver (above), or wait for one.', fg=c.MUTED,
                      font=(c.FONT, 9), wraplength=400).pack(anchor='w', padx=self._padx(box), pady=(4, 8))
        for h in incoming[:SHOWN]:
            self._line(box, challenge_text(h, 'opponent'), 'Challenges you · answer within %s' % _left(h['answerBy'] - now),
                       (('ACCEPT', lambda h=h: self.answer_challenge(h, 'accept'), True),
                        ('DECLINE', lambda h=h: self.answer_challenge(h, 'decline'), False)), colour=COLOUR['h2h'])
        for h in outgoing[:SHOWN]:
            self._line(box, challenge_text(h, 'challenger'), 'Waiting for their answer',
                       (('CANCEL', lambda h=h: self.answer_challenge(h, 'cancel'), False),))
        for h in past:                               # a 1V1 that was played: REMATCH, the same again
            self._line(box, result_text(h, me), h.get('name') or '',
                       (('REMATCH', lambda h=h: self.rematch(h), False),) if h.get('status') == 'settled' else (), colour=c.SOFT)

    def new_challenge(self):
        """CHALLENGE A DRIVER: the form (challengeui.py); the challenges again once it has gone."""
        from .challengeui import ChallengeDialog
        ChallengeDialog(self, done=self.refresh_tab_extras)

    def rematch(self, h):
        """REMATCH: the same 1V1 sent again to the other driver (its stages, car, rules and stake), open as long, from
        now (the server's: POST /api/h2h/<id>/rematch)."""
        c = _c()
        me = self.s.get('steamId')
        other = h['opponent'] if (h.get('challenger') or {}).get('steamId') == me else h['challenger']
        ask = 'Rematch %s: the same stages, car and rules?' % (other.get('name') or 'them')
        ask += ('\n\n%d credits each.' % h['stake']
                if h.get('stake') else '\n\nA friendly: no credits.')
        if not messagebox.askyesno('ACR Daily', ask):
            return

        def go():
            try:
                self.api.h2h_rematch(h['id'])
                c.ui(self.root, self.sub_l.configure, {'text': 'Rematch sent to %s: they have a day to answer.' % (other.get('name') or 'them')})
                c.ui(self.root, self.refresh_credits)
            except ApiError as e:
                c.ui(self.root, messagebox.showwarning, 'ACR Daily', 'Not sent: %s' % e)
            c.ui(self.root, self.refresh_tab_extras)
        threading.Thread(target=go, daemon=True).start()

    def answer_challenge(self, h, action):
        """ACCEPT (the stake is taken), DECLINE or CANCEL a challenge."""
        c = _c()
        if action == 'accept':
            bal = (self.credits or {}).get('balance', 0)
            ask = 'Accept %s\'s 1V1, %s?' % ((h.get('challenger') or {}).get('name') or 'the', h.get('name') or '')
            if h.get('stake'):
                ask += '\n\nStake: %d credits each (you have %d).' % (h['stake'], bal)
            if not messagebox.askyesno('ACR Daily', ask):
                return
        elif action == 'decline' and not messagebox.askyesno('ACR Daily', 'Decline this 1V1?'):
            return

        def go():
            try:
                self.api.h2h_answer(h['id'], action)
                said = {'accept': 'Accepted: the match is under 1V1.', 'decline': 'Declined.',
                        'cancel': 'Cancelled: your stake is back.' if h.get('stake') else 'Cancelled.'}[action]
                c.ui(self.root, self.sub_l.configure, {'text': said})
                c.ui(self.root, self.refresh_leagues)
                c.ui(self.root, self.refresh_credits)
            except ApiError as e:
                c.ui(self.root, messagebox.showwarning, 'ACR Daily', 'Not done: %s' % e)
            c.ui(self.root, self.refresh_tab_extras)
        threading.Thread(target=go, daemon=True).start()

    def _render_cups(self, box):
        c = _c()
        r = self.cups_data
        self._part(box, 'My cups', 'Cups on the website  ›', lambda: self.open_page('/cups'))
        if r is None:
            self._lbl(box, self.tab_msg or 'Loading…', fg=c.MUTED, font=(c.FONT, 9)).pack(anchor='w', padx=self._padx(box), pady=(4, 8))
            return
        mine = set(r.get('mine') or [])
        listed = (r.get('open') or []) + (r.get('running') or [])
        my = [x for x in listed if x['id'] in mine]
        if not my:
            self._lbl(box, 'You are in no cup right now.', fg=c.MUTED, font=(c.FONT, 9)).pack(anchor='w', padx=self._padx(box), pady=(4, 6))
        for x in my[:SHOWN]:
            if x['status'] == 'open':
                sub = 'Starts %s · %d of %d drivers' % (time.strftime('%a %d %b %H:%M', time.localtime(x['starts'] / 1000)),
                                                      x['entrants'], x['size'])
                buttons = (('LEAVE', lambda x=x: self.cup_entry(x, 'leave'), False),)
            else:
                sub = 'Under way: your match is above when its round opens'
                buttons = ()
            self._line(box, self._cup_title(x), sub, buttons + (('CUP ›', lambda x=x: self.open_page('/cup/%s' % x['id']), False),),
                       colour=COLOUR['cup'], banner=self._cup_banner(x))
        others = [x for x in (r.get('open') or []) if x['id'] not in mine and x['entrants'] < x['size']]
        if others:
            self._part(box, 'Open for entries')
            for x in others[:SHOWN]:
                money = ('entry %d' % x['fee']) if x.get('fee') else 'free entry'
                if x.get('prize'):
                    money += ' · prize %d' % x['prize']
                sub = '%s · %s · %d of %d · starts %s' % (x.get('rally') or '', money, x['entrants'], x['size'],
                                                         time.strftime('%a %d %b', time.localtime(x['starts'] / 1000)))
                self._line(box, self._cup_title(x), sub, (('JOIN', lambda x=x: self.cup_entry(x, 'join'), True),),
                           banner=self._cup_banner(x))

    def _cup_banner(self, x):
        """A cup's banner (/api/cups: its address), once downloaded; the cups drawn again when it is."""
        return self.banner_key(x.get('banner'), lambda: self.league_view and self.league_kind == 'cup' and self._render_leagues())

    @staticmethod
    def _cup_title(x):
        return ('OFFICIAL · ' if x.get('official') else '') + x['name']

    def cup_entry(self, x, action):
        """JOIN (the entry fee is taken) or LEAVE (it comes back) a cup before its start."""
        c = _c()
        fee = x.get('fee') or 0
        if action == 'join':
            ask = 'Join %s?' % x['name']
            if fee:
                ask += '\n\nEntry fee: %d credits (you have %d).' % (fee, (self.credits or {}).get('balance', 0))
        else:
            ask = 'Leave %s?%s' % (x['name'], (' Your entry fee of %d credits comes back.' % fee) if fee else '')
        if not messagebox.askyesno('ACR Daily', ask):
            return

        def go():
            try:
                self.api.cup_entry(x['id'], action)
                c.ui(self.root, self.sub_l.configure, {'text': ('You are in %s.' if action == 'join' else 'You left %s.') % x['name']})
                c.ui(self.root, self.refresh_credits)
            except ApiError as e:
                c.ui(self.root, messagebox.showwarning, 'ACR Daily', 'Not done: %s' % e)
            c.ui(self.root, self.refresh_tab_extras)
        threading.Thread(target=go, daemon=True).start()
