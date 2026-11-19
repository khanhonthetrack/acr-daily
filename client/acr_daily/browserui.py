"""The RALLIES tab as a server browser (from 0.1.6), mixed into App (app.py) beside the LEAGUES view (leagueui.py).

Every rally and championship round the driver can drive or has driven lately, in one list that scrolls, as a game's
server browser: what it is (a bar in its colour: a championship's round in the leagues' blue, a rally in pink), its
name, its championship or maker, location, car, stages, how many have driven it, and where the driver is in it. The
one picked shows in full over the list (leagueui._render_leagues: its card, DRIVE); a click on a row picks one, a
double click (or Enter) drives it. ALL / CHAMPIONSHIPS / RALLIES narrow it; a click on a heading sorts by it. Public
rallies are in everyone's list (server 0033), so it can be long: before it, the window listed four events and the
rest were only on the website, where nothing is driven (2026-11-15).

The championships the driver isn't in are rows too, public and private (GET /api/leagues: `champ_rows`, leagues.py,
leagueui.refresh_leagues), with how many rounds they have and drivers in them: picked, the card over the list offers
JOIN (a public one: a double click joins, asked first) or ASK TO JOIN (a private one: its admins accept drivers, server
0043); joined, their rounds are in the list as any other. The ones the driver runs are rows too, with the requests to
join waiting in them (the card: ACCEPT / DECLINE, ADD A DRIVER). A private rally without its code is a row as any rally,
`locked`: its DRIVE asks for the code. The list's look (browser_style, bar_images) is the COMMUNITY page's lists' too
(communityui.py).
"""
import time
import tkinter as tk
from tkinter import ttk

from . import i18n
from .i18n import N_, _, n_

CHAMP, RALLY = '#5BA8FF', '#FF7AC6'          # (the website's: server src/leaguepages.js .k-champ / .k-rally)
COLOUR = {'league': CHAMP, 'event': RALLY}
FILTERS = (('all', N_('ALL')), ('league', N_('CHAMPIONSHIPS')), ('event', N_('RALLIES')))
# (column, heading, width at 96 dpi, anchor, stretches)
COLS = (('name', N_('EVENT'), 190, 'w', True), ('of', N_('CHAMPIONSHIP'), 160, 'w', True),
        ('rally', N_('LOCATION'), 96, 'w', False), ('car', N_('CAR'), 150, 'w', False), ('ss', 'SS', 34, 'e', False),
        ('drivers', N_('DRIVERS'), 72, 'center', False), ('state', N_('STATUS'), 170, 'w', True))
DROP = ('of', 'car', 'drivers', 'rally', 'ss')     # (narrow: these go first; the event and where I am in it stay)


def _c():
    from . import app
    return app


def kind_of(ev):
    """'event' (a rally, anyone's) or 'league' (a championship's round, or a public championship to join) for the
    RALLIES tab."""
    return 'event' if ev.get('kind') == 'event' else 'league'


def is_champ(x):
    """A championship to join, to ask to join or that I run (a row of the list: not an event)."""
    return bool(x.get('_champ'))


def champ_iid(x):
    return 'L:%s' % x['id']


