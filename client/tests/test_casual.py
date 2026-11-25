"""CASUAL (casual.py, ig_casual.py, crew.py, qrcode_min.py): a lobby of up to four, the pages, the QR code, the icons."""
import io
import json
import os
import struct
import tempfile
import time
import unittest
from unittest import mock

from acr_daily import casual, ig_casual, ig_copilot, qrcode_min, settings
from acr_daily.ingamekit import check

try:
    from tests.test_copilot import CH, NOTES, app_stub
except ImportError:                          # (run by unittest discover -s tests)
    from test_copilot import CH, NOTES, app_stub

CX = dict(CH, id='cx:4', kind='casual')
OPTIONS = {'stages': [{'track': 'Monte Carlo La Bollène', 'stageName': 'La Bollène', 'menuName': 'La Bollène', 'rally': 'Monte Carlo',
                       'lengthM': 12000},
                      {'track': 'Sweden Y', 'stageName': 'Y', 'menuName': 'Yxtjärnshöjden', 'rally': 'Sweden', 'lengthM': 9000}],
           'cars': [{'id': 'c1', 'name': 'Car One', 'cls': 'Rally2'}],
           'weather': [{'code': 'Clear', 'label': 'Clear'}, {'code': 'Storm', 'label': 'Storm'}],
           'times': [{'code': 'morning', 'label': 'Morning (08:00)'}, {'code': 'midday', 'label': 'Midday (12:00)'}]}


def member(sid, name, seat, ready=False):
    return {'steamId': sid, 'name': name, 'avatar': None, 'country': None, 'role': 'driver' if seat == 0 else 'codriver',
            'seat': seat, 'ready': ready}


def lobby(me='1', state='open', n=2, **kw):
    ms = [member('1', 'Me', 0, True), member('2', 'Ann', 1), member('3', 'Bob', 2), member('4', 'Cy', 3)][:n]
    mine = next(m for m in ms if m['steamId'] == me)
    l = {'id': 4, 'private': False, 'state': state, 'created': 0, 'started': time.time() * 1000, 'max': 4, 'langs': ['en', 'pl'],
         'stage': OPTIONS['stages'][0], 'car': {'id': 'c1', 'name': 'Car One', 'cls': 'Rally2'},
         'weather': {'code': 'Clear', 'label': 'Clear'}, 'time': {'code': 'midday', 'label': 'Midday (12:00)'},
         'host': ms[0], 'members': ms, 'count': n, 'free': 4 - n,
         'me': {'steamId': mine['steamId'], 'role': mine['role'], 'seat': mine['seat']}, 'notesUrl': '/n/abcdefghijkl',
         'signals': {}}
    if state == 'started':
        l.update(ch=CX, notes=NOTES)
    l.update(kw)
    return l


class Fake:
    def __init__(self, cs):
        self.app = cs.app
        self._mem = {}
        self.dialog = None
        self.tab = 'copilot'
        self.opened = mock.Mock()

    def mem(self, tab):
        return self._mem.setdefault(tab, {})

    def ask(self, *a, **k):
        self.asked = a
        a[3]()


def made():
    a = app_stub()
    a.api.base = 'https://acrdaily.com'
    cs = casual.Casual(a)
    a.casual = cs
    cs.options, cs.enabled, cs.day = OPTIONS, True, {'on': True}
    cs.refresh = lambda force=False: None
    return a, cs


