"""INBOX in the game (ingamekit.py says how a page is made): the window's inbox (inboxui.py). The notices from ACR Daily
(read once shown here) beside the conversations; one opened: its messages, newest first, under the box to write in
(SEND sends what was typed: the window's inbox_send). A new conversation, blocking and reporting are the website's, as in
the window. The data is the window's own (app.inbox, inbox_with, inbox_thread...), asked for by its refresh_inbox."""
import time

from .i18n import _
from .ig_profile import avatar_png, hexc
from .inboxui import PRIVATE, TAB_OF, ago, one_line, ref_page
from . import tmtext
from .ingamekit import (ACC, FG2, LINE, LINE2, MUTED, PAGE_W, PANEL, PANEL2, SOFT, WHITE, box, btn, chip, col, edit, empty,
                        img, kicker, line_row, link, primary, row, size, sp, stack, tab_id, txt)

TAB = 'inbox'
GAP = 28
HALF = (PAGE_W - GAP) // 2
NOTICES = 8                    # notices listed (the rest: the website)
THREADS = 10                   # conversations listed
MESSAGES = 40                  # a conversation's last messages shown
REFRESH_S = 60                 # asked for again while on screen (as the window's view: every minute)


def opened(ig):
    m = ig.mem(TAB)
    m['asked'], m['fresh'] = set(), set()
    m['next'] = time.monotonic() + REFRESH_S
    ig.app.refresh_inbox()


def page(ig):
    a = ig.app
    m = ig.mem(TAB)
    if not a.s.get('token'):
        return col(kicker(_('Inbox')), txt(_('Not signed in. Sign in from the ACR Daily launcher.'), 22, 'medium', SOFT,
                                           pad=[0, 10, 0, 0]), al='l')
    settle(a, m)
    if ig.shown and time.monotonic() >= m.setdefault('next', time.monotonic() + REFRESH_S):
        m['next'] = time.monotonic() + REFRESH_S
        a.refresh_inbox()                        # (a thread: the page is drawn again once it is in)
    if a.inbox_with:
        return conversation(ig)
    return the_list(ig)


def settle(a, m):
    """A message SEND gave the window's inbox_send: once done, sent (no note under the box) -> its draft emptied."""
    s = m.get('sending')
    if not s or getattr(a, '_inbox_sending', False):
        return
    m['sending'] = None
    drafts = m.setdefault('drafts', {})
    if a.inbox_note is None and (drafts.get(s[0]) or '').strip() == s[1]:
        drafts[s[0]] = ''


# ---- the list
def the_list(ig):
    a = ig.app
    m = ig.mem(TAB)
    r = a.inbox
    if r is None:
        return col(kicker(_('From ACR Daily')), empty(a.inbox_msg or _('Loading…'), pad=[0, 10, 0, 0]))
    now = time.time() * 1000
    notices, threads = r.get('notices') or [], r.get('threads') or []
    shown = notices[:NOTICES]
    new = [n['id'] for n in shown if not n.get('read') and n.get('id') is not None]
    fresh = m.setdefault('fresh', set())
    if ig.shown:                                  # (read once seen: not while the pages are away)
        fresh.update(new)
        ask = [i for i in new if i not in m.setdefault('asked', set())]
        if ask:
            m['asked'].update(ask)
            a._inbox_read(ask)
    left = col(kicker(_('From ACR Daily'), pad=[0, 0, 0, 10]),
               *([notice_row(n, now, n.get('id') in fresh or not n.get('read')) for n in shown] or
                 [txt(_('Nothing yet. Challenges, cup matches and their results are told here.'), 17, 'medium', MUTED,
                      wrap=True)]))
    right = col(row(kicker(_('Messages')), sp(fill=1), pad=[0, 0, 0, 4]),
                txt(PRIVATE, 15, 'medium', MUTED, wrap=True, pad=[0, 0, 0, 8]),
                *([thread_row(t, now) for t in threads[:THREADS]] or
                  [txt(_('No messages yet.'), 17, 'medium', MUTED)]))
    more = max(0, len(notices) - NOTICES) + max(0, len(threads) - THREADS)
    foot = row(link(tab_id(TAB, 'site'), (_('%d more on the website  ›') % more) if more
                    else _('New message on the website  ›')),
               sp(fill=1), txt(a.inbox_msg, 15, 'medium', MUTED) if a.inbox_msg else None, pad=[0, 16, 0, 0])
    return col(row(size(box(left, bg=PANEL, p=[22, 16, 22, 18], ol=LINE), w=HALF, va='f'), sp(GAP),
                   size(box(right, bg=PANEL, p=[22, 16, 22, 18], ol=LINE), w=HALF, va='f')), foot)


