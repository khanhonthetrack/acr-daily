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


class Page(unittest.TestCase):
    def test_tree(self):
        from acr_daily import ig_ranked
        ig = mock.Mock()
        ig.app = app()
        mem = {}
        ig.mem = lambda k: mem.setdefault(k, {})
        ig.shown = False
        key = ('rally2', 1000)
        st = rankedchat.state(ig_ranked._mem(ig), key)
        rankedchat.take(st, [{'id': 1, 'steamId': 's2', 'name': 'Bob', 'body': 'hello ' * 30, 'at': 1}])
        node = ig_ranked.chat_part(ig, key)
        self.assertEqual(check(node), [])
        self.assertIn('live.chat_send:rally2|1000', str(node))
        ig.app.s['rankedChat'] = False
        node = ig_ranked.chat_part(ig, key)
        self.assertEqual(check(node), [])
        self.assertNotIn('chat_send', str(node))


if __name__ == '__main__':
    unittest.main()
