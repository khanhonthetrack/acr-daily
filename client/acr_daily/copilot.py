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
CODRIVER_ON_DNF_S = 3.0          # the game's own co-driver on this long during the stage: a DNF (mine or the partner's)
STATUS_S = 1.0                   # my game's own co-driver told to the partner this often
TALK_MODES = ('ptt', 'open', 'off')
TALK_NAMES = {'ptt': _('PUSH TO TALK'), 'open': _('OPEN MIC'), 'off': _('VOICE OFF')}
ROLE_NAMES = {'driver': _('DRIVER'), 'codriver': _('CO-DRIVER')}


def is_cp(cid):
    return str(cid or '').startswith(('cp:', 'cx:'))     # (cx: CASUAL's: casual.py)


def settings_of(s):
    """The voice's settings (SETTINGS in the game): {'talk': ptt / open / off, 'key': a key name (voice.VK), 'button':
    a wheel's / pad's button id (cardbuttons.py) or None, 'gain': the other's voice, 0.5..3, 'radio': it through the rally
    intercom (voice.Intercom), on unless turned off}."""
    c = s.setdefault('copilot', {})
    from .voice import VK
    c['talk'] = c.get('talk') if c.get('talk') in TALK_MODES else 'ptt'
    c['key'] = c.get('key') if c.get('key') in VK else 'V'
    c['button'] = c.get('button') if isinstance(c.get('button'), str) else None
    try:
        c['gain'] = max(0.5, min(3.0, float(c.get('gain', 1.0))))
    except (TypeError, ValueError):
        c['gain'] = 1.0
    c['radio'] = c.get('radio') is not False
    c['mic'] = c.get('mic') if isinstance(c.get('mic'), str) else ''          # (a microphone's name: voice.mic_devices; '' the default)
    try:
        c['micgain'] = max(0.25, min(4.0, float(c.get('micgain', 1.0))))
    except (TypeError, ValueError):
        c['micgain'] = 1.0
    return c


