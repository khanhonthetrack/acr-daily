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
        self.assertEqual(len(doc['rows']), 601)                # (every 100 ms of clock, from its first, and the finish's)
        self.assertEqual(doc['rows'][-1][0], 60000)
        self.assertTrue(all(len(r) == 14 and all(isinstance(v, int) for v in r) for r in doc['rows']))
        chk = replays.check(doc)
        self.assertTrue(chk['signed'])
        self.assertFalse(chk['live'])
        doc['rows'][5][1] += 1                                 # (changed: no longer its signature)
        self.assertFalse(replays.check(doc)['signed'])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'replay-key.json')))

    def test_the_cars_damage_kept_as_it_came(self):
        hit = 'D coll_front=0.40 P Root_BumperF Z 3=0.50'
        looks = {'now': ''}
        rec = replays.Recorder({}, look=lambda: looks['now'])
        drive(rec, 0.0, 20000)
        looks['now'] = hit                                     # (a crash 20 s in)
        for c in range(20050, 30001, 50):
            rec.feed(frame(c), c / 1000.0)
        rec.outcome('finished', {'clockMs': 30000, 'resets': 0, 'totalMs': 30000})
        rec.feed(None, 60.0)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual([x[1] for x in doc['looks']], ['', hit])   # (only when it changes)
        self.assertTrue(20000 <= doc['looks'][1][0] <= 21000)
        self.assertTrue(replays.check(doc)['signed'])                  # (not in the signature: still signed)

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

    def test_it_stops_at_the_finish_line(self):
        """At its end (the finish line) the car stands: no speed sent with it, so the mod doesn't carry it on past the
        line and back between updates (the user, 26 Nov 2026: "it should STOP. Not stutter")."""
        from acr_daily import replayplay
        rows = [[100 + i * 100, i * 1000, 0, 0, 0, 0, 0, 360, 5, 5000, 1000, 0, 0, 0] for i in range(50)]
        d = replayplay.ReplayDriver({'head': {'car': 'Car'}, 'rows': rows})
        with mock.patch('time.monotonic', return_value=10.0):
            d.play(True)
        moving = d.motion(11.0)[1]
        self.assertGreater(abs(moving[0]), 50)                      # (10 m per 100 ms of its clock: 100 m/s)
        with mock.patch('time.monotonic', return_value=11.0):
            d.speed(+1)                                              # (2x: twice as fast in the viewer's time)
        self.assertAlmostEqual(d.motion(11.5)[1][0], 2 * moving[0], delta=abs(moving[0]) * 0.05)
        end = d.motion(99.0)                                         # (past its end: held at the line)
        self.assertTrue(d.paused)
        self.assertEqual(round(d.clock(99.0)), rows[-1][0])
        self.assertEqual(end[1], (0.0,) * 6)
        self.assertEqual(d.motion(100.0)[0], end[0])                 # (and still there)

    def test_its_damage_as_it_came(self):
        """The car's dents and panels as the game drew them while driving (doc 'looks'), put on the replay's car at the
        replay's clock (the user, 27 Nov 2026: "make sure that replays also have the data so we can actually see
        damage on replay")."""
        from acr_daily import replayplay
        rows = [[100 + i * 100, i * 100, 0, 0, 0, 0, 0, 360, 5, 5000, 1000, 0, 0, 0] for i in range(100)]
        hit = 'D coll_front=0.40 P Root_BumperF Z 3=0.50'
        d = replayplay.ReplayDriver({'head': {'car': 'Car'}, 'rows': rows, 'looks': [[100, ''], [5000, hit]]})
        d.seek(2000)
        self.assertEqual(d.look_now(), '')                            # (before the crash: as new)
        d.seek(6000)
        self.assertEqual(d.look_now(), hit)
        d.seek(100)
        self.assertEqual(d.look_now(), '')                            # (back to the start: as new again)
        self.assertIsNone(replayplay.ReplayDriver({'head': {}, 'rows': rows}).look_now())   # (an older replay)

    def test_the_mods_look_file(self):
        from acr_daily import ingamedrive
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'ingame-carlook.txt')

            def read(text):
                with open(p, 'w', encoding='ascii') as fh:
                    fh.write(text + ' ' * 50 + '\n')
                return ingamedrive.read_look(p)
            self.assertEqual(read('ACRLOOK 4 D coll_front=0.40 P Root_Hood,Root_Boot Z 3=0.50 end 4'),
                             'D coll_front=0.40 P Root_Hood,Root_Boot Z 3=0.50')
            self.assertEqual(read('ACRLOOK 5 D  P  Z  end 5'), '')       # (as new)
            self.assertIsNone(read('ACRLOOK 6 none end 6'))             # (no car of yours)
            self.assertIsNone(read('ACRLOOK 7 D  P  Z  end 6'))         # (half written)

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


