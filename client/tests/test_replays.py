"""REPLAYS (replays.py, replayui.py, replayplay.py, ig_replay.py): Ed25519 as RFC 8032 has it, a run recorded from the
telemetry and kept signed, the chain sent to the server while driving (the final commit at the finish line), a run cut
short by the app closing kept, the store's keep / star / import, the replay's clock in the game (play, pause, speed,
seek), what the server wants found here, and the REPLAY page's tree. Never the real APPDATA: settings.DIR is a temp one."""
import json
import math
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace as N
from unittest import mock

from acr_daily import ed25519, replays, settings


def frame(c, track='Test Road', car='Car', x=None, speed=100.0, airborne=False):
    a = c / 20000.0
    return N(track=track, car=car, clock_ms=c, x=1000 * math.cos(a) if x is None else x, y=50.0, z=1000 * math.sin(a),
             heading=a, pitch=0.01, roll=-0.02, speed=speed, gear=5, rpm=6000, gas=0.8, brake=0.0, steer=0.1,
             airborne=airborne)


def drive(rec, t0, ms, step=50, **kw):
    for c in range(0, ms + 1, step):
        rec.feed(frame(c, **kw), t0 + c / 1000.0)


class FakeApi:
    def __init__(self, fail=False):
        self.begins, self.commits, self.fail = [], [], fail

    def replay_begin(self, body):
        if self.fail:
            raise OSError('offline')
        self.begins.append(body)
        return {'rid': 'r' * 16, 'nonce': 'n' * 24}

    def replay_commit(self, body):
        self.commits.append(body)
        return {'ok': True}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = mock.patch.object(settings, 'DIR', self.tmp)
        self.p.start()
        replays._key = None

    def tearDown(self):
        self.p.stop()
        replays._key = None
        shutil.rmtree(self.tmp, ignore_errors=True)


class Ed25519(unittest.TestCase):
    def test_rfc8032_vectors(self):
        for sk, pk, msg, sig in (
                ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
                 'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
                 'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
                ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
                 '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
                 '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')):
            seed, pub = ed25519.keypair(bytes.fromhex(sk))
            self.assertEqual(pub.hex(), pk)
            s = ed25519.sign(seed, bytes.fromhex(msg))
            self.assertEqual(s.hex(), sig)
            self.assertTrue(ed25519.verify(pub, bytes.fromhex(msg), s))
            self.assertFalse(ed25519.verify(pub, bytes.fromhex(msg) + b'x', s))
            self.assertFalse(ed25519.verify(pub, bytes.fromhex(msg), s[:-1] + bytes([s[-1] ^ 1])))


