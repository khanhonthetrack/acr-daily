"""Records a stage's route from a clean run (start to finish, no resets).

The app keeps one running all the time: the first clean run on a stage that has no route yet is sent to the
server and becomes that stage's route (admin mode's "Record route" uses the same recorder)."""
import json
import math
import os
import re

from . import settings
from .judge import (FINISH_FREEZE_S, NEUTRAL, RESET_FROM_KMH, RESET_STOP_KMH, RESET_STOP_WINDOW_S,
                    teleported)
from .route import thin


class RouteRecorder:
    def __init__(self):
        self.state = 'idle'       # idle | armed | recording | done | failed
        self.message = 'Drive to a start line: recording starts with the stage clock'
        self.points, self.track, self.car = [], '', ''
        self.clock = 0
        self._last = None
        self._freeze = None
        self._fast_at = None      # last moment driving in gear at RESET_FROM_KMH or more
        self.saved = None

    def feed(self, f, now):
        if f is None:
            return
        prev, self._last = self._last, f
        if self.state in ('idle', 'done', 'failed'):
            if f.clock_ms == 0 and f.track:
                self.state, self.message = 'armed', 'Armed on %s: go!' % f.track
            return
        if self.state == 'armed':
            if f.clock_ms > 0 and prev is not None and prev.clock_ms <= 0:
                self.state, self.points, self.track, self.car = 'recording', [(f.x, f.z)], f.track, f.car
                self.clock, self._freeze = f.clock_ms, None
                self.message = 'Recording %s - drive cleanly, no resets' % f.track
            return
        # recording
        if f.clock_ms < self.clock - 500 or f.track != self.track:
            self.state, self.message = 'failed', 'Restarted or left the stage - not saved'
            return
        # a reset (the same two signs the timer uses): a jump no car could drive, or put down stopped in neutral
        # right after driving in gear - the line would include the trip off the road
        if f.speed >= RESET_FROM_KMH and f.gear > NEUTRAL:
            self._fast_at = f.t
        put_down = (f.speed < RESET_STOP_KMH and f.gear == NEUTRAL and self._fast_at is not None
                    and f.t - self._fast_at <= RESET_STOP_WINDOW_S)
        if put_down or (prev is not None and teleported(math.dist((prev.x, prev.z), (f.x, f.z)), f.t - prev.t,
                                                        max(prev.speed, f.speed))):
            self.state, self.message = 'failed', 'Reset to the road - a reference route must be clean. Restart and try again.'
            return
        if math.dist(self.points[-1], (f.x, f.z)) >= 1.0:
            self.points.append((f.x, f.z))
        if f.clock_ms == self.clock:
            if self._freeze is None:   # where the clock stopped: the route ends here, not where the car rolls to
                self._freeze = (now, len(self.points), (f.x, f.z))
            t0, n, at = self._freeze
            # finish = the clock stopped while the car kept rolling; a pause freezes the car too
            if now - t0 >= FINISH_FREEZE_S and math.dist(at, (f.x, f.z)) > 2.0:
                self.points = self.points[:n]
                self._save()
            elif now - t0 > 30:
                self.state, self.message = 'failed', 'Stopped on the stage - not saved'
        else:
            self._freeze = None
            self.clock = f.clock_ms

    def _save(self):
        pts = thin(self.points, 5.0)
        length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        data = {'track': self.track, 'car': self.car, 'clockMs': self.clock, 'length': round(length), 'points': pts}
        os.makedirs(settings.ROUTES, exist_ok=True)
        path = os.path.join(settings.ROUTES, re.sub(r'[^\w\- ]', '_', self.track) + '.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        self.saved = data
        self.state = 'done'
        self.message = 'Saved %s (%.1f km, %d points) to %s' % (self.track, length / 1000, len(pts), path)
