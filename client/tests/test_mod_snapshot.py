"""The game mod's copy of the car at the finish line (mod/.../drive.lua snap_read / snap_write: the car as it crossed the
line written into the game's own store at NEXT STAGE; the user, 24 Nov 2026): test_mod_snapshot.lua, run with a Lua
interpreter if one is found (lua, luajit, texlua), else skipped."""
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'mod', 'ACRDailyGhosts', 'Scripts'))
LUA = next((p for p in (shutil.which(n) for n in ('lua', 'lua5.4', 'luajit', 'texlua')) if p), None) or next(
    (p for p in (r'D:\MiKTeX\miktex\bin\x64\texlua.exe',) if os.path.exists(p)), None)


@unittest.skipIf(LUA is None, 'no Lua interpreter')
class FinishLineCar(unittest.TestCase):
    def test_the_car_at_the_line_goes_into_the_games_store(self):
        r = subprocess.run([LUA, os.path.join(HERE, 'test_mod_snapshot.lua'), SCRIPTS.replace('\\', '/')],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), 'ok', r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
