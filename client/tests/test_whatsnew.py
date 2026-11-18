"""What's new (whatsnew.py): once per version, never on a new install, the server's words on a screen over the app,
with the versions skipped since the one seen last; opened again from SETTINGS and the UPDATED TO bar."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from acr_daily import settings, whatsnew  # noqa: E402
from acr_daily.api import ApiError  # noqa: E402

ENTRY = {'version': '0.0.31', 'date': '2026-11-20', 'title': 'Something new to drive', 'photo': 'leagues',
         'changes': ['The first thing that changed, in a few plain words.', 'And a second one.', 'A third, fixed.'],
         'kinds': ['new', 'better', 'fix']}
OLDER = [{'version': '0.0.30', 'date': '2026-11-18', 'title': 'The one before', 'photo': 'wales',
          'changes': ['A change in the one before.', 'Worth knowing.'], 'kinds': ['new', 'note']},
         {'version': '0.0.29', 'date': '2026-11-10', 'title': None, 'photo': None,
          'changes': ['An old line without a kind.'], 'kinds': [None]}]


def tk_or_skip(test):
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    root.withdraw()
    test.addCleanup(root.destroy)
    return root


class Due(unittest.TestCase):
    def test_a_newer_version_than_the_one_seen(self):
        self.assertTrue(whatsnew.due('0.0.31', '0.0.32', False, True))
        self.assertTrue(whatsnew.due('0.0.9', '0.0.10', False, False))          # (as numbers)
        self.assertTrue(whatsnew.due('0.1.5', '0.1.5.1', False, False))         # (a test build)

    def test_the_same_or_an_older_one_never(self):
        self.assertFalse(whatsnew.due('0.0.31', '0.0.31', True, True))
        self.assertFalse(whatsnew.due('0.0.32', '0.0.31', True, True))
        self.assertFalse(whatsnew.due('0.1.5.43', '0.1.5.43', True, True))

    def test_a_test_build_after_a_screen_under_the_release_it_led_to(self):
        # (0.1.5.42's screen said 0.1.6: the next test build asks again, the server naming it by its own number)
        self.assertTrue(whatsnew.due('0.1.6', '0.1.5.43', True, True))
        self.assertFalse(whatsnew.due('0.1.6', '0.1.5', True, True))            # (a release: never back)

    def test_none_seen_yet_updated_or_used_before_but_not_a_new_install(self):
        self.assertTrue(whatsnew.due('', '0.0.31', True, False))               # the updater started it
        self.assertTrue(whatsnew.due(None, '0.0.31', False, True))             # signed in already: updated by hand
        self.assertFalse(whatsnew.due(None, '0.0.31', False, False))           # a new install


def inline():
    """The thread run at once, the Tk thread's calls too."""
    return (mock.patch('acr_daily.whatsnew.threading.Thread', side_effect=lambda target, daemon: mock.Mock(start=target)),
            mock.patch('acr_daily.app.ui', side_effect=lambda root, fn, *x: fn(*x)))


class Check(unittest.TestCase):
    def app(self, **s):
        a = mock.Mock()
        a.s = dict(s)
        return a

    def run_check(self, a, version='0.0.31', updated=False, answer=None, error=None):
        a.api.changelog.side_effect = error
        a.api.changelog.return_value = answer
        shown = []
        thread, ui = inline()
        with thread, ui, mock.patch('acr_daily.whatsnew.show', side_effect=lambda app, e, since: shown.append((e, since))), \
                mock.patch.object(settings, 'save') as save:
            whatsnew.check(a, version, updated)
        return shown, save

    def test_updated_shows_the_servers_entry_and_the_versions_skipped(self):
        a = self.app(seenVersion='0.0.29', token='t')
        shown, _ = self.run_check(a, answer=dict(ENTRY, earlier=OLDER[:1]))
        self.assertEqual(shown, [(dict(ENTRY, earlier=OLDER[:1]), '0.0.29')])
        a.api.changelog.assert_called_once_with('0.0.31', since='0.0.29')

    def test_used_before_but_none_seen_this_version_alone(self):
        a = self.app(token='t')
        shown, _ = self.run_check(a, answer=ENTRY)
        self.assertEqual(shown, [(ENTRY, None)])
        a.api.changelog.assert_called_once_with('0.0.31', since=None)

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


