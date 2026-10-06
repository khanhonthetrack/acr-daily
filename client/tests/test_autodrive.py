"""Auto-drive (autodrive.py): which menu screen a capture shows, when to press a key, the player's Select key."""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import autodrive  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'menus')


def fstr(s):
    s = s.encode('ascii')
    return struct.pack('<i', len(s) + 1) + s + b'\x00'


class Screens(unittest.TestCase):
    """Real captures of the game's menus (21:9, scaled down to 640 x 268)."""

    def setUp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('no Pillow')
        self.Image = Image

    def test_each_menu_screen(self):
        for name in ('title', 'home', 'racing', 'rally', 'setup', 'park'):
            self.assertEqual(autodrive.screen(self.Image.open(os.path.join(FIX, name + '.jpg'))), name)

    def test_loading_and_other_pictures_are_nothing(self):
        self.assertIsNone(autodrive.screen(self.Image.open(os.path.join(FIX, 'loading.jpg'))))
        self.assertIsNone(autodrive.screen(self.Image.new('RGB', (640, 268), (219, 25, 22))))   # all red
        self.assertIsNone(autodrive.screen(self.Image.new('RGB', (640, 268), (0, 0, 0))))       # black (fullscreen)

    def test_any_size(self):
        img = self.Image.open(os.path.join(FIX, 'racing.jpg'))
        self.assertEqual(autodrive.screen(img.resize((2560, 1072))), 'racing')

    def test_16_9(self):
        """At 16:9 the menu sits at the left edge, but it is the same size per window height and centred the same."""
        self.assertEqual(autodrive.screen(self.Image.open(os.path.join(FIX, 'racing_169.jpg'))), 'racing')
        self.assertEqual(autodrive.screen(self.Image.open(os.path.join(FIX, 'rally_right_169.jpg'))), 'rally_right')
        self.assertIsNone(autodrive.screen(self.Image.open(os.path.join(FIX, 'settings_169.jpg'))))

    def test_narrower_screens(self):
        """16:10 and 4:3: the main menu sits in a 16:9 box fitted to the width, the other pages fill the height."""
        for name, want in (('home_1610', 'home'), ('racing_1610', 'racing'), ('rally_1610', 'rally'),
                           ('park_1610', 'park'), ('home_43', 'home'), ('rally_43', 'rally'), ('park_43', 'park')):
            self.assertEqual(autodrive.screen(self.Image.open(os.path.join(FIX, name + '.jpg'))), want, name)

    def test_super_ultrawide_and_triple_screens(self):
        """32:9 (49" monitors) and 48:9 (three 16:9 screens): centred, sized by the height, like 21:9."""
        for name, want in (('home_329', 'home'), ('park_329', 'park'), ('home_489', 'home'), ('park_489', 'park')):
            ext = '.png' if name == 'home_489' else '.jpg'      # a 240 px high tab: no JPEG blur
            self.assertEqual(autodrive.screen(self.Image.open(os.path.join(FIX, name + ext))), want, name)

    def test_the_mouse_pointer_lighting_another_button(self):
        """Clicking DRIVE leaves the pointer over a full-screen game: it lights the button under it."""
        self.assertEqual(autodrive.screen(self.Image.open(os.path.join(FIX, 'setup_pointer.jpg'))), 'setup_other')

    def test_a_set_up_with_something_else_selected_is_not_start_race(self):
        self.assertIsNone(autodrive.screen(self.Image.open(os.path.join(FIX, 'weekend_setup.jpg'))))   # CHANGE CAR lit


