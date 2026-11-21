"""ACR DAILY inside the game (0.2, a private build for now): the app's pages drawn by the game itself.

The app stays the brain (the server, the game's save, the timing, the judge); the game draws its pages. In the game's
main menu, MULTIPLAYER gets an ACR DAILY tile (the game's own tile); clicking it puts the game's menu away and shows
these pages in its place (mod/ACRDailyGhosts/Scripts/appui.lua). Esc or BACK TO THE GAME brings the game's menu back.

What the pages show goes to the mod as a tree of boxes, words, pictures and buttons (ingamekit.py makes them), in
%APPDATA%\\ACR Daily\\ingame-app.txt:

    ACRAPP 1 <seq> <rev>       seq: each write (the app is alive while it changes, at least every ALIVE_S)
    <json>                     rev: what the pages say: the mod draws them again only for a new one
    end <seq>

and what was done there comes back in ingame-app-events.txt: "ACRAPP <session>.<n> <what> [<id> [<words>]]" (open,
close, click <id>, text <id> <words>).

Each tab is a module, ig_<tab>.py (PAGES; ingamekit.py says what one has). A page is made from the app's own state and
its buttons call the app's own methods, as its window does: the same data, the same actions. Whatever the app would ask
or say in a window while the pages are on screen in the game is asked there instead (questions()): its window would sit
unseen behind the game. A question asked during a click shows in the game with YES / NO; YES does the click again with
that question answered yes (and a question that wants words, simpledialog.askstring, gets a box to type them in).
"""
import hashlib
import importlib
import json
import os
import time
import tkinter.messagebox as tk_messagebox

from . import liverally, photos, saveslot, settings
from .i18n import _
from .ingamekit import (ACC, BG, FG2, LINE2, MUTED, PANEL, PANEL2, PICS_DIR, SOFT, WHITE, box, btn, col, edit, empty,
                        kicker, primary, quiet, row, rule, scroll, size, sp, txt)

try:
    from PIL import Image
except ImportError:                     # (an app built without Pillow: no pictures in the game)
    Image = None

FILE = 'ingame-app.txt'
EVENTS_FILE = 'ingame-app-events.txt'
ALIVE_S = 1.0                           # written at least this often: the mod takes the app for gone after 4 s
TICK_MS = 100
NAV_MS = 30                             # the wheel / pad looked at this often while the pages are on screen
STATUS_S = 15.0                         # the app's status line shown over the pages this long after it changed

# the app's own nav (tabsui.NAV: RANKED in the builds that have it), then its icons as words
TABS = (('home', _('HOME')), ('daily', _('DAILIES')), ('tt', _('TIME TRIAL'))) + (
    (('live', _('RANKED')),) if liverally.ON else ()) + (
    ('comp', _('COMPETITIONS')), ('community', _('COMMUNITY')), ('inbox', _('INBOX')), ('profile', _('PROFILE')),
    ('settings', _('SETTINGS')))
# each tab's page (ig_<name>.py); a tab whose module isn't there yet says so, with OPEN THE WINDOW
PAGES = {'home': 'ig_home', 'daily': 'ig_daily', 'tt': 'ig_tt', 'live': 'ig_ranked', 'comp': 'ig_comp',
         'community': 'ig_community', 'inbox': 'ig_inbox', 'profile': 'ig_profile', 'settings': 'ig_settings',
         'prep': 'ig_prep'}                 # (DRIVE's set-up screen: no tab of its own)
FIRST_TAB = 'home'                      # (where ACR DAILY opens, as the app's window: HOME)


# the tile's picture: ACR DAILY's banner (photos/banner.webp, 1640 x 624), cut to the tile (532 x 175, drawn from twice
# that for sharpness). The game's label bar covers the tile from 55 % down: the logo's top and the headline ("YOUR DAILY
# COMPETITIVE PORTAL") sit above it. (left, top, bottom) in the banner; the width follows from the shape.
TILE_W, TILE_H = 532, 175
BANNER_CUT = (107, 150, 611)


