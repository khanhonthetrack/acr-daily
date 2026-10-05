"""The one-click update: download + checks + swap, against a local web server and a fake 'running exe'."""
import functools
import hashlib
import http.server
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acr_daily import updater  # noqa: E402

NEW = b'MZ' + os.urandom(1_200_000)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class UpdaterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = tempfile.mkdtemp()
        with open(os.path.join(cls.web, 'ACR-Daily.exe'), 'wb') as f:
            f.write(NEW)
        with open(os.path.join(cls.web, 'ACR-Daily.exe.sha256'), 'w') as f:
            f.write(hashlib.sha256(NEW).hexdigest())
        with open(os.path.join(cls.web, 'bad.exe'), 'wb') as f:
            f.write(NEW)
        with open(os.path.join(cls.web, 'bad.exe.sha256'), 'w') as f:
            f.write('0' * 64)
        with open(os.path.join(cls.web, 'html.exe'), 'wb') as f:
            f.write(b'<html>' + b' ' * 1_200_000)
        with open(os.path.join(cls.web, 'html.exe.sha256'), 'w') as f:
            f.write(hashlib.sha256(b'<html>' + b' ' * 1_200_000).hexdigest())
        cls.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=cls.web))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d/' % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.exe = os.path.join(self.dir, 'ACR-Daily.exe')
        with open(self.exe, 'wb') as f:
            f.write(b'MZ old version')
        self.patches = [mock.patch.object(sys, 'frozen', True, create=True),
                        mock.patch.object(sys, 'executable', self.exe)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_download_checks_and_swaps(self):
        seen = []
        new = updater.download(self.base + 'ACR-Daily.exe', progress=seen.append)
        self.assertEqual(new, self.exe + '.new')
        self.assertTrue(seen and seen[-1] == 1.0)
        with mock.patch.object(updater.subprocess, 'Popen') as popen:
            updater.install_and_restart(new)
        with open(self.exe, 'rb') as f:
            self.assertEqual(f.read(), NEW)                      # new version in place
        with open(self.exe + '.old', 'rb') as f:
            self.assertEqual(f.read(), b'MZ old version')        # old one kept until the next start
        self.assertEqual(popen.call_args[0][0], [self.exe, '--updated'])   # and the new one started
        self.assertEqual(popen.call_args[1]['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        updater.cleanup_old()
        self.assertFalse(os.path.exists(self.exe + '.old'))

    def test_checksum_mismatch_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, 'damaged'):
            updater.download(self.base + 'bad.exe')
        self.assertFalse(os.path.exists(self.exe + '.new'))

    def test_error_page_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, 'not a Windows program'):
            updater.download(self.base + 'html.exe')

    def test_no_checksum_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, 'checksum'):
            updater.download(self.base + 'missing.exe')

    def test_failed_swap_puts_the_old_version_back(self):
        new = updater.download(self.base + 'ACR-Daily.exe')
        real = os.replace

        def fail_second(a, b):
            if a == new:
                raise PermissionError('locked')
            return real(a, b)
        with mock.patch.object(updater.os, 'replace', side_effect=fail_second), \
                mock.patch.object(updater.subprocess, 'Popen') as popen:
            with self.assertRaises(updater.UpdateError):
                updater.install_and_restart(new)
        with open(self.exe, 'rb') as f:
            self.assertEqual(f.read(), b'MZ old version')
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
