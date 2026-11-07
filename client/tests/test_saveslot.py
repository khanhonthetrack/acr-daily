"""The save editor on a copy of the real save (skipped when the game's save isn't on this PC), and on a new
player's save (fixtures/saves/new-player.sav: the game freshly installed, one Rally Weekend started, nothing else)."""
import ctypes
import os
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from acr_daily import rallyweekend, saveslot  # noqa: E402

NEW_PLAYER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'saves', 'new-player.sav')


class NewPlayer(unittest.TestCase):
    """A player who has never driven a Single Rally Stage: the per-mode settings hold only "DefaultRally", and the
    selection after them has the game's default car and no weather options."""

    def setUp(self):
        with open(NEW_PLAYER, 'rb') as f:
            self.b = f.read()

    def test_the_selection_is_found_without_a_single_stage_entry(self):
        self.assertNotIn(saveslot.SECTION, self.b)
        s = saveslot.read_setup(self.b)
        self.assertEqual((s['stage'][1], s['car'][1]), (b'WelesS3HafrenNorthFullForward', b'LanciaDeltaIntegraleEvo'))
        self.assertFalse({'time', 'preset', 'speed'} & set(s))

    def test_a_rally_weekend_daily_sets_the_car(self):
        new = rallyweekend.apply_weekend(self.b, 'MonteCarloS1BolleneFullReverse', 'CitroenXsaraWRC', 57600, 'WT_HEAVY_CLOUDS')
        s = saveslot.read_setup(new)
        self.assertEqual((s['stage'][1], s['car'][1]), (b'MonteCarloS1BolleneFullReverse', b'CitroenXsaraWRC'))
        w = rallyweekend.read_weekend(new)
        self.assertEqual((w['preset'], [x['stage'] for x in w['stages']]), ('MontecarloWeekendShort', ['MonteCarloS1BolleneFullReverse']))
        so = saveslot._payload(new)
        self.assertEqual(struct.unpack_from('<i', new, so)[0], len(new) - so - 4)
        self.assertEqual(new[-200:], self.b[-200:])               # the driver profile after it is untouched

    def test_a_single_stage_daily_needs_the_weather_options(self):
        with self.assertRaises(saveslot.SaveError) as e:
            saveslot.apply_daily(self.b, 'MonteCarloS1BolleneFullReverse', 'CitroenXsaraWRC', 57600, 'WT_CLEAR')
        self.assertIn('Single Rally Stage', str(e.exception))

    def test_the_stock_driver_has_no_country(self):
        self.assertIsNone(saveslot.driver_country(self.b))        # Irvin Zonca, Italy: the profile never set up


def _text(s):
    """An FString as the game writes it: ASCII, or UTF-16 with a negative length for any other letter."""
    if all(ord(c) < 128 for c in s):
        return struct.pack('<i', len(s) + 1) + s.encode('ascii') + b'\0'
    return struct.pack('<i', -(len(s) + 1)) + s.encode('utf-16-le') + b'\0\0'


def _profile(*people):
    """The end of a save: each person's first name, last name (texts: flags, kind, namespace, GUID key, the name) and
    country, as in new-player.sav."""
    out = b'\0' * 40
    for k, (first, last, country) in enumerate(people):
        for j, name in enumerate((first, last)):
            out += struct.pack('<iB', 0, 0) + _text('') + _text('%032X' % (k * 2 + j + 1)) + _text(name)
        out += _text(country)
    return out + struct.pack('<i', 7) + b'\0' * 4


