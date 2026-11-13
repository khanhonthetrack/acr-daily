"""The game's own log, sent to ACR Daily's admin when the game loses the official result of a finished run.

After a Rally Weekend stage the game writes its result into its save as the driver goes on from its results screen
(waiting.py). Some games never get there: stuck on a loading screen they are closed from the Task Manager (or crash),
and the run goes in as a DNF ("the game closed before saving its official result"). Nothing the app sees says why
(13 Nov 2026: the save untouched from 3 s after the finish until the game was closed 12 minutes later); the game's own
log may. Unreal writes what the game does to LOGS\\acr.log as it goes, and keeps the one before as
acr-backup-<when>.log when it starts again.

So when a wait for an official result ends without one (app.py _check_official, leagueui.py) the app files a bug report
for the driver, as the website's /report would (server/src/reports.js: the driver sees it and its status there, only
the admin opens its file): what the app saw (its notes on the run, official.log) and the log of that game session,
gzipped: its start (the game's version, Windows, the CPU and graphics card) and its end (what the game did last), with
the Windows user's and the PC's names taken out. One copy of a session's log is enough. Never raises.

The game's log is not there on players' PCs (13 Nov 2026: the first two reports found none), so the report also carries
what the app itself saw (gamewatch.py: whether the game left the stage, stopped responding, how its process ended),
Windows' own records of the game (the Application log's errors and hangs: the module that failed) and any crash report
the game left, in a diagnostics file attached to every such report; the body sums it up and says what is attached.
"""
import datetime
import gzip
import os
import platform
import re
import subprocess
import threading
import time

from . import __version__, gamewatch, settings, waiting
from .judge import fmt_ms

LOGS = os.path.join(os.environ.get('LOCALAPPDATA') or '', 'acr', 'Saved', 'Logs')
HEAD = 64 * 1024          # the log's start sent: the game's version and the PC (Unreal's start-up lines)
TAIL = 448 * 1024         # ... and its end: what the game did from about the finish on, up to where it stopped
NOTES_MAX = 2500          # characters of the app's notes in the report (the server takes 5000 in all)
BODY_MAX = 4900
AREAS = ('daily', 'time trial', 'league', '1v1', 'cup')               # (server/src/reports.js AREAS)
OPENED = re.compile(r'Log file open, (\d\d)/(\d\d)/(\d\d) (\d\d):(\d\d):(\d\d)')   # its first line: this PC's time
STAMP = re.compile(r'^\[(\d{4}\.\d\d\.\d\d-\d\d\.\d\d\.\d\d):\d{3}\]', re.M)      # a line's [2026.11.13-04.42.07:123]
CLOSED = 'Log file closed'                                            # its last line when the game quits the normal way
CRASH = re.compile(r'Critical error|Fatal error|Unhandled Exception')
SYSTEM = re.compile(r'LogInit: (?:Display: )?(OS: [^\r\n]{5,400})')   # "OS: Windows 11 (24H2) [...], CPU: ..., GPU: ..."
FOLDER = r'%LOCALAPPDATA%\acr\Saved\Logs'                             # (said in the report instead of the real path)
SAVED = os.path.dirname(LOGS)                                         # the game's Saved folder (Logs, Crashes)
EVENT_IDS = (1000, 1001, 1002)    # Windows' Application log: Application Error (a crash, the module that failed),
                                  # Windows Error Reporting, Application Hang
DIAG_MAX = 400 * 1024             # characters of the diagnostics file

_sent = {}                # the session (its start, or its log's path) -> the report its log went with
_lock = threading.Lock()


