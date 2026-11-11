"""The COMMUNITY page: tracks and cars made by the community (community.py, the server's src/community.js),
installed into the game in one click and taken out again.

The page: a photo across the top with what it is, the two categories (TRACKS, CARS: the one shown
underlined), and the category's items, each a card: its picture, name, what it is, who made it, the size of its
package, where it stands in this game (not installed, installed, an update, waiting for a package for this build of
the game) and its button. Installing downloads the package (shown as it comes), checks it, and puts it into the
game's ~mods folder; the game must be closed (it keeps its packages open). An item a time trial or a daily needs
(their `requires`) is installed from here: DRIVE sends the driver here when it is missing (ttui.py, app.py).
"""
import threading
import tkinter as tk
from tkinter import messagebox

from . import community, photos, tiles

CATEGORIES = (('tracks', 'TRACKS'), ('cars', 'CARS'))
COMMUNITY_COLOUR = '#30D158'
HEAD_H = 170                   # the photo across the top
CARD_H = 250                   # an item's card, at least
STATUS = {'nogame': ("Assetto Corsa Rally isn't found on this PC.", 'muted'),
          'unavailable': ('Coming soon: its package is being made.', 'muted'),
          'install': ('Not installed.', 'info'),
          'installed': ('Installed: in the game\'s rally selection.', 'good'),
          'update': ('An update is ready.', 'good'),
          'wait': ('The game has been updated: a package for this version is on its way.', 'muted')}
