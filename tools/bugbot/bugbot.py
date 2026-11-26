"""The bug bot: Discord #bug-reports -> GitHub issues -> AI fix PRs -> a reply in Discord once the fix is out.

Run by the GitHub workflows .github/workflows/bugbot-*.yml (see tools/bugbot/README.md). Python standard library only.

  intake        every 12 hours: new forum posts in #bug-reports are read by Claude (read-only tools). A clear report
                becomes an issue (labels from-discord, bug/enhancement, area:*) and the thread gets "Logged as #N";
                a known one is added to that issue; one missing details gets up to two rounds of questions. Later
                messages in a logged thread are copied to its issue.
  setup-forum   once: the forum's post guidelines (the questions every report should answer) and its tags.
  fix           on the `ai-fix` label: Claude fixes the issue in the checkout and writes .bugbot/fix.json.
  review        after the tests: Claude reviews the PR's diff and the test log, writes .bugbot/review.json.
  notify        after a release (or the `live` label): "Fixed ..." in every Discord thread of the fixed issues.

Everything that comes from Discord is untrusted text. Claude gets it as data in its prompt, never runs with the Discord
or GitHub tokens in its environment, and at intake has only Read/Grep/Glob. Nothing here merges or deploys.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DISCORD_API = 'https://discord.com/api/v10'
DISCORD_EPOCH = 1420070400000
UA = 'DiscordBot (https://github.com/khanhonthetrack/acr-daily, 1.0) acr-daily-bugbot'

FORUM_NAME = 'bug-reports'
SETTLE_MS = 10 * 60000          # a post is read once nobody has written in it for 10 minutes (screenshots come later)
MAX_ROUNDS = 2                  # rounds of questions before the report is logged anyway (label needs-info)
MAX_THREAD_CHARS = 20000
MAX_CHAT_PER_CHANNEL = 400      # messages read per channel per run
MAX_CHAT_CHARS = 60000          # chat sent to Claude per call (more is split over calls)
CHAT_FIRST_LOOK_MS = 24 * 3600000    # the first run reads the last day; later ones from the last scheduled run on
CHAT_MAX_LOOK_MS = 3 * 86400000
MAX_ATTACHMENTS = 6
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
TEXT_EXT = ('.txt', '.log', '.json', '.ini', '.lua', '.cfg', '.csv')
IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/webp', 'image/gif')

AREAS = ['app', 'game-mod', 'server', 'website', 'daily', 'time-trial', 'league', 'cup', '1v1', 'community', 'replay',
         'watch', 'copilot', 'other']
LABELS = {   # name: (colour, description), made by `labels`
    'from-discord': ('5865F2', 'Reported in Discord #bug-reports'),
    'needs-info': ('FBCA04', 'The report is missing details'),
    'ai-fix': ('7057FF', 'Let the AI write a fix (draft PR)'),
    'bugbot': ('7057FF', 'Made by the bug bot'),
    'tests-passed': ('0E8A16', 'Unit tests passed on the bot PR'),
    'tests-failed': ('B60205', 'Unit tests failed on the bot PR'),
    'needs-in-game-test': ('D93F0B', 'Can only be checked in the game'),
    'live': ('0E8A16', 'The fix is live on the server: tell the Discord threads'),
    'notified': ('C5DEF5', 'The Discord threads were told it is fixed'),
}
for _a in AREAS:
    LABELS['area:' + _a] = ('BFD4F2', '')

GUIDELINES = (
    'One bug per post. Please answer:\n'
    '1. App version (for example 0.2.2)\n'
    '2. What you were doing: daily, time trial, league, 1V1, cup, WATCH, COPILOT... and which stage\n'
    '3. What happened\n'
    '4. What you expected\n'
    '5. Does it happen every time?\n'
    '6. A screenshot or clip if you can\n'
    'Crash, freeze or lost time? Also send your logs at https://acrdaily.com/report\n'
    'A bot reads every post, logs it on GitHub and tells you here when the fix is out.')
FORUM_TAGS = ['App', 'In game', 'Website', 'Crash', 'Lost time']


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ small helpers

def snowflake_ms(sid):
    return (int(sid) >> 22) + DISCORD_EPOCH


def no_pings(text):
    """Text safe to put on GitHub: no @mentions of GitHub users or teams."""
    return re.sub(r'@(?=[\w-])', '@\u200b', str(text or ''))


def discord_safe(text, limit=1900):
    """Text from the AI for a Discord message: no mass pings, no masked links, capped."""
    t = str(text or '').replace('@everyone', '@\u200beveryone').replace('@here', '@\u200bhere')
    t = re.sub(r'\[([^\]]*)\]\((https?://[^)]*)\)', r'\1 (\2)', t)
    return t[:limit]


def thread_markers(body):
    """Discord thread ids an issue body names (<!-- discord-thread:ID -->)."""
    return re.findall(r'<!-- discord-thread:(\d+) -->', body or '')


def seen_marker(body, thread_id):
    m = re.search(r'<!-- discord-seen:%s:(\d+) -->' % re.escape(str(thread_id)), body or '')
    return m.group(1) if m else None


def set_seen(body, thread_id, msg_id):
    mark = '<!-- discord-seen:%s:%s -->' % (thread_id, msg_id)
    pat = r'<!-- discord-seen:%s:\d+ -->' % re.escape(str(thread_id))
    return re.sub(pat, mark, body) if re.search(pat, body or '') else (body or '').rstrip() + '\n' + mark


def thread_url(guild_id, thread_id):
    return 'https://discord.com/channels/%s/%s' % (guild_id, thread_id)


def message_url(guild_id, channel_id, msg_id):
    return 'https://discord.com/channels/%s/%s/%s' % (guild_id, channel_id, msg_id)


def message_markers(body):
    """(channel id, message id) of chat messages an issue came from (<!-- discord-message:CH:MSG -->)."""
    return re.findall(r'<!-- discord-message:(\d+):(\d+) -->', body or '')


def ms_to_snowflake(ms):
    return str(max(0, int(ms) - DISCORD_EPOCH) << 22)


def quote(text):
    return '\n'.join('> ' + line for line in str(text).splitlines()) or '> (empty)'


# ------------------------------------------------------------------ HTTP

class HttpError(Exception):
    def __init__(self, status, body, url):
        super().__init__('%s %s: %s' % (status, url, body[:300]))
        self.status, self.body = status, body


def http(method, url, headers, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if data is not None:
        h['Content-Type'] = 'application/json'
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                content = r.read()
                if raw:
                    return content
                return json.loads(content) if content else None
        except urllib.error.HTTPError as e:
            text = e.read().decode('utf-8', 'replace')
            if e.code == 429 and attempt < 3:                    # Discord's rate limit: wait as told
                try:
                    wait = float(json.loads(text).get('retry_after', 2))
                except ValueError:
                    wait = 2
                time.sleep(min(wait, 30) + 0.2)
                continue
            raise HttpError(e.code, text, url)


class Discord:
    def __init__(self, token, guild_id):
        self.h = {'Authorization': 'Bot ' + token, 'User-Agent': UA}
        self.guild_id = guild_id

    def get(self, path):
        return http('GET', DISCORD_API + path, self.h)

    def me(self):
        return self.get('/users/@me')

    def forum(self, name=FORUM_NAME, forum_id=None):
        for c in self.get('/guilds/%s/channels' % self.guild_id):
            if (forum_id and str(c['id']) == str(forum_id)) or (not forum_id and c.get('type') == 15 and c.get('name') == name):
                return c
        return None

    def threads(self, forum_id):
        """The forum's open threads, then the ones archived in the last 3 days."""
        out = [t for t in self.get('/guilds/%s/threads/active' % self.guild_id).get('threads', [])
               if str(t.get('parent_id')) == str(forum_id)]
        try:
            arch = self.get('/channels/%s/threads/archived/public?limit=25' % forum_id).get('threads', [])
        except HttpError as e:
            log('archived threads:', e)
            arch = []
        cutoff = time.time() - 3 * 86400
        for t in arch:
            ts = (t.get('thread_metadata') or {}).get('archive_timestamp')
            if ts and _iso_s(ts) > cutoff and not any(x['id'] == t['id'] for x in out):
                out.append(t)
        return out

    def messages(self, channel_id, after=None):
        """Up to 100 messages, oldest first."""
        q = '?limit=100' + ('&after=%s' % after if after else '')
        return sorted(self.get('/channels/%s/messages%s' % (channel_id, q)), key=lambda m: int(m['id']))

    def post(self, channel_id, content, reply_to=None):
        body = {'content': discord_safe(content), 'allowed_mentions': {'parse': []}}
        if reply_to:      # (under that message, without pinging its author; still sent if it was deleted)
            body['message_reference'] = {'message_id': str(reply_to), 'fail_if_not_exists': False}
        return http('POST', DISCORD_API + '/channels/%s/messages' % channel_id, self.h, body)

    def chat_channels(self, skip_parent=None):
        """Every text/announcement channel and every open thread outside the bug forum -> [{id, name}]."""
        chans = self.get('/guilds/%s/channels' % self.guild_id)
        names = {str(c['id']): c.get('name', '') for c in chans}
        out = [{'id': str(c['id']), 'name': c.get('name', '')} for c in chans if c.get('type') in (0, 5)]
        for t in self.get('/guilds/%s/threads/active' % self.guild_id).get('threads', []):
            if skip_parent and str(t.get('parent_id')) == str(skip_parent):
                continue
            out.append({'id': str(t['id']), 'name': '%s > %s' % (names.get(str(t.get('parent_id')), '?'), t.get('name', ''))})
        return out

    def messages_since(self, channel_id, after_id, limit=MAX_CHAT_PER_CHANNEL):
        """Messages after after_id, oldest first, up to limit (None when the bot may not read the channel)."""
        out, after = [], str(after_id)
        while len(out) < limit:
            try:
                batch = self.messages(channel_id, after=after)
            except HttpError as e:
                if e.status in (403, 404):
                    return None
                raise
            if not batch:
                break
            out += batch
            after = batch[-1]['id']
            if len(batch) < 100:
                break
        return out[:limit]

    def patch_channel(self, channel_id, body):
        return http('PATCH', DISCORD_API + '/channels/%s' % channel_id, self.h, body)

    def download(self, url):
        return http('GET', url, {'User-Agent': UA}, raw=True)