class Lobby(unittest.TestCase):
    def test_the_driver_links_to_every_co_driver_and_a_co_driver_to_the_driver(self):
        a, cs = made()
        cs.lobby = lobby('1', n=3)
        self.assertEqual(cs.peers(), [('2', 1), ('3', 2)])
        self.assertEqual((cs.role(), cs.my_seat(), cs.is_host(), cs.solo()), ('driver', 0, True, False))
        cs.lobby = lobby('3', n=3)
        self.assertEqual(cs.peers(), [('1', 0)])
        self.assertEqual((cs.role(), cs.my_seat(), cs.is_host()), ('codriver', 2, False))
        self.assertEqual(cs.partner()['name'], 'Me')
        self.assertEqual(cs.room_id(), casual.ROOM_BASE + 4)

    def test_alone_there_is_no_link_and_the_games_own_co_driver_stays(self):
        a, cs = made()
        cs.lobby = lobby('1', 'started', n=1)
        self.assertTrue(cs.solo())
        self.assertFalse(cs.mod_on(), 'solo: the game\'s own co-driver is left on')
        cs.start_link()
        self.assertIsNone(cs.crew)
        self.assertIsNone(cs.start_alert())
        cs.lobby = lobby('1', 'started', n=2)
        self.assertTrue(cs.mod_on())

    def test_the_stage_is_driven_by_the_driver_and_watched_by_the_others_without_rules(self):
        a, cs = made()
        cs.start_link = lambda: None
        a._tt_drive_go = mock.Mock()
        cs._take_lobby(lobby('1', 'started', n=2))
        self.assertEqual(a.tt[casual.CP_SLOT]['ch']['id'], 'cx:4')
        a._tt_drive_go.assert_called_once_with(casual.CP_SLOT)
        self.assertEqual(cs.watch_run({}, mock.Mock(), []), [], 'no DNF rules in casual')

    def test_the_apps_one_lobby_owner(self):
        from acr_daily import ttui
        a, cs = made()
        daily = mock.Mock()
        owner = ttui.TimeTrialUI.crew_owner
        a.copilot = daily
        a.crew_owner = lambda: owner(a)
        self.assertIs(a.crew_owner(), daily)
        cs.lobby = lobby('1')
        self.assertIs(a.crew_owner(), cs)

    def test_the_result_is_not_sent_and_says_not_ranked(self):
        a, cs = made()
        a.tt[casual.CP_SLOT] = {}
        cs.on_result({'status': 'finished', 'totalMs': 225123})
        self.assertIn('3:45.123', cs.final)
        self.assertEqual(a.tt[casual.CP_SLOT]['said'], 'FINISHED · NOT RANKED')
        a.api._req.assert_not_called()

    def test_the_icons_show_who_talks(self):
        a, cs = made()
        cs.lobby = lobby('1', 'started', n=3)
        cs.crew = mock.Mock()
        cs.crew.voice = mock.Mock(speaking=lambda: {2, 'me'})
        names = {n: on for n, _s, on in cs.speakers()}
        self.assertEqual(names, {'Ann': False, 'Bob': True, 'You': True})
        self.assertEqual(cs.speaking(), ['Bob', 'You'])
        ov = ig_copilot._icons(cs)
        words = json.dumps(ov)
        self.assertIn('Bob', words)
        self.assertEqual(check(ov), [])
        cs.crew.voice = None
        self.assertIsNone(ig_copilot._icons(cs), 'no voice: no icons')


