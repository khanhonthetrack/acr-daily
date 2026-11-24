"""A comment on a run, as on RallySimFans: after a stage driven once (a daily, or a stage of a rally, a championship, a
cup or a ranked rally), a line on how it went ("lost the rear in the hairpin before the split", "the game froze at the
finish"), sent to the server (server/src/comments.js). Who sees it:
  a daily: everyone, with the driver's time on the website's timing sheet and in Discord's results of the day;
  a league event's stage (rallies, cup and 1V1 matches too, ranked rallies): only whoever runs it (a championship's
  owner and admins, a rally's or a cup's maker; ACR Daily's admins for its own and for 1V1s), told in their inbox.
Not after a time trial run: those are driven again and again.

Offered once the run's result is on the server, in a card under the timer that pops up over the game (CommentCard),
with DRIVE on the other daily when there is one to drive (app.py _offer_next): the comment box, SEND, CLOSE. It closes
by itself after CLOSE_S unless the box is clicked or typed in: then it stays until a button is pressed. What was sent
before fills the box (asked of the server once per run). Sending it empty takes it back.
"""
import threading
import tkinter as tk

from . import i18n
from .api import ApiError
from .i18n import _
from .widgets import fit_on_screen, keep_on_top, ON_TOP_S, born, show_window, hide_window

MAX = 200          # characters (the server's COMMENT.maxLen)
CELL = 44          # characters of it on the app's timing sheet, in the driver's cell
CLOSE_S = 30       # the card goes by itself after this long (the mouse on it: it waits), unless its box is used
STEP_MS = 100
BAR_H = 3
BG, PANEL, PANEL2, LINE2 = '#0A0A0B', '#141417', '#1C1C20', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#85858E'
ACC, BAD = '#E30613', '#FF453A'
ACC_TEXT = '#FF4655'   # ACR red as text (app.ACC_TEXT: WCAG AA on the dark panels)
FONT, FONT_C = i18n.font('Bahnschrift'), i18n.font('Bahnschrift SemiBold Condensed')

# who sees it, said under the box
NOTE = {
    'daily': _("Shown with your time on the daily's timing sheet on the website once the day is over (UTC), and in "
               "Discord's results."),
    'league': _("Only you and whoever runs the event see it: the league's owner and admins."),
    'cup': _("Only you and the cup's maker see it (ACR Daily's admins for its own cups)."),
    'event': _("Only you and the rally's maker see it."),
    'h2h': _("Only you and ACR Daily's admins see it."),
}


def _c():
    """The helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def with_comment(name, comment, n=CELL):
    """A timing sheet's driver cell: the name, then their comment cut to n characters."""
    if not comment:
        return name
    c = ' '.join(str(comment).split())
    return '%s   “%s”' % (name, c if len(c) <= n else c[:n - 1].rstrip() + '…')


def px(widget, n):
    """n pixels at 96 dpi on this screen."""
    return round(n * widget.winfo_fpixels('1i') / 96)


