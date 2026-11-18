"""What's new: after each update, a screen over the app with what changed, as the server's changelog says it
(server/src/changelog.js, GET /api/changelog/<version>?since=<the version seen last>):

  the backdrop  the version's photo, blurred and dark, over the whole of the app's window, a soft shadow under the card;
  the card      in the middle: the photo with WHAT'S NEW IN <version>, the headline and the day over it; each change
                with its tag (NEW, IMPROVED, FIXED, NOTE); under them, along a line down the left, every version
                skipped since the one seen last, each with its headline and changes; FULL CHANGELOG ON THE WEBSITE
                and LET'S DRIVE along the bottom. It scrolls (mouse wheel, arrows, Page Up / Down) when it is taller
                than the window. Escape, Enter, the ✕, a click beside it or LET'S DRIVE close it.

It is drawn inside the app's own window, over everything in it (a frame, not a window of its own): it moves and sizes
with the app, is never lost behind the app or the game, and has no Windows title bar.

Shown once per version (settings 'seenVersion'; this screen from 0.1.6 on, a simpler window from 0.0.31). A new
install doesn't get one (nothing is new to them); an app that updated itself, or one already signed in that someone
updated by hand, does. The server offline: asked again at the next start. No entry for the version: nothing shown,
and not asked again. Opened again any time (reopen): SETTINGS › About › WHAT'S NEW, the "UPDATED TO ... · WHAT'S NEW"
bar; then with the versions before it (the website's changelog when the server can't be reached).
"""
import datetime as dt
import threading
import tkinter as tk
import webbrowser
from tkinter import font as tkfont

from . import i18n, photos
from .api import ApiError
from .i18n import N_, _

DEFAULT_PHOTO = 'dailies'
CARD_W, CARD_MIN_W = 660, 440     # the card's width at 96 dpi: as wide as this, the window allowing; never narrower
MARGIN = 28                       # around the card in the window (at 96 dpi)
HERO_H = 270                      # the photo at the top of the card, at most (at 96 dpi; taller for a long headline)
BACK, SURFACE = '#050506', '#0E0E11'
LINE, LINE2 = '#1F1F23', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#6B6B74'
ACC, GOOD, SLOW = '#E30613', '#30D158', '#FF9F0A'
FONT, FONT_C = i18n.font('Bahnschrift'), i18n.font('Bahnschrift SemiBold Condensed')
# A change's kind (server KINDS): its tag's words, its colour, filled or a hairline
KINDS = {
    'new': (N_('NEW'), ACC, True),
    'better': (N_('IMPROVED'), SOFT, False),
    'fix': (N_('FIXED'), GOOD, False),
    'note': (N_('NOTE'), SLOW, False),
}
SLIDE = (8, 16)                   # its arrival: this many steps, ms apart, rising into place


def _c():
    from . import app
    return app


def _ver(v):
    return tuple(int(x) for x in str(v).split('.') if x.isdigit())


def due(seen, version, updated, known):
    """Show the screen for `version`? seen: the version whose screen was seen last ('' or None: none yet);
    updated: started by the updater; known: this PC has used the app before (signed in). A test build (four parts)
    whose seen version is ahead of it: the screen came under the release the build led to (0.1.5.42's said 0.1.6,
    before the server named a test build's screen by its own number): shown again, asked of the server, which says
    when there is nothing new."""
    if seen:
        if len(_ver(version)) >= 4 and _ver(seen) > _ver(version):
            return True
        return _ver(version) > _ver(seen)
    return bool(updated or known)


