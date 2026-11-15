"""A comment on a run, as on RallySimFans: after a daily, a time trial run or a league stage, a line on how it went
("lost the rear in the hairpin before the split", "the game froze at the finish"), sent to the server
(server/src/comments.js). Who sees it:
  a daily, a time trial stage: everyone, with the driver's time on the timing sheet (the app's, the website's) and, for
  a daily, in Discord's results of the day;
  a league event's stage (cup and 1V1 matches too): only whoever runs it (the league's owner and admins, a cup's
  maker; ACR Daily's admins for its own and for 1V1s), told in their inbox.

Offered once the run's result is on the server (CommentUI.offer_comment): a 'COMMENT ON SS1  ›' link in the footer
after what the app says of the run, and a COMMENT button on the next-daily card (nextcard.py). Either opens
CommentDialog: one line of at most MAX characters, what happens to it, SEND / CANCEL (Enter, Escape). What was sent
before fills the box (asked of the server once per run). Sending it empty takes it back.
"""
import threading
import tkinter as tk

from . import i18n
from .api import ApiError
from .i18n import _

MAX = 200          # characters (the server's COMMENT.maxLen)
CELL = 44          # characters of it on the app's timing sheet, in the driver's cell
BG, PANEL, LINE2 = '#0A0A0B', '#141417', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC, BAD = '#E30613', '#FF453A'
FONT, FONT_C = i18n.font('Bahnschrift'), i18n.font('Bahnschrift SemiBold Condensed')

