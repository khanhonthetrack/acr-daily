"""COPILOT (server src/copilot.js): the daily for two, a driver and a co-driver (the user, 24 Nov 2026).

The day's stage, car and weather stay hidden ("?") until you have driven it. Hardcore Mode. Once a day as the driver,
once as the co-driver. A lobby: set one up (public, or private with a code), pick your role; the other joins; both
READY. Then:

- the driver's app takes the game to the stage (its in-game DRIVE, as a time trial stage's: the run judged by the same
  judge and sent with the game's own result, ttui.py, on the app's tt under CP_SLOT, never shown with the time trial);
- the co-driver's app takes their game there to WATCH the driver's car from inside it (watch.py, its 'copilot' kind:
  in the car, no broadcast delay, the crew's own room on the relay), with the stage's notes over it (ig_copilot.py) to
  scroll through and read out (Up / Down: the keyboard's arrows, the wheel's / pad's);
- both talk over voice (voice.py: push to talk or an open microphone), straight between the two PCs when their routers
  allow it, else through the relay (copilotlink.py); the driver's car goes the same way to the co-driver.

The game's own co-driver is off for both: the game mod keeps it off while a crew's stage is on (main.lua codriver_off,
the app's state 'copilot'). It reports whether it is: off on the start line, or the run doesn't count; on again during
the stage: a DNF. Without the mod saying so (an older one), the driver is told to keep it off themselves, and that
switching it on is a DNF.
"""
import json
import threading
import time

from .i18n import _

CP_SLOT = 90                     # the crew's stage in the app's tt (ttui.py: never shown, never fetched as a time trial's)
POLL_S = 1.5                     # my lobby asked for this often while it is open or started
DAY_S = 20.0                     # the day (its open lobbies) this often while the page is on screen
RESUME_S = 15 * 60               # a lobby started this long ago: its stage set up again only by hand (an app restart)
CODRIVER_ON_DNF_S = 3.0          # the game's own co-driver on this long during the stage: a DNF
TALK_MODES = ('ptt', 'open', 'off')
TALK_NAMES = {'ptt': _('PUSH TO TALK'), 'open': _('OPEN MIC'), 'off': _('VOICE OFF')}
ROLE_NAMES = {'driver': _('DRIVER'), 'codriver': _('CO-DRIVER')}


def is_cp(cid):
    return str(cid or '').startswith('cp:')


def settings_of(s):
    """The voice's settings (SETTINGS in the game): {'talk': ptt / open / off, 'key': a key name (voice.VK), 'button':
    a wheel's / pad's button id (cardbuttons.py) or None, 'gain': the other's voice, 0.5..3}."""
    c = s.setdefault('copilot', {})
    from .voice import VK
    c['talk'] = c.get('talk') if c.get('talk') in TALK_MODES else 'ptt'
    c['key'] = c.get('key') if c.get('key') in VK else 'V'
    c['button'] = c.get('button') if isinstance(c.get('button'), str) else None
    try:
        c['gain'] = max(0.5, min(3.0, float(c.get('gain', 1.0))))
    except (TypeError, ValueError):
        c['gain'] = 1.0
    return c