class Pages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = mock.patch.object(settings, 'DIR', self.tmp)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_the_browser_the_set_up_and_the_pickers_are_valid_pages(self):
        a, cs = made()
        cs.lobbies = [dict(lobby('1', n=2), id=7, host=member('9', 'Zed', 0)),
                      dict(lobby('1', n=4), id=8, private=True), dict(lobby('1', 'started', n=2), id=9)]
        for l in cs.lobbies:
            l.pop('me', None)
            l.pop('notesUrl', None)
        ig = Fake(cs)
        page = ig_casual.page(ig)
        self.assertEqual(check(page), [])
        words = json.dumps(page, ensure_ascii=False)
        for w in ('casual.create', 'casual.join:7', 'Zed', 'FULL', 'ON THE STAGE', 'PRIVATE', 'La Bollène', 'Car One', '2 / 4'):
            self.assertIn(w, words)
        for field in ('stage', 'car', 'weather', 'time', 'lang'):
            ig.mem('casual')['pick'] = field
            self.assertEqual(check(ig_casual.page(ig)), [], field)
        # picking
        ig_casual.click(ig, 'open', 'weather')
        ig_casual.click(ig, 'pick', 'Storm')
        self.assertEqual(ig_casual.chosen(ig, 'weather'), 'Storm')
        self.assertIsNone(ig.mem('casual')['pick'])
        self.assertEqual(ig_casual.chosen(ig, 'time'), 'midday')

    def test_up_to_three_languages(self):
        a, cs = made()
        ig = Fake(cs)
        ig.mem('casual')['langs'] = []
        ig_casual.click(ig, 'open', 'lang')
        for code in ('en', 'pl', 'de', 'fr'):
            ig_casual.click(ig, 'pick', code)
        self.assertEqual(ig_casual.chosen(ig, 'lang'), ['en', 'pl', 'de'], 'a fourth is not taken')
        ig_casual.click(ig, 'pick', 'pl')
        self.assertEqual(ig_casual.chosen(ig, 'lang'), ['en', 'de'], 'a click again takes one off')

    def test_setting_up_sends_the_pick(self):
        a, cs = made()
        ig = Fake(cs)
        ig.mem('casual')['langs'] = ['pl']
        cs.create = mock.Mock()
        ig.mem('casual')['private'] = True
        ig_casual.click(ig, 'create', None)
        cs.create.assert_called_once_with({'track': 'Monte Carlo La Bollène', 'car': 'c1', 'weather': 'Clear',
                                           'time': 'midday', 'langs': ['pl'], 'private': True})

    def test_my_lobby_with_its_qr_code_and_start(self):
        a, cs = made()
        cs.lobby = lobby('1', code='ABC234', private=True)
        ig = Fake(cs)
        page = ig_casual.page(ig)
        self.assertEqual(check(page), [])
        words = json.dumps(page)
        for w in ('casual.start', 'casual.leave', 'ABC234', 'Ann', 'qr-', 'acrdaily.com/n/abcdefghijkl'):
            self.assertIn(w, words)
        self.assertEqual(cs.notes_url(), 'https://acrdaily.com/n/abcdefghijkl')
        # a co-driver: READY, not START; the driver's started stage: TO THE CAR
        cs.lobby = lobby('2')
        words = json.dumps(ig_casual.page(ig))
        self.assertIn('casual.ready', words)
        self.assertNotIn('casual.start', words)
        cs.lobby = lobby('2', 'started')
        self.assertIn('TO THE CAR', json.dumps(ig_casual.page(ig)))
        cs.lobby = lobby('1', 'started', n=1)
        self.assertIn('DRIVE', json.dumps(ig_casual.page(ig)))

    def test_the_codriver_page_has_two_tabs(self):
        a, cs = made()
        a.copilot = mock.Mock(lobby=None, day={'on': True}, board=None, msg='', final='')
        ig = Fake(cs)
        page = ig_copilot.page(ig)
        words = json.dumps(page)
        self.assertIn('copilot.mode:daily', words)
        self.assertIn('copilot.mode:casual', words)
        ig_copilot.click(ig, 'mode', 'casual')
        self.assertIn('casual.create', json.dumps(ig_copilot.page(ig)))

    def test_the_flags_of_the_languages(self):
        self.assertEqual(casual.LANG_FLAG['en'], 'GB')
        self.assertEqual(casual.flag_emoji('pl'), '🇵🇱')
        self.assertEqual(casual.flag_emoji('xx'), '')
        self.assertEqual(len(casual.LANGS), len(set(casual.LANGS)))
        self.assertTrue(all(c in casual.LANG_FLAG for c in casual.LANGS))
        self.assertIsNone(ig_casual.flags([]))


class Qr(unittest.TestCase):
    def test_the_matrix_has_its_finders_and_the_right_size(self):
        m = qrcode_min.matrix('https://acrdaily.com/n/abcdefghijkl')
        self.assertEqual(len(m), 29, 'version 3: 35 bytes')
        for r, c in ((0, 0), (0, 22), (22, 0)):
            self.assertEqual([m[r][c + i] for i in range(7)], [1] * 7, 'a finder\'s top row')
        self.assertEqual(len(qrcode_min.matrix('A')), 21)
        with self.assertRaises(ValueError):
            qrcode_min.matrix('x' * 200)

    def test_the_png_is_a_png(self):
        data = qrcode_min.png('hi', 4, 2)
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        w, h = struct.unpack('>II', data[16:24])
        self.assertEqual((w, h), ((21 + 4) * 4, (21 + 4) * 4))


