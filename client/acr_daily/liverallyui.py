"""The app's RANKED page (the testers' for now): ranked rallies (liverally.py; server src/liverallies.js), as iRacing's
official races, mixed into App (app.py) like the other pages (communityui.py, homeui.py).

The page: a row for each series (its class and cars, this week's country, its next session with a countdown and who
registered, the car picked, REGISTER / WITHDRAW); under them the session picked (registered drivers; from its hour its
stages, the START LIST, SS2's and SS3's queues, the RESULTS); then the sessions to come. Along the bottom of the app, in
every view, the registration bar (as iRacing's): registered and when it starts, then YOUR RALLY IS READY (DRIVE), my start
(START SSn), on stage, the result. At the hour a card over everything says the rally is ready, with DRIVE and the time
left to my start (rankedcard.py); on a stage's start line another one asks for START SSn.

DRIVE is the leagues' (leagueui.py league_drive): the session's event joins the app's events, the car registered with is
its car, and the app then follows it stage by stage. A start counts for ranked only after START SSn (as a daily's after
START OFFICIAL RALLY): each start goes with the server's time (the slot is checked against it); a finished stage asks for
the next stage's slot at once (queue). Every run on a ranked stage belongs to a mode: ranked (START SSn), a daily
(START OFFICIAL RALLY) or the time trial; one that belongs to none (practice) before my ranked run on it is a DNF there.
While a session's stage is driven, the ghost cars are only its drivers' (livelink.py room).
"""
import threading
import time
import tkinter as tk
from tkinter import messagebox

from . import liverally, names, photos, rankedcard, settings, tiles, waiting
from .api import ApiError
from .i18n import _, local, n_, said


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


INFO_EVERY_S = 60              # the series and their sessions, while the page is open (else: app.periodic, 5 minutes)
POLL_S = 30                    # a session, unless the server says otherwise (pollS)
QUEUE_RETRY_S = 10             # the next stage's slot asked again (offline, or the stage's start not in yet)
QUEUE_TRY_S = 5 * 60
START_NEAR_M = 400             # a stage clock starting this near a session stage's start (its route's): on that stage
SHOWN_ROWS = 60                # a queue's rows listed at most (a full session: 40 or so)


