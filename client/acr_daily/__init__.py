"""ACR Daily: one stage, one car, one leaderboard per day for Assetto Corsa Rally."""
__version__ = '0.0.5'
# The User-Agent says "public": the test builds before 0.0.1 were numbered 0.1.0 to 0.15.1, above this one, and the
# server tells them apart by it (server/src/index.js, tooOld).
USER_AGENT = 'ACR-Daily/%s public' % __version__
