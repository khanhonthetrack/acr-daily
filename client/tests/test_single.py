"""One ACR Daily at a time (single.py): a second copy is told the app is open and quits; the updater's new copy waits
for the old one to go. On a stand-in for Windows' kernel32."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import single  # noqa: E402


class FakeKernel:
    """Named mutexes as Windows keeps them: CreateMutexW opens the existing one (last error 183) or makes it."""

    def __init__(self, held_until=None, clock=None):
        self.held_until, self.clock = held_until, clock     # another copy holds it until then (None: never)
        self.err, self.handles, self.closed = 0, 0, []

    def CreateMutexW(self, attrs, owner, name):
        assert name == single.NAME
        self.handles += 1
        other = self.held_until is not None and (self.held_until == 'forever' or self.clock() < self.held_until)
        self.err = single.ERROR_ALREADY_EXISTS if other else 0
        return self.handles

    def CloseHandle(self, h):
        self.closed.append(h)

    def last_error(self):
        return self.err


class OneCopy(unittest.TestCase):
    def setUp(self):
        self.t = [0.0]
        self.addCleanup(setattr, single, '_held', None)

    def go(self, k, wait_s=0.0):
        def sleep(s):
            self.t[0] += s
        return single.acquire(wait_s, kernel32=k, last_error=k.last_error, sleep=sleep, clock=lambda: self.t[0])

    def test_the_first_copy_holds_it(self):
        k = FakeKernel()
        self.assertTrue(self.go(k))
        self.assertEqual((single._held, k.closed), (1, []))

    def test_a_second_copy_is_refused_at_once(self):
        k = FakeKernel('forever')
        self.assertFalse(self.go(k))
        self.assertEqual((single._held, k.closed, self.t[0]), (None, [1], 0.0))

    def test_the_updaters_new_copy_waits_for_the_old_one_to_quit(self):
        k = FakeKernel(held_until=3.0, clock=lambda: self.t[0])
        self.assertTrue(self.go(k, wait_s=20.0))
        self.assertGreaterEqual(self.t[0], 3.0)
        self.assertEqual(single._held, k.handles)

    def test_an_old_copy_that_never_quits(self):
        k = FakeKernel('forever')
        self.assertFalse(self.go(k, wait_s=20.0))
        self.assertGreaterEqual(self.t[0], 20.0)

    def test_no_mutex_at_all_still_starts(self):
        k = FakeKernel()
        k.CreateMutexW = lambda *a: 0
        self.assertTrue(self.go(k))


if __name__ == '__main__':
    unittest.main()
