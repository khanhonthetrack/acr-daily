"""The app's INBOX, mixed into App (app.py) like the LEAGUES view (leagueui.py): notices from ACR Daily (a challenge
came in, a cup match is ready, a result) and short 1:1 messages between drivers (server src/social.js).

INBOX in the header counts what is unread, asked for every few minutes (INBOX_EVERY_MIN; every minute while its view is
open) and after the sign-in. Its view takes the place of the cards and the timing sheet: the latest notices (read once
shown) and conversations; one opened shows its messages and a reply box. The rest is the website's: challenging a driver
to a 1V1 (/1v1), cups (/cups), a new conversation, blocking and reporting (/inbox).
"""
import threading
import time
import tkinter as tk
import webbrowser

from .api import ApiError

INBOX_EVERY_MIN = 5
NOTICES_SHOWN = 3              # notices listed in the view (the rest: the website)
THREADS_SHOWN = 4              # conversations listed
MAX_LEN = 500                  # a message's length at most (the server's MSG.maxLen)


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


def site_url(base, path):
    """A page of the website: the server's own address, under the website's name."""
    return base.replace('://acr-daily.acr-daily-server.workers.dev', '://acrdaily.com') + path


def ago(ms, now_ms):
    """How long ago a time (ms) was: 'now', '12 min', '3 h', '2 d', then its date."""
    s = max(0, (now_ms - (ms or 0)) / 1000)
    if s < 60:
        return 'now'
    if s < 3600:
        return '%d min' % (s // 60)
    if s < 86400:
        return '%d h' % (s // 3600)
    if s < 7 * 86400:
        return '%d d' % (s // 86400)
    return time.strftime('%d %b', time.localtime(ms / 1000))


def ref_page(ref):
    """What a notice is about, on the website ('h2h:<id>', 'cup:<id>'): (link text, path), or None."""
    kind, _, rid = (ref or '').partition(':')
    if kind == 'h2h':
        return '1V1s  ›', '/1v1'
    if kind == 'cup' and rid:
        return 'The cup  ›', '/cup/' + rid
    return None


def one_line(text, n=60):
    """A message on one line, cut to n characters."""
    t = ' '.join((text or '').split())
    return t if len(t) <= n else t[:n - 1].rstrip() + '…'


class InboxUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    inbox_view = False             # the window shows the INBOX view (in the place of the cards and the timing sheet)
    inbox_unread = 0               # INBOX's count: notices and messages unread
    inbox = None                   # /api/inbox: the notices and the conversations
    inbox_with = None              # the conversation open in the view: the other driver's steamId
    inbox_thread = None            # /api/inbox/with/<steamId>: its messages
    inbox_msg = ''                 # why the inbox could not be loaded
    inbox_note = None              # under the reply box: (text, colour), e.g. why a message was not sent
    _inbox_sending = False
    _inbox_hid = ()                # what the view put away of the timing sheet: (widget, its pack options)
    _inbox_reading = frozenset()   # notices on their way to being read

    # -------------------------------------------------------------- layout
    def _build_inbox_button(self, head):
        """INBOX in the header, the unread count beside it in red."""
        c = _c()
        f = tk.Frame(head, bg=c.BG)
        f.pack(side='right', padx=(0, 18))
        self.inbox_b = self._link(f, 'INBOX', self.toggle_inbox_view)
        self.inbox_b.configure(font=(c.FONT_C, 11))
        self.inbox_b.pack(side='left')
        self.inbox_n = tk.Label(f, text='', bg=c.ACC, fg=c.WHITE, font=(c.FONT_C, 9), padx=4, cursor='hand2')
        self.inbox_n.bind('<Button-1>', lambda _e: self.toggle_inbox_view())

    def _build_inbox_box(self):
        c = _c()
        self.inbox_box = tk.Frame(self.root, bg=c.BG)
        self._inbox_var = tk.StringVar(self.root)    # the reply being written (kept while the view is drawn again)

    def _inbox_badge(self):
        """INBOX: white while its view is open; the unread count beside it."""
        b = getattr(self, 'inbox_b', None)
        if b is None:
            return
        c = _c()
        b._fg = c.WHITE if self.inbox_view else c.FG2
        b.configure(fg=b._fg)
        n = self.inbox_unread
        if n:
            self.inbox_n.configure(text=str(n) if n < 100 else '99+')
            self.inbox_n.pack(side='left', padx=(5, 0))
        else:
            self.inbox_n.pack_forget()

    def toggle_inbox_view(self, on=None):
        on = (not self.inbox_view) if on is None else on
        if on == self.inbox_view:
            return
        if not on:
            self._inbox_leave()
            (self.league_box if self.league_view else self.daily_box).pack(fill='x', before=self._status_frame)
            self._render_strip()
            return
        self.inbox_view = True
        self._inbox_hid = [(w, w.pack_info()) for w in (self.board_l, self.tree) if w.winfo_manager() == 'pack']
        for w in (self.daily_box, self.league_box, self.board_l, self.tree):
            w.pack_forget()
        self._render_strip()                         # (put away too: it sits over the dailies)
        self.inbox_box.pack(fill='both', expand=True, before=self._status_frame)
        self.inbox_with = self.inbox_thread = self.inbox_note = None
        self._inbox_badge()
        self._render_inbox()
        self.refresh_inbox()

    def _inbox_leave(self):
        """The view closes: the timing sheet comes back (the cards are the caller's: the dailies or the leagues)."""
        if not self.inbox_view:
            return
        self.inbox_view = False
        self.inbox_box.pack_forget()
        for w, info in self._inbox_hid:
            w.pack(**info)
        self._inbox_hid = ()
        self.inbox_with = self.inbox_thread = self.inbox_note = None
        self._inbox_badge()

    def open_page(self, path):
        """A page of the website, in the browser."""
        if self.api.configured:
            webbrowser.open(site_url(self.api.base, path))

    # -------------------------------------------------------------- the view
    def _render_inbox(self):
        if not self.inbox_view:
            return
        c = _c()
        box = self.inbox_box
        typing = self._inbox_typing()
        for w in box.winfo_children():
            w.destroy()
        if not self.s.get('token'):
            self._lbl(box, 'Sign in with Steam (below) to read ACR Daily\'s notices and your messages.', fg=c.SOFT,
                      font=(c.FONT, 10), wraplength=400).pack(anchor='w', padx=20, pady=(16, 6))
            self._link(box, 'The inbox on the website  ›', lambda: self.open_page('/inbox')).pack(anchor='w', padx=20,
                                                                                                    pady=(0, 14))
            self._rule(box, padx=20)
            return
        if self.inbox_with:
            self._render_conversation(box, typing)
        else:
            self._render_inbox_list(box)

    def _render_inbox_list(self, box):
        """The latest notices (marked read as they are shown here), then the conversations."""
        c = _c()
        top = tk.Frame(box, bg=c.BG)
        top.pack(fill='x', padx=20, pady=(14, 4))
        self._k(top, 'From ACR Daily').pack(side='left')
        self._link(top, 'Cups  ›', lambda: self.open_page('/cups')).pack(side='right')
        self._link(top, 'Challenge a driver  ›', lambda: self.open_page('/1v1')).pack(side='right', padx=(0, 14))
        r = self.inbox
        if r is None:
            self._lbl(box, self.inbox_msg or 'Loading…', fg=c.SOFT, font=(c.FONT, 10), wraplength=400).pack(
                anchor='w', padx=20, pady=(4, 14))
            self._rule(box, padx=20)
            return
        now = time.time() * 1000
        notices, threads = r.get('notices') or [], r.get('threads') or []
        shown = notices[:NOTICES_SHOWN]
        for n in shown:
            self._notice_row(box, n, now)
        if not notices:
            self._lbl(box, 'Nothing yet. Challenges, cup matches and their results are told here.', fg=c.MUTED,
                      font=(c.FONT, 9), wraplength=400).pack(anchor='w', padx=20, pady=(2, 12))
        self._rule(box, padx=20)
        head = tk.Frame(box, bg=c.BG)
        head.pack(fill='x', padx=20, pady=(14, 4))
        self._k(head, 'Messages').pack(side='left')
        for t in threads[:THREADS_SHOWN]:
            self._thread_row(box, t, now)
        if not threads:
            self._lbl(box, 'No messages yet. Write to a driver from the inbox on the website; their answers come here.',
                      fg=c.MUTED, font=(c.FONT, 9), wraplength=400).pack(anchor='w', padx=20, pady=(2, 12))
        self._rule(box, padx=20)
        foot = tk.Frame(box, bg=c.BG)
        foot.pack(fill='x', padx=20, pady=(8, 10))
        more = max(0, len(notices) - NOTICES_SHOWN) + max(0, len(threads) - THREADS_SHOWN)
        self._link(foot, ('%d more on the website  ›' % more) if more else 'New message on the website  ›',
                   lambda: self.open_page('/inbox')).pack(side='left')
        if self.inbox_msg:                           # (the last refresh failed: what is shown is older)
            self._lbl(foot, self.inbox_msg, fg=c.MUTED, font=(c.FONT, 8)).pack(side='right')
        self._inbox_read([n['id'] for n in shown if not n.get('read') and n.get('id') is not None])

    def _notice_row(self, box, n, now):
        """A notice: a red bar while it is new; a link to what it is about (the website, or LEAGUES: a match to drive)."""
        c = _c()
        new, text = not n.get('read'), n.get('body') or ''
        row = tk.Frame(box, bg=c.BG)
        row.pack(fill='x', padx=(17, 20))
        tk.Frame(row, bg=c.ACC if new else c.BG, width=3).pack(side='left', fill='y', padx=(0, 14))
        body = tk.Frame(row, bg=c.BG)
        body.pack(side='left', fill='x', expand=True, pady=(5, 5))
        self._lbl(body, text, fg=c.WHITE if new else c.SOFT, font=(c.FONT, 9), wraplength=370).pack(anchor='w')
        sub = tk.Frame(body, bg=c.BG)
        sub.pack(fill='x')
        self._lbl(sub, ago(n.get('created'), now), fg=c.MUTED, font=(c.FONT, 8)).pack(side='left')
        page = ref_page(n.get('ref'))
        if page:
            self._link(sub, page[0], lambda p=page[1]: self.open_page(p)).pack(side='right')
        if 'LEAGUES' in text:                        # ("...drive it from ACR Daily's LEAGUES view")
            self._link(sub, 'LEAGUES  ›', lambda: self.toggle_league_view(True)).pack(side='right', padx=(0, 14))

    def _thread_row(self, box, t, now):
        """A conversation: the other driver, how many of their messages are new, the last one (a click opens it)."""
        c = _c()
        who, last, n = t.get('with') or {}, t.get('last') or {}, t.get('unread') or 0
        row = tk.Frame(box, bg=c.BG, cursor='hand2')
        row.pack(fill='x', padx=(17, 20))
        tk.Frame(row, bg=c.ACC if n else c.BG, width=3).pack(side='left', fill='y', padx=(0, 14))
        body = tk.Frame(row, bg=c.BG, cursor='hand2')
        body.pack(side='left', fill='x', expand=True, pady=(5, 5))
        top = tk.Frame(body, bg=c.BG, cursor='hand2')
        top.pack(fill='x')
        ws = [row, body, top, self._lbl(top, who.get('name') or 'Driver', font=(c.FONT_C, 14), fg=c.WHITE if n else c.SOFT,
                                        cursor='hand2')]
        ws[-1].pack(side='left')
        if n:
            ws.append(self._lbl(top, '%d NEW' % n, font=(c.FONT, 8, 'bold'), fg=c.ACC, cursor='hand2'))
            ws[-1].pack(side='left', padx=(10, 0))
        if t.get('blocked'):
            ws.append(self._lbl(top, 'BLOCKED', font=(c.FONT, 8, 'bold'), fg=c.MUTED, cursor='hand2'))
            ws[-1].pack(side='left', padx=(10, 0))
        ws.append(self._lbl(top, ago(last.get('created'), now), fg=c.MUTED, font=(c.FONT, 8), cursor='hand2'))
        ws[-1].pack(side='right')
        ws.append(self._lbl(body, ('You: ' if last.get('mine') else '') + one_line(last.get('body')),
                            fg=c.FG2 if n else c.MUTED, font=(c.FONT, 9), cursor='hand2'))
        ws[-1].pack(anchor='w')
        for w in ws:
            w.bind('<Button-1>', lambda _e, sid=who.get('steamId'): self.open_conversation(sid))

    def _render_conversation(self, box, typing):
        """The messages with one driver (theirs on the left, mine on the right), the reply box under them."""
        c = _c()
        r = self.inbox_thread or {}
        known = next((t.get('with') for t in (self.inbox or {}).get('threads') or []
                      if (t.get('with') or {}).get('steamId') == self.inbox_with), None)
        who = r.get('with') or known or {}
        top = tk.Frame(box, bg=c.BG)
        top.pack(fill='x', padx=20, pady=(14, 0))
        self._link(top, '‹  INBOX', self.close_conversation).pack(side='left')
        self._link(top, 'Open on the website  ›', lambda s=self.inbox_with: self.open_page('/inbox?with=' + s)).pack(side='right')
        self._lbl(box, who.get('name') or 'Driver', font=(c.FONT_C, 20), fg=c.WHITE).pack(anchor='w', padx=20, pady=(4, 0))
        if r.get('blocked'):
            self._lbl(box, 'You block this driver: they can\'t write to you. Unblock on the website.', fg=c.MUTED,
                      font=(c.FONT, 8)).pack(anchor='w', padx=20)
        # the reply box at the bottom, the messages above it in the room left
        note = self.inbox_note or ('', c.MUTED)
        self._inbox_note_l = self._lbl(box, note[0], fg=note[1], font=(c.FONT, 8), wraplength=400)
        self._inbox_note_l.pack(side='bottom', anchor='w', padx=20, pady=(0, 10))
        reply = tk.Frame(box, bg=c.BG)
        reply.pack(side='bottom', fill='x', padx=20, pady=(8, 4))
        self._btn(reply, 'SEND  ›', self.inbox_send, primary=True).pack(side='right', padx=(8, 0))
        e = self.inbox_entry = tk.Entry(reply, textvariable=self._inbox_var, bg=c.PANEL, fg=c.WHITE, insertbackground=c.WHITE,
                                        relief='flat', font=(c.FONT, 10), highlightthickness=1,
                                        highlightbackground=c.LINE2, highlightcolor=c.FG2)
        e.pack(side='left', fill='x', expand=True, ipady=4)
        e.bind('<Return>', lambda _e: self.inbox_send())
        if typing:
            e.focus_set()
        t = tk.Text(box, bg=c.BG, fg=c.SOFT, font=(c.FONT, 10), wrap='word', relief='flat', borderwidth=0,
                    highlightthickness=0, height=8, padx=0, pady=4, cursor='arrow', selectbackground=c.PANEL2)
        t.tag_configure('who', foreground=c.MUTED, font=(c.FONT, 8), spacing1=8)
        t.tag_configure('mine', foreground=c.WHITE, justify='right', lmargin1=60, lmargin2=60)
        t.tag_configure('theirs', rmargin=60)
        t.tag_configure('note', foreground=c.MUTED, font=(c.FONT, 9))
        msgs, now = r.get('messages'), time.time() * 1000
        if msgs is None:
            t.insert('end', self.inbox_msg or 'Loading…', ('note',))
        elif not msgs:
            t.insert('end', 'No messages yet: write the first one below.', ('note',))
        for m in msgs or []:
            side = 'mine' if m.get('mine') else 'theirs'
            t.insert('end', '%s · %s\n' % ('You' if m.get('mine') else who.get('name') or 'Driver',
                                           ago(m.get('created'), now)), ('who', side))
            t.insert('end', (m.get('body') or '') + '\n', (side,))
        t.configure(state='disabled')
        t.pack(fill='both', expand=True, padx=20, pady=(6, 0))
        t.see('end')
        self.inbox_text = t

    def _inbox_typing(self):
        """Is the reply box being written in? (It keeps the keyboard when the view is drawn again.)"""
        e = getattr(self, 'inbox_entry', None)
        try:
            return bool(e is not None and e.winfo_exists() and self.root.focus_get() is e)
        except (KeyError, tk.TclError):            # (focus_get on some of Tk's own windows)
            return False

    def _inbox_say(self, text, colour):
        """The line under the reply box (kept while the view is drawn again)."""
        self.inbox_note = (text, colour)
        lbl = getattr(self, '_inbox_note_l', None)
        if lbl is not None and lbl.winfo_exists():
            lbl.configure(text=text, fg=colour)

    def open_conversation(self, steam_id):
        if not steam_id:
            return
        for t in (self.inbox or {}).get('threads') or []:
            if (t.get('with') or {}).get('steamId') == steam_id:
                t['unread'] = 0                      # (read as it opens: the server marks them)
        self.inbox_with, self.inbox_thread, self.inbox_note = steam_id, None, None
        self._inbox_var.set('')
        self._render_inbox()
        self.refresh_inbox()

    def close_conversation(self):
        """Back to the list (asked for again: it may have changed meanwhile)."""
        self.inbox_with, self.inbox_thread, self.inbox_note = None, None, None
        self._render_inbox()
        self.refresh_inbox()

    # -------------------------------------------------------------- data
    def refresh_unread(self):
        """What is unread, for INBOX (the periodic timer, the sign-in); the whole inbox while its view is open. Signed
        out: nothing."""
        if not self.api.configured or not self.s.get('token'):
            self.inbox = self.inbox_thread = self.inbox_with = None
            self._set_unread(0)
            self._render_inbox()
            return
        if self.inbox_view:
            self.refresh_inbox()
            return

        def go():
            try:
                n = self.api.inbox_unread()
            except ApiError:
                return                               # (offline, or a server without the inbox: the count stays)
            _c().ui(self.root, self._set_unread, n)
        threading.Thread(target=go, daemon=True).start()

    def _set_unread(self, n):
        self.inbox_unread = int(n or 0) if self.s.get('token') else 0   # (signed out since it was asked for: none)
        self._inbox_badge()

    def refresh_inbox(self):
        """The view's data: the notices and the conversations, or the conversation open (and then the unread count:
        opening it read their messages)."""
        if not self.api.configured or not self.s.get('token'):
            return
        who = self.inbox_with

        def go():
            try:
                if who:
                    r = self.api.inbox_with(who)
                    try:
                        n = self.api.inbox_unread()
                    except ApiError:
                        n = None
                else:
                    r = self.api.inbox()
                    n = (r or {}).get('unread')
                _c().ui(self.root, self._set_inbox, who, r, '', n)
            except ApiError as e:
                _c().ui(self.root, self._set_inbox, who, None, 'Inbox: %s' % e, None)
        threading.Thread(target=go, daemon=True).start()

    def _set_inbox(self, who, r, msg, unread):
        if not self.s.get('token'):                  # (signed out since it was asked for)
            return
        if r is not None:
            if not who:
                self.inbox = r
            elif who == self.inbox_with:
                self.inbox_thread = r
        if unread is not None:
            self._set_unread(unread)
        if who == self.inbox_with:                   # (still the one on screen)
            self.inbox_msg = msg
            self._render_inbox()

    def _inbox_read(self, ids):
        """Notices shown: read, on the server, then in INBOX's count."""
        ids = [i for i in ids if i not in self._inbox_reading]
        if not ids:
            return
        self._inbox_reading = self._inbox_reading | set(ids)

        def go():
            try:
                self.api.inbox_read(ids)
                _c().ui(self.root, self._notices_read, ids, True)
            except ApiError:
                _c().ui(self.root, self._notices_read, ids, False)
        threading.Thread(target=go, daemon=True).start()

    def _notices_read(self, ids, ok):
        self._inbox_reading = self._inbox_reading - set(ids)
        if not ok:
            return                                   # (still new: read the next time they are shown)
        k = 0
        for n in (self.inbox or {}).get('notices') or []:
            if n.get('id') in ids and not n.get('read'):
                n['read'], k = True, k + 1
        self._set_unread(max(0, self.inbox_unread - k))

    # -------------------------------------------------------------- writing
    def inbox_send(self):
        """SEND (or Enter): the reply box's message to the driver of the conversation open."""
        c = _c()
        to, body = self.inbox_with, self._inbox_var.get().strip()
        if not to or not body or self._inbox_sending:
            return
        if len(body) > MAX_LEN:
            self._inbox_say('Not sent: %d characters at most (this one has %d).' % (MAX_LEN, len(body)), c.BAD)
            return
        self._inbox_sending = True
        self._inbox_say('Sending…', c.MUTED)

        def go():
            try:
                self.api.inbox_send(to, body)
                _c().ui(self.root, self._inbox_sent, to, body, None)
            except ApiError as e:
                _c().ui(self.root, self._inbox_sent, to, body, e)
        threading.Thread(target=go, daemon=True).start()

    def _inbox_sent(self, to, body, e):
        c = _c()
        self._inbox_sending = False
        if to != self.inbox_with:                    # (another conversation open since)
            if e is not None:
                self.sub_l.configure(text='Your message was not sent: %s' % e)
            return
        if e is not None:                            # (the message stays in the box, to send again)
            self._inbox_say('Not sent: %s.' % str(e).rstrip('.'), c.BAD)
            return
        if self._inbox_var.get().strip() == body:
            self._inbox_var.set('')
        if self.inbox_thread is not None:
            self.inbox_thread.setdefault('messages', []).append({'id': None, 'mine': True, 'body': body,
                                                                 'created': time.time() * 1000})
        self.inbox_note = None
        self._render_inbox()
