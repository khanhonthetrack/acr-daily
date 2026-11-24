"""COPILOT in the game (EVENTS' third sub-tab; copilot.py says how it works): today's crew stage as a "?" until you
have driven it, the lobbies (set one up as driver or co-driver, public or private with a code; join one; READY), the
voice (push to talk / open mic, its key or wheel button), today's crews. Over the stage: the co-driver's notes to scroll
(overlay), and for the driver a small line with the voice and the link."""
from .copilot import ROLE_NAMES, TALK_MODES, TALK_NAMES, settings_of
from .i18n import _
from .ingamekit import (ACC, BG, FG2, GOOD, LINE2, MUTED, PANEL, PANEL2, SLOW, SOFT, WHITE, box, btn, chip, col, edit,
                        empty, fmt_ms, kicker, primary, quiet, row, size, sp, tab_id, txt)

TAB = 'copilot'
COLOUR = 'FF9F0A'                        # COPILOT's colour (the pacenote book's orange)
NOTES_SHOWN = 9                          # notes on screen over the stage (the one on in the middle)
NAVY = '0A1428'


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
    left = col(_stage_card(d), sp(h=20), _lobby_part(ig, cp, d), sp(h=20), _voice_part(ig, cp), fill=1)
    right = size(col(_board(cp)), w=640)
    return row(left, sp(28), right, al='f')


def _stage_card(d):
    """Today's crew stage: a big "?" until you have driven it; then the stage, car and conditions."""
    rules = _('One stage, two of you: the driver drives, the co-driver reads the notes over voice. Hardcore Mode. '
              'Once a day as the driver and once as the co-driver.')
    if d.get('revealed') and d.get('stage'):
        s = d['stage']
        what = col(kicker(_('Today\'s stage'), fg=COLOUR),
                   txt((s.get('menuName') or s.get('stageName') or '').upper(), 30, 'bold', WHITE, wrap=True),
                   txt(' · '.join(x for x in (s.get('rally'), s.get('car'), s.get('weatherLabel'), s.get('timeLabel')) if x),
                       18, 'semi', FG2, wrap=True, pad=[0, 4, 0, 0]), fill=1)
        mark = box(txt('✓', 60, 'bold', GOOD, j=1), bg=PANEL2, p=[30, 6, 30, 6], va='c')
    else:
        what = col(kicker(_('Today\'s stage'), fg=COLOUR),
                   txt(_('HIDDEN UNTIL YOU DRIVE IT'), 30, 'bold', WHITE, wrap=True),
                   txt(_('The stage, the car and the weather: you find out on the start line.'), 18, 'semi', FG2,
                       wrap=True, pad=[0, 4, 0, 0]), fill=1)
        mark = box(txt('?', 96, 'bold', BG, j=1), bg=COLOUR, p=[38, 0, 38, 0], va='c')
    tries = d.get('tries') or {}
    done = lambda r: _('done') if tries.get(r) else _('not yet')
    who = txt(_('As the driver: %s  ·  As the co-driver: %s') % (done('driver'), done('codriver')), 16, 'semi', MUTED,
              pad=[0, 10, 0, 0])
    return box(col(row(mark, sp(24), what, va='c'), txt(rules, 16, 'medium', SOFT, wrap=True, pad=[0, 14, 0, 0]), who),
               bg=PANEL, p=[24, 20, 24, 20])


