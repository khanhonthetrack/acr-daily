"""ACR Daily desktop app: main window + the timer window that sits over the game's own timer."""
import ctypes
import datetime as dt
import json
import os
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from . import __version__, settings
from .api import TOO_OLD, Api, ApiError
from .judge import Judge, fmt_ms
from . import nextcard, saveslot, updater, widgets
from .ghosts import GhostSet
from .names import norm, same_car, same_track
from .recorder import RouteRecorder
from .standings import standing
from .telemetry import ReplaySource, SharedMemory, steam_account

# Assetto Corsa Rally look: black and white, ACR red as the accent (and for LIVE), green = faster / ready,
# orange = slower
# (same palette as the website: black ground, hairlines instead of boxes, red only where it matters)
BG, PANEL, PANEL2, LINE, LINE2 = '#0A0A0B', '#121214', '#1C1C20', '#1F1F23', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC, GOOD, BAD, LIVE = '#E30613', '#30D158', '#FF453A', '#E10600'
SLOW = '#FF9F0A'   # slower than the reference, and time lost to penalties
STEAM_BG, STEAM_HOVER = '#171A21', '#2A475E'   # Steam's own colours, for the sign-in button
YEL = ACC
FONT = 'Bahnschrift'
FONT_C = 'Bahnschrift SemiBold Condensed'   # WRC-style condensed figures (ships with Windows 10/11)

# overlay status badge: text, background, text colour
STATUS = {
    'offline': ('OFFLINE', PANEL2, MUTED),
    'standby': ('STANDBY', PANEL2, SOFT),
    'ready': ('READY', GOOD, '#0A0A0C'),
    'live': ('● LIVE', LIVE, WHITE),
    'rec': ('● REC', LIVE, WHITE),
    'finished': ('FINISHED', WHITE, '#0A0A0C'),
    'dnf': ('DNF', BAD, WHITE),
    'invalid': ('INVALID', '#FF8A00', '#0A0A0C'),
}
TICK_MS = 50
SPLIT_SHOW_S = 8      # how long the split standings stay on the timer window
NEXT_CARD_AFTER_MS = 5000   # the next-daily card shows this long after a run ends
LIVE_EVERY_S = 1      # how often our position goes to the website's live map while on stage
LIVE_POLL_MS = 1000   # how often the overlays fetch the other drivers' positions
COND_TOL_K = 3.0     # air at the start this far from the other drivers' = the game's time / weather differ
WIN_W, WIN_H = 440, 820   # main window at first start; then as tall as its contents need (and as the user left it)
TIMING_ROWS = 7           # the timing sheet always has room for this many drivers


def conditions(ch):
    """'Light rain · Afternoon (16:00)': the weather and time of day the daily is driven in."""
    return ' · '.join(x for x in ((ch or {}).get('weatherLabel'), (ch or {}).get('timeLabel')) if x)


def stage_name(ch, short=False):
    """The daily's stage as the game's menu names it ('Peïra Cava - La Bollène-Vésubie'), or its short name
    ('Peïra Cava', for the timer window). Servers before menu names only send the short one."""
    ch = ch or {}
    return (ch.get('stageName') if short else ch.get('menuName') or ch.get('stageName')) or ch.get('track') or ''


def ui(widget, fn, *a):
    """Run fn on the Tk thread."""
    widget.after(0, lambda: fn(*a))


def work_area():
    """(left, top, right, bottom) of the main screen without the taskbar, or None."""
    try:
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
            return r.left, r.top, r.right, r.bottom
    except (AttributeError, OSError):
        pass
    return None


def on_screen(x, y):
    """Is the window's top-left corner on one of the screens (they may have been unplugged since)?"""
    try:
        m = ctypes.windll.user32.GetSystemMetrics      # the virtual screen: every monitor together
        left, top, w, h = m(76), m(77), m(78), m(79)
        return left <= x < left + w - 100 and top <= y < top + h - 100
    except (AttributeError, OSError):
        return x >= 0 and y >= 0


# ---------------------------------------------------------------------- timer window

