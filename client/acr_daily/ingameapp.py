"""ACR DAILY inside the game (0.2, a private build for now): the app's pages drawn by the game itself.

The app stays the brain (the server, the game's save, the timing, the judge); the game draws its pages. In the game's
main menu, HOME gets an ACR DAILY tile (the game's own tile); clicking it puts the game's menu away and shows these pages
in its place (mod/ACRDailyGhosts/Scripts/appui.lua). Esc or BACK TO THE GAME brings the game's menu back.

What the pages show goes to the mod as a tree of boxes, words, pictures and buttons (appui.lua's top says the nodes),
in %APPDATA%\\ACR Daily\\ingame-app.txt:

    ACRAPP 1 <seq> <rev>       seq: each write (the app is alive while it changes, at least every ALIVE_S)
    <json>                     rev: what the pages say: the mod draws them again only for a new one
    end <seq>

and what was clicked comes back in ingame-app-events.txt: "ACRAPP <session>.<n> <what> [<id>]" (open, close, click).
A page is a function of the app's own state (its dailies, time trials, boards...): the same data and the same actions
as its window, so DRIVE in the game is the window's DRIVE (questions asked in the game, not in windows behind it).

Ported so far: DAILIES and TIME TRIAL (cards, today's times, DRIVE). The other tabs say they are still in the window.
"""
import hashlib
import json
import os
import time
import tkinter.messagebox as tk_messagebox

from . import liverally, photos, settings
from .i18n import _
from .judge import fmt_ms

try:
    from PIL import Image, ImageDraw
except ImportError:                     # (an app built without Pillow: no pictures in the game)
    Image = None

FILE = 'ingame-app.txt'
EVENTS_FILE = 'ingame-app-events.txt'
PICS_DIR = os.path.join('hud', 'app')   # (in settings.DIR) the pictures cut for the game's pages
ALIVE_S = 1.0                           # written at least this often: the mod takes the app for gone after 4 s
TICK_MS = 100

# the look: the app's colours (app.py), the game's font (appui.lua draws in Rajdhani)
BG, PANEL, PANEL2, LINE, LINE2 = '0A0A0B', '141417', '1C1C21', '1F1F23', '2B2B31'
WHITE, SOFT, FG2, MUTED = 'F4F4F5', 'D4D4D8', 'A1A1AA', '85858E'
ACC, GOOD, BAD = 'E30613', '30D158', 'FF453A'
TT_COL = 'BF5AF2'

PAGE_W = 1840                           # the page's width in the game's units (appui.lua: 1080 tall)

# the app's own nav (tabsui.NAV: RANKED in the builds that have it), then its icons as words
TABS = (('daily', _('DAILIES')), ('tt', _('TIME TRIAL'))) + ((('live', _('RANKED')),) if liverally.ON else ()) + (
    ('comp', _('COMPETITIONS')), ('community', _('COMMUNITY')), ('inbox', _('INBOX')), ('profile', _('PROFILE')),
    ('settings', _('SETTINGS')))


# ---------------------------------------------------------------------- the tree's nodes (appui.lua draws them)
def col(*c, **o):
    return dict(t='col', c=[x for x in c if x], **o)


def row(*c, **o):
    return dict(t='row', c=[x for x in c if x], **o)


def stack(*c, **o):
    return dict(t='stack', c=[x for x in c if x], **o)


def box(c=None, **o):
    return dict(t='box', c=c, **o)


def txt(s, sz=18, f='semi', fg=SOFT, **o):
    return dict(t='txt', s=str(s), sz=sz, f=f, fg=fg, **o)


def img(src, w, h, **o):
    return dict(t='img', src=src, w=w, h=h, **o) if src else dict(t='sp', w=w, h=h, **o)


def sp(w=None, h=None, **o):
    return dict(t='sp', w=w, h=h, **o)


def btn(id_, s=None, c=None, **o):
    n = dict(t='btn', id=id_, **o)
    if c is not None:
        n['c'] = c
    else:
        n['s'] = s
    return n


def primary(id_, s, **o):
    """The page's main button (DRIVE): solid white, red under the mouse."""
    return btn(id_, s, bg=WHITE, hov=ACC, fg=BG, hfg=WHITE, sz=20, f='bold', sp=60, p=[28, 10, 28, 10], r=2, **o)


