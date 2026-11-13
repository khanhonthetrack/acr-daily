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
"""
import datetime
import gzip
import os
import re
import threading
import time

from . import __version__, settings, waiting
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


def compose(runs, area, url, context, log):
    """-> the report's fields (server/src/reports.js checkReport) for runs lost in one game session. log: {'name',
    'size', 'text'} of the game's log sent with it, {'name', 'report'} when it went with an earlier report, or {}: none
    found."""
    r0 = runs[0]
    title = "Sent by the app: the game didn't save %s" % (
        r0['what'] if len(runs) == 1 else '%d runs (%s, ...)' % (len(runs), r0['what']))
    parts = ["The ACR Daily app sent this on its own: the game didn't save the official result of a finished run, so "
             "it went in as a DNF. The game's own log of that session is attached for ACR Daily's admin."]
    for r in runs:
        done = r['startedAt'] + (r.get('clockMs') or 0) / 1000 if r.get('startedAt') else None
        parts.append('%s: %s, %s, stage clock %s%s. DNF: %s.' % (
            r['what'], r.get('stage') or '?', r.get('car') or '?', fmt_ms(r.get('clockMs')),
            ', finished about %s' % _utc(done) if done else '', r['why']))
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
        parts.append("The game's log: none found in %s." % FOLDER)
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


def send(api, runs, area, url=None, context='', on_sent=None, folder=None):
    """File the report for runs lost in one game session, on its own thread. runs: [{'id' (official.log's), 'what'
    ('SS1 2026-11-13'), 'stage', 'car', 'startedAt' (unix time its stage clock started), 'clockMs', 'why'}]; area: one
    of AREAS; url: the event's page; context: the app's side (what of it was on); on_sent(report id) is called on that
    thread. -> the thread, or None when nothing is sent (not signed in)."""
    s = getattr(api, 's', None)
    token = s.get('token') if isinstance(s, dict) else None
    if not runs:
        return None
    if not (isinstance(token, str) and token and api.configured):
        _note(runs, "the game's log not sent: not signed in")
        return None
    t = threading.Thread(target=_send, args=(api, runs, area, url, context, on_sent, folder), daemon=True)
    t.start()
    return t


def _send(api, runs, area, url, context, on_sent, folder):
    try:
        since = min((r['startedAt'] for r in runs if r.get('startedAt')), default=time.time() - 3600)
        path, log, key = session_log(since, folder), {}, None
        if path:
            key = _opened(path) or path
            with _lock:
                earlier = _sent.get(key)
            if earlier:
                log = {'name': os.path.basename(path), 'report': earlier}
            else:
                text, size = read_part(path)
                log = {'name': os.path.basename(path), 'size': size, 'text': scrub(text)}
        rid = api.report(compose(runs, area, url, context, log))
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
