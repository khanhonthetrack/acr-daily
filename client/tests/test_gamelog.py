"""The game's log sent with a run the game lost (gamelog.py): the right session's log, its start and end, without who
and where, filed as a bug report the server takes (server/src/reports.js checkReport)."""
import datetime
import gzip
import os
import re
import tempfile
import unittest
from unittest import mock

from acr_daily import gamelog, gamewatch, settings, waiting

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

    def report_file(self, rid, data, name, kind='log', size=None, content_type='application/gzip'):
        if content_type == 'image/jpeg':                    # (a picture of the results screen: as it is)
            self.files.append((rid, data, name, kind, size))
        else:
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
        (f,), files = api.reports, {x[2]: x for x in api.files}
        self.assertEqual(sorted(files), ['acr-daily-diagnostics.txt', 'acr.log'])   # (the diagnostics with every report)
        rid, text, name, kind, size = files['acr.log']
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
        self.assertEqual((len(api.reports), [x[2] for x in api.files].count('acr.log')), (2, 1))
        self.assertIn('went with report #41', api.reports[1]['body'])

    def test_without_a_log_the_report_still_says_what_the_app_saw(self):
        api = FakeApi()
        gamelog.send(api, lost(), 'daily', folder=os.path.join(self.dir, 'none')).join(5)
        self.assertEqual([x[2] for x in api.files], ['acr-daily-diagnostics.txt'])
        body = api.reports[0]['body']
        self.assertIn("The game's log: none found", body)
        self.assertNotIn("the game's own log of that session", body)        # (nothing said to be attached that isn't)
        self.assertIn('Attached for ACR Daily\'s admin: diagnostics', body)

    def test_the_report_says_what_the_app_saw_and_what_windows_recorded(self):
        """13 Nov 2026: no game log on players' PCs. What the app saw of the game after the finish, Windows' own records
        of it and its crash reports go with the report instead (a summary in its body, all of it attached)."""
        done = T0 + 238.137
        watch = {'exe': None, 'events': [(T0 - 100, gamewatch.STATE_WORDS['stage']),
                                         (done + 40, 'Windows: the game is "Not Responding"'),
                                         (done + 771, gamewatch.STATE_WORDS['none']),
                                         (done + 772, 'the game ended: ' + gamewatch.exit_words(1))]}
        hang = ('Event[0]:\n  Log Name: Application\n  Source: Application Hang\n  Event ID: 1002\n  Description:\n'
                '  The program acr.exe version 0.6.0 stopped interacting with Windows and was closed.\n'
                r'  Path: C:\Users\Khanh\Games\acr\Binaries\Win64\acr.exe')
        api = FakeApi()
        with mock.patch.dict(os.environ, ENV), mock.patch.object(gamelog, 'windows_events', return_value=[hang]):
            gamelog.send(api, lost(), 'daily', folder=os.path.join(self.dir, 'none'), watch=watch).join(5)
        body = api.reports[0]['body']
        for said in ('the game never left the stage', 'Not Responding" at +0:40',
                     'it ended: ended from outside (the Task Manager', 'at +12:52',
                     'Windows recorded 1 error / hang event(s) of the game'):
            self.assertIn(said, body)
        (name, packed), = [(x[2], x[1]) for x in api.files]
        self.assertEqual(name, 'acr-daily-diagnostics.txt')
        for said in ('+40 s  Windows: the game is "Not Responding"', 'Application Hang', 'stopped interacting',
                     '%USERPROFILE%'):
            self.assertIn(said, packed)
        self.assertNotIn('Khanh', packed)
        self.assertTrue(len(body) <= 5000)

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


