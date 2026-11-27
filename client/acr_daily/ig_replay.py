"""REPLAY in the game (ingamekit.py says how a page is made; replays.py what a replay is): the replays kept on this PC,
newest first, one picked beside them: its stage, car, time and what can be told of it (signed by this PC, followed by
the server while driven, the server's checks once sent), and what can be done with it:

  WATCH IN THE GAME   the game taken to its stage, its car played back with the TV director (replayplay.py)
  SEND                to the server: a code (private: its driver, the admin, its rally's stewards), its checks
  SHARE               public: its page on the website (/r/<code>), the link copied (a stage that still counts: once it
                      no longer does)
  STAR                kept past the newest N; DELETE

OPEN A CODE: someone's replay (its code, from their link) fetched and kept with the others; a file someone sent: put it
in the replays folder's "import" folder (OPEN FOLDER), it is taken in when this page opens. The stewards' requests,
when SETTINGS says ask first, wait here for a SEND / NO."""
import os
import threading
import time

from . import replays
from .i18n import _
from .ingamekit import (ACC, FG2, GOOD, LINE, LINE2, MUTED, PAGE_W, PANEL, PANEL2, SOFT, WHITE, box, btn, chip, col, edit,
                        empty, kicker, link, primary, quiet, row, rule, size, sp, tab_id, txt)

TAB = 'replay'
GAP = 28
LEFT_W = 1020
RIGHT_W = PAGE_W - LEFT_W - GAP
PER_PAGE = 12
FILTERS = (('all', _('ALL')), ('counted', _('COUNTED')), ('star', _('STARRED')), ('received', _('SENT TO ME')))
WARN = 'FF9F0A'


def opened(ig):
    m = ig.mem(TAB)
    m['rows'] = None
    threading.Thread(target=_import_folder, args=(ig,), daemon=True).start()


def _import_folder(ig):
    """Files put in the replays folder's 'import' folder: taken in (moved out of it), the page drawn again."""
    d = os.path.join(replays.folder(), 'import')
    try:
        os.makedirs(d, exist_ok=True)
        names = [n for n in os.listdir(d) if n.lower().endswith(replays.EXT)]
    except OSError:
        return
    got = 0
    for n in names:
        p = os.path.join(d, n)
        try:
            replays.import_file(p, replays.opts(ig.app.s)['keep'])
            os.remove(p)
            got += 1
        except (OSError, ValueError) as e:
            ig.note(_('%s: not a replay (%s)') % (n, e))
    if got:
        ig.mem(TAB)['rows'] = None
        ig.note(_('%d replays taken in from the import folder.') % got)


def rows_of(ig):
    m = ig.mem(TAB)
    if m.get('rows') is None or time.monotonic() - m.get('rows_at', 0) > 5:
        try:
            m['rows'] = replays.index()
        except OSError:
            m['rows'] = []
        m['rows_at'] = time.monotonic()
    f = m.get('filter', 'all')
    rows = m['rows']
    if f == 'counted':
        rows = [r for r in rows if r.get('rid') or r.get('kind') in ('daily', 'event')]
    elif f == 'star':
        rows = [r for r in rows if r.get('star')]
    elif f == 'received':
        rows = [r for r in rows if not r.get('mine', True)]
    return rows


def page(ig):
    a = ig.app
    m = ig.mem(TAB)
    rows = rows_of(ig)
    sel = next((r for r in rows if r.get('file') == m.get('sel')), rows[0] if rows else None)
    if sel is not None:
        m['sel'] = sel['file']
    on = replays.opts(a.s)['on']
    head = row(kicker(_('Replays')), sp(12),
               txt(_('%d kept on this PC') % len(m.get('rows') or []), 15, 'medium', MUTED, va='c'),
               sp(fill=1),
               box(edit(tab_id(TAB, 'code'), m.get('code', ''), _('a replay\'s code'), sz=17), bg=PANEL2, p=[10, 6, 10, 6],
                   r=2, ol=LINE2, va='c'),
               sp(8), quiet(tab_id(TAB, 'open_code'), _('OPEN A CODE'), va='c'), sp(8),
               quiet(tab_id(TAB, 'folder'), _('OPEN FOLDER'), va='c'), sp(8),
               quiet(tab_id(TAB, 'check'), _('CHECKING…') if m.get('busy') == 'check' else _('CHECK MY DNFS'), va='c'),
               pad=[0, 0, 0, 12])
    asks = [ask_row(w) for w in (getattr(a, 'replay_asks', None) or [])]
    note = getattr(a, 'replay_note', '') or m.get('note') or ''
    off = None if on else box(txt(_('Replays are off: SETTINGS > Replays turns them on.'), 17, 'semi', WHITE),
                              bg=PANEL2, p=[14, 8, 14, 8], pad=[0, 0, 0, 10])
    filters = row(*[btn(tab_id(TAB, 'filter', k), label, bg=WHITE if m.get('filter', 'all') == k else '-', hov=PANEL2,
                        fg='0A0A0B' if m.get('filter', 'all') == k else FG2, hfg=WHITE, sz=15, f='bold', sp=60,
                        p=[12, 5, 12, 5], r=2, ol=None if m.get('filter', 'all') == k else LINE2,
                        pad=[0 if i == 0 else 6, 0, 0, 0]) for i, (k, label) in enumerate(FILTERS)], pad=[0, 0, 0, 10])
    left = col(filters, *the_list(ig, rows, sel))
    right = detail(ig, sel) if sel else empty(_('No replays yet. Every run you drive is kept here.'))
    return col(head, off, *asks,
               txt(note, 16, 'semi', WHITE, wrap=True, pad=[0, 0, 0, 10]) if note else None,
               row(size(box(left, bg=PANEL, p=[20, 16, 20, 16], ol=LINE), w=LEFT_W, va='f'), sp(GAP),
                   size(box(right, bg=PANEL, p=[22, 16, 22, 18], ol=LINE), w=RIGHT_W, va='f')))


