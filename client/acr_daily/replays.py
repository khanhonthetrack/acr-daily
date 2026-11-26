"""REPLAYS: every run kept on this PC as a replay, watched again in the game, sent to others, and a proof of a finish
the game lost (the user, 26 Nov 2026: "after every run, a replay is saved ... a league admin may want to verify that
users did not do anything malicious, or not cut ... if you do send such a replay - it is a proof that user drove the
stage. This may allow to cancel DNF, basically automatically").

What a replay is: the car on the stage, 10 times a second of its stage clock (position, heading / pitch / roll, speed,
gear, revs, pedals, steering), from the game's telemetry as the app reads it (telemetry.py, 20 a second: app._tick).
Not the game's own replay: that one lives only in the game's memory, has no way to save it in the menus and only the
game can read it. This one the app plays back in the game as WATCH plays the live drivers (a real car moved by the mod,
the TV director's cameras: replayplay.py), and the website draws it on the stage's map (/r/<code>).

The file (<APPDATA>/ACR Daily/replays/*.acrreplay): gzip'd JSON {format, v, head, cols, rows, live, sig, stamp}.
  head   what it is: driver, kind (daily / event / tt / practice), ref, track, car, status, clock and penalty...
  rows   [clockMs, x cm, y cm, z cm, heading, pitch, roll (1e-4 rad), km/h x10, gear, rpm, throttle, brake (0-1000),
          steering (-1000..1000), airborne (0/1)], every ROW_MS of stage clock
  live   the server's part, when the run counted (kind daily / event, signed in): {rid, nonce, commits: [[count, hash]]}.
         At the start the server gives the run an id and a nonce (POST /api/replays/begin); every COMMIT_S while the
         stage runs, and at the finish line, the app sends the hash of the rows so far, chained from the nonce
         (POST /api/replays/commit). The server keeps each with ITS clock. So the rows existed at those moments: driven
         as the stage ran, not made afterwards, not sped up (the server checks the clock in them against its own).
  sig    the app's own Ed25519 key (made once on this PC, its public half told to the server with the first begin):
         the file comes from this driver's app, unchanged since (anyone can check it, offline too).
  stamp  the server's word once it checked an uploaded replay: {code, verdict, at, mac} (GET /api/replays/<code>).

What the server does with an uploaded replay (server/src/replays.js): the chain against its commits, the signature,
the rows against the stage's road (left it, cut it, a car faster than a car can be), the finish in it. A daily's DNF
whose result the game lost, or an online rally's DNF on that stage, is taken back on its own when the replay shows the
finish, clean; anything else goes to the admin / the stewards with the replay to watch.

Kept: the newest KEEP (settings 'replays': {'on', 'keep', 'send'}), a starred one never dropped."""
import gzip
import hashlib
import json
import os
import queue
import re
import secrets
import threading
import time

from . import ed25519, settings

FORMAT, VERSION = 'acr-replay', 1
EXT = '.acrreplay'
COLS = ('ms', 'x', 'y', 'z', 'h', 'p', 'r', 'kmh10', 'gear', 'rpm', 'gas', 'brake', 'steer', 'air')
ROW_MS = 100                   # a row every 100 ms of stage clock (WATCH plays the live drivers on a 100 ms grid too)
COMMIT_S = 10.0                # the chain's hash to the server this often while the stage runs
PART_S = 5.0                   # the rows so far on disk this often (an app closed mid-stage keeps them: recover())
AFTER_S = 3.0                  # rows kept this long after the run's end (the car rolling past the finish line)
PENALTY_S = 45.0               # the replay kept open this long after the end, the game's penalties read in meanwhile
NEW_RUN_BACK_MS = 500          # the clock gone back this far: a new run
KEEP_DEFAULT = 100
KEEP_MIN, KEEP_MAX = 10, 1000
MAX_ROWS = 4 * 3600 * 1000 // ROW_MS
KINDS_LIVE = ('daily', 'event')   # the runs the server follows (a proof of their finish)


