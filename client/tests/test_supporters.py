"""The launcher's thank-you bar (acr_daily/supporters.py): the current supporters' names roll by, nobody yet asks for
support, the server down keeps the list as it was, SUPPORT opens only a Buy Me a Coffee address."""
import tkinter as tk
import unittest
from unittest import mock

from acr_daily import supporters


class FakeApi:
    def __init__(self, r):
        self.r = r

    def supporters(self):
        if isinstance(self.r, Exception):
            raise self.r
        return self.r


class FakeApp:
    def __init__(self, root, r):
        self.root = root
        self.api = FakeApi(r)


class SupportBarTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.geometry('520x40')

    def tearDown(self):
        self.root.destroy()

    def bar(self, r):
        with mock.patch.object(supporters.threading, 'Thread') as T:
            b = supporters.SupportBar(self.root, FakeApp(self.root, r), 'Segoe UI', 'Segoe UI')
            b.f.pack(fill='x')
            T.call_args.kwargs['target']()          # (the server asked, here and now)
        self.root.update()
        return b

    def words(self, b):
        return [b.cv.itemcget(i, 'text') for i in b.cv.find_all()]

    def test_names_roll(self):
        b = self.bar({'url': 'https://buymeacoffee.com/acrdaily', 'supporters': [{'name': 'Kim', 'kind': 'member'},
                                                                                 {'name': 'Alex', 'kind': 'coffee'}]})
        w = self.words(b)
        self.assertEqual(w.count('Kim'), 2)          # (two copies, rolling round)
        self.assertIn('Alex', w)
        x0 = b.cv.coords(b.cv.find_withtag('roll')[0])[0]
        for _ in range(5):
            b._tick()
        self.assertLess(b.cv.coords(b.cv.find_withtag('roll')[0])[0], x0)

    def test_nobody_yet_asks_for_support(self):
        b = self.bar({'url': 'https://buymeacoffee.com/acrdaily', 'supporters': []})
        self.assertEqual(len(self.words(b)), 1)
        self.assertIn('coffee', self.words(b)[0])

    def test_server_down_keeps_the_list(self):
        b = self.bar({'supporters': [{'name': 'Kim'}]})
        b._got(None)
        self.root.update()
        self.assertIn('Kim', self.words(b))

    def test_support_opens_buy_me_a_coffee_only(self):
        b = self.bar({'url': 'https://evil.example/x', 'supporters': []})
        with mock.patch.object(supporters.webbrowser, 'open') as op:
            b.open()
        op.assert_called_once_with('https://buymeacoffee.com/acrdaily')

    def test_the_button_is_buy_me_a_coffees_own(self):
        b = self.bar({'supporters': []})
        self.assertTrue(b.btn.cget('image'))
        self.assertEqual(b._btn_pic.height(), round(supporters.BTN_H * b.k))

    def test_line_of(self):
        self.assertIsNone(supporters.line_of([]))
        names = [t for t, is_name in supporters.line_of([{'name': 'A'}, {}]) if is_name]
        self.assertEqual(names, ['A', 'Someone'])


if __name__ == '__main__':
    unittest.main()