# ---------------------------------------------------------------------- the ways a finish gets lost (26 Nov 2026)

class FakeServer:
    """The server's begin / commit / run as src/replays.js has them (in order, each once), with a connection that can
    go down (down=True: every call fails as offline) and an answer that can be lost after the server took it."""

    def __init__(self):
        self.runs, self.down, self.lose_answer, self.calls = {}, False, set(), []

    def _net(self):
        if self.down:
            raise OSError('offline')

    def replay_begin(self, body):
        self._net()
        rid = '%016d' % (len(self.runs) + 1)
        self.runs[rid] = {'begin': body, 'commits': []}
        self.calls.append(('begin', body['clockMs']))
        return {'rid': rid, 'nonce': 'n' * 24}

    def replay_commit(self, body):
        self._net()
        run = self.runs[body['rid']]
        if body['n'] != len(run['commits']) + 1:
            e = OSError('not this run\'s next commit')
            e.code = 409
            raise e
        run['commits'].append([body['count'], body['hash'], body.get('fin')])
        self.calls.append(('commit', body['n']))
        if body['n'] in self.lose_answer:          # (the server took it, its answer never came)
            self.lose_answer.discard(body['n'])
            raise OSError('timed out')
        return {'ok': True}

    def replay_run(self, rid):
        self._net()
        return {'have': len(self.runs[rid]['commits']), 'open': True}


def wait_for(cond, s=5.0):
    import time as _t
    end = _t.time() + s
    while _t.time() < end:
        if cond():
            return True
        _t.sleep(0.01)
    return False