class Decide(unittest.TestCase):
    def test_presses_only_on_a_steady_expected_screen(self):
        d = autodrive.decide
        self.assertEqual(d(None, ['title', 'title'], 50), 'press')
        self.assertEqual(d(None, [None, 'title'], 50), 'wait')               # just appeared: once more
        self.assertEqual(d(None, ['home', 'home'], 1), 'press')
        self.assertEqual(d('title', ['racing', 'racing'], 2), 'press')       # menu opened on the Racing tab
        self.assertEqual(d('racing', ['rally', 'rally'], 2), 'press')
        self.assertEqual(d('setup', [None, None], 40), 'wait')               # the stage is loading

    def test_stops_on_anything_unexpected(self):
        d = autodrive.decide
        self.assertNotIn(d('home', ['rally', 'rally'], 2), ('press', 'wait'))     # skipped a screen
        self.assertNotIn(d(None, ['setup', 'setup'], 2), ('press', 'wait'))       # not where a start begins
        self.assertNotIn(d('rally', [None, None], autodrive.STEP_WAIT_S + 1), ('press', 'wait'))   # a pop-up?
        self.assertNotIn(d('racing', ['racing', 'racing'], autodrive.STEP_WAIT_S + 1), ('press', 'wait'))

    def test_down_to_start_race(self):
        d = autodrive.decide
        self.assertEqual(d('rally', ['setup_other', 'setup_other'], 2), 'press')                # Down
        self.assertEqual(d('setup_other', ['setup_other', 'setup_other'], 2, 0), 'press')       # Down again
        self.assertEqual(d('setup_other', ['setup', 'setup'], 2), 'press')                      # START RACE
        self.assertNotIn(d('setup_other', ['setup_other', 'setup_other'], 13, 2), ('press', 'wait'))

    def test_never_presses_twice_on_one_screen(self):
        self.assertEqual(autodrive.decide('racing', ['racing', 'racing'], 2), 'wait')

    def test_moves_the_highlight_to_the_right_tile_first(self):
        d = autodrive.decide
        self.assertEqual(d('home', ['racing_other', 'racing_other'], 2), 'press')          # Up
        self.assertEqual(d('racing_other', ['racing_other', 'racing_other'], 2, 0), 'press')  # Up once more
        self.assertNotIn(d('racing_other', ['racing_other', 'racing_other'], 13, 2), ('press', 'wait'))  # 3 is it
        self.assertEqual(d('racing_other', ['racing', 'racing'], 2), 'press')               # there: Select
        self.assertEqual(d('racing', ['rally_right', 'rally_right'], 2), 'press')           # Left
        self.assertEqual(d('rally_right', ['rally', 'rally'], 2), 'press')
        self.assertEqual(d('rally_right', ['rally_right', 'rally_right'], 2), 'wait')       # Left: once


class Keys(unittest.TestCase):
    def save(self, *entries):
        b = b'GVAS' + b'\x00' * 20
        for e in entries:
            b += b''.join(fstr(s) for s in e) + b'\x05\x00\x00\x00\x00\x00'
        f = tempfile.NamedTemporaryFile(delete=False, suffix='.sav')
        f.write(b)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_defaults_and_the_wheel_does_not_count(self):
        p = self.save(('Select', 'GenericUSBController_Button4_3670_0500', 'RawInput', 'SteeringWheel'))
        default = {'select': 'Enter', 'tab_right': 'E', 'up': 'Up', 'down': 'Down', 'left': 'Left'}
        self.assertEqual(autodrive.player_keys(p), default)
        self.assertEqual(autodrive.player_keys(os.path.join(FIX, 'missing.sav')), default)

    def test_rebound_keys(self):
        p = self.save(('SelectKeyboard', 'SpaceBar', 'KBM', 'KeyboardAndMouse'),
                      ('UpKeyboard', 'W', 'KBM', 'KeyboardAndMouse'), ('LeftKeyboard', 'A', 'KBM', 'KeyboardAndMouse'))
        self.assertEqual(autodrive.player_keys(p), {'select': 'SpaceBar', 'tab_right': 'E', 'up': 'W', 'down': 'Down',
                                                    'left': 'A'})

    def test_the_keys_in_words(self):
        self.assertEqual(autodrive.describe_keys({'select': 'Enter', 'tab_right': 'E', 'up': 'Up', 'down': 'Down',
                                                  'left': 'Left'}),
                         'Enter to select, E for the Racing tab, Up arrow, Down arrow and Left arrow to move the '
                         'highlight onto the right button')
        self.assertTrue(autodrive.describe_keys({'select': 'SpaceBar', 'tab_right': 'E', 'up': 'W', 'down': 'S',
                                                 'left': 'A'}).startswith('Space to select, E for the Racing tab, W, S and A'))

    def test_a_key_it_will_not_press(self):
        with self.assertRaises(ValueError):
            autodrive.player_keys(self.save(('SelectKeyboard', 'Y', 'KBM', 'KeyboardAndMouse')))       # Exit Game
        with self.assertRaises(ValueError):
            autodrive.player_keys(self.save(('SelectKeyboard', 'LeftMouseButton', 'KBM', 'KeyboardAndMouse')))


class Record(unittest.TestCase):
    def test_kept_when_it_stops_short(self):
        a = autodrive.AutoDrive(lambda t: None)
        d = tempfile.mkdtemp()
        a._note('screen: rally')
        a.record(d)
        with open(os.path.join(d, 'autodrive-last.txt'), encoding='utf-8') as f:
            self.assertIn('screen: rally', f.read())


if __name__ == '__main__':
    unittest.main()
