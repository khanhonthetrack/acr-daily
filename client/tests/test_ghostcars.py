"""Ghost cars (a test): the camera maths, the recorder, and the whole thing on a real recorded run."""
import math
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import ghostcars as gc, settings  # noqa: E402
from acr_daily.telemetry import Frame, Replay  # noqa: E402
from tests.test_judge import DUMP  # noqa: E402

W, H = 1920, 1080
BONNET = {'fov': 75.0, 'fwd': 1.09, 'up': 0.58, 'side': 0.0, 'tilt': -5.31}     # the Skoda's, from its car point


def frame(t, clock, x=0.0, z=0.0, y=0.0, h=0.0, speed=80.0, track='Test Stage'):
    return Frame(t, int(t * 60), clock, x, z, speed, 'Car', track, y=y, heading=h)


class Maths(unittest.TestCase):
    def test_basis(self):
        f, r, u = gc.basis(0.0)
        self.assertEqual((round(f[0], 6), f[1], f[2]), (0, 0.0, 1.0))      # heading 0: along +z
        self.assertAlmostEqual(r[0], -1.0)                                   # right: -x
        for h, p, rl in ((0.3, 0.1, -0.2), (-2.5, -0.15, 0.3)):
            f, r, u = gc.basis(h, p, rl)
            for a, b in ((f, r), (f, u), (r, u)):
                self.assertAlmostEqual(gc.dot(a, b), 0.0, places=9)
            for a in (f, r, u):
                self.assertAlmostEqual(gc.dot(a, a), 1.0, places=9)
            self.assertAlmostEqual(f[1], math.sin(p), places=9)             # nose up: forward points up
        f, r, u = gc.basis(0.0, 0.0, 0.2)
        self.assertGreater(r[1], 0)                                          # roll > 0: right side up

    def test_project(self):
        cam = gc.camera_for((0, 0, 0, 0.0, 0, 0), dict(BONNET, up=0.0, fwd=0.0, tilt=0.0), W, H)
        x, y = cam.project((0, 0, 50))
        self.assertAlmostEqual(x, W / 2)
        self.assertAlmostEqual(y, H / 2)
        f, r, u = gc.basis(0.0)
        x, _ = cam.project(gc.add(gc.mul(f, 50), gc.mul(r, 5)))
        self.assertGreater(x, W / 2)                                         # to the right: right half
        _, y = cam.project((0, 3, 50))
        self.assertLess(y, H / 2)                                            # above: upper half
        self.assertIsNone(cam.project((0, 0, -5)))                           # behind
        # the field of view: a point on its edge lands on the screen's edge
        fov = math.radians(BONNET['fov'])
        x, _ = cam.project(gc.add(gc.mul(f, 10), gc.mul(r, 10 * math.tan(fov / 2))))
        self.assertAlmostEqual(x, W, places=6)
        cam.mirror = True
        x, _ = cam.project(gc.add(gc.mul(f, 50), gc.mul(r, 5)))
        self.assertLess(x, W / 2)

    def test_tilt(self):
        cam = gc.camera_for((0, 0, 0, 0.0, 0, 0), dict(BONNET, up=0.0, fwd=0.0, tilt=-10), W, H)
        _, y = cam.project((0, 0, 50))
        self.assertLess(y, H / 2)            # looking down: the road ahead moves up the screen

    def test_wide_screen_shows_more_at_the_sides(self):
        """The view keeps its height: 3440 x 1440 shows what 2560 x 1440 does, plus more at each side."""
        cfg = dict(BONNET, up=0.0, fwd=0.0, tilt=0.0)
        wide = gc.camera_for((0, 0, 0, 0.0, 0, 0), cfg, 3440, 1440)
        normal = gc.camera_for((0, 0, 0, 0.0, 0, 0), cfg, 2560, 1440)
        f, r, u = gc.basis(0.0)
        p = gc.add(gc.add(gc.mul(f, 40), gc.mul(r, 9)), gc.mul(u, -2))
        (xw, yw), (xn, yn) = wide.project(p), normal.project(p)
        self.assertAlmostEqual(xw - 3440 / 2, xn - 2560 / 2, places=6)
        self.assertAlmostEqual(yw, yn, places=6)
        across = 2 * math.degrees(math.atan((3440 / 2) / wide.focal))
        self.assertAlmostEqual(across, 91.2, delta=1.0)       # what the game showed on 3440 x 1440 (fitted to ~1 degree)

    def test_box(self):
        c = gc.box_corners((10, 2, 5, 0.7, 0, 0))
        self.assertEqual(len(c), 8)
        self.assertAlmostEqual(math.dist(c[0], c[3]), gc.CAR_BOX[0])   # front left to rear left: the length
        self.assertAlmostEqual(math.dist(c[0], c[1]), gc.CAR_BOX[1])   # front left to front right: the width

    def test_sight(self):
        straight = [(0, 0, z) for z in range(0, 201, 5)]
        self.assertTrue(gc.in_sight((0, 1, 0), (0, 0, 200), straight))
        # a right angle: the straight line cuts the corner, far from the road
        corner = [(0, 0, z) for z in range(0, 101, 5)] + [(-x, 0, 100) for x in range(5, 101, 5)]
        self.assertFalse(gc.in_sight((0, 1, 0), (-100, 0, 100), corner))
        self.assertTrue(gc.in_sight((0, 1, 0), (-8, 0, 100), corner))
        # a crest: the road rises 6 m between you and the ghost
        crest = [(0, 6 * math.sin(math.pi * z / 200), z) for z in range(0, 201, 5)]
        self.assertFalse(gc.in_sight((0, 1, 0), (0, 0, 200), crest))