def check(app, version, updated):
    """At start: show what's new in `version` (and in the versions skipped since the one seen last) when it is due
    (in a thread: the server is asked first)."""
    seen = app.s.get('seenVersion')
    if not due(seen, version, updated, bool(app.s.get('steamId') or app.s.get('token'))):
        if not seen:
            _seen(app, version)                  # (a new install: this version counts as seen)
        return

    def go():
        try:
            entry = app.api.changelog(version, since=seen or None)
        except ApiError as e:
            if e.code == 404:                    # nothing written for it: not asked again
                _c().ui(app.root, _seen, app, version)
            return                               # (offline: the next start asks again)
        if entry and entry.get('changes'):
            _c().ui(app.root, show, app, entry, seen or None)
    threading.Thread(target=go, daemon=True).start()


def reopen(app, version=None):
    """SETTINGS › About › WHAT'S NEW, the UPDATED TO bar: what's new in this version and the ones before it (asked of
    the server, in a thread); the website's changelog when the server can't be reached."""
    from . import __version__
    version = version or __version__
    if getattr(app, '_whatsnew_asking', False):
        return
    app._whatsnew_asking = True

    def go():
        try:
            entry = app.api.changelog(version, since='0')
        except ApiError:
            entry = None
        app._whatsnew_asking = False
        if entry and entry.get('changes'):
            _c().ui(app.root, show, app, entry, '0')
        else:
            _c().ui(app.root, webbrowser.open, url(app, version))
    threading.Thread(target=go, daemon=True).start()


def url(app, version):
    """The website's changelog at this version."""
    return '%s/changelog#v%s' % (app.api.site, version)


def _seen(app, version):
    from . import settings
    app.s['seenVersion'] = version
    try:
        settings.save(app.s)
    except OSError:
        pass


def show(app, entry, since=None):
    """The screen (on the Tk thread); seen as soon as it is up. since: the version seen before ('0': opened again,
    the earlier versions are simply the ones before)."""
    _seen(app, entry['version'])
    old = getattr(app, '_whatsnew', None)
    if old is not None:
        old.close()
    app._whatsnew = WhatsNew(app, entry, since)
    return app._whatsnew


def day(iso):
    """'15 November 2026' (in the app's language) for '2026-11-15'."""
    try:
        return i18n.strftime(_('%-d %B %Y'), dt.date.fromisoformat(str(iso)).timetuple())
    except (TypeError, ValueError):
        return str(iso or '')


# ---------------------------------------------------------------- the pictures (None without Pillow or the photo)
def hero(widget, key, w, h):
    """The photo cut to the top of the card, darker towards the bottom so the headline reads on any photo."""
    img = photos.compose(key, w, h)
    if img is None:
        return None
    from PIL import Image, ImageDraw, ImageTk
    shade = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=(8, 8, 10, int(215 * max(0.0, (t - 0.25) / 0.75) ** 1.2)))
    return ImageTk.PhotoImage(Image.alpha_composite(img.convert('RGBA'), shade).convert('RGB'), master=widget)


def backdrop(widget, key, w, h, box=None):
    """The window behind the card: the photo blurred and dark, washed red from the left (as the card on screen), and a
    soft shadow under the card (box: its x, y, w, h). Made small and blown up: quick at any size."""
    s = 6
    sw, sh = max(4, w // s), max(4, h // s)
    img = photos.compose(key, sw, sh)
    if img is None:
        return None
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageTk
    img = ImageEnhance.Brightness(img.filter(ImageFilter.GaussianBlur(2.5))).enhance(0.5).convert('RGBA')
    over = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for x in range(sw):
        t = x / max(1, sw - 1)
        if t < 0.55:
            d.line([(x, 0), (x, sh)], fill=photos.RED + (int(80 * (1 - t / 0.55) ** 1.6),))
    for y in range(sh):                                # darker towards the bottom
        t = y / max(1, sh - 1)
        d.line([(0, y), (sw, y)], fill=(5, 5, 6, int(150 * t ** 1.5)))
    img = Image.alpha_composite(img, over)
    if box:
        x, y, bw, bh = (v / s for v in box)
        shadow = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rectangle([x - 1, y, x + bw + 1, y + bh + 2], fill=(0, 0, 0, 210))
        img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(3)))
    return ImageTk.PhotoImage(img.convert('RGB').resize((w, h), Image.BICUBIC), master=widget)


