"""The launcher's thank-you bar: the current supporters on Buy Me a Coffee rolling by in a thin strip at the bottom,
with a SUPPORT button that opens buymeacoffee.com/acrdaily (the user, 27 Nov 2026: "thank the supporters as a small
rolling thin bar ... with a button to open buy me a coffee", "a list of current supporters").

The list comes from the server (Api.supporters, server/src/supporters.js), asked when the bar is built and every
10 minutes after; with nobody on it yet, the strip just asks for support. It rolls only while the launcher shows."""
import threading
import tkinter as tk
import webbrowser

from .i18n import _

URL = 'https://buymeacoffee.com/acrdaily'
BG, FG, NAME, LINE = '#141417', '#A1A1AA', '#F4F4F5', '#2B2B31'
ACC, WHITE, COFFEE = '#E30613', '#F4F4F5', '#FFDD00'
H = 26
STEP_MS, STEP_PX = 30, 1
EVERY_MS = 10 * 60 * 1000
GAP = '      '


def line_of(people):
    """The rolling words: [(text, is_name)], or None when nobody is on the list."""
    if not people:
        return None
    out = [(_('THANK YOU TO OUR SUPPORTERS') + GAP, False)]
    for k, p in enumerate(people):
        if k:
            out.append(('  ·  ', False))
        out.append((str(p.get('name') or 'Someone'), True))
    out.append((GAP, False))
    return out


class SupportBar:
    def __init__(self, parent, app, font, cond, is_on=lambda: True):
        self.app = app
        self.is_on = is_on
        self.font, self.cond = font, cond
        self.url = URL
        self.people = None            # (None: not asked yet; [] nobody)
        self._x = 0
        self._w = 0                   # (one copy of the words' width)
        self._rolling = False
        self._ids = {}                # (the waiting after() calls, cancelled when the bar goes)
        k = app.root.winfo_fpixels('1i') / 96
        self.f = tk.Frame(parent, bg=BG, height=round(H * k), highlightthickness=1, highlightbackground=LINE)
        self.f.pack_propagate(False)
        self.btn = tk.Label(self.f, text='☕ ' + _('SUPPORT'), bg=COFFEE, fg='#0A0A0B', font=(cond, 10), padx=10,
                            cursor='hand2')
        self.btn.pack(side='right', fill='y')
        self.btn.bind('<Button-1>', lambda _e: self.open())
        self.btn.bind('<Enter>', lambda _e: self.btn.configure(bg=ACC, fg=WHITE))
        self.btn.bind('<Leave>', lambda _e: self.btn.configure(bg=COFFEE, fg='#0A0A0B'))
        self.cv = tk.Canvas(self.f, bg=BG, highlightthickness=0, height=round(H * k), cursor='hand2')
        self.cv.pack(side='left', fill='both', expand=True)
        self.cv.bind('<Button-1>', lambda _e: self.open())
        self.cv.bind('<Configure>', lambda _e: self._draw())
        self.f.bind('<Destroy>', lambda _e: self._stop())
        self._draw()
        self.fetch()

    def _stop(self):
        for i in list(self._ids.values()):
            try:
                self.app.root.after_cancel(i)
            except Exception:
                pass
        self._ids.clear()
        self._w = 0

    def open(self):
        try:
            webbrowser.open(self.url)
        except Exception:
            pass

    # ---- the list
    def fetch(self):
        api = getattr(self.app, 'api', None)

        def work():
            try:
                r = api.supporters() if api is not None else None
            except Exception:
                r = None
            try:
                self.app.root.after(0, lambda: self._got(r))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()
        try:
            self._ids['fetch'] = self.app.root.after(EVERY_MS, self.fetch)
        except Exception:
            pass

    def _got(self, r):
        if not isinstance(r, dict):
            if self.people is None:
                self.people = []
                self._draw()
            return                              # (the server not reachable: the list as it was)
        u = str(r.get('url') or '')
        if u.startswith('https://buymeacoffee.com/') or u.startswith('https://www.buymeacoffee.com/'):
            self.url = u
        people = [p for p in (r.get('supporters') or []) if isinstance(p, dict)]
        if people != self.people:
            self.people = people
            self._draw()

    # ---- the strip
    def _draw(self):
        cv = self.cv
        cv.delete('all')
        h = max(1, cv.winfo_height())
        words = line_of(self.people)
        if not words:
            cv.create_text(10, h // 2, text=_('ACR DAILY is free. Like it? Buy us a coffee.'), fill=FG,
                           font=(self.font, 9), anchor='w')
            self._w = 0
            return
        # two copies side by side, so the words roll round without a gap
        x = 0
        for _copy in range(2):
            for text, is_name in words:
                t = cv.create_text(x, h // 2, text=text, fill=NAME if is_name else FG, anchor='w', tags='roll',
                                   font=(self.cond, 10) if is_name else (self.font, 9))
                b = cv.bbox(t)
                x += (b[2] - b[0]) if b else 0
            if _copy == 0:
                self._w = x
        if self._w:
            self._x %= self._w
        cv.move('roll', -self._x, 0)
        self.roll()

    def roll(self):
        if self._rolling:
            return
        self._rolling = True
        self._tick()

    def _tick(self):
        if not self._w or not self.is_on():
            self._rolling = False
            return
        try:
            self._x += STEP_PX
            self.cv.move('roll', -STEP_PX, 0)
            if self._x >= self._w:
                self.cv.move('roll', self._w, 0)
                self._x -= self._w
            if 'tick' in self._ids:                 # (one roll at a time)
                self.app.root.after_cancel(self._ids['tick'])
            self._ids['tick'] = self.app.root.after(STEP_MS, self._tick)
        except tk.TclError:                         # (the window closed)
            self._rolling = False
