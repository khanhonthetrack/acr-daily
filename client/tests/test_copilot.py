"""COPILOT (copilot.py, copilotlink.py, voice.py, ig_copilot.py): the voice's packing, the direct link between two apps
on this PC, the relay when there is none, the lobby's start for each role, the co-driver's notes and keys, the pages'
trees, and the bits of the rest of the app it leans on (the relay's room, the run's address, the mod's C group)."""
import json
import math
import struct
import time
import unittest
from unittest import mock

from acr_daily import api, copilot, copilotlink, ig_copilot, ingamehud, livelink, ttui, voice
from acr_daily.ingamekit import check


def tone(n=voice.FRAME, hz=440.0, amp=8000, start=0):
    return struct.pack('<%dh' % n, *[int(amp * math.sin(2 * math.pi * hz * (start + i) / voice.RATE)) for i in range(n)])


class Packing(unittest.TestCase):
    def test_adpcm_four_to_one_and_close_to_the_sound(self):
        state = [0, 0]
        first = voice.encode(tone(), state)
        self.assertEqual(len(first), 3 + voice.FRAME // 2, '160 bytes for 20 ms, and its start')
        pcm = tone(start=voice.FRAME)                 # (the next 20 ms: the step fitted to the voice by then)
        pkt = voice.encode(pcm, state)
        back = struct.unpack('<%dh' % voice.FRAME, voice.decode(pkt))   # (decoded on its own: a packet says its start)
        orig = struct.unpack('<%dh' % voice.FRAME, pcm)
        err = max(abs(a - b) for a, b in zip(orig, back))
        self.assertLess(err, 1600, 'within 5 % of full scale')
        self.assertEqual(voice.decode(b''), b'\0' * voice.FRAME_BYTES)
        self.assertGreater(voice.peak(pcm), 7000)
        loud = struct.unpack('<%dh' % voice.FRAME, voice.decode(pkt, gain=2.0))
        self.assertTrue(all(-32768 <= v <= 32767 for v in loud))


class FakeMic:
    ok = True

    def __init__(self, frames):
        self.frames = list(frames)

    def read(self):
        return self.frames.pop(0) if self.frames else None

    def close(self):
        pass


class FakeSpeaker:
    ok = True

    def __init__(self):
        self.played = []

    def queued(self):
        return 0

    def play(self, pcm):
        self.played.append(pcm)
        return True

    def close(self):
        pass


def wait(cond, s=3.0):
    end = time.monotonic() + s
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Talking(unittest.TestCase):
    def test_push_to_talk_sends_only_while_held_and_heard_is_played(self):
        sent = []
        spk = FakeSpeaker()
        v = voice.Voice(sent.append, lambda: False, mode='ptt', mic=FakeMic([tone()] * 5), speaker=spk)
        try:
            time.sleep(0.15)
            self.assertEqual(sent, [], 'not held: nothing sent')
            v2 =voice.Voice(sent.append, lambda: True, mode='ptt', mic=FakeMic([tone()] * 3), speaker=FakeSpeaker())
            self.assertTrue(wait(lambda: len(sent) == 3))
            self.assertEqual([struct.unpack_from('<H', p)[0] for p in sent], [1, 2, 3])
            v2.close()
            for k in range(6):                       # (heard: 120 ms, more than the jitter's 60: played)
                v.heard(struct.pack('<H', k + 1) + voice.encode(tone(start=k * voice.FRAME)))
            self.assertTrue(wait(lambda: len(spk.played) == 6))
            self.assertTrue(v.hearing)
            v.heard(struct.pack('<H', 2) + voice.encode(tone()))   # (late: one already played is older)
            time.sleep(0.1)
            self.assertEqual(len(spk.played), 6)
        finally:
            v.close()

    def test_open_mic_sends_speech_not_silence(self):
        sent = []
        quiet = b'\0' * voice.FRAME_BYTES
        v = voice.Voice(sent.append, mode='open', mic=FakeMic([quiet, quiet, tone(), quiet]), speaker=FakeSpeaker())
        try:
            self.assertTrue(wait(lambda: len(sent) >= 2))
            time.sleep(0.1)
            self.assertEqual(len(sent), 2, 'the speech and the hang after it')
        finally:
            v.close()


class DirectLink(unittest.TestCase):
    def test_two_apps_find_each_other_and_pass_samples_and_voice(self):
        got = {'a': [], 'b': [], 'av': [], 'bv': []}
        pub = {}
        a = copilotlink.Link(lambda d: pub.__setitem__('a', d), got['a'].append, got['av'].append, stun=(),
                             bind=('127.0.0.1', 0))
        b = copilotlink.Link(lambda d: pub.__setitem__('b', d), got['b'].append, got['bv'].append, stun=(),
                             bind=('127.0.0.1', 0))
        try:
            self.assertTrue(wait(lambda: 'a' in pub and 'b' in pub))
            # (only this PC: the addresses on its own network, as the lobby passes them on)
            pa = dict(pub['a'], loc=['127.0.0.1:%d' % a.port])
            pb = dict(pub['b'], loc=['127.0.0.1:%d' % b.port])
            a.peer(json.dumps(pb), 'sid-b')           # (as the lobby gives it: a JSON string, or a dict)
            b.peer(pa, 'sid-a')
            self.assertTrue(wait(lambda: a.direct and b.direct), (a.state, b.state))
            self.assertTrue(wait(lambda: a.rtt_ms is not None))
            self.assertEqual(a.mode(), 'direct')
            a.send_samples({'t': 's', 'sid': 'sid-a', 's': [[1000, 1, 2, 3, 0, 0, 0]]})
            b.send_voice(b'\x01\x00abc')
            self.assertTrue(wait(lambda: got['b'] and got['av']))
            self.assertEqual(got['b'][0]['s'], [[1000, 1, 2, 3, 0, 0, 0]])
            self.assertEqual(got['av'][0], b'\x01\x00abc')
        finally:
            a.close()
            b.close()

    def test_another_key_is_not_theirs(self):
        got = []
        a = copilotlink.Link(lambda d: None, got.append, got.append, stun=(), bind=('127.0.0.1', 0))
        try:
            a.peer({'key': '00' * 8, 'loc': []})
            a._take(copilotlink.MAGIC + b'V' + b'\x11' * 8 + b'xx', ('127.0.0.1', 1), time.monotonic())
            self.assertEqual(got, [])
            a._take(copilotlink.MAGIC + b'V' + b'\x00' * 8 + b'xx', ('127.0.0.1', 1), time.monotonic())
            self.assertEqual(got, [b'xx'])
        finally:
            a.close()

    def test_no_way_through_the_voice_goes_by_the_relay(self):
        relay = mock.Mock(state='live')
        heard = []
        a = copilotlink.Link(lambda d: None, lambda m: None, heard.append, relay=lambda: relay, stun=())
        try:
            a.peer({'key': 'ab' * 8, 'loc': []}, 'sid-b')
            a.send_voice(b'\x05\x00zz')
            sent = relay.send_crew.call_args[0][0]
            self.assertTrue(sent.startswith('v'))
            a.crew('sid-b', sent)                     # (the other's, back through the relay)
            self.assertEqual(heard, [b'\x05\x00zz'])
            a.crew('someone-else', sent)
            self.assertEqual(len(heard), 1, 'only the partner\'s')
        finally:
            a.close()

    def test_stun_answer(self):
        tid = b'\x01' * 12
        ip = struct.unpack('>I', bytes([203, 0, 113, 7]))[0] ^ copilotlink.STUN_COOKIE
        attr = struct.pack('>HHBBHI', 0x0020, 8, 0, 1, 54321 ^ (copilotlink.STUN_COOKIE >> 16), ip)
        msg = struct.pack('>HHI', 0x0101, len(attr), copilotlink.STUN_COOKIE) + tid + attr
        self.assertEqual(copilotlink.stun_address(msg, tid), '203.0.113.7:54321')
        self.assertIsNone(copilotlink.stun_address(msg, b'\x02' * 12), 'not our question')


class RelayLink(unittest.TestCase):
    def test_samples_straight_from_the_driver_one_car_not_two(self):
        link = livelink.LiveLink.__new__(livelink.LiveLink)
        link.watch, link.drivers, link._lock = True, {}, __import__('threading').Lock()
        link.on_crew = None
        msg = {'t': 's', 'id': 7, 'sid': 'drv', 'name': 'D', 'car': 'C', 'run': 5, 's': [[100, 1, 2, 3, 0, 0, 0]]}
        link._got(msg)
        self.assertIn(7, link.drivers)
        link.take_direct(dict(msg, s=[[150, 1, 2, 3, 0, 0, 0]]))
        self.assertEqual(list(link.drivers), [7], 'the relay\'s id kept')
        link._got(dict(msg, s=[[120, 9, 9, 9, 0, 0, 0]]))          # (the relay's copy: left aside now)
        self.assertEqual(link.drivers[7].trace.ms[-1], 150)
        crew = []
        link.on_crew = lambda sid, b: crew.append((sid, b))
        link._got({'t': 'x', 'sid': 'drv', 'b': 'v123'})
        self.assertEqual(crew, [('drv', 'v123')])


class Bits(unittest.TestCase):
    def test_runs_rooms_slots_and_the_mods_word(self):
        self.assertEqual(api.run_path({'challengeId': 'cp:2026-11-25/3'}), '/api/copilot/runs')
        self.assertEqual(api.run_path({'challengeId': 'tt:2026-11-23/1'}), '/api/tt/runs')
        self.assertEqual(ttui.parse_id('cp:2026-11-25/3'), copilot.CP_SLOT)
        self.assertEqual(set(ttui.listed({1: {}, copilot.CP_SLOT: {}, 3: {}})), {1, 3})
        line = 'CAM 5 0 0 0 0 0 0 90 5 M weekend 5 C 1 5'
        self.assertEqual(ingamehud.ModPulse._digits(line, 'C', ('off',)), {'off': 1})
        s = {}
        c = copilot.settings_of(s)
        self.assertEqual((c['talk'], c['key'], c['button'], c['gain']), ('ptt', 'V', None, 1.0))
        s['copilot'].update(talk='loud', gain='9')
        self.assertEqual((copilot.settings_of(s)['talk'], copilot.settings_of(s)['gain']), ('ptt', 3.0))


def app_stub():
    a = mock.Mock()
    a.s = {'steamId': '1', 'name': 'Me', 'token': 't'}
    a.tt = {}
    a.root.after = lambda ms, fn, *args: fn(*args)
    a.ghostcars.live = None
    a.watch.on = False
    return a


NOTES = [{'n': i + 1, 'at': i * 60, 'len': 50, 'text': 'right %d' % (i % 6 + 1)} for i in range(30)]
CH = {'id': 'cp:2026-11-25/4', 'track': 'Monte Carlo La Bollène', 'car': 'Car', 'carId': 'CarId',
      'stageId': 'MonteCarloS1BolleneCut2Forward', 'weatherGame': 'WT_CLEAR',
      'startSeconds': 43200, 'weekend': {'hardcore': True}, 'route': [[i * 10, 0] for i in range(200)], 'penaltyMs': 0,
      'mode': 'weekend', 'splits': [0.25, 0.5, 0.75], 'timing': {}}


def lobby(state='open', role='driver', **kw):
    l = {'id': 4, 'state': state, 'me': 'host', 'myRole': role, 'host': {'steamId': '1', 'name': 'Me', 'role': role,
                                                                         'ready': True},
         'guest': {'steamId': '2', 'name': 'Them', 'role': 'codriver' if role == 'driver' else 'driver', 'ready': False},
         'started': time.time() * 1000}
    l.update(kw)
    return l


class Crew(unittest.TestCase):
    def test_the_start_drives_for_the_driver(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        cp.start_link = lambda: None
        cp._take_lobby(lobby())
        self.assertEqual(cp.room(), 'cp:4')
        self.assertFalse(cp.mod_on())
        cp._take_lobby(lobby('started', ch=CH))
        self.assertTrue(cp.mod_on())
        self.assertIn(copilot.CP_SLOT, a.tt)
        self.assertEqual(a.tt[copilot.CP_SLOT]['ch']['id'], CH['id'])
        a._tt_drive_go.assert_called_once_with(copilot.CP_SLOT)
        cp._take_lobby(lobby('started', ch=CH))
        a._tt_drive_go.assert_called_once()           # (once a lobby)
        cp._take_lobby(lobby('finished'))
        self.assertIsNone(cp.room())
        self.assertNotIn(copilot.CP_SLOT, a.tt, 'gone once over')

    def test_the_codriver_watches_with_the_notes(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        cp.start_link = lambda: None
        with mock.patch('acr_daily.ig_watch._when_ready', lambda ig, go: go()), \
                mock.patch('acr_daily.ig_watch._go', lambda ig, setup, ch, begin: begin()):
            cp._take_lobby(lobby('started', role='codriver', ch=CH, notes=NOTES))
        kind, slot = a.watch.start.call_args[0]
        ev = a.watch.start.call_args[1]['event']
        self.assertEqual((kind, ev['kind'], ev['eventId']), ('event', 'copilot', 4))
        self.assertEqual(a.watch.start.call_args[1]['prefer'], '2', 'the driver followed')
        self.assertEqual(len(cp.notes), 30)
        self.assertTrue(cp.key('down') and cp.key('right'))
        self.assertEqual(cp.cursor, 6)
        cp.key('up')
        self.assertEqual(cp.cursor, 5)
        for _ in range(20):
            cp.key('left')
        self.assertEqual(cp.cursor, 0)
        self.assertFalse(cp.key('select'))

    def test_an_old_start_is_not_set_up_again_by_itself(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        cp.start_link = lambda: None
        cp._take_lobby(lobby('started', ch=CH, started=(time.time() - 3600) * 1000))
        a._tt_drive_go.assert_not_called()

    def test_the_game_s_own_codriver_on_during_the_stage_is_a_dnf(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        j = mock.Mock(state='running', ch=CH)
        j.disqualify.return_value = ['dnf']
        t = {}
        a._pulse.return_value.codriver_off.return_value = True
        self.assertEqual(cp.watch_run(t, j, ['start']), [])
        self.assertTrue(t['codriver_said'])
        a._pulse.return_value.codriver_off.return_value = False
        self.assertEqual(cp.watch_run(t, j, []), [])
        cp._codriver_on_at -= copilot.CODRIVER_ON_DNF_S + 0.1
        self.assertEqual(cp.watch_run(t, j, []), ['dnf'])


class Pages(unittest.TestCase):
    def ig(self, cp):
        ig = mock.Mock()
        ig.app.copilot = cp
        ig.app.s = {'token': 't', 'steamId': '1'}
        mem = {}
        ig.mem = lambda tab: mem.setdefault(tab, {})
        return ig

    def test_every_state_draws(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        cp.refresh = lambda force=False: None
        ig = self.ig(cp)
        self.assertEqual(check(ig_copilot.page(ig)), [], 'loading')
        cp.day = {'on': True, 'revealed': False, 'tries': {'driver': None, 'codriver': None},
                  'lobbies': [{'id': 9, 'host': {'name': 'H', 'role': 'driver'}, 'wants': 'codriver'}]}
        cp.board = {'entries': [{'rank': 1, 'totalMs': 200000, 'gapMs': 0, 'driver': {'name': 'A'}, 'codriver': {'name': 'B'}},
                                {'rank': None, 'status': 'dnf', 'totalMs': None, 'driver': {'name': 'C'}, 'codriver': {'name': 'D'}}]}
        page = ig_copilot.page(ig)
        self.assertEqual(check(page), [])
        words = json.dumps(page)
        self.assertIn('"?"', words, 'the stage hidden')
        self.assertIn('copilot.join:9', words)
        cp.lobby = lobby(code='ABC234')
        self.assertIn('ABC234', json.dumps(ig_copilot.page(ig)))
        cp.lobby = lobby('started', ch=CH)
        self.assertIn('copilot.go', json.dumps(ig_copilot.page(ig)))
        cp.lobby = None
        cp.day.update(revealed=True, stage={'menuName': 'Afon Bidno', 'car': 'Car'}, tries={'driver': 4, 'codriver': 5})
        page = ig_copilot.page(ig)
        self.assertEqual(check(page), [])
        self.assertIn('AFON BIDNO', json.dumps(page))

    def test_the_notes_over_the_stage(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        cp.lobby = lobby('started', role='codriver')
        cp.notes, cp.cursor = NOTES, 12
        a.watch.on = True
        a.watch.copilot.return_value = True
        ig = self.ig(cp)
        ig.app = a
        a.copilot = cp
        ov = ig_copilot.overlay(ig)
        self.assertEqual(check(ov), [])
        words = json.dumps(ov)
        self.assertIn('13 / 30', words)
        self.assertIn('RIGHT 1', words)
        self.assertEqual(words.count('"n"'), 0)
        cp.lobby = lobby('started', role='driver')
        self.assertIsNone(ig_copilot.overlay(ig), 'nothing to say yet: no voice, no link')


if __name__ == '__main__':
    unittest.main()
