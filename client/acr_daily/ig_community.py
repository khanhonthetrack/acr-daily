"""COMMUNITY in the game (ingamekit.py says how a page is made): TRACKS / CARS / LIVERIES as sub-tabs, the item picked as
a photo card (what it is, who made it, its credits, where it stands in this game, its button, how far it is going) beside
the category's list, and over the tracks ALL TRACKS (how many are in, INSTALL ALL / STOP ALL, how far). Every button does
the window's own (communityui.py): its words and its checks.

The game keeps its packages open while it runs, and these pages are drawn by the running game: what changes the game's
files (INSTALL, UPDATE, REMOVE, SHOW, REBUILD, MANAGE, INSTALL ALL) is not offered while it runs, the page says why
(the window's CLOSE_GAME). What works with the game open: liveries (in once the game restarts, as the window says), a
WRC Generations stage put in line (it starts by itself once the game is closed, as in the window), CANCEL / STOP ALL,
GET IT and the makers' pages (the browser). Picking a file (FIND TOOL / FIND GAME) stays in the window.

The page is drawn every tick: where each item stands (read from the game's folder) is looked at again every VIEW_S, after
a click, or when something starts or ends; what is going on (its words, how far) is read as it is."""
import hashlib
import os
import threading
import time
import webbrowser

from . import community, liveries, photos, settings
from .communityui import (BADGE, BUTTON, CATEGORIES, CLASH, CLOSE_GAME, EXPORT_BUTTON, LINK_BUTTON, LV_BUTTON, LV_SORTS,
                          LV_STATUS, MANAGER_BUTTON, ROW_COLOUR, SHORT, SWITCH_CLASH, SWITCH_NAMES, _span)
from .i18n import _, n_
from .ingamekit import (COLOUR, FG2, LINE2, MUTED, PAGE_W, PANEL, PANEL2, PICS_DIR, SOFT, WHITE, box, chip, col, empty,
                        img, link, picture, primary, quiet, row, size, sp, stack, tab_id, tabs, txt)

try:
    from PIL import Image
except ImportError:                     # (an app built without Pillow: no pictures in the game)
    Image = None

TAB = 'community'
GREEN = COLOUR['community']
WARN_BG = '3A2A00'                      # (the window's warning strip)
CARD_W, PHOTO_H, GAP = 1060, 330, 28
LIST_W = PAGE_W - CARD_W - GAP
VIEW_S = 1.5                            # where each item stands: looked at again this often (it reads the game's folder)
RUN_S = 3.0                             # whether the game runs: looked at again this often (in a thread)
REFRESH_S = 15.0                        # the catalogue fetched again on opening, at most this often
KIND_FG = {'good': GREEN, 'info': SOFT, 'muted': MUTED, 'sub': WHITE}


def _hex(c):
    return (c or '').lstrip('#') or MUTED


# ---------------------------------------------------------------------- the page's own state
def _mem(ig):
    return ig.mem(TAB)


def running(ig):
    """Whether the game runs (Windows' process list, looked at in a thread every RUN_S; taken for running until known:
    these pages are in the game)."""
    m = _mem(ig)
    now = time.monotonic()
    if now - m.get('run_t', -1e9) >= RUN_S and not m.get('run_busy'):
        m['run_t'], m['run_busy'] = now, True

        def look():
            try:
                m['running'] = bool(community.game_running())
            finally:
                m['run_busy'] = False
        threading.Thread(target=look, daemon=True).start()
    return m.get('running', True)


def opened(ig):
    m = _mem(ig)
    now = time.monotonic()
    if now - m.get('fetched', -1e9) >= REFRESH_S:
        m['fetched'] = now
        ig.app.refresh_community()
    m['dirty'] = True


# ---------------------------------------------------------------------- pictures
_cut = {}


def _pic(key, w, h):
    """An item's picture cut for the game: the app's own photos (ingamekit.picture), or one fetched by its address
    (photos.fetch keeps those as images, not files: cut here, its file named by the address's hash)."""
    if not key:
        return None
    ck = (key, w, h)
    if ck in _cut:
        return _cut[ck]
    if not key.startswith('url:'):
        out = picture(key, w, h)
    else:
        out = _cut_url(key, w, h)
    if out:
        _cut[ck] = out
    return out


