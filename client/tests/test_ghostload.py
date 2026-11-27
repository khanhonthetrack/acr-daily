"""Ghost cars with many drivers on the stage: the app's work a frame stays small (the grid of each run's line), the
game gets the nearest few only, and the files the app and the mod share are kept open and written in place."""
import math
import os
import random
import shutil
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import ghostcars as gc  # noqa: E402

try:
    from acr_daily import ghostui
except Exception:          # (no display / not Windows)
    ghostui = None


def winding_run(n=4000, every_ms=50):
    """A long run along a winding road (n samples): [clockMs, x, y, z, heading, pitch, roll]."""
    s, x, z, h = [], 0.0, 0.0, 0.0
    for i in range(n):
        h += 0.02 * math.sin(i / 90.0)
        x -= math.sin(h) * 1.5
        z += math.cos(h) * 1.5
        s.append([i * every_ms, x, 0.0, z, h, 0.0, 0.0])
    return s


class WhereTheyPassed(unittest.TestCase):
    def test_the_grid_finds_what_a_whole_run_search_finds(self):
        s = winding_run()
        g = gc.GhostTrace({'samples': s})
        rnd = random.Random(3)
        for _ in range(200):
            k = rnd.randrange(len(s) - 1)
            x, z = s[k][1] + rnd.uniform(-15, 15), s[k][3] + rnd.uniform(-15, 15)
            g._hint = rnd.randrange(len(s))              # (as if last found somewhere else on the run)
            got = g.passed(x, z)
            i, d, kk = g._nearest(x, z, 0, len(s) - 1)    # the whole run, the slow way
            want = s[i][0] + (s[i + 1][0] - s[i][0]) * kk
            if d < 25.0:
                self.assertAlmostEqual(got, want, delta=1.0)

    def test_a_driver_behind_you_costs_no_whole_run_search(self):
        """They have not been where you are: the search looks near you only (it scanned all of their run each frame:
        3 ms a frame with 10 drivers)."""
        s = winding_run()
        g = gc.GhostTrace({'samples': s[:2000]})        # they are halfway; you are further on
        far = s[3500]
        looked = []
        nearest = g._nearest
        g._nearest = lambda x, z, lo, hi: (looked.append(max(1, hi - lo)), nearest(x, z, lo, hi))[1]
        for _ in range(5):
            g.passed(far[1], far[3])
        self.assertLess(sum(looked), 5 * 200)

    def test_a_live_driver_growing(self):
        s = winding_run(600)
        g = gc.GhostTrace({'samples': []})
        for row in s[:300]:
            g.s.append(tuple(row))
            g.ms.append(row[0])
        g.passed(s[100][1], s[100][3])
        for row in s[300:]:                               # (more samples come: the grid takes them in when asked)
            g.s.append(tuple(row))
            g.ms.append(row[0])
        g._hint = 0
        self.assertAlmostEqual(g.passed(s[500][1], s[500][3]), s[500][0], delta=60)


@unittest.skipIf(ghostui is None, 'no ghostui here')
class GhostCarsOff(unittest.TestCase):
    """Ghost cars off: your car still goes to the relay (everyone with them on sees every driver), sending only."""

    def overlay(self, frames, signed_in=True):
        ov = ghostui.GhostOverlay.__new__(ghostui.GhostOverlay)
        ov.app = types.SimpleNamespace(s={'name': 'Me', 'token': 't' if signed_in else None}, api=None)
        ov.cfg = {'on': False, 'liveServer': 'wss://relay.example/live'}
        ov.live, ov._live_want, ov._phys, ov.root, ov._root_at, ov._timer = None, None, None, None, 0.0, False
        ov.src = types.SimpleNamespace(read=lambda: frames[0])
        ov._fine_timer = lambda on: None
        made = []

        class Link:
            def __init__(self, url, name, ticket=None, watch=True):
                self.watch, self.fed, self.closed, self.root = watch, [], False, None
                made.append(self)

            def feed(self, f):
                self.fed.append(f)

            def close(self):
                self.closed = True
        self._orig = ghostui.livelink.LiveLink
        ghostui.livelink.LiveLink = Link
        self.addCleanup(setattr, ghostui.livelink, 'LiveLink', self._orig)
        return ov, made

    def test_sends_only_while_on_a_stage(self):
        frames = [None]
        ov, made = self.overlay(frames)
        self.assertEqual(ov._share(), 500)                              # the game not on a stage: no connection
        self.assertEqual(made, [])
        frames[0] = types.SimpleNamespace(track='Monte Carlo', car='Skoda Fabia RS Rally2', clock_ms=1200, x=1.0, y=2.0,
                                          z=3.0, heading=0.0, pitch=0.0, roll=0.0)
        self.assertEqual(ov._share(), ghostui.SHARE_MS)                 # driving: sent, read often
        self.assertEqual(len(made), 1)
        self.assertFalse(made[0].watch)                                 # (sending only: nobody's samples back)
        self.assertEqual(made[0].fed, [frames[0]])
        self.assertIsNotNone(made[0].root)                              # (where your car's model sits)
        ov.cfg['on'] = True                                             # ghost cars on: a link that watches
        ov._live_link(watch=True)
        self.assertTrue(made[0].closed)
        self.assertTrue(made[1].watch)

    def test_left_after_the_game_is_gone_for_a_while(self):
        frames = [types.SimpleNamespace(track='Monte Carlo', car='', clock_ms=0, x=0.0, y=0.0, z=0.0, heading=0.0,
                                        pitch=0.0, roll=0.0)]
        ov, made = self.overlay(frames)
        ov._car_root = lambda f: None
        ov._share()
        frames[0] = None
        self.assertEqual(ov._share(), 250)                              # just gone: kept a while (back to a stage)
        self.assertFalse(made[0].closed)
        ov._share_seen -= ghostui.SHARE_IDLE_S
        self.assertEqual(ov._share(), 500)
        self.assertTrue(made[0].closed)

    def test_not_signed_in_nothing_sent(self):
        frames = [types.SimpleNamespace(track='Monte Carlo', car='', clock_ms=500, x=0.0, y=0.0, z=0.0, heading=0.0,
                                        pitch=0.0, roll=0.0)]
        ov, made = self.overlay(frames, signed_in=False)
        self.assertEqual(ov._share(), 500)
        self.assertEqual(made, [])