class GameCameras(unittest.TestCase):
    """The game's own cameras (cameras.json, read out of the game by tools/gamefiles/cameras.py)."""

    def test_every_car_has_every_camera(self):
        cars = gc.camera_table()['cars']
        self.assertEqual(len(cars), 18)
        for key, c in cars.items():
            self.assertEqual(set(c['cameras']), set(gc.GAME_VIEWS), key)
            for v, cam in c['cameras'].items():
                self.assertTrue(40 <= cam['fov'] <= 120, (key, v))
                self.assertAlmostEqual(cam['yaw'], 90.0, delta=1.0)

    def test_the_cars_the_game_reports(self):
        """The names the telemetry gives (server/src/cars.js) find their car's cameras."""
        for reported, helmet_left in (('Skoda Fabia RS Rally2', True), ('Mini Cooper S 1275', False),
                                      ('Alfa_Romeo_GTA', True), ('FIAT Abarth 124 Rally', True), ('Lancia 037', True),
                                      ('Peugeot 306 II Maxi Kit', True), ('Hyundai i20N Rally2', True)):
            cams = gc.car_cameras(reported)
            self.assertIsNotNone(cams, reported)
            self.assertEqual(cams['helmet']['x'] > 0, helmet_left, reported)        # (the Mini drives on the right)
        self.assertIsNone(gc.car_cameras('Some Other Car 2000'))

    def test_skoda_bonnet(self):
        """Measured in the game: 75 across at 16:9, looking 5.3 degrees down, 1.05 m above the road."""
        v = gc.game_view('Skoda Fabia RS Rally2', 'bonnet', root=(-0.17, -0.47))
        self.assertAlmostEqual(v['fov'], 75.0)
        self.assertAlmostEqual(v['tilt'], -5.31, places=2)
        self.assertAlmostEqual(v['up'] + 0.47, 1.05, places=2)
        self.assertAlmostEqual(v['fwd'], 1.0875, places=2)
        self.assertAlmostEqual(v['side'], 0.0, places=2)
        helmet = gc.game_view('Skoda Fabia RS Rally2', 'helmet', root=(-0.17, -0.47))
        self.assertLess(helmet['side'], -0.25)                                   # the driver sits on the left
        self.assertEqual(gc.game_view('Skoda Fabia RS Rally2', 'far')['tilt'], 0.0)   # chase: level with the car
        self.assertIsNotNone(gc.game_view('Some Other Car 2000', 'bonnet'))       # (not in the table: the Skoda's)

    def test_fine_tuning_adds_to_the_game_camera(self):
        cfg = dict(gc.DEFAULTS, view='helmet', adjust={'helmet': {'up': 0.1, 'fov': -5}, 'bonnet': {'up': 9}})
        base = gc.game_view('Skoda Fabia RS Rally2', 'helmet')
        v = gc.view_cfg(cfg, 'Skoda Fabia RS Rally2')
        self.assertAlmostEqual(v['up'], base['up'] + 0.1)
        self.assertAlmostEqual(v['fov'], base['fov'] - 5)
        self.assertAlmostEqual(v['fwd'], base['fwd'])

    def test_car_root_from_the_tyres(self):
        """The Skoda standing on the start line: tyres 1.113 m ahead / 1.456 m behind, 0.47 m below the car point."""
        h = 0.7
        f, r, u = gc.basis(h)
        car = (10.0, 2.0, 5.0)
        pts = [gc.add(gc.add(gc.add(car, gc.mul(f, a)), gc.mul(r, b)), gc.mul(u, -0.47))
               for a, b in ((1.113, -0.81), (1.113, 0.81), (-1.456, -0.81), (-1.456, 0.81))]
        fw, up = gc.car_root(pts, car + (h, 0.0, 0.0))
        self.assertAlmostEqual(fw, -0.1715 + 0.04, places=3)          # the game's actor: 4 cm ahead of mid-wheelbase
        self.assertAlmostEqual(up, -0.47 - 0.10, places=6)            # and 10 cm below the contacts (seen in the game)

    def test_the_games_units(self):
        """Telemetry -> the game's actor (read from the game with the mod while driving): x, z, y in cm; yaw = heading;
        the actor's pitch / roll are the car's roll / pitch, the other way round."""
        pose = (1135.5, 1098.0, 3329.2, math.radians(156.13), math.radians(-1.32), math.radians(0.60))
        X, Y, Z, P, Yw, R = gc.ue_pose(pose, root=(0.0, 0.0))
        self.assertEqual((round(X), round(Y), round(Z)), (113550, 332920, 109800))
        self.assertAlmostEqual(Yw, 156.13, places=6)
        self.assertAlmostEqual(P, -0.60, places=6)
        self.assertAlmostEqual(R, 1.32, places=6)

    def test_the_games_camera(self):
        """A camera the game reports (the mod) looks where a car with that heading looks, its fov across the picture."""
        h = 0.7
        cam = gc.camera_from_game((10000.0, 20000.0, 500.0, 0.0, math.degrees(h) + 90.0, 0.0, 90.0), 1920, 1080)
        f, r, u = gc.basis(h)
        for a, b in ((cam.f, f), (cam.r, r), (cam.u, u)):
            for i in range(3):
                self.assertAlmostEqual(a[i], b[i], places=6)
        self.assertEqual(cam.pos, (100.0, 5.0, 200.0))
        x, _y = cam.project(gc.add(cam.pos, gc.add(gc.mul(f, 10), gc.mul(r, 10))))     # 45 degrees right: the edge
        self.assertAlmostEqual(x, 1920, places=6)