def opts(s):
    """The replay settings: {'on' bool, 'keep' int, 'send' 'auto' / 'ask'} ('send': a steward's request answered by
    itself or asked first)."""
    r = s.get('replays') if isinstance(s.get('replays'), dict) else {}
    keep = r.get('keep', KEEP_DEFAULT)
    try:
        keep = max(KEEP_MIN, min(KEEP_MAX, int(keep)))
    except (TypeError, ValueError):
        keep = KEEP_DEFAULT
    return {'on': r.get('on', True) is not False, 'keep': keep, 'send': 'ask' if r.get('send') == 'ask' else 'auto'}


def folder():
    return os.path.join(settings.DIR, 'replays')


# ------------------------------------------------------------------ the format

def row_of(f):
    """A telemetry frame -> one row (ints only: the chain hashes their JSON, the same in Python and on the server)."""
    g = lambda k: getattr(f, k, 0) or 0              # noqa: E731
    q = lambda v, lo, hi: max(lo, min(hi, int(round(v))))   # noqa: E731
    return [int(f.clock_ms), int(round(f.x * 100)), int(round(f.y * 100)), int(round(f.z * 100)),
            int(round(g('heading') * 10000)), int(round(g('pitch') * 10000)), int(round(g('roll') * 10000)),
            q(g('speed') * 10, 0, 9999), q(g('gear'), 0, 20), q(g('rpm'), 0, 30000),
            q(g('gas') * 1000, 0, 1000), q(g('brake') * 1000, 0, 1000), q(g('steer') * 1000, -1000, 1000),
            1 if g('airborne') else 0]


def row_text(row):
    return json.dumps([int(v) for v in row], separators=(',', ':'))


def canon(obj):
    """The head as signed: sorted keys, no spaces, non-ASCII escaped (the server's canon() makes the same text)."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def chain_start(rid, nonce):
    return hashlib.sha256(('acr-replay-chain|%s|%s' % (rid, nonce)).encode('ascii')).hexdigest()


def chain_next(h, rows):
    """The chain's next hash: the one before and the rows since (their JSON, one a line)."""
    return hashlib.sha256((h + '\n' + '\n'.join(row_text(r) for r in rows)).encode('ascii')).hexdigest()


def rows_hash(rows):
    return hashlib.sha256('\n'.join(row_text(r) for r in rows).encode('ascii')).hexdigest()


def digest(head, rows, rid=None):
    """What the device key signs: the head, the rows and the server's run id, in one hash."""
    text = 'acr-replay/1\n%s\n%s\n%s' % (canon(head), rows_hash(rows), rid or '')
    return hashlib.sha256(text.encode('ascii')).digest()


def clean_head(h):
    """Only strings, ints, bools and None in the head (a float prints differently in Python and JavaScript)."""
    out = {}
    for k, v in h.items():
        if isinstance(v, float):
            v = int(round(v))
        if v is None or isinstance(v, (bool, int, str)):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = clean_head(v)
    return out


def dumps(doc):
    return gzip.compress(json.dumps(doc, separators=(',', ':')).encode('utf-8'), 6)


def loads(data):
    """File bytes -> the replay dict; ValueError when it is not one."""
    try:
        raw = gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data
        doc = json.loads(raw.decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError, EOFError) as e:
        raise ValueError('not a replay file') from e
    if not isinstance(doc, dict) or doc.get('format') != FORMAT or not isinstance(doc.get('rows'), list) \
            or not isinstance(doc.get('head'), dict):
        raise ValueError('not a replay file')
    if int(doc.get('v') or 0) > VERSION:
        raise ValueError('a replay from a newer ACR DAILY: update the app')
    return doc


def read(path):
    with open(path, 'rb') as f:
        return loads(f.read())


# ------------------------------------------------------------------ the device key

def _key_file():
    return os.path.join(settings.DIR, 'replay-key.json')


_key = None


def device_key():
    """(seed, public key) of this PC's replay key, made once (replay-key.json; never sent anywhere: only its public half)."""
    global _key
    if _key is not None:
        return _key
    try:
        with open(_key_file(), encoding='utf-8') as f:
            seed = bytes.fromhex(json.load(f)['seed'])
        _key = ed25519.keypair(seed)
        return _key
    except (OSError, ValueError, KeyError, TypeError):
        pass
    seed = secrets.token_bytes(32)
    _key = ed25519.keypair(seed)
    try:
        os.makedirs(settings.DIR, exist_ok=True)
        tmp = _key_file() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'seed': seed.hex(), 'public': _key[1].hex(),
                       'note': "ACR DAILY's replay key for this PC: it signs your replays. Keep it private."}, f, indent=1)
        os.replace(tmp, _key_file())
    except OSError:
        pass
    return _key


