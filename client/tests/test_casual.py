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


if __name__ == '__main__':
    unittest.main()
