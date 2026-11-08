"""The app's TIME TRIAL tab and its part of the loop, mixed into App (app.py) like the LEAGUES view (leagueui.py).

The weekly time trial (server src/timetrial.js) is a hotlap mode: two stages a week, Monday 00:00 UTC to the next
Monday, each with its own car, conditions and board, driven as often as one likes; each driver's best time is the one
on the board. With credits on, a stage has an entry fee, paid before the first run on it (DRIVE asks), and once the
week is over the top half of the drivers with a time share the pot, more the higher they placed.

The tab shows the week's two stages as cards (the one picked has its board in the timing sheet): the entry, the pot,
my best and place, the time left. DRIVE sets the stage up in the game as a one-stage Rally Weekend, as for a daily, and
the frames are judged for it: each finished run waits for the game's official result in its save (app.py
_await_official, kind 'tt') and is sent with it; DNFs and restarts are not sent. The game keeps the set-up, so after a
run Rally Weekend › START RALLY drives the stage again, without DRIVE. While on the stage the app sends where it is (the
/tt page's live map, as the dailies'), and the stage strip display shows the other drivers on it.

The time trial's judges see every frame, unless the app follows a league event, or a daily has today the same stage and
car as a time trial stage (the server avoids it): then only the one DRIVE was last clicked for, so one run never counts
for both. The timer window, the split standings and the displays are the time trial's while one of its stages is
driven, waiting for its official time, on its start line, or just finished.
"""
import threading
import time
import tkinter as tk
from tkinter import messagebox

from . import autodrive, photos, rallyweekend, saveslot, settings, tiles, widgets
from .api import TOO_OLD, ApiError, refused
from .ghosts import GhostSet
from .judge import Judge, fmt_ms
from .leagueui import _left
from .standings import standing

TT_COLOUR = '#BF5AF2'          # the time trial's colour, as on the website (purple: the fastest sector)
TT_EVERY_MIN = 30              # the week's stages and pots, now and then (the boards: while the tab is open or driving)
SPLIT_SHOW_S = 8


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def parse_id(cid):
    """'tt:2026-11-09/2' -> 2 (the stage's slot), else None."""
    s = str(cid or '')
    if not s.startswith('tt:') or '/' not in s:
        return None
    tail = s.rsplit('/', 1)[1]
    return int(tail) if tail in ('1', '2') else None


def week_text(info, now_ms):
    """'WEEK 46  ·  CLOSES IN 3 d 4 h' (or CLOSED), '' without a week."""
    if not info or not info.get('on'):
        return ''
    no = (info.get('isoWeek') or {}).get('no')
    left = (info.get('endsAt') or 0) - now_ms
    return '  ·  '.join(x for x in ('WEEK %s' % no if no else 'THIS WEEK',
                                    'CLOSES IN %s' % _left(left).upper() if left > 0 else 'CLOSED') if x)


def stage_status(ch, board, me):
    """A stage's line on its card: (text, coin by its last number, colour key: 'good' / 'acc' / 'soft').
    My best and place once I have a time; else what entering costs and the pot, or that I'm in."""
    ch = ch or {}
    fee, mine_ch = ch.get('fee') or 0, ch.get('me') or {}
    entries = (board or {}).get('entries') or []
    mine = next((e for e in entries if me and e.get('steamId') == me), None)
    if mine:
        runs = mine.get('runs') or 1
        text = 'BEST %s  ·  P%d OF %d  ·  %d RUN%s' % (fmt_ms(mine['totalMs']), mine['rank'], len(entries), runs,
                                                     '' if runs == 1 else 'S')
        if mine.get('prize'):
            return text + '  ·  PRIZE %d' % mine['prize'], True, 'good'
        return text, False, 'good'
    if mine_ch.get('bestMs') is not None:                     # (the board not in yet)
        return 'BEST %s  ·  %d RUN%s' % (fmt_ms(mine_ch['bestMs']), mine_ch.get('runs') or 1,
                                       '' if (mine_ch.get('runs') or 1) == 1 else 'S'), False, 'good'
    if not fee:
        return 'FREE ENTRY  ·  NO TIME YET', False, 'soft'
    if mine_ch.get('entered'):
        return 'ENTERED  ·  NO TIME YET  ·  POT %d' % (ch.get('pot') or 0), True, 'good'
    return 'ENTRY %d  ·  %d IN  ·  POT %d' % (fee, ch.get('entrants') or 0, ch.get('pot') or 0), True, 'acc'