class Recording(Base):
    def test_a_run_kept_signed_with_its_end(self):
        rec = replays.Recorder({}, app_version='0.2.3', penalty=lambda: (5000, False))
        drive(rec, 100.0, 60000)
        rec.tag('practice', None, 'free', False)
        rec.outcome('finished', {'clockMs': 60000, 'resets': 0, 'totalMs': 60000})
        # (the results screen: the clock stopped, the game's penalty read in, then the game leaves the stage)
        for k in range(5):
            rec.feed(frame(60000), 100.0 + 60 + 1.2 * k)
        rec.feed(None, 200.0)
        self.assertEqual(len(rec.saved), 1)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual(doc['head']['status'], 'finished')
        self.assertEqual(doc['head']['finMs'], 60000)
        self.assertEqual(doc['head']['penaltyMs'], 5000)
        self.assertEqual(len(doc['rows']), 600)                # (every 100 ms of clock, from its first)
        self.assertTrue(all(len(r) == 14 and all(isinstance(v, int) for v in r) for r in doc['rows']))
        chk = replays.check(doc)
        self.assertTrue(chk['signed'])
        self.assertFalse(chk['live'])
        doc['rows'][5][1] += 1                                 # (changed: no longer its signature)
        self.assertFalse(replays.check(doc)['signed'])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'replay-key.json')))

    def test_a_restart_is_a_new_run_and_a_joined_run_is_not_kept(self):
        rec = replays.Recorder({})
        drive(rec, 0.0, 10000)
        drive(rec, 20.0, 8000)                                 # (the clock back to 0: a restart)
        rec.feed(None, 40.0)
        self.assertEqual(len(rec.saved), 2)
        rec2 = replays.Recorder({})
        for c in range(30000, 40000, 50):                      # (the app started mid-stage)
            rec2.feed(frame(c), c / 1000.0)
        rec2.feed(None, 50.0)
        self.assertEqual(rec2.saved, [])

    def test_off_in_the_settings_keeps_nothing(self):
        rec = replays.Recorder({'replays': {'on': False}})
        drive(rec, 0.0, 10000)
        rec.feed(None, 20.0)
        self.assertEqual(rec.saved, [])

    def test_a_counted_run_is_followed_by_the_server_and_its_finish_sent_at_once(self):
        api = FakeApi()
        rec = replays.Recorder({'token': 't'}, api=api, me=lambda: {'steamId': '7656', 'name': 'Ann'})
        rec.feed(frame(0), 0.0)
        rec.feed(frame(50), 0.05)
        rec.tag('daily', '2026-11-26/1', 'SS1', True, stageId='S1', carId='C1')
        import time as _t
        for _ in range(50):                                    # (the begin answered, in its thread)
            if rec.run['live'].get('h'):
                break
            _t.sleep(0.01)
        drive(rec, 0.0, 35000)
        rec.outcome('finished', {'clockMs': 35000, 'resets': 0, 'totalMs': 35000})
        for _ in range(100):
            if api.commits and api.commits[-1].get('fin'):
                break
            _t.sleep(0.01)
        self.assertEqual(api.begins[0]['kind'], 'daily')
        self.assertEqual(len(api.begins[0]['key']), 64)
        self.assertEqual([c['n'] for c in api.commits], list(range(1, len(api.commits) + 1)))
        self.assertEqual(api.commits[-1]['fin'], 35000)
        self.assertGreaterEqual(len(api.commits), 4)          # (every 10 s of the stage, and the finish)
        rec.feed(None, 100.0)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual(doc['head']['stageId'], 'S1')
        self.assertEqual(doc['live']['rid'], 'r' * 16)
        chk = replays.check(doc)
        self.assertTrue(chk['signed'] and chk['live'] and chk['chain'], chk)
        # the hashes sent are the file's own chain
        self.assertEqual([c['hash'] for c in api.commits], [h for _n, h in doc['live']['commits']])

    def test_offline_the_run_is_kept_all_the_same(self):
        rec = replays.Recorder({'token': 't'}, api=FakeApi(fail=True))
        rec.feed(frame(0), 0.0)
        rec.feed(frame(100), 0.1)
        rec.tag('daily', '2026-11-26/1', 'SS1', True)
        import time as _t
        _t.sleep(0.1)
        drive(rec, 0.0, 5000)
        rec.feed(None, 50.0)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertIsNone(doc['live'])
        self.assertTrue(replays.check(doc)['signed'])

    def test_a_run_cut_short_by_the_app_closing_is_kept(self):
        rec = replays.Recorder({})
        drive(rec, 0.0, 12000)                                 # (its rows on disk every 5 s)
        self.assertTrue(os.path.exists(os.path.join(replays.folder(), 'recording.part')))
        name = replays.recover()
        doc = replays.read(replays.path_of(name))
        self.assertIn('cut short', doc['head']['reason'])
        self.assertTrue(replays.check(doc)['signed'])
        self.assertIsNone(replays.recover())


class Store(Base):
    def doc(self, created, kind='practice'):
        rows = [[i * 100, i, 0, 0, 0, 0, 0, 100, 5, 5000, 1000, 0, 0, 0] for i in range(30)]
        return replays.sign_doc({'format': 'acr-replay', 'v': 1, 'head': {'created': created, 'track': 'T', 'car': 'C',
                                                                          'kind': kind, 'status': 'ended'},
                                 'cols': list(replays.COLS), 'rows': rows, 'live': None})

    def test_the_newest_are_kept_a_starred_one_and_one_sent_never_dropped(self):
        names = [replays.save(self.doc(1000 + i), keep=3) for i in range(3)]
        replays.update(names[0], star=True)
        got = tempfile.mktemp(suffix=replays.EXT, dir=self.tmp)
        with open(got, 'wb') as f:
            f.write(replays.dumps(self.doc(500)))
        theirs = replays.import_file(got, keep=3)
        for i in range(3, 6):
            replays.save(self.doc(1000 + i), keep=3)
        kept = {r['file'] for r in replays.index()}
        self.assertIn(names[0], kept)                          # (starred)
        self.assertIn(theirs, kept)                            # (someone else's)
        self.assertEqual(len(kept), 5)
        self.assertFalse(next(r for r in replays.index() if r['file'] == theirs)['mine'])
        # the index made again from the files when it is gone
        os.remove(os.path.join(replays.folder(), 'index.json'))
        self.assertEqual(len(replays.index()), 5)

    def test_not_a_replay(self):
        with self.assertRaises(ValueError):
            replays.loads(b'hello')
        with self.assertRaises(ValueError):
            replays.loads(replays.dumps({'format': 'acr-replay', 'v': 99, 'head': {}, 'rows': []}))

    def test_what_the_server_wants_is_found_here(self):
        from acr_daily import replayui
        a = replays.save(self.doc(1000, 'event'))
        b = replays.save(self.doc(2000, 'event'))
        replays.update(a, rid='x' * 16, ref='event:5:1')
        replays.update(b, ref='event:5:1')
        self.assertEqual(replayui.find_local({'rid': 'x' * 16}), a)
        self.assertEqual(replayui.find_local({'ref': 'event:5:1', 'why': 'steward'}), a)   # (the followed one first)
        self.assertIsNone(replayui.find_local({'ref': 'event:9:0', 'why': 'steward'}))