def quiet(id_, s, **o):
    """A plain button: a hairline, white under the mouse."""
    return btn(id_, s, bg='-', hov=WHITE, fg=SOFT, hfg=BG, sz=17, f='semi', sp=40, p=[20, 8, 20, 8], r=2, ol=LINE2,
               **o)


def chip(s, fg=WHITE, bg=ACC):
    return box(txt(s, 14, 'bold', fg, sp=60), bg=bg, p=[8, 2, 8, 2], r=2)


def kicker(s, fg=MUTED):
    """A small spaced-out uppercase label (as the app's and the website's)."""
    return txt(s.upper(), 14, 'bold', fg, sp=120)


# ---------------------------------------------------------------------- pictures, cut for the game
def picture(key, w, h, fade=True):
    """One of the app's photos (photos.py: a rally's, a part's) cut to w x h (its focus point kept), darkened towards
    its bottom for the words on it -> the PNG's path (made once), or None."""
    if Image is None or not key:
        return None
    m = photos.meta().get(key)
    if not m:
        return None
    out_dir = os.path.join(settings.DIR, PICS_DIR)
    out = os.path.join(out_dir, '%s-%dx%d%s.png' % (key, w, h, '-f' if fade else ''))
    if os.path.exists(out):
        return out
    try:
        im = Image.open(os.path.join(photos.DIR, m['file'])).convert('RGB')
        fx, fy = (m.get('focus') or [0.5, 0.5])[:2]
        sw, sh = im.size
        k = max(w / sw, h / sh)
        im = im.resize((max(w, round(sw * k)), max(h, round(sh * k))), Image.LANCZOS)
        sw, sh = im.size
        x = min(max(0, round(fx * sw - w / 2)), sw - w)
        y = min(max(0, round(fy * sh - h / 2)), sh - h)
        im = im.crop((x, y, x + w, y + h))
        if fade:
            shade = Image.new('L', (1, h))
            for i in range(h):
                a = max(0.0, (i / h - 0.35) / 0.65)
                shade.putpixel((0, i), round(235 * a ** 1.4))
            dark = Image.new('RGB', (w, h), (10, 10, 11))
            im = Image.composite(dark, im, shade.resize((w, h)))
        os.makedirs(out_dir, exist_ok=True)
        tmp = out + '.tmp'
        im.save(tmp, 'PNG')
        os.replace(tmp, out)
        return out
    except (OSError, ValueError, KeyError):
        return None


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
    """ingame-app-events.txt as the mod writes it: poll() -> the new event since the last look, [(what, id)] (the mod
    writes one at a time, each over the last; the first look only notes what was there)."""

    def __init__(self, path, opener=None):
        self.path = path
        self.opener = opener
        self.fh = None
        self.seq = None

    def poll(self):
        try:
            if self.fh is None:
                self.fh = self.opener(self.path) if self.opener else open(self.path, 'rb')
            self.fh.seek(0)
            raw = self.fh.read(1024)
        except (OSError, ValueError):
            self.close()
            if self.seq is None:
                self.seq = ''
            return []
        text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
        if '\n' not in text:
            return []
        parts = text.split('\n', 1)[0].rstrip().split(' ', 3)
        if len(parts) < 3 or parts[0] != 'ACRAPP':
            return []
        if self.seq is None or parts[1] == self.seq:
            self.seq = parts[1]
            return []
        self.seq = parts[1]
        return [(parts[2], parts[3] if len(parts) > 3 else '')]

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
        self.tab = 'daily'
        self.shown = False           # the pages on screen in the game (the mod says: open / close)
        self.dialog = None           # {'title', 'lines', 'go': (label, fn), 'cancel'} or None
        self.ask_open = False        # the app asks the mod to show its pages (a notice to read)
        self._notices_on = False

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
        for what, id_ in self.events.poll():
            self.event(what, id_)
        self.notices()
        body = json.dumps(self.state(), ensure_ascii=False, separators=(',', ':'))
        self.writer.write(body, now)

    def event(self, what, id_):
        if what == 'open':
            self.shown = True
            self.ask_open = False
            self.refresh_tab()
        elif what == 'close':
            self.shown = False
            self.dialog = None
        elif what == 'click':
            self.click(id_)

    def click(self, id_):
        kind, _sep, arg = id_.partition(':')
        if kind == 'tab':
            self.tab = arg
            self.refresh_tab()
        elif kind == 'drive':
            self.ask_drive(int(arg))
        elif kind == 'ttdrive':
            self.ask_tt_drive(int(arg))
        elif kind == 'go' and self.dialog:
            fn = self.dialog.get('go', (None, None))[1]
            self.dialog = None
            if fn:
                fn()
        elif kind == 'cancel':
            self.dialog = None
        elif kind == 'window':
            self.dialog = None
            self.open_window(self.tab)

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
            else:
                a.show_tab(tab)
        except Exception:
            pass
        to_front = getattr(a, 'to_front', None)
        if to_front:
            to_front()

    def refresh_tab(self):
        """The tab's data fetched again as it is opened (as the window's tabs do)."""
        a = self.app
        try:
            if self.tab == 'daily':
                a.refresh_board()
            elif self.tab == 'tt':
                a.refresh_tt()
        except Exception:
            pass

    # ---- the window's questions and notes, while the game shows the pages: in the game
    def notices(self):
        """A note the app would show in a window (showinfo: 'Finish the stage you are on first'...) is said in the game
        while its pages are on screen there: the window would sit unseen behind the game."""
        if self._notices_on:
            return
        self._notices_on = True
        page = self
        for name in ('showinfo', 'showwarning', 'showerror'):
            orig = getattr(tk_messagebox, name)

            def said(title=None, message=None, _orig=orig, **kw):
                if page.shown:
                    page.dialog = {'title': title or 'ACR Daily', 'lines': [str(message or '')], 'cancel': _('OK')}
                    return 'ok'
                return _orig(title, message, **kw)
            setattr(tk_messagebox, name, said)

    # ---- DRIVE, asked in the game
    def ask_drive(self, slot):
        a = self.app
        d = a.dailies.get(slot)
        if not d:
            return
        ch = d['ch']
        lines = [_('The game restarts on SS%d: %s · %s · %s.') % (slot, stage_name(a, ch), ch.get('car', ''),
                                                                 conditions(a, ch))]
        agreed = False
        try:
            offer = a._stake_offer(slot)
        except Exception:
            offer = None
        if offer and offer[0] != 'no' and (ch.get('wager') or {}).get('stake'):
            w, c = ch['wager'], a.credits or {}
            lines.append(_('Stake %d credits on SS%d? You have %d. The faster half get %d back.')
                         % (w['stake'], slot, c.get('balance') or 0, 2 * w['stake']))
            agreed = True
        self.dialog = {'title': 'SS%d' % slot, 'lines': lines,
                       'go': (_('DRIVE'), lambda: a.drive_click(slot, confirm=False, agreed=agreed)),
                       'cancel': _('CANCEL')}

    def ask_tt_drive(self, slot):
        a = self.app
        t = a.tt.get(slot)
        if not t:
            return
        ch = t['ch']
        self.dialog = {'title': 'TT%d' % slot,
                       'lines': [_('The game restarts on TT%d: %s · %s · %s.') % (slot, stage_name(a, ch), ch.get('car', ''),
                                                                                conditions(a, ch))],
                       'go': (_('DRIVE'), lambda: a.tt_drive(slot, confirm=False)), 'cancel': _('CANCEL')}

    # ---- what the mod gets
    def state(self):
        return {'tile': {'label': 'ACR DAILY', 'img': picture('dailies', 532, 716, fade=False)},
                'open': self.ask_open, 'page': self.page(), 'dialog': self.dialog_node()}

    def page(self):
        body = {'daily': self.dailies_page, 'tt': self.tt_page}.get(self.tab, self.not_yet_page)()
        return col(self.header(),
                   dict(t='size', h=1, c=box(None, bg=LINE), pad=[0, 14, 0, 18]),
                   dict(t='scroll', id='main:' + self.tab, c=[body], fill=1))

    def header(self):
        a = self.app
        tabs = []
        for kind, label in TABS:
            on = kind == self.tab
            if kind == 'inbox' and getattr(a, 'inbox_unread', 0):
                label = '%s (%d)' % (label, a.inbox_unread)
            tabs.append(btn('tab:' + kind, label, bg=WHITE if on else '-', hov=WHITE if on else PANEL2,
                            fg=BG if on else FG2, hfg=BG if on else WHITE, sz=17, f='bold', sp=80, p=[16, 7, 16, 7],
                            pad=[0 if not tabs else 4, 0, 0, 0]))
        drv = getattr(a, 'driver', None) or {}
        name = drv.get('name') or a.s.get('name') or ''
        credits = (a.credits or {}).get('balance')
        who = col(txt(name, 18, 'bold', WHITE, j=2),
                  txt(_('%d credits') % credits, 14, 'medium', MUTED, j=2) if credits is not None else None,
                  va='c', pad=[24, 0, 24, 0])
        logo = box(txt('ACR DAILY', 24, 'bold', WHITE, sp=60), bg=ACC, p=[14, 4, 14, 4], va='c')
        return row(logo, sp(28), row(*tabs, va='c'), sp(fill=1), who,
                   quiet('close', _('BACK TO THE GAME  ·  ESC'), va='c'))

    # DAILIES
    def dailies_page(self):
        a = self.app
        if not a.dailies:
            msg = getattr(a, 'net_msg', '') or _('Loading today\'s dailies…')
            return col(kicker(_('Today')), txt(msg, 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
        slots = sorted(a.dailies)
        gap = 28
        w = int((PAGE_W - gap * (len(slots) - 1)) / len(slots))
        cards = [self.daily_card(s, w, pad=[0 if i == 0 else gap, 0, 0, 0]) for i, s in enumerate(slots)]
        return row(*cards)

    def daily_card(self, slot, w, **o):
        a = self.app
        d = a.dailies[slot]
        ch = d['ch']
        km = '%.1f KM' % (ch['lengthM'] / 1000) if ch.get('lengthM') else ''
        photo = picture(photos.for_rally(ch.get('rally')) or 'dailies', w, 300)
        top = col(row(chip('SS%d' % slot), sp(10),
                      txt((ch.get('rally') or '').upper(), 16, 'bold', WHITE, sp=80, va='c', sh=True)),
                  sp(h=1, fill=1),
                  txt(stage_name(a, ch).upper(), 30, 'bold', WHITE, sh=True, wrap=True),
                  txt(' · '.join(x for x in (km, (ch.get('surface') or '').upper()) if x), 16, 'semi', SOFT, sp=60,
                      sh=True),
                  pad=[22, 18, 22, 16])
        head = stack(img(photo, w, 300), dict(top, al='f', va='f'), h=300)
        car = ch.get('car', '') + ('  ·  %s' % ch['carClass'] if ch.get('carClass') else '')
        info = col(txt(car, 20, 'semi', WHITE),
                   txt(' · '.join(x for x in (conditions(a, ch), set_by(ch)) if x), 16, 'medium', FG2, wrap=True,
                       pad=[0, 4, 0, 0]),
                   row(primary('drive:%d' % slot, _('DRIVE  ›')), sp(fill=1), mine(a, d, a.s.get('steamId')),
                       pad=[0, 16, 0, 0]),
                   pad=[22, 16, 22, 18])
        board = self.board(d.get('board'), a.s.get('steamId'))
        return dict(col(head, box(info, bg=PANEL), box(board, bg=PANEL2, p=[22, 16, 22, 18]), **o), fill=1)

    def board(self, b, me, rows=12, title=None):
        title = title or _('Today\'s times')
        entries = [e for e in (b or {}).get('entries', []) if e.get('totalMs') is not None]
        if b is None:
            return col(kicker(title), txt(_('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
        if not entries:
            return col(kicker(title), txt(_('No times yet. Be the first.'), 17, 'medium', MUTED, pad=[0, 8, 0, 0]))
        shown = entries[:rows]
        mine_e = next((e for e in entries if e.get('steamId') == me), None)
        if mine_e is not None and mine_e not in shown:
            shown = shown[:rows - 1] + [mine_e]
        best = entries[0]['totalMs']
        out = [row(kicker(title), sp(fill=1), kicker(_('%d drivers') % len(entries)), pad=[0, 0, 0, 6])]
        for e in shown:
            pos = entries.index(e) + 1
            is_me = e.get('steamId') == me
            gap = '' if pos == 1 else '+' + fmt_ms(e['totalMs'] - best).lstrip('0:')
            fg = WHITE if is_me else SOFT
            line = row(txt('%d' % pos, 17, 'bold', ACC if pos == 1 else MUTED, j=2, pad=[0, 0, 0, 0]),
                       sp(14),
                       txt(shown_name(e), 17, 'bold' if is_me else 'semi', fg, fill=1),
                       txt(fmt_ms(e['totalMs']), 17, 'semi', fg, j=2),
                       sp(14),
                       txt(gap, 15, 'medium', MUTED, j=2),
                       pad=[0, 5, 0, 0])
            out.append(box(line, bg=PANEL if is_me else '-', p=[6, 0, 6, 4]) if is_me else line)
        return col(*out)

    # TIME TRIAL
    def tt_page(self):
        a = self.app
        tt = getattr(a, 'tt', None) or {}
        if not tt:
            info = getattr(a, 'tt_info', None) or {}
            msg = _('No time trial this week.') if info and not info.get('on') else _('Loading the time trial…')
            return col(kicker(_('Time trial')), txt(msg, 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
        slots = sorted(tt)
        gap = 28
        w = int((PAGE_W - gap * (len(slots) - 1)) / len(slots))
        cards = []
        for i, slot in enumerate(slots):
            t = tt[slot]
            ch = t['ch']
            photo = picture(photos.for_rally(ch.get('rally')) or 'tt', w, 300)
            top = col(row(chip('TT%d' % slot, bg=TT_COL), sp(10),
                          txt((ch.get('rally') or '').upper(), 16, 'bold', WHITE, sp=80, va='c', sh=True)),
                      sp(h=1, fill=1),
                      txt(stage_name(a, ch).upper(), 30, 'bold', WHITE, sh=True, wrap=True),
                      pad=[22, 18, 22, 16])
            head = stack(img(photo, w, 300), dict(top, al='f', va='f'), h=300)
            info = col(txt(ch.get('car', ''), 20, 'semi', WHITE),
                       txt(conditions(a, ch), 16, 'medium', FG2, pad=[0, 4, 0, 0]),
                       row(primary('ttdrive:%d' % slot, _('DRIVE  ›')), sp(fill=1), pad=[0, 16, 0, 0]),
                       pad=[22, 16, 22, 18])
            board = self.board(t.get('board'), a.s.get('steamId'), title=_('This week\'s times'))
            cards.append(dict(col(head, box(info, bg=PANEL), box(board, bg=PANEL2, p=[22, 16, 22, 18]),
                                  pad=[0 if i == 0 else gap, 0, 0, 0]), fill=1))
        return row(*cards)

    # the rest, for now
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
        lines = [txt(x, 20, 'medium', SOFT, wrap=True, pad=[0, 10, 0, 0]) for x in d.get('lines', [])]
        buttons = []
        if d.get('go'):
            buttons.append(primary('go', d['go'][0]))
            buttons.append(sp(14))
        buttons.append(quiet('cancel', d.get('cancel') or _('CANCEL')))
        return dict(t='size', w=760, c=box(col(txt(d.get('title', ''), 30, 'bold', WHITE),
                                              *lines, row(*buttons, pad=[0, 26, 0, 0])),
                                          bg=PANEL, p=[32, 26, 32, 28], r=4, ol=LINE2))


# ---------------------------------------------------------------------- the app's words for a stage (app.py's own)
def stage_name(a, ch):
    from . import app as app_mod
    return app_mod.stage_name(ch)


def conditions(a, ch):
    from . import app as app_mod
    return app_mod.conditions(ch)


def set_by(ch):
    from . import app as app_mod
    return app_mod.set_by(ch)


def shown_name(e):
    from . import app as app_mod
    return app_mod.shown_name(e)


def mine(a, d, me):
    """My place on the daily so far, or nothing."""
    entries = [e for e in (d.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
    for i, e in enumerate(entries):
        if e.get('steamId') == me:
            return col(kicker(_('You')), txt('P%d  ·  %s' % (i + 1, fmt_ms(e['totalMs'])), 20, 'bold', WHITE), va='c')
    return None