BADGE = {'installed': ('INSTALLED', '#30D158'), 'update': ('UPDATE', '#1F6FD6'), 'unavailable': ('SOON', '#5A5A63')}
BUTTON = {'install': 'INSTALL', 'update': 'UPDATE', 'installed': 'REMOVE'}


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
        if messagebox.askyesno('ACR Daily', '%s is on %s, a community track that isn\'t in your game yet.\n\nInstall it '
                               'from COMMUNITY now? (One click; then DRIVE again.)' % (what, self.community_name(need))):
            self.open_community('tracks')
        return True

    def community_select(self, cat):
        if cat != self.community_cat:
            self.community_cat = cat
            self._render_community()

    # -------------------------------------------------------------- the list
    def refresh_community(self):
        """The list from the server, each item's package from GitHub, the game's folder and build (in a thread)."""
        def go():
            msg, data, mans = '', None, {}
            try:
                data = community.catalog(self.api)
            except Exception as e:                   # (no internet, the server down: said on the page)
                msg = "Couldn't load the community's content (%s)." % e
            for cat in (data or {}).get('categories', []):
                for it in cat.get('items', []):
                    try:
                        mans[it['id']] = community.manifest(it)
                    except community.CommunityError:
                        mans[it['id']] = None
            try:
                from .modinstall import game_dir
                game = game_dir()
            except Exception:
                game = None
            build = community.game_build(game)
            gone = community.guard(game, build) if game else []
            _c().ui(self.root, self._set_community, data, mans, msg, game, build, gone)
        threading.Thread(target=go, daemon=True).start()

    def _set_community(self, data, mans, msg, game, build, gone):
        if data is not None:
            self.community_data = data
        self._community_man = dict(self._community_man or {}, **mans)
        self.community_msg = msg
        self._community_game, self._community_build = game, build
        if gone:
            names = {it['id']: it.get('name') or it['id'] for cat, _l in CATEGORIES for it in self._items(cat)}
            messagebox.showinfo('ACR Daily', 'Assetto Corsa Rally has been updated, so these were taken out of the '
                                'game until a package for this version is up: %s.' % ', '.join(names.get(g, g) for g in gone))
        if self.community_view:
            self._render_community()
        if getattr(self, 'home_view', False):
            self._render_home()                      # (its COMMUNITY tile: what is new)

    def _items(self, cat):
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
        head.render({'photo': 'community', 'bottom': True, 'title': 'COMMUNITY', 'sizes': (34, 30, 26), 'button': False,
                     'lines': [('Tracks and cars made by the community', 'sub'),
                               ('Installed into the game in one click, taken out as easily. Find them in the game\'s '
                                'rally selection.', 'info')]})
        # the categories: the one shown underlined
        row = tk.Frame(page, bg=c.BG)
        row.pack(fill='x', padx=20, pady=(0, 12))
        for cat, label in CATEGORIES:
            on = cat == self.community_cat
            f = tk.Frame(row, bg=c.BG, cursor='hand2')
            f.pack(side='left', padx=(0, 22))
            l = tk.Label(f, text='%s  %d' % (label, len(self._items(cat))), bg=c.BG, fg=c.WHITE if on else c.FG2,
                         font=(c.FONT_C, 14), cursor='hand2')
            l.pack()
            tk.Frame(f, bg=COMMUNITY_COLOUR if on else c.BG, height=3).pack(fill='x')
            for x in (f, l):
                x.bind('<Button-1>', lambda _e, kk=cat: self.community_select(kk))
        # the category's items: cards two by two
        if self.community_data is None:
            tk.Label(page, text=self.community_msg or 'Loading…', bg=c.BG, fg=c.MUTED, font=(c.FONT, 10)).pack(
                anchor='w', padx=20)
            return
        items = self._items(self.community_cat)
        if not items:
            label = dict(CATEGORIES)[self.community_cat].lower()
            tk.Label(page, text='No %s yet. They will be here as the community makes them.' % label, bg=c.BG,
                     fg=c.MUTED, font=(c.FONT, 10)).pack(anchor='w', padx=20)
            return
        grid = tk.Frame(page, bg=c.BG)
        grid.pack(fill='x', pady=(0, 20))
        rows = tiles.TileRow(grid, 2, base=round(CARD_H * k))
        for it in items:
            t = rows.add(tiles.Tile(grid, restyle=self._btn_style))
            self._community_tiles[it['id']] = t
            self._community_fill(t, it)

    def _community_spec(self, it):
        """An item's card: its picture behind, where it stands in this game (badge, last line), its button."""
        man = (self._community_man or {}).get(it['id'])
        st = community.status(it, man, self._community_game, self._community_build)
        busy = (self._community_busy or {}).get(it['id'])
        info = ['by %s' % it['author']] if it.get('author') else []
        if man and (man.get('zip') or {}).get('size'):
            info.append(community.size_text(man['zip']['size']))
        if man and man.get('version'):
            info.append('version %s' % man['version'])
        key = photos.fetch(it.get('image'), then=lambda: _c().ui(self.root, self._community_redraw, it['id']))
        words, kind = (busy, 'info') if busy else STATUS[st]
        own = it.get('photo') if photos.has(it.get('photo')) else None     # (bundled with the app: London's render)
        return st, {'photo': key or own or 'community', 'bottom': True, 'badge': BADGE.get(st), 'title': it.get('name', ''),
                    'sizes': (26, 23, 20), 'button': bool(st in BUTTON and not busy),
                    'lines': [(it.get('subtitle'), 'sub'), (it.get('description'), 'info'),
                              ('   ·   '.join(info), 'muted'), (words, kind)]}

    def _community_fill(self, t, it):
        st, spec = self._community_spec(it)
        if t.button is not None:
            t.button.destroy()
            t.button = None
        if spec['button']:
            if st == 'installed':
                t.button = self._btn(t.cv, BUTTON[st], lambda: self.community_remove(it))
            else:
                t.button = self._btn(t.cv, BUTTON[st] + '  ›', lambda: self.community_install(
                    it, (self._community_man or {}).get(it['id'])), primary=True)
        t.render(spec, t._w or None)

    def _community_redraw(self, item_id):
        """One card again (its download's progress, its picture come): the page's others as they are."""
        t = (getattr(self, '_community_tiles', None) or {}).get(item_id)
        it = next((x for cat, _l in CATEGORIES for x in self._items(cat) if x['id'] == item_id), None)
        if self.community_view and t is not None and it is not None and t.frame.winfo_exists():
            self._community_fill(t, it)

    # -------------------------------------------------------------- install / remove
    def _community_say(self, item_id, text):
        if self._community_busy is None:
            self._community_busy = {}
        if text:
            self._community_busy[item_id] = text
        else:
            self._community_busy.pop(item_id, None)
        self._community_redraw(item_id)

    def community_install(self, it, man):
        game = self._community_game
        if not game or not man:
            return
        clash = community.clashes(game, man)
        force = False
        if clash:
            if not messagebox.askyesno('ACR Daily', 'Other converted stages are installed in the game (%s). Only one '
                                       'set of converted stages works at a time, so installing %s takes them out.\n\n'
                                       'Install it?' % (', '.join(clash[:4]) + (' …' if len(clash) > 4 else ''),
                                                        it.get('name', it['id']))):
                return
            force = True
        if community.game_running():
            messagebox.showinfo('ACR Daily', 'Close Assetto Corsa Rally first: it keeps its packages open while it runs.')
            return
        ui = _c().ui
        last = [-1]

        def progress(done, total):
            pct = 100 * done // total if total else done >> 24
            if pct != last[0]:                         # (each percent: the card drawn again, not each megabyte)
                last[0] = pct
                ui(self.root, self._community_say, it['id'], 'Downloading %s of %s…' % (
                    community.size_text(done), community.size_text(total)) if total else 'Downloading %s…'
                    % community.size_text(done))

        def go():
            try:
                path = community.download(man, progress=progress)
                ui(self.root, self._community_say, it['id'], 'Installing…')
                community.install(game, man, path, force=force)
                ui(self.root, self._community_done, it, None)
            except community.CommunityError as e:
                ui(self.root, self._community_done, it, e)
            except Exception as e:                     # (anything else: said, nothing half done is left as ours)
                ui(self.root, self._community_done, it, community.CommunityError('files', str(e)))
        self._community_say(it['id'], 'Starting…')
        threading.Thread(target=go, daemon=True).start()

    def community_remove(self, it):
        game = self._community_game
        if not game:
            return
        if not messagebox.askyesno('ACR Daily', 'Take %s out of the game?' % it.get('name', it['id'])):
            return
        try:
            community.uninstall(game, it['id'])
        except community.CommunityError as e:
            messagebox.showinfo('ACR Daily', 'Close Assetto Corsa Rally first: it keeps its packages open while it '
                                'runs.' if e.kind == 'running' else str(e))
        self._render_community()

    def _community_done(self, it, e):
        self._community_say(it['id'], None)
        if e is None:
            messagebox.showinfo('ACR Daily', '%s is installed. Start the game: it is in the rally selection.'
                                % it.get('name', it['id']))
        elif e.kind == 'running':
            messagebox.showinfo('ACR Daily', 'Close Assetto Corsa Rally first: it keeps its packages open while it runs.')
        elif e.kind == 'build':
            messagebox.showinfo('ACR Daily', 'This package was made for another version of the game (%s). A package '
                                'for yours is on its way.' % e.detail)
        else:
            messagebox.showwarning('ACR Daily', "Couldn't install %s: %s" % (it.get('name', it['id']), e))