def _opened(path):
    """When the game session that wrote this log started (its first line, "Log file open, 11/13/26 13:30:00", this
    PC's time) -> unix time, or None."""
    try:
        with open(path, 'rb') as f:
            head = f.read(600)
    except OSError:
        return None
    text = head.decode('utf-16-le', 'ignore') if head[:2] == b'\xff\xfe' else head.decode('utf-8', 'ignore')
    m = OPENED.search(text)
    if not m:
        return None
    mo, d, y, hh, mm, ss = (int(x) for x in m.groups())
    try:
        return datetime.datetime(2000 + y, mo, d, hh, mm, ss).timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def session_log(since, folder=None):
    """The log of the game session a run was driven in, the stage clock starting at unix time `since`: of acr.log and
    the acr-backup-*.log the game keeps of its earlier sessions, the one that started last before it. Logs without a
    start line: the one last written soonest after it, else acr.log (the game not started again since). -> path or
    None."""
    folder = folder or LOGS
    try:
        paths = [os.path.join(folder, n) for n in os.listdir(folder)
                 if n.lower() == 'acr.log' or re.match(r'(?i)^acr-backup-.+\.log$', n)]
    except OSError:
        return None
    started = [(t, p) for t, p in ((_opened(p), p) for p in paths) if t is not None and t <= since + 5]
    if started:
        return max(started)[1]
    later = []
    for p in paths:
        try:
            m = os.stat(p).st_mtime
        except OSError:
            continue
        if m >= since:
            later.append((m, p))
    if later:
        return min(later)[1]
    current = os.path.join(folder, 'acr.log')
    return current if current in paths else None


def saved_folders(exe=None):
    """The game's Saved folders: under %LOCALAPPDATA%, and next to the game itself (acr\\Binaries\\Win64\\acr.exe ->
    acr\\Saved), where a game installed elsewhere may keep its logs and crash reports."""
    out = [SAVED]
    if exe:
        alt = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(exe))), 'Saved')
        if os.path.normcase(alt) != os.path.normcase(SAVED):
            out.append(alt)
    return out


def find_log(since, folders):
    """session_log() in the first of these Saved folders that has one. -> path or None."""
    for d in folders:
        p = session_log(since, os.path.join(d, 'Logs'))
        if p:
            return p
    return None


