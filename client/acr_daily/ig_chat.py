"""RANKED's chat on the stage (the user, 22 Nov 2026: "it was supposed to be while you're in the car, on stage"): the
session's lines drawn over the game, left of the middle, while I'm in a ranked session and the game is on a stage
(waiting for my turn, between stages); T writes a line (appui.lua: a box the keyboard types in, the car not driven
meanwhile), Enter sends it, Esc puts it away; Page Up / Page Down scroll back. On / off: SETTINGS (rankedchat.on).
The lines come and go through rankedchat.py (the server's: only the session's drivers)."""
import time

from . import rankedchat
from .i18n import _
from .ingamekit import box, btn, col, row, size, sp, txt

W = 520
SHOWN = 8                                  # lines on screen (Page Up: further back)
NAVY, LIVE_C, SOFT_C, MUTED_C = '0A1428', 'FF2D3A', 'D4D4D8', '85858E'


def session_key(app):
    """My ranked session while it runs (registered, its rally not over), or None."""
    try:
        key = app._lr_registered()
    except Exception:
        return None
    if not key:
        return None
    v = (getattr(app, 'lr_data', None) or {}).get(key) or {}
    return None if v.get('phase') == 'over' or v.get('resultsOut') else key


def overlay(ig):
    """-> the chat's tree over the stage, or None (no session, the chat off)."""
    a = ig.app
    if not rankedchat.on(a):
        return None
    key = session_key(a)
    if not key:
        return None
    m = ig.mem('chat-stage')
    st = rankedchat.state(ig.mem('live'), key)
    rankedchat.poll(a, st, key)
    back = max(0, min(m.get('back', 0), max(0, len(st['lines']) - SHOWN)))
    m['back'] = back
    lines = st['lines'][max(0, len(st['lines']) - SHOWN - back):len(st['lines']) - back]
    me = a.s.get('steamId')
    out = [box(row(txt(_('CHAT'), 15, 'bold', 'FFFFFF', sp=120, va='c'), sp(fill=1),
                   txt(_('T or click to write · PgUp / PgDn scroll') if not m.get('typing') else _('Enter send · Esc cancel'),
                       12, 'semi', 'FFFFFF', va='c')),
               bg=LIVE_C, p=[12, 4, 12, 4])]
    for x in lines:
        mine = x.get('steamId') == me
        out.append(box(row(txt((x.get('name') or '?')[:16], 15, 'bold', LIVE_C if mine else 'FFFFFF', va='t'), sp(8),
                           txt(x.get('body') or '', 15, 'medium', SOFT_C, wrap=True, fill=1)),
                       bg=NAVY, a=0.78, p=[12, 3, 12, 3]))
    if not lines:
        out.append(box(txt(_('Nothing said yet.'), 14, 'medium', MUTED_C), bg=NAVY, a=0.78, p=[12, 4, 12, 4]))
    if back:
        out.append(box(txt(_('%d newer below') % back, 12, 'semi', MUTED_C), bg=NAVY, a=0.78, p=[12, 2, 12, 2]))
    if st['note']:
        out.append(box(txt(st['note'], 13, 'semi', 'FF9F0A', wrap=True), bg=NAVY, a=0.85, p=[12, 3, 12, 3]))
    # (a click on it opens the box to write, as T: the user, 24 Nov 2026 "press with a mouse on the chat/comment window
    # and start writing"; appui.lua chat_tick)
    panel = size(btn('chat:open', c=col(*out)), w=W)
    return col(sp(fill=1), row(panel, sp(fill=1)), sp(h=300))


def key(ig, what):
    """The mod's keys for the chat on the stage: 'up' / 'down' (Page Up / Down), 'typing' / 'idle' (the box opened /
    put away)."""
    m = ig.mem('chat-stage')
    if what == 'up':
        m['back'] = m.get('back', 0) + 3
    elif what == 'down':
        m['back'] = max(0, m.get('back', 0) - 3)
    elif what in ('typing', 'idle'):
        m['typing'] = what == 'typing'
    m['at'] = time.monotonic()


def send(ig, words):
    """A line typed on the stage (Enter in the mod's box): sent to my session's chat."""
    a = ig.app
    key_ = session_key(a)
    if not key_ or not ' '.join((words or '').split()):
        return
    st = rankedchat.state(ig.mem('live'), key_)
    st['draft'] = words
    ig.mem('chat-stage')['back'] = 0
    rankedchat.send(a, st, key_)
