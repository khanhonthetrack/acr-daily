"""RANKED's chat (rankedchat.py, ig_ranked.chat_part): lines in by id, the cursor from what was asked for, sending, the
switch; the page's tree."""
import threading
import unittest
from unittest import mock

from acr_daily import rankedchat
from acr_daily.ingamekit import check


class Now(threading.Thread):
    """(tests) a thread run at once, where it is started."""
    def __init__(self, target=None, daemon=None):
        self.fn = target

    def start(self):
        self.fn()


def app():
    a = mock.Mock()
    a.s = {'token': 't', 'steamId': 's1'}
    a.api.live_chat.return_value = {'messages': [{'id': 3, 'steamId': 's2', 'name': 'Bob', 'body': 'hi', 'at': 1},
                                                 {'id': 5, 'steamId': 's1', 'name': 'Me', 'body': 'yo', 'at': 2}],
                                    'pollS': 4}
    a.api.live_chat_send.return_value = {'message': {'id': 9, 'steamId': 's1', 'name': 'Me', 'body': 'go', 'at': 3}}
    return a


class Chat(unittest.TestCase):
    def setUp(self):
        p = mock.patch('acr_daily.rankedchat.threading.Thread', Now)
        p.start()
        self.addCleanup(p.stop)

    def test_lines_in_and_sent(self):
        a, mem, key = app(), {}, ('rally2', 1000)
        st = rankedchat.state(mem, key)
        rankedchat.poll(a, st, key)
        self.assertEqual([x['id'] for x in st['lines']], [3, 5])
        self.assertEqual(st['last'], 5)
        rankedchat.poll(a, st, key)                  # (too soon: not asked again)
        self.assertEqual(a.api.live_chat.call_count, 1)
        st['draft'] = '  go  '
        rankedchat.send(a, st, key)
        a.api.live_chat_send.assert_called_once_with('rally2', 1000, 'go')
        self.assertEqual([x['id'] for x in st['lines']], [3, 5, 9])
        self.assertEqual((st['draft'], st['last']), ('', 5))     # (the cursor from what was asked for only)
        rankedchat.poll(a, st, key)                  # (after a send: asked at once)
        self.assertEqual(a.api.live_chat.call_args[0], ('rally2', 1000, 5))

    def test_refused_says_why(self):
        a, mem, key = app(), {}, ('rally2', 1000)
        a.api.live_chat_send.side_effect = Exception('too fast')
        st = rankedchat.state(mem, key)
        st['draft'] = 'x'
        rankedchat.send(a, st, key)
        self.assertEqual((st['note'], st['draft']), ('too fast', 'x'))

    def test_the_switch(self):
        a = app()
        self.assertTrue(rankedchat.on(a))
        with mock.patch('acr_daily.settings.save'):
            rankedchat.toggle(a)
        self.assertFalse(rankedchat.on(a))


