"""The app's driver page, mixed into App (app.py) like the pages beside it (settingsui.py, liveui.py): the website's
driver page (/d/<me>), its shop and the driver's own settings, in the view's place while open. Opened from the
driver's card on the left (Profile ›, Shop ›, their picture, their credits).

    [ PROFILE | ACHIEVEMENTS | SHOP | CUSTOMIZE ]                               Your page on the website ›
    PROFILE        who they are (picture, name in their colour with their badge, team, flag, since when), their rating
                   and world rank with its history, their career numbers, their last results, their leagues and cups
    ACHIEVEMENTS   every one, as on the website: a tile in its tier's colours (grey and locked until unlocked), what it
                   takes, when it was unlocked, how rare it is
    SHOP           the looks (a colour for their name and their dot on the live map, a badge, a frame round their
                   picture): bought with credits, worn one of each kind at a time; and a daily of their own
    CUSTOMIZE      a name of their own, their flag, a picture of their own; what they wear; their team

Everything comes from the website's own requests (GET /api/drivers/<me>?full=1, /api/shop, /api/countries; POST
/api/shop/buy, /wear, /daily, /api/me/name, /country, /avatar): nothing the website can't do, nothing it does
differently.
"""
import datetime as dt
import io
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import avatars, tiles
from .api import ApiError

PARTS = (('profile', 'PROFILE'), ('achievements', 'ACHIEVEMENTS'), ('shop', 'SHOP'), ('customize', 'CUSTOMIZE'))
# the achievements' tiles: their tier's colours (top, bottom, rim), as the website's (server src/achievements.js TIERS)
TIERS = {'bronze': ('#D9955A', '#7A4A22', '#F0B98A'), 'silver': ('#D5DBE3', '#6B727D', '#F2F5F8'),
         'gold': ('#FFD86B', '#A26F00', '#FFE9A6'), 'platinum': ('#A9E4FA', '#2F6380', '#D9F4FF')}
LOCKED = ('#3A3A42', '#202024', '#4A4A52')
# each achievement's mark (the website draws its own icons; Tk draws no SVG: a symbol each, of the plain ones every
# Windows font has)
GLYPHS = {'flag': '⚑', 'podium': '▟', 'trophy': '♕', 'crown': '♛', 'calendar': '▦', 'flame': '♨', 'road': '⇶',
          'globe': '◍', 'drop': '☂', 'snow': '❄', 'fog': '≋', 'moon': '☾', 'shield': '◈', 'jump': '⤴', 'wings': '✈',
          'coin': '◉', 'coins': '◎', 'sparkle': '✦', 'swords': '⚔', 'cupline': '♜', 'cup': '♔', 'cupstar': '✪',
          'star': '★', 'gem': '◆', 'people': '☻', 'wheel': '☸'}
KINDS = (('color', 'Colours', 'Your name on the timing sheets and your dot on the live map, in it.'),
         ('badge', 'Badges', 'By your name, on the timing sheets and the live map.'),
         ('frame', 'Frames', 'Round your picture on the live map.'))
PICTURE_PX = 256                # a picture of one's own is sent square, this big (the server takes 64 to 512)


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def career(stats):
    """The career numbers as the page lists them: [(word, figure)]."""
    s = stats or {}
    one = s.get('oneVone') or {}
    return [('DAILIES', str(s.get('dailies', 0))), ('FINISHES', str(s.get('finishes', 0))), ('WINS', str(s.get('wins', 0))),
            ('PODIUMS', str(s.get('podiums', 0))), ('BEST', 'P%d' % s['best'] if s.get('best') else '–'),
            ('RUNS', str(s.get('runs', 0))), ('KM DRIVEN', ('%.1f' % s.get('km', 0)).rstrip('0').rstrip('.')),
            ('FAVOURITE RALLY', s.get('rally') or '–'),
            ('1V1', '%d – %d – %d' % (one.get('won', 0), one.get('lost', 0), one.get('drawn', 0)))]


def result_line(r):
    """A recent daily: ('Sun 08 Nov', 'SS1 · Peïra Cava', 'P3 / 40', '+12')."""
    try:
        day = dt.date.fromisoformat(r['date']).strftime('%a %d %b')
    except (KeyError, ValueError):
        day = r.get('date') or ''
    where = ' · '.join(x for x in ('SS%s' % r.get('slot', ''), r.get('stage') or '') if x)
    place = 'DNF' if r.get('status') == 'dnf' or not r.get('place') else 'P%d / %d' % (r['place'], r.get('field') or 0)
    d = r.get('delta')
    delta = '' if d is None else ('%+d' % round(d)) if round(d) else '±0'
    return day, where, place, delta


def unlocked_text(a):
    """'Unlocked 12 Oct 2026 · 23 %' / 'Locked · 4 %': when, and the share of drivers who have it (short: it fits its tile)."""
    rare = '%s %%' % ('%g' % a.get('rarity', 0))
    if a.get('at'):
        return 'Unlocked %s · %s' % (dt.datetime.fromtimestamp(a['at'] / 1000).strftime('%d %b %Y'), rare)
    return 'Locked · %s' % rare


def square_picture(data):
    """A picture file's bytes -> (bytes, content type) as the server takes them: cut square from its middle, PICTURE_PX
    big, JPEG (well under 60 KB). Without Pillow: the file as it is (the server says what is wrong with it)."""
    try:
        from PIL import Image
    except ImportError:
        kind = 'image/png' if data[:8] == b'\x89PNG\r\n\x1a\n' else 'image/webp' if data[8:12] == b'WEBP' else 'image/jpeg'
        return data, kind
    img = Image.open(io.BytesIO(data)).convert('RGB')
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((PICTURE_PX, PICTURE_PX), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, 'JPEG', quality=88)
    return out.getvalue(), 'image/jpeg'


class ProfileUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    profile_view = False
    profile_box = None
    profile_part = 'profile'
    profile_data = None            # GET /api/drivers/<me>?full=1
    profile_msg = ''               # why it could not be loaded
    shop_data = None               # GET /api/shop
    countries = None               # GET /api/countries: [[code, name]]
    _profile_hid = ()
    _profile_tries = 0
    shop_inner = 'looks'           # the shop's part: its looks, or a daily of one's own

    # -------------------------------------------------------------- opening and closing it
    def open_profile(self, part='profile'):
        """The driver page, at that part (from the driver's card)."""
        self.profile_part = part
        if self.profile_view:
            self._render_profile()
            self._profile_fetch()
        else:
            self.toggle_profile_view(True)

    def toggle_profile_view(self, on=None):
        on = (not self.profile_view) if on is None else on
        if on == self.profile_view:
            return
        if not on:
            self._profile_leave()
            self._view_box().pack(fill='x', before=self._view_end)
            self._render_strip()
            return
        self._pages_leave()                          # (the inbox, the settings or LIVE give way)
        self.profile_view = True
        self._profile_hid = self._page_show(self.profile_box)
        self._mark_tabs()
        self._render_profile()
        self._profile_fetch()

    def _profile_leave(self):
        if not self.profile_view:
            return
        self.profile_view = False
        self._page_hide(self.profile_box, self._profile_hid)
        self._profile_hid = ()
        self._mark_tabs()

    def profile_show_part(self, part):
        if part != self.profile_part:
            self.profile_part = part
            self._render_profile()
            self._profile_fetch()

    # -------------------------------------------------------------- the requests
    def _profile_fetch(self):
        """What the part shown needs: the driver page (always: it is the page), the shop, the flags."""
        if not self.api.configured or not self.s.get('token') or not self.s.get('steamId'):
            return
        part, sid = self.profile_part, self.s['steamId']

        def go():
            try:
                d = self.api.driver_page(sid)
                _c().ui(self.root, self._profile_in, 'profile_data', d, '')
            except ApiError as e:
                _c().ui(self.root, self._profile_in, None, None, 'Your driver page: %s' % e)
            try:
                if part == 'shop':
                    _c().ui(self.root, self._profile_in, 'shop_data', self.api.shop(), '')
                elif part == 'customize' and self.countries is None:
                    _c().ui(self.root, self._profile_in, 'countries', self.api.countries(), '')
            except ApiError as e:
                _c().ui(self.root, self._profile_in, None, None, '%s: %s' % ('The shop' if part == 'shop' else 'The flags', e))
        threading.Thread(target=go, daemon=True).start()

    def _profile_in(self, key, value, msg):
        if key:
            setattr(self, key, value)
        self.profile_msg = msg
        if self.profile_view:
            self._render_profile()

    def _profile_did(self, what, call, said=None, after=None):
        """A change (buy, wear, a name, a flag, a picture...): sent in a thread; then the page, the driver's card and the
        credits again; a refusal said as the server says it."""
        def go():
            try:
                r = call()
            except ApiError as e:
                _c().ui(self.root, messagebox.showwarning, 'ACR Daily', '%s: %s' % (what, e))
                return
            if said:
                _c().ui(self.root, self.sub_l.configure, {'text': said(r) if callable(said) else said})
            if after:
                _c().ui(self.root, after, r)
            _c().ui(self.root, self.refresh_driver)
            _c().ui(self.root, self.refresh_credits)
            _c().ui(self.root, self._profile_fetch)
        threading.Thread(target=go, daemon=True).start()

    # -------------------------------------------------------------- the page
    def _build_profile_box(self):
        """The page's frame: its head (the parts, the website), and its body (_render_profile)."""
        c = _c()
        self.profile_box = box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)
        head = tk.Frame(box, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(0, 8))
        self._profile_chips = {}
        for part, text in PARTS:
            l = tk.Label(head, text=text, font=(c.FONT_C, 11), padx=14, pady=4, cursor='hand2', highlightthickness=1)
            l.bind('<Button-1>', lambda _e, p=part: self.profile_show_part(p))
            l.pack(side='left', padx=(0, 6))
            self._profile_chips[part] = l
        self._link(head, 'Your page on the website  ›', self.open_my_page).pack(side='right')
        self.profile_note = self._lbl(head, '', fg=c.BAD, font=(c.FONT, 9))
        self.profile_note.pack(side='right', padx=(0, 18))
        self._profile_scroll = tiles.ScrollArea(box, c.BG)  # (taller than the window: it scrolls)
        self._profile_scroll.outer.pack(fill='both', expand=True)
        self.profile_body = self._profile_scroll.inner

    def _render_profile(self):
        if self.profile_box is None:
            return
        c = _c()
        for part, l in self._profile_chips.items():
            on = part == self.profile_part
            l.configure(bg=c.WHITE if on else c.BG, fg=c.BG if on else c.FG2, highlightbackground=c.WHITE if on else c.LINE2)
        self.profile_note.configure(text=self.profile_msg)
        body = self.profile_body
        for w in body.winfo_children():
            w.destroy()
        self._profile_scroll.top()
        for col in (0, 1):
            body.columnconfigure(col, weight=1, uniform='profile')
        if not self.s.get('token'):
            self._lbl(body, 'Sign in with Steam (on the left) to see your driver page, your achievements and the shop.',
                      fg=c.SOFT, font=(c.FONT, 10)).grid(row=0, column=0, columnspan=2, sticky='nw', padx=20, pady=10)
            return
        if self.profile_data is None:
            self._lbl(body, self.profile_msg or 'Loading your driver page…', fg=c.SOFT, font=(c.FONT, 10)).grid(
                row=0, column=0, columnspan=2, sticky='nw', padx=20, pady=10)
            return
        {'profile': self._render_profile_part, 'achievements': self._render_achievements,
         'shop': self._render_shop, 'customize': self._render_customize}[self.profile_part](body)

    def _panel(self, parent, title, row=0, col=0, colspan=1, sticky='new', right=None):
        """A panel of the page, its title spaced out with a hairline after it (as the settings' and the status box);
        right: (text, command) a link on its right. -> its frame."""
        c = _c()
        p = tk.Frame(parent, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
        p.grid(row=row, column=col, columnspan=colspan, sticky=sticky, padx=(20, 6) if col == 0 and colspan == 1 else
               (6, 20) if colspan == 1 else 20, pady=(0, 10))
        head = tk.Frame(p, bg=c.PANEL)
        head.pack(fill='x', padx=14, pady=(12, 6))
        self._k(head, title, bg=c.PANEL).pack(side='left')
        if right:
            ln = self._link(head, right[0], right[1])
            ln.configure(bg=c.PANEL)
            ln.pack(side='right')
        tk.Frame(head, bg=c.LINE2, height=1).pack(side='left', fill='x', expand=True, padx=(10, 10 if right else 0))
        return p

    # -------------------------------------------------------------- PROFILE
    def _render_profile_part(self, body):
        c = _c()
        d = self.profile_data
        look = d.get('look') or {}
        k = self.root.winfo_fpixels('1i') / 96
        left = tk.Frame(body, bg=c.BG)
        left.grid(row=0, column=0, sticky='nsew')
        right = tk.Frame(body, bg=c.BG)
        right.grid(row=0, column=1, sticky='nsew')
        for col in (left, right):
            col.columnconfigure(0, weight=1)
        # who they are: their picture, their name in their colour with their badge, their team, their flag, since when
        p = self._panel(left, 'Driver')
        row = tk.Frame(p, bg=c.PANEL)
        row.pack(fill='x', padx=14, pady=(0, 12))
        size = round(84 * k)
        pic = self.profile_pic = tk.Canvas(row, width=size, height=size, bg=c.PANEL, highlightthickness=0)
        pic.pack(side='left', padx=(0, 14))
        self._profile_picture(pic, d, size, look)
        who = tk.Frame(row, bg=c.PANEL)
        who.pack(side='left', fill='x', expand=True)
        name = (look.get('badge') + ' ' if look.get('badge') else '') + (d.get('name') or '')
        self._safe_label(who, name, (c.FONT_C, 24), look.get('color') or c.WHITE)
        team = d.get('team') or {}
        if team.get('name'):
            t = self._lbl(who, team['name'].upper(), fg=team.get('color') or c.ACC, font=(c.FONT, 9, 'bold'), bg=c.PANEL, cursor='hand2')
            t.bind('<Button-1>', lambda _e: self.open_team())
            t.pack(anchor='w')
        bits = [x for x in (self._country_name(d.get('country')),
                            'Driving since %s' % dt.datetime.fromtimestamp(d['since'] / 1000).strftime('%B %Y') if d.get('since') else '')
                if x]
        self._lbl(who, '  ·  '.join(bits), fg=c.FG2, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w', pady=(4, 0))
        # their rating, world rank and its history
        p = self._panel(left, 'Driver rating', row=1)
        r = d.get('rating') or {}
        top = tk.Frame(p, bg=c.PANEL)
        top.pack(fill='x', padx=14)
        if not d.get('ratingOn'):
            self._lbl(top, 'No rating on this server.', fg=c.MUTED, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w', pady=(0, 12))
        elif not r:
            self._lbl(top, 'Not rated yet: finish a daily to get your rating.', fg=c.MUTED, font=(c.FONT, 9), bg=c.PANEL).pack(
                anchor='w', pady=(0, 12))
        else:
            tk.Label(top, text='%d' % r['rating'], bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, 34)).pack(side='left')
            fig = tk.Frame(top, bg=c.PANEL)
            fig.pack(side='left', padx=(14, 0))
            self._lbl(fig, 'WORLD #%d OF %d' % (r['rank'], r['of']), fg=c.SOFT, font=(c.FONT_C, 13), bg=c.PANEL).pack(anchor='w')
            extra = '  ·  '.join(x for x in ('Peak %d' % r['peak'] if r.get('peak') else '',
                                              '%d races' % r['races'] if r.get('races') else '') if x)
            self._lbl(fig, extra, fg=c.MUTED, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w')
            chart = tk.Canvas(p, height=round(110 * k), bg='#0E0E11', highlightthickness=0)
            chart.pack(fill='x', padx=14, pady=(8, 12))
            chart.bind('<Configure>', lambda _e, cv=chart, h=d.get('history') or []: self._rating_chart(cv, h))
        # their leagues and cups
        lc = [('League · ' + x['name'], lambda i=x['id']: self.open_page('/l/%s' % i)) for x in (d.get('leagues') or [])[:4]]
        lc += [('Cup · %s%s' % (x['name'], ' · P%d' % x['place'] if x.get('place') else ''), lambda i=x['id']: self.open_page('/cup/%s' % i))
               for x in (d.get('cups') or [])[:4]]
        if lc:
            p = self._panel(left, 'Leagues and cups', row=2)
            for text, cmd in lc:
                ln = self._link(p, text + '  ›', cmd)
                ln.configure(bg=c.PANEL, anchor='w')
                ln.pack(anchor='w', padx=14, pady=(0, 4))
            tk.Frame(p, bg=c.PANEL, height=8).pack()
        # the career numbers
        p = self._panel(right, 'Career')
        grid = tk.Frame(p, bg=c.PANEL)
        grid.pack(fill='x', padx=14, pady=(0, 12))
        for i, (word, fig) in enumerate(career(d.get('stats'))):
            cell = tk.Frame(grid, bg=c.PANEL)
            cell.grid(row=i // 3, column=i % 3, sticky='w', pady=(0, 8))
            grid.columnconfigure(i % 3, weight=1, uniform='career')
            tk.Label(cell, text=' '.join(word), bg=c.PANEL, fg=c.MUTED, font=(c.FONT, 7, 'bold')).pack(anchor='w')
            tk.Label(cell, text=fig, bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, 16)).pack(anchor='w')
        cars = (d.get('stats') or {}).get('cars') or []
        if cars:
            self._lbl(p, 'Most driven: ' + ', '.join('%s (%d)' % (x['car'], x['runs']) for x in cars), fg=c.FG2, font=(c.FONT, 9),
                      bg=c.PANEL, wraplength=round(400 * k)).pack(anchor='w', padx=14, pady=(0, 12))
        # the last dailies
        p = self._panel(right, 'Last dailies', row=1)
        rows = (d.get('recent') or [])[:8]
        if not rows:
            self._lbl(p, 'No dailies yet.', fg=c.MUTED, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w', padx=14, pady=(0, 12))
        tab = tk.Frame(p, bg=c.PANEL)
        tab.pack(fill='x', padx=14, pady=(0, 12))
        tab.columnconfigure(1, weight=1)
        for i, r in enumerate(rows):
            day, where, place, delta = result_line(r)
            fg = c.BAD if place == 'DNF' else c.WHITE if place.startswith('P1 ') else c.SOFT
            for col, (text, colour, anchor) in enumerate(((day, c.MUTED, 'w'), (where, c.SOFT, 'w'), (place, fg, 'e'),
                                                         (delta, c.GOOD if delta.startswith('+') else c.BAD if delta.startswith('-')
                                                          else c.MUTED, 'e'))):
                tk.Label(tab, text=text, bg=c.PANEL, fg=colour, font=(c.FONT, 9), anchor=anchor).grid(
                    row=i, column=col, sticky='ew', padx=(0, 10), pady=1)

    def _rating_chart(self, cv, history):
        """The rating after each race: a line, its lowest and highest figures on the left, the last one marked."""
        c = _c()
        cv.delete('all')
        pts = [h['rating'] for h in history if h.get('rating') is not None]
        w, h = cv.winfo_width(), int(cv.cget('height'))
        if len(pts) < 2 or w < 50:
            cv.create_text(w / 2, h / 2, text='The rating\'s history: after a few races', fill=c.MUTED, font=(c.FONT, 9))
            return
        lo, hi = min(pts), max(pts)
        pad, left = 10, 44
        span = max(1, hi - lo)
        xy = []
        for i, v in enumerate(pts):
            xy.extend((left + (w - left - pad) * i / (len(pts) - 1), pad + (h - 2 * pad) * (hi - v) / span))
        for v, y in ((hi, pad), (lo, h - pad)):
            cv.create_text(left - 8, y, text=str(v), anchor='e', fill=c.MUTED, font=(c.FONT, 8))
            cv.create_line(left, y, w - pad, y, fill='#1C1C21')
        cv.create_line(*xy, fill=c.ACC, width=2, smooth=True)
        cv.create_oval(xy[-2] - 4, xy[-1] - 4, xy[-2] + 4, xy[-1] + 4, fill=c.WHITE, outline=c.ACC, width=2)

    def _profile_picture(self, cv, d, size, look):
        """Their picture in a ring (their frame from the shop, or white), their initials until it has downloaded."""
        c = _c()
        from .tabsui import initials
        cv.delete('all')
        fr = look.get('frame') or {}
        ring = fr.get('color') or c.WHITE
        cv.create_oval(2, 2, size - 2, size - 2, fill=c.ACC, outline=ring, width=max(2, fr.get('width') or 2),
                       dash=(4, 3) if fr.get('dash') else None)
        img = avatars.get(d.get('avatar'), size - 10) if d.get('avatar') else None
        if img is not None:
            cv._img = img
            cv.create_image(size / 2, size / 2, image=img)
            return
        cv.create_text(size / 2, size / 2, text=initials(d.get('name') or ''), fill=c.WHITE, font=(c.FONT_C, 26))
        if d.get('avatar') and avatars.Image is not None and self._profile_tries < 10:
            self._profile_tries += 1
            self.root.after(1500, lambda: cv.winfo_exists() and self._profile_picture(cv, d, size, look))

    def _safe_label(self, parent, text, font, fg):
        """A label whose text may hold a badge Tk can't draw (an emoji): without it then."""
        c = _c()
        try:
            l = tk.Label(parent, text=text, bg=c.PANEL, fg=fg, font=font, anchor='w')
        except tk.TclError:
            l = tk.Label(parent, text=text.encode('ascii', 'ignore').decode().strip(), bg=c.PANEL, fg=fg, font=font, anchor='w')
        l.pack(anchor='w')
        return l

    def _country_name(self, code):
        if not code:
            return ''
        names = dict(self.countries or [])
        return names.get(code) or code.upper()

    # -------------------------------------------------------------- ACHIEVEMENTS
    def _render_achievements(self, body):
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        achs = self.profile_data.get('achievements') or []
        got = sum(1 for a in achs if a.get('at'))
        head = tk.Frame(body, bg=c.BG)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 8))
        tk.Label(head, text='%d' % got, bg=c.BG, fg=c.WHITE, font=(c.FONT_C, 22)).pack(side='left')
        tk.Label(head, text=' / %d UNLOCKED' % len(achs), bg=c.BG, fg=c.FG2, font=(c.FONT_C, 13)).pack(side='left', pady=(6, 0))
        bar = tk.Canvas(head, height=round(6 * k), bg=c.PANEL2, highlightthickness=0)
        bar.pack(side='left', fill='x', expand=True, padx=(16, 0), pady=(8, 0))
        bar.bind('<Configure>', lambda e: (bar.delete('all'), bar.create_rectangle(0, 0, e.width * got / max(1, len(achs)),
                                                                                    e.height, fill=c.ACC, outline='')))
        grid = tk.Frame(body, bg=c.BG)
        grid.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=20)
        cols = 4
        for i in range(cols):
            grid.columnconfigure(i, weight=1, uniform='ach')
        for i, a in enumerate(achs):
            tile = tk.Frame(grid, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
            tile.grid(row=i // cols, column=i % cols, sticky='nsew', padx=(0 if i % cols == 0 else 6, 0), pady=(0, 6))
            self._ach_tile(tile, a, k)

    def _ach_tile(self, tile, a, k):
        """An achievement: its badge in its tier's colours (grey, locked, until unlocked), its name, what it takes, when."""
        c = _c()
        on = bool(a.get('at'))
        top, bottom, rim = TIERS.get(a.get('tier'), TIERS['bronze']) if on else LOCKED
        s = round(44 * k)
        cv = tk.Canvas(tile, width=s, height=s, bg=c.PANEL, highlightthickness=0)
        cv.pack(side='left', anchor='n', padx=(8, 8), pady=8)
        cv.create_rectangle(2, 2, s - 2, s - 2, fill=bottom, outline=rim, width=2)
        cv.create_rectangle(4, 4, s - 4, s * 0.55, fill=top, outline='')           # (a gradient's top half)
        cv.create_text(s / 2, s / 2 - 1, text=GLYPHS.get(a.get('glyph'), '★'), fill='#16161A' if on else c.MUTED,
                       font=(c.FONT, 16))                                              # (locked: its mark greyed, as the website's)
        if a.get('label') and on:
            cv.create_text(s - 5, s - 4, text=a['label'], anchor='se', fill=c.WHITE, font=(c.FONT_C, 8))
        txt = tk.Frame(tile, bg=c.PANEL)
        txt.pack(side='left', fill='both', expand=True, pady=(6, 6), padx=(0, 6))
        tk.Label(txt, text=a.get('name') or a.get('id'), bg=c.PANEL, fg=c.WHITE if on else c.FG2, font=(c.FONT_C, 11),
                 anchor='w').pack(anchor='w')
        desc = tk.Label(txt, text=a.get('desc') or '', bg=c.PANEL, fg=c.FG2 if on else c.MUTED, font=(c.FONT, 8), anchor='w',
                        justify='left', wraplength=round(150 * k))
        desc.pack(anchor='w')
        when = tk.Label(txt, text=unlocked_text(a), bg=c.PANEL, fg=c.GOOD if on else c.MUTED, font=(c.FONT, 7), anchor='w',
                        justify='left')
        when.pack(anchor='w', pady=(2, 0))
        txt.bind('<Configure>', lambda e: [w.configure(wraplength=max(80, e.width - 4)) for w in (desc, when)])   # (the tile's room)

    # -------------------------------------------------------------- SHOP
    def _render_shop(self, body):
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        shop = self.shop_data
        if shop is None:
            self._lbl(body, self.profile_msg or 'Opening the shop…', fg=c.SOFT, font=(c.FONT, 10)).grid(row=0, column=0, sticky='nw', padx=20)
            return
        if not shop.get('enabled'):
            self._lbl(body, 'The shop opens with credits: they are off on this server.', fg=c.SOFT, font=(c.FONT, 10)).grid(
                row=0, column=0, columnspan=2, sticky='nw', padx=20)
            return
        head = tk.Frame(body, bg=c.BG)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', padx=20, pady=(0, 6))
        tk.Label(head, text='BALANCE', bg=c.BG, fg=c.MUTED, font=(c.FONT, 8, 'bold')).pack(side='left', padx=(0, 8), pady=(6, 0))
        tk.Label(head, text='%d ' % (shop.get('balance') or 0), image=self.coin_img or '', compound='right', bg=c.BG, fg=c.WHITE,
                 font=(c.FONT_C, 20)).pack(side='left')
        for inner, text in (('daily', 'A DAILY OF YOUR OWN'), ('looks', 'LOOKS')):    # (right to left)
            on = inner == self.shop_inner
            l = tk.Label(head, text=text, font=(c.FONT_C, 10), padx=12, pady=3, cursor='hand2', highlightthickness=1,
                         bg=c.WHITE if on else c.BG, fg=c.BG if on else c.FG2, highlightbackground=c.WHITE if on else c.LINE2)
            l.bind('<Button-1>', lambda _e, i=inner: self._shop_show(i))
            l.pack(side='right', padx=(6, 0))
        self._lbl(head, 'Looks change nothing on the stage. Credits are only ever earned.', fg=c.MUTED, font=(c.FONT, 9)).pack(
            side='right', pady=(6, 0), padx=(0, 12))
        if self.shop_inner == 'daily':
            self._render_own_daily(body, shop, k)
            return
        worn = shop.get('worn') or {}
        items = shop.get('items') or []
        looks = tk.Frame(body, bg=c.BG)
        looks.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=20)
        looks.columnconfigure(0, weight=1)
        for r, (kind, title, about) in enumerate(KINDS):
            p = tk.Frame(looks, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
            p.grid(row=r, column=0, sticky='ew', pady=(0, 8))
            hd = tk.Frame(p, bg=c.PANEL)
            hd.pack(fill='x', padx=12, pady=(10, 6))
            self._k(hd, title, bg=c.PANEL).pack(side='left')
            self._lbl(hd, about, fg=c.MUTED, font=(c.FONT, 8), bg=c.PANEL).pack(side='left', padx=(10, 0))
            grid = tk.Frame(p, bg=c.PANEL)
            grid.pack(fill='x', padx=12, pady=(0, 10))
            mine = [x for x in items if x.get('kind') == kind]
            per = 9
            for i in range(per):
                grid.columnconfigure(i, weight=1, uniform='items%s' % kind)
            for i, it in enumerate(mine):
                self._shop_item(grid, it, worn.get(kind) == it['id'], shop.get('balance') or 0, k).grid(
                    row=i // per, column=i % per, sticky='nsew', padx=(0 if i % per == 0 else 4, 0), pady=(0, 4))

    def _shop_show(self, inner):
        self.shop_inner = inner
        self._render_profile()

    def _shop_item(self, parent, it, worn, balance, k):
        """A look: how it looks, its name and price, and what can be done with it: BUY, WEAR, or WORN (a click takes it
        off)."""
        c = _c()
        f = tk.Frame(parent, bg='#101013', highlightthickness=1, highlightbackground=c.WHITE if worn else c.LINE)
        cv = tk.Canvas(f, height=round(34 * k), bg='#101013', highlightthickness=0)
        cv.pack(fill='x', padx=6, pady=(6, 2))
        cv.bind('<Configure>', lambda e, it=it: self._look_preview(cv, it, e.width))
        tk.Label(f, text=it['name'], bg='#101013', fg=c.WHITE, font=(c.FONT_C, 10), wraplength=round(90 * k)).pack()
        if worn:
            b = self._btn(f, 'WORN  ✓', lambda: self._shop_wear(it, None), primary=True, surface='#101013')
        elif it.get('owned'):
            b = self._btn(f, 'WEAR', lambda: self._shop_wear(it, it['id']), surface='#101013')
        else:
            b = self._btn(f, '%d ' % it['price'], lambda: self._shop_buy(it, balance), primary=balance >= it['price'], surface='#101013')
            b.configure(image=self.coin_img or '', compound='right')
        b.configure(font=(c.FONT_C, 9), padx=8, pady=2)
        b.pack(pady=(2, 6))
        return f

    def _look_preview(self, cv, it, w):
        c = _c()
        cv.delete('all')
        h = int(cv.cget('height'))
        if it['kind'] == 'color':
            grad = it.get('grad') or [it.get('color')]
            n = len(grad)
            for i, col in enumerate(grad):                    # its colours, side by side (a gradient's stops)
                cv.create_rectangle(w * i / n, h - 6, w * (i + 1) / n, h, fill=col, outline='')
            name = self.s.get('name') or 'Your name'
            size = tiles.fit_size(cv, name, w - 6, (12, 11, 10, 9, 8))                  # (as big as fits the card)
            cv.create_text(w / 2, (h - 6) / 2, text=name, fill=it.get('color'), font=(c.FONT_C, size))
        elif it['kind'] == 'badge':
            try:
                cv.create_text(w / 2, h / 2, text=it.get('badge') or '', font=('Segoe UI Emoji', 16), fill=c.WHITE)
            except tk.TclError:
                cv.create_text(w / 2, h / 2, text=it['name'], font=(c.FONT_C, 10), fill=c.WHITE)
        else:
            r = h / 2 - 3
            cv.create_oval(w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r, fill=c.ACC, outline=it.get('ring'), width=it.get('width') or 3,
                           dash=(4, 3) if it.get('dash') else None)

    def _shop_buy(self, it, balance):
        if balance < it['price']:
            messagebox.showinfo('ACR Daily', '%s is %d credits: you have %d.' % (it['name'], it['price'], balance))
            return
        if not messagebox.askyesno('ACR Daily', 'Buy %s for %d credits? You wear it straight away.' % (it['name'], it['price'])):
            return
        self._profile_did('Not bought', lambda: self.api.shop_buy(it['id']), 'You bought %s: you are wearing it.' % it['name'])

    def _shop_wear(self, it, item):
        self._profile_did('Not changed', lambda: self.api.shop_wear(it['kind'], item),
                          ('You are wearing %s.' % it['name']) if item else ('You took %s off.' % it['name']))

    def _render_own_daily(self, body, shop, k):
        """A daily of one's own: the free daily (SS1) of a day at least two days ahead, set by the driver (the stage, the
        car, the weather, the time of day), as the website's shop."""
        c = _c()
        dd = shop.get('daily') or {}
        p = tk.Frame(body, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
        p.grid(row=1, column=0, sticky='new', padx=(20, 6))
        hd = tk.Frame(p, bg=c.PANEL)
        hd.pack(fill='x', padx=14, pady=(12, 6))
        self._k(hd, 'A daily of your own', bg=c.PANEL).pack(side='left')
        self._lbl(p, 'SS%s of a day of your choice: its stage, car, weather and time of day. It names you ("set by"). '
                  'One at a time; change it for free until two days before.' % dd.get('slot', 1), fg=c.FG2, font=(c.FONT, 9),
                  bg=c.PANEL, wraplength=round(380 * k)).pack(anchor='w', padx=14)
        mine = dd.get('mine') or []
        for m in mine:
            self._lbl(p, 'Yours: %s · %s · %s%s' % (m['date'], m.get('track'), m.get('car'), '' if m.get('editable') else ' (fixed now)'),
                      fg=c.GOOD, font=(c.FONT, 9, 'bold'), bg=c.PANEL).pack(anchor='w', padx=14, pady=(6, 0))
        form = tk.Frame(p, bg=c.PANEL)
        form.pack(fill='x', padx=14, pady=(8, 4))
        form.columnconfigure(1, weight=1)
        days = self._days(dd.get('from'), dd.get('to'))
        fields = (('Day', days), ('Stage', [t.get('name') or t.get('track') for t in dd.get('tracks') or []]),
                  ('Car', [x['name'] for x in dd.get('cars') or []]), ('Weather', [x['label'] for x in dd.get('weathers') or []]),
                  ('Time of day', [x['label'] for x in dd.get('times') or []]))
        boxes = {}
        for i, (word, values) in enumerate(fields):
            tk.Label(form, text=word, bg=c.PANEL, fg=c.FG2, font=(c.FONT, 9)).grid(row=i, column=0, sticky='w', pady=2, padx=(0, 10))
            cb = ttk.Combobox(form, values=values, state='readonly')
            if values:
                cb.set(values[0])
            cb.grid(row=i, column=1, sticky='ew', pady=2)
            boxes[word] = cb
        if mine and mine[0].get('editable'):              # (mine: its settings in the form, to change)
            m = mine[0]
            boxes['Day'].set(m['date'])
            pick = lambda cb, items, key, val, label: [cb.set(x[label]) for x in items if x.get(key) == val]  # noqa: E731
            pick(boxes['Stage'], dd.get('tracks') or [], 'track', m.get('track'), 'name')
            boxes['Car'].set(m.get('car') or '')
            pick(boxes['Weather'], dd.get('weathers') or [], 'id', m.get('weather'), 'label')
            pick(boxes['Time of day'], dd.get('times') or [], 'id', m.get('time'), 'label')
        acts = tk.Frame(p, bg=c.PANEL)
        acts.pack(fill='x', padx=14, pady=(6, 14))
        label = 'CHANGE IT' if mine and mine[0].get('editable') else 'SET IT  ·  %d ' % (dd.get('price') or 0)
        b = self._btn(acts, label, lambda: self._own_daily(dd, boxes, bool(mine)), primary=True, surface=c.PANEL)
        if not mine:
            b.configure(image=self.coin_img or '', compound='right')
        b.pack(side='left')

    @staticmethod
    def _days(first, last):
        try:
            d, end = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
        except (TypeError, ValueError):
            return []
        out = []
        while d <= end and len(out) < 60:
            out.append(d.isoformat())
            d += dt.timedelta(days=1)
        return out

    def _own_daily(self, dd, boxes, change):
        def by(items, label, value, key):
            return next((x[key] for x in items if x.get(label) == value), None)
        body = {'date': boxes['Day'].get(), 'track': by(dd.get('tracks') or [], 'name', boxes['Stage'].get(), 'track') or
                by(dd.get('tracks') or [], 'track', boxes['Stage'].get(), 'track'),
                'car': boxes['Car'].get(), 'weather': by(dd.get('weathers') or [], 'label', boxes['Weather'].get(), 'id'),
                'time': by(dd.get('times') or [], 'label', boxes['Time of day'].get(), 'id')}
        ask = ('Change your daily of %s?' % body['date']) if change else \
            ('Set the daily of %s for %d credits?\n\n%s · %s · %s · %s' % (body['date'], dd.get('price') or 0, boxes['Stage'].get(),
                                                                            body['car'], boxes['Weather'].get(), boxes['Time of day'].get()))
        if not messagebox.askyesno('ACR Daily', ask):
            return
        self._profile_did('Not set', lambda: self.api.shop_daily(body), 'The daily of %s is yours.' % body['date'])

    # -------------------------------------------------------------- CUSTOMIZE
    def _render_customize(self, body):
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        d = self.profile_data
        me = d.get('me') or {}
        look = d.get('look') or {}
        # a name of their own
        p = self._panel(body, 'Name')
        self._lbl(p, 'Your name on the timing sheets, the live maps and your page. One change a week; your Steam name is %s.'
                  % (me.get('steamName') or '–'), fg=c.FG2, font=(c.FONT, 9), bg=c.PANEL, wraplength=round(380 * k)).pack(anchor='w', padx=14)
        row = tk.Frame(p, bg=c.PANEL)
        row.pack(fill='x', padx=14, pady=(8, 4))
        self._name_var = tk.StringVar(self.root, value=me.get('customName') or '')
        tk.Entry(row, textvariable=self._name_var, bg='#0E0E11', fg=c.WHITE, insertbackground=c.WHITE, relief='flat',
                 font=(c.FONT, 11), highlightthickness=1, highlightbackground=c.LINE2, highlightcolor=c.FG2).pack(
            side='left', fill='x', expand=True, ipady=4)
        self._btn(row, 'SAVE', lambda: self._set_name(self._name_var.get().strip()), primary=True, surface=c.PANEL).pack(side='left', padx=(8, 0))
        if me.get('customName'):
            ln = self._link(p, 'Use my Steam name again  ›', lambda: self._set_name(None))
            ln.configure(bg=c.PANEL)
            ln.pack(anchor='w', padx=14)
        if me.get('nextNameChange'):
            nxt = dt.datetime.fromtimestamp(me['nextNameChange'] / 1000)
            if nxt > dt.datetime.now():
                self._lbl(p, 'Your next change: %s.' % nxt.strftime('%a %d %b, %H:%M'), fg=c.MUTED, font=(c.FONT, 8), bg=c.PANEL).pack(
                    anchor='w', padx=14)
        tk.Frame(p, bg=c.PANEL, height=10).pack()
        # their flag
        p = self._panel(body, 'Flag', row=1)
        self._lbl(p, 'By your name everywhere, and the ranking of your country.', fg=c.FG2, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w', padx=14)
        row = tk.Frame(p, bg=c.PANEL)
        row.pack(fill='x', padx=14, pady=(8, 14))
        names = ['No flag'] + [n for _code, n in (self.countries or [])]
        flag = ttk.Combobox(row, values=names, state='readonly')
        flag.set(self._country_name(d.get('country')) or 'No flag')
        flag.pack(side='left', fill='x', expand=True)
        self._btn(row, 'SAVE', lambda: self._set_country(flag.get()), primary=True, surface=c.PANEL).pack(side='left', padx=(8, 0))
        # their picture
        p = self._panel(body, 'Picture', col=1)
        row = tk.Frame(p, bg=c.PANEL)
        row.pack(fill='x', padx=14, pady=(0, 14))
        size = round(72 * k)
        pic = tk.Canvas(row, width=size, height=size, bg=c.PANEL, highlightthickness=0)
        pic.pack(side='left', padx=(0, 14))
        self._profile_picture(pic, d, size, look)
        side = tk.Frame(row, bg=c.PANEL)
        side.pack(side='left', fill='x', expand=True)
        self._lbl(side, 'Your picture on your page, the timing sheets and the live maps: a square one is best (it is cut '
                  'square from the middle).', fg=c.FG2, font=(c.FONT, 9), bg=c.PANEL, wraplength=round(300 * k)).pack(anchor='w')
        acts = tk.Frame(side, bg=c.PANEL)
        acts.pack(anchor='w', pady=(8, 0))
        self._btn(acts, 'CHOOSE A PICTURE…', self._choose_picture, primary=True, surface=c.PANEL).pack(side='left')
        if me.get('ownAvatar'):
            self._btn(acts, 'USE MY STEAM PICTURE', lambda: self._profile_did('Not changed', self.api.remove_avatar,
                                                                               'Your Steam picture is back.'), surface=c.PANEL).pack(side='left', padx=(8, 0))
        # what they wear, their team
        p = self._panel(body, 'Your look', row=1, col=1, right=('Shop  ›', lambda: self.profile_show_part('shop')))
        worn = [('Colour', look.get('color')), ('Badge', look.get('badge')),
                ('Frame', (look.get('frame') or {}).get('color'))]
        for word, v in worn:
            row = tk.Frame(p, bg=c.PANEL)
            row.pack(fill='x', padx=14, pady=1)
            tk.Label(row, text=word, bg=c.PANEL, fg=c.FG2, font=(c.FONT, 9), width=8, anchor='w').pack(side='left')
            if v and word != 'Badge':
                tk.Label(row, text='■', bg=c.PANEL, fg=v, font=(c.FONT, 12)).pack(side='left')
            text = (v if word == 'Badge' else '') if v else 'none (the shop has them)'
            try:
                tk.Label(row, text=text, bg=c.PANEL, fg=c.WHITE if v else c.MUTED, font=(c.FONT, 9)).pack(side='left', padx=(4, 0))
            except tk.TclError:
                pass
        team = d.get('team') or {}
        row = tk.Frame(p, bg=c.PANEL)
        row.pack(fill='x', padx=14, pady=(8, 14))
        tk.Label(row, text='Team', bg=c.PANEL, fg=c.FG2, font=(c.FONT, 9), width=8, anchor='w').pack(side='left')
        ln = self._link(row, (team.get('name') + '  ›') if team.get('name') else 'Make or join a team on the website  ›', self.open_team)
        ln.configure(bg=c.PANEL)
        ln.pack(side='left', padx=(4, 0))

    def _set_name(self, name):
        if name is not None and not name:
            name = None
        ask = ('Your name: %s?' % name) if name else 'Use your Steam name again?'
        if messagebox.askyesno('ACR Daily', ask + '\n\nOne change a week.'):
            def done(r):
                if isinstance(r, dict) and r.get('name'):    # (the name as shown now, on the card at once)
                    self.s['name'] = r['name']
            self._profile_did('Not changed', lambda: self.api.set_name(name), 'Your name is changed.', after=done)

    def _set_country(self, name):
        code = None if name == 'No flag' else next((cc for cc, n in (self.countries or []) if n == name), None)
        self._profile_did('Not changed', lambda: self.api.set_country(code), 'Your flag is changed.' if code else 'No flag now.')

    def _choose_picture(self):
        path = filedialog.askopenfilename(parent=self.root, title='A picture of your own',
                                          filetypes=[('Pictures', '*.png *.jpg *.jpeg *.webp'), ('All files', '*.*')])
        if not path:
            return
        try:
            with open(path, 'rb') as f:
                data, kind = square_picture(f.read())
        except Exception as e:      # (not a picture Pillow can read, or no file)
            messagebox.showwarning('ACR Daily', 'That picture can\'t be used: %s' % e)
            return
        self._profile_did('Not changed', lambda: self.api.set_avatar(data, kind), 'Your picture is changed.')