class CommentCard:
    """The card under the timer after a stage driven once, its result on the server (over the game, never
    click-through):

        SS1 FINISHED · P3 today
        SS1 · Peïra Cava · 3:21.456
        How did it go? One line.
        [                                                ]            12 / 200
        Shown with your time on the daily's timing sheet ... Send it empty to take it back.
        [ SEND ]  [ DRIVE SS2 ›  restarts the game ]  [ CLOSE ]
        ▬▬▬▬▬▬▬▬▬▬▬▬▬▬────────────   (filling up: full, it closes; it waits while the mouse is on it)

    The moment the box is clicked or typed in, the bar stops for good: the card stays until SEND, DRIVE or CLOSE. Sent,
    it closes, unless DRIVE is on it: it then says so and stays for DRIVE, its bar running again."""

    def __init__(self, root, at, title, what, note, text, on_send, drive=None, title_fg=WHITE, close_s=CLOSE_S):
        """at: (x, y) of its top-left corner; what: the run in a few words; note: who sees the comment; text: the box's
        start (what was sent before); on_send(text); drive: (label, fn) for DRIVE on the other daily, or None."""
        self.on_send = on_send
        self.drive = drive
        self.close_s = close_s
        self.left = close_s or 0
        self.hover = False
        self.writing = False           # the box used: the card stays (no bar)
        self.busy = False
        self.touched = False
        self._filling = False
        self._said = {'title': title, 'title_c': title_fg, 'what': what, 'note': note}   # (for the game: snapshot)
        self._msg = None
        self.win = w = tk.Toplevel(root)
        born(w)                          # (never over the game in front filling its screen: widgets.game_in_front)
        w.overrideredirect(True)
        w.attributes('-topmost', True)
        w.configure(bg=BG, highlightthickness=1, highlightbackground=ACC)
        tk.Frame(w, bg=ACC, height=2).pack(fill='x')
        body = tk.Frame(w, bg=BG)
        body.pack(fill='both', expand=True, padx=14, pady=(8, 12))
        tk.Label(body, text=title, bg=BG, fg=title_fg, font=(FONT_C, 13), anchor='w').pack(anchor='w')
        tk.Label(body, text=what, bg=BG, fg=WHITE, font=(FONT_C, 17), anchor='w').pack(anchor='w', pady=(4, 0))
        tk.Label(body, text=_('How did it go? One line.'), bg=BG, fg=FG2, font=(FONT, 9), anchor='w').pack(anchor='w', pady=(8, 3))
        self.var = tk.StringVar(value=(text or '')[:MAX])
        self.entry = tk.Entry(body, textvariable=self.var, width=52, bg=PANEL, fg=WHITE, insertbackground=WHITE, relief='flat',
                              font=(FONT, 11), highlightthickness=1, highlightbackground=LINE2, highlightcolor=FG2)
        self.entry.pack(fill='x', ipady=5)
        row = tk.Frame(body, bg=BG)
        row.pack(fill='x', pady=(3, 0))
        self.count = tk.Label(row, text='', bg=BG, fg=MUTED, font=(FONT, 8))
        self.count.pack(side='right')
        tk.Label(row, text=note + ' ' + _('Send it empty to take it back.'), bg=BG, fg=MUTED, font=(FONT, 8), anchor='w',
                 justify='left', wraplength=px(w, 380)).pack(side='left', anchor='w')
        self.msg = tk.Label(body, text='', bg=BG, fg=BAD, font=(FONT, 9), anchor='w', justify='left', wraplength=px(w, 440))
        btns = self.btns = tk.Frame(body, bg=BG)
        btns.pack(fill='x', pady=(10, 0))
        self.send_b = self._button(btns, _('SEND'), self._send, white=True)
        self.send_b.pack(side='left')
        self.drive_b = None
        if drive:
            self.drive_b = self._button(btns, drive[0], self._drive, primary=True)
            self.drive_b.pack(side='left', padx=(8, 0))
        self._button(btns, _('CLOSE'), self.close).pack(side='left', padx=(8, 0))
        self.bar = tk.Canvas(w, height=BAR_H, bg=PANEL2, highlightthickness=0)
        if close_s:
            self.bar.pack(side='bottom', fill='x')
        self.var.trace_add('write', lambda *_a: self._changed())
        self._changed(touch=False)
        # the box used (a click in it, a key): the card stays; a click takes the keyboard from the game to it
        self.entry.bind('<Button-1>', lambda _e: self._grab(), add='+')
        self.entry.bind('<FocusIn>', lambda _e: self.stay(), add='+')
        self.entry.bind('<Key>', lambda _e: self.stay(), add='+')
        self.entry.bind('<Return>', lambda _e: self._send())
        self.entry.bind('<KP_Enter>', lambda _e: self._send())
        w.bind('<Escape>', lambda _e: self.close())
        w.bind('<Enter>', lambda _e: setattr(self, 'hover', True))
        w.bind('<Leave>', lambda _e: setattr(self, 'hover', False))
        w.update_idletasks()
        w.geometry('+%d+%d' % fit_on_screen(at[0], at[1], w.winfo_reqwidth(), w.winfo_reqheight()))
        self._ticks = 0
        self._tick()

    @staticmethod
    def _button(parent, text, cmd, primary=False, white=False):
        """primary: red (DRIVE); white: SEND; else outlined (CLOSE)."""
        bg, fg = (ACC, WHITE) if primary else (WHITE, BG) if white else (BG, SOFT)
        b = tk.Label(parent, text=text, font=(FONT_C, 11), padx=12, pady=4, cursor='hand2', bg=bg, fg=fg,
                     highlightthickness=0 if primary or white else 1, highlightbackground=LINE2)
        b.bind('<Button-1>', lambda _e: cmd())
        b.bind('<Enter>', lambda _e: b.configure(bg=ACC if white else WHITE, fg=WHITE if white else BG))
        b.bind('<Leave>', lambda _e: b.configure(bg=bg, fg=fg))
        return b

    def _grab(self):
        """A click in the box: the keyboard from the game to it."""
        self.stay()
        try:
            self.win.focus_force()
            self.entry.focus_set()
        except tk.TclError:
            pass

    def stay(self):
        """The box used: the bar stops for good (until SEND, DRIVE or CLOSE)."""
        if not self.writing:
            self.writing = True
            if self.bar.winfo_manager():
                self.bar.pack_forget()

    def _changed(self, touch=True):
        v = self.var.get()
        if len(v) > MAX:                 # (a paste longer than that: cut; Tcl calls no trace from inside its own)
            v = v[:MAX]
            self.var.set(v)
        touch = touch and not self._filling
        self.touched = self.touched or touch
        if touch:
            self.stay()
        self.count.configure(text='%d / %d' % (len(v), MAX), fg=ACC_TEXT if len(v) >= MAX else MUTED)

    def prefill(self, text):
        """What was sent before, once the server says: into the box, unless something was typed meanwhile."""
        if self.alive and text and not self.touched and not self.var.get():
            self._filling = True         # (not the driver's typing: the bar runs on)
            self.var.set(text[:MAX])
            self._filling = False
            self.entry.icursor('end')

    def _say(self, text, fg):
        self._msg = (text, fg)
        self.msg.configure(text=text, fg=fg)
        if not self.msg.winfo_manager():
            self.msg.pack(anchor='w', pady=(6, 0), before=self.btns)

    def _send(self):
        if self.busy or not self.alive:
            return
        self.stay()
        self.busy = True
        self.send_b.configure(cursor='arrow')
        self._say(_('Sending...'), FG2)
        self.on_send(' '.join(self.var.get().split()))

    def failed(self, error):
        self.busy = False
        if self.alive:
            self.send_b.configure(cursor='hand2')
            self._say(_('Not sent: %s') % error, BAD)

    def sent(self, text):
        """The server has it: closed, or (DRIVE on it) said, the bar running again for DRIVE."""
        self.busy = False
        if not self.alive:
            return
        if not self.drive:
            self.close()
            return
        self._say(('✓ ' + _('Comment sent.')) if text else _('Comment taken back.'), WHITE)
        self.send_b.configure(cursor='hand2')
        self.writing, self.left = False, self.close_s or 0
        if self.close_s and not self.bar.winfo_manager():
            self.bar.pack(side='bottom', fill='x')

    def _drive(self):
        fn = self.drive[1]
        self.close()
        fn()

    def _tick(self):
        if not self.alive:
            return
        if self.close_s and not self.writing:
            if not self.hover:
                self.left -= STEP_MS / 1000
            if self.left <= 0:
                self.close()
                return
            wd = self.bar.winfo_width()
            self.bar.delete('all')
            self.bar.create_rectangle(0, 0, wd * (1 - self.left / self.close_s), BAR_H, fill=ACC, width=0)
        self._ticks += 1
        if not self.writing and self._ticks % max(1, round(ON_TOP_S * 1000 / STEP_MS)) == 0:
            keep_on_top(self.win)            # (back over the game if it came over it; not while typing in it)
        self.win.after(STEP_MS, self._tick)

    @property
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        if self.alive:
            self.win.destroy()

    # ---- in the game (ingamehud.py: the game draws it; F9 opens a box there to type the comment in)
    def snapshot(self):
        """What it says, for the game: {id, kind, title, title_c, what, line, note, text (the box's), max, msg (text,
        colour), left, span, keys [(key, words, primary, action)]}; None once closed."""
        if not self.alive:
            return None
        from .nextcard import KEYS
        s = self._said
        keys = [(KEYS['comment'], _('COMMENT'), not self.drive, 'comment')]
        if self.drive:
            keys.insert(0, (KEYS['drive'], self.drive[0], True, 'drive'))
        keys.append((KEYS['close'], _('CLOSE'), False, 'close'))
        running = self.close_s and not self.writing
        return {'id': '%x' % id(self), 'kind': 'comment', 'title': s['title'], 'title_c': s['title_c'], 'what': s['what'],
                'line': _('How did it go? One line.'), 'note': s['note'], 'text': self.var.get(), 'max': MAX,
                'msg': self._msg, 'left': self.left * 1000 if running else None, 'span': (self.close_s or 0) * 1000,
                'keys': keys}

    def act(self, action, text=''):
        """A key pressed in the game for it: 'typing' (its box opened there: the card stays), 'comment' (typed and
        Enter: sent), 'drive' (its DRIVE), 'close'."""
        if action == 'typing':
            self.stay()
        elif action == 'comment':
            self.var.set(' '.join(str(text or '').split())[:MAX])
            self._send()
        elif action == 'drive' and self.drive:
            self._drive()
        elif action == 'close':
            self.close()

    def in_game(self, on):
        """The game draws it (on): its window put away, the card itself goes on (its time, its buttons' keys)."""
        if not self.alive:
            return
        if on:
            hide_window(self.win)
        elif self.win.state() == 'withdrawn':
            show_window(self.win)            # (not over the game in front filling its screen: kept back then)