def windows_events(since, run=subprocess.run, now=time.time):
    """Windows' Application log entries about the game (errors, crash reports, hangs) since a minute before `since`, as
    text blocks, newest first (wevtutil, which any user may run). [] elsewhere or when it fails."""
    if os.name != 'nt' and run is subprocess.run:
        return []
    ms = int(max(120.0, now() - since + 60) * 1000)
    q = '*[System[(%s) and TimeCreated[timediff(@SystemTime) <= %d]]]' % (
        ' or '.join('EventID=%d' % i for i in EVENT_IDS), ms)
    try:
        out = run(['wevtutil', 'qe', 'Application', '/q:' + q, '/c:40', '/rd:true', '/f:text'], capture_output=True,
                  stdin=subprocess.DEVNULL, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        # (stdin: the app has none, built without a console; one inherited that way fails the call)
        raw = out.stdout or b''
    except Exception:
        return []
    text = None
    for enc in ('utf-8', 'mbcs', 'cp1252'):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        text = raw.decode('utf-8', 'replace')
    blocks = [b.strip() for b in re.split(r'(?m)^(?=Event\[\d+\])', text) if b.strip()]
    return [b[:6000] for b in blocks if re.search(r'(?i)\bacr(-win64-shipping)?\.exe\b', b)][:10]


def crash_reports(since, folders):
    """Crash reports the game (Unreal) left since a minute before `since`: [(folder name, its files, the start of its
    CrashContext.runtime-xml or '')]."""
    out = []
    for d in folders:
        root = os.path.join(d, 'Crashes')
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            try:
                if not os.path.isdir(p) or os.stat(p).st_mtime < since - 60:
                    continue
                files = sorted(os.listdir(p))
            except OSError:
                continue
            ctx = ''
            for f in files:
                if f.lower().startswith('crashcontext') and f.lower().endswith('xml'):   # (CrashContext.runtime-xml)
                    try:
                        with open(os.path.join(p, f), 'rb') as fh:
                            ctx = fh.read(48 * 1024).decode('utf-8', 'replace')
                    except OSError:
                        pass
            out.append((n, files, ctx))
    return out[:5]


def looked_in(folders):
    """Where the app looked for the game's log, and what each folder holds (for the report)."""
    lines = []
    for d in folders:
        logs = os.path.join(d, 'Logs')
        try:
            names = os.listdir(logs)
            lines.append('%s: %d file(s)%s' % (logs, len(names), (': ' + ', '.join(sorted(names)[:8])) if names else ''))
        except OSError:
            lines.append('%s: not there' % logs)
    return lines


def diagnostics(runs, watch, events, crashes, folders, log, context):
    """The diagnostics file: everything the app knows about the lost runs, as text (scrubbed by the caller)."""
    w = watch or {}
    parts = ['ACR Daily diagnostics: finished runs whose official result the game did not save',
             'App %s on %s. %s' % (__version__, platform.platform(), context or ''), '']
    for r in runs:
        done = r['startedAt'] + (r.get('clockMs') or 0) / 1000 if r.get('startedAt') else None
        parts.append('%s: %s, %s, stage clock %s, finished about %s. DNF: %s.' % (
            r['what'], r.get('stage') or '?', r.get('car') or '?', fmt_ms(r.get('clockMs')),
            _utc(done) if done else '?', r['why']))
        if done:
            lines = gamewatch.timeline(w.get('events') or [], done)
            parts.append('  What the app saw, from the finish (this PC):')
            parts += ['    ' + x for x in lines] or ['    (nothing recorded)']
    parts += ['', '== Windows\' records of the game (Application log: errors, crash reports, hangs) ==']
    parts += events or ['(none since the run started)']
    parts += ['', '== Crash reports the game left (Saved\\Crashes) ==']
    for n, files, ctx in crashes:
        parts.append('%s: %s' % (n, ', '.join(files)))
        if ctx:
            parts.append(ctx)
    if not crashes:
        parts.append('(none since the run started)')
    parts += ['', "== The game's log ==", 'Sent: %s' % (log.get('name') or 'none found')] + looked_in(folders)
    parts += ['', "== The app's notes (official.log, this PC's time) ==", notes([r['id'] for r in runs], DIAG_MAX // 2)]
    return '\n'.join(parts)[:DIAG_MAX]


def _decode(b, utf16):
    return b.decode('utf-16-le' if utf16 else 'utf-8', 'replace').lstrip('﻿')


def read_part(path, head=HEAD, tail=TAIL):
    """The log's first `head` and last `tail` bytes as text (all of it when it is no longer), in whole lines. Read
    without disturbing the game, which may still be writing it (it shares it for reading). -> (text, its size)."""
    with open(path, 'rb') as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(0)
        if size <= head + tail:
            first = f.read()
            return _decode(first, first[:2] == b'\xff\xfe'), size
        first = f.read(head)
        utf16 = first[:2] == b'\xff\xfe'
        start = size - tail
        f.seek(start + (start % 2 if utf16 else 0))       # (UTF-16: whole characters)
        last = f.read()
    a, b = _decode(first, utf16), _decode(last, utf16)
    a = a[:a.rfind('\n') + 1] or a
    b = b[b.find('\n') + 1:]
    return '%s\n[... %d KB of the log left out ...]\n\n%s' % (a, (size - len(first) - len(last)) // 1024, b), size


def scrub(text, env=None):
    """The text without who and where: the Windows user's folder and name and the PC's name (Unreal's start-up lines
    and its paths say them), and anything a launcher passes the game to sign in with."""
    env = os.environ if env is None else env
    home = (env.get('USERPROFILE') or '').rstrip('\\/')
    if len(home) > 3:
        for form in {home, home.replace('\\', '/')}:
            text = re.sub(re.escape(form), '%USERPROFILE%', text, flags=re.I)
    for var, label in (('COMPUTERNAME', '<PC>'), ('USERNAME', '<user>')):
        v = env.get(var) or ''
        if len(v) >= 3:
            text = re.sub(r'(?<![\w.-])%s(?![\w.-])' % re.escape(v), label, text, flags=re.I)
    return re.sub(r'(?i)(-(?:auth_password|auth_login|epicusername|epicuserid)=)("[^"]*"|\S+)', r'\1<removed>', text)


def system_of(text):
    """Unreal's start-up line on the PC ("OS: Windows 11 (24H2) [...], CPU: ..., GPU: ..."), spaces squeezed, or None."""
    m = SYSTEM.search(text)
    return re.sub(r'\s+', ' ', m.group(1)).strip()[:200] if m else None


def ending(text):
    """How the session's log ends, in words for the report."""
    if CRASH.search(text[-60000:]):
        return "it has an error from Unreal near its end (a crash?): see its last lines"
    if CLOSED in text[-3000:]:
        return "it ends with Unreal's \"Log file closed\": the game was quit the normal way"
    return "it ends without Unreal's \"Log file closed\": the game was ended from outside (the Task Manager) or hung"


def last_stamp(text):
    """The stamp on the log's last stamped line ('2026.11.13-04.42.07', UTC unless the game says otherwise), or None."""
    found = STAMP.findall(text[-100000:])
    return found[-1] if found else None


def notes(ids, limit=NOTES_MAX):
    """The app's lines about these runs in official.log (waiting.note), the latest ones if there are many."""
    try:
        with open(os.path.join(settings.DIR, 'official.log'), encoding='utf-8', errors='replace') as f:
            lines = [ln.rstrip() for ln in f if any(i and i in ln for i in ids)]
    except OSError:
        return ''
    out = '\n'.join(lines)
    return out if len(out) <= limit else '...\n' + out[-limit:].split('\n', 1)[-1]


def _utc(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def compose(runs, area, url, context, log, watch=None, events=(), crashes=()):
    """-> the report's fields (server/src/reports.js checkReport) for runs lost in one game session. log: {'name',
    'size', 'text'} of the game's log sent with it, {'name', 'report'} when it went with an earlier report, or {}: none
    found. watch: gamewatch.GameWatch.snapshot(); events, crashes: windows_events(), crash_reports()."""
    r0 = runs[0]
    title = "Sent by the app: the game didn't save %s" % (
        r0['what'] if len(runs) == 1 else '%d runs (%s, ...)' % (len(runs), r0['what']))
    attached = ['diagnostics (what the app saw after the finish, Windows\' records of the game, crash reports)']
    if log.get('text') is not None:
        attached.append("the game's own log of that session")
    parts = ["The ACR Daily app sent this on its own: the game didn't save the official result of a finished run, so "
             "it went in as a DNF. Attached for ACR Daily's admin: %s." % ' and '.join(attached)]
    for r in runs:
        done = r['startedAt'] + (r.get('clockMs') or 0) / 1000 if r.get('startedAt') else None
        parts.append('%s: %s, %s, stage clock %s%s. DNF: %s.' % (
            r['what'], r.get('stage') or '?', r.get('car') or '?', fmt_ms(r.get('clockMs')),
            ', finished about %s' % _utc(done) if done else '', r['why']))
        said = gamewatch.summary((watch or {}).get('events') or [], done) if done else ''
        if said:
            parts.append(said)
    parts.append('Windows recorded %s; crash reports from the game: %s.' % (
        '%d error / hang event(s) of the game (in the diagnostics)' % len(events) if events else
        'no error or hang of the game', '%d (in the diagnostics)' % len(crashes) if crashes else 'none'))
    if log.get('text') is not None:
        stamp, end = last_stamp(log['text']), ending(log['text'])
        parts.append("The game's log: %s, %d KB (%s sent). %s%s.\nThe PC: %s" % (
            log['name'], -(-log['size'] // 1024), 'all of it' if log['size'] <= HEAD + TAIL else
            'its first %d KB and last %d KB' % (HEAD // 1024, TAIL // 1024),
            'Its last line: [%s]. ' % stamp if stamp else '', end[0].upper() + end[1:],
            system_of(log['text']) or 'not in the log'))
    elif log.get('report'):
        parts.append("The game's log of that session went with report #%s." % log['report'])
    else:
        parts.append("The game's log: none found (the game may keep none on this PC; where the app looked: in the "
                     "diagnostics).")
    if context:
        parts.append(context)
    head = '\n\n'.join(parts)
    said = notes([r['id'] for r in runs], max(0, min(NOTES_MAX, BODY_MAX - len(head) - 80)))
    body = head + ("\n\nThe app's notes (official.log, this PC's time):\n" + said if said else '')
    happened = None
    if r0.get('startedAt'):
        happened = 'finished about %s UTC' % _utc(r0['startedAt'] + (r0.get('clockMs') or 0) / 1000)[:16]
    system = system_of(log['text']) if log.get('text') is not None else None
    return {'title': title[:120], 'body': body[:BODY_MAX], 'area': area if area in AREAS else 'other',
            'appVersion': __version__, 'eventUrl': (url or '')[:200] or None, 'happened': happened, 'system': system}


def _note(runs, text):
    for r in runs:
        waiting.note('%s: %s' % (r['id'], text))


def send(api, runs, area, url=None, context='', on_sent=None, folder=None, watch=None):
    """File the report for runs lost in one game session, on its own thread. runs: [{'id' (official.log's), 'what'
    ('SS1 2026-11-13'), 'stage', 'car', 'startedAt' (unix time its stage clock started), 'clockMs', 'why'}]; area: one
    of AREAS; url: the event's page; context: the app's side (what of it was on); on_sent(report id) is called on that
    thread; watch: what the app saw of the game meanwhile (gamewatch.GameWatch.snapshot()). -> the thread, or None
    when nothing is sent (not signed in)."""
    s = getattr(api, 's', None)
    token = s.get('token') if isinstance(s, dict) else None
    if not runs:
        return None
    if not (isinstance(token, str) and token and api.configured):
        _note(runs, "the game's log not sent: not signed in")
        return None
    t = threading.Thread(target=_send, args=(api, runs, area, url, context, on_sent, folder, watch), daemon=True)
    t.start()
    return t


def _send(api, runs, area, url, context, on_sent, folder, watch=None):
    try:
        since = min((r['startedAt'] for r in runs if r.get('startedAt')), default=time.time() - 3600)
        folders = [os.path.dirname(folder)] if folder else saved_folders((watch or {}).get('exe'))
        path = session_log(since, folder) if folder else find_log(since, folders)
        log, key = {}, None
        if path:
            key = _opened(path) or path
            with _lock:
                earlier = _sent.get(key)
            if earlier:
                log = {'name': os.path.basename(path), 'report': earlier}
            else:
                text, size = read_part(path)
                log = {'name': os.path.basename(path), 'size': size, 'text': scrub(text)}
        events = [scrub(e) for e in windows_events(since)]
        crashes = [(n, f, scrub(c)) for n, f, c in crash_reports(since, folders)]
        rid = api.report(compose(runs, area, url, context, log, watch, events, crashes))
        try:
            diag = scrub(diagnostics(runs, watch, events, crashes, folders, log, context))
            api.report_file(rid, gzip.compress(diag.encode('utf-8')), 'acr-daily-diagnostics.txt', kind='log',
                            size=len(diag.encode('utf-8')))
        except Exception as e:                              # (the report itself is in: its log may still go)
            _note(runs, "the diagnostics not sent: %s" % e)
        if log.get('text') is not None:
            api.report_file(rid, gzip.compress(log['text'].encode('utf-8')), log['name'], kind='log', size=log['size'])
            with _lock:
                _sent[key] = rid
            what = log['name']
        elif log.get('report'):
            what = 'its log went with #%s' % log['report']
        else:
            what = 'no log found'
        _note(runs, "the game's log sent to ACR Daily (report #%s, %s)" % (rid, what))
        if on_sent:
            on_sent(rid)
    except Exception as e:                                  # (offline, the day's reports used up: nothing more to do)
        _note(runs, "the game's log not sent: %s" % e)
