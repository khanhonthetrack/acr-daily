"""The COMMUNITY page: tracks and cars made by the community (community.py, the server's src/community.js) and the
drivers' liveries (liveries.py, src/liveries.js), installed into the game in one click and taken out again.

The page: a photo across the top with what it is, the categories (TRACKS, CARS, LIVERIES: the one shown underlined),
and the category's items as a game's server browser (from 0.1.6; they were cards two by two): the one picked in full
over the list (its card: its picture, name, what it is, who made it, the size of its package, where it stands in this
game, its button), and every item a row under it, one under another (a click picks one; a double click takes its first
step: INSTALL, GET IT...). The page scrolls. Installing downloads the package (shown as it comes), checks it, and puts it into the
game's ~mods folder; the game must be closed (it keeps its packages open). An item a time trial or a daily needs
(their `requires`) is installed from here: DRIVE sends the driver here when it is missing (ttui.py, app.py).

Stages from other tools (the test builds, community.py): Sando Rally's original stages (INSTALL downloads the official
zip from sandorally.com, unpacks it and opens Sando's Stage Manager, where the player installs it; MANAGE opens the
manager again) and WRC Generations' stages, one row each, made on this PC (stageexport.py): INSTALL finds WRC
Generations and Sando's Stage Export Tool, puts Stage Exporter into the tool the first time, makes the stage (its
progress on the card and the row; CANCEL stops it, and more stages wait their turn) and it is INSTALLED; REMOVE takes it
out. Without the tool (Sando no longer offers it) FIND TOOL lets the player show it once (its folder, or the zip it came
in, unpacked here); FIND GAME, WRC Generations' folder when neither Steam nor the Epic Games launcher lists it. What is in the game is read from its packages (community.stage_packs, as the page opens); with stages
of more than one tool in the game the page warns that only one tool's show (the game's one stage list).

LIVERIES: the drivers' liveries from the website (/liveries, liveries.py): a car picked (or all), in an order (top
rated, newest, most downloaded); each a card with its preview, who painted it, the stars and the downloads, RATE (a
vote of 1 to 5 stars, signed in), and INSTALL (its zip downloaded and unzipped into the game's liveries folder; REMOVE
takes it out) or DOWNLOAD (a link to a page: the browser). The game's liveries folder opens from here too.
"""
import os
import threading
import time
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import messagebox, ttk

from . import community, liveries, photos, settings, stageexport, stageswitch, tiles
from .i18n import N_, _, n_

CATEGORIES = (('tracks', _('TRACKS')), ('cars', _('CARS')), ('liveries', _('LIVERIES')))
COMMUNITY_COLOUR = '#30D158'
HEAD_H = 170                   # the photo across the top
CARD_H = 250                   # an item's card, at least
STATUS = {'nogame': (_("Assetto Corsa Rally isn't found on this PC."), 'muted'),
          'unavailable': (_('Coming soon: its package is being made.'), 'muted'),
          'install': (_('Not installed.'), 'info'),
          'installed': (_("Installed: in the game's rally selection."), 'good'),
          'update': (_('An update is ready.'), 'good'),
          'wait': (_('The game has been updated: a package for this version is on its way.'), 'muted'),
          # (its package is built on the PC from the game's own files: community.status, not this app yet)
          'newer': (_('This version of it needs a newer ACR Daily: the app update that installs it is on its way.'), 'muted'),
          # (another tool's stages: community.status; _other_tool_words says more)
          'ready': (_('Downloaded. OPEN MANAGER starts its Stage Manager: click Install there.'), 'info'),
          'link': (_("Not in your game. Its tool builds it on your PC from a game you own: GET IT opens the tool's "
                     'page.'), 'info'),
          'nowrcg': (_("It is made from your own copy of WRC Generations, which isn't found on this PC (Steam or Epic "
                       'Games). If it is somewhere else, FIND GAME shows ACR Daily its folder.'), 'info'),
          'off': (_("In your game, but hidden: the game shows another set of stages now. SHOW swaps these back in a "
                    'second; nothing is made again.'), 'info'),
          'stale': (_("Hidden since the game's update: its stage list was made for the version before. MANAGE opens "
                      "Sando's Stage Manager, which makes it for this version."), 'info'),
          'notool': (_("It is made with Sando Rally's Stage Export Tool 0.3.7, which isn't found on this PC. Sando no "
                       'longer offers it: if you have it (its folder or its zip), FIND TOOL shows ACR Daily where it is.'),
                     'info')}
# a stage made on this PC (stageexport.py): its button, and what it is doing
EXPORT_BUTTON = {'install': _('INSTALL'), 'installed': _('REMOVE'), 'notool': _('FIND TOOL'), 'nowrcg': _('FIND GAME'),
                 'off': _('SHOW'), 'stale': _('REBUILD')}
STALE_WRCG = _("Hidden since the game's update: its stage list was made for the version before and could hide the "
               "game's own stages. REBUILD makes it for this version in about 2 minutes; no stage is made again.")
EXPORT_PHASE = {'get': _('Getting Stage Exporter'), 'setup': _('Setting up Stage Exporter'), 'prep': _('Preparing'),
                'wrcg': _('Taking it from WRC Generations'), 'build': _('Building it for Assetto Corsa Rally'),
                'pack': _('Putting it in the game'), 'remove': _('Taking it out'),
                'unpack': _('Unpacking the Stage Export Tool'), 'repack': _('Rebuilding for this game version')}
# (a card more than one tool makes: GET IT asks which, _community_page_open)
LINK_TOOLS = _('Not in your game. One of its tools builds it on your PC from a game you own: GET IT picks one and '
               'opens its page.')
BADGE = {'installed': (_('INSTALLED'), '#30D158'), 'update': (_('UPDATE'), '#1F6FD6'), 'unavailable': (_('SOON'), '#5A5A63'),
         'newer': (_('SOON'), '#5A5A63'), 'ready': (_('DOWNLOADED'), '#1F6FD6'), 'off': (_('HIDDEN'), '#5A5A63'),
         'stale': (_('GAME UPDATED'), '#1F6FD6')}
# London or WRC Generations shown (stageswitch.py): the names its buttons say
SWITCH_NAMES = {'acrdaily': 'London', 'wrcg': 'WRC Generations', 'sando': 'Sando Rally'}
# settings: the game build each set's stage list was made for, and the sets hidden since an update (_check_stale)
STALE_BUILDS, STALE_SETS = 'stageSetBuilds', 'stageSetStale'
CLOSE_GAME = _('Close Assetto Corsa Rally first: it keeps its packages open while it runs.')
BUTTON = {'install': _('INSTALL'), 'update': _('UPDATE'), 'installed': _('REMOVE'), 'off': _('SHOW')}
# another tool's stages: installed by its own manager, or a link to the tool (community.py)
MANAGER_BUTTON = {'install': _('INSTALL'), 'ready': _('OPEN MANAGER'), 'installed': _('MANAGE'), 'off': _('SHOW'),
                  'stale': _('MANAGE')}
LINK_BUTTON = {'link': _('GET IT'), 'installed': _('OPEN PAGE')}
# the list's columns (key, heading, width at 96 dpi, anchor, stretches): browserui.table
ITEM_COLS = ((('name', N_('NAME'), 230, 'w', True), ('by', N_('BY'), 150, 'w', False), ('what', N_('WHAT'), 300, 'w', True),
              ('size', N_('SIZE'), 80, 'center', False), ('state', N_('STATUS'), 160, 'w', False)))
LV_COLS = (('title', N_('LIVERY'), 230, 'w', True), ('car', N_('CAR'), 180, 'w', True), ('by', N_('BY'), 130, 'w', False),
           ('stars', N_('RATING'), 120, 'w', False), ('clicks', N_('DOWNLOADS'), 100, 'center', False),
           ('state', N_('STATUS'), 120, 'w', False))
ITEM_DROP, LV_DROP = ('by', 'size', 'what'), ('clicks', 'stars', 'by', 'car')   # (narrow: these go, the first first)
# a row: where it stands, short, and its bar's colour
SHORT = {'nogame': N_('No game found'), 'unavailable': N_('Coming soon'), 'install': N_('Not installed'),
         'installed': N_('Installed'), 'update': N_('Update ready'), 'wait': N_('After a game update'),
         'newer': N_('Coming soon'), 'ready': N_('Downloaded'), 'link': N_('Not installed'),
         'page': N_('On a web page'), 'showonly': N_('Shown only'), 'nowrcg': N_('Needs WRC Generations'),
         'notool': N_('Needs the export tool'), 'off': N_('Hidden'), 'stale': N_('Needs a rebuild')}
ROW_COLOUR = {'installed': '#30D158', 'update': '#1F6FD6', 'ready': '#1F6FD6', 'install': '#D4D4D8', 'link': '#D4D4D8',
              'page': '#D4D4D8', 'off': '#8E8E93', 'stale': '#1F6FD6', 'other': '#5A5A63'}
NO_TOOL = _("There's no Stage Export Tool there: pick Sando-Rally-Stage-Export-Tool.exe in its folder, or the zip it "
            'came in.')