def _person(p, label):
    if not p:
        return box(col(kicker(label), txt(_('Waiting for someone to join…'), 20, 'semi', MUTED)), bg=PANEL2, p=[18, 12, 18, 12],
                   fill=1)
    ready = chip(_('READY'), bg=GOOD, fg=BG) if p.get('ready') else chip(_('NOT READY'), bg=LINE2, fg=SOFT)
    return box(col(row(kicker(ROLE_NAMES.get(p.get('role'), '')), sp(fill=1), ready),
                   txt(p.get('name') or '?', 22, 'bold', WHITE, pad=[0, 4, 0, 0])), bg=PANEL2, p=[18, 12, 18, 12], fill=1)


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
                       note, row(go, sp(14), quiet(tab_id(TAB, 'leave'), _('LEAVE')), sp(16),
                                 txt(warn, 15, 'semi', MUTED, va='c'), pad=[0, 14, 0, 0])),
                   bg=PANEL, p=[24, 18, 24, 20])
    if l and l.get('state') == 'open':
        me = l.get('host') if l.get('me') == 'host' else l.get('guest')
        other = l.get('guest') if l.get('me') == 'host' else l.get('host')
        code = row(kicker(_('Private · code'), va='c'), sp(10), box(txt(l['code'], 26, 'bold', WHITE, sp=200), bg=BG,
                                                                     p=[14, 2, 14, 2], ol=COLOUR),
                   sp(12), txt(_('Give it to your partner: JOIN WITH A CODE.'), 15, 'semi', MUTED, va='c'),
                   pad=[0, 0, 0, 12]) if l.get('code') else None
        ready = (quiet(tab_id(TAB, 'unready'), _('NOT READY')) if (me or {}).get('ready')
                 else primary(tab_id(TAB, 'ready'), _('READY')))
        hint = (_('Both READY: the stage starts for both of you.') if other else
                _('Waiting for a %s to join.') % ROLE_NAMES.get(l.get('wants'), '').lower())
        return box(col(kicker(_('Your lobby'), fg=COLOUR), code, note,
                       row(_person(me, _('You')), sp(14), _person(other, _('Your partner')), pad=[0, 6, 0, 0]),
                       row(ready, sp(14), quiet(tab_id(TAB, 'leave'), _('LEAVE')), sp(16),
                           txt(hint, 16, 'semi', MUTED, va='c', wrap=True, fill=1), pad=[0, 14, 0, 0])),
                   bg=PANEL, p=[24, 18, 24, 20])
    # no lobby: set one up, join one with a code, or one of the open ones
    tries = d.get('tries') or {}
    role = m.get('role') or ('codriver' if tries.get('driver') else 'driver')
    if tries.get(role):
        role = 'codriver' if role == 'driver' else 'driver'
    private = bool(m.get('private'))

    def pick(key, label, on, done=False):
        return btn(tab_id(TAB, 'role' if key in ROLE_NAMES else 'priv', key), label + ('  ✓' if done else ''),
                   bg=WHITE if on else '-', hov=ACC, fg=BG if on else SOFT, hfg=WHITE, sz=17, f='bold', sp=60,
                   p=[18, 7, 18, 7], r=2, ol=None if on else LINE2, pad=[8, 0, 0, 0])
    both = tries.get('driver') and tries.get('codriver')
    setup = col(kicker(_('Set up a lobby'), fg=COLOUR),
                row(txt(_('I am the'), 17, 'semi', FG2, va='c'),
                    *[pick(r, ROLE_NAMES[r], r == role, bool(tries.get(r))) for r in ('driver', 'codriver')],
                    sp(24), pick('public', _('PUBLIC'), not private), pick('private', _('PRIVATE'), private),
                    sp(fill=1), primary(tab_id(TAB, 'create'), _('SET UP  ›')) if not both else None,
                    va='c', pad=[0, 8, 0, 0]))
    code = row(kicker(_('Join with a code'), va='c'), sp(14),
               size(box(edit(tab_id(TAB, 'code'), m.get('code') or '', _('CODE')), bg=PANEL2, p=[12, 6, 12, 6], ol=LINE2),
                    w=220),
               sp(12), quiet(tab_id(TAB, 'joincode'), _('JOIN')), va='c', pad=[0, 16, 0, 0])
    rows = []
    for x in (d.get('lobbies') or [])[:8]:
        host = x.get('host') or {}
        can = not tries.get(x.get('wants'))
        rows.append(box(row(txt(host.get('name') or '?', 20, 'bold', WHITE, va='c'), sp(12),
                            txt(_('%s · wants a %s') % (ROLE_NAMES.get(host.get('role'), '').lower(),
                                                       ROLE_NAMES.get(x.get('wants'), '').lower()), 16, 'semi', FG2, va='c'),
                            sp(fill=1), quiet(tab_id(TAB, 'join', x['id']), _('JOIN')) if can else
                            txt(_('you did that role today'), 15, 'semi', MUTED, va='c')),
                        bg=PANEL2, p=[16, 8, 16, 8], pad=[0, 6, 0, 0]))
    open_ = col(kicker(_('Open lobbies')), *(rows or [txt(_('None right now: set one up, or ask a friend for theirs.'),
                                                          17, 'medium', MUTED, pad=[0, 6, 0, 0])]), pad=[0, 18, 0, 0])
    done_all = txt(_('You have driven today\'s COPILOT in both roles. Back tomorrow.'), 18, 'semi', GOOD, wrap=True) \
        if both else None
    return box(col(note, done_all, setup if not both else None, code if not both else None, open_ if not both else None),
               bg=PANEL, p=[24, 18, 24, 20])