class Playback(Base):
    def test_the_viewers_clock(self):
        from acr_daily import replayplay
        rows = [[100 + i * 100, i * 100, 0, 0, 0, 0, 0, 360, 5, 5000, 1000, 0, 0, 0] for i in range(600)]
        d = replayplay.ReplayDriver({'head': {'driver': {'name': 'Ann'}, 'car': 'Car', 'finMs': 60000}, 'rows': rows})
        self.assertTrue(d.paused)
        with mock.patch('time.monotonic', return_value=10.0):
            d.play(True)
        self.assertAlmostEqual(d.clock(12.0), 2100.0)
        with mock.patch('time.monotonic', return_value=12.0):
            d.speed(+1)
        self.assertEqual(d.rate, 2.0)
        self.assertAlmostEqual(d.clock(13.0), 4100.0)
        self.assertEqual(d.rate_now(), 2.0)
        with mock.patch('time.monotonic', return_value=13.0):
            d.play(False)
        self.assertEqual(d.rate_now(), 0.0)
        self.assertAlmostEqual(d.clock(99.0), 4100.0)
        d.seek(1e9)
        self.assertEqual(d.clock(), 60000)
        with mock.patch('time.monotonic', return_value=20.0):
            d.play(True)                                       # (at its end: from the start again)
        self.assertEqual(d.clock(20.0), 100)
        pose = d.pose(20.5)
        self.assertIsNotNone(pose)
        self.assertEqual(d.dash_at(20.5)['gear'], 5)

    def test_it_waits_for_the_viewer_at_the_start_line(self):
        from acr_daily import replayplay
        rows = [[100 + i * 100, i * 100, 0, 0, 0, 0, 0, 360, 5, 5000, 1000, 0, 0, 0] for i in range(100)]
        d = replayplay.ReplayDriver({'head': {'track': 'Wales Afon Bidno', 'car': 'Car'}, 'rows': rows})
        menus = N(track=None, clock_ms=None)
        park = N(track='Wales Afon Bidno', clock_ms=-1)              # (the Service Park: no stage clock)
        line = N(track='Wales Afon Bidno', clock_ms=0)
        for f, t in ((menus, 1.0), (park, 2.0), (line, 3.0), (line, 4.0)):
            d.arm(f, t)
        self.assertTrue(d.waiting and d.paused)                       # (not yet ARM_S at the line)
        d.arm(line, 5.5)
        self.assertFalse(d.waiting or d.paused)
        self.assertEqual(round(d.clock()), 100)                       # (from its start)


class Page(Base):
    def test_the_replay_page_and_the_home_tile_build(self):
        from acr_daily import ig_home, ig_replay
        from acr_daily.ingamekit import check
        rec = replays.Recorder({})
        drive(rec, 0.0, 10000)
        rec.feed(None, 20.0)

        class IG:
            def __init__(self):
                self._m = {}
                self.notes = []
                self.app = N(s={}, replay_asks=[{'ref': 'event:3:1', 'requestId': 7}], replay_note='', driver={},
                             credits=None, _home_spec=lambda k: {})

            def mem(self, tab):
                return self._m.setdefault(tab, {})

            def note(self, w):
                self.notes.append(w)
        ig = IG()
        tree = ig_replay.page(ig)
        check(tree)
        text = json.dumps(tree)
        self.assertIn('WATCH IN THE GAME', text)
        self.assertIn('Test Road', text)
        self.assertIn('ask_send', text)
        spec = ig_home.spec(ig, 'replay')
        self.assertEqual(spec['photo'], 'replay')
        self.assertEqual(spec['badge'][0], '1 ASKED')


if __name__ == '__main__':
    unittest.main()