def _cut_url(key, w, h):
    im = getattr(photos, '_raw', {}).get(key)
    if Image is None or im is None:
        return None
    out_dir = os.path.join(settings.DIR, PICS_DIR)
    out = os.path.join(out_dir, 'url-%s-%dx%d-f.png' % (hashlib.md5(key.encode('utf-8')).hexdigest()[:16], w, h))
    if os.path.exists(out):
        return out
    try:
        im = im.convert('RGB')
        sw, sh = im.size
        k = max(w / sw, h / sh)
        im = im.resize((max(w, round(sw * k)), max(h, round(sh * k))), Image.LANCZOS)
        sw, sh = im.size
        x, y = (sw - w) // 2, (sh - h) // 2
        im = im.crop((x, y, x + w, y + h))
        shade = Image.new('L', (1, h))
        for i in range(h):
            a = max(0.0, (i / h - 0.35) / 0.65)
            shade.putpixel((0, i), round(235 * a ** 1.4))
        im = Image.composite(Image.new('RGB', (w, h), (10, 10, 11)), im, shade.resize((w, h)))
        os.makedirs(out_dir, exist_ok=True)
        im.save(out + '.tmp', 'PNG')
        os.replace(out + '.tmp', out)
        return out
    except (OSError, ValueError):
        return None


def bar(frac, w, h=8, fg=GREEN, **o):
    """How far: a track, the done part over it (a box in a size node as wide as the fraction)."""
    f = min(1.0, max(0.0, float(frac or 0)))
    done = int(round(w * f))
    return stack(size(box(None, bg=LINE2), w=w, h=h), size(box(None, bg=fg), w=done, h=h, al='l') if done else None,
                 **o)


# ---------------------------------------------------------------------- what each item is now (kept VIEW_S)
def _items(a, cat):
    return a._items(cat) if cat != 'liveries' else []


def _sig(a):
    ex = getattr(a, '_export_now', None)
    return (a.community_cat, tuple(sorted(a._community_busy or {})), tuple(sorted(map(str, a._livery_busy or {}))),
            id(ex), id(getattr(a, '_export_waiting', None)), len(getattr(a, '_export_queue', None) or []),
            (getattr(a, '_all_now', None) or {}).get('id'), getattr(a, '_all_queue', None) is None,
            id(a.community_data), id(a.liveries_data), id(a._community_packs), id(getattr(a, '_community_switch', None)),
            a._community_game, a.livery_car, a.livery_sort, a.livery_pick,
            tuple(sorted((a.community_picks or {}).items())))


def view(ig):
    m, a = _mem(ig), ig.app
    sig, now = _sig(a), time.monotonic()
    v = m.get('view')
    dirty = m.pop('dirty', False)
    if v is not None and not dirty and v['sig'] == sig and now - v['t'] < VIEW_S:
        return v
    v = {'sig': sig, 't': now}
    cat = a.community_cat
    if cat == 'liveries':
        v.update(_livery_view(a))
    else:
        v.update(_item_view(a, cat))
    m['view'] = v
    return v


def _item_view(a, cat):
    items = _items(a, cat)
    if a.community_data is None or not items:
        return {'items': items}
    if a.community_picks is None:
        a.community_picks = {}
    ids = [it['id'] for it in items]
    if a.community_picks.get(cat) not in ids:
        a.community_picks[cat] = ids[0]
    pick = items[ids.index(a.community_picks[cat])]
    rows = [(it,) + tuple(a._community_row(it)) for it in items]
    sts = {it['id']: st for it, st, _v in rows}
    out = {'items': items, 'rows': rows, 'sts': sts, 'pick': pick, 'spec': a._community_spec(pick)}
    if cat == 'tracks':
        clash = a._community_clash()
        sets = a._switchable() if clash else []
        out['clash'] = (SWITCH_CLASH % a._and([SWITCH_NAMES[g] for g in sets]) if sets and len(clash) == len(sets)
                        else CLASH % a._and(clash)) if clash else None
        out['switch'] = sets
        if len(items) > 1:
            todo = a._all_todo(items, sts)
            out['strip'] = {
                'have': [x for x in items if sts[x['id']] in ('installed', 'off', 'stale', 'update')],
                'hidden': [x for x in items if sts[x['id']] == 'off'],
                'stale': [x for x in items if sts[x['id']] == 'stale' and x.get('install') == 'export'],
                'todo': todo, 'ups': [x for x in todo if sts[x['id']] == 'update'],
                'lists': a._lists_possible()}
    return out