def result_text(slot, r):
    """What the server said of a run sent: a new best (by how much), its place, or that the best stands."""
    if not isinstance(r, dict):
        return 'TT%d: sent.' % slot
    place = ' P%s of %s.' % (r['rank'], r.get('drivers') or r['rank']) if r.get('rank') else ''
    prize = ' Prize now: %d credits.' % r['prize'] if r.get('prize') else ''
    if r.get('best') and r.get('improvedMs'):
        return 'TT%d: new best %s (−%.3f).%s%s' % (slot, fmt_ms(r['totalMs']), r['improvedMs'] / 1000, place, prize)
    if r.get('best'):
        return 'TT%d: %s, your first time.%s%s' % (slot, fmt_ms(r['totalMs']), place, prize)
    return 'TT%d: %s. Your best stays %s.%s' % (slot, fmt_ms(r.get('totalMs') or 0), fmt_ms(r.get('bestMs') or 0), place)


AGAIN = 'Go again: leave the results screen, then Rally Weekend › START RALLY.'


class TimeTrialUI:
    # what an App has before _tt_init gives it its own (the tests build bare ones: App.__new__)
    tt_view = False
    tt_info = None
    tt_sel = 1
    tt_active = None
    tt_msg = ''
    tt_box = None

    @property
    def tt(self):
        """slot -> {'ch', 'judge', 'board', 'ghosts', 'ghost_loading', 'ghost_for', 'ghost_name', 'known', 'counts',
        'entered', 'said'}: the week's stages."""
        return self.__dict__.setdefault('_tt', {})

    def _tt_init(self):
        self._tt = {}
        self.tt_view = False           # the window shows the TIME TRIAL tab (in the cards' place)
        self.tt_info = None            # /api/tt: the week (None: not in yet; on False: no time trial)
        self.tt_sel = 1                # the stage picked in the tab (its board in the timing sheet)
        self.tt_active = None          # the stage driven last (the timer window's while DRIVE was for the time trial)
        self.tt_msg = ''

    # -------------------------------------------------------------- which judges see the frames
    def _tt_clash(self):
        """A time trial stage with the same stage and car as one of today's dailies (one run would fit both)."""
        return any(t['ch'].get('track') == d['ch'].get('track') and t['ch'].get('car') == d['ch'].get('car')
                   for t in self.tt.values() for d in self.dailies.values() if d.get('ch'))

    def _dailies_judged(self):
        return self.drive_target == 'daily' or (self.drive_target == 'tt' and not self._tt_clash())

    def _tt_judged(self):
        return self.drive_target == 'tt' or (self.drive_target == 'daily' and not self._tt_clash())

    def _tt_running(self):
        return any(t.get('judge') and t['judge'].state == 'running' for t in self.tt.values())

    def _tt_waiting(self, slot, started=None):
        """Is a run of this stage waiting for the game's official time (that run's, with `started`)?"""
        return any(a.get('kind') == 'tt' and a['slot'] == slot and (started is None or a['result'].get('startedAt') == started)
                   for a in self.awaiting)

    def _tt_entered(self, slot):
        t = self.tt.get(slot) or {}
        ch = t.get('ch') or {}
        return not ch.get('fee') or bool((ch.get('me') or {}).get('entered')) or bool(t.get('entered'))

    # -------------------------------------------------------------- the tab
    def _build_tt_box(self):
        c = _c()
        self.tt_box = tk.Frame(getattr(self, '_main', self.root), bg=c.BG)   # (in the view, on the right)

    def toggle_tt_view(self, on):
        """The TIME TRIAL tab on (in the place of the dailies or the events), or back to the dailies."""
        if on == self.tt_view and not self._page_on() and not (on and self.league_view):
            return
        self._pages_leave()                        # (a page open: the inbox, the settings, LIVE make way: app.py)
        if self.league_view:                       # (the events view gives way: tabsui.py)
            self.league_view = False
            self.league_box.pack_forget()
        self.tt_view = on
        self._mark_tabs()
        if on:
            self.daily_box.pack_forget()
            self.tt_box.pack(fill='x', before=self._view_end)
            self._render_tt()
            self.refresh_tt()
        else:
            self.tt_box.pack_forget()
            self.daily_box.pack(fill='x', before=self._view_end)
        self._render_strip()
        self._show_board_title()
        self._fill_tree()

    def _tt_leave(self):
        """Another view takes the tab's place (it packs its own cards)."""
        if self.tt_view:
            self.tt_view = False
            if self.tt_box is not None:
                self.tt_box.pack_forget()

    def tt_select(self, slot):
        if slot in self.tt and slot != self.tt_sel:
            self.tt_sel = slot
            self._render_tt()
            self._show_board_title()
            self._fill_tree()

    def _render_tt(self):
        if self.tt_box is None or not self.tt_view:
            return
        c = _c()
        box = self.tt_box
        for w in box.winfo_children():
            w.destroy()
        info = self.tt_info
        if info is None or not info.get('on'):
            if info is None:
                text = self.tt_msg or 'Loading the time trial…'
            elif info.get('startsAt'):
                text = 'The time trial starts %s.' % time.strftime('%A %d %B', time.gmtime(info['startsAt'] / 1000))
            else:
                text = 'There is no time trial on this server.'
            self._lbl(box, text, fg=c.SOFT, font=(c.FONT, 10), wraplength=800).pack(anchor='w', padx=20, pady=(16, 14))
            self._rule(box, padx=20)
            return
        head = tk.Frame(box, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(0, 0))
        self._lbl(head, week_text(info, time.time() * 1000), font=(c.FONT, 8, 'bold'), fg=TT_COLOUR).pack(side='left')
        self._link(head, 'On the website  ›', lambda: self.open_page('/tt')).pack(side='right')
        rule = 'Drive as often as you like this week: your best time counts.'
        if info.get('credits') and info.get('fee'):
            rule += ' Entry %d a stage; the top half share the pot.' % info['fee']
        if not self.s.get('token'):
            rule += ' Sign in with Steam (on the left) to put your times on the board.'
        self._lbl(box, rule, fg=c.MUTED, font=(c.FONT, 8), wraplength=800).pack(anchor='w', padx=20, pady=(2, 6))
        if not self.tt:
            self._lbl(box, 'No stages this week.', fg=c.SOFT, font=(c.FONT, 10)).pack(anchor='w', padx=20, pady=(10, 12))
        row = tk.Frame(box, bg=c.BG)                  # the week's stages side by side, as tall as each other
        row.pack(fill='x')
        self._tt_row = tiles.TileRow(row, max(2, len(self.tt)), base=self._card_base())
        for slot in sorted(self.tt):
            self._tt_card(row, slot)
        self._tt_row.even()

    def _tt_card(self, box, slot):
        """A stage of the week, a card as the dailies' (tiles.py): red while it is the one picked (a click picks it), its
        standing in the strip under it (the entry, the pot, my best and place)."""
        c = _c()
        t = self.tt[slot]
        ch = t['ch']
        j = t.get('judge')
        tile = self._tt_row.add(tiles.Tile(box, on_click=lambda s=slot: self.tt_select(s), restyle=self._btn_style))
        tile.button = self._btn(tile.cv, 'DRIVE  ›', lambda s=slot: self.tt_drive(s), primary=True)
        km = '%.1f KM' % (ch['lengthM'] / 1000) if ch.get('lengthM') else ''
        tile.render({'active': slot == self.tt_sel, 'lock': ('TT%d' % slot, (ch.get('rally') or '').upper()),
                     'photo': photos.for_rally(ch.get('rally')), 'bottom': True,
                     'chips': [x for x in (km, (ch.get('surface') or '').upper()) if x], 'title': c.stage_name(ch).upper(),
                     'lines': [(ch.get('car', '') + ('  ·  %s' % ch['carClass'] if ch.get('carClass') else ''), 'sub'),
                               (c.conditions(ch), 'info'),
                               ('' if j else 'No route for this stage yet: check back later.', 'muted')],
                     'road': j.route.points if j else ch.get('route')})
        text, coin, colour = stage_status(ch, t.get('board'), self.s.get('steamId'))
        tile.strip().configure(text=text, fg={'good': c.GOOD, 'acc': c.ACC}.get(colour, c.SOFT),
                               image=(self.coin_img or '') if coin else '')
        tile.strip().pack(fill='x')

    def _fill_tt_tree(self):
        c = _c()
        me = self.s.get('steamId')
        t = self.tt.get(self.tt_sel) or {}
        b = t.get('board')
        entries = (b or {}).get('entries', [])[:50]
        for e in entries:
            pen = c.penalty_s(e)
            tag = 'me' if e.get('steamId') == me else 'p1' if e.get('rank') == 1 else ''
            self.tree.insert('', 'end', values=(e['rank'], c.shown_name(e), fmt_ms(e['totalMs']), '+%d' % pen if pen > 0 else ''),
                             tags=(tag,))
        if not entries:
            self.tree.insert('', 'end', values=('', 'No times yet' if b is not None or not t else 'Loading…', '', ''))

    def _tt_board_title(self):
        return 'BEST TIMES  TT%d' % self.tt_sel

    # -------------------------------------------------------------- data
    def refresh_tt(self, full=False):
        """(any thread) The week's stages, the pots and my entries; the routes only when a stage is new."""
        if not self.api.configured:
            return
        lite = bool(self.tt) and not full and all(t.get('judge') for t in self.tt.values())

        def go():
            try:
                r = self.api.time_trial(lite=lite)
                _c().ui(self.root, self._set_tt, r, '', lite)
            except ApiError as e:
                _c().ui(self.root, self._set_tt, None, 'Time trial: %s' % e)
        threading.Thread(target=go, daemon=True).start()

    def _set_tt(self, info, msg, lite=False):
        self.tt_msg = msg
        if info is not None:
            stages = (info.get('stages') or []) if info.get('on') else []
            if lite and any(not ch.get('route') and (self.tt.get(ch.get('slot')) or {}).get('ch', {}).get('id') != ch.get('id')
                            for ch in stages):
                self.refresh_tt(full=True)          # a new week: its routes (the lite answer has none)
                return
            for ch in stages:
                slot = ch.get('slot')
                t = self.tt.get(slot)
                if t and t['ch'].get('id') == ch.get('id'):
                    t['ch'].update({k: v for k, v in ch.items() if k != 'route'})
                    continue
                if t and t.get('judge') and t['judge'].state == 'running':
                    self.root.after(5000, lambda: self._set_tt(info, msg, lite))   # never swap a stage mid-run
                    return
                judge = Judge(ch) if ch.get('route') else None
                self.tt[slot] = {'ch': ch, 'judge': judge, 'board': None, 'ghost_for': None, 'ghost_name': None,
                                 'ghosts': GhostSet(judge.route, 0) if judge else None, 'ghost_loading': set()}
            for slot in list(self.tt):
                j = self.tt[slot].get('judge')
                if slot not in {ch.get('slot') for ch in stages} and not (j and j.state == 'running'):
                    del self.tt[slot]
            if self.tt_sel not in self.tt and self.tt:
                self.tt_sel = min(self.tt)
            self.tt_info = info
            if self.tt_view or self.drive_target == 'tt' or any(t.get('board') is None for t in self.tt.values()):
                self.refresh_tt_board()
        if self.tt_view:
            self._render_tt()
            self._show_board_title()
            self._fill_tree()

    def _tt_week_over(self):
        """The week shown has closed (Monday 00:00 UTC): time for the new one."""
        info = self.tt_info or {}
        return bool(info.get('on') and info.get('endsAt') and info['endsAt'] <= time.time() * 1000)

    def refresh_tt_board(self):
        if not self.api.configured:
            return
        for slot, t in list(self.tt.items()):
            def go(slot=slot, week=t['ch'].get('week')):
                try:
                    b = self.api.tt_board(week, slot)
                    _c().ui(self.root, self._set_tt_board, slot, week, b)
                except ApiError:
                    pass
            threading.Thread(target=go, daemon=True).start()

    def _set_tt_board(self, slot, week, b):
        t = self.tt.get(slot)
        if not t or t['ch'].get('week') != week:
            return
        t['board'] = b
        if self.tt_view:
            self._render_tt()
            if slot == self.tt_sel:
                self._fill_tree()
        entries = [e for e in (b or {}).get('entries', []) if e.get('totalMs') is not None]
        me = self.s.get('steamId')
        gs = t.get('ghosts')
        if gs is not None:                        # the displays' ghosts: the top runs and my best
            for e in entries[:6] + [e for e in entries if e.get('steamId') == me]:
                rid = e['runId']
                if rid in gs.runs or rid in t['ghost_loading']:
                    continue
                t['ghost_loading'].add(rid)

                def load(rid=rid, name=e['name']):
                    try:
                        tr = self.api.tt_trace(rid)
                        _c().ui(self.root, gs.add, rid, name, tr.get('trace'))
                    except ApiError:
                        pass
                    finally:
                        t['ghost_loading'].discard(rid)
                threading.Thread(target=load, daemon=True).start()
        target = entries[0] if entries else None      # the live gap: against the leader (my own best when it's me)
        if target and t.get('judge') and target['runId'] != t['ghost_for']:
            t['ghost_for'] = target['runId']

            def go():
                try:
                    tr = self.api.tt_trace(target['runId'])
                    _c().ui(self.root, self._set_tt_ghost, slot, tr, target)
                except ApiError:
                    t['ghost_for'] = None
            threading.Thread(target=go, daemon=True).start()

    def _set_tt_ghost(self, slot, tr, target):
        t = self.tt.get(slot)
        if t and t.get('judge') and tr and tr.get('trace'):
            t['judge'].set_ghost(tr['trace'])
            t['ghost_name'] = 'your best' if target.get('steamId') == self.s.get('steamId') else _c().shown_name(target)

    # -------------------------------------------------------------- DRIVE
    def tt_drive(self, slot, confirm=True):
        """Enter (asked, credits on) and set the stage up in the game's save, then start the game on it."""
        t = self.tt.get(slot)
        if not t or getattr(self, '_restarting', False):
            return
        ch = t['ch']
        if self._drive_wait:
            self.sub_l.configure(text=self._drive_wait)
            return
        run = self.league_run
        if self._tt_running() or any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or \
                (run and not run.get('over') and run['judge'].state == 'running'):
            messagebox.showinfo('ACR Daily', 'Finish or leave the stage you are on first.')
            return
        if self._waiting_text():
            messagebox.showinfo('ACR Daily', self._waiting_text())
            return
        if not t.get('judge'):
            messagebox.showinfo('ACR Daily', 'TT%d has no route yet: check back later.' % slot)
            return
        if (self.tt_info or {}).get('endsAt') and self.tt_info['endsAt'] <= time.time() * 1000:
            messagebox.showinfo('ACR Daily', 'This week\'s time trial is over. The new one is on its way.')
            self.refresh_tt(full=True)
            return
        told = self._league_before_daily(True)     # a league stage or rally in progress (leagueui.py)
        if told is None:
            return
        c = _c()
        if saveslot.game_running() and confirm and not told and not messagebox.askyesno(
                'ACR Daily', 'The game is running. ACR Daily will restart it with TT%d (%s · %s · %s).\n\nGo?'
                             % (slot, c.stage_name(ch), ch.get('car'), c.conditions(ch))):
            return
        if self._tt_entry_first(slot, lambda: self._tt_drive_go(slot)):
            self._tt_drive_go(slot)

    def _tt_drive_go(self, slot):
        if saveslot.game_running():
            self._close_game_then('TT%d' % slot, lambda: self._tt_setup_and_launch(slot))
        else:
            self._tt_setup_and_launch(slot)

    def _tt_setup_and_launch(self, slot):
        t = self.tt.get(slot)
        if not t:
            return
        ch = t['ch']
        if not self._league_park_for_daily():    # a league rally (or the player's own) in the game: set aside first
            return
        c = _c()
        try:
            rallyweekend.write_daily(ch)
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', '%s\n\nSet it up by hand as a one-stage Rally Weekend: %s · %s · %s'
                                   % (e, ch.get('track'), ch.get('car'), c.conditions(ch)))
            return
        self.drive_target = 'tt'                   # the game's frames are judged for the time trial
        self.tt_active = slot
        if self.tt_sel != slot:
            self.tt_select(slot)
        path = ('In the game: Racing › Rally › Rally Weekend › START RALLY › J › CONFIRM › Start Stage. After each run, '
                'leave the results screen (the game saves its time) and START RALLY again for another go.')
        self.sub_l.configure(text='Starting the game... ' + path)
        try:
            saveslot.launch_game()
        except OSError:
            self.sub_l.configure(text='TT%d set up. Start the game from Steam. ' % slot + path)
        if self.s.get('autoDrive'):
            if getattr(self, 'auto', None):
                self.auto.cancel()
            self.auto = autodrive.AutoDrive(lambda x: c.ui(self.root, self.sub_l.configure, {'text': x}), 'weekend').start()

    def _tt_entry_first(self, slot, then):
        """DRIVE on a stage with an entry fee not entered yet: the entry asked for first (it is paid before the first
        run). -> True to go on with DRIVE now; else DRIVE stops here, or then() once the entry is in."""
        t = self.tt.get(slot) or {}
        ch = t.get('ch') or {}
        fee = ch.get('fee') or 0
        if not fee or self._tt_entered(slot) or not self.api.configured:
            return True
        if not self.s.get('token'):
            messagebox.showinfo('ACR Daily', 'TT%d has an entry fee of %d credits. Sign in with Steam first.' % (slot, fee))
            return False
        cr = self.credits or {}
        if cr.get('signedIn') and cr.get('balance') is not None and cr['balance'] < fee:
            messagebox.showinfo('ACR Daily', 'TT%d\'s entry fee is %d credits and you have %d.\n\nYou get more each day, '
                                             'and for finishing SS1.' % (slot, fee, cr['balance']))
            return False
        ends = (self.tt_info or {}).get('endsAt')
        until = time.strftime('%a %d %b, %H:%M UTC', time.gmtime(ends / 1000)) if ends else 'the end of the week'
        bal = ' You have %d.' % cr['balance'] if cr.get('balance') is not None else ''
        if not messagebox.askyesno('ACR Daily', 'Enter TT%d (%s) for %d credits?%s\n\nDrive it as often as you like until '
                                                '%s: your best time counts. The top half of the drivers with a time share '
                                                'the pot, more the higher they place. Set no time and the fee comes back.'
                                   % (slot, _c().stage_name(ch), fee, bal, until)):
            return False
        self._drive_wait = 'Entering TT%d... DRIVE goes on once the entry is in.' % slot
        self.sub_l.configure(text=self._drive_wait)
        week = ch.get('week')

        def go():
            try:
                r = self.api.tt_enter(slot, week)
            except Exception as e:                 # (an ApiError; anything else must not leave DRIVE waiting either)
                _c().ui(self.root, self._tt_entry_failed, slot, e)
                return
            _c().ui(self.root, self._tt_entered_now, slot, r, then)
        threading.Thread(target=go, daemon=True).start()
        return False

    def _tt_entered_now(self, slot, r, then):
        self._drive_wait = None
        t = self.tt.get(slot)
        if t:
            t['entered'] = True
            t['ch'].setdefault('me', {})['entered'] = True
        self.refresh_credits()
        self.refresh_tt()
        self._render_tt()
        left = ' (%s credits left)' % r['balance'] if isinstance(r, dict) and r.get('balance') is not None else ''
        self._drive_resume(then, 'You are in TT%d%s.' % (slot, left))

    def _tt_entry_failed(self, slot, e):
        self._drive_wait = None
        self.refresh_credits()
        code = getattr(e, 'code', None)
        if code is None or code >= 500:
            text = ('No answer from the server (%s). The entry may have gone through: TT%d will say ENTERED if it did.'
                    '\n\nClick DRIVE again.' % (e, slot))
            self.refresh_tt()
        else:
            text = 'Not entered: %s' % e
        messagebox.showwarning('ACR Daily', text)

    # -------------------------------------------------------------- the loop
    def _tt_tick(self, f, unloaded):
        """Every frame: the time trial's judges (unless the frames are another's: _tt_judged)."""
        if not self.tt or not self._tt_judged():
            return
        c = _c()
        for slot, t in list(self.tt.items()):
            j = t.get('judge')
            if not j:
                continue
            for ev in j.feed(f, unloaded):
                if ev == 'start':
                    t['known'] = self._game_results()  # the game's result of this run will be a new one
                    t['counts'] = self._tt_entered(slot)
                    t['said'] = None
                    t['accounts'] = {c.steam_account()}
                    self.tt_active = slot
                    if self.tt_view and self.tt_sel != slot:
                        self.tt_select(slot)
                    self._clear_standing()
                    self._tt_send_live(slot, j, f, 'live')
                elif ev == 'split':
                    n = len(j.splits)
                    self._tt_standing(slot, 'SPLIT %d / %d' % (n, len(j.split_at)), j.splits[-1], n - 1, hold=SPLIT_SHOW_S)
                elif ev == 'finished':
                    if not t.get('counts', True):
                        self.sub_l.configure(text='TT%d: not counted. %s' % (slot, 'Click its DRIVE to enter first.' if self.s.get('token')
                                                                              else 'Sign in with Steam, then click its DRIVE to enter.'))
                        continue
                    accounts = (t.get('accounts') or set()) | {c.steam_account()}
                    result = dict(j.result, gameSteamIds=sorted(a for a in accounts if a), country=self.country)
                    self._await_official(slot, result, t.get('known'), kind='tt')
                    self._tt_standing(slot, 'FINISH (provisional)', j.result['totalMs'], None, hold=None)
                    self._tt_send_live(slot, j, f, 'finished')
                elif ev in ('dnf', 'invalid'):
                    self._clear_standing()
                    self._tt_send_live(slot, j, f, 'dnf')
                    self.sub_l.configure(text='TT%d: %s (%s). Not sent: only finished runs count. %s'
                                         % (slot, ev.upper(), (j.result or {}).get('reason') or '', AGAIN))
            if j.state == 'running' and time.monotonic() - t.get('live_at', -1e9) >= self.timing('liveSendS'):
                self._tt_send_live(slot, j, f, 'live')

    def _tt_send_live(self, slot, j, f, state):
        """Our position on a time trial stage for its live map (every liveSendS while on it, and at the start, finish or
        DNF), as for a daily (app._send_live). Not for a run that doesn't count (not entered), nor signed out. With the
        stage strip display on, the answer brings the other drivers on the stage too."""
        t = self.tt.get(slot) or {}
        t['live_at'] = time.monotonic()
        if not self.s.get('token') or not self.api.configured or f is None or not t.get('counts', True):
            return
        others = self._others_shown()
        body = {'challengeId': j.ch.get('id'), 'x': round(f.x, 1), 'z': round(f.z, 1), 'progress': round(j.progress, 4),
                'totalMs': j.total_ms, 'state': state, 'others': others}

        def go():
            r = self.api.tt_live(body)
            if others and r and isinstance(r.get('drivers'), list):
                self._tt_take_live(t, r['drivers'])
        threading.Thread(target=go, daemon=True).start()

    def _tt_take_live(self, t, drivers):
        """Who is on a time trial stage now (our own position's answer, or _tt_poll_live): for the displays."""
        chosen = {str(x.get('steamId')): x['look']['color'] for x in drivers if (x.get('look') or {}).get('color')}
        t['live_colours'] = widgets.colours([x.get('steamId') for x in drivers], chosen)
        t['live'] = [x for x in drivers if x.get('steamId') != self.s.get('steamId')]

    def _tt_poll_live(self):
        """(app.poll_live, every second) While the timer window is a time trial stage's: who else is on it, for the
        stage strip (as often as for a daily: livePollS on the stage, liveIdleS elsewhere; while driving signed in they
        come back with our own position). -> True when the time trial took the turn (the dailies' are not asked)."""
        slot = self._tt_focus(getattr(self, 'last_frame', None)) if self.tt else None
        if slot is None:
            return False
        t = self.tt[slot]
        j = t.get('judge')
        if not self._others_shown() or not self.api.configured or t.get('live_busy') or \
                (j and j.state == 'running' and self.s.get('token') and t.get('counts', True)):
            return True
        every = self.timing('livePollS') if j and j.state != 'waiting' else self.timing('liveIdleS')
        if time.monotonic() - t.get('live_polled', -1e9) < every:
            return True
        t['live_polled'], t['live_busy'] = time.monotonic(), True
        week = t['ch'].get('week')

        def go():
            try:
                self._tt_take_live(t, (self.api.tt_live_now(week, slot) or {}).get('drivers') or [])
            except ApiError:
                pass
            finally:
                t['live_busy'] = False
        threading.Thread(target=go, daemon=True).start()
        return True

    def _tt_standing(self, slot, title, my_ms, split, hold):
        """Where this run stands on the time trial's board, under the timer (a split, the finish)."""
        entries = ((self.tt.get(slot) or {}).get('board') or {}).get('entries', [])
        self.overlay.show_standing(title, standing(entries, self.s.get('steamId'), my_ms, split), pb_label='vs your best')
        self.panel_until = time.monotonic() + hold if hold else 0
        self.panel_slot = ('tt', slot)

    def on_tt_result(self, result):
        """A time trial run with the game's official time (or a DNF without it): sent, or queued for later."""
        settings.append_result(result)
        slot = parse_id(result.get('challengeId')) or 1
        if result.get('status') != 'finished':     # (no official time from the game after all: nothing to send)
            self.sub_l.configure(text='TT%d: not sent (%s). %s' % (slot, result.get('reason') or 'DNF', AGAIN))
            return
        if not self.api.configured:
            return
        if not self.s.get('token'):
            from . import __version__
            self.api._queue(dict(result, appVersion=__version__))
            self.sub_l.configure(text='Sign in with Steam to put this run on the time trial board.')
            return
        c = _c()

        def go():
            said = None
            try:
                r = self.api.submit(result)
                msg = result_text(slot, r)
                if isinstance(r, dict) and r.get('rank'):
                    said = ('NEW BEST · ' if r.get('best') else 'BEST STAYS · ') + 'P%s OF %s' % (r['rank'], r.get('drivers') or r['rank'])
                msg += ' ' + AGAIN
            except ApiError as e:
                if e.code == TOO_OLD:
                    msg = 'Not on the board: %s' % e
                    self.check_update()
                elif refused(e):
                    msg = 'Not counted: %s' % e
                    said = 'NOT COUNTED'
                else:
                    msg = 'Not sent yet (%s) - will retry.' % e
            c.ui(self.root, self._tt_said, slot, result.get('startedAt'), said, msg)
        threading.Thread(target=go, daemon=True).start()

    def _tt_said(self, slot, started, said, msg):
        t = self.tt.get(slot)
        if t and said and t.get('judge') and (t['judge'].result or {}).get('startedAt') == started:
            t['said'] = said
        self.sub_l.configure(text=msg)
        self.refresh_tt_board()

    # -------------------------------------------------------------- what the timer window and the displays show
    def _tt_focus(self, f):
        """The time trial stage the timer window is for now, or None (the dailies'): one driven, waiting for its
        official time, ready on its start line, or just finished with the game still on it; after DRIVE on the time
        trial, the one driven last, unless a daily's stage is loaded."""
        if not self.tt or not self._tt_judged():
            return None
        for slot, t in self.tt.items():
            j = t.get('judge')
            if j and (j.state == 'running' or (j.state == 'finished' and self._tt_waiting(slot, (j.result or {}).get('startedAt')))):
                return slot
        for slot, t in self.tt.items():
            j = t.get('judge')
            if j and (j.state == 'armed' or j.approaching):
                return slot
            if j and f is not None and f.track and j.state in ('finished', 'dnf', 'invalid') and j._right(f):
                return slot
        if self.drive_target == 'tt':
            for d in self.dailies.values():
                dj = d.get('judge')
                if dj and (dj.state in ('running', 'armed') or dj.approaching):
                    return None
            slot = self.tt_active if self.tt_active in self.tt else self.tt_sel
            return slot if slot in self.tt else None
        return None

    def _tt_allowed(self, f):
        """The in-game displays with 'only on the daily' on: a time trial stage being driven, waiting, or loaded."""
        if not self.tt or not self._tt_judged():
            return False
        for slot, t in self.tt.items():
            j = t.get('judge')
            if j and (j.state == 'running' or j.approaching or self._tt_waiting(slot) or (f is not None and f.track and j._right(f))):
                return True
        return False

    def _tt_overlay_state(self, f):
        """(status, sub-line, overlay args) while the timer window is the time trial's, else None."""
        slot = self._tt_focus(f)
        if slot is None:
            return None
        c = _c()
        t = self.tt[slot]
        j, ch = t.get('judge'), t['ch']
        stage = 'TT%d · %s' % (slot, c.stage_name(ch, short=True).upper())
        if not j:
            return 'TT%d has no route yet' % slot, '', ('offline', stage, 0, 0, 'No route for this stage yet', c.MUTED)
        signed = bool(self.s.get('token'))
        if j.state == 'running':
            gap = j.gap_ms
            if j.paused:
                line, lc = 'PAUSED · the run carries on with the clock', c.SOFT
            elif gap is not None:
                line = 'vs %s  %s%.2f' % (t.get('ghost_name') or 'P1', '+' if gap >= 0 else '−', abs(gap) / 1000)
                lc = c.SLOW if gap > 0 else c.GOOD
            else:
                line, lc = 'Time trial · %d%%' % round(j.progress * 100), c.SOFT
            if not t.get('counts', True):
                line, lc = 'NOT ENTERED · this run does not count', c.BAD
            elif not signed:
                line += '   · not signed in'
            return j.message, '', ('live', stage, j.total_ms, j.resets, line, lc)
        if j.state == 'finished':
            if not t.get('counts', True):
                return j.message, '', ('finished', stage, j.total_ms, j.resets, 'Not counted: enter TT%d first (DRIVE)' % slot, c.BAD)
            if self._tt_waiting(slot, (j.result or {}).get('startedAt')):
                return j.message, '', ('finished', stage, j.total_ms, j.resets, 'Official time next: go on from the results screen', c.SOFT)
            return j.message, '', ('finished', stage, j.total_ms, j.resets,
                                   t.get('said') or ('Sending...' if signed else 'Sign in to submit'), c.ACC)
        if j.state in ('dnf', 'invalid'):
            r = j.result or {}
            return j.message, '', (j.state, stage, r.get('clockMs', 0), r.get('resets', 0),
                                   '%s · not sent' % (r.get('reason') or j.state).capitalize(), c.BAD)
        if j.state == 'armed':
            if not self._tt_entered(slot):
                return j.message, '', ('ready', stage, 0, 0, 'NOT ENTERED · click DRIVE on TT%d to enter' % slot, c.BAD)
            best = (ch.get('me') or {}).get('bestMs')
            mine = next((e for e in (t.get('board') or {}).get('entries', []) if e.get('steamId') == self.s.get('steamId')), None)
            best = mine['totalMs'] if mine else best
            line = ('Your best %s · ' % fmt_ms(best) if best else 'Time trial · ') + 'goes LIVE with the stage clock'
            return j.message, '', ('ready', stage, 0, 0, line, c.SOFT)
        if f is None:
            return 'Waiting for Assetto Corsa Rally', '', ('standby', 'TIME TRIAL · TT%d' % slot, 0, 0, 'Waiting for the game', c.MUTED)
        if j.approaching:
            return j.message, '', ('standby', stage, 0, 0, 'Drive up to the start line', c.SOFT)
        return (j.message, '', ('standby', stage, 0, 0, 'TT%d: Rally Weekend › START RALLY' % slot, c.MUTED))

    def _tt_widget_view(self, f):
        """What the optional displays show while the timer window is the time trial's (its ghosts: the leader, the
        driver just ahead, my best), else None (app._render_widgets)."""
        slot = self._tt_focus(f)
        if slot is None:
            return None
        t = self.tt[slot]
        j, gs = t.get('judge'), t.get('ghosts')
        running = bool(j and j.state == 'running')
        my_idx = j._max_idx if running else 0
        my_total = j.total_ms if running else 0
        entries = [e for e in (t.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
        me = self.s.get('steamId')
        me_run = next((e['runId'] for e in entries if e.get('steamId') == me), None)
        p1_run = entries[0]['runId'] if entries else None
        picked = gs.pick(my_idx, my_total, me_run, p1_run) if gs else []
        cols, c = t.get('live_colours') or {}, _c()
        live_now = [x for x in t.get('live') or [] if x.get('state') == 'live']
        return {'slot': slot, 'label': 'TT%d' % slot, 'running': running, 'splits': j.split_at if j else [],
                'progress': j.progress if running else (0.0 if j else None),
                'ghosts': [(lab, kind, g.progress_at(my_total), gap if running else None) for lab, kind, g, gap in picked],
                'gap_p1': j.gap_ms if running else None, 'p1_name': t.get('ghost_name'),
                'others_prog': [(c.shown_name(x), cols.get(str(x.get('steamId')), widgets.FG2), x.get('progress') or 0.0,
                                 x.get('avatar')) for x in live_now]}

    def _tt_footer(self):
        """The footer's closing time while the tab is open: '   ·   time trial closes in 3 d 4 h', else ''."""
        info = self.tt_info or {}
        if not self.tt_view or not info.get('on') or not info.get('endsAt'):
            return ''
        left = info['endsAt'] - time.time() * 1000
        return '   ·   time trial closes in %s' % _left(left) if left > 0 else '   ·   time trial closed'