def _qr_read(m, v):
    """A reader written from the QR specification (not from the maker): format info (both copies), unmask, the zig-zag, the
    blocks' error correction checked, the byte-mode text returned."""
    n = len(m)
    fmt = 0
    for i in range(6):
        fmt |= m[i][8] << i
    fmt |= m[7][8] << 6 | m[8][8] << 7 | m[8][7] << 8
    for i in range(9, 15):
        fmt |= m[8][14 - i] << i
    fmt2 = 0
    for i in range(8):
        fmt2 |= m[8][n - 1 - i] << i
    for i in range(8, 15):
        fmt2 |= m[n - 15 + i][8] << i
    assert fmt == fmt2 == qrcode_min._bch_format((fmt ^ 0x5412) >> 10)
    mask = ((fmt ^ 0x5412) >> 10) & 7
    fn = [[False] * n for _ in range(n)]

    def rect(x0, y0, w, h):
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                if 0 <= x < n and 0 <= y < n:
                    fn[y][x] = True
    for i in range(n):
        fn[6][i] = fn[i][6] = True
    rect(0, 0, 9, 9), rect(n - 8, 0, 8, 9), rect(0, n - 8, 9, 8)
    if v >= 2:
        rect(n - 9, n - 9, 5, 5)
    bits, x, up = [], n - 1, True
    while x > 0:
        x -= 1 if x == 6 else 0
        for i in range(n):
            y = n - 1 - i if up else i
            for xx in (x, x - 1):
                if not fn[y][xx]:
                    bits.append(m[y][xx] ^ (1 if qrcode_min._MASKS[mask](y, xx) else 0))
        up, x = not up, x - 2
    cw = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits) - len(bits) % 8, 8)]
    ec, blocks = qrcode_min._M[v]
    nb, dd = sum(b for b, _d in blocks), blocks[0][1]
    cw = cw[:nb * (dd + ec)]
    blk = [[cw[i * nb + b] for i in range(dd)] for b in range(nb)]
    for b in range(nb):
        assert qrcode_min._rs(blk[b], ec) == [cw[nb * dd + i * nb + b] for i in range(ec)], 'error correction of block %d' % b
    s = ''.join(format(w, '08b') for b in blk for w in b)
    assert s[:4] == '0100'
    return bytes(int(s[12 + 8 * i:20 + 8 * i], 2) for i in range(int(s[4:12], 2)))