# who sees it, said under the box
NOTE = {
    'daily': _("Shown with your time on the daily's timing sheet: in the app, on the website and in Discord's results."),
    'tt': _('Shown with your best time on the time trial board, in the app and on the website.'),
    'league': _("Only you and whoever runs the event see it: the league's owner and admins."),
    'cup': _("Only you and the cup's maker see it (ACR Daily's admins for its own cups)."),
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


class CommentDialog:
    """The box: a small window of its own, over everything (the game too), the line typed in it sent with SEND."""

    def __init__(self, root, what, note, text, on_send):
        self.on_send = on_send
        self.win = w = tk.Toplevel(root)
        w.title('ACR Daily')
        w.configure(bg=BG, highlightthickness=1, highlightbackground=ACC)
        w.attributes('-topmost', True)
        w.resizable(False, False)
        tk.Frame(w, bg=ACC, height=2).pack(fill='x')
        body = tk.Frame(w, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(12, 14))
        tk.Label(body, text=_('YOUR COMMENT'), bg=BG, fg=ACC, font=(FONT_C, 12), anchor='w').pack(anchor='w')
        tk.Label(body, text=what, bg=BG, fg=WHITE, font=(FONT_C, 17), anchor='w').pack(anchor='w', pady=(2, 0))
        tk.Label(body, text=_('How did it go? One line.'), bg=BG, fg=FG2, font=(FONT, 9), anchor='w').pack(anchor='w', pady=(10, 4))
        self.var = tk.StringVar(value=(text or '')[:MAX])
        self.entry = tk.Entry(body, textvariable=self.var, width=60, bg=PANEL, fg=WHITE, insertbackground=WHITE, relief='flat',
                              font=(FONT, 11), highlightthickness=1, highlightbackground=LINE2, highlightcolor=FG2)
        self.entry.pack(fill='x', ipady=5)
        row = tk.Frame(body, bg=BG)
        row.pack(fill='x', pady=(4, 0))
        self.count = tk.Label(row, text='', bg=BG, fg=MUTED, font=(FONT, 8))
        self.count.pack(side='right')
        tk.Label(row, text=note + ' ' + _('Send it empty to take it back.'), bg=BG, fg=MUTED, font=(FONT, 8), anchor='w',
                 justify='left', wraplength=440).pack(side='left', anchor='w')
        self.msg = tk.Label(body, text='', bg=BG, fg=BAD, font=(FONT, 9), anchor='w', justify='left', wraplength=500)
        self.msg.pack(anchor='w', pady=(6, 0))
        btns = tk.Frame(body, bg=BG)
        btns.pack(fill='x', pady=(8, 0))
        self.send_b = self._button(btns, _('SEND'), self._send, primary=True)
        self.send_b.pack(side='left')
        self._button(btns, _('CANCEL'), self.close).pack(side='left', padx=(8, 0))
        self.busy = False
        self.touched = False
        self.var.trace_add('write', lambda *_a: self._changed())
        self._changed(touch=False)
        self.entry.bind('<Return>', lambda _e: self._send())
        w.bind('<Escape>', lambda _e: self.close())
        w.protocol('WM_DELETE_WINDOW', self.close)
        w.update_idletasks()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry('+%d+%d' % (max(0, (sw - w.winfo_reqwidth()) // 2), max(0, (sh - w.winfo_reqheight()) // 3)))
        w.after(60, self._focus)

    @staticmethod
    def _button(parent, text, cmd, primary=False):
        b = tk.Label(parent, text=text, font=(FONT_C, 11), padx=14, pady=4, cursor='hand2',
                     bg=WHITE if primary else BG, fg=BG if primary else SOFT,
                     highlightthickness=0 if primary else 1, highlightbackground=LINE2)
        b.bind('<Button-1>', lambda _e: cmd())
        b.bind('<Enter>', lambda _e: b.configure(bg=ACC, fg=WHITE) if primary else b.configure(bg=WHITE, fg=BG))
        b.bind('<Leave>', lambda _e: b.configure(bg=WHITE if primary else BG, fg=BG if primary else SOFT))
        return b

    def _focus(self):
        if self.alive:
            self.win.lift()
            self.win.focus_force()
            self.entry.focus_set()
            self.entry.icursor('end')

    def _changed(self, touch=True):
        v = self.var.get()
        if len(v) > MAX:                 # (a paste longer than that: cut; Tcl calls no trace from inside its own)
            v = v[:MAX]
            self.var.set(v)
        self.touched = self.touched or touch
        self.count.configure(text='%d / %d' % (len(v), MAX), fg=ACC if len(v) >= MAX else MUTED)

    def prefill(self, text):
        """What was sent before, once the server says: into the box, unless something was typed meanwhile."""
        if self.alive and text and not self.touched and not self.var.get():
            self.var.set(text[:MAX])
            self.touched = False
            self.entry.icursor('end')

    def _send(self):
        if self.busy or not self.alive:
            return
        self.set_busy(True)
        self.msg.configure(text=_('Sending...'), fg=FG2)
        self.on_send(' '.join(self.var.get().split()))

    def set_busy(self, busy):
        self.busy = busy
        self.send_b.configure(cursor='arrow' if busy else 'hand2')

    def failed(self, error):
        self.set_busy(False)
        if self.alive:
            self.msg.configure(text=_('Not sent: %s') % error, fg=BAD)

    @property
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        if self.alive:
            self.win.destroy()


class CommentUI:
    """App's part (a mixin): the offer after a run, the box, sending it. Needs root, api, s, sub_l, _status_bar, _link,
    refresh_board, refresh_tt_board, flush_leagues."""

    comment_offer = None          # {on, what, kind, short}: the last run that can be commented on
    _comment_link = None
    _comment_box = None
    _comment_said = None          # on -> what I sent (the box starts from it)

    def offer_comment(self, on, what, kind, short):
        """A run whose result is on the server: offer a comment on it. on: what it is on ('2026-11-15/1', 'tt:...',
        'event:12/0'); what: the run in a few words ('SS1 · Peïra Cava · 3:21.456'); kind: a key of NOTE (who sees it);
        short: the link's name for it ('SS1', 'TT2')."""
        self.comment_offer = {'on': on, 'what': what, 'kind': kind, 'short': short}
        bar = getattr(self, '_status_bar', None)
        if bar is None:                      # (no window built: the offer alone)
            return
        if self._comment_link is None:
            self._comment_link = self._link(bar, '', lambda: self.open_comment(), fg=WHITE)
        self._comment_link.configure(text=_('COMMENT ON %s  ›') % short)
        self._comment_link.pack(side='left', anchor='n', padx=(0, 14), pady=(1, 0))

    def open_comment(self, offer=None):
        o = offer or self.comment_offer
        if not o:
            return
        if not self.s.get('token'):
            self.sub_l.configure(text=_('Sign in with Steam to comment on your runs.'))
            return
        if self._comment_box is not None and self._comment_box.alive:
            self._comment_box.close()
        said = self._comment_said = self._comment_said or {}
        box = self._comment_box = CommentDialog(self.root, o['what'], NOTE.get(o['kind'], NOTE['league']), said.get(o['on'], ''),
                                                lambda text: self._send_comment(o, text, box))
        if o['on'] not in said:              # what I sent before (another time, another PC)
            def ask():
                try:
                    text = self.api.my_comments([o['on']]).get(o['on'])
                except ApiError:
                    return
                if text:
                    _c().ui(self.root, box.prefill, text)
            threading.Thread(target=ask, daemon=True).start()

    def _send_comment(self, o, text, box):
        def go():
            try:
                if o['on'].startswith('event:'):
                    self.flush_leagues()    # (the stage's own result first: a comment goes only on a stage the server has)
                self.api.comment(o['on'], text)
                err = None
            except ApiError as e:
                err = str(e)
            _c().ui(self.root, self._comment_sent, o, text, box, err)
        threading.Thread(target=go, daemon=True).start()

    def _comment_sent(self, o, text, box, error):
        if error:
            box.failed(error)
            return
        self._comment_said = self._comment_said or {}
        self._comment_said[o['on']] = text
        box.close()
        self.sub_l.configure(text=(_('Comment sent: %s') % with_comment(o['what'], text, 80)) if text else _('Comment taken back.'))
        if o['kind'] == 'daily':
            self.refresh_board()
        elif o['kind'] == 'tt':
            self.refresh_tt_board()
