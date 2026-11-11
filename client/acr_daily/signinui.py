"""Signing in, mixed into App (app.py) like the pages beside it: the app asks for the Steam account first. Until the
driver is signed in, a screen over the whole window (a photo, the logo, SIGN IN WITH STEAM) is all there is; once they
are, it goes and everything of their account is loaded (their card, credits, leagues, 1V1s, cups, the inbox, the time
trial). It comes back after Sign out, or when the server no longer knows the session (api.py drops the token).

Without a server set (a build from the source with none: SETUP.md) there is nothing to sign in to: no screen.
"""
import threading
import time
import tkinter as tk
from tkinter import messagebox

from . import __version__, photos
from .i18n import _


def _c():
    """The palette and helpers of app.py (imported late: app.py imports this module)."""
    from . import app
    return app


class SignInUI:
    # what an App has before anything sets its own (the tests build bare ones: App.__new__)
    _gate = None
    _signing_in = False

    def _needs_sign_in(self):
        return bool(self.api.configured and not self.s.get('token'))

    def _gate_check(self):
        """(from the tick, and as the account changes) The screen up while there is no account, gone once there is."""
        if self._needs_sign_in():
            if self._gate is None:
                self._show_gate()
        elif self._gate is not None:
            self._hide_gate()

    # -------------------------------------------------------------- the screen
    def _show_gate(self):
        c = _c()
        r = self.root
        k = r.winfo_fpixels('1i') / 96
        g = self._gate = tk.Frame(r, bg=c.BG)
        g.place(x=0, y=0, relwidth=1, relheight=1)
        g.lift()
        cv = self._gate_cv = tk.Canvas(g, bg=c.BG, highlightthickness=0, bd=0)
        cv.pack(fill='both', expand=True)
        box = tk.Frame(cv, bg=c.PANEL, highlightthickness=1, highlightbackground=c.LINE2)
        logo = getattr(self, '_logo_img', None)
        top = tk.Frame(box, bg=c.PANEL)
        top.pack(anchor='w', padx=28, pady=(26, 0))
        if logo:
            tk.Label(top, image=logo, bg=c.PANEL, bd=0).pack(side='left')
        tk.Label(top, text='ACR DAILY', bg=c.PANEL, fg=c.WHITE, font=(c.FONT_C, 26)).pack(side='left', padx=(14, 0))
        tk.Label(box, text=_('SIGN IN TO START'), bg=c.PANEL, fg=c.ACC, font=(c.FONT, 8, 'bold')).pack(anchor='w', padx=28, pady=(18, 4))
        tk.Label(box, text=_('ACR Daily runs on your Steam account: your times on the boards, your profile, credits, '
                           'leagues, 1V1s and cups. Steam opens in your browser to confirm it is you.'),
                 bg=c.PANEL, fg=c.SOFT, font=(c.FONT, 10), justify='left', anchor='w',
                 wraplength=round(380 * k)).pack(anchor='w', padx=28)
        self._gate_b = b = tk.Label(box, text=('  ' + _('SIGN IN WITH STEAM')), image=getattr(self, '_steam_img', None) or '',
                                    compound='left', bg=c.STEAM_BG, fg=c.WHITE, font=(c.FONT_C, 13), padx=16, pady=8,
                                    cursor='hand2')
        b.bind('<Button-1>', lambda _e: self.sign_in())
        b.bind('<Enter>', lambda _e: b.configure(bg=c.STEAM_HOVER))
        b.bind('<Leave>', lambda _e: b.configure(bg=c.STEAM_BG))
        b.pack(anchor='w', padx=28, pady=(20, 8))
        self._gate_msg = tk.Label(box, text='', bg=c.PANEL, fg=c.FG2, font=(c.FONT, 9), justify='left', anchor='w',
                                  wraplength=round(380 * k))
        self._gate_msg.pack(anchor='w', fill='x', padx=28)
        links = tk.Frame(box, bg=c.PANEL)
        links.pack(fill='x', padx=28, pady=(14, 22))
        for text, cmd in ((_('Website'), self.open_site), ('Discord', self.open_discord), (_('Quit'), lambda: self.quit(ask=False))):
            ln = self._link(links, text, cmd)
            ln.configure(bg=c.PANEL)
            ln.pack(side='left', padx=(0, 18))
        tk.Label(links, text='v%s' % __version__, bg=c.PANEL, fg=c.MUTED, font=(c.FONT, 8)).pack(side='right')
        if hasattr(self, '_lang_picker'):            # the language, before anything else (settingsui.py)
            self._lang_picker(links, c.PANEL).pack(side='right', padx=(0, 14))
        self._gate_box = cv.create_window(0, 0, window=box, anchor='w')
        cv.bind('<Configure>', lambda e: self._gate_later(e.width, e.height))
        self._gate_drawn(max(r.winfo_width(), 2), max(r.winfo_height(), 2))

    def _gate_later(self, w, h):
        """The window resized: the box moved now, the photo drawn again once it stops (a big photo takes a moment)."""
        cv = self._gate_cv
        cv.coords(self._gate_box, round(80 * self.root.winfo_fpixels('1i') / 96), h / 2)
        if getattr(self, '_gate_job', None):
            cv.after_cancel(self._gate_job)
        self._gate_job = cv.after(150, lambda: self._gate_drawn(w, h))

    def _gate_drawn(self, w, h):
        """The photo over the whole window (dark at the bottom, washed red from the left), the box on its left."""
        cv = getattr(self, '_gate_cv', None)
        if cv is None or not cv.winfo_exists():
            return
        k = self.root.winfo_fpixels('1i') / 96
        cv.delete('photo')
        img = photos.card(cv, 'dailies', w, h, True) if w > 2 and h > 2 else None
        if img is not None:
            cv._img = img
            cv.create_image(0, 0, image=img, anchor='nw', tags=('photo',))
            cv.tag_lower('photo')
        cv.coords(self._gate_box, round(80 * k), h / 2)

    def _hide_gate(self):
        g, self._gate = self._gate, None
        if getattr(self, '_gate_job', None) and g is not None and g.winfo_exists():
            g.after_cancel(self._gate_job)
        self._gate_job = None
        if g is not None and g.winfo_exists():
            g.destroy()
        self._gate_cv = None

    # -------------------------------------------------------------- signing in and out
    def sign_in(self):
        """Steam in the browser (api.login), once at a time; then everything of the account (_signed_in)."""
        if self._signing_in or self.s.get('token'):
            return
        if not self.api.configured:
            messagebox.showinfo('ACR Daily', _('No server is set yet. See SETUP.md.'))
            return
        self._signing_in = True
        self._gate_say(_('Waiting for Steam in your browser…'), busy=True)
        self.steam_b.configure(text=(' ' + _('WAITING FOR STEAM...')))
        ui = _c().ui
        self.api.login(lambda ok, info: ui(self.root, self._signed_in if ok else self._sign_in_failed, info))

    def _gate_say(self, text, busy=False, bad=False):
        c = _c()
        if self._gate is None:
            return
        self._gate_msg.configure(text=text, fg=c.BAD if bad else c.FG2)
        self._gate_b.configure(text=('  ' + _('WAITING FOR STEAM…')) if busy else ('  ' + _('SIGN IN WITH STEAM')), cursor='watch' if busy else 'hand2')

    def _sign_in_failed(self, why):
        self._signing_in = False
        self._account_ui()
        if self._gate is not None:
            self._gate_say(_('%s. Try again.') % str(why).rstrip('.'), bad=True)
        else:
            messagebox.showwarning('ACR Daily', why)

    def _signed_in(self, _name=None):
        """Signed in: the screen goes, HOME comes, and everything of the account is asked for."""
        self._signing_in = False
        self._hide_gate()
        self._account_ui()
        for fn in (self.refresh_board, self.refresh_leagues, self.refresh_credits, self.refresh_unread, self.refresh_driver,
                   self.refresh_home_extras):
            fn()
        self.refresh_tt(full=True)
        threading.Thread(target=self.api.flush, args=(self._runs_sent,), daemon=True).start()
        threading.Thread(target=self.flush_leagues, daemon=True).start()
        self._mark_tabs()
        if getattr(self, 'home_box', None) is not None:
            self.open_home()

    def sign_out(self):
        """Sign out (the driver's card, SETTINGS > Account): their things dropped, the sign-in screen back."""
        self.api.logout()
        self._set_credits(None)                   # (the account line, and no wager staked or offered any more)
        self._set_driver(None)                    # (no driver's card)
        self.h2h_data = self.cups_data = None
        self.refresh_leagues()
        self.refresh_unread()                     # (no count, no messages)
        self._account_ui()                        # (the sign-in screen: at the next tick, _gate_check)

    def refresh_home_extras(self):
        """(any thread) The challenges and the cups, for HOME's tiles (their badges), whichever tab is open."""
        if not self.api.configured or not self.s.get('token'):
            return
        ui = _c().ui
        from .api import ApiError

        def go():
            for kind, ask in (('h2h', self.api.h2h), ('cup', self.api.cups)):
                try:
                    ui(self.root, self._set_tab_extras, kind, ask(), '')
                except ApiError:
                    pass
                time.sleep(0.2)
        threading.Thread(target=go, daemon=True).start()