class Copilot:
    def __init__(self, app):
        self.app = app
        self.day = None              # GET /api/copilot (None: not in yet)
        self.board = None
        self.lobby = None            # my lobby, as the server has it
        self.msg = ''
        self.busy = False
        self.notes = []              # the co-driver's notes (once started)
        self.cursor = 0              # the note the co-driver is on
        self.started_id = None       # the lobby whose stage was set up here
        self.link = None             # copilotlink.Link, while a lobby is on
        self.voice = None            # voice.Voice, while a lobby is on
        self._lobby_at = self._day_at = -1e9
        self._polling = False
        self._buttons = None
        self.capturing = None        # SET for push to talk: until when a press is waited for
        self._codriver_on_at = None  # (the game's own co-driver seen on, during the stage, since)

    # ---- what the pages ask
    def role(self):
        return (self.lobby or {}).get('myRole')

    def started(self):
        return (self.lobby or {}).get('state') == 'started'

    def room(self):
        """The relay's room while my crew's stage is on: 'cp:<lobby>' (only the two of us in it), else None."""
        l = self.lobby or {}
        return 'cp:%d' % int(l['id']) if l.get('state') in ('open', 'started') and l.get('id') else None

    def mod_on(self):
        """The game's own co-driver to be kept off (the app's state for the mod: 'copilot')."""
        return self.started()

    def partner(self):
        l = self.lobby or {}
        return l.get('guest') if l.get('me') == 'host' else l.get('host')

    # ---- the server
    def _bg(self, fn, then=None, say_error=True):
        a = self.app
        if self.busy:
            return
        self.busy = True

        def go():
            try:
                r = fn()
                err = None
            except Exception as e:                     # (an ApiError: its words)
                r, err = None, e
            a.root.after(0, self._done, r, err, then, say_error)
        threading.Thread(target=go, daemon=True).start()

    def _done(self, r, err, then, say_error):
        self.busy = False
        if err is not None:
            if say_error:
                self.msg = str(err)
            return
        self.msg = ''
        if then:
            then(r)

    def refresh(self, force=False):
        """The day: its open lobbies, mine, my tries, the stage once revealed."""
        a = self.app
        now = time.monotonic()
        if self._polling or (not force and now - self._day_at < DAY_S) or not a.api.configured:
            return
        self._day_at, self._polling = now, True

        def go():
            try:
                d = a.api.copilot()
                b = a.api.copilot_board() if d.get('on') else None
            except Exception as e:
                a.root.after(0, self._day_failed, e)
                return
            a.root.after(0, self._take_day, d, b)
        threading.Thread(target=go, daemon=True).start()

    def _day_failed(self, e):
        self._polling = False
        self.msg = str(e)

    def _take_day(self, d, b):
        self._polling = False
        self.day, self.board = d, b
        if d.get('lobby') is not None or self.lobby is None:
            self._take_lobby(d.get('lobby'))

    def tick(self, now=None):
        """(app.py, about 10 times a second) My lobby asked for while it is on; its link and voice kept with it; the
        relay's room for it."""
        now = time.monotonic() if now is None else now
        l = self.lobby
        if l and l.get('state') in ('open', 'started') and now - self._lobby_at >= POLL_S and not self._polling:
            self._lobby_at, self._polling = now, True
            a = self.app

            def go():
                try:
                    r = a.api.copilot_lobby(l['id'])
                    a.root.after(0, self._lobby_in, r.get('lobby'))
                except Exception as e:
                    a.root.after(0, self._lobby_failed, e)
            threading.Thread(target=go, daemon=True).start()
        link = getattr(getattr(self.app, 'ghostcars', None), 'live', None)
        if link is not None and self.lobby is None and getattr(link, 'room', None) and str(link.room).startswith('cp:'):
            link.room = None
        elif link is not None and self.room() and getattr(link, 'room', None) != self.room():
            link.room = self.room()                    # (without live rallies on: liverallyui._lr_room does it too)
        self._wire()
        if self.capturing:
            self._capture_tick(now)

    def _lobby_in(self, l):
        self._polling = False
        self._take_lobby(l)

    def _lobby_failed(self, e):
        self._polling = False
        if getattr(e, 'code', None) == 404:            # (gone: closed, or not mine any more)
            self._take_lobby(None)

    def _take_lobby(self, l):
        was = self.lobby
        self.lobby = l
        if not l or l.get('state') not in ('open', 'started'):
            if was and (not l or l.get('id') == was.get('id')):
                self._ended(l or was)
            return
        if l.get('notes') is not None and l.get('notes') != self.notes:
            self.notes = l['notes']
        if self.link is not None and l.get('signal'):
            self.link.peer(l['signal'], (self.partner() or {}).get('steamId'))
        if l.get('state') == 'started' and self.started_id != l.get('id'):
            fresh = time.time() * 1000 - (l.get('started') or 0) < RESUME_S * 1000
            if fresh:
                self.go()

    def _ended(self, l):
        """The lobby over (finished, a DNF, closed): its link and voice gone, the day again (the stage revealed)."""
        self.stop_link()
        self.app.root.after(1500, lambda: self.refresh(force=True))
        tt = getattr(self.app, 'tt', None) or {}
        t = tt.get(CP_SLOT)
        if t and not (t.get('judge') and t['judge'].state == 'running'):
            del tt[CP_SLOT]
        w = getattr(self.app, 'watch', None)
        if w is not None and w.on and w.copilot() and (l or {}).get('state') in ('finished', 'dnf', 'closed'):
            pass                                        # (the co-driver sees the finish: WATCH ends as they leave the stage)

    # ---- the buttons
    def create(self, role, private=False):
        self._bg(lambda: self.app.api.copilot_create(role, private), lambda r: self._take_lobby(r.get('lobby')))

    def join(self, lobby_id=None, code=None):
        self._bg(lambda: self.app.api.copilot_join(lobby_id, code), lambda r: self._take_lobby(r.get('lobby')))

    def ready(self, on=True):
        l = self.lobby or {}
        if l.get('id'):
            self._bg(lambda: self.app.api.copilot_ready(l['id'], on), lambda r: self._take_lobby(r.get('lobby')))

    def leave(self):
        l = self.lobby or {}
        if not l.get('id'):
            return
        lid = l['id']

        def gone(_r):
            self._take_lobby(None)
            self.refresh(force=True)
        self._bg(lambda: self.app.api.copilot_leave(lid), gone)

    # ---- the start: the stage for each one
    def go(self):
        """My crew's stage: the driver drives it, the co-driver watches the driver's car with the notes."""
        l = self.lobby or {}
        ch = l.get('ch')
        if not ch or l.get('state') != 'started':
            return
        self.started_id = l['id']
        self.cursor = 0
        self.start_link()
        if self.role() == 'driver':
            self._drive(ch)
        else:
            self._watch(ch)

    def _drive(self, ch):
        a = self.app
        from .judge import Judge
        from .ghosts import GhostSet
        judge = Judge(ch) if ch.get('route') else None
        if judge is None:
            self.msg = _('The stage has no route: it can\'t be driven from here.')
            return
        a.tt[CP_SLOT] = {'ch': ch, 'judge': judge, 'board': None, 'ghost_for': None, 'ghost_name': None,
                         'ghosts': GhostSet(judge.route, 0), 'ghost_loading': set(), 'copilot': True}
        a._tt_drive_go(CP_SLOT)

    def _watch(self, ch):
        a = self.app
        ig = getattr(a, 'ingame_app', None)
        from . import ig_watch, ingamedrive, saveslot
        from .judge import Judge
        driver = (self.partner() or {})
        held = {'ch': dict(ch, weekend=None), 'judge': Judge(ch) if ch.get('route') else None, 'live': [], 'board': None,
                'name': 'COPILOT', 'eventId': int(self.lobby['id']), 'kind': 'copilot', 'cars': []}
        try:
            setup = ingamedrive.setup_of(ingamedrive.daily_stages(ch), ch['carId'], None)
        except (saveslot.SaveError, KeyError, ValueError):
            self.msg = _('This stage can\'t be set up in the game.')
            return
        if ig is None:
            self.msg = _('Start the game: the co-driver watches from inside it.')
            return
        ig_watch._when_ready(ig, lambda: ig_watch._go(ig, setup, ch, lambda: a.watch.start(
            'event', 1, event=held, prefer=driver.get('steamId'))))

    # ---- the co-driver's notes
    def key(self, k):
        """The co-driver's keys over the stage: up / down a note (left / right: five)."""
        if not self.notes:
            return False
        step = {'up': -1, 'down': 1, 'left': -5, 'right': 5}.get(k)
        if step is None:
            return False
        self.cursor = max(0, min(len(self.notes) - 1, self.cursor + step))
        return True

    def scroll_to(self, n):
        if self.notes:
            self.cursor = max(0, min(len(self.notes) - 1, int(n)))

    # ---- the link and the voice
    def start_link(self):
        if self.link is not None:
            return
        a = self.app
        l = self.lobby or {}
        lid = l.get('id')
        if not lid:
            return
        from .copilotlink import Link
        from .voice import Voice

        def publish(d):
            a.api.copilot_signal(lid, json.dumps(d, separators=(',', ':')))

        def relay():
            return getattr(getattr(a, 'ghostcars', None), 'live', None)

        def samples(m):
            r = relay()
            if r is not None:
                r.take_direct(m)

        self.link = Link(publish, samples, lambda p: self.voice and self.voice.heard(p), relay)
        if l.get('signal'):
            self.link.peer(l['signal'], (self.partner() or {}).get('steamId'))
        c = settings_of(a.s)
        self.voice = Voice(self.link.send_voice, self._held, mode=c['talk'], gain=c['gain'])
        self._wired = None

    def _wire(self):
        """The relay's link (it can be made again: ghost cars switched, a reconnect) tied to ours: the driver's
        samples sent straight too, the crew's voice through it."""
        if self.link is None:
            return
        live = getattr(getattr(self.app, 'ghostcars', None), 'live', None)
        if live is None or getattr(self, '_wired', None) is live:
            return
        self._wired = live
        link, me = self.link, self.app.s
        live.on_crew = link.crew
        if self.role() == 'driver':
            live.tee = lambda m: link.send_samples(dict(m, sid=me.get('steamId') or '', name=me.get('name') or '',
                                                        car=getattr(live, 'car', '') or ''))
        else:
            live.tee = None

    def stop_link(self):
        live = getattr(getattr(self.app, 'ghostcars', None), 'live', None)
        if live is not None:
            live.tee, live.on_crew, live.direct_sid = None, None, None
        if self.voice is not None:
            self.voice.close()
        if self.link is not None:
            self.link.close()
        self.link = self.voice = self._wired = None

    def set_talk(self, mode):
        c = settings_of(self.app.s)
        if mode in TALK_MODES:
            c['talk'] = mode
            from . import settings
            settings.save(self.app.s)
            if self.voice is not None:
                self.voice.mode = mode

    def _held(self):
        """Push to talk held now: its key, or its wheel's / pad's button."""
        c = settings_of(self.app.s)
        from .voice import key_held
        if key_held(c['key']):
            return True
        if c['button']:
            if self._buttons is None:
                from .cardbuttons import Buttons
                self._buttons = Buttons()
            try:
                return c['button'] in self._buttons.held()
            except Exception:
                return False
        return False

    def capture_button(self):
        """SET: the next wheel / pad button pressed is push to talk (for 10 s)."""
        from .cardbuttons import Buttons, CAPTURE_S
        if self._buttons is None:
            self._buttons = Buttons()
        self._buttons.poll()
        self.capturing = time.monotonic() + CAPTURE_S

    def _capture_tick(self, now):
        if now > self.capturing:
            self.capturing = None
            return
        pressed = self._buttons.poll()
        if pressed:
            c = settings_of(self.app.s)
            c['button'] = pressed[0]
            from . import settings
            settings.save(self.app.s)
            self.capturing = None

    def link_text(self):
        """How the two are linked, for the page: 'DIRECT · 23 MS', 'THROUGH THE RELAY', 'CONNECTING…'."""
        if self.link is None:
            return ''
        m = self.link.mode()
        if m == 'direct':
            return _('DIRECT · %d MS') % round(self.link.rtt_ms) if self.link.rtt_ms is not None else _('DIRECT')
        if m == 'relay':
            return _('THROUGH THE RELAY')
        return _('CONNECTING…')

    # ---- the driver's run (ttui.py)
    def watch_run(self, t, j, evs):
        """The driver's stage, every frame: the game's own co-driver on (the mod says so) at the start: the run won't
        count (said); on again during the stage for CODRIVER_ON_DNF_S: a DNF. -> events to handle after evs."""
        a = self.app
        try:
            off = a._pulse().codriver_off()
        except Exception:
            off = None
        if 'start' in evs:
            t['codriver_said'] = off
            self._codriver_on_at = None
            if off is None:
                from . import waiting
                waiting.note('copilot: the game mod says nothing of the game\'s co-driver: the driver told to keep it off')
            return []
        if j.state != 'running' or off is not False:
            self._codriver_on_at = None
            return []
        now = time.monotonic()
        if self._codriver_on_at is None:
            self._codriver_on_at = now
        if now - self._codriver_on_at < CODRIVER_ON_DNF_S:
            return []
        from . import waiting
        from .i18n import said
        waiting.note('%s: the game\'s own co-driver on during the stage (DNF)' % (j.ch.get('id') or 'copilot'))
        return j.disqualify(said("the game's own co-driver was on during the stage"))

    def on_result(self, result):
        """The driver's run with the game's official result (or a DNF): to the server, as the crew's."""
        a = self.app
        if not a.api.configured or not a.s.get('token'):
            return
        from . import __version__

        def go():
            try:
                r = a.api._req('POST', '/api/copilot/runs', dict(result, appVersion=__version__), auth=True)
                text = (_('COPILOT: P%s of %s crews. The stage is revealed.') % (r.get('rank'), r.get('drivers'))
                        if r.get('status') == 'finished' and r.get('rank') else _('COPILOT: DNF. The stage is revealed.'))
            except Exception as e:
                text = _('COPILOT: not sent: %s') % e
            a.root.after(0, lambda: (a.sub_l.configure(text=text), self.refresh(force=True)))
        threading.Thread(target=go, daemon=True).start()
