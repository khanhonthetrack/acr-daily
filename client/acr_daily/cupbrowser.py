"""The CUPS tab's cups as a server browser (from 0.1.5.1), as the RALLIES tab's list (browserui.py), mixed into App.

Every cup open for entries or under way (the server's /api/cups), mine marked, in one list that scrolls under the
match to drive (its card, leagueui._render_leagues): a bar in its colour (an official cup in ACR Daily's red), its name,
location, drivers (entrants of its size), entry fee, prize, when it starts or that it is under way, and where I am in
it. ALL / OPEN / UNDER WAY / MINE narrow it, with their counts; a click on a heading sorts by it. A click picks a cup:
its buttons under the list (JOIN or LEAVE, CUP ›); a double click (or Enter) joins an open one with room (asked first,
its fee said: tabsui.cup_entry), else opens its page on the website. Before it the tab listed three of mine and three
open ones; the rest were only on the website.
"""
import time
import tkinter as tk
from tkinter import ttk

from . import i18n
from .i18n import N_, _

CUP, OFFICIAL = '#FFD60A', '#E30613'          # (tabsui.COLOUR['cup'], the CUPS tab's; an official cup: ACR Daily's red)
FILTERS = (('all', N_('ALL')), ('open', N_('OPEN')), ('running', N_('UNDER WAY')), ('mine', N_('MINE')))
# (column, heading, width at 96 dpi, anchor, stretches)
COLS = (('name', N_('CUP'), 230, 'w', True), ('rally', N_('LOCATION'), 100, 'w', False),
        ('drivers', N_('DRIVERS'), 74, 'e', False), ('entry', N_('ENTRY'), 74, 'e', False),
        ('prize', N_('PRIZE'), 70, 'e', False), ('state', N_('STATUS'), 170, 'w', True), ('me', N_('YOU'), 96, 'w', False))


def _c():
    from . import app
    return app


def cups_of(r):
    """/api/cups -> (every cup listed: the open ones then those under way, mine: set of their ids)."""
    r = r or {}
    seen, out = set(), []
    for x in (r.get('open') or []) + (r.get('running') or []):
        if x.get('id') not in seen:
            seen.add(x.get('id'))
            out.append(x)
    return out, set(r.get('mine') or [])


def can_join(x, mine):
    return x.get('status') == 'open' and x['id'] not in mine and (x.get('entrants') or 0) < (x.get('size') or 0)