def notice_row(n, now, new):
    """A notice: a red bar while new; a link to its tab in the game (a match to drive...) and to its page on the
    website."""
    text = n.get('body') or ''
    tab = TAB_OF.get(n.get('kind')) or (('league', _('RALLIES')) if 'LEAGUES' in text or 'RALLIES' in text else None)
    page = ref_page(n.get('ref'))
    sub = row(txt(ago(n.get('created'), now), 15, 'medium', MUTED, va='c'), sp(fill=1),
              link(tab_id(TAB, 'tab', tab[0]), '%s  ›' % tab[1], sz=16, va='c') if tab else None,
              sp(18) if tab and page else None,
              link(tab_id(TAB, 'ref', n.get('id')), page[0], sz=16, va='c') if page and n.get('id') is not None else None,
              pad=[0, 4, 0, 0])
    # (its words a row the wheel's / pad's arrows can stop on, so a long list scrolls with them; its links under it
    # stay buttons of their own, 22 Nov 2026)
    words = line_row(txt(text, 18, 'semi', WHITE if new else SOFT, wrap=True), fid='inbox:n:%s' % n.get('id'), h=None)
    return row(size(box(None, bg=ACC if new else PANEL), w=4, va='f'), sp(6),
               col(words, dict(sub, pad=[8, 4, 0, 0]), fill=1), pad=[0, 6, 0, 8])


def thread_row(t, now):
    """A conversation: the other driver, how many of their messages are new, the last one (a click opens it)."""
    who, last, n = t.get('with') or {}, t.get('last') or {}, t.get('unread') or 0
    top = row(txt(tmtext.tagged(who, who.get('name') or _('Driver')), 20, 'bold', WHITE if n else SOFT, va='c'),
              chip(_('%d NEW') % n, pad=[10, 0, 0, 0], va='c') if n else None,
              txt(_('BLOCKED'), 13, 'bold', MUTED, sp=60, va='c', pad=[10, 0, 0, 0]) if t.get('blocked') else None,
              sp(fill=1), txt(ago(last.get('created'), now), 15, 'medium', MUTED, va='c'))
    body = txt(((_('You:') + ' ') if last.get('mine') else '') + one_line(last.get('body'), 90), 16, 'medium',
               FG2 if n else MUTED)
    inside = row(size(box(None, bg=ACC if n else '-'), w=4, va='f'), sp(12),
                 avatar(who.get('avatar'), 44), sp(12), col(top, body, fill=1, va='c'))
    return btn(tab_id(TAB, 'open', who.get('steamId')), c=inside, bg='-', hov=PANEL2, p=[0, 6, 8, 6], r=2, al='f',
               pad=[0, 2, 0, 0]) if who.get('steamId') else inside