def tile_picture():
    """-> the tile's picture (a PNG, made once), or None."""
    if Image is None:
        return None
    out_dir = os.path.join(settings.DIR, PICS_DIR)
    out = os.path.join(out_dir, 'tile-banner-%dx%d-%d-%d-%d.png' % ((TILE_W * 2, TILE_H * 2) + BANNER_CUT))
    if os.path.exists(out):
        return out
    try:
        im = Image.open(os.path.join(photos.DIR, 'banner.webp')).convert('RGB')
        x0, y0, y1 = BANNER_CUT
        w = round((y1 - y0) * TILE_W / TILE_H)
        x0 = max(0, min(x0, im.width - w))
        im = im.crop((x0, y0, x0 + w, y1)).resize((TILE_W * 2, TILE_H * 2), Image.LANCZOS)
        os.makedirs(out_dir, exist_ok=True)
        im.save(out + '.tmp', 'PNG')
        os.replace(out + '.tmp', out)
        return out
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------- a game pad's B (back)
_xinput = None
PAD_B = 0x2000


def pad_b_pressed(holder):
    """B on any game pad pressed since the last look (XInput; the game's UI moves and presses with the pad itself, but
    its B would go to the game's own menu): -> True once per press. holder keeps whether it was held (_pad_b)."""
    global _xinput
    import ctypes
    if _xinput is None:
        _xinput = False
        for dll in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
            try:
                _xinput = getattr(ctypes.windll, dll).XInputGetState
                break
            except (OSError, AttributeError):
                continue
    if not _xinput:
        return False

    class State(ctypes.Structure):
        _fields_ = [('packet', ctypes.c_uint32), ('buttons', ctypes.c_uint16), ('lt', ctypes.c_ubyte),
                    ('rt', ctypes.c_ubyte), ('lx', ctypes.c_short), ('ly', ctypes.c_short), ('rx', ctypes.c_short),
                    ('ry', ctypes.c_short)]
    held = False
    for i in range(4):
        st = State()
        if _xinput(i, ctypes.byref(st)) == 0 and st.buttons & PAD_B:
            held = True
    was, holder._pad_b = holder._pad_b, held
    return held and not was


# ---------------------------------------------------------------------- the files
class Writer:
    """ingame-app.txt, kept open and overwritten in place (opening a changed file costs the game ms: ghostui.open_kept)."""

    def __init__(self, path, opener=None):
        self.path = path
        self.opener = opener
        self.fh = None
        self.seq = 0
        self.rev = None
        self.size = 0
        self.last_t = -1e9

    def write(self, body, now=None):
        """body: the JSON text. Written when it changed, or ALIVE_S after the last write. -> whether it was."""
        now = time.monotonic() if now is None else now
        rev = hashlib.md5(body.encode('utf-8')).hexdigest()[:12]
        if rev == self.rev and now - self.last_t < ALIVE_S:
            return False
        self.seq += 1
        data = ('ACRAPP 1 %d %s\n%s\nend %d\n' % (self.seq, rev, body, self.seq)).encode('utf-8')
        if self.fh is None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.fh = self.opener(self.path) if self.opener else open(self.path, 'w+b')
        self.fh.seek(0)
        self.fh.write(data + b' ' * max(0, self.size - len(data)))
        self.fh.flush()
        self.size = len(data)
        self.rev, self.last_t = rev, now
        return True

    def close(self):
        if self.fh is not None:
            try:
                self.fh.close()
            except OSError:
                pass
        self.fh = None


