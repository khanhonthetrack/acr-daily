"""SETTINGS in the game (ingamekit.py says how a page is made): the window's settings page (settingsui.py) in its panels,
each setting's control as small buttons (ON / OFF, the choices, the one on highlighted). Every button calls the app's own
method, as the window's control does (its questions are asked in the game: ingameapp.questions).

Not as the window: picking a language asks first, in the game (YES starts the app again in it, NO changes nothing);
ghost cars switched on don't open the SET UP window (it would sit behind the game): its settings are here, under the
switch; WHAT'S NEW and the photo credits open in the page; SIGN IN WITH STEAM is the window's (its sign-in screen)."""
import threading
import webbrowser

from . import __version__, i18n
from .i18n import _
from .ingamekit import (ACC, BG, FG2, GOOD, LINE2, MUTED, PANEL, PANEL2, SOFT, WHITE, box, btn, col, edit,
                        kicker, link, quiet, row, rule, size, sp, tab_id, txt)

TAB = 'settings'
GAP = 28                             # between the two columns (each half of the page's 1840 less it)
SIZE_STEP = 1.15                     # (the window's − / +: Overlay.resize)
NEWS_EARLIER = 4                     # WHAT'S NEW: this many versions before this one


def _id(action, arg=None):
    return tab_id(TAB, action, arg)


# ---------------------------------------------------------------------- the parts of a panel
def choice(action, arg, label, on, colour=WHITE, **o):
    """A small button of a choice: filled while it is the one on."""
    return btn(_id(action, arg), label, **dict(dict(bg=colour if on else '-', hov=colour if on else PANEL2,
                                                    fg=BG if on else FG2, hfg=BG if on else WHITE, sz=16, f='bold',
                                                    sp=60, p=[12, 6, 12, 6], r=2, ol=None if on else LINE2), **o))


def choices(action, items, on, colour=WHITE, per_row=None, **o):
    """A row (or rows of per_row) of choices: items [(arg, label)], on the arg that's on."""
    per_row = per_row or len(items) or 1
    rows = []
    for i in range(0, len(items), per_row):
        part = items[i:i + per_row]
        rows.append(row(*[choice(action, arg, label, arg == on, colour, pad=[0 if j == 0 else 6, 0, 0, 0])
                          for j, (arg, label) in enumerate(part)], pad=[0, 0 if not rows else 6, 0, 0]))
    return col(*rows, **o)


def switch(action, on, **o):
    """ON / OFF: ON green while on."""
    return row(choice(action, 'on', _('ON'), on, GOOD), choice(action, 'off', _('OFF'), not on, SOFT, pad=[6, 0, 0, 0]),
               **o)


def setting(name, words, control=None, under=None):
    """A setting: its name and what it does, its control at the right (a wide one under them)."""
    head = row(col(txt(name, 20, 'bold', WHITE) if name else None,
                   txt(words, 15, 'medium', FG2, wrap=True, pad=[0, 3, 0, 0]) if words else None, fill=1),
               sp(24), control, va='t')
    return col(head, col(under, pad=[0, 10, 0, 0]) if under else None, pad=[0, 16, 0, 0])


def panel(title, *rows, first=False):
    return box(col(row(kicker(title), rule(fill=1, va='c', pad=[12, 0, 0, 0])), *rows),
               bg=PANEL, p=[24, 18, 24, 20], ol=LINE2, pad=[0, 0 if first else 16, 0, 0])


# ---------------------------------------------------------------------- the page
def opened(ig):
    m = ig.mem(TAB)
    m['sizes'] = window_sizes(ig.app)


def page(ig):
    a = ig.app
    m = ig.mem(TAB)
    o = a.s.get('overlay') or {}
    # (0.2: no window to size, no AUTO, no Windows sound: DRIVE goes straight to the Service Park, the app sits in the
    # game; the user, 20 Nov 2026: "most settings are outdated")
    left = col(language_panel(a), timer_panel(a, o), fill=1)
    right = col(displays_panel(a), account_panel(a), save_panel(), about_panel(a, m), admin_panel(a), fill=1)
    return row(left, sp(GAP), right)


def language_panel(a):
    langs = [(code, name) for code, name in i18n.LANGS]
    return panel(_('Language'),
                 setting(_('Language'), _('The app\'s words in your language. ACR Daily starts again to switch.'),
                         under=choices('lang', langs, i18n.lang(), per_row=5)), first=True)