# ---------------------------------------------------------------- the screen
class WhatsNew:
    def __init__(self, app, entry, since=None):
        self.app, self.entry, self.since = app, entry, since
        self.root = root = app.root
        self.k = root.winfo_fpixels('1i') / 96
        self.key = entry.get('photo') if photos.has(entry.get('photo')) else DEFAULT_PHOTO
        self.card = self.cv = self._back_img = self._hero_img = None
        self._size = None
        self._fonts = {}
        self._after = None
        self.win = w = tk.Frame(root, bg=BACK)
        w.place(x=0, y=0, relwidth=1, relheight=1)
        self.back = tk.Canvas(w, bg=BACK, highlightthickness=0, bd=0)
        self.back.place(x=0, y=0, relwidth=1, relheight=1)
        self.back.bind('<Button-1>', lambda _e: self.close())         # a click beside the card
        self._wheel_on(w)
        self._wheel_on(self.back)
        self._layout(slide=True)
        w.bind('<Configure>', self._resized)
        w.tkraise()
        root.after(700, self._on_top)
        root.after(30, self._focus)

    # ---- size and place
    def _room(self):
        """The window's size, as the card is laid out in it (a window not shown yet: as if it had room)."""
        k = self.k
        least_w, least_h = int((CARD_MIN_W + 2 * MARGIN) * k), int(420 * k)
        try:
            return max(self.root.winfo_width(), least_w), max(self.root.winfo_height(), least_h)
        except tk.TclError:
            return least_w, least_h

    def _resized(self, _e=None):
        if self._after is not None:
            self.root.after_cancel(self._after)
        self._after = self.root.after(120, self._relayout)

    def _relayout(self):
        self._after = None
        if self.alive and self._room() != self._size:
            self._layout()
            self._focus()

    def _layout(self, slide=False):
        """The card at the window's size (made again when it changes), in its middle, on the backdrop."""
        k = self.k
        W, H = self._size = self._room()
        self._gen = getattr(self, '_gen', 0) + 1           # (a slide under way stops: this card is placed anew)
        cw = round(max(CARD_MIN_W * k, min(CARD_W * k, W - 2 * MARGIN * k)))   # (rounded: 659.9 px on a screen of 95.97 dpi is 660)
        at = self.cv.yview()[0] if self.cv is not None else 0.0
        if self.card is not None:
            self.card.destroy()
        self.card = card = tk.Frame(self.win, bg=SURFACE, highlightthickness=1, highlightbackground=LINE2)
        foot = self._footer(card)
        foot.pack(side='bottom', fill='x')
        self.cv = cv = tk.Canvas(card, width=cw, bg=SURFACE, highlightthickness=0, bd=0, takefocus=1,
                                 yscrollincrement=max(1, round(20 * k)))
        content_h = self._draw(cv, cw)
        foot.update_idletasks()
        room = H - int(2 * MARGIN * k) - foot.winfo_reqheight() - 2
        view_h = max(int(160 * k), min(content_h, room))
        self.scrolls = content_h > view_h
        cv.configure(height=view_h, scrollregion=(0, 0, cw, content_h), yscrollcommand=self._scrolled)
        cv.pack(side='top', fill='x')
        for key in ('<Escape>', '<Return>', '<KP_Enter>'):
            cv.bind(key, lambda _e: self.close())
        for key, n, what in (('<Down>', 2, 'units'), ('<Up>', -2, 'units'), ('<Next>', 1, 'pages'), ('<Prior>', -1, 'pages'),
                             ('<space>', 1, 'pages')):
            cv.bind(key, lambda _e, n=n, what=what: self._scroll(n, what))
        cv.bind('<Home>', lambda _e: cv.yview_moveto(0))
        cv.bind('<End>', lambda _e: cv.yview_moveto(1))
        for wd in (card, cv, foot) + tuple(_all(foot)):
            self._wheel_on(wd)
        card.update_idletasks()
        ch = card.winfo_reqheight()
        x, y = max(0, (W - card.winfo_reqwidth()) // 2), max(0, (H - ch) // 2)
        self._back_img = backdrop(self.back, self.key, W, H, (x, y, card.winfo_reqwidth(), ch))
        self.back.delete('all')
        if self._back_img is not None:
            self.back.create_image(0, 0, image=self._back_img, anchor='nw')
        if at:
            cv.yview_moveto(at)
        if slide:
            self._slide(x, y, 0, self._gen)
        else:
            card.place(x=x, y=y)

    def _slide(self, x, y, step, gen):
        """Rising into place, quick and slowing at the end."""
        if not self.alive or gen != self._gen:
            return
        n, ms = SLIDE
        ease = 1 - (1 - step / n) ** 3
        self.card.place(x=x, y=y + round(24 * self.k * (1 - ease)))
        if step < n:
            self.root.after(ms, self._slide, x, y, step + 1, gen)

    def _on_top(self):
        """Over everything in the window: a part of the app made after it (a view opened meanwhile) goes under it."""
        if not self.alive:
            return
        kids = [w for w in self.root.winfo_children() if not isinstance(w, tk.Toplevel)]
        if kids and kids[-1] is not self.win:
            self.win.tkraise()
        self.root.after(700, self._on_top)

    def _focus(self):
        if self.alive:
            try:
                self.cv.focus_set()
            except tk.TclError:
                pass

    # ---- the card's words
    def _draw(self, cv, cw):
        """The photo with the headline, the changes, the versions before it, on the canvas cw wide. -> its height."""
        k, e = self.k, self.entry
        pad = round(28 * k)
        # the headline over the photo: its words first, measured, then the photo as tall as they need
        title = (e.get('title') or 'ACR Daily %s' % e['version']).upper()
        kick = cv.create_text(pad + 8 * k, 0, text=_("WHAT'S NEW IN %s") % e['version'], anchor='nw', fill=WHITE,
                              font=(FONT_C, 11), tags='kick')
        head = cv.create_text(pad, 0, text=title, anchor='nw', width=cw - 2 * pad, fill=WHITE, font=(FONT_C, 25),
                              tags='title')
        when = cv.create_text(pad, 0, text=day(e.get('date')), anchor='nw', fill=SOFT, font=(FONT, 9), tags='date')
        hk, ht, hd = (_h(cv, i) for i in (kick, head, when))
        gap1, gap2 = round(12 * k), round(6 * k)
        hero_h = round(min(cw * 0.42, HERO_H * k))
        top = hero_h - round(22 * k) - (hk + gap1 + ht + gap2 + hd)
        if top < round(58 * k):                           # (a long headline: a taller photo)
            hero_h += round(58 * k) - top
            top = round(58 * k)
        cv.move(kick, 0, top + 3 * k)
        cv.move(head, 0, top + hk + gap1)
        cv.move(when, 0, top + hk + gap1 + ht + gap2)
        x0, y0, x1, y1 = cv.bbox(kick)
        cv.create_rectangle(x0 - 8 * k, y0 - 3 * k, x1 + 8 * k, y1 + 3 * k, fill=ACC, width=0, tags='kickbg')
        cv.tag_lower('kickbg', kick)
        self._hero_img = hero(cv, self.key, cw, hero_h)
        if self._hero_img is not None:
            cv.create_image(0, 0, image=self._hero_img, anchor='nw', tags='photo')
        else:
            cv.create_rectangle(0, 0, cw, hero_h, fill='#141417', width=0, tags='photo')
        cv.tag_lower('photo')
        cv.create_rectangle(0, 0, round(5 * k), hero_h, fill=ACC, width=0)     # the red edge, as the cards'
        cv.create_text(pad, round(22 * k), text=i18n.spaced('ACR DAILY'), anchor='w', fill=WHITE, font=(FONT_C, 9))
        self._close_button(cv, cw)
        # the changes
        y = hero_h + round(24 * k)
        y = self._lines(cv, pad, y, cw - pad, e, big=True)
        # the versions before it
        earlier = e.get('earlier') or []
        if earlier:
            y += round(16 * k)
            label = _('EARLIER VERSIONS') if self.since in (None, '0') else _('ALSO NEW SINCE %s') % self.since
            t = cv.create_text(pad, y, text=label, anchor='nw', fill=MUTED, font=(FONT_C, 10), tags='earlier')
            x0, y0, x1, y1 = cv.bbox(t)
            cv.create_line(x1 + 12 * k, (y0 + y1) / 2, cw - pad, (y0 + y1) / 2, fill=LINE2)
            y = y1 + round(18 * k)
            for i, older in enumerate(earlier):
                y = self._older(cv, pad, y, cw - pad, older, last=i == len(earlier) - 1)
        return y + round(14 * k)

    def _font(self, spec):
        if spec not in self._fonts:
            self._fonts[spec] = tkfont.Font(root=self.root, font=spec)
        return self._fonts[spec]

    def _chip_w(self, font):
        """The tags' width: the widest of them in this language (all of them as wide, the words beside in line)."""
        return max(self._font(font).measure(_(words)) for words, _col, _fill in KINDS.values()) + round(14 * self.k)

    def _lines(self, cv, x0, y, x1, entry, big):
        """An entry's changes from y: its tag (or a red square for an entry without them) and its words. -> y after."""
        k = self.k
        kinds = entry.get('kinds') or []
        font, chip_font = ((FONT, 10), (FONT_C, 9)) if big else ((FONT, 9), (FONT_C, 8))
        tagged = any(kd in KINDS for kd in kinds)
        col = self._chip_w(chip_font) if tagged else round(6 * k)
        gap = round(14 * k)
        line_h = self._font(font).metrics('linespace')
        chip_h = self._font(chip_font).metrics('linespace') + round(4 * k)
        for i, words in enumerate(entry.get('changes') or []):
            kd = kinds[i] if i < len(kinds) else None
            t = cv.create_text(x0 + col + gap, y, text=words, anchor='nw', width=max(60, x1 - x0 - col - gap),
                               fill=SOFT if big else FG2, font=font, tags='line')
            if kd in KINDS:
                name, colour, filled = KINDS[kd]
                cy = y + max(0, (line_h - chip_h) / 2)
                cv.create_rectangle(x0, cy, x0 + col, cy + chip_h, fill=colour if filled else '',
                                    outline='' if filled else colour, width=1, tags='chip')
                cv.create_text(x0 + col / 2, cy + chip_h / 2, text=_(name), fill=WHITE if filled else colour,
                               font=chip_font, tags=('chip', 'chip-' + kd))
            else:
                s = round(6 * k)
                cy = y + (line_h - s) / 2
                cv.create_rectangle(x0, cy, x0 + s, cy + s, fill=ACC, width=0)
            y += max(_h(cv, t), chip_h if kd in KINDS else 0) + round((11 if big else 7) * k)
        return y

    def _older(self, cv, x0, y, x1, e, last):
        """A version before it, on the line down the left: its number and day, its headline, its changes."""
        k = self.k
        rail, cx = x0 + round(5 * k), x0 + round(26 * k)
        meta = cv.create_text(cx, y, text='%s   ·   %s' % (e['version'], day(e.get('date'))), anchor='nw', fill=MUTED,
                              font=(FONT_C, 10), tags='older')
        hm = _h(cv, meta)
        dot_y, r = y + hm / 2, round(5 * k)
        cv.create_oval(rail - r, dot_y - r, rail + r, dot_y + r, fill=SURFACE, outline=FG2, width=max(1, round(2 * k)))
        y2 = y + hm + round(2 * k)
        if e.get('title'):
            t = cv.create_text(cx, y2, text=e['title'], anchor='nw', width=x1 - cx, fill=WHITE, font=(FONT_C, 14),
                               tags='older-title')
            y2 += _h(cv, t) + round(8 * k)
        y2 = self._lines(cv, cx, y2, x1, e, big=False)
        nxt = y2 + round(12 * k)
        if not last:                                      # down to the next one's dot
            cv.create_line(rail, dot_y + r + 3 * k, rail, nxt + hm / 2 - r - 3 * k, fill=LINE2, width=max(1, round(2 * k)))
        return nxt

    def _close_button(self, cv, cw):
        k = self.k
        s, m = round(30 * k), round(12 * k)
        cv.create_rectangle(cw - m - s, m, cw - m, m + s, fill=BACK, outline=LINE2, tags=('close', 'close-bg'))
        cv.create_text(cw - m - s / 2, m + s / 2, text='✕', fill=WHITE, font=(FONT, 11), tags=('close', 'close-x'))
        cv.tag_bind('close', '<Button-1>', lambda _e: self.close())
        cv.tag_bind('close', '<Enter>', lambda _e: (cv.itemconfigure('close-bg', fill=ACC, outline=ACC),
                                                    cv.configure(cursor='hand2')))
        cv.tag_bind('close', '<Leave>', lambda _e: (cv.itemconfigure('close-bg', fill=BACK, outline=LINE2),
                                                    cv.configure(cursor='')))

    def _footer(self, card):
        k = self.k
        foot = tk.Frame(card, bg=SURFACE)
        tk.Frame(foot, bg=LINE, height=1).pack(fill='x')
        row = tk.Frame(foot, bg=SURFACE)
        row.pack(fill='x', padx=round(28 * k), pady=(round(14 * k), round(16 * k)))
        self.drive = self.app._btn(row, _("LET'S DRIVE"), self.close, primary=True, surface=SURFACE)
        self.drive.pack(side='right')
        self.more = self.app._link(row, _('Full changelog on the website ›'), self.website)
        self.more.configure(bg=SURFACE)
        self.more.pack(side='left')
        return foot

    # ---- scrolling
    def _scrolled(self, first, last):
        """The thin bar down the card's right edge: where in it the view is (none when it all fits)."""
        cv = self.cv
        cv.delete('bar')
        first, last = float(first), float(last)
        if not self.scrolls or last - first >= 0.999:
            return
        k = self.k
        top, h = cv.canvasy(0), cv.winfo_height()
        w = int(cv.cget('width'))
        cv.create_rectangle(w - 6 * k, top + 6 * k + first * (h - 12 * k), w - 3 * k, top + 6 * k + last * (h - 12 * k),
                            fill=FG2, width=0, tags='bar')

    def _scroll(self, n, what='units'):
        if self.alive and self.scrolls:
            self.cv.yview_scroll(n, what)
        return 'break'

    def _wheel(self, e):
        if getattr(e, 'num', None) in (4, 5):             # (X11)
            return self._scroll(-3 if e.num == 4 else 3)
        return self._scroll(-3 if e.delta > 0 else 3)

    def _wheel_on(self, widget):
        """The wheel scrolls the card, never the app's pages under it (their bind_all: 'break' stops it)."""
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            widget.bind(seq, self._wheel)

    # ---- going
    @property
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def website(self):
        webbrowser.open(url(self.app, self.entry['version']))
        self.close()

    def close(self):
        if self.alive:
            self.win.destroy()
        if getattr(self.app, '_whatsnew', None) is self:
            self.app._whatsnew = None


def _h(cv, item):
    """An item's height on the canvas."""
    b = cv.bbox(item)
    return (b[3] - b[1]) if b else 0


def _all(widget):
    """A widget's children, theirs, and so on."""
    for w in widget.winfo_children():
        yield w
        yield from _all(w)