def sign_doc(doc):
    seed, pub = device_key()
    rid = (doc.get('live') or {}).get('rid')
    doc['sig'] = {'alg': 'ed25519', 'key': pub.hex(),
                  'sig': ed25519.sign(seed, digest(doc['head'], doc['rows'], rid)).hex()}
    return doc


def check(doc):
    """What can be told about a replay here, without the server: {'signed': bool (signed and unchanged since),
    'key': hex or None, 'live': bool (the server followed it), 'chain': bool or None (its rows match its commits),
    'stamp': the server's stamp or None}."""
    out = {'signed': False, 'key': None, 'live': False, 'chain': None, 'stamp': doc.get('stamp') or None}
    live = doc.get('live') or {}
    sig = doc.get('sig') or {}
    try:
        key, s = bytes.fromhex(sig.get('key') or ''), bytes.fromhex(sig.get('sig') or '')
        out['key'] = sig.get('key')
        out['signed'] = ed25519.verify(key, digest(doc['head'], doc['rows'], live.get('rid')), s)
    except (ValueError, TypeError, KeyError):
        out['signed'] = False
    if live.get('rid') and live.get('nonce') and isinstance(live.get('commits'), list):
        out['live'] = True
        try:
            h, at = chain_start(live['rid'], live['nonce']), 0
            ok = True
            for count, want in live['commits']:
                count = int(count)
                if count < at or count > len(doc['rows']):
                    ok = False
                    break
                h = chain_next(h, doc['rows'][at:count])
                at = count
                if h != want:
                    ok = False
                    break
            out['chain'] = ok
        except (TypeError, ValueError):
            out['chain'] = False
    return out


# ------------------------------------------------------------------ the store

_INDEX = 'index.json'
_lock = threading.RLock()


def _index_path():
    return os.path.join(folder(), _INDEX)


def summary(doc, name):
    h = doc['head']
    return {'file': name, 'created': h.get('created'), 'kind': h.get('kind'), 'ref': h.get('ref'),
            'title': h.get('title'), 'track': h.get('track'), 'car': h.get('car'), 'status': h.get('status'),
            'reason': h.get('reason'), 'clockMs': h.get('clockMs'), 'penaltyMs': h.get('penaltyMs'),
            'totalMs': h.get('totalMs'), 'driver': (h.get('driver') or {}).get('name'),
            'rid': (doc.get('live') or {}).get('rid'), 'live': bool((doc.get('live') or {}).get('commits')),
            'code': (doc.get('stamp') or {}).get('code'), 'verdict': (doc.get('stamp') or {}).get('verdict'),
            'mine': True, 'star': False, 'sent': None}


def index():
    """The kept replays, newest first: [summary()] (index.json, made again from the files if it is gone)."""
    with _lock:
        try:
            with open(_index_path(), encoding='utf-8') as f:
                rows = json.load(f)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict) and os.path.exists(os.path.join(folder(), r.get('file', '')))]
        except (OSError, ValueError):
            pass
        rows = []
        for name in sorted(os.listdir(folder()) if os.path.isdir(folder()) else [], reverse=True):
            if name.endswith(EXT):
                try:
                    rows.append(summary(read(os.path.join(folder(), name)), name))
                except (OSError, ValueError):
                    continue
        rows.sort(key=lambda r: -(r.get('created') or 0))
        _write_index(rows)
        return rows


def _write_index(rows):
    os.makedirs(folder(), exist_ok=True)
    tmp = _index_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=0)
    os.replace(tmp, _index_path())


def update(name, **kw):
    """One kept replay's line changed (star, sent, code, verdict)."""
    with _lock:
        rows = index()
        for r in rows:
            if r.get('file') == name:
                r.update(kw)
        _write_index(rows)


def path_of(name):
    p = os.path.join(folder(), os.path.basename(name or ''))
    return p if p.endswith(EXT) and os.path.exists(p) else None