def window_panel(ig, m):
    from . import app as app_mod
    a = ig.app
    keys = m.get('sizes')
    if keys is None:
        keys = m['sizes'] = window_sizes(a)
    cur = a.s.get('windowSize') or app_mod.WINDOW_DEFAULT
    if cur not in keys:                              # (saved on a bigger screen: the biggest that fits is on)
        cur = ([k for k in keys if k != 'free'] or ['free'])[-1]
    dims = {k: (w, h) for k, w, h in app_mod.WINDOW_SIZES}
    wide = [(k, '%d × %d' % dims[k]) for k in keys if k in dims and dims[k][0] >= dims[k][1]]
    tall = [(k, '%d × %d' % dims[k]) for k in keys if k in dims and dims[k][0] < dims[k][1]]
    under = col(choices('win', wide + [('free', _('Resizable'))], cur, per_row=5),
                row(kicker(_('vertical'), va='c'), sp(12), choices('win', tall, cur), pad=[0, 6, 0, 0]) if tall else None)
    return panel(_('Window'),
                 setting(_('Window size'), _("The app's window is always this size, so nothing on its pages moves or "
                                             "gets cut off. Sizes are at Windows' display scale; only the ones that fit "
                                             "your screen are listed. Resizable: drag its edges as you like."),
                         under=under))


def window_sizes(a):
    """The window's sizes that fit a screen of this PC (as the window's picker), and 'free'."""
    from . import app as app_mod
    try:
        k, room = a.window_room()
        fit = app_mod.sizes_anywhere(k, [room] + [app_mod.room_of(x) for x in app_mod.work_areas()])
    except Exception:
        fit = [kk for kk, _w, _h in app_mod.WINDOW_SIZES]
    return [kk for kk, _w, _h in app_mod.WINDOW_SIZES if kk in fit] + ['free']


def drive_panel(a):
    return panel(_('Drive'),
                 setting(_('Auto-drive'), _('After every DRIVE (dailies, leagues, 1V1s, cups) the app goes on through the '
                                            'game\'s menus to the Service Park; you press START STAGE. Touch the '
                                            'keyboard or mouse to take over.'),
                         switch('auto', bool(a.s.get('autoDrive', False)))),
                 setting(_('Sound and notification'), _('When a finished run\'s official time is saved, or lost, the '
                                                        'app plays a sound and shows a Windows notification: heard '
                                                        'over the game in full screen too.'),
                         switch('notify', bool(a.s.get('notify', True)))))


def timer_panel(a, o):
    keys = a.ingame_keys()
    from .nextcard import GAME_KEYS
    pickers = []
    for action, label in (('comment', _('COMMENT')), ('close', _('CLOSE'))):
        items = [('%s-%s' % (action, k), k) for k in GAME_KEYS]
        pickers.append(row(size(txt(label, 15, 'bold', FG2), w=120, va='c'), sp(8),
                           row(*[choice('key', arg, k, k == keys[action], sz=15, p=[8, 5, 8, 5],
                                        pad=[0 if i == 0 else 4, 0, 0, 0]) for i, (arg, k) in enumerate(items)]),
                           pad=[0, 0 if not pickers else 6, 0, 0]))
    scale = '%d %%' % round(100 * float(o.get('scale') or 1.0))
    how_big = row(choice('size', 'down', '−', False, p=[14, 4, 14, 4]),
                  size(txt(scale, 18, 'bold', WHITE, j=1), w=80, va='c'),
                  choice('size', 'up', '+', False, p=[14, 4, 14, 4]))
    places = [('dock', _('BY THE TIMER')), ('top', _('TOP')), ('bottom', _('BOTTOM'))]
    return panel(_('Timer'),
                 setting(_('Show the timer'), _("ACR Daily's timer in the game, with the split standings under it."),
                         switch('timer', bool(o.get('visible', True)))),
                 setting(_('Size'), _("How big ACR Daily's displays are in the game."), how_big),
                 setting(_('Only on a stage'), _("ACR Daily's displays show only while a daily's, an event's or a time "
                                                 'trial stage is loaded in the game.'),
                         switch('only', bool(o.get('onlyOnDaily', True)))),
                 setting(_('Place in the game'), _("Where ACR Daily's displays sit: by the game's timer, top or bottom."),
                         under=choices('place', places, a.ingame_place())),
                 setting(_('Our clock in the game'), _("Only if you hide the game's HUD: ACR Daily's clock under its "
                                                       'displays.'),
                         switch('clock', bool(o.get('inGameClock')))),
                 setting(_('Keys in the game'), _('The keys for the comment card after a run: write a comment, close.'),
                         under=col(*pickers)))