def _lv_status(lv, have):
    """liveries.status, with what is installed read once for the whole list."""
    if str(lv.get('id')) in have:
        return 'installed'
    if not lv.get('go'):
        return 'showonly'
    return 'install' if lv.get('direct') else 'page'


def _livery_view(a):
    if a.liveries_data is None:
        return {}
    items = a._livery_list()
    have = liveries.installed()
    sts = {str(lv['id']): _lv_status(lv, have) for lv in items}
    if items and str(a.livery_pick) not in sts:
        a.livery_pick = items[0]['id']
    pick = next((lv for lv in items if str(lv['id']) == str(a.livery_pick)), None)
    return {'items': items, 'sts': sts, 'pick': pick}


# ---------------------------------------------------------------------- an item's button (the window's _community_fill)
def action(a, it, st):
    """The card's button: (label, fn, primary, game_closed: it changes the game's files), ('window', label) for a file to
    pick in the window, or None."""
    man = (a._community_man or {}).get(it['id'])
    busy = (a._community_busy or {}).get(it['id'])
    how = it.get('install')
    mine = a._export_mine(it) if how == 'export' else None
    buttons = {'manager': MANAGER_BUTTON, 'link': LINK_BUTTON, 'export': EXPORT_BUTTON}.get(how, BUTTON)
    if not (st in buttons and not busy) and mine is None:
        return None
    go = '  ›'
    if how == 'manager':
        if st == 'off':
            return MANAGER_BUTTON[st] + go, lambda: a.community_show(it), True, True
        return (MANAGER_BUTTON[st] + ('' if st == 'installed' else go), lambda: a.community_manager(it, man),
                st != 'installed', True)
    if how == 'export':
        if mine is not None:
            return _('CANCEL'), lambda: a.community_export_cancel(it), False, False
        if st == 'installed':
            return EXPORT_BUTTON[st], lambda: a.community_export_remove(it), False, True
        if st in ('notool', 'nowrcg'):
            return 'window', EXPORT_BUTTON[st]
        if st == 'off':
            return EXPORT_BUTTON[st] + go, lambda: a.community_show(it), True, True
        if st == 'stale':
            return EXPORT_BUTTON[st] + go, lambda: a.community_export_rebuild(it), True, True
        # (made once the game is closed: put in line now, it starts by itself then, as in the window)
        return EXPORT_BUTTON[st] + go, lambda: a.community_export(it), True, False
    if how == 'link':
        return LINK_BUTTON[st] + ('' if st == 'installed' else go), None, st != 'installed', False
    if st == 'off':
        return BUTTON[st] + go, lambda: a.community_show(it), True, True
    if st == 'installed':
        return BUTTON[st], lambda: a.community_remove(it), False, True
    return BUTTON[st] + go, lambda: a.community_install(it, man), True, True


# ---------------------------------------------------------------------- the page
def page(ig):
    a = ig.app
    v = view(ig)
    cat = a.community_cat
    head = _head()
    cats = tabs(tab_id(TAB, 'cat'), [(k, '%s  %d' % (label, a._cat_count(k))) for k, label in CATEGORIES], cat,
                pad=[0, 18, 0, 18])
    body = _liveries(ig, v) if cat == 'liveries' else _tracks(ig, v, cat)
    return col(head, cats, body)


def _head():
    photo = _pic('community', PAGE_W, 150)
    words = col(sp(h=1, fill=1), txt(_('COMMUNITY'), 34, 'bold', WHITE, sp=60, sh=True),
                txt(_('Tracks, cars and liveries made by the community'), 18, 'semi', SOFT, sh=True),
                pad=[26, 14, 26, 16], al='f', va='f')
    return stack(img(photo, PAGE_W, 150), words) if photo else box(words, bg=PANEL)


