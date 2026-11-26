"""REPLAYS in the app (replays.py has what a replay is): the recorder fed every frame, told by the judges what each run
is and how it ended; and what the server wants back (GET /api/replays/wanted, server src/replays.js): the replay of a
DNF it may take back (sent by itself: the DNF is gone a moment later, the rally goes on), and the stewards' requests
(sent by itself, or asked first: settings 'replays' 'send')."""
import threading
import time

from . import __version__, replays, waiting
from .i18n import _

POLL_S = 600.0                    # the server asked what it wants this often
AFTER_RUN_S = (40.0, 150.0, 400.0)  # ... and this long after a counted run ended (its DNF, if any, is in by then)


class ReplayUI:
    replays = None                # the Recorder (replays.py)
    replay_asks = ()              # the stewards' requests waiting for the driver's yes ('send': 'ask'): [wanted dict]
    replay_note = ''              # the last word on a replay sent (the REPLAY page shows it)
    _replay_polling = False       # (class defaults: the tests build bare apps, _replay_init never run)

    def _replay_init(self):
        from . import ingamedrive
        self.replays = replays.Recorder(self.s, self.api, me=lambda: {'steamId': self.s.get('steamId'), 'name': self.s.get('name')},
                                        app_version=__version__, penalty=self._live_penalty,
                                        damage=ingamedrive.read_damage)   # (the car at the finish line: the mod's)
        self.replays.on_saved = self._replay_saved
        self.replay_asks = []
        self._replay_polling = False
        try:
            name = replays.recover(replays.opts(self.s)['keep'])
            if name:
                waiting.note('replays: a run the app was recording when it closed kept as %s' % name)
        except Exception:
            pass
        self.root.after(20000, self._replay_tick)

    def _replay_feed(self, f, now):
        if self.replays is not None:
            try:
                self.replays.feed(f, now)
            except Exception:
                import traceback
                traceback.print_exc()

    # ---- what the judges say
    def _replay_tag(self, kind, ref, title, counted, **extra):
        """extra: stageId, carId (the game's: the replay set up in the game later), weather, startSeconds."""
        if self.replays is not None:
            self.replays.tag(kind, ref, title, counted, **{k: v for k, v in extra.items() if v is not None})

    def _replay_end(self, status, result, reason=None):
        if self.replays is None:
            return
        pen = None
        try:
            p = self._live_penalty()
            pen = p[0] if p else None
        except Exception:
            pass
        self.replays.outcome(status, result, pen, reason)
        if self.replays.run and self.replays.run.get('live'):
            for s in AFTER_RUN_S:             # (the DNF the server may take back: asked about soon after)
                self.root.after(int(s * 1000), self._replay_poll)

    def _replay_saved(self, name, doc):
        waiting.note('replays: kept %s (%s, %d rows%s)' % (name, doc['head'].get('status'), len(doc['rows']),
                                                          ', followed by the server' if doc.get('live') else ''))

    # ---- what the server wants
    def _replay_tick(self):
        self._replay_poll()
        self.root.after(int(POLL_S * 1000), self._replay_tick)

    def _replay_poll(self):
        if self._replay_polling or not self.s.get('token') or not self.api.configured:
            return
        self._replay_polling = True
        threading.Thread(target=self._replay_poll_bg, daemon=True).start()

    def _replay_poll_bg(self):
        try:
            # (first what the server missed: commits of runs driven while the connection was down, sent from their files,
            # then what it wants: a DNF's proof needs its finish on the server)
            try:
                n = replays.catch_up(self.api, skip=set(getattr(self.replays, 'saved', ()) or ()))
                if n:
                    waiting.note('replays: %d replays brought up to date on the server' % n)
            except Exception:
                pass
            try:
                want = self.api.replays_wanted()
            except Exception:
                return
            asks = []
            for w in want:
                if w.get('why') == 'missing' and self._result_on_its_way(w.get('ref')):
                    continue                     # (its own result still queued here: that one, not the replay)
                name = find_local(w)
                if w.get('why') == 'steward':
                    if not name:
                        try:
                            self.api.replay_none(w['requestId'])
                        except Exception:
                            pass
                        continue
                    if replays.opts(self.s)['send'] == 'ask':
                        asks.append(dict(w, file=name))
                        continue
                if name:
                    self.replay_send(name, why=w.get('why'))
            self.replay_asks = asks
        finally:
            self._replay_polling = False

    def replay_send(self, name, public=False, why=None, done=None):
        """A kept replay uploaded (in this thread: call it from one of its own). -> the server's answer, or None. Its
        code, verdict and stamp kept with it; a DNF taken back said, and the events looked at again."""
        p = replays.path_of(name)
        if not p:
            return None
        try:
            with open(p, 'rb') as f:
                data = f.read()
            a = self.api.replay_upload(data, public)
        except Exception as e:
            self.replay_note = _('Replay not sent: %s') % e
            waiting.note('replays: %s not sent: %s' % (name, e))
            if done:
                self.root.after(0, lambda: done(None))
            return None
        try:
            doc = replays.read(p)
            if a.get('stamp'):
                doc['stamp'] = a['stamp']
                with open(p + '.tmp', 'wb') as f:
                    f.write(replays.dumps(doc))
                import os
                os.replace(p + '.tmp', p)
            replays.update(name, code=a.get('code'), verdict=a.get('verdict'), sent=int(time.time() * 1000),
                           public=bool(a.get('public')))
        except Exception:
            pass
        act = a.get('action') or ''
        waiting.note('replays: %s sent (%s): %s %s' % (name, why or 'by hand', a.get('verdict'), act))
        if act.startswith('DNF taken back') or act.startswith('SS'):
            self.replay_note = _('Your replay proved the finish: %s') % act

            def told():
                self._notify(True, _('DNF taken back'), act)
                self.sub_l.configure(text=_('Your replay proved the finish: %s') % act)
                for fn in ('refresh_leagues', 'refresh_challenge'):    # (the rally goes on: CONTINUE)
                    if hasattr(self, fn):
                        try:
                            getattr(self, fn)()
                        except Exception:
                            pass
            self.root.after(0, told)
        elif act:
            self.replay_note = _('Replay sent: %s') % act
        if done:
            self.root.after(0, lambda: done(a))
        return a

    def _result_on_its_way(self, ref):
        """Is this run's own result still on this PC, to be sent (the runs' queue, the leagues' queue, a finish still
        waiting for the game's official time)? Then a replay never stands in for it."""
        ref = str(ref or '')
        try:
            for body in self.api._pending():
                if str(body.get('challengeId') or '') == ref:
                    return True
        except Exception:
            pass
        m = ref.split(':')
        if len(m) == 3 and m[0] == 'event':
            try:
                from . import leagues
                for it in leagues.pending():
                    if str(it.get('eventId')) == m[1] and str(it.get('no')) == m[2]:
                        return True
            except Exception:
                pass
        try:
            for a in waiting.load():
                if ref and (str(a.get('id') or '').startswith(ref) or str((a.get('result') or {}).get('challengeId') or '') == ref
                            or (len(m) == 3 and str(a.get('eventId')) == m[1] and str(a.get('no')) == m[2])):
                    return True
        except Exception:
            pass
        return False

    def replay_answer(self, w, send):
        """A steward's request answered by the driver (REPLAY: SEND / NO)."""
        self.replay_asks = [x for x in self.replay_asks if x is not w]

        def go():
            if send and w.get('file'):
                self.replay_send(w['file'], why='steward')
            elif w.get('requestId'):
                try:
                    self.api.replay_none(w['requestId'])
                except Exception:
                    pass
        threading.Thread(target=go, daemon=True).start()

    def _replay_close(self):
        if self.replays is not None:
            self.replays.finish()


def find_local(w):
    """A wanted replay on this PC: its run id's, else (a steward's request) the first kept of that stage."""
    rows = replays.index()
    if w.get('rid'):
        hit = next((r for r in rows if r.get('rid') == w['rid']), None)
        if hit:
            return hit['file']
    ref = w.get('ref')
    mine = [r for r in rows if r.get('ref') == ref and r.get('mine', True)]
    mine.sort(key=lambda r: r.get('created') or 0)
    live = [r for r in mine if r.get('rid')]
    return (live or mine or [{}])[0].get('file')
