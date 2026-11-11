"""The app's languages (i18n.py): every catalog loads and its words fill in, plurals, word order, dates, and the header
made room for longer words."""
import json
import os
import re
import time
import unittest

from acr_daily import app as app_mod
from acr_daily import i18n


class Languages(unittest.TestCase):
    def tearDown(self):
        i18n.load('en')

    def test_every_language_offered_has_its_catalog(self):
        for code in i18n.CODES:
            if code == 'en':
                continue
            with open(os.path.join(i18n.DIR, code + '.json'), encoding='utf-8') as f:
                words = json.load(f)
            self.assertGreater(len(words), 800, code)
            self.assertEqual(i18n.load(code), code)
            self.assertNotEqual(i18n._('Language'), 'Language', code)

    def test_every_word_fills_in(self):
        """A translation takes the English's values: the same % specs (or all of them numbered, %2$s, for another
        order), so filling it in never raises."""
        spec = re.compile(r'%(?:(\d)\$)?[-#0 +]*\d*(?:\.\d+)?([sdifr%])')
        sample = {'s': 'x', 'd': 3, 'i': 3, 'f': 1.5, 'r': 'x'}
        for code in i18n.CODES:
            if code == 'en':
                continue
            i18n.load(code)
            for en, tr in i18n._words.items():
                if '%' not in en or re.fullmatch(r'[%a-zA-Z.:,\-年月日() ]+', en):   # (a date's format: strftime's)
                    continue
                args = tuple(sample[m.group(2)] for m in spec.finditer(en) if m.group(2) != '%')
                for form in (tr if isinstance(tr, list) else [tr]):
                    try:
                        i18n._Ordered(form) % args if '$' in form else form % args
                    except (TypeError, ValueError, KeyError) as e:
                        self.fail('%s: %r -> %r: %s' % (code, en, form, e))

    def test_plurals(self):
        self.assertEqual([i18n.plural_index('pl', n) for n in (1, 2, 4, 5, 12, 22, 25)], [0, 1, 1, 2, 2, 1, 2])
        self.assertEqual([i18n.plural_index('fr', n) for n in (0, 1, 2)], [0, 0, 1])
        self.assertEqual([i18n.plural_index('de', n) for n in (0, 1, 2)], [1, 0, 1])
        self.assertEqual(i18n.plural_index('ja', 7), 0)
        i18n.load('pl')
        self.assertEqual(i18n.n_('%d DAY', '%d DAYS', 5) % 5, '5 DNI')
        self.assertEqual(i18n.n_('%d DAY', '%d DAYS', 2) % 2, '2 DNI')

    def test_another_word_order(self):
        i18n.load('zh')
        self.assertEqual(i18n._('Buy %s for %d credits? You wear it straight away.') % ('Neon', 50),
                         '花 50 积分购买 Neon 吗？购买后立即佩戴。')

    def test_dates_in_the_language(self):
        i18n.load('de')
        t = time.struct_time((2026, 11, 9, 12, 0, 0, 0, 313, 0))      # a Monday
        self.assertEqual(i18n.strftime(i18n._('%A %d %B'), t), 'Montag, 9. November')
        i18n.load('ja')
        self.assertEqual(i18n.strftime(i18n._('%A %d %B'), t), '11月9日 月曜日')

    def test_the_server_is_asked_in_the_language(self):
        self.assertEqual(i18n.accept_language(), 'en')
        i18n.load('hu')
        self.assertEqual(i18n.accept_language(), 'hu, en;q=0.5')

    def test_a_language_not_offered_is_english(self):
        self.assertEqual(i18n.load('es'), 'en')          # (translated, but switched off for now)
        self.assertEqual(i18n.load('xx'), 'en')


class LongerWords(unittest.TestCase):
    def test_the_header_goes_to_two_rows_sooner(self):
        self.assertEqual(app_mod.layout_for(1200), (False, False))
        self.assertEqual(app_mod.layout_for(1200, extra=120), (True, False))

    def test_the_extra_width_is_the_words(self):
        self.assertEqual(app_mod.nav_extra(len), 0)              # (English: as wide as ever)
        i18n.load('fr')
        try:
            import importlib
            from acr_daily import tabsui
            importlib.reload(tabsui)                             # (NAV: the words in French)
            self.assertGreater(app_mod.nav_extra(len), 0)
        finally:
            i18n.load('en')
            importlib.reload(tabsui)


if __name__ == '__main__':
    unittest.main()