def _warn(words, *more):
    return box(col(txt(words, 18, 'medium', WHITE, wrap=True), *more), bg=WARN_BG, p=[16, 10, 16, 10], pad=[0, 0, 0, 14])


def _tracks(ig, v, cat):
    a = ig.app
    if a.community_data is None:
        return empty(a.community_msg or _('Loading…'))
    if not v.get('items'):
        return empty({'tracks': _('No tracks yet. They will be here as the community makes them.'),
                      'cars': _('No cars yet. They will be here as the community makes them.')}.get(cat, ''))
    run = running(ig)
    out = []
    if run:                      # (always, in the game: one plain line, not a warning strip: a review, 21 Nov 2026)
        out.append(txt(_('Install and remove with the game closed, in the ACR Daily window.'), 17, 'medium', MUTED,
                       pad=[0, 0, 0, 12]))
    if v.get('clash'):
        more = [row(*[quiet(tab_id(TAB, 'showonly', g), _('SHOW ONLY %s') % SWITCH_NAMES[g].upper(),
                            pad=[0 if i == 0 else 10, 10, 0, 0]) for i, g in enumerate(v.get('switch') or [])])] \
            if v.get('switch') and not run else []
        out.append(_warn(v['clash'], *more))
    if v.get('strip'):
        out.append(_strip(ig, v, run))
    out.append(row(item_card(ig, v['pick'], v['spec'], run), sp(GAP),
                   col(*[item_row(it, st, vals, it['id'] == v['pick']['id']) for it, st, vals in v['rows']],
                       fill=1)))
    return col(*out)


def _strip(ig, v, run):
    """ALL TRACKS: how many are in, INSTALL ALL / STOP ALL, and how far (the window's _export_strip_show)."""
    a, s = ig.app, v['strip']
    items = v['items']
    count = _('%d of %d installed') % (len(s['have']), len(items)) + (
        '   ·   ' + n_('%d update', '%d updates', len(s['ups'])) % len(s['ups']) if s['ups'] else '') + (
        '   ·   ' + _('Hidden') if s['hidden'] or s['stale'] else '')
    o = a._export_overall()
    going = getattr(a, '_all_queue', None) is not None
    btn = None
    if o is not None or going:
        btn = quiet(tab_id(TAB, 'stopall'), _('STOP ALL'))
    elif run:
        btn = None                                   # (the rest change the game's files: CLOSE_GAME says so above)
    elif s['stale']:
        btn = primary(tab_id(TAB, 'rebuild', s['stale'][0]['id']), _('REBUILD') + '  ›')
    elif s['hidden'] and not s['lists']:
        btn = primary(tab_id(TAB, 'show', s['hidden'][0]['id']), _('SHOW') + '  ›')
    elif s['todo']:
        ups, todo = s['ups'], s['todo']
        label = _('UPDATE ALL') if len(ups) == len(todo) else _('INSTALL / UPDATE ALL') if ups else _('INSTALL ALL')
        btn = primary(tab_id(TAB, 'all'), label + '  (%d)  ›' % len(todo))
    top = row(txt(_('ALL TRACKS'), 20, 'bold', WHITE, sp=60, va='c'), sp(14), txt(count, 16, 'medium', MUTED, va='c'),
              sp(fill=1), btn)
    lines = []
    if going and o is None:
        n = getattr(a, '_all_now', None) or {}
        lines.append(txt(_('Installing %s   ·   track %d of %d') % (n.get('name', ''), n.get('n', 1), n.get('of', 1)), 17,
                         'medium', SOFT, pad=[0, 8, 0, 0]))
    elif o is not None:
        w = PAGE_W - 40
        parts = ['%s  %d%%' % (o['name'], int(100 * o['cur'])) if o['phase'] != 'wait' else
                 '%s: %s' % (o['name'], _('Waiting for the game to close'))]
        if o['total'] > 1:
            parts.append(_('stage %d of %d') % (o['done'] + 1, o['total']))
            parts.append(_('%d%% in all') % int(100 * o['fraction']))
        if o['eta']:
            parts.append(_('about %s left') % _span(o['eta']))
        cur = None
        if o['total'] > 1 and o['cur'] > 0:          # (the one being made: its share, how far)
            cur = row(sp(int(w * o['done'] / o['total'])), size(box(None, bg=WHITE), w=int(w * o['cur'] / o['total']), h=3),
                      al='f', va='b')
        lines.append(stack(bar(o['fraction'], w, 10), cur, pad=[0, 10, 0, 0]))
        lines.append(txt('   ·   '.join(parts), 17, 'medium', SOFT, pad=[0, 6, 0, 0]))
    return box(col(top, *lines), bg=PANEL, ol=LINE2, p=[20, 12, 20, 12], pad=[0, 0, 0, 14])