class CommentUI:
    """App's part (a mixin): the offer after a run, the card, sending it. Needs root, api, s, sub_l, overlay,
    refresh_board, flush_leagues."""

    comment_offer = None          # {on, what, kind, short}: the last run that can be commented on
    comment_card = None
    _comment_said = None          # on -> what I sent (the box starts from it)

    def offer_comment(self, on, what, kind, short, title=None, show=True):
        """A run whose result is on the server: a comment on it offered. on: what it is on ('2026-11-15/1',
        'event:12/0'); what: the run in a few words ('SS1 · Peïra Cava · 3:21.456'); kind: a key of NOTE (who sees it);
        short: its name ('SS1'); title: the card's top line; show: False when the next-daily card shows it
        (app.py _offer_next)."""
        self.comment_offer = {'on': on, 'what': what, 'kind': kind, 'short': short}
        if show:
            self.open_comment(title=title)

    def _card_at(self):
        """Under the timer (where the next-daily card goes), or the screen's top left."""
        ov = getattr(getattr(self, 'overlay', None), 'win', None)
        try:
            if ov is not None and ov.winfo_ismapped():
                return ov.winfo_x(), ov.winfo_y() + ov.winfo_height() + 8
        except tk.TclError:
            pass
        return 60, 60

    def open_comment(self, offer=None, title=None, drive=None, title_fg=WHITE):
        """The card for the run offered: its box, SEND, DRIVE on the other daily (drive: (label, fn)), CLOSE."""
        o = offer or self.comment_offer
        if not o or not self.s.get('token'):
            return None
        for card in (self.comment_card, getattr(self, 'next_card', None)):
            if card is not None and card.alive:
                card.close()
        said = self._comment_said = self._comment_said or {}
        try:
            card = self.comment_card = CommentCard(
                self.root, self._card_at(), title or _('%s · YOUR RUN') % o['short'], o['what'],
                NOTE.get(o['kind'], NOTE['league']), said.get(o['on'], ''), lambda text: self._send_comment(o, text, card),
                drive=drive, title_fg=title_fg)
        except (tk.TclError, AttributeError, TypeError):
            return None                      # (no window to put it on: the tests' bare apps)
        if o['on'] not in said:              # what I sent before (another time, another PC)
            def ask():
                try:
                    text = self.api.my_comments([o['on']]).get(o['on'])
                except ApiError:
                    return
                if text:
                    _c().ui(self.root, card.prefill, text)
            threading.Thread(target=ask, daemon=True).start()
        return card

    def _send_comment(self, o, text, card):
        def go():
            try:
                if o['on'].startswith('event:'):
                    self.flush_leagues()    # (the stage's own result first: a comment goes only on a stage the server has)
                self.api.comment(o['on'], text)
                err = None
            except ApiError as e:
                err = str(e)
            _c().ui(self.root, self._comment_sent, o, text, card, err)
        threading.Thread(target=go, daemon=True).start()

    def _comment_sent(self, o, text, card, error):
        if error:
            card.failed(error)
            return
        self._comment_said = self._comment_said or {}
        self._comment_said[o['on']] = text
        card.sent(text)
        self.sub_l.configure(text=(_('Comment sent: %s') % with_comment(o['what'], text, 80)) if text else _('Comment taken back.'))
        if o['kind'] == 'daily':
            self.refresh_board()