def avatar(url, px):
    """A driver's picture, round; a grey dot until it is in."""
    return stack(size(box(None, bg=PANEL2, r=px // 2), w=px, h=px), img(avatar_png(url, px), px, px), va='c')


# ---- a conversation
def conversation(ig):
    a = ig.app
    m = ig.mem(TAB)
    r = a.inbox_thread or {}
    known = next((t.get('with') for t in (a.inbox or {}).get('threads') or []
                  if (t.get('with') or {}).get('steamId') == a.inbox_with), None)
    who = r.get('with') or known or {}
    name = who.get('name') or _('Driver')
    head = row(link(tab_id(TAB, 'back'), _('‹  INBOX'), sz=18, f='bold'), sp(fill=1),
               link(tab_id(TAB, 'site_with'), _('Open on the website  ›')), pad=[0, 0, 0, 14])
    title = row(avatar(who.get('avatar'), 64), sp(16), col(txt(tmtext.tagged(who, name), 34, 'bold', WHITE),
                                                          txt(_('You blocked this driver. Unblock on the website.'), 15,
                                                              'medium', MUTED) if r.get('blocked') else None, va='c'))
    draft = (m.get('drafts') or {}).get(a.inbox_with, '')
    note = a.inbox_note or (PRIVATE, None)
    write = col(row(box(edit(tab_id(TAB, 'draft'), draft, _('Your message'), fill=1), bg=PANEL2, p=[12, 8, 12, 8], r=2,
                        ol=LINE2, fill=1),
                    sp(12), primary(tab_id(TAB, 'send'), _('SEND  ›'), va='c')),
                txt(note[0], 15, 'medium', hexc(note[1], MUTED) if note[1] else MUTED, wrap=True, pad=[0, 8, 0, 0]),
                pad=[0, 18, 0, 18])
    msgs, now = r.get('messages'), time.time() * 1000
    if msgs is None:
        lines = [empty(a.inbox_msg or _('Loading…'))]
    elif not msgs:
        lines = [empty(_('No messages yet.'))]
    else:
        lines = [bubble(x, name, now) for x in reversed(msgs[-MESSAGES:])]
    return col(head, title, write, *lines)


def bubble(x, name, now):
    """A message: mine on the right, theirs on the left."""
    mine = bool(x.get('mine'))
    inner = col(txt('%s · %s' % (_('You') if mine else name, ago(x.get('created'), now)), 14, 'semi', MUTED,
                    j=2 if mine else 0),
                txt(x.get('body') or '', 20, 'medium', WHITE if mine else SOFT, wrap=True, j=2 if mine else 0,
                    pad=[0, 2, 0, 0]))
    return size(box(inner, bg=PANEL2 if mine else PANEL, p=[16, 10, 16, 12], r=3, ol=LINE), maxw=1100,
                al='r' if mine else 'l', pad=[0, 0, 0, 10])


# ---------------------------------------------------------------------- what's clicked and typed
def text(ig, field, words):
    a = ig.app
    if field == 'draft' and a.inbox_with:
        ig.mem(TAB).setdefault('drafts', {})[a.inbox_with] = words


def click(ig, action, arg):
    a = ig.app
    m = ig.mem(TAB)
    if action == 'open' and arg:
        a.open_conversation(arg)                 # (the window's: read as it opens, asked for)
    elif action == 'back':
        a.close_conversation()
    elif action == 'send':
        send(ig)
    elif action == 'site':
        a.open_page('/inbox')
        ig.browser()
    elif action == 'site_with' and a.inbox_with:
        a.open_page('/inbox?with=' + a.inbox_with)
        ig.browser()
    elif action == 'ref':
        n = next((x for x in (a.inbox or {}).get('notices') or [] if str(x.get('id')) == str(arg)), None)
        page = ref_page((n or {}).get('ref'))
        if page:
            a.open_page(page[1])
            ig.browser()
    elif action == 'tab' and arg:                # a match to drive, a challenge to answer: its tab in the game
        if arg != 'tt':
            ig.mem('comp')['sub'] = arg          # (COMPETITIONS on that part: RALLIES / 1V1 / CUPS, as HOME's tiles)
        ig.click('tab:' + ('tt' if arg == 'tt' else 'comp'))


def send(ig):
    """SEND: the draft typed for this driver, by the window's inbox_send (its checks, its notes under the box)."""
    a = ig.app
    m = ig.mem(TAB)
    to = a.inbox_with
    body = ((m.get('drafts') or {}).get(to) or '').strip()
    var = getattr(a, '_inbox_var', None)
    if not to or not body or var is None:
        return
    var.set(body)
    m['sending'] = (to, body)
    a.inbox_send()
