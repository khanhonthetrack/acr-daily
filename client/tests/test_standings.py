import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily.standings import standing  # noqa: E402

BOARD = [
    {'steamId': 'a', 'name': 'Ann', 'totalMs': 200000, 'splits': [50000, 100000, 150000]},
    {'steamId': 'b', 'name': 'Bob', 'totalMs': 205000, 'splits': [51000, 102000, 154000]},
    {'steamId': 'me', 'name': 'Me', 'totalMs': 210000, 'splits': [52000, 104000, 158000]},
    {'steamId': 'c', 'name': 'Cid', 'totalMs': 220000, 'splits': [53000, 106000, 160000]},
    {'steamId': 'd', 'name': 'Dee', 'totalMs': 230000, 'splits': None},
]


class Standing(unittest.TestCase):
    def test_split_middle_of_the_field(self):
        s = standing(BOARD, 'me', 101000, split=1)
        self.assertEqual((s['pos'], s['of']), (2, 4))          # Dee has no split data, own old run excluded
        self.assertEqual(s['gapLeader'], 1000)
        self.assertEqual([r[1] for r in s['rows']], ['Ann', 'YOU', 'Bob', 'Cid'])
        self.assertEqual(s['pbGap'], 101000 - 104000)

    def test_leading(self):
        s = standing(BOARD, 'me', 49000, split=0)
        self.assertEqual(s['pos'], 1)
        self.assertEqual(s['rows'][0], (1, 'YOU', 0, True))

    def test_last_at_finish(self):
        s = standing(BOARD, 'me', 240000)
        self.assertEqual((s['pos'], s['of']), (5, 5))
        self.assertEqual(s['rows'][-1][1], 'YOU')
        self.assertEqual(s['rows'][0][1], 'Ann')

    def test_tie_goes_to_the_earlier_driver(self):
        s = standing(BOARD, 'me', 51000, split=0)
        self.assertEqual(s['pos'], 3)

    def test_empty_field(self):
        s = standing([], 'me', 60000, split=0)
        self.assertEqual((s['pos'], s['of'], s['gapLeader']), (1, 1, 0))


if __name__ == '__main__':
    unittest.main()
