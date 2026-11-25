"""COPILOT in the game, called CODRIVER on screen (the user, 25 Nov 2026; EVENTS' third sub-tab; copilot.py says how it
works): today's crew stage as a "?" until you have driven it; your lobby (or setting one up: driver or co-driver,
public or private with a code); every lobby of the day (the lobby browser: public ones joined with a click, private
ones with their code); today's results, one table: place, driver, co-driver, time (the user: "4 columns"). The voice's
settings are in SETTINGS (settings_panel). Over the stage: the co-driver's notes to scroll, the rules (what is a DNF);
for the driver, the co-driver's voice and the link."""
from .copilot import CP_SLOT, ROLE_NAMES, TALK_MODES, TALK_NAMES, settings_of
from .i18n import _
from .ingamekit import (ACC, ACC_TEXT, BAD, BG, FG2, GOOD, LINE2, MUTED, PANEL, PANEL2, SLOW, SOFT, WHITE, box, btn, chip,
                        col, edit, empty, fmt_ms, kicker, line_row, primary, quiet, row, sheet, size, sp, tab_id, tabs, txt)

TAB = 'copilot'
COLOUR = 'FF9F0A'                        # COPILOT's colour (the pacenote book's orange)
NOTES_SHOWN = 9                          # notes on screen over the stage (the one on in the middle)
LOBBIES_SHOWN = 12
NAVY = '0A1428'
RULES = _('Changing the game\'s settings, driving aids, its co-driver or pacenotes during the stage is a DNF for the crew.')


def _cp(ig):
    return getattr(ig.app, 'copilot', None)


def opened(ig):
    cp = _cp(ig)
    if cp is not None:
        cp.refresh(force=True)
    cs = getattr(ig.app, 'casual', None)
    if cs is not None:
        cs.refresh(force=True)


MODES = (('daily', _('CODRIVER DAILY')), ('casual', _('CASUAL')))


def page(ig):
    """CODRIVER's two tabs: the daily for two, and CASUAL (ig_casual.py: up to four in a lobby)."""
    m = ig.mem(TAB)
    cs = getattr(ig.app, 'casual', None)
    if (cs is not None and (cs.lobby or {}).get('state') in ('open', 'started')) and not m.get('mode_set'):
        m['mode'] = 'casual'                          # (a lobby of mine on: its tab)
    mode = m.get('mode') if m.get('mode') in dict(MODES) else 'daily'
    bar = row(tabs(tab_id(TAB, 'mode'), MODES, mode, va='c'), sp(fill=1), pad=[0, 0, 0, 16])
    if mode == 'casual':
        from . import ig_casual
        return col(bar, ig_casual.page(ig))
    return col(bar, _daily_page(ig))


