"""CASUAL in the game (the second tab of CODRIVER, ig_copilot.py; casual.py says how it works): a lobby browser (public
ones with a click, private ones with their code), set up your own (stage, car, weather, time, up to three languages you
are happy to talk in, public or private), and your lobby: who is in, the QR code for the notes on a phone (for a
co-driver without the game), the voice, START. Languages show as flags to keep the words few."""
import os

from . import settings
from .casual import LANG_FLAG, LANGS, MAX_LANGS
from .i18n import _, n_
from . import i18n
from .ingamekit import (ACC, BAD, BG, FG2, GOOD, LINE2, MUTED, PANEL, PANEL2, SLOW, SOFT, WHITE, box, btn, chip, col, edit,
                        empty, img, kicker, primary, quiet, row, scroll, size, sp, tab_id, txt)

TAB = 'casual'
COLOUR = 'FF9F0A'
LOBBIES_SHOWN = 14
FIELDS = (('stage', _('Stage')), ('car', _('Car')), ('weather', _('Weather')), ('time', _('Time of day')))
QR_DIR = os.path.join('hud', 'app')


def _cs(ig):
    return getattr(ig.app, 'casual', None)


def opened(ig):
    cs = _cs(ig)
    if cs is not None:
        cs.refresh(force=True)


# ---------------------------------------------------------------------- languages as flags
def flags(langs, size_=(27, 18)):
    """The languages as small flags (the country most often meant; its code beside while the picture comes)."""
    from .ig_ranked import flag_png
    out = []
    for i, code in enumerate(langs or []):
        cc = LANG_FLAG.get(code, '')
        png = flag_png(cc) if cc else None
        out.append(img(png, size_[0], size_[1], va='c', pad=[0 if i == 0 else 6, 0, 0, 0]) if png else
                   txt(code.upper(), 14, 'bold', FG2, va='c', pad=[0 if i == 0 else 6, 0, 0, 0]))
    return row(*out, va='c') if out else None


# ---------------------------------------------------------------------- what can be picked
def options(ig, field):
    """[(value, label)] for a field of the set-up form, from the server's list."""
    o = _cs(ig).options or {}
    if field == 'stage':
        return [(s['track'], '%s · %s' % (s.get('rally') or '', s.get('menuName') or s.get('stageName') or s['track']))
                for s in o.get('stages') or []]
    if field == 'car':
        return [(c['id'] or c['name'], c['name']) for c in o.get('cars') or []]
    if field == 'weather':
        return [(w['code'], w['label']) for w in o.get('weather') or []]
    if field == 'time':
        return [(t['code'], t['label']) for t in o.get('times') or []]
    if field == 'lang':
        return [(c, c.upper()) for c in LANGS]
    return []


def chosen(ig, field):
    """The value picked for a field, else the first of its list (the language: the app's own, to start with)."""
    m = ig.mem(TAB)
    if field == 'lang':
        if 'langs' not in m:
            m['langs'] = [i18n.lang()] if i18n.lang() in LANGS else ['en']
        return m['langs']
    opts = options(ig, field)
    v = (m.get('sel') or {}).get(field)
    if v in [o[0] for o in opts]:
        return v
    if field == 'time':                                   # (midday: the game's default light)
        return next((o[0] for o in opts if o[0] == 'midday'), opts[0][0] if opts else None)
    return opts[0][0] if opts else None


def label_of(ig, field):
    v = chosen(ig, field)
    return next((l for k, l in options(ig, field) if k == v), '–')