def ask_row(w):
    """A steward's request waiting for the driver's word (SETTINGS: ask me first)."""
    ref = w.get('ref') or ''
    no = ref.rsplit(':', 1)[-1]
    words = _("A rally's stewards ask for your SS%s replay.") % (int(no) + 1 if no.isdigit() else '?')
    return box(row(txt(words, 18, 'semi', WHITE, va='c', fill=1),
                   primary(tab_id(TAB, 'ask_send', w.get('requestId')), _('SEND'), va='c', sz=17, p=[18, 6, 18, 6]), sp(8),
                   quiet(tab_id(TAB, 'ask_no', w.get('requestId')), _('NO'), va='c')),
               bg=PANEL2, p=[16, 8, 16, 8], ol=ACC, pad=[0, 0, 0, 10])


def when(ms):
    if not ms:
        return '-'
    return time.strftime('%d %b %H:%M', time.localtime(ms / 1000.0))


def kind_words(r):
    k = r.get('kind') or 'practice'
    return {'daily': _('DAILY'), 'event': _('ONLINE RALLY'), 'tt': _('TIME TRIAL'), 'practice': _('PRACTICE')}.get(k, k.upper())


def result_words(r):
    if r.get('status') == 'finished' and r.get('clockMs'):
        return replays.fmt_ms((r.get('clockMs') or 0) + (r.get('penaltyMs') or 0))
    return {'dnf': _('DNF'), 'invalid': _('INVALID')}.get(r.get('status'), _('NOT FINISHED'))


