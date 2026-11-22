"""RANKED's chat: the drivers of a session talking to each other (the user, 22 Nov 2026: "a game chat within players
who take part in the ranked. Scrollable window, one can turn off or on, and write there"). The server keeps the lines
(src/liverallies.js chat: its drivers only, 200 characters a line, one every 2 s); the app asks for the new ones every
pollS while RANKED is on screen with the chat on, in a thread. The page draws it: ig_ranked.chat_part.

State, per session key: {'lines': [{id, steamId, name, body, at}], 'last': newest id, 'at', 'poll', 'busy', 'draft',
'note', 'sending'}."""
import threading
import time

from .i18n import _

KEEP = 200                            # the lines kept (the newest)
POLL_S = 4.0


def on(app):
    """The chat shown (RANKED's own switch, on by default)."""
    return bool(app.s.get('rankedChat', True))


def toggle(app):
    app.s['rankedChat'] = not on(app)
    try:
        from . import settings
        settings.save(app.s)
    except Exception:
        pass


def state(mem, key):
    return mem.setdefault('chat', {}).setdefault(key, {'lines': [], 'last': 0, 'at': -1e9, 'poll': POLL_S,
                                                        'busy': False, 'draft': '', 'note': '', 'sending': False})


def take(st, msgs):
    """New lines in (any already had, by id, left out), the newest KEEP kept."""
    have = {x['id'] for x in st['lines']}
    for x in msgs or ():
        if isinstance(x, dict) and isinstance(x.get('id'), int) and x['id'] not in have:
            st['lines'].append(x)
            have.add(x['id'])
    st['lines'].sort(key=lambda x: x['id'])
    del st['lines'][:-KEEP]


def poll(app, st, key, force=False):
    """The new lines asked for (at most every pollS; in a thread)."""
    now = time.monotonic()
    if st['busy'] or (not force and now - st['at'] < st['poll']) or not app.s.get('token'):
        return
    st['at'], st['busy'] = now, True

    def go():
        try:
            r = app.api.live_chat(key[0], key[1], st['last']) or {}
            take(st, r.get('messages'))
            # (the cursor from what was asked for only: a line of mine sent meanwhile never skips the others')
            ids = [x['id'] for x in r.get('messages') or () if isinstance(x, dict) and isinstance(x.get('id'), int)]
            if ids:
                st['last'] = max(st['last'], max(ids))
            st['poll'] = float(r.get('pollS') or POLL_S)
            if st['note'] == _('The chat could not be reached.'):
                st['note'] = ''
        except Exception:
            st['note'] = _('The chat could not be reached.')
        finally:
            st['busy'] = False
    threading.Thread(target=go, daemon=True).start()


def send(app, st, key):
    """The draft sent (in a thread): it shows once the server has it; the server's words when it says no."""
    body = ' '.join((st['draft'] or '').split())
    if not body or st['sending']:
        return
    st['sending'] = True

    def go():
        try:
            r = app.api.live_chat_send(key[0], key[1], body) or {}
            if isinstance(r.get('message'), dict):
                take(st, [r['message']])
            st['draft'], st['note'] = '', ''
        except Exception as e:
            st['note'] = str(e) or _('Not sent.')
        finally:
            st['sending'] = False
            st['at'] = -1e9                     # (the others' lines asked for at once)
    threading.Thread(target=go, daemon=True).start()