class Events:
    """ingame-app-events.txt as the mod writes it: its last events, oldest first, one a line, "ACRAPP <session>.<n>
    <what> [<rest>]", ended by a line "end <session>.<n>" (a read in the middle of a write is skipped). poll() -> the
    events since the last look, in order, [(what, rest)]; the first look only notes where the file is (what it says
    was for an earlier opening)."""

    def __init__(self, path, opener=None):
        self.path = path
        self.opener = opener
        self.fh = None
        self.last = None             # (session, n) of the last event taken

    def poll(self):
        try:
            if self.fh is None:
                self.fh = self.opener(self.path) if self.opener else open(self.path, 'rb')
            self.fh.seek(0)
            raw = self.fh.read(65536)
        except (OSError, ValueError):
            self.close()
            if self.last is None:
                self.last = ('', 0)
            return []
        text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
        lines = text.split('\n')
        events, end = [], None
        for line in lines:
            line = line.rstrip()
            if line.startswith('end '):
                end = line[4:].strip()
                break
            parts = line.split(' ', 3)
            if len(parts) >= 3 and parts[0] == 'ACRAPP' and '.' in parts[1]:
                session, _sep, n = parts[1].partition('.')
                if n.isdigit():
                    events.append(((session, int(n)), parts[2], parts[3] if len(parts) > 3 else ''))
        if not events or end != '%s.%d' % events[-1][0]:
            return []                                  # (half written, or nothing: the next look)
        if self.last is None:
            self.last = events[-1][0]
            return []
        session, n = self.last
        new = [e for e in events if e[0][0] != session or e[0][1] > n]
        if new and new[-1][0][0] != session:           # (the mod made again: a new session's events are all new)
            new = [e for e in events if e[0][0] == new[-1][0][0]]
        self.last = events[-1][0]
        return [(what, rest) for _k, what, rest in new]

    def close(self):
        if self.fh is not None:
            try:
                self.fh.close()
            except OSError:
                pass
        self.fh = None