def _span(sec):
    """A time to go, as people say it: '25 minutes', '3 h 20 min'."""
    m = max(1, int(round(sec / 60)))
    return n_('%d minute', '%d minutes', m) % m if m < 60 else _('%d h %02d min') % (m // 60, m % 60)


SWITCH_CLASH = _('The game has %s in it, and it shows only one set of stages at a time. Pick the one to show: the '
                 'others stay on your PC, hidden, and come back in a second.')
CLASH = _("Only one tool's stages show in the game at a time, and the game has stages from %s. Keep one: remove the "
          'others with the tool that put them in.')
# a livery's card (liveries.status)
LV_STATUS = {'install': (_('Not in your game yet: INSTALL puts it in.'), 'info'),
             'installed': (_("In your game: in the car's liveries once the game (re)starts."), 'good'),
             'page': (_('Its link is a download page: DOWNLOAD opens it in your browser.'), 'muted'),
             'showonly': (_('Shown only: its author has not shared the file.'), 'muted')}
LV_BUTTON = {'install': _('INSTALL'), 'page': _('DOWNLOAD'), 'installed': _('REMOVE')}
LV_SORTS = (('top', _('Top rated')), ('new', _('Newest')), ('clicks', _('Most downloaded')))


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


class CommunityUI:
    community_view = False
    community_box = None
    community_cat = 'tracks'
    community_data = None          # /api/community: {categories: [{id, name, items}]}
    community_msg = ''             # why the list could not be loaded
    _community_man = None          # item id -> its package's manifest (None: none yet)
    _community_busy = None         # item id -> what it is doing ("Downloading 40 %...")
    _community_hid = ()
    _community_game = None         # the game's folder (looked up as the page opens)
    _community_build = None
    _community_packs = None        # the stage packages in the game: {path: [stage ids]} (community.stage_packs)
    community_picks = None         # category -> the item picked, over the list (its id)
    livery_pick = None             # the livery picked, over the list (its id)
    liveries_data = None           # /api/liveries: {liveries: [...], cars: [{id, name, count}], limits}
    liveries_msg = ''              # why they could not be loaded
    livery_car = ''                # the car picked ('' all)
    livery_sort = 'top'
    _livery_busy = None            # livery id -> what it is doing ("Downloading 12.0 MB...")

    # -------------------------------------------------------------- open / close
    def _build_community_box(self):
        c = _c()
        self.community_box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)
        self._community_man, self._community_busy = {}, {}

    def open_community(self, cat=None):
        if cat:
            self.community_cat = cat
        self.toggle_community_view(True)

    def toggle_community_view(self, on=None):
        on = (not self.community_view) if on is None else on
        if on == self.community_view:
            if on:
                self._render_community()
            return
        if not on:
            self._community_leave()
            self._view_box().pack(fill='x', before=self._view_end)
            self._render_strip()
            return
        self._pages_leave()                          # (HOME, the inbox, the settings, the driver page give way: app.py)
        self.community_view = True
        self._community_hid = self._page_show(self.community_box)
        side = getattr(self, '_side', None)          # (the whole width, as HOME)
        if side is not None and side.winfo_manager():
            side.pack_forget()
        self._mark_tabs()
        self._render_community()
        self.refresh_community()

    def _community_leave(self):
        if not self.community_view:
            return
        self.community_view = False
        self._page_hide(self.community_box, self._community_hid)
        self._community_hid = ()
        if getattr(self, '_side', None) is not None:
            self._pack_side()
        self._mark_tabs()

    # -------------------------------------------------------------- a stage that needs an item (DRIVE)
    def community_ready(self, need, look=False):
        """Is the item a stage needs (its `requires`) installed? look: find the game now if it isn't known yet (DRIVE);
        else (a card being drawn) not known yet reads as not installed."""
        if not need:
            return True
        game = self._community_game
        if game is None and not look:
            return False
        return community.requires_ok(need, game)

    def community_name(self, item_id):
        return next((it.get('name') for cat, _l in CATEGORIES for it in self._items(cat) if it['id'] == item_id),
                    None) or item_id

    def community_missing(self, ch, what):
        """DRIVE on a stage of a community item not installed in the game (ch['requires']): said, and the COMMUNITY page
        offered. -> True when DRIVE stops here."""
        need = (ch or {}).get('requires')
        if self.community_ready(need, look=True):
            return False
        if messagebox.askyesno('ACR Daily', _("%s is on %s, a community track that isn't in your game yet.\n\nInstall it "
                                             'from COMMUNITY now? (One click; then DRIVE again.)') % (what, self.community_name(need))):
            self.open_community('tracks')
        return True

    def community_select(self, cat):
        if cat != self.community_cat:
            self.community_cat = cat
            self._render_community()

    def _cat_count(self, cat):
        return len((self.liveries_data or {}).get('liveries') or []) if cat == 'liveries' else len(self._items(cat))

    # -------------------------------------------------------------- the list
    def refresh_community(self):
        """The list from the server, each item's package from GitHub, the game's folder and build (in a thread)."""
        def go():
            msg, data, mans = '', None, {}
            try:
                data = community.catalog(self.api)
            except Exception as e:                   # (no internet, the server down: said on the page)
                msg = _("Couldn't load the community's content (%s).") % e
            for cat in (data or {}).get('categories', []):
                for it in cat.get('items', []):
                    try:
                        mans[it['id']] = community.manifest(it)
                    except community.CommunityError as e:
                        # (GitHub not reached: the package known already stays, not "coming soon" for a lost answer)
                        mans[it['id']] = (getattr(self, '_community_man', None) or {}).get(it['id']) \
                            if e.kind == 'download' else None
            try:
                from .modinstall import game_dir
                game = game_dir()
            except Exception:
                game = None
            build = community.game_build(game)
            gone = community.guard(game, build) if game else []
            packs = community.stage_packs(game, self._catalogue_stage_ids(data)) if game else {}
            switch = stageswitch.state(game) if game else {}
            parked = stageswitch.parked_packs(game, self._catalogue_stage_ids(data)) if game else {}
            env = None
            if any(it.get('install') == 'export' for cat in (data or {}).get('categories', []) for it in cat.get('items', [])):
                s = settings.load()
                env = stageexport.environment(s.get(stageexport.SETTING), search=not getattr(self, '_export_searched', False),
                                              wrcg=s.get(stageexport.WRCG_SETTING))
                self._export_searched = True             # (the PC looked through once a session, unless shown)
            _c().ui(self.root, self._set_community, data, mans, msg, game, build, gone, packs, env, switch, parked)
            try:
                lv, lmsg = self.api.liveries(), ''
            except Exception as e:                   # (no internet, an older server: said on its tab)
                lv, lmsg = None, _("Couldn't load the liveries (%s).") % e
            _c().ui(self.root, self._set_liveries, lv, lmsg)
        threading.Thread(target=go, daemon=True).start()

    def _set_liveries(self, data, msg):
        if data is not None:
            self.liveries_data = data
        self.liveries_msg = msg
        if self.community_view and self.community_cat == 'liveries':
            self._render_community()

    def _set_community(self, data, mans, msg, game, build, gone, packs=None, env=None, switch=None, parked=None):
        if data is not None:
            self.community_data = data
        self._community_man = dict(self._community_man or {}, **mans)
        self.community_msg = msg
        self._community_game, self._community_build = game, build
        if packs is not None:
            self._community_packs = packs
        if switch is not None:
            self._community_switch, self._community_parked = switch, parked or {}
            self._check_stale(game, build)
        if env is not None:
            self._export_set_env(env)                   # (a stage still being made from before: followed again)
        if gone:
            names = {it['id']: it.get('name') or it['id'] for cat, _l in CATEGORIES for it in self._items(cat)}
            messagebox.showinfo('ACR Daily', _('Assetto Corsa Rally has been updated, so these were taken out of the '
                                               'game until a package for this version is up: %s.') % ', '.join(names.get(g, g) for g in gone))
        if self.community_view:
            self._render_community()
        if getattr(self, 'home_view', False):
            self._render_home()                      # (its COMMUNITY tile: what is new)
        if getattr(self, 'tt_view', False):
            self._render_tt()                        # (a time trial on a community track: installed or not)

    def _items(self, cat):
        """A category's tracks or cars (the liveries: _livery_list)."""
        for c in (self.community_data or {}).get('categories', []):
            if c.get('id') == cat:
                return c.get('items', [])
        return []

    # -------------------------------------------------------------- drawing
    def _render_community(self):
        if self.community_box is None or not self.community_view:
            return
        c = _c()
        box = self.community_box
        for w in box.winfo_children():
            w.destroy()
        self._community_tiles = {}
        k = box.winfo_fpixels('1i') / 96
        scroll = tiles.ScrollArea(box, c.BG)             # (more items than the window has room for: it scrolls)
        scroll.outer.pack(fill='both', expand=True)
        page = self._community_page = scroll.inner
        # the photo across the top, the words on it (a tile as HOME's)
        head = tiles.Tile(page)
        head.min_h = round(HEAD_H * k)
        head.frame.pack(fill='x', padx=20, pady=(0, 12))
        head.render({'photo': 'community', 'bottom': True, 'title': _('COMMUNITY'), 'sizes': (34, 30, 26), 'button': False,
                     'lines': [(_('Tracks, cars and liveries made by the community'), 'sub'),
                               (_("Installed into the game in one click, taken out as easily. Find them in the game's "
                                  "rally selection and the cars' liveries."), 'info')]})
        # the categories: the one shown underlined
        row = tk.Frame(page, bg=c.BG)
        row.pack(fill='x', padx=20, pady=(0, 12))
        for cat, label in CATEGORIES:
            on = cat == self.community_cat
            f = tk.Frame(row, bg=c.BG, cursor='hand2')
            f.pack(side='left', padx=(0, 22))
            l = tk.Label(f, text='%s  %d' % (label, self._cat_count(cat)), bg=c.BG, fg=c.WHITE if on else c.FG2,
                         font=(c.FONT_C, 14), cursor='hand2')
            l.pack()
            tk.Frame(f, bg=COMMUNITY_COLOUR if on else c.BG, height=3).pack(fill='x')
            for x in (f, l):
                x.bind('<Button-1>', lambda _e, kk=cat: self.community_select(kk))
        if self.community_cat == 'liveries':
            self._render_liveries(page)
            return
        # the category's items: cards two by two
        if self.community_data is None:
            tk.Label(page, text=self.community_msg or _('Loading…'), bg=c.BG, fg=c.MUTED, font=(c.FONT, 10)).pack(
                anchor='w', padx=20)
            return
        items = self._items(self.community_cat)
        if not items:
            said = {'tracks': _('No tracks yet. They will be here as the community makes them.'),
                    'cars': _('No cars yet. They will be here as the community makes them.')}
            tk.Label(page, text=said.get(self.community_cat, ''), bg=c.BG,
                     fg=c.MUTED, font=(c.FONT, 10)).pack(anchor='w', padx=20)
            return
        clash = self._community_clash()
        if clash and self.community_cat == 'tracks':     # (the game's one stage list: one tool's stages show)
            sets = self._switchable()
            words = SWITCH_CLASH % self._and([SWITCH_NAMES[g] for g in sets]) if sets and len(clash) == len(sets) \
                else CLASH % self._and(clash)
            warn = tk.Label(page, text=words, bg='#3A2A00', fg=c.WHITE, font=(c.FONT, 10), anchor='w',
                            justify='left', wraplength=round(600 * k), padx=12, pady=8)
            warn.pack(fill='x', padx=20, pady=(0, 0 if self._switchable() else 12))
            warn.bind('<Configure>', lambda e, w=warn: w.configure(wraplength=max(200, e.width - round(24 * k)))
                      if abs(int(w.cget('wraplength')) - (e.width - round(24 * k))) > 4 else None)
            if self._switchable():                       # (London and WRC Generations both in: one click each way)
                row = tk.Frame(page, bg='#3A2A00')
                row.pack(fill='x', padx=20, pady=(0, 12))
                for g in self._switchable():
                    self._btn(row, _('SHOW ONLY %s') % SWITCH_NAMES[g].upper(), lambda g=g: self._community_show_group(g),
                              surface='#3A2A00').pack(side='left', padx=(12, 0), pady=(0, 10))
        if self.community_picks is None:
            self.community_picks = {}
        ids = [it['id'] for it in items]
        if self.community_picks.get(self.community_cat) not in ids:
            self.community_picks[self.community_cat] = ids[0]
        pick = items[ids.index(self.community_picks[self.community_cat])]
        if any(it.get('install') == 'export' for it in items):
            self._export_strip(page, items)              # (over the card: INSTALL ALL and how far, seen first)
        grid = tk.Frame(page, bg=c.BG)                   # the one picked, in full
        grid.pack(fill='x', pady=(0, 12))
        t = tiles.TileRow(grid, 1, base=round(CARD_H * k)).add(tiles.Tile(grid, restyle=self._btn_style))
        self._community_tile = t
        self._community_tiles[pick['id']] = t
        self._community_fill(t, pick)
        self._community_table(page, items, pick['id'])

    def _community_status(self, it):
        man = (self._community_man or {}).get(it['id'])
        st = community.status(it, man, self._community_game, self._community_build, self._community_packs,
                              getattr(self, '_export_env', None))
        group = it.get('group')
        if group in stageswitch.GROUPS and (getattr(self, '_community_switch', None) or {}).get(group) == 'off':
            if st == 'installed' and not it.get('install'):            # (London: ours, its files parked)
                return 'off'
            if it.get('install') in ('export', 'manager') and st != 'installed' and \
                    community.stages_in_game(it, getattr(self, '_community_parked', None)):
                return 'stale' if group in self._stale_sets() else 'off'
        return st

    def _community_spec(self, it):
        """An item's card: its picture behind, where it stands in this game (badge, last line), its button."""
        man = (self._community_man or {}).get(it['id'])
        st = self._community_status(it)
        busy = (self._community_busy or {}).get(it['id'])
        info = [_('by %s') % it['author']] if it.get('author') else []
        if man and (man.get('zip') or {}).get('size'):
            info.append(community.size_text(man['zip']['size']))
        if man and man.get('version'):
            info.append(_('version %s') % man['version'])
        key = photos.fetch(it.get('image'), then=lambda: _c().ui(self.root, self._community_redraw, it['id']))
        words, kind = (busy, 'info') if busy else self._other_tool_words(it, man, st) or STATUS[st]
        frac = (getattr(self, '_community_frac', None) or {}).get(it['id']) if busy else None
        own = it.get('photo') if photos.has(it.get('photo')) else None     # (bundled with the app: London's render)
        buttons = {'manager': MANAGER_BUTTON, 'link': LINK_BUTTON, 'export': EXPORT_BUTTON}.get(it.get('install'), BUTTON)
        button = bool(st in buttons and not busy) or self._export_mine(it) is not None   # (making it: CANCEL)
        return st, {'photo': key or own or 'community', 'bottom': True, 'badge': BADGE.get(st), 'title': it.get('name', ''),
                    'sizes': (26, 23, 20), 'button': button, 'progress': frac,
                    'lines': [(it.get('subtitle'), 'sub'), (it.get('description'), 'info'),
                              ('   ·   '.join(info), 'muted'), (words, kind)]}

    def _community_fill(self, t, it):
        st, spec = self._community_spec(it)
        if t.button is not None:
            t.button.destroy()
            t.button = None
        if spec['button'] and it.get('install') == 'manager' and st == 'off':
            t.button = self._btn(t.cv, MANAGER_BUTTON[st] + '  ›', lambda: self.community_show(it), primary=True)
        elif spec['button'] and it.get('install') == 'manager':
            man = (self._community_man or {}).get(it['id'])
            t.button = self._btn(t.cv, MANAGER_BUTTON[st] + ('' if st == 'installed' else '  ›'),
                                 lambda: self.community_manager(it, man), primary=st != 'installed')
        elif spec['button'] and it.get('install') == 'export':
            if self._export_mine(it) is not None:
                t.button = self._btn(t.cv, _('CANCEL'), lambda: self.community_export_cancel(it))
            elif st == 'installed':
                t.button = self._btn(t.cv, EXPORT_BUTTON[st], lambda: self.community_export_remove(it))
            elif st == 'notool':
                t.button = self._btn(t.cv, EXPORT_BUTTON[st] + '  ›', lambda: self.community_find_tool(it), primary=True)
            elif st == 'nowrcg':
                t.button = self._btn(t.cv, EXPORT_BUTTON[st] + '  ›', self.community_find_wrcg, primary=True)
            elif st == 'off':
                t.button = self._btn(t.cv, EXPORT_BUTTON[st] + '  ›', lambda: self.community_show(it), primary=True)
            elif st == 'stale':
                t.button = self._btn(t.cv, EXPORT_BUTTON[st] + '  ›', lambda: self.community_export_rebuild(it),
                                     primary=True)
            else:
                t.button = self._btn(t.cv, EXPORT_BUTTON[st] + '  ›', lambda: self.community_export(it), primary=True)
        elif spec['button'] and it.get('install') == 'link':
            t.button = self._btn(t.cv, LINK_BUTTON[st] + ('' if st == 'installed' else '  ›'),
                                 lambda: self._community_page_open(it, t.button), primary=st != 'installed')
        elif spec['button']:
            if st == 'off':
                t.button = self._btn(t.cv, BUTTON[st] + '  ›', lambda: self.community_show(it), primary=True)
            elif st == 'installed':
                t.button = self._btn(t.cv, BUTTON[st], lambda: self.community_remove(it))
            else:
                t.button = self._btn(t.cv, BUTTON[st] + '  ›', lambda: self.community_install(
                    it, (self._community_man or {}).get(it['id'])), primary=True)
        t.render(spec, t._w or None)

    def _community_redraw(self, item_id):
        """Its card again if it is the one picked (its download's progress, its picture come), and its row."""
        t = (getattr(self, '_community_tiles', None) or {}).get(item_id)
        it = next((x for cat, _l in CATEGORIES for x in self._items(cat) if x['id'] == item_id), None)
        if self.community_view and t is not None and it is not None and t.frame.winfo_exists():
            self._community_fill(t, it)
        tree = getattr(self, '_community_tree', None)
        if it is not None and tree is not None and tree.winfo_exists() and tree.exists(item_id):
            st, values = self._community_row(it)
            tree.item(item_id, values=values, image=self._row_img(st))
        if it is not None and it.get('install') == 'export':
            self._export_strip_show()

    # -------------------------------------------------------------- the list (a server browser, browserui.table)
    def _row_img(self, st):
        if getattr(self, '_row_imgs', None) is None:
            from .browserui import bar_images
            self._row_imgs = bar_images(self.root, ROW_COLOUR)
        return self._row_imgs.get(st) or self._row_imgs['other']

    def _community_row(self, it):
        """An item's row: name, who made it, what it is, its package's size, where it stands (short)."""
        man = (self._community_man or {}).get(it['id'])
        st = self._community_status(it)
        busy = (self._community_busy or {}).get(it['id'])
        size = community.size_text(man['zip']['size']) if man and (man.get('zip') or {}).get('size') else ''
        mine = self._export_mine(it) if it.get('install') == 'export' else None
        prog = (self._export_now or {}).get('progress') if mine == 'now' else None
        if prog is not None and prog.phase != 'remove':
            busy = _('Making it: %d%%') % int(100 * prog.fraction())      # (the card says the rest)
        elif mine == 'next':
            busy = _('Next in line')
        elif mine == 'wait':
            busy = _('Waiting for the game to close')
        return st, (it.get('name') or it['id'], it.get('author') or '', it.get('subtitle') or '', size,
                    busy or _(SHORT.get(st, st)))

    def _community_table(self, page, items, picked):
        """Every item of the category a row, one under another (the page scrolls); the one picked selected."""
        from .browserui import table
        c = _c()
        f = tk.Frame(page, bg=c.BG)
        f.pack(fill='x', padx=20, pady=(0, 20))
        t = self._community_tree = table(f, self.root, ITEM_COLS, ITEM_DROP)
        t.pack(fill='x')
        for i, it in enumerate(items):
            st, values = self._community_row(it)
            t.insert('', 'end', iid=it['id'], image=self._row_img(st), values=values, tags=('odd',) if i % 2 else ())
        t.configure(height=len(items))
        t.selection_set(picked)
        t.bind('<<TreeviewSelect>>', lambda _e: self._community_row_picked())
        t.bind('<Double-1>', self._community_row_go)
        t.bind('<Return>', self._community_row_go)

    def community_pick(self, item_id):
        """Show that item over the list (its card), the list as it is."""
        it = next((x for x in self._items(self.community_cat) if x['id'] == item_id), None)
        t = getattr(self, '_community_tile', None)
        if it is None or t is None or not t.frame.winfo_exists():
            return
        (self.community_picks or {}).update({self.community_cat: item_id})
        self._community_tiles = {item_id: t}
        self._community_fill(t, it)
        tree = getattr(self, '_community_tree', None)
        if tree is not None and tree.exists(item_id) and tuple(tree.selection()) != (item_id,):
            tree.selection_set(item_id)

    def _community_row_picked(self):
        sel = self._community_tree.selection()
        if sel and sel[0] not in self._community_tiles:
            self.community_pick(sel[0])

    def _community_row_go(self, e=None):
        """A double click (or Enter): its card's first step, when it puts something in (never REMOVE or MANAGE)."""
        t = self._community_tree
        iid = t.identify_row(e.y) if e is not None and e.type == tk.EventType.ButtonPress else (t.selection() or [None])[0]
        it = next((x for x in self._items(self.community_cat) if x['id'] == iid), None)
        if it is None:
            return
        self.community_pick(iid)
        man = (self._community_man or {}).get(iid)
        st = self._community_status(it)
        if st == 'off':
            self.community_show(it)
        elif st == 'stale':
            self.community_export_rebuild(it) if it.get('install') == 'export' else self.community_manager(it, man)
        elif it.get('install') == 'export' and self._export_mine(it) is None and st in ('install', 'notool', 'nowrcg'):
            {'install': self.community_export, 'notool': self.community_find_tool,
             'nowrcg': lambda _it: self.community_find_wrcg()}[st](it)
        elif it.get('install') == 'manager' and st in ('install', 'ready'):
            self.community_manager(it, man)
        elif it.get('install') == 'link' and st == 'link':
            self._community_page_open(it)
        elif not it.get('install') and st in ('install', 'update'):
            self.community_install(it, man)

    # -------------------------------------------------------------- install / remove
    def _community_say(self, item_id, text, frac=None):
        """What the item's card says it is doing (None: nothing), and how far (0..1: a bar under it; None: no bar)."""
        if self._community_busy is None:
            self._community_busy = {}
        if getattr(self, '_community_frac', None) is None:
            self._community_frac = {}
        if text:
            self._community_busy[item_id] = text
            self._community_frac[item_id] = frac
        else:
            self._community_busy.pop(item_id, None)
            self._community_frac.pop(item_id, None)
        self._community_redraw(item_id)

    def community_install(self, it, man):
        game = self._community_game
        if not game or not man:
            return
        clash = community.clashes(game, man)
        force = False
        if clash:
            if not messagebox.askyesno('ACR Daily', _('Other converted stages are installed in the game (%s). Only one '
                                                      'set of converted stages works at a time, so installing %s takes them out.\n\n'
                                                      'Install it?') % (', '.join(clash[:4]) + (' …' if len(clash) > 4 else ''),
                                                                        it.get('name', it['id']))):
                return
            force = True
        if community.game_running():
            messagebox.showinfo('ACR Daily', CLOSE_GAME)
            return
        ui = _c().ui
        last = [None]
        # its steps: downloading, building it on this PC (a package made from the player's own game files: manifest
        # 'assemble'), putting it into the game; each with how far it is (the words and a bar on the card)
        steps = 3 if man.get('assemble') else 2

        def say(n, what, frac):
            pct = int(100 * min(1.0, max(0.0, frac)))
            if (n, pct) != last[0]:                    # (each percent: the card drawn again, not each megabyte)
                last[0] = (n, pct)
                ui(self.root, self._community_say, it['id'], _('Step %d of %d · %s') % (n, steps, what) + ' · %d%%' % pct,
                   frac)

        def progress(done, total):
            if total:
                say(1, _('downloading %s of %s') % (community.size_text(done), community.size_text(total)), done / total)
            else:
                ui(self.root, self._community_say, it['id'], _('Downloading %s…') % community.size_text(done))

        def step(which, frac):
            if which == 'build':
                say(2, _('building it on your PC'), frac)
            else:
                say(steps, _('putting it into the game'), frac)

        def go():
            try:
                path = community.download(man, progress=progress)
                community.install(game, man, path, force=force, progress=step)
                ui(self.root, self._community_done, it, None)
            except community.CommunityError as e:
                ui(self.root, self._community_done, it, e)
            except Exception as e:                     # (anything else: said, nothing half done is left as ours)
                ui(self.root, self._community_done, it, community.CommunityError('files', str(e)))
        self._community_say(it['id'], _('Starting…'))
        threading.Thread(target=go, daemon=True).start()

    def community_remove(self, it):
        game = self._community_game
        if not game:
            return
        if not messagebox.askyesno('ACR Daily', _('Take %s out of the game?') % it.get('name', it['id'])):
            return
        try:
            community.uninstall(game, it['id'])
        except community.CommunityError as e:
            messagebox.showinfo('ACR Daily', CLOSE_GAME if e.kind == 'running' else str(e))
        self._render_community()

    def _community_done(self, it, e):
        self._community_say(it['id'], None)
        if e is None and it.get('group') in stageswitch.GROUPS:
            self._community_show_group(it['group'], quiet=True)    # (just installed: shown, the other set parked)
        if e is None:
            messagebox.showinfo('ACR Daily', _('%s is installed. Start the game: it is in the rally selection.')
                                % it.get('name', it['id']))
        elif e.kind == 'running':
            messagebox.showinfo('ACR Daily', CLOSE_GAME)
        elif e.kind == 'build':
            messagebox.showinfo('ACR Daily', _('This package was made for another version of the game (%s). A package '
                                               'for yours is on its way.') % e.detail)
        elif e.kind == 'gamefiles':
            messagebox.showinfo('ACR Daily', _("%s is built from your game's own files, and yours are not the ones it "
                                               "was made from. Check the game's files in Steam (Properties › Installed "
                                               "Files › Verify), then install it again.") % it.get('name', it['id']))
        else:
            messagebox.showwarning('ACR Daily', _("Couldn't install %s: %s") % (it.get('name', it['id']), e))

    # -------------------------------------------------------------- other tools' stages (community.py)
    def _catalogue_stage_ids(self, data=None):
        """Every stage id of the catalogue's items (looked for in the game's packages)."""
        return [s.get('stageId') for cat in (data or self.community_data or {}).get('categories', [])
                for it in cat.get('items', []) for s in it.get('stages') or []]

    @staticmethod
    def _and(names):
        return names[0] if len(names) == 1 else _('%s and %s') % (', '.join(names[:-1]), names[-1])

    def _community_clash(self):
        """The tools whose stages are in the game, when there are more than one (only one tool's show), else []."""
        groups = community.pack_groups(self._items('tracks'), self._community_packs, self._community_game,
                                       getattr(self, '_community_switch', None))
        if len(groups) < 2:
            return []
        return [' / '.join(names) for names in groups.values()]

    def _other_tool_words(self, it, man, st):
        """Another tool's item: its last line, as it stands in this game (None: STATUS's)."""
        if it.get('install') == 'export':
            return self._export_words(it, st)
        if it.get('install') not in ('manager', 'link'):
            return None
        if st == 'stale':
            return STATUS['stale']
        tool = it.get('managerName') or _('its Stage Manager')
        words, kind = None, None
        if st == 'installed' and it['install'] == 'link':
            n, of = len(community.stages_in_game(it, self._community_packs)), len(it.get('stages') or [])
            words, kind = n_('%d of its %d stages is in your game.', '%d of its %d stages are in your game.', n) % (n, of), 'good'
        elif st == 'link' and len([t for t in it.get('tools') or [] if t.get('page')]) > 1:
            words, kind = LINK_TOOLS, 'info'
        elif st == 'installed':
            words, kind = _('Installed. %s updates or removes it: MANAGE opens it.') % tool, 'good'
        elif st == 'install' and man:
            words, kind = _('Not installed. INSTALL downloads it from %s (%s) and opens %s.') % (
                urllib.parse.urlsplit(man['zipUrl']).hostname or '', community.size_text(man['zip']['size']), tool), 'info'
        elif st == 'ready':
            words, kind = _('Downloaded. OPEN MANAGER starts %s: click Install there.') % tool, 'info'
        if words is None:
            return None
        build = self._community_build
        if man and man.get('acrBuild') and build and str(man['acrBuild']) != str(build):
            words += ' ' + _('Made for game build %s, yours is %s: %s says whether it works.') % (man['acrBuild'], build, tool)
        if st == 'installed' and self._community_clash():
            words += ' ' + _("Another tool's stages are in the game too: only one tool's show at a time.")
            kind = 'muted'
        return words, kind

    def _community_page_open(self, it, anchor=None):
        """GET IT / OPEN PAGE: the tool's page in the browser. A card more than one tool makes (its `tools`: WRC
        Generations' stages, by Stage Studio or Stage-Exporter) asks which first: a menu of them under anchor (its
        button), else at the mouse (a double click on its row), each with who made it, its stages and its site.
        -> the menu, or None."""
        tools = [t for t in it.get('tools') or [] if t.get('page')]
        if len(tools) < 2:
            page = tools[0]['page'] if tools else it.get('page')
            if page:
                webbrowser.open(page)
            return None
        c = _c()
        m = tk.Menu(self.root, tearoff=0, bg=c.PANEL, fg=c.SOFT, activebackground=c.ACC, activeforeground=c.WHITE,
                    font=(c.FONT, 10))
        for t in tools:
            host = (urllib.parse.urlsplit(t['page']).hostname or '').removeprefix('www.')
            words = [t.get('name') or host, _('by %s') % t['author'] if t.get('author') else '',
                     n_('%d stage', '%d stages', t['stages']) % t['stages'] if t.get('stages') else '', host]
            m.add_command(label='  ·  '.join(w for w in words if w), command=lambda u=t['page']: webbrowser.open(u))
        if anchor is not None and anchor.winfo_exists():
            x, y = anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height()
        else:
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()
        return m

    def community_manager(self, it, man):
        """An item installed by its own manager: INSTALL (download it, unpack it, open the manager), OPEN MANAGER, or
        MANAGE (the manager again: to update, change pace notes, remove; its download again first if it went)."""
        game = self._community_game
        if not game or not man:
            return
        if community.manager_exe(man):
            self._manager_open(it, man)
            return
        tool = it.get('managerName') or _('its Stage Manager')
        size = community.size_text(man['zip']['size'])
        host = urllib.parse.urlsplit(man['zipUrl']).hostname or ''
        if community.stages_in_game(it, self._community_packs):
            ask = _("%s comes with the stage's download, which isn't on this PC any more. Download it again (%s)?") % (tool, size)
        else:
            ask = _('%s comes from %s (%s to download, and about twice that in free space while it unpacks).\n\n'
                    'ACR Daily downloads it, checks it and opens %s, where you click Install.\n\nIts terms: %s\n\n'
                    'Download it?') % (it.get('name', it['id']), host, size, tool, it.get('terms') or '')
        if not messagebox.askyesno('ACR Daily', ask):
            return
        short = community.space_needed(man, game)
        if short:
            messagebox.showinfo('ACR Daily', '\n'.join(_('Not enough free space: %s more is needed in %s.') % (
                community.size_text(n), folder) for folder, n in short))
            return
        ui = _c().ui
        last = [-1]

        def progress(done, total):
            pct = 100 * done // total if total else done >> 24
            if pct != last[0]:
                last[0] = pct
                ui(self.root, self._community_say, it['id'], _('Downloading %s of %s…') % (
                    community.size_text(done), community.size_text(total)) if total else _('Downloading %s…')
                    % community.size_text(done))

        def unpacking(done, total):
            pct = 100 * done // total if total else 0
            if pct != last[0]:
                last[0] = pct
                ui(self.root, self._community_say, it['id'], _('Unpacking %d%%…') % pct)

        def go():
            try:
                path = community.download(man, progress=progress)
                last[0] = -1
                community.unpack(man, path, progress=unpacking)
                ui(self.root, self._manager_open, it, man)
            except community.CommunityError as e:
                ui(self.root, self._manager_failed, it, e)
            except Exception as e:                     # (anything else: said)
                ui(self.root, self._manager_failed, it, community.CommunityError('files', str(e)))
        self._community_say(it['id'], _('Starting…'))
        threading.Thread(target=go, daemon=True).start()

    def _manager_failed(self, it, e):
        self._community_say(it['id'], None)
        messagebox.showwarning('ACR Daily', _("Couldn't get %s: %s") % (it.get('name', it['id']), e))

    def _manager_open(self, it, man):
        """Its manager started; as it closes, the game's packages are looked at again."""
        tool = it.get('managerName') or _('its Stage Manager')
        self._community_say(it['id'], None)
        if community.game_running():
            messagebox.showinfo('ACR Daily', _('Close Assetto Corsa Rally first: %s changes nothing while the game runs.') % tool)
            return
        if (getattr(self, '_community_switch', None) or {}).get(it.get('group')) == 'off':
            try:                                          # (his files as he put them, before his manager looks)
                stageswitch.unpark(self._community_game, it['group'])
            except stageswitch.SwitchError as e:
                messagebox.showwarning('ACR Daily', _("Couldn't switch: %s") % e)
                return
        try:
            proc = community.open_manager(man)
        except community.CommunityError as e:
            messagebox.showwarning('ACR Daily', _("Couldn't open %s: %s") % (tool, e))
            return
        self._community_say(it['id'], _('%s is open: install, update or remove the stage there, then close it.') % tool)
        ui = _c().ui
        game, ids = self._community_game, self._catalogue_stage_ids()

        def wait():
            try:
                proc.wait()
            except Exception:
                pass
            ui(self.root, self._manager_closed, it, man, community.stage_packs(game, ids))
        threading.Thread(target=wait, daemon=True).start()

    def _manager_closed(self, it, man, packs):
        """Its manager closed: the game looked at again. Its download stays, asked nothing: the manager needs it to
        update or remove the stage, or change its pace notes."""
        self._community_packs = packs
        self._community_say(it['id'], None)
        if it.get('group') in stageswitch.GROUPS and community.stages_in_game(it, packs):
            self._set_built(it['group'])                            # (his manager made its list for this version)
            self._community_show_group(it['group'], quiet=True)     # (just installed or managed: shown)
            return
        self._community_switch = stageswitch.state(self._community_game)
        self._render_community()
        if getattr(self, 'home_view', False):
            self._render_home()

    # -------------------------------------------------------------- one set of stages shown (stageswitch.py)
    def _switchable(self):
        """The sets of stages in the game together (London's, WRC Generations', Sando Rally's): the ones a click can
        show alone."""
        sw = getattr(self, '_community_switch', None) or {}
        on = [g for g in SWITCH_NAMES if sw.get(g) == 'on']
        return on if len(on) > 1 else []

    def _stale_sets(self):
        """The sets hidden since a game update (their stage list made for the version before): kept in the settings."""
        if getattr(self, '_stage_stale', None) is None:
            self._stage_stale = set(settings.load().get(STALE_SETS) or [])
        return self._stage_stale

    def _set_built(self, group):
        """A set's stage list made for this game version (Stage Exporter's run, Sando's manager): no longer stale."""
        build = getattr(self, '_community_build', None)
        s = settings.load()
        builds = dict(s.get(STALE_BUILDS) or {})
        if build:
            builds[group] = str(build)
        stale = self._stale_sets()
        stale.discard(group)
        s[STALE_BUILDS], s[STALE_SETS] = builds, sorted(stale)
        settings.save(s)

    def _check_stale(self, game, build):
        """After a game update, the sets whose stage list was made for the version before (WRC Generations', Sando
        Rally's) are hidden: each list carries its own copy of the game's stage tables, and an old copy can hide or
        break the game's own stages, and the dailies on them. London's is taken out by community.guard. Their builds
        are kept (the first look: as they are); with the game open, looked at again next time."""
        if not game or not build:
            return
        s = settings.load()
        builds, stale = dict(s.get(STALE_BUILDS) or {}), self._stale_sets()
        sw, hid = getattr(self, '_community_switch', None) or {}, []
        for g in ('wrcg', 'sando'):
            if sw.get(g) != 'on' or g in stale:
                continue
            if not builds.get(g):
                builds[g] = str(build)
            elif builds[g] != str(build):
                try:
                    stageswitch.park(game, g)
                except stageswitch.SwitchError:
                    continue
                stale.add(g)
                hid.append(g)
        if builds != (s.get(STALE_BUILDS) or {}) or hid:
            s[STALE_BUILDS], s[STALE_SETS] = builds, sorted(stale)
            settings.save(s)
        if hid:
            ids = self._catalogue_stage_ids()
            self._community_packs = community.stage_packs(game, ids)
            self._community_switch = stageswitch.state(game)
            self._community_parked = stageswitch.parked_packs(game, ids)
            messagebox.showinfo('ACR Daily', _(
                "Assetto Corsa Rally was updated, so %s are hidden for now: their stage list was made for the version "
                "before and could hide the game's own stages. Rebuild them on COMMUNITY › TRACKS.") % self._and(
                [SWITCH_NAMES[g] for g in hid]))

    def community_export_rebuild(self, it):
        """REBUILD (WRC Generations' set, hidden since a game update): Stage Exporter makes its stage list again for this
        version from the stages it made (wr repack: a couple of minutes, no stage made again), and it is shown."""
        game, env = self._community_game, getattr(self, '_export_env', None) or {}
        if not game or not env.get('tool'):
            return
        if getattr(self, '_export_now', None) is not None:
            messagebox.showinfo('ACR Daily', _('Wait until %s is done, then switch.') % self._export_now['it'].get('name', ''))
            return
        if community.game_running():
            messagebox.showinfo('ACR Daily', CLOSE_GAME)
            return
        self._export_go(it, ['repack'], env, None, game)

    def community_show(self, it):
        """SHOW on a hidden one: its set in the game, the other parked (a second; nothing made again)."""
        if it.get('group') in stageswitch.GROUPS:
            self._community_show_group(it['group'])

    def _community_show_group(self, group, quiet=False):
        """Only this set of ours in the game. quiet: after an install (nothing said unless it can't)."""
        game = self._community_game
        if not game:
            return
        if not quiet and getattr(self, '_export_now', None) is not None:
            messagebox.showinfo('ACR Daily', _('Wait until %s is done, then switch.') % self._export_now['it'].get('name', ''))
            return
        try:
            stageswitch.show(game, group)
        except stageswitch.SwitchError as e:
            if not quiet:
                messagebox.showinfo('ACR Daily', CLOSE_GAME if e.kind == 'running' else _("Couldn't switch: %s") % e)
            return
        self._community_rescan()

    def _community_rescan(self):
        """The game's packages looked at again (after a switch: renames only, so at once) and the page drawn."""
        game, ids = self._community_game, self._catalogue_stage_ids()
        self._community_packs = community.stage_packs(game, ids)
        self._community_switch = stageswitch.state(game)
        self._community_parked = stageswitch.parked_packs(game, ids)
        self._render_community()
        if getattr(self, 'home_view', False):
            self._render_home()

    # -------------------------------------------------------------- stages made on this PC (stageexport.py)
    def _exporter(self, it):
        """The tool an item's INSTALL runs (the catalogue's `tools`), or None."""
        return ((self.community_data or {}).get('tools') or {}).get(it.get('exporter'))

    def _export_mine(self, it):
        """'now' (being made or taken out), 'wait' (to start once the game is closed), 'next' (waiting its turn),
        or None."""
        now, wait = getattr(self, '_export_now', None), getattr(self, '_export_waiting', None)
        if now is not None and now['it']['id'] == it['id']:
            return 'now'
        if wait is not None and wait['id'] == it['id']:
            return 'wait'
        if now is None and wait is None:
            return None
        return 'next' if any(x['id'] == it['id'] for x in getattr(self, '_export_queue', None) or []) else None

    def _export_ahead(self):
        """The stage being made, or waiting for the game to close, or None."""
        return (getattr(self, '_export_now', None) or {}).get('it') or getattr(self, '_export_waiting', None)

    def _export_set_env(self, env, attach=True):
        """What the two games and the tool are now (found tool kept in the settings); attach: a stage this app was making
        before it was closed, still being made, followed again."""
        self._export_env = env
        tool = env.get('tool')
        s = settings.load()
        if tool and s.get(stageexport.SETTING) != tool:
            s[stageexport.SETTING] = tool               # (found once: the next look starts there)
            settings.save(s)
        run = stageexport.current_run() if attach else None
        if run and getattr(self, '_export_now', None) is None:
            self._export_attach(run)

    def _export_words(self, it, st):
        """A stage made on this PC: its last line."""
        ex = self._exporter(it) or {}
        env = getattr(self, '_export_env', None) or {}
        mine = self._export_mine(it)
        if mine == 'next':
            return _('Next in line: it starts when %s is done.') % self._export_ahead().get('name', ''), 'info'
        if mine == 'wait':
            return _('Waiting for Assetto Corsa Rally to close: it starts by itself then.'), 'info'
        if st == 'stale':
            return STALE_WRCG, 'info'
        if st == 'installed':
            if env.get('tool') and it.get('slug') not in (env.get('pack') or []):
                words = _('In your game, from another copy of the export tool: take it out with that one.')
            else:
                words = _('Installed. REMOVE takes it out; the other stages stay.')
            if self._community_clash():
                words += ' ' + _("Another tool's stages are in the game too: only one tool's show at a time.")
                return words, 'muted'
            return words, 'good'
        if st == 'install':
            return _('Not installed. INSTALL makes it on your PC from your WRC Generations: about %d minutes, with the '
                     'game closed. You can keep using ACR Daily meanwhile.') % int(ex.get('minutes') or 40), 'info'
        return None

    def _export_busy_text(self, prog):
        words = '%s…  %d%%' % (EXPORT_PHASE.get(prog.phase, ''), int(100 * prog.fraction()))
        eta = prog.eta()
        if eta:
            words += '  ·  ' + _('about %s left') % _span(eta)
        return words

    # ---------------------------------------------- INSTALL ALL, and how far the stages being made are (a bar)
    def _export_strip(self, page, items):
        """Over the list: how many of WRC Generations' stages are in the game, INSTALL ALL (the ones that aren't, one
        after another) or STOP ALL, and while any is being made a bar: how far all of them are, the one being made
        (its step, how far), and the time left."""
        c = _c()
        k = page.winfo_fpixels('1i') / 96
        f = tk.Frame(page, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE2)
        f.pack(fill='x', padx=20, pady=(0, 12))
        top = tk.Frame(f, bg=c.PANEL)
        top.pack(fill='x', padx=14, pady=(10, 4))
        title = tk.Label(top, bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, 14), anchor='w')
        title.pack(side='left')
        count = tk.Label(top, bg=c.PANEL, fg=c.MUTED, font=(c.FONT, 10), anchor='w')
        count.pack(side='left', padx=(12, 0))
        bar = tk.Canvas(f, bg=c.PANEL, height=round(10 * k), highlightthickness=0, bd=0)
        words = tk.Label(f, bg=c.PANEL, fg=c.SOFT, font=(c.FONT, 10), anchor='w', justify='left')
        self._export_ui = {'frame': f, 'top': top, 'title': title, 'count': count, 'bar': bar, 'words': words,
                           'button': None, 'items': [x for x in items if x.get('install') == 'export'], 'k': k}
        bar.bind('<Configure>', lambda _e: self._export_bar_draw())
        self._export_strip_show()

    def _export_overall(self):
        """How far the stages being made are, all of them: {done, total, fraction, name, phase, cur, eta} or None."""
        now, wait = getattr(self, '_export_now', None), getattr(self, '_export_waiting', None)
        queue = getattr(self, '_export_queue', None) or []
        prog = (now or {}).get('progress')
        if now is not None and (prog is None or prog.phase == 'remove'):
            return None                                   # (one taken out: quick, said on its card)
        pending = (1 if now is not None or wait is not None else 0) + len(queue)
        if not pending:
            return None
        batch = getattr(self, '_export_batch', None) or {'done': 0, 'took': []}
        ex = next((self._exporter(x) for x in self._items('tracks') if x.get('install') == 'export'), None) or {}
        each = sum(batch['took']) / len(batch['took']) if batch['took'] else 60 * int(ex.get('minutes') or 40)
        cur = prog.fraction() if prog is not None else 0.0
        eta_now = prog.eta() if prog is not None else None
        eta = (eta_now if eta_now is not None else each * (1 - cur)) + each * (pending - 1)
        total = batch['done'] + pending
        ahead = self._export_ahead() or {}
        return {'done': batch['done'], 'total': total, 'fraction': (batch['done'] + cur) / total, 'cur': cur,
                'name': ahead.get('name', ''), 'phase': prog.phase if prog is not None else 'wait', 'eta': eta}

    def _export_strip_show(self):
        u = getattr(self, '_export_ui', None)
        if not u or not u['frame'].winfo_exists():
            return
        items = u['items']
        sts = {x['id']: self._community_status(x) for x in items}
        have = [x for x in items if sts[x['id']] in ('installed', 'off', 'stale')]
        hidden = [x for x in items if sts[x['id']] == 'off']
        stale = [x for x in items if sts[x['id']] == 'stale']
        todo = [x for x in items if sts[x['id']] == 'install' and not self._export_mine(x)]
        u['title'].configure(text='WRC GENERATIONS')
        u['count'].configure(text=_('%d of %d installed') % (len(have), len(items))
                             + ('   ·   ' + _('Hidden') if hidden or stale else ''))
        o = self._export_overall()
        if u['button'] is not None:
            u['button'].destroy()
            u['button'] = None
        if o is not None:
            u['button'] = self._btn(u['top'], _('STOP ALL'), self.community_export_stop_all, surface=_c().PANEL)
        elif stale:
            u['button'] = self._btn(u['top'], _('REBUILD') + '  ›', lambda: self.community_export_rebuild(stale[0]),
                                    primary=True, surface=_c().PANEL)
        elif hidden:
            u['button'] = self._btn(u['top'], _('SHOW') + '  ›', lambda: self.community_show(hidden[0]),
                                    primary=True, surface=_c().PANEL)
        elif todo:
            u['button'] = self._btn(u['top'], _('INSTALL ALL') + '  (%d)  ›' % len(todo), self.community_export_all,
                                    primary=True, surface=_c().PANEL)
        if u['button'] is not None:
            u['button'].pack(side='right')
        if o is None:
            u['bar'].pack_forget()
            u['words'].pack_forget()
            u['top'].pack_configure(pady=(10, 10))
            return
        u['top'].pack_configure(pady=(10, 4))
        u['bar'].pack(fill='x', padx=14, pady=(2, 4))
        u['words'].pack(fill='x', padx=14, pady=(0, 10))
        # (the step it is on is said on its card and its row: here only how far)
        parts = ['%s  %d%%' % (o['name'], int(100 * o['cur'])) if o['phase'] != 'wait' else
                 '%s: %s' % (o['name'], _('Waiting for the game to close'))]
        if o['total'] > 1:
            parts.append(_('stage %d of %d') % (o['done'] + 1, o['total']))
            parts.append(_('%d%% in all') % int(100 * o['fraction']))
        if o['eta']:
            parts.append(_('about %s left') % _span(o['eta']))
        u['words'].configure(text='   ·   '.join(parts))
        u['overall'] = o
        self._export_bar_draw()

    def _export_bar_draw(self):
        """The bar: all of them (green), the one being made over it (white, thin)."""
        u = getattr(self, '_export_ui', None)
        if not u or not u['bar'].winfo_exists() or not u.get('overall'):
            return
        cv, o, c = u['bar'], u['overall'], _c()
        w, h = max(cv.winfo_width(), 1), max(cv.winfo_height(), 1)
        cv.delete('all')
        cv.create_rectangle(0, 0, w, h, fill=c.LINE2, width=0)
        cv.create_rectangle(0, 0, round(w * o['fraction']), h, fill=COMMUNITY_COLOUR, width=0)
        if o['total'] > 1:                                 # (the stage being made: its share, how far)
            x0 = w * o['done'] / o['total']
            cv.create_rectangle(round(x0), h - max(2, h // 3), round(x0 + w * o['cur'] / o['total']), h,
                                fill=c.WHITE, width=0)

    def community_export_all(self):
        """INSTALL ALL: every WRC Generations stage not in the game, made one after another."""
        items = [x for x in self._items('tracks') if x.get('install') == 'export'
                 and self._community_status(x) == 'install' and not self._export_mine(x)]
        if not items:
            return
        ex = self._exporter(items[0]) or {}
        minutes = int(ex.get('minutes') or 40)
        if not messagebox.askyesno('ACR Daily', _(
                "Install the %d WRC Generations stages that aren't in your game yet? Each takes about %d minutes, so all "
                'of them take about %s, one after another, with the game closed. You can stop them at any time.') % (
                len(items), minutes, _span(60 * minutes * len(items)))):
            return
        if self._export_ahead() is None:
            self._export_batch = {'done': 0, 'took': []}
        for it in items:
            self.community_export(it)
            if self._export_ahead() is None:                # (it couldn't start: its terms said no, no room...)
                return
        self._export_strip_show()

    def community_export_stop_all(self):
        """STOP ALL: the one being made stops (the game keeps what it had), the ones waiting are taken off."""
        if not messagebox.askyesno('ACR Daily', _(
                'Stop making WRC Generations stages? The one being made stops (the game keeps the stages it had), and '
                'the ones waiting are taken off.')):
            return
        queue, self._export_queue = getattr(self, '_export_queue', None) or [], []
        for x in queue:
            self._community_redraw(x['id'])
        wait, self._export_waiting = getattr(self, '_export_waiting', None), None
        if wait is not None:
            self._community_redraw(wait['id'])
        state = getattr(self, '_export_now', None)
        if state is not None:
            state['stop'] = True
            if state.get('job') is not None:
                state['job'].cancel()
            self._community_say(state['it']['id'], _('Stopping…'))
        self._export_strip_show()

    def community_export(self, it):
        """INSTALL on a stage made on this PC: the two games and the tool there, Stage Exporter in it (the first time),
        the stage made and the pack installed; with one being made already, it waits its turn."""
        game, ex = self._community_game, self._exporter(it)
        env = getattr(self, '_export_env', None) or {}
        if not game or not ex:
            return
        if not env.get('wrcg'):
            self.community_find_wrcg()
            return
        if not env.get('tool') and not env.get('toolZip'):
            self.community_find_tool(it)
            return
        if self._export_mine(it):
            return
        if self._export_ahead() is not None:
            self._export_queue = (getattr(self, '_export_queue', None) or []) + [it]
            self._community_redraw(it['id'])
            return
        s = settings.load()
        if not s.get(stageexport.OK_SETTING):
            base = ex.get('base') or {}
            if not messagebox.askyesno('ACR Daily', _(
                    '%s is made on your PC from your own WRC Generations with %s (by %s) and %s %s. The first time, ACR '
                    'Daily gets %s from GitHub and sets it up. Each stage then takes about %d minutes, with the game '
                    'closed, and the PC works hard meanwhile.\n\nIts terms: %s\n\nMake it?') % (
                    it.get('name', it['id']), ex.get('name'), ex.get('author'), base.get('name', ''), base.get('version', ''),
                    ex.get('name'), int(ex.get('minutes') or 40), it.get('terms') or '')):
                return
            s[stageexport.OK_SETTING] = True
            settings.save(s)
        if community.game_running():                       # (it starts by itself once the game is closed)
            self._export_waiting = it
            self._community_redraw(it['id'])
            self.root.after(3000, self._export_poll_game)
            return
        self._export_go(it, ['export', it['slug']], env, ex, game)

    def _export_poll_game(self):
        it = getattr(self, '_export_waiting', None)
        if it is None:
            return
        if community.game_running():
            self.root.after(3000, self._export_poll_game)
            return
        self._export_waiting = None
        self.community_export(it)

    def community_export_remove(self, it):
        game = self._community_game
        env = getattr(self, '_export_env', None) or {}
        if not game or not env.get('tool'):
            return
        if it.get('slug') not in (env.get('pack') or []):
            messagebox.showinfo('ACR Daily', _('%s was put in the game by another copy of the export tool: take it out '
                                               'with that one.') % it.get('name', it['id']))
            return
        if getattr(self, '_export_now', None) is not None:
            messagebox.showinfo('ACR Daily', _('Wait until %s is done, then REMOVE.') % self._export_now['it'].get('name', ''))
            return
        if community.game_running():
            messagebox.showinfo('ACR Daily', CLOSE_GAME)
            return
        if not messagebox.askyesno('ACR Daily', _('Take %s out of the game?') % it.get('name', it['id'])):
            return
        self._export_go(it, ['remove', it['slug']], env, None, game)

    def _export_go(self, it, args, env, ex, game):
        """A run of Stage Exporter for it (in a thread): Stage Exporter put in first when making one."""
        prog = stageexport.Progress(it.get('slug'))
        if args[0] in ('remove', 'repack'):
            prog.phase = args[0]
        env = dict(env)
        state = self._export_now = {'it': it, 'job': None, 'progress': prog, 'stop': False, 't0': time.time(),
                                    'args': args}
        ui = _c().ui
        shown = [0.0, -1]
        ids = self._catalogue_stage_ids()

        def phase(name):
            prog.phase = name
            ui(self.root, self._community_say, it['id'], EXPORT_PHASE[name] + '…')

        def line(text):
            prog.feed(text)
            if args[0] != 'export':
                return
            now = time.time()
            if now - shown[0] >= 1.0:                    # (the card drawn again each second, not each line)
                shown[0] = now
                ui(self.root, self._community_say, it['id'], self._export_busy_text(prog))

        def unpacking(done, total):
            pct = 100 * done // total if total else 0
            if pct != shown[1]:
                shown[1] = pct
                ui(self.root, self._community_say, it['id'], '%s…  %d%%' % (EXPORT_PHASE['unpack'], pct))

        def go():
            err = None
            try:
                if not env.get('tool'):                  # (its zip, where downloads go: unpacked here first)
                    phase('unpack')
                    env['tool'] = stageexport.unpack_tool(env['toolZip'], unpacking)
                try:                                     # (Stage Exporter reads Paks as the game's own: no other set)
                    state['parked'] = stageswitch.park_others(game, 'wrcg')
                except stageswitch.SwitchError as e:
                    raise stageexport.ExportError('running' if e.kind == 'running' else 'export', str(e))
                if ex is not None:
                    stageexport.ensure_addon(env['tool'], ex, game, env['wrcg'], say=phase)
                if state['stop']:
                    raise stageexport.ExportError('cancelled')
                if args[0] == 'export':
                    phase('prep')
                watch = [env['tool'], os.path.join(game, 'acr', 'Content', 'Paks')]
                job = state['job'] = stageexport.start(env['tool'], args, line, watch)
                if state['stop']:
                    job.cancel()
                err = self._export_wait(job, game)
            except stageexport.ExportError as e:
                err = e
            except Exception as e:                       # (anything else: said)
                err = stageexport.ExportError('export', str(e))
            packs = community.stage_packs(game, ids)
            after = stageexport.environment(env.get('tool'), search=False, wrcg=env.get('wrcg'))
            ui(self.root, self._export_done, it, err, packs, after, state['job'].log if state['job'] else None)
        self._community_say(it['id'], EXPORT_PHASE[args[0]] + '…' if args[0] in ('remove', 'repack') else _('Starting…'))
        threading.Thread(target=go, daemon=True).start()

    @staticmethod
    def _export_wait(job, game):
        """None when it went through, else why not (stopped: the game's pack put back)."""
        ok = job.wait()
        if job.no_space is not None:                     # (a drive full: stopped, the game's pack put back)
            if job.cancelled:
                stageexport.restore_aside(game)
            return stageexport.ExportError('space', job.no_space)
        if job.cancelled:
            stageexport.restore_aside(game)
            return stageexport.ExportError('cancelled')
        if not ok:
            return stageexport.ExportError('export', ' / '.join(job.last()) or _('it stopped'))
        return None

    def _export_attach(self, run):
        """A stage this app started making before it was closed, still being made: followed again to its end."""
        slug = run['args'][1] if len(run['args']) > 1 else None
        it = next((x for x in self._items('tracks') if x.get('slug') == slug), None)
        if it is None:
            return
        prog = stageexport.Progress(slug)
        state = self._export_now = {'it': it, 'job': None, 'progress': prog, 'stop': False}
        ui = _c().ui
        game, ids = self._community_game, self._catalogue_stage_ids()
        tool, wrcg = (self._export_env or {}).get('tool'), (self._export_env or {}).get('wrcg')
        shown = [0.0]

        def line(text):
            prog.feed(text)
            now = time.time()
            if now - shown[0] >= 1.0:
                shown[0] = now
                ui(self.root, self._community_say, it['id'], self._export_busy_text(prog))

        def go():
            job = state['job'] = stageexport.Job(attach=run, on_line=line)
            err = self._export_wait(job, game)
            ui(self.root, self._export_done, it, err, community.stage_packs(game, ids),
               stageexport.environment(tool, search=False, wrcg=wrcg), job.log)
        threading.Thread(target=go, daemon=True).start()

    def _export_done(self, it, err, packs, env, log):
        state = getattr(self, '_export_now', None) or {}
        if err is not None and state.get('parked'):
            for g in state['parked']:                     # (it didn't go through: the sets shown before, back)
                try:
                    stageswitch.unpark(self._community_game, g)
                except stageswitch.SwitchError:
                    pass
            packs = community.stage_packs(self._community_game, self._catalogue_stage_ids())
        if err is None:
            self._set_built('wrcg')                               # (its list made for this game version)
            self._community_packs = packs
            self._community_show_group('wrcg', quiet=True)         # (made or taken out: its set shown)
            packs = self._community_packs
        if err is None and (state.get('args') or ['export'])[0] == 'export':
            batch = self._export_batch = getattr(self, '_export_batch', None) or {'done': 0, 'took': []}
            batch['done'] += 1
            if state.get('t0'):
                batch['took'].append(time.time() - state['t0'])
        self._export_now = None
        self._community_packs = packs
        self._export_set_env(env, attach=False)         # (a tool unpacked from its zip: kept)
        self._community_say(it['id'], None)
        queue = getattr(self, '_export_queue', None) or []
        if err is not None and err.kind not in ('cancelled',):
            self._export_queue = []
            for x in queue:
                self._community_say(x['id'], None)
            if err.kind == 'busy':
                messagebox.showinfo('ACR Daily', _('Stage Exporter is already working on this PC (its own window is '
                                                   'open, or a stage is still being made): let it finish, then try again.'))
            elif err.kind == 'space':
                messagebox.showwarning('ACR Daily', _('The drive of %s is full, so %s was stopped. Free some space there, '
                                                      'then INSTALL again.') % (err.detail, it.get('name', it['id'])))
            elif err.kind == 'running':
                messagebox.showinfo('ACR Daily', CLOSE_GAME)
            else:
                messagebox.showwarning('ACR Daily', _("Couldn't finish %s: %s") % (it.get('name', it['id']), err)
                                       + ('\n\n' + _('What happened is in %s.') % log if log else ''))
        elif queue:
            self._export_queue = queue[1:]
            self.community_export(queue[0])
            if self._export_ahead() is None:            # (it couldn't start: no room...)
                self._export_queue = []
        if self._export_ahead() is None:
            self._export_batch = None                   # (all done: the next INSTALL counts from one again)
        self._render_community()
        if getattr(self, 'home_view', False):
            self._render_home()

    def community_export_cancel(self, it):
        """CANCEL: one waiting its turn leaves the line; the one being made stops (the game keeps what it had)."""
        mine = self._export_mine(it)
        if mine == 'next':
            self._export_queue = [x for x in self._export_queue if x['id'] != it['id']]
            self._community_redraw(it['id'])
            return
        if mine == 'wait':                              # (not started yet: the next one waits in its place)
            self._export_waiting = None
            self._community_redraw(it['id'])
            queue = getattr(self, '_export_queue', None) or []
            if queue:
                self._export_queue = queue[1:]
                self._community_redraw(queue[0]['id'])
                self.community_export(queue[0])
            return
        if mine != 'now' or not messagebox.askyesno('ACR Daily', _('Stop %s? The game keeps the stages it had.')
                                                    % it.get('name', it['id'])):
            return
        state = self._export_now
        state['stop'] = True
        if state.get('job') is not None:
            state['job'].cancel()
        self._community_say(it['id'], _('Stopping…'))

    def community_find_tool(self, it=None):
        """FIND TOOL: the player shows where Sando's Stage Export Tool is: its .exe in its folder, or the zip it came in
        (unpacked into the app's folder; how far on the card). Kept in the settings."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, title=_("Sando Rally's Stage Export Tool, or its zip"),
                                          filetypes=[(_('Stage Export Tool, or its zip'),
                                                      (stageexport.TOOL_EXE, '*.zip')), (_('All files'), '*.*')])
        if not path:
            return
        if not path.lower().endswith('.zip'):
            tool = stageexport.tool_of(os.path.dirname(path)) or stageexport.tool_of(path)
            if not tool:
                messagebox.showwarning('ACR Daily', NO_TOOL)
                return
            self._export_tool_found(tool)
            return
        ui, key, last = _c().ui, (it or {}).get('id'), [-1]

        def unpacking(done, total):
            pct = 100 * done // total if total else 0
            if key and pct != last[0]:
                last[0] = pct
                ui(self.root, self._community_say, key, _('Unpacking %d%%…') % pct)

        def go():
            try:
                tool, err = stageexport.unpack_tool(path, unpacking), None
            except stageexport.ExportError as e:
                tool, err = None, e
            ui(self.root, self._export_tool_unpacked, key, tool, err)
        if key:
            self._community_say(key, _('Starting…'))
        threading.Thread(target=go, daemon=True).start()

    def _export_tool_unpacked(self, key, tool, err):
        if key:
            self._community_say(key, None)
        if err is not None:
            messagebox.showwarning('ACR Daily', NO_TOOL if err.kind == 'notool' else _("Couldn't unpack it: %s") % err)
            return
        self._export_tool_found(tool)

    def _export_tool_found(self, tool):
        env = dict(getattr(self, '_export_env', None) or {}, tool=tool, pack=stageexport.pack(tool))
        self._export_set_env(env)
        self._render_community()

    def community_find_wrcg(self):
        """FIND GAME: the player shows where WRC Generations is (one Steam and the Epic Games launcher don't list). Kept
        in the settings."""
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, mustexist=True, title=_('WRC Generations: its folder'))
        if not path:
            return
        if not stageexport.looks_like_wrcg(path) and not messagebox.askyesno('ACR Daily', _(
                "That folder doesn't look like WRC Generations: nothing in it has WRC in its name. Use it anyway?")):
            return
        path = os.path.normpath(path)
        s = settings.load()
        s[stageexport.WRCG_SETTING] = path
        settings.save(s)
        self._export_env = dict(getattr(self, '_export_env', None) or {}, wrcg=path)
        self._render_community()

    # -------------------------------------------------------------- LIVERIES (liveries.py)
    def _livery_list(self):
        """The liveries shown: the car picked, in the order picked."""
        items = [x for x in (self.liveries_data or {}).get('liveries') or [] if not self.livery_car or x.get('car') == self.livery_car]
        key = {'top': lambda x: (-(x.get('stars') or 0), -(x.get('votes') or 0), -(x.get('published') or 0)),
               'new': lambda x: -(x.get('published') or 0),
               'clicks': lambda x: (-(x.get('clicks') or 0), -(x.get('published') or 0))}[self.livery_sort]
        return sorted(items, key=key)

    def livery_filter(self, car=None, sort=None):
        if car is not None:
            self.livery_car = car
        if sort is not None:
            self.livery_sort = sort
        self._render_community()

    def _render_liveries(self, page):
        c = _c()
        k = page.winfo_fpixels('1i') / 96
        self._livery_tiles = {}
        if self.liveries_data is None:
            tk.Label(page, text=self.liveries_msg or _('Loading…'), bg=c.BG, fg=c.MUTED, font=(c.FONT, 10)).pack(anchor='w', padx=20)
            return
        data = self.liveries_data
        everyone = data.get('liveries') or []
        # the bar: the car, the order; the game's folder, publishing one (the website)
        bar = tk.Frame(page, bg=c.BG)
        bar.pack(fill='x', padx=20, pady=(0, 6))
        cars = sorted((x for x in data.get('cars') or [] if x.get('count') or x.get('id') == self.livery_car),
                      key=lambda x: x.get('name') or '')
        ids = [''] + [x['id'] for x in cars]
        pick = ttk.Combobox(bar, state='readonly', width=30,
                            values=[_('All cars (%d)') % len(everyone)] + ['%s (%d)' % (x['name'], x.get('count') or 0) for x in cars])
        pick.current(ids.index(self.livery_car) if self.livery_car in ids else 0)
        pick.bind('<<ComboboxSelected>>', lambda _e: self.livery_filter(car=ids[pick.current()]))
        pick.pack(side='left')
        order = ttk.Combobox(bar, state='readonly', width=18, values=[label for _k, label in LV_SORTS])
        order.current([key for key, _l in LV_SORTS].index(self.livery_sort))
        order.bind('<<ComboboxSelected>>', lambda _e: self.livery_filter(sort=LV_SORTS[order.current()][0]))
        order.pack(side='left', padx=(10, 0))
        self._livery_pickers = (pick, order)
        self._link(bar, _('Publish yours ›'), lambda: webbrowser.open(self.api.site + '/liveries#send')).pack(side='right')
        self._link(bar, _('Open the liveries folder'), self.livery_open_folder).pack(side='right', padx=(0, 18))
        tk.Label(page, text=_('INSTALL puts one into Documents\\My Games\\acr\\Liveries\\<car>: the game sees a new livery '
                 'when it starts, %d a car at most. Rate them, and publish yours, on the website.')
                 % liveries.PER_CAR, bg=c.BG, fg=c.MUTED, font=(c.FONT, 9), anchor='w', justify='left').pack(
            fill='x', padx=20, pady=(0, 12))
        items = self._livery_list()
        if not items:
            tk.Label(page, text=_('No liveries for this car yet.') if everyone else _('No liveries yet: publish the first one on '
                                                                          'the website!'), bg=c.BG, fg=c.MUTED, font=(c.FONT, 10)).pack(anchor='w', padx=20)
            return
        if self.livery_pick not in [lv['id'] for lv in items]:
            self.livery_pick = items[0]['id']
        pick = next(lv for lv in items if lv['id'] == self.livery_pick)
        grid = tk.Frame(page, bg=c.BG)                   # the one picked, in full
        grid.pack(fill='x', pady=(0, 12))
        t = tiles.TileRow(grid, 1, base=round(CARD_H * k)).add(tiles.Tile(grid, restyle=self._btn_style))
        self._livery_tile = t
        self._livery_tiles[pick['id']] = t
        self._livery_fill(t, pick)
        self._livery_table(page, items, pick['id'])

    def _livery_spec(self, t, lv):
        st = liveries.status(lv)
        busy = (self._livery_busy or {}).get(lv['id'])
        key = photos.fetch(lv.get('shot'), then=lambda: _c().ui(self.root, self._livery_redraw, lv['id']))
        info = [liveries.stars_text(lv), n_('%d download', '%d downloads', lv.get('clicks') or 0) % (lv.get('clicks') or 0)]
        if lv.get('hostName'):
            info.append(_('from %s') % lv['hostName'])
        words, kind = (busy, 'info') if busy else LV_STATUS[st]
        desc = ' '.join((lv.get('description') or '').split())
        if len(desc) > 150:
            desc = desc[:147].rstrip() + '…'
        if getattr(t, '_lv_links', None) is not None and getattr(t, '_lv_for', None) != lv['id']:
            for w in t._lv_links:                        # (the card shows another livery now: its own links)
                w.destroy()
            t._lv_links = None
        if getattr(t, '_lv_links', None) is None:      # (made once a livery: the card is drawn again and again)
            t._lv_for = lv['id']
            t._lv_links = [self._link(t.cv, '', lambda: self.livery_rate(lv)),
                           self._link(t.cv, _('ON THE WEBSITE'), lambda: webbrowser.open(self.api.site + '/liveries?car=%s' % lv.get('car')))]
        t._lv_links[0].configure(text=_('YOUR VOTE %s  ›') % ('★' * int(lv['mine'])) if lv.get('mine') else _('RATE IT  ›'))
        return st, {'photo': key or 'community', 'bottom': True, 'badge': (_('INSTALLED'), COMMUNITY_COLOUR) if st == 'installed' else None,
                    'chips': [lv.get('carName') or lv.get('car') or ''], 'title': lv.get('title', ''), 'sizes': (26, 23, 20),
                    'button': bool(st in LV_BUTTON and not busy),
                    'lines': [(_('by %s') % lv.get('author', ''), 'sub'), (desc, 'info'), ('   ·   '.join(info), 'muted'), (words, kind)],
                    'below': [t._lv_links]}

    def _livery_fill(self, t, lv):
        st, spec = self._livery_spec(t, lv)
        if t.button is not None:
            t.button.destroy()
            t.button = None
        if spec['button']:
            if st == 'installed':
                t.button = self._btn(t.cv, LV_BUTTON[st], lambda: self.livery_remove(lv))
            elif st == 'page':
                t.button = self._btn(t.cv, LV_BUTTON[st] + '  ›', lambda: self.livery_page(lv))
            else:
                t.button = self._btn(t.cv, LV_BUTTON[st] + '  ›', lambda: self.livery_install(lv), primary=True)
        t.render(spec, t._w or None)

    def _livery_redraw(self, livery_id):
        """Its card again if it is the one picked (its download's progress, its preview come, a vote), and its row."""
        t = (getattr(self, '_livery_tiles', None) or {}).get(livery_id)
        lv = next((x for x in (self.liveries_data or {}).get('liveries') or [] if x['id'] == livery_id), None)
        if self.community_view and t is not None and lv is not None and t.frame.winfo_exists():
            self._livery_fill(t, lv)
        tree = getattr(self, '_livery_tree', None)
        if lv is not None and tree is not None and tree.winfo_exists() and tree.exists(str(livery_id)):
            st, values = self._livery_row(lv)
            tree.item(str(livery_id), values=values, image=self._row_img(st))

    def _livery_row(self, lv):
        """A livery's row: its name, car, painter, stars, downloads, where it stands (short)."""
        st = liveries.status(lv)
        busy = (self._livery_busy or {}).get(lv['id'])
        return st, (lv.get('title') or '', lv.get('carName') or lv.get('car') or '', lv.get('author') or '',
                    liveries.stars_text(lv), lv.get('clicks') or 0, busy or _(SHORT.get(st, st)))

    def _livery_table(self, page, items, picked):
        from .browserui import table
        c = _c()
        f = tk.Frame(page, bg=c.BG)
        f.pack(fill='x', padx=20, pady=(0, 20))
        t = self._livery_tree = table(f, self.root, LV_COLS, LV_DROP)
        t.pack(fill='x')
        for i, lv in enumerate(items):
            st, values = self._livery_row(lv)
            t.insert('', 'end', iid=str(lv['id']), image=self._row_img(st), values=values, tags=('odd',) if i % 2 else ())
        t.configure(height=len(items))
        t.selection_set(str(picked))
        t.bind('<<TreeviewSelect>>', lambda _e: self._livery_row_picked())
        t.bind('<Double-1>', self._livery_row_go)
        t.bind('<Return>', self._livery_row_go)

    def _livery_of(self, iid):
        return next((x for x in (self.liveries_data or {}).get('liveries') or [] if str(x['id']) == str(iid)), None)

    def livery_pick_one(self, livery_id):
        """Show that livery over the list (its card), the list as it is."""
        lv = self._livery_of(livery_id)
        t = getattr(self, '_livery_tile', None)
        if lv is None or t is None or not t.frame.winfo_exists():
            return
        self.livery_pick = lv['id']
        self._livery_tiles = {lv['id']: t}
        self._livery_fill(t, lv)
        tree = getattr(self, '_livery_tree', None)
        if tree is not None and tree.exists(str(lv['id'])) and tuple(tree.selection()) != (str(lv['id']),):
            tree.selection_set(str(lv['id']))

    def _livery_row_picked(self):
        sel = self._livery_tree.selection()
        if sel and self.livery_pick is not None and sel[0] != str(self.livery_pick):
            self.livery_pick_one(sel[0])

    def _livery_row_go(self, e=None):
        """A double click (or Enter): INSTALL it (or DOWNLOAD: its page), never REMOVE."""
        t = self._livery_tree
        iid = t.identify_row(e.y) if e is not None and e.type == tk.EventType.ButtonPress else (t.selection() or [None])[0]
        lv = self._livery_of(iid)
        if lv is None:
            return
        self.livery_pick_one(iid)
        st = liveries.status(lv)
        if st == 'install':
            self.livery_install(lv)
        elif st == 'page':
            self.livery_page(lv)

    def _livery_say(self, livery_id, text):
        if self._livery_busy is None:
            self._livery_busy = {}
        if text:
            self._livery_busy[livery_id] = text
        else:
            self._livery_busy.pop(livery_id, None)
        self._livery_redraw(livery_id)

    def livery_open_folder(self):
        try:
            liveries.open_folder()
        except OSError as e:
            messagebox.showwarning('ACR Daily', _("Couldn't open the liveries folder: %s") % e)

    def livery_page(self, lv):
        """A link to a page (Overtake.gg, MEGA...): the browser, through the website (counted as a download)."""
        if lv.get('go'):
            webbrowser.open(lv['go'])
            lv['clicks'] = (lv.get('clicks') or 0) + 1
            self._livery_redraw(lv['id'])

    def livery_install(self, lv):
        ui = _c().ui
        last = [-1]
        cars = (self.liveries_data or {}).get('cars') or []
        game = self._community_game

        def progress(done, total):
            pct = 100 * done // total if total else done >> 22
            if pct != last[0]:
                last[0] = pct
                ui(self.root, self._livery_say, lv['id'], _('Downloading %s of %s…') % (
                    liveries.size_text(done), liveries.size_text(total)) if total else _('Downloading %s…')
                    % liveries.size_text(done))

        def go():
            try:
                path = liveries.download(lv, progress=progress)
                ui(self.root, self._livery_say, lv['id'], _('Unzipping…'))
                made = liveries.install(lv, path, cars, game=game)
                ui(self.root, self._livery_done, lv, made, None)
            except liveries.LiveryError as e:
                ui(self.root, self._livery_done, lv, [], e)
            except Exception as e:                     # (anything else: said; nothing half done is left as ours)
                ui(self.root, self._livery_done, lv, [], liveries.LiveryError('files', str(e)))
        self._livery_say(lv['id'], _('Starting…'))
        threading.Thread(target=go, daemon=True).start()

    def _livery_done(self, lv, made, e):
        self._livery_say(lv['id'], None)
        name = lv.get('title', '')
        if e is None:
            lv['clicks'] = (lv.get('clicks') or 0) + 1
            self._livery_redraw(lv['id'])
            where = '\n'.join('   ' + '\\'.join(p.replace('/', '\\').split('\\')[-2:]) for p in made)
            messagebox.showinfo('ACR Daily', _('%s is in your game:') % name + '\n%s\n\n%s' % (
                where, _('Restart Assetto Corsa Rally: it reads new liveries when it starts.') if community.game_running()
                else _('Start the game: pick the %s, it is among its liveries.') % (lv.get('carName') or _('car'))))
        elif e.kind == 'page':
            if messagebox.askyesno('ACR Daily', _("%s's link doesn't give the zip itself (%s).\n\nOpen it in your browser?")
                                   % (name, e.detail or _('a download page'))):
                webbrowser.open(lv.get('go') or self.api.site + '/liveries')
        elif e.kind == 'full':
            messagebox.showinfo('ACR Daily', _("Couldn't install %s: %s.") % (name, e.detail))
        elif e.kind == 'unpack':                       # (a .rar this Windows can't read: its page, by hand)
            if messagebox.askyesno('ACR Daily', _("%s comes as a .rar or .7z file, and Windows on this PC can't unpack it "
                                                  '(%s).\n\nOpen its page to download it by hand?') % (name, e.detail)):
                webbrowser.open(lv.get('go') or lv.get('link') or self.api.site + '/liveries')
        else:
            messagebox.showwarning('ACR Daily', _("Couldn't install %s: %s") % (name, e))

    def livery_remove(self, lv):
        if not messagebox.askyesno('ACR Daily', _('Take %s out of the game?') % lv.get('title', '')):
            return
        try:
            liveries.uninstall(lv['id'])
        except OSError as e:
            messagebox.showwarning('ACR Daily', _("Couldn't take it out: %s") % e)
        self._livery_redraw(lv['id'])

    def livery_rate(self, lv):
        """RATE: 1 to 5 stars from a menu at the mouse (signed in; never one's own)."""
        m = tk.Menu(self.root, tearoff=0)
        for n in (5, 4, 3, 2, 1):
            m.add_command(label='%s%s   %d' % ('★' * n, '☆' * (5 - n), n), command=lambda n=n: self.livery_vote(lv, n))
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def livery_vote(self, lv, stars):
        ui = _c().ui

        def go():
            try:
                r = self.api.livery_vote(lv['id'], stars)
            except Exception as e:
                ui(self.root, messagebox.showinfo, 'ACR Daily', _("Couldn't rate it: %s.") % (
                    _('sign in first (the driver panel)') if getattr(e, 'code', None) == 401 else e))
                return
            lv.update(votes=r.get('votes', lv.get('votes')), stars=r.get('stars', lv.get('stars')), mine=r.get('mine', stars))
            ui(self.root, self._livery_redraw, lv['id'])
        threading.Thread(target=go, daemon=True).start()