def browser_style(root):
    """The server browser's look (the RALLIES and CUPS lists, the COMMUNITY page's): set once a window."""
    if getattr(root, '_browser_styled', False):
        return
    root._browser_styled = True
    c = _c()
    k = root.winfo_fpixels('1i') / 96
    st = ttk.Style(root)
    st.configure('Browser.Treeview', background=c.BG, fieldbackground=c.BG, foreground=c.SOFT, rowheight=round(30 * k),
                 font=('Segoe UI', 10), borderwidth=0, relief='flat', indent=0)
    st.map('Browser.Treeview', background=[('selected', '#26262C')], foreground=[('selected', c.WHITE)])
    st.layout('Browser.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
    # a row: its kind's bar, no open/close arrow before it (a flat list)
    st.layout('Browser.Treeview.Item', [('Treeitem.padding', {'sticky': 'nswe', 'children': [
        ('Treeitem.image', {'side': 'left', 'sticky': ''}), ('Treeitem.focus', {'side': 'left', 'sticky': '', 'children': [
            ('Treeitem.text', {'side': 'left', 'sticky': ''})]})]})])
    st.configure('Browser.Vertical.TScrollbar', background=c.PANEL2, troughcolor=c.BG, bordercolor=c.BG, arrowcolor=c.FG2,
                 lightcolor=c.PANEL2, darkcolor=c.PANEL2, gripcount=0)
    st.map('Browser.Vertical.TScrollbar', background=[('active', c.LINE2)])


def bar_images(root, colours):
    """{key: a bar in its colour}, for a row's first column (what it is, at a glance)."""
    k = root.winfo_fpixels('1i') / 96
    w, h = round(4 * k), round(18 * k)
    out = {}
    for key, colour in colours.items():
        img = tk.PhotoImage(master=root, width=w, height=h)
        img.put(colour, to=(0, 0, w, h))
        out[key] = img
    return out


def fit_columns(tree, cols, drop):
    """The columns that fit the table's width: on a narrow window those in `drop` go, the first first, until the rest
    fit (squeezed to 85 % of their width at most), so the name and the status always show (the columns on the right
    were cut off instead, the status among them: a UI review, Nov 2026). Again whenever the table is resized."""
    def fit(_e=None):
        width = tree.winfo_width()
        if width <= 1:
            return
        k = tree.winfo_fpixels('1i') / 96
        want = {key: w * k for key, _h, w, _a, _s in cols}
        shown = [x[0] for x in cols]
        room = width - 18 * k
        for key in drop:
            if sum(want[x] for x in shown) * 0.85 <= room:
                break
            shown.remove(key)
        if tuple(tree.cget('displaycolumns')) != tuple(shown):
            tree.configure(displaycolumns=shown)
    tree.bind('<Configure>', fit, add='+')
    return fit


def table(parent, root, cols, drop=()):
    """A server browser's table in parent: columns (key, heading, width at 96 dpi, anchor, stretches), every other row
    striped ('odd'). No scrollbar of its own: as tall as its rows (fill sets it), the page around it scrolls. drop: the
    columns that go on a narrow window, the first first (fit_columns)."""
    browser_style(root)
    k = root.winfo_fpixels('1i') / 96
    t = ttk.Treeview(parent, columns=[x[0] for x in cols], show='tree headings', style='Browser.Treeview',
                     selectmode='browse', height=1)
    t.column('#0', width=round(14 * k), minwidth=round(14 * k), stretch=False)
    for key, heading, w, anchor, stretch in cols:
        t.heading(key, text=_(heading), anchor=anchor)
        t.column(key, width=round(w * k), minwidth=round(36 * k), anchor=anchor, stretch=stretch)
    t.tag_configure('odd', background=_c().STRIPE)
    if drop:
        fit_columns(t, cols, drop)
    return t


class BrowserUI:
    browse_box = None
    browse_tree = None
    _browse_filter = 'all'
    _browse_sort = None                       # (column, descending) or None: the app's order (leagueui.listed_order)
    champ_rows = ()                           # the championships I'm not in, and the ones I run (leagues.champ_rows)
    champ_sel = None                          # the one picked (its id), shown over the list instead of an event

    # -------------------------------------------------------------- layout
    def _build_browser(self, box):
        """The list under the event picked: built once, filled by _render_browser (shown on the RALLIES tab only)."""
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        browser_style(self.root)
        f = self.browse_box = tk.Frame(box, bg=c.BG)
        head = tk.Frame(f, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(16, 8))
        self._browse_tabs = {}
        for key, label in FILTERS:
            l = tk.Label(head, text=_(label), bg=c.BG, fg=c.FG2, font=(c.FONT_C, 11), cursor='hand2')
            l.pack(side='left', padx=(0, 20))
            l.bind('<Button-1>', lambda _e, k=key: self.browse_filter(k))
            self._browse_tabs[key] = l
        self._link(head, _('Create a rally on the website  ›'), lambda: self.open_page('/rallies/new')).pack(side='right')
        for kind, text in (('event', N_('RALLY')), ('league', N_('CHAMPIONSHIP'))):      # (the legend, right to left)
            tk.Label(head, text='■ ' + i18n.spaced(_(text)), bg=c.BG, fg=COLOUR[kind], font=(c.FONT, 7, 'bold')).pack(side='right', padx=(0, 16))
        body = tk.Frame(f, bg=c.BG)
        body.pack(fill='both', expand=True, padx=20, pady=(0, 12))
        t = self.browse_tree = ttk.Treeview(body, columns=[x[0] for x in COLS], show='tree headings', style='Browser.Treeview',
                                            selectmode='browse')
        t.column('#0', width=round(14 * k), minwidth=round(14 * k), stretch=False)
        for key, heading, w, anchor, stretch in COLS:
            t.heading(key, text=_(heading) if heading != 'SS' else 'SS', anchor=anchor, command=lambda k=key: self.browse_sort(k))
            t.column(key, width=round(w * k), minwidth=round(36 * k), anchor=anchor, stretch=stretch)
        sb = ttk.Scrollbar(body, orient='vertical', command=t.yview, style='Browser.Vertical.TScrollbar')
        t.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        t.pack(side='left', fill='both', expand=True)
        t.tag_configure('odd', background=c.STRIPE)
        t.tag_configure('running', foreground=c.GOOD)
        t.tag_configure('done', foreground=c.MUTED)
        t.tag_configure('soon', foreground=c.FG2)
        t.tag_configure('join', foreground=CHAMP)
        self._kind_img = bar_images(self.root, COLOUR)   # (a bar in the kind's colour, in the row's first column)
        fit_columns(t, COLS, DROP)
        t.bind('<<TreeviewSelect>>', self._browse_picked)
        t.bind('<Double-1>', self._browse_drive)
        t.bind('<Return>', self._browse_drive)
        self._browse_rows = []

    # -------------------------------------------------------------- what it lists
    def _browse_values(self, ev, now):
        """A row: name, championship (or 'Rally by <maker>'), location, car, stages, drivers, where I am in it. A
        championship: its name, who runs it, its rounds and drivers, JOIN (or what asking to join it is at)."""
        if is_champ(ev):
            return (ev.get('name') or '', _('Official championship') if ev.get('official') else
                    _('Championship by %s') % (ev.get('owner') or '?'), '', '', ev.get('events') or 0,
                    ev.get('members') or 0, self._champ_state(ev))
        entry = ev.get('entry') or {}
        of = _('Rally by %s') % (ev.get('organizer') or '?') if kind_of(ev) == 'event' else (ev.get('league') or '')
        car = ev.get('car') or entry.get('car') or ev.get('carClass') or ''
        return (ev['name'], of, i18n.data(ev.get('rally') or ''), car, len(ev.get('stages') or ()),
                ev.get('drivers') if ev.get('drivers') is not None else '', self._browse_state(ev, now))

    @staticmethod
    def _champ_state(x):
        """A championship's row: JOIN and when it can be driven (a public one), ASK TO JOIN (a private one, server 0043),
        asked, declined (until when), or the requests waiting in one I run."""
        state = x.get('_state') or 'join'
        if state == 'run':
            k = len(x.get('_requests') or ())
            return n_('%d request to join', '%d requests to join', k) % k if k else \
                (_('You run it') if x.get('_role') == 'owner' else _('You are an admin'))
        if state == 'asked':
            return _('Asked to join')
        if state == 'declined':
            return _('Declined · ask again %s') % i18n.strftime(_('%a %d %b'), time.localtime((x.get('_again') or 0) / 1000))
        if state == 'ask':
            return _('Private · ask to join')
        n = x.get('openEvents') or 0
        if n:
            return n_('Join · %d round open', 'Join · %d rounds open', n) % n
        if x.get('nextOpens'):
            return _('Join · next round %s') % i18n.strftime(_('%a %d %b'), time.localtime(x['nextOpens'] / 1000))
        return _('Join')

    def _browse_state(self, ev, now):
        """Where I am in it, short (the card over the list says it in full)."""
        from .leagueui import _left
        from .judge import fmt_ms
        entry = ev.get('entry') or {}
        st = entry.get('status')
        if st == 'running':
            return _('In progress · SS%d of %d') % (entry.get('done', 0) + 1, len(ev.get('stages') or ()))
        if st == 'finished':
            return _('Finished · %s') % fmt_ms(entry.get('totalMs') or 0)
        if st in ('dnf', 'dsq'):
            return _('DNF') if st == 'dnf' else _('DSQ')
        if ev.get('status') == 'closed':
            return _('CLOSED')
        if ev.get('locked'):                      # a private rally: its code first (server 0043)
            return _('Private · enter its code')
        if ev.get('status') == 'upcoming':
            return _('Opens %s') % i18n.strftime(_('%a %d %b %H:%M'), time.localtime(ev['opens'] / 1000))
        return _('Closes in %s') % _left(ev['closes'] - now)

    def _browse_key(self, col):
        """How a column sorts: names as text, numbers as numbers, STATUS by when each closes."""
        i = [x[0] for x in COLS].index(col)
        if col == 'state':
            return lambda ev: (ev.get('nextOpens') or 9e15) if is_champ(ev) else ev['closes']
        if col == 'drivers':
            return lambda ev: (ev.get('members') if is_champ(ev) else ev.get('drivers')) or 0
        if col == 'ss':
            return lambda ev: (ev.get('events') or 0) if is_champ(ev) else len(ev.get('stages') or ())
        return lambda ev: str(self._browse_values(ev, 0)[i]).casefold()

    def _render_browser(self, evs, now):
        """Fill the list with evs (the tab's events, in the app's order) and the championships after them (to join, to
        ask to join, or mine to run), as the filter and the sort say; the one picked selected; the scroll kept."""
        t = self.browse_tree
        if t is None:
            return
        c = _c()
        evs = list(evs) + [dict(x, _champ=True) for x in self.champ_rows or ()]
        counts = {'all': len(evs), 'league': sum(kind_of(e) == 'league' for e in evs), 'event': sum(kind_of(e) == 'event' for e in evs)}
        for key, label in FILTERS:                    # the filter shown white, with how many each has
            self._browse_tabs[key].configure(text='%s  %d' % (_(label), counts[key]),
                                             fg=c.WHITE if key == self._browse_filter else c.FG2)
        rows = [e for e in evs if self._browse_filter == 'all' or kind_of(e) == self._browse_filter]
        if self._browse_sort:
            col, desc = self._browse_sort
            rows = sorted(rows, key=self._browse_key(col), reverse=desc)
        for key, heading, *_rest in COLS:             # (the sorted column marked)
            mark = ('  ▼' if self._browse_sort[1] else '  ▲') if self._browse_sort and self._browse_sort[0] == key else ''
            t.heading(key, text=(_(heading) if heading != 'SS' else 'SS') + mark)
        top = t.yview()[0]
        t.delete(*t.get_children())
        for i, ev in enumerate(rows):
            st, status = (ev.get('entry') or {}).get('status'), ev.get('status')
            tag = ('join' if is_champ(ev) else 'running' if st == 'running' else 'done' if st in ('finished', 'dnf', 'dsq')
                   or status == 'closed' else 'soon' if status == 'upcoming' else '')
            t.insert('', 'end', iid=champ_iid(ev) if is_champ(ev) else str(ev['id']), image=self._kind_img[kind_of(ev)],
                     values=self._browse_values(ev, now), tags=tuple(x for x in (tag, 'odd' if i % 2 else '') if x))
        self._browse_rows = rows
        sel = 'L:%s' % self.champ_sel if self.champ_sel else str(self.league_sel)
        if t.exists(sel):
            t.selection_set(sel)
        t.yview_moveto(top)

    # -------------------------------------------------------------- what a click does
    def browse_filter(self, key):
        self._browse_filter = key
        self._render_leagues()

    def browse_sort(self, col):
        """A heading clicked: sort by it; again: the other way; a third time: the app's order back."""
        cur = self._browse_sort
        self._browse_sort = (col, False) if not cur or cur[0] != col else (col, True) if not cur[1] else None
        self._render_leagues()

    def _browse_picked(self, _e=None):
        sel = self.browse_tree.selection()
        if not sel:
            return
        if sel[0].startswith('L:'):                   # a championship: over the list, to JOIN (or ask to)
            if sel[0][2:] != self.champ_sel:
                self.champ_sel = sel[0][2:]
                self._render_leagues()
        elif int(sel[0]) != self.league_sel or self.champ_sel:
            self.champ_sel = None
            self.select_league_event(int(sel[0]))

    def _browse_drive(self, e=None):
        """A double click on a row (or Enter): DRIVE it, as its card's button (when it can be driven)."""
        t = self.browse_tree
        iid = t.identify_row(e.y) if e is not None and e.type == tk.EventType.ButtonPress else (t.selection() or [None])[0]
        if not iid:
            return
        if iid.startswith('L:'):                      # a championship: JOIN (asked first), or ASK TO JOIN a private one
            x = self._champ(iid[2:]) or {}
            if x.get('_state', 'join') == 'join':
                self.champ_join(iid[2:])
            elif x.get('_state') == 'ask':
                self.champ_ask(iid[2:])
            return
        ev = self._league_event(int(iid))
        if ev and ev.get('locked') and ev['status'] != 'closed':   # a private rally: its code first (server 0043)
            if int(iid) != self.league_sel:
                self.select_league_event(int(iid))
            self.rally_code(int(iid))
            return
        if ev and ev['status'] == 'open' and (ev.get('entry') or {}).get('status') in (None, 'running'):
            if int(iid) != self.league_sel:
                self.select_league_event(int(iid))
            self.league_drive(int(iid))
