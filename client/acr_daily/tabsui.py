"""The app's tabs, mixed into App (app.py) like the views they switch (leagueui.py, inboxui.py): DAILIES, LEAGUES, 1V1
and CUPS, each in its colour as on the website, and the inbox's letter on the right (inboxui.py). LEAGUES, 1V1 and CUPS
are one view of my events (leagueui.py) showing one kind each, DRIVE the same for all; 1V1 adds the challenges (accept,
decline, cancel, a rematch of one that is over: server src/h2h.js; a new one: challengeui.py), CUPS the cups I'm in
and the ones open for entries (join, leave: src/cups.js). Making a cup stays on the website.

Under the tabs, the driver: their team's tag, their rating and world rank (server src/rating.js, from their page
src/drivers.js), their credits with the coin (the shop a click away), their team (or every team) and their page.
"""
import threading
import time
import tkinter as tk
from tkinter import messagebox

from .api import ApiError
from .leagueui import _left

# (kind, tab, colour): the website's colours for each part of the game (server src/site.js); the dailies in white
TABS = (('daily', 'DAILIES', None), ('league', 'LEAGUES', '#5BA8FF'), ('h2h', '1V1', '#FF9F43'), ('cup', 'CUPS', '#FFD60A'))
COLOUR = {k: col for k, _t, col in TABS}
DRIVER_EVERY_MIN = 15          # the rating moves once a day (and with a cup match): the driver strip now and then
EXTRAS_EVERY_MIN = 5           # the challenges / the cups while their tab is open
SHOWN = 3                      # challenges, cups listed in each part (the rest: the website)


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def rating_text(d):
    """The driver strip's rating: 'RATING 1512 · #3 OF 40', 'NOT RATED YET', or '' (no rating on the server)."""
    if not d or not d.get('ratingOn'):
        return ''
    r = d.get('rating')
    if not r:
        return 'NOT RATED YET'
    return 'RATING %d · #%d OF %d' % (r['rating'], r['rank'], r['of'])


def challenge_text(h, mine):
    """A challenge in one line: 'Ann · Monte Carlo · 3 stages · 50 each' (mine: 'challenger' / 'opponent')."""
    other = h['opponent'] if mine == 'challenger' else h['challenger']
    n = len(h.get('stages') or [])
    return '%s · %s · %d stage%s · %s' % (other.get('name') or 'a driver', h.get('rally') or '', n, '' if n == 1 else 's',
                                          ('%d each' % h['stake']) if h.get('stake') else 'friendly')


def result_text(h, me):
    """A settled 1V1: 'WON vs Bob (by 1.250 s)', 'LOST vs Bob', 'NO CONTEST vs Bob (nobody finished)'."""
    other = h['opponent'] if h['challenger']['steamId'] == me else h['challenger']
    if h.get('status') != 'settled':
        return '%s · %s' % (h.get('status', '').upper(), other.get('name') or '')
    word = 'NO CONTEST' if not h.get('winner') else 'WON' if h['winner'] == me else 'LOST'
    return '%s vs %s%s' % (word, other.get('name') or 'a driver', (' (%s)' % h['note']) if h.get('note') else '')


class TabsUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    league_kind = 'league'         # what the events view shows: 'league', 'h2h' (1V1) or 'cup'
    driver = None                  # /api/drivers/<me>: the driver strip's rating
    h2h_data = None                # /api/h2h: my challenges
    cups_data = None               # /api/cups: the cups, mine among them
    tab_msg = ''                   # why the challenges / the cups could not be loaded
    _tab_parts = None              # kind -> (label, underline)

    # -------------------------------------------------------------- layout
    def _build_tabs(self, parent):
        """DAILIES · LEAGUES · 1V1 · CUPS, the inbox's letter on the right (inboxui.py)."""
        c = _c()
        row = tk.Frame(parent, bg=c.BG)
        row.pack(fill='x', padx=20, pady=(0, 2))
        self._tab_parts = {}
        for kind, text, colour in TABS:
            f = tk.Frame(row, bg=c.BG)
            f.pack(side='left', padx=(0, 18))
            l = tk.Label(f, text=text, bg=c.BG, fg=colour or c.SOFT, font=(c.FONT_C, 12), cursor='hand2')
            l.pack()
            u = tk.Frame(f, bg=c.BG, height=2)
            u.pack(fill='x', pady=(3, 0))
            for w in (f, l):
                w.bind('<Button-1>', lambda _e, k=kind: self.show_tab(k))
            l.bind('<Enter>', lambda _e, l=l: l.configure(fg=c.WHITE))
            l.bind('<Leave>', lambda _e, l=l, k=kind: l.configure(fg=COLOUR[k] or c.SOFT))
            self._tab_parts[kind] = (l, u)
        self._build_inbox_button(row)             # the letter, on the right
        self._mark_tabs()

    def _build_driver_strip(self, parent):
        """The driver: name, rating and world rank, credits; their page."""
        c = _c()
        self.driver_box = tk.Frame(parent, bg=c.BG)
        self.driver_box.pack(fill='x', padx=20, pady=(8, 10))
        # the team's tag in its colour (a click: the team's page), then the name
        self.driver_tag = tk.Label(self.driver_box, text='', bg=c.BG, fg=c.WHITE, font=(c.FONT_C, 12), cursor='hand2')
        self.driver_tag.bind('<Button-1>', lambda _e: self.open_team())
        self.driver_name = tk.Label(self.driver_box, text='', bg=c.BG, fg=c.WHITE, font=(c.FONT_C, 12), anchor='w')
        self.driver_name.pack(side='left')
        self.driver_rating = tk.Label(self.driver_box, text='', bg=c.BG, fg=c.FG2, font=(c.FONT, 8, 'bold'), anchor='w')
        self.driver_rating.pack(side='left', padx=(10, 0))
        self.driver_page = self._link(self.driver_box, 'My page ›', self.open_my_page)
        self.driver_page.pack(side='right')
        self.driver_team = self._link(self.driver_box, 'Teams ›', self.open_team)     # my team's page, or every team
        self.driver_team.pack(side='right', padx=(0, 12))
        self.driver_credits = tk.Label(self.driver_box, text='', bg=c.BG, fg=c.SOFT, font=(c.FONT_C, 12), compound='right',
                                       cursor='hand2')
        self.driver_credits.bind('<Button-1>', lambda _e: self.open_shop())    # the balance: the shop
        self.driver_credits.pack(side='right', padx=(0, 14))
        self._render_driver()

    def _mark_tabs(self):
        """The tab on screen underlined in its colour (the inbox's letter: inboxui.py)."""
        c = _c()
        on = None if self.inbox_view else (self.league_kind if self.league_view else 'daily')
        for kind, (_l, u) in (self._tab_parts or {}).items():
            u.configure(bg=(COLOUR[kind] or c.WHITE) if kind == on else c.BG)
        self._inbox_badge()

    def show_tab(self, kind):
        """A tab clicked: the dailies, or my events of one kind (and that kind's own parts)."""
        if kind == 'daily':
            self.toggle_league_view(False)
        else:
            self.toggle_league_view(True, kind)
            self.refresh_tab_extras()

    # -------------------------------------------------------------- the driver strip
    def _render_driver(self):
        box = getattr(self, 'driver_box', None)
        if box is None:
            return
        c = _c()
        if not self.s.get('token'):
            box.pack_forget()
            return
        if not box.winfo_manager():
            box.pack(fill='x', padx=20, pady=(8, 10), before=self._head_rule)
        d = self.driver or {}
        team = d.get('team') or {}
        if team.get('tag'):
            self.driver_tag.configure(text=team['tag'], fg=team.get('color') or c.WHITE)
            if not self.driver_tag.winfo_manager():
                self.driver_tag.pack(side='left', padx=(0, 6), before=self.driver_name)
        else:
            self.driver_tag.pack_forget()
        self.driver_team.configure(text='My team ›' if team.get('id') else 'Teams ›')
        self.driver_name.configure(text=d.get('name') or self.s.get('name') or 'Signed in')
        self.driver_rating.configure(text=rating_text(d))
        cr = self.credits or {}
        if cr.get('enabled') and cr.get('signedIn') and cr.get('earning', True):
            self.driver_credits.configure(text='%d ' % cr.get('balance', 0), image=self.coin_img or '', font=(c.FONT_C, 12))
        elif cr.get('enabled') and cr.get('signedIn'):           # (credits start with the first finished run)
            self.driver_credits.configure(text='finish a run to earn credits', image='', font=(c.FONT, 8))
        else:
            self.driver_credits.configure(text='', image='')

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
            self.driver = d
        self._render_driver()

    def open_my_page(self):
        if self.s.get('steamId'):
            self.open_page('/d/%s' % self.s['steamId'])

    def open_team(self):
        """My team's page on the website, or every team (to make or join one)."""
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
        top.pack(fill='x', padx=20, pady=(14, 2))
        self._k(top, title).pack(side='left')
        if link:
            self._link(top, link, cmd).pack(side='right')
        return top

    def _line(self, box, text, sub, buttons=(), colour=None):
        """One row of a part: its text, a smaller line under it, its buttons on the right."""
        c = _c()
        row = tk.Frame(box, bg=c.BG)
        row.pack(fill='x', padx=20, pady=(6, 6))
        for label, cmd, primary in reversed(buttons):
            self._btn(row, label, cmd, primary=primary).pack(side='right', padx=(6, 0))
        body = tk.Frame(row, bg=c.BG)
        body.pack(side='left', fill='x', expand=True)
        self._lbl(body, text, font=(c.FONT_C, 13), fg=colour or c.WHITE).pack(anchor='w')
        if sub:
            self._lbl(body, sub, font=(c.FONT, 8), fg=c.MUTED, wraplength=280).pack(anchor='w')
        self._rule(box, padx=20)

    def _render_challenges(self, box):
        c = _c()
        self._part(box, 'Challenges', 'Challenge a driver  ›', self.new_challenge)
        r = self.h2h_data
        if r is None:
            self._lbl(box, self.tab_msg or 'Loading…', fg=c.MUTED, font=(c.FONT, 9)).pack(anchor='w', padx=20, pady=(4, 8))
            return
        me, now = self.s.get('steamId'), time.time() * 1000
        incoming, outgoing, past = r.get('incoming') or [], r.get('outgoing') or [], (r.get('past') or [])[:SHOWN]
        if not (incoming or outgoing or past):
            self._lbl(box, 'No challenges yet: challenge a driver (above), or wait for one.', fg=c.MUTED,
                      font=(c.FONT, 9), wraplength=400).pack(anchor='w', padx=20, pady=(4, 8))
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
            self._lbl(box, self.tab_msg or 'Loading…', fg=c.MUTED, font=(c.FONT, 9)).pack(anchor='w', padx=20, pady=(4, 8))
            return
        mine = set(r.get('mine') or [])
        listed = (r.get('open') or []) + (r.get('running') or [])
        my = [x for x in listed if x['id'] in mine]
        if not my:
            self._lbl(box, 'You are in no cup right now.', fg=c.MUTED, font=(c.FONT, 9)).pack(anchor='w', padx=20, pady=(4, 6))
        for x in my[:SHOWN]:
            if x['status'] == 'open':
                sub = 'Starts %s · %d of %d drivers' % (time.strftime('%a %d %b %H:%M', time.localtime(x['starts'] / 1000)),
                                                      x['entrants'], x['size'])
                buttons = (('LEAVE', lambda x=x: self.cup_entry(x, 'leave'), False),)
            else:
                sub = 'Under way: your match is above when its round opens'
                buttons = ()
            self._line(box, self._cup_title(x), sub, buttons + (('CUP ›', lambda x=x: self.open_page('/cup/%s' % x['id']), False),),
                       colour=COLOUR['cup'])
        others = [x for x in (r.get('open') or []) if x['id'] not in mine and x['entrants'] < x['size']]
        if others:
            self._part(box, 'Open for entries')
            for x in others[:SHOWN]:
                money = ('entry %d' % x['fee']) if x.get('fee') else 'free entry'
                if x.get('prize'):
                    money += ' · prize %d' % x['prize']
                sub = '%s · %s · %d of %d · starts %s' % (x.get('rally') or '', money, x['entrants'], x['size'],
                                                         time.strftime('%a %d %b', time.localtime(x['starts'] / 1000)))
                self._line(box, self._cup_title(x), sub, (('JOIN', lambda x=x: self.cup_entry(x, 'join'), True),))

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
