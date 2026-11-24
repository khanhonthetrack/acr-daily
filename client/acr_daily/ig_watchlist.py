"""WATCH in the game: everyone on a stage right now, as a server list, each with WATCH (the user, 22 Nov 2026: "a server
list basically of everyone currently driving, and you can join to watch them directly"). The dailies' and the time
trials' drivers (their live lists, ig_daily.refresh_live), and the events' the server lets this driver see
(api.events_live: none on a stage kept hidden from them; a stage they may see, having driven it, or as its staff, shown).
WATCH takes the game to that stage and follows that driver (ig_watch.start / start_event)."""
import threading
import time

from .i18n import _
from .ingamekit import (ACC, COLOUR, FG2, MUTED, PANEL, PANEL2, SOFT, WHITE, box, chip, col, empty, fmt_ms, kicker,
                        primary, row, size, sp, stage_name, tab_id, txt)

TAB = 'watch'
EVERY_S = 5.0                          # the events' list fetched this often while it (or WATCH on one) is on screen
BAR_W = 220


def opened(ig):
    m = ig.mem(TAB)
    m['at'] = -1e9
    refresh(ig)


def refresh(ig):
    """The events' drivers on a stage now, fetched in a thread (at most every EVERY_S): mem 'events', 'events_at'."""
    a = ig.app
    m = ig.mem(TAB)
    now = time.monotonic()
    if m.get('busy') or now - m.get('at', -1e9) < EVERY_S or not a.api.configured or not a.s.get('token'):
        return
    m['at'], m['busy'] = now, True

    def go():
        try:
            r = a.api.events_live() or {}
            me = str(a.s.get('steamId') or '')
            m['events'] = [x for x in r.get('drivers') or [] if str(x.get('steamId') or '') != me]
            m['events_at'] = time.monotonic()
            m.pop('error', None)
        except Exception as e:
            m['error'] = str(e)
        finally:
            m['busy'] = False
    threading.Thread(target=go, daemon=True).start()


def _tag(x):
    """A driver's team tag ({text, color}) from a live list's line, or None (whatever shape it came in)."""
    look = x.get('look') if isinstance(x, dict) else None
    tag = look.get('tag') if isinstance(look, dict) else None
    return tag if isinstance(tag, dict) else None


def lines(ig):
    """Everyone on a stage now: [{'key' (WATCH's button), 'what', 'colour', 'stage', 'name', 'country', 'team', 'car',
    'progress', 'ms'}], the dailies first, then the time trials, then the events."""
    a = ig.app
    out = []
    from .ttui import listed
    for kind, held, label in (('daily', a.dailies or {}, 'SS%d'), ('tt', listed(getattr(a, 'tt', None)), 'TT%d')):
        for slot in sorted(held):
            d = held[slot]
            ch = d.get('ch') or {}
            for x in d.get('live') or ():
                if not isinstance(x, dict) or x.get('state') != 'live':
                    continue
                what = (_('DAILY') if kind == 'daily' else _('TIME TRIAL')) + ' · ' + label % slot
                out.append({'key': '%s:%d:%s' % (kind[0], slot, x.get('steamId') or ''), 'what': what,
                            'colour': COLOUR.get(kind, WHITE), 'stage': stage_name(ch), 'name': x.get('name') or '',
                            'country': x.get('country'), 'team': _tag(x),
                            'car': x.get('car') or ch.get('car') or '', 'progress': x.get('progress'),
                            'ms': x.get('totalMs')})
    for i, x in enumerate(ig.mem(TAB).get('events') or ()):
        st = x.get('stage') if isinstance(x.get('stage'), dict) else {}
        car = x.get('car')                     # (the event's car: its name, a string; a record in older answers)
        car = car if isinstance(car, dict) else {'name': car if isinstance(car, str) else ''}
        if not car.get('name'):
            car = next((c for c in x.get('cars') or [] if isinstance(c, dict)), car)
        what = '%s · SS%d' % (x.get('event') or _('EVENT'), int(x.get('stageNo') or 1))
        out.append({'key': 'e:%s:%s:%s' % (x.get('eventId'), x.get('stageNo'), x.get('steamId') or ''), 'what': what,
                    'sub': x.get('league') or '', 'colour': COLOUR.get('league', WHITE),
                    'stage': st.get('name') or st.get('track') or '', 'name': x.get('name') or '',
                    'country': x.get('country'), 'team': _tag(x),
                    'car': car.get('name') or '', 'progress': x.get('progress'), 'ms': x.get('totalMs')})
    return out


