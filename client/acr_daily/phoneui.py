"""ON YOUR PHONE, mixed into App (app.py): the page on screen, on the website, as a QR code the phone's camera opens.

The app is the PC's (it times runs next to the game, and its narrowest window is for a second screen, not a phone);
the phone's is the website, made for one: the timing sheets, the live map, the standings, the inbox. The app's links
opened them on the PC only, its notifications are Windows' (a UI review, Nov 2026): this hands the page over. Opened
from the help menu (?) and the status bar (On your phone), for the view on screen (phone_page): a daily's timing sheet,
the time trial, the event picked under RALLIES, the cups, the inbox, the driver's own page.
"""
import tkinter as tk

from . import qr
from .i18n import _


def _c():
    from . import app
    return app


class PhoneUI:
    _phone_win = None

    def phone_page(self):
        """(path on the website, what it is) for what is on screen."""
        sid = (self.s or {}).get('steamId')
        if getattr(self, 'inbox_view', False):
            return '/inbox', _('Your inbox')
        if getattr(self, 'profile_view', False) and sid:
            return '/d/%s' % sid, _('Your driver page')
        if getattr(self, 'tt_view', False):
            return '/tt', _('The time trial: its timing sheets')
        if getattr(self, 'league_view', False):
            kind = getattr(self, 'league_kind', None)
            if kind == 'cup':
                return '/cups', _('The cups')
            if kind == 'h2h':
                return '/1v1', _('Your 1V1s')
            ev = getattr(self, 'league_sel', None)
            if isinstance(ev, int) or (isinstance(ev, str) and ev.isdigit()):
                return '/e/%s' % ev, _('This event: its standings and live map')
            return '/leagues', _('The rallies and championships')
        slot = getattr(self, 'active', None)
        if slot in (1, 2) and slot in (getattr(self, 'dailies', None) or {}):
            return '/#ss%d' % slot, _("Today's dailies: SS%d's timing sheet and live map") % slot
        return '/', _("Today's dailies: timing sheets and live map")

    def open_phone(self):
        """A window with the QR code of the page on screen, its address, and what the phone gets there."""
        c = _c()
        if not self.api.configured:
            return
        old = self._phone_win
        if old is not None and old.winfo_exists():
            old.destroy()
        path, what = self.phone_page()
        url = self.api.site + path
        k = self.root.winfo_fpixels('1i') / 96
        w = self._phone_win = tk.Toplevel(self.root, bg=c.BG)
        w.title(_('On your phone'))
        w.resizable(False, False)
        w.transient(self.root)
        box = tk.Frame(w, bg=c.BG)
        box.pack(padx=round(24 * k), pady=round(20 * k))
        tk.Label(box, text=_('ON YOUR PHONE'), bg=c.BG, fg=c.ACC_TEXT, font=(c.FONT, 8, 'bold'), anchor='w').pack(anchor='w')
        tk.Label(box, text=what, bg=c.BG, fg=c.WHITE, font=(c.FONT_C, 16), anchor='w', justify='left',
                 wraplength=round(320 * k)).pack(anchor='w', pady=(round(4 * k), round(12 * k)))
        rows = qr.matrix(url)
        cell = max(3, round(5 * k))
        quiet = 4 * cell
        side = len(rows) * cell + 2 * quiet
        cv = tk.Canvas(box, width=side, height=side, bg='#FFFFFF', highlightthickness=0, bd=0)
        for y, row in enumerate(rows):
            x = 0
            while x < len(row):                  # (a run of dark modules as one rectangle)
                if row[x]:
                    end = x
                    while end < len(row) and row[end]:
                        end += 1
                    cv.create_rectangle(quiet + x * cell, quiet + y * cell, quiet + end * cell, quiet + (y + 1) * cell,
                                        fill='#000000', width=0)
                    x = end
                else:
                    x += 1
        cv.pack(anchor='w')
        tk.Label(box, text=_("Point your phone's camera at it to open the page on acrdaily.com: the timing sheets, "
                             'the live map, the standings and your inbox are all there, made for a phone.'),
                 bg=c.BG, fg=c.SOFT, font=(c.FONT, 9), anchor='w', justify='left',
                 wraplength=round(320 * k)).pack(anchor='w', pady=(round(12 * k), round(4 * k)))
        tk.Label(box, text=url, bg=c.BG, fg=c.MUTED, font=(c.FONT, 8), anchor='w').pack(anchor='w')
        row = tk.Frame(box, bg=c.BG)
        row.pack(fill='x', pady=(round(12 * k), 0))
        said = tk.Label(row, text='', bg=c.BG, fg=c.GOOD, font=(c.FONT, 8))

        def copy():
            w.clipboard_clear()
            w.clipboard_append(url)
            said.configure(text=_('Copied'))
        close = self._btn(row, _('CLOSE'), w.destroy, primary=True)
        close.pack(side='right')
        self._link(row, _('Copy the link'), copy).pack(side='left')
        said.pack(side='left', padx=(round(10 * k), 0))
        w.bind('<Escape>', lambda _e: w.destroy())
        w.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - w.winfo_reqheight()) // 3)
        w.geometry('+%d+%d' % (max(0, x), max(0, y)))
        close.focus_set()
        return w
