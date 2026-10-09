"""The app's LEAGUES view and its part of the loop, mixed into App (app.py). The logic is in leagues.py.

The view lists the events of the driver's leagues (open or coming soon) with their progress; DRIVE sets an event's rally
up in the game (or puts it back, or resumes it) and the app then follows the driver through it: the frames are judged
for the event's next stage instead of the dailies (drive_target), each finished stage is sent with the game's own
result, and the next stage is armed. The timing sheet shows the event's standings while the view is open.
The dailies and the events share the game's one Rally Weekend: over the dailies, a strip shows a league rally in
progress, and DRIVE on a daily sets it aside (said first; refused while a league stage is being driven). A Rally
Weekend of the player's own is set aside the same way, and the strip offers it back (PUT BACK).
"""
import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import autodrive, leagues, rallyweekend, saveslot, settings, waiting
from .api import TOO_OLD, ApiError
from .judge import Judge, fmt_ms

OFFICIAL_CHECK_MS = 2000
OFFICIAL_WAIT_S = 30 * 60
OFFICIAL_CLOCK_MS = 5000
LEAGUES_EVERY_MIN = 5
SHOWN = 4                      # events listed in the window (the rest: the website)


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def _left(ms_left):
    s = int(ms_left / 1000)
    if s <= 0:
        return 'now'
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return '%d d %d h' % (d, h) if d else '%d h %02d min' % (h, m) if h else '%d min' % m


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
        self.league_board = None       # the standings of the event on screen
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
    def _build_league_toggle(self, head):
        c = _c()
        self.view_b = self._link(head, 'LEAGUES', self.toggle_league_view)
        self.view_b.configure(font=(c.FONT_C, 11))
        self.view_b.pack(side='right', padx=(0, 18))

    def _build_league_box(self):
        c = _c()
        self.league_box = tk.Frame(self.root, bg=c.BG)
        self.league_rows = tk.Frame(self.league_box, bg=c.BG)
        self.league_rows.pack(fill='x')
        self.league_strip = tk.Frame(self.root, bg=c.BG)   # over the dailies: a league rally in progress

    def toggle_league_view(self, on=None):
        on = (not self.league_view) if on is None else on
        if on == self.league_view:
            return
        self.league_view = on
        self.view_b.configure(text='DAILIES' if on else 'LEAGUES')
        if on:
            self.daily_box.pack_forget()
            self.league_box.pack(fill='x', before=self._status_frame)
            self.refresh_leagues()
        else:
            self.league_box.pack_forget()
            self.daily_box.pack(fill='x', before=self._status_frame)
        self._render_strip()
        self._show_board_title()
        self._fill_tree()

    def _league_in_progress(self):
        """My events with a rally under way (my entry still running, the event open), the soonest to close first."""
        return sorted((e for e in self.league_events
                       if e['status'] == 'open' and (e.get('entry') or {}).get('status') == 'running'), key=lambda e: e['closes'])

    def _progress_text(self, ev, now):
        e = ev.get('entry') or {}
        done = e.get('done', 0)
        return 'SS%d of %d next%s · closes in %s' % (done + 1, len(ev['stages']),
                                                     (' · %s so far' % fmt_ms(e.get('totalMs') or 0)) if done else '',
                                                     _left(ev['closes'] - now))

    @staticmethod
    def _held_hint(ev):
        """Where a rally in progress waits, and what not to do with it."""
        if leagues.is_parked(ev['id']):
            return 'Set aside while a daily was set up: CONTINUE puts it back in the game.'
        return ('The game keeps it: Rally Weekend › RESUME (CREATE NEW would throw it away). DRIVE on a daily sets it '
                'aside first: nothing is lost.')

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
        if self.league_view or not (evs or own):
            s.pack_forget()
            return
        if evs:
            self._strip_league(s, evs)
        if own:
            self._strip_own(s, own)
        s.pack(fill='x', before=self.daily_box)

    def _strip_own(self, s, own):
        c = _c()
        x = own[0]
        row = tk.Frame(s, bg=c.BG)
        row.pack(fill='x', padx=(17, 20))
        tk.Frame(row, bg=c.SOFT, width=3).pack(side='left', fill='y', padx=(0, 14))
        body = tk.Frame(row, bg=c.BG)
        body.pack(side='left', fill='x', expand=True, pady=(12, 12))
        top = tk.Frame(body, bg=c.BG)
        top.pack(fill='x')
        self._lbl(top, 'YOUR RALLY WEEKEND · SET ASIDE', font=(c.FONT, 8, 'bold'), fg=c.SOFT).pack(side='left')
        self._btn(top, 'PUT BACK  ›', lambda p=x['path']: self.put_back_own(p)).pack(side='right')
        self._lbl(body, 'Rally %s' % x['location'], font=(c.FONT_C, 17), fg=c.WHITE).pack(anchor='w', pady=(2, 0))
        self._lbl(body, '%d of %d stages done · set aside %s' % (x['done'], x['stages'], time.strftime(
            '%a %d %b %H:%M', time.localtime(x['at']))), fg=c.SOFT, font=(c.FONT, 9)).pack(anchor='w')
        more = (' %d more set aside.' % (len(own) - 1)) if len(own) > 1 else ''
        self._lbl(body, 'Set aside for a daily or a league event. PUT BACK returns it to the game (then Rally Weekend › '
                        'RESUME).' + more, fg=c.MUTED, font=(c.FONT, 8), wraplength=370).pack(anchor='w', pady=(2, 0))
        self._rule(s, padx=20)

    def _strip_league(self, s, evs):
        c = _c()
        ev = evs[0]
        run = self.league_run
        following = bool(run and run['ev']['id'] == ev['id'] and self.drive_target == 'league')
        row = tk.Frame(s, bg=c.BG)
        row.pack(fill='x', padx=(17, 20))
        tk.Frame(row, bg=c.GOOD, width=3).pack(side='left', fill='y', padx=(0, 14))
        body = tk.Frame(row, bg=c.BG)
        body.pack(side='left', fill='x', expand=True, pady=(12, 12))
        top = tk.Frame(body, bg=c.BG)
        top.pack(fill='x')
        self._lbl(top, 'LEAGUE RALLY IN PROGRESS · %s' % (ev.get('league') or 'League').upper(), font=(c.FONT, 8, 'bold'),
                  fg=c.GOOD).pack(side='left')
        b = self._btn(top, 'FOLLOWING' if following else 'CONTINUE  ›',
                      (lambda: None) if following else (lambda i=ev['id']: self.league_drive(i)))
        b.pack(side='right')
        self._lbl(body, ev['name'], font=(c.FONT_C, 17), fg=c.WHITE).pack(anchor='w', pady=(2, 0))
        self._lbl(body, self._progress_text(ev, time.time() * 1000), fg=c.SOFT, font=(c.FONT, 9)).pack(anchor='w')
        more = (' %d more in LEAGUES.' % (len(evs) - 1)) if len(evs) > 1 else ''
        self._lbl(body, self._held_hint(ev) + more, fg=c.MUTED, font=(c.FONT, 8), wraplength=370).pack(anchor='w', pady=(2, 0))
        self._rule(s, padx=20)

    def _league_event(self, eid):
        return next((e for e in self.league_events if e['id'] == eid), None)

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
        if not self.s.get('token'):
            self._lbl(box, 'Sign in with Steam (below) to see the events of your leagues.', fg=c.SOFT, font=(c.FONT, 10),
                      wraplength=400).pack(anchor='w', padx=20, pady=(16, 6))
            self._link(box, 'What are leagues?  ›', self.open_leagues).pack(anchor='w', padx=20, pady=(0, 14))
            self._rule(box, padx=20)
            return
        evs = [e for e in self.league_events if e['status'] != 'closed' or (e.get('entry') or {}).get('status') == 'running']
        evs.sort(key=lambda e: (e.get('entry') or {}).get('status') != 'running')     # a rally in progress first
        if not evs:
            self._lbl(box, self.league_msg or 'No league events open right now.', fg=c.SOFT, font=(c.FONT, 10),
                      wraplength=400).pack(anchor='w', padx=20, pady=(16, 4))
            self._link(box, 'Find, create or join a league on the website  ›', self.open_leagues).pack(anchor='w', padx=20, pady=(0, 14))
            self._rule(box, padx=20)
            return
        if self.league_sel not in [e['id'] for e in evs]:
            run = self.league_run
            self.league_sel = run['ev']['id'] if run else evs[0]['id']
            self.refresh_league_board()
        now = time.time() * 1000
        for ev in evs[:SHOWN]:
            self._event_card(box, ev, now)
        more = len(evs) - SHOWN
        foot = tk.Frame(box, bg=c.BG)
        foot.pack(fill='x', padx=20, pady=(8, 10))
        self._link(foot, ('%d more on the website  ›' % more) if more > 0 else 'Leagues on the website  ›',
                   self.open_leagues).pack(side='left')

    def _event_card(self, box, ev, now):
        """An event of my leagues: the one picked in full (itinerary, car, progress; its standings in the timing
        sheet), the others in two lines (a click picks one)."""
        c = _c()
        sel = ev['id'] == self.league_sel
        entry = ev.get('entry') or {}
        status = entry.get('status')
        run = self.league_run
        following = bool(run and run['ev']['id'] == ev['id'] and self.drive_target == 'league')
        if ev['status'] == 'upcoming':
            label, primary, cmd = 'OPENS IN %s' % _left(ev['opens'] - now).upper(), False, None
        elif status == 'finished':
            label, primary, cmd = 'FINISHED', False, None
        elif status in ('dnf', 'dsq'):
            label, primary, cmd = status.upper(), False, None
        elif ev['status'] == 'closed':
            label, primary, cmd = 'CLOSED', False, None
        else:                                             # red: the event picked (as the daily on screen)
            label = 'FOLLOWING' if following else 'CONTINUE  ›' if status == 'running' else 'DRIVE  ›'
            primary, cmd = sel and not following, (lambda e=ev['id']: self.league_drive(e))
        if status == 'running':
            txt, fg = self._progress_text(ev, now), c.GOOD
        elif status == 'finished':
            txt, fg = 'Finished · %s' % fmt_ms(entry.get('totalMs') or 0), c.WHITE
        elif status in ('dnf', 'dsq'):
            txt, fg = '%s · %s' % (status.upper(), entry.get('reason') or ''), c.BAD
        elif ev['status'] == 'upcoming':
            txt, fg = 'Opens %s' % time.strftime('%a %d %b %H:%M', time.localtime(ev['opens'] / 1000)), c.FG2
        else:
            txt, fg = 'Not started · closes in %s' % _left(ev['closes'] - now), c.FG2
        row = tk.Frame(box, bg=c.BG)
        row.pack(fill='x', padx=(17, 20))
        bar = tk.Frame(row, bg=c.ACC if sel else c.BG, width=3)
        bar.pack(side='left', fill='y', padx=(0, 14))
        body = tk.Frame(row, bg=c.BG)
        body.pack(side='left', fill='x', expand=True, pady=(12, 12) if sel else (9, 9))
        top = tk.Frame(body, bg=c.BG)
        top.pack(fill='x')
        b = self._btn(top, label, cmd or (lambda: None), primary=primary)
        if not cmd:
            b.configure(cursor='arrow')
        b.pack(side='right')
        if not sel:
            name = self._lbl(top, ev['name'], font=(c.FONT_C, 15), fg=c.SOFT, cursor='hand2')
            name.pack(side='left')
            info = self._lbl(body, '%s · %s%s' % ((ev.get('league') or 'League').upper(),
                                                  'In progress · ' if status == 'running' else '', txt),
                             fg=c.GOOD if status == 'running' else c.MUTED, font=(c.FONT, 8), cursor='hand2')
            info.pack(anchor='w')
            for w in (row, body, top, name, info):
                w.bind('<Button-1>', lambda _e, i=ev['id']: self.select_league_event(i))
            self._rule(box, padx=20)
            return
        self._lbl(top, (ev.get('league') or 'League').upper(), font=(c.FONT, 8, 'bold'), fg=c.ACC).pack(side='left')
        if status == 'running':
            self._lbl(top, '●  IN PROGRESS', font=(c.FONT, 8, 'bold'), fg=c.GOOD).pack(side='left', padx=(10, 0))
        self._lbl(body, ev['name'], font=(c.FONT_C, 20), fg=c.WHITE).pack(anchor='w', pady=(2, 0))
        km = sum(s.get('lengthM') or 0 for s in ev['stages']) / 1000
        self._lbl(body, '%s · %d stage%s · %d day%s · %.1f km' % (ev['rally'], len(ev['stages']), '' if len(ev['stages']) == 1 else 's',
                  ev['days'], '' if ev['days'] == 1 else 's', km), fg=c.SOFT, font=(c.FONT, 10)).pack(anchor='w')
        if ev.get('car'):
            self._lbl(body, ev['car'], fg=c.SOFT, font=(c.FONT, 10)).pack(anchor='w')
        elif status:
            self._lbl(body, entry.get('car') or '', fg=c.SOFT, font=(c.FONT, 10)).pack(anchor='w')
        else:                                             # a class: pick a car of it before the start
            names = [x['name'] for x in ev['cars']]
            cur = (self._league_car(ev) or {}).get('name') or ''
            pick = ttk.Combobox(body, values=names, state='readonly', width=34)
            pick.set(cur or 'Pick your %s car' % ev.get('carClass', ''))
            pick.bind('<<ComboboxSelected>>', lambda _e, e=ev, p=pick: self._pick_car(e, p.get()))
            pick.pack(anchor='w', pady=(3, 1))
        links = tk.Frame(body, bg=c.BG)
        links.pack(fill='x', pady=(2, 0))
        self._lbl(links, txt, fg=fg, font=(c.FONT, 9)).pack(side='left')
        self._link(links, 'Standings ›', lambda i=ev['id']: self.open_event_page(i)).pack(side='right')
        if status == 'running':
            self._lbl(body, self._held_hint(ev), fg=c.MUTED, font=(c.FONT, 8), wraplength=400).pack(anchor='w', pady=(3, 0))
        self._rule(box, padx=20)

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
                _c().ui(self.root, self._set_league_events, None, 'Leagues: %s' % e)
        threading.Thread(target=go, daemon=True).start()

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
                any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()):
            return
        try:
            with open(saveslot.SAVE, 'rb') as f:
                b = f.read()
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
            self.sub_l.configure(text='Following %s: SS%d next. In the game: Racing › Rally › Rally Weekend › RESUME.'
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
                _c().ui(self.root, self.sub_l.configure, {'text': 'Could not get the stages of %s (%s). Try again.'
                                                                  % (ev['name'], e)})
        threading.Thread(target=go, daemon=True).start()

    def select_league_event(self, eid):
        self.league_sel = eid
        self._render_leagues()
        self.refresh_league_board()

    def refresh_league_board(self):
        eid = self.league_sel
        if not eid:
            return

        def go():
            try:
                e = self.api.event(eid)
                _c().ui(self.root, self._set_league_board, eid, e)
            except ApiError:
                pass
        threading.Thread(target=go, daemon=True).start()

    def _set_league_board(self, eid, e):
        if eid != self.league_sel:
            return
        self.league_board = e
        if self.league_view:
            self._show_board_title()
            self._fill_tree()

    def _show_board_title(self):
        if self.league_view:
            ev = self._league_event(self.league_sel)
            self.board_l.configure(text=' '.join(('STANDINGS  ' + (ev['name'] if ev else '')).upper()))
        else:
            self.board_l.configure(text=' '.join(('TIMING  SS%d' % self.active)))

    def _fill_league_tree(self):
        me = self.s.get('steamId')
        rows = (self.league_board or {}).get('standings') or []
        for r in rows[:50]:
            if r['status'] == 'finished':
                pos, t = r['rank'], fmt_ms(r['totalMs'])
            elif r['status'] in ('dnf', 'dsq'):
                pos, t = '–', r['status'].upper()
            else:
                pos, t = '', 'SS%d…' % (r['done'] + 1)
            pen = '+%d' % round(r['penaltyMs'] / 1000) if r.get('penaltyMs') and r['status'] != 'dnf' else ''
            tag = 'me' if r['steamId'] == me else 'p1' if r.get('rank') == 1 else ''
            self.tree.insert('', 'end', values=(pos, r['name'], t, pen), tags=(tag,))
        if not rows:
            self.tree.insert('', 'end', values=('', 'Nobody has started yet' if self.league_board else 'Loading…', '', ''))

    def open_leagues(self):
        if self.api.configured:
            webbrowser.open(self.api.base.replace('://acr-daily.acr-daily-server.workers.dev', '://acrdaily.com') + '/leagues')

    def open_event_page(self, eid):
        if self.api.configured:
            webbrowser.open(self.api.base.replace('://acr-daily.acr-daily-server.workers.dev', '://acrdaily.com') + '/e/%d' % eid)

    # -------------------------------------------------------------- DRIVE on an event
    def league_drive(self, eid):
        ev = self._league_event(eid)
        if not ev or getattr(self, '_restarting', False):
            return
        entry = ev.get('entry') or {}
        car = (leagues.car_of(ev, entry.get('car')) if entry.get('car') else None) or self._league_car(ev)
        if not car:
            messagebox.showinfo('ACR Daily', 'Pick your car for %s first (a %s car).' % (ev['name'], ev.get('carClass') or ''))
            return
        if not self._fill_routes(ev):                     # to judge the stages like dailies
            self.sub_l.configure(text='Getting the stages of %s...' % ev['name'])
            self._league_routes(ev, lambda: self.league_drive(eid))
            return
        run = self.league_run
        if any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or \
                (run and not run.get('over') and run['judge'].state == 'running'):
            messagebox.showinfo('ACR Daily', 'Finish or leave the stage you are on first.')
            return
        if self._waiting_text():                  # (DRIVE may close the game before it saves that run's time)
            messagebox.showinfo('ACR Daily', self._waiting_text())
            return
        if saveslot.game_running():
            # the game is open: if its rally is already this event's, follow it from here without a restart
            try:
                with open(saveslot.SAVE, 'rb') as f:
                    b = f.read()
                state, p = leagues.rally_state(b, ev)
                changed = leagues.changed_in_game(rallyweekend.read_weekend(b), ev) if state == 'this' else []
            except (OSError, saveslot.SaveError):
                state, p, changed = None, None, []
            done = (ev.get('entry') or {}).get('done', 0)
            if state == 'this' and p['done'] == done and not changed and not leagues.is_parked(ev['id']):
                self._follow(ev, car)
                self.sub_l.configure(text='Following %s: SS%d next. In the game: Racing › Rally › Rally Weekend › RESUME.'
                                     % (ev['name'], done + 1))
                return
            if not messagebox.askyesno('ACR Daily', 'Assetto Corsa Rally is running.\n\nACR Daily will close it, set up '
                                       '%s (%s, %d stages) and start it again. This takes about a minute.\n\nGo?'
                                       % (ev['name'], ev['rally'], len(ev['stages']))):
                return
            self._restart_into_league(ev, car)
            return
        self._league_setup_and_launch(ev, car)

    def _restart_into_league(self, ev, car):
        self._close_game_then(ev['name'], lambda: self._league_setup_and_launch(ev, car))

    def _league_setup_and_launch(self, ev, car):
        first = ev['stages'][0]
        try:
            b = saveslot.read_for_daily({'stageId': first['stageId'], 'carId': car['id'], 'weatherGame': first['weatherGame'],
                                         'startSeconds': first['startSeconds']})
            changed = False
            for _ in range(len(self.league_events) + 2):
                action, details = leagues.plan(ev, b, self.league_events)
                if action not in ('park-other', 'park-own'):
                    break
                other = details
                ask = (self._own_text(other, ev['name']) if action == 'park-own' else
                       'The game holds your rally for %s (%d of %d stages done).\n\nACR Daily will set it aside and put '
                       'it back when you click CONTINUE on it.' % (other['name'], (other.get('entry') or {}).get('done', 0),
                                                                   len(other['stages'])))
                if not messagebox.askyesno('ACR Daily', ask + '\n\nGo on?'):
                    return
                b = leagues.apply_plan(ev, car, action, details, b)   # (it waits in its own file; the save is written once)
                changed = True
                self._render_strip()
            new = leagues.apply_plan(ev, car, action, details, b)
            if new is not None or changed:
                saveslot.replace(new if new is not None else b)
            if action in ('setup', 'reset', 'unpark') or leagues.is_parked(ev['id']) and action == 'resume':
                leagues.forget_parked(ev['id'])        # (a rally set aside before the start, or an older copy)
        except leagues.Gone as g:
            self._league_dnf_entry(ev, str(g))
            messagebox.showwarning('ACR Daily', 'Your entry in %s ends here (DNF): %s.' % (ev['name'], g))
            return
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', str(e))
            return
        self._follow(ev, car)
        if action in ('setup', 'reset'):
            path = ('In the game: any key › E (Racing) › Rally › Rally Weekend › START RALLY › J (automatic tyres) › '
                    'CONFIRM AND START RALLY › Start Stage. Everything is set up.')
        else:
            path = 'In the game: Racing › Rally › Rally Weekend › RESUME, then Start Stage (SS%d).' % ((details or 0) + 1 if
                                                                                                  action == 'resume' else
                                                                                                  (ev.get('entry') or {}).get('done', 0) + 1)
        self.sub_l.configure(text='Starting the game... ' + path)
        try:
            saveslot.launch_game()
        except OSError:
            self.sub_l.configure(text='Set up. Start the game from Steam. ' + path)
        if self.s.get('autoDrive') and action in ('setup', 'reset'):
            if getattr(self, 'auto', None):
                self.auto.cancel()
            self.auto = autodrive.AutoDrive(lambda t: _c().ui(self.root, self.sub_l.configure, {'text': t}), 'weekend').start()

    def _follow(self, ev, car):
        """From now on the frames are judged for the event's next stage (its routes fetched: _league_routes)."""
        if not self._fill_routes(ev):
            self._league_routes(ev, lambda: self._follow(ev, car))
            return
        done = (ev.get('entry') or {}).get('done', 0)
        self.league_run = {'ev': ev, 'car': car, 'no': done, 'judge': Judge(leagues.stage_ch(ev, done, car)),
                           'known': None, 'ignore': None, 'wait': None}
        self.drive_target = 'league'
        self.league_sel = ev['id']
        self.toggle_league_view(True)
        self._render_leagues()
        self.refresh_league_board()

    def _held(self, b=None):
        """The rally in progress in the game's save: ('league', the event) for one of my events (my entry running, or
        not started with no stage driven), ('own', describe()) for any other, or None."""
        try:
            if b is None:
                with open(saveslot.SAVE, 'rb') as f:
                    b = f.read()
            p = rallyweekend.progress(b)
            if p is None:
                return None
            ev = leagues.owner_of(b, self.league_events)
            return ('league', ev) if ev else ('own', leagues.describe(p, rallyweekend.read_weekend(b)['preset']))
        except (OSError, saveslot.SaveError):
            return None

    def _league_held(self):
        """The event whose started rally the game's save holds (my entry still running), or None."""
        h = self._held()
        return h[1] if h and h[0] == 'league' and (h[1].get('entry') or {}).get('status') == 'running' else None

    @staticmethod
    def _set_aside_text(ev):
        e = ev.get('entry') or {}
        return ('Your league rally %s is in progress (%d of %d stages done).\n\nThe game keeps one Rally Weekend at a '
                'time, and the daily is one too: ACR Daily sets your rally aside for the daily. Nothing is lost (its '
                'stages, times and damage are kept): CONTINUE on the event in LEAGUES puts it back.'
                % (ev['name'], e.get('done', 0), len(ev['stages'])))

    @staticmethod
    def _own_text(info, what='the daily'):
        return ('A Rally Weekend of your own is in progress in the game (%s, %d of %d stages done).\n\nThe game keeps one '
                'Rally Weekend at a time, and %s is one too: ACR Daily sets yours aside. Nothing is lost (its stages, '
                'times and damage are kept): PUT BACK, over the dailies in ACR Daily, returns it to the game whenever '
                'you want.' % (info['location'], info['done'], info['stages'], what))

    def _league_before_daily(self, weekend):
        """DRIVE on a daily, before anything changes. A league stage being driven comes first: the daily's set-up closes
        the game, and that stage would be a DNF. A rally in progress in the game (a league event's, or the player's
        own) is set aside for a daily set up as a Rally Weekend: said once, here. -> None to stop, else whether the
        driver was told (then the game-is-running question is not asked again)."""
        self._park_said = None
        run = self.league_run
        if run and not run.get('over') and (run['judge'].state == 'running' or run.get('wait')):
            messagebox.showinfo('ACR Daily', 'You are on a stage of %s. Finish it first (and wait until the game has '
                                             'saved its time): a daily now would close the game, and the stage would be '
                                             'a DNF.' % run['ev']['name'])
            return None
        h = self._held() if weekend else None
        if h and h[0] == 'league' and (h[1].get('entry') or {}).get('status') == 'running':
            text, said = self._set_aside_text(h[1]), h[1]['id']
        elif h and h[0] == 'own':
            text, said = self._own_text(h[1]), 'own'
        else:
            return False
        more = ('\n\nThe game is running: ACR Daily closes it, sets the daily up and starts it again (about a minute).'
                if saveslot.game_running() else '')
        if not messagebox.askyesno('ACR Daily', text + more + '\n\nDrive the daily?'):
            return None
        self._park_said = said
        return True

    def _league_park_for_daily(self):
        """Before a daily is set up as a Rally Weekend: a rally in progress is set aside, a league event's or the
        player's own (asked first, unless _league_before_daily did; a league event not started yet, with no stage
        driven, needs no question). -> False to stop the daily's set-up."""
        try:
            with open(saveslot.SAVE, 'rb') as f:
                b = f.read()
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
        if ask and not messagebox.askyesno('ACR Daily', ask + '\n\nGo on?'):
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
        if any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or \
                (run and not run.get('over') and run['judge'].state == 'running'):
            messagebox.showinfo('ACR Daily', 'Finish or leave the stage you are on first.')
            return
        if self._waiting_text():
            messagebox.showinfo('ACR Daily', self._waiting_text())
            return
        if saveslot.game_running():
            if not messagebox.askyesno('ACR Daily', 'Assetto Corsa Rally is running.\n\nACR Daily will close it, put your '
                                                    'rally back and start it again. This takes about a minute.\n\nGo?'):
                return
            self._close_game_then('your rally', lambda: self._put_back_now(path))
            return
        self._put_back_now(path)

    def _put_back_now(self, path):
        try:
            if not os.path.exists(saveslot.SAVE):
                raise saveslot.SaveError('No game save found.')
            with open(saveslot.SAVE, 'rb') as f:
                b = f.read()
            h = self._held(b)
            if h and h[0] == 'league' and (h[1].get('entry') or {}).get('status') == 'running' and \
                    not messagebox.askyesno('ACR Daily', 'Your league rally %s is in progress in the game. ACR Daily sets '
                                                         'it aside (CONTINUE on it in LEAGUES puts it back). Go on?' % h[1]['name']):
                return
            new, _moved = leagues.put_back(b, path, self.league_events)
            saveslot.replace(new)
            leagues.forget_own(path)
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', 'Your rally could not be put back: %s' % e)
            return
        self.drive_target = 'daily'
        self._render_strip()
        if self.league_view:
            self._render_leagues()
        path_txt = 'In the game: Racing › Rally › Rally Weekend › RESUME.'
        self.sub_l.configure(text='Your rally is back. Starting the game... ' + path_txt)
        try:
            saveslot.launch_game()
        except OSError:
            self.sub_l.configure(text='Your rally is back. Start the game from Steam. ' + path_txt)

    def _close_game_then(self, what, then):
        """Close the game the normal way (it saves on exit), wait for it, then call then()."""
        self._restarting = 'league'
        saveslot.ask_game_to_quit()
        t0 = time.monotonic()

        def wait():
            if not saveslot.game_running():
                self.sub_l.configure(text='Game closed. Setting up %s...' % what)
                self._restart_job = self.root.after(4000, lambda: (setattr(self, '_restarting', False), then()))
                return
            waited = time.monotonic() - t0
            if waited > 120:
                self._restarting = False
                self.sub_l.configure(text='The game did not close. Quit it from its menu, then try again.')
                return
            if 8 < waited < 9 or 30 < waited < 31:
                saveslot.ask_game_to_quit()
            self.sub_l.configure(text='Closing Assetto Corsa Rally... (%d s) If the game asks, confirm quitting.' % waited)
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
            elif e == 'finished':
                self._league_finished(run)
            elif e in ('dnf', 'invalid'):
                self._league_failed(run, (j.result or {}).get('reason') or e)

    def _league_started(self, run):
        ev, k = run['ev'], run['no']
        run['known'] = None
        run['ignore'] = None
        changed = []
        try:                                       # this stage must be driven in the event's own rally
            with open(saveslot.SAVE, 'rb') as f:
                b = f.read()
            run['known'] = leagues.known(b)        # the game's result of this stage will be a new one
            w = rallyweekend.read_weekend(b)
            if k == 0:
                ok = leagues.same_calendar(w['stages'], ev)
            else:
                state, p = leagues.rally_state(b, ev)
                ok = state == 'this' and p['done'] == k
            changed = leagues.changed_in_game(w, ev) if ok else []
        except (OSError, saveslot.SaveError):
            ok = False
        if not ok:
            run['ignore'] = 'not in the event\'s rally: this run does not count (click CONTINUE on the event, then ' \
                            'Rally Weekend › Resume)'
            run['ignore_short'] = 'not the event\'s rally'
            self.sub_l.configure(text='SS%d: %s' % (k + 1, run['ignore']))
            return
        if changed and (k == 0 or not ev.get('entry')):
            # changed in the game's menus before the rally started: nothing counts yet, set it up again
            run['ignore'] = ('the event\'s %s changed in the game\'s menus: this run does not count. Click DRIVE on the '
                             'event again: ACR Daily sets it up afresh' % ', '.join(changed))
            run['ignore_short'] = '%s changed in the game' % ', '.join(changed)
            self.sub_l.configure(text='SS%d: %s.' % (k + 1, run['ignore']))
            return
        if changed:                                # the rally ran with other settings: the entry ends
            self._league_failed(run, 'the event\'s %s changed in the game' % ', '.join(changed))
            return
        # the server keeps each stage's first start: a stage started again (after the app was closed during it, say)
        # ends the entry, as a restart does
        if not ev.get('entry'):
            ev['entry'] = {'status': 'running', 'done': 0, 'totalMs': 0, 'car': run['car']['name'], 'reason': ''}
            self._league_send({'kind': 'start', 'eventId': ev['id'], 'car': run['car']['name']})
        else:
            self._league_send({'kind': 'begin', 'eventId': ev['id'], 'no': k})
        self.sub_l.configure(text='%s · SS%d of %d LIVE' % (ev['name'], k + 1, len(ev['stages'])))

    def _league_finished(self, run):
        if run['ignore']:
            self._league_rearm(run)
            return
        ev, k = run['ev'], run['no']
        r = dict(run['judge'].result)
        w = run['wait'] = {'id': 'league:%d:%d:%s' % (ev['id'], k, r.get('startedAt')), 'result': r,
                           'until': time.time() + OFFICIAL_WAIT_S, 'closed': 0, 'other': None}
        try:                                       # on disk too: closing the app loses nothing (waiting.py)
            waiting.add({'id': w['id'], 'kind': 'league', 'eventId': ev['id'], 'no': k, 'stageId': ev['stages'][k]['stageId'],
                         'carId': run['car']['id'], 'result': r, 'until': w['until'],
                         'known': leagues.known_to_json(run['known']) if run['known'] is not None else None,
                         'event': {'name': ev['name'], 'rules': ev.get('rules'),
                                   'stages': [{x: s.get(x) for x in ('stageId', 'weatherGame', 'startSeconds', 'day', 'service')}
                                              for s in ev['stages']]}})
        except (OSError, TypeError, ValueError):
            pass
        self.sub_l.configure(text='SS%d finished. %s' % (k + 1, waiting.HINT))
        self.root.after(OFFICIAL_CHECK_MS, self._league_check_official)

    def _league_wait_step(self, b, w, ev, stage_id, car_id, known):
        """One look at the game's save (b) for a league stage waiting for its official result. w: {'result', 'until',
        'closed', 'other'}, updated; ev: the event (its rules and stages). -> ('stage', the game's result), ('dnf', why)
        or None: still waiting."""
        r = w['result']
        o = leagues.official(b, stage_id, car_id, known or set()) if b else None
        if o and abs(o['time'] * 1000 - r['clockMs']) <= OFFICIAL_CLOCK_MS:
            try:                                   # the save written with the result: still the event's settings?
                changed = leagues.changed_in_game(rallyweekend.read_weekend(b), ev)
            except saveslot.SaveError:
                changed = []
            return ('dnf', 'the event\'s %s changed in the game' % ', '.join(changed)) if changed else ('stage', o)
        w['other'] = o or w['other']
        w['closed'] = 0 if saveslot.game_running() else w['closed'] + 1
        if w['closed'] >= 3 or time.time() > w['until']:
            return 'dnf', ('the game saved %s, not this stage\'s time' % fmt_ms(round(w['other']['time'] * 1000))
                           if w['other'] else 'no official result from the game')
        return None

    @staticmethod
    def _read_save():
        try:
            with open(saveslot.SAVE, 'rb') as f:
                return f.read()
        except OSError:
            return None

    def _league_check_official(self):
        run = self.league_run
        if not run or not run.get('wait'):
            return
        w, ev, k = run['wait'], run['ev'], run['no']
        out = self._league_wait_step(self._read_save(), w, ev, ev['stages'][k]['stageId'], run['car']['id'], run['known'])
        if out is None:
            self.root.after(OFFICIAL_CHECK_MS, self._league_check_official)
            return
        waiting.remove(w.get('id'))
        if out[0] == 'stage':
            self._league_stage_done(run, out[1])
        else:
            run['wait'] = None
            self._league_failed(run, out[1])

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
            self.sub_l.configure(text='%s: SS%d is still waiting for the game\'s official time: looking for it in the '
                                      'game\'s save. %s' % (x['event'].get('name') or 'League event', x['no'] + 1, waiting.HINT))
            self.root.after(OFFICIAL_CHECK_MS, self._league_check_restored)

    def _league_check_restored(self):
        """Every OFFICIAL_CHECK_MS while such stages wait: sent with the game's result as if the app had stayed open
        (or a DNF, saying why); following the event goes on from there (CONTINUE, or the autofollow)."""
        b = self._read_save()
        for x in list(self._league_restored):
            out = self._league_wait_step(b, x, x['event'], x['stageId'], x['carId'], x['known'])
            if out is None:
                continue
            self._league_restored.remove(x)
            waiting.remove(x['id'])
            name, k = x['event'].get('name') or 'League event', x['no']
            if out[0] == 'stage':
                t, p = self._league_send_stage(x['eventId'], k, x['result'], out[1])
                self.sub_l.configure(text='%s · SS%d: %s + %d s (official), sent. CONTINUE on the event goes on from '
                                          'there.' % (name, k + 1, fmt_ms(t), round(p / 1000)))
            else:
                self._league_send({'kind': 'dnf', 'eventId': x['eventId'], 'no': k, 'reason': out[1]})
                self.sub_l.configure(text='%s: DNF on SS%d (%s).' % (name, k + 1, out[1]))
        if self._league_restored:
            self.root.after(OFFICIAL_CHECK_MS, self._league_check_restored)

    def _league_stage_done(self, run, o):
        ev, k, r = run['ev'], run['no'], run['wait']['result']
        run['wait'] = None
        time_ms, pen_ms = self._league_send_stage(ev['id'], k, r, o)
        e = ev['entry'] = ev.get('entry') or {'status': 'running', 'done': 0, 'totalMs': 0}
        e['done'], e['totalMs'] = k + 1, (e.get('totalMs') or 0) + time_ms + pen_ms
        n = len(ev['stages'])
        if k + 1 >= n:
            e['status'] = 'finished'
            run['over'] = True
            self.drive_target = 'daily'
            self.sub_l.configure(text='%s finished: %s (SS%d: %s + %d s). Well driven!' % (
                ev['name'], fmt_ms(e['totalMs']), k + 1, fmt_ms(time_ms), round(pen_ms / 1000)))
        else:
            run['no'] = k + 1
            run['judge'] = Judge(leagues.stage_ch(ev, k + 1, run['car']))
            self.sub_l.configure(text='SS%d: %s + %d s (official). Next: SS%d %s. Go on in the game, or stop and come back '
                                      'before the event closes (Rally Weekend › Resume).' % (
                                          k + 1, fmt_ms(time_ms), round(pen_ms / 1000), k + 2, ev['stages'][k + 1]['name']))
        self._render_leagues()

    def _league_rearm(self, run):
        """A run that didn't count (outside the event's rally): the same stage again."""
        run['judge'] = Judge(leagues.stage_ch(run['ev'], run['no'], run['car']))
        run['ignore'] = None

    def _league_failed(self, run, reason):
        if run.get('ignore'):
            self._league_rearm(run)
            return
        if not (run['ev'].get('entry')):            # never started (e.g. invalid before the start): nothing to end
            self._league_rearm(run)
            self.sub_l.configure(text='Not started: %s' % reason)
            return
        self._league_dnf_entry(run['ev'], reason, run['no'])
        run['over'] = True
        self.drive_target = 'daily'
        self.sub_l.configure(text='%s: DNF on SS%d (%s).' % (run['ev']['name'], run['no'] + 1, reason))

    def _league_server_dnf(self, eid, reason):
        """The server ended the entry (a stage started a second time): stop following the event."""
        run = self.league_run
        if run and run['ev']['id'] == eid and not run.get('over'):
            run['over'] = True
            if run.get('wait'):
                waiting.remove(run['wait'].get('id'))
            run['wait'] = None
            self.drive_target = 'daily'
            self.sub_l.configure(text='%s: DNF (%s). The first start of each stage is the one that counts.'
                                 % (run['ev']['name'], reason))
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
                    if it['kind'] == 'start':
                        r = self.api.league_start(it['eventId'], it['car'])
                    elif it['kind'] == 'begin':
                        r = self.api.league_begin(it['eventId'], it['no'])
                    elif it['kind'] == 'stage':
                        r = self.api.league_stage(it['eventId'], {k: v for k, v in it.items() if k not in ('kind', 'eventId')})
                    else:
                        r = self.api.league_dnf(it['eventId'], it['no'], it['reason'])
                    if it['kind'] in ('start', 'begin') and (r or {}).get('status') == 'dnf':   # a stage started again
                        _c().ui(self.root, self._league_server_dnf, it['eventId'], r.get('reason') or 'DNF')
                except ApiError as e:
                    if e.code is None or e.code >= 500 or e.code == 401:
                        break                        # offline or signed out: later
                    if e.code == TOO_OLD:
                        _c().ui(self.root, self.check_update)
                    _c().ui(self.root, self.sub_l.configure, {'text': 'League: %s' % e})
                q.pop(0)
                sent_any = True
                leagues.save_pending(q)
        if sent_any:
            _c().ui(self.root, self.refresh_league_board)
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
                return ('%s finished: %s' % (ev['name'], fmt_ms(e.get('totalMs') or 0)), '',
                        ('finished', stage, e.get('totalMs') or 0, 0, 'Event finished', c.SOFT))
            reason = e.get('reason') or (j.result or {}).get('reason') or ''
            return ('%s: DNF (%s)' % (ev['name'], reason), '', ('dnf', stage, (j.result or {}).get('clockMs', 0),
                                                                 (j.result or {}).get('resets', 0), 'DNF: %s' % reason, c.BAD))
        if run.get('wait'):
            return (j.message, '', ('finished', stage, j.total_ms, j.resets, 'Official time next: go on from the results screen',
                                    c.SOFT))
        if j.state == 'running':
            if run['ignore']:
                return ('NOT COUNTING · ' + j.message, '', ('live', stage, j.total_ms, j.resets,
                                                            'NOT COUNTING: ' + run.get('ignore_short', 'not the event\'s rally'), c.BAD))
            line = 'On stage · %d%%' % round(j.progress * 100)
            if j.paused:
                line = 'PAUSED · the run carries on with the clock'
            return (j.message, '', ('live', stage, j.total_ms, j.resets, line, c.SOFT))
        if j.state == 'armed':
            return (j.message, '', ('ready', stage, 0, 0, 'League · goes LIVE with the stage clock', c.SOFT))
        if f is None:
            return ('Waiting for Assetto Corsa Rally', '', ('standby', 'LEAGUE · ' + ev['name'].upper(), 0, 0, 'Waiting for the game', c.MUTED))
        if j.approaching:
            return (j.message, '', ('standby', stage, 0, 0, 'Drive up to the start line', c.SOFT))
        return ('%s: load SS%d %s · %s (Rally Weekend › Resume)' % (ev['name'], k + 1, st['name'], run['car']['name']), '',
                ('standby', stage, 0, 0, 'Next: SS%d in the event\'s rally' % (k + 1), c.MUTED))

    def _league_widget_view(self, f):
        """While following an event: what the optional displays show (its stage, no ghosts or other drivers), else
        None (see app._render_widgets)."""
        run = self.league_run
        if self.drive_target != 'league' or not run:
            return None
        j = run['judge']
        running = j.state == 'running'
        return {'slot': min(run['no'], len(run['ev']['stages']) - 1) + 1, 'running': running, 'route': j.ch.get('route'),
                'splits': j.split_at, 'progress': j.progress if running else 0.0, 'ghosts': [], 'ghost_pos': [],
                'me_pos': (f.x, f.z) if (f is not None and j._right(f)) else None, 'gap_p1': None, 'p1_name': None,
                'field': [], 'colours': {}, 'others': [], 'others_prog': []}

    def _league_allowed(self, f):
        """The in-game displays while following an event (see app._overlays_allowed)."""
        run = self.league_run
        if not run:
            return False
        j = run['judge']
        if self.drive_target != 'league':          # (an event just over: its result while still on its stage)
            return bool(run.get('over') and f is not None and f.track and j._right(f))
        return bool(run.get('wait') or j.state == 'running' or j.approaching or (f is not None and f.track and j._right(f)))