def file_name(head):
    t = time.strftime('%Y-%m-%d_%H%M%S', time.localtime((head.get('created') or 0) / 1000.0))
    what = re.sub(r'[^A-Za-z0-9]+', '-', '%s %s' % (head.get('kind') or 'run', head.get('track') or '')).strip('-')[:60]
    return '%s_%s%s' % (t, what or 'run', EXT)


def save(doc, keep=KEEP_DEFAULT, name=None, mine=True):
    """A replay into the store, the oldest of this PC's own past `keep` dropped (a starred one, or one someone sent,
    never). -> its file name."""
    with _lock:
        os.makedirs(folder(), exist_ok=True)
        name = name or file_name(doc['head'])
        base, n = name[:-len(EXT)], 1
        while os.path.exists(os.path.join(folder(), name)):
            n += 1
            name = '%s-%d%s' % (base, n, EXT)
        tmp = os.path.join(folder(), name + '.tmp')
        with open(tmp, 'wb') as f:
            f.write(dumps(doc))
        os.replace(tmp, os.path.join(folder(), name))
        rows = [r for r in index() if r.get('file') != name]
        rows.insert(0, dict(summary(doc, name), mine=mine, star=not mine))
        rows.sort(key=lambda r: -(r.get('created') or 0))
        own = [r for r in rows if not r.get('star') and r.get('mine', True)]
        for r in own[keep:]:
            try:
                os.remove(os.path.join(folder(), r['file']))
            except OSError:
                pass
            rows.remove(r)
        _write_index(rows)
        return name


def import_file(path, keep=KEEP_DEFAULT):
    """A replay someone sent (a file): checked, kept with the others (as theirs: mine False). -> its file name."""
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('too big for a replay')
    doc = loads(data)
    return save(doc, keep, mine=False)    # (someone else's: kept until removed by hand)


def remove(name):
    with _lock:
        p = path_of(name)
        if p:
            try:
                os.remove(p)
            except OSError:
                pass
        _write_index([r for r in index() if r.get('file') != name])


# ------------------------------------------------------------------ the recorder