# ---------------------------------------------------------------------- the pages
class InGameApp:
    """The app's pages in the game: tick() (on the app's Tk loop, TICK_MS apart) writes them and does what was
    clicked."""

    def __init__(self, app, opener=None, reader=None):
        self.app = app
        self.writer = Writer(os.path.join(settings.DIR, FILE), opener)
        self.events = Events(os.path.join(settings.DIR, EVENTS_FILE), reader)
        self.tab = FIRST_TAB
        self.shown = False           # the pages on screen in the game (the mod says: open / close)
        self.dialog = None           # {'title', 'lines', 'go': (label, fn), 'cancel', 'field': hint} or None
        self.ask_open = False        # the app asks the mod to show its pages (a notice to read)
        self._mem = {}               # each page's own state (ig_*.py: mem(tab))
        self._mods = {}              # tab -> its module, or None (not made yet)
        self._running = None         # the click being done (a question asked meanwhile can do it again: questions())
        self._agreed = {}            # the questions answered for the click being done again: (title, words) -> answer
        self._dialog_words = ''      # what's typed in a question that wants words
        self._patched = False
        self.cmd = {'n': 0, 'do': None}   # a command to the mod, done once each (n): 'close'
        self._status_words, self._status_at = None, -1e9   # the status line: its words and since when (status())
        self.focus = ''              # the button the keyboard / wheel / pad is on (the mod says: across())
        self.prep = None             # DRIVE's set-up screen on, over the tab ({'kind', 'key'}: ig_prep.py)
        self._last_page = None      # the page last sent to the mod (across())
        self._pad_b = False          # B on a game pad held at the last look
        from .ingamedrive import Drives
        self.drives = Drives()       # DRIVE done in the running game (ingamedrive.py): its answers
        self.nav = None              # the game's menu buttons on the wheel / pad (ingamenav.py), once the pages show
        self._front_at, self._front = -1e9, False

    # ---- what a page has to hand
    def mem(self, tab):
        """A page's own state (a sub-tab picked, a draft...): kept while the app runs."""
        return self._mem.setdefault(tab, {})

    def ask(self, title, lines, go_label, fn, cancel=None):
        """A question over the page: go_label does fn."""
        self.dialog = {'title': title, 'lines': [str(x) for x in lines], 'go': (go_label, fn),
                       'cancel': cancel or _('CANCEL')}

    def say(self, title, lines):
        self.dialog = {'title': title, 'lines': [str(x) for x in lines], 'cancel': _('OK')}

    def game_up(self):
        """The game running with the mod in it (its pulse): a note is kept for the pages then, not put in a window."""
        try:
            return bool(self.app._pulse().alive())
        except Exception:
            return False

    def window(self, tab=None):
        """What stays in the app's window (picking a file...): the window on that tab, in front."""
        self.open_window(tab or self.tab)

    def module(self, tab):
        if tab not in self._mods:
            name = PAGES.get(tab)
            try:
                self._mods[tab] = importlib.import_module('.' + name, __package__) if name else None
            except ImportError:
                self._mods[tab] = None
        return self._mods[tab]

    # ---- the loop
    def tick(self):
        try:
            self.step()
        except Exception as e:      # (never the app's end: the next tick tries again)
            self.writer.close()
            self.events.close()
            try:
                from . import waiting
                waiting.note('in-game pages: %r' % (e,))
            except Exception:
                pass
        self.app.root.after(TICK_MS, self.tick)

    def step(self, now=None):
        self.questions()
        for what, rest in self.events.poll():
            self.event(what, rest)
        self.drives.check(now)
        if self.shown and not self.game_up():
            # the game gone (closed for a restart, crashed) with the pages on: they are not, and the app's questions go
            # to its window again (a review, 21 Nov 2026: they went to pages nobody saw and the set-up stopped)
            self.shown = False
        body = json.dumps(self.state(), ensure_ascii=False, separators=(',', ':'))
        self.writer.write(body, now)

    def event(self, what, rest):
        if what == 'open':
            self.shown = True
            self.ask_open = False
            self.opened()
        elif what == 'close':
            self.shown = False
            self.dialog = None
            self.prep = None                       # (DRIVE's set-up screen: not kept for the next opening)
        elif what == 'click':
            self.click(rest)
        elif what == 'text':
            id_, _sep, words = rest.partition(' ')
            self.text(id_, words)
        elif what == 'drive':
            self.drives.answer(rest)
        elif what == 'tab':                       # (Q / E in the game, as its own menu's tabs: appui.lua)
            self.switch_tab(-1 if rest.strip() == 'prev' else 1)
        elif what == 'focus':                     # (the button the keyboard / wheel / pad is on: across())
            self.focus = rest.strip()
        elif what == 'back':                      # (Esc on DRIVE's set-up screen: appui.lua)
            self.back()
        elif what == 'watchkey':                  # (WATCH: the keyboard's arrows over the stage, appui.lua)
            self.watch_key(rest.strip())
        elif what == 'arrow':                     # (the keyboard's Left / Right: across a page's columns)
            to = self.across(-1 if rest.strip() == 'left' else 1)
            if to:
                self.cmd = {'n': self.cmd['n'] + 1, 'do': 'focus', 'id': to}

    # ---- WATCH (watch.py, ig_watch.py)
    def watch_overlay(self):
        """The broadcast over the stage while watching (and its end: back in the game's menus after the stage)."""
        w = getattr(self.app, 'watch', None)
        if w is None or not w.on:
            return None
        menus = self._in_menus()
        if not menus:
            w.on_stage = True
        elif getattr(w, 'on_stage', False):             # (left the stage: WATCH is over)
            w.stop()
            w.on_stage = False
            return None
        if menus or not self.app._on_stage():          # (the Service Park: the game's own menu, nothing over it)
            return None
        from . import ig_watch
        try:
            return ig_watch.overlay(self)
        except Exception as e:
            from . import waiting
            waiting.note('WATCH overlay: %r' % (e,))
            return None

    def watch_key(self, what):
        w = getattr(self.app, 'watch', None)
        if w is None or not w.on:
            return
        if what in ('left', 'right'):
            w.step(-1 if what == 'left' else 1)
        elif what in ('up', 'down'):
            w.camera(-1 if what == 'up' else 1)

    def across(self, d):
        """Left (d -1) / right (+1) from a page's list to the one picked beside it and back: the game's own navigation
        can't go across columns whose rows don't line up (21 Nov 2026: the wheel's Right stayed in COMPETITIONS'
        list). -> the button id to put the focus on, or None (the game's own move then)."""
        if not self.focus or self.dialog or not isinstance(self._last_page, dict):
            return None
        lists = {}                               # 'list' / 'pick' -> [(button id, picked)] in the page's two columns

        def ids(n, out):
            if isinstance(n, dict):
                if n.get('t') == 'btn' and (n.get('id') or n.get('fid')):
                    out.append((n.get('id') or n.get('fid'), bool(n.get('ol'))))
                kids = n.get('c')
                for c in (kids if isinstance(kids, list) else [kids]):
                    ids(c, out)

        def walk(n):
            if isinstance(n, dict):
                sid = str(n.get('id') or '')
                if n.get('t') == 'scroll' and (':list:' in sid or ':pick:' in sid):
                    ids(n, lists.setdefault('list' if ':list:' in sid else 'pick', []))
                    return
                kids = n.get('c')
                for c in (kids if isinstance(kids, list) else [kids]):
                    walk(c)
        walk(self._last_page)
        left, right = lists.get('list') or [], lists.get('pick') or []
        if d > 0 and any(i == self.focus for i, _p in left) and right:
            main = [i for i, _p in right if '.drive' in i or '.join' in i]     # (its main button first: DRIVE, JOIN)
            return (main or [right[0][0]])[0]
        if d < 0 and any(i == self.focus for i, _p in right) and left:
            picked = [i for i, p in left if p]
            return (picked or [left[0][0]])[0]
        return None

    def click(self, id_):
        kind, _sep, arg = id_.partition(':')
        if kind == 'tab':
            self.tab = arg
            self.dialog = None
            self.prep = None
            self.opened()
        elif kind == 'go' and self.dialog:
            fn = self.dialog.get('go', (None, None))[1]
            self.dialog = None
            if fn:
                self.run(fn)                      # (a question it asks: in the game too)
        elif kind == 'cancel':
            self.dialog = None
        elif kind == 'window':
            self.dialog = None
            self.open_window(self.tab)
        elif '.' in kind:                         # a page's own: '<tab>.<action>[:<arg>]'
            tab, _sep, action = kind.partition('.')
            m = self.module(tab)
            if m is not None and hasattr(m, 'click'):
                self.run(lambda: m.click(self, action, arg or None))

    def text(self, id_, words):
        if id_ == 'dialog.words':
            self._dialog_words = words
            if self.dialog and 'field' in self.dialog:      # (drawn again: the words typed, not the first ones)
                self.dialog['field'] = words
            return
        tab, _sep, field = id_.partition('.')
        m = self.module(tab)
        if m is not None and hasattr(m, 'text'):
            self.run(lambda: m.text(self, field, words))

    def drive(self, setup, on_ok, on_fail):
        """DRIVE in the running game (ingamedrive.py): the set-up to the mod; on_ok() once the game is on its way to
        the Service Park, on_fail(why) if it can't be done there."""
        n = self.cmd['n'] + 1
        self.drives.send(n, on_ok, on_fail)
        self.cmd = {'n': n, 'do': 'drive', 'setup': setup}

    def switch_tab(self, d):
        """The tab before (d -1) / after (+1) the one on screen: the game's tab keys and buttons (ingamenav.py)."""
        if self.dialog:                      # (a question up: answered first, not dropped by a tab key: a review)
            return
        keys = [k for k, _l in TABS]
        i = keys.index(self.tab) if self.tab in keys else 0
        self.tab = keys[(i + d) % len(keys)]
        self.prep = None
        self.opened()

    def nav_tick(self):
        """While the pages are on screen and the game is in front: the game's menu buttons on the player's wheel (or a
        pad's shoulders and B) work in them (ingamenav.py). A quicker loop than tick(): a button's press is short."""
        from . import ingamenav
        try:
            front = self._game_in_front()
            if self.nav is None and front:
                self.nav = ingamenav.MenuInputs()
            if self.nav is not None:
                watching = getattr(getattr(self.app, 'watch', None), 'on', False)
                if not front:
                    self.nav.reset()
                elif not self.shown and not self._in_menus() and watching:
                    # WATCH on the stage: the wheel's / pad's menu arrows: the driver before / after, the camera
                    for action in self.nav.poll():
                        if action in ('left', 'right', 'up', 'down'):
                            self.watch_key(action)
                elif not self.shown and not self._in_menus():
                    self.nav.reset()                   # (on a stage: the wheel is the player's, nothing looked at)
                elif not self.shown:
                    # the pages closed: the wheel's Select (or A on a pad) on the ACR DAILY tile opens them. The mod
                    # opens them only if the tile has the game's focus (21 Nov 2026: only the Enter key did)
                    if any(a in ('select', 'pad_a') for a in self.nav.poll()):
                        self.cmd = {'n': self.cmd['n'] + 1, 'do': 'select'}
                else:
                    for action in self.nav.poll():
                        to = self.across(-1 if action == 'left' else 1) if action in ('left', 'right') else None
                        if to:
                            self.cmd = {'n': self.cmd['n'] + 1, 'do': 'focus', 'id': to}
                        elif action in ingamenav.KEYS:
                            ingamenav.press_key(ingamenav.KEYS[action])
                        elif action == 'back':
                            self.back()
                        elif action in ('tab_left', 'tab_right'):
                            self.switch_tab(-1 if action == 'tab_left' else 1)
        except Exception:
            self.nav = None
        # (quick while the game is in front: a wheel button's press is short, a slower look missed it)
        self.app.root.after(NAV_MS if getattr(self, '_front', False) else 250, self.nav_tick)

    def _in_menus(self):
        try:
            return bool(self.app._pulse().in_menus())
        except Exception:
            return False

    def _game_in_front(self):
        from . import ingamenav
        now = time.monotonic()
        if now - self._front_at > 0.5:
            self._front_at, self._front = now, ingamenav.game_in_front()
        return self._front

    def back(self):
        """B on a game pad: a question over the page goes; otherwise the pages go (the game's menu back)."""
        if self.dialog:
            self.dialog = None
        elif self.prep:                            # (DRIVE's set-up screen: back to the tab)
            self.prep = None
        else:
            self.cmd = {'n': self.cmd['n'] + 1, 'do': 'close'}

    def opened(self):
        """The tab on screen opened (or the pages): its data fetched again, as the window's tabs do."""
        m = self.module(self.tab)
        if m is not None and hasattr(m, 'opened'):
            try:
                m.opened(self)
            except Exception:
                pass

    def open_window(self, tab):
        """A tab not in the game yet: the app's window on it, in front."""
        a = self.app
        if getattr(a, 'launcher', None) is not None:
            a.launcher.hide()
        try:
            if tab == 'settings':
                a.toggle_settings_view(True)
            elif tab == 'inbox':
                a.toggle_inbox_view(True)
            elif tab == 'profile':
                a.open_profile()
            elif tab == 'comp':
                a.show_tab('league')
            elif tab == 'home':
                a.open_home()
            else:
                a.show_tab(tab)
        except Exception:
            pass
        to_front = getattr(a, 'to_front', None)
        if to_front:
            to_front()

    # ---- the app's questions and notes, in the game while its pages are there
    def run(self, fn, agreed=None):
        """Do a click (fn); a question the app asks meanwhile is put in the game and can do it again (questions())."""
        self._running, self._agreed = fn, dict(agreed or {})
        try:
            fn()
        finally:
            self._running, self._agreed = None, {}

    def questions(self):
        """messagebox / simpledialog, while the pages are on screen in the game: said and asked there. Once, for good:
        with the pages away (or the game closed) the windows are the app's as before."""
        if self._patched:
            return
        self._patched = True
        page = self

        def note(name):
            orig = getattr(tk_messagebox, name)

            def said(title=None, message=None, **kw):
                if not page.shown and not page.game_up():
                    return orig(title, message, **kw)
                # (the pages away but the game up: kept for them, no window behind the game and no Windows sound)
                page.say(title or 'ACR Daily', [message or ''])
                return 'ok'
            setattr(tk_messagebox, name, said)

        def question(name, yes, no):
            orig = getattr(tk_messagebox, name)

            def asked(title=None, message=None, **kw):
                if not page.shown:
                    return orig(title, message, **kw)
                key = (title, str(message))
                if key in page._agreed:
                    return yes
                run = page._running
                if run is None:                  # (asked later, not by a click: no way to do it again)
                    page.ask(title or 'ACR Daily', [message or ''], _('OK'), lambda: None)
                    return no
                agreed = dict(page._agreed)
                agreed[key] = yes
                page.ask(title or 'ACR Daily', [message or ''], _('YES'), lambda: page.run(run, agreed), _('NO'))
                return no
            setattr(tk_messagebox, name, asked)

        for n in ('showinfo', 'showwarning', 'showerror'):
            note(n)
        question('askyesno', True, False)
        question('askokcancel', True, False)
        question('askyesnocancel', True, None)
        question('askretrycancel', True, False)
        question('askquestion', 'yes', 'no')

        from tkinter import simpledialog
        orig_ask = simpledialog.askstring

        def askstring(title=None, prompt=None, **kw):
            if not page.shown:
                return orig_ask(title, prompt, **kw)
            key = ('words', title, str(prompt))
            if key in page._agreed:
                return page._agreed[key]
            run = page._running
            if run is None:
                return None
            page._dialog_words = kw.get('initialvalue') or ''
            before = dict(page._agreed)              # (the answers so far: kept for when it's done again)

            def go():
                agreed = dict(before)
                agreed[key] = page._dialog_words
                page.run(run, agreed)
            page.dialog = {'title': title or 'ACR Daily', 'lines': [prompt or ''], 'go': (_('OK'), go),
                           'cancel': _('CANCEL'), 'field': page._dialog_words}
            return None
        simpledialog.askstring = askstring

    # ---- what the mod gets
    def state(self):
        page = self._last_page = self.page()
        return {'tile': {'label': 'ACR DAILY', 'img': tile_picture()},
                'open': self.ask_open, 'page': page, 'dialog': self.dialog_node(),
                'focus': ('dialog.words' if self.dialog and 'field' in self.dialog else
                          'go' if self.dialog and self.dialog.get('go') else 'cancel' if self.dialog else 'prep.start' if self.prep else 'tab:' + self.tab),
                'cmd': self.cmd, 'prep': bool(self.prep), 'overlay': self.watch_overlay(),
                # (the game started by the app with its set-up in the save: its stages count, appui.lua's own)
                'own': int(saveslot.SET_UP_AT) if saveslot.SET_UP_AT else None}

    def page(self):
        m = self.module('prep' if self.prep else self.tab)       # (DRIVE's set-up screen over the tab: ig_prep.py)
        try:
            body = m.page(self) if m is not None else self.not_yet_page()
        except Exception as e:                    # (a page that fails says so, the rest still works)
            body = col(kicker(dict(TABS).get(self.tab, '')), empty(_('This page failed: %s') % e, pad=[0, 10, 0, 18]),
                       quiet('window', _('OPEN THE WINDOW')), al='l')
        if getattr(m, 'OWN_SCROLL', False) and body.get('fill'):   # (its lists scroll on their own: ig_comp)
            return col(self.header(), rule(pad=[0, 14, 0, 0]), self.status(), sp(h=18), body)
        return col(self.header(), rule(pad=[0, 14, 0, 0]), self.status(), sp(h=18),
                   scroll(body, id='main:' + ('prep' if self.prep else self.tab), fill=1))

    def status(self):
        """The window's status line (what DRIVE is doing: "Game closed. Setting up the daily...", a stake on its way),
        under the header: in the game it would go unseen."""
        try:
            words = self.app.sub_l.cget('text')
        except Exception:
            words = ''
        # only a fresh one, for STATUS_S: an old line stayed on every page for hours, out of date (the user, 21 Nov
        # 2026: "why is this gray line there?")
        now = time.monotonic()
        if words != self._status_words:
            self._status_words, self._status_at = words, now
        if not words or now - self._status_at > STATUS_S:
            return None
        return box(txt(words, 17, 'medium', WHITE, wrap=True), bg=PANEL2, p=[16, 8, 16, 8], pad=[0, 12, 0, 0])

    def header(self):
        a = self.app
        tabs = []
        for kind, label in TABS:
            on = kind == self.tab
            if kind == 'inbox' and getattr(a, 'inbox_unread', 0):
                label = '%s (%d)' % (label, a.inbox_unread)
            tabs.append(btn('tab:' + kind, label, bg=WHITE if on else '-', hov=WHITE if on else PANEL2,
                            fg=BG if on else FG2, hfg=BG if on else WHITE, sz=17, f='bold', sp=80, p=[14, 7, 14, 7],
                            pad=[0 if not tabs else 2, 0, 0, 0]))
        drv = getattr(a, 'driver', None) or {}
        name = drv.get('name') or a.s.get('name') or ''
        credits = (a.credits or {}).get('balance')
        who = col(txt(name, 18, 'bold', WHITE, j=2),
                  txt(_('%d credits') % credits, 14, 'medium', MUTED, j=2) if credits is not None else None,
                  va='c', pad=[20, 0, 20, 0])
        logo = box(txt('ACR DAILY', 24, 'bold', WHITE, sp=60), bg=ACC, p=[14, 4, 14, 4], va='c')
        return row(logo, sp(22), row(*tabs, va='c'), sp(fill=1), who,
                   quiet('close', _('BACK TO THE GAME  ·  ESC'), va='c'))

    def not_yet_page(self):
        label = dict(TABS).get(self.tab, '')
        return col(kicker(label),
                   txt(_('Not in the game yet: it comes next. Until then it is in the ACR Daily window.'), 22, 'medium',
                       SOFT, pad=[0, 10, 0, 18]),
                   quiet('window', _('OPEN THE WINDOW')), al='l')

    def dialog_node(self):
        d = self.dialog
        if not d:
            return None
        lines = [txt(x, 20, 'medium', SOFT, wrap=True, pad=[0, 10, 0, 0]) for x in d.get('lines', []) if x]
        field = None
        if 'field' in d:
            field = box(edit('dialog.words', d.get('field') or '', '', fill=1), bg=PANEL2, p=[12, 8, 12, 8], r=2,
                        ol=LINE2, pad=[0, 14, 0, 0])
        buttons = []
        if d.get('go'):
            buttons.append(primary('go', d['go'][0]))
            buttons.append(sp(14))
        buttons.append(quiet('cancel', d.get('cancel') or _('CANCEL')))
        return size(box(col(txt(d.get('title', ''), 30, 'bold', WHITE, wrap=True), *lines, field,
                            row(*buttons, pad=[0, 26, 0, 0])),
                        bg=PANEL, p=[32, 26, 32, 28], r=4, ol=LINE2), w=760)