def _daily_page(ig):
    cp = _cp(ig)
    if cp is None:
        return empty(_('CODRIVER is not in this version of the app.'))
    if ig.mem('casual').get('pick') == 'lang':          # (the languages' picker is CASUAL's: ig_casual.py)
        from . import ig_casual
        return ig_casual._picker(ig, None, 'lang')
    cp.refresh()
    d = cp.day
    if d is None:
        return col(kicker(_('Codriver')), txt(cp.msg or _('Loading today\'s CODRIVER…'), 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    if not d.get('on'):
        return col(kicker(_('Codriver')), txt(_('No CODRIVER on this server yet.'), 22, 'medium', SOFT, pad=[0, 10, 0, 0]))
    if not ig.app.s.get('token'):
        return col(_stage_card(d), txt(_('Sign in with Steam to drive CODRIVER (PROFILE, or the app\'s window).'), 20,
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
           txt(_('(SETTINGS › CODRIVER VOICE)'), 14, 'semi', MUTED, va='c'), sp(fill=1)]
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
    final = txt(cp.final, 18, 'semi', GOOD, wrap=True, pad=[0, 0, 0, 10]) if cp.final else None
    if both:
        return box(col(note, final, txt(_('You have driven today\'s CODRIVER in both roles. Back tomorrow.'), 19, 'semi', GOOD,
                                        wrap=True)), bg=PANEL, p=[24, 18, 24, 20])
    role = m.get('role') or ('codriver' if tries.get('driver') else 'driver')
    if tries.get(role):
        role = 'codriver' if role == 'driver' else 'driver'
    private = bool(m.get('private'))

    def pick(key, label, on, done=False):
        return btn(tab_id(TAB, 'role' if key in ROLE_NAMES else 'priv', key), label + ('  ✓' if done else ''),
                   bg=WHITE if on else '-', hov=ACC, fg=BG if on else SOFT, hfg=WHITE, sz=17, f='bold', sp=60,
                   p=[18, 7, 18, 7], r=2, ol=None if on else LINE2, pad=[8, 0, 0, 0])
    from . import ig_casual
    speak = row(txt(_('I speak'), 17, 'semi', FG2, va='c'), sp(12),
                btn(tab_id(TAB, 'langs'), c=row(ig_casual.flags(ig_casual.chosen(ig, 'lang')) or txt(_('pick up to 3'), 16, 'medium', MUTED, va='c'),
                                                sp(10), txt('›', 17, 'semi', SOFT, va='c'), va='c'),
                    bg='-', hov=PANEL2, p=[16, 6, 16, 6], r=2, ol=LINE2), va='c', pad=[0, 8, 0, 0])
    setup = row(txt(_('I am the'), 17, 'semi', FG2, va='c'),
                *[pick(r, ROLE_NAMES[r], r == role, bool(tries.get(r))) for r in ('driver', 'codriver')],
                sp(20), pick('public', _('PUBLIC'), not private), pick('private', _('PRIVATE'), private),
                sp(fill=1), primary(tab_id(TAB, 'create'), _('SET UP A LOBBY  ›')), va='c', pad=[0, 8, 0, 0])
    code = row(txt(_('Got a code?'), 17, 'semi', FG2, va='c'), sp(12),
               size(box(edit(tab_id(TAB, 'code'), m.get('code') or '', _('CODE')), bg=PANEL2, p=[12, 6, 12, 6], ol=LINE2),
                    w=200),
               sp(10), quiet(tab_id(TAB, 'joincode'), _('JOIN')), va='c', pad=[0, 14, 0, 0])
    return box(col(kicker(_('Your lobby'), fg=COLOUR), note, final, setup, speak, code), bg=PANEL, p=[24, 18, 24, 20])


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
        from .ig_casual import flags
        lang = flags(x.get('langs'))
        yours = chip(_('YOURS'), bg=COLOUR, fg=BG, pad=[8, 0, 0, 0]) if x.get('mine') or x.get('id') == mine else None
        rows.append(box(row(names, lang, row(status, lock, yours, va='c', pad=[10, 0, 0, 0]), sp(14), button, va='c'),
                        bg=PANEL2, p=[16, 8, 16, 8], pad=[0, 6, 0, 0]))
    if not rows:
        rows = [txt(_('No lobbies yet today: set one up, or ask a friend for their code.'), 17, 'medium', MUTED,
                    pad=[0, 6, 0, 0])]
    return box(col(row(kicker(_('Lobbies'), fg=COLOUR), sp(fill=1), quiet(tab_id(TAB, 'refresh'), _('REFRESH'), va='c'),
                       va='c'), *rows), bg=PANEL, p=[24, 18, 24, 20])


NAME_W = 220                             # the results' driver and co-driver columns


def _standings(ig, cp):
    """Today's results: one table, as the dailies' with a column more: place, driver, co-driver, time (mine stands
    out; a DNF at the foot, its time 'DNF')."""
    b = cp.board
    me = ig.app.s.get('steamId')
    title = _('Today\'s results')
    if b is None:
        body = txt(_('Loading…'), 17, 'medium', MUTED, pad=[0, 8, 0, 0])
        return box(col(kicker(title, fg=COLOUR), body), bg=PANEL, p=[22, 16, 22, 20])
    entries = b.get('entries') or []
    head = row(kicker(title, fg=COLOUR), sp(fill=1), kicker(_('%d crews') % len(entries) if entries else ''),
               pad=[0, 0, 0, 8])
    cols = row(size(kicker('#', j=2), w=40), sp(14), size(kicker(_('Driver')), w=NAME_W), sp(10),
               kicker(_('Co-driver'), fill=1), kicker(_('Time'), j=2), pad=[8, 0, 8, 4])
    if not entries:
        return box(col(head, cols, txt(_('No crew has driven it yet.'), 17, 'medium', MUTED, pad=[8, 8, 0, 0])),
                   bg=PANEL, p=[22, 16, 22, 20])
    lines = []
    for e in entries:
        d, c = e.get('driver') or {}, e.get('codriver') or {}
        mine = me in (d.get('steamId'), c.get('steamId'))
        fg = WHITE if mine else SOFT
        place = '%d' % e['rank'] if e.get('rank') else '–'
        time_ = fmt_ms(e['totalMs']) if e.get('totalMs') is not None else 'DNF'
        line = row(size(txt(place, 17, 'bold', ACC_TEXT if e.get('rank') == 1 else MUTED, j=2), w=40), sp(14),
                   size(txt(d.get('name') or '?', 17, 'bold' if mine else 'semi', fg), w=NAME_W), sp(10),
                   txt(c.get('name') or '?', 17, 'bold' if mine else 'semi', fg, fill=1),
                   txt(time_, 17, 'semi', fg if e.get('totalMs') is not None else MUTED, j=2))
        lines.append(line_row(line, mine, fid='copilot:board:%d' % len(lines)))
    return box(col(head, cols, sheet(lines, 14, 'copilot:board')), bg=PANEL, p=[22, 16, 22, 20])


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
    mic_name = c['mic'] or _('DEFAULT')
    microw = row(choice('mic', 'next', mic_name + '  ›', False), sp(10),
                 choice('mictest', None, _('STOP TEST') if cp is not None and cp.mic_test is not None else _('TEST'),
                        bool(cp is not None and cp.mic_test is not None)), va='c')
    lvl = cp.mic_level() if cp is not None else None
    meter = size(box(size(box(None, bg=GOOD if (lvl or 0) < 0.8 else SLOW, r=2), w=max(2, int(380 * min(1.0, lvl or 0.0))), h=14),
                     bg=LINE2, r=2), w=380, h=14, va='c')
    mgain = row(choice('micgain', '-', '−', False), size(txt('%d %%' % round(c['micgain'] * 100), 18, 'bold', WHITE, j=1), w=80,
                                                         va='c'), choice('micgain', '+', '+', False), sp(20), meter, va='c')
    return panel(_('CODRIVER voice'),
                 setting(_('Microphone'), _('Click to go through the microphones; TEST shows its level.'), under=microw),
                 setting(_('My volume'), _('How loud your voice goes out. The bar moves when the microphone hears you.'),
                         under=mgain),
                 setting(_('Talk'), _('Push to talk: hold the key or the button. Open mic: sent whenever you speak.'),
                         under=modes),
                 setting(_('Push to talk'), _('The key (click to change it), and a wheel or pad button (click, then press '
                                              'the button).'), under=keys) if c['talk'] == 'ptt' else None,
                 setting(_('Your partner\'s volume'), None, volume),
                 setting(_('Rally intercom'), _('Your partner\'s voice as a crew hears it in their helmets: narrow and punchy, '
                                              'a click as they start, a hiss as they stop.'),
                         under=row(choice('radio', 'on', _('ON'), c['radio']), sp(6), choice('radio', 'off', _('OFF'), not c['radio']))),
                 txt(_('Use headphones: your speakers in your partner\'s microphone come back as an echo.'), 15, 'medium',
                     MUTED, wrap=True, pad=[0, 14, 0, 0]))


def click(ig, action, arg):
    cp = _cp(ig)
    if cp is None:
        return
    m = ig.mem(TAB)
    if action == 'mode' and arg in dict(MODES):
        m['mode'], m['mode_set'] = arg, True
        ig.opened()
    elif action == 'langs':
        ig.mem('casual')['pick'] = 'lang'
    elif action == 'mic':
        cp.next_mic()
    elif action == 'micgain' and arg in ('-', '+'):
        cp.set_mic_gain(settings_of(ig.app.s)['micgain'] + (0.25 if arg == '+' else -0.25))
    elif action == 'mictest':
        cp.test_mic(cp.mic_test is None)
    elif action == 'role' and arg in ROLE_NAMES:
        m['role'] = arg
    elif action == 'radio':
        cp.set_radio(arg == 'on')
    elif action == 'priv':
        m['private'] = arg == 'private'
    elif action == 'refresh':
        cp.refresh(force=True)
    elif action == 'create':
        tries = (cp.day or {}).get('tries') or {}
        role = m.get('role') or ('codriver' if tries.get('driver') else 'driver')
        from . import ig_casual
        cp.create(role, bool(m.get('private')), list(ig_casual.chosen(ig, 'lang')))
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
def _owner(ig):
    """The mode my lobby is in (CASUAL's, or the daily crew's)."""
    f = getattr(ig.app, 'crew_owner', None)
    return f() if f else _cp(ig)


def overlay(ig):
    """What the mod draws over the stage for a crew: the co-driver's notes (watching the driver's car, from the passenger
    seat) with the driver's clock; the driver's line (the voice, the link, the rules while not driving yet); the speaker
    icons on the side for both; None otherwise."""
    cp = _owner(ig)
    if cp is None or not cp.started():
        return None
    w = getattr(ig.app, 'watch', None)
    if cp.role() == 'codriver' and w is not None and w.on and w.copilot():
        return _notes(cp)
    if cp.role() == 'driver':
        return _driver_line(ig, cp)
    return None


def _casual(cp):
    return str(((cp.lobby or {}).get('ch') or {}).get('id', '')).startswith('cx:')


def _icons(cp):
    """Small speaker icons on the side, one for each person in the crew: lit while they talk (the user, 25 Nov 2026: to see
    that someone speaks at all, and to troubleshoot); me last, lit while I send."""
    if cp.voice is None or len(cp.speakers()) < 2:      # (no voice on, or alone in the crew: nobody to see)
        return None
    items = []
    for name, _seat, on in cp.speakers():
        items.append(box(row(box(None, bg=GOOD if on else '52525B', r=6), sp(8),
                             txt(name, 14, 'bold' if on else 'semi', 'FFFFFF' if on else 'A1A1AA', va='c'), va='c'),
                         bg=NAVY, a=0.9 if on else 0.55, p=[10, 4, 12, 4], pad=[0, 0, 0, 4]))
    if not items:
        return None
    return col(*[size(i, h=30) for i in items])


def _voice_chips(cp):
    v = cp.voice
    out = []
    if v is not None:
        out.append(chip(_('TALKING'), bg=GOOD, fg=BG) if v.talking else None)
        out.append(chip(_('HEARING'), bg=COLOUR, fg=BG, pad=[6, 0, 0, 0]) if v.hearing else None)
        if v.mic_ok is False:
            out.append(chip(_('NO MIC'), bg=BAD, fg='FFFFFF', pad=[6, 0, 0, 0]))
    link = cp.link_text()
    if link:
        out.append(txt(link, 13, 'bold', 'FFFFFF', va='c', pad=[10, 0, 0, 0]))
    return out


def _warning(cp, mine_on, partner_on=False):
    """The rules' line over the stage: red while the game's own co-driver is on (mine, or the partner's: a DNF in 3 s
    once the stage runs, daily only), else the rule itself."""
    casual = _casual(cp)
    if mine_on:
        return box(txt(_("THE GAME'S CO-DRIVER IS ON: switch it off (Settings › Co-driver).") if casual else
                       _("THE GAME'S CO-DRIVER IS ON: switch it off (Settings › Co-driver) or it's a DNF for your crew."),
                       15, 'bold', 'FFFFFF', wrap=True), bg=BAD, p=[14, 6, 14, 6])
    if partner_on and not casual:
        return box(txt(_("Your co-driver's game has its own co-driver on: if it stays on, it's a DNF."), 15, 'bold', 'FFFFFF',
                       wrap=True), bg=BAD, p=[14, 6, 14, 6])
    if casual:
        return None
    return box(txt(RULES, 13, 'semi', 'D4D4D8', wrap=True), bg=NAVY, a=0.85, p=[14, 5, 14, 5])


def _logo():
    return box(txt('ACR DAILY', 16, 'bold', 'FFFFFF', sp=60, va='c'), bg=ACC, p=[12, 4, 12, 4], va='c')


def _driver_bar(cp):
    """The co-driver's view of the driver's stage, as the dailies' timer: GOOD LUCK on the start line; the clock and the gap
    to the leader (daily) while it runs; the finish with its time; a DNF. -> a box."""
    import time as _t
    ds = cp.driver_state
    if ds is None or _t.monotonic() - ds['at'] > 6.0:
        return box(txt(_('Good luck!'), 20, 'bold', 'FFFFFF'), bg=NAVY, a=0.85, p=[14, 6, 14, 6])
    st = ds['state']
    if st == 'r':
        ms = ds['ms'] + min(2000, int((_t.monotonic() - ds['at']) * 1000))
        gap = ds.get('gap')
        parts = [txt(fmt_ms(ms), 26, 'bold', 'FFFFFF')]
        if gap is not None:
            parts.append(txt('%s%.2f' % ('+' if gap >= 0 else '−', abs(gap) / 1000.0) + '  ' + _('vs leader'), 17, 'bold',
                             SLOW if gap > 0 else GOOD, va='c', pad=[14, 0, 0, 0]))
        parts.append(txt('%d %%' % ds['pct'], 15, 'semi', 'D4D4D8', va='c', pad=[14, 0, 0, 0]))
        return box(row(*parts, va='c'), bg=NAVY, a=0.9, p=[14, 5, 14, 5])
    if st == 'f':
        line = cp.final or _('Finished')
        return box(col(txt(_('FINISHED  %s') % fmt_ms(ds['ms']), 22, 'bold', GOOD), txt(line, 14, 'semi', 'D4D4D8', wrap=True)),
                   bg=NAVY, a=0.9, p=[14, 6, 14, 6])
    if st == 'd':
        return box(txt(_('DNF'), 22, 'bold', 'FFFFFF'), bg=BAD, p=[14, 6, 14, 6])
    return box(txt(_('Good luck!'), 20, 'bold', 'FFFFFF'), bg=NAVY, a=0.85, p=[14, 6, 14, 6])


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
    head = box(row(_logo(), sp(12), txt(_('PACENOTES'), 15, 'bold', 'FFFFFF', sp=120, va='c'), sp(10),
                   txt('%d / %d' % (i + 1, n) if n else _('none'), 14, 'semi', 'FFFFFF', va='c'), sp(fill=1),
                   *_voice_chips(cp), va='c'),
               bg=ACC, p=[14, 5, 14, 5])
    foot = box(txt(_('↑ ↓  one note   ·   ← →  five'), 13, 'semi', 'D4D4D8'), bg=NAVY, a=0.85, p=[14, 4, 14, 4])
    warn = _warning(cp, cp.game_codriver_off() is False)
    panel = size(col(head, _driver_bar(cp), *lines, foot, warn), w=620)
    return col(sp(fill=1), row(sp(30), _icons(cp), sp(fill=1), panel, sp(40)), sp(fill=1))


def _driver_line(ig, cp):
    """The driver's: the co-driver's voice and the link; the logo and good luck (casual) or the rules (daily) until the
    stage's clock runs, what's wrong at any time; the speaker icons on the side."""
    a = ig.app
    j = ((getattr(a, 'tt', None) or {}).get(cp.SLOT) or {}).get('judge')
    running = j is not None and j.state == 'running'
    mine_on = cp.game_codriver_off() is False and not cp.solo() if hasattr(cp, 'solo') else cp.game_codriver_off() is False
    partner_on = cp.partner_off is False
    chips = [c for c in _voice_chips(cp) if c]
    parts = []
    if chips:
        parts.append(box(row(txt(_('CREW'), 14, 'bold', 'FFFFFF', sp=120, va='c'), sp(10), *chips, va='c'),
                         bg=NAVY, a=0.8, p=[12, 4, 12, 4]))
    if not running and _casual(cp):
        parts.append(box(row(_logo(), sp(12), txt(_('Good luck!'), 20, 'bold', 'FFFFFF', va='c'), va='c'), bg=NAVY, a=0.85,
                         p=[12, 6, 14, 6], pad=[0, 6 if parts else 0, 0, 0]))
    if not running or mine_on or partner_on:
        w = _warning(cp, mine_on, partner_on)
        if w is not None:
            parts.append(size(w, w=520, pad=[0, 6 if parts else 0, 0, 0]))
    icons = _icons(cp)
    if not parts and icons is None:
        return None
    return col(sp(h=110), row(sp(30), icons, sp(fill=1), col(*parts) if parts else None, sp(40)), sp(fill=1))