class CameraKeySettings(unittest.TestCase):
    def test_bindings_from_the_games_save(self):
        from acr_daily import ghostui
        fs = lambda s: (len(s) + 1).to_bytes(4, 'little') + s.encode() + b'\0'
        blob = b'GVAS' + b''.join(fs(s) for s in ['gas', 'GenericUSBController_Axis1_7864_5801', 'RawInput',
                                                  'SteeringWheel', 'CycleCamera', 'GenericUSBController_Button11_3670_0500',
                                                  'RawInput', 'SteeringWheel', 'LookLeft', 'None'])
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, 'EnhancedInputUserSettings.sav')
            with open(p, 'wb') as f:
                f.write(blob)
            keys, joy = ghostui.camera_bindings(p)
            self.assertEqual(keys, [ord('C')])                       # the keyboard's own C
            self.assertEqual(joy, [(0x3670, 0x0500, 11)])            # and the wheel's button 11
            with open(p, 'wb') as f:
                f.write(blob + fs('CycleCamera') + fs('V') + fs('Keyboard') + fs('Slot'))
            self.assertEqual(ghostui.camera_bindings(p)[0], [ord('V')])   # a key of their own instead of C
            self.assertEqual(ghostui.camera_bindings(os.path.join(d, 'none.sav')), ([ord('C')], []))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_old_settings_move_over(self):
        from acr_daily import ghostui
        s = {'ghostCars': {'on': True, 'view': 'cockpit', 'fov': 70.0, 'tilt': -4.5, 'level': False, 'earlierS': 3.0,
                           'source': 'best', 'line': True, 'live': True}}
        cfg = ghostui.config(s)
        self.assertEqual(cfg['view'], 'helmet')
        self.assertFalse(any(k in cfg for k in gc.LEGACY))              # (your own past runs: gone, live only)
        self.assertEqual((cfg['on'], cfg['adjust'], cfg['follow'], cfg['ingame']), (True, {}, True, False))

    def test_the_cars_class_for_the_mod(self):
        self.assertEqual(gc.car_class('Hyundai i20N Rally2'),
                         '/Game/Data/Vehicles/HyundaiI20NRally2/BC_HyundaiI20NRally2.BC_HyundaiI20NRally2_C')
        self.assertTrue(gc.car_class('Alfa_Romeo_GTA').endswith('BC_AlfaRomeoGiuliaGTAJunior1300_C'))
        self.assertIsNone(gc.car_class('Some Other Car 2000'))
        for key, c in gc.camera_table()['cars'].items():
            self.assertTrue(c['cls'].startswith('/Game/Data/Vehicles/') and c['cls'].endswith('_C'), key)