def the_list(ig, rows, sel):
    m = ig.mem(TAB)
    n_pages = max(1, (len(rows) + PER_PAGE - 1) // PER_PAGE)
    p = max(0, min(n_pages - 1, m.get('page', 0)))
    m['page'] = p
    out = []
    for r in rows[p * PER_PAGE:(p + 1) * PER_PAGE]:
        on = sel is not None and r['file'] == sel['file']
        badges = row(chip(_('LIVE'), bg=GOOD.lstrip('#'), fg='0A0A0B', va='c') if r.get('rid') else None,
                     chip(_('SENT'), bg=PANEL2.lstrip('#'), pad=[6, 0, 0, 0], va='c') if r.get('code') else None,
                     chip('★', bg=ACC.lstrip('#'), pad=[6, 0, 0, 0], va='c') if r.get('star') else None,
                     chip(_('FROM %s') % (r.get('driver') or '?').upper(), bg=PANEL2.lstrip('#'), pad=[6, 0, 0, 0], va='c')
                     if not r.get('mine', True) else None)
        inside = row(size(box(None, bg=ACC if on else '-'), w=4, va='f'), sp(10),
                     col(row(txt(r.get('track') or '?', 19, 'bold', WHITE, va='c', fill=1),
                             txt(result_words(r), 19, 'bold', WHITE if r.get('status') == 'finished' else MUTED, va='c')),
                         row(txt('%s · %s · %s' % (when(r.get('created')), kind_words(r), r.get('car') or ''), 15, 'medium',
                                 FG2, va='c', fill=1), badges), fill=1))
        out.append(btn(tab_id(TAB, 'sel', r['file']), c=inside, bg=PANEL2 if on else '-', hov=PANEL2, p=[0, 6, 8, 6],
                       r=2, al='f', pad=[0, 2, 0, 0]))
    if not out:
        out.append(empty(_('Nothing here.')))
    if n_pages > 1:
        out.append(row(link(tab_id(TAB, 'page', p - 1), _('‹ NEWER')) if p > 0 else None, sp(fill=1),
                       txt('%d / %d' % (p + 1, n_pages), 15, 'medium', MUTED, va='c'), sp(fill=1),
                       link(tab_id(TAB, 'page', p + 1), _('OLDER ›')) if p < n_pages - 1 else None, pad=[0, 10, 0, 0]))
    return out


def detail(ig, r):
    m = ig.mem(TAB)
    doc = cached_doc(m, r['file'])
    if doc is None:
        return empty(_('This replay can\'t be read.'))
    h = doc['head']
    chk = m.setdefault('checks', {}).get(r['file'])
    if chk is None:
        chk = m['checks'][r['file']] = replays.check(doc)
    st = replays.stats(doc)
    lines = [
        kicker('%s · %s' % (kind_words(r), h.get('title') or ''), pad=[0, 0, 0, 4]),
        txt(h.get('track') or '?', 32, 'bold', WHITE, wrap=True),
        txt('%s · %s' % ((h.get('driver') or {}).get('name') or '', h.get('car') or ''), 17, 'medium', FG2, pad=[0, 2, 0, 10]),
        row(col(kicker(_('Time')), txt(result_words(r), 30, 'bold', WHITE)), sp(30),
            col(kicker(_('Penalty')), txt('%.1f s' % ((h.get('penaltyMs') or 0) / 1000.0), 22, 'bold', SOFT)), sp(30),
            col(kicker(_('Top speed')), txt('%d km/h' % st['top'], 22, 'bold', SOFT)), sp(30),
            col(kicker(_('Driven')), txt('%.2f km' % st['km'], 22, 'bold', SOFT))),
        rule_line(),
        check_line(chk['signed'], _('Signed by the ACR DAILY that recorded it: unchanged since')),
        check_line(chk['live'] and chk['chain'] is not False,
                   _('Followed by the server while driven: a proof of when it was driven') if chk['live'] else
                   _('Not followed by the server (practice, offline or not signed in)')),
    ]
    if r.get('verdict'):
        lines.append(check_line(r['verdict'] == 'clean', _("The server's checks: clean") if r['verdict'] == 'clean'
                                else _("The server's checks want a look (the road left, a cut...)")))
    if r.get('code'):
        lines.append(row(txt(_('Code:'), 17, 'semi', MUTED, va='c'), sp(8), txt(r['code'], 22, 'bold', WHITE, sp=40, va='c'),
                         sp(fill=1), link(tab_id(TAB, 'web'), _('Its page on the website  ›'), va='c'), pad=[0, 8, 0, 0]))
    busy = m.get('busy')
    acts = [primary(tab_id(TAB, 'watch'), _('WATCH IN THE GAME')),
            row(quiet(tab_id(TAB, 'send'), _('SENDING…') if busy == 'send' else (_('SENT') if r.get('code') else _('SEND'))),
                sp(8), quiet(tab_id(TAB, 'share'), _('SHARING…') if busy == 'share' else _('SHARE')), sp(8),
                quiet(tab_id(TAB, 'star'), _('UNSTAR') if r.get('star') else _('STAR')), sp(8),
                quiet(tab_id(TAB, 'delete'), _('DELETE')), pad=[0, 10, 0, 0])]
    lines += [sp(h=14), *acts,
              txt(_('SEND gives it a code: private to you, the admin and your rally\'s stewards. SHARE makes its page '
                    'public, the link copied, for Discord or social media.'), 14, 'medium', MUTED, wrap=True,
                  pad=[0, 12, 0, 0])]
    return col(*lines)


def rule_line():
    return rule(pad=[0, 14, 0, 8])


def check_line(ok, words):
    return row(txt('✓' if ok else '–', 20, 'bold', GOOD if ok else WARN, va='c'), sp(10),
               txt(words, 16, 'medium', SOFT if ok else FG2, wrap=True, va='c', fill=1), pad=[0, 4, 0, 0])


def cached_doc(m, name):
    c = m.setdefault('docs', {})
    if name not in c:
        if len(c) > 6:
            c.clear()
        p = replays.path_of(name)
        try:
            c[name] = replays.read(p) if p else None
        except (OSError, ValueError):
            c[name] = None
    return c[name]


# ---------------------------------------------------------------------- what's clicked and typed
def text(ig, field, words):
    if field == 'code':
        ig.mem(TAB)['code'] = words


def click(ig, action, arg):
    a = ig.app
    m = ig.mem(TAB)
    rows = m.get('rows') or []
    sel = next((r for r in rows if r.get('file') == m.get('sel')), None)
    if action == 'sel' and arg:
        m['sel'] = arg
    elif action == 'filter' and arg:
        m['filter'], m['page'] = arg, 0
    elif action == 'page':
        m['page'] = int(arg or 0)
    elif action == 'folder':
        d = os.path.join(replays.folder(), 'import')
        os.makedirs(d, exist_ok=True)
        try:
            os.startfile(d)                          # noqa: S606  (Explorer, behind the game)
            ig.note(_('The import folder is open on the desktop: put a replay file there, then open REPLAY again.'))
        except (OSError, AttributeError):
            ig.note(d)
    elif action == 'open_code':
        open_code(ig, (m.get('code') or '').strip().lower())
    elif action == 'check':
        check(ig)
    elif action in ('ask_send', 'ask_no'):
        w = next((x for x in (getattr(a, 'replay_asks', None) or []) if str(x.get('requestId')) == str(arg)), None)
        if w is not None:
            a.replay_answer(w, action == 'ask_send')
    elif sel is None:
        return
    elif action == 'watch':
        from . import replayplay
        replayplay.start(ig, sel['file'])
    elif action == 'star':
        replays.update(sel['file'], star=not sel.get('star'))
        m['rows'] = None
    elif action == 'delete':
        ig.ask(_('DELETE'), [_('This replay goes from this PC for good.')], _('DELETE'),
               lambda: (replays.remove(sel['file']), m.update(rows=None, sel=None)))
    elif action in ('send', 'share'):
        upload(ig, sel, public=action == 'share')
    elif action == 'web' and sel.get('code'):
        a.open_page('/r/' + sel['code'])
        ig.browser()


def upload(ig, sel, public):
    a = ig.app
    m = ig.mem(TAB)
    if m.get('busy') or not a.s.get('token'):
        if not a.s.get('token'):
            ig.say(_('REPLAY'), [_('Sign in to ACR DAILY to send replays.')])
        return
    m['busy'] = 'share' if public else 'send'

    def done(ans):
        m['busy'], m['rows'] = None, None
        if not ans:
            m['note'] = getattr(a, 'replay_note', '') or _('Not sent.')
            return
        m['note'] = ans.get('action') or (_('Sent: its code is %s.') % ans.get('code'))
        if public:
            url = ans.get('url') or ''
            if ans.get('public'):
                try:
                    a.root.clipboard_clear()
                    a.root.clipboard_append(url)
                    m['note'] = _('Public: %s (the link is copied).') % url
                except Exception:
                    m['note'] = _('Public: %s') % url
            else:
                m['note'] = _('Sent; public once the stage no longer counts (its daily over, its rally closed).')

    def go():
        code = sel.get('code')
        if code and public:                          # (sent already: made public)
            try:
                r = a.api.replay_share(code, True)
                a.root.after(0, lambda: done({'code': code, 'public': r.get('public'),
                                              'url': a.api.base + '/r/' + code}))
            except Exception as e:
                a.root.after(0, lambda: (done(None), m.update(note=str(e))))
            return
        a.replay_send(sel['file'], public=public, done=done)
    threading.Thread(target=go, daemon=True).start()


def check(ig):
    """CHECK MY DNFS: the DNFs of the last 30 days a replay on this PC takes back, sent now (the app does it by itself
    after each run, for 3 days: this for after a crash, or older ones)."""
    a = ig.app
    m = ig.mem(TAB)
    if m.get('busy') or not hasattr(a, 'replay_check'):
        return
    m['busy'], m['note'] = 'check', _('Checking your DNFs of the last 30 days…')
    a.replay_note = ''

    def done(words):
        m['busy'], m['rows'], m['note'] = None, None, words
        a.replay_note = ''                           # (each replay's own word: the summary says them all)
    a.replay_check(done)


def open_code(ig, code):
    a = ig.app
    m = ig.mem(TAB)
    if not code or len(code) != 10 or not code.isalnum():
        ig.note(_('A replay\'s code is 10 letters and numbers (the end of its link: acrdaily.com/r/<code>).'))
        return
    m['note'] = _('Fetching %s…') % code

    def go():
        try:
            data = a.api.replay_file(code)
            doc = replays.loads(data)
            meta = {}
            try:
                meta = a.api.replay_meta(code) or {}
            except Exception:
                pass
            mine = (doc['head'].get('driver') or {}).get('steamId') == a.s.get('steamId')
            name = replays.save(doc, replays.opts(a.s)['keep'], mine=mine)
            replays.update(name, code=code, verdict=meta.get('verdict'))
            m.update(rows=None, sel=name, note=_('Replay %s kept with yours.') % code, filter='all', page=0)
        except Exception as e:
            m['note'] = str(e)
    threading.Thread(target=go, daemon=True).start()