def _now_frac(a, it):
    """How far its job is (0..1), or None: a package's install (its step), a stage being made."""
    busy = (a._community_busy or {}).get(it['id'])
    if not busy:
        return None
    frac = (getattr(a, '_community_frac', None) or {}).get(it['id'])
    if frac is None and it.get('install') == 'export' and a._export_mine(it) == 'now':
        prog = (getattr(a, '_export_now', None) or {}).get('progress')
        if prog is not None and prog.phase != 'remove':
            frac = prog.fraction()
    return frac


def item_card(ig, it, spec_st, run):
    a = ig.app
    st, spec = spec_st
    m = _mem(ig)
    photo = _pic(spec.get('photo'), CARD_W, PHOTO_H) or _pic('community', CARD_W, PHOTO_H)
    badge = spec.get('badge')
    lines = list(spec.get('lines') or [])
    sub = lines[0][0] if lines else ''
    top = col(row(chip(badge[0], bg=_hex(badge[1])) if badge else None),
              sp(h=1, fill=1),
              txt((spec.get('title') or '').upper(), 34, 'bold', WHITE, sh=True, wrap=True),
              txt(sub, 17, 'semi', SOFT, sh=True, wrap=True) if sub else None,
              pad=[24, 18, 24, 16], al='f', va='f')
    busy = (a._community_busy or {}).get(it['id'])
    words = []
    for i, (s, kind) in enumerate(lines[1:], 1):
        if not s:
            continue
        if i == len(lines) - 1 and busy:             # (where it stands: what it is doing now, read as it is)
            s, kind = busy, 'info'
        words.append(txt(s, 17 if kind != 'muted' else 15, 'medium', KIND_FG.get(kind, SOFT), wrap=True,
                         pad=[0, 0 if not words else 6, 0, 0]))
    frac = _now_frac(a, it)
    if frac is not None:
        words.append(bar(frac, CARD_W - 48, 8, pad=[0, 10, 0, 0]))
    act = action(a, it, st)
    buttons = []
    if act is not None and act[0] == 'window':
        buttons.append(quiet('window', _('OPEN THE WINDOW')))
    elif act is not None and not (act[3] and run):
        label, _fn, main = act[0], act[1], act[2]
        buttons.append((primary if main else quiet)(tab_id(TAB, 'go', it['id']), label))
    sup = it.get('support') or {}
    if sup.get('name') and str(sup.get('url') or '').startswith('https://'):
        buttons.append(link(tab_id(TAB, 'support', it['id']),
                            _('%s on %s') % (it.get('author') or it.get('name', ''), sup['name']) + '  ›',
                            pad=[24 if buttons else 0, 0, 0, 0], va='c'))
    tools = None
    if m.get('tools') == it['id']:                   # (GET IT on one more than one tool makes: which one)
        tools = col(*[link(tab_id(TAB, 'tool', '%s/%d' % (it['id'], i)), _tool_words(t) + '  ›', pad=[0, 6, 0, 0])
                      for i, t in enumerate(_tools(it))], pad=[0, 12, 0, 0])
    info = col(*words, row(*buttons, pad=[0, 16, 0, 0]) if buttons else None, tools, pad=[24, 16, 24, 20])
    return size(col(stack(img(photo, CARD_W, PHOTO_H), top), box(info, bg=PANEL)), w=CARD_W)


