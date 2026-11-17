"""The app's LIVE page: live rallies (liverally.py; server src/liverallies.js), mixed into App (app.py) like the other
pages (communityui.py, homeui.py).

On top, a card for each series (its class and cars, this week's country, its next session); under them the session
picked: before its hour the car picker, SIGN UP / WITHDRAW and who signed up; from its hour its rally (stages, weather),
my start (a countdown), DRIVE, and the queues (SS1's start list, then SS2's and SS3's as drivers finish) and the
standings; then the sessions to come. Signed up, the app keeps an eye on the session (as often as the server says) for
the timer window's countdown to each start (leagueui.py _league_overlay_state), its start list and its queues.

DRIVE is the leagues' (leagueui.py league_drive): the session's event joins the app's events, the car signed up with is
its car, and the app then follows it stage by stage. Each start goes with the server's time (the slot is checked against
it); a finished stage asks for the next stage's slot at once (queue); while a session's stage is driven, the ghost cars
are only its drivers' (livelink.py room).
"""
import threading
import time
import tkinter as tk
from tkinter import messagebox

from . import liverally, photos, settings, tiles
from .api import ApiError
from .i18n import _, n_


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


INFO_EVERY_S = 60              # the series and their sessions, while the page is open (else: app.periodic, 5 minutes)
POLL_S = 30                    # a session, unless the server says otherwise (pollS)
QUEUE_RETRY_S = 10             # the next stage's slot asked again (offline, or the stage's start not in yet)
QUEUE_TRY_S = 5 * 60
SHOWN_ROWS = 60                # a queue's rows listed at most (a full session: 40 or so)


