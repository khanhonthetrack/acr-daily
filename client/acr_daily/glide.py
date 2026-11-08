"""The LIVE page's cars (liveui.py): smooth, a few seconds behind, as the website's live maps (server src/glide.js, of
which this is a port: the same behaviour, the same tests in tests/test_glide.py as server/test/glide.test.mjs).

Each app sends how far along the route its driver is every liveSendS; the page keeps each driver's last updates and
plays them back a few seconds late, along the route, so a car moves steadily on the road between two updates it already
has: it never cuts across a corner, nor stops and catches up when a check of the page's comes between two of the app's.
Times are in milliseconds.
"""
import bisect
import math


class RouteTrack:
    """A route [[x, z], ...] in game metres: at(progress) is the point that far along it (0..1 of its length, as the app
    measures progress: the route's own points, route.py)."""

    def __init__(self, pts):
        self.pts = [(float(p[0]), float(p[1])) for p in (pts or ())]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.len = self.cum[-1]

    def at(self, p):
        if not self.pts:
            return None
        if len(self.pts) == 1:
            return self.pts[0]
        d = max(0.0, min(1.0, float(p or 0))) * self.len
        lo = max(0, min(len(self.pts) - 2, bisect.bisect_right(self.cum, d) - 1))
        hi = lo + 1
        seg = self.cum[hi] - self.cum[lo]
        f = (d - self.cum[lo]) / seg if seg > 0 else 0.0
        (x0, z0), (x1, z1) = self.pts[lo], self.pts[hi]
        return (x0 + (x1 - x0) * f, z0 + (z1 - z0) * f)


class LivePlayback:
    """The playback of one map's cars. feed(drivers, server_now, now) with each answer of /api/live (each driver's
    progress, state and `updated`: when the server got it); at(id, now) -> {'p', 'state'}: where and how to show that
    driver at this computer's time `now` (None: not any more). delay: how far behind the server's clock the cars run;
    gap: two updates further apart than this (the page was closed, the app lost its connection) are not driven between:
    the car waits, then jumps. Going back along the route (a new run) is a jump too, never a drive backwards."""

    def __init__(self, delay, gap):
        self.delay, self.gap = delay, gap
        self.cars = {}
        # the server's clock - this computer's, from the quickest answer (a slow one says less: the cars never go
        # back); taken afresh when it is 5 s out (this computer's clock was set)
        self.off = None

    def time(self, now):
        return now + (self.off or 0) - self.delay

    def feed(self, drivers, server_now, now):
        o = server_now - now
        self.off = o if self.off is None or abs(o - self.off) > 5000 else max(o, self.off)
        seen, r = set(), self.time(now)
        for d in drivers or ():
            sid = str(d.get('steamId'))
            c = self.cars.setdefault(sid, {'s': [], 'gone': False})
            s = c['s']
            last = s[-1] if s else None
            t = d.get('updated') or server_now
            p = max(0.0, min(1.0, float(d.get('progress') or 0)))
            seen.add(sid)
            c['gone'] = False
            if last and t <= last['t']:                    # the same update again
                if t == last['t']:
                    last['state'] = d.get('state')
                continue
            s.append({'t': t, 'p': p, 'state': d.get('state'),
                      'jump': bool(last) and (p < last['p'] - 0.002 or t - last['t'] > self.gap)})
            k = 0          # what playback still needs: the last update before now's playback time, and those after it
            while k + 1 < len(s) and s[k + 1]['t'] <= r:
                k += 1
            del s[:k]
        for sid, c in self.cars.items():
            if sid not in seen:
                c['gone'] = True

    def at(self, sid, now):
        c = self.cars.get(str(sid))
        if not c or not c['s']:
            return None
        s, r = c['s'], self.time(now)
        if r <= s[0]['t']:                                  # not there yet: where it was first seen
            return {'p': s[0]['p'], 'state': s[0]['state']}
        i = len(s) - 1
        while i > 0 and s[i]['t'] > r:
            i -= 1
        a = s[i]
        b = s[i + 1] if i + 1 < len(s) else None
        if b is None:
            if c['gone']:                                   # off the server's list, and all of it shown
                del self.cars[str(sid)]
                return None
            return {'p': a['p'], 'state': a['state']}
        if b['jump']:
            return {'p': a['p'], 'state': a['state']}
        return {'p': a['p'] + (b['p'] - a['p']) * (r - a['t']) / (b['t'] - a['t']), 'state': a['state']}
