"""CASUAL (server src/casual.js): a lobby of up to four, the user's ask of 25 Nov 2026. The host (the driver) picks the
stage, car, weather, time of day, the languages they speak, and public or private (a code); up to three co-drivers join
and read the notes (voice over the crew's links, crew.py; the notes also on the website for a co-driver without the game:
a QR code in the lobby). No results and no limits: driving alone (1 of 4) is fine, and then the game's own co-driver
stays on. Built on copilot.py's machinery (the driver's stage in the app's tt under CP_SLOT, the co-driver's WATCH, the
voice): the same one lobby at a time, either mode.
"""
import threading
import time

from .copilot import CP_SLOT, Copilot
from .i18n import _

OPTIONS_S = 600.0                 # what can be picked: asked again this often
LIST_S = 6.0                      # the lobby browser: this often while the page is on screen
ROOM_BASE = 1000000               # the relay's room for a casual lobby: cp:<ROOM_BASE + id> (a daily crew's ids are small)
MAX_LANGS = 3
LANGS = ('en', 'es', 'fr', 'de', 'it', 'pt', 'pl', 'cs', 'sk', 'hu', 'ro', 'ru', 'uk', 'tr', 'nl', 'sv', 'no', 'da', 'fi',
         'el', 'ja', 'ko', 'zh', 'ar', 'he', 'id', 'th', 'vi', 'lt', 'lv', 'et', 'bg', 'hr', 'sr', 'sl')
# the flag each language shows as (the country most often meant; the page draws flags as the driver page's: flags.py)
LANG_FLAG = {'en': 'GB', 'es': 'ES', 'fr': 'FR', 'de': 'DE', 'it': 'IT', 'pt': 'PT', 'pl': 'PL', 'cs': 'CZ', 'sk': 'SK',
             'hu': 'HU', 'ro': 'RO', 'ru': 'RU', 'uk': 'UA', 'tr': 'TR', 'nl': 'NL', 'sv': 'SE', 'no': 'NO', 'da': 'DK',
             'fi': 'FI', 'el': 'GR', 'ja': 'JP', 'ko': 'KR', 'zh': 'CN', 'ar': 'SA', 'he': 'IL', 'id': 'ID', 'th': 'TH',
             'vi': 'VN', 'lt': 'LT', 'lv': 'LV', 'et': 'EE', 'bg': 'BG', 'hr': 'HR', 'sr': 'RS', 'sl': 'SI'}


def flag_emoji(lang):
    """A language's flag as the two regional-indicator letters (the game's font may not draw it: the pages draw the
    country code beside as a fallback, ig_casual.flags)."""
    cc = LANG_FLAG.get(lang)
    return ''.join(chr(0x1F1E6 + ord(ch) - 65) for ch in cc) if cc else ''


