"""A 1V1 challenge made in the app (the 1V1 tab: CHALLENGE A DRIVER): who, where, which stages (or a few drawn at
random, never two on the same road), the car or a class, the conditions, how long it is open and the stake. The server
checks it as the website's form (src/h2h.js, POST /api/h2h); the rules are its defaults. A REMATCH of a 1V1 that is
over goes through the server too (POST /api/h2h/<id>/rematch, tabsui.py).
"""
import random
import re
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .api import ApiError

MAX_STAGES = 5                 # a 1V1 is short: up to five stages, all on day 1
GAP_MIN = 30                   # each stage starts this long after the one before (the game's clock)
TIMES = ('08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00')
WINDOWS = ((1, '1 day'), (2, '2 days'), (3, '3 days'), (7, 'a week'), (14, '2 weeks'))
ROAD = re.compile(r'^(.*?)(Full|Cut\d+)(Forward|Reverse)$')


def _c():
    from . import app
    return app


def road_of(stage):
    """A stage's place on the map from the game's id ('MonteCarloS1BolleneCut1Forward' -> ('MonteCarloS1Bollene',
    'Cut1')): its reverse is the same road, a full stage holds its cuts (as the server's cup draw, src/cups.js)."""
    m = ROAD.match(stage.get('stageId') or '')
    return (m.group(1), m.group(2)) if m else (stage.get('stageId') or stage.get('track'), 'Full')


def same_road(a, b):
    (x, xc), (y, yc) = road_of(a), road_of(b)
    return x == y and (xc == yc or 'Full' in (xc, yc))


def random_stages(stages, n, rng=random):
    """n of a rally's stages at random, never two on the same road (fewer when it hasn't the roads)."""
    pool = list(stages)
    rng.shuffle(pool)
    got = []
    for s in pool:
        if len(got) < n and not any(same_road(s, g) for g in got):
            got.append(s)
    return got


def stage_times(start, n):
    """The stages' start times: SS1 at `start` ('HH:MM'), each next GAP_MIN later, all on the same day (moved earlier
    when the last would start after 23:30)."""
    h, m = map(int, start.split(':'))
    t = max(0, min(h * 60 + m, 23 * 60 + 30 - GAP_MIN * (n - 1)))
    return ['%02d:%02d' % divmod(t + GAP_MIN * k, 60) for k in range(n)]


def challenge_event(rally, stages, weather, start, days, now_ms, car=None, car_class=None, name=''):
    """The event as the server takes it: open from now for `days`, one day of stages."""
    ev = {'rally': rally, 'opens': int(now_ms), 'closes': int(now_ms + days * 86400000),
          'stages': [{'track': s['track'], 'day': 1, 'weather': weather, 'time': t}
                     for s, t in zip(stages, stage_times(start, len(stages)))]}
    if car:
        ev['car'] = car
    else:
        ev['carClass'] = car_class
    if name.strip():
        ev['name'] = name.strip()
    return ev