class Recorder:
    """Fed every frame the app reads (app._tick). A run starts when the stage clock starts and ends when the clock goes
    back (a restart), the stage or car changes, the game leaves the stage, or AFTER_S after the judge's word on it
    (outcome()). What it was (tag()) and how it ended (outcome()) come from the app's judges; a run nobody tagged is
    kept as practice.

    api: the app's Api (begin / commit, in a thread of their own), s: the settings dict, me: () -> {steamId, name}."""

    def __init__(self, s, api=None, me=None, app_version='', penalty=None):
        self.s, self.api, self.me = s, api, me or (lambda: {})
        self.app_version = app_version
        self.penalty_fn = penalty        # () -> (ms, dq) or None: the game's penalties as the mod reads them
        self.run = None
        self.saved = []                  # (file names saved this session, newest last: the app's notes)
        self.on_saved = None             # a function (name, doc) called on the main thread when one is kept
        self._q = queue.Queue(maxsize=500)
        self._worker = None
        self._chain_lock = threading.Lock()

    # ---- the app's judges say what the run is
    def tag(self, kind, ref=None, title=None, counted=False, **extra):
        r = self.run
        if r is None or r.get('tagged'):
            return
        r['tagged'] = True
        r['head'].update(clean_head(dict(extra, kind=kind, ref=ref, title=title, counted=bool(counted))))
        if counted and kind in KINDS_LIVE and ref and self.api is not None and self.s.get('token'):
            r['live'] = {'rid': None, 'nonce': None, 'commits': [], 'h': None, 'at': 0, 'pending': True}
            self._send('begin', r, {'kind': kind, 'ref': ref, 'track': r['head'].get('track'),
                                    'car': r['head'].get('car'), 'clockMs': r['rows'][-1][0] if r['rows'] else 0,
                                    'key': device_key()[1].hex()})

    def outcome(self, status, result=None, penalty_ms=None, reason=None):
        """The judge's word on the run: 'finished' / 'dnf' / 'invalid', its result (clockMs, resets, totalMs). The
        finish: the chain sent at once (the moment the line was crossed, on the server's clock)."""
        r = self.run
        if r is None or r.get('ended'):
            return
        res = result or {}
        r['ended'] = time.monotonic()
        clock = res.get('clockMs')
        r['head'].update(clean_head({'status': status, 'reason': reason or res.get('reason') or '',
                                     'clockMs': clock, 'resets': res.get('resets'), 'penaltyMs': penalty_ms,
                                     'totalMs': res.get('totalMs')}))
        if status == 'finished' and clock:
            r['head']['finMs'] = int(clock)
        self._commit(r, final=True)

    # ---- every frame
    def feed(self, f, now=None):
        now = time.monotonic() if now is None else now
        r = self.run
        on = opts(self.s)['on']
        track = getattr(f, 'track', None) if f is not None else None
        if r is not None:
            gone = (not track or track != r['head']['track'] or (getattr(f, 'car', None) and f.car != r['head']['car'])
                    or f.clock_ms < r['last'] - NEW_RUN_BACK_MS)
            # (kept open on the results screen: the game's penalties given there are read in, PENALTY_S at most; a
            # game frozen on its loading screen leaves its last frame in the telemetry for good)
            late = r.get('ended') and now - r['ended'] >= PENALTY_S
            if r.get('ended') and not gone and self.penalty_fn is not None and now - r.get('pen_at', 0) >= 1.0:
                r['pen_at'] = now
                try:
                    pen = self.penalty_fn()
                except Exception:
                    pen = None
                if pen is not None and pen[0] is not None:
                    r['head']['penaltyMs'] = int(pen[0])
                    if pen[1]:
                        r['head']['dq'] = True
            if gone or late or len(r['rows']) >= MAX_ROWS:
                self._close(r, 'left' if gone and not r.get('ended') else None)
                r = self.run = None
        if not on or not track or f.clock_ms is None or f.clock_ms <= 0:
            return
        if r is None:
            if f.clock_ms > 5000:         # (joined mid-run: an app started on a stage; no replay of half a stage)
                return
            me = self.me() or {}
            r = self.run = {
                'head': {'created': int(time.time() * 1000), 'app': 'ACR DAILY', 'appVersion': self.app_version,
                         'driver': clean_head({'steamId': me.get('steamId') or '', 'name': me.get('name') or ''}),
                         'track': track, 'car': getattr(f, 'car', '') or '', 'kind': 'practice', 'ref': None,
                         'status': 'ended', 'rowMs': ROW_MS},
                'rows': [], 'last': -ROW_MS, 'part_at': now, 'live': None}
        if f.clock_ms >= r['last'] + ROW_MS and not (r.get('ended') and now - r['ended'] >= AFTER_S):
            r['rows'].append(row_of(f))
            r['last'] = f.clock_ms
        if r.get('live') and now - r.setdefault('commit_at', now) >= COMMIT_S and not r.get('ended'):
            self._commit(r, now=now)
        if now - r['part_at'] >= PART_S:
            r['part_at'] = now
            self._part(r)

    # ---- the server's chain
    def _commit(self, r, final=False, now=None):
        with self._chain_lock:            # (the main thread's ticks and the worker's late begin)
            live = r.get('live')
            if not live or live.get('h') is None:
                if live and final:
                    live['final_wanted'] = True          # (the begin not answered yet: sent when it is)
                return
            r['commit_at'] = time.monotonic() if now is None else now
            n = len(r['rows'])
            if n <= live['at'] and not final:
                return
            live['h'] = chain_next(live['h'], r['rows'][live['at']:n])
            live['at'] = n
            live['commits'].append([n, live['h']])
            body = {'rid': live['rid'], 'n': len(live['commits']), 'count': n, 'hash': live['h'],
                    'clockMs': r['rows'][n - 1][0] if n else 0, 'fin': r['head'].get('finMs') if final else None}
        self._send('commit', r, body)

    def _send(self, what, r, body):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._work, daemon=True)
            self._worker.start()
        try:
            self._q.put_nowait((what, r, body))
        except queue.Full:
            pass

    def _work(self):
        while True:
            what, r, body = self._q.get()
            try:
                if what == 'begin':
                    a = self.api.replay_begin(body)
                    live = r.get('live')
                    if live is not None and a and a.get('rid') and a.get('nonce'):
                        # (on the main thread's data: one assignment each, the hash first set last)
                        live['rid'], live['nonce'] = str(a['rid']), str(a['nonce'])
                        live['h'] = chain_start(live['rid'], live['nonce'])
                        live['pending'] = False
                        if live.pop('final_wanted', False) or r.get('closed'):
                            self._commit(r, final=True)
                    elif live is not None:
                        r['live'] = None
                elif what == 'commit':
                    self.api.replay_commit(body)
            except Exception:
                if what == 'begin':
                    r['live'] = None              # (not followed by the server: kept on this PC all the same)

    # ---- kept
    def _part(self, r):
        try:
            os.makedirs(folder(), exist_ok=True)
            with open(os.path.join(folder(), 'recording.part'), 'w', encoding='utf-8') as fh:
                json.dump({'head': r['head'], 'rows': r['rows'], 'live': self._live_out(r)}, fh,
                          separators=(',', ':'))
        except OSError:
            pass

    @staticmethod
    def _live_out(r):
        live = r.get('live')
        if not live or not live.get('rid'):
            return None
        return {'rid': live['rid'], 'nonce': live['nonce'], 'commits': [list(c) for c in live['commits']]}

    def _close(self, r, why=None):
        r['closed'] = True
        if why and r['head'].get('status') == 'ended':
            r['head']['reason'] = why
        if len(r['rows']) < 20:           # (under 2 s of stage clock: a start and straight out again)
            self._drop_part()
            return
        doc = self.build(r)
        try:
            name = save(doc, opts(self.s)['keep'])
        except OSError:
            return
        self._drop_part()
        self.saved.append(name)
        fn = self.on_saved
        if fn is not None:
            try:
                fn(name, doc)
            except Exception:
                pass

    def build(self, r):
        doc = {'format': FORMAT, 'v': VERSION, 'head': clean_head(r['head']), 'cols': list(COLS), 'rows': r['rows'],
               'live': self._live_out(r)}
        return sign_doc(doc)

    def finish(self):
        """The app closing: the run under way kept as it is."""
        if self.run is not None:
            self._close(self.run, 'app closed')
            self.run = None

    @staticmethod
    def _drop_part():
        try:
            os.remove(os.path.join(folder(), 'recording.part'))
        except OSError:
            pass