@unittest.skipUnless(os.path.exists(DUMP), 'no shm dump')
class RealRun(unittest.TestCase):
    """The recorded Wales run (Mini): its samples as a live driver's would come (every 100 ms of clock), played back,
    and the camera pointed along it."""

    @classmethod
    def setUpClass(cls):
        cls.frames = [f for f in Replay(DUMP).frames]
        samples, last = [], -1
        for f in cls.frames:
            if f.clock_ms > 0 and f.clock_ms >= last + 100:
                last = f.clock_ms
                samples.append([f.clock_ms, f.x, f.y, f.z, f.heading, f.pitch, f.roll])
        cls.ghost = gc.GhostTrace({'samples': samples})

    def test_playback_follows_the_run(self):
        g, errs, clock_errs = self.ghost, [], []
        running = [f for f in self.frames if 0 < f.clock_ms < g.end_ms]
        for f in running[::25]:
            p = g.at(f.clock_ms)
            errs.append(math.dist(p[:3], (f.x, f.y, f.z)))
        g._hint = 0
        for f in running[::25]:
            clock_errs.append(abs(g.passed(f.x, f.z) - f.clock_ms))
        errs.sort()
        clock_errs.sort()
        print('\n  position error: median %.2f m, 95%% %.2f m; time at a place: median %d ms, 95%% %d ms' % (
            errs[len(errs) // 2], errs[int(len(errs) * .95)], clock_errs[len(clock_errs) // 2],
            clock_errs[int(len(clock_errs) * .95)]))
        self.assertLess(errs[int(len(errs) * .95)], 1.5)
        self.assertLess(clock_errs[int(len(clock_errs) * .95)], 150)

    def test_road_ahead_is_in_front(self):
        """Where the car is 1.5 s later is in front of the bonnet camera and on the screen, and on the side it turns to."""
        g = self.ghost
        cfg = gc.game_view('Mini Cooper S 1275', 'bonnet')          # (the recorded run is a Mini's)
        on_screen = sides = turning = 0
        n = 0
        for f in [f for f in self.frames if 2000 < f.clock_ms < g.end_ms - 2000 and f.speed > 40][::10]:
            cam = gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), cfg, W, H)
            ahead = g.at(f.clock_ms + 1500)
            pt = cam.project(ahead[:3])
            n += 1
            if pt and 0 <= pt[0] <= W and 0 <= pt[1] <= H:
                on_screen += 1
            turn = (ahead[3] - f.heading + math.pi) % (2 * math.pi) - math.pi
            if pt and abs(turn) > 0.3:          # heading going up = turning right (ghostcars.basis)
                turning += 1
                sides += (pt[0] > W / 2) == (turn > 0)
        print('\n  1.5 s ahead on screen: %d / %d; on the side of the turn: %d / %d' % (on_screen, n, sides, turning))
        self.assertGreater(on_screen / n, 0.9)
        self.assertGreater(sides / max(1, turning), 0.9)

    def test_ghost_line_sits_low_on_the_screen(self):
        """Its line 20 m ahead (on the road) is below the middle of the screen from a bonnet camera: the camera is above the road."""
        g, below, n = self.ghost, 0, 0
        cfg = dict(gc.game_view('Mini Cooper S 1275', 'bonnet'), tilt=0.0)
        for f in [f for f in self.frames if 2000 < f.clock_ms < g.end_ms - 2000 and f.speed > 40][::20]:
            cam = gc.camera_for((f.x, f.y, f.z, f.heading, f.pitch, f.roll), cfg, W, H)
            g._hint = 0
            at = g.passed(f.x, f.z)
            pts = g.path(at, at + 60000, 3.0, 20.0)
            if len(pts) < 3:
                continue
            x, y, z = pts[-1]
            pt = cam.project((x, y - gc.CAR_ABOVE_GROUND, z))
            n += 1
            below += bool(pt and pt[1] > H / 2)
        print('\n  line 20 m ahead below the middle: %d / %d' % (below, n))
        self.assertGreater(below / n, 0.85)


if __name__ == '__main__':
    unittest.main()