class LostFinishes(Base):
    def setUp(self):
        super().setUp()
        self.fast = mock.patch.multiple(replays, RETRY_S=0.01, RETRY_MAX_S=0.02)
        self.fast.start()

    def tearDown(self):
        self.fast.stop()
        super().tearDown()

    def rec(self, srv, **kw):
        return replays.Recorder({'token': 't'}, api=srv, me=lambda: {'steamId': '7656', 'name': 'Ann'}, **kw)

    def drive_counted(self, rec, ms, t0=0.0, during=None, kind='daily', ref='2026-11-26/1'):
        """A counted run, its frames as fast as they go; the sender given its time where a stage's real seconds would
        (each 10 s of clock, after the begin): during(c) may take the connection down / up."""
        rec.feed(frame(50), t0 + 0.05)
        rec.tag(kind, ref, 'SS1', True)
        wait_for(lambda: rec.sender.idle(), 1.0)
        for c in range(100, ms + 1, 50):
            if during:
                during(c)
            rec.feed(frame(c), t0 + c / 1000.0)
            if c % 10000 == 0:
                wait_for(lambda: rec.sender.idle(), 0.3)

    def chain_ok(self, srv, rid, doc):
        """The server's commits are the file's chain, in order."""
        h = replays.chain_start(rid, 'n' * 24)
        at = 0
        for count, hh, _fin in srv.runs[rid]['commits']:
            h = replays.chain_next(h, doc['rows'][at:count])
            at = count
            if h != hh:
                return False
        return True

    def test_the_connection_lost_for_a_while_every_commit_gets_there_in_order(self):
        srv = FakeServer()
        rec = self.rec(srv)
        down = lambda c: setattr(srv, 'down', 30000 <= c < 70000)   # noqa: E731  (40 s with no connection)
        self.drive_counted(rec, 100000, during=down)
        rec.outcome('finished', {'clockMs': 100000, 'resets': 0, 'totalMs': 100000})
        rec.feed(None, 300.0)
        self.assertTrue(wait_for(lambda: rec.sender.idle()))
        rid = next(iter(srv.runs))
        commits = srv.runs[rid]['commits']
        self.assertEqual(commits[-1][2], 100000)                       # (the finish, at the end)
        self.assertGreaterEqual(len(commits), 9)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertTrue(self.chain_ok(srv, rid, doc))
        self.assertGreater(rec.sender.failures, 0)

    def test_the_connection_down_at_the_start_followed_from_when_it_came_back(self):
        srv = FakeServer()
        srv.down = True
        rec = self.rec(srv)
        self.drive_counted(rec, 60000, during=lambda c: setattr(srv, 'down', c < 20000))
        rec.outcome('finished', {'clockMs': 60000, 'resets': 0, 'totalMs': 60000})
        rec.feed(None, 300.0)
        self.assertTrue(wait_for(lambda: rec.sender.idle()))
        rid = next(iter(srv.runs))
        self.assertGreaterEqual(srv.runs[rid]['begin']['clockMs'], 19900)   # (begun late: the server follows from there)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual(doc['live']['rid'], rid)
        self.assertTrue(self.chain_ok(srv, rid, doc))
        self.assertEqual(srv.runs[rid]['commits'][0][0], [c for c, _h in doc['live']['commits']][0])
        self.assertTrue(replays.check(doc)['chain'])

    def test_a_run_kept_before_its_begin_got_there_gets_its_server_part_after(self):
        srv = FakeServer()
        srv.down = True
        rec = self.rec(srv)
        self.drive_counted(rec, 30000)
        rec.outcome('finished', {'clockMs': 30000, 'resets': 0, 'totalMs': 30000})
        rec.feed(None, 300.0)                                           # (kept: no run id yet)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertIsNone(doc['live'])
        srv.down = False                                                # (the connection back)
        self.assertTrue(wait_for(lambda: rec.sender.idle() and srv.runs))
        self.assertTrue(wait_for(lambda: (replays.read(replays.path_of(rec.saved[0])).get('live') or {}).get('rid')))
        doc = replays.read(replays.path_of(rec.saved[0]))
        rid = doc['live']['rid']
        chk = replays.check(doc)
        self.assertTrue(chk['signed'] and chk['chain'], chk)            # (signed again: the run id is in what is signed)
        self.assertEqual(srv.runs[rid]['commits'][-1][2], 30000)        # (its finish told)
        self.assertTrue(self.chain_ok(srv, rid, doc))

    def test_an_answer_lost_after_the_server_took_the_commit(self):
        srv = FakeServer()
        srv.lose_answer = {2}
        rec = self.rec(srv)
        self.drive_counted(rec, 50000)
        rec.outcome('finished', {'clockMs': 50000, 'resets': 0, 'totalMs': 50000})
        rec.feed(None, 300.0)
        self.assertTrue(wait_for(lambda: rec.sender.idle()))
        rid = next(iter(srv.runs))
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual(len(srv.runs[rid]['commits']), len(doc['live']['commits']))   # (2 once, the rest after it)
        self.assertTrue(self.chain_ok(srv, rid, doc))

    def test_the_finish_s_exact_clock_and_the_car_as_it_crossed_the_line(self):
        rec = replays.Recorder({}, damage=lambda: {'Engine': 40.46, 'Radiator': 100.0}, penalty=lambda: (5000, False))
        for c in range(50, 12001, 50):
            rec.feed(frame(c), c / 1000.0)
        for k in range(10):                                             # (the clock stopped at 12 040: the finish)
            rec.feed(frame(12040), 12.1 + k * 0.1)
        rec.outcome('finished', {'clockMs': 12040, 'resets': 0, 'totalMs': 12040})
        rec.feed(None, 100.0)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual(doc['rows'][-1][0], 12040)
        self.assertEqual(doc['head']['damage'], {'Engine': 405, 'Radiator': 1000})
        self.assertEqual(doc['head']['damageScale'], 10)
        self.assertEqual(doc['head']['penaltyMs'], 5000)
        self.assertTrue(replays.check(doc)['signed'])

    def test_the_game_frozen_its_clock_kept_where_it_stopped(self):
        rec = replays.Recorder({})
        for c in range(50, 8001, 50):
            rec.feed(frame(c), c / 1000.0)
        for k in range(20):                                             # (frozen at 8 030: the same frame again and again)
            rec.feed(frame(8030), 8.1 + k * 0.05)
        rec.outcome('dnf', {'clockMs': 8030, 'resets': 0, 'reason': 'lost the game (closed or frozen)'})
        rec.feed(None, 100.0)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertEqual(doc['rows'][-1][0], 8030)
        self.assertEqual(doc['head']['reason'], 'lost the game (closed or frozen)')

    def test_after_a_restart_the_commits_never_sent_go_from_the_file(self):
        srv = FakeServer()
        rec = self.rec(srv)
        self.drive_counted(rec, 40000, during=lambda c: setattr(srv, 'down', c >= 15000))
        rec.outcome('finished', {'clockMs': 40000, 'resets': 0, 'totalMs': 40000})
        rec.feed(None, 300.0)
        rid = next(iter(srv.runs))
        have = len(srv.runs[rid]['commits'])
        # the app closed now, its sender with it: a new one at the next start, the connection back
        rec.sender.q.clear()
        srv.down = False
        self.assertEqual(replays.catch_up(srv), 1)
        doc = replays.read(replays.path_of(rec.saved[0]))
        self.assertGreater(len(srv.runs[rid]['commits']), have)
        self.assertEqual(len(srv.runs[rid]['commits']), len(doc['live']['commits']))
        self.assertEqual(srv.runs[rid]['commits'][-1][2], 40000)
        self.assertTrue(self.chain_ok(srv, rid, doc))
        self.assertEqual(replays.catch_up(srv), 0)                      # (synced: never again)

    def test_a_counted_run_never_begun_is_begun_from_its_file(self):
        srv = FakeServer()
        srv.down = True
        rec = self.rec(srv)
        self.drive_counted(rec, 20000)
        rec.outcome('finished', {'clockMs': 20000, 'resets': 0, 'totalMs': 20000})
        rec.feed(None, 300.0)
        rec.sender.q.clear()                                            # (the app closed before the connection came back)
        srv.down = False
        self.assertEqual(replays.catch_up(srv), 1)
        doc = replays.read(replays.path_of(rec.saved[0]))
        rid = doc['live']['rid']
        self.assertEqual(srv.runs[rid]['begin']['clockMs'], 20000)     # (followed only from its end: the admin decides)
        self.assertTrue(replays.check(doc)['chain'] and replays.check(doc)['signed'])
        self.assertEqual(srv.runs[rid]['commits'][-1][2], 20000)

    def test_a_result_still_queued_here_is_never_stood_in_for(self):
        from acr_daily import replayui, leagues
        ui = replayui.ReplayUI()
        ui.api = N(_pending=lambda: [{'challengeId': '2026-11-26/1'}])
        self.assertTrue(ui._result_on_its_way('2026-11-26/1'))
        self.assertFalse(ui._result_on_its_way('2026-11-26/2'))
        with mock.patch.object(leagues, 'pending', lambda: [{'kind': 'stage', 'eventId': 7, 'no': 1}]):
            self.assertTrue(ui._result_on_its_way('event:7:1'))
            self.assertFalse(ui._result_on_its_way('event:7:2'))