class Casual(Copilot):
    SLOT = CP_SLOT

    def __init__(self, app):
        super().__init__(app)
        self.options = None          # GET /api/casual/options
        self.lobbies = []            # the lobby browser
        self._opt_at = self._list_at = -1e9
        self.enabled = None          # None: not asked yet; the server's word

    # ---- what the pages ask
    def me(self):
        return (self.lobby or {}).get('me') or {}

    def role(self):
        return self.me().get('role')

    def members(self):
        return (self.lobby or {}).get('members') or []

    def others(self):
        sid = self.me().get('steamId')
        return [m for m in self.members() if m.get('steamId') != sid]

    def solo(self):
        return len(self.members()) <= 1

    def is_host(self):
        return self.me().get('seat') == 0

    def partner(self):
        return next((m for m in self.members() if m.get('role') == 'driver'), None)

    def room_id(self):
        return ROOM_BASE + int((self.lobby or {})['id'])

    def mod_on(self):
        """The game's own co-driver off only when someone reads the notes (a solo driver keeps it)."""
        return self.started() and not self.solo()

    def notes_url(self):
        """The notes on the website, for a co-driver without the game (the QR code): the full address, or ''."""
        path = (self.lobby or {}).get('notesUrl')
        if not path:
            return ''
        base = getattr(self.app.api, 'base', None) or getattr(self.app.api, 'server', None) or 'https://acrdaily.com'
        base = str(base).rstrip('/')
        return path if path.startswith('http') else base + path

    # ---- the server
    def refresh(self, force=False):
        """The open lobbies, mine, and (now and then) what can be picked."""
        a = self.app
        now = time.monotonic()
        if self._polling or (not force and now - self._list_at < LIST_S) or not a.api.configured:
            return
        self._list_at, self._polling = now, True
        want_options = self.options is None or now - self._opt_at > OPTIONS_S

        def go():
            try:
                d = a.api.casual()
                o = a.api.casual_options() if want_options and d.get('on') else None
            except Exception as e:
                a.root.after(0, self._day_failed, e)
                return
            a.root.after(0, self._take_list, d, o)
        threading.Thread(target=go, daemon=True).start()

    def _take_list(self, d, o=None):
        self._polling = False
        self.enabled = bool(d.get('on'))
        self.day = d                                   # (the pages test it for 'loaded')
        self.lobbies = d.get('lobbies') or []
        if o:
            self.options, self._opt_at = o, time.monotonic()
        if d.get('lobby') is not None or self.lobby is None:
            self._take_lobby(d.get('lobby'))

    def _fetch_lobby(self, lobby_id):
        return self.app.api.casual_lobby(lobby_id)

    def _take_lobby(self, l):
        super()._take_lobby(l)
        if l and l.get('state') in ('open', 'started') and not self.solo():
            self.start_link()
            if self.crew is not None:
                self.crew.sync(self.peers())
                self.crew.signals(l.get('signals'))
        elif self.crew is not None and l and self.solo():
            self.stop_link()                           # (everyone left: nobody to talk to)

    def _ended(self, l):
        self.stop_link()
        self.app.root.after(1500, lambda: self.refresh(force=True))
        tt = getattr(self.app, 'tt', None) or {}
        t = tt.get(self.SLOT)
        if t and (t.get('ch') or {}).get('id', '').startswith('cx:') and not (t.get('judge') and t['judge'].state == 'running'):
            del tt[self.SLOT]

    # ---- the link
    def peers(self):
        me = self.me()
        if me.get('seat') == 0:
            return [(m['steamId'], m['seat']) for m in self.others() if m.get('steamId')]
        d = self.partner()
        return [(d['steamId'], 0)] if d and d.get('steamId') else []

    def start_link(self):
        if not self.solo():                            # (alone: nobody to talk to)
            super().start_link()

    def my_seat(self):
        return self.me().get('seat') or 0

    def _publish(self, lid, sid, data):
        self.app.api.casual_signal(lid, sid, data)

    def _signals_in(self, l):
        if self.crew is not None:
            self.crew.signals(l.get('signals'))

    def speaking(self):
        v = self.voice
        if v is None:
            return []
        names = {m.get('seat'): m.get('name') or '?' for m in self.members()}
        return [_('You') if s == 'me' else names.get(s, '?')
                for s in sorted(v.speaking(), key=lambda x: (x == 'me', x if x != 'me' else 0))]

    def speakers(self):
        """The icons' data: [(name, seat, speaking now)] for everyone in the lobby but me, then me (seat 'me')."""
        v = self.voice
        now = v.speaking() if v is not None else set()
        out = [(m.get('name') or '?', m.get('seat'), m.get('seat') in now) for m in self.others()]
        out.append((_('You'), 'me', 'me' in now))
        return out

    # ---- the buttons
    OTHER = 'copilot'

    def create(self, opts):
        """opts: {'track', 'car', 'weather', 'time', 'langs': [...], 'private': bool}."""
        if self._guard_other_mode():
            self._bg(lambda: self.app.api.casual_create(opts), lambda r: self._take_lobby(r.get('lobby')))

    def join(self, lobby_id=None, code=None):
        if self._guard_other_mode():
            self._bg(lambda: self.app.api.casual_join(lobby_id, code), lambda r: self._take_lobby(r.get('lobby')))

    def ready(self, on=True):
        l = self.lobby or {}
        if l.get('id'):
            self._bg(lambda: self.app.api.casual_ready(l['id'], on), lambda r: self._take_lobby(r.get('lobby')))

    def start(self):
        l = self.lobby or {}
        if l.get('id') and self.is_host():
            self._bg(lambda: self.app.api.casual_start(l['id']), lambda r: self._take_lobby(r.get('lobby')))

    def leave(self):
        l = self.lobby or {}
        if not l.get('id'):
            return
        lid = l['id']

        def gone(_r):
            self._take_lobby(None)
            self.refresh(force=True)
        self._bg(lambda: self.app.api.casual_leave(lid), gone)

    # ---- the stage
    def watch_run(self, t, j, evs):
        return []                                      # (no rules to judge: a casual drive has no result)

    def start_alert(self):
        if self.solo():
            return None
        if self.game_codriver_off() is False:
            return (_("THE GAME'S CO-DRIVER IS ON"),
                    (_("Switch it off in the game's settings (Co-driver): your co-driver reads the notes."),), 'warn')
        return None

    def armed_line(self):
        from .ttui import _c
        return _('Good luck!'), _c().SOFT

    def on_result(self, result):
        """The drive's end: no result is kept (a casual stage has none), the time said under the clock."""
        a = self.app
        from .judge import fmt_ms
        if result.get('status') == 'finished' and result.get('totalMs'):
            text = _('Finished: %s') % fmt_ms(result['totalMs'])
            said = _('FINISHED · NOT RANKED')
        else:
            text, said = _('Stage over.'), _('STAGE OVER')
        self.final = text

        def shown():
            t = (getattr(a, 'tt', None) or {}).get(self.SLOT)
            if t is not None:
                t['said'] = said
            a.sub_l.configure(text=text)
        a.root.after(0, shown)
