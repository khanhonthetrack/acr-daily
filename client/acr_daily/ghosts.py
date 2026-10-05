"""Ghosts: other drivers' runs of today's daily, replayed against yours.

Each ghost knows its total time (clock + penalties) at every point of the route, so at any moment:
  gap      = your time now - the ghost's time when it was where you are   (+ = you are slower)
  position = where the ghost was on the route after the same time as you
"""
from .judge import Ghost


class GhostRun:
    def __init__(self, name, kind, trace, route, penalty_ms):
        self.name, self.kind = name, kind            # kind: 'p1' | 'ahead' | 'me' | 'field'
        self.g = Ghost(trace, route, penalty_ms)
        self.route = route
        self.total = next((v for v in reversed(self.g.at) if v is not None), None)

    def gap(self, my_idx, my_total):
        t = self.g.total_at(my_idx)
        return None if t is None else my_total - t

    def idx_at(self, t_ms):
        """Route index the ghost had reached after t_ms (its own time incl. penalties)."""
        best = 0
        for i, v in enumerate(self.g.at):
            if v is not None and v <= t_ms:
                best = i
        return best

    def progress_at(self, t_ms):
        L = self.route.length or 1
        return self.route.cum[self.idx_at(t_ms)] / L

    def pos_at(self, t_ms):
        return self.route.points[self.idx_at(t_ms)]


class GhostSet:
    """The ghosts shown on the displays: today's P1, the driver just ahead of you, and your own first run."""

    def __init__(self, route, penalty_ms):
        self.route, self.penalty_ms = route, penalty_ms
        self.runs = {}                               # runId -> GhostRun

    def add(self, run_id, name, trace, kind='field'):
        if run_id not in self.runs and trace:
            self.runs[run_id] = GhostRun(name, kind, trace, self.route, self.penalty_ms)

    def pick(self, my_idx, my_total, me_run_id=None, p1_run_id=None):
        """-> list of (label, kind, GhostRun, gap): P1, the closest ghost ahead of you, and your own run."""
        out, used = [], set()
        p1 = self.runs.get(p1_run_id) if p1_run_id != me_run_id else None   # you are P1: shown as "Your run"
        if p1:
            out.append(('P1 ' + p1.name, 'p1', p1, p1.gap(my_idx, my_total)))
            used.add(p1_run_id)
        # ahead = the ghost you are closest behind (smallest positive gap)
        best = None
        for rid, gr in self.runs.items():
            if rid in used or rid == me_run_id:
                continue
            g = gr.gap(my_idx, my_total)
            if g is not None and g > 0 and (best is None or g < best[2]):
                best = (rid, gr, g)
        if best:
            out.append((best[1].name, 'ahead', best[1], best[2]))
            used.add(best[0])
        mine = self.runs.get(me_run_id)
        if mine:
            out.append(('Your run' + (' · P1' if p1_run_id == me_run_id else ''), 'me', mine, mine.gap(my_idx, my_total)))
        return out
