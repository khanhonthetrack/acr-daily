"""COPILOT in the game (EVENTS' third sub-tab; copilot.py says how it works): today's crew stage as a "?" until you
have driven it; your lobby (or setting one up: driver or co-driver, public or private with a code); every lobby of the
day (the lobby browser: public ones joined with a click, private ones with their code); today's crews and this month's
ranking of drivers and of co-drivers. The voice's settings are in SETTINGS (settings_panel). Over the stage: the
co-driver's notes to scroll, the rules (what is a DNF); for the driver, the co-driver's voice and the link."""
from .copilot import CP_SLOT, ROLE_NAMES, TALK_MODES, TALK_NAMES, settings_of
from .i18n import _
from .ingamekit import (ACC, BAD, BG, FG2, GOOD, LINE2, MUTED, PANEL, PANEL2, SLOW, SOFT, WHITE, box, btn, chip, col, edit,
                        empty, fmt_ms, kicker, primary, quiet, row, size, sp, tab_id, tabs, txt)

TAB = 'copilot'
COLOUR = 'FF9F0A'                        # COPILOT's colour (the pacenote book's orange)
NOTES_SHOWN = 9                          # notes on screen over the stage (the one on in the middle)
LOBBIES_SHOWN = 12
RANK_SHOWN = 15
NAVY = '0A1428'
SIDES = (('board', _('TODAY')), ('drivers', _('DRIVERS')), ('codrivers', _('CO-DRIVERS')))
RULES = _('Changing the game\'s settings, driving aids, its co-driver or pacenotes during the stage is a DNF for the crew.')


def _cp(ig):
    return getattr(ig.app, 'copilot', None)


def opened(ig):
    cp = _cp(ig)
    if cp is not None:
        cp.refresh(force=True)