def displays_panel(a):
    from . import widgets
    words = {'strip': _('The stage from the start (bottom) to the finish (top): your car, the ghosts and the drivers on it '
                        'right now.'),
             'delta': _('Your gap to P1, and whether you are gaining or losing over the last 10 s.')}
    rows = [setting(widgets.LABELS[key], words.get(key, ''),
                    row(choice('widget', key + '-on', _('ON'), a._widget_on(key), GOOD),
                        choice('widget', key + '-off', _('OFF'), not a._widget_on(key), SOFT, pad=[6, 0, 0, 0])))
            for key in widgets.SHOWN]
    on = a.ghost_cars_on()
    under = None
    if on:
        cfg = ghost_cfg(a)
        status = getattr(getattr(a, 'ghostcars', None), 'status', None) or ''
        keeper = getattr(a, 'gamemod', None)
        note = keeper.note() if keeper is not None and hasattr(keeper, 'note') else ''
        under = col(row(txt(_('Show through trees and hills'), 17, 'semi', SOFT, va='c', fill=1),
                        switch('always', bool(cfg.get('always')))),
                    row(size(txt(_('Live server'), 17, 'semi', SOFT), w=160, va='c'),
                        box(edit(_id('liveServer'), cfg.get('liveServer') or '', '', fill=1), bg=PANEL2,
                            p=[12, 6, 12, 6], r=2, ol=LINE2, fill=1), pad=[0, 8, 0, 0]),
                    txt(' · '.join(x for x in (status, note) if x), 15, 'medium', MUTED, wrap=True, pad=[0, 8, 0, 0])
                    if (status or note) else None)
    rows.append(setting(_('Ghost cars (test)'), _('The drivers on your stage right now, as cars in the game.'),
                        switch('ghosts', on), under))
    return panel(_('In-game displays'), *rows, first=True)


def ghost_cfg(a):
    from . import ghostui
    return ghostui.config(a.s)


def account_panel(a):
    signed = bool(a.s.get('token'))
    who = (a.s.get('name') or _('Signed in')) if signed else _('Not signed in')
    control = quiet(_id('signout'), _('SIGN OUT')) if signed else quiet(_id('signin'), _('SIGN IN WITH STEAM'))
    return panel(_('Account'),
                 setting(who, _('Your runs go on the boards under the Steam account signed in here.'), control))


def save_panel():
    return panel(_('Game save'),
                 setting(_('Restore the save'), _('DRIVE keeps a backup of the game\'s save before each set-up: this '
                                                  'puts back the one from before the last.'),
                         quiet(_id('restore'), _('RESTORE'))),
                 setting(_('Send diagnostics'), _('A time did not arrive, or a run went in as a DNF for no reason? Send '
                                                  "ACR Daily the app's notes and the game's save, with a line on what "
                                                  'happened. You get a number to quote.'),
                         quiet(_id('diag'), _('SEND'))))


def about_panel(a, m):
    links = row(*[link(_id(action), label, pad=[0 if i == 0 else 22, 0, 0, 0])
                  for i, (action, label) in enumerate((('guide', _('How to play ›')), ('site', _('Website ›')),
                                                       ('discord', _('Discord ›')), ('credits', _('Photo credits ›'))))],
                pad=[0, 14, 0, 0])
    return panel(_('About'),
                 setting(_('ACR Daily %s (beta)') % __version__, _('Two daily stages, random cars and one leaderboard for '
                                                                  'Assetto Corsa Rally. Open source (MIT licence).'),
                         quiet(_id('whatsnew'), _("WHAT'S NEW"))),
                 news(m) if m.get('news') else None,
                 links,
                 credits(m) if m.get('credits') else None,
                 txt(_('A fan project, not affiliated with the makers of Assetto Corsa Rally. Photos: Wikimedia Commons '
                       '(CC BY, CC0, public domain). Icons: Lucide (ISC licence).'), 14, 'medium', MUTED, wrap=True,
                     pad=[0, 14, 0, 0]))