class Copilot:
    SLOT = CP_SLOT
    MODE = 'daily'                   # (its tab on the CODRIVER page: ig_copilot.MODES)

    def __init__(self, app):
        self.app = app
        self.day = None              # GET /api/copilot (None: not in yet)
        self.board = None
        self.ranking = None          # this month's drivers and co-drivers (GET /api/copilot/ranking)
        self.partner_off = None      # the partner's game's own co-driver as their app says (True off / False on / None)
        self._partner_on_at = None   # (seen on, during my stage, since)
        self._status_at = -1e9       # (mine told to the partner last)
        self.lobby = None            # my lobby, as the server has it
        self.msg = ''
        self.busy = False
        self.notes = []              # the co-driver's notes (once started)
        self.cursor = 0              # the note the co-driver is on
        self.started_id = None       # the lobby whose stage was set up here
        self.crew = None             # crew.Crew (the links and the voice), while a lobby is on
        self.driver_state = None     # the driver's stage as their app says it (the co-driver's page): {state, ms, gap, pct, at}
        self.final = ''              # my crew's last result, in words (both pages)
        self.mic_test = None         # voice.MicTest, while the settings' meter is on
        self._lobby_at = self._day_at = -1e9
        self._polling = False
        self._buttons = None
        self.capturing = None        # SET for push to talk: until when a press is waited for
        self._codriver_on_at = None  # (the game's own co-driver seen on, during the stage, since)

    # ---- what the pages ask
    @property
    def link(self):
        return self.crew.first() if self.crew is not None else None

    @property
    def voice(self):
        return self.crew.voice if self.crew is not None else None

    def role(self):
        return (self.lobby or {}).get('myRole')

    def started(self):
        return (self.lobby or {}).get('state') == 'started'

    def room(self):
        """The relay's room while my crew's stage is on: 'cp:<lobby>' (only the two of us in it), else None."""
        l = self.lobby or {}
        return 'cp:%d' % self.room_id() if l.get('state') in ('open', 'started') and l.get('id') else None

    def room_id(self):
        return int((self.lobby or {})['id'])

    def mod_on(self):
        """The game's own co-driver to be kept off (the app's state for the mod: 'copilot'): on my crew's stage only
        (another stage driven meanwhile keeps its co-driver)."""
        return self.on_my_stage()

    def on_my_stage(self):
        """My crew's stage is the one in the game now: the driver's (the app judges its stage under SLOT, this lobby's),
        the co-driver's (watching the driver's car)."""
        a = self.app
        if not self.started():
            return False
        if self.role() != 'driver':
            w = getattr(a, 'watch', None)
            return bool(w is not None and w.on and w.copilot())
        t = (getattr(a, 'tt', None) or {}).get(self.SLOT) or {}
        mine = ((self.lobby or {}).get('ch') or {}).get('id')
        return bool(t) and mine is not None and (t.get('ch') or {}).get('id') == mine and \
            getattr(a, 'drive_target', None) == 'tt' and getattr(a, 'tt_active', None) == self.SLOT

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
                r = None                              # (no ranking on the page: today's results only, the user 25 Nov)
            except Exception as e:
                a.root.after(0, self._day_failed, e)
                return
            a.root.after(0, self._take_day, d, b, r)
        threading.Thread(target=go, daemon=True).start()

    def _day_failed(self, e):
        self._polling = False
        self.msg = str(e)

    def _apply_board(self, t):
        """The crew's stage (the app's tt under SLOT): the day's board as the displays' (the leader to chase: the live gap
        from its splits; the split standings under the timer, as the dailies')."""
        b = self.board
        if not t or not isinstance(b, dict) or str((t.get('ch') or {}).get('id', '')).startswith('cx:'):
            return
        entries = []
        for e in b.get('entries') or []:
            d, c = e.get('driver') or {}, e.get('codriver') or {}
            entries.append({'runId': e.get('runId'), 'steamId': d.get('steamId'),
                            'name': '%s / %s' % (d.get('name') or '?', c.get('name') or '?'),
                            'totalMs': e.get('totalMs') if e.get('status') == 'finished' else None, 'splits': e.get('splits')})
        t['board'] = {'entries': entries}
        j = t.get('judge')
        lead = next((e for e in entries if e['totalMs'] is not None and e.get('splits')), None)
        if j is not None and lead is not None and t.get('ghost_for') != lead['runId']:
            t['ghost_for'] = lead['runId']
            j.set_ghost_splits(lead['splits'], lead['totalMs'])
            t['ghost_name'] = _('LEADER')

    def _take_day(self, d, b, r=None):
        self._polling = False
        self.day, self.board = d, b
        self._apply_board((getattr(self.app, 'tt', None) or {}).get(self.SLOT))
        self._apply_board(getattr(self, 'watch_held', None))
        if r is not None:
            self.ranking = r
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
                    r = self._fetch_lobby(l['id'])
                    a.root.after(0, self._lobby_in, r.get('lobby'), l['id'])
                except Exception as e:
                    a.root.after(0, self._lobby_failed, e, l['id'])
            threading.Thread(target=go, daemon=True).start()
        link = getattr(getattr(self.app, 'ghostcars', None), 'live', None)
        owner = self.app.crew_owner() if hasattr(self.app, 'crew_owner') else self
        mine = owner.room() if owner is not None and owner.lobby else None      # (the room of whichever mode has my lobby)
        if link is not None and self.lobby is None and getattr(link, 'room', None) and str(link.room).startswith('cp:') \
                and link.room != mine:
            link.room = None                           # (not the other mode's: both modes tick, one lobby at a time)
        elif link is not None and self.room() and getattr(link, 'room', None) != self.room():
            link.room = self.room()                    # (without live rallies on: liverallyui._lr_room does it too)
        if owner is self and link is not None and hasattr(link, 'set_crew'):
            link.set_crew(self.room())                 # (the crew's own room on the relay: its voice in the menus too)
        if self.crew is not None:
            self.crew.wire()
            if now - self._status_at >= STATUS_S:
                self._status_at = now                  # (my game's own co-driver, to the partner: the driver's check;
                self.crew.send_status(self.status_line())   # and the driver's stage: the co-driver's page)
        if self.mic_test is not None and not self.mic_test.on:
            self.mic_test = None
        if self.capturing:
            self._capture_tick(now)

    def _fetch_lobby(self, lobby_id):
        return self.app.api.copilot_lobby(lobby_id)

    def start_alert(self):
        """(ttui) The crew's start line: (title, lines, 'stop' / 'warn') for the timer's note: the game's own co-driver on
        (mine, or my co-driver's) must be off; else the rules."""
        if self.game_codriver_off() is False:
            return (_("THE GAME'S CO-DRIVER IS ON"),
                    (_("Switch it off in the game's settings (Co-driver), or this run won't count."),
                     _('Your co-driver reads the notes: the game must not.')), 'stop')
        if self.partner_off is False:
            return (_("YOUR CO-DRIVER'S GAME CALLS THE NOTES"),
                    (_("Their game's own co-driver is on: it must be off, or it's a DNF for the crew."),), 'stop')
        return (_('CODRIVER · ONE GO'),
                (_('Good luck! Your co-driver reads the notes: the game\'s own co-driver is off.'),
                 _('Changing settings, driving aids, the co-driver or pacenotes on the stage is a DNF.')), 'warn')

    def armed_line(self):
        """(ttui) The timer's line on the start line: (text, colour)."""
        from .ttui import _c
        return _('Good luck! One go · settings changed = DNF'), _c().SLOW

    def game_codriver_off(self):
        """My game's own co-driver as the mod keeps it (True off, False on, None: can't be told)."""
        try:
            return self.app._pulse().codriver_off()
        except Exception:
            return None

    def status_line(self):
        """My status for the partner: '<1 / 0 / - my game's own co-driver off / on / unknown>' and, from the driver,
        '|<w / r / f / d: waiting, running, finished, DNF>|<clock ms>|<gap to the leader ms>|<percent>'."""
        line = {True: '1', False: '0', None: '-'}[self.game_codriver_off()]
        if self.role() != 'driver':
            return line
        t = (getattr(self.app, 'tt', None) or {}).get(self.SLOT) or {}
        j = t.get('judge')
        if j is None:
            return line
        st = {'running': 'r', 'finished': 'f', 'dnf': 'd', 'invalid': 'd'}.get(j.state, 'w')
        r = j.result or {}
        ms = j.total_ms if st == 'r' else int(r.get('totalMs') or r.get('clockMs') or 0) if st in 'fd' else 0
        gap = j.gap_ms if st == 'r' and j.gap_ms is not None else None
        return '%s|%s|%d|%s|%d' % (line, st, max(0, int(ms)), '' if gap is None else int(gap), round(j.progress * 100))

    def _status_in(self, s, sid=None):
        """The partner's word on their game's own co-driver ('1' off, '0' on, '-' can't be told) and, from the driver,
        their stage (status_line)."""
        s = s if isinstance(s, str) else s.decode('ascii', 'replace')
        self.partner_off = {'1': True, '0': False}.get(s[:1])
        parts = s.split('|')
        if len(parts) >= 5:
            try:
                self.driver_state = {'state': parts[1], 'ms': int(parts[2]), 'gap': int(parts[3]) if parts[3] else None,
                                     'pct': int(parts[4]), 'at': time.monotonic()}
            except ValueError:
                pass

    def _lobby_in(self, l, lid=None):
        self._polling = False
        if lid is not None and (self.lobby or {}).get('id') != lid:
            return                                     # (an answer for a lobby I have left since: never brings it back)
        self._take_lobby(l)

    def _lobby_failed(self, e, lid=None):
        self._polling = False
        if lid is not None and (self.lobby or {}).get('id') != lid:
            return                                     # (the old lobby's 404 must not end the new one)
        if getattr(e, 'code', None) == 404:            # (gone: closed, or not mine any more)
            self._take_lobby(None)

    def _take_lobby(self, l):
        was = self.lobby
        self.lobby = l
        if was and l and l.get('id') != was.get('id') and self.crew is not None:
            self.stop_link()                           # (another lobby: the old one's links and voice are not its)
        if not l or l.get('state') not in ('open', 'started'):
            if was and (not l or l.get('id') == was.get('id')):
                self._ended(l or was)
            return
        if l.get('notes') is not None and l.get('notes') != self.notes:
            self.notes = l['notes']
        self._lobby_link(l)
        self._signals_in(l)
        if l.get('state') == 'started' and self.started_id != l.get('id'):
            # (the start seen here, the lobby open a moment ago: set up at once; else by its age, the PC's clock against the
            # server's: a clock more than RESUME_S ahead would otherwise never start the stage by itself)
            seen_open = bool(was and was.get('id') == l.get('id') and was.get('state') == 'open')
            fresh = seen_open or time.time() * 1000 - (l.get('started') or 0) < RESUME_S * 1000
            if fresh:
                self.go()

    def _lobby_link(self, l):
        """The voice in the lobby already, as CASUAL has it (the user, 27 Nov 2026: 'no microphone in the CODRIVER daily
        lobby'): the link made once the partner is in, closed when they leave before the start."""
        if self.peers():
            self.start_link()
            if self.crew is not None:
                self.crew.sync(self.peers())
        elif self.crew is not None and l.get('state') == 'open':
            self.stop_link()                           # (the partner left the lobby: nobody to talk to)

    def host_left(self, l):
        """The lobby over because its driver went (a DNF 'the driver left', or closed before the start), seen by the
        co-driver."""
        l = l or {}
        res = l.get('result') or {}
        return l.get('myRole') == 'codriver' and (res.get('reason') == 'the driver left' or l.get('state') == 'closed')

    def leave_stage(self, why):
        """Everyone back to the lobbies (the user, 26 Nov 2026: 'if the leader leaves, everyone else also leave'): WATCH
        over, the game back to its main menu from the stage (the mod's 'menu': its own ExitToMain), ACR DAILY's
        CODRIVER page on the lobbies, saying why."""
        a = self.app
        self.msg = why
        w = getattr(a, 'watch', None)
        if w is not None and w.on and w.copilot():
            w.stop()
        ig = getattr(a, 'ingame_app', None)
        on_stage = getattr(a, '_on_stage', lambda: False)()
        if ig is not None and on_stage and isinstance(getattr(ig, 'cmd', None), dict):
            ig.cmd = {'n': ig.cmd['n'] + 1, 'do': 'menu'}
        if ig is not None and hasattr(ig, 'mem'):
            ig.mem('copilot')['mode'] = self.MODE
            ig.mem('copilot')['mode_set'] = True

    def _ended(self, l):
        """The lobby over (finished, a DNF, closed): its link and voice gone, the day again (the stage revealed)."""
        if self.host_left(l):
            self.leave_stage(_('Your driver left: back to the lobbies.'))
        res = (l or {}).get('result')
        if res and (l or {}).get('myRole') == 'codriver':       # (the driver's app says its own: on_result)
            from .judge import fmt_ms
            self.final = (_('CODRIVER: your crew finished in %s.') % fmt_ms(res['totalMs']) if res.get('status') == 'finished'
                          and res.get('totalMs') else _('CODRIVER: your crew did not finish.'))
        self.stop_link()
        self.app.root.after(1500, lambda: self.refresh(force=True))
        tt = getattr(self.app, 'tt', None) or {}
        t = tt.get(self.SLOT)
        if t and not (t.get('judge') and t['judge'].state == 'running') and not str((t.get('ch') or {}).get('id', '')).startswith('cx:'):
            del tt[self.SLOT]                           # (not CASUAL's stage: its mode ends it, casual.py)
        w = getattr(self.app, 'watch', None)
        if w is not None and w.on and w.copilot() and (l or {}).get('state') in ('finished', 'dnf', 'closed'):
            pass                                        # (the co-driver sees the finish: WATCH ends as they leave the stage)

    # ---- the buttons
    OTHER = 'casual'                 # (the other mode: one lobby at a time, either mode: the stage's slot, the relay's room)

    def _guard_other_mode(self):
        o = getattr(self.app, self.OTHER, None)
        if o is not None and o is not self and (o.lobby or {}).get('state') in ('open', 'started'):
            self.msg = (_('Leave your CASUAL lobby first.') if self.OTHER == 'casual'
                        else _('Leave your CODRIVER DAILY lobby first.'))
            return False
        return True

    def create(self, role, private=False, langs=None):
        if self._guard_other_mode():
            self._bg(lambda: self.app.api.copilot_create(role, private, langs), lambda r: self._take_lobby(r.get('lobby')))

    def join(self, lobby_id=None, code=None):
        if self._guard_other_mode():
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
        a.tt[self.SLOT] = {'ch': ch, 'judge': judge, 'board': None, 'ghost_for': None, 'ghost_name': None,
                           'ghosts': GhostSet(judge.route, 0), 'ghost_loading': set(), 'copilot': True}
        self._apply_board(a.tt[self.SLOT])
        a._tt_drive_go(self.SLOT)

    def _watch(self, ch):
        a = self.app
        ig = getattr(a, 'ingame_app', None)
        from . import ig_watch, ingamedrive, saveslot
        from .judge import Judge
        driver = (self.partner() or {})
        held = {'ch': dict(ch, weekend=None), 'judge': Judge(ch) if ch.get('route') else None, 'live': [], 'board': None,
                'name': 'CODRIVER', 'eventId': self.room_id(), 'kind': 'copilot', 'cars': []}
        self.watch_held = held
        self._apply_board(held)          # (the daily's: the leader's splits for the gap; CASUAL has no board)
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
    def peers(self):
        """The others in my lobby as (steam id, seat): the partner (seat 0 the driver, 1 the co-driver)."""
        p = self.partner() or {}
        return [(p['steamId'], 0 if p.get('role') == 'driver' else 1)] if p.get('steamId') else []

    def my_seat(self):
        return 0 if self.role() == 'driver' else 1

    def speakers(self):
        """The speaker icons' data: [(name, seat, talking now)], the partner, then me (seat 'me')."""
        v = self.voice
        now = v.speaking() if v is not None else set()
        p = self.partner() or {}
        seat = 0 if p.get('role') == 'driver' else 1
        out = [(p.get('name') or '?', seat, seat in now)] if p else []
        out.append((_('You'), 'me', 'me' in now))
        return out

    def _publish(self, lid, sid, data):
        """My link details to a member of the lobby (copilotlink: the lobby's signal)."""
        self.app.api.copilot_signal(lid, data)

    def _signals_in(self, l):
        """The others' link details the lobby carries for me."""
        if self.crew is not None and l.get('signal'):
            sid = (self.partner() or {}).get('steamId')
            if sid:
                self.crew.signals({sid: l['signal']})

    def voice_args(self):
        c = settings_of(self.app.s)
        return dict(held=self._held, mode=c['talk'], gain=c['gain'], radio=c['radio'], mic_name=c['mic'],
                    mic_gain=c['micgain'])

    def start_link(self):
        if self.crew is not None:
            return
        l = self.lobby or {}
        lid = l.get('id')
        if not lid:
            return
        from .crew import Crew
        self.partner_off, self._partner_on_at, self._codriver_on_at = None, None, None   # (not the last lobby's partner's word)
        self.crew = Crew(self.app, self.my_seat(), self.role() == 'driver', lambda sid, d: self._publish(lid, sid, d),
                         self.peers(), self.voice_args(), on_status=lambda sid, s: self._status_in(s, sid))
        self._signals_in(l)

    def stop_link(self):
        if self.crew is not None:
            self.crew.close()
        self.crew = None
        self.driver_state = None
        self.partner_off, self._partner_on_at = None, None

    def voices(self):
        """Every voice that is on (this mode's and the other's): the settings change them all."""
        out = [self.voice]
        for name in ('copilot', 'casual'):
            o = getattr(self.app, name, None)
            if o is not None and o is not self:
                out.append(o.voice)
        return [v for v in out if v is not None]

    def set_radio(self, on):
        """The partner's voice through the rally intercom, or as it is."""
        c = settings_of(self.app.s)
        c['radio'] = bool(on)
        from . import settings
        settings.save(self.app.s)
        for v in self.voices():
            v.radio = bool(on)

    def set_talk(self, mode):
        c = settings_of(self.app.s)
        if mode in TALK_MODES:
            c['talk'] = mode
            from . import settings
            settings.save(self.app.s)
            for v in self.voices():
                v.mode = mode

    def mics(self):
        """The microphones Windows has: ['' (the default one), names...]."""
        from .voice import mic_devices
        return [''] + mic_devices()

    def set_mic(self, name):
        """Another microphone (its name; '' the default one): kept; used from the next lobby (or the test's restart)."""
        c = settings_of(self.app.s)
        c['mic'] = name or ''
        from . import settings
        settings.save(self.app.s)
        if self.mic_test is not None:
            self.test_mic(False)
            self.test_mic(True)

    def next_mic(self):
        names = self.mics()
        c = settings_of(self.app.s)
        self.set_mic(names[(names.index(c['mic']) + 1) % len(names)] if c['mic'] in names else '')

    def set_mic_gain(self, gain):
        """How loud my voice goes out (0.25 to 4)."""
        c = settings_of(self.app.s)
        c['micgain'] = max(0.25, min(4.0, round(float(gain), 2)))
        from . import settings
        settings.save(self.app.s)
        for v in self.voices():
            v.mic_gain = c['micgain']
        if self.mic_test is not None:
            self.mic_test.gain = c['micgain']

    def test_mic(self, on=True):
        """The settings' level meter: the microphone alone (not while a crew's voice has it)."""
        if not on:
            if self.mic_test is not None:
                self.mic_test.close()
            self.mic_test = None
            return
        if self.voices() or self.mic_test is not None:       # (a crew's voice of either mode has the microphone)
            return
        from .voice import MicTest
        c = settings_of(self.app.s)
        self.mic_test = MicTest(c['mic'], c['micgain'])

    def mic_level(self):
        """The microphone's level now, 0..1 (the crew's voice, or the test's), or None when neither is on."""
        vs = self.voices()
        if vs:
            return vs[0].level
        return self.mic_test.level if self.mic_test is not None else None

    def speaking(self):
        """Who is talking now, by name: ['you', 'Anna'...] (the speaker icons)."""
        v = self.voice
        if v is None:
            return []
        names = {}
        for m in (self.lobby or {}).get('members') or []:
            names[m.get('seat')] = m.get('name') or '?'
        for p in (self.lobby or {}).get('host'), (self.lobby or {}).get('guest'):
            if p:
                names.setdefault(0 if p.get('role') == 'driver' else 1, p.get('name') or '?')
        out = []
        for s in sorted(v.speaking(), key=lambda x: (x == 'me', x if x != 'me' else 0)):
            out.append(_('You') if s == 'me' else names.get(s, '?'))
        return out
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
        """How the crew is linked, for the page: 'DIRECT · 23 MS', 'THROUGH THE RELAY', 'CONNECTING…' (several: the worst)."""
        if self.crew is None or not self.crew.links:
            return ''
        modes = self.crew.modes()
        if all(m == 'direct' for m in modes):
            rtts = [l.rtt_ms for l in self.crew.links.values() if l.rtt_ms is not None]
            return _('DIRECT · %d MS') % round(max(rtts)) if rtts else _('DIRECT')
        if 'connecting' in modes or 'none' in modes:
            return _('CONNECTING…')
        return _('THROUGH THE RELAY')

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
        now = time.monotonic()
        running = j.state == 'running'
        # mine, and my co-driver's (their app tells it over the link: their game calling the notes to them is as bad)
        self._codriver_on_at = (self._codriver_on_at or now) if running and off is False else None
        self._partner_on_at = (self._partner_on_at or now) if running and self.partner_off is False else None
        from . import waiting
        from .i18n import said
        if self._codriver_on_at is not None and now - self._codriver_on_at >= CODRIVER_ON_DNF_S:
            waiting.note('%s: the game\'s own co-driver on during the stage (DNF)' % (j.ch.get('id') or 'copilot'))
            return j.disqualify(said("the game's own co-driver was on during the stage"))
        if self._partner_on_at is not None and now - self._partner_on_at >= CODRIVER_ON_DNF_S:
            waiting.note('%s: the co-driver\'s game had its own co-driver on (DNF)' % (j.ch.get('id') or 'copilot'))
            return j.disqualify(said("your co-driver's game had its own co-driver on"))
        return []

    def on_result(self, result):
        """The driver's run with the game's official result (or a DNF): to the server, as the crew's."""
        a = self.app
        if not a.api.configured or not a.s.get('token'):
            self.final = _('CODRIVER: not sent: sign in with Steam.')
            return
        from . import __version__

        def go():
            try:
                r = a.api._req('POST', '/api/copilot/runs', dict(result, appVersion=__version__), auth=True)
                text = (_('CODRIVER: P%s of %s crews. The stage is revealed.') % (r.get('rank'), r.get('drivers'))
                        if r.get('status') == 'finished' and r.get('rank') else _('CODRIVER: DNF. The stage is revealed.'))
                said = (_('P%s OF %s CREWS') % (r.get('rank'), r.get('drivers'))
                        if r.get('status') == 'finished' and r.get('rank') else _('CREW DNF'))
            except Exception as e:
                text, said = _('CODRIVER: not sent: %s') % e, _('NOT SENT')
            def shown():
                t = (getattr(a, 'tt', None) or {}).get(self.SLOT)
                if t is not None:
                    t['said'] = said                 # (the timer's line under the finish time)
                self.final = text
                a.sub_l.configure(text=text)
                self.refresh(force=True)
            a.root.after(0, shown)
        threading.Thread(target=go, daemon=True).start()