# ---------------------------------------------------------------------- the page
def page(ig):
    cs = _cs(ig)
    if cs is None:
        return empty(_('CASUAL is not in this version of the app.'))
    cs.refresh()
    if not ig.app.s.get('token'):
        return txt(_('Sign in with Steam to play CASUAL (PROFILE, or the app\'s window).'), 20, 'medium', SOFT)
    if cs.enabled is None:
        return col(kicker(_('Casual')), txt(cs.msg or _('Loading…'), 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    if not cs.enabled:
        return col(kicker(_('Casual')), txt(_('No CASUAL on this server yet.'), 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    m = ig.mem(TAB)
    if cs.lobby and cs.lobby.get('state') in ('open', 'started'):
        return _lobby(ig, cs)
    if m.get('pick'):
        return _picker(ig, cs, m['pick'])
    note = txt(cs.msg, 17, 'semi', BAD, wrap=True, pad=[0, 0, 0, 10]) if cs.msg else None
    return col(note, row(size(_setup(ig, cs), w=700), sp(28), col(_browser(ig, cs), fill=1), al='f'))


def _setup(ig, cs):
    m = ig.mem(TAB)
    private = bool(m.get('private'))
    rows = []
    for key, word in FIELDS:
        rows.append(row(size(txt(word, 17, 'semi', FG2, va='c'), w=170),
                        size(quiet(tab_id(TAB, 'open', key), label_of(ig, key) + '  ›', fg=WHITE, cal='l', al='f'), minw=480),
                        pad=[0, 6, 0, 0], va='c'))
    langs = chosen(ig, 'lang')
    rows.append(row(size(txt(_('I speak'), 17, 'semi', FG2, va='c'), w=170),
                    btn(tab_id(TAB, 'open', 'lang'), c=row(flags(langs) or txt(_('pick up to 3'), 16, 'medium', MUTED, va='c'),
                                                           sp(fill=1), txt('›', 17, 'semi', SOFT, va='c'), va='c'),
                        bg='-', hov=PANEL2, p=[20, 8, 20, 8], r=2, ol=LINE2),
                    pad=[0, 6, 0, 0], va='c'))
    pick = lambda key, label, on: btn(tab_id(TAB, 'priv', key), label, bg=WHITE if on else '-', hov=ACC,
                                      fg=BG if on else SOFT, hfg=WHITE, sz=17, f='bold', sp=60, p=[18, 7, 18, 7], r=2,
                                      ol=None if on else LINE2, pad=[8, 0, 0, 0])
    vis = row(pick('public', _('PUBLIC'), not private), pick('private', _('PRIVATE'), private), pad=[0, 12, 0, 0])
    return box(col(kicker(_('Set up a lobby'), fg=COLOUR), col(*rows, pad=[0, 10, 0, 0]), vis,
                   row(primary(tab_id(TAB, 'create'), _('SET UP  ›')), pad=[0, 16, 0, 0]),
                   row(txt(_('You drive; up to 3 co-drivers read the notes. Alone is fine.'), 15, 'medium', MUTED, wrap=True,
                           pad=[0, 12, 0, 0]))), bg=PANEL, p=[24, 18, 24, 20])


def _browser(ig, cs):
    m = ig.mem(TAB)
    rows = []
    for x in cs.lobbies[:LOBBIES_SHOWN]:
        host = x.get('host') or {}
        st = x.get('stage') or {}
        car = (x.get('car') or {}).get('name') or ''
        n, mx = x.get('count') or 0, x.get('max') or 4
        started = x.get('state') == 'started'
        full = n >= mx
        what = col(txt(host.get('name') or '?', 19, 'bold', WHITE),
                   txt(' · '.join(p for p in (st.get('menuName') or st.get('stageName'), car, (x.get('weather') or {}).get('label'),
                                              (x.get('time') or {}).get('label')) if p), 14, 'semi', FG2, wrap=True), fill=1)
        count = chip('%d / %d' % (n, mx), bg=GOOD if not full else LINE2, fg=BG if not full else SOFT, pad=[10, 0, 0, 0], va='c')
        if x.get('mine'):
            action = chip(_('YOURS'), bg=COLOUR, fg=BG, va='c')
        elif started:
            action = chip(_('ON THE STAGE'), bg=ACC, va='c')
        elif full:
            action = chip(_('FULL'), bg=LINE2, fg=SOFT, va='c')
        else:
            action = quiet(tab_id(TAB, 'join', x['id']), _('JOIN WITH CODE') if x.get('private') else _('JOIN'), va='c')
        lock = chip(_('PRIVATE'), bg=PANEL, fg=SOFT, ol=LINE2, pad=[8, 0, 0, 0], va='c') if x.get('private') else None
        rows.append(box(row(what, flags(x.get('langs')), count, lock, sp(14), action, va='c'), bg=PANEL2, p=[16, 8, 16, 8],
                        pad=[0, 6, 0, 0]))
    if not rows:
        rows = [txt(_('No lobbies yet: set one up, or ask a friend for their code.'), 17, 'medium', MUTED, pad=[0, 6, 0, 0])]
    code = row(txt(_('Got a code?'), 17, 'semi', FG2, va='c'), sp(12),
               size(box(edit(tab_id(TAB, 'code'), m.get('code') or '', _('CODE')), bg=PANEL2, p=[12, 6, 12, 6], ol=LINE2), w=200),
               sp(10), quiet(tab_id(TAB, 'joincode'), _('JOIN')), va='c', pad=[0, 14, 0, 0])
    return box(col(row(kicker(_('Lobbies'), fg=COLOUR), sp(fill=1), quiet(tab_id(TAB, 'refresh'), _('REFRESH'), va='c'), va='c'),
                   *rows, code), bg=PANEL, p=[24, 18, 24, 20])


def _picker(ig, cs, field):
    """A field's list in the place of the page: a click picks (languages: a click toggles, up to 3)."""
    opts = options(ig, field)
    on = chosen(ig, field)
    per, gap = (6, 8) if field == 'lang' else (2, 10)
    w = (1800 - 48 - gap * (per - 1)) // per
    rows = []
    for i in range(0, len(opts), per):
        cells = []
        for j, (key, lab) in enumerate(opts[i:i + per]):
            here = (key in on) if field == 'lang' else key == on
            body = row(flags([key]) if field == 'lang' else None, sp(10) if field == 'lang' else None,
                       txt(lab, 17, 'semi', BG if here else SOFT, va='c'), va='c')
            cells.append(size(btn(tab_id(TAB, 'pick', key), c=body, bg=WHITE if here else '-', hov=ACC if not here else WHITE,
                                  p=[18, 8, 18, 8], r=2, ol=None if here else LINE2), w=w, pad=[0 if j == 0 else gap, 0, 0, 0]))
        rows.append(row(*cells, pad=[0, 0 if i == 0 else gap, 0, 0]))
    word = dict(FIELDS).get(field, _('Languages (up to %d)') % MAX_LANGS)
    head = row(kicker(word, fg=COLOUR), sp(fill=1), primary(tab_id(TAB, 'unpick'), _('DONE')), va='c', pad=[0, 0, 0, 12])
    return box(col(head, size(scroll(*(rows or [empty(_('Nothing to pick.'))]), id='casual:pick:%s' % field), h=760)),
               bg=PANEL, p=[24, 18, 24, 20])


# ---------------------------------------------------------------------- my lobby
def qr_file(url):
    """The QR code of an address as a PNG next to the pages' pictures (made once for each address) -> its path, or None."""
    if not url:
        return None
    import hashlib
    from . import qrcode_min
    path = os.path.join(settings.DIR, QR_DIR, 'qr-%s.png' % hashlib.sha1(url.encode()).hexdigest()[:12])
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            qrcode_min.write_png(path + '.tmp', url, 6, 3)
            os.replace(path + '.tmp', path)
        except (OSError, ValueError):
            return None
    return path


def speakers(cs, small=False):
    """Small speaker icons, one for each person in the lobby, lit while they talk (the user: to see if someone speaks, and to
    troubleshoot): a dot and the name; green while heard, dim otherwise."""
    items = []
    for name, seat, on in cs.speakers():
        items.append(row(box(None, bg=GOOD if on else LINE2, r=8), sp(8), txt(name, 15, 'bold' if on else 'semi', WHITE if on else MUTED,
                                                                              va='c'), va='c', pad=[0, 0, 18, 0]))
    return row(kicker(_('Voice'), va='c'), sp(12), *[size(i, h=24) for i in items], va='c')


def _member(m, me):
    ready = chip(_('READY'), bg=GOOD, fg=BG) if m.get('ready') or m.get('seat') == 0 else chip(_('NOT READY'), bg=LINE2, fg=SOFT)
    role = _('DRIVER') if m.get('role') == 'driver' else _('CO-DRIVER')
    mine = m.get('steamId') == me.get('steamId')
    return box(row(kicker(role, fg=COLOUR if m.get('seat') == 0 else MUTED), sp(14),
                   txt((m.get('name') or '?') + ('  ·  ' + _('YOU') if mine else ''), 20, 'bold', WHITE), sp(fill=1), ready,
                   va='c'), bg=PANEL2, p=[18, 10, 18, 10], pad=[0, 6, 0, 0])


def _lobby(ig, cs):
    l = cs.lobby
    me = cs.me()
    host = cs.is_host()
    started = l.get('state') == 'started'
    st, car = l.get('stage') or {}, (l.get('car') or {}).get('name') or ''
    note = txt(cs.msg, 17, 'semi', BAD, wrap=True, pad=[0, 0, 0, 10]) if cs.msg else None
    stage = col(kicker(_('Stage'), fg=COLOUR), txt((st.get('menuName') or st.get('stageName') or '').upper(), 26, 'bold', WHITE, wrap=True),
                txt(' · '.join(p for p in (st.get('rally'), car, (l.get('weather') or {}).get('label'),
                                           (l.get('time') or {}).get('label')) if p), 16, 'semi', FG2, wrap=True),
                row(flags(l.get('langs')), pad=[0, 8, 0, 0]) if l.get('langs') else None)
    code = row(kicker(_('Private · code'), va='c'), sp(10),
               box(txt(l['code'], 26, 'bold', WHITE, sp=200), bg=BG, p=[14, 2, 14, 2], ol=COLOUR),
               sp(12), txt(_('Give it to your co-drivers.'), 15, 'semi', MUTED, va='c'), pad=[0, 10, 0, 0]) if l.get('code') else None
    members = col(*[_member(m, me) for m in cs.members()],
                  txt(n_('%d free seat', '%d free seats', l.get('free') or 0) % (l.get('free') or 0), 15, 'medium', MUTED,
                      pad=[0, 8, 0, 0]) if not started else None)
    if started:
        say = (_('Your stage is on. Drive it: your co-drivers read the notes.') if host else
               _('The stage is on. You watch from the passenger seat: Up / Down move through the notes (Left / Right: five).'))
        go = primary(tab_id(TAB, 'go'), (_('DRIVE  ›') if host else _('TO THE CAR  ›')))
        buttons = row(go, sp(14), quiet(tab_id(TAB, 'leave'), _('LEAVE')))
        hint = txt(say, 18, 'medium', SOFT, wrap=True, pad=[0, 10, 0, 10])
    else:
        ready_btn = (primary(tab_id(TAB, 'start'), _('START  ›')) if host else
                     quiet(tab_id(TAB, 'unready'), _('NOT READY')) if me and _is_ready(cs) else primary(tab_id(TAB, 'ready'), _('READY')))
        buttons = row(ready_btn, sp(14), quiet(tab_id(TAB, 'leave'), _('LEAVE')), sp(16),
                      txt(_('Start when you like, even alone.') if host else _('Waiting for the driver to start.'), 15, 'semi',
                          MUTED, va='c'))
        hint = None
    left = box(col(stage, code, note, members, hint, buttons, row(_voice(ig, cs), pad=[0, 14, 0, 0])), bg=PANEL, p=[24, 18, 24, 20])
    right = _qr_panel(cs)
    return row(col(left, fill=1), sp(24), right, al='f') if right else left


def _is_ready(cs):
    return any(m.get('steamId') == cs.me().get('steamId') and m.get('ready') for m in cs.members())


def _voice(ig, cs):
    from .ig_copilot import _voice_line
    return col(_voice_line(ig, cs), speakers(cs))


def _qr_panel(cs):
    url = cs.notes_url()
    path = qr_file(url)
    if not path:
        return None
    return size(box(col(kicker(_('Notes on a phone'), fg=COLOUR),
                        txt(_('A co-driver without the game: scan this, and read this stage\'s notes.'), 16, 'medium', SOFT,
                            wrap=True, pad=[0, 6, 0, 10]),
                        img(path, 300, 300, al='c'), txt(url.replace('https://', ''), 13, 'semi', MUTED, wrap=True, j=1,
                                                         pad=[0, 8, 0, 0])), bg=PANEL, p=[22, 18, 22, 20]), w=380)


# ---------------------------------------------------------------------- clicks
def click(ig, action, arg):
    cs = _cs(ig)
    if cs is None:
        return
    m = ig.mem(TAB)
    if action == 'open':
        m['pick'] = arg
    elif action in ('unpick', 'refresh'):
        if action == 'unpick':
            m['pick'] = None
        else:
            cs.refresh(force=True)
    elif action == 'pick' and m.get('pick'):
        field = m['pick']
        if field == 'lang':
            langs = list(chosen(ig, 'lang'))
            if arg in langs:
                langs.remove(arg)
            elif len(langs) < MAX_LANGS:
                langs.append(arg)
            m['langs'] = langs
        else:
            m.setdefault('sel', {})[field] = arg
            m['pick'] = None
    elif action == 'priv':
        m['private'] = arg == 'private'
    elif action == 'create':
        cs.create({'track': chosen(ig, 'stage'), 'car': chosen(ig, 'car'), 'weather': chosen(ig, 'weather'),
                   'time': chosen(ig, 'time'), 'langs': list(chosen(ig, 'lang')), 'private': bool(m.get('private'))})
    elif action == 'join' and arg:
        x = next((l for l in cs.lobbies if str(l.get('id')) == str(arg)), None)
        if x and x.get('private'):
            _ask_code(ig, cs, int(arg))
        else:
            cs.join(lobby_id=int(arg))
    elif action == 'joincode':
        code = ''.join((m.get('code') or '').split()).upper()
        if code:
            cs.join(code=code)
    elif action == 'ready':
        cs.ready(True)
    elif action == 'unready':
        cs.ready(False)
    elif action == 'start':
        cs.start()
    elif action == 'leave':
        if cs.started() and cs.is_host() and not cs.solo():
            ig.ask(_('LEAVE'), [_('The stage is on: your co-drivers lose their driver.')], _('LEAVE'), cs.leave, safe=True)
        else:
            cs.leave()
    elif action == 'go':
        cs.started_id = None
        cs.go()


def _ask_code(ig, cs, lobby_id):
    ig._dialog_words = ''

    def go():
        code = ''.join((getattr(ig, '_dialog_words', '') or '').split()).upper()
        if code:
            cs.join(lobby_id=lobby_id, code=code)
    ig.dialog = {'title': _('PRIVATE LOBBY'), 'lines': [_('Its code (the one who set it up has it):')],
                 'go': (_('JOIN'), go), 'cancel': _('CANCEL'), 'field': ''}


def text(ig, field, words):
    if field == 'code':
        ig.mem(TAB)['code'] = words