class QrRead(unittest.TestCase):
    def test_every_version_reads_back_what_was_put_in(self):
        for text in ('A', 'x' * 14, 'x' * 15, 'y' * 27, 'https://acrdaily.com/n/abcdefghijkl', 'u' * 62, 'v' * 84, 'k' * 106):
            m = qrcode_min.matrix(text)
            self.assertEqual(_qr_read(m, (len(m) - 17) // 4), text.encode(), text)


class Reviewed(unittest.TestCase):
    """Bugs found in the review of 25 Nov 2026 (CODRIVER DAILY + CASUAL), each with its regression."""

    def test_a_packet_that_came_two_ways_is_played_once(self):
        from acr_daily import voice
        played = []

        class Spk:
            ok = True

            def queued(self):
                return 0

            def play(self, pcm):
                played.append(pcm)
                return True

            def close(self):
                pass

        class Mic:
            ok = True

            def read(self):
                return None

            def close(self):
                pass
        v = voice.Voice(lambda p: None, mode='off', mic=Mic(), speaker=Spk(), radio=False, seat=2)
        try:
            pk = [struct.pack('<H', k + 1) + voice.encode(b'\0\0' * voice.FRAME) for k in range(6)]
            for p in pk:                                   # (straight, and again through the relay)
                v.heard(p, 0)
                v.heard(p, 0)
            self.assertEqual(len(v._in[0]) + len(played), 6)
            time.sleep(0.4)
            self.assertEqual(len(played), 6, 'each 20 ms once, not twice')
            v.heard(pk[5], 0)                              # (the last one played, again: its copy)
            time.sleep(0.1)
            self.assertEqual(len(played), 6)
        finally:
            v.close()

    def test_a_speaker_who_comes_back_with_a_new_count_is_heard(self):
        from acr_daily import voice
        v = voice.Voice(lambda p: None, mode='off', mic=type('M', (), {'ok': True, 'read': lambda s: None, 'close': lambda s: None})(),
                        speaker=type('S', (), {'ok': True, 'queued': lambda s: 99, 'play': lambda s, p: True, 'close': lambda s: None})(),
                        radio=False, seat=2)
        try:
            v._last[1] = 3000                              # (the last of their words, heard 2 s ago)
            v._at[1] = time.monotonic() - 2.0
            v.heard(struct.pack('<H', 1) + voice.encode(b'\0\0' * voice.FRAME), 1)    # (a re-joined member: its count from 1)
            self.assertEqual(len(v._in[1]), 1, 'not dropped as older than 3000')
            v._last[1] = 3000                              # (but right after their words, 1 is still late)
            v._in[1].clear()
            v.heard(struct.pack('<H', 1) + voice.encode(b'\0\0' * voice.FRAME), 1)
            self.assertEqual(len(v._in[1]), 0)
        finally:
            v.close()

    def test_a_relayed_voice_is_taken_by_its_senders_link_only(self):
        import base64
        from acr_daily import crew, copilotlink
        heard = []

        class V:
            def __init__(self, send, seat=None, **kw):
                self.heard = lambda p, w: heard.append((p, w))
                self.close = lambda: None
        c = crew.Crew(mock.Mock(), 0, True, lambda *a: None, [('s1', 1), ('s2', 2)], {},
                      link_factory=lambda *a, **k: copilotlink.Link(*a, stun=(), bind=('127.0.0.1', 0), **k), voice_factory=V)
        try:
            msg = 'v' + base64.b64encode(bytes([2]) + b'12345').decode()
            for link in c.links.values():                  # (the relay's message from s2 goes to every link, as on_crew does)
                link.crew('s2', msg)
            self.assertEqual(heard, [(b'12345', 2)], 'once, as seat 2: before any details came it was taken by both links')
        finally:
            c.close()

    def test_the_status_goes_through_the_relay_once_for_all_the_links(self):
        from acr_daily import crew
        sent = []

        class L:
            def __init__(self, direct):
                self.direct = direct

            def send_status(self, s, relay=True):
                sent.append((id(self), s, relay))

            def close(self):
                pass
        links = iter([L(True), L(False), L(False)])
        c = crew.Crew(mock.Mock(), 0, True, lambda *a: None, [('a', 1), ('b', 2), ('c', 3)], {},
                      link_factory=lambda *a, **k: next(links), voice_factory=lambda *a, **k: mock.Mock())
        c.send_status('1|r|5|0|3')
        self.assertEqual([(s, r) for _i, s, r in sent], [('1|r|5|0|3', False), ('1|r|5|0|3', True)],
                         'straight to the one, and ONE relay message for the two others')

    def test_a_link_that_cannot_publish_does_not_hammer_the_server(self):
        from acr_daily import copilotlink
        tries = []

        def refuse(d):
            tries.append(time.monotonic())
            raise OSError('refused')
        link = copilotlink.Link(refuse, lambda m: None, lambda p, s: None, stun=(), bind=('127.0.0.1', 0))
        try:
            time.sleep(0.6)
            self.assertLessEqual(len(tries), 2)
        finally:
            link.close()

    def test_the_other_modes_room_is_not_cleared_nor_the_mine_dropped_by_the_daily_crew(self):
        a, cs = made()
        from acr_daily import copilot
        daily = copilot.Copilot(a)
        a.copilot = daily
        owner = __import__('acr_daily.ttui', fromlist=['x']).TimeTrialUI.crew_owner
        a.crew_owner = lambda: owner(a)
        a.ghostcars.live = mock.Mock(room=None)
        cs.lobby = lobby('1', 'started', n=2)
        cs._lobby_at = daily._lobby_at = time.monotonic() + 1e6          # (no poll to the stub api)
        cs.tick()
        self.assertEqual(a.ghostcars.live.room, 'cp:%d' % (casual.ROOM_BASE + 4))
        daily.tick()
        self.assertEqual(a.ghostcars.live.room, 'cp:%d' % (casual.ROOM_BASE + 4), 'the daily mode has no lobby: not its room')
        cs.lobby = None
        daily.tick()
        self.assertIsNone(a.ghostcars.live.room, 'nobody has a lobby: cleared')

    def test_the_relay_room_of_the_ghost_cars_follows_the_mode_that_has_the_lobby(self):
        from acr_daily import liverallyui
        a, cs = made()
        owner = __import__('acr_daily.ttui', fromlist=['x']).TimeTrialUI.crew_owner
        holder = mock.Mock()
        holder.casual, holder.copilot = cs, mock.Mock(room=lambda: None, lobby=None)
        holder.crew_owner = lambda: owner(holder)
        holder.ghostcars.live = mock.Mock(room=None)
        holder.league_run = None
        holder.watch = None
        holder._lr_following = lambda: False
        cs.lobby = lobby('1', 'started', n=2)
        liverallyui.LiveRallyUI._lr_room(holder)
        self.assertEqual(holder.ghostcars.live.room, 'cp:%d' % (casual.ROOM_BASE + 4))

    def test_a_casual_result_goes_to_casual_even_after_its_lobby_is_over(self):
        from acr_daily import ttui
        holder = mock.Mock()
        holder.casual, holder.copilot = mock.Mock(lobby=None), mock.Mock(lobby=None)
        holder.crew_owner = lambda: ttui.TimeTrialUI.crew_owner(holder)
        crew_for = lambda cid: ttui.TimeTrialUI.crew_for(holder, cid)
        self.assertIs(crew_for('cx:4'), holder.casual, 'the lobby is over already: still casual\'s')
        self.assertIs(crew_for('cp:2026-11-25/4'), holder.copilot)

    def test_the_other_mode_blocks_a_second_lobby_both_ways(self):
        from acr_daily import copilot
        a, cs = made()
        daily = copilot.Copilot(a)
        a.copilot = daily
        cs.lobby = lobby('1')
        daily.create('driver')
        self.assertIn('CASUAL', daily.msg)
        self.assertFalse(daily.busy)
        cs.lobby = None
        daily.lobby = {'id': 9, 'state': 'open'}
        cs.create({})
        self.assertIn('CODRIVER DAILY', cs.msg)

    def test_a_start_seen_here_is_set_up_even_with_the_pc_clock_far_ahead(self):
        a, cs = made()
        cs.start_link = lambda: None
        a._tt_drive_go = mock.Mock()
        cs._take_lobby(lobby('1', 'open', n=2))
        cs._take_lobby(lobby('1', 'started', n=2, started=(time.time() - 7200) * 1000))
        a._tt_drive_go.assert_called_once()
        a2, cs2 = made()
        cs2.start_link = lambda: None
        a2._tt_drive_go = mock.Mock()
        cs2._take_lobby(lobby('1', 'started', n=2, started=(time.time() - 7200) * 1000))
        a2._tt_drive_go.assert_not_called()                 # (found started and old: only by hand)

    def test_an_answer_about_a_lobby_i_left_changes_nothing(self):
        a, cs = made()
        cs.start_link = lambda: None
        a._tt_drive_go = mock.Mock()
        cs.lobby = None
        cs._lobby_in(lobby('1', 'started', n=2), 4)         # (the poll was for lobby 4, which I have left since)
        self.assertIsNone(cs.lobby)
        a._tt_drive_go.assert_not_called()
        cs.lobby = dict(lobby('1', n=2), id=5)
        cs._lobby_failed(mock.Mock(code=404), 4)
        self.assertEqual(cs.lobby['id'], 5, 'lobby 4\'s 404 must not end lobby 5')
        cs._lobby_failed(mock.Mock(code=404), 5)
        self.assertIsNone(cs.lobby)

    def test_the_last_partner_s_game_co_driver_word_is_not_kept_for_the_next_lobby(self):
        a, cs = made()
        cs._status_in('0')
        self.assertIs(cs.partner_off, False)
        cs._partner_on_at = time.monotonic() - 10
        cs.stop_link()
        self.assertIsNone(cs.partner_off)
        self.assertIsNone(cs._partner_on_at)

    def test_another_lobby_replaces_the_old_ones_crew(self):
        a, cs = made()
        closed = []
        cs.crew = mock.Mock(close=lambda: closed.append(1))
        cs.lobby = lobby('1', n=2)
        cs.start_link = lambda: None
        cs._take_lobby(dict(lobby('1', n=2), id=9))
        self.assertEqual(closed, [1])
        self.assertIsNone(cs.crew)


if __name__ == '__main__':
    unittest.main()
