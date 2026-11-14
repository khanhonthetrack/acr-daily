"""Pictures of the game's results screen after a finish (from 0.1.5): the evidence of a lost result's final time.

After a Rally Weekend stage the game shows its results screen (the stage time, its penalty, the final time) and writes
the result into its save when the driver goes on from it (waiting.py). Sometimes it never writes it (it hangs, is
closed, or the stage is started again from that screen), and with respawns the penalty can't be known otherwise: the
game publishes no final time anywhere else (telemetry.py). So while a finished run waits for its result the app takes a
few pictures of the game's window, at SHOT_AFTER_S after the finish, while the results screen is up. They stay in
memory: dropped as soon as the game's result is in, sent only with the report of a run the game lost (gamelog.py), for
the admin to read the penalty off and reinstate the run with it (tools/admin.py reinstate <id> <penalty s>).

Only the game's own window is taken (autodrive.game_window, as auto-drive looks at the game's menus), never the rest of
the screen; nothing when the game has no window or Pillow is missing. Never raises.
"""
import io

SHOT_AFTER_S = (4, 9, 16)   # after the finish: the results screen comes up a few seconds after the line, and stays
MAX_SIDE = 1600             # the picture made at most this wide (the results' numbers stay readable), as JPEG
QUALITY = 75
KEEP = len(SHOT_AFTER_S)


def shot(window=None, grab=None):
    """A JPEG of the game's window as it is now, or None. window/grab: autodrive.game_window / autodrive.capture
    (tests give their own)."""
    try:
        if window is None or grab is None:
            from . import autodrive
            if autodrive.ImageGrab is None:
                return None
            window, grab = window or autodrive.game_window, grab or autodrive.capture
        hwnd = window()
        if not hwnd:
            return None
        img = grab(hwnd)
        if img is None:
            return None
        img = img.convert('RGB')
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=QUALITY, optimize=True)
        return out.getvalue()
    except Exception:
        return None


class Shots:
    """The pictures of the runs waiting for their result: run id -> [(seconds after the finish, JPEG bytes)]."""

    def __init__(self):
        self.by_run = {}

    def add(self, run_id, after_s, jpeg):
        if jpeg:
            self.by_run.setdefault(run_id, []).append((after_s, jpeg))
            del self.by_run[run_id][:-KEEP]

    def take(self, run_id):
        """The run's pictures, let go of here: [(after_s, jpeg)]."""
        return self.by_run.pop(run_id, [])

    def drop(self, run_id):
        self.by_run.pop(run_id, None)
