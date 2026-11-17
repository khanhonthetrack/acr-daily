"""The app's LEAGUES view and its part of the loop, mixed into App (app.py). The logic is in leagues.py.

The view lists the events of the driver's leagues (open or coming soon) with their progress; DRIVE sets an event's rally
up in the game (or puts it back, or resumes it) and the app then follows the driver through it: the frames are judged
for the event's next stage instead of the dailies (drive_target), each finished stage is sent with the game's own
result, and the next stage is armed. No timing sheet under the view (from 0.1.6): its list of events takes the room,
and each event's standings are on its page on the website (Standings ›).
The dailies and the events share the game's one Rally Weekend: over the dailies, a strip shows a league rally in
progress, and DRIVE on a daily sets it aside (said first; refused while a league stage is being driven). A Rally
Weekend of the player's own is set aside the same way, and the strip offers it back (PUT BACK).
1V1s (head-to-heads) and cup matches (made on the website) come as events too, of a hidden league of their own (kind
'h2h' / 'cup', open to their two drivers only): driven the same way, tagged as such with the other driver's name.
"""
import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import autodrive, gamelog, leagues, names, photos, rallyweekend, saveslot, settings, tiles, tmtext, waiting
from .api import TOO_OLD, ApiError
from .judge import Judge, fmt_ms
from .i18n import N_, _, local, n_, said
from . import i18n

# the game keeps a Rally Weekend under way only when it is left from a service park; quit anywhere else (or a crash) it
# takes the rally back, and the counted stages are driven again (leagues.plan): said after each stage, from 0.1.5
STOP_HINT = _('To stop between stages, quit the game from a service park: the game keeps its rally only then.')

OFFICIAL_CHECK_MS = 2000
OFFICIAL_WAIT_S = 30 * 60
OFFICIAL_CLOCK_MS = 5000
OFFICIAL_SAME_MS = 50          # (app.py)
LEAGUES_EVERY_MIN = 5
SHOWN = 4                      # events listed as full cards: the one picked, the others under it (1V1)
LISTED = 7                     # with more than that, the others as slim cards, at most this many (the rest: a drop-down)
KINDS = {'h2h': '1V1', 'cup': _('CUP')}   # an event's kind other than 'league': its tag
# each tab of events (tabsui.py): what it lists, and where the website has more
# (signed out, none open, the link, its page)
EMPTY = {'league': (_('Sign in with Steam (on the left) to see the rallies.'), _('No rallies open right now.'),
                    _('Create a rally on the website  ›'), '/rallies/new'),
         'h2h': (_('Sign in with Steam (on the left) to see your 1V1 matches.'), _('No 1V1 matches open right now.'),
                 _('Challenge a driver on the website  ›'), '/1v1'),
         'cup': (_('Sign in with Steam (on the left) to see your cup matches.'), _('No cup matches open right now.'),
                 _('Cups on the website  ›'), '/cups')}


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def opponent(ev, me):
    """The other driver of a 1V1 or a cup match: the server's `opponent` (their name now, their team's tag first:
    '[GFX] Ann'), else as the match's name says ('Ann vs Bob', 'Quarter-final: Ann vs Bob'; a 1V1's league:
    '1V1: Ann vs Bob'), or None."""
    if (ev.get('opponent') or {}).get('name'):
        return tmtext.tagged(ev['opponent'])
    me = (me or '').strip().casefold()
    for text in (ev.get('name'), ev.get('league')):
        sides = [x.strip() for x in (text or '').split(': ', 1)[-1].split(' vs ')]
        if me and len(sides) == 2 and me in (sides[0].casefold(), sides[1].casefold()):
            return sides[1] if sides[0].casefold() == me else sides[0]
    return None


def tab_of(ev):
    """The tab an event is listed on: 'league' (RALLIES: a championship's round, or a rally: kind 'event', from 0.1.6),
    'h2h' (1V1) or 'cup' (CUPS)."""
    kind = ev.get('kind') or 'league'
    return 'league' if kind == 'event' else kind


def listed_order(ev):
    """Where an event is listed: a rally in progress first, then what can be driven now (1V1s and cup matches
    before league events: a driver waits on the other side), then the rest; each by closing time (the server's order)."""
    status = (ev.get('entry') or {}).get('status')
    can = ev['status'] == 'open' and status in (None, 'running')
    return status != 'running', not can, tab_of(ev) == 'league'


HIDDEN_WHAT = {('stages',): N_('stage names'), ('weather',): N_('weather'), ('times',): N_('times'),
               ('stages', 'weather'): N_('stage names and weather'), ('stages', 'times'): N_('stage names and times'),
               ('weather', 'times'): N_('weather and times'),
               ('stages', 'weather', 'times'): N_('stage names, weather and times')}


def hidden_what(h):
    """What a hidden event keeps (server src/hidden.js): 'stage names, weather and times'."""
    w = tuple(k for k in ('stages', 'weather', 'times') if (h or {}).get(k))
    return _(HIDDEN_WHAT[w]) if w else ''


def hidden_text(ev):
    """The line under a hidden event the driver hasn't seen yet, or ''."""
    if not ev.get('hidden') or ev.get('revealed') or not hidden_what(ev['hidden']):
        return ''
    return _('%s hidden until it ends: DRIVE shows them') % i18n.cap(hidden_what(ev['hidden']))