class Reopen(unittest.TestCase):
    """SETTINGS › About › WHAT'S NEW and the UPDATED TO bar: this version's and the ones before it."""

    def run_reopen(self, answer=None, error=None):
        a = mock.Mock(_whatsnew_asking=False)
        a.api.site = 'https://acrdaily.com'
        a.api.changelog.side_effect = error
        a.api.changelog.return_value = answer
        thread, ui = inline()
        with thread, ui, mock.patch('acr_daily.whatsnew.show') as show, mock.patch('acr_daily.whatsnew.webbrowser.open') as op:
            whatsnew.reopen(a, '0.0.31')
        return a, show, op

    def test_the_screen_with_every_version_before(self):
        a, show, op = self.run_reopen(answer=dict(ENTRY, earlier=OLDER))
        a.api.changelog.assert_called_once_with('0.0.31', since='0')
        show.assert_called_once_with(a, dict(ENTRY, earlier=OLDER), '0')
        op.assert_not_called()
        self.assertFalse(a._whatsnew_asking)

    def test_the_server_out_of_reach_the_website(self):
        a, show, op = self.run_reopen(error=ApiError('server not reachable (timed out)'))
        show.assert_not_called()
        op.assert_called_once_with('https://acrdaily.com/changelog#v0.0.31')

    def test_asked_once_at_a_time(self):
        a = mock.Mock(_whatsnew_asking=True)
        with mock.patch('acr_daily.whatsnew.threading.Thread') as th:
            whatsnew.reopen(a, '0.0.31')
        th.assert_not_called()


class Day(unittest.TestCase):
    def test_the_day_written_out(self):
        self.assertEqual(whatsnew.day('2026-11-15'), '15 November 2026')
        self.assertEqual(whatsnew.day('soon'), 'soon')
        self.assertEqual(whatsnew.day(None), '')


