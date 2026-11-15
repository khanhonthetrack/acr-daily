"""The RALLIES tab as a server browser (from 0.1.6), mixed into App (app.py) beside the LEAGUES view (leagueui.py).

Every rally and championship round the driver can drive or has driven lately, in one list that scrolls, as a game's
server browser: what it is (a bar in its colour: a championship's round in the leagues' blue, a rally in pink), its
name, its championship or maker, location, car, stages, how many have driven it, and where the driver is in it. The
one picked shows in full over the list (leagueui._render_leagues: its card, DRIVE); a click on a row picks one, a
double click (or Enter) drives it. ALL / CHAMPIONSHIPS / RALLIES narrow it; a click on a heading sorts by it. Public
rallies are in everyone's list (server 0033), so it can be long: before it, the window listed four events and the
rest were only on the website, where nothing is driven (2026-11-15).
"""
import time
import tkinter as tk
from tkinter import ttk

from . import i18n
from .i18n import N_, _

CHAMP, RALLY = '#5BA8FF', '#FF7AC6'          # (the website's: server src/leaguepages.js .k-champ / .k-rally)
COLOUR = {'league': CHAMP, 'event': RALLY}
FILTERS = (('all', N_('ALL')), ('league', N_('CHAMPIONSHIPS')), ('event', N_('RALLIES')))
# (column, heading, width at 96 dpi, anchor, stretches)
COLS = (('name', N_('EVENT'), 190, 'w', True), ('of', N_('CHAMPIONSHIP'), 160, 'w', True),
        ('rally', N_('LOCATION'), 96, 'w', False), ('car', N_('CAR'), 150, 'w', False), ('ss', 'SS', 34, 'e', False),
        ('drivers', N_('DRIVERS'), 64, 'e', False), ('state', N_('STATUS'), 170, 'w', True))


def _c():
    from . import app
    return app


def kind_of(ev):
    """'event' (a rally, anyone's) or 'league' (a championship's round) for the RALLIES tab."""
    return 'event' if ev.get('kind') == 'event' else 'league'


class BrowserUI:
    browse_box = None
    browse_tree = None
    _browse_filter = 'all'
    _browse_sort = None                       # (column, descending) or None: the app's order (leagueui.listed_order)

    # -------------------------------------------------------------- layout
    def _build_browser(self, box):
        """The list under the event picked: built once, filled by _render_browser (shown on the RALLIES tab only)."""
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        st = ttk.Style(self.root)
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
        w, h = round(4 * k), round(18 * k)
        self._kind_img = {}
        for kind, colour in COLOUR.items():          # (a bar in the kind's colour, in the row's first column)
            img = tk.PhotoImage(master=self.root, width=w, height=h)
            img.put(colour, to=(0, 0, w, h))
            self._kind_img[kind] = img
        t.bind('<<TreeviewSelect>>', self._browse_picked)
        t.bind('<Double-1>', self._browse_drive)
        t.bind('<Return>', self._browse_drive)
        self._browse_rows = []

    # -------------------------------------------------------------- what it lists
    def _browse_values(self, ev, now):
        """A row: name, championship (or 'Rally by <maker>'), location, car, stages, drivers, where I am in it."""
        entry = ev.get('entry') or {}
        of = _('Rally by %s') % (ev.get('organizer') or '?') if kind_of(ev) == 'event' else (ev.get('league') or '')
        car = ev.get('car') or entry.get('car') or ev.get('carClass') or ''
        return (ev['name'], of, i18n.data(ev.get('rally') or ''), car, len(ev.get('stages') or ()),
                ev.get('drivers') if ev.get('drivers') is not None else '', self._browse_state(ev, now))

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
        if ev.get('status') == 'upcoming':
            return _('Opens %s') % i18n.strftime(_('%a %d %b %H:%M'), time.localtime(ev['opens'] / 1000))
        if ev.get('status') == 'closed':
            return _('CLOSED')
        return _('Closes in %s') % _left(ev['closes'] - now)

    def _browse_key(self, col):
        """How a column sorts: names as text, numbers as numbers, STATUS by when each closes."""
        i = [x[0] for x in COLS].index(col)
        if col == 'state':
            return lambda ev: ev['closes']
        if col == 'drivers':
            return lambda ev: ev.get('drivers') or 0
        if col == 'ss':
            return lambda ev: len(ev.get('stages') or ())
        return lambda ev: str(self._browse_values(ev, 0)[i]).casefold()

    def _render_browser(self, evs, now):
        """Fill the list with evs (the tab's events, in the app's order), as the filter and the sort say; the event picked
        selected; the scroll kept."""
        t = self.browse_tree
        if t is None:
            return
        c = _c()
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
            tag = ('running' if st == 'running' else 'done' if st in ('finished', 'dnf', 'dsq') or status == 'closed'
                   else 'soon' if status == 'upcoming' else '')
            t.insert('', 'end', iid=str(ev['id']), image=self._kind_img[kind_of(ev)], values=self._browse_values(ev, now),
                     tags=tuple(x for x in (tag, 'odd' if i % 2 else '') if x))
        self._browse_rows = rows
        sel = str(self.league_sel)
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
        if sel and int(sel[0]) != self.league_sel:
            self.select_league_event(int(sel[0]))

    def _browse_drive(self, e=None):
        """A double click on a row (or Enter): DRIVE it, as its card's button (when it can be driven)."""
        t = self.browse_tree
        iid = t.identify_row(e.y) if e is not None and e.type == tk.EventType.ButtonPress else (t.selection() or [None])[0]
        if not iid:
            return
        ev = self._league_event(int(iid))
        if ev and ev['status'] == 'open' and (ev.get('entry') or {}).get('status') in (None, 'running'):
            if int(iid) != self.league_sel:
                self.select_league_event(int(iid))
            self.league_drive(int(iid))