def news(m):
    """WHAT'S NEW opened in the page: this version's changes (the server's changelog), and the versions before it."""
    from . import whatsnew
    n = m.get('news')
    if n == 'loading':
        return txt(_('Loading…'), 17, 'medium', MUTED, pad=[0, 12, 0, 0])
    if not isinstance(n, dict):
        return col(txt(_('The server can\'t be reached.'), 17, 'medium', MUTED),
                   link(_id('changelog'), _('Full changelog on the website ›'), pad=[0, 6, 0, 0]), pad=[0, 12, 0, 0])

    def lines(e, big):
        out = []
        kinds = e.get('kinds') or []
        for i, words in enumerate(e.get('changes') or []):
            kd = kinds[i] if i < len(kinds) else None
            tag = whatsnew.KINDS.get(kd)
            if tag:
                mark = size(box(txt(_(tag[0]), 13, 'bold', WHITE if tag[2] else _hex(tag[1]), sp=60, j=1),
                                bg=_hex(tag[1]) if tag[2] else '-', ol=None if tag[2] else _hex(tag[1]), p=[6, 1, 6, 1],
                                r=2), w=96, va='t')
            else:
                mark = size(box(None, bg=ACC), w=6, h=6, va='t', pad=[0, 8, 0, 0])
            out.append(row(mark,
                           sp(12), txt(words, 17 if big else 15, 'medium', SOFT if big else FG2, wrap=True, fill=1),
                           pad=[0, 6, 0, 0]))
        return out
    parts = [kicker(_("WHAT'S NEW IN %s") % n.get('version', __version__), fg=WHITE),
             txt(n.get('title') or '', 22, 'bold', WHITE, wrap=True, pad=[0, 4, 0, 0]) if n.get('title') else None,
             txt(whatsnew.day(n.get('date')), 15, 'medium', MUTED) if n.get('date') else None]
    parts += lines(n, True)
    earlier = (n.get('earlier') or [])[:NEWS_EARLIER]
    if earlier:
        parts.append(kicker(_('EARLIER VERSIONS'), pad=[0, 16, 0, 0]))
        for e in earlier:
            parts.append(txt('%s   ·   %s' % (e.get('version', ''), whatsnew.day(e.get('date'))), 15, 'bold', MUTED,
                             pad=[0, 10, 0, 0]))
            if e.get('title'):
                parts.append(txt(e['title'], 18, 'semi', WHITE, wrap=True))
            parts += lines(e, False)
    parts.append(link(_id('changelog'), _('Full changelog on the website ›'), pad=[0, 12, 0, 0]))
    return box(col(*parts), bg=PANEL2, p=[18, 14, 18, 16], pad=[0, 14, 0, 0])


def _hex(c):
    return (c or '').lstrip('#') or WHITE


def credits(m):
    """Photo credits opened in the page: who took each photo, its licence (each a link to its page), the software."""
    from . import photos
    rows = [kicker(_('PHOTO CREDITS'), fg=WHITE)]
    for i, (what, title, author, licence, _url) in enumerate(photos.credits()):
        name = title.rsplit('.', 1)[0] if title.lower().endswith('.jpg') else title
        rows.append(row(size(txt(what.replace('-', ' ').upper(), 14, 'bold', FG2), w=150, va='c'),
                        link(_id('photo', i), '%s · %s · %s  ›' % (name, author, licence), sz=15, fill=1),
                        pad=[0, 6, 0, 0]))
    rows.append(txt(_('Cut to size and darkened for the words on them.'), 14, 'medium', MUTED, pad=[0, 8, 0, 0]))
    rows.append(row(size(txt(_('SOFTWARE'), 14, 'bold', FG2), w=150, va='c'),
                    link(_id('7zip'), _('7-Zip by Igor Pavlov · GNU LGPL, unRAR restriction · unpacks .rar and .7z '
                                        'liveries') + '  ›', sz=15, fill=1), pad=[0, 10, 0, 0]))
    return box(col(*rows), bg=PANEL2, p=[18, 14, 18, 16], pad=[0, 14, 0, 0])


def admin_panel(a):
    if not a.s.get('admin'):
        return None
    rec = getattr(a, 'recorder', None)
    msg = getattr(rec, 'message', '') if rec is not None else ''
    return panel(_('Admin'),
                 row(quiet(_id('record'), _('RECORD ROUTE')), sp(8), quiet(_id('upload'), _('UPLOAD ROUTE')),
                     pad=[0, 14, 0, 0]),
                 txt(msg, 15, 'medium', MUTED, wrap=True, pad=[0, 8, 0, 0]) if msg else None)


