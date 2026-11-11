"""What's new: on the first start of a new version, a window with that version's changes, as the server's changelog
says them (server/src/changelog.js, GET /api/changelog/<version>): its photo (one of photos.py's, shipped in this app)
with the headline over it, a few short lines, MORE ON THE WEBSITE and LET'S DRIVE. From app 0.0.31 on.

Shown once per version (settings 'seenVersion'). A new install doesn't get one (nothing is new to them); an app that
updated itself, or one already signed in that someone updated by hand, does. The server offline: asked again at the
next start. No entry for the version: nothing shown, and not asked again.
"""
import threading
import tkinter as tk
import webbrowser

from . import photos
from .api import ApiError

W, PHOTO_H = 540, 240
DEFAULT_PHOTO = 'dailies'


def _c():
    from . import app
    return app


def _ver(v):
    return tuple(int(x) for x in str(v).split('.') if x.isdigit())


def due(seen, version, updated, known):
    """Show the window for `version`? seen: the version whose window was seen last ('' or None: none yet);
    updated: started by the updater; known: this PC has used the app before (signed in)."""
    if seen:
        return _ver(version) > _ver(seen)
    return bool(updated or known)


def check(app, version, updated):
    """At start: show what's new in `version` when it is due (in a thread: the server is asked first)."""
    seen = app.s.get('seenVersion')
    if not due(seen, version, updated, bool(app.s.get('steamId') or app.s.get('token'))):
        if not seen:
            _seen(app, version)                  # (a new install: this version counts as seen)
        return

    def go():
        try:
            entry = app.api.changelog(version)
        except ApiError as e:
            if e.code == 404:                    # nothing written for it: not asked again
                _c().ui(app.root, _seen, app, version)
            return                               # (offline: the next start asks again)
        if entry and entry.get('changes'):
            _c().ui(app.root, show, app, entry)
    threading.Thread(target=go, daemon=True).start()


def _seen(app, version):
    from . import settings
    app.s['seenVersion'] = version
    try:
        settings.save(app.s)
    except OSError:
        pass


def show(app, entry):
    """The window (on the Tk thread); seen as soon as it is up."""
    _seen(app, entry['version'])
    return WhatsNew(app, entry)


def banner(widget, key):
    """The photo cut to the banner, darker from a fifth of the way down so the headline reads on any photo, as a Tk
    image (None without Pillow or without the photo)."""
    img = photos.compose(key, W, PHOTO_H)
    if img is None:
        return None
    from PIL import Image, ImageDraw, ImageTk
    shade = Image.new('RGBA', (W, PHOTO_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for y in range(PHOTO_H):
        t = y / (PHOTO_H - 1)
        d.line([(0, y), (W, y)], fill=(8, 8, 10, int(205 * max(0.0, (t - 0.2) / 0.8) ** 1.1)))
    return ImageTk.PhotoImage(Image.alpha_composite(img.convert('RGBA'), shade).convert('RGB'), master=widget)


class WhatsNew:
    def __init__(self, app, entry):
        c = _c()
        self.app, self.entry = app, entry
        self.win = w = tk.Toplevel(app.root)
        w.title("ACR Daily · What's new")
        w.configure(bg=c.BG)
        w.resizable(False, False)
        w.transient(app.root)
        w.bind('<Escape>', lambda _e: self.close())
        # the photo, the headline over its dark fade
        self.banner = cv = tk.Canvas(w, width=W, height=PHOTO_H, bg=c.PANEL, highlightthickness=0, bd=0)
        cv.pack(fill='x')
        img = banner(cv, entry.get('photo') if photos.has(entry.get('photo')) else DEFAULT_PHOTO)
        if img is not None:
            cv.create_image(0, 0, image=img, anchor='nw')
            cv.image = img
        cv.create_rectangle(0, 0, 6, PHOTO_H, fill=c.ACC, width=0)            # the red edge, as the cards'
        title = entry.get('title') or 'ACR Daily %s' % entry['version']
        cv.create_text(26, PHOTO_H - 20, text=title.upper(), anchor='sw', width=W - 52, fill=c.WHITE,
                       font=(c.FONT_C, 22), tags='title')
        top = (cv.bbox('title') or (0, PHOTO_H - 50, 0, 0))[1]
        # the version on a red tag (red words alone vanish on a red car)
        cv.create_text(34, top - 12, text="WHAT'S NEW IN %s" % entry['version'], anchor='sw', fill=c.WHITE,
                       font=(c.FONT_C, 12), tags='kick')
        x0, y0, x1, y1 = cv.bbox('kick') or (34, top - 30, 160, top - 12)
        cv.create_rectangle(x0 - 8, y0 - 3, x1 + 8, y1 + 3, fill=c.ACC, width=0, tags='kickbg')
        cv.tag_lower('kickbg', 'kick')
        # the changes
        body = tk.Frame(w, bg=c.BG)
        body.pack(fill='x', padx=26, pady=(18, 4))
        for line in entry.get('changes') or []:
            row = tk.Frame(body, bg=c.BG)
            row.pack(fill='x', pady=4)
            tk.Frame(row, bg=c.ACC, width=6, height=6).pack(side='left', anchor='n', pady=(7, 0), padx=(0, 12))
            tk.Label(row, text=line, bg=c.BG, fg=c.SOFT, font=(c.FONT, 10), justify='left', anchor='w',
                     wraplength=W - 70).pack(side='left', fill='x')
        # the buttons
        foot = tk.Frame(w, bg=c.BG)
        foot.pack(fill='x', padx=26, pady=(14, 22))
        self.drive = app._btn(foot, "LET'S DRIVE", self.close, primary=True)
        self.drive.pack(side='right')
        self.more = app._btn(foot, 'MORE ON THE WEBSITE', self.website)
        self.more.pack(side='right', padx=(0, 10))
        self._place()
        w.lift()
        try:
            w.attributes('-topmost', True)       # (in front of the app, which the updater brings up too)
            w.after(1500, lambda: w.winfo_exists() and w.attributes('-topmost', False))
            w.focus_force()
        except tk.TclError:
            pass

    def _place(self):
        """Over the middle of the app's window."""
        w, root = self.win, self.app.root
        try:
            w.update_idletasks()
            x = root.winfo_rootx() + (root.winfo_width() - w.winfo_reqwidth()) // 2
            y = root.winfo_rooty() + (root.winfo_height() - w.winfo_reqheight()) // 3
            w.geometry('+%d+%d' % (max(0, x), max(0, y)))
        except tk.TclError:
            pass

    def website(self):
        webbrowser.open('%s/changelog#v%s' % (self.app.api.site, self.entry['version']))
        self.close()

    def close(self):
        if self.win.winfo_exists():
            self.win.destroy()