class Screen(unittest.TestCase):
    """The screen itself: over the app's window, the photo, the headline, each change with its tag, the versions
    skipped, the buttons; closing; scrolling; staying over the app's own parts."""

    def setUp(self):
        import tkinter as tk
        self.tk = tk
        self.root = tk_or_skip(self)
        tk.Frame(self.root, name='under', bg='#123456').pack(fill='both', expand=True)   # the app under it
        from acr_daily.app import App
        a = App.__new__(App)
        a.root, a.s = self.root, {}
        a.api = mock.Mock(site='https://acrdaily.com')
        self.a = a

    def shown(self):
        """The window on the screen (clicks and keys reach only what is shown)."""
        self.root.geometry('900x660+0+0')
        self.root.deiconify()
        self.root.update()

    def show(self, entry=ENTRY, since=None):
        with mock.patch.object(settings, 'save'):
            d = whatsnew.show(self.a, entry, since)
        self.root.update_idletasks()
        return d

    def words(self, d, tag):
        return [d.cv.itemcget(i, 'text') for i in d.cv.find_withtag(tag)]

    def texts(self, widget):
        out = []
        for w in widget.winfo_children():
            try:
                out.append(w.cget('text'))
            except Exception:
                pass
            out += self.texts(w)
        return out

    def test_built_over_the_app_and_seen(self):
        d = self.show()
        self.assertEqual(self.a.s['seenVersion'], '0.0.31')
        self.assertIs(self.a._whatsnew, d)
        self.assertIs(self.root.winfo_children()[-1], d.win, 'over everything in the window')
        self.assertEqual(d.win.place_info()['relwidth'], '1')
        self.assertEqual(self.words(d, 'title'), [ENTRY['title'].upper()])
        self.assertEqual(self.words(d, 'kick'), ["WHAT'S NEW IN 0.0.31"])
        self.assertEqual(self.words(d, 'date'), ['20 November 2026'])
        self.assertEqual(self.words(d, 'line'), ENTRY['changes'])
        self.assertEqual([d.cv.itemcget(d.cv.find_withtag('chip-' + k)[0], 'text') for k in ENTRY['kinds']],
                         ['NEW', 'IMPROVED', 'FIXED'])
        self.assertEqual(self.words(d, 'earlier'), [], 'no versions before it asked for')
        words = self.texts(d.card)
        self.assertIn("LET'S DRIVE", words)
        self.assertIn('Full changelog on the website ›', words)
        if whatsnew.photos.Image is not None:
            self.assertTrue(d.cv.find_withtag('photo') and d._hero_img is not None, 'the photo')
            self.assertIsNotNone(d._back_img, 'the backdrop')

    def test_the_versions_skipped_under_it(self):
        d = self.show(dict(ENTRY, earlier=OLDER), '0.0.28')
        self.assertEqual(self.words(d, 'earlier'), ['ALSO NEW SINCE 0.0.28'])
        self.assertEqual(self.words(d, 'older'), ['0.0.30   ·   18 November 2026', '0.0.29   ·   10 November 2026'])
        self.assertEqual(self.words(d, 'older-title'), ['The one before'])            # (0.0.29: none)
        self.assertEqual(self.words(d, 'line'), ENTRY['changes'] + OLDER[0]['changes'] + OLDER[1]['changes'])
        self.assertEqual(len(d.cv.find_withtag('chip-note')), 1)
        opened = self.show(dict(ENTRY, earlier=OLDER), '0')
        self.assertEqual(self.words(opened, 'earlier'), ['EARLIER VERSIONS'])

    def test_an_old_server_lines_without_kinds_and_an_unknown_photo(self):
        e = {k: v for k, v in ENTRY.items() if k != 'kinds'}
        d = self.show(dict(e, photo='not-a-photo'))
        self.assertEqual(d.key, whatsnew.DEFAULT_PHOTO)
        self.assertEqual(self.words(d, 'line'), ENTRY['changes'])
        self.assertEqual(d.cv.find_withtag('chip'), ())

    def test_lets_drive_escape_and_the_cross_close_it(self):
        self.shown()
        for how in ('drive', 'escape', 'cross', 'beside'):
            d = self.show()
            self.root.update()
            if how == 'drive':
                d.drive.event_generate('<Button-1>', x=2, y=2)
            elif how == 'escape':
                d.cv.focus_force()
                self.root.update()
                d.cv.event_generate('<Escape>')
            elif how == 'cross':
                d.close()          # (the ✕'s binding: a canvas item gets no generated click)
                self.assertTrue(d.cv.find_withtag('close-x') if d.alive else True)
            else:
                d.back.event_generate('<Button-1>', x=2, y=2)
            self.root.update()
            self.assertFalse(d.alive, how)
            self.assertIsNone(self.a._whatsnew, how)
            self.assertTrue(self.root.nametowidget('under').winfo_exists())

    def test_the_website_button_opens_this_versions_changelog_and_closes(self):
        d = self.show()
        with mock.patch('acr_daily.whatsnew.webbrowser.open') as op:
            d.website()
        op.assert_called_once_with('https://acrdaily.com/changelog#v0.0.31')
        self.assertFalse(d.alive)

    def test_shown_again_the_old_one_goes(self):
        first = self.show()
        second = self.show()
        self.assertFalse(first.alive)
        self.assertTrue(second.alive)
        self.assertEqual([w for w in self.root.winfo_children() if isinstance(w, self.tk.Frame)
                          and w is not self.root.nametowidget('under')], [second.win])

    def test_a_part_of_the_app_made_after_it_goes_under_it(self):
        d = self.show()
        late = self.tk.Frame(self.root)
        late.place(x=0, y=0)
        self.assertIsNot(self.root.winfo_children()[-1], d.win)
        d._on_top()
        self.assertIs(self.root.winfo_children()[-1], d.win)

    def test_longer_than_the_window_it_scrolls_and_the_wheel_stays_on_it(self):
        self.shown()
        d = self.show(dict(ENTRY, earlier=OLDER * 4), '0')
        self.root.update()
        self.assertTrue(d.scrolls)
        self.assertEqual(d.cv.yview()[0], 0.0)
        app_wheel = mock.Mock()
        self.root.bind_all('<MouseWheel>', app_wheel)            # (a page of the app's: tiles.py's bind_all)
        self.addCleanup(self.root.unbind_all, '<MouseWheel>')
        self.assertEqual(d._wheel(mock.Mock(num=None, delta=-120)), 'break')
        self.root.update()
        self.assertGreater(d.cv.yview()[0], 0.0)
        self.assertTrue(d.cv.find_withtag('bar'), 'the bar down its edge')
        d.cv.focus_force()
        self.root.update()
        d.cv.event_generate('<End>')
        self.root.update()
        self.assertAlmostEqual(d.cv.yview()[1], 1.0, places=2)
        d.cv.event_generate('<MouseWheel>', delta=120)
        app_wheel.assert_not_called()

    def test_short_it_does_not_scroll(self):
        d = self.show()
        with mock.patch.object(whatsnew.WhatsNew, '_room', return_value=(1600, 1000)):
            d._layout()
        self.root.update()
        self.assertFalse(d.scrolls)
        d._wheel(mock.Mock(num=None, delta=-120))
        self.assertEqual(d.cv.yview()[0], 0.0)
        self.assertEqual(d.cv.find_withtag('bar'), ())

    def test_the_window_made_bigger_the_card_laid_out_again(self):
        d = self.show()
        small = int(d.cv.cget('width'))
        with mock.patch.object(whatsnew.WhatsNew, '_room', return_value=(1600, 1000)):
            d._relayout()
        self.assertGreater(int(d.cv.cget('width')), small)
        self.assertEqual(int(d.cv.cget('width')), round(whatsnew.CARD_W * d.k))
        self.assertEqual(self.words(d, 'line'), ENTRY['changes'])


if __name__ == '__main__':
    unittest.main()
