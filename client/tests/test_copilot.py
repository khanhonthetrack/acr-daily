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
        v = voice.Voice(sent.append, lambda: False, mode='ptt', mic=FakeMic([tone()] * 5), speaker=spk, radio=False)
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


class Intercom(unittest.TestCase):
    """The partner's voice through the rally intercom (voice.Intercom, 25 Nov 2026): the headsets' band, pressed hard,
    a click as the channel opens, a squelch as it closes."""

    def band(self, hz):
        fx = voice.Intercom(seed=1)
        fx.HISS = 0.0
        out = b''.join(fx.process(tone(hz=hz, amp=6000, start=k * voice.FRAME)) for k in range(25))
        s = struct.unpack('<%dh' % (len(out) // 2), out)[voice.FRAME * 10:]      # (after the click, the filters settled)
        return max(abs(x) for x in s)

    def test_the_headsets_band(self):
        mid, low, high = self.band(1000), self.band(80), self.band(6500)
        self.assertGreater(mid, 4 * low, 'the rumble under 300 Hz gone')
        self.assertGreater(mid, 4 * high, 'the hiss over 3.4 kHz gone')

    def test_pressed_a_click_then_a_squelch_never_clipped(self):
        fx = voice.Intercom(seed=2)
        quiet = [fx.process(tone(amp=800, start=k * voice.FRAME)) for k in range(30)]
        peak = max(voice.peak(f) for f in quiet[10:])
        self.assertGreater(peak, 2400, 'a quiet voice brought up')
        loud = voice.Intercom(seed=2)
        self.assertLess(max(voice.peak(loud.process(tone(amp=32000, start=k * voice.FRAME))) for k in range(30)), 32767)
        first = struct.unpack('<%dh' % voice.FRAME, voice.Intercom(seed=3).process(b'\0' * voice.FRAME_BYTES))
        self.assertGreater(max(abs(x) for x in first[:96]), 3000, 'the click as the channel opens')
        self.assertLess(max(abs(x) for x in first[200:]), 1000, '... then only the hiss')
        tail = fx.tail()
        self.assertEqual(len(tail), voice.Intercom.TAIL_FRAMES)
        self.assertTrue(all(len(f) == voice.FRAME_BYTES for f in tail))
        self.assertGreater(voice.peak(tail[0]), voice.peak(tail[-1]), 'the squelch fades')
        self.assertEqual(fx.tail(), [], 'closed once')

    def test_heard_through_it_with_its_squelch_after_or_plain(self):
        for radio, n in ((True, 6 + voice.Intercom.TAIL_FRAMES), (False, 6)):
            spk = FakeSpeaker()
            v = voice.Voice(lambda p: None, mode='off', mic=FakeMic([]), speaker=spk, radio=radio)
            try:
                for k in range(6):
                    v.heard(struct.pack('<H', k + 1) + voice.encode(tone(start=k * voice.FRAME)))
                self.assertTrue(wait(lambda: len(spk.played) >= n), (radio, len(spk.played)))
                time.sleep(0.3)
                self.assertEqual(len(spk.played), n, radio)
            finally:
                v.close()
        c = copilot.settings_of({})
        self.assertIs(c['radio'], True)                      # (on unless turned off)
        self.assertIs(copilot.settings_of({'copilot': {'radio': False}})['radio'], False)


class DirectLink(unittest.TestCase):
    def test_two_apps_find_each_other_and_pass_samples_and_voice(self):
        got = {'a': [], 'b': [], 'av': [], 'bv': []}
        pub = {}
        a = copilotlink.Link(lambda d: pub.__setitem__('a', d), got['a'].append, lambda p, w: got['av'].append((p, w)),
                             stun=(), bind=('127.0.0.1', 0))
        b = copilotlink.Link(lambda d: pub.__setitem__('b', d), got['b'].append, lambda p, w: got['bv'].append((p, w)),
                             stun=(), bind=('127.0.0.1', 0))
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
            status = []
            a.on_status = status.append
            a.send_samples({'t': 's', 'sid': 'sid-a', 's': [[1000, 1, 2, 3, 0, 0, 0]]})
            b.send_voice(b'\x01\x00abc', 2)
            b.send_status('0')
            self.assertTrue(wait(lambda: got['b'] and got['av'] and status))
            self.assertEqual(status, ['0'])
            self.assertEqual(got['b'][0]['s'], [[1000, 1, 2, 3, 0, 0, 0]])
            self.assertEqual(got['av'][0], (b'\x01\x00abc', 2), 'the packet and the seat of whoever spoke')
        finally:
            a.close()
            b.close()

    def test_another_key_is_not_theirs(self):
        got = []
        a = copilotlink.Link(lambda d: None, got.append, lambda p, w: got.append(p), stun=(), bind=('127.0.0.1', 0))
        try:
            a.peer({'key': '00' * 8, 'loc': []})
            a._take(copilotlink.MAGIC + b'V' + b'\x11' * 8 + b'\x00xx', ('127.0.0.1', 1), time.monotonic())
            self.assertEqual(got, [])
            a._take(copilotlink.MAGIC + b'V' + b'\x00' * 8 + b'\x00xx', ('127.0.0.1', 1), time.monotonic())
            self.assertEqual(got, [b'xx'])
        finally:
            a.close()

    def test_no_way_through_the_voice_goes_by_the_relay(self):
        relay = mock.Mock(state='live')
        heard = []
        a = copilotlink.Link(lambda d: None, lambda m: None, lambda p, w: heard.append((p, w)), relay=lambda: relay, stun=())
        try:
            a.peer({'key': 'ab' * 8, 'loc': []}, 'sid-b')
            a.send_voice(b'\x05\x00zz', 1)
            sent = relay.send_crew.call_args[0][0]
            self.assertTrue(sent.startswith('v'))
            a.crew('sid-b', sent)                     # (the other's, back through the relay)
            self.assertEqual(heard, [(b'\x05\x00zz', 1)])
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
    a.casual = None
    a.drive_target, a.tt_active = 'tt', copilot.CP_SLOT     # (as _tt_drive_go leaves them)
    a.crew_owner = lambda: getattr(a, 'copilot', None)
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

    def test_the_voice_is_on_in_the_lobby_once_the_partner_is_in(self):
        """The user, 27 Nov 2026: no microphone in the CODRIVER daily lobby (CASUAL had one)."""
        a = app_stub()
        cp = copilot.Copilot(a)
        made = []

        class FakeCrew:
            def __init__(self, *args, **kw):
                self.peers, self.closed = args[4], False
                made.append(self)

            def sync(self, peers):
                self.peers = peers

            def signals(self, s):
                pass

            def close(self):
                self.closed = True
        with mock.patch('acr_daily.crew.Crew', FakeCrew):
            cp._take_lobby(lobby(guest=None))
            self.assertIsNone(cp.crew, 'alone: nobody to talk to')
            cp._take_lobby(lobby())
            self.assertIsNotNone(cp.crew, 'the partner in: the voice on in the lobby')
            self.assertEqual(made[0].peers, [('2', 1)])
            cp._take_lobby(lobby())
            self.assertEqual(len(made), 1, 'once a lobby')
            cp._take_lobby(lobby(guest=None))
            self.assertTrue(made[0].closed and cp.crew is None, 'the partner left: closed')

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
        # the co-driver's game calling the notes (their app says so over the link): as bad
        a._pulse.return_value.codriver_off.return_value = True
        cp._codriver_on_at = None
        cp._status_in('0')
        self.assertEqual(cp.watch_run(t, j, []), [])
        cp._partner_on_at -= copilot.CODRIVER_ON_DNF_S + 0.1
        self.assertEqual(cp.watch_run(t, j, []), ['dnf'])
        self.assertIn("co-driver's game", j.disqualify.call_args[0][0])
        cp._status_in('1')
        self.assertEqual(cp.watch_run(t, j, []), [])


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
                  'lobbies': [{'id': 9, 'state': 'open', 'host': {'name': 'H', 'role': 'driver'}, 'wants': 'codriver'},
                              {'id': 10, 'state': 'open', 'private': True, 'host': {'name': 'P', 'role': 'codriver'},
                               'wants': 'driver'},
                              {'id': 11, 'state': 'open', 'host': {'name': 'F', 'role': 'driver'},
                               'guest': {'name': 'G', 'role': 'codriver'}},
                              {'id': 12, 'state': 'started', 'host': {'name': 'S', 'role': 'driver'},
                               'guest': {'name': 'T', 'role': 'codriver'}}]}
        cp.ranking = {'drivers': [{'rank': 1, 'steamId': '1', 'name': 'Me', 'points': 43, 'days': 2, 'wins': 1}],
                      'codrivers': []}
        cp.board = {'entries': [{'rank': 1, 'totalMs': 200000, 'gapMs': 0, 'driver': {'name': 'A'}, 'codriver': {'name': 'B'}},
                                {'rank': None, 'status': 'dnf', 'totalMs': None, 'driver': {'name': 'C'}, 'codriver': {'name': 'D'}}]}
        page = ig_copilot.page(ig)
        self.assertEqual(check(page), [])
        words = json.dumps(page)
        self.assertIn('"?"', words, 'the stage hidden')
        self.assertIn('copilot.join:9', words)
        self.assertIn('copilot.join:10', words, 'a private one: joined with its code')
        self.assertNotIn('copilot.join:11', words, 'full')
        self.assertIn('ON THE STAGE', words)
        cp.join = mock.Mock()
        ig_copilot.click(ig, 'join', '9')
        cp.join.assert_called_with(lobby_id=9)
        ig.dialog = None
        ig_copilot.click(ig, 'join', '10')                  # (asked for its code in the game first)
        self.assertEqual(ig.dialog['field'], '')
        ig._dialog_words = ' abc 234 '
        ig.dialog['go'][1]()
        cp.join.assert_called_with(lobby_id=10, code='ABC234')
        table = ig_copilot._standings(ig, cp)               # (one table: place, driver, co-driver, time)
        self.assertEqual(check(table), [])
        words = json.dumps(table)
        for w in ('"#"', 'DRIVER', 'CO-DRIVER', 'TIME', '"A"', '"B"', '3:20.000', '"DNF"', '"C"', '"D"'):
            self.assertIn(w, words)
        self.assertNotIn('PTS', words)
        cp.lobby = lobby(code='ABC234')
        self.assertIn('ABC234', json.dumps(ig_copilot.page(ig)))
        cp.lobby = lobby('started', ch=CH)
        page = ig_copilot.page(ig)
        self.assertIn('copilot.go', json.dumps(page))
        self.assertIn('DNF for the crew', json.dumps(page))
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
        a.watch.followed.return_value = None             # (the driver's car not on the relay: the notes alone)
        ig = self.ig(cp)
        ig.app = a
        a.copilot = cp
        ov = ig_copilot.overlay(ig)
        self.assertEqual(check(ov), [])
        words = json.dumps(ov)
        self.assertIn('13 / 30', words)
        self.assertIn('RIGHT 1', words)
        self.assertEqual(words.count('"n"'), 0)
        a._pulse.return_value.codriver_off.return_value = False      # (the game's own co-driver on: said in red)
        self.assertIn("THE GAME'S CO-DRIVER IS ON", json.dumps(ig_copilot.overlay(ig)))
        a._pulse.return_value.codriver_off.return_value = True
        cp.lobby = lobby('started', role='driver', ch=CH)
        a.tt = {}
        self.assertIsNone(ig_copilot.overlay(ig), 'not on the crew\'s stage (another one driven): nothing')
        a.tt = {copilot.CP_SLOT: {'ch': CH, 'judge': None}}
        ov = ig_copilot.overlay(ig)
        self.assertEqual(check(ov), [])
        self.assertIn('DNF for the crew', json.dumps(ov), 'the rules before the start')
        a.tt = {copilot.CP_SLOT: {'ch': CH, 'judge': mock.Mock(state='running')}}
        self.assertIsNone(ig_copilot.overlay(ig), 'driving, all fine, no voice yet: nothing in the way')
        cp.partner_off = False
        self.assertIn("co-driver's game", json.dumps(ig_copilot.overlay(ig)))

    def test_the_voice_s_settings_in_settings(self):
        a = app_stub()
        cp = copilot.Copilot(a)
        ig = self.ig(cp)
        ig.app = a
        a.copilot = cp
        panel = ig_copilot.settings_panel(ig)
        self.assertEqual(check(panel), [])
        self.assertIn('copilot.talk:open', json.dumps(panel))
        with mock.patch('acr_daily.settings.save'):
            ig_copilot.click(ig, 'talk', 'open')
            ig_copilot.click(ig, 'gain', '+')
            ig_copilot.click(ig, 'key', 'next')
        c = copilot.settings_of(a.s)
        self.assertEqual((c['talk'], c['gain'], c['key']), ('open', 1.25, 'B'))
        self.assertNotIn('copilot.key', json.dumps(ig_copilot.settings_panel(ig)), 'open mic: no key to set')


class Seats(unittest.TestCase):
    """Up to four in a crew (CASUAL): each speaker a seat of their own, mixed; the hub passes voice on; a mic by name."""

    def test_two_speakers_are_mixed_and_each_one_shows_as_speaking(self):
        spk = FakeSpeaker()
        v = voice.Voice(lambda p: None, mode='off', mic=FakeMic([]), speaker=spk, radio=False, seat=2)
        try:
            for k in range(6):
                v.heard(struct.pack('<H', k + 1) + voice.encode(tone(start=k * voice.FRAME)), 0)
                v.heard(struct.pack('<H', k + 1) + voice.encode(tone(hz=700, start=k * voice.FRAME)), 1)
            v.heard(struct.pack('<H', 9) + voice.encode(tone()), 2)          # (my own seat: dropped)
            self.assertTrue(wait(lambda: len(spk.played) >= 6))
            self.assertEqual(v.speaking(), {0, 1})
            self.assertEqual(len(spk.played[0]), voice.FRAME_BYTES)
            time.sleep(0.5)
            self.assertEqual(v.speaking(), set(), 'nobody now')
            self.assertEqual(len(spk.played), 6, 'one mixed frame for both, none for the dropped one')
        finally:
            v.close()

    def test_my_voice_is_scaled_and_the_level_is_kept(self):
        sent = []
        v = voice.Voice(sent.append, lambda: True, mode='ptt', mic=FakeMic([tone(amp=4000)] * 3), speaker=FakeSpeaker(),
                        mic_gain=2.0)
        try:
            self.assertTrue(wait(lambda: len(sent) == 3))
            back = struct.unpack('<%dh' % voice.FRAME, voice.decode(sent[1][2:]))
            self.assertGreater(max(back), 6500, 'twice as loud as the 4000 it heard')
            self.assertGreater(v.level, 0.2)
        finally:
            v.close()
        self.assertEqual(voice.scale(b'\x00\x40' * 4, 8.0), b'\xff\x7f' * 4, 'clipped, never wrapped')

    def test_the_microphone_is_found_by_name_else_the_default(self):
        self.assertEqual(voice.mic_index('', ['A', 'B']), voice.WAVE_MAPPER)
        self.assertEqual(voice.mic_index('B', ['A', 'B']), 1)
        self.assertEqual(voice.mic_index('gone', ['A', 'B']), voice.WAVE_MAPPER, 'unplugged since: the default one')

    def test_the_hub_passes_a_co_driver_s_voice_to_the_others_tagged_with_the_seat(self):
        from acr_daily import crew
        sent, heard = [], []

        class L:
            direct = True

            def __init__(self):
                self.sid = None

            def send_voice(self, packet, who=0, relay=True):
                sent.append((self.sid, packet, who))

            def close(self):
                pass

        class V:
            def __init__(self, send, seat=None, **kw):
                self.heard = lambda p, w: heard.append((p, w))
                self.close = lambda: None
        c = crew.Crew(mock.Mock(), 0, True, lambda *a: None, [('s1', 1), ('s2', 2), ('s3', 3)], {},
                      link_factory=lambda pub, smp, vin, relay, on_status=None: L(), voice_factory=V)
        for sid, l in c.links.items():
            l.sid = sid
        c._voice_in('s2', b'pkt', 0)                      # (seat 2 spoke: whatever the packet says)
        self.assertEqual(heard, [(b'pkt', 2)])
        self.assertEqual(sorted((s, w) for s, _p, w in sent), [('s1', 2), ('s3', 2)], 'not back to the speaker')
        sent.clear()
        c.send_voice(b'mine')                             # (mine: to all three, as seat 0)
        self.assertEqual(sorted((s, w) for s, _p, w in sent), [('s1', 0), ('s2', 0), ('s3', 0)])


class Scoreboard(unittest.TestCase):
    def test_a_split_ghost_gives_the_live_gap_between_the_leader_s_splits(self):
        from acr_daily.judge import Judge
        j = Judge(dict(CH))
        j.set_ghost_splits([10000, 20000, 30000], 40000)
        n = len(j.route.points)
        self.assertEqual(j.ghost.total_at(0), 0)
        self.assertAlmostEqual(j.ghost.total_at(n // 2) / 20000.0, 1.0, delta=0.06)
        self.assertEqual(j.ghost.total_at(n - 1), 40000)
        j.set_ghost_splits(None, None)
        self.assertIsNone(j.ghost)

class CrewLiveOnTheWebsite(unittest.TestCase):
    """The daily crew's driver on the website's CODRIVER DAILY map (26 Nov 2026); CASUAL's never."""

    def test_the_daily_crew_s_driver_is_sent_casual_s_is_not(self):
        from acr_daily import ttui
        a = app_stub()
        sent = []
        a.api.copilot_live = sent.append
        a.api.configured = True
        f = mock.Mock(x=12.34, z=5.0)
        for cid, want in (('cp:2026-11-26/4', 1), ('cx:9', 0)):
            sent.clear()
            j = mock.Mock(ch={'id': cid}, progress=0.25, total_ms=61000, resets=1)
            a.tt = {copilot.CP_SLOT: {}}
            with mock.patch('acr_daily.ttui.threading.Thread', lambda target, daemon: mock.Mock(start=target)):
                ttui.TimeTrialUI._tt_send_live(a, copilot.CP_SLOT, j, f, 'live')
            self.assertEqual(len(sent), want, cid)
        a.tt = {copilot.CP_SLOT: {}}
        with mock.patch('acr_daily.ttui.threading.Thread', lambda target, daemon: mock.Mock(start=target)):
            ttui.TimeTrialUI._tt_send_live(a, copilot.CP_SLOT, mock.Mock(ch={'id': 'cp:2026-11-26/4'}, progress=0.5,
                                                                         total_ms=1, resets=0), f, 'finished')
        self.assertEqual(sent[-1], {'challengeId': 'cp:2026-11-26/4', 'x': 12.3, 'z': 5.0, 'progress': 0.5, 'totalMs': 1,
                                    'resets': 0, 'state': 'finished'})


if __name__ == '__main__':
    unittest.main()