class ResultsScreenPictures(unittest.TestCase):
    """Pictures of the game's results screen after a finish (finishshot.py): the final time and penalty, for a result
    the game lost; sent with its report, nothing else."""

    def test_a_picture_of_the_game_window_only(self):
        from acr_daily import finishshot
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow')
        big = Image.new('RGB', (3840, 2160), (200, 30, 30))
        jpeg = finishshot.shot(window=lambda: 4242, grab=lambda h: big if h == 4242 else None)
        self.assertEqual(jpeg[:3], b'\xff\xd8\xff')
        self.assertEqual(Image.open(__import__('io').BytesIO(jpeg)).size, (1600, 900))     # (made smaller, readable)
        self.assertIsNone(finishshot.shot(window=lambda: None, grab=lambda h: big))   # no game window: nothing
        self.assertIsNone(finishshot.shot(window=lambda: 1, grab=mock.Mock(side_effect=OSError('denied'))))
        s = finishshot.Shots()
        for k in range(5):
            s.add('run', 4 + k, b'jpeg%d' % k)
        self.assertEqual([a for a, _j in s.take('run')], [6, 7, 8])                   # (the last ones kept)
        self.assertEqual(s.take('run'), [])

    def test_sent_with_the_report_and_said_in_it(self):
        api = FakeApi()
        shots = [('SS1 2026-11-14 results +4s.jpg', b'\xff\xd8\xff one'), ('SS1 2026-11-14 results +9s.jpg', b'\xff\xd8\xff two')]
        gamelog.send(api, lost(resets=2), 'daily', folder=os.path.join(self.dir, 'none'), shots=shots).join(5)
        body = api.reports[0]['body']
        self.assertIn('2 picture(s) of the game after the finish', body)
        self.assertIn('2 respawn(s)', body)
        pics = [(x[2], x[3]) for x in api.files if x[3] == 'screenshot']
        self.assertEqual(pics, [('SS1 2026-11-14 results +4s.jpg', 'screenshot'), ('SS1 2026-11-14 results +9s.jpg', 'screenshot')])

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        p = mock.patch('acr_daily.settings.DIR', tempfile.mkdtemp())
        p.start()
        self.addCleanup(p.stop)


class WhatWindowsKeeps(unittest.TestCase):
    """Windows' Application log (wevtutil) and the game's crash reports, read for such a report."""

    def test_only_the_games_events_since_the_run(self):
        text = ('Event[0]:\r\n  Source: Application Error\r\n  Faulting application name: acr.exe\r\n'
                '  Faulting module name: nvwgf2umx.dll\r\n'
                'Event[1]:\r\n  Source: Application Error\r\n  Faulting application name: chrome.exe\r\n'
                'Event[2]:\r\n  Source: Application Hang\r\n  The program acr-Win64-Shipping.exe stopped\r\n')
        seen = {}

        def run(args, **kw):
            seen['args'], seen['kw'] = args, kw
            return mock.Mock(stdout=text.encode('utf-8'))
        got = gamelog.windows_events(T0, run=run, now=lambda: T0 + 900)
        self.assertEqual(len(got), 2)
        self.assertIn('nvwgf2umx.dll', got[0])
        self.assertIn('acr-Win64-Shipping.exe', got[1])
        q = next(a for a in seen['args'] if a.startswith('/q:'))
        self.assertIn('EventID=1000 or EventID=1001 or EventID=1002', q)
        self.assertIn('timediff(@SystemTime) <= 960000', q)                 # (since a minute before the run)
        self.assertEqual(gamelog.windows_events(T0, run=mock.Mock(side_effect=OSError('no wevtutil'))), [])

    def test_crash_reports_since_the_run_and_the_games_own_folder(self):
        d = tempfile.mkdtemp()
        new = os.path.join(d, 'Crashes', 'UECC-Windows-ABC')
        old = os.path.join(d, 'Crashes', 'UECC-Windows-OLD')
        for p in (new, old):
            os.makedirs(p)
        with open(os.path.join(new, 'CrashContext.runtime-xml'), 'w', encoding='utf-8') as f:
            f.write('<ErrorMessage>Fatal error: [File:D3D12Util.cpp] GPU crashed</ErrorMessage>')
        open(os.path.join(new, 'UEMinidump.dmp'), 'w').close()
        os.utime(old, (T0 - 86400, T0 - 86400))
        os.utime(new, (T0 + 300, T0 + 300))
        (name, files, ctx), = gamelog.crash_reports(T0, [d])
        self.assertEqual((name, files), ('UECC-Windows-ABC', ['CrashContext.runtime-xml', 'UEMinidump.dmp']))
        self.assertIn('GPU crashed', ctx)
        exe = os.path.join('D:', os.sep, 'Games', 'Assetto Corsa Rally', 'acr', 'Binaries', 'Win64', 'acr.exe')
        self.assertEqual(gamelog.saved_folders(exe)[1],
                         os.path.join('D:', os.sep, 'Games', 'Assetto Corsa Rally', 'acr', 'Saved'))
        self.assertEqual(gamelog.saved_folders(None), [gamelog.SAVED])


if __name__ == '__main__':
    unittest.main()