def _tools(it):
    return [t for t in it.get('tools') or [] if t.get('page')]


def _tool_words(t):
    import urllib.parse
    host = (urllib.parse.urlsplit(t['page']).hostname or '').removeprefix('www.')
    words = [t.get('name') or host, _('by %s') % t['author'] if t.get('author') else '',
             n_('%d stage', '%d stages', t['stages']) % t['stages'] if t.get('stages') else '', host]
    return '  ·  '.join(w for w in words if w)


def item_row(it, st, values, on):
    name, by, what, sz, state = values
    colour = _hex(ROW_COLOUR.get(st) or ROW_COLOUR['other'])
    line = row(size(box(None, bg=colour), w=4, h=44, va='c'), sp(14),
               col(txt(name, 19, 'bold', WHITE if on else SOFT),
                   txt('  ·  '.join(x for x in (by, sz) if x), 14, 'medium', MUTED), fill=1, va='c'),
               sp(12),
               size(txt(state, 16, 'semi', colour if st in ('installed', 'update', 'ready') else FG2, j=2, wrap=True),
                    maxw=300, va='c'))
    return btn_row(tab_id(TAB, 'pick', it['id']), line, on)


def btn_row(id_, line, on):
    from .ingamekit import btn
    return btn(id_, c=line, bg=PANEL2 if on else PANEL, hov=PANEL2, p=[12, 8, 14, 8], r=2, ol=LINE2 if on else None,
               pad=[0, 0, 0, 4], al='f')


# ---------------------------------------------------------------------- LIVERIES
def _liveries(ig, v):
    a = ig.app
    if a.liveries_data is None:
        return empty(a.liveries_msg or _('Loading…'))
    data = a.liveries_data
    everyone = data.get('liveries') or []
    cars = _cars(a)
    here = next((c for c in cars if c['id'] == a.livery_car), None)
    car = '%s (%d)' % (here['name'], here.get('count') or 0) if here else _('All cars (%d)') % len(everyone)
    pick = row(link(tab_id(TAB, 'car', 'prev'), '‹', sz=24, va='c'), sp(10),
               size(txt(car, 18, 'bold', WHITE, j=1, va='c'), w=340), sp(10),
               link(tab_id(TAB, 'car', 'next'), '›', sz=24, va='c'), sp(30),
               tabs(tab_id(TAB, 'sort'), LV_SORTS, a.livery_sort, va='c'))
    note = txt(_('INSTALL puts one into Documents\\My Games\\acr\\Liveries\\<car>: the game sees a new livery when it '
                 'starts, %d a car at most. Rate them, and publish yours, on the website.') % liveries.PER_CAR,
               15, 'medium', MUTED, wrap=True, pad=[0, 10, 0, 16])
    items = v.get('items') or []
    if not items:
        return col(pick, note, empty(_('No liveries for this car yet.') if everyone else
                                     _('No liveries yet: publish the first one on the website!')))
    lv = v.get('pick') or items[0]
    # (LV_PAGE at a time, MORE for the next: hundreds of rows were drawn at once, a review, 21 Nov 2026)
    upto = _mem(ig).get('lv_upto') or LV_PAGE
    rows = [_livery_row(a, x, v['sts'].get(str(x['id']), 'showonly'), str(x['id']) == str(lv['id']))
            for x in items[:upto]]
    if len(items) > upto:
        rows.append(quiet(tab_id(TAB, 'lvmore'), _('MORE (%d)') % (len(items) - upto), pad=[0, 10, 0, 0]))
    return col(pick, note, row(livery_card(ig, lv, v['sts'].get(str(lv['id']), 'showonly')), sp(GAP),
                               col(*rows, fill=1)))


LV_PAGE = 40


def _cars(a):
    cars = (a.liveries_data or {}).get('cars') or []
    return sorted((x for x in cars if x.get('count') or x.get('id') == a.livery_car), key=lambda x: x.get('name') or '')