class OnStage(unittest.TestCase):
    """The chat over the stage (ig_chat.py): my session's lines, scrolled back with Page Up, a line typed sent."""
    def ig(self):
        ig = mock.Mock()
        ig.app = app()
        ig.app._lr_registered.return_value = ('rally2', 1000)
        ig.app._lr_following.return_value = ('rally2', 1000)       # (its rally the one driven)
        ig.app.watch = None                                          # (not watching)
        ig.app.lr_data = {('rally2', 1000): {'phase': 'running'}}
        mem = {}
        ig.mem = lambda k: mem.setdefault(k, {})
        return ig

    def test_tree_and_keys(self):
        from acr_daily import ig_chat
        ig = self.ig()
        st = rankedchat.state(ig.mem('live'), ('rally2', 1000))
        rankedchat.take(st, [{'id': i, 'steamId': 's2', 'name': 'Bob', 'body': 'line %d' % i, 'at': i} for i in range(20)])
        st['at'] = 1e18                                 # (not asked in the test)
        node = ig_chat.overlay(ig)
        self.assertEqual(check(node), [])
        self.assertIn('line 19', str(node))
        ig_chat.key(ig, 'up')
        node = ig_chat.overlay(ig)
        self.assertNotIn('line 19', str(node))
        self.assertIn('3 newer below', str(node))
        ig.app.s['rankedChat'] = False                  # (off in SETTINGS)
        self.assertIsNone(ig_chat.overlay(ig))
        ig.app.s['rankedChat'] = True
        ig.app.lr_data[('rally2', 1000)]['phase'] = 'over'
        self.assertIsNone(ig_chat.overlay(ig))          # (the session over: no chat on the stage)

    def test_not_on_another_stage(self):
        """Registered for a ranked hour but driving a time trial or a daily: no chat (the user, 28 Nov 2026)."""
        from acr_daily import ig_chat
        ig = self.ig()
        rankedchat.state(ig.mem('live'), ('rally2', 1000))['at'] = 1e18
        self.assertIsNotNone(ig_chat.overlay(ig))
        ig.app._lr_following.return_value = None
        self.assertIsNone(ig_chat.overlay(ig))
        with mock.patch('acr_daily.rankedchat.threading.Thread', Now):
            ig_chat.send(ig, 'hello')
        ig.app.api.live_chat_send.assert_not_called()

    def test_its_turn_off_button(self):
        from acr_daily import ig_chat
        ig = self.ig()
        rankedchat.state(ig.mem('live'), ('rally2', 1000))['at'] = 1e18
        self.assertIn("'chat:off'", str(ig_chat.overlay(ig)))
        with mock.patch('acr_daily.settings.save'):
            ig_chat.key(ig, 'off')
        self.assertFalse(rankedchat.on(ig.app))
        self.assertIsNone(ig_chat.overlay(ig))

    def test_with_watch_s_broadcast(self):
        """Watching meanwhile: the chat lower and shorter; with the broadcast, each layer across the whole screen (a
        stack's layers sit top left at their smallest: the dash and the driver bar came up to the middle, 28 Nov 2026)."""
        from acr_daily import ig_chat
        from acr_daily.ingameapp import InGameApp
        ig = self.ig()
        st = rankedchat.state(ig.mem('live'), ('rally2', 1000))
        rankedchat.take(st, [{'id': i, 'steamId': 's2', 'name': 'Bob', 'body': 'line %d' % i, 'at': i} for i in range(20)])
        st['at'] = 1e18
        node = ig_chat.overlay(ig)
        self.assertIn('line 12', str(node))
        self.assertEqual(node['c'][-1].get('h'), ig_chat.BOTTOM)
        ig.app.watch = mock.Mock(on=True)
        node = ig_chat.overlay(ig)
        self.assertNotIn('line 13', str(node))
        self.assertIn('line 14', str(node))
        self.assertEqual(node['c'][-1].get('h'), ig_chat.BOTTOM_WATCHING)
        self_ = mock.Mock()
        self_._in_menus.return_value = False
        self_.app._on_stage.return_value = True
        self_.watch_overlay.return_value = {'t': 'col', 'c': []}
        with mock.patch.object(ig_chat, 'overlay', return_value={'t': 'col', 'c': [{'t': 'sp'}]}):
            tree = InGameApp.stage_overlay(self_)
        self.assertEqual(tree['t'], 'stack')
        self.assertEqual([(x.get('al'), x.get('va')) for x in tree['c']], [('f', 'f'), ('f', 'f')])

    def test_a_line_typed_on_the_stage(self):
        from acr_daily import ig_chat
        ig = self.ig()
        with mock.patch('acr_daily.rankedchat.threading.Thread', Now):
            ig_chat.send(ig, 'hello all')
        ig.app.api.live_chat_send.assert_called_once_with('rally2', 1000, 'hello all')


if __name__ == '__main__':
    unittest.main()