class LiveRallyUI:
    # what an App has before _lr_init gives it its own (the tests build bare ones: App.__new__)
    lr_view = False
    lr_box = None
    lr_info = None
    lr_sel = None
    lr_tab = 0
    _lr_hid = ()

    def _lr_init(self):
        self.lr_clock = liverally.Clock()
        self.lr_view = False
        self.lr_info = None            # /api/liverallies: the series and their sessions (None: not in yet)
        self.lr_data = {}              # (series, starts) -> /api/liverallies/<series>/<starts>
        self.lr_sel = None             # the session on the page: (series, starts)
        self.lr_tab = None             # its queue shown: 0.. (SS1...), 'standings'; None: as it goes (mine)
        self.lr_msg = ''
        self._lr_at = {}               # when each was last asked (monotonic): 'info', or a session's key
        self._lr_busy = set()
        self._lr_cd = []               # (label, fn): the countdowns on the page, redrawn every half second
        self._lr_cd_at = 0.0
        self._lr_queue_want = {}       # (key, no) -> [finished at (server ms), first try (monotonic), last try]
        self._lr_told = set()          # the sessions whose rally I was told is out (_lr_announce)

    def _lr_ready(self):
        """(an App the tests build bare, App.__new__: its state made the first time it is needed)"""
        if '_lr_busy' not in self.__dict__:
            self._lr_init()

    def _lr_server_ms(self, pc_ms):
        """A moment on this PC's clock (ms: a judge's start) on the server's (leagueui.py, a session's start)."""
        self._lr_ready()
        return self.lr_clock.server_ms(pc_ms)

    # -------------------------------------------------------------- the page
    def _build_lr_box(self):
        c = _c()
        self.lr_box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)
        self._lr_scroll = tiles.ScrollArea(self.lr_box, c.BG)    # (a full start list: it scrolls)
        self._lr_scroll.outer.pack(fill='both', expand=True)
        self._lr_page = self._lr_scroll.inner

    def open_live_rallies(self, sel=None):
        self._lr_ready()
        if not liverally.ON or self.lr_box is None:
            return
        if sel:
            self.lr_sel, self.lr_tab = sel, None
        if self.lr_view:
            self._render_lr()
            return
        self._pages_leave()                          # (HOME, the inbox, the settings... give way: app.py)
        self.lr_view = True
        self._lr_hid = self._page_show(self.lr_box)
        side = getattr(self, '_side', None)          # (the whole width: the start list's columns)
        if side is not None and side.winfo_manager():
            side.pack_forget()
        self._mark_tabs()
        self._render_lr()
        self.refresh_live_rallies()

    def _lr_leave(self):
        if not self.lr_view:
            return
        self.lr_view = False
        self._page_hide(self.lr_box, self._lr_hid)
        self._lr_hid = ()
        if getattr(self, '_side', None) is not None:
            self._pack_side()
        self._mark_tabs()

    def lr_pick(self, key):
        if key != self.lr_sel:
            self.lr_sel, self.lr_tab = key, None
            self._render_lr()
            self._lr_poll(key)

    def lr_show_tab(self, tab):
        self.lr_tab = tab
        self._render_lr()

    # -------------------------------------------------------------- the server
    def refresh_live_rallies(self):
        """The series and their sessions (then the one picked, or mine)."""
        self._lr_ready()
        if not liverally.ON or not self.api.configured or 'info' in self._lr_busy:
            return
        self._lr_busy.add('info')
        self._lr_at['info'] = time.monotonic()

        def go():
            t0 = time.time()
            try:
                r, msg = self.api.live_rallies(), ''
            except ApiError as e:
                r, msg = None, str(e)
            _c().ui(self.root, self._lr_set_info, r, msg, t0, time.time())
        threading.Thread(target=go, daemon=True).start()

    def _lr_set_info(self, r, msg, t0, t1):
        self._lr_busy.discard('info')
        if r is None:
            self.lr_msg = msg
        else:
            self.lr_clock.learn(r.get('now'), t0, t1)
            self.lr_info, self.lr_msg = r, ''
            keys = [(s['series'], s['starts']) for s in r.get('sessions') or []]
            if self.lr_sel not in keys and not (self.lr_sel and self.lr_sel in self.lr_data):
                self.lr_sel, self.lr_tab = liverally.pick(r, self.lr_clock.now_ms()), None
            for key in {self.lr_sel, self._lr_mine()} - {None}:
                self._lr_poll(key)
        self._render_lr()

    def _lr_poll(self, key):
        """One session again (its sign-ups, start list, queues and my next start)."""
        self._lr_ready()
        if not key or key in self._lr_busy or not self.api.configured:
            return
        self._lr_busy.add(key)
        self._lr_at[key] = time.monotonic()

        def go():
            t0 = time.time()
            try:
                r, msg = self.api.live_session(*key), ''
            except ApiError as e:
                r, msg = None, str(e)
            _c().ui(self.root, self._lr_set_session, key, r, msg, t0, time.time())
        threading.Thread(target=go, daemon=True).start()

    def _lr_set_session(self, key, r, msg, t0=None, t1=None):
        self._lr_busy.discard(key)
        if r is None:
            self.lr_msg = msg
        else:
            if t0 is not None:
                self.lr_clock.learn(r.get('now'), t0, t1)
            self.lr_data[key] = r
            self.lr_msg = ''
            if r.get('event') and (r.get('me') or {}).get('signedUp'):
                self._lr_merge_event(r['event'])
                self._lr_announce(key, r)
        self._render_lr()

    def _lr_announce(self, key, v):
        """My session's rally is out (its hour): said once, with a sound and a notification (the driver may be in the
        game's menus), and where to go: DRIVE, by my start."""
        st = liverally.my_start(v, self.lr_clock.now_ms())
        if key in self._lr_told or v.get('phase') != 'running' or not st or st['no'] != 0:
            return
        self._lr_told.add(key)
        name = (v.get('event') or {}).get('name') or self._lr_series_name(key[0])
        text = _('The rally is out: press DRIVE on LIVE. Your start: SS1 at %s.') % liverally.hms(st['at'])
        self.sub_l.configure(text='%s: %s' % (name, text))
        self._notify(True, name, text)

    def _lr_merge_event(self, ev):
        """The session's event among the app's events (league_drive finds it there): added, or brought up to date
        unless the app is following it (its entry is the app's own then, as _set_league_events keeps it)."""
        run = getattr(self, 'league_run', None)
        if run and not run.get('over') and run['ev']['id'] == ev['id']:
            return
        evs = list(self.league_events or [])
        old = next((e for e in evs if e['id'] == ev['id']), None)
        if old:
            for a, b in zip(ev.get('stages') or [], old.get('stages') or []):
                a['route'] = a.get('route') or b.get('route')
            evs[evs.index(old)] = ev
        else:
            evs.append(ev)
        self.league_events = evs

    def _lr_mine(self):
        """The session I'm in now or soon: the one the app follows, else one I signed up for that is under way or starts
        within liverally.SOON_S. -> (series, starts) or None."""
        self._lr_ready()
        run = getattr(self, 'league_run', None)
        if run and not run.get('over') and run['ev'].get('kind') == liverally.KIND and run['ev'].get('series'):
            return run['ev']['series'], run['ev']['sessionStarts']
        now = self.lr_clock.now_ms()
        for s in (self.lr_info or {}).get('sessions') or []:
            if s.get('signedUp') and s.get('phase') in ('signup', 'running') and s['starts'] - now < liverally.SOON_S * 1000 \
                    and (s.get('entry') or {}).get('status') not in ('finished', 'dnf', 'dsq'):
                return s['series'], s['starts']
        return None

    # -------------------------------------------------------------- signing up, DRIVE
    def _lr_series(self, key):
        return next((x for x in (self.lr_info or {}).get('series') or [] if x['key'] == key), None)

    def _lr_car(self, series):
        """The car picked for a series (remembered), else the class's first."""
        s = self._lr_series(series) or {}
        cars = [c['name'] for c in s.get('cars') or []]
        picked = (self.s.get('liveCars') or {}).get(series)
        return picked if picked in cars else (cars[0] if cars else None)

    def lr_pick_car(self, series, name):
        self.s.setdefault('liveCars', {})[series] = name
        settings.save(self.s)
        self._render_lr()

    def lr_signup(self, key, withdraw=False):
        if not self.s.get('token'):
            messagebox.showinfo('ACR Daily', _('Sign in with Steam first (on the left).'))
            return
        car = self._lr_car(key[0])

        def go():
            try:
                r = (self.api.live_withdraw(*key) if withdraw else self.api.live_signup(key[0], key[1], car))
                _c().ui(self.root, self._lr_set_session, key, r, '')
                _c().ui(self.root, self.refresh_live_rallies)
            except ApiError as e:
                _c().ui(self.root, messagebox.showwarning, 'ACR Daily', str(e))
                _c().ui(self.root, self._lr_set_session, key, None, str(e))
        self._lr_busy.discard(key)
        threading.Thread(target=go, daemon=True).start()

    def lr_drive(self, key):
        """DRIVE on a session under way: the leagues' DRIVE on its event, with the car signed up with."""
        v = self.lr_data.get(key) or {}
        ev = v.get('event')
        if not ev or not (v.get('me') or {}).get('signedUp'):
            return
        self._lr_merge_event(ev)
        car = (v.get('me') or {}).get('car') or self._lr_car(key[0])
        if car:
            self._pick_car(ev, car)                  # (leagueui.py: an event in a class remembers its car)
        self.league_drive(ev['id'])

    # -------------------------------------------------------------- following a session (leagueui.py calls these)
    def _lr_key(self, ev):
        """A session's event -> its (series, starts), or None for any other event."""
        self._lr_ready()
        if ev.get('kind') != liverally.KIND:
            return None
        if ev.get('series') and ev.get('sessionStarts'):
            return ev['series'], ev['sessionStarts']
        return next((k for k, v in self.lr_data.items() if (v.get('event') or {}).get('id') == ev.get('id')), None)

    def _lr_started(self, event_id, slot):
        """A start's answer (flush_leagues): early, the seconds jumped came on top; late, said."""
        self._lr_ready()
        ev = self._league_event(event_id) or {}
        if slot.get('penaltyMs'):
            self.sub_l.configure(text=_('%s: jump start, %d s before your slot: they are added to the stage.') % (
                ev.get('name') or _('Live rally'), round(slot['penaltyMs'] / 1000)))
        elif slot.get('late'):
            self.sub_l.configure(text=_('%s: a late start, taken as it is.') % (ev.get('name') or _('Live rally')))
        key = self._lr_key(ev)
        if key:
            self._lr_poll(key)

    def _lr_finished(self, ev, no):
        """Stage `no` of a session finished (the app's judge): the next stage's slot, asked at once (and again while the
        server can't give it yet)."""
        self._lr_ready()
        key = self._lr_key(ev)
        if not key or no + 1 >= len(ev.get('stages') or ()):
            return
        self._lr_queue_want[(key, no + 1)] = [self.lr_clock.now_ms(), time.monotonic(), 0.0]
        self._lr_queue_try()

    def _lr_queue_try(self):
        now = time.monotonic()
        for (key, no), w in list(self._lr_queue_want.items()):
            if now - w[1] > QUEUE_TRY_S:
                del self._lr_queue_want[(key, no)]
                continue
            if now - w[2] < QUEUE_RETRY_S or ('q', key, no) in self._lr_busy:
                continue
            w[2] = now
            self._lr_busy.add(('q', key, no))

            def go(key=key, no=no, fin=w[0]):
                try:
                    r = self.api.live_queue(key[0], key[1], no, round(fin))
                    _c().ui(self.root, self._lr_queued, key, no, r, None)
                except ApiError as e:
                    _c().ui(self.root, self._lr_queued, key, no, None, e)
            threading.Thread(target=go, daemon=True).start()

    def _lr_queued(self, key, no, r, e):
        self._lr_busy.discard(('q', key, no))
        if e is not None:
            if e.code is not None and e.code != 409:       # (refused for good: not in it, the session over)
                self._lr_queue_want.pop((key, no), None)
                self.sub_l.configure(text=_('Live rally: %s') % e)
            return                                         # (offline, or SS(no) not in yet: again shortly)
        self._lr_queue_want.pop((key, no), None)
        slot = (r or {}).get('slot') or {}
        v = self.lr_data.get(key)
        if v is not None and slot.get('at'):
            v.setdefault('me', {})['next'] = slot           # (the timer's countdown at once; the queue with the next look)
        if slot.get('at'):
            self.sub_l.configure(text=_('SS%d: your start is %s (in %s).') % (
                no + 1, liverally.hms(slot['at']), liverally.left(slot['at'] - self.lr_clock.now_ms())))
        self._lr_poll(key)

    def _lr_overlay(self, run, stage):
        """The timer window before a session's stage (not on it yet): the countdown to my start, GO, or LATE. ->
        _league_overlay_state's answer, or None (not a session, or no start known yet)."""
        self._lr_ready()
        c = _c()
        key = self._lr_key(run['ev'])
        if not key:
            return None
        o = liverally.overlay(self.lr_data.get(key), run['no'], self.lr_clock.now_ms())
        if not o:
            return None
        status, ms, line, col = o
        colour = {'good': c.GOOD, 'bad': c.BAD, 'slow': c.SLOW}.get(col, c.SOFT)
        return line, '', (status, stage, ms, 0, line, colour)

    def _lr_next_line(self, run):
        """While a session's stage waits for the game's official time: the next stage's start, or None."""
        self._lr_ready()
        key = self._lr_key(run['ev'])
        st = liverally.my_start(self.lr_data.get(key), self.lr_clock.now_ms()) if key else None
        if not st or st['no'] != run['no'] + 1:
            return None
        return _('Next: SS%d at %s (in %s) · go on from the results screen') % (
            st['no'] + 1, liverally.hms(st['at']), liverally.left(st['left']))

    # -------------------------------------------------------------- every tick (app.py _render)
    def _lr_tick(self):
        self._lr_ready()
        if not liverally.ON:
            return
        now = time.monotonic()
        if now - self._lr_cd_at >= 0.5:              # the page's countdowns
            self._lr_cd_at = now
            for l, fn in list(self._lr_cd):
                try:
                    t = fn()
                    if l.cget('text') != t:
                        l.configure(text=t)
                except tk.TclError:
                    self._lr_cd.remove((l, fn))
            self._lr_room()
            if self._lr_queue_want:
                self._lr_queue_try()
            if self.lr_view and now - self._lr_at.get('info', -1e9) >= INFO_EVERY_S:
                self.refresh_live_rallies()
            for key in {self.lr_sel if self.lr_view else None, self._lr_mine()} - {None}:
                every = (self.lr_data.get(key) or {}).get('pollS') or POLL_S
                if now - self._lr_at.get(key, -1e9) >= every:
                    self._lr_poll(key)

    def _lr_room(self):
        """The ghost cars: a session's own room on the live relay while one of its stages is followed (only its
        drivers), else the stage's own."""
        link = getattr(getattr(self, 'ghostcars', None), 'live', None)
        if link is None:
            return
        run = getattr(self, 'league_run', None)
        room = None
        if self.drive_target == 'league' and run and not run.get('over') and run['ev'].get('kind') == liverally.KIND:
            room = 'live:%d' % run['ev']['id']
        if getattr(link, 'room', None) != room:
            link.room = room

    # -------------------------------------------------------------- HOME's tile
    def _lr_home_spec(self):
        self._lr_ready()
        c = _c()
        now = self.lr_clock.now_ms()
        info = self.lr_info or {}
        mine = self._lr_mine()
        nxt = sorted((s for s in info.get('sessions') or [] if s.get('phase') in ('signup', 'upcoming', 'running')),
                     key=lambda s: s['starts'])
        lines = [(_('Scheduled rallies every 2 hours · start every 30 s · a queue for each stage'), 'sub')]
        badge = None
        if mine:
            s = next((x for x in nxt if (x['series'], x['starts']) == mine), None)
            badge = (_('YOU ARE IN'), liverally.COLOUR)
            if s:
                lines.append(('%s · %s · %s' % (self._lr_series_name(s['series']), liverally.hm(s['starts']), s.get('rally') or ''), 'info'))
        elif nxt:
            s = next((x for x in nxt if x['phase'] == 'signup'), None)
            if s:
                badge = (_('SIGN-UP OPEN'), liverally.COLOUR)
            s = s or nxt[0]
            lines.append(('%s · %s · %s' % (self._lr_series_name(s['series']), liverally.hm(s['starts']), s.get('rally') or ''), 'info'))
        elif not info:
            lines.append((_('Loading the sessions…'), 'info'))
        rally = (nxt[0].get('rally') if nxt else None)
        return {'photo': photos.for_rally(rally) or 'leagues', 'bottom': True, 'badge': badge, 'title': _('LIVE'),
                'sizes': (34, 30, 26), 'lines': lines, 'button': False}

    def _lr_series_name(self, key):
        return (self._lr_series(key) or {}).get('name') or key

    # -------------------------------------------------------------- drawing the page
    def _render_lr(self):
        self._lr_ready()
        if self.lr_box is None or not self.lr_view:
            return
        c = _c()
        page = self._lr_page
        for w in page.winfo_children():
            w.destroy()
        self._lr_cd = []
        now = self.lr_clock.now_ms()
        info = self.lr_info
        head = tk.Frame(page, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(4, 0))
        self._lbl(head, _('LIVE RALLIES'), font=(c.FONT_C, 16), fg=c.WHITE).pack(side='left')
        self._lbl(head, '  ' + _('NOT RATED YET'), font=(c.FONT, 8, 'bold'), fg=liverally.COLOUR).pack(side='left', pady=(6, 0))
        r = liverally.rules_of(info)
        rule = _('A rally every 2 hours, the two series in turn. Sign up in the %d minutes before the hour: the stages and '
                 'the weather are drawn at the hour, with the start list. Car 1 starts %d minutes later, then one every %d s; '
                 'after each stage you join the next one\'s queue. Late: you go to the end of the queue. Early: the '
                 'seconds you jumped are added. Ghost cars: only this rally\'s drivers.') % (
            r['signupMin'], r['firstStartMin'], r['gapS'])
        self._lbl(page, rule, fg=c.MUTED, font=(c.FONT, 8), wraplength=900).pack(anchor='w', padx=20, pady=(2, 8))
        if info is None or not info.get('on'):
            text = self.lr_msg or (_('Loading the live rallies…') if info is None else _('There are no live rallies on this server yet.'))
            self._lbl(page, text, fg=c.SOFT, font=(c.FONT, 10), wraplength=800).pack(anchor='w', padx=20, pady=(10, 12))
            return
        self._lr_series_cards(page, info, now)
        key = self.lr_sel
        if key:
            self._lr_session(page, key, now)
        self._lr_upcoming(page, info, now)

    def _lr_series_cards(self, page, info, now):
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96
        row = tk.Frame(page, bg=c.BG)
        row.pack(fill='x')
        series = info.get('series') or []
        tr = tiles.TileRow(row, max(2, len(series)), base=round(170 * k), cols=1 if getattr(self, 'layout_stack', False) else None)
        for s in series:
            nxt = liverally.next_session(info, s['key'], now)
            key = (s['key'], nxt['starts']) if nxt else None
            tile = tr.add(tiles.Tile(row, on_click=(lambda kk=key: self.lr_pick(kk)) if key else None, restyle=self._btn_style))
            label = _('VIEW  ›')
            if nxt and nxt['phase'] == 'signup' and not nxt.get('signedUp'):
                label = _('SIGN UP  ›')
            tile.button = self._btn(tile.cv, label, (lambda kk=key: self.lr_pick(kk)) if key else (lambda: None), primary=True)
            cars = ' · '.join(x['name'] for x in s.get('cars') or [])
            when = (_('Next: %s · %s') % (liverally.hm(nxt['starts']), nxt.get('rally') or '')) if nxt else ''
            tile.render({'active': bool(key) and key == self.lr_sel, 'lock': (s.get('carClass') or '', (s.get('rally') or '').upper()),
                         'photo': photos.for_rally(s.get('rally')), 'bottom': True, 'title': (s.get('name') or '').upper(),
                         'sizes': (24, 21, 18),
                         'badge': (_('SIGNED UP'), c.GOOD) if nxt and nxt.get('signedUp') else None,
                         'lines': [(cars, 'sub'),
                                   (_('Every %d hours · this week %s, next week %s') % (s.get('everyHours') or 4, s.get('rally') or '',
                                                                                         s.get('nextRally') or ''), 'info'),
                                   (when + ('  ·  ' + liverally.card_line(nxt, now) if nxt else ''), 'muted')]})
        tr.even()

    def _lr_session(self, page, key, now):
        c = _c()
        v = self.lr_data.get(key)
        s_row = next((s for s in (self.lr_info or {}).get('sessions') or [] if (s['series'], s['starts']) == key), None)
        box = tk.Frame(page, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
        box.pack(fill='x', padx=20, pady=(12, 0))
        head = tk.Frame(box, bg=c.PANEL)
        head.pack(fill='x', padx=14, pady=(10, 2))
        rally = (v or s_row or {}).get('rally') or ''
        self._lbl(head, '%s  ·  %s  ·  %s' % (self._lr_series_name(key[0]).upper(), liverally.hm(key[1]), rally.upper()),
                  font=(c.FONT_C, 14), fg=c.WHITE, bg=c.PANEL).pack(side='left')
        if v is None:
            self._lbl(box, self.lr_msg or _('Loading the session…'), fg=c.SOFT, bg=c.PANEL).pack(anchor='w', padx=14, pady=(4, 12))
            return
        phase = v.get('phase')
        me = v.get('me') or {}
        if phase in ('upcoming', 'signup') or (v.get('publishing') and not v.get('event')):
            self._lr_signup_part(box, key, v, now)
        elif phase == 'empty' or (phase == 'over' and not v.get('event')):
            self._lbl(box, _('Nobody signed up for this one.'), fg=c.SOFT, bg=c.PANEL).pack(anchor='w', padx=14, pady=(4, 12))
        elif v.get('event'):
            self._lr_rally_part(box, key, v, me, now)

    def _lr_signup_part(self, box, key, v, now):
        c = _c()
        me = v.get('me') or {}
        line = tk.Frame(box, bg=c.PANEL)
        line.pack(fill='x', padx=14, pady=(2, 6))
        if v.get('publishing'):
            t = lambda: _('Drawing the rally and the start list…')    # noqa: E731
        elif v.get('phase') == 'upcoming':
            t = lambda: _('Sign-up opens in %s (%s).') % (liverally.left(v['signupOpens'] - self.lr_clock.now_ms()),   # noqa: E731
                                                         liverally.hm(v['signupOpens']))
        else:
            t = lambda: _('Sign-up open: the rally and the start list come out in %s, at %s. Car 1 starts at %s.') % (   # noqa: E731
                liverally.left(v['starts'] - self.lr_clock.now_ms()), liverally.hm(v['starts']), liverally.hm(v['firstStart']))
        l = self._lbl(line, t(), fg=c.SOFT, bg=c.PANEL, font=(c.FONT, 10))
        l.pack(side='left')
        self._lr_cd.append((l, t))
        cars = (self._lr_series(key[0]) or {}).get('cars') or []
        if v.get('phase') == 'signup' and not v.get('publishing'):
            pick = tk.Frame(box, bg=c.PANEL)
            pick.pack(fill='x', padx=14, pady=(0, 6))
            self._lbl(pick, _('Your car:'), fg=c.MUTED, bg=c.PANEL, font=(c.FONT, 9)).pack(side='left', padx=(0, 8))
            mine = me.get('car') if me.get('signedUp') else self._lr_car(key[0])
            for car in cars:
                on = car['name'] == mine
                b = tk.Label(pick, text=car['name'], bg=c.WHITE if on else c.PANEL2, fg=c.BG if on else c.SOFT,
                             font=(c.FONT_C, 10), padx=10, pady=3, cursor='hand2')
                b.bind('<Button-1>', lambda _e, n=car['name']: self.lr_pick_car(key[0], n))
                b.pack(side='left', padx=(0, 4))
            act = tk.Frame(box, bg=c.PANEL)
            act.pack(fill='x', padx=14, pady=(2, 8))
            if me.get('signedUp'):
                if me.get('car') != self._lr_car(key[0]):
                    self._btn(act, _('CHANGE CAR  ›'), lambda: self.lr_signup(key), primary=True, surface=c.PANEL).pack(side='left')
                self._lbl(act, '✓ ' + _('Signed up with the %s') % me.get('car'), fg=c.GOOD, bg=c.PANEL,
                          font=(c.FONT, 10, 'bold')).pack(side='left', padx=(10, 12))
                self._btn(act, _('WITHDRAW'), lambda: self.lr_signup(key, withdraw=True), surface=c.PANEL).pack(side='left')
            else:
                self._btn(act, _('SIGN UP  ›'), lambda: self.lr_signup(key), primary=True, surface=c.PANEL).pack(side='left')
        ents = v.get('entrants') or []
        self._lbl(box, n_('%d signed up', '%d signed up', len(ents)) % len(ents) + (
            ': ' + ', '.join(e.get('name') or '?' for e in ents[:40]) if ents else ''), fg=c.FG2, bg=c.PANEL,
            font=(c.FONT, 9), wraplength=860).pack(anchor='w', padx=14, pady=(0, 12))

    def _lr_rally_part(self, box, key, v, me, now):
        c = _c()
        ev = v['event']
        stages = ev.get('stages') or []
        it = tk.Frame(box, bg=c.PANEL)
        it.pack(fill='x', padx=14, pady=(0, 6))
        for s in stages:
            self._lbl(it, 'SS%d  %s  ·  %.1f km  ·  %s  ·  %s' % (s['no'], s.get('name') or '', (s.get('lengthM') or 0) / 1000,
                                                              s.get('weatherLabel') or s.get('weather') or '', s.get('time') or ''),
                      fg=c.SOFT, bg=c.PANEL, font=(c.FONT, 9)).pack(anchor='w')
        self._lbl(it, (ev.get('car') or ev.get('carClass') or '') + '  ·  ' + _('service park before SS1 only: the damage carries'),
                  fg=c.MUTED, bg=c.PANEL, font=(c.FONT, 8)).pack(anchor='w', pady=(2, 0))
        # my start, and DRIVE
        mine = tk.Frame(box, bg=c.PANEL)
        mine.pack(fill='x', padx=14, pady=(6, 8))
        entry = ev.get('entry') or {}
        if me.get('signedUp'):
            def start_text():
                st = liverally.my_start(self.lr_data.get(key), self.lr_clock.now_ms())
                e = ((self.lr_data.get(key) or {}).get('event') or {}).get('entry') or {}
                if e.get('status') == 'finished':
                    return _('Finished: %s') % liverally.fmt_time(e.get('totalMs'))
                if e.get('status') in ('dnf', 'dsq'):
                    return _('Your rally is over: %s') % (e.get('reason') or e['status'].upper())
                if not st:
                    out = ((self.lr_data.get(key) or {}).get('me') or {}).get('out')
                    if out:
                        return _('Out: you missed your start %d times') % (out.get('moved') or 0)
                    return _('On a stage, or between stages: your next start comes as you finish')
                word = {'wait': _('in %s') % liverally.left(st['left']), 'go': _('GO NOW'), 'late': _('LATE: you go to the end')}[st['phase']]
                return _('YOUR START  SS%d  %s  ·  %s') % (st['no'] + 1, liverally.hms(st['at']), word) + (
                    ('  ·  ' + _('moved %d×') % st['moved']) if st.get('moved') else '')
            l = self._lbl(mine, start_text(), font=(c.FONT_C, 16), fg=liverally.COLOUR, bg=c.PANEL)
            l.pack(side='left')
            self._lr_cd.append((l, start_text))
            if entry.get('status') in (None, 'running') and v.get('phase') == 'running':
                self._btn(mine, _('DRIVE  ›'), lambda: self.lr_drive(key), primary=True, surface=c.PANEL).pack(side='right')
        else:
            self._lbl(mine, _('%d drivers in this rally.') % (v.get('entrants') or 0), fg=c.SOFT, bg=c.PANEL).pack(side='left')
        # the queues and the standings
        n = len(stages)
        tab = self.lr_tab
        if tab is None:                              # (as it goes: my next stage's queue, else SS1's, the standings once over)
            st = liverally.my_start(v, now)
            tab = st['no'] if st else 'standings' if v.get('phase') == 'over' or entry.get('status') in ('finished', 'dnf') else 0
        tabs = tk.Frame(box, bg=c.PANEL)
        tabs.pack(fill='x', padx=14, pady=(4, 0))
        names = [(k, _('SS1 START LIST') if k == 0 else _('SS%d QUEUE') % (k + 1)) for k in range(n)] + [('standings', _('STANDINGS'))]
        for kk, text in names:                       # (the one shown in LIVE's colour)
            on = kk == tab
            b = tk.Label(tabs, text=text, bg=c.PANEL, fg=liverally.COLOUR if on else c.FG2, font=(c.FONT_C, 10), padx=8,
                         pady=3, cursor='hand2')
            b.bind('<Button-1>', lambda _e, t=kk: self.lr_show_tab(t))
            b.pack(side='left')
        grid = tk.Frame(box, bg=c.PANEL)
        grid.pack(fill='x', padx=14, pady=(6, 12))
        sid = self.s.get('steamId')
        colour = {'good': c.GOOD, 'bad': c.BAD, 'slow': c.SLOW, 'live': liverally.COLOUR, 'muted': c.MUTED}
        if tab == 'standings':
            rows = liverally.standings_rows(v, sid)
            heads = (_('POS'), _('DRIVER'), _('CAR'), _('TOTAL'), _('GAP'))
            cells = [(p, nm, car, tot, gap, c.WHITE if mine_ else c.SOFT, mine_) for p, nm, car, tot, gap, mine_ in rows]
        else:
            rows = liverally.queue_rows(v, tab, sid)
            heads = (_('START'), _('DRIVER'), _('CAR'), _('STATE'), '')
            cells = [(at, nm, car, what, '', colour.get(col, c.SOFT), mine_) for at, nm, car, what, col, mine_ in rows]
        for i, h in enumerate(heads):
            self._k(grid, h, bg=c.PANEL).grid(row=0, column=i, sticky='w', padx=(0, 16))
        if not cells:
            self._lbl(grid, _('Nobody yet: drivers join this queue as they finish the stage before.') if tab not in (0, 'standings')
                      else _('Nobody yet.'), fg=c.MUTED, bg=c.PANEL, font=(c.FONT, 9)).grid(row=1, column=0, columnspan=5, sticky='w')
        for r_, cell in enumerate(cells[:SHOWN_ROWS], start=1):
            *texts, fg, mine_ = cell
            for i, t in enumerate(texts):
                self._lbl(grid, t, fg=(c.WHITE if mine_ and i == 1 else fg if i == 3 else c.SOFT), bg=c.PANEL,
                          font=(c.FONT, 9, 'bold' if mine_ else 'normal')).grid(row=r_, column=i, sticky='w', padx=(0, 16))
        grid.columnconfigure(3, weight=1)

    def _lr_upcoming(self, page, info, now):
        """The other sessions: a row each, a click shows it."""
        c = _c()
        ss = [s for s in info.get('sessions') or [] if (s['series'], s['starts']) != self.lr_sel and s['phase'] != 'over']
        if not ss:
            return
        self._k(page, _('THE NEXT SESSIONS')).pack(anchor='w', padx=20, pady=(14, 4))
        for s in ss[:8]:
            row = tk.Frame(page, bg=c.BG, cursor='hand2')
            row.pack(fill='x', padx=20)
            mark = '✓ ' if s.get('signedUp') else ''
            text = '%s%s   %s   %s   ·   %s' % (mark, liverally.hm(s['starts']), self._lr_series_name(s['series']),
                                               s.get('rally') or '', liverally.card_line(s, now))
            l = self._lbl(row, text, fg=c.GOOD if mark else c.FG2, font=(c.FONT, 9), cursor='hand2')
            l.pack(side='left', pady=1)
            for w in (row, l):
                w.bind('<Button-1>', lambda _e, kk=(s['series'], s['starts']): self.lr_pick(kk))