def livery_card(ig, lv, st):
    a = ig.app
    busy = (a._livery_busy or {}).get(lv['id'])
    key = photos.fetch(lv.get('shot'))
    photo = _pic(key, CARD_W, PHOTO_H) or _pic('community', CARD_W, PHOTO_H)
    info = [liveries.stars_text(lv), n_('%d download', '%d downloads', lv.get('clicks') or 0) % (lv.get('clicks') or 0)]
    if lv.get('hostName'):
        info.append(_('from %s') % lv['hostName'])
    words, kind = (busy, 'info') if busy else LV_STATUS[st]
    desc = ' '.join((lv.get('description') or '').split())
    if len(desc) > 150:
        desc = desc[:147].rstrip() + '…'
    top = col(row(chip(_('INSTALLED'), bg=GREEN) if st == 'installed' else None, sp(10) if st == 'installed' else None,
                  chip(lv.get('carName') or lv.get('car') or '', bg=PANEL2)),
              sp(h=1, fill=1),
              txt((lv.get('title') or '').upper(), 34, 'bold', WHITE, sh=True, wrap=True),
              txt(_('by %s') % lv.get('author', ''), 17, 'semi', SOFT, sh=True),
              pad=[24, 18, 24, 16], al='f', va='f')
    buttons = []
    if st in LV_BUTTON and not busy:
        if st == 'installed':
            buttons.append(quiet(tab_id(TAB, 'lvgo', lv['id']), LV_BUTTON[st]))
        elif st == 'page':
            buttons.append(quiet(tab_id(TAB, 'lvgo', lv['id']), LV_BUTTON[st] + '  ›'))
        else:
            buttons.append(primary(tab_id(TAB, 'lvgo', lv['id']), LV_BUTTON[st] + '  ›'))
    rate = _('YOUR VOTE %s  ›') % ('★' * int(lv['mine'])) if lv.get('mine') else _('RATE IT  ›')
    buttons.append(link(tab_id(TAB, 'lvrate', lv['id']), rate, pad=[24 if buttons else 0, 0, 0, 0], va='c'))
    stars = None
    if str(_mem(ig).get('rate')) == str(lv['id']):   # (the window's menu of 1 to 5 stars)
        stars = row(*[quiet(tab_id(TAB, 'lvvote', '%s/%d' % (lv['id'], n)), '%s%s   %d' % ('★' * n, '☆' * (5 - n), n),
                            pad=[0 if n == 5 else 8, 0, 0, 0]) for n in (5, 4, 3, 2, 1)], pad=[0, 12, 0, 0])
    body = col(txt(desc, 17, 'medium', SOFT, wrap=True) if desc else None,
               txt('   ·   '.join(info), 15, 'medium', MUTED, wrap=True, pad=[0, 6, 0, 0]),
               txt(words, 17, 'medium', KIND_FG.get(kind, SOFT), wrap=True, pad=[0, 6, 0, 0]),
               row(*buttons, pad=[0, 16, 0, 0]), stars, pad=[24, 16, 24, 20])
    return size(col(stack(img(photo, CARD_W, PHOTO_H), top), box(body, bg=PANEL)), w=CARD_W)


def _livery_row(a, lv, st, on):
    busy = (a._livery_busy or {}).get(lv['id'])
    colour = _hex(ROW_COLOUR.get(st) or ROW_COLOUR['other'])
    line = row(size(box(None, bg=colour), w=4, h=44, va='c'), sp(14),
               col(txt(lv.get('title') or '', 19, 'bold', WHITE if on else SOFT),
                   txt('  ·  '.join(x for x in (lv.get('carName') or lv.get('car') or '', lv.get('author') or '') if x),
                       14, 'medium', MUTED), fill=1, va='c'),
               sp(12),
               col(txt(liveries.stars_text(lv), 14, 'medium', FG2, j=2),
                   txt(busy or _(SHORT.get(st, st)), 16, 'semi', colour if st == 'installed' else FG2, j=2), va='c'))
    return btn_row(tab_id(TAB, 'lvpick', lv['id']), line, on)


# ---------------------------------------------------------------------- clicks
def _item(a, item_id):
    return next((x for cat, _l in CATEGORIES for x in _items(a, cat) if x['id'] == item_id), None)


def _livery(a, livery_id):
    return a._livery_of(livery_id)