def _iso_s(ts):
    from datetime import datetime
    return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()


class GitHub:
    def __init__(self, token, repo):
        self.h = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'acr-daily-bugbot',
                  'X-GitHub-Api-Version': '2022-11-28'}
        self.base = 'https://api.github.com/repos/' + repo
        self.repo = repo

    def call(self, method, path, body=None):
        return http(method, self.base + path, self.h, body)

    def issues(self, label='from-discord', state='all'):
        out, page = [], 1
        while True:
            batch = self.call('GET', '/issues?labels=%s&state=%s&per_page=100&page=%d' % (urllib.parse.quote(label), state, page))
            out += [i for i in batch if 'pull_request' not in i]
            if len(batch) < 100:
                return out
            page += 1

    def open_issues(self):
        out = self.call('GET', '/issues?state=open&per_page=100')
        return [i for i in out if 'pull_request' not in i]

    def issue(self, n):
        return self.call('GET', '/issues/%d' % n)

    def create_issue(self, title, body, labels):
        return self.call('POST', '/issues', {'title': title[:200], 'body': body, 'labels': labels})

    def edit_issue(self, n, **fields):
        return self.call('PATCH', '/issues/%d' % n, fields)

    def comment(self, n, body):
        return self.call('POST', '/issues/%d/comments' % n, {'body': body})

    def comments(self, n):
        return self.call('GET', '/issues/%d/comments?per_page=100' % n)

    def add_labels(self, n, labels):
        return self.call('POST', '/issues/%d/labels' % n, {'labels': labels})

    def last_scheduled_run_s(self):
        """When the last scheduled intake run that succeeded started (unix s), or None."""
        r = self.call('GET', '/actions/workflows/bugbot-intake.yml/runs?event=schedule&status=success&per_page=1')
        runs = (r or {}).get('workflow_runs') or []
        return _iso_s(runs[0]['run_started_at'] or runs[0]['created_at']) if runs else None

    def start_fix(self, n, ref='main'):
        """Starts bugbot-fix.yml for issue n. (Issues and labels made with the workflow token start no workflows;
        a workflow_dispatch does.)"""
        return self.call('POST', '/actions/workflows/bugbot-fix.yml/dispatches', {'ref': ref, 'inputs': {'issue': str(n)}})

    def ensure_labels(self):
        for name, (color, desc) in LABELS.items():
            try:
                self.call('POST', '/labels', {'name': name, 'color': color, 'description': desc})
            except HttpError as e:
                if e.status != 422:          # 422: it exists already
                    raise


