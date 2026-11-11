"""The app's HOME, mixed into App (app.py) like the pages beside it (settingsui.py, profileui.py): where the app opens,
as RaceRoom's DRIVE screen, a photo tile for each part of ACR Daily, two big ones over four:

    [ DAILIES                        ]  [ TIME TRIAL                     ]
    [ LEAGUES      ]  [ 1V1          ]  [ CUPS         ]  [ COMMUNITY    ]

Each tile its photo (photos.py), its name big at the bottom, what it is under it, what is on now (today's stages, the
week's, a challenge to answer, a cup open for entries...) and a badge when something wants the driver (RaceRoom's red
FREE); a click goes there. The tiles are drawn again every few seconds while HOME is open (what they say changes).
"""
import time
import tkinter as tk

from . import tiles

REDRAW_S = 5
COLS = 4                       # (the grid: the big tiles 2 columns each, the small ones 1)
PLACES = (('daily', 0, 0, 2), ('tt', 0, 2, 2), ('league', 1, 0, 1), ('h2h', 1, 1, 1), ('cup', 1, 2, 1),
          ('community', 1, 3, 1))   # (key, row, column, span)


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


class HomeUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    home_view = False
    home_box = None
    _home_hid = ()
    _home_drawn = 0.0

    def open_home(self):
        self.toggle_home_view(True)

    def toggle_home_view(self, on=None):
        on = (not self.home_view) if on is None else on
        if on == self.home_view:
            return
        if not on:
            self._home_leave()
            self._view_box().pack(fill='x', before=self._view_end)
            self._render_strip()
            return
        self._pages_leave()                          # (the inbox, the settings or the driver page give way)
        self.home_view = True
        self._home_hid = self._page_show(self.home_box)
        side = getattr(self, '_side', None)          # (the whole width, as RaceRoom's DRIVE: no driver's panel)
        if side is not None and side.winfo_manager():
            side.pack_forget()
        self._mark_tabs()
        self._render_home()

    def _home_leave(self):
        if not self.home_view:
            return
        self.home_view = False
        self._page_hide(self.home_box, self._home_hid)
        self._home_hid = ()
        if getattr(self, '_side', None) is not None:  # (the driver's panel back: on the left, or across the top)
            self._pack_side()
        self._mark_tabs()

    def _build_home_box(self):
        """The tiles: two big ones over three, as tall as the view has room for (_home_sized)."""
        c = _c()
        self.home_box = box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)
        for col in range(COLS):
            box.columnconfigure(col, weight=1, uniform='home')
        box.rowconfigure(0, weight=3)
        box.rowconfigure(1, weight=2)
        self._home_tiles = {}
        for key, row, col, span in PLACES:
            t = tiles.Tile(box, on_click=lambda k=key: self.show_tab(k), restyle=self._btn_style)
            t.frame.grid(row=row, column=col, columnspan=span, sticky='nsew',
                         padx=(20 if col == 0 else 5, 20 if col + span == COLS else 5), pady=(0, 10))
            self._home_tiles[key] = t
        box.bind('<Configure>', lambda e: self._home_sized(e.height))

    def _home_sized(self, h):
        """The big tiles 3/5 of the view's height, the small ones the rest."""
        if h < 50:
            return
        big, small = round((h - 20) * 0.58), round((h - 20) * 0.42)
        for key, t in self._home_tiles.items():
            want = big if key in ('daily', 'tt') else small
            if t.min_h != want:
                t.min_h = want
                if t.spec is not None:
                    t.render(t.spec, t._w or None)

    def _render_home(self):
        if self.home_box is None or not self.home_view:
            return
        self._home_drawn = time.monotonic()
        for key, t in self._home_tiles.items():
            t.render(self._home_spec(key))

    def _home_tick(self):
        """(from the app's tick) While HOME is open: its tiles again every REDRAW_S seconds."""
        if self.home_view and time.monotonic() - self._home_drawn >= REDRAW_S:
            self._render_home()

    def _home_spec(self, key):
        """What a tile says: its name, what it is, what is on now, and its badge."""
        c = _c()
        if key == 'daily':
            names = ['SS%s %s' % (s, c.stage_name(d['ch'])) for s, d in sorted(self.dailies.items())]
            ch = self.challenge or {}
            left = int((ch.get('endsAt') or 0) / 1000 - time.time())
            badge = ('CLOSES IN %d:%02d' % (left // 3600, left % 3600 // 60), c.ACC) if left > 0 else None
            return {'photo': 'dailies', 'bottom': True, 'badge': badge, 'title': 'DAILIES', 'sizes': (34, 30, 26),
                    'lines': [('Two stages a day · random cars · your first run counts', 'sub'),
                              ('   ·   '.join(names) or 'Loading today\'s stages…', 'info')], 'button': False}
        if key == 'tt':
            info = getattr(self, 'tt_info', None) or {}
            names = ['TT%s %s' % (s, c.stage_name(t['ch'])) for s, t in sorted((getattr(self, 'tt', None) or {}).items())]
            entered = any(((t.get('ch') or {}).get('me') or {}).get('entered') for t in (getattr(self, 'tt', None) or {}).values())
            badge = ('ENTERED', c.GOOD) if entered else ('NEW WEEK', '#BF5AF2') if names else None
            return {'photo': 'tt', 'bottom': True, 'badge': badge, 'title': 'TIME TRIAL', 'sizes': (34, 30, 26),
                    'lines': [('Two stages all week · as many runs as you like · your best counts', 'sub'),
                              ('   ·   '.join(names) or ('No time trial this week' if info.get('on') is False else 'Loading the week…'),
                               'info')], 'button': False}
        if key == 'league':
            evs = [e for e in self.league_events if (e.get('kind') or 'league') == 'league' and e.get('status') == 'open']
            badge = ('%d OPEN' % len(evs), '#1F6FD6') if evs else None
            return {'photo': 'leagues', 'bottom': True, 'badge': badge, 'title': 'LEAGUES', 'sizes': (24, 21, 18),
                    'lines': [('Your clubs\' multi-stage rallies', 'sub')], 'button': False}
        if key == 'h2h':
            incoming = len((getattr(self, 'h2h_data', None) or {}).get('incoming') or [])
            mine = [e for e in self.league_events if e.get('kind') == 'h2h' and e.get('status') == 'open']
            badge = ('%d TO ANSWER' % incoming, c.ACC) if incoming else ('%d TO DRIVE' % len(mine), '#C46A12') if mine else None
            return {'photo': 'h2h', 'bottom': True, 'badge': badge, 'title': '1V1', 'sizes': (24, 21, 18),
                    'lines': [('Challenge a driver, stake credits', 'sub')], 'button': False}
        if key == 'community':
            from . import community
            items = [it for cat in (getattr(self, 'community_data', None) or {}).get('categories', [])
                     for it in cat.get('items', [])]
            new = [it for it in items if community.status(it, (getattr(self, '_community_man', None) or {}).get(it['id']),
                                                          getattr(self, '_community_game', None)) == 'install']
            badge = ('%d NEW' % len(new), '#30D158') if new else None
            return {'photo': 'community', 'bottom': True, 'badge': badge, 'title': 'COMMUNITY', 'sizes': (24, 21, 18),
                    'lines': [('Tracks, cars and skins to install', 'sub')], 'button': False}
        cups = getattr(self, 'cups_data', None) or {}
        open_ = [x for x in cups.get('open') or [] if (x.get('entrants') or 0) < (x.get('size') or 0)]
        mine = [e for e in self.league_events if e.get('kind') == 'cup' and e.get('status') == 'open']
        badge = ('YOUR MATCH', c.ACC) if mine else ('OPEN FOR ENTRIES', '#A88A00') if open_ else None
        return {'photo': 'cups', 'bottom': True, 'badge': badge, 'title': 'CUPS', 'sizes': (24, 21, 18),
                'lines': [('Knockouts of 1V1s', 'sub')], 'button': False}