class CupBrowserUI:
    cup_box = None
    cup_tree = None
    _cup_filter = 'all'
    _cup_sort = None                          # (column, descending) or None: the server's order
    _cup_sel = None                           # the cup picked (its id)

    # -------------------------------------------------------------- layout
    def _build_cup_browser(self, box):
        """The list (built once; the style is the RALLIES list's: browserui._build_browser, built before it)."""
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        f = self.cup_box = tk.Frame(box, bg=c.BG)
        head = tk.Frame(f, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(16, 8))
        self._cup_tabs = {}
        for key, label in FILTERS:
            l = tk.Label(head, text=_(label), bg=c.BG, fg=c.FG2, font=(c.FONT_C, 11), cursor='hand2')
            l.pack(side='left', padx=(0, 20))
            l.bind('<Button-1>', lambda _e, kk=key: self.cup_filter(kk))
            self._cup_tabs[key] = l
        self._link(head, _('Create a cup on the website  ›'), lambda: self.open_page('/cups#new')).pack(side='right')
        for colour, text in ((CUP, N_('CUP')), (OFFICIAL, N_('OFFICIAL'))):           # (the legend, right to left)
            tk.Label(head, text='■ ' + i18n.spaced(_(text)), bg=c.BG, fg=colour, font=(c.FONT, 7, 'bold')).pack(side='right', padx=(0, 16))
        body = tk.Frame(f, bg=c.BG)
        body.pack(fill='both', expand=True, padx=20, pady=(0, 6))
        t = self.cup_tree = ttk.Treeview(body, columns=[x[0] for x in COLS], show='tree headings', style='Browser.Treeview',
                                         selectmode='browse')
        t.column('#0', width=round(14 * k), minwidth=round(14 * k), stretch=False)
        for key, heading, w, anchor, stretch in COLS:
            t.heading(key, text=_(heading), anchor=anchor, command=lambda kk=key: self.cup_sort(kk))
            t.column(key, width=round(w * k), minwidth=round(36 * k), anchor=anchor, stretch=stretch)
        sb = ttk.Scrollbar(body, orient='vertical', command=t.yview, style='Browser.Vertical.TScrollbar')
        t.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        t.pack(side='left', fill='both', expand=True)
        t.tag_configure('odd', background=c.STRIPE)
        t.tag_configure('mine', foreground=c.GOOD)
        t.tag_configure('full', foreground=c.MUTED)
        w, h = round(4 * k), round(18 * k)
        self._cup_img = {}
        for key, colour in (('cup', CUP), ('official', OFFICIAL)):     # (a bar in its colour, in the row's first column)
            img = tk.PhotoImage(master=self.root, width=w, height=h)
            img.put(colour, to=(0, 0, w, h))
            self._cup_img[key] = img
        t.bind('<<TreeviewSelect>>', self._cup_picked)
        t.bind('<Double-1>', self._cup_open)
        t.bind('<Return>', self._cup_open)
        self._cup_actions = tk.Frame(f, bg=c.BG)                      # the picked cup's buttons
        self._cup_actions.pack(fill='x', padx=20, pady=(0, 12))
        self._cup_rows = []

    # -------------------------------------------------------------- what it lists
    def _cup_values(self, x, mine):
        """A row: name, location, drivers, entry, prize, when it starts (or that it is under way), where I am in it."""
        name = self._cup_title(x)                     # (OFFICIAL · its name: tabsui.py)
        if x.get('status') == 'open':
            state = _('Starts %s') % i18n.strftime(_('%a %d %b %H:%M'), time.localtime((x.get('starts') or 0) / 1000))
        else:
            state = _('Under way')
        if x['id'] in mine:
            me = _('Joined') if x.get('status') == 'open' else _('In it')
        else:
            me = _('Full') if x.get('status') == 'open' and not can_join(x, mine) else ''
        return (name, i18n.data(x.get('rally') or ''), '%d / %d' % (x.get('entrants') or 0, x.get('size') or 0),
                str(x['fee']) if x.get('fee') else _('free'), str(x['prize']) if x.get('prize') else '', state, me)

    def _cup_key(self, col, mine):
        i = [x[0] for x in COLS].index(col)
        if col == 'state':
            return lambda x: (x.get('status') != 'open', x.get('starts') or 0)
        if col == 'drivers':
            return lambda x: x.get('entrants') or 0
        if col in ('entry', 'prize'):
            return lambda x: x.get('fee' if col == 'entry' else 'prize') or 0
        return lambda x: str(self._cup_values(x, mine)[i]).casefold()

    def _show_cups_list(self):
        """The list under the tab's match (or its message): packed in the events' box and filled."""
        if self.cup_box is None:
            return
        self.cup_box.pack(fill='both', expand=True)
        self._render_cup_browser()

    def _render_cup_browser(self):
        t = self.cup_tree
        if t is None:
            return
        c = _c()
        cups, mine = cups_of(self.cups_data)
        groups = {'all': cups, 'open': [x for x in cups if x.get('status') == 'open'],
                  'running': [x for x in cups if x.get('status') != 'open'], 'mine': [x for x in cups if x['id'] in mine]}
        for key, label in FILTERS:                    # the filter shown white, with how many each has
            self._cup_tabs[key].configure(text='%s  %d' % (_(label), len(groups[key])),
                                          fg=c.WHITE if key == self._cup_filter else c.FG2)
        rows = groups[self._cup_filter]
        if self._cup_sort:
            col, desc = self._cup_sort
            rows = sorted(rows, key=self._cup_key(col, mine), reverse=desc)
        for key, heading, *_rest in COLS:             # (the sorted column marked)
            mark = ('  ▼' if self._cup_sort[1] else '  ▲') if self._cup_sort and self._cup_sort[0] == key else ''
            t.heading(key, text=_(heading) + mark)
        top = t.yview()[0]
        t.delete(*t.get_children())
        if self.cups_data is None:
            t.insert('', 'end', iid='-', values=(self.tab_msg or _('Loading…'),) + ('',) * (len(COLS) - 1))
        for i, x in enumerate(rows):
            tag = 'mine' if x['id'] in mine else 'full' if x.get('status') == 'open' and not can_join(x, mine) else ''
            t.insert('', 'end', iid=str(x['id']), image=self._cup_img['official' if x.get('official') else 'cup'],
                     values=self._cup_values(x, mine), tags=tuple(y for y in (tag, 'odd' if i % 2 else '') if y))
        self._cup_rows = rows
        if self._cup_sel is not None and t.exists(str(self._cup_sel)):
            t.selection_set(str(self._cup_sel))
        t.yview_moveto(top)
        self._cup_buttons()

    def _cup_buttons(self):
        """The picked cup's buttons: JOIN (open, with room, not mine) or LEAVE (open, mine), and CUP › (its page)."""
        bar = self._cup_actions
        for w in bar.winfo_children():
            w.destroy()
        cups, mine = cups_of(self.cups_data)
        x = next((y for y in cups if y['id'] == self._cup_sel), None)
        if x is None:
            if cups:
                self._lbl(bar, _('Click a cup to join it or see it; double-click to join.'), fg=_c().MUTED,
                          font=(_c().FONT, 9)).pack(side='left')
            return
        self._lbl(bar, x.get('name', ''), fg=_c().WHITE, font=(_c().FONT_C, 13)).pack(side='left', padx=(0, 14))
        if can_join(x, mine):
            self._btn(bar, _('JOIN'), lambda: self.cup_entry(x, 'join'), primary=True).pack(side='left', padx=(0, 6))
        elif x.get('status') == 'open' and x['id'] in mine:
            self._btn(bar, _('LEAVE'), lambda: self.cup_entry(x, 'leave')).pack(side='left', padx=(0, 6))
        self._btn(bar, _('CUP ›'), lambda: self.open_page('/cup/%s' % x['id'])).pack(side='left')

    # -------------------------------------------------------------- what a click does
    def cup_filter(self, key):
        self._cup_filter = key
        self._render_cup_browser()

    def cup_sort(self, col):
        """A heading clicked: sort by it; again: the other way; a third time: the server's order back."""
        cur = self._cup_sort
        self._cup_sort = (col, False) if not cur or cur[0] != col else (col, True) if not cur[1] else None
        self._render_cup_browser()

    def _cup_picked(self, _e=None):
        sel = self.cup_tree.selection()
        if sel and sel[0] != '-':
            self._cup_sel = sel[0]
            self._cup_buttons()

    def _cup_open(self, e=None):
        """A double click (or Enter): JOIN an open cup with room (asked first), else its page on the website."""
        t = self.cup_tree
        iid = t.identify_row(e.y) if e is not None and e.type == tk.EventType.ButtonPress else (t.selection() or [None])[0]
        if not iid or iid == '-':
            return
        cups, mine = cups_of(self.cups_data)
        x = next((y for y in cups if str(y['id']) == iid), None)
        if x is None:
            return
        if can_join(x, mine):
            self.cup_entry(x, 'join')
        else:
            self.open_page('/cup/%s' % x['id'])