# ------------------------------------------------------------------ Claude

SECRET_NAME = re.compile(r'TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL', re.I)


def claude_env():
    """The environment Claude runs in: ours minus every secret but its own login."""
    env = {k: v for k, v in os.environ.items() if not SECRET_NAME.search(k) or k == 'CLAUDE_CODE_OAUTH_TOKEN'}
    env.pop('GITHUB_TOKEN', None)
    env.pop('GH_TOKEN', None)
    if 'CLAUDE_CODE_OAUTH_TOKEN' in env:   # (a token copied from a wrapped terminal line can carry a break or spaces)
        env['CLAUDE_CODE_OAUTH_TOKEN'] = re.sub(r'\s+', '', env['CLAUDE_CODE_OAUTH_TOKEN'])
    return env


def token_problem(env=None):
    """What is wrong with the Claude login secret as far as we can tell without using it, or None."""
    tok = re.sub(r'\s+', '', (env if env is not None else os.environ).get('CLAUDE_CODE_OAUTH_TOKEN') or '')
    if not tok:
        return ('the secret CLAUDE_CODE_OAUTH_TOKEN is empty or missing: add it under Settings > Secrets and variables '
                '> Actions > Repository secrets')
    if not tok.startswith('sk-ant-oat'):
        return ('the secret CLAUDE_CODE_OAUTH_TOKEN does not start with sk-ant-oat (%d characters): paste the token '
                'that `claude setup-token` prints, not an API key or the Discord token' % len(tok))
    if len(tok) < 80:
        return 'the secret CLAUDE_CODE_OAUTH_TOKEN is only %d characters: part of the token is missing' % len(tok)
    return None


def run_claude(prompt, schema, tools, allowed=None, model=None, cwd=None, max_turns=30, permission_mode=None, runner=None):
    """claude -p with a JSON schema for its answer -> the answer (dict). runner: a stand-in for tests."""
    if runner:
        return runner(prompt=prompt, schema=schema, tools=tools)
    problem = token_problem()
    if problem:
        raise ClaudeError('Claude could not run: ' + problem)
    cmd = ['claude', '-p', '--output-format', 'json', '--json-schema', json.dumps(schema),
           '--tools', ','.join(tools), '--allowedTools', ','.join(allowed or tools), '--max-turns', str(max_turns)]
    if model:
        cmd += ['--model', model]
    if permission_mode:
        cmd += ['--permission-mode', permission_mode]
    cmd[0] = shutil.which('claude') or 'claude'          # (npm's claude.cmd on Windows)
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding='utf-8', cwd=cwd, env=claude_env(), timeout=3600)
    if r.returncode != 0:
        raise ClaudeError(claude_failure(r.returncode, r.stdout, r.stderr))
    return parse_claude_output(r.stdout)


class ClaudeError(RuntimeError):
    """Claude could not run at all (login, usage limit, model name): the rest of the run would fail the same way."""


def claude_failure(code, stdout, stderr):
    """The reason in Claude's own words: its JSON's "result" (e.g. "Invalid API key"), else the output's end."""
    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            data = [d for d in data if d.get('type') == 'result'][-1]
        if data.get('result'):
            hint = (' (Claude refused the CLAUDE_CODE_OAUTH_TOKEN secret: make a new one with `claude setup-token` '
                    'and paste it again)' if data.get('api_error_status') == 401 else '')
            return 'Claude could not run: %s%s' % (data['result'], hint)
    except (ValueError, IndexError, AttributeError):
        pass
    return 'Claude could not run (exit %d): %s %s' % (code, (stderr or '')[-800:], (stdout or '')[-800:])


def parse_claude_output(stdout):
    data = json.loads(stdout)
    if isinstance(data, list):                       # (stream form: the last "result" event)
        data = [d for d in data if d.get('type') == 'result'][-1]
    if data.get('structured_output'):
        return data['structured_output']
    text = data.get('result') or ''
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        raise RuntimeError('no JSON in Claude\'s answer: ' + text[:500])
    return json.loads(m.group(0))


def prompt_file(name):
    with open(os.path.join(HERE, 'prompts', name), encoding='utf-8') as f:
        return f.read()


TRIAGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'kind': {'type': 'string', 'enum': ['bug', 'feature', 'question', 'other']},
        'complete': {'type': 'boolean'},
        'questions': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 5},
        'duplicate_of': {'type': ['integer', 'null']},
        'title': {'type': 'string'},
        'app_version': {'type': 'string'},
        'area': {'type': 'string', 'enum': AREAS},
        'what_happened': {'type': 'string'},
        'expected': {'type': 'string'},
        'steps': {'type': 'string'},
        'every_time': {'type': 'string'},
        'notes': {'type': 'string'},
        'likely_files': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['kind', 'complete', 'questions', 'duplicate_of', 'title', 'area', 'what_happened', 'expected', 'steps',
                 'notes', 'likely_files', 'app_version', 'every_time'],
}


# ------------------------------------------------------------------ intake

def thread_text(messages, bot_id):
    """The thread as plain text for Claude: who (reporter / other / bot), when, what, attachment names."""
    starter = messages[0]['author']['id'] if messages else None
    lines = []
    for m in messages:
        who = 'BOT' if m['author']['id'] == bot_id else ('REPORTER' if m['author']['id'] == starter else 'OTHER USER')
        att = ''.join(' [attachment: %s]' % a.get('filename') for a in m.get('attachments', []))
        lines.append('--- %s, %s ---\n%s%s' % (who, time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(snowflake_ms(m['id']) / 1000)),
                                              m.get('content', ''), att))
    text = '\n'.join(lines)
    return text if len(text) <= MAX_THREAD_CHARS else text[:MAX_THREAD_CHARS // 4] + '\n[...]\n' + text[-MAX_THREAD_CHARS * 3 // 4:]


def needs_reading(messages, bot_id, now_ms):
    """Has someone written since the bot last spoke, and has the thread been quiet for SETTLE_MS?"""
    if not messages:
        return False
    last_bot = max([int(m['id']) for m in messages if m['author']['id'] == bot_id] or [0])
    users_after = [m for m in messages if m['author']['id'] != bot_id and int(m['id']) > last_bot]
    return bool(users_after) and now_ms - snowflake_ms(messages[-1]['id']) >= SETTLE_MS


def question_rounds(messages, bot_id):
    return sum(1 for m in messages if m['author']['id'] == bot_id and 'we need a bit more' in m.get('content', ''))


def issue_body(t, thread, guild_id, messages, needs_info=False):
    starter = messages[0].get('content', '') if messages else ''
    parts = [
        '**Reported on Discord:** %s (%s)' % (thread_url(guild_id, thread['id']), no_pings(thread.get('name', ''))),
        '**App version:** %s' % (no_pings(t.get('app_version')) or 'not given'),
        '**Area:** %s' % t.get('area', 'other'),
        '**Every time?** %s' % (no_pings(t.get('every_time')) or 'not given'),
    ]
    if needs_info:
        parts.append('\n> [!NOTE]\n> The reporter did not answer every question: some details are missing.')
    parts += ['', '### What happened', no_pings(t.get('what_happened')) or '-',
              '', '### Expected', no_pings(t.get('expected')) or '-',
              '', '### Steps', no_pings(t.get('steps')) or '-']
    if t.get('notes') or t.get('likely_files'):
        parts += ['', '### Notes (AI triage)', no_pings(t.get('notes', ''))]
        if t.get('likely_files'):
            parts.append('Likely places: ' + ', '.join('`%s`' % no_pings(f) for f in t['likely_files'][:8]))
    atts = sum(len(m.get('attachments', [])) for m in messages)
    parts += ['', '<details><summary>The report as posted%s</summary>\n\n%s\n\n</details>' % (
        ' (%d attachment%s in the Discord thread)' % (atts, '' if atts == 1 else 's') if atts else '', quote(no_pings(starter[:6000])))]
    parts += ['', '<!-- discord-thread:%s -->' % thread['id'], '<!-- discord-seen:%s:%s -->' % (thread['id'], messages[-1]['id'] if messages else thread['id'])]
    return '\n'.join(parts)


def fetch_attachments(dc, messages, folder):
    """Screenshots and text files of the thread saved for Claude to Read -> [relative paths]."""
    out = []
    os.makedirs(folder, exist_ok=True)
    for m in messages:
        for a in m.get('attachments', []):
            if len(out) >= MAX_ATTACHMENTS:
                return out
            name = str(a.get('filename', 'file'))
            ctype = str(a.get('content_type', '')).split(';')[0]
            ext = os.path.splitext(name)[1].lower()
            if (ctype not in IMAGE_TYPES and ext not in TEXT_EXT) or int(a.get('size', 0)) > MAX_ATTACHMENT_BYTES:
                continue
            safe_ext = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/gif': '.gif'}.get(ctype) or ('.txt' if ext != '.json' else '.json')
            path = os.path.join(folder, '%d%s' % (len(out) + 1, safe_ext))
            try:
                data = dc.download(a['url'])
            except Exception as e:     # noqa: BLE001  (a missing file is no reason to stop)
                log('attachment', name, e)
                continue
            with open(path, 'wb') as f:
                f.write(data[:MAX_ATTACHMENT_BYTES])
            out.append(path)
    return out


def triage_prompt(thread, text, attachments, open_issues):
    known = '\n'.join('#%d %s' % (i['number'], i['title']) for i in open_issues[:100]) or '(none)'
    files = '\n'.join(attachments) or '(none)'
    return (prompt_file('triage.md')
            .replace('{{THREAD_TITLE}}', thread.get('name', ''))
            .replace('{{THREAD}}', text)
            .replace('{{ATTACHMENTS}}', files)
            .replace('{{OPEN_ISSUES}}', known))


def reply_logged(n, url, title):
    return 'Thanks! Logged as **#%d**: %s\n<%s>\nYou\'ll get a message here when the fix is out.' % (n, title, url)


def reply_known(n, url, title):
    return 'Thanks! This one is known already: **#%d** %s\n<%s>\nYou\'ll get a message here when the fix is out.' % (n, title, url)


def reply_questions(questions):
    qs = '\n'.join('- ' + q.strip()[:200] for q in questions[:5] if q.strip())
    return ('Thanks for the report. To track it down we need a bit more:\n%s\n'
            'Screenshots and log files can go here, or at <https://acrdaily.com/report>.' % qs)


REPLY_NOT_BUG = ('This doesn\'t look like a bug report, so I haven\'t logged it. If something isn\'t working, reply with '
                 'what you did, what you expected and what happened.')


def intake(dc, gh, now_ms=None, runner=None, workdir='.bugbot', forum_id=None, model=None, dry=False, autofix=0,
           chat=True, chat_since_ms=None):
    """autofix: how many new bugs of this run go straight to an AI fix (0: none, only the ai-fix label starts one).
    chat: also look for bug reports in every other channel (chat_scan)."""
    now_ms = now_ms or int(time.time() * 1000)
    bot_id = dc.me()['id']
    forum = dc.forum(forum_id=forum_id)
    if not forum:
        raise SystemExit('no forum channel called #%s (set BUGBOT_FORUM_ID)' % FORUM_NAME)
    tracked = {}                                   # thread id -> issue
    for i in gh.issues():
        for tid in thread_markers(i.get('body')):
            tracked[tid] = i
    did = []
    for th in dc.threads(forum['id']):
        tid = str(th['id'])
        try:
            if tid in tracked:
                did += forward_new(dc, gh, tracked[tid], th, bot_id, dry)
                continue
            msgs = dc.messages(tid)
            if msgs and not msgs[0].get('content') and not msgs[0].get('attachments') and msgs[0]['author']['id'] != bot_id:
                log('thread %s: the starter message has no text: is the bot\'s Message Content intent on?' % tid)
            if not needs_reading(msgs, bot_id, now_ms):
                continue
            did.append(handle_new(dc, gh, th, msgs, bot_id, runner, workdir, model, dry))
        except ClaudeError as e:    # (the same for every thread: say it once and stop)
            log(str(e))
            return did + [{'error': str(e)[:1000]}]
        except Exception as e:      # noqa: BLE001  (one bad thread must not stop the others)
            log('thread %s failed: %r' % (tid, e))
            did.append({'thread': tid, 'error': repr(e)[:300]})
    if chat:
        try:
            did += chat_scan(dc, gh, bot_id, forum['id'], now_ms=now_ms, since_ms=chat_since_ms, runner=runner, model=model, dry=dry)
        except ClaudeError as e:
            log(str(e))
            did.append({'chat': 'error', 'error': str(e)[:1000]})
        except Exception as e:      # noqa: BLE001
            log('reading the other channels failed: %r' % e)
            did.append({'chat': 'error', 'error': repr(e)[:300]})
    started = 0
    for d in did:                   # new, clear bugs -> an AI fix each, up to `autofix` a run (the Claude plan's usage)
        if d.get('fixable') and not dry:
            if started >= autofix:
                d['fix'] = 'not started (limit %d a run): add the ai-fix label' % autofix
                continue
            try:
                gh.start_fix(d['issue'])
                d['fix'] = 'started'
                started += 1
            except HttpError as e:
                d['fix'] = 'could not start: %s' % e.status
    return did


def handle_new(dc, gh, th, msgs, bot_id, runner, workdir, model, dry):
    tid = str(th['id'])
    atts = fetch_attachments(dc, msgs, os.path.join(workdir, 'att', tid)) if not dry else []
    t = run_claude(triage_prompt(th, thread_text(msgs, bot_id), atts, gh.open_issues()), TRIAGE_SCHEMA,
                   tools=['Read', 'Grep', 'Glob'], model=model, max_turns=25, runner=runner)
    rounds = question_rounds(msgs, bot_id)
    if t['kind'] in ('question', 'other') and not t.get('duplicate_of'):
        if not dry:
            dc.post(tid, REPLY_NOT_BUG)
        return {'thread': tid, 'did': 'not a bug'}
    dup = t.get('duplicate_of')
    if dup:
        try:
            issue = gh.issue(int(dup))
        except HttpError:
            issue = None
        if issue and 'pull_request' not in issue:
            if not dry:
                body = set_seen((issue.get('body') or '') + '\n<!-- discord-thread:%s -->' % tid, tid, msgs[-1]['id'])
                gh.edit_issue(issue['number'], body=body)
                gh.add_labels(issue['number'], ['from-discord'])
                gh.comment(issue['number'], 'Reported again on Discord: %s\n\n%s' % (
                    thread_url(dc.guild_id, tid), quote(no_pings(msgs[0].get('content', '')[:3000]))))
                dc.post(tid, reply_known(issue['number'], issue['html_url'], issue['title']))
            return {'thread': tid, 'did': 'duplicate of #%s' % issue['number']}
    if not t['complete'] and t.get('questions') and rounds < MAX_ROUNDS:
        if not dry:
            dc.post(tid, reply_questions(t['questions']))
        return {'thread': tid, 'did': 'asked %d questions' % len(t['questions'])}
    needs_info = not t['complete']
    labels = ['from-discord', 'enhancement' if t['kind'] == 'feature' else 'bug', 'area:' + t.get('area', 'other')]
    if needs_info:
        labels.append('needs-info')
    title = no_pings(t.get('title') or th.get('name') or 'Bug report')
    if dry:
        return {'thread': tid, 'did': 'would log', 'title': title, 'labels': labels}
    issue = gh.create_issue(title, issue_body(t, th, dc.guild_id, msgs, needs_info), labels)
    dc.post(tid, reply_logged(issue['number'], issue['html_url'], title))
    return {'thread': tid, 'did': 'logged #%d' % issue['number'], 'issue': issue['number'],
            'fixable': t['kind'] == 'bug' and not needs_info}


def forward_new(dc, gh, issue, th, bot_id, dry):
    """Messages written in a logged thread since the last look go to the issue as one comment."""
    tid = str(th['id'])
    seen = seen_marker(issue.get('body'), tid)
    last = th.get('last_message_id')
    if not last or (seen and int(last) <= int(seen)):
        return []
    new = [m for m in dc.messages(tid, after=seen or tid) if m['author']['id'] != bot_id]
    if not new or dry:
        return []
    text = '\n\n'.join('%s%s' % (quote(no_pings(m.get('content', '')[:3000])),
                                 '\n> _(%d attachment(s))_' % len(m['attachments']) if m.get('attachments') else '') for m in new)
    gh.comment(issue['number'], 'New in the Discord thread (%s):\n\n%s' % (thread_url(dc.guild_id, tid), text))
    gh.edit_issue(issue['number'], body=set_seen(issue.get('body'), tid, new[-1]['id']))
    return [{'thread': tid, 'did': 'forwarded %d message(s) to #%d' % (len(new), issue['number'])}]


# ------------------------------------------------------------------ the rest of the server

CHAT_REPORT = dict(TRIAGE_SCHEMA['properties'])
for _k in ('kind', 'questions'):
    CHAT_REPORT.pop(_k)
CHAT_REPORT['message_id'] = {'type': 'string'}
CHAT_SCHEMA = {
    'type': 'object',
    'properties': {'reports': {'type': 'array', 'items': {
        'type': 'object', 'properties': CHAT_REPORT,
        'required': ['message_id', 'complete', 'duplicate_of', 'title', 'area', 'what_happened', 'expected', 'steps',
                     'notes', 'likely_files', 'app_version', 'every_time']}}},
    'required': ['reports'],
}


def chat_lines(channel, messages, bot_id, people):
    """A channel's messages as lines for Claude: id, who (U1, U2... never names), when, what it replies to, text."""
    out = []
    for m in messages:
        if m['author'].get('bot') or m['author']['id'] == bot_id or (not m.get('content') and not m.get('attachments')):
            continue
        who = people.setdefault(m['author']['id'], 'U%d' % (len(people) + 1))
        ref = (m.get('message_reference') or {}).get('message_id')
        att = ''.join(' [attachment: %s]' % a.get('filename') for a in m.get('attachments', []))
        out.append('[id %s | %s | %s%s] %s%s' % (m['id'], who, time.strftime('%d %b %H:%M', time.gmtime(snowflake_ms(m['id']) / 1000)),
                                                 ' | reply to %s' % ref if ref else '', m.get('content', '')[:1500], att))
    return ('## #%s\n' % channel['name'] + '\n'.join(out)) if out else ''


def chat_batches(blocks, limit=MAX_CHAT_CHARS):
    batches, cur = [], ''
    for b in blocks:
        b = b[:limit]
        if cur and len(cur) + len(b) > limit:
            batches.append(cur)
            cur = ''
        cur += b + '\n\n'
    return batches + ([cur] if cur else [])


def chat_issue_body(t, guild_id, channel, m):
    parts = [
        '**Reported in Discord #%s:** %s' % (no_pings(channel['name']), message_url(guild_id, channel['id'], m['id'])),
        '**App version:** %s' % (no_pings(t.get('app_version')) or 'not given'),
        '**Area:** %s' % t.get('area', 'other'),
        '**Every time?** %s' % (no_pings(t.get('every_time')) or 'not given'),
    ]
    if not t.get('complete'):
        parts.append('\n> [!NOTE]\n> Found in chat: some details are missing.')
    parts += ['', '### What happened', no_pings(t.get('what_happened')) or '-',
              '', '### Expected', no_pings(t.get('expected')) or '-',
              '', '### Steps', no_pings(t.get('steps')) or '-']
    if t.get('notes') or t.get('likely_files'):
        parts += ['', '### Notes (AI triage)', no_pings(t.get('notes', ''))]
        if t.get('likely_files'):
            parts.append('Likely places: ' + ', '.join('`%s`' % no_pings(f) for f in t['likely_files'][:8]))
    parts += ['', '<details><summary>The message</summary>\n\n%s\n\n</details>' % quote(no_pings(m.get('content', '')[:6000])),
              '', '<!-- discord-message:%s:%s -->' % (channel['id'], m['id'])]
    return '\n'.join(parts)


def reply_logged_chat(n, url, title, complete):
    more = '' if complete else '\nMore details help: app version, what you did, what happened (here or in #bug-reports).'
    return 'Logged this as a bug: **#%d** %s\n<%s>%s\nYou\'ll get a message here when the fix is out.' % (n, title, url, more)


def chat_scan(dc, gh, bot_id, forum_id, now_ms=None, since_ms=None, runner=None, model=None, dry=False):
    """Bug reports said anywhere else on the server since the last run -> issues + a reply under each."""
    now_ms = now_ms or int(time.time() * 1000)
    if since_ms is None:
        last = gh.last_scheduled_run_s()
        since_ms = int(last * 1000) - 15 * 60000 if last else now_ms - CHAT_FIRST_LOOK_MS
    since_ms = max(since_ms, now_ms - CHAT_MAX_LOOK_MS)
    logged = set()
    for i in gh.issues():
        logged.update(mid for _, mid in message_markers(i.get('body')))
    after = ms_to_snowflake(since_ms)
    people, blocks, by_id = {}, [], {}
    for ch in dc.chat_channels(skip_parent=forum_id):
        msgs = dc.messages_since(ch['id'], after)
        if not msgs:
            continue
        for m in msgs:
            by_id[m['id']] = (ch, m)
        block = chat_lines(ch, msgs, bot_id, people)
        if block:
            blocks.append(block)
    did = []
    if not blocks:
        return did
    known = gh.open_issues()
    for batch in chat_batches(blocks):
        prompt = (prompt_file('chat.md').replace('{{CHAT}}', batch)
                  .replace('{{OPEN_ISSUES}}', '\n'.join('#%d %s' % (i['number'], i['title']) for i in known[:100]) or '(none)'))
        found = run_claude(prompt, CHAT_SCHEMA, tools=['Read', 'Grep', 'Glob'], model=model, max_turns=25, runner=runner)
        for t in found.get('reports', [])[:10]:
            mid = str(t.get('message_id', ''))
            if mid not in by_id or mid in logged:          # (an id Claude made up, or logged already)
                continue
            logged.add(mid)
            try:
                did.append(log_chat_report(dc, gh, t, *by_id[mid], dry=dry))
            except Exception as e:     # noqa: BLE001
                log('message %s failed: %r' % (mid, e))
                did.append({'message': mid, 'error': repr(e)[:300]})
    return did


def log_chat_report(dc, gh, t, ch, m, dry=False):
    mark = '<!-- discord-message:%s:%s -->' % (ch['id'], m['id'])
    link = message_url(dc.guild_id, ch['id'], m['id'])
    dup = t.get('duplicate_of')
    if dup:
        try:
            issue = gh.issue(int(dup))
        except HttpError:
            issue = None
        if issue and 'pull_request' not in issue:
            if not dry:
                gh.edit_issue(issue['number'], body=(issue.get('body') or '') + '\n' + mark)
                gh.add_labels(issue['number'], ['from-discord'])
                gh.comment(issue['number'], 'Also reported in Discord #%s: %s\n\n%s' % (
                    no_pings(ch['name']), link, quote(no_pings(m.get('content', '')[:3000]))))
                dc.post(ch['id'], reply_known(issue['number'], issue['html_url'], issue['title']), reply_to=m['id'])
            return {'message': m['id'], 'channel': ch['name'], 'did': 'duplicate of #%s' % issue['number']}
    labels = ['from-discord', 'bug', 'area:' + t.get('area', 'other')] + ([] if t.get('complete') else ['needs-info'])
    title = no_pings(t.get('title') or 'Bug report from Discord')
    if dry:
        return {'message': m['id'], 'channel': ch['name'], 'did': 'would log', 'title': title}
    issue = gh.create_issue(title, chat_issue_body(t, dc.guild_id, ch, m), labels)
    dc.post(ch['id'], reply_logged_chat(issue['number'], issue['html_url'], title, t.get('complete')), reply_to=m['id'])
    return {'message': m['id'], 'channel': ch['name'], 'did': 'logged #%d' % issue['number'], 'issue': issue['number'],
            'fixable': bool(t.get('complete'))}


def setup_forum(dc, forum_id=None):
    forum = dc.forum(forum_id=forum_id)
    if not forum:
        raise SystemExit('no forum channel called #%s' % FORUM_NAME)
    have = {t['name'].lower() for t in forum.get('available_tags', [])}
    tags = list(forum.get('available_tags', [])) + [{'name': n} for n in FORUM_TAGS if n.lower() not in have]
    try:
        dc.patch_channel(forum['id'], {'topic': GUIDELINES, 'available_tags': tags[:20]})
    except HttpError as e:
        raise SystemExit('Discord said %s: the bot needs Manage Channels on #%s for this (once)' % (e.status, FORUM_NAME))
    return {'forum': forum['id'], 'tags': [t['name'] for t in tags]}


# ------------------------------------------------------------------ notify

def notify_message(issue, release=None):
    title = no_pings(issue['title'])
    if release:
        return 'Fixed: **%s** (#%d)\nIt\'s in ACR Daily **%s**: click UPDATE in the app.\nThanks for reporting it!' % (title, issue['number'], release)
    return 'Fixed: **%s** (#%d)\nIt\'s live now, no update needed.\nThanks for reporting it!' % (title, issue['number'])


def fixed_for_release(issues, release_time_s):
    """Closed-as-done Discord issues not told yet, closed before the release's commit."""
    out = []
    for i in issues:
        names = {l['name'] for l in i.get('labels', [])}
        if i.get('state') != 'closed' or i.get('state_reason') != 'completed' or 'notified' in names:
            continue
        if not i.get('closed_at') or _iso_s(i['closed_at']) > release_time_s:
            continue
        out.append(i)
    return out


def tell_threads(dc, gh, issue, text, dry=False):
    sent = []
    for tid in thread_markers(issue.get('body')):
        if dry:
            sent.append(tid)
            continue
        try:
            dc.post(tid, text)
            sent.append(tid)
        except HttpError as e:
            log('thread %s: %s' % (tid, e))
    for ch, mid in message_markers(issue.get('body')):     # reports found in chat: under the message
        if dry:
            sent.append(mid)
            continue
        try:
            dc.post(ch, text, reply_to=mid)
            sent.append(mid)
        except HttpError as e:
            log('message %s: %s' % (mid, e))
    if not dry and sent:
        gh.add_labels(issue['number'], ['notified'])
    return sent


def notify(dc, gh, release=None, release_time_s=None, issue_number=None, dry=False):
    if issue_number:
        issue = gh.issue(issue_number)
        return [{'issue': issue['number'], 'threads': tell_threads(dc, gh, issue, notify_message(issue), dry)}]
    out = []
    for i in fixed_for_release(gh.issues(state='closed'), release_time_s or time.time()):
        out.append({'issue': i['number'], 'threads': tell_threads(dc, gh, i, notify_message(i, release), dry)})
    return out


# ------------------------------------------------------------------ fix + review (run in the checkout)

FIX_SCHEMA = {
    'type': 'object',
    'properties': {
        'fixed': {'type': 'boolean'},
        'pr_title': {'type': 'string'},
        'cause': {'type': 'string'},
        'change': {'type': 'string'},
        'tests': {'type': 'string'},
        'in_game_check': {'type': 'string'},
        'why_not': {'type': 'string'},
    },
    'required': ['fixed', 'pr_title', 'cause', 'change', 'tests', 'in_game_check', 'why_not'],
}
FIX_TOOLS = ['Read', 'Edit', 'Write', 'Glob', 'Grep', 'Bash']
FIX_ALLOWED = ['Read', 'Edit', 'Write', 'Glob', 'Grep', 'Bash(cd:*)', 'Bash(npm test:*)','Bash(node --test:*)',
               'Bash(python -m unittest:*)', 'Bash(git diff:*)', 'Bash(git status:*)', 'Bash(git log:*)', 'Bash(ls:*)']

REVIEW_SCHEMA = {
    'type': 'object',
    'properties': {
        'verdict': {'type': 'string', 'enum': ['looks-good', 'needs-changes']},
        'summary': {'type': 'string'},
        'problems': {'type': 'array', 'items': {'type': 'string'}},
        'in_game_checks': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['verdict', 'summary', 'problems', 'in_game_checks'],
}


def issue_for_prompt(gh, n):
    i = gh.issue(n)
    cs = gh.comments(n)
    text = '# #%d %s\n\n%s' % (i['number'], i['title'], i.get('body') or '')
    for c in cs:
        text += '\n\n--- comment by %s ---\n%s' % (c['user']['login'], c.get('body') or '')
    return text[:40000]


def fix(gh, n, model=None, runner=None):
    prompt = prompt_file('fix.md').replace('{{ISSUE}}', issue_for_prompt(gh, n)).replace('{{N}}', str(n))
    return run_claude(prompt, FIX_SCHEMA, tools=FIX_TOOLS, allowed=FIX_ALLOWED, model=model, max_turns=120,
                      permission_mode='acceptEdits', runner=runner)


def review(gh, n, pr, diff_path, tests_path, model=None, runner=None):
    prompt = (prompt_file('review.md').replace('{{ISSUE}}', issue_for_prompt(gh, n)).replace('{{PR}}', str(pr))
              .replace('{{DIFF}}', diff_path).replace('{{TESTS}}', tests_path))
    return run_claude(prompt, REVIEW_SCHEMA, tools=['Read', 'Grep', 'Glob'], model=model, max_turns=60, runner=runner)


def pr_body(n, f):
    return ('Fixes #%d\n\nWritten by the bug bot (AI). Not tested in the game.\n\n### Cause\n%s\n\n### Change\n%s\n\n'
            '### Tests\n%s\n\n### Check in the game\n%s\n' % (n, f['cause'], f['change'], f['tests'], f['in_game_check'] or '-'))


def review_comment(r, tests_ok):
    lines = ['### AI review: %s' % ('looks good' if r['verdict'] == 'looks-good' else 'needs changes'),
             '', 'Unit tests (Windows): **%s**' % ('passed' if tests_ok else 'FAILED'), '', r['summary']]
    if r['problems']:
        lines += ['', '**Problems**'] + ['- ' + p for p in r['problems']]
    if r['in_game_checks']:
        lines += ['', '**Check in the game before merging**'] + ['- [ ] ' + c for c in r['in_game_checks']]
    lines += ['', '_The bot never merges: that is yours._']
    return '\n'.join(lines)


# ------------------------------------------------------------------ command line

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=['intake', 'setup-forum', 'labels', 'notify', 'fix', 'review', 'pr-body', 'review-comment'])
    p.add_argument('--issue', type=int)
    p.add_argument('--pr', type=int)
    p.add_argument('--release')
    p.add_argument('--release-time', type=float, help='unix seconds of the release commit')
    p.add_argument('--diff')
    p.add_argument('--tests')
    p.add_argument('--tests-ok', choices=['true', 'false'])
    p.add_argument('--out')
    p.add_argument('--dry', action='store_true', help='read and decide, write nothing to Discord/GitHub')
    a = p.parse_args(argv)
    env = os.environ
    model = env.get('BUGBOT_MODEL') or None

    def dc():
        return Discord(env['DISCORD_BOT_TOKEN'], env.get('DISCORD_GUILD_ID') or '1556808894205141145')

    def gh():
        return GitHub(env['GITHUB_TOKEN'], env['GITHUB_REPOSITORY'])

    def out(obj):
        text = json.dumps(obj, indent=2, ensure_ascii=False)
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            with open(a.out, 'w', encoding='utf-8') as f:
                f.write(text)
        print(text)

    if a.command == 'labels':
        gh().ensure_labels()
        out({'labels': list(LABELS)})
    elif a.command == 'intake':
        out(intake(dc(), gh(), forum_id=env.get('BUGBOT_FORUM_ID') or None, model=env.get('BUGBOT_TRIAGE_MODEL') or model, dry=a.dry,
                   autofix=int(env.get('BUGBOT_AUTOFIX') or 0), chat=env.get('BUGBOT_READ_ALL', '1') != '0'))
    elif a.command == 'setup-forum':
        out(setup_forum(dc(), forum_id=env.get('BUGBOT_FORUM_ID') or None))
    elif a.command == 'notify':
        out(notify(dc(), gh(), release=a.release, release_time_s=a.release_time, issue_number=a.issue, dry=a.dry))
    elif a.command == 'fix':
        out(fix(gh(), a.issue, model=model))
    elif a.command == 'review':
        out(review(gh(), a.issue, a.pr, a.diff, a.tests, model=model))
    elif a.command == 'pr-body':
        with open(os.path.join('.bugbot', 'fix.json'), encoding='utf-8') as f:
            print(pr_body(a.issue, json.load(f)))
    elif a.command == 'review-comment':
        with open(os.path.join('.bugbot', 'review.json'), encoding='utf-8') as f:
            print(review_comment(json.load(f), a.tests_ok == 'true'))


if __name__ == '__main__':
    main()