def page(ig):
    cp = _cp(ig)
    if cp is None:
        return empty(_('COPILOT is not in this version of the app.'))
    cp.refresh()
    d = cp.day
    if d is None:
        return col(kicker(_('Copilot')), txt(cp.msg or _('Loading today\'s COPILOT…'), 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    if not d.get('on'):
        return col(kicker(_('Copilot')), txt(_('No COPILOT on this server yet.'), 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    if not ig.app.s.get('token'):
        return col(_stage_card(d), txt(_('Sign in with Steam to drive COPILOT (PROFILE, or the app\'s window).'), 20,
                                       'medium', SOFT, pad=[0, 18, 0, 0]))
    left = col(_stage_card(d), sp(h=16), _lobby_part(ig, cp, d), sp(h=16), _browser(ig, cp, d), fill=1)
    right = size(_standings(ig, cp), w=640)
    return row(left, sp(28), right, al='f')


def _stage_card(d):
    """Today's crew stage: a "?" until you have driven it; then the stage, car and conditions."""
    tries = d.get('tries') or {}
    done = lambda r: _('done') if tries.get(r) else _('not yet')
    if d.get('revealed') and d.get('stage'):
        s = d['stage']
        mark = box(txt('✓', 52, 'bold', GOOD, j=1), bg=PANEL2, p=[26, 4, 26, 4], va='c')
        title = (s.get('menuName') or s.get('stageName') or '').upper()
        sub = ' · '.join(x for x in (s.get('rally'), s.get('car'), s.get('weatherLabel'), s.get('timeLabel')) if x)
    else:
        mark = box(txt('?', 70, 'bold', BG, j=1), bg=COLOUR, p=[30, 0, 30, 0], va='c')
        title = _('HIDDEN UNTIL YOU DRIVE IT')
        sub = _('The stage, the car and the weather: you find out on the start line.')
    what = col(kicker(_('Today\'s stage'), fg=COLOUR), txt(title, 26, 'bold', WHITE, wrap=True),
               txt(sub, 16, 'semi', FG2, wrap=True, pad=[0, 2, 0, 0]),
               txt(_('Hardcore Mode · once as the driver (%s), once as the co-driver (%s)') % (done('driver'), done('codriver')),
                   15, 'semi', MUTED, wrap=True, pad=[0, 6, 0, 0]), fill=1)
    return box(row(mark, sp(22), what, va='c'), bg=PANEL, p=[22, 16, 22, 16])


def _person(p, label):
    if not p:
        return box(col(kicker(label), txt(_('Waiting for someone to join…'), 20, 'semi', MUTED)), bg=PANEL2, p=[18, 12, 18, 12],
                   fill=1)
    ready = chip(_('READY'), bg=GOOD, fg=BG) if p.get('ready') else chip(_('NOT READY'), bg=LINE2, fg=SOFT)
    return box(col(row(kicker(ROLE_NAMES.get(p.get('role'), '')), sp(fill=1), ready),
                   txt(p.get('name') or '?', 22, 'bold', WHITE, pad=[0, 4, 0, 0])), bg=PANEL2, p=[18, 12, 18, 12], fill=1)


def _voice_line(ig, cp):
    """The voice as set (SETTINGS has it), and what it does now: talking, hearing, the link."""
    c = settings_of(ig.app.s)
    how = TALK_NAMES[c['talk']] + ((' · %s' % c['key']) if c['talk'] == 'ptt' else '')
    out = [kicker(_('Voice'), va='c'), sp(10), txt(how, 16, 'bold', WHITE, va='c'), sp(10),
           txt(_('(SETTINGS › COPILOT VOICE)'), 14, 'semi', MUTED, va='c'), sp(fill=1)]
    v = cp.voice
    if v is not None:
        out += [chip(_('TALKING'), bg=GOOD, fg=BG, va='c') if v.talking else None,
                chip(_('HEARING'), bg=COLOUR, fg=BG, va='c', pad=[6, 0, 0, 0]) if v.hearing else None]
        if not getattr(v, 'mic_ok', True):
            out.append(txt(_('No microphone found.'), 15, 'semi', SLOW, va='c', pad=[8, 0, 0, 0]))
    link = cp.link_text()
    if link:
        out.append(txt(link, 15, 'bold', FG2, va='c', pad=[10, 0, 0, 0]))
    return row(*out, va='c', pad=[0, 14, 0, 0])


def _lobby_part(ig, cp, d):
    m = ig.mem(TAB)
    l = cp.lobby
    note = txt(cp.msg, 17, 'semi', SLOW, wrap=True, pad=[0, 0, 0, 10]) if cp.msg else None
    if l and l.get('state') == 'started':
        driver = cp.role() == 'driver'
        say = (_('Your stage is on. Drive it: your co-driver watches your car from inside it and reads the notes.')
               if driver else _('Your driver\'s stage is on. You watch from inside their car: Up / Down move through '
                                'the notes (Left / Right: five at a time).'))
        go = primary(tab_id(TAB, 'go'), _('DRIVE  ›') if driver else _('TO THE CAR  ›'))
        warn = _('Leaving now is a DNF for the crew.') if driver else _('Your driver can finish without you.')
        return box(col(kicker(_('On the stage'), fg=COLOUR), txt(say, 19, 'medium', SOFT, wrap=True, pad=[0, 6, 0, 0]),
                       txt(RULES, 16, 'semi', SLOW, wrap=True, pad=[0, 8, 0, 0]), note,
                       row(go, sp(14), quiet(tab_id(TAB, 'leave'), _('LEAVE')), sp(16),
                           txt(warn, 15, 'semi', MUTED, va='c'), pad=[0, 14, 0, 0]), _voice_line(ig, cp)),
                   bg=PANEL, p=[24, 18, 24, 20])
    if l and l.get('state') == 'open':
        me = l.get('host') if l.get('me') == 'host' else l.get('guest')
        other = l.get('guest') if l.get('me') == 'host' else l.get('host')
        code = row(kicker(_('Private · code'), va='c'), sp(10), box(txt(l['code'], 26, 'bold', WHITE, sp=200), bg=BG,
                                                                     p=[14, 2, 14, 2], ol=COLOUR),
                   sp(12), txt(_('Give it to your partner.'), 15, 'semi', MUTED, va='c'),
                   pad=[0, 0, 0, 12]) if l.get('code') else None
        ready = (quiet(tab_id(TAB, 'unready'), _('NOT READY')) if (me or {}).get('ready')
                 else primary(tab_id(TAB, 'ready'), _('READY')))
        hint = (_('Both READY: the stage starts for both of you.') if other else
                _('Waiting for a %s to join.') % ROLE_NAMES.get(l.get('wants'), '').lower())
        return box(col(kicker(_('Your lobby'), fg=COLOUR), code, note,
                       row(_person(me, _('You')), sp(14), _person(other, _('Your partner')), pad=[0, 6, 0, 0]),
                       row(ready, sp(14), quiet(tab_id(TAB, 'leave'), _('LEAVE')), sp(16),
                           txt(hint, 16, 'semi', MUTED, va='c', wrap=True, fill=1), pad=[0, 14, 0, 0]),
                       _voice_line(ig, cp)),
                   bg=PANEL, p=[24, 18, 24, 20])
    # no lobby: set one up, or join one with its code
    tries = d.get('tries') or {}
    both = tries.get('driver') and tries.get('codriver')
    if both:
        return box(col(note, txt(_('You have driven today\'s COPILOT in both roles. Back tomorrow.'), 19, 'semi', GOOD,
                                 wrap=True)), bg=PANEL, p=[24, 18, 24, 20])
    role = m.get('role') or ('codriver' if tries.get('driver') else 'driver')
    if tries.get(role):
        role = 'codriver' if role == 'driver' else 'driver'
    private = bool(m.get('private'))

    def pick(key, label, on, done=False):
        return btn(tab_id(TAB, 'role' if key in ROLE_NAMES else 'priv', key), label + ('  ✓' if done else ''),
                   bg=WHITE if on else '-', hov=ACC, fg=BG if on else SOFT, hfg=WHITE, sz=17, f='bold', sp=60,
                   p=[18, 7, 18, 7], r=2, ol=None if on else LINE2, pad=[8, 0, 0, 0])
    setup = row(txt(_('I am the'), 17, 'semi', FG2, va='c'),
                *[pick(r, ROLE_NAMES[r], r == role, bool(tries.get(r))) for r in ('driver', 'codriver')],
                sp(20), pick('public', _('PUBLIC'), not private), pick('private', _('PRIVATE'), private),
                sp(fill=1), primary(tab_id(TAB, 'create'), _('SET UP A LOBBY  ›')), va='c', pad=[0, 8, 0, 0])
    code = row(txt(_('Got a code?'), 17, 'semi', FG2, va='c'), sp(12),
               size(box(edit(tab_id(TAB, 'code'), m.get('code') or '', _('CODE')), bg=PANEL2, p=[12, 6, 12, 6], ol=LINE2),
                    w=200),
               sp(10), quiet(tab_id(TAB, 'joincode'), _('JOIN')), va='c', pad=[0, 14, 0, 0])
    return box(col(kicker(_('Your lobby'), fg=COLOUR), note, setup, code), bg=PANEL, p=[24, 18, 24, 20])


def _browser(ig, cp, d):
    """Every lobby of the day still on: public ones joined with a click, private ones with their code."""
    tries = d.get('tries') or {}
    mine = (cp.lobby or {}).get('id')
    rows = []
    for x in (d.get('lobbies') or [])[:LOBBIES_SHOWN]:
        host, guest = x.get('host') or {}, x.get('guest')
        crew = {host.get('role'): host.get('name')}
        if guest:
            crew[guest.get('role')] = guest.get('name')
        names = col(row(kicker(_('Driver'), va='c'), sp(8), txt(crew.get('driver') or _('open seat'), 18, 'bold',
                                                                 WHITE if crew.get('driver') else MUTED, va='c')),
                    row(kicker(_('Co-driver'), va='c'), sp(8), txt(crew.get('codriver') or _('open seat'), 18, 'bold',
                                                                    WHITE if crew.get('codriver') else MUTED, va='c')),
                    fill=1)
        if x.get('state') == 'started':
            status, button = chip(_('ON THE STAGE'), bg=ACC), None
        elif guest:
            status, button = chip(_('FULL'), bg=LINE2, fg=SOFT), None
        else:
            status = chip(_('OPEN'), bg=GOOD, fg=BG)
            can = not tries.get(x.get('wants')) and x.get('id') != mine and not x.get('mine')
            label = _('JOIN WITH CODE') if x.get('private') else _('JOIN AS %s') % ROLE_NAMES.get(x.get('wants'), '')
            button = quiet(tab_id(TAB, 'join', x['id']), label, va='c') if can else None
        lock = chip(_('PRIVATE'), bg=PANEL, fg=SOFT, ol=LINE2, pad=[8, 0, 0, 0]) if x.get('private') else None
        yours = chip(_('YOURS'), bg=COLOUR, fg=BG, pad=[8, 0, 0, 0]) if x.get('mine') or x.get('id') == mine else None
        rows.append(box(row(names, row(status, lock, yours, va='c'), sp(14), button, va='c'),
                        bg=PANEL2, p=[16, 8, 16, 8], pad=[0, 6, 0, 0]))
    if not rows:
        rows = [txt(_('No lobbies yet today: set one up, or ask a friend for their code.'), 17, 'medium', MUTED,
                    pad=[0, 6, 0, 0])]
    return box(col(row(kicker(_('Lobbies'), fg=COLOUR), sp(fill=1), quiet(tab_id(TAB, 'refresh'), _('REFRESH'), va='c'),
                       va='c'), *rows), bg=PANEL, p=[24, 18, 24, 20])


def _standings(ig, cp):
    m = ig.mem(TAB)
    side = m.get('side') if m.get('side') in dict(SIDES) else 'board'
    head = tabs(tab_id(TAB, 'side'), SIDES, side)
    body = _board(cp) if side == 'board' else _ranking(cp, side)
    return box(col(head, sp(h=10), body), bg=PANEL, p=[22, 16, 22, 20])


def _board(cp):
    b = cp.board or {}
    out = [kicker(_('Today\'s crews'), fg=COLOUR)]
    if b.get('stage'):
        s = b['stage']
        out.append(txt(' · '.join(x for x in (s.get('menuName') or s.get('stageName'), s.get('car')) if x), 16, 'semi', FG2,
                       wrap=True, pad=[0, 4, 0, 0]))
    entries = b.get('entries') or []
    if not entries:
        out.append(txt(_('No crew has driven it yet.'), 18, 'medium', MUTED, pad=[0, 10, 0, 0]))
    for e in entries[:14]:
        place = str(e['rank']) if e.get('rank') else 'DNF'
        time_ = fmt_ms(e['totalMs']) if e.get('totalMs') is not None else ''
        gap = '+%s' % fmt_ms(e['gapMs']) if e.get('gapMs') else ''
        out.append(box(row(size(txt(place, 18, 'bold', WHITE if e.get('rank') else MUTED, va='c'), w=48), sp(4),
                           col(txt((e.get('driver') or {}).get('name') or '?', 18, 'bold', WHITE),
                               txt(_('with %s') % ((e.get('codriver') or {}).get('name') or '?'), 15, 'semi', FG2),
                               fill=1),
                           col(txt(time_, 18, 'bold', WHITE, j=2), txt(gap, 14, 'semi', MUTED, j=2)), va='c'),
                       bg=PANEL2, p=[14, 6, 14, 6], pad=[0, 6, 0, 0]))
    return col(*out)


def _ranking(cp, side):
    r = cp.ranking or {}
    rows = r.get('drivers' if side == 'drivers' else 'codrivers') or []
    title = _('This month\'s drivers') if side == 'drivers' else _('This month\'s co-drivers')
    out = [kicker(title, fg=COLOUR),
           txt(_('Each day: 25 points for the fastest crew, then 18, 15, 12, 10, 8, 6, 4, 2, 1; any other finish 1.'), 14,
               'semi', MUTED, wrap=True, pad=[0, 4, 0, 0])]
    me = getattr(getattr(cp, 'app', None), 's', {}).get('steamId')
    if not rows:
        out.append(txt(_('No points yet this month.'), 18, 'medium', MUTED, pad=[0, 10, 0, 0]))
    for x in rows[:RANK_SHOWN]:
        mine = x.get('steamId') == me
        days = x.get('days') or 0
        bits = [_('%d days') % days if days != 1 else _('1 day')]
        if x.get('wins'):
            bits.append(_('%d wins') % x['wins'] if x['wins'] != 1 else _('1 win'))
        out.append(box(row(size(txt(str(x.get('rank') or ''), 18, 'bold', COLOUR if mine else WHITE, va='c'), w=48), sp(4),
                           col(txt(x.get('name') or '?', 18, 'bold', COLOUR if mine else WHITE),
                               txt(' · '.join(bits), 14, 'semi', FG2), fill=1),
                           txt('%d' % (x.get('points') or 0), 22, 'bold', WHITE, va='c'), sp(6),
                           txt(_('PTS'), 13, 'bold', MUTED, va='c'), va='c'),
                       bg=PANEL2, p=[14, 6, 14, 6], pad=[0, 6, 0, 0]))
    return col(*out)


# ---------------------------------------------------------------------- SETTINGS › COPILOT VOICE
def settings_panel(ig):
    """The voice's settings, in SETTINGS (ig_settings.py): how to talk, its key or wheel / pad button, the volume."""
    from .cardbuttons import name as button_name
    from .ig_settings import panel, setting
    cp = _cp(ig)
    c = settings_of(ig.app.s)

    def choice(action, arg, label, on):
        return btn(tab_id(TAB, action, arg), label, bg=WHITE if on else '-', hov=WHITE if on else PANEL2,
                   fg=BG if on else FG2, hfg=BG if on else WHITE, sz=16, f='bold', sp=60, p=[12, 6, 12, 6], r=2,
                   ol=None if on else LINE2)
    modes = row(*[col(choice('talk', k, TALK_NAMES[k], c['talk'] == k), pad=[0 if i == 0 else 6, 0, 0, 0])
                  for i, k in enumerate(TALK_MODES)])
    capturing = cp is not None and cp.capturing
    keys = row(choice('key', 'next', c['key'], True), sp(16),
               choice('setbtn', None, _('PRESS IT NOW…') if capturing else button_name(c['button']), bool(capturing)),
               sp(6), choice('clearbtn', None, _('CLEAR'), False) if c['button'] else None, va='c')
    volume = row(choice('gain', '-', '−', False), size(txt('%d %%' % round(c['gain'] * 100), 18, 'bold', WHITE, j=1), w=80,
                                                         va='c'), choice('gain', '+', '+', False))
    return panel(_('COPILOT voice'),
                 setting(_('Talk'), _('Push to talk: hold the key or the button. Open mic: sent whenever you speak.'),
                         under=modes),
                 setting(_('Push to talk'), _('The key (click to change it), and a wheel or pad button (click, then press '
                                              'the button).'), under=keys) if c['talk'] == 'ptt' else None,
                 setting(_('Your partner\'s volume'), None, volume),
                 txt(_('Use headphones: your speakers in your partner\'s microphone come back as an echo.'), 15, 'medium',
                     MUTED, wrap=True, pad=[0, 14, 0, 0]))


def click(ig, action, arg):
    cp = _cp(ig)
    if cp is None:
        return
    m = ig.mem(TAB)
    if action == 'role' and arg in ROLE_NAMES:
        m['role'] = arg
    elif action == 'priv':
        m['private'] = arg == 'private'
    elif action == 'side' and arg in dict(SIDES):
        m['side'] = arg
    elif action == 'refresh':
        cp.refresh(force=True)
    elif action == 'create':
        tries = (cp.day or {}).get('tries') or {}
        role = m.get('role') or ('codriver' if tries.get('driver') else 'driver')
        cp.create(role, bool(m.get('private')))
    elif action == 'join' and arg:
        x = next((l for l in (cp.day or {}).get('lobbies') or [] if str(l.get('id')) == str(arg)), None)
        if x and x.get('private'):
            _ask_code(ig, cp, int(arg))
        else:
            cp.join(lobby_id=int(arg))
    elif action == 'joincode':
        code = ''.join((m.get('code') or '').split()).upper()
        if code:
            cp.join(code=code)
    elif action == 'ready':
        cp.ready(True)
    elif action == 'unready':
        cp.ready(False)
    elif action == 'leave':
        if cp.started() and cp.role() == 'driver':
            ig.ask(_('LEAVE'), [_('Your stage is on: leaving now is a DNF for your crew.')], _('LEAVE'), cp.leave, safe=True)
        else:
            cp.leave()
    elif action == 'go':
        cp.started_id = None
        cp.go()
    elif action == 'talk' and arg in TALK_MODES:
        cp.set_talk(arg)
    elif action == 'key':
        from .voice import VK
        c = settings_of(ig.app.s)
        keys = list(VK)
        c['key'] = keys[(keys.index(c['key']) + 1) % len(keys)]
        _save(ig)
    elif action == 'setbtn':
        cp.capture_button()
    elif action == 'clearbtn':
        settings_of(ig.app.s)['button'] = None
        _save(ig)
    elif action == 'gain' and arg in ('-', '+'):
        c = settings_of(ig.app.s)
        c['gain'] = max(0.5, min(3.0, round(c['gain'] + (0.25 if arg == '+' else -0.25), 2)))
        if cp.voice is not None:
            cp.voice.gain = c['gain']
        _save(ig)


def _ask_code(ig, cp, lobby_id):
    """A private lobby from the list: its code asked for in the game (a box to type it in), then joined."""
    ig._dialog_words = ''

    def go():
        code = ''.join((getattr(ig, '_dialog_words', '') or '').split()).upper()
        if code:
            cp.join(lobby_id=lobby_id, code=code)
    ig.dialog = {'title': _('PRIVATE LOBBY'), 'lines': [_('Its code (the one who set it up has it):')],
                 'go': (_('JOIN'), go), 'cancel': _('CANCEL'), 'field': ''}


def text(ig, field, words):
    if field == 'code':
        ig.mem(TAB)['code'] = words


def _save(ig):
    from . import settings
    settings.save(ig.app.s)


# ---------------------------------------------------------------------- over the stage
def overlay(ig):
    """The co-driver's notes over the stage (watching the driver's car), or the driver's line (the voice, the link, the
    rules while not driving yet); None otherwise."""
    cp = _cp(ig)
    if cp is None or not cp.started():
        return None
    w = getattr(ig.app, 'watch', None)
    if cp.role() == 'codriver' and w is not None and w.on and w.copilot():
        return _notes(cp)
    if cp.role() == 'driver':
        return _driver_line(ig, cp)
    return None


def _voice_chips(cp):
    v = cp.voice
    out = []
    if v is not None:
        out.append(chip(_('TALKING'), bg=GOOD, fg=BG) if v.talking else None)
        out.append(chip(_('HEARING'), bg=COLOUR, fg=BG, pad=[6, 0, 0, 0]) if v.hearing else None)
    link = cp.link_text()
    if link:
        out.append(txt(link, 13, 'bold', 'FFFFFF', va='c', pad=[10, 0, 0, 0]))
    return out


def _warning(cp, mine_on, partner_on=False):
    """The rules' line over the stage: red while the game's own co-driver is on (mine, or the partner's: a DNF in 3 s
    once the stage runs), else the rule itself."""
    if mine_on:
        return box(txt(_("THE GAME'S CO-DRIVER IS ON: switch it off (Settings › Co-driver) or it's a DNF for your crew."),
                       15, 'bold', 'FFFFFF', wrap=True), bg=BAD, p=[14, 6, 14, 6])
    if partner_on:
        return box(txt(_("Your co-driver's game has its own co-driver on: if it stays on, it's a DNF."), 15, 'bold', 'FFFFFF',
                       wrap=True), bg=BAD, p=[14, 6, 14, 6])
    return box(txt(RULES, 13, 'semi', 'D4D4D8', wrap=True), bg=NAVY, a=0.85, p=[14, 5, 14, 5])


def _notes(cp):
    notes = cp.notes or []
    n = len(notes)
    i = max(0, min(n - 1, cp.cursor)) if n else 0
    first = max(0, min(i - NOTES_SHOWN // 2, n - NOTES_SHOWN))
    lines = []
    for k in range(first, min(n, first + NOTES_SHOWN)):
        x = notes[k]
        on = k == i
        nxt = notes[k + 1] if k + 1 < n else None
        gap = '%d m' % (nxt['at'] - x['at']) if nxt else ''
        lines.append(box(row(txt('%d' % x['n'], 14 if not on else 16, 'bold', MUTED if not on else BG, va='c'), sp(12),
                             txt(x['text'].upper(), 22 if on else 18, 'bold', BG if on else 'FFFFFF', wrap=True, fill=1,
                                 va='c'),
                             txt(gap, 13, 'semi', MUTED if not on else BG, va='c', pad=[10, 0, 0, 0])),
                         bg=COLOUR if on else NAVY, a=0.95 if on else 0.8, p=[14, 6 if not on else 10, 14, 6 if not on else 10]))
    head = box(row(txt(_('PACENOTES'), 15, 'bold', 'FFFFFF', sp=120, va='c'), sp(10),
                   txt('%d / %d' % (i + 1, n) if n else _('none'), 14, 'semi', 'FFFFFF', va='c'), sp(fill=1),
                   *_voice_chips(cp), va='c'),
               bg=ACC, p=[14, 5, 14, 5])
    foot = box(txt(_('↑ ↓  one note   ·   ← →  five'), 13, 'semi', 'D4D4D8'), bg=NAVY, a=0.85, p=[14, 4, 14, 4])
    warn = _warning(cp, cp.game_codriver_off() is False)
    panel = size(col(head, *lines, foot, warn), w=620)
    return col(sp(fill=1), row(sp(fill=1), panel, sp(40)), sp(fill=1))


def _driver_line(ig, cp):
    """The driver's: the co-driver's voice and the link; the rules (or what's wrong) until the stage's clock runs."""
    a = ig.app
    j = ((getattr(a, 'tt', None) or {}).get(CP_SLOT) or {}).get('judge')
    running = j is not None and j.state == 'running'
    mine_on = cp.game_codriver_off() is False
    partner_on = cp.partner_off is False
    chips = [c for c in _voice_chips(cp) if c]
    parts = []
    if chips:
        parts.append(box(row(txt(_('CO-DRIVER'), 14, 'bold', 'FFFFFF', sp=120, va='c'), sp(10), *chips, va='c'),
                         bg=NAVY, a=0.8, p=[12, 4, 12, 4]))
    if not running or mine_on or partner_on:
        parts.append(size(_warning(cp, mine_on, partner_on), w=520, pad=[0, 6 if parts else 0, 0, 0]))
    if not parts:
        return None
    return col(sp(h=110), row(sp(fill=1), col(*parts), sp(40)), sp(fill=1))
