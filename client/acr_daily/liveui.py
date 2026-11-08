"""The app's LIVE tab, mixed into App (app.py) like the pages beside it (inboxui.py, settingsui.py): who is driving
right now, as on the website's live map (server src/stagemap.js), in the view's place while open.

    [ DAILIES | TIME TRIAL ]                          3 drivers on stage · Live map on the website ›
    SS1 · PEÏRA CAVA - LA BOLLÈNE-VÉSUBIE   2 ON STAGE     SS2 · OBERSTEIGEN               NOBODY ON STAGE
    (the stage's road, each driver a dot in their own colour gliding along it, their name by it)
     1  ● Kalle R.        64 %   4:12.3                    Nobody on this stage right now.
     2  ● MaybeIWill      31 %   2:01.8
     –  ● Ott T.          FINISHED  6:58.412

Both dailies come in one request (GET /api/live?slot=all), both time trial stages in one (GET /api/tt/live?slot=all),
only the part shown, only while the tab is open and the window not minimised: every few seconds while someone is on a
stage, less often while nobody is (the server's timing, as the website: LIVE_BUSY, LIVE_IDLE in server src/site.js).
The cars are played back a few seconds late along the road (glide.py, the website's glide.js), so they move steadily
between the apps' updates; the list says where each driver is now, their clock running.
"""
import threading
import time
import tkinter as tk

from . import glide, tiles, tmtext, widgets
from .api import ApiError

LIVE_COLOUR = '#FF453A'        # the tab's colour (the badge's LIVE red)
FRAME_MS = 100                 # the cars and the clocks: 10 times a second
ROWS = 8                       # drivers listed on each stage (the rest: '+3 more')
PARTS = (('daily', 'DAILIES'), ('tt', 'TIME TRIAL'))


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def live_order(drivers):
    """A stage's drivers as the list shows them: those on it first, the furthest along first; then the finishers, the
    quickest first; then the DNFs."""
    def key(d):
        st = d.get('state')
        if st == 'live':
            return 0, -(d.get('progress') or 0), 0
        if st == 'finished':
            return 1, 0, d.get('totalMs') or 0
        return 2, 0, 0
    return sorted(drivers or [], key=key)


def clock_ms(d, server_now):
    """A driver's time as the list shows it: a finisher's own; on a stage, theirs when they last sent it, run on to
    server_now (the server's clock, as this computer reckons it)."""
    t = d.get('totalMs') or 0
    if d.get('state') == 'live' and d.get('updated') and server_now:
        t += max(0, server_now - d['updated'])
    return t


def fmt_clock(ms, exact=False):
    """'4:12.3' (running), '6:58.412' (a finish)."""
    ms = max(0, int(ms))
    m, s = divmod(ms / 1000, 60)
    return ('%d:%06.3f' % (m, s)) if exact else ('%d:%04.1f' % (m, int(s * 10) / 10))


class LiveUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    live_view = False
    live_box = None
    live_part = 'daily'            # the part shown: the dailies or the time trial
    _live_hid = ()
    _live_answer = None            # {part: {'drivers', 'now', 'at' (this computer's ms), 'key'}}
    _live_pb = None                # {(part, slot): glide.LivePlayback}
    _live_busy = False
    _live_polled = -1e9
    _live_frame_job = None
    _live_any = False              # someone on a stage in the last answer (the tab's dot blinks)

    # -------------------------------------------------------------- the tab
    def _build_live_button(self, parent):
        """LIVE, a block like the tabs' with a dot (red and blinking while someone is on a stage), after CUPS."""
        c = _c()
        k = self.root.winfo_fpixels('1i') / 96 if hasattr(self, 'root') else 1
        f = tk.Frame(parent, bg=c.BG)
        f.pack(side='left', padx=(0, 2))
        top = self._live_top = tk.Frame(f, bg=c.PANEL, cursor='hand2')
        top.pack(fill='both', expand=True)
        self.live_dot = tk.Canvas(top, width=round(10 * k), height=round(10 * k), bg=c.PANEL, highlightthickness=0, cursor='hand2')
        self.live_dot.pack(side='left', padx=(round(16 * k), round(6 * k)))
        self.live_l = tk.Label(top, text='LIVE', bg=c.PANEL, fg=LIVE_COLOUR, font=(c.FONT_C, 12), pady=7, cursor='hand2')
        self.live_l.pack(side='left', padx=(0, round(18 * k)))
        self.live_u = tk.Frame(f, bg=c.BG, height=3)          # the tab's underline
        self.live_u.pack(fill='x')
        for w in (f, top, self.live_dot, self.live_l):
            w.bind('<Button-1>', lambda _e: self.toggle_live_view())
            w.bind('<Enter>', lambda _e: self._live_badge(hover=True))
            w.bind('<Leave>', lambda _e: self._live_badge())
        self._live_badge()

    def _live_badge(self, hover=False):
        top = getattr(self, '_live_top', None)
        if top is None:
            return
        c = _c()
        on = self.live_view
        bg = c.WHITE if on else c.PANEL2 if hover else c.PANEL
        for w in (top, self.live_dot, self.live_l):
            w.configure(bg=bg)
        self.live_l.configure(fg=c.BG if on else c.WHITE if hover else LIVE_COLOUR)
        self.live_u.configure(bg=LIVE_COLOUR if on else c.BG)
        self._draw_live_dot()

    def _draw_live_dot(self):
        cv = getattr(self, 'live_dot', None)
        if cv is None:
            return
        c = _c()
        if self._live_any:                       # someone on a stage: red, blinking
            col = LIVE_COLOUR
            fill = col if (time.monotonic() % 1.0) < 0.6 else cv.cget('bg')
        else:                                    # nobody (or not known yet): red while the page is open, else grey
            col = fill = LIVE_COLOUR if self.live_view else c.MUTED
        w = int(cv.cget('width'))
        cv.delete('all')
        cv.create_oval(1, 1, w - 1, w - 1, fill=fill, outline=col)

    # -------------------------------------------------------------- opening and closing it
    def toggle_live_view(self, on=None):
        on = (not self.live_view) if on is None else on
        if on == self.live_view:
            return
        if not on:
            self._live_leave()
            self._view_box().pack(fill='x', before=self._view_end)
            self._render_strip()
            return
        self._pages_leave()                          # (the inbox or the settings give way)
        self.live_view = True
        self._live_hid = self._page_show(self.live_box)
        self._mark_tabs()
        self._render_live()
        self._live_poll(force=True)
        self._live_frame()

    def _live_leave(self):
        if not self.live_view:
            return
        self.live_view = False
        self._page_hide(self.live_box, self._live_hid)
        self._live_hid = ()
        job, self._live_frame_job = self._live_frame_job, None
        if job is not None:
            self.root.after_cancel(job)
        self._mark_tabs()

    def live_show_part(self, part):
        """DAILIES or TIME TRIAL on the page: its stages, asked for at once."""
        if part != self.live_part:
            self.live_part = part
            self._render_live()
            self._live_poll(force=True)

    # -------------------------------------------------------------- the page
    def _build_live_box(self):
        """The page's frame: its head (the parts, what is going on), and two panels, one a stage (_render_live)."""
        c = _c()
        self.live_box = box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)
        head = tk.Frame(box, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(0, 8))
        self._live_chips = {}
        for part, text in PARTS:
            l = tk.Label(head, text=text, font=(c.FONT_C, 11), padx=14, pady=4, cursor='hand2', highlightthickness=1)
            l.bind('<Button-1>', lambda _e, p=part: self.live_show_part(p))
            l.pack(side='left', padx=(0, 6))
            self._live_chips[part] = l
        self._live_site = self._link(head, 'Live map on the website  ›', lambda: self.open_page('/tt' if self.live_part == 'tt' else '/'))
        self._live_site.pack(side='right')
        self.live_note = self._lbl(head, '', fg=c.FG2, font=(c.FONT, 9))
        self.live_note.pack(side='right', padx=(0, 18))
        self.live_panels = tk.Frame(box, bg=c.BG)
        self.live_panels.pack(fill='both', expand=True)
        for col in (0, 1):
            self.live_panels.columnconfigure(col, weight=1, uniform='live')
        self.live_panels.rowconfigure(0, weight=1)
        self._live_stages = {}

    def _live_held(self, part):
        """{slot: {'ch', 'route'}} of the part's stages: the dailies, or the week's time trial stages."""
        held = self.dailies if part == 'daily' else (getattr(self, 'tt', None) or {})
        out = {}
        for slot, d in sorted(held.items()):
            j = d.get('judge')
            out[slot] = {'ch': d.get('ch') or {}, 'route': j.route.points if j else (d.get('ch') or {}).get('route')}
        return out

    def _render_live(self):
        """The page's parts as they are: the chips, a panel per stage (its name, car, map and list)."""
        if self.live_box is None:
            return
        c = _c()
        for part, l in self._live_chips.items():
            on = part == self.live_part
            l.configure(bg=c.WHITE if on else c.BG, fg=c.BG if on else c.FG2, highlightbackground=c.WHITE if on else c.LINE2)
        for w in self.live_panels.winfo_children():
            w.destroy()
        self._live_stages = {}
        stages = self._live_held(self.live_part)
        if not stages:
            text = ('Loading today\'s stages…' if self.live_part == 'daily' else
                    'There is no time trial this week.' if (getattr(self, 'tt_info', None) or {}).get('on') is False else
                    'Loading the time trial…')
            self._lbl(self.live_panels, text, fg=c.SOFT, font=(c.FONT, 10)).grid(row=0, column=0, sticky='nw', padx=20, pady=10)
            return
        label = 'SS%d' if self.live_part == 'daily' else 'TT%d'
        k = self.root.winfo_fpixels('1i') / 96
        for i, (slot, st) in enumerate(stages.items()):
            if i > 1:
                break
            ch = st['ch']
            p = tk.Frame(self.live_panels, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE)
            p.grid(row=0, column=i, sticky='nsew', padx=(20, 6) if i == 0 else (6, 20))
            top = tk.Frame(p, bg=c.PANEL)
            top.pack(fill='x', padx=14, pady=(12, 0))
            count = tk.Label(top, text='', bg=c.PANEL, fg=c.MUTED, font=(c.FONT_C, 10), padx=8, pady=1)
            count.pack(side='right')
            tk.Label(top, text=label % slot, bg=c.WHITE, fg=c.BG, font=(c.FONT_C, 11), padx=7).pack(side='left')
            name = c.stage_name(ch).upper()
            pw = self.live_panels.winfo_width() if self.live_panels.winfo_ismapped() else round(920 * k)
            size = tiles.fit_size(top, name, max(120, pw // 2 - round(200 * k)), (14, 13, 12, 11))   # (beside the count)
            tk.Label(top, text=name, bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, size), anchor='w').pack(side='left', padx=(10, 10))
            sub = '  ·  '.join(x for x in (ch.get('car') or '', c.conditions(ch)) if x)
            self._lbl(p, sub, fg=c.FG2, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w', padx=14, pady=(4, 6))
            rows = tk.Frame(p, bg=c.PANEL)              # the list under the map; the map takes the room left
            rows.pack(side='bottom', fill='x', padx=14, pady=(8, 12))
            cv = tk.Canvas(p, height=round(160 * k), bg='#0E0E11', highlightthickness=0)
            cv.pack(fill='both', expand=True, padx=14)
            s = self._live_stages[slot] = {'canvas': cv, 'rows': rows, 'count': count, 'route': st['route'],
                                           'track': glide.RouteTrack(st['route']), 'to': None, 'clocks': [], 'id': ch.get('id')}
            cv.bind('<Configure>', lambda _e, s=s: self._live_draw_map(s))
            self._live_draw_map(s)
        self._live_fill()

    def _live_draw_map(self, s):
        """A stage's map: its road (the start a ring, the finish a square); the cars are drawn on it each frame."""
        c = _c()
        cv = s['canvas']
        w, h = max(cv.winfo_width(), 200), max(cv.winfo_height(), int(cv.cget('height')))
        k = self.root.winfo_fpixels('1i') / 96
        pad = round(18 * k)
        cv.delete('all')
        s['w'] = w
        s['to'] = to = tiles.fit(s['route'], (pad, pad, w - pad, h - pad))
        if to is None:
            cv.create_text(w / 2, h / 2, text='No map of this stage yet', fill=c.MUTED, font=(c.FONT, 9))
            return
        line = tiles.road(s['route'], (pad, pad, w - pad, h - pad))
        cv.create_line(*line, fill='#55555E', width=max(2, round(2.5 * k)), capstyle='round', joinstyle='round', smooth=True)
        r = round(4 * k)
        sx, sy, ex, ey = line[0], line[1], line[-2], line[-1]
        cv.create_oval(sx - r, sy - r, sx + r, sy + r, outline=c.GOOD, width=2)
        cv.create_rectangle(ex - r, ey - r, ex + r, ey + r, fill=c.WHITE, outline='')
        cv.create_text(sx, sy + r + 3, text='START', anchor='n', fill=c.MUTED, font=(c.FONT, 7, 'bold'))
        cv.create_text(ex, ey + r + 3, text='FINISH', anchor='n', fill=c.MUTED, font=(c.FONT, 7, 'bold'))
        self._live_draw_cars(s)

    # -------------------------------------------------------------- the drivers
    def _live_drivers(self, slot):
        a = (self._live_answer or {}).get(self.live_part)
        return [d for d in (a or {}).get('drivers') or [] if d.get('slot') == slot]

    def _live_server_now(self):
        """The server's clock now, as reckoned from its last answer (for the running clocks)."""
        a = (self._live_answer or {}).get(self.live_part)
        return a['now'] + (time.time() * 1000 - a['at']) if a and a.get('now') else None

    def _live_fill(self):
        """Each stage's list and count, from the last answer (or 'Loading…' before the first)."""
        c = _c()
        answer = (self._live_answer or {}).get(self.live_part)
        me = self.s.get('steamId')
        for slot, s in self._live_stages.items():
            for w in s['rows'].winfo_children():
                w.destroy()
            s['clocks'] = []
            drivers = live_order(self._live_drivers(slot))
            on = sum(1 for d in drivers if d.get('state') == 'live')
            s['count'].configure(text=('%d ON STAGE' % on) if on else 'NOBODY ON STAGE', bg=LIVE_COLOUR if on else c.PANEL2,
                                 fg=c.WHITE if on else c.MUTED)
            chosen = {str(d['steamId']): d['look']['color'] for d in drivers if (d.get('look') or {}).get('color')}
            s['colours'] = widgets.colours([d.get('steamId') for d in drivers], chosen)   # (the website's set)
            if answer is None:
                self._lbl(s['rows'], 'Loading…', fg=c.MUTED, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w')
                continue
            if not drivers:
                self._lbl(s['rows'], 'Nobody on this stage right now.', fg=c.MUTED, font=(c.FONT, 9), bg=c.PANEL).pack(anchor='w')
                continue
            n = 0
            for d in drivers[:ROWS]:
                mine = d.get('steamId') == me
                bg = c.ME_ROW if mine else c.PANEL
                row = tk.Frame(s['rows'], bg=bg, cursor='hand2')
                row.pack(fill='x', pady=(0, 1))
                live = d.get('state') == 'live'
                n += live
                pos = tk.Label(row, text=str(n) if live else '–', bg=bg, fg=c.MUTED, font=(c.FONT_C, 11), width=3, anchor='w')
                dot = tk.Label(row, text='●', bg=bg, fg=s['colours'].get(str(d.get('steamId')), c.FG2), font=(c.FONT, 9))
                name = tk.Label(row, text=tmtext.tagged(d), bg=bg, fg=c.ACC if mine else c.WHITE, font=(c.FONT, 10), anchor='w')
                clock = tk.Label(row, text='', bg=bg, fg=c.WHITE, font=('Segoe UI', 10), anchor='e', width=9)
                state = d.get('state')
                where = ('%d %%' % round(100 * (d.get('progress') or 0)) if live else
                         'FINISHED' if state == 'finished' else 'DNF')
                prog = tk.Label(row, text=where, bg=bg, font=(c.FONT_C, 10), width=9, anchor='e',
                                fg=c.FG2 if live else c.WHITE if state == 'finished' else c.BAD)
                pos.pack(side='left')
                dot.pack(side='left', padx=(0, 6))
                name.pack(side='left', fill='x', expand=True)
                clock.pack(side='right', padx=(6, 0))
                prog.pack(side='right')
                if state != 'dnf':
                    s['clocks'].append((clock, d))
                for w in (row, pos, dot, name, clock, prog):     # a driver: their page on the website
                    w.bind('<Button-1>', lambda _e, i=d.get('steamId'): self.open_page('/d/%s' % i))
            if len(drivers) > ROWS:
                self._lbl(s['rows'], '+%d more' % (len(drivers) - ROWS), fg=c.MUTED, font=(c.FONT, 8), bg=c.PANEL).pack(anchor='w')
        self._live_clocks()
        live_n = sum(1 for d in (answer or {}).get('drivers') or [] if d.get('state') == 'live')
        self.live_note.configure(text='' if answer is None else
                                 ('%d driver%s on stage' % (live_n, '' if live_n == 1 else 's')) if live_n else 'Nobody on stage right now')

    def _live_clocks(self):
        """Each listed driver's time: running on while they are on the stage."""
        now = self._live_server_now()
        for s in self._live_stages.values():
            for label, d in s['clocks']:
                text = fmt_clock(clock_ms(d, now), exact=d.get('state') == 'finished')
                if label.cget('text') != text:
                    label.configure(text=text)

    def _live_draw_cars(self, s):
        """The cars on a stage's map where the playback has them now: a dot in each driver's colour (their picture in it
        once downloaded), their name by it; my own ringed in white."""
        c = _c()
        cv, to = s['canvas'], s.get('to')
        cv.delete('car')
        if to is None:
            return
        pb = (self._live_pb or {}).get((self.live_part, self._slot_of(s)))
        if pb is None:
            return
        now = time.time() * 1000
        k = self.root.winfo_fpixels('1i') / 96
        me = self.s.get('steamId')
        for d in self._live_drivers(self._slot_of(s)):
            sid = str(d.get('steamId'))
            at = pb.at(sid, now)
            if at is None:
                continue
            pt = s['track'].at(at['p']) if s['track'].len else (d.get('x'), d.get('z'))
            if not pt or pt[0] is None:
                continue
            x, y = to(*pt)
            col = (s.get('colours') or {}).get(sid, c.FG2)
            r = round(6 * k)
            if at['state'] == 'dnf':
                cv.create_oval(x - r, y - r, x + r, y + r, outline=col, width=2, tags=('car',))
            else:
                before = set(cv.find_all())
                widgets.driver_dot(cv, x, y, col, d.get('avatar'), r=r, ring=c.WHITE if sid == me else None)
                for item in set(cv.find_all()) - before:
                    cv.addtag_withtag('car', item)
            name = tmtext.tagged(d)
            f = (c.FONT_C, 10)
            if x + r + 8 + tiles.font(cv, f).measure(name) > s.get('w', 0):       # (near the right edge: on the left)
                tx, anchor = x - r - 4, 'e'
            else:
                tx, anchor = x + r + 4, 'w'
            cv.create_text(tx + 1, y + 1, text=name, anchor=anchor, fill='#0E0E11', font=f, tags=('car',))
            cv.create_text(tx, y, text=name, anchor=anchor, fill=col, font=f, tags=('car',))

    def _slot_of(self, s):
        return next((slot for slot, x in self._live_stages.items() if x is s), None)

    def _live_frame(self):
        """10 times a second while the page is open: the cars, the clocks, the tab's dot."""
        self._live_frame_job = None
        if not self.live_view:
            return
        try:
            for s in self._live_stages.values():
                self._live_draw_cars(s)
            self._live_clocks()
            self._draw_live_dot()
            self._live_poll()
        except Exception:      # a drawing bug must never stop the app
            import traceback
            traceback.print_exc()
        self._live_frame_job = self.root.after(FRAME_MS, self._live_frame)

    # -------------------------------------------------------------- the requests
    def _live_every_ms(self):
        """How often to ask: every few seconds while someone is on a stage, less often while nobody is (as the website:
        min(livePollS, liveSendS / 2) and liveIdleS)."""
        busy = min(self.timing('livePollS'), max(1, -(-self.timing('liveSendS') // 2)))
        return 1000 * (busy if self._live_any else self.timing('liveIdleS'))

    def _live_poll(self, force=False):
        """The part shown, asked for when it is due (force: now), never while the window is minimised."""
        if not self.live_view or self._live_busy or not self.api.configured:
            return
        try:
            if self.root.state() == 'iconic':
                return
        except tk.TclError:
            return
        now = time.monotonic() * 1000
        if not force and now - self._live_polled < self._live_every_ms():
            return
        part = self.live_part
        if part == 'daily':
            date = next((d['ch'].get('date') for d in self.dailies.values() if d.get('ch', {}).get('date')), None)
            if not date:
                return
            ask = lambda: self.api.live_all(date)       # noqa: E731
        else:
            week = (getattr(self, 'tt_info', None) or {}).get('week')
            if not week or not (self.tt_info or {}).get('on'):
                return
            ask = lambda: self.api.tt_live_all(week)    # noqa: E731
        self._live_polled = now
        self._live_busy = True

        def go():
            try:
                r = ask()
                _c().ui(self.root, self._live_take, part, r)
            except ApiError:
                pass
            finally:
                self._live_busy = False
        threading.Thread(target=go, daemon=True).start()

    def _live_take(self, part, r):
        """An answer: kept for the part, fed to each stage's playback, the lists drawn again."""
        if not isinstance(r, dict):
            return
        drivers = r.get('drivers') or []
        now = time.time() * 1000
        self._live_answer = dict(self._live_answer or {})
        self._live_answer[part] = {'drivers': drivers, 'now': r.get('now') or now, 'at': now}
        if part == self.live_part:
            self._live_any = any(d.get('state') == 'live' for d in drivers)
        send = self.timing('liveSendS')
        busy = min(self.timing('livePollS'), max(1, -(-send // 2)))
        self._live_pb = dict(self._live_pb or {})
        for slot in {d.get('slot') for d in drivers} | set(self._live_stages):
            pb = self._live_pb.get((part, slot))
            if pb is None:
                pb = self._live_pb[(part, slot)] = glide.LivePlayback((send + busy + 1) * 1000, 3 * send * 1000)
            pb.feed([d for d in drivers if d.get('slot') == slot], r.get('now') or now, now)
        if self.live_view and part == self.live_part:
            if any(s.get('id') != ((self._live_held(part).get(slot) or {}).get('ch') or {}).get('id')
                   for slot, s in self._live_stages.items()) or not self._live_stages:
                self._render_live()                  # (new stages: a new day, a new week)
            else:
                self._live_fill()