class DriverCountry(unittest.TestCase):
    """The nationality in the driver profile, whatever the driver's name (any length, any letters)."""

    def test_names(self):
        co = ('Alexandre', 'Lebertre', 'Italy')
        for first, last in (('Khanh', 'Nguyen'), ('Łukasz', 'Żółć'), ('Li', 'Wu'), ('Zoë', 'Ng'), ('', 'X')):
            self.assertEqual(saveslot.driver_country(_profile((first, last, 'Poland'), co)), 'Poland', (first, last))
        self.assertEqual(saveslot.driver_country(_profile(('Irvin', 'Zonca', 'Vietnam'), co)), 'Vietnam')  # own country
        self.assertIsNone(saveslot.driver_country(_profile(saveslot.STOCK_DRIVER, co)))
        self.assertIsNone(saveslot.driver_country(b'GVAS' + b'\0' * 100))

    def test_utf16_text(self):
        b = _text('Łukasz') + _text('ok')
        self.assertEqual(saveslot._text_at(b, 0), ('Łukasz', len(_text('Łukasz'))))
        self.assertEqual(saveslot._text_at(b, len(_text('Łukasz'))), ('ok', len(b)))
        self.assertIsNone(saveslot._text_at(struct.pack('<i', -5) + b'\0' * 4, 0))   # runs past the end


@unittest.skipUnless(os.path.exists(saveslot.SAVE), 'no game save')
class SaveSlot(unittest.TestCase):
    def setUp(self):
        with open(saveslot.SAVE, 'rb') as f:
            self.b = f.read()

    def test_reads_the_current_setup(self):
        s = saveslot.read_setup(self.b)
        print('\n  current online single stage:', {k: v[1].decode() for k, v in s.items()})
        self.assertRegex(s['stage'][1].decode(), r'S\d')
        self.assertTrue(s['time'][1].startswith(b'(TimeSeconds='))

    def test_writes_a_daily_and_only_that(self):
        new = saveslot.apply_daily(self.b, 'WelesS4HafrenSouthFullForward', 'LanciaStratosHF', 57600, 'WT_LIGHT_FOG')
        s = saveslot.read_setup(new)
        self.assertEqual(s['stage'][1], b'WelesS4HafrenSouthFullForward')
        self.assertEqual(s['car'][1], b'LanciaStratosHF')
        self.assertEqual(s['time'][1], b'(TimeSeconds=57600.000000)')
        self.assertTrue(s['preset'][1].startswith(b'(WeatherType=WT_LIGHT_FOG,'))
        self.assertTrue(s['preset'][1].endswith(b'bRandom=False)'))
        self.assertEqual(s['speed'][1], b'WT_SPEEDFIX')
        # the block size matches the new file
        so = saveslot._payload(new)
        self.assertEqual(struct.unpack_from('<i', new, so)[0], len(new) - so - 4)
        # everything before the selection (stage, car, weather options) is byte for byte the same
        i = saveslot.read_setup(self.b)['stage'][0]
        self.assertEqual(new[so + 4:i], self.b[so + 4:i])
        self.assertEqual(new[:so], self.b[:so])
        # and the end of the file (records etc.) too
        tail = 1500
        self.assertEqual(new[-tail:], self.b[-tail:])

    def test_setting_it_back_gives_the_original_file(self):
        s = saveslot.read_setup(self.b)
        new = saveslot.apply_daily(self.b, 'AlsaceS4SaverneFullForward', 'Peugeot208Rally4', 32400, 'WT_CLEAR')
        orig = {k: v[1].decode() for k, v in s.items()}
        import re
        back = saveslot.apply_daily(new, orig['stage'], orig['car'],
                                    float(re.search(r'=([0-9.]+)', orig['time']).group(1)),
                                    re.search(r'WeatherType=(\w+)', orig['preset']).group(1), orig['speed'])
        self.assertEqual(back, self.b)

    def test_refuses_a_broken_file(self):
        with self.assertRaises(saveslot.SaveError):
            saveslot.apply_daily(self.b[:-10], 'AlsaceS4SaverneFullForward', 'Peugeot208Rally4', 32400, 'WT_CLEAR')
        with self.assertRaises(saveslot.SaveError):
            saveslot.apply_daily(b'NOPE' + self.b[4:], 'AlsaceS4SaverneFullForward', 'Peugeot208Rally4', 32400, 'WT_CLEAR')


