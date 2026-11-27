"""The launcher's thank-you card: THANK YOU TO OUR SUPPORTERS and Buy Me a Coffee's own yellow button, which opens
buymeacoffee.com/acrdaily, with the current supporters on Buy Me a Coffee rolling by under them (the user, 27 Nov 2026:
"thank the supporters as a small rolling thin bar ... with a button to open buy me a coffee", "a list of current
supporters", then "make bar bigger, put buy me a coffee logo somehow").

The list comes from the server (Api.supporters, server/src/supporters.js), asked when the bar is built and every
10 minutes after; with nobody on it yet, the strip just asks for support. It rolls only while the launcher shows."""
import threading
import tkinter as tk
import webbrowser

from .i18n import _

URL = 'https://buymeacoffee.com/acrdaily'
BG, FG, NAME, LINE = '#141417', '#A1A1AA', '#F4F4F5', '#2B2B31'
ACC, WHITE, COFFEE, INK = '#E30613', '#F4F4F5', '#FFDD00', '#0A0A0B'
BTN_H = 44                      # (Buy Me a Coffee's button, px high at 100 %)
ROLL_H = 34                     # (the names' strip)
STEP_MS, STEP_PX = 30, 1
EVERY_MS = 10 * 60 * 1000
GAP = '        '


def line_of(people):
    """The rolling words: [(text, is_name)], or None when nobody is on the list."""
    if not people:
        return None
    out = []
    for k, p in enumerate(people):
        if k:
            out.append(('   ·   ', False))
        out.append((str(p.get('name') or 'Someone'), True))
    out.append((GAP + '·' + GAP, False))
    return out


def button_picture(h):
    """Buy Me a Coffee's yellow button (photos/bmc-button.png, 545 x 153) h px high, or None."""
    try:
        import os
        from PIL import Image, ImageTk
        src = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos', 'bmc-button.png')).convert('RGBA')
        return ImageTk.PhotoImage(src.resize((round(src.width * h / src.height), h), Image.LANCZOS))
    except Exception:
        return None


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
        k = self.k = app.root.winfo_fpixels('1i') / 96
        # a card: the cup and THANK YOU on top with the yellow button, the names rolling under them
        self.f = tk.Frame(parent, bg=BG, highlightthickness=1, highlightbackground=LINE)
        top = tk.Frame(self.f, bg=BG)
        top.pack(fill='x', padx=12, pady=(10, 0))
        tk.Label(top, text=_('THANK YOU TO OUR SUPPORTERS'), bg=BG, fg=WHITE, font=(cond, 13), anchor='w').pack(side='left')
        # Buy Me a Coffee's own yellow button (photos/bmc-button.png, from their embed code); a plain one without it
        self._btn_pic = button_picture(round(BTN_H * k))
        if self._btn_pic is not None:
            self.btn = tk.Label(top, image=self._btn_pic, bg=BG, bd=0, cursor='hand2')
        else:
            self.btn = tk.Label(top, text=_('SUPPORT'), bg=COFFEE, fg=INK, font=(cond, 12), padx=16, pady=6, cursor='hand2')
            self.btn.bind('<Enter>', lambda _e: self.btn.configure(bg=ACC, fg=WHITE))
            self.btn.bind('<Leave>', lambda _e: self.btn.configure(bg=COFFEE, fg=INK))
        self.btn.pack(side='right')
        self.btn.bind('<Button-1>', lambda _e: self.open())
        self.cv = tk.Canvas(self.f, bg=BG, highlightthickness=0, height=round(ROLL_H * k), cursor='hand2')
        self.cv.pack(fill='x', padx=1, pady=(6, 6))
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
            cv.create_text(12, h // 2, text=_('ACR DAILY is free. Like it? Buy us a coffee.'), fill=FG,
                           font=(self.font, 11), anchor='w')
            self._w = 0
            return
        # two copies side by side, so the words roll round without a gap
        x = 0
        for _copy in range(2):
            for text, is_name in words:
                t = cv.create_text(x, h // 2, text=text, fill=NAME if is_name else FG, anchor='w', tags='roll',
                                   font=(self.cond, 14) if is_name else (self.font, 12))
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
