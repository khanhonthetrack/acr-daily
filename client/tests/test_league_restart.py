"""A stage of a rally sent at its finish line, then started again from its results screen before the next stage: the
entry ends (a restart that would leave the stage's damage behind, the user 24 Nov 2026)."""
import types
import unittest
from unittest import mock

from acr_daily.leagueui import LeaguesUI


def frame(track, clock):
    return types.SimpleNamespace(track=track, clock_ms=clock)


class Restart(unittest.TestCase):
    def setUp(self):
        self.ui = types.SimpleNamespace(_league_failed=mock.Mock())
        self.run = {'ev': {'name': 'Cup'}, 'no': 2,
                    'sent': {'k': 1, 'track': 'Monte Carlo Sommet de Turini', 'clock': 300000,
                             'next': 'Monte Carlo La Bollène'}}

    def look(self, f):
        return LeaguesUI._league_restarted(self.ui, self.run, f)

    def test_results_screen_then_restart(self):
        self.assertFalse(self.look(frame('Monte Carlo Sommet de Turini', 300000)))   # (its results screen)
        self.assertFalse(self.look(frame('Monte Carlo Sommet de Turini', 0)))        # (on its start line again)
        self.assertTrue(self.look(frame('Monte Carlo Sommet de Turini', 1500)))      # (driven again)
        self.ui._league_failed.assert_called_once()
        self.assertEqual(self.run['no'], 1)
        self.assertIn('SS2 restarted after its finish', self.ui._league_failed.call_args[0][1])
        self.assertIsNone(self.run['sent'])

    def test_the_next_stage_is_no_restart(self):
        self.assertFalse(self.look(frame('Monte Carlo La Bollène', 1500)))
        self.ui._league_failed.assert_not_called()
        self.assertIsNone(self.run['sent'])                                        # (left behind for good)
        self.assertFalse(self.look(frame('Monte Carlo Sommet de Turini', 1500)))

    def test_nothing_sent_nothing_judged(self):
        self.run['sent'] = None
        self.assertFalse(self.look(frame('Monte Carlo Sommet de Turini', 1500)))
        self.ui._league_failed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