class LiveRallyUI:
    # what an App has before _lr_init gives it its own (the tests build bare ones: App.__new__)
    lr_view = False
    lr_box = None
    lr_info = None
    lr_sel = None
    lr_tab = 0
    _lr_hid = ()
    _lr_watching = ()
    _lr_clock_was = 0

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
        self._lr_outed = {}            # (series, starts) -> [no, reason, first try, last try]: my DNF on its way (_lr_out)
        self._lr_watching = []         # [(key, event, stages counted)]: my sessions under way, their stages watched
        self._lr_clock_was = 0         # the stage clock on the frame before (_lr_watch: a start is 0 -> running)
        self._lr_pending = None        # a start on a session stage, decided on the next frame (_lr_watch)
        self._lr_armed = None          # (event id, stage): START SSn pressed, for my next start on that stage
        self._lr_cards = {}            # 'ready' / 'start' -> the RankedCard up (rankedcard.py)
        self._lr_shown = set()         # (key, 'ready') / (key, stage, 'start'): each card once
        self._lr_bar_key = None        # what the registration bar shows (drawn again only when it changes)

    def _lr_ready(self):
        """(an App the tests build bare, App.__new__: its state made the first time it is needed)"""
        if '_lr_busy' not in self.__dict__:
            self._lr_init()

    def _lr_server_ms(self, pc_ms):
        """A moment on this PC's clock (ms: a judge's start) on the server's (leagueui.py, a session's start), or None
        while the server's clock isn't known yet (the server then takes the start when it gets it: a PC clock behind
        the server's would make a start on time look early, a jump start)."""
        self._lr_ready()
        return self.lr_clock.server_ms(pc_ms) if self.lr_clock.known else None

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
        text = _('Your rally is ready: DRIVE. Your start: SS1 at %s.') % liverally.hms(st['at'])
        self.sub_l.configure(text='%s: %s' % (name, text))
        self._notify(True, name, text)
        self._lr_ready_card(key, v)

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
            if hasattr(self, '_league_routes'):        # (its stages' routes: _lr_watch knows them by where they start)
                self._league_routes(ev, lambda: None)
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
                ev.get('name') or _('Ranked rally'), round(slot['penaltyMs'] / 1000)))
        elif slot.get('late'):
            self.sub_l.configure(text=_('%s: a late start, taken as it is.') % (ev.get('name') or _('Ranked rally')))
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
            if e.code is not None and e.code != 409:       # (refused for good: not in it, the session over: 403, 410)
                self._lr_queue_want.pop((key, no), None)
                self.sub_l.configure(text=_('Ranked: %s') % e)
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

    # -------------------------------------------------------------- every start on a session's stages counts
    def _lr_watch_list(self):
        """My sessions under way whose stages the app watches: [(key, event, stages counted so far)]."""
        out = []
        for key, v in self.lr_data.items():
            ev = v.get('event')
            me = v.get('me') or {}
            if not ev or v.get('phase') != 'running' or not me.get('signedUp') or key in self._lr_outed:
                continue
            run = getattr(self, 'league_run', None)
            e = run['ev'].get('entry') if run and run['ev'].get('id') == ev.get('id') else ev.get('entry')
            if (e or {}).get('status') in ('finished', 'dnf', 'dsq') or me.get('out'):
                continue
            out.append((key, ev, (e or {}).get('done', 0)))
        return out

    def _lr_watch(self, f):
        """(app.py _tick, every frame) A stage clock starting on one of my ranked session's stages not driven yet,
        decided on the next frame (once every mode's judge has seen it): fine when it is a run of a mode, ranked (the app
        follows that stage: its start, START SSn or not, is the leagues' to judge, leagueui.py), a daily (its judge took
        it, START OFFICIAL RALLY pressed) or the time trial (its judge took it); else practice on a ranked stage before
        my run on it (before DRIVE, a later stage early, in any mode): a DNF. A stage counted already, driven again (the
        game took its rally back), changes nothing."""
        if self._lr_pending is not None:
            ev, i = self._lr_pending
            self._lr_pending = None
            if not self._lr_run_of_a_mode(ev, i):
                self._lr_out(ev, i, said('SS%d driven outside the rally, before its start', i + 1))
        clock = f.clock_ms if f is not None and f.track else 0
        started = clock > 0 and self._lr_clock_was == 0 and clock < 3000
        self._lr_clock_was = clock
        if not started or not self._lr_watching:
            return
        for key, ev, done in self._lr_watching:
            for i, st in enumerate(ev.get('stages') or []):
                if i < done or not names.same_track(f.track, st):
                    continue
                route = st.get('route') or (getattr(self, '_route_cache', None) or {}).get(st.get('track'))
                if route and ((f.x - route[0][0]) ** 2 + (f.z - route[0][1]) ** 2) ** 0.5 > START_NEAR_M:
                    continue                             # (another stage of that name: "Alsace Forêt" is two)
                self._lr_pending = (ev, i)
                return

    def _lr_run_of_a_mode(self, ev, i):
        """The run just started on stage i of a session: one of a mode (see _lr_watch)?"""
        run = getattr(self, 'league_run', None)
        if self.drive_target == 'league' and run and run['ev'].get('id') == ev.get('id') and run['no'] == i and \
                (run['judge'].state == 'running' or run.get('over')):
            return True                                  # ranked: the leagues' (START SSn checked there)
        for d in (getattr(self, 'dailies', None) or {}).values():
            j = d.get('judge')
            if j is not None and j.state == 'running' and not d.get('norally') and not d.get('practice'):
                return True                              # a daily's counted run (START OFFICIAL RALLY pressed)
        judged = getattr(self, '_tt_judged', None)
        if judged is not None and judged():
            for slot, t in (getattr(self, '_tt', None) or {}).items():
                j = t.get('judge')
                if j is not None and j.state == 'running' and self._tt_entered(slot):
                    return True                          # a time trial run
        return False

    # -------------------------------------------------------------- START SSn: my next start counts for ranked
    def lr_arm(self, key):
        """START SSn (the bar, the card at the start line): my next start on my next stage of the session counts for
        ranked. Not following it yet: DRIVE first. A daily's START OFFICIAL RALLY pressed before is taken back (one run,
        one mode)."""
        self._lr_ready()
        v = self.lr_data.get(key) or {}
        ev = v.get('event') or {}
        st = liverally.my_start(v, self.lr_clock.now_ms())
        run = getattr(self, 'league_run', None)
        if not ev or not st:
            return
        if not (self.drive_target == 'league' and run and not run.get('over') and run['ev'].get('id') == ev.get('id')):
            self.lr_drive(key)
            return
        self._lr_armed = (ev['id'], st['no'])
        for d in (getattr(self, 'dailies', None) or {}).values():
            d['committed'] = None
        card = getattr(self, 'commit_card', None)
        if card is not None and getattr(card, 'alive', False):
            card.close()
        self._lr_close_card('start')
        self.sub_l.configure(text=_('SS%d counts for ranked: start it at %s (GO on the timer). Once the clock starts, '
                                    'restarting or quitting is a DNF.') % (st['no'] + 1, liverally.hms(st['at'])))
        self._lr_bar_render()

    def _lr_disarm(self):
        """(app.py commit: a daily's START OFFICIAL RALLY) START SSn taken back: one run, one mode."""
        self._lr_ready()
        self._lr_armed = None
        self._lr_bar_render()

    def _lr_take_arm(self, ev, no):
        """(leagueui.py, a session's stage started) Was START SSn pressed for it? Used up either way."""
        self._lr_ready()
        armed, self._lr_armed = self._lr_armed, None
        return armed == (ev.get('id'), no)

    def _lr_out(self, ev, no, reason):
        """A stage of my session driven outside it: my entry a DNF, here at once (the app stops following it) and on the
        server (sent until it has it), said loudly: in a live rally every start on its stages counts."""
        self._lr_ready()
        key = self._lr_key(ev)
        if not key or key in self._lr_outed:
            return
        self._lr_outed[key] = [no, reason, time.monotonic(), 0.0]
        e = dict(ev.get('entry') or {'done': 0, 'totalMs': 0}, status='dnf', reason=reason)
        ev['entry'] = e
        v = self.lr_data.get(key) or {}
        if v.get('event'):
            v['event']['entry'] = dict(e)
            v.setdefault('me', {})['next'] = None
        run = getattr(self, 'league_run', None)
        if run and run['ev'].get('id') == ev.get('id') and not run.get('over'):
            run['over'] = True
            if run.get('wait'):
                waiting.remove(run['wait'].get('id'))
            run['wait'] = None
            run['ev']['entry'] = dict(e)
            self.drive_target = 'daily'
        name = ev.get('name') or _('Ranked rally')
        text = _('%s: DNF. %s. In a ranked rally every start on its stages counts.') % (name, local(reason))
        self.sub_l.configure(text=text)
        self._notify(False, _('DNF'), text)
        self._lr_out_try()
        self._render_lr()

    def _lr_out_try(self):
        now = time.monotonic()
        for key, w in list(self._lr_outed.items()):
            if len(w) < 4 or now - w[3] < QUEUE_RETRY_S or ('out', key) in self._lr_busy:
                continue
            w[3] = now
            self._lr_busy.add(('out', key))

            def go(key=key, no=w[0], reason=w[1]):
                try:
                    self.api.live_out(key[0], key[1], no, reason)
                    _c().ui(self.root, self._lr_out_sent, key, True)
                except ApiError as e:
                    _c().ui(self.root, self._lr_out_sent, key, e.code is not None and e.code < 500 and e.code != 401)
            threading.Thread(target=go, daemon=True).start()

    def _lr_out_sent(self, key, done):
        self._lr_busy.discard(('out', key))
        w = self._lr_outed.get(key)
        if done and w is not None:
            del w[2:]                                    # (sent, or refused for good: kept as said, not sent again)
            self._lr_poll(key)

    def _lr_overlay(self, run, stage):
        """The timer window before a session's stage (not on it yet): the countdown to my start, GO, or LATE. ->
        _league_overlay_state's answer, or None (not a session, or no start known yet)."""
        self._lr_ready()
        c = _c()
        key = self._lr_key(run['ev'])
        if not key:
            return None
        v = self.lr_data.get(key)
        out = ((v or {}).get('me') or {}).get('out')
        if out and out.get('no') == run['no']:          # missed this stage's start too often: out of the session
            line = _('OUT · you missed your start %d times') % ((out.get('moved') or 0) + 1)
            return line, '', ('dnf', stage, 0, 0, line, c.BAD)
        o = liverally.overlay(v, run['no'], self.lr_clock.now_ms())
        if not o:
            return None
        status, ms, line, col = o
        colour = {'good': c.GOOD, 'bad': c.BAD, 'slow': c.SLOW}.get(col, c.SOFT)
        if status in ('wait', 'go') and self._lr_armed != (run['ev'].get('id'), run['no']):
            st = liverally.my_start(v, self.lr_clock.now_ms())   # (not pressed yet: say so, in red, the countdown on)
            line, colour = _('Press START SS%d first · your start %s') % (run['no'] + 1, liverally.hms(st['at'])), c.BAD
        return line, '', (status, stage, ms, 0, line, colour)

    def _lr_overlay_queue(self):
        """The timer window's queue (liverally.overlay_queue): while I follow a session and wait for my start on its
        stage (on the start line, or a stage's official time on its way and my slot on the next one known), that
        stage's whole queue; else None (driving, or nothing to wait for)."""
        self._lr_ready()
        run = getattr(self, 'league_run', None)
        if getattr(self, 'drive_target', None) != 'league' or not run or run.get('over') or \
                run['ev'].get('kind') != liverally.KIND:
            return None
        if not run.get('wait') and run['judge'].state == 'running':
            return None
        key = self._lr_key(run['ev'])
        v = self.lr_data.get(key) if key else None
        now = self.lr_clock.now_ms()
        st = liverally.my_start(v, now)
        no = run['no'] + 1 if run.get('wait') else run['no']
        if not st or st['no'] != no:
            return None
        return liverally.overlay_queue(v, no, self.s.get('steamId'), now)

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
            ov = getattr(self, 'overlay', None)       # (the timer's queue: its countdowns are to the second)
            if ov is not None:
                ov.show_queue(self._lr_overlay_queue())
            if self._lr_queue_want:
                self._lr_queue_try()
            self._lr_watching = self._lr_watch_list()
            if any(len(w) > 2 for w in self._lr_outed.values()):
                self._lr_out_try()
            self._lr_bar_render()
            self._lr_cards_tick()
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
        info = self.lr_info or {}
        mine = self._lr_mine()
        nxt = sorted((s for s in info.get('sessions') or [] if s.get('phase') in ('signup', 'upcoming', 'running')),
                     key=lambda s: s['starts'])
        lines = [(_('Official rallies every 2 hours · start every 30 s · a queue for each stage'), 'sub')]
        badge = None
        if mine:
            s = next((x for x in nxt if (x['series'], x['starts']) == mine), None)
            badge = (_('REGISTERED'), liverally.COLOUR)
            if s:
                lines.append(('%s · %s · %s' % (self._lr_series_name(s['series']), liverally.hm(s['starts']), s.get('rally') or ''), 'info'))
        elif nxt:
            s = next((x for x in nxt if x['phase'] == 'signup'), None)
            if s:
                badge = (_('REGISTRATION OPEN'), liverally.COLOUR)
            s = s or nxt[0]
            lines.append(('%s · %s · %s' % (self._lr_series_name(s['series']), liverally.hm(s['starts']), s.get('rally') or ''), 'info'))
        elif not info:
            lines.append((_('Loading the sessions…'), 'info'))
        rally = (nxt[0].get('rally') if nxt else None)
        return {'photo': photos.for_rally(rally) or 'leagues', 'bottom': True, 'badge': badge, 'title': _('RANKED'),
                'sizes': (34, 30, 26), 'lines': lines, 'button': False}

    def _lr_series_name(self, key):
        return (self._lr_series(key) or {}).get('name') or key

    # -------------------------------------------------------------- the registration bar (along the bottom, every view)
    def _build_lr_bar(self, parent, before=None):
        """(app.py _build) The bar, made once; shown while there is something to say (_lr_bar_render)."""
        c = _c()
        self._lr_bar_before = before
        bar = self.lr_bar = tk.Frame(parent, bg=c.PANEL, highlightthickness=1, highlightbackground=liverally.COLOUR)
        self.lr_bar_chip = tk.Label(bar, text='', bg=liverally.COLOUR, fg=c.WHITE, font=(c.FONT_C, 11), padx=10, pady=4)
        self.lr_bar_chip.pack(side='left', fill='y')
        self.lr_bar_kind = tk.Label(bar, text=_('RANKED'), bg=c.PANEL, fg=liverally.COLOUR, font=(c.FONT_C, 11), padx=10)
        self.lr_bar_kind.pack(side='left')
        self.lr_bar_words = tk.Label(bar, text='', bg=c.PANEL, fg=c.SOFT, font=(c.FONT, 10), anchor='w', cursor='hand2')
        self.lr_bar_words.pack(side='left', fill='x', expand=True)
        self.lr_bar_button = tk.Label(bar, text='', bg=c.WHITE, fg=c.BG, font=(c.FONT_C, 11), padx=14, pady=3, cursor='hand2')
        self.lr_bar_time = tk.Label(bar, text='', bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, 16), padx=10)
        self.lr_bar_label = tk.Label(bar, text='', bg=c.PANEL, fg=c.MUTED, font=(c.FONT_C, 10))
        self.lr_bar_button.pack(side='right', padx=(6, 8), pady=4)
        self.lr_bar_time.pack(side='right')
        self.lr_bar_label.pack(side='right')
        for w in (self.lr_bar_words, self.lr_bar_kind):
            w.bind('<Button-1>', lambda _e: self.open_live_rallies(self._lr_bar_key and self._lr_bar_key[0]))
        self.lr_bar_button.bind('<Button-1>', lambda _e: self._lr_bar_go())

    def _lr_bar_state(self):
        run = getattr(self, 'league_run', None)
        follow = driving = None
        if self.drive_target == 'league' and run and not run.get('over') and run['ev'].get('kind') == liverally.KIND:
            follow = self._lr_key(run['ev'])
            if run['judge'].state == 'running' and not run.get('wait'):
                driving = run['no']
        return liverally.bar_state(self.lr_info, self.lr_data, self.lr_clock.now_ms(), follow=follow, armed=self._lr_armed,
                                   driving=driving, name_of=self._lr_series_name, me_id=self.s.get('steamId'))

    def _lr_bar_render(self):
        bar = getattr(self, 'lr_bar', None)
        if bar is None:
            return
        c = _c()
        st = self._lr_bar_state() if liverally.ON else None
        key = None if st is None else (st['key'], st['chip'], st['tone'], st['words'], st['label'], st['time'], st['button'])
        if key == (self._lr_bar_key[1] if self._lr_bar_key else None):
            return
        self._lr_bar_key = (st['key'], key) if st else None
        if st is None:
            if bar.winfo_manager():
                bar.pack_forget()
            return
        tone = {'good': c.GOOD, 'bad': c.BAD, 'slow': c.SLOW}.get(st['tone'], liverally.COLOUR)
        self.lr_bar_chip.configure(text=st['chip'], bg=tone, fg=c.BG if st['tone'] in ('good', 'slow') else c.WHITE)
        self.lr_bar_words.configure(text=st['words'])
        self.lr_bar_label.configure(text=st['label'])
        self.lr_bar_time.configure(text=st['time'], fg=tone if st['tone'] != 'soft' else c.WHITE)
        self._lr_bar_action = st['button'][1] if st['button'] else None
        if st['button']:
            primary = st['button'][1] in ('drive', 'arm')
            self.lr_bar_button.configure(text=st['button'][0] + ('  ›' if primary else ''),
                                         bg=c.WHITE if primary else c.PANEL2, fg=c.BG if primary else c.SOFT)
            if not self.lr_bar_button.winfo_manager():
                self.lr_bar_button.pack(side='right', padx=(6, 8), pady=4, before=self.lr_bar_time)
        elif self.lr_bar_button.winfo_manager():
            self.lr_bar_button.pack_forget()
        if not bar.winfo_manager():
            before = getattr(self, '_lr_bar_before', None)
            bar.pack(side='bottom', fill='x', padx=20, pady=(0, 8), **({'before': before} if before is not None else {}))

    def _lr_bar_go(self):
        key = self._lr_bar_key[0] if self._lr_bar_key else None
        action = getattr(self, '_lr_bar_action', None)
        if not key or not action:
            return
        if action == 'withdraw':
            self.lr_signup(key, withdraw=True)
        elif action == 'drive':
            self.lr_drive(key)
        elif action == 'arm':
            self.lr_arm(key)
        else:
            self.lr_tab = 'standings'
            self.open_live_rallies(key)

    # -------------------------------------------------------------- the cards over everything (rankedcard.py)
    def _lr_ready_card(self, key, v):
        """At the hour: YOUR RALLY IS READY, DRIVE, the time left to my start (to the end of its window: then I go to
        the end of the queue). Once a session."""
        if (key, 'ready') in self._lr_shown or 'ready' in self._lr_cards:
            return
        now = self.lr_clock.now_ms()
        st = liverally.my_start(v, now)
        if not st or st['no'] != 0 or st['phase'] == 'late':
            return
        self._lr_shown.add((key, 'ready'))
        ev = v['event']
        r = liverally.rules_of(v)
        stages = '   '.join('SS%d %s' % (s['no'], s.get('name') or '') for s in ev.get('stages') or [])
        weather = ev['stages'][0].get('weatherLabel') if ev.get('stages') else ''
        place = next((i + 1 for i, q in enumerate((v.get('queues') or [[]])[0]) if q.get('steamId') == self.s.get('steamId')), None)
        lines = [stages, '%s  ·  %s%s' % ((v.get('me') or {}).get('car') or '', weather or '',
                                          ('  ·  ' + _('car %d on the start list') % place) if place else '')]

        def countdown():
            s2 = liverally.my_start(self.lr_data.get(key), self.lr_clock.now_ms())
            if not s2:
                return _('Your start'), '', _c().WHITE
            words = _('Your start  SS%d  %s') % (s2['no'] + 1, liverally.hms(s2['at']))
            return words, (liverally.left(s2['left']) if s2['phase'] == 'wait' else _('GO')), \
                _c().GOOD if s2['phase'] != 'wait' or s2['left'] > 60000 else _c().SLOW
        deadline = time.monotonic() + (st['at'] + r['windowS'] * 1000 - now) / 1000
        self._lr_open_card('ready', None, _('RANKED · YOUR RALLY IS READY'), '%s · %s' % (
            self._lr_series_name(key[0]), v.get('rally') or ev.get('rally') or ''), lines, _('DRIVE  ›'),
            lambda: self.lr_drive(key), countdown, deadline, True)

    def _lr_cards_tick(self):
        """(twice a second) The ready card's chance (my rally out, not driven yet: once), and the START SSn card on my
        next stage's start line while it isn't pressed (under the timer); each gone when it no longer applies."""
        for kind in [k for k, card in self._lr_cards.items() if not card.alive]:
            del self._lr_cards[kind]                     # (closed: LATER, its deadline)
        st = self._lr_bar_state() if liverally.ON else None
        if st and st['button'] and st['button'][1] == 'drive' and st['chip'] == _('READY'):
            self._lr_ready_card(st['key'], self.lr_data.get(st['key']) or {})
        elif 'ready' in self._lr_cards and not (st and st['button'] and st['button'][1] == 'drive'):
            self._lr_close_card('ready')                 # (DRIVE pressed elsewhere, or it is too late)
        run = getattr(self, 'league_run', None)
        on_line = bool(st and st['button'] and st['button'][1] == 'arm' and run and
                       (run['judge'].state == 'armed' or getattr(run['judge'], 'approaching', False)))
        if not on_line:
            self._lr_close_card('start')
            return
        key = st['key']
        v = self.lr_data.get(key) or {}
        s2 = liverally.my_start(v, self.lr_clock.now_ms())
        if 'start' in self._lr_cards or not s2:
            return
        ev = v.get('event') or {}
        stage = (ev.get('stages') or [{}] * (s2['no'] + 1))[s2['no']]

        def countdown():
            s3 = liverally.my_start(self.lr_data.get(key), self.lr_clock.now_ms())
            if not s3:
                return '', '', _c().WHITE
            return (_('Your start  %s') % liverally.hms(s3['at']),
                    liverally.left(s3['left']) if s3['phase'] == 'wait' else _('GO') if s3['phase'] == 'go' else _('LATE'),
                    _c().GOOD if s3['phase'] == 'go' else _c().BAD if s3['phase'] == 'late' else _c().WHITE)
        ov = getattr(getattr(self, 'overlay', None), 'win', None)
        try:
            at = (ov.winfo_x(), ov.winfo_y() + ov.winfo_height() + 8) if ov is not None and ov.winfo_ismapped() else None
        except tk.TclError:
            at = None
        self._lr_open_card('start', at, _('RANKED · SS%d') % (s2['no'] + 1), stage.get('name') or '',
                           [_('Press START SS%d, then start the stage at GO: only then does it count for ranked. A run '
                              'without it is practice, and practice on a ranked stage is a DNF.') % (s2['no'] + 1)],
                           _('START SS%d  ›') % (s2['no'] + 1), lambda: self.lr_arm(key), countdown, None, False)

    def _lr_open_card(self, kind, at, kicker, title, lines, label, go, countdown, deadline, later):
        def pressed():
            self._lr_cards.pop(kind, None)
            go()
        try:
            self._lr_cards[kind] = rankedcard.RankedCard(self.root, at, kicker, title, lines, label, pressed, countdown=countdown,
                                                         deadline=deadline, later=later, colour=liverally.COLOUR)
        except (tk.TclError, AttributeError, TypeError):
            self._lr_cards.pop(kind, None)               # (no window to put it on: the tests' bare apps)

    def _lr_close_card(self, kind):
        card = self._lr_cards.pop(kind, None)
        if card is not None:
            card.close()

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
        self._lbl(head, _('RANKED'), font=(c.FONT_C, 24), fg=c.WHITE).pack(side='left')
        tk.Label(head, text=_('NOT RATED YET'), bg=c.BG, fg=liverally.COLOUR, font=(c.FONT_C, 10), padx=6,
                 highlightthickness=1, highlightbackground=liverally.COLOUR).pack(side='left', padx=(12, 0), pady=(8, 0))
        self._lbl(page, _('Official rallies every 2 hours, the two series in turn. Register in the 30 minutes before the '
                          'hour: the stages and the weather are drawn at the hour, with the start list.'),
                  fg=c.FG2, font=(c.FONT, 9), wraplength=900).pack(anchor='w', padx=20, pady=(2, 10))
        if info is None or not info.get('on'):
            text = self.lr_msg or (_('Loading…') if info is None else _('No ranked rallies on this server yet.'))
            self._lbl(page, text, fg=c.SOFT, font=(c.FONT, 10), wraplength=800).pack(anchor='w', padx=20, pady=(10, 12))
            return
        self._lr_heading(page, _('SERIES'))
        for s in info.get('series') or []:
            self._lr_series_row(page, s, info, now)
        if self.lr_sel:
            self._lr_session(page, self.lr_sel, now)
        self._lr_upcoming(page, info, now)
        r = liverally.rules_of(info)
        self._lbl(page, _('Car 1 starts %d minutes after the hour, then one every %d s; after each stage you join the next '
                          'stage\'s queue. Before each stage press START SSn, then start at GO: a start counts for ranked '
                          'only then. Late: you go to the end of the queue. Early: the seconds you jumped are added. A '
                          'restart, retiring, the wrong mode, settings changed in the game, or practice on a ranked stage '
                          'before your run on it: DNF. Ghost cars: this rally\'s drivers only.') % (r['firstStartMin'], r['gapS']),
                  fg=c.MUTED, font=(c.FONT, 8), wraplength=900).pack(anchor='w', padx=20, pady=(14, 10))

    def _lr_heading(self, parent, text, right=None):
        c = _c()
        row = tk.Frame(parent, bg=c.BG)
        row.pack(fill='x', padx=20, pady=(12, 4))
        self._k(row, text).pack(side='left')
        if right:
            self._lbl(row, right, fg=c.MUTED, font=(c.FONT, 8)).pack(side='right')
        tk.Frame(parent, bg=c.LINE, height=1).pack(fill='x', padx=20)

    def _lr_series_row(self, page, s, info, now):
        """A series as iRacing lists one: its picture, class and name, its cars, this week's country, its next session
        (when, how long to go, how many registered), the car picked and REGISTER / WITHDRAW."""
        c = _c()
        nxt = liverally.next_session(info, s['key'], now)
        key = (s['key'], nxt['starts']) if nxt else None
        picked = bool(key) and key == self.lr_sel
        row = tk.Frame(page, bg=c.PANEL2 if picked else c.PANEL, cursor='hand2')
        row.pack(fill='x', padx=20, pady=(6, 0))
        bg = row.cget('bg')
        tk.Frame(row, bg=liverally.COLOUR if picked else c.LINE2, width=4).pack(side='left', fill='y')
        img = photos.thumb(row, photos.for_rally(s.get('rally')), 132, 74)
        if img:
            tk.Label(row, image=img, bg=bg, bd=0).pack(side='left', padx=(10, 0), pady=8)
        mid = tk.Frame(row, bg=bg)
        mid.pack(side='left', fill='both', expand=True, padx=14, pady=8)
        top = tk.Frame(mid, bg=bg)
        top.pack(anchor='w')
        tk.Label(top, text=s.get('carClass') or '', bg=c.WHITE, fg=c.BG, font=(c.FONT_C, 10), padx=6).pack(side='left')
        tk.Label(top, text=(s.get('name') or '').upper(), bg=bg, fg=c.WHITE, font=(c.FONT_C, 18)).pack(side='left', padx=(8, 0))
        tk.Label(mid, text='  ·  '.join(x['name'] for x in s.get('cars') or []), bg=bg, fg=c.FG2, font=(c.FONT, 9),
                 anchor='w').pack(anchor='w', pady=(2, 0))
        week = tk.Label(mid, text=_('This week  %s   ·   next week  %s') % (s.get('rally') or '', s.get('nextRally') or ''),
                        bg=bg, fg=c.SOFT, font=(c.FONT, 9), anchor='w')
        week.pack(anchor='w', pady=(2, 0))
        right = tk.Frame(row, bg=bg)
        right.pack(side='right', padx=(0, 14), pady=8)
        when = tk.Frame(right, bg=bg)
        when.pack(side='left', padx=(0, 18))
        tk.Label(when, text=_('NEXT SESSION'), bg=bg, fg=c.MUTED, font=(c.FONT_C, 9), anchor='e').pack(anchor='e')
        tk.Label(when, text=liverally.hm(nxt['starts']) if nxt else '–', bg=bg, fg=c.WHITE, font=(c.FONT_C, 22),
                 anchor='e').pack(anchor='e')
        if nxt:
            t = lambda n=nxt: liverally.card_line(n, self.lr_clock.now_ms())   # noqa: E731
            l = tk.Label(when, text=t(), bg=bg, fg=c.FG2, font=(c.FONT, 8), anchor='e')
            l.pack(anchor='e')
            self._lr_cd.append((l, t))
        act = tk.Frame(right, bg=bg)
        act.pack(side='left')
        if nxt and nxt['phase'] in ('signup', 'upcoming') and not nxt.get('signedUp'):
            car = self._lr_car(s['key'])                  # the car to register with (iRacing's car pick)
            cl = tk.Label(act, text=(car or '') + '  ▾', bg=c.BG, fg=c.SOFT, font=(c.FONT, 9), padx=8, pady=3,
                          cursor='hand2', highlightthickness=1, highlightbackground=c.LINE2)
            cl.pack(anchor='e', pady=(0, 6))
            cl.bind('<Button-1>', lambda e, sr=s: self._lr_car_menu(e.widget, sr))
        if not nxt:
            pass
        elif nxt.get('signedUp') and nxt['phase'] == 'signup':
            self._btn(act, _('WITHDRAW'), lambda k=key: self.lr_signup(k, withdraw=True), surface=bg).pack(anchor='e')
        elif nxt['phase'] == 'signup':
            self._btn(act, _('REGISTER  ›'), lambda k=key: self.lr_signup(k), primary=True, surface=bg).pack(anchor='e')
        elif nxt['phase'] == 'upcoming':
            b = self._btn(act, _('OPENS %s') % liverally.hm(nxt['signupOpens']), lambda: None, surface=bg)
            b.configure(cursor='arrow', fg=c.MUTED)
            b.pack(anchor='e')
        elif nxt['phase'] == 'running':
            self._btn(act, _('VIEW  ›') if nxt.get('signedUp') else _('UNDER WAY'), lambda k=key: self.lr_pick(k),
                      surface=bg).pack(anchor='e')
        if key:
            for w in (row, mid, top, week, when):
                w.bind('<Button-1>', lambda _e, k=key: self.lr_pick(k))

    def _lr_car_menu(self, widget, s):
        c = _c()
        m = tk.Menu(widget, tearoff=0, bg=c.PANEL, fg=c.SOFT, activebackground=c.WHITE, activeforeground=c.BG)
        for car in s.get('cars') or []:
            m.add_command(label=car['name'], command=lambda n=car['name']: self.lr_pick_car(s['key'], n))
        m.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())

    def _lr_session(self, page, key, now):
        """The session picked: before its hour who registered; from it its stages, START LIST, SS2 / SS3 QUEUE and
        RESULTS, as iRacing's session tabs."""
        c = _c()
        v = self.lr_data.get(key)
        s_row = next((s for s in (self.lr_info or {}).get('sessions') or [] if (s['series'], s['starts']) == key), None)
        rally = (v or s_row or {}).get('rally') or ''
        phase = (v or s_row or {}).get('phase')
        chip = {'upcoming': _('REGISTRATION OPENS %s') % liverally.hm(key[1] - 30 * 60000), 'signup': _('REGISTRATION OPEN'),
                'running': _('UNDER WAY'), 'over': _('OVER'), 'empty': _('NOBODY REGISTERED')}.get(phase, '')
        self._lr_heading(page, _('SESSION'), chip)
        box = tk.Frame(page, bg=c.PANEL)
        box.pack(fill='x', padx=20)
        head = tk.Frame(box, bg=c.PANEL)
        head.pack(fill='x', padx=14, pady=(10, 2))
        self._lbl(head, '%s  ·  %s  ·  %s' % (self._lr_series_name(key[0]).upper(), liverally.hm(key[1]), rally.upper()),
                  font=(c.FONT_C, 16), fg=c.WHITE, bg=c.PANEL).pack(side='left')
        if v is None:
            self._lbl(box, self.lr_msg or _('Loading the session…'), fg=c.SOFT, bg=c.PANEL).pack(anchor='w', padx=14, pady=(4, 12))
            return
        me = v.get('me') or {}
        if phase in ('upcoming', 'signup') or (v.get('publishing') and not v.get('event')):
            self._lr_signup_part(box, key, v)
        elif v.get('event'):
            self._lr_rally_part(box, key, v, me, now)
        else:
            self._lbl(box, _('Nobody registered for this one.'), fg=c.SOFT, bg=c.PANEL).pack(anchor='w', padx=14, pady=(4, 12))

    def _lr_signup_part(self, box, key, v):
        c = _c()
        me = v.get('me') or {}
        if v.get('publishing'):
            t = lambda: _('Drawing the rally and the start list…')    # noqa: E731
        elif v.get('phase') == 'upcoming':
            t = lambda: _('Registration opens in %s (%s).') % (liverally.left(v['signupOpens'] - self.lr_clock.now_ms()),   # noqa: E731
                                                              liverally.hm(v['signupOpens']))
        else:
            t = lambda: _('The stages, the weather and the start list come out in %s, at %s. Car 1 starts at %s.') % (   # noqa: E731
                liverally.left(v['starts'] - self.lr_clock.now_ms()), liverally.hm(v['starts']), liverally.hm(v['firstStart']))
        l = self._lbl(box, t(), fg=c.SOFT, bg=c.PANEL, font=(c.FONT, 10))
        l.pack(anchor='w', padx=14, pady=(2, 6))
        self._lr_cd.append((l, t))
        if me.get('signedUp'):
            self._lbl(box, '✓ ' + _('Registered with the %s') % me.get('car'), fg=c.GOOD, bg=c.PANEL,
                      font=(c.FONT, 10, 'bold')).pack(anchor='w', padx=14)
        ents = v.get('entrants') or []
        self._k(box, n_('%d REGISTERED', '%d REGISTERED', len(ents)) % len(ents), bg=c.PANEL).pack(anchor='w', padx=14, pady=(10, 2))
        grid = tk.Frame(box, bg=c.PANEL)
        grid.pack(fill='x', padx=14, pady=(0, 12))
        for i, e in enumerate(ents[:40]):
            self._lbl(grid, e.get('name') or '?', fg=c.WHITE if e.get('steamId') == self.s.get('steamId') else c.SOFT,
                      bg=c.PANEL, font=(c.FONT, 9)).grid(row=i // 4, column=i % 4, sticky='w', padx=(0, 24))
            self._lbl(grid, e.get('car') or '', fg=c.MUTED, bg=c.PANEL, font=(c.FONT, 8)).grid(
                row=i // 4, column=i % 4, sticky='e', padx=(0, 24))

    def _lr_rally_part(self, box, key, v, me, now):
        c = _c()
        ev = v['event']
        grid = tk.Frame(box, bg=c.PANEL)                  # the itinerary
        grid.pack(fill='x', padx=14, pady=(4, 4))
        for i, h in enumerate((_('SS'), _('STAGE'), _('LENGTH'), _('WEATHER'), _('TIME OF DAY'))):
            self._k(grid, h, bg=c.PANEL).grid(row=0, column=i, sticky='w', padx=(0, 22))
        for r_, s in enumerate(ev.get('stages') or [], start=1):
            for i, t in enumerate(('SS%d' % s['no'], s.get('name') or '', '%.1f km' % ((s.get('lengthM') or 0) / 1000),
                                   s.get('weatherLabel') or s.get('weather') or '', s.get('time') or '')):
                self._lbl(grid, t, fg=c.WHITE if i == 1 else c.SOFT, bg=c.PANEL, font=(c.FONT, 9)).grid(
                    row=r_, column=i, sticky='w', padx=(0, 22))
        self._lbl(box, (ev.get('carClass') or '') + '  ·  ' + _('service park before SS1 only: the damage carries'),
                  fg=c.MUTED, bg=c.PANEL, font=(c.FONT, 8)).pack(anchor='w', padx=14)
        st = self._lr_bar_state() if me.get('signedUp') else None
        if st and st['key'] == key:                       # my place in it: as the bar says, with its button
            mine = tk.Frame(box, bg=c.PANEL2)
            mine.pack(fill='x', padx=14, pady=(10, 4))
            t = lambda: ((self._lr_bar_state() or {}).get('words') or '').split('  ·  ', 1)[-1]   # noqa: E731
            l = self._lbl(mine, t(), font=(c.FONT_C, 15), fg=liverally.COLOUR, bg=c.PANEL2)
            l.pack(side='left', padx=10, pady=8)
            self._lr_cd.append((l, t))
            if st['button']:
                self._btn(mine, st['button'][0] + '  ›', self._lr_bar_go, primary=st['button'][1] in ('drive', 'arm'),
                          surface=c.PANEL2).pack(side='right', padx=10)
        n = len(ev.get('stages') or [])
        tab = self.lr_tab
        if tab is None:                                   # (as it goes: my next stage's queue, the results once over)
            s2 = liverally.my_start(v, now)
            done = (ev.get('entry') or {}).get('status') in ('finished', 'dnf', 'dsq')
            tab = s2['no'] if s2 else 'standings' if v.get('phase') == 'over' or done else 0
        tabs = tk.Frame(box, bg=c.PANEL)
        tabs.pack(fill='x', padx=14, pady=(8, 0))
        names_ = [(k, _('START LIST') if k == 0 else _('SS%d QUEUE') % (k + 1)) for k in range(n)] + [('standings', _('RESULTS'))]
        for kk, text in names_:
            on = kk == tab
            cell = tk.Frame(tabs, bg=c.PANEL)
            cell.pack(side='left', padx=(0, 4))
            b = tk.Label(cell, text=text, bg=c.PANEL2 if on else c.PANEL, fg=c.WHITE if on else c.FG2, font=(c.FONT_C, 11),
                         padx=12, pady=4, cursor='hand2')
            b.pack()
            tk.Frame(cell, bg=liverally.COLOUR if on else c.PANEL, height=2).pack(fill='x')
            b.bind('<Button-1>', lambda _e, t2=kk: self.lr_show_tab(t2))
        table = tk.Frame(box, bg=c.PANEL)
        table.pack(fill='x', padx=14, pady=(6, 12))
        sid = self.s.get('steamId')
        colour = {'good': c.GOOD, 'bad': c.BAD, 'slow': c.SLOW, 'live': liverally.COLOUR, 'muted': c.MUTED}
        if tab == 'standings':
            heads = (_('POS'), _('DRIVER'), _('CAR'), _('TOTAL'), _('GAP'))
            cells = [(p, nm, car, tot, gap, c.WHITE if mine_ else c.SOFT, mine_)
                     for p, nm, car, tot, gap, mine_ in liverally.standings_rows(v, sid)]
        else:
            heads = (_('START'), _('DRIVER'), _('CAR'), _('STATE'), '')
            cells = [(at, nm, car, what, '', colour.get(col, c.SOFT), mine_)
                     for at, nm, car, what, col, mine_ in liverally.queue_rows(v, tab, sid)]
        for i, h in enumerate(heads):
            self._k(table, h, bg=c.PANEL).grid(row=0, column=i, sticky='w', padx=(0, 18), pady=(0, 2))
        if not cells:
            self._lbl(table, _('Nobody yet: drivers join this queue as they finish the stage before.') if tab not in (0, 'standings')
                      else _('Nobody yet.'), fg=c.MUTED, bg=c.PANEL, font=(c.FONT, 9)).grid(row=1, column=0, columnspan=5, sticky='w')
        for r_, cell in enumerate(cells[:SHOWN_ROWS], start=1):
            *texts, fg, mine_ = cell
            rbg = c.PANEL2 if mine_ else c.PANEL
            for i, t in enumerate(texts):
                self._lbl(table, t, fg=(c.WHITE if mine_ and i == 1 else fg if i == 3 else c.SOFT), bg=rbg,
                          font=(c.FONT, 9, 'bold' if mine_ else 'normal')).grid(row=r_, column=i, sticky='ew', padx=(0, 18), ipady=1)
        table.columnconfigure(3, weight=1)

    def _lr_upcoming(self, page, info, now):
        """The other sessions, as iRacing's session list: when, which series, where, how many registered, a click shows it."""
        c = _c()
        ss = [s for s in info.get('sessions') or [] if (s['series'], s['starts']) != self.lr_sel and s['phase'] != 'over']
        if not ss:
            return
        self._lr_heading(page, _('UPCOMING SESSIONS'))
        table = tk.Frame(page, bg=c.BG)
        table.pack(fill='x', padx=20, pady=(4, 0))
        for i, h in enumerate((_('START'), _('SERIES'), _('COUNTRY'), _('REGISTERED'), '')):
            self._k(table, h).grid(row=0, column=i, sticky='w', padx=(0, 22))
        for r_, s in enumerate(ss[:8], start=1):
            key = (s['series'], s['starts'])
            mark = '✓ ' if s.get('signedUp') else ''
            cells = (mark + liverally.hm(s['starts']), self._lr_series_name(s['series']), s.get('rally') or '',
                     str(s.get('signups') or 0), liverally.card_line(s, now))
            for i, t in enumerate(cells):
                l = self._lbl(table, t, fg=c.GOOD if mark and i == 0 else c.SOFT if i < 4 else c.MUTED, font=(c.FONT, 9),
                              cursor='hand2')
                l.grid(row=r_, column=i, sticky='w', padx=(0, 22), pady=1)
                l.bind('<Button-1>', lambda _e, k=key: self.lr_pick(k))
        table.columnconfigure(4, weight=1)