class ChallengeDialog:
    """The window: built at once, filled when the catalog is in. app: the App (its api, credits, palette helpers);
    done(): called once a challenge has gone."""

    def __init__(self, app, done=None, opponent=None):
        c = _c()
        self.app, self.done, self.cat, self.opp, self.found = app, done, None, opponent, []
        self.win = w = tk.Toplevel(app.root)
        w.title('ACR Daily · Challenge a driver')
        w.configure(bg=c.BG)
        w.resizable(False, False)
        w.transient(app.root)
        try:
            w.geometry('+%d+%d' % (app.root.winfo_rootx() + 40, app.root.winfo_rooty() + 60))
        except tk.TclError:
            pass
        self.body = tk.Frame(w, bg=c.BG)
        self.body.pack(fill='both', expand=True, padx=20, pady=16)
        app._lbl(self.body, 'CHALLENGE A DRIVER', font=(c.FONT_C, 18), fg='#FF9F43').pack(anchor='w')
        app._lbl(self.body, 'A 1V1: you both drive it here, under 1V1, whenever you like while it is open. The lower '
                            'total wins (and takes both stakes).', font=(c.FONT, 8), fg=c.MUTED, wraplength=400).pack(anchor='w', pady=(2, 8))
        self.loading = app._lbl(self.body, 'Loading the stages…', fg=c.MUTED, font=(c.FONT, 9))
        self.loading.pack(anchor='w')
        threading.Thread(target=self._load, daemon=True).start()

    # -------------------------------------------------------------- data
    def _load(self):
        try:
            cat = self.app.api.catalog()
            _c().ui(self.app.root, self._fill, cat, '')
        except ApiError as e:
            _c().ui(self.app.root, self._fill, None, 'Not loaded: %s' % e)

    def _fill(self, cat, msg):
        if not self.win.winfo_exists():
            return
        if cat is None:
            self.loading.configure(text=msg, fg=_c().BAD)
            return
        self.loading.destroy()
        self.cat = cat
        self._build()

    # -------------------------------------------------------------- the form
    def _part(self, text):
        self.app._k(self.body, text).pack(anchor='w', pady=(10, 3))

    def _combo(self, parent, values, width=30):
        cb = ttk.Combobox(parent, values=values, state='readonly', width=width)
        return cb

    def _build(self):
        c, a, b = _c(), self.app, self.body
        # who
        self._part('Who')
        self.who = tk.Frame(b, bg=c.BG)
        self.who.pack(fill='x')
        self._who()
        # where, which stages
        self._part('Where')
        self.rallies = [r for r in self.cat.get('rallies') or [] if r.get('stages')]
        self.rally = self._combo(b, [r['name'] for r in self.rallies])
        self.rally.pack(anchor='w')
        self.rally.bind('<<ComboboxSelected>>', lambda _e: self._stages())
        top = tk.Frame(b, bg=c.BG)
        top.pack(fill='x', pady=(10, 3))
        a._k(top, 'Stages (1 to %d)' % MAX_STAGES).pack(side='left')
        self.random_b = a._link(top, 'Draw 2 at random', lambda: self.draw(2))
        self.random_b.pack(side='right')
        self.stage_l = tk.Listbox(b, selectmode='multiple', height=7, width=52, bg=c.PANEL, fg=c.SOFT, bd=0,
                                  highlightthickness=1, highlightbackground=c.LINE2, selectbackground=c.ACC,
                                  selectforeground=c.WHITE, activestyle='none', font=(c.FONT, 9), exportselection=False)
        self.stage_l.pack(anchor='w', fill='x')
        # the car
        self._part('Car')
        row = tk.Frame(b, bg=c.BG)
        row.pack(fill='x')
        self.car_mode = tk.StringVar(value='class')
        for v, t in (('class', 'A class (each picks a car of it)'), ('car', 'One car')):
            tk.Radiobutton(row, text=t, value=v, variable=self.car_mode, command=self._cars, bg=c.BG, fg=c.SOFT,
                           selectcolor=c.PANEL, activebackground=c.BG, activeforeground=c.WHITE, font=(c.FONT, 9),
                           highlightthickness=0, bd=0).pack(side='left', padx=(0, 12))
        self.car = self._combo(b, [], width=44)
        self.car.pack(anchor='w', pady=(4, 0))
        # the conditions, the window, the stake
        self._part('Weather · SS1 starts at · open for')
        row = tk.Frame(b, bg=c.BG)
        row.pack(fill='x')
        weathers = self.cat.get('weathers') or []
        self.weather_ids = [x['id'] for x in weathers]
        self.weather = self._combo(row, [x['label'] for x in weathers], width=16)
        self.weather.pack(side='left')
        self.start = self._combo(row, list(TIMES), width=6)
        self.start.pack(side='left', padx=(8, 0))
        self.window = self._combo(row, [t for _d, t in WINDOWS], width=8)
        self.window.pack(side='left', padx=(8, 0))
        cr = a.credits or {}
        self.stake = None
        if cr.get('enabled'):
            self._part('Stake each, in credits (0: a friendly)')
            row = tk.Frame(b, bg=c.BG)
            row.pack(fill='x')
            self.stake = tk.Spinbox(row, from_=0, to=1000, increment=10, width=6, bg=c.PANEL, fg=c.WHITE, bd=0,
                                    buttonbackground=c.PANEL2, insertbackground=c.WHITE, font=(c.FONT, 10),
                                    highlightthickness=1, highlightbackground=c.LINE2)
            self.stake.pack(side='left')
            a._lbl(row, '  You have %d.' % (cr.get('balance') or 0), fg=c.MUTED, font=(c.FONT, 9)).pack(side='left')
        self._part('Name (optional)')
        self.name = tk.Entry(b, width=44, bg=c.PANEL, fg=c.WHITE, insertbackground=c.WHITE, bd=0, font=(c.FONT, 10),
                             highlightthickness=1, highlightbackground=c.LINE2)
        self.name.pack(anchor='w', ipady=3)
        row = tk.Frame(b, bg=c.BG)
        row.pack(fill='x', pady=(16, 0))
        self.send_b = a._btn(row, 'SEND THE CHALLENGE', self.send, primary=True)
        self.send_b.pack(side='left')
        a._link(row, 'Cancel', self.win.destroy).pack(side='right')
        self.msg = a._lbl(b, '', fg=c.BAD, font=(c.FONT, 9), wraplength=400)
        self.msg.pack(anchor='w', pady=(8, 0))
        # defaults: the first rally, a class, clear at noon, open 2 days
        if self.rallies:
            self.rally.current(0)
        self.weather.current(self.weather_ids.index('Clear') if 'Clear' in self.weather_ids else 0)
        self.start.set('12:00')
        self.window.current(1)
        self._stages()
        self._cars()

    def _who(self):
        c, a = _c(), self.app
        for w in self.who.winfo_children():
            w.destroy()
        if self.opp:
            row = tk.Frame(self.who, bg=c.BG)
            row.pack(fill='x')
            a._lbl(row, self.opp['name'], font=(c.FONT_C, 14), fg=c.WHITE).pack(side='left')
            a._link(row, 'change', self._change).pack(side='left', padx=(10, 0))
            return
        row = tk.Frame(self.who, bg=c.BG)
        row.pack(fill='x')
        self.q = tk.Entry(row, width=30, bg=c.PANEL, fg=c.WHITE, insertbackground=c.WHITE, bd=0, font=(c.FONT, 10),
                          highlightthickness=1, highlightbackground=c.LINE2)
        self.q.pack(side='left', ipady=3)
        self.q.bind('<Return>', lambda _e: self.find())
        a._btn(row, 'FIND', self.find).pack(side='left', padx=(8, 0))
        for p in self.found[:6]:
            l = a._link(self.who, '%s%s' % (p['name'], ('  (%s)' % p['country'].upper()) if p.get('country') else ''),
                        lambda p=p: self._pick(p), fg=c.SOFT)
            l.pack(anchor='w', pady=(3, 0))

    def _change(self):
        self.opp, self.found = None, []
        self._who()

    def _pick(self, p):
        self.opp = p
        self._who()

    def find(self):
        q = self.q.get().strip()
        if len(q) < 2:
            self.msg.configure(text='Type 2 letters of their name at least.')
            return
        me = self.app.s.get('steamId')

        def go():
            try:
                found = [p for p in self.app.api.players(q) if p.get('steamId') != me]
                _c().ui(self.app.root, self._found, found, '' if found else 'Nobody by that name.')
            except ApiError as e:
                _c().ui(self.app.root, self._found, [], 'Not found: %s' % e)
        threading.Thread(target=go, daemon=True).start()

    def _found(self, found, msg):
        if not self.win.winfo_exists():
            return
        self.found = found
        self.msg.configure(text=msg)
        self._who()

    def _rally(self):
        i = self.rally.current()
        return self.rallies[i] if 0 <= i < len(self.rallies) else None

    def _stages(self):
        r = self._rally()
        self.stage_l.delete(0, 'end')
        for s in (r or {}).get('stages') or []:
            self.stage_l.insert('end', '%s · %.1f km' % (s['name'], (s.get('lengthM') or 0) / 1000))

    def draw(self, n):
        r = self._rally()
        if not r:
            return
        picks = random_stages(r['stages'], n)
        self.stage_l.selection_clear(0, 'end')
        for s in picks:
            self.stage_l.selection_set(r['stages'].index(s))

    def _cars(self):
        if self.car_mode.get() == 'car':
            self.car_values = [x['name'] for x in self.cat.get('cars') or []]
            self.car.configure(values=['%s · %s' % (x['name'], x['cls']) for x in self.cat.get('cars') or []])
        else:
            self.car_values = [k['cls'] for k in self.cat.get('classes') or []]
            self.car.configure(values=['%s (%s)' % (k['cls'], k['group']) for k in self.cat.get('classes') or []])
        if self.car_values:
            pref = 'Rally2/R5' if 'Rally2/R5' in self.car_values else None
            self.car.current(self.car_values.index(pref) if pref else 0)

    # -------------------------------------------------------------- sending
    def event(self, now_ms=None):
        """The event from the form, or a str: what is missing."""
        r = self._rally()
        if not r:
            return 'Pick where.'
        picked = [r['stages'][i] for i in self.stage_l.curselection()]
        if not picked:
            return 'Pick a stage (or draw some at random).'
        if len(picked) > MAX_STAGES:
            return 'Up to %d stages.' % MAX_STAGES
        k = self.car.current()
        if k < 0:
            return 'Pick the car.'
        car = self.car_values[k]
        days = WINDOWS[max(0, self.window.current())][0]
        return challenge_event(r['name'], picked, self.weather_ids[max(0, self.weather.current())], self.start.get() or '12:00',
                               days, now_ms if now_ms is not None else time.time() * 1000,
                               car=car if self.car_mode.get() == 'car' else None,
                               car_class=car if self.car_mode.get() == 'class' else None, name=self.name.get())

    def send(self):
        if not self.opp:
            self.msg.configure(text='Find who you challenge first.')
            return
        ev = self.event()
        if isinstance(ev, str):
            self.msg.configure(text=ev)
            return
        try:
            stake = int(self.stake.get()) if self.stake is not None else 0
        except ValueError:
            self.msg.configure(text='The stake: a whole number of credits, 0 for a friendly.')
            return
        ask = 'Challenge %s: %s, %d stage%s, open %s?' % (self.opp['name'], ev['rally'], len(ev['stages']),
                                                         '' if len(ev['stages']) == 1 else 's',
                                                         WINDOWS[max(0, self.window.current())][1])
        ask += ('\n\n%d credits each: yours is taken now (back if they decline or don\'t answer within a day).' % stake
                if stake else '\n\nA friendly: no credits.')
        if not messagebox.askyesno('ACR Daily', ask, parent=self.win):
            return
        opp = self.opp

        def go():
            try:
                self.app.api.h2h_challenge(opp['steamId'], stake, ev)
                _c().ui(self.app.root, self._sent, opp)
            except ApiError as e:
                _c().ui(self.app.root, self.msg.configure, {'text': 'Not sent: %s' % e})
        threading.Thread(target=go, daemon=True).start()

    def _sent(self, opp):
        self.app.sub_l.configure(text='Challenge sent to %s: they have a day to answer.' % opp['name'])
        if self.win.winfo_exists():
            self.win.destroy()
        if self.done:
            self.done()