def recover(keep=KEEP_DEFAULT):
    """A run the app was recording when it closed or crashed (recording.part): kept as a replay, cut short. -> its
    file name or None."""
    p = os.path.join(folder(), 'recording.part')
    try:
        with open(p, encoding='utf-8') as f:
            part = json.load(f)
        os.remove(p)
    except (OSError, ValueError):
        return None
    if not isinstance(part, dict) or len(part.get('rows') or []) < 20:
        return None
    head = dict(part['head'])
    if head.get('status') == 'ended':
        head['reason'] = head.get('reason') or 'cut short: the app closed'
    doc = sign_doc({'format': FORMAT, 'v': VERSION, 'head': clean_head(head), 'cols': list(COLS),
                    'rows': part['rows'], 'live': part.get('live')})
    try:
        return save(doc, keep)
    except OSError:
        return None


# ------------------------------------------------------------------ what a replay says, for the pages

def fmt_ms(ms):
    if ms is None:
        return '-'
    ms = int(ms)
    m, s = divmod(ms // 1000, 60)
    return '%d:%02d.%03d' % (m, s, ms % 1000) if m < 60 else '%d:%02d:%02d.%03d' % (m // 60, m % 60, s, ms % 1000)


def stats(doc):
    """{'km': driven, 'top': top speed km/h, 'avg': average km/h, 'airborne': s in the air, 'ms': clock at its end}."""
    rows = doc.get('rows') or []
    if len(rows) < 2:
        return {'km': 0.0, 'top': 0.0, 'avg': 0.0, 'airborne': 0.0, 'ms': rows[-1][0] if rows else 0}
    d, top, air = 0.0, 0.0, 0
    for a, b in zip(rows, rows[1:]):
        step = ((b[1] - a[1]) ** 2 + (b[3] - a[3]) ** 2) ** 0.5 / 100.0
        if step < 60:                 # (a reset's jump left out)
            d += step
        top = max(top, b[7] / 10.0)
        air += b[13]
    ms = rows[-1][0] - rows[0][0]
    return {'km': d / 1000.0, 'top': top, 'avg': (d / 1000.0) / (ms / 3600000.0) if ms > 0 else 0.0,
            'airborne': air * ROW_MS / 1000.0, 'ms': rows[-1][0]}
