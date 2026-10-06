"""Matching the car name the game reports with the daily's car (same rules as server/src/cars.js).

The game reports e.g. "Mini Cooper S 1275"; its internal id is "MiniCooperS1275". Names for cars nobody has
driven yet are best guesses, so the match is lenient: same model numbers and nearly the same letters
("Peugeot 306 Maxi" = "Peugeot 306 II Maxi"), but never a different model number ("124" is not "131")."""
import re
import unicodedata


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).lower()
    return re.sub(r'[^a-z0-9]', '', s)


def _digits(s):
    return re.sub(r'[^0-9]', '', norm(s))


def _ratio(a, b):
    """2 * longest common subsequence / total length (like the server)."""
    if not a and not b:
        return 1.0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b):
            cur.append(prev[j] + 1 if ca == cb else max(prev[j + 1], cur[j]))
        prev = cur
    return 2.0 * prev[-1] / (len(a) + len(b))


def same_car(reported, challenge):
    """challenge: the daily ({'car', 'carId', 'carAliases'})."""
    r = norm(reported)
    if not r:
        return False
    names = [challenge.get('car'), challenge.get('carId')] + list(challenge.get('carAliases') or [])
    names = [n for n in names if n]
    if any(norm(n) == r for n in names):
        return True
    return any(_digits(n) == _digits(reported) and _ratio(norm(n), r) >= 0.85 for n in names)


TRACK_CHARS = 32   # the game's telemetry cuts the stage name off after 32 characters


def same_track(reported, challenge):
    """'Monte Carlo St. Geniez - Sistero' (cut off by the game) is 'Monte Carlo St. Geniez - Sisteron'."""
    r, t = norm(reported), norm(challenge.get('track'))
    if r == t:
        return True
    return len(str(reported or '')) >= TRACK_CHARS and len(r) >= 10 and t.startswith(r)
