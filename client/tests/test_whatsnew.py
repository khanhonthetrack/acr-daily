"""What's new (whatsnew.py): once per version, never on a new install, the server's words in a window."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from acr_daily import settings, whatsnew  # noqa: E402
from acr_daily.api import ApiError  # noqa: E402

ENTRY = {'version': '0.0.31', 'date': '2026-11-20', 'title': 'Something new to drive', 'photo': 'leagues',
         'changes': ['The first thing that changed, in a few plain words.', 'And a second one.']}


class Due(unittest.TestCase):
    def test_a_newer_version_than_the_one_seen(self):
        self.assertTrue(whatsnew.due('0.0.31', '0.0.32', False, True))
        self.assertTrue(whatsnew.due('0.0.9', '0.0.10', False, False))          # (as numbers)

    def test_the_same_or_an_older_one_never(self):
        self.assertFalse(whatsnew.due('0.0.31', '0.0.31', True, True))
        self.assertFalse(whatsnew.due('0.0.32', '0.0.31', True, True))

    def test_none_seen_yet_updated_or_used_before_but_not_a_new_install(self):
        self.assertTrue(whatsnew.due('', '0.0.31', True, False))               # the updater started it
        self.assertTrue(whatsnew.due(None, '0.0.31', False, True))             # signed in already: updated by hand
        self.assertFalse(whatsnew.due(None, '0.0.31', False, False))           # a new install


class Check(unittest.TestCase):
    def app(self, **s):
        a = mock.Mock()
        a.s = dict(s)
        return a

    def run_check(self, a, version='0.0.31', updated=False, answer=None, error=None):
        a.api.changelog.side_effect = error
        a.api.changelog.return_value = answer
        shown = []
        with mock.patch('acr_daily.whatsnew.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)), \
                mock.patch('acr_daily.app.ui', side_effect=lambda root, fn, *x: fn(*x)), \
                mock.patch('acr_daily.whatsnew.show', side_effect=lambda app, e: shown.append(e)), \
                mock.patch.object(settings, 'save') as save:
            whatsnew.check(a, version, updated)
        return shown, save

    def test_updated_shows_the_servers_entry(self):
        a = self.app(seenVersion='0.0.30', token='t')
        shown, _ = self.run_check(a, answer=ENTRY)
        self.assertEqual(shown, [ENTRY])
        a.api.changelog.assert_called_once_with('0.0.31')

    def test_a_new_install_is_not_shown_and_counts_as_seen(self):
        a = self.app()
        shown, save = self.run_check(a)
        self.assertEqual(shown, [])
        a.api.changelog.assert_not_called()
        self.assertEqual(a.s['seenVersion'], '0.0.31')
        save.assert_called_once()

    def test_seen_already_nothing_asked(self):
        a = self.app(seenVersion='0.0.31', token='t')
        shown, save = self.run_check(a, updated=True)
        self.assertEqual(shown, [])
        a.api.changelog.assert_not_called()
        save.assert_not_called()

    def test_no_entry_on_the_server_not_asked_again(self):
        a = self.app(seenVersion='0.0.30')
        shown, _ = self.run_check(a, error=ApiError('no changelog for that version', 404))
        self.assertEqual(shown, [])
        self.assertEqual(a.s['seenVersion'], '0.0.31')

    def test_offline_asked_again_next_start(self):
        a = self.app(seenVersion='0.0.30')
        shown, save = self.run_check(a, error=ApiError('server not reachable (timed out)'))
        self.assertEqual(shown, [])
        self.assertEqual(a.s['seenVersion'], '0.0.30')
        save.assert_not_called()


class Window(unittest.TestCase):
    """The window itself: the photo, the headline, each line, the two buttons."""

    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        from acr_daily.app import App
        a = App.__new__(App)
        a.root, a.s = self.root, {}
        a.api = mock.Mock(site='https://acrdaily.com')
        self.a = a

    def texts(self, widget):
        out = []
        for w in widget.winfo_children():
            if hasattr(w, 'cget'):
                try:
                    out.append(w.cget('text'))
                except Exception:
                    pass
            out += self.texts(w)
        return out

    def test_built_and_seen(self):
        with mock.patch.object(settings, 'save'):
            d = whatsnew.show(self.a, ENTRY)
        self.assertEqual(self.a.s['seenVersion'], '0.0.31')
        cv = d.banner
        self.assertEqual(cv.itemcget('title', 'text'), ENTRY['title'].upper())
        self.assertEqual(cv.itemcget('kick', 'text'), "WHAT'S NEW IN 0.0.31")
        words = self.texts(d.win)
        for line in ENTRY['changes']:
            self.assertIn(line, words)
        self.assertIn("LET'S DRIVE", words)
        self.assertIn('MORE ON THE WEBSITE', words)
        if whatsnew.photos.Image is not None:
            self.assertTrue(cv.find_withtag('all') and getattr(cv, 'image', None), 'the photo')

    def test_the_website_button_opens_this_versions_changelog_and_closes(self):
        with mock.patch.object(settings, 'save'):
            d = whatsnew.show(self.a, dict(ENTRY, photo='not-a-photo'))   # (an unknown photo: the default one)
        with mock.patch('acr_daily.whatsnew.webbrowser.open') as op:
            d.website()
        op.assert_called_once_with('https://acrdaily.com/changelog#v0.0.31')
        self.assertFalse(d.win.winfo_exists())


if __name__ == '__main__':
    unittest.main()
