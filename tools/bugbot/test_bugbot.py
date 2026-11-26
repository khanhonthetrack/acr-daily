"""Tests of the bug bot with stand-ins for Discord, GitHub and Claude:  python -m unittest tools/bugbot/test_bugbot.py"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bugbot as bb  # noqa: E402

BOT, ALICE, BOB = '900', '101', '102'
NOW = 1_800_000_000_000


def sid(ms):
    """A Discord id made at ms."""
    return str((ms - bb.DISCORD_EPOCH) << 22)


def msg(author, minutes_ago, content='', attachments=None):
    return {'id': sid(NOW - minutes_ago * 60000), 'author': {'id': author}, 'content': content, 'attachments': attachments or []}


class FakeDiscord:
    guild_id = '1556808894205141145'

    def __init__(self, threads):
        self.threads_ = threads           # id -> (thread, [messages])
        self.posts = []

    def me(self):
        return {'id': BOT}

    def forum(self, forum_id=None):
        return {'id': '555', 'available_tags': []}

    def threads(self, forum_id):
        return [t for t, _ in self.threads_.values()]

    def messages(self, tid, after=None):
        ms = sorted(self.threads_[tid][1], key=lambda m: int(m['id']))
        return [m for m in ms if not after or int(m['id']) > int(after)]

    def chat_channels(self, skip_parent=None):
        return [{'id': cid, 'name': 'general'} for cid in getattr(self, 'chat', {})]

    def messages_since(self, cid, after):
        return [m for m in self.chat[cid] if int(m['id']) > int(after)]

    def post(self, tid, content, reply_to=None):
        if tid in getattr(self, 'chat', {}):
            self.posts.append((tid, content, reply_to))
            return
        self.posts.append((tid, content))   # (right after the newest message)
        last = max([int(m['id']) for m in self.threads_[tid][1]] or [int(sid(NOW))])
        self.threads_[tid][1].append({'id': str(last + (1 << 22)), 'author': {'id': BOT}, 'content': content})

    def download(self, url):
        return b'png'


class FakeGitHub:
    def __init__(self, issues=None):
        self.list = issues or []
        self.comments_ = []
        self.fixes = []

    def start_fix(self, n):
        self.fixes.append(n)

    def last_scheduled_run_s(self):
        return None

    def issues(self, label='from-discord', state='all'):
        return [i for i in self.list if state == 'all' or i['state'] == state]

    def open_issues(self):
        return [i for i in self.list if i['state'] == 'open']

    def issue(self, n):
        return next(i for i in self.list if i['number'] == n)

    def create_issue(self, title, body, labels):
        i = {'number': 10 + len(self.list), 'title': title, 'body': body, 'labels': [{'name': l} for l in labels],
             'state': 'open', 'html_url': 'https://github.com/x/y/issues/%d' % (10 + len(self.list))}
        self.list.append(i)
        return i

    def edit_issue(self, n, **f):
        self.issue(n).update(f)

    def comment(self, n, body):
        self.comments_.append((n, body))

    def add_labels(self, n, labels):
        self.issue(n)['labels'] += [{'name': l} for l in labels]


def triage(**over):
    t = {'kind': 'bug', 'complete': True, 'questions': [], 'duplicate_of': None, 'title': 'Timer stuck at 0', 'area': 'app',
         'what_happened': 'timer stays 0', 'expected': 'it counts', 'steps': 'DRIVE', 'notes': '', 'likely_files': [],
         'app_version': '0.2.2', 'every_time': 'yes'}
    t.update(over)
    return lambda **kw: t


class Helpers(unittest.TestCase):
    def test_markers(self):
        body = 'x\n<!-- discord-thread:11 -->\n<!-- discord-thread:22 -->\n<!-- discord-seen:11:5 -->'
        self.assertEqual(bb.thread_markers(body), ['11', '22'])
        self.assertEqual(bb.seen_marker(body, '11'), '5')
        self.assertIsNone(bb.seen_marker(body, '22'))
        body = bb.set_seen(bb.set_seen(body, '11', '9'), '22', '7')
        self.assertEqual((bb.seen_marker(body, '11'), bb.seen_marker(body, '22')), ('9', '7'))

    def test_no_pings(self):
        self.assertNotIn('@khanh', bb.no_pings('hi @khanh @org/team'))
        self.assertNotIn('@org', bb.no_pings('hi @khanh @org/team'))

    def test_discord_safe(self):
        t = bb.discord_safe('@everyone see [here](https://evil.example)')
        self.assertNotIn('@everyone', t)
        self.assertIn('here (https://evil.example)', t)

    def test_settle(self):
        self.assertFalse(bb.needs_reading([msg(ALICE, 3, 'bug')], BOT, NOW))          # still typing
        self.assertTrue(bb.needs_reading([msg(ALICE, 30, 'bug')], BOT, NOW))
        self.assertFalse(bb.needs_reading([msg(ALICE, 30, 'bug'), msg(BOT, 20, 'q')], BOT, NOW))
        self.assertTrue(bb.needs_reading([msg(ALICE, 30, 'bug'), msg(BOT, 20, 'q'), msg(ALICE, 15, 'a')], BOT, NOW))

    def test_claude_output(self):
        self.assertEqual(bb.parse_claude_output(json.dumps({'type': 'result', 'structured_output': {'a': 1}})), {'a': 1})
        self.assertEqual(bb.parse_claude_output(json.dumps({'type': 'result', 'result': 'ok {"a": 2}'})), {'a': 2})

    def test_claude_env_has_no_secrets(self):
        fake = {'DISCORD_BOT_TOKEN': 'd', 'GITHUB_TOKEN': 'g', 'CLAUDE_CODE_OAUTH_TOKEN': 'c', 'ACTIONS_RUNTIME_TOKEN': 'r'}
        old = {k: os.environ.get(k) for k in fake}
        os.environ.update(fake)
        try:
            env = bb.claude_env()
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(env.get('CLAUDE_CODE_OAUTH_TOKEN'), 'c')
        for k in ('DISCORD_BOT_TOKEN', 'GITHUB_TOKEN', 'ACTIONS_RUNTIME_TOKEN'):
            self.assertNotIn(k, env)


class Intake(unittest.TestCase):
    def run_intake(self, dc, gh, runner, autofix=0):
        with tempfile.TemporaryDirectory() as d:
            return bb.intake(dc, gh, now_ms=NOW, runner=runner, workdir=d, autofix=autofix, chat=False)

    def test_autofix_new_clear_bugs_up_to_the_limit(self):
        threads = {}
        for k in range(3):
            th = {'id': sid(NOW - 3600000 - k * 60000), 'name': 'bug %d' % k}
            m = msg(ALICE, 60 + k, 'broken %d' % k)
            m['id'] = th['id']
            threads[th['id']] = (th, [m])
        dc, gh = FakeDiscord(threads), FakeGitHub()
        did = self.run_intake(dc, gh, triage(), autofix=2)
        self.assertEqual(len(gh.fixes), 2)
        self.assertEqual(sum(1 for d in did if str(d.get('fix', '')).startswith('not started')), 1)

    def test_no_autofix_for_features_or_missing_details(self):
        th = {'id': sid(NOW - 3600000), 'name': 'wish'}
        m = msg(ALICE, 60, 'add rain')
        m['id'] = th['id']
        dc, gh = FakeDiscord({th['id']: (th, [m])}), FakeGitHub()
        self.run_intake(dc, gh, triage(kind='feature'), autofix=3)
        self.assertEqual(gh.fixes, [])

    def test_logs_a_clear_report(self):
        th = {'id': sid(NOW - 3600000), 'name': 'Timer broken'}
        start = msg(ALICE, 60, 'timer stuck @someone', [{'filename': 'a.png', 'content_type': 'image/png', 'size': 10, 'url': 'u'}])
        start['id'] = th['id']
        dc, gh = FakeDiscord({th['id']: (th, [start])}), FakeGitHub()
        did = self.run_intake(dc, gh, triage())
        self.assertEqual(did[0]['did'], 'logged #10')
        issue = gh.list[0]
        self.assertIn('<!-- discord-thread:%s -->' % th['id'], issue['body'])
        self.assertNotIn('@someone', issue['body'])
        self.assertIn('area:app', [l['name'] for l in issue['labels']])
        self.assertIn('Logged as **#10**', dc.posts[0][1])
        # the next run: the bot spoke last, nothing new -> nothing happens
        self.assertEqual(self.run_intake(dc, gh, triage()), [])

    def test_asks_then_logs_with_needs_info(self):
        th = {'id': sid(NOW - 7200000), 'name': 'crash'}
        m = msg(ALICE, 120, 'it crashed')
        m['id'] = th['id']
        dc, gh = FakeDiscord({th['id']: (th, [m])}), FakeGitHub()
        ask = triage(complete=False, questions=['Which app version?'])
        self.assertIn('asked', self.run_intake(dc, gh, ask)[0]['did'])
        self.assertIn('we need a bit more', dc.posts[-1][1])
        for i in range(bb.MAX_ROUNDS - 1):            # the reporter answers, still not enough
            dc.threads_[th['id']][1].append(msg(ALICE, 100 - i * 20, 'dunno'))
            self.assertIn('asked', self.run_intake(dc, gh, ask)[0]['did'])
        dc.threads_[th['id']][1].append(msg(ALICE, 11, 'still dunno'))
        self.assertIn('logged', self.run_intake(dc, gh, ask)[0]['did'])
        self.assertIn('needs-info', [l['name'] for l in gh.list[0]['labels']])

    def test_duplicate_joins_the_issue(self):
        old = {'number': 3, 'title': 'Timer stuck', 'body': 'x\n<!-- discord-thread:1 -->', 'labels': [], 'state': 'open',
               'html_url': 'https://github.com/x/y/issues/3'}
        th = {'id': sid(NOW - 3600000), 'name': 'timer'}
        m = msg(BOB, 60, 'timer 0')
        m['id'] = th['id']
        dc, gh = FakeDiscord({th['id']: (th, [m])}), FakeGitHub([old])
        self.assertEqual(self.run_intake(dc, gh, triage(duplicate_of=3))[0]['did'], 'duplicate of #3')
        self.assertEqual(bb.thread_markers(old['body']), ['1', th['id']])
        self.assertIn('known already', dc.posts[0][1])

    def test_claude_down_says_why_once_and_stops(self):
        out = json.dumps({'type': 'result', 'is_error': True, 'duration_api_ms': 0, 'result': 'Invalid API key · Please run /login'})
        self.assertEqual(bb.claude_failure(1, out, ''), 'Claude could not run: Invalid API key · Please run /login')
        out401 = json.dumps({'type': 'result', 'api_error_status': 401, 'result': 'Not logged in · Please run /login'})
        self.assertIn('setup-token', bb.claude_failure(1, out401, ''))
        good = 'sk-ant-oat01-' + 'a' * 90
        self.assertIsNone(bb.token_problem({'CLAUDE_CODE_OAUTH_TOKEN': good[:50] + '\n  ' + good[50:]}))
        self.assertIn('empty', bb.token_problem({}))
        self.assertIn('sk-ant-oat', bb.token_problem({'CLAUDE_CODE_OAUTH_TOKEN': 'MTU1NjgwOD' * 9}))
        self.assertIn('missing', bb.token_problem({'CLAUDE_CODE_OAUTH_TOKEN': good[:40]}))
        threads, calls = {}, []
        for k in range(3):
            th = {'id': sid(NOW - 3600000 - k * 60000), 'name': 'b%d' % k}
            m = msg(ALICE, 60 + k, 'x')
            m['id'] = th['id']
            threads[th['id']] = (th, [m])

        def down(**kw):
            calls.append(1)
            raise bb.ClaudeError('Claude could not run: Invalid API key')
        did = self.run_intake(FakeDiscord(threads), FakeGitHub(), down)
        self.assertEqual(len(calls), 1)
        self.assertEqual(did, [{'error': 'Claude could not run: Invalid API key'}])

    def test_old_quiet_posts_left_alone(self):
        th = {'id': sid(NOW - 9 * 86400000), 'name': 'old'}
        m = msg(ALICE, 9 * 24 * 60, 'old bug')
        m['id'] = th['id']
        th['last_message_id'] = m['id']
        dc, gh = FakeDiscord({th['id']: (th, [m])}), FakeGitHub()
        self.assertEqual(self.run_intake(dc, gh, triage()), [])
        dc.threads_[th['id']][1].append(msg(ALICE, 60, 'still broken'))   # someone writes again: read it
        th['last_message_id'] = dc.threads_[th['id']][1][-1]['id']
        self.assertEqual(self.run_intake(dc, gh, triage())[0]['did'], 'logged #10')

    def test_questions_shown_with_the_post(self):
        th = {'id': sid(NOW - 3600000), 'name': 'Timer broken'}
        m = msg(ALICE, 60, 'timer')
        m['id'] = th['id']
        dc, gh = FakeDiscord({th['id']: (th, [m])}), FakeGitHub()
        did = self.run_intake(dc, gh, triage(complete=False, questions=['Which version?']))
        self.assertEqual((did[0]['post'], did[0]['questions']), ('Timer broken', ['Which version?']))

    def test_not_a_bug(self):
        th = {'id': sid(NOW - 3600000), 'name': 'hi'}
        m = msg(BOB, 60, 'how do I drive?')
        m['id'] = th['id']
        dc, gh = FakeDiscord({th['id']: (th, [m])}), FakeGitHub()
        self.assertEqual(self.run_intake(dc, gh, triage(kind='question'))[0]['did'], 'not a bug')
        self.assertEqual(gh.list, [])

    def test_forwards_later_messages(self):
        th = {'id': sid(NOW - 3600000), 'name': 't'}
        m = msg(ALICE, 60, 'bug')
        m['id'] = th['id']
        later = msg(ALICE, 1, 'here is my log')
        issue = {'number': 4, 'title': 't', 'state': 'open', 'labels': [],
                 'body': '<!-- discord-thread:%s -->\n<!-- discord-seen:%s:%s -->' % (th['id'], th['id'], th['id'])}
        th['last_message_id'] = later['id']
        dc, gh = FakeDiscord({th['id']: (th, [m, later])}), FakeGitHub([issue])
        self.assertIn('forwarded 1', self.run_intake(dc, gh, triage())[0]['did'])
        self.assertIn('here is my log', gh.comments_[0][1])
        self.assertEqual(bb.seen_marker(issue['body'], th['id']), later['id'])
        self.assertEqual(self.run_intake(dc, gh, triage()), [])        # seen: not again


class Chat(unittest.TestCase):
    def setup(self):
        report = msg(ALICE, 120, 'the timer overlay vanished after DRIVE on 0.2.2')
        noise = msg(BOB, 100, 'gg everyone')
        old = msg(BOB, 48 * 60, 'ancient bug')                       # before the first look (24 h)
        bot = dict(msg(BOT, 90, 'board'), author={'id': BOT, 'bot': True})
        dc = FakeDiscord({})
        dc.chat = {'40': [old, report, noise, bot]}
        return dc, report, noise

    def test_logs_a_report_said_in_chat_and_replies_under_it(self):
        dc, report, noise = self.setup()
        gh, seen = FakeGitHub(), {}

        def runner(prompt, schema, tools):
            seen['prompt'] = prompt
            return {'reports': [dict(triage()(), message_id=report['id']), dict(triage()(), message_id='123')]}   # (123: made up)
        did = bb.chat_scan(dc, gh, BOT, '555', now_ms=NOW, runner=runner)
        self.assertEqual([d['did'] for d in did], ['logged #10'])
        self.assertIn('gg everyone', seen['prompt'])
        self.assertNotIn('ancient bug', seen['prompt'])
        self.assertNotIn('board', seen['prompt'])
        self.assertNotIn(ALICE, seen['prompt'])                       # (people as U1, U2: no Discord ids or names)
        self.assertEqual(bb.message_markers(gh.list[0]['body']), [('40', report['id'])])
        self.assertEqual(dc.posts[0][2], report['id'])
        # the next run: logged already -> no second issue
        self.assertEqual(bb.chat_scan(dc, gh, BOT, '555', now_ms=NOW, runner=runner), [])
        # fixed + released: the reply goes under the message too
        gh.list[0].update(state='closed', state_reason='completed', closed_at='2027-01-01T00:00:00Z')
        bb.notify(dc, gh, release='v0.2.3', release_time_s=bb._iso_s('2027-01-02T00:00:00Z'))
        self.assertEqual((dc.posts[-1][0], dc.posts[-1][2]), ('40', report['id']))

    def test_nothing_found(self):
        dc, _, _ = self.setup()
        gh = FakeGitHub()
        self.assertEqual(bb.chat_scan(dc, gh, BOT, '555', now_ms=NOW, runner=lambda **kw: {'reports': []}), [])
        self.assertEqual((gh.list, dc.posts), ([], []))


class Notify(unittest.TestCase):
    def issue(self, n, closed_at, labels=(), reason='completed'):
        return {'number': n, 'title': 'T%d' % n, 'state': 'closed', 'state_reason': reason, 'closed_at': closed_at,
                'labels': [{'name': l} for l in labels], 'body': '<!-- discord-thread:7%d -->' % n}

    def test_release(self):
        issues = [self.issue(1, '2026-11-20T10:00:00Z'), self.issue(2, '2026-11-20T10:00:00Z', ['notified']),
                  self.issue(3, '2026-11-20T10:00:00Z', reason='not_planned'), self.issue(4, '2026-11-25T10:00:00Z')]
        gh = FakeGitHub(issues)
        dc = FakeDiscord({'71': ({}, [])})
        out = bb.notify(dc, gh, release='v0.2.3', release_time_s=bb._iso_s('2026-11-21T00:00:00Z'))
        self.assertEqual([o['issue'] for o in out], [1])
        self.assertIn('v0.2.3', dc.posts[0][1])
        self.assertIn('notified', [l['name'] for l in issues[0]['labels']])


if __name__ == '__main__':
    unittest.main()