def _closed_first(ig):
    """True when the game runs (said, as the window says it): what changes its files waits."""
    if community.game_running():
        ig.say('ACR Daily', [CLOSE_GAME])
        return False
    return True


def click(ig, action_, arg):
    a, m = ig.app, _mem(ig)
    m['dirty'] = True
    if action_ == 'lvmore':
        m['lv_upto'] = (m.get('lv_upto') or LV_PAGE) + LV_PAGE
        return
    if action_ in ('car', 'sort'):
        m['lv_upto'] = None                  # (another car / order: from its first ones again)
    if action_ == 'cat':
        if arg in dict(CATEGORIES):
            a.community_select(arg)
            m.pop('tools', None)
            m.pop('rate', None)
        return
    if action_ == 'pick':
        if _item(a, arg) is not None:
            if a.community_picks is None:
                a.community_picks = {}
            a.community_picks[a.community_cat] = arg
            m.pop('tools', None)
        return
    if action_ in ('go', 'support', 'tool', 'rebuild', 'show'):
        item_id = (arg or '').rsplit('/', 1)[0] if action_ == 'tool' else arg
        it = _item(a, item_id)
        if it is None:
            return
        if action_ == 'go':
            _go(ig, it)
        elif action_ == 'support':
            url = str((it.get('support') or {}).get('url') or '')
            if url.startswith('https://'):
                webbrowser.open(url)
        elif action_ == 'tool':
            tools = _tools(it)
            try:
                webbrowser.open(tools[int(arg.rsplit('/', 1)[1])]['page'])
            except (ValueError, IndexError):
                pass
        elif action_ == 'rebuild' and _closed_first(ig):
            a.community_export_rebuild(it)
        elif action_ == 'show' and _closed_first(ig):
            a.community_show(it)
        return
    if action_ == 'showonly':
        if arg in SWITCH_NAMES and _closed_first(ig):
            a._community_show_group(arg)
    elif action_ == 'all':
        if _closed_first(ig):
            a.community_install_all()
    elif action_ == 'stopall':
        a.community_export_stop_all()
    elif action_ == 'car':
        ids = [''] + [c['id'] for c in _cars(a)]
        i = ids.index(a.livery_car) if a.livery_car in ids else 0
        a.livery_filter(car=ids[(i + (1 if arg == 'next' else -1)) % len(ids)])
        m.pop('rate', None)
    elif action_ == 'sort':
        if arg in dict(LV_SORTS):
            a.livery_filter(sort=arg)
    elif action_ == 'lvpick':
        lv = _livery(a, arg)
        if lv is not None:
            a.livery_pick = lv['id']
            m.pop('rate', None)
    elif action_ == 'lvgo':
        lv = _livery(a, arg)
        if lv is None or (a._livery_busy or {}).get(lv['id']):
            return
        st = liveries.status(lv)
        if st == 'installed':
            a.livery_remove(lv)
        elif st == 'page':
            a.livery_page(lv)
        elif st == 'install':
            a.livery_install(lv)
    elif action_ == 'lvrate':
        m['rate'] = None if str(m.get('rate')) == str(arg) else arg
    elif action_ == 'lvvote':
        lid, _sep, n = (arg or '').rpartition('/')
        lv = _livery(a, lid)
        if lv is not None and n.isdigit() and 1 <= int(n) <= 5:
            m.pop('rate', None)
            a.livery_vote(lv, int(n))


def _go(ig, it):
    """The card's button, as it stands now (the window's _community_fill)."""
    a, m = ig.app, _mem(ig)
    st = a._community_status(it)
    act = action(a, it, st)
    if act is None:
        return
    if act[0] == 'window':
        ig.window(TAB)
        return
    label, fn, _main, closed = act
    if it.get('install') == 'link':                  # GET IT / OPEN PAGE: the tool's page (more than one: which)
        tools = _tools(it)
        if len(tools) < 2:
            page = tools[0]['page'] if tools else it.get('page')
            if page:
                webbrowser.open(page)
        else:
            m['tools'] = None if m.get('tools') == it['id'] else it['id']
        return
    if closed and not _closed_first(ig):
        return
    fn()