def event_figures(ev, now):
    """The figures beside an event's card (RaceRoom's DAYS LEFT / ENTRIES): the time left to drive it (or until it
    opens), its stages."""
    out = []
    ms = (ev.get('opens') if ev.get('status') == 'upcoming' else ev.get('closes') if ev.get('status') == 'open' else 0) or 0
    left = ms - now
    if left > 0:
        days, hours = int(left // 86400000), int(left // 3600000)
        if ev.get('status') == 'upcoming':
            out.append(('%d' % days, n_('DAY TO GO', 'DAYS TO GO', days)) if days >= 1 else
                       ('%d' % hours, n_('HOUR TO GO', 'HOURS TO GO', hours)) if hours >= 1 else ('<1', _('HOUR TO GO')))
        else:
            out.append(('%d' % days, n_('DAY LEFT', 'DAYS LEFT', days)) if days >= 1 else
                       ('%d' % hours, n_('HOUR LEFT', 'HOURS LEFT', hours)) if hours >= 1 else ('<1', _('HOUR LEFT')))
    out.append(('%d' % len(ev.get('stages') or ()), n_('STAGE', 'STAGES', len(ev.get('stages') or ()))))
    return out


def _left(ms_left):
    s = int(ms_left / 1000)
    if s <= 0:
        return _('now')
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return _('%d d %d h') % (d, h) if d else _('%d h %02d min') % (h, m) if h else _('%d min') % m


class LeaguesUI:
    # what an App has before _league_init gives it its own (the tests build bare ones: App.__new__)
    league_events = ()
    league_view = False
    league_run = None
    drive_target = 'daily'
    awaiting = ()
    _league_restored = ()

    def _league_init(self):
        self.league_events = []        # /api/me/events: the events of my leagues, open or coming soon
        self.league_view = False       # the window shows the LEAGUES view (instead of the dailies)
        self.league_run = None         # the event being driven: {'ev', 'car', 'no', 'judge', 'known', 'ignore', 'wait'}
        self.league_sel = None         # its id
        self.drive_target = 'daily'    # what the game's frames are judged for: 'daily' or 'league'
        self.league_msg = ''
        self._league_lock = threading.Lock()
        self._league_at = 0.0
        self._route_cache = {}         # track -> route of the league stages fetched so far
        self._park_said = None         # the event whose rally a daily's DRIVE said it sets aside
        # league stages left waiting for the game's official result when the app last closed (_league_check_restored)
        self._league_restored = [dict(x, known=leagues.known_from_json(x['known']) if x.get('known') is not None else None,
                                      closed=0, other=None) for x in waiting.load('league')]

    # -------------------------------------------------------------- layout
    def _build_league_box(self):
        c = _c()
        self.league_box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)   # (in the view, on the right)
        self._build_comp_tabs(self.league_box)
        self.league_rows = tk.Frame(self.league_box, bg=c.BG)
        self.league_rows.pack(fill='x')
        self._build_browser(self.league_box)       # RALLIES: every one in a list under the one picked (browserui.py)
        self._build_cup_browser(self.league_box)   # CUPS: every cup in a list under the match to drive (cupbrowser.py)
        self.league_strip = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)   # over the dailies: a league rally in progress

    def _build_comp_tabs(self, box):
        """COMPETITIONS' own tabs over its events (RaceRoom's RUNNING / ENTERED / FINISHED): LEAGUES, 1V1, CUPS as
        words on a hairline, the one shown white and underlined in its colour, as COMMUNITY's (tabsui._mark_comp); a
        click shows that kind."""
        c = _c()
        from .tabsui import COMP
        bar = tk.Frame(box, bg=c.BG)
        bar.pack(fill='x', padx=20, pady=(2, 8))
        row = tk.Frame(bar, bg=c.BG)
        row.pack(fill='x')
        self._comp_parts = {}
        for kind, text in COMP:
            f = tk.Frame(row, bg=c.BG, cursor='hand2')
            f.pack(side='left', padx=(0, 22))
            l = tk.Label(f, text=text, bg=c.BG, fg=c.FG2, font=(c.FONT_C, 14), pady=4, cursor='hand2')
            l.pack()
            u = tk.Frame(f, bg=c.BG, height=3)
            u.pack(fill='x')
            for w in (f, l):
                w.bind('<Button-1>', lambda _e, k=kind: self.show_tab(k))
            l.bind('<Enter>', lambda _e, w=l: w.configure(fg=c.WHITE))
            l.bind('<Leave>', lambda _e: self._mark_comp())
            self._comp_parts[kind] = (l, u)
        tk.Frame(bar, bg=c.LINE2, height=1).pack(fill='x')

    def toggle_league_view(self, on=None, kind=None):
        """The events view on (showing one kind: 'league', 'h2h' or 'cup'; the tabs, tabsui.py) or the dailies."""
        on = (not self.league_view) if on is None else on
        if kind and kind != self.league_kind:
            self.league_kind = kind
            self.league_sel = None               # (the first of that kind is picked)
            if on and self.league_view and not self._page_on():
                self._mark_tabs()
                self._render_leagues()
                return
        if on == self.league_view and not self._page_on():
            return
        self._pages_leave()                        # (a page open: HOME, the inbox, the settings, the driver page make way: app.py)
        self.league_view = on
        self._mark_tabs()
        if on:
            self.daily_box.pack_forget()
            self._pack_view(self.league_box)
            self.refresh_leagues()
        else:
            self.league_box.pack_forget()
            self.daily_box.pack(fill='x', before=self._view_end)
        self._render_strip()

    def _league_in_progress(self):
        """My events with a rally under way (my entry still running, the event open), the soonest to close first."""
        return sorted((e for e in self.league_events
                       if e['status'] == 'open' and (e.get('entry') or {}).get('status') == 'running'), key=lambda e: e['closes'])

    def _progress_text(self, ev, now):
        e = ev.get('entry') or {}
        done = e.get('done', 0)
        return _('SS%d of %d next%s · closes in %s') % (done + 1, len(ev['stages']),
                                                     ((' ' + _('· %s so far')) % fmt_ms(e.get('totalMs') or 0)) if done else '',
                                                     _left(ev['closes'] - now))

    @staticmethod
    def _held_hint(ev):
        """Where a rally in progress waits, and what not to do with it."""
        if leagues.is_parked(ev['id']):
            return _('Set aside for a daily. CONTINUE puts it back.')
        return _('Resume it in the game: Rally Weekend › RESUME.')

    def _render_strip(self):
        """In the DAILIES view, on top: the league rally in progress (CONTINUE takes it up again) and the player's own
        rally set aside (PUT BACK), as the dailies, the league events and the player's own rallies share the game's
        one Rally Weekend."""
        s = getattr(self, 'league_strip', None)
        if s is None:
            return
        for w in s.winfo_children():
            w.destroy()
        evs = self._league_in_progress() if self.s.get('token') else []
        own = leagues.own_parked()
        if self.league_view or self.tt_view or self._page_on() or not (evs or own):
            s.pack_forget()
            return
        if evs:
            self._strip_league(s, evs)
        if own:
            self._strip_own(s, own)
        s.pack(fill='x', before=self.daily_box)

    def _strip_card(self, s, kicker, title, lines, label, cmd):
        """A card over the dailies (tiles.py): what is set aside or in progress, and its button."""
        tile = tiles.Tile(s, restyle=self._btn_style)
        tile.button = b = self._btn(tile.cv, label, cmd or (lambda: None), primary=bool(cmd))
        if not cmd:
            b.configure(cursor='arrow')
        tile.frame.pack(fill='x', padx=20, pady=(6, 0))
        tile.render({'kicker': [kicker], 'title': title, 'sizes': (17, 15, 14), 'lines': lines})

    def _strip_own(self, s, own):
        c = _c()
        x = own[0]
        more = ((' ' + _('%d more set aside.')) % (len(own) - 1)) if len(own) > 1 else ''
        self._strip_card(s, (_('YOUR RALLY WEEKEND · SET ASIDE'), c.SOFT), _('Rally %s') % i18n.data(x['location']),
                         [('%d of %d stages done · set aside %s' % (x['done'], x['stages'], i18n.strftime(
                             _('%a %d %b %H:%M'), time.localtime(x['at']))), 'info'),
                          (_('Set aside. PUT BACK returns it to the game.') + more, 'muted')],
                         _('PUT BACK  ›'), lambda p=x['path']: self.put_back_own(p))

    def _strip_league(self, s, evs):
        c = _c()
        ev = evs[0]
        run = self.league_run
        # (a run of it that didn't count: CONTINUE sets it up again, rather than FOLLOWING as if all were well)
        following = bool(run and run['ev']['id'] == ev['id'] and self.drive_target == 'league' and not run.get('missed'))
        more = ((' ' + _('%d more in RALLIES.')) % (len(evs) - 1)) if len(evs) > 1 else ''
        self._strip_card(s, (_('%s IN PROGRESS · %s') % (_('MATCH') if ev.get('kind') in KINDS else _('RALLY'), self._event_of(ev)), c.GOOD),
                         ev['name'], [(self._progress_text(ev, time.time() * 1000), 'info'), (self._held_hint(ev) + more, 'muted')],
                         _('FOLLOWING') if following else _('CONTINUE  ›'), None if following else (lambda i=ev['id']: self.league_drive(i)))

    def _league_event(self, eid):
        return next((e for e in self.league_events if e['id'] == eid), None)

    def _event_of(self, ev):
        """What an event is part of, over its name: its league ('WRC MASTERS'), or a 1V1's or a cup's tag with the
        other driver ('1V1 · VS BOB', 'CUP · AUTUMN CUP · VS BOB')."""
        kind = ev.get('kind')
        if kind == 'event':                       # a rally (anyone's, from 0.1.6): who made it
            return (_('Rally by %s') % (ev.get('organizer') or '?')).upper()
        if kind not in KINDS:
            return (ev.get('league') or _('League')).upper()
        opp = opponent(ev, self.s.get('name'))
        return ' · '.join([KINDS[kind]] + ([ev['league']] if kind == 'cup' and ev.get('league') else []) +
                          ([_('vs %s') % opp] if opp else [])).upper()

    def _league_car(self, ev):
        """The event's car, or the class car picked for it (remembered per event)."""
        if ev.get('car'):
            return leagues.car_of(ev, ev['car'])
        picked = (self.s.get('leagueCars') or {}).get(str(ev['id']))
        return leagues.car_of(ev, picked) if picked else None

    def _pick_car(self, ev, name):
        self.s.setdefault('leagueCars', {})[str(ev['id'])] = name
        settings.save(self.s)

    def _render_leagues(self):
        c = _c()
        self._render_strip()                     # (over the dailies)
        for w in self.league_rows.winfo_children():
            w.destroy()
        box = self.league_rows
        kind = self.league_kind                  # the tab on screen: one kind of events (tabsui.py)
        signed_out, none, site, path = EMPTY[kind]
        # every tab in one column (from 0.1.6), as a game's server browser: the one picked in full, and under it the rest
        # in a list that scrolls. RALLIES: its events and the public championships to join (browserui.py); CUPS: every
        # cup (cupbrowser.py: one of mine picked shows its match); 1V1: the others one under another, then the challenges.
        # (Before, the others were cards beside the one picked.)
        browser = getattr(self, 'browse_box', None) if kind == 'league' else None
        for lst in (getattr(self, 'browse_box', None), getattr(self, 'cup_box', None)):
            if lst is not None:
                lst.pack_forget()
        if not self.s.get('token'):
            self._lbl(box, signed_out, fg=c.SOFT, font=(c.FONT, 10),
                      wraplength=c.px(box, 400)).pack(anchor='w', padx=20, pady=(16, 6))
            self._link(box, site, lambda: self.open_page(path)).pack(anchor='w', padx=20, pady=(0, 14))
            self._rule(box, padx=20)
            return
        evs = [e for e in self.league_events if tab_of(e) == kind and
               (e['status'] != 'closed' or (e.get('entry') or {}).get('status') == 'running')]
        evs.sort(key=listed_order)                # a rally in progress first, then what can be driven
        champs = list(self.public_champs or ()) if kind == 'league' else []
        if not evs and not champs:
            self._lbl(box, self.league_msg or none, fg=c.SOFT, font=(c.FONT, 10),
                      wraplength=c.px(box, 400)).pack(anchor='w', padx=20, pady=(16, 4))
            if kind == 'league':
                self._link(box, site, lambda: self.open_page(path)).pack(anchor='w', padx=20, pady=(0, 14))
            self._rule(box, padx=20)
            self._render_tab_extras(box)
            return
        now = time.time() * 1000
        picked, rest = None, []
        if evs:
            if self.league_sel not in [e['id'] for e in evs]:
                run = self.league_run
                self.league_sel = run['ev']['id'] if run else evs[0]['id']
            picked = next((e for e in evs if e['id'] == self.league_sel), evs[0])
            rest = [e for e in evs if e is not picked]
        champ = self._champ(self.champ_sel) if champs and self.champ_sel else None
        if picked is None and champ is None:      # (no events yet: the first championship to join, over the list)
            champ = champs[0]
            self.champ_sel = champ['id']
        for col in (0, 1):
            box.columnconfigure(col, weight=1, uniform='events')
        top = tk.Frame(box, bg=c.BG)
        top.padx_ = 20
        top.grid(row=0, column=0, columnspan=2, sticky='new')
        if champ is not None:
            self._champ_card(top, champ)
        else:
            self._event_card(top, picked, now)
        if kind == 'league':
            foot = tk.Frame(top, bg=c.BG)
            foot.pack(fill='x', padx=top.padx_, pady=(8, 10))
            self._link(foot, _('Rallies on the website  ›'), self.open_leagues).pack(side='left')
        if browser is not None:
            browser.pack(fill='both', expand=True)
            self._render_browser(evs, now)
        elif kind == 'h2h':                       # the others under it (a click picks one), more in a drop-down
            slim = len(rest) > SHOWN - 1
            for ev in rest[:LISTED]:
                self._event_card(top, ev, now, slim=slim)
            more = rest[LISTED:]
            if more:                                     # (its drop-down opens under the row's left edge)
                row = tk.Frame(top, bg=c.BG)
                row.pack(fill='x', padx=self._padx(top), pady=(8, 0))
                self._link(row, n_('%d more event  ▾', '%d more events  ▾', len(more)) % len(more),
                           lambda r=row, evs=more: self._more_events(r, evs)).pack(side='left')
            self._render_tab_extras(top)
        else:
            self._render_tab_extras(top)

    def _more_events(self, anchor, evs):
        """The events past the ones listed: a drop-down under anchor, each as 'name · its league · where I am in it';
        one picked shows in full on the left, to DRIVE. -> the menu."""
        c = _c()
        now = time.time() * 1000
        m = tk.Menu(anchor, tearoff=0, bg=c.PANEL, fg=c.SOFT, activebackground=c.ACC, activeforeground=c.WHITE,
                    font=(c.FONT, 10))
        for ev in evs:
            m.add_command(label='%s  ·  %s  ·  %s' % (ev['name'], self._event_of(ev), self._status_line(ev, now)[0]),
                          command=lambda i=ev['id']: self.select_league_event(i))
        m.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
        return m

    def banner_key(self, rel, then):
        """A league's or a cup's banner (its address on the website, as the server gives it: /l/<id>/banner?v=) for
        photos.py: its key once downloaded, else None (fetched; then() on the Tk thread once it is here)."""
        if not rel or not self.api.configured:
            return None
        return photos.fetch(self.api.base + rel, lambda: _c().ui(self.root, then))

    def _event_photo(self, ev):
        """An event card's picture: {'banner': its league's banner (its cup's), as its admins put it on the website} once
        it is here, else {'photo': the rally's photo} (until then, or if there is none)."""
        b = self.banner_key(ev.get('leagueBanner'), lambda: self.league_view and self._render_leagues())
        return {'banner': b} if b else {'photo': photos.for_rally(ev.get('rally'))}

    def _status_line(self, ev, now):
        """Where I am in an event, in a line: -> (text, colour)."""
        c = _c()
        entry = ev.get('entry') or {}
        status = entry.get('status')
        if status == 'running':
            return self._progress_text(ev, now), c.GOOD
        if status == 'finished':
            return _('Finished · %s') % fmt_ms(entry.get('totalMs') or 0), c.WHITE
        if status in ('dnf', 'dsq'):
            return '%s · %s' % (_('DNF') if status == 'dnf' else _('DSQ'), local(entry.get('reason') or '')), c.BAD
        if ev['status'] == 'upcoming':
            return _('Opens %s') % i18n.strftime(_('%a %d %b %H:%M'), time.localtime(ev['opens'] / 1000)), c.FG2
        return _('Not started · closes in %s') % _left(ev['closes'] - now), c.FG2

    def _event_card(self, box, ev, now, slim=False):
        """An event of my leagues: the one picked in full (itinerary, car, progress; its standings in the timing
        sheet), the others in two lines (a click picks one); slim: closer together, for a long list of them."""
        c = _c()
        sel = ev['id'] == self.league_sel
        entry = ev.get('entry') or {}
        status = entry.get('status')
        run = self.league_run
        following = bool(run and run['ev']['id'] == ev['id'] and self.drive_target == 'league')
        if ev['status'] == 'upcoming':
            label, primary, cmd = _('OPENS IN %s') % _left(ev['opens'] - now).upper(), False, None
        elif status == 'finished':
            label, primary, cmd = _('FINISHED'), False, None
        elif status in ('dnf', 'dsq'):
            label, primary, cmd = _('DNF') if status == 'dnf' else _('DSQ'), False, None
        elif ev['status'] == 'closed':
            label, primary, cmd = _('CLOSED'), False, None
        else:                                             # solid: the event picked (its card red, as the daily on screen)
            # a run that didn't count (the event's set-up changed in the game, or not its rally): DRIVE AGAIN sets it
            # up afresh, as the message asks; FOLLOWING would say all is well
            missed = following and bool(run.get('missed'))
            label = _('DRIVE AGAIN  ›') if missed else _('FOLLOWING') if following else _('CONTINUE  ›') if status == 'running' else _('DRIVE  ›')
            primary, cmd = sel and (missed or not following), (lambda e=ev['id']: self.league_drive(e))
        txt, fg = self._status_line(ev, now)
        from .tabsui import COLOUR                      # (each kind in its colour, as its tab)
        tile = tiles.Tile(box, on_click=None if sel else (lambda i=ev['id']: self.select_league_event(i)), restyle=self._btn_style)
        tile.button = b = self._btn(tile.cv, label, cmd or (lambda: None), primary=primary)
        if not cmd:
            b.configure(cursor='arrow')
        tile.frame.pack(fill='x', padx=self._padx(box), pady=(6, 0))
        kind = {c.GOOD: 'good', c.WHITE: 'sub', c.BAD: 'bad'}.get(fg, 'info')
        if not sel:                                       # listed under the one picked: two lines (a click picks it)
            if slim and not status and ev['status'] == 'open':   # (one line: its DRIVE says it is not started)
                txt = _('Closes in %s') % _left(ev['closes'] - now)
            tile.render({'title': ev['name'], 'sizes': tiles.SLIM_SIZES if slim else tiles.COMPACT_SIZES, 'slim': slim,
                         **self._event_photo(ev), 'banner_side': True,
                         'lines': [('%s · %s%s' % (self._event_of(ev), (_('In progress ·') + ' ') if status == 'running' else '', txt),
                                    'good' if status == 'running' else 'muted')]})
            return
        km = sum(s.get('lengthM') or 0 for s in ev['stages']) / 1000
        secret = hidden_text(ev)                          # (a hidden event not driven yet: server src/hidden.js)
        picker = None
        if not ev.get('car') and not status:              # a class: pick a car of it before the start
            names = [x['name'] for x in ev['cars']]
            cur = (self._league_car(ev) or {}).get('name') or ''
            picker = ttk.Combobox(tile.cv, values=names, state='readonly', width=34)
            picker.set(cur or _('Pick your %s car') % ev.get('carClass', ''))
            picker.bind('<<ComboboxSelected>>', lambda _e, e=ev, p=picker: self._pick_car(e, p.get()))
        links = [self._link(tile.cv, _('Standings ›'), lambda i=ev['id']: self.open_event_page(i))]
        if ev.get('kind') == 'cup' and ev.get('leagueId'):        # (a cup's league is the cup: its id)
            links.append(self._link(tile.cv, _('Cup ›'), lambda i=ev['leagueId']: self.open_page('/cup/%s' % i)))
        elif ev.get('kind') == 'h2h':
            links.append(self._link(tile.cv, '1V1s ›', lambda: self.open_page('/1v1')))
        tile.min_h = round(220 * tile.k)                  # (RaceRoom's competition banner: its photo, the figures beside it)
        tile.render({'active': True, 'lock': ('%d SS' % len(ev['stages']), i18n.data(ev.get('rally') or '').upper()),
                     **self._event_photo(ev), 'bottom': True, 'figures': event_figures(ev, now),
                     'chips': [_('STAGES HIDDEN') if ev.get('lengthM') is None else '%.1f KM' % km,
                               n_('%d DAY', '%d DAYS', ev['days']) % ev['days']],
                     'kicker': [(self._event_of(ev), COLOUR.get(ev.get('kind') or 'league') or c.ACC_TEXT)] +
                               ([(_('●  IN PROGRESS'), c.GOOD)] if status == 'running' else []),
                     'title': ev['name'],
                     'lines': [(ev.get('car') or entry.get('car') or '', 'sub'), (txt, kind),
                               (self._held_hint(ev) if status == 'running' else secret, 'muted')],
                     'below': [[picker], links]})

    # -------------------------------------------------------------- data
    def refresh_leagues(self):
        if not self.api.configured or not self.s.get('token'):
            self.league_events = []
            self._render_leagues()
            return
        self._league_at = time.monotonic()

        def go():
            try:
                r = self.api.my_events()
                _c().ui(self.root, self._set_league_events, r.get('events') or [], '')
            except ApiError as e:
                _c().ui(self.root, self._set_league_events, None, _('Leagues: %s') % e)
            try:                                 # RALLIES: the public championships I'm not in, to join (browserui.py)
                lg = self.api.leagues() or {}
                mine = {x.get('id') for x in lg.get('mine') or []}
                _c().ui(self.root, self._set_public_champs, [x for x in lg.get('public') or [] if x.get('id') not in mine])
            except (ApiError, AttributeError, TypeError):
                pass                             # (the ones known stay)
        threading.Thread(target=go, daemon=True).start()

    def _set_public_champs(self, champs):
        self.public_champs = champs
        if self.champ_sel and self.champ_sel not in [x['id'] for x in champs]:
            self.champ_sel = None                # (joined, or gone: its rounds, or the first event, over the list)
        if getattr(self, 'league_view', False):
            self._render_leagues()

    def _set_league_events(self, evs, msg):
        self.league_msg = msg
        if evs is not None:
            with self._league_lock:              # what is still on its way to the server counts already
                leagues.with_pending(evs, leagues.pending())
            run = self.league_run
            if run:                              # keep the routes already fetched, and what the app knows of the run
                fresh = next((e for e in evs if e['id'] == run['ev']['id']), None)
                if fresh:
                    for a, b in zip(fresh['stages'], run['ev']['stages']):
                        a['route'] = b.get('route')
                    if run['ev'].get('entry') and (fresh.get('entry') or {}).get('done', 0) < run['ev']['entry'].get('done', 0):
                        fresh['entry'] = run['ev']['entry']
                    run['ev'] = fresh
                    fe = fresh.get('entry') or {}
                    if fe.get('status') in ('dsq', 'dnf') and not run.get('over') and not run.get('wait'):
                        # ended on the server (the stewards, or removed from the league): stop following it
                        run['over'] = True
                        self.drive_target = 'daily'
                        self.sub_l.configure(text='%s: %s (%s).' % (fresh['name'], fe['status'].upper(), fe.get('reason') or ''))
            self.league_events = evs
            self._league_autofollow()
        if self.league_view:
            self._render_leagues()
        else:
            self._render_strip()

    def _league_autofollow(self):
        """The game's save holds the rally of an event the driver is in the middle of (the app was restarted, or the
        game resumed it): follow it, so its next stage is judged without a click on CONTINUE first."""
        if self.league_run and not self.league_run.get('over') or getattr(self, '_restarting', False) or \
                any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or self._tt_running():
            return
        if self._waiting_text():                  # a result on its way: the game is about to write its save (SaveWatch)
            return
        try:
            b = saveslot.read_save_idle()          # (the game may be running: not just after it wrote its save)
            ev = leagues.owner_of(b, self.league_events)
            if not ev or (ev.get('entry') or {}).get('status') != 'running' or leagues.is_parked(ev['id']) or \
                    any(x['eventId'] == ev['id'] for x in self._league_restored):   # (its last stage: not sent yet)
                return
            state, p = leagues.rally_state(b, ev)
        except (OSError, saveslot.SaveError):
            return
        car = leagues.car_of(ev, ev['entry'].get('car')) or self._league_car(ev)
        if state != 'this' or p['done'] != ev['entry'].get('done', 0) or not car:
            return                                # (stages driven without the app: DRIVE says so)
        self._league_routes(ev, lambda: self._league_autofollow_go(ev['id'], car))

    def _league_autofollow_go(self, eid, car):
        ev = self._league_event(eid)
        if ev and not (self.league_run and not self.league_run.get('over')):
            self._follow(ev, car)
            self.sub_l.configure(text=_('Following %s: SS%d next. In the game: Racing › Rally › Rally Weekend › RESUME.')
                                 % (ev['name'], ev['entry'].get('done', 0) + 1))

    def _fill_routes(self, ev):
        """The routes already fetched into the event's stages. -> True when every stage has one."""
        for s in ev['stages']:
            s['route'] = s.get('route') or self._route_cache.get(s['track'])
        return all(s['route'] for s in ev['stages'])

    def _league_routes(self, ev, then):
        """Fetch the routes of the event's stages (to judge them like dailies), then call then() on the Tk thread."""
        if self._fill_routes(ev):
            then()
            return

        def go():
            try:
                for s in ev['stages']:
                    if s['track'] not in self._route_cache:
                        self._route_cache[s['track']] = self.api.route(s['track'])
                _c().ui(self.root, then)
            except ApiError as e:
                _c().ui(self.root, self.sub_l.configure, {'text': _('Could not get the stages of %s (%s). Try again.')
                                                                  % (ev['name'], e)})
        threading.Thread(target=go, daemon=True).start()

    def select_league_event(self, eid):
        self.league_sel = eid
        self.champ_sel = None                    # (an event over the list, not a championship to join)
        self._render_leagues()

    # -------------------------------------------------------------- a public championship to join (RALLIES)
    def _champ(self, cid):
        return next((x for x in self.public_champs or () if x.get('id') == cid), None)

    def _champ_card(self, box, x):
        """The public championship picked in the list, over it: who runs it, its drivers and rounds, JOIN."""
        from .browserui import CHAMP
        rounds = x.get('events') or 0
        sub = ['%s' % (_('Official championship') if x.get('official') else _('Championship by %s') % (x.get('owner') or '?')),
               n_('%d driver', '%d drivers', x.get('members') or 0) % (x.get('members') or 0),
               n_('%d round', '%d rounds', rounds) % rounds, self._champ_state(x)]
        about = ' '.join((x.get('about') or '').split())
        if len(about) > 300:
            about = about[:297].rstrip() + '…'
        c = _c()
        P = c.PANEL
        k = self.root.winfo_fpixels('1i') / 96
        card = tk.Frame(box, bg=P, highlightthickness=1, highlightbackground=c.LINE)
        card.pack(fill='x', padx=self._padx(box), pady=(6, 0))
        img = photos.thumb(card, x.get('banner'), round(150 * k), round(50 * k)) if x.get('banner') else None
        if img is not None:                              # (its banner, 3:1, as the website's)
            pic = tk.Label(card, image=img, bg=P, bd=0)
            pic._img = img
            pic.pack(side='left', padx=(12, 0), pady=12, anchor='n')
        inner = tk.Frame(card, bg=P)
        inner.pack(fill='x', padx=14, pady=12)
        for label, cmd, primary in ((_('CHAMPIONSHIP ›'), lambda: self.open_page('/l/%s' % x['id']), False),
                                    (_('JOIN  ›'), lambda: self.champ_join(x['id']), True)):
            self._btn(inner, label, cmd, primary=primary, surface=P).pack(side='right', padx=(6, 0), anchor='n')
        body = tk.Frame(inner, bg=P)
        body.pack(side='left', fill='x', expand=True)
        labels = [self._lbl(body, x.get('name') or '', font=(c.FONT_C, 18), fg=CHAMP, bg=P),
                  self._lbl(body, '   ·   '.join(sub), font=(c.FONT, 9), fg=c.SOFT, bg=P)]
        if about:
            labels.append(self._lbl(body, about, font=(c.FONT, 9), fg=c.MUTED, bg=P))
        for lab in labels:
            lab.pack(anchor='w', pady=(0, 2))
        body.bind('<Configure>', lambda e: [lab.configure(wraplength=max(200, e.width)) for lab in labels[1:]])

    def champ_join(self, cid):
        """JOIN a public championship (asked first): then its rounds are in the list, to DRIVE."""
        x = self._champ(cid)
        if x is None or not self.s.get('token'):
            return
        if not messagebox.askyesno('ACR Daily', _('Join %s? Its rounds then show in RALLIES, to drive when they open.')
                                   % x.get('name', '')):
            return

        def go():
            try:
                self.api.league_join(cid)
                _c().ui(self.root, self._champ_joined, x, None)
            except ApiError as e:
                _c().ui(self.root, self._champ_joined, x, e)
        threading.Thread(target=go, daemon=True).start()

    def _champ_joined(self, x, e):
        if e is not None:
            messagebox.showwarning('ACR Daily', _("Couldn't join %s: %s") % (x.get('name', ''), e))
            return
        self.public_champs = [y for y in self.public_champs or () if y.get('id') != x['id']]
        self.champ_sel = None
        self.sub_l.configure(text=_('You joined %s: its rounds are in RALLIES.') % x.get('name', ''))
        self.refresh_leagues()

    def open_leagues(self):
        if self.api.configured:
            webbrowser.open(self.api.site + '/rallies')

    def open_event_page(self, eid):
        if self.api.configured:
            webbrowser.open(self.api.site + '/e/%d' % eid)

    # -------------------------------------------------------------- DRIVE on an event
    def league_drive(self, eid):
        ev = self._league_event(eid)
        if not ev or getattr(self, '_restarting', False):
            return
        if self._drive_wait:                       # a stake on its way (app.py, credits): the daily's DRIVE goes on then
            self.sub_l.configure(text=self._drive_wait)
            return
        entry = ev.get('entry') or {}
        car = (leagues.car_of(ev, entry.get('car')) if entry.get('car') else None) or self._league_car(ev)
        if not car:
            messagebox.showinfo('ACR Daily', _('Pick your car for %s first (a %s car).') % (ev['name'], ev.get('carClass') or ''))
            return
        if ev.get('hidden') and not ev.get('revealed'):   # its set-up comes from the server now (server src/hidden.js)
            self._league_reveal(ev)
            return
        if not self._fill_routes(ev):                     # to judge the stages like dailies
            self.sub_l.configure(text=_('Getting the stages of %s...') % ev['name'])
            self._league_routes(ev, lambda: self.league_drive(eid))
            return
        run = self.league_run
        if any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or self._tt_running() or \
                (run and not run.get('over') and run['judge'].state == 'running'):
            messagebox.showinfo('ACR Daily', _('Finish or leave the stage you are on first.'))
            return
        if self._waiting_text():                  # (DRIVE may close the game before it saves that run's time)
            messagebox.showinfo('ACR Daily', self._waiting_text())
            return
        if saveslot.game_running():
            # the game is open: if its rally is already this event's, follow it from here without a restart
            try:
                b = saveslot.read_save()
                state, p = leagues.rally_state(b, ev)
                changed = leagues.changed_in_game(rallyweekend.read_weekend(b), ev) if state == 'this' else []
            except (OSError, saveslot.SaveError):
                state, p, changed = None, None, []
            done = (ev.get('entry') or {}).get('done', 0)
            if state == 'this' and p['done'] == done and not changed and not leagues.is_parked(ev['id']):
                self._follow(ev, car)
                self.sub_l.configure(text=_('Following %s: SS%d next. In the game: Racing › Rally › Rally Weekend › RESUME.')
                                     % (ev['name'], done + 1))
                return
            if not messagebox.askyesno('ACR Daily', _('Assetto Corsa Rally is running.\n\nACR Daily will close it, set up '
                                       '%s (%s, %d stages) and start it again. This takes about a minute.\n\nGo?')
                                       % (ev['name'], ev['rally'], len(ev['stages']))):
                return
            self._restart_into_league(ev, car)
            return
        self._league_setup_and_launch(ev, car)

    def _league_reveal(self, ev):
        """DRIVE on a hidden event: ask, then get its stages, weather and start times from the server (which keeps that
        they were given), and go on with DRIVE."""
        if not messagebox.askyesno('ACR Daily', _('%s keeps its %s hidden until it ends.\n\nDRIVE gets them now and sets the '
                                   'rally up: from then on you know them, so start it as soon as you can.\n\nGo?')
                                   % (ev['name'], hidden_what(ev['hidden']))):
            return
        self.sub_l.configure(text=_('Getting the stages of %s...') % ev['name'])

        def go():
            try:
                full = self.api.reveal(ev['id'])
                _c().ui(self.root, self._league_revealed, ev['id'], full)
            except ApiError as e:
                _c().ui(self.root, self.sub_l.configure, {'text': _('Could not get the stages of %s (%s). Try again.') % (ev['name'], e)})
        threading.Thread(target=go, daemon=True).start()

    def _league_revealed(self, eid, full):
        ev = self._league_event(eid)
        if not ev:
            return
        for k in ('stages', 'lengthM', 'hidden', 'revealed', 'cars', 'days'):   # (its entry, league and opponent stay)
            if k in full:
                ev[k] = full[k]
        ev['revealed'] = True
        self._render_leagues()
        self.league_drive(eid)

    def _restart_into_league(self, ev, car):
        self._close_game_then(ev['name'], lambda: self._league_setup_and_launch(ev, car))

    def _league_setup_and_launch(self, ev, car):
        first = ev['stages'][0]
        try:
            b = saveslot.read_for_daily({'stageId': first['stageId'], 'carId': car['id'], 'weatherGame': first['weatherGame'],
                                         'startSeconds': first['startSeconds']})
            changed = False
            for _i in range(len(self.league_events) + 2):
                action, details = leagues.plan(ev, b, self.league_events)
                if action not in ('park-other', 'park-own'):
                    break
                other = details
                ask = (self._own_text(other, ev['name']) if action == 'park-own' else
                       _('The game holds your rally for %s (%d of %d stages done).\n\nACR Daily will set it aside and put '
                       'it back when you click CONTINUE on it.') % (other['name'], (other.get('entry') or {}).get('done', 0),
                                                                   len(other['stages'])))
                if not messagebox.askyesno('ACR Daily', ask + ('\n\n' + _('Go on?'))):
                    return
                b = leagues.apply_plan(ev, car, action, details, b)   # (it waits in its own file; the save is written once)
                changed = True
                self._render_strip()
            new = leagues.apply_plan(ev, car, action, details, b)
            if new is not None or changed:
                saveslot.replace(new if new is not None else b)
            if action in ('setup', 'reset', 'unpark') or leagues.is_parked(ev['id']) and action == 'resume':
                leagues.forget_parked(ev['id'])        # (a rally set aside before the start, or an older copy)
            if action == 'unpark-own':                 # (it was in PUT BACK's list: it is the event's again)
                leagues.forget_own(details)
                self._render_strip()
            if action == 'missed':
                if not self._league_missed(ev, details):
                    return
        except leagues.Gone as g:
            why = g.args[0] if g.args else str(g)
            self._league_dnf_entry(ev, why)
            messagebox.showwarning('ACR Daily', _('Your entry in %s ends here (DNF): %s.') % (ev['name'], local(why)))
            return
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', str(e))
            return
        self._follow(ev, car)
        if action in ('setup', 'reset'):
            path = (_('In the game: any key › E (Racing) › Rally › Rally Weekend › START RALLY › J (automatic tyres) › '
                    'CONFIRM AND START RALLY › Start Stage. Everything is set up.'))
        else:
            path = _('In the game: Racing › Rally › Rally Weekend › RESUME, then Start Stage (SS%d).') % ((details or 0) + 1 if
                                                                                                  action == 'resume' else
                                                                                                  (ev.get('entry') or {}).get('done', 0) + 1)
        done = (ev.get('entry') or {}).get('done', 0)
        back = details if action == 'resume' else 0 if action == 'setup' else done
        if (ev.get('entry') or {}).get('status') == 'running' and back < done:
            # the game took its rally back (quit away from a service park, a crash): the counted stages again
            path += ' ' + self._again_text(back, done)
            messagebox.showinfo('ACR Daily', self._again_text(back, done) + '\n\n' + STOP_HINT)
        self.sub_l.configure(text=(_('Starting the game...') + ' ') + path)
        try:
            saveslot.launch_game()
        except OSError:
            self.sub_l.configure(text=(_('Set up. Start the game from Steam.') + ' ') + path)
        if self.s.get('autoDrive') and action in ('setup', 'reset'):
            if getattr(self, 'auto', None):
                self.auto.cancel()
            self.auto = autodrive.AutoDrive(lambda t: _c().ui(self.root, self.sub_l.configure, {'text': t}), 'weekend').start()

    def _league_missed(self, ev, upto):
        """The game's rally has `upto` stages done, more than the entry: those were driven without the app watching.
        Under the event's retirement rule each counts as retired (its slowest time + the rule's minutes; server
        leaguesapi.js missed) and the entry goes on from there. -> True when there is a stage left to follow."""
        e = ev['entry']
        done, n = e.get('done', 0), len(ev['stages'])
        for k in range(done, upto):
            self._league_send({'kind': 'missed', 'eventId': ev['id'], 'no': k,
                               'reason': said('SS%d was driven without ACR Daily watching', k + 1)})
        e['done'] = upto
        if upto >= n:
            e['status'] = 'finished'
        self._render_leagues()
        minutes = (ev.get('rules') or {}).get('retire') or 0
        which = 'SS%d' % upto if upto - done == 1 else 'SS%d–SS%d' % (done + 1, upto)
        messagebox.showinfo('ACR Daily', _('%s was driven without ACR Daily watching, so it counts as retired: the slowest '
                                           'time on it + %d min.') % (which, minutes) + '\n\n' + (
            _('Go on with SS%d.') % (upto + 1) if upto < n else _('That was the last stage: your rally is over.')))
        return upto < n

    @staticmethod
    def _again_text(back, done):
        """The game took the rally back to SS(back + 1) while the entry has `done` stages counted."""
        return (_('The game took your rally back to SS%d. Drive SS%d to SS%d again to get to SS%d: they count for '
                  'nothing, your times on them stand.') % (back + 1, back + 1, done, done + 1) if done - back > 1 else
                _('The game took your rally back to SS%d. Drive it again to get to SS%d: it counts for nothing, your '
                  'time on it stands.') % (back + 1, done + 1))

    def _follow(self, ev, car):
        """From now on the frames are judged for the event's next stage (its routes fetched: _league_routes)."""
        if not self._fill_routes(ev):
            self._league_routes(ev, lambda: self._follow(ev, car))
            return
        done = (ev.get('entry') or {}).get('done', 0)
        self.league_run = {'ev': ev, 'car': car, 'no': done, 'judge': Judge(leagues.stage_ch(ev, done, car)),
                           'known': None, 'ignore': None, 'wait': None}
        self.drive_target = 'league'
        key = self._lr_key(ev) if ev.get('kind') == 'live' else None
        if ev.get('kind') == 'live':                  # a ranked rally's session: its page (liverallyui.py), no tab of events
            self.open_live_rallies(key)
            return
        self.toggle_league_view(True, tab_of(ev))     # (its tab: RALLIES, 1V1 or CUPS)
        self.league_sel = ev['id']
        self._render_leagues()

    def _held(self, b=None):
        """The rally in progress in the game's save: ('league', the event) for one of my events (my entry running, or
        not started with no stage driven), ('own', describe()) for any other, or None."""
        try:
            if b is None:                          # (asked on DRIVE, once: not one of the app's own looks)
                b = saveslot.read_save()
            p = rallyweekend.progress(b)
            if p is None:
                return None
            ev = leagues.owner_of(b, self.league_events)
            return ('league', ev) if ev else ('own', leagues.describe(p, rallyweekend.read_weekend(b)['preset']))
        except (OSError, saveslot.SaveError):
            return None

    @staticmethod
    def _set_aside_text(ev):
        e = ev.get('entry') or {}
        return (_('Your rally %s is in progress (%d of %d stages).\n\nIt will be set aside for the daily. Nothing is '
                'lost: CONTINUE on the event puts it back.') % (ev['name'], e.get('done', 0), len(ev['stages'])))

    @staticmethod
    def _own_text(info, what=_('the daily')):
        return (_('Your own Rally Weekend is in progress (%s, %d of %d stages).\n\nIt will be set aside for %s. Nothing '
                'is lost: PUT BACK returns it.') % (info['location'], info['done'], info['stages'], what))

    def _league_before_daily(self, weekend):
        """DRIVE on a daily, before anything changes. A league stage being driven comes first: the daily's set-up closes
        the game, and that stage would be a DNF. A rally in progress in the game (a league event's, or the player's
        own) is set aside for a daily set up as a Rally Weekend: said once, here. -> None to stop, else whether the
        driver was told (then the game-is-running question is not asked again)."""
        self._park_said = None
        run = self.league_run
        if run and not run.get('over') and (run['judge'].state == 'running' or run.get('wait')):
            messagebox.showinfo('ACR Daily', _('Finish your stage of %s first, or it will be a DNF.') % run['ev']['name'])
            return None
        h = self._held() if weekend else None
        if h and h[0] == 'league' and (h[1].get('entry') or {}).get('status') == 'running':
            text, said = self._set_aside_text(h[1]), h[1]['id']
        elif h and h[0] == 'own':
            text, said = self._own_text(h[1]), 'own'
        else:
            return False
        more = ('\n\n' + _('The game will restart.')) if saveslot.game_running() else ''
        if not messagebox.askyesno('ACR Daily', text + more + ('\n\n' + _('Drive the daily?'))):
            return None
        self._park_said = said
        return True

    def _league_park_for_daily(self):
        """Before a daily is set up as a Rally Weekend: a rally in progress is set aside, a league event's or the
        player's own (asked first, unless _league_before_daily did; a league event not started yet, with no stage
        driven, needs no question). -> False to stop the daily's set-up."""
        try:
            b = saveslot.read_save()
        except OSError:
            return True
        h = self._held(b)
        said, self._park_said = getattr(self, '_park_said', None), None
        if not h:
            return True
        kind, x = h
        if kind == 'own':
            ask = said != 'own' and self._own_text(x)
        else:
            ask = (x.get('entry') or {}).get('status') == 'running' and said != x['id'] and self._set_aside_text(x)
        if ask and not messagebox.askyesno('ACR Daily', ask + ('\n\n' + _('Go on?'))):
            return False
        try:
            saveslot.replace(leagues.park_own(b) if kind == 'own' else leagues.park(b, x['id']))
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', str(e))
            return False
        self._render_strip()
        return True

    # -------------------------------------------------------------- PUT BACK: the player's own rally set aside
    def put_back_own(self, path):
        """Return the player's own rally set aside (leagues.own_parked) to the game, closing the game first if it is
        running; the rally in its place, if any, is set aside in turn."""
        if getattr(self, '_restarting', False):
            return
        run = self.league_run
        if any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or self._tt_running() or \
                (run and not run.get('over') and run['judge'].state == 'running'):
            messagebox.showinfo('ACR Daily', _('Finish or leave the stage you are on first.'))
            return
        if self._waiting_text():
            messagebox.showinfo('ACR Daily', self._waiting_text())
            return
        if saveslot.game_running():
            if not messagebox.askyesno('ACR Daily', _('Assetto Corsa Rally is running.\n\nACR Daily will close it, put your '
                                                    'rally back and start it again. This takes about a minute.\n\nGo?')):
                return
            self._close_game_then(_('your rally'), lambda: self._put_back_now(path))
            return
        self._put_back_now(path)

    def _put_back_now(self, path):
        try:
            if not os.path.exists(saveslot.SAVE):
                raise saveslot.SaveError(_('No game save found.'))
            b = saveslot.read_save()
            h = self._held(b)
            if h and h[0] == 'league' and (h[1].get('entry') or {}).get('status') == 'running' and \
                    not messagebox.askyesno('ACR Daily', _('Your rally %s is in progress in the game. ACR Daily sets '
                                                         'it aside (CONTINUE on it in RALLIES puts it back). Go on?') % h[1]['name']):
                return
            new, _moved = leagues.put_back(b, path, self.league_events)
            saveslot.replace(new)
            leagues.forget_own(path)
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', _('Your rally could not be put back: %s') % e)
            return
        self.drive_target = 'daily'
        self._render_strip()
        if self.league_view:
            self._render_leagues()
        path_txt = _('In the game: Racing › Rally › Rally Weekend › RESUME.')
        self.sub_l.configure(text=(_('Your rally is back. Starting the game...') + ' ') + path_txt)
        try:
            saveslot.launch_game()
        except OSError:
            self.sub_l.configure(text=(_('Your rally is back. Start the game from Steam.') + ' ') + path_txt)

    def _close_game_then(self, what, then):
        """Close the game the normal way (it saves on exit), wait for it, then call then()."""
        self._restarting = 'league'
        saveslot.ask_game_to_quit()
        t0 = time.monotonic()

        def wait():
            if not saveslot.game_running():
                self.sub_l.configure(text=_('Game closed. Setting up %s...') % what)
                self._restart_job = self.root.after(4000, lambda: (setattr(self, '_restarting', False), then()))
                return
            waited = time.monotonic() - t0
            if waited > 120:
                self._restarting = False
                self.sub_l.configure(text=_('The game did not close. Quit it from its menu, then try again.'))
                return
            if 8 < waited < 9 or 30 < waited < 31:
                saveslot.ask_game_to_quit()
            self.sub_l.configure(text=_('Closing Assetto Corsa Rally... (%d s) If the game asks, confirm quitting.') % waited)
            self._restart_job = self.root.after(1000, wait)
        self._restart_job = self.root.after(1000, wait)

    # -------------------------------------------------------------- the loop: the event's next stage
    def _league_tick(self, f, unloaded):
        run = self.league_run
        if not run or run.get('wait') or run.get('over'):
            return
        j = run['judge']
        for e in j.feed(f, unloaded):
            if e == 'start':
                self._league_started(run)
                self._league_live(run, f, 'live', force=True)
            elif e == 'finished':
                self._league_live(run, f, 'finished', force=True)
                self._league_finished(run)
            elif e in ('dnf', 'invalid'):
                self._league_live(run, f, 'dnf', force=True)
                self._league_failed(run, (j.result or {}).get('reason') or e)
        if j.state == 'running':
            self._league_live(run, f, 'live')

    def _league_live(self, run, f, state, force=False):
        """Where we are on the event's stage, for the website (a cup match followed live on its map): every liveSendS
        while on it, and at the start, the finish or a DNF. Not for a run that doesn't count, nor signed out."""
        if run.get('ignore') or not self.s.get('token') or not self.api.configured:
            return
        now = time.monotonic()
        if not force and now - run.get('live_at', 0) < self.timing('liveSendS'):
            return
        run['live_at'] = now
        j = run['judge']
        body = {'no': run['no'], 'progress': round(j.progress or 0.0, 4), 'totalMs': j.total_ms, 'state': state}
        if f is not None:
            body.update(x=round(f.x, 1), z=round(f.z, 1))
        ev_id = run['ev']['id']
        threading.Thread(target=self.api.event_live, args=(ev_id, body), daemon=True).start()

    def _league_started(self, run):
        ev, k = run['ev'], run['no']
        run['known'] = None
        run['ignore'] = None
        run['missed'] = None
        run['again'] = False
        changed, again = [], False
        try:                                       # this stage must be driven in the event's own rally
            b = saveslot.read_save()
            run['known'] = leagues.known(b)        # the game's result of this stage will be a new one
            w = rallyweekend.read_weekend(b)
            if k == 0:
                ok = leagues.same_calendar(w['stages'], ev)
            else:
                state, p = leagues.rally_state(b, ev)
                ok = state == 'this' and p['done'] == k
                again = state == 'this' and p['done'] < k
            changed = leagues.changed_in_game(w, ev) if ok else []
            read = True
        except (OSError, saveslot.SaveError):
            ok, read = False, False
        live = ev.get('kind') == 'live'
        if live and not again and read and (not ok or changed and (k == 0 or not ev.get('entry'))):
            # a ranked rally: every start on its stages counts (nobody prepares them): outside its Rally Weekend, or with
            # its settings changed in the game, a DNF, not a run that just doesn't count (liverallyui.py)
            self._lr_out(ev, k, said('SS%d driven outside the session\'s Rally Weekend', k + 1) if not ok else
                         said('the session\'s %s changed in the game', ', '.join(changed)))
            return
        if live and not read:                      # (the save not read now: counted; its official time tells later)
            ok = True
        if again:                                  # the game took its rally back: a counted stage driven again
            run['again'] = True
            run['ignore'] = _('SS%d counted already: driven again it changes nothing. Go on to SS%d') % (p['done'] + 1, k + 1)
            run['ignore_short'] = _('SS%d counted already') % (p['done'] + 1)
            self.sub_l.configure(text=_('SS%d: %s.') % (k + 1, run['ignore']))
            return
        if not ok:
            run['ignore'] = _('not in the event\'s rally: this run does not count (click DRIVE AGAIN on the event, then ' \
                            'Rally Weekend › Resume)')
            run['ignore_short'] = _('not the event\'s rally')
            self.sub_l.configure(text=_('SS%d: %s') % (k + 1, run['ignore']))
            return
        if changed and (k == 0 or not ev.get('entry')):
            # changed in the game's menus before the rally started: nothing counts yet, set it up again
            run['ignore'] = (_('the event\'s %s changed in the game\'s menus: this run does not count. Click DRIVE AGAIN on '
                             'the event: ACR Daily sets it up afresh') % ', '.join(_(x) for x in changed))
            run['ignore_short'] = _('%s changed in the game') % ', '.join(_(x) for x in changed)
            self.sub_l.configure(text=_('SS%d: %s.') % (k + 1, run['ignore']))
            return
        if changed:                                # the rally ran with other settings: the entry ends
            self._league_failed(run, said('the event\'s %s changed in the game', ', '.join(changed)))
            return
        # the server keeps each stage's first start: a stage started again (after the app was closed during it, say)
        # ends the entry, as a restart does. `at` (when this start was) tells it this same start sent again (a send
        # retried after the server had it) from a second one
        at = run['judge'].started_ms
        # a ranked rally's session: the start on the server's clock too, for its turn to judge (liverallyui.py)
        server_at = self._lr_server_ms(at) if ev.get('kind') == 'live' and at is not None else None
        live = {'serverAt': server_at} if server_at is not None else {}
        if not ev.get('entry'):
            ev['entry'] = {'status': 'running', 'done': 0, 'totalMs': 0, 'car': run['car']['name'], 'reason': ''}
            self._league_send(dict({'kind': 'start', 'eventId': ev['id'], 'car': run['car']['name'], 'at': at}, **live))
        else:
            self._league_send(dict({'kind': 'begin', 'eventId': ev['id'], 'no': k, 'at': at}, **live))
        self.sub_l.configure(text=_('%s · SS%d of %d LIVE') % (ev['name'], k + 1, len(ev['stages'])))

    def _league_finished(self, run):
        if run['ignore']:
            self._league_rearm(run)
            return
        ev, k = run['ev'], run['no']
        self._lr_finished(ev, k)                   # a ranked rally's session: the next stage's queue, now (liverallyui.py)
        r = dict(run['judge'].result)
        w = run['wait'] = {'id': 'league:%d:%d:%s' % (ev['id'], k, r.get('startedAt')), 'result': r,
                           'until': time.time() + OFFICIAL_WAIT_S, 'closed': 0, 'other': None,
                           'watch': saveslot.SaveWatch()}
        try:                                       # on disk too: closing the app loses nothing (waiting.py)
            waiting.add({'id': w['id'], 'kind': 'league', 'eventId': ev['id'], 'no': k, 'stageId': ev['stages'][k]['stageId'],
                         'carId': run['car']['id'], 'result': r, 'until': w['until'],
                         'known': leagues.known_to_json(run['known']) if run['known'] is not None else None,
                         'event': {'name': ev['name'], 'rules': ev.get('rules'),
                                   'stages': [{x: s.get(x) for x in ('stageId', 'weatherGame', 'startSeconds', 'day', 'service')}
                                              for s in ev['stages']]}})
        except (OSError, TypeError, ValueError):
            pass
        self.sub_l.configure(text=_('SS%d finished. %s') % (k + 1, waiting.HINT))
        self.root.after(OFFICIAL_CHECK_MS, self._league_check_official)

    def _league_wait_step(self, b, w, ev, stage_id, car_id, known):
        """One look at the game's save (b) for a league stage waiting for its official result. w: {'result', 'until',
        'closed', 'other'}, updated; ev: the event (its rules and stages). -> ('stage', the game's result), ('dnf', why)
        or None: still waiting."""
        tag = w.get('id') or 'league'
        if b is not None:
            waiting.note('%s: save read; %s' % (tag, rallyweekend.describe(b, stage_id, car_id)))
        out = self._league_match(b, w, ev, stage_id, car_id, known)
        if out:
            return out
        gw = self._game_watch_on()
        if gw is not None:
            gw.process(saveslot.game_pids)           # (gamewatch.py: for the report if the game loses this result)
        w['closed'] = 0 if saveslot.game_running() else w['closed'] + 1
        if w['closed'] >= 3 or time.time() > w['until']:
            last = saveslot.read_save_now()        # a last look at the save as it is now (app.py: _check_official)
            waiting.note('%s: last look: %s' % (tag, rallyweekend.describe(last, stage_id, car_id)))
            out = self._league_match(last, w, ev, stage_id, car_id, known)
            if out:
                return out
            why = (said('the game saved %s, not this stage\'s time', fmt_ms(round(w['other']['time'] * 1000)))
                   if w['other'] else said('the game closed before saving its official result') if w['closed'] >= 3
                   else said('no official result from the game'))
            waiting.note('%s: DNF: %s' % (tag, why))
            w['lost'] = not w['other']             # the game saved nothing of it: its log goes to the admin (gamelog.py)
            return 'dnf', why
        return None

    def _league_match(self, b, w, ev, stage_id, car_id, known):
        """The stage's result in the save b -> ('stage', o), ('dnf', why) if the event's settings changed in the game,
        or None (w['other']: a new result with another time). A result that was in the save at the start still counts
        when its time is the app's to OFFICIAL_SAME_MS (app.py: _official_match)."""
        if not b:
            return None
        r = w['result']
        o = leagues.official(b, stage_id, car_id, known or set())
        if not (o and abs(o['time'] * 1000 - r['clockMs']) <= OFFICIAL_CLOCK_MS):
            same = rallyweekend.official(b, stage_id, car_id, clock_ms=r['clockMs'], tol_ms=OFFICIAL_SAME_MS)
            if not same:
                w['other'] = o or w['other']
                return None
            o = same
        try:                                       # the save written with the result: still the event's settings?
            changed = leagues.changed_in_game(rallyweekend.read_weekend(b), ev)
        except saveslot.SaveError:
            changed = []
        waiting.note('%s: the game\'s result found: %.3f +%g%s' % (w.get('id') or 'league', o['time'], o['penalty'],
                                                                   ' (settings changed)' if changed else ''))
        if not changed:
            self._saved_at = time.monotonic()     # (the timer window: saved, in green, for a moment: app._render_saving)
        return ('dnf', said('the event\'s %s changed in the game', ', '.join(changed))) if changed else ('stage', o)

    def _league_check_official(self):
        """Every OFFICIAL_CHECK_MS while the stage just driven waits: its result in the game's save yet? (Read only
        once the game has written it: saveslot.SaveWatch.)"""
        run = self.league_run
        if not run or not run.get('wait'):
            return
        w, ev, k = run['wait'], run['ev'], run['no']
        watch = w.setdefault('watch', saveslot.SaveWatch())
        out = self._league_wait_step(watch.look(), w, ev, ev['stages'][k]['stageId'], run['car']['id'], run['known'])
        if out is None:
            self.root.after(OFFICIAL_CHECK_MS, self._league_check_official)
            return
        waiting.remove(w.get('id'))
        if out[0] == 'stage':
            self._league_stage_done(run, out[1])
        else:
            run['wait'] = None
            self._league_failed(run, out[1])
            if w.get('lost'):
                self._league_game_log(ev['id'], ev['name'], k, ev['stages'][k]['stageId'], run['car']['id'], w, out[1])

    def _league_send_stage(self, event_id, k, r, o):
        """Send stage k of an event with the game's own result o (and keep it in results.jsonl). -> (time, penalty) ms."""
        time_ms, pen_ms = int(round(o['time'] * 1000)), int(round(o['penalty'] * 1000))
        self._league_send({'kind': 'stage', 'eventId': event_id, 'no': k, 'timeMs': time_ms, 'penaltyMs': pen_ms,
                           'splitsMs': [int(round(t * 1000)) for t in o['splits']], 'startedAt': r.get('startedAt'),
                           'clockMs': r.get('clockMs'), 'resets': r.get('resets')})
        settings.append_result(dict(r, challengeId='league:%d:%d' % (event_id, k), official={'timeMs': time_ms, 'penaltyMs': pen_ms},
                                    totalMs=time_ms + pen_ms))
        return time_ms, pen_ms

    def _league_resume_waiting(self):
        """League stages left waiting for the game's official result when the app last closed: looked for again."""
        if self._league_restored:
            x = self._league_restored[0]
            self.sub_l.configure(text=_('%s: SS%d is still waiting for the game\'s official time: looking for it in the '
                                      'game\'s save. %s') % (x['event'].get('name') or _('League event'), x['no'] + 1, waiting.HINT))
            self._restored_watch = saveslot.SaveWatch()
            self.root.after(OFFICIAL_CHECK_MS, self._league_check_restored)

    def _league_check_restored(self):
        """Every OFFICIAL_CHECK_MS while such stages wait: sent with the game's result as if the app had stayed open
        (or a DNF, saying why); following the event goes on from there (CONTINUE, or the autofollow)."""
        if getattr(self, '_restored_watch', None) is None:
            self._restored_watch = saveslot.SaveWatch()
        b = self._restored_watch.look()
        for x in list(self._league_restored):
            out = self._league_wait_step(b, x, x['event'], x['stageId'], x['carId'], x['known'])
            if out is None:
                continue
            self._league_restored.remove(x)
            waiting.remove(x['id'])
            name, k = x['event'].get('name') or _('League event'), x['no']
            if out[0] == 'stage':
                t, p = self._league_send_stage(x['eventId'], k, x['result'], out[1])
                self.sub_l.configure(text=_('%s · SS%d: %s + %d s (official), sent. CONTINUE on the event goes on from '
                                          'there.') % (name, k + 1, fmt_ms(t), round(p / 1000)))
            else:
                self._league_send({'kind': 'dnf', 'eventId': x['eventId'], 'no': k, 'reason': out[1]})
                self.sub_l.configure(text=_('%s: DNF on SS%d (%s).') % (name, k + 1, local(out[1])))
                if x.get('lost'):
                    self._league_game_log(x['eventId'], name, k, x['stageId'], x['carId'], x, out[1])
        if self._league_restored:
            self.root.after(OFFICIAL_CHECK_MS, self._league_check_restored)

    def _league_game_log(self, event_id, name, k, stage_id, car_id, w, why):
        """A league, 1V1 or cup stage the game didn't save the result of: the game's log goes to the admin (app.py
        _send_game_log, gamelog.py). w: its wait ({'id', 'result'})."""
        api = getattr(self, 'api', None)
        if api is None:
            return
        try:
            kind = next((e.get('kind') for e in (getattr(self, 'league_events', None) or [])
                         if e.get('id') == event_id), None)
            r = w.get('result') or {}
            gamelog.send(api, [{'id': w.get('id') or 'league', 'what': '%s · SS%d' % (name, k + 1), 'stage': stage_id,
                                'car': car_id, 'startedAt': r.get('startedAt'), 'clockMs': r.get('clockMs'),
                                'why': str(why)}],
                         {'h2h': '1v1', 'cup': 'cup'}.get(kind, 'league'), '%s/e/%d' % (api.site, event_id),
                         self._game_log_context(), on_sent=self._game_log_sent, watch=self._game_watch_seen())
        except Exception:                          # (a report never holds up the waits)
            import traceback
            traceback.print_exc()

    def _league_stage_done(self, run, o):
        ev, k, r = run['ev'], run['no'], run['wait']['result']
        run['wait'] = None
        time_ms, pen_ms = self._league_send_stage(ev['id'], k, r, o)
        self._notify(True, _('Official time saved'), '%s · SS%d: %s' % (ev['name'], k + 1, fmt_ms(time_ms + pen_ms)))
        # a comment on the stage, for whoever runs the event: its card pops up (commentui.py; sent after the stage's result)
        self.offer_comment('event:%d/%d' % (ev['id'], k), '%s · SS%d · %s' % (ev['name'], k + 1, fmt_ms(time_ms + pen_ms)),
                           ev.get('kind') or 'league', 'SS%d' % (k + 1), title=_('SS%d FINISHED') % (k + 1))
        e = ev['entry'] = ev.get('entry') or {'status': 'running', 'done': 0, 'totalMs': 0}
        e['done'], e['totalMs'] = k + 1, (e.get('totalMs') or 0) + time_ms + pen_ms
        n = len(ev['stages'])
        if k + 1 >= n:
            e['status'] = 'finished'
            run['over'] = True
            self.drive_target = 'daily'
            self.sub_l.configure(text=_('%s finished: %s (SS%d: %s + %d s). Well driven!') % (
                ev['name'], fmt_ms(e['totalMs']), k + 1, fmt_ms(time_ms), round(pen_ms / 1000)))
        else:
            run['no'] = k + 1
            run['judge'] = Judge(leagues.stage_ch(ev, k + 1, run['car']))
            self.sub_l.configure(text=_('SS%d: %s + %d s (official). Next: SS%d %s. Go on in the game, or stop and come back '
                                      'before the event closes (Rally Weekend › Resume).') % (
                                          k + 1, fmt_ms(time_ms), round(pen_ms / 1000), k + 2, ev['stages'][k + 1]['name'])
                                  + ' ' + STOP_HINT)
        self._render_leagues()

    def _league_rearm(self, run):
        """A run that didn't count (outside the event's rally, or its set-up changed in the game): the same stage again.
        Why it didn't count stays on the timer window and the event's button reads DRIVE AGAIN (missed) until the next
        start, so it isn't taken for a run that counted."""
        if run.get('ignore') and not run.get('again'):   # (a counted stage driven again: nothing missed)
            run['missed'], run['missed_short'] = run['ignore'], run.get('ignore_short') or _('did not count')
            self._render_leagues()
        run['judge'] = Judge(leagues.stage_ch(run['ev'], run['no'], run['car']))
        run['ignore'] = None

    def _league_failed(self, run, reason):
        if run.get('ignore'):
            self._league_rearm(run)
            return
        if not (run['ev'].get('entry')):            # never started (e.g. invalid before the start): nothing to end
            self._league_rearm(run)
            self.sub_l.configure(text=_('Not started: %s') % local(reason))
            return
        self._league_dnf_entry(run['ev'], reason, run['no'])
        self._notify(False, _('DNF'), '%s · SS%d: %s' % (run['ev']['name'], run['no'] + 1, local(reason)))
        ev = run['ev']                              # a comment on the stage it ended on (commentui.py)
        self.offer_comment('event:%d/%d' % (ev['id'], run['no']), '%s · SS%d · %s' % (ev['name'], run['no'] + 1, _('DNF')),
                           ev.get('kind') or 'league', 'SS%d' % (run['no'] + 1), title='SS%d %s' % (run['no'] + 1, _('DNF')))
        run['over'] = True
        self.drive_target = 'daily'
        self.sub_l.configure(text=_('%s: DNF on SS%d (%s).') % (run['ev']['name'], run['no'] + 1, local(reason)))

    def _league_server_dnf(self, eid, reason):
        """The server ended the entry (a stage started a second time): stop following the event."""
        run = self.league_run
        if run and run['ev']['id'] == eid and not run.get('over'):
            run['over'] = True
            if run.get('wait'):
                waiting.remove(run['wait'].get('id'))
            run['wait'] = None
            self.drive_target = 'daily'
            self.sub_l.configure(text=_('%s: DNF (%s). The first start of each stage is the one that counts.')
                                 % (run['ev']['name'], local(reason)))
        ev = self._league_event(eid)
        if ev:
            ev['entry'] = dict(ev.get('entry') or {'done': 0, 'totalMs': 0}, status='dnf', reason=reason)
        self._render_leagues()

    def _league_dnf_entry(self, ev, reason, no=None):
        e = ev['entry'] = ev.get('entry') or {'done': 0, 'totalMs': 0}
        e['status'], e['reason'] = 'dnf', reason
        self._league_send({'kind': 'dnf', 'eventId': ev['id'], 'no': e.get('done', 0) if no is None else no, 'reason': reason})
        self._render_leagues()

    # -------------------------------------------------------------- sending, in order (kept until the server has it)
    def _league_send(self, item):
        with self._league_lock:
            q = leagues.pending()
            q.append(item)
            leagues.save_pending(q)
        threading.Thread(target=self.flush_leagues, daemon=True).start()

    def flush_leagues(self):
        """Send what waits, oldest first; stop at the first network failure (the order matters)."""
        if not self.s.get('token'):
            return
        with self._league_lock:
            q = leagues.pending()
            sent_any = False
            while q:
                it = q[0]
                try:
                    live = {'server_at': it['serverAt']} if it.get('serverAt') is not None else {}   # (a ranked rally's)
                    if it['kind'] == 'start':
                        r = self.api.league_start(it['eventId'], it['car'], it.get('at'), **live)
                    elif it['kind'] == 'begin':
                        r = self.api.league_begin(it['eventId'], it['no'], it.get('at'), **live)
                    elif it['kind'] == 'stage':
                        r = self.api.league_stage(it['eventId'], {k: v for k, v in it.items() if k not in ('kind', 'eventId')})
                    elif it['kind'] == 'missed':
                        r = self.api.league_missed(it['eventId'], it['no'], it['reason'])
                    else:
                        r = self.api.league_dnf(it['eventId'], it['no'], it['reason'])
                    if it['kind'] in ('start', 'begin', 'missed') and (r or {}).get('status') == 'dnf':   # a stage started again
                        _c().ui(self.root, self._league_server_dnf, it['eventId'], r.get('reason') or _('DNF'))
                    elif it['kind'] in ('start', 'begin') and isinstance((r or {}).get('slot'), dict):   # a ranked rally's start
                        _c().ui(self.root, self._lr_started, it['eventId'], r['slot'])
                except ApiError as e:
                    if e.code is None or e.code >= 500 or e.code == 401:
                        break                        # offline or signed out: later
                    if e.code == TOO_OLD:
                        _c().ui(self.root, self.check_update)
                    _c().ui(self.root, self.sub_l.configure, {'text': _('League: %s') % e})
                q.pop(0)
                sent_any = True
                leagues.save_pending(q)
        if sent_any:
            _c().ui(self.root, self.refresh_leagues)

    # -------------------------------------------------------------- what the window and the timer show
    def _league_overlay_state(self, f):
        """While following an event: (status, sub-line, overlay args) for its stage, else None."""
        c = _c()
        run = self.league_run
        if not run:
            return None
        ev, k, j = run['ev'], run['no'], run['judge']
        n = len(ev['stages'])
        st = ev['stages'][min(k, n - 1)]
        stage = 'SS%d/%d · %s' % (min(k, n - 1) + 1, n, st['name'].upper())
        if self.drive_target != 'league':
            # an event just over (a DNF, or finished): its result stays on screen while the game is still on its stage
            if not (run.get('over') and f is not None and f.track and j._right(f)):
                return None
            e = ev.get('entry') or {}
            if e.get('status') == 'finished':
                return (_('%s finished: %s') % (ev['name'], fmt_ms(e.get('totalMs') or 0)), '',
                        ('finished', stage, e.get('totalMs') or 0, 0, _('Event finished'), c.SOFT))
            reason = local(e.get('reason') or (j.result or {}).get('reason') or '')
            return (_('%s: DNF (%s)') % (ev['name'], reason), '', ('dnf', stage, (j.result or {}).get('clockMs', 0),
                                                                 (j.result or {}).get('resets', 0), _('DNF: %s') % reason, c.BAD))
        if run.get('wait'):
            return (j.message, '', ('finished', stage, j.total_ms, j.resets, self._lr_next_line(run) or self._next_line(),
                                    c.SOFT))
        if j.state == 'running':
            if run['ignore']:
                return ((_('NOT COUNTING ·') + ' ') + j.message, '', ('live', stage, j.total_ms, j.resets,
                                                            (_('NOT COUNTING:') + ' ') + run.get('ignore_short', 'not the event\'s rally'), c.BAD))
            line, lc = _('On stage · %d%%') % round(j.progress * 100), c.SOFT
            if j.paused:
                line = _('PAUSED · the run carries on with the clock')
            elif 0 <= j.total_ms < c.COUNTS_LIVE_MS:   # (its first seconds: no restart now)
                line, lc = c.COUNTS_LINE, c.SLOW
            return (j.message, '', ('live', stage, j.total_ms, j.resets, line, lc))
        live = self._lr_overlay(run, stage)        # a ranked rally's session: my turn, or the wait for it (liverallyui.py)
        if live:
            return live
        if j.state == 'armed':
            return (j.message, '', ('ready', stage, 0, 0, c.COUNTS_LINE, c.SLOW))
        if f is None:
            return (_('Waiting for Assetto Corsa Rally'), '', ('standby', (_('LEAGUE ·') + ' ') + ev['name'].upper(), 0, 0, _('Waiting for the game'), c.MUTED))
        if j.approaching:
            return (j.message, '', ('standby', stage, 0, 0, _('Drive up to the start line'), c.SOFT))
        back = self._counted_again(run, f)
        if back is not None:                       # the game took its rally back: a counted stage, driven again
            return (_('SS%d counted already: drive it to get back to SS%d. It changes nothing.') % (back + 1, k + 1), '',
                    ('standby', stage, 0, 0, _('SS%d counted already · on to SS%d') % (back + 1, k + 1), c.SOFT))
        if run.get('missed'):                      # the last run didn't count: say why until the next start
            return (_('SS%d did not count: %s.') % (k + 1, run['missed']), '',
                    ('standby', stage, 0, 0, _('NOT COUNTED: %s · DRIVE AGAIN on the event') % run['missed_short'], c.BAD))
        return (_('%s: load SS%d %s · %s (Rally Weekend › Resume)') % (ev['name'], k + 1, st['name'], run['car']['name']), '',
                ('standby', stage, 0, 0, _('Next: SS%d in the event\'s rally') % (k + 1), c.MUTED))

    @staticmethod
    def _counted_again(run, f):
        """The game is on one of the event's counted stages (before run['no']), not the next one: -> its index, else
        None. (The game took its rally back: those stages are driven again to get to the next.)"""
        j = run['judge']
        if f is None or not f.track or names.same_track(f.track, j.ch) or f.track == j._track_alias:
            return None
        for i in range(run['no']):
            if names.same_track(f.track, leagues.stage_ch(run['ev'], i, run['car'])):
                return i
        return None

    def _league_widget_view(self, f):
        """While following an event: what the optional displays show (its stage, no ghosts or other drivers), else
        None (see app._render_widgets)."""
        run = self.league_run
        if self.drive_target != 'league' or not run:
            return None
        j = run['judge']
        running = j.state == 'running'
        return {'slot': min(run['no'], len(run['ev']['stages']) - 1) + 1, 'running': running,
                'splits': j.split_at, 'progress': j.progress if running else 0.0, 'ghosts': [], 'gap_p1': None,
                'p1_name': None, 'others_prog': []}

    def _league_allowed(self, f):
        """The in-game displays while following an event (see app._overlays_allowed)."""
        run = self.league_run
        if not run:
            return False
        j = run['judge']
        if self.drive_target != 'league':          # (an event just over: its result while still on its stage)
            return bool(run.get('over') and f is not None and f.track and j._right(f))
        return bool(run.get('wait') or j.state == 'running' or j.approaching or (f is not None and f.track and j._right(f)))
