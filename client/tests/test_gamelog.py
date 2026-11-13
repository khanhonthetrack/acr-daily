"""The game's log sent with a run the game lost (gamelog.py): the right session's log, its start and end, without who
and where, filed as a bug report the server takes (server/src/reports.js checkReport)."""
import datetime
import gzip
import os
import re
import tempfile
import unittest
from unittest import mock

from acr_daily import gamelog, settings, waiting

T0 = 1794544674.4259543                       # 13 Nov 2026: a daily's stage clock started (the PC's time)
ENV = {'USERPROFILE': r'C:\Users\Khanh', 'USERNAME': 'Khanh', 'COMPUTERNAME': 'DESKTOP-AB12CD'}


def opened(t):
    """Unreal's first line for a session that started at unix time t (this PC's time)."""
    return 'Log file open, %s\n' % datetime.datetime.fromtimestamp(t).strftime('%m/%d/%y %H:%M:%S')


def stamp(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('[%Y.%m.%d-%H.%M.%S:123][  0]')


class FakeApi:
    def __init__(self, token='a' * 64):
        self.s, self.configured, self.reports, self.files = {'token': token}, True, [], []

    def report(self, fields):
        self.reports.append(fields)
        return 40 + len(self.reports)

    def report_file(self, rid, data, name, kind='log', size=None):
        self.files.append((rid, gzip.decompress(data).decode('utf-8'), name, kind, size))


def lost(**kw):
    return [dict({'id': 'daily:2026-11-13/1:%s' % T0, 'what': 'SS1 2026-11-13', 'stage': 'MonteCarloS1BolleneCut3Forward',
                  'car': 'LanciaRally037Evo2', 'startedAt': T0, 'clockMs': 238137,
                  'why': 'the game closed before saving its official result'}, **kw)]


class Logs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        p = mock.patch('acr_daily.settings.DIR', tempfile.mkdtemp())      # (official.log: waiting.note)
        p.start()
        self.addCleanup(p.stop)
        gamelog._sent.clear()

    def log(self, name, text, mtime=None):
        path = os.path.join(self.dir, name)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        if mtime:
            os.utime(path, (mtime, mtime))
        return path

    def test_the_session_the_run_was_driven_in(self):
        """The game started again since: the run's session is the backup that started last before the run."""
        self.log('acr.log', opened(T0 + 900) + 'the next session\n')
        self.log('acr-backup-2026.11.13-04.55.10.log', opened(T0 - 600) + 'the stuck one\n')
        self.log('acr-backup-2026.11.12-20.00.00.log', opened(T0 - 86400) + 'yesterday\n')
        self.log('cefdebug.log', opened(T0 - 60))                    # (not the game's own log)
        self.assertTrue(gamelog.session_log(T0, self.dir).endswith('acr-backup-2026.11.13-04.55.10.log'))
        self.log('acr.log', opened(T0 - 300) + 'still running\n')   # not started again: acr.log itself
        self.assertTrue(gamelog.session_log(T0, self.dir).endswith('acr.log'))

    def test_logs_without_their_start_line_go_by_when_they_were_written(self):
        self.log('acr-backup-a.log', 'x\n', mtime=T0 - 3600)
        self.log('acr-backup-b.log', 'x\n', mtime=T0 + 700)
        self.log('acr.log', 'x\n', mtime=T0 + 5000)
        self.assertTrue(gamelog.session_log(T0, self.dir).endswith('acr-backup-b.log'))
        self.assertIsNone(gamelog.session_log(T0, os.path.join(self.dir, 'none')))

    def test_its_start_and_its_end_in_whole_lines(self):
        lines = ['%06d %s' % (i, 'x' * 40) for i in range(30000)]
        path = self.log('acr.log', '\n'.join(lines) + '\n')
        text, size = gamelog.read_part(path, head=4096, tail=8192)
        self.assertEqual(size, os.path.getsize(path))
        first, rest = text.split('\n[... ', 1)
        kept, last = rest.split(' ...]\n\n', 1)
        self.assertTrue(first.startswith('000000 ') and first.endswith('\n'))
        self.assertTrue(all(re.fullmatch(r'\d{6} x{40}', ln) for ln in first.splitlines() + last.splitlines()))
        self.assertTrue(last.endswith('029999 ' + 'x' * 40 + '\n'))
        self.assertIn('KB of the log left out', kept)
        small = self.log('acr-backup-small.log', 'one\ntwo\n')
        self.assertEqual(gamelog.read_part(small), ('one\ntwo\n', 8))

    def test_who_and_where_are_taken_out(self):
        text = ('LogInit: Computer: DESKTOP-AB12CD\nLogInit: User: Khanh\n'
                'LogInit: User Dir: C:/Users/khanh/AppData/Local/acr/Saved/\n'
                r'LogPakFile: C:\Users\Khanh\AppData\Local\acr\Saved\Config' + '\n'
                'LogInit: Command Line: -AUTH_PASSWORD=secret123 -epicusername="Khanh Nguyen" -dx12\n'
                'LogTemp: acr.exe Khanhs KhanhCar stays\n')
        out = gamelog.scrub(text, ENV)
        for gone in ('DESKTOP-AB12CD', 'User: Khanh', '/Users/khanh', r'\Users\Khanh', 'secret123', 'Nguyen'):
            self.assertNotIn(gone, out)
        self.assertIn('LogInit: Computer: <PC>', out)
        self.assertIn('%USERPROFILE%/AppData/Local/acr/Saved/', out)
        self.assertIn('-dx12', out)
        self.assertIn('acr.exe Khanhs KhanhCar stays', out)                # (only the name itself)

    def test_what_the_log_says_about_itself(self):
        text = ('[2026.11.13-04.30.00:001][  0]LogInit: OS: Windows 11 (24H2) [10.0.26100.4202] (), CPU: AMD Ryzen 7 '
                '7800X3D 8-Core Processor           , GPU: NVIDIA GeForce RTX 4080\n'
                '[2026.11.13-04.42.07:123][900]LogLoad: LoadMap: /Game/Maps/ServicePark\n')
        self.assertEqual(gamelog.system_of(text), 'OS: Windows 11 (24H2) [10.0.26100.4202] (), CPU: AMD Ryzen 7 7800X3D '
                                                  '8-Core Processor , GPU: NVIDIA GeForce RTX 4080')
        self.assertEqual(gamelog.last_stamp(text), '2026.11.13-04.42.07')
        self.assertIn('ended from outside', gamelog.ending(text))
        self.assertIn('quit the normal way', gamelog.ending(text + 'Log file closed, 11/13/26 13:54:38\n'))
        self.assertIn('crash', gamelog.ending(text + 'LogWindows: Error: === Critical error: ===\n'))

    def test_a_lost_run_files_a_report_with_the_sessions_log(self):
        waiting.note('daily:2026-11-13/1:%s: finished (MonteCarloS1BolleneCut3Forward, LanciaRally037Evo2)' % T0)
        waiting.note('daily:2026-11-12/2:1794455997.58: another run')
        waiting.note('daily:2026-11-13/1:%s: DNF: the game closed before saving its official result' % T0)
        self.log('acr.log', opened(T0 - 400) + stamp(T0 - 400) + 'LogInit: OS: Windows 11, CPU: X, GPU: Y\n'
                 + stamp(T0 - 380) + r'LogInit: User Dir: C:\Users\Khanh\AppData' + '\n'
                 + stamp(T0 + 260) + 'LogLoad: the last thing the game did\n')
        api = FakeApi()
        with mock.patch.dict(os.environ, ENV):
            gamelog.send(api, lost(), 'daily', None, 'App 0.1.2: ghost cars off.', folder=self.dir).join(5)
        (f,), ((rid, text, name, kind, size),) = api.reports, api.files
        self.assertEqual((rid, name, kind, f['area'], f['appVersion']), (41, 'acr.log', 'log', 'daily', gamelog.__version__))
        self.assertEqual(size, os.path.getsize(os.path.join(self.dir, 'acr.log')))      # (its size before packing)
        self.assertIn('the last thing the game did', text)
        self.assertNotIn('Khanh', text)
        self.assertEqual(f['system'], 'OS: Windows 11, CPU: X, GPU: Y')
        self.assertIn('SS1 2026-11-13', f['title'])
        body = f['body']
        for said in ('MonteCarloS1BolleneCut3Forward', 'stage clock 3:58.137', 'the game closed before saving',
                     'Its last line: [%s]' % stamp(T0 + 260)[1:20], 'ended from outside', 'ghost cars off',
                     'finished (MonteCarloS1BolleneCut3Forward'):
            self.assertIn(said, body)
        self.assertNotIn('another run', body)                       # (only this run's notes)
        # within what the server takes (src/reports.js checkReport)
        self.assertTrue(4 <= len(f['title']) <= 120 and 10 <= len(body) <= 5000)
        self.assertTrue(len(f['happened']) <= 60 and len(f['system']) <= 200)
        self.assertRegex(f['appVersion'], r'^\d{1,3}\.\d{1,3}\.\d{1,3}$')
        with open(os.path.join(settings.DIR, 'official.log'), encoding='utf-8') as fh:
            self.assertIn("the game's log sent to ACR Daily (report #41, acr.log)", fh.read())

    def test_one_copy_of_a_sessions_log(self):
        self.log('acr.log', opened(T0 - 400) + 'x\n')
        api = FakeApi()
        gamelog.send(api, lost(), 'daily', folder=self.dir).join(5)
        gamelog.send(api, lost(id='tt:tt-1:%s' % (T0 + 600), what='TT1 (tt-1)', startedAt=T0 + 600), 'time trial',
                     folder=self.dir).join(5)
        self.assertEqual((len(api.reports), len(api.files)), (2, 1))
        self.assertIn('went with report #41', api.reports[1]['body'])

    def test_without_a_log_the_report_still_says_what_the_app_saw(self):
        api = FakeApi()
        gamelog.send(api, lost(), 'daily', folder=os.path.join(self.dir, 'none')).join(5)
        self.assertEqual(api.files, [])
        self.assertIn("The game's log: none found in %LOCALAPPDATA%", api.reports[0]['body'])

    def test_nothing_is_sent_signed_out_and_a_failure_is_noted(self):
        self.assertIsNone(gamelog.send(FakeApi(token=''), lost(), 'daily', folder=self.dir))
        self.assertIsNone(gamelog.send(mock.Mock(), lost(), 'daily', folder=self.dir))   # (a test's stand-in api)
        api = FakeApi()
        api.report = mock.Mock(side_effect=OSError('offline'))
        told = mock.Mock()
        gamelog.send(api, lost(), 'daily', on_sent=told, folder=self.dir).join(5)
        told.assert_not_called()
        with open(os.path.join(settings.DIR, 'official.log'), encoding='utf-8') as fh:
            log = fh.read()
        self.assertIn("the game's log not sent: not signed in", log)
        self.assertIn("the game's log not sent: offline", log)


if __name__ == '__main__':
    unittest.main()