# ---------------------------------------------------------------------- the buttons
def click(ig, action, arg):
    a = ig.app
    o = a.s.setdefault('overlay', {})
    on = arg == 'on'
    if action == 'lang':
        ask_language(ig, arg)
    elif action == 'win':
        from . import app as app_mod
        if arg != (a.s.get('windowSize') or app_mod.WINDOW_DEFAULT):
            a.set_window_size(arg)
    elif action == 'auto':
        if on != bool(a.s.get('autoDrive', False)):
            a.toggle_auto_drive()                    # (turning it on asks first: in the game)
    elif action == 'notify':
        if on != bool(a.s.get('notify', True)):
            a.toggle_notify()
    elif action == 'timer':
        if on != bool(o.get('visible', True)):
            a.toggle_overlay(on)
    elif action == 'size':
        ov = getattr(a, 'overlay', None)
        if ov is not None:
            ov.resize(SIZE_STEP if arg == 'up' else 1 / SIZE_STEP)
    elif action == 'only':
        if on != bool(o.get('onlyOnDaily', True)):
            a.toggle_only_daily()
    elif action == 'place':
        if arg != a.ingame_place():
            a.set_ingame_place(arg)
    elif action == 'clock':
        if on != bool(o.get('inGameClock')):
            a.toggle_ingame_clock()
    elif action == 'key':
        what, _sep, key = (arg or '').partition('-')
        a.set_ingame_key(what, key)                  # (a key another button had: they swap)
    elif action == 'widget':
        key, _sep, state = (arg or '').partition('-')
        if key in (getattr(a, 'widgets', None) or {}) and (state == 'on') != a._widget_on(key):
            a.toggle_widget(key)
    elif action == 'ghosts':
        set_ghosts(a, on)
    elif action == 'always':
        cfg = ghost_cfg(a)
        if on != bool(cfg.get('always')):
            cfg['always'] = on
            a.save_settings()
    elif action == 'signout':
        if a.s.get('token'):
            ig.ask(_('Sign out?'), [a.s.get('name') or ''], _('SIGN OUT'),
                   lambda: a.login_click() if a.s.get('token') else None)
    elif action == 'signin':
        ig.window(TAB)                               # (the sign-in screen is the window's: Steam in the browser)
    elif action == 'restore':
        a.restore_click()                            # (asks first: in the game)
    elif action == 'diag':
        a.diagnostics_click()                        # (asks for a line: in the game)
    elif action == 'whatsnew':
        whats_new(ig)
    elif action == 'changelog':
        from . import whatsnew
        n = ig.mem(TAB).get('news')
        webbrowser.open(whatsnew.url(a, n.get('version') if isinstance(n, dict) else __version__))
    elif action == 'credits':
        m = ig.mem(TAB)
        m['credits'] = not m.get('credits')
    elif action == 'photo':
        from . import photos
        try:
            url = photos.credits()[int(arg)][4]
        except (IndexError, TypeError, ValueError):
            url = None
        if url:
            webbrowser.open(url)
    elif action == '7zip':
        webbrowser.open('https://www.7-zip.org/license.txt')
    elif action == 'guide':
        a.open_guide()
    elif action == 'site':
        a.open_site()
    elif action == 'discord':
        a.open_discord()
    elif action == 'record' and a.s.get('admin'):
        a.record_click()
    elif action == 'upload' and a.s.get('admin'):
        a.upload_click()


def text(ig, field, words):
    if field == 'liveServer':
        cfg = ghost_cfg(ig.app)
        words = (words or '').strip()
        if words != (cfg.get('liveServer') or ''):
            cfg['liveServer'] = words
            ig.app.save_settings()


def ask_language(ig, code):
    """The window's set_language, asked in the game first: YES starts the app again in it (set_language with its
    question answered), NO changes nothing. Driving, or a run waiting for its time: set_language says it comes next
    time."""
    a = ig.app
    if code not in i18n.CODES or code == a.s.get('lang', i18n.lang()) and code == i18n.lang():
        return
    busy = (getattr(a, '_driving', None) and a._driving()) or (getattr(a, '_waiting_text', None) and a._waiting_text())
    if busy:
        a.set_language(code)
        return
    question = i18n.word_in(code, 'Start ACR Daily again now, in %s?') % i18n.NAMES[code]
    ig.ask(i18n.NAMES[code], [question], _('YES'),
           lambda: ig.run(lambda: a.set_language(code), {('ACR Daily', question): True}), _('NO'))


def set_ghosts(a, on):
    """Ghost cars on / off as the window's switch (app.toggle_ghosts), but turned on without its SET UP window (behind
    the game it would sit unseen; its settings are under the switch here)."""
    if on == a.ghost_cars_on():
        return
    if not on or getattr(a, 'ghost_setup', None) is not None:
        a.toggle_ghosts()
        return
    cfg = ghost_cfg(a)
    cfg['on'] = True
    a.save_settings()
    a.ghost_buttons()
    a.poke_game_mod()


def whats_new(ig):
    """WHAT'S NEW: open in the page (the server's changelog, asked in a thread, as whatsnew.reopen), or closed again."""
    a = ig.app
    m = ig.mem(TAB)
    if m.get('news') not in (None, 'failed'):
        m['news'] = None
        return
    m['news'] = 'loading'

    def go():
        try:
            entry = a.api.changelog(__version__, since='0')
        except Exception:
            entry = None
        m['news'] = entry if entry and entry.get('changes') else 'failed'
    threading.Thread(target=go, daemon=True).start()