def _bar(p):
    p = max(0.0, min(1.0, p or 0.0))
    done = max(1, round(BAR_W * p))
    return col(size(row(size(box(None, bg=ACC), w=done, h=6), box(None, bg='3A3A44', fill=1), h=6), w=BAR_W, h=6),
               txt('%d %%' % round(p * 100), 14, 'semi', FG2, pad=[0, 4, 0, 0]), va='c')


def _line(r, k):
    from .ig_watch import _flag, tag_colours, team_text
    team = None
    if r.get('team') and team_text(r['team']):
        tbg, tfg = tag_colours(r['team'])
        team = box(txt(team_text(r['team']), 14, 'bold', tfg, sp=40), bg=tbg, p=[7, 1, 7, 1], va='c', pad=[0, 0, 10, 0])
    who = row(_flag(r.get('country'), 33, 22), sp(10) if r.get('country') else None, team,
              txt(r['name'], 22, 'bold', WHITE, va='c'), va='c')
    where = col(row(chip(r['what'].upper(), fg='0A0A0B', bg=r['colour'].lstrip('#')), sp(fill=1)),
                txt(r['stage'], 18, 'semi', SOFT, pad=[0, 6, 0, 0]),
                txt(r['sub'], 14, 'medium', MUTED, pad=[0, 2, 0, 0]) if r.get('sub') else None)
    return box(row(size(where, w=560), size(col(who, txt(r['car'], 16, 'medium', FG2, pad=[0, 4, 0, 0]), va='c'), w=560),
                   _bar(r.get('progress')), sp(24),
                   size(txt(fmt_ms(r['ms'], 1) if r.get('ms') is not None else '', 20, 'semi', WHITE, va='c'), w=130),
                   sp(fill=1), primary(tab_id(TAB, 'go', r['key']), _('WATCH  ›'), va='c'), va='c'),
               bg=PANEL if k % 2 == 0 else PANEL2, p=[22, 14, 22, 14])


def page(ig):
    a = ig.app
    if ig.shown:
        refresh(ig)
        from . import ig_daily
        ig_daily.refresh_live(ig, 'daily')
        ig_daily.refresh_live(ig, 'tt')
    m = ig.mem(TAB)
    rows = lines(ig)
    head = col(kicker(_('Live now')),
               txt(_('Everyone on a stage right now. WATCH takes you there and follows them.'), 20, 'medium', SOFT,
                   pad=[0, 8, 0, 18]))
    if not a.s.get('token'):
        return col(head, empty(_('Not signed in. Sign in from the ACR Daily launcher.')), al='l')
    if not rows:
        words = _('Nobody is on a stage right now.') if m.get('events_at') or m.get('error') else _('Looking…')
        return col(head, empty(words), al='l')
    return col(head, *[_line(r, k) for k, r in enumerate(rows)])


def click(ig, action, arg):
    if action != 'go' or not arg:
        return
    kind, _s, rest = arg.partition(':')
    from . import ig_watch
    if kind in ('d', 't'):
        slot, _s, sid = rest.partition(':')
        try:
            slot = int(slot)
        except ValueError:
            return
        ig_watch.start(ig, 'daily' if kind == 'd' else 'tt', slot, prefer=sid or None)
    elif kind == 'e':
        eid, _s, more = rest.partition(':')
        no, _s, sid = more.partition(':')
        for x in ig.mem(TAB).get('events') or ():
            if str(x.get('eventId')) == eid and str(x.get('stageNo')) == no and str(x.get('steamId') or '') == sid:
                ig_watch.start_event(ig, x)
                return
        ig.say(_('WATCH'), [_('They are no longer on that stage.')])