@unittest.skipIf(ghostui is None or os.name != 'nt', 'Windows only')
class TheGamesShare(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        ov = ghostui.GhostOverlay.__new__(ghostui.GhostOverlay)
        ov._ingame_path = lambda name: os.path.join(self.d, name)
        ov.root, ov.cfg = None, {'ingame': True}
        self.addCleanup(lambda: [getattr(ov, n).close() for n in ('_ghosts_fh', '_cam_fh') if getattr(ov, n, None)])
        self.ov = ov

    def test_the_nearest_ten_go_to_the_game(self):
        f = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
        cars = [('L%d' % i, (0.0, 0.0, 30.0 * (i + 1), 0, 0, 0), None, '', True, ('Car', None)) for i in range(15)]
        out = self.ov._real_cars(f, cars, {})
        self.assertEqual([c[0] for c in out], ['L%d' % i for i in range(10)])          # the nearest 10 of 15
        far = [(cid, (0.0, 0.0, 520.0, 0, 0, 0), *rest) for cid, p, *rest in cars[:1]]
        self.assertEqual([c[0] for c in self.ov._real_cars(f, far, {})], ['L0'])        # 520 m: still shown...
        self.assertEqual(self.ov._real_cars(f, [(c[0], (0.0, 0.0, 560.0, 0, 0, 0), *c[2:]) for c in far], {}), [])
        self.assertEqual(self.ov._real_cars(f, far, {}), [])                              # ...gone: back only by 500

    def test_a_shown_car_keeps_its_place(self):
        """Ten shown; an eleventh only a little nearer than the furthest of them does not swap in (a ghost made and
        removed again each time); one much nearer does."""
        f = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
        car = lambda cid, z: (cid, (0.0, 0.0, z, 0, 0, 0), None, '', True, ('Car', None))   # noqa: E731
        ten = [car('L%d' % i, 30.0 * (i + 1)) for i in range(10)]                         # L9 at 300 m
        self.ov._real_cars(f, ten, {})
        out = self.ov._real_cars(f, ten + [car('N', 280.0)], {})
        self.assertNotIn('N', [c[0] for c in out])
        out = self.ov._real_cars(f, ten + [car('N', 200.0)], {})
        self.assertIn('N', [c[0] for c in out])
        self.assertNotIn('L9', [c[0] for c in out])

    def test_the_ghosts_file_written_in_place(self):
        car = ('Skoda Fabia RS Rally2', None)
        reader = None
        try:
            self.ov._write_ingame([('L1', (1.0, 2.0, 3.0, 0.1, 0.0, 0.0), (5.0, 0.0, 0.0, 0.0, 0.0, 0.0), car),
                                   ('L2', (4.0, 2.0, 3.0, 0.1, 0.0, 0.0), None, car)], 100.0)
            reader = open(os.path.join(self.d, 'ingame-ghosts.txt'), newline='')   # (as the mod: opened once)
            first = reader.read().split('\n')
            self.assertEqual(first[0].split()[:3], ['ACRDG', '2', '1'])
            self.assertTrue(all(line.split()[-1] == '1' for line in first[1:3]))      # each line: the update's number
            self.assertEqual(len(first[1].split()), 15)
            self.assertEqual(first[3], 'end 1')
            self.ov._write_ingame([], 101.0)
            reader.seek(0)
            self.assertEqual(reader.read(), 'ACRDG 2 2 101.0000\nend 2\n')            # the same file, nothing left over
            self.ov._write_ingame([], 102.0, {'/Game/X/BC_X.BC_X_C': 4})              # the models that may come
            reader.seek(0)
            self.assertEqual(reader.read(), 'ACRDG 2 3 102.0000\nwarm /Game/X/BC_X.BC_X_C 4 3\nend 3\n')
        finally:
            if reader:
                reader.close()

    def test_a_half_written_camera_is_skipped(self):
        path = os.path.join(self.d, 'ingame-camera.txt')
        with open(path, 'w') as fh:
            fh.write('CAM 7 100.00 200.00 300.00 -5.0 90.0 0.0 80.0 7'.ljust(159) + '\n')
        self.assertIsNotNone(self.ov._game_camera(1920, 1080))
        self.assertEqual(self.ov._cam_seq, 7)
        with open(path, 'r+') as fh:                    # (in place, as the mod writes it: the reader's file still open)
            fh.write('CAM 8 999.00 999.00 999.00 -5.0 90.0 0.0 80.0 7'.ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual(self.ov._cam_seq, 7)            # two numbers that differ: a half-written line, not taken
        with open(path, 'r+') as fh:
            fh.write('CAM 9 101.00 200.00 300.00 -5.0 90.0 0.0 80.0 9'.ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual(self.ov._cam_seq, 9)

    def test_the_cars_the_mod_hides_get_no_name(self):
        """A newer mod lists the cars it hides while they are in yours ("H <id>... <seq>"): no name drawn over them.
        An older mod's line lists none."""
        path = os.path.join(self.d, 'ingame-camera.txt')
        line = 'CAM 7 100.00 200.00 300.00 -5.0 90.0 0.0 80.0 7'
        with open(path, 'w') as fh:
            fh.write((line + ' H L3 L12 7').ljust(159) + '\n')
        self.assertIsNotNone(self.ov._game_camera(1920, 1080))
        self.assertEqual(self.ov._cam_hidden, {'L3', 'L12'})
        with open(path, 'r+') as fh:                    # (half written: the list's number is the last line's)
            fh.write((line.replace('CAM 7', 'CAM 8').replace(' 7', ' 8') + ' H L5 7').ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual((self.ov._cam_seq, self.ov._cam_hidden), (7, {'L3', 'L12'}))
        with open(path, 'r+') as fh:                    # (none hidden now / an older mod)
            fh.write(line.replace('CAM 7', 'CAM 9').replace(' 7', ' 9').ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual((self.ov._cam_seq, self.ov._cam_hidden), (9, set()))
        with open(path, 'r+') as fh:                    # (the game's mode first, then the hidden ones: still read)
            fh.write((line.replace('CAM 7', 'CAM 10').replace(' 7', ' 10') + ' M weekend 10 H L4 10').ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertEqual((self.ov._cam_seq, self.ov._cam_hidden), (10, {'L4'}))

    def test_the_game_draws_the_names(self):
        """(19 Nov 2026, the user: the names over the ghosts weren't drawn by the game.) Each car's name goes in the
        ghosts' file after its car ("name <id> <seq> <shown> <colour> <the name>"), for the mod's hud.lua to draw;
        once the mod says it draws them (camera line "N 1 <seq>"), the app's window draws none."""
        car = ('Skoda Fabia RS Rally2', None)
        reader = None
        try:
            self.ov._write_ingame([('L1', (1.0, 2.0, 3.0, 0.1, 0.0, 0.0), None, car)], 100.0, None,
                                  {'L1': ('Ann  de  Vries', '#FFB547', True, 'C:\\ACR Daily\\pics\\flag-nl.png'),
                                   'L9': ('Bob', '#FFB547', True)})
            reader = open(os.path.join(self.d, 'ingame-ghosts.txt'), newline='')
            lines = reader.read().split('\n')
            self.assertEqual(lines[2], 'name L1 1 1 FFB547 Ann de Vries')      # (only cars sent: L9 is not)
            self.assertEqual(lines[3], 'flag L1 1 C:\\ACR Daily\\pics\\flag-nl.png')
            self.assertEqual(lines[4], 'end 1')
        finally:
            if reader:
                reader.close()
        path = os.path.join(self.d, 'ingame-camera.txt')
        with open(path, 'w') as fh:
            fh.write('CAM 7 100.00 200.00 300.00 -5.0 90.0 0.0 80.0 7 M weekend 7 N 1 7'.ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertTrue(self.ov._cam_names)
        with open(path, 'r+') as fh:                    # (an older mod: the app's window draws them)
            fh.write('CAM 8 100.00 200.00 300.00 -5.0 90.0 0.0 80.0 8 M weekend 8'.ljust(159) + '\n')
        self.ov._game_camera(1920, 1080)
        self.assertFalse(self.ov._cam_names)


class GhostFlagLabels(unittest.TestCase):
    """Ghost nickname flag rendering (Tk canvas + ingame-ghosts.txt), runnable on any OS."""

    def _load_ghostui(self):
        if ghostui is not None:
            return ghostui
        import importlib
        from unittest import mock
        tk_stub = types.ModuleType('tkinter')
        tk_stub.TclError = Exception
        with mock.patch.dict(sys.modules, {'tkinter': tk_stub}):
            return importlib.import_module('acr_daily.ghostui')

    def test_write_ingame_and_tk_flag_on_left(self):
        from unittest import mock
        gu = self._load_ghostui()
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)

        ov = gu.GhostOverlay.__new__(gu.GhostOverlay)
        ov._ingame_path = lambda name: os.path.join(d, name)
        ov.root, ov.cfg, ov._n = None, {'ingame': False, 'always': True}, 0
        ov.rect = (0, 0, 1280, 720)
        ov._cam_at, ov._cam_names, ov._cam_fresh = -1e9, False, False

        drawn_imgs, drawn_texts = [], []

        class Canvas:
            def delete(self, *_a): pass
            def create_image(self, x, y, **kw): drawn_imgs.append((x, y, kw))
            def create_text(self, x, y, **kw): drawn_texts.append((x, y, kw))
            def create_line(self, *_a, **_kw): pass
            def create_polygon(self, *_a, **_kw): pass

        ov.c = Canvas()
        ov._name_font = types.SimpleNamespace(metrics=lambda k: 18 if k == 'ascent' else 22, measure=lambda s: 10.0 * len(s))
        fake_flag = object()
        ov._flag_tk = staticmethod(lambda code, w, h: fake_flag if (code == 'pl' and (w, h) == (27, 18)) else None)
        ov._flag_png = staticmethod(lambda code: '/tmp/pics/flag-%s.png' % code if code else None)

        drv = types.SimpleNamespace(
            id=1, name='Kajetan', sid='76561198000000001', car='Skoda Fabia RS Rally2', root=None,
            motion=lambda _now: ((0.0, 0.0, 20.0, 0.0, 0.0, 0.0), (0.0,) * 6),
            trace=types.SimpleNamespace(passed=lambda *_a: 0, path=lambda *_a: []),
            clock_now=lambda _now: 0, ahead_s=lambda *_a: None,
        )
        ov.app = types.SimpleNamespace(watch=types.SimpleNamespace(on=False, country_of=lambda _n, _s=None: 'pl'))
        f = types.SimpleNamespace(x=0.0, y=0.0, z=0.0, heading=0.0, pitch=0.0, roll=0.0, car='Skoda Fabia RS Rally2')
        ov._draw(f, others=[drv], labels=True)

        self.assertEqual(len(drawn_imgs), 1)
        ix, iy, ikw = drawn_imgs[0]
        self.assertIs(ikw['image'], fake_flag)
        self.assertEqual(ikw['anchor'], 'se')
        self.assertEqual(len(drawn_texts), 2)
        tx, ty, tkw = drawn_texts[1]
        self.assertEqual(tkw['text'], 'Kajetan')
        self.assertEqual(ty, iy)
        self.assertLess(ix, tx)  # flag is to the left of the nickname

        # Also verify _write_ingame emits flag line with spaces in path
        with mock.patch.object(gu, 'open_kept', side_effect=lambda p, write=False, binary=False: open(p, 'w+' if write else 'r')):
            ov._write_ingame([('L1', (1.0, 2.0, 3.0, 0.1, 0.0, 0.0), None, ('Skoda Fabia RS Rally2', None))],
                             100.0, None, {'L1': ('Kajetan', '#FFB547', True, '/tmp/ACR Daily/flag-pl.png')})
            ov._ghosts_fh.close()
        with open(os.path.join(d, 'ingame-ghosts.txt')) as fh:
            lines = fh.read().splitlines()
        self.assertEqual(lines[2], 'name L1 1 1 FFB547 Kajetan')
        self.assertEqual(lines[3], 'flag L1 1 /tmp/ACR Daily/flag-pl.png')
        self.assertEqual(lines[4], 'end 1')


if __name__ == '__main__':
    unittest.main()