def _voice_part(ig, cp):
    c = settings_of(ig.app.s)
    from .cardbuttons import name as button_name
    modes =[btn(tab_id(TAB, 'talk', k), TALK_NAMES[k], bg=WHITE if c['talk'] == k else '-', hov=ACC,
                 fg=BG if c['talk'] == k else SOFT, hfg=WHITE, sz=16, f='bold', sp=60, p=[14, 6, 14, 6], r=2,
                 ol=None if c['talk'] == k else LINE2, pad=[0 if i == 0 else 8, 0, 0, 0]) for i, k in enumerate(TALK_MODES)]
    ptt = row(txt(_('Key'), 16, 'semi', FG2, va='c'), sp(8),
              quiet(tab_id(TAB, 'key'), c['key'], va='c'), sp(16),
              txt(_('Wheel / pad button'), 16, 'semi', FG2, va='c'), sp(8),
              quiet(tab_id(TAB, 'setbtn'), _('PRESS IT NOW…') if cp.capturing else button_name(c['button']), va='c'),
              sp(8), quiet(tab_id(TAB, 'clearbtn'), _('CLEAR'), va='c') if c['button'] else None,
              va='c', pad=[0, 12, 0, 0]) if c['talk'] == 'ptt' else None
    v = cp.voice
    live = []
    if v is not None:
        live.append(chip(_('TALKING'), bg=GOOD, fg=BG) if v.talking else chip(_('MUTED'), bg=LINE2, fg=SOFT))
        live.append(sp(8))
        live.append(chip(_('HEARING'), bg=COLOUR, fg=BG) if v.hearing else None)
        if not getattr(v, 'mic_ok', True):
            live.append(txt(_('No microphone found.'), 15, 'semi', SLOW, va='c', pad=[8, 0, 0, 0]))
    link = cp.link_text()
    return box(col(row(kicker(_('Voice'), fg=COLOUR), sp(fill=1), *live, sp(12) if link else None,
                       txt(link, 15, 'bold', FG2, va='c') if link else None, va='c'),
                   row(*modes, sp(16), txt(_('Volume'), 16, 'semi', FG2, va='c'), sp(8),
                       quiet(tab_id(TAB, 'gain', '-'), '−', va='c'), txt('%d %%' % round(c['gain'] * 100), 17, 'bold', WHITE,
                                                                      va='c', pad=[10, 0, 10, 0]),
                       quiet(tab_id(TAB, 'gain', '+'), '+', va='c'), va='c', pad=[0, 10, 0, 0]),
                   ptt,
                   txt(_('Use headphones: your speakers in your partner\'s microphone come back as an echo.'), 15, 'medium',
                       MUTED, wrap=True, pad=[0, 12, 0, 0])),
               bg=PANEL, p=[24, 16, 24, 18])


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
        out.append(box(row(txt(place, 18, 'bold', WHITE if e.get('rank') else MUTED, va='c'), sp(12),
                           col(txt((e.get('driver') or {}).get('name') or '?', 18, 'bold', WHITE),
                               txt(_('with %s') % ((e.get('codriver') or {}).get('name') or '?'), 15, 'semi', FG2),
                               fill=1),
                           col(txt(time_, 18, 'bold', WHITE, j=2), txt(gap, 14, 'semi', MUTED, j=2)), va='c'),
                       bg=PANEL2, p=[14, 6, 14, 6], pad=[0, 6, 0, 0]))
    return box(col(*out), bg=PANEL, p=[22, 18, 22, 20])


def click(ig, action, arg):
    cp = _cp(ig)
    if cp is None:
        return
    m = ig.mem(TAB)
    if action == 'role' and arg in ROLE_NAMES:
        m['role'] = arg
    elif action == 'priv':
        m['private'] = arg == 'private'
    elif action == 'create':
        tries = (cp.day or {}).get('tries') or {}
        role = m.get('role') or ('codriver' if tries.get('driver') else 'driver')
        cp.create(role, bool(m.get('private')))
    elif action == 'join' and arg:
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


def text(ig, field, words):
    if field == 'code':
        ig.mem(TAB)['code'] = words


def _save(ig):
    from . import settings
    settings.save(ig.app.s)


# ---------------------------------------------------------------------- over the stage
def overlay(ig):
    """The co-driver's notes over the stage (watching the driver's car), or the driver's voice line; None otherwise."""
    cp = _cp(ig)
    if cp is None or not cp.started():
        return None
    w = getattr(ig.app, 'watch', None)
    if cp.role() == 'codriver' and w is not None and w.on and w.copilot():
        return _notes(cp)
    if cp.role() == 'driver':
        return _driver_line(cp)
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
    panel = size(col(head, *lines, foot), w=620)
    return col(sp(fill=1), row(sp(fill=1), panel, sp(40)), sp(fill=1))


def _driver_line(cp):
    chips = _voice_chips(cp)
    if not any(chips):
        return None
    line = box(row(txt(_('CO-DRIVER'), 14, 'bold', 'FFFFFF', sp=120, va='c'), sp(10), *chips, va='c'),
               bg=NAVY, a=0.8, p=[12, 4, 12, 4])
    return col(sp(h=110), row(sp(fill=1), line, sp(40)), sp(fill=1))