class FakeKernel32:
    """CreateFileW / ReadFile / CloseHandle over bytes, handing out `chunk` bytes a read."""

    def __init__(self, data, chunk=7, fail_read=False):
        self.data, self.chunk, self.fail_read, self.opened, self.closed, self.pos = data, chunk, fail_read, None, 0, 0

    def CreateFileW(self, path, access, share, security, disposition, flags, template):
        self.opened = (path, access, share, disposition)
        return 1234

    def ReadFile(self, h, address, n, got, overlapped):
        if self.fail_read:
            return 0
        part = self.data[self.pos:self.pos + min(n, self.chunk)]
        ctypes.memmove(address, part, len(part))
        got._obj.value = len(part)
        self.pos += len(part)
        return 1

    def CloseHandle(self, h):
        self.closed += 1
        return 1


class ReadingWhileTheGameRuns(unittest.TestCase):
    """The game writes its save as the driver leaves a stage's results screen, and wants the file to itself while it
    does: the waits for a stage's result look at the file's time and size, and read it only once it has changed and
    settled (SaveWatch); a read shares read, write and delete on Windows (read_save)."""

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'PlayerDataSaveSlot.sav')

    def write(self, data, age):
        """The game writing its save `age` seconds ago."""
        with open(self.path, 'wb') as f:
            f.write(data)
        t = time.time() - age
        os.utime(self.path, (t, t))

    def test_read_once_per_settled_change(self):
        w = saveslot.SaveWatch(self.path)
        self.assertIsNone(w.look())                               # no save yet
        self.write(b'before the stage', 60)
        self.assertEqual(w.look(), b'before the stage')           # an old save: read at once
        self.assertIsNone(w.look())                               # unchanged: not read again
        self.write(b'the stage result!', 0)                       # the game writing it just now
        with mock.patch.object(saveslot, 'read_save', side_effect=AssertionError('read as the game writes')):
            self.assertIsNone(w.look())                           # not opened at all
        self.assertEqual(w.look(), b'the stage result!')          # the same at the next look: settled, read
        self.assertIsNone(w.look())
        self.write(b'written as the game exits', 30)
        self.assertEqual(w.look(), b'written as the game exits')  # changed long enough ago: read at once

    def test_a_read_that_fails_is_tried_again(self):
        w = saveslot.SaveWatch(self.path)
        self.write(b'result', 60)
        with mock.patch.object(saveslot, 'read_save', side_effect=PermissionError(13, 'in use')):
            self.assertIsNone(w.look())                           # the game had it open after all
        self.assertEqual(w.look(), b'result')

    def test_read_save_shares_the_file_on_windows(self):
        data = bytes(range(256)) * 300                            # (more than one ReadFile)
        k = FakeKernel32(data, chunk=1 << 15)
        with mock.patch.object(saveslot, '_kernel32', k):
            self.assertEqual(saveslot._read_shared('C:\\save.sav'), data)
        self.assertEqual(k.opened, ('C:\\save.sav', 0x80000000, 0x7, 3))   # GENERIC_READ; read | write | delete
        self.assertEqual(k.closed, 1)
        k = FakeKernel32(data, fail_read=True)
        with mock.patch.object(saveslot, '_kernel32', k), \
                mock.patch('ctypes.get_last_error', return_value=32, create=True), \
                mock.patch('ctypes.WinError', side_effect=lambda c: PermissionError(13, 'winerror %d' % c), create=True):
            with self.assertRaises(PermissionError):
                saveslot._read_shared('C:\\save.sav')
        self.assertEqual(k.closed, 1)                             # closed whatever happens

    def test_read_save_falls_back_to_open(self):
        self.write(b'plain', 60)
        self.assertEqual(saveslot.read_save(self.path), b'plain')
        with mock.patch.object(saveslot.os, 'name', 'nt'), \
                mock.patch.object(saveslot, '_read_shared', side_effect=AttributeError('no WinDLL')):
            self.assertEqual(saveslot.read_save(self.path), b'plain')
        with mock.patch.object(saveslot.os, 'name', 'nt'), \
                mock.patch.object(saveslot, '_read_shared', side_effect=PermissionError(13, 'in use')):
            with self.assertRaises(OSError):                      # the game has it: said so, not read another way
                saveslot.read_save(self.path)


if __name__ == '__main__':
    unittest.main()
