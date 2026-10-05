"""A stage route: the reference line from start to finish, as [[x, z], ...] in world metres."""
import math

CHECKPOINT_EVERY_M = 100.0


class Route:
    def __init__(self, points):
        self.points = [(float(p[0]), float(p[1])) for p in points]
        self.cum = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            self.cum.append(self.cum[-1] + math.dist(a, b))
        self.length = self.cum[-1] if self.cum else 0.0
        # checkpoints: route indices every ~100 m (not the very start and end)
        self.checkpoints = []
        nxt = CHECKPOINT_EVERY_M
        for i, c in enumerate(self.cum):
            if c >= nxt and self.length - c > CHECKPOINT_EVERY_M / 2:
                self.checkpoints.append(i)
                nxt = c + CHECKPOINT_EVERY_M

    @property
    def start(self):
        return self.points[0]

    @property
    def end(self):
        return self.points[-1]

    def nearest(self, x, z, hint=None, window=(20, 80)):
        """Nearest route index to (x, z). With a hint, search around it first (routes can cross)."""
        pts = self.points
        best, bd = 0, float('inf')
        if hint is not None:
            lo, hi = max(0, hint - window[0]), min(len(pts) - 1, hint + window[1])
            for i in range(lo, hi + 1):
                d = (pts[i][0] - x) ** 2 + (pts[i][1] - z) ** 2
                if d < bd:
                    best, bd = i, d
            if bd <= 60 * 60:
                return best, math.sqrt(bd)
        for i, p in enumerate(pts):
            d = (p[0] - x) ** 2 + (p[1] - z) ** 2
            if d < bd:
                best, bd = i, d
        return best, math.sqrt(bd)


def thin(points, step=5.0):
    """Keep a point every `step` metres."""
    if not points:
        return []
    out, acc = [tuple(points[0])], 0.0
    for a, b in zip(points, points[1:]):
        acc += math.dist(a, b)
        if acc >= step:
            out.append(tuple(b))
            acc = 0.0
    if out[-1] != tuple(points[-1]):
        out.append(tuple(points[-1]))
    return [[round(x, 2), round(z, 2)] for x, z in out]