class Overlay:
    """Borderless always-on-top timer. Drag it over the game's timer once; then lock it (click-through)."""

    def __init__(self, app):
        self.app = app
        o = app.s['overlay']
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.94)
        self.win.configure(bg=BG)
        self.scale = float(o.get('scale') or 1.0)
        self.status = None
        self._blink = False
        # header strip: status badge + what is going on (always visible)
        head_row = tk.Frame(self.win, bg=PANEL)
        head_row.pack(fill='x')
        self.badge = tk.Label(head_row, text='STANDBY', bg=PANEL2, fg=SOFT, padx=8)
        self.badge.pack(side='left', fill='y')
        self.title = tk.Label(head_row, text='ACR DAILY', bg=PANEL, fg=SOFT, anchor='w', padx=8)
        self.title.pack(side='left', fill='x', expand=True)
        tk.Frame(self.win, bg=ACC, height=2).pack(fill='x')       # ACR red rule
        body = tk.Frame(self.win, bg=BG)
        body.pack(fill='both', expand=True, padx=(12, 12), pady=(2, 8))
        self.bar = body   # kept for the drag bindings below
        row = tk.Frame(body, bg=BG)
        row.pack(anchor='w')
        self.time = tk.Label(row, text='0:00.00', fg=WHITE, bg=BG)
        self.time.pack(side='left')
        self.pen = tk.Label(row, text='', fg='#0A0A0C', bg=SLOW, padx=6)   # shown only after a reset
        self.line = tk.Label(body, text='', fg=MUTED, bg=BG, anchor='w')
        self.line.pack(anchor='w', fill='x')
        self._head = (head_row, self.badge, self.title)
        # split / finish standings (RallySimFans style): shown for a few seconds after each split
        self.panel = tk.Frame(body, bg=BG)
        tk.Frame(self.panel, bg=LINE, height=2).pack(fill='x', pady=(6, 4))
        head = tk.Frame(self.panel, bg=BG)
        head.pack(fill='x')
        self.p_title = tk.Label(head, text='', fg=MUTED, bg=BG, anchor='w')
        self.p_title.pack(side='left')
        self.p_pos = tk.Label(head, text='', fg=WHITE, bg=BG, anchor='e')
        self.p_pos.pack(side='right')
        grid = tk.Frame(self.panel, bg=BG)
        grid.pack(fill='x', pady=(2, 0))
        grid.columnconfigure(1, weight=1)
        self.p_rows = []
        for i in range(4):
            cells = (tk.Label(grid, bg=BG, fg=MUTED, anchor='e', width=3),
                     tk.Label(grid, bg=BG, fg=SOFT, anchor='w'),
                     tk.Label(grid, bg=BG, fg=SOFT, anchor='e'))
            for c, w in enumerate(cells):
                w.grid(row=i, column=c, sticky='ew', padx=(0, 8) if c < 2 else 0)
            self.p_rows.append(cells)
        self.p_pb = tk.Label(self.panel, text='', fg=MUTED, bg=BG, anchor='w')
        self.p_pb.pack(anchor='w', fill='x', pady=(2, 0))
        self._fonts()
        self.win.geometry('+%d+%d' % (int(o.get('x', 60)), int(o.get('y', 60))))
        for w in (self.win, body, row, self.time, self.line, self.pen) + self._head:
            w.bind('<ButtonPress-1>', self._press)
            w.bind('<B1-Motion>', self._drag)
            w.bind('<ButtonRelease-1>', self._release)
            w.bind('<Button-3>', self._menu)
        self.win.update_idletasks()
        self.set_locked(bool(o.get('locked')))
        if not o.get('visible', True):
            self.win.withdraw()

    def _fonts(self):
        s = self.scale
        self.badge.configure(font=(FONT_C, int(12 * s)))
        self.title.configure(font=(FONT_C, int(12 * s)))
        self.time.configure(font=(FONT_C, int(40 * s)))
        self.pen.configure(font=(FONT_C, int(16 * s)))
        self.line.configure(font=(FONT_C, int(13 * s)), wraplength=int(300 * s), justify='left')
        self.win.minsize(int(300 * s), 1)    # same width in every state, so it never jumps around
        self.p_title.configure(font=(FONT_C, int(12 * s)))
        self.p_pos.configure(font=(FONT_C, int(17 * s)))
        for pos, name, gap in self.p_rows:
            pos.configure(font=(FONT_C, int(13 * s)))
            name.configure(font=(FONT_C, int(13 * s)))
            gap.configure(font=(FONT_C, int(13 * s)))
        self.p_pb.configure(font=(FONT_C, int(11 * s)))

    def _press(self, e):
        self._off = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag(self, e):
        if not self.app.s['overlay'].get('locked'):
            self.win.geometry('+%d+%d' % (e.x_root - self._off[0], e.y_root - self._off[1]))

    def _release(self, _e):
        o = self.app.s['overlay']
        o['x'], o['y'] = self.win.winfo_x(), self.win.winfo_y()
        settings.save(self.app.s)

    def _menu(self, e):
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label='Bigger', command=lambda: self.resize(1.15))
        m.add_command(label='Smaller', command=lambda: self.resize(1 / 1.15))
        m.add_command(label='Lock (click-through)', command=lambda: self.app.set_locked(True))
        m.add_command(label='Hide', command=lambda: self.app.toggle_overlay(False))
        m.tk_popup(e.x_root, e.y_root)

    def resize(self, k):
        self.scale = max(0.6, min(3.0, self.scale * k))
        self.app.s['overlay']['scale'] = round(self.scale, 2)
        settings.save(self.app.s)
        self._fonts()

    def set_locked(self, locked):
        """Locked = clicks go through to the game (WS_EX_TRANSPARENT | WS_EX_LAYERED)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            GWL_EXSTYLE, LAYERED, TRANSPARENT, NOACTIVATE = -20, 0x80000, 0x20, 0x08000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | LAYERED | NOACTIVATE
            style = style | TRANSPARENT if locked else style & ~TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass
        self.win.configure(highlightthickness=0 if locked else 2, highlightbackground=YEL)

    def show_standing(self, title, st):
        """st: standings.standing(...) result, or None to hide the panel."""
        if st is None:
            if self.panel.winfo_ismapped():
                self.panel.pack_forget()
            return
        self.p_title.configure(text=title)
        self.p_pos.configure(text='P%d / %d' % (st['pos'], st['of']), fg=ACC if st['pos'] == 1 else WHITE)
        for i, (pos, name, gap) in enumerate(self.p_rows):
            if i < len(st['rows']):
                p, n, g, me = st['rows'][i]
                pos.configure(text=str(p), fg=ACC if me else MUTED)
                name.configure(text=n[:22], fg=ACC if me else SOFT, font=(FONT_C if me else FONT_C, int(13 * self.scale)))
                gap.configure(text='' if p == 1 else '+%.3f' % (g / 1000), fg=ACC if me else SOFT)
            else:
                for w in (pos, name, gap):
                    w.configure(text='')
        pb = st.get('pbGap')
        self.p_pb.configure(text='' if pb is None else 'vs your best today  %s%.3f' % ('+' if pb >= 0 else '−', abs(pb) / 1000),
                            fg=SLOW if pb is not None and pb > 0 else GOOD if pb is not None else MUTED)
        if not self.panel.winfo_ismapped():
            self.panel.pack(anchor='w', fill='x')

    def show(self, on):
        if on:
            self.win.deiconify()
            self.win.attributes('-topmost', True)
        else:
            self.win.withdraw()

    def render(self, status, title, total_ms, resets, line, line_color=MUTED):
        """status: a key of STATUS (badge), title: header text, then the big time and the line under it."""
        text, bg, fg = STATUS[status]
        if status in ('live', 'rec'):          # the red dot blinks while recording
            self._blink = (time.monotonic() % 1.0) < 0.6
            text = text if self._blink else text.replace('●', '○')
        if (self.badge.cget('text'), self.badge.cget('bg')) != (text, bg):
            self.badge.configure(text=text, bg=bg, fg=fg)
        if self.title.cget('text') != title:
            self.title.configure(text=title)
        exact = status in ('finished', 'dnf', 'invalid')
        t = fmt_ms(total_ms, 3 if exact else 2) if total_ms else '0:00.00'
        if self.time.cget('text') != t:
            self.time.configure(text=t)
        tc = MUTED if status in ('offline', 'standby') else WHITE
        if self.time.cget('fg') != tc:
            self.time.configure(fg=tc)
        pen = '+%d s' % (resets * self.app.penalty_s()) if resets else ''
        if self.pen.cget('text') != pen:
            self.pen.configure(text=pen)
            if pen:
                self.pen.pack(side='left', padx=(10, 0))
            else:
                self.pen.pack_forget()
        if self.line.cget('text') != line or self.line.cget('fg') != line_color:
            self.line.configure(text=line, fg=line_color)
        self.win.attributes('-topmost', True)


# ---------------------------------------------------------------------- main window

class App:
    def __init__(self):
        self.s = settings.load()
        self.api = Api(self.s)
        replay = os.environ.get('ACR_DAILY_REPLAY')
        self.shm = ReplaySource(replay, float(os.environ.get('ACR_DAILY_REPLAY_FROM') or 0)) if replay else SharedMemory()
        # the day's dailies, by slot: {'ch': challenge, 'judge': Judge, 'board': leaderboard, 'ghost_for', 'ghost_name'}
        self.dailies = {}
        self._offered = set()    # dailies (ids, so per day) the next-daily card has already offered
        self.next_card = None
        self.active = 1          # the daily on screen: the one being driven, or the one whose stage is loaded
        self.live_at = 0.0       # last live-position update sent
        self.recorder = None
        self.auto_rec = RouteRecorder()   # always on: new stages get their route from your first clean run
        self.country = saveslot.driver_country()   # nationality from the in-game driver profile (flag on the website)
        self.known_routes = None          # normalised names of stages that already have a route (None = unknown)
        self.net_msg = ''
        self.last_frame = None

        self.root = tk.Tk()
        self.root.title('ACR Daily')
        self.root.configure(bg=BG)
        self.root.geometry('%dx%d' % (WIN_W, WIN_H))
        self.root.minsize(400, 700)
        try:
            self.root.iconbitmap(os.path.join(os.path.dirname(__file__), 'icon.ico'))
        except tk.TclError:
            pass
        self._ov_allowed = True   # overlays allowed on screen right now (see _overlays_allowed)
        self._style()
        self._build()
        self._place_window()
        self.overlay = Overlay(self)
        self.widgets = {k: cls(self, k) for k, cls in widgets.CLASSES.items()}   # optional displays
        self._widget_buttons()
        if not self.s.get('introSeen'):
            self._show_intro()
        self._wtick = 0
        self.root.protocol('WM_DELETE_WINDOW', self.quit)

        self.update_msg = ''
        self.update_info = None    # {'version', 'url'} when the server has a newer app
        self.update_busy = ''      # bar text while downloading / installing
        self._pending_update = None
        threading.Thread(target=updater.cleanup_old, daemon=True).start()
        self.panel_until = 0
        self.week_txt = ''
        self.refresh_challenge()
        self.refresh_routes()
        self.refresh_week()
        threading.Thread(target=self.check_update, daemon=True).start()
        self.root.after(TICK_MS, self.tick)
        self.root.after(60000, self.periodic)
        self.root.after(3000, self.poll_live)

    # the active daily
    @property
    def challenge(self):
        return self.dailies.get(self.active, {}).get('ch')

    @property
    def judge(self):
        return self.dailies.get(self.active, {}).get('judge')

    @property
    def board(self):
        return self.dailies.get(self.active, {}).get('board')

    @property
    def ghost_name(self):
        return self.dailies.get(self.active, {}).get('ghost_name') or '#1'

    def _pick_active(self, f):
        """The daily being driven; otherwise the one whose stage and car are loaded; otherwise keep."""
        for slot, d in self.dailies.items():
            if d.get('judge') and d['judge'].state == 'running':
                return slot
        if f is not None and f.track:
            for slot, d in self.dailies.items():
                if same_track(f.track, d['ch']) and same_car(f.car, d['ch']):
                    return slot
        return self.active if self.active in self.dailies else min(self.dailies or {1: None})

    # -------------------------------------------------------------- layout

    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use('clam')
        # Segoe UI: its digits are all the same width, so the times line up like a timing sheet
        st.configure('Treeview', background=BG, fieldbackground=BG, foreground=SOFT, rowheight=30,
                     font=('Segoe UI', 10), borderwidth=0, relief='flat')
        st.configure('Treeview.Heading', background=BG, foreground=MUTED, font=(FONT, 8, 'bold'),
                     relief='flat', borderwidth=0, padding=(0, 6))
        st.map('Treeview.Heading', background=[('active', BG)])
        st.map('Treeview', background=[('selected', PANEL)], foreground=[('selected', WHITE)])
        st.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])   # no frame around the sheet

    def _lbl(self, parent, text='', size=11, fg=SOFT, bold=False, **kw):
        font = kw.pop('font', (FONT, size, 'bold' if bold else 'normal'))
        return tk.Label(parent, text=text, bg=kw.pop('bg', BG), fg=fg, font=font, anchor='w', justify='left', **kw)

    def _k(self, parent, text):
        """A small spaced-out uppercase label (like the website's)."""
        return tk.Label(parent, text=' '.join(text.upper()), bg=BG, fg=MUTED, font=(FONT, 7, 'bold'), anchor='w')

    def _rule(self, parent=None, pady=0):
        f = tk.Frame(parent or self.root, bg=LINE, height=1)
        f.pack(fill='x', padx=0 if parent else 20, pady=pady)
        return f

    def _link(self, parent, text, cmd, fg=FG2):
        """Text that acts as a button: quiet until hovered."""
        l = tk.Label(parent, text=text, bg=BG, fg=fg, font=(FONT, 9), cursor='hand2')
        l.bind('<Button-1>', lambda _e: cmd())
        l.bind('<Enter>', lambda _e: l.configure(fg=WHITE))
        l.bind('<Leave>', lambda _e: l.configure(fg=l._fg))
        l._fg = fg
        return l

    def _btn(self, parent, text, cmd, primary=False):
        """Drive button: red block when it's the stage on screen, a hairline outline otherwise."""
        b = tk.Label(parent, text=text, font=(FONT_C, 11), padx=12, pady=4, cursor='hand2')
        b.bind('<Button-1>', lambda _e: cmd())
        b.bind('<Enter>', lambda _e: b.configure(bg=WHITE, fg=BG))
        b.bind('<Leave>', lambda _e: self._btn_style(b, b._primary))
        self._btn_style(b, primary)
        return b

    @staticmethod
    def _btn_style(b, primary):
        b._primary = primary
        b.configure(bg=ACC if primary else BG, fg=WHITE if primary else SOFT,
                    highlightthickness=0 if primary else 1, highlightbackground=LINE2)

    def _build(self):
        r = self.root
        # ---- header
        head = tk.Frame(r, bg=BG)
        head.pack(fill='x', padx=20, pady=(16, 14))
        self._logo_img = self._logo()
        if self._logo_img:
            tk.Label(head, image=self._logo_img, bg=BG, bd=0).pack(side='left')
        else:
            self._lbl(head, 'ACR DAILY', font=(FONT_C, 15), fg=WHITE).pack(side='left')
        self.date_l = self._lbl(head, '', fg=FG2, font=(FONT_C, 11))
        self.date_l.pack(side='right')
        discord = self._link(head, 'DISCORD', self.open_discord)   # chat, ideas and bug reports
        discord.configure(font=(FONT_C, 11))
        discord.pack(side='right', padx=(0, 18))
        self._head_rule = self._rule()
        # ---- a new version: one red bar, one click (shown only when there is one)
        self.upd = tk.Label(r, text='', bg=ACC, fg=WHITE, font=(FONT_C, 12), pady=9, cursor='hand2')
        self.upd.bind('<Button-1>', lambda _e: self.do_update())

        # ---- today's two special stages; the active one (driven / loaded) gets the red bar
        self.cards = {}
        for slot in (1, 2):
            row = tk.Frame(r, bg=BG)
            row.pack(fill='x', padx=(17, 20))
            bar = tk.Frame(row, bg=BG, width=3)
            bar.pack(side='left', fill='y', padx=(0, 14))
            body = tk.Frame(row, bg=BG)
            body.pack(side='left', fill='x', expand=True, pady=(14, 14))
            top = tk.Frame(body, bg=BG)
            top.pack(fill='x')
            ss = self._lbl(top, 'SS%d' % slot, font=(FONT_C, 11), fg=MUTED)
            ss.pack(side='left')
            where = self._lbl(top, '', font=(FONT, 8, 'bold'), fg=MUTED)
            where.pack(side='left', padx=(10, 0))
            drive = self._btn(top, 'DRIVE  ›', lambda s=slot: self.drive_click(s), primary=True)
            drive.pack(side='right')
            name = self._lbl(body, 'Loading…', font=(FONT_C, 24), fg=WHITE)
            name.pack(anchor='w', pady=(2, 0))
            car = self._lbl(body, '', fg=SOFT, font=(FONT, 10))
            car.pack(anchor='w')
            cond = self._lbl(body, '', fg=FG2, font=(FONT, 9))
            cond.pack(anchor='w')
            self.cards[slot] = {'bar': bar, 'ss': ss, 'where': where, 'name': name, 'car': car, 'cond': cond, 'drive': drive}
            self._rule()

        # ---- status: dot + state + what to do
        st = tk.Frame(r, bg=BG)
        st.pack(fill='x', padx=20, pady=(12, 12))
        line = tk.Frame(st, bg=BG)
        line.pack(fill='x')
        self.dot = tk.Label(line, text='●', bg=BG, fg=MUTED, font=(FONT, 9))
        self.dot.pack(side='left')
        self.state_l = self._lbl(line, 'STANDBY', font=(FONT_C, 11), fg=MUTED)
        self.state_l.pack(side='left', padx=(6, 10))
        self.status_l = self._lbl(line, '', fg=SOFT, font=(FONT, 10))
        self.status_l.pack(side='left', fill='x', expand=True)
        self.sub_l = self._lbl(st, '', fg=MUTED, font=(FONT, 9), wraplength=400)
        self.sub_l.pack(anchor='w', pady=(4, 0))
        self._rule()

        # ---- bottom rows first, so the timing sheet (which expands) never squeezes them out
        self.foot_l = self._lbl(r, '', fg=MUTED, font=(FONT, 8))
        self.foot_l.pack(side='bottom', anchor='w', padx=20, pady=(0, 12))
        if self.s.get('admin'):
            adm = tk.Frame(r, bg=BG)
            adm.pack(side='bottom', fill='x', padx=20, pady=(0, 6))
            self._link(adm, 'Record route', self.record_click, fg=ACC).pack(side='left')
            self._link(adm, 'Upload route', self.upload_click, fg=ACC).pack(side='left', padx=12)
            self.adm_l = self._lbl(adm, 'Admin', fg=MUTED, font=(FONT, 8), wraplength=220)
            self.adm_l.pack(side='left')
        # optional in-game displays (each one on / off)
        # optional in-game displays: a 2 x 2 grid of chips, solid red = on, outline = off
        disp = tk.Frame(r, bg=BG)
        disp.pack(side='bottom', fill='x', padx=20, pady=(8, 0))
        self._k(disp, 'In-game displays').grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.only_b = self._link(disp, '', self.toggle_only_daily)
        self.only_b.grid(row=0, column=1, sticky='e', pady=(0, 6))
        disp.columnconfigure(0, weight=1, uniform='d')
        disp.columnconfigure(1, weight=1, uniform='d')
        self.widget_links = {}
        for i, key in enumerate(widgets.CLASSES):
            b = tk.Label(disp, font=(FONT_C, 10), anchor='w', padx=10, pady=5, cursor='hand2', highlightthickness=1)
            b.bind('<Button-1>', lambda _e, k=key: self.toggle_widget(k))
            b.bind('<Enter>', lambda _e, b=b: b.configure(highlightbackground=WHITE))
            b.bind('<Leave>', lambda _e, b=b: b.configure(highlightbackground=b._edge))
            b.grid(row=1 + i // 2, column=i % 2, sticky='ew', padx=(0, 6) if i % 2 == 0 else 0, pady=(0, 6))
            self.widget_links[key] = b
        self.next_b = self._link(disp, '', self.toggle_offer_next)   # the next-daily card after a run (nextcard.py)
        self.next_b.grid(row=2 + (len(widgets.CLASSES) - 1) // 2, column=0, columnspan=2, sticky='w', pady=(2, 0))
        links = tk.Frame(r, bg=BG)
        links.pack(side='bottom', fill='x', padx=20, pady=(10, 6))
        self.lock_b = self._link(links, '', lambda: self.set_locked(not self.s['overlay'].get('locked')))
        self.lock_b.pack(side='left')
        self.vis_b = self._link(links, '', lambda: self.toggle_overlay(not self.s['overlay'].get('visible', True)))
        self.vis_b.pack(side='left', padx=14)
        self._link(links, 'Website', self.open_site).pack(side='right')
        self._link(links, 'How to play', self.open_guide).pack(side='right', padx=(0, 14))
        self._link(links, 'Restore save', self.restore_click).pack(side='right', padx=14)
        acct = tk.Frame(r, bg=BG)
        acct.pack(side='bottom', fill='x', padx=20, pady=(10, 0))
        self.acct_l = self._lbl(acct, '', fg=FG2, font=(FONT, 9))
        self.acct_l.pack(side='left')
        self.acct_b = self._link(acct, 'Sign out', self.login_click, fg=FG2)
        # signed out: a Steam-coloured button with the Steam logo (Steam is a trademark of Valve Corporation)
        self._steam_img = self._steam_logo()
        self.steam_b = tk.Label(acct, text=' SIGN IN WITH STEAM', image=self._steam_img or '', compound='left',
                                bg=STEAM_BG, fg=WHITE, font=(FONT_C, 10), padx=10, pady=5, cursor='hand2')
        self.steam_b.bind('<Button-1>', lambda _e: self.login_click())
        self.steam_b.bind('<Enter>', lambda _e: self.steam_b.configure(bg=STEAM_HOVER))
        self.steam_b.bind('<Leave>', lambda _e: self.steam_b.configure(bg=STEAM_BG))
        tk.Frame(r, bg=LINE, height=1).pack(side='bottom', fill='x', padx=20)

        # ---- timing sheet of the active stage (the live commentary is on the website only)
        self.board_l = self._k(r, 'Timing')
        self.board_l.pack(anchor='w', padx=20, pady=(14, 2))
        cols = ('pos', 'driver', 'time', 'pen')
        self.tree = ttk.Treeview(r, columns=cols, show='headings', height=TIMING_ROWS, selectmode='none')
        for c, w, a in (('pos', 40, 'w'), ('driver', 220, 'w'), ('time', 90, 'e'), ('pen', 44, 'e')):
            self.tree.heading(c, text=c.upper(), anchor=a)
            self.tree.column(c, width=w, anchor=a, stretch=c == 'driver')
        self.tree.tag_configure('p1', foreground=WHITE)
        self.tree.tag_configure('me', foreground=ACC)
        self.tree.pack(fill='both', expand=True, padx=20, pady=(0, 4))
        self._account_ui()
        self._overlay_buttons()

    # -------------------------------------------------------------- actions

    def penalty_s(self):
        return int((self.challenge or {}).get('penaltyMs', 60000) / 1000)

    def login_click(self):
        if self.s.get('token'):
            self.api.logout()
            self._account_ui()
            return
        if not self.api.configured:
            messagebox.showinfo('ACR Daily', 'No server is set yet. See SETUP.md.')
            return
        self.steam_b.configure(text=' WAITING FOR STEAM...')

        def done(ok, info):
            ui(self.root, self._account_ui)
            if ok:
                ui(self.root, self.refresh_board)
                threading.Thread(target=self.api.flush, daemon=True).start()
            else:
                ui(self.root, messagebox.showwarning, 'ACR Daily', info)
        self.api.login(done)

    def _account_ui(self):
        if self.s.get('token'):
            self.acct_l.configure(text=self.s.get('name') or 'Signed in', fg=SOFT)
            self.steam_b.pack_forget()
            self.acct_b.pack(side='right')
        else:
            self.acct_l.configure(text='Not signed in · runs wait until you are', fg=MUTED)
            self.acct_b.pack_forget()
            self.steam_b.configure(text=' SIGN IN WITH STEAM')
            self.steam_b.pack(side='right')

    def _logo(self):
        """The ACR Daily logo at the screen's scale (acr_daily/logo-<px>.png, made by make_icon.py)."""
        scale = self.root.winfo_fpixels('1i') / 96
        px = 48 if scale < 1.25 else 72 if scale < 1.75 else 96
        try:
            return tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), 'logo-%d.png' % px))
        except tk.TclError:
            return None

    def _steam_logo(self):
        """The Steam mark at the screen's scale (acr_daily/steam-<px>.png, made by make_steam_logo.py)."""
        scale = self.root.winfo_fpixels('1i') / 96
        px = 18 if scale < 1.25 else 27 if scale < 1.75 else 36
        try:
            return tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), 'steam-%d.png' % px))
        except tk.TclError:
            return None

    def open_guide(self):
        if self.api.configured:
            webbrowser.open(self.api.base + '/guide')

    def open_discord(self):
        """The ACR Daily Discord: the server sends /discord on to the current invite."""
        if self.api.configured:
            webbrowser.open(self.api.base + '/discord')

    def _show_intro(self):
        """First start: four steps above the timing sheet, until 'Got it'."""
        box = tk.Frame(self.root, bg=PANEL, highlightthickness=1, highlightbackground=LINE2)
        box.pack(fill='x', padx=20, pady=(14, 0), before=self.board_l)
        self.board_l.pack_forget()   # it takes the timing sheet's place until 'Got it' (no times to show yet anyway)
        self.tree.pack_forget()
        bar = tk.Frame(box, bg=PANEL)    # title + buttons on top, so they show even on a short screen
        bar.pack(fill='x', padx=14, pady=(10, 6))
        tk.Label(bar, text='G E T T I N G   S T A R T E D', bg=PANEL, fg=ACC, font=(FONT, 7, 'bold'),
                 anchor='w').pack(side='left')
        steps = ('Sign in with Steam (button below).',
                 'Click DRIVE: it sets everything up and starts the game (restarting it if it is open).',
                 'Racing › Rally › Single Rally Stage › Start Race › Start Stage.',
                 'Drag the timer over the game\'s, Lock overlays, drive. First run counts.')
        for i, t in enumerate(steps, 1):
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill='x', padx=14, pady=(0, 10 if i == len(steps) else 1))
            tk.Label(row, text='%02d' % i, bg=PANEL, fg=ACC, font=(FONT_C, 10), width=3, anchor='nw').pack(side='left', anchor='n')
            tk.Label(row, text=t, bg=PANEL, fg=SOFT, font=(FONT, 9), anchor='w', justify='left',
                     wraplength=350).pack(side='left', fill='x')

        def done():
            self.s['introSeen'] = True
            settings.save(self.s)
            self.board_l.pack(anchor='w', padx=20, pady=(14, 2), after=box)
            self.tree.pack(fill='both', expand=True, padx=20, pady=(0, 4), after=self.board_l)
            box.destroy()
        ok = tk.Label(bar, text='GOT IT', bg=ACC, fg=WHITE, font=(FONT_C, 10), padx=10, pady=2, cursor='hand2')
        ok.bind('<Button-1>', lambda _e: done())
        ok.pack(side='right')
        g = tk.Label(bar, text='Full guide ›', bg=PANEL, fg=FG2, font=(FONT, 9), cursor='hand2')
        g.bind('<Button-1>', lambda _e: self.open_guide())
        g.bind('<Enter>', lambda _e: g.configure(fg=WHITE))
        g.bind('<Leave>', lambda _e: g.configure(fg=FG2))
        g.pack(side='right', padx=12)

    def save_settings(self):
        settings.save(self.s)

    def set_locked(self, locked):
        self.s['overlay']['locked'] = locked
        settings.save(self.s)
        self.overlay.set_locked(locked)
        for w in getattr(self, 'widgets', {}).values():
            w.set_locked(locked)
        self._overlay_buttons()

    def toggle_widget(self, key):
        w = self.widgets[key]
        w.cfg['visible'] = not w.cfg.get('visible')
        settings.save(self.s)
        w.show(w.cfg['visible'] and self._ov_allowed)
        self._widget_buttons()

    def toggle_offer_next(self):
        o = self.s['overlay']
        o['offerNext'] = not o.get('offerNext', True)
        settings.save(self.s)
        self._overlay_buttons()
        if not o['offerNext'] and getattr(self, 'next_card', None):
            self.next_card.close()

    def toggle_only_daily(self):
        o = self.s['overlay']
        o['onlyOnDaily'] = not o.get('onlyOnDaily', True)
        settings.save(self.s)
        self._overlay_buttons()

    def _overlays_allowed(self, f):
        """With 'only on the daily' on: show the overlays only while a daily's stage + car are loaded and the
        conditions look right (and always while moving them, recording, or during / just after a run)."""
        o = self.s['overlay']
        if not o.get('onlyOnDaily', True) or not o.get('locked') or (self.recorder and self.recorder.state == 'recording'):
            return True
        for d in self.dailies.values():
            j = d.get('judge')
            if j and j.state == 'running':
                return True
            if j and f is not None and f.track and j._right(f):
                return d.get('cond_ok') is not False
        return False

    def _check_conditions(self, f):
        """On a daily's start line: the game's air temperature vs the other drivers' at the start of the same daily.
        The same time of day + weather give the same air, so a big difference = the game is set up differently.
        -> sets d['cond_ok'] (None = can't tell yet) and d['cond_diff'] (kelvin)."""
        if f is None or not f.track or f.clock_ms > 0 or not (150 < f.air_k < 350):
            return
        for d in self.dailies.values():
            j, want = d.get('judge'), d['ch'].get('startTempK')
            if j and j.state != 'running' and j._right(f):
                if want:
                    d['cond_diff'] = f.air_k - want
                    d['cond_ok'] = abs(d['cond_diff']) <= COND_TOL_K
                else:
                    d['cond_ok'], d['cond_diff'] = None, None

    def _apply_visibility(self, f):
        allowed = self._overlays_allowed(f)
        if allowed == self._ov_allowed:
            return
        self._ov_allowed = allowed
        self.overlay.show(allowed and self.s['overlay'].get('visible', True))
        for w in self.widgets.values():
            w.show(allowed and bool(w.cfg.get('visible')))

    def _widget_buttons(self):
        for key, l in self.widget_links.items():
            on = bool(self.widgets[key].cfg.get('visible')) if hasattr(self, 'widgets') else False
            l._edge = ACC if on else LINE2
            l.configure(text=('✓  ' if on else '+  ') + widgets.LABELS[key].upper() + ('' if on else '  (off)'),
                        bg=ACC if on else BG, fg=WHITE if on else FG2, highlightbackground=l._edge)

    def toggle_overlay(self, on):
        self.s['overlay']['visible'] = on
        settings.save(self.s)
        self.overlay.show(on and self._ov_allowed)
        self._overlay_buttons()

    def _overlay_buttons(self):
        o = self.s['overlay']
        self.lock_b.configure(text='Move overlays' if o.get('locked') else 'Lock overlays')
        self.vis_b.configure(text='Hide timer' if o.get('visible', True) else 'Show timer')
        self.only_b._fg = ACC if o.get('onlyOnDaily', True) else FG2
        self.only_b.configure(text=('✓ ' if o.get('onlyOnDaily', True) else '') + 'Only on the daily', fg=self.only_b._fg)
        self.next_b._fg = ACC if o.get('offerNext', True) else FG2
        self.next_b.configure(text=('✓ ' if o.get('offerNext', True) else '') + 'Offer the next daily after a run',
                              fg=self.next_b._fg)

    def open_site(self):
        if self.api.configured:
            webbrowser.open(self.api.base + '/')

    def drive_click(self, slot, confirm=True):
        """Set the daily up in the game's save, then start the game: it opens on the daily's stage, car and conditions.
        confirm=False: no 'restart the game?' question (the next-daily card's button already says it restarts)."""
        d = self.dailies.get(slot)
        if not d:
            return
        ch = d['ch']
        if getattr(self, '_restarting', False):
            if self._restarting == slot:       # this daily's button reads CANCEL while the game closes
                self._cancel_restart()
            return
        if saveslot.game_running():
            # the game only reads the set-up when it starts (and writes its save when it exits), so: close it the
            # normal way, set the daily up, start it again. One click, no need to quit by hand.
            if any(x.get('judge') and x['judge'].state == 'running' for x in self.dailies.values()):
                messagebox.showinfo('ACR Daily', 'Finish or leave the stage you are on first.')
                return
            if confirm and not messagebox.askyesno('ACR Daily', 'Assetto Corsa Rally is running.\n\nACR Daily will close it, set up '
                                       'SS%d (%s · %s · %s) and start it again. This takes about a minute.\n\n'
                                       'Go?' % (slot, stage_name(ch), ch['car'], conditions(ch))):
                return
            self._restart_into(slot)
            return
        self._setup_and_launch(slot)

    def _restart_into(self, slot):
        """Close the game (WM_CLOSE, like its X button), wait for it to exit and save, then set up + start.
        While it waits, that daily's DRIVE button reads CANCEL and takes the app back (_cancel_restart)."""
        self._restarting = slot
        self.cards[slot]['drive'].configure(text='CANCEL  ✕')
        saveslot.ask_game_to_quit()
        t0 = time.monotonic()

        def wait():
            if not saveslot.game_running():
                self.sub_l.configure(text='Game closed. Setting up the daily...')
                self._restart_job = self.root.after(4000, lambda: (self._restart_done(), self._setup_and_launch(slot)))
                return
            waited = time.monotonic() - t0
            if waited > 120:
                self._restart_done()
                self.sub_l.configure(text='The game did not close. Quit it from its menu, then click DRIVE again.')
                return
            if 8 < waited < 9 or 30 < waited < 31:
                saveslot.ask_game_to_quit()     # ask again (it may have been on a loading screen)
            self.sub_l.configure(text='Closing Assetto Corsa Rally... (%d s) If the game asks, confirm quitting. '
                                      'CANCEL to stop.' % waited)
            self._restart_job = self.root.after(1000, wait)
        self._restart_job = self.root.after(1000, wait)

    def _restart_done(self):
        slot, self._restarting = self._restarting, False
        if slot in self.cards:
            self.cards[slot]['drive'].configure(text='DRIVE  ›')

    def _cancel_restart(self):
        """Stop waiting for the game to close (it may still ask its player whether to quit)."""
        job = getattr(self, '_restart_job', None)
        if job:
            self.root.after_cancel(job)
        self._restart_job = None
        self._restart_done()
        self.sub_l.configure(text='Cancelled. Nothing was changed (if the game asks whether to quit, you can say no).')

    def _setup_and_launch(self, slot):
        d = self.dailies.get(slot)
        if not d:
            return
        ch = d['ch']
        try:
            msg = saveslot.write_daily(ch)
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', '%s\n\nSet it up by hand: %s · %s · %s' % (e, ch['track'], ch['car'], conditions(ch)))
            return
        self.active = slot
        self._show_active()
        path = ('In the game: any key › E (Racing) › Rally › Single Rally Stage › START RACE › Start Stage. '
                'Stage, car and conditions are already set.')
        self.sub_l.configure(text='Starting the game... ' + path)
        try:
            saveslot.launch_game()
        except OSError:
            self.sub_l.configure(text='Daily set up. Start the game from Steam. ' + path)

    def restore_click(self):
        if not messagebox.askyesno('ACR Daily', 'Put back the game save from before the last daily set-up?'):
            return
        try:
            messagebox.showinfo('ACR Daily', saveslot.restore_latest())
        except (saveslot.SaveError, OSError) as e:
            messagebox.showwarning('ACR Daily', str(e))

    def record_click(self):
        self.recorder = RouteRecorder()

    def upload_click(self):
        rec = self.recorder.saved if self.recorder else None
        if not rec:
            messagebox.showinfo('ACR Daily', 'Record a route first.')
            return

        def go():
            try:
                self.api.upload_route(rec['track'], rec['points'])
                ui(self.root, self.adm_l.configure, {'text': 'Uploaded %s' % rec['track']})
            except ApiError as e:
                ui(self.root, self.adm_l.configure, {'text': 'Upload failed: %s' % e})
        threading.Thread(target=go, daemon=True).start()

    def _place_window(self):
        """Where and how big the user left the window; at first, as tall as its contents need (timing sheet and
        an UPDATE bar included), within the screen."""
        self.root.update_idletasks()
        area = work_area() or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48)
        w = self.s.get('window') or {}
        width = int(w.get('w') or WIN_W)
        height = int(w.get('h') or max(WIN_H, self.root.winfo_reqheight() + 50))
        height = max(700, min(height, area[3] - area[1] - 40))     # 40: the title bar
        x, y = w.get('x'), w.get('y')
        if not (isinstance(x, int) and isinstance(y, int) and on_screen(x, y)):
            x, y = area[0] + 60, area[1] + 20
        self.root.geometry('%dx%d+%d+%d' % (width, height, x, y))

    def _save_window(self):
        if self.root.state() != 'normal':      # minimised or maximised: keep the last normal size
            return
        self.s['window'] = {'w': self.root.winfo_width(), 'h': self.root.winfo_height(),
                            'x': self.root.winfo_x(), 'y': self.root.winfo_y()}
        settings.save(self.s)

    def quit(self):
        try:
            self._save_window()
        except (tk.TclError, OSError):
            pass
        self.shm.close()
        self.root.destroy()

    # -------------------------------------------------------------- network

    def refresh_challenge(self):
        if not self.api.configured:
            self.net_msg = 'No server set (see SETUP.md)'
            return

        def go():
            try:
                chs = self.api.today()
                ui(self.root, self._set_challenges, chs)
            except ApiError as e:
                self.net_msg = str(e)
                ui(self.root, self.root.after, 15000, self.refresh_challenge)
        threading.Thread(target=go, daemon=True).start()

    def _set_challenges(self, chs):
        self.net_msg = ''
        for ch in chs:
            slot = ch.get('slot', 1)
            d = self.dailies.get(slot)
            if d and d['ch'].get('id') == ch.get('id'):
                # the same daily: take the server's latest details (a corrected car or stage id, the start air) - the
                # route object stays, the judge holds it
                d['ch'].update({k: v for k, v in ch.items() if k != 'route'})
                continue
            if d and d.get('judge') and d['judge'].state == 'running':
                self.root.after(5000, lambda: self._set_challenges(chs))   # never swap a daily mid-run
                return
            judge = Judge(ch) if ch.get('route') else None
            self.dailies[slot] = {'ch': ch, 'judge': judge, 'board': None, 'ghost_for': None, 'ghost_name': None,
                                  'ghosts': GhostSet(judge.route, judge.penalty_ms) if judge else None,
                                  'ghost_loading': set(), 'live': []}
            c = self.cards.get(slot)
            if c:
                km = '%.1f KM' % (ch['lengthM'] / 1000) if ch.get('lengthM') else ''
                c['where'].configure(text='  ·  '.join(x for x in ((ch.get('rally') or '').upper(),
                                                                     (ch.get('surface') or '').upper(), km) if x))
                self._fit_name(c['name'], stage_name(ch).upper())
                c['car'].configure(text=ch['car'] + ('  ·  %s' % ch['carClass'] if ch.get('carClass') else ''))
                c['cond'].configure(text=conditions(ch))
        for slot in list(self.dailies):
            if slot not in {c.get('slot', 1) for c in chs}:
                del self.dailies[slot]
        if chs:
            try:
                self.date_l.configure(text=dt.date.fromisoformat(chs[0]['date']).strftime('%a %d %b').upper())
            except (KeyError, ValueError):
                self.date_l.configure(text=chs[0].get('date', ''))
        self._show_active()
        self.refresh_board()

    def _fit_name(self, label, text):
        """A stage name on its card: as big as fits on one line (menu names run to 30+ letters), else wrapped."""
        room = max(300, self.root.winfo_width() - 75) if self.root.winfo_ismapped() else WIN_W - 75
        for size in (24, 21, 18, 16):
            if tkfont.Font(family=FONT_C, size=size).measure(text) <= room:
                break
        label.configure(text=text, font=(FONT_C, size), wraplength=room)

    def _show_active(self):
        for slot, c in self.cards.items():
            on = slot == self.active and slot in self.dailies
            c['bar'].configure(bg=ACC if on else BG)
            c['ss'].configure(fg=ACC if on else MUTED)
            self._btn_style(c['drive'], on)
        self.board_l.configure(text=' '.join(('TIMING  SS%d' % self.active)))
        self._fill_tree()

    def refresh_board(self):
        if not self.api.configured:
            return
        for slot, d in list(self.dailies.items()):
            def go(slot=slot, date=d['ch'].get('date')):
                try:
                    b = self.api.leaderboard(date, slot)
                    ui(self.root, self._set_board, slot, b)
                except ApiError as e:
                    self.net_msg = str(e)
            threading.Thread(target=go, daemon=True).start()

    def _set_board(self, slot, b):
        d = self.dailies.get(slot)
        if not d:
            return
        d['board'] = b
        if slot == self.active:
            self._fill_tree()
        # live gap: against this daily's #1
        entries = [e for e in (b or {}).get('entries', []) if e.get('totalMs') is not None]
        # ghosts for the displays: the top runs and your own first run
        me = self.s.get('steamId')
        gs = d.get('ghosts')
        if gs is not None:
            for e in entries[:6] + [e for e in entries if e.get('steamId') == me]:
                rid = e['runId']
                if rid in gs.runs or rid in d['ghost_loading']:
                    continue
                d['ghost_loading'].add(rid)

                def load(rid=rid, name=e['name']):
                    try:
                        tr = self.api.run_trace(rid)
                        ui(self.root, gs.add, rid, name, tr.get('trace'))
                    except ApiError:
                        pass
                    finally:
                        d['ghost_loading'].discard(rid)
                threading.Thread(target=load, daemon=True).start()
        target = entries[0] if entries else None
        if target and d.get('judge') and target['runId'] != d['ghost_for']:
            d['ghost_for'] = target['runId']

            def go():
                try:
                    tr = self.api.run_trace(target['runId'])
                    ui(self.root, self._set_ghost, slot, tr, target)
                except ApiError:
                    d['ghost_for'] = None
            threading.Thread(target=go, daemon=True).start()

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        me = self.s.get('steamId')
        entries = (self.board or {}).get('entries', [])[:50]
        for e in entries:
            dnf = e.get('status') == 'dnf' or e.get('totalMs') is None
            pen = '+%d' % (e['resets'] * self.penalty_s()) if e.get('resets') and not dnf else ''
            tag = 'me' if e.get('steamId') == me else 'p1' if e.get('rank') == 1 else ''
            self.tree.insert('', 'end', values=('–' if dnf else e['rank'], e['name'], 'DNF' if dnf else fmt_ms(e['totalMs']), pen),
                             tags=(tag,))
        if not entries:
            self.tree.insert('', 'end', values=('', 'No times yet', '', ''))

    def _set_ghost(self, slot, tr, target):
        d = self.dailies.get(slot)
        if d and d.get('judge') and tr and tr.get('trace'):
            d['judge'].set_ghost(tr['trace'])
            d['ghost_name'] = target['name']

    def check_update(self):
        """(thread) Ask the server for the latest version; tick() shows the UPDATE bar."""
        try:
            v = self.api.version()
        except ApiError:
            return
        newer = tuple(int(x) for x in str(v.get('latest', '0')).split('.') if x.isdigit()) > \
            tuple(int(x) for x in __version__.split('.'))
        if newer and v.get('url'):
            url = v['url'] if v['url'].startswith('http') else self.api.base + v['url']
            self.update_info = {'version': v['latest'], 'url': url}

    def _driving(self):
        return any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or \
            bool(self.recorder and self.recorder.state == 'recording')

    def _render_update(self):
        info = self.update_info
        if not info:
            return
        if not self.upd.winfo_ismapped():
            self.upd.pack(fill='x', padx=20, pady=(12, 0), after=self._head_rule)
        if self.update_busy:
            text = self.update_busy
        elif self._driving():
            text = 'NEW VERSION %s  ·  UPDATE AFTER THIS RUN' % info['version']
        else:
            text = 'UPDATE TO %s  ›' % info['version']
        if self.upd.cget('text') != text:
            self.upd.configure(text=text, cursor='watch' if self.update_busy or self._driving() else 'hand2')

    def do_update(self):
        info = self.update_info
        if not info or self.update_busy or self._driving():
            return
        if not updater.can_self_update():      # running from source: get it from the website
            webbrowser.open(info['url'])
            return
        if self._pending_update and os.path.exists(self._pending_update):   # downloaded during a run
            self._install_update(self._pending_update)
            return
        self.update_busy = 'DOWNLOADING %s ...' % info['version']

        def go():
            try:
                new = updater.download(info['url'], progress=lambda p: setattr(
                    self, 'update_busy', 'DOWNLOADING %s  ·  %d %%' % (info['version'], p * 100)))
                self.update_busy = 'INSTALLING %s ...' % info['version']
                self.root.after(0, lambda: self._install_update(new))
            except updater.UpdateError as e:
                self.update_busy = ''
                self.root.after(0, lambda: messagebox.showerror('ACR Daily', 'Update failed: %s' % e))
        threading.Thread(target=go, daemon=True).start()

    def _install_update(self, new):
        if self._driving():                    # a run started while downloading: install after it
            self.update_busy = ''
            self._pending_update = new
            return
        try:
            updater.install_and_restart(new)
        except updater.UpdateError as e:
            self.update_busy = ''
            messagebox.showerror('ACR Daily', 'Update failed: %s' % e)
            return
        self.quit()

    def just_updated(self):
        """Started by the updater: come to the front (Windows keeps it behind otherwise) and say so."""
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self.root.after(1500, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()
        if not self.update_info:
            self.upd.configure(text='UPDATED TO %s  ✓' % __version__, bg=WHITE, cursor='arrow')
            self.upd.pack(fill='x', padx=20, pady=(12, 0), after=self._head_rule)
            self.root.after(8000, lambda: (self.upd.pack_forget(), self.upd.configure(bg=ACC)))

    def periodic(self):
        self._periodic_n = getattr(self, '_periodic_n', 0) + 1
        if self._periodic_n % 30 == 0 and not self.update_info:   # every 30 min: a new version?
            threading.Thread(target=self.check_update, daemon=True).start()
        self.refresh_challenge()
        self.refresh_routes()
        self.refresh_week()
        self.refresh_board()
        threading.Thread(target=self.api.flush, daemon=True).start()
        self.root.after(60000, self.periodic)

    def on_result(self, result):
        settings.append_result(result)
        if not self.api.configured:
            return
        if not self.s.get('token'):
            self.api._queue(dict(result, appVersion=__version__))
            self.sub_l.configure(text='Sign in with Steam to put this run on the leaderboard.')
            return

        def go():
            try:
                r = self.api.submit(result)
                if r and r.get('counted') is False:
                    msg = 'Practice run: not on the board (your first run of the day is your result).'
                else:
                    msg = 'Submitted.' + (' Rank %s today.' % r['rank'] if r and r.get('rank') else '')
            except ApiError as e:
                if e.code == TOO_OLD:
                    msg = 'Not on the board: %s' % e
                    self.check_update()          # shows the UPDATE bar
                else:
                    msg = 'Not sent yet (%s) - will retry.' % e
            ui(self.root, self.sub_l.configure, {'text': msg})
            ui(self.root, self.refresh_board)
        threading.Thread(target=go, daemon=True).start()

    # -------------------------------------------------------------- loop

    def tick(self):
        """20 times a second: read the game, judge, draw. Always schedules the next tick, whatever happens."""
        try:
            self._tick()
        except Exception:
            import traceback
            traceback.print_exc()
        self.root.after(TICK_MS, self.tick)

    def _tick(self):
        try:
            f = self.shm.read()
        except Exception:
            f = None
        self.last_frame = f
        now = time.monotonic()
        self.auto_rec.feed(f, now)
        if self.auto_rec.state == 'done':
            self._contribute(self.auto_rec.saved)
            self.auto_rec = RouteRecorder()
        if self.recorder:
            self.recorder.feed(f, now)
            if self.s.get('admin'):
                self.adm_l.configure(text=self.recorder.message)
        # every daily's judge sees every frame; each only starts on its own stage + car
        for slot, d in list(self.dailies.items()):
            j = d.get('judge')
            if not j:
                continue
            for ev in j.feed(f):
                if ev == 'start':   # which Steam account the game runs under (checked against the sign-in)
                    d['practice'] = self._driven(slot)    # the first start of a daily is the one that counts
                    d['accounts'] = {steam_account()}
                if ev in ('finished', 'dnf', 'invalid'):
                    accounts = (d.get('accounts') or set()) | {steam_account()}
                    self.on_result(dict(j.result, gameSteamIds=sorted(a for a in accounts if a), country=self.country))
                    self._send_live(slot, j, f, 'finished' if ev == 'finished' else 'dnf')
                    other = self._next_to_offer(slot)
                    if other:      # a few seconds later, when the result is in and the game shows its own
                        self.root.after(NEXT_CARD_AFTER_MS, lambda s=slot, o=other, e=ev: self._offer_next(s, o, e))
                if ev == 'start':
                    self.active = slot
                    self._show_active()
                    self._send_live(slot, j, f, 'live')
                if ev == 'incident' and j.incident_queue:
                    self._send_incident(j, j.incident_queue.pop(0))
                if ev == 'split':
                    n = len(j.splits)
                    self._standing('SPLIT %d / %d' % (n, len(j.split_at)), j.splits[-1], n - 1, hold=SPLIT_SHOW_S)
                elif ev == 'finished':
                    self._standing('FINISH (provisional)', j.result['totalMs'], None, hold=None)
                elif ev in ('start', 'dnf', 'invalid'):
                    self.overlay.show_standing('', None)
                    self.panel_until = 0
            if j.state == 'running' and now - self.live_at >= LIVE_EVERY_S:
                self._send_live(slot, j, f, 'live')
        if self.panel_until and now > self.panel_until:
            self.overlay.show_standing('', None)
            self.panel_until = 0
        active = self._pick_active(f)
        if active != self.active:
            self.active = active
            self._show_active()
        try:
            self._check_conditions(f)
            self._apply_visibility(f)
            self._render(f)
            self._wtick += 1
            if self._wtick % 2 == 0:          # the optional displays: 10 times a second
                self._render_widgets(f)
        except Exception:   # a display bug must never stop the run being judged
            import traceback
            traceback.print_exc()

    def _render(self, f):
        ch = self.challenge
        status, sub, ov = self._overlay_state(f)
        if self.status_l.cget('text') != status:
            self.status_l.configure(text=status)
        if sub:
            self.sub_l.configure(text=sub)
        word, colour = {'live': ('LIVE', BAD), 'rec': ('REC', BAD), 'ready': ('READY', GOOD), 'finished': ('FINISHED', WHITE),
                        'dnf': ('DNF', BAD), 'invalid': ('INVALID', BAD), 'offline': ('OFFLINE', MUTED)}.get(ov[0], ('STANDBY', MUTED))
        if self.state_l.cget('text') != word:
            self.state_l.configure(text=word, fg=colour if word != 'STANDBY' else FG2)
            self.dot.configure(fg=colour)
        self.overlay.render(*ov)
        self._render_update()
        pending = len(self.api._pending())
        ends = ''
        if ch and ch.get('endsAt'):
            left = int(ch['endsAt'] / 1000 - time.time())
            if left > 0:
                ends = '   ·   stages close in %d:%02d' % (left // 3600, left % 3600 // 60)
        foot = 'v%s%s%s%s%s%s' % (__version__, '   ·   ' + self.week_txt if self.week_txt else '', ends, '   ·   %d run(s) waiting to send' % pending if pending else '',
                                '   ·   ' + self.net_msg if self.net_msg and ch else '',
                                '   ·   ' + self.update_msg if self.update_msg else '')
        if self.foot_l.cget('text') != foot:
            self.foot_l.configure(text=foot, fg=ACC if self.update_msg else MUTED)

    def _overlay_state(self, f):
        """-> (main window status, main window sub-line, overlay args (status, title, ms, resets, line, colour))."""
        j, ch, rec = self.judge, self.challenge, self.recorder
        if rec and rec.state == 'recording':
            return rec.message, '', ('rec', 'RECORDING ROUTE · %s' % rec.track.upper(), f.clock_ms if f else 0, 0,
                                     'Drive cleanly to the finish', SOFT)
        if not ch:
            return ('Getting today\'s challenge...', self.net_msg,
                    ('offline', 'ACR DAILY', 0, 0, self.net_msg or 'Connecting to the server', MUTED))
        stage = 'SS%d · %s' % (ch.get('slot', 1), stage_name(ch, short=True).upper())
        today = '  |  '.join('%d: %s · %s%s' % (s, stage_name(d['ch']), d['ch']['car'],
                                                 ' (%s)' % conditions(d['ch']) if conditions(d['ch']) else '')
                             for s, d in sorted(self.dailies.items()))
        if not j:
            return 'Today\'s stage has no route yet', 'Check back later.', ('offline', stage, 0, 0, 'No route for today yet', MUTED)
        signed = bool(self.s.get('token'))
        if j.state == 'running':
            gap = j.gap_ms
            if gap is not None:
                line = 'vs %s  %s%.2f' % (getattr(self, 'ghost_name', '#1'), '+' if gap >= 0 else '−', abs(gap) / 1000)
                lc = SLOW if gap > 0 else GOOD
            else:
                line, lc = 'On stage · %d%%' % round(j.progress * 100), SOFT
            if not signed:
                line += '   · not signed in'
            if (self.dailies.get(ch.get('slot', 1)) or {}).get('practice'):
                line = 'PRACTICE · ' + line
            return j.message, '', ('live', stage, j.total_ms, j.resets, line, lc)
        if j.state == 'finished':
            rank = self._my_rank()
            return j.message, '', ('finished', stage, j.total_ms, j.resets,
                                   'P%s today' % rank if rank else 'Sending...' if signed else 'Sign in to submit', ACC)
        if j.state in ('dnf', 'invalid'):
            return j.message, '', (j.state, stage, j.result['clockMs'], j.result['resets'], j.result['reason'].capitalize(), BAD)
        cond = conditions(ch)
        d = self.dailies.get(ch.get('slot', 1)) or {}
        if j.state == 'armed' and d.get('cond_ok') is False:
            diff = d.get('cond_diff') or 0
            why = 'The air is %.1f °C %s than for the other drivers: check the time of day and weather (%s)' % (
                abs(diff), 'warmer' if diff > 0 else 'colder', cond or '?')
            return j.message, why, ('ready', stage, 0, 0, 'CHECK TIME / WEATHER · set: ' + (cond or '?'), BAD)
        if j.state == 'armed':
            if self._driven(ch.get('slot', 1)):
                return j.message, '', ('ready', stage, 0, 0, 'PRACTICE · your first run is your result', SOFT)
            return j.message, '', ('ready', stage, 0, 0, ('Set: %s · ' % cond if cond else '') + 'goes LIVE with the stage clock', SOFT)
        # waiting
        if f is None:
            return 'Waiting for Assetto Corsa Rally', '', ('standby', 'ACR DAILY', 0, 0, 'Waiting for the game', MUTED)
        if f.track and not (same_track(f.track, ch) and same_car(f.car, ch)):
            return (j.message, 'The game reports: %s · %s' % (f.track, f.car or '?'),
                    ('standby', 'NOT A DAILY STAGE', 0, 0, 'Load daily ' + today, MUTED))
        if f.clock_ms > 0:
            return j.message, '', ('standby', stage, 0, 0, 'Restart the stage to take part' + (' · set: ' + cond if cond else ''), MUTED)
        return j.message, '', ('standby', stage, 0, 0, 'Load ' + today, MUTED)

    def _next_to_offer(self, slot):
        """After a run of daily `slot`: the other daily to offer, or None (setting off, a practice run, the other one
        already driven or already offered today)."""
        d = self.dailies.get(slot) or {}
        if not self.s['overlay'].get('offerNext', True) or d.get('practice'):
            return None
        for other, od in sorted(self.dailies.items()):
            key = (od.get('ch') or {}).get('id')
            if other == slot or not od.get('judge') or self._driven(other) or key in self._offered:
                continue
            self._offered.add(key)
            return other
        return None

    def _offer_next(self, slot, other, ev):
        """Show the next-daily card under the timer (unless the other daily got started in the meantime)."""
        od = self.dailies.get(other)
        if not od or self._driven(other) or any(x.get('judge') and x['judge'].state == 'running' for x in self.dailies.values()):
            return
        if getattr(self, 'next_card', None):
            self.next_card.close()
        me = self.s.get('steamId')
        mine = next((e for e in ((self.dailies.get(slot) or {}).get('board') or {}).get('entries', [])
                     if me and e.get('steamId') == me), None)
        if ev == 'finished':
            title = 'SS%d FINISHED' % slot + (' · P%s today' % mine['rank'] if mine and mine.get('rank') else '')
        else:
            title = 'SS%d %s' % (slot, 'DNF' if ev == 'dnf' else 'INVALID')
        ch = od['ch']
        ov = self.overlay.win
        at = (ov.winfo_x(), ov.winfo_y() + ov.winfo_height() + 8) if ov.winfo_ismapped() else (60, 60)
        self.next_card = nextcard.NextCard(
            self.root, at, title, 'Next: SS%d · %s' % (other, stage_name(ch)),
            ' · '.join(x for x in (ch.get('car'), conditions(ch)) if x),
            'DRIVE SS%d ›  restarts the game' % other, lambda: self.drive_click(other, confirm=False),
            title_fg=WHITE if ev == 'finished' else BAD)

    def _driven(self, slot):
        """Has this daily already been started (by this app, or is there a result on the board)?"""
        d = self.dailies.get(slot) or {}
        me = self.s.get('steamId')
        if d.get('started_once'):
            return True
        on_board = any(e.get('steamId') == me for e in (d.get('board') or {}).get('entries', [])) if me else False
        d['started_once'] = on_board or bool(d.get('judge') and d['judge'].state in ('running', 'finished', 'dnf', 'invalid'))
        return on_board

    def refresh_week(self):
        """Your place in this week's hall of fame, for the footer."""
        if not self.api.configured or not self.s.get('steamId'):
            return

        def go():
            try:
                w = self.api.week()
            except ApiError:
                return
            me = next((p for p in w.get('standings', []) if p.get('steamId') == self.s.get('steamId')), None)
            played = sum(1 for s in w.get('stages', []) if not s.get('future'))
            self.week_txt = ('week %s · P%s · %d pts · %d/%d stages' % (w.get('week'), me['rank'], me['total'], me['scored'], played)
                             if me else 'week %s · no points yet' % w.get('week'))
        threading.Thread(target=go, daemon=True).start()

    def refresh_routes(self):
        if not self.api.configured:
            return

        def go():
            try:
                # stages with a driven route; estimated ones (from the game's files) still take the first clean run
                self.known_routes = {norm(r['track']) for r in self.api.routes() if not r.get('estimated')}
            except (ApiError, KeyError, TypeError):
                pass
        threading.Thread(target=go, daemon=True).start()

    def _contribute(self, rec):
        """A clean run just finished: if its stage has no route yet, it becomes the stage's route."""
        if not rec or self.known_routes is None or norm(rec['track']) in self.known_routes:
            return
        if not self.s.get('token') or not self.api.configured:
            return
        self.known_routes.add(norm(rec['track']))      # once per stage per session
        stage_id = None
        try:   # the game's own stage id, from its save (only if the save's car is the car just driven)
            with open(saveslot.SAVE, 'rb') as fh:
                setup = saveslot.read_setup(fh.read())
            if same_car(rec['car'], {'carId': setup['car'][1].decode()}):
                stage_id = setup['stage'][1].decode()
        except (OSError, saveslot.SaveError):
            pass

        def go():
            try:
                r = self.api.contribute_route(rec, stage_id)
                msg = ('New stage recorded: %s (%.1f km). It joins the daily rotation.' % (rec['track'], r['length'] / 1000)
                       if r.get('added') else '')
            except ApiError as e:
                msg = 'Route of %s not used: %s' % (rec['track'], e)
            if msg:
                ui(self.root, self.sub_l.configure, {'text': msg})
        threading.Thread(target=go, daemon=True).start()

    def poll_live(self):
        """Every second while the Stage strip, Mini map or Live field display is on: who else is on the active stage."""
        self.root.after(LIVE_POLL_MS, self.poll_live)
        on = any(self.widgets[k].cfg.get('visible') for k in ('strip', 'map', 'field'))
        d = self.dailies.get(self.active)
        if not on or not d or not self.api.configured or getattr(self, '_live_busy', False):
            return
        self._live_busy = True

        def go():
            try:
                r = self.api.live_now(d['ch']['date'], self.active)
                drivers = r.get('drivers', [])
                d['live_colours'] = widgets.colours([x.get('steamId') for x in drivers])   # same set as the website
                d['live'] = [x for x in drivers if x.get('steamId') != self.s.get('steamId')]
            except ApiError:
                pass
            finally:
                self._live_busy = False
        threading.Thread(target=go, daemon=True).start()

    def _render_widgets(self, f):
        """What the optional displays show, for the active daily."""
        vis = {k: w for k, w in self.widgets.items() if w.cfg.get('visible')}
        if not vis:
            return
        d = self.dailies.get(self.active) or {}
        j, ch, gs = d.get('judge'), d.get('ch') or {}, d.get('ghosts')
        running = bool(j and j.state == 'running')
        my_idx = j._max_idx if running else 0
        my_total = j.total_ms if running else 0
        entries = [e for e in (d.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
        me = self.s.get('steamId')
        me_run = next((e['runId'] for e in entries if e.get('steamId') == me), None)
        p1_run = entries[0]['runId'] if entries else None
        picked = gs.pick(my_idx, my_total, me_run, p1_run) if gs else []
        cols = d.get('live_colours') or {}
        live_now = [x for x in d.get('live') or [] if x.get('state') == 'live']
        view = {
            'slot': ch.get('slot'), 'running': running, 'route': ch.get('route'),
            'splits': j.split_at if j else [],
            'progress': j.progress if running else (0.0 if j else None),
            'ghosts': [(lab, kind, g.progress_at(my_total), gap if running else None) for lab, kind, g, gap in picked],
            'ghost_pos': [(lab, kind, g.pos_at(my_total)) for lab, kind, g, gap in picked],
            'me_pos': (f.x, f.z) if (f is not None and j and j._right(f)) else None,
            'gap_p1': j.gap_ms if running else None, 'p1_name': d.get('ghost_name'),
            'field': d.get('live') or [],
            'colours': cols,
            'others': [(x['name'], cols.get(str(x.get('steamId')), widgets.FG2), (x['x'], x['z']), x.get('avatar'))
                       for x in live_now],
            'others_prog': [(x['name'], cols.get(str(x.get('steamId')), widgets.FG2), x.get('progress') or 0.0, x.get('avatar'))
                            for x in live_now],
        }
        for w in vis.values():
            try:
                w.render(view)
            except Exception:
                import traceback
                traceback.print_exc()

    def _send_live(self, slot, j, f, state):
        """Our position for the website's live map (every LIVE_EVERY_S while on stage, plus start / finish / DNF)."""
        self.live_at = time.monotonic()
        if not self.s.get('token') or not self.api.configured or f is None:
            return
        body = {'challengeId': j.ch.get('id'), 'x': round(f.x, 1), 'z': round(f.z, 1), 'progress': round(j.progress, 4),
                'totalMs': j.total_ms, 'resets': j.resets, 'state': state,
                'startedAt': getattr(j, '_start_wall', None), 'country': self.country}
        threading.Thread(target=self.api.live, args=(body,), daemon=True).start()

    def _send_incident(self, j, inc):
        """An incident of the run (judge -> incidents.py) for the website's live commentary. The server only uses
        the counted run's."""
        if not self.s.get('token') or not self.api.configured:
            return
        body = dict(inc, challengeId=j.ch.get('id'), startedAt=getattr(j, '_start_wall', None))
        threading.Thread(target=self.api.incident, args=(body,), daemon=True).start()

    def _standing(self, title, my_ms, split, hold):
        st = standing((self.board or {}).get('entries', []), self.s.get('steamId'), my_ms, split)
        self.overlay.show_standing(title, st)
        self.panel_until = time.monotonic() + hold if hold else 0

    def _my_rank(self):
        for e in (self.board or {}).get('entries', []):
            if e.get('steamId') == self.s.get('steamId'):
                return e['rank']
        return None


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # sharp text on high-DPI screens
    except Exception:
        pass
    app = App()
    if '--updated' in sys.argv:
        app.root.after(300, app.just_updated)
    app.root.mainloop()


if __name__ == '__main__':
    main()
