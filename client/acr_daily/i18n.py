"""The app's languages: every word on screen in the language picked in SETTINGS (or, the first time the app starts,
Windows' own when it is one of these; English otherwise).

The English is the key (as gettext's): _('Sign out') is 'Wyloguj się' in Polish. Each language's words are in
locales/<code>.json, English -> that language; a string not translated yet shows in English. A plural is keyed by its
English plural and holds the language's forms (CLDR's: Polish has three, Japanese one): n_('%d run', '%d runs', n).
tools/i18n/extract.py lists the strings the code uses and what each language still lacks.

Proper names stay as they are: the game's stages and cars, the drivers', leagues' and cups' own.
"""
import json
import os
import re

# (code, its own name): the order of the language pickers
LANGS = (
    ('en', 'English'),
    ('pl', 'Polski'),
    ('hu', 'Magyar'),
    ('ja', '日本語'),
    ('de', 'Deutsch'),
    ('fr', 'Français'),
    ('es', 'Español'),
    ('it', 'Italiano'),
    ('pt', 'Português (Brasil)'),
    ('zh', '简体中文'),
)
CODES = tuple(c for c, _n in LANGS)
NAMES = dict(LANGS)
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')

# Windows' primary language ids (LANGID & 0x3FF) -> ours
_WIN_LANG = {0x09: 'en', 0x15: 'pl', 0x0E: 'hu', 0x11: 'ja', 0x07: 'de', 0x0C: 'fr', 0x0A: 'es', 0x10: 'it',
             0x16: 'pt', 0x04: 'zh'}
# Bahnschrift has no Japanese or Chinese: their own Windows UI fonts instead (Latin in them too, so one font a label)
_CJK_FONT = {'ja': 'Yu Gothic UI', 'zh': 'Microsoft YaHei UI'}

_lang = 'en'
_words = {}


def plural_index(code, n):
    """Which of a language's plural forms goes with n (CLDR's rules for whole numbers)."""
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        n = 0
    if code in ('ja', 'zh', 'hu'):          # one form (Hungarian counts with the singular: "5 futam")
        return 0
    if code == 'pl':                        # 1 bieg, 2-4 biegi, 5 biegów (12-14 biegów, 22 biegi)
        if n == 1:
            return 0
        return 1 if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else 2
    if code in ('fr', 'pt'):                # 0 and 1 are singular
        return 0 if n in (0, 1) else 1
    return 0 if n == 1 else 1               # en, de, es, it


def load(code):
    """Switch to a language (an unknown one: English)."""
    global _lang, _words
    code = code if code in CODES else 'en'
    words = {}
    if code != 'en':
        try:
            with open(os.path.join(DIR, code + '.json'), encoding='utf-8') as f:
                words = json.load(f)
        except (OSError, ValueError):
            words = {}
    _lang, _words = code, words if isinstance(words, dict) else {}
    return _lang


def lang():
    return _lang


def word_in(code, s):
    """s in another language than the app's (the language picker asks in the one picked)."""
    if code == _lang:
        return _(s)
    try:
        with open(os.path.join(DIR, code + '.json'), encoding='utf-8') as f:
            v = json.load(f).get(s)
    except (OSError, ValueError, AttributeError):
        v = None
    return _word(v) if isinstance(v, str) and v else s


_ORDER = re.compile(r'%(\d+)\$')


class _Ordered(str):
    """A translation that puts the English's %s in another order: '%2$s ... %1$s' (as gettext's), the 1st, the 2nd...
    of the values the code gives it."""

    def __mod__(self, args):
        args = args if isinstance(args, tuple) else (args,)
        return str.__mod__(_ORDER.sub(lambda m: '%%(%s)' % m.group(1), self),
                           {str(i): a for i, a in enumerate(args, 1)})


def _word(v):
    return _Ordered(v) if '$' in v and _ORDER.search(v) else v


def _(s):
    """s in the app's language (s itself while it has no translation)."""
    v = _words.get(s)
    return _word(v) if isinstance(v, str) and v else s


def n_(one, other, n):
    """The form of a counted phrase that goes with n, in the app's language: n_('%d run', '%d runs', n) % n."""
    v = _words.get(other)
    if isinstance(v, str) and v:
        return _word(v)
    if isinstance(v, list) and v:
        return _word(v[min(plural_index(_lang, n), len(v) - 1)] or (one if n == 1 else other))
    return one if n == 1 else other


class Said(str):
    """English words that go to the server as they are (a run's DNF reason) and say themselves in the app's language
    on screen: local(s)."""
    tpl, args = '', ()


def said(tpl, *args):
    """tpl % args in English, which local() puts in the app's language."""
    s = Said(tpl % args if args else tpl)
    s.tpl, s.args = tpl, args
    return s


def said_n(one, other, n, *args):
    """said() of a counted phrase: one or other % args in English, n_(one, other, n) % args on screen."""
    s = Said((one if n == 1 else other) % args)
    s.tpl, s.args = (one, other, n), args
    return s


def local(s):
    """English words (said(), or a fixed phrase: from the server, from a file) in the app's language."""
    if isinstance(s, Said):
        if isinstance(s.tpl, tuple):
            return n_(*s.tpl) % s.args
        return _(s.tpl) % s.args if s.args else _(s.tpl)
    return _(s) if isinstance(s, str) and s else s


def cap(s):
    """The first letter in capitals, the rest as it is (str.capitalize would lower a German noun)."""
    return s[:1].upper() + s[1:] if s else s


def N_(s):
    """A word the code shows from data (the server's, the game's): marked here for tools/i18n/extract.py."""
    return s


# The server's and the game's own words the app shows: the rallies, their surfaces, the weather and the times of day
# (server src/conditions.js), as data.
DATA = (
    N_('Alsace'), N_('Greece'), N_('Monte Carlo'), N_('Wales'), N_('Livigno'),
    N_('Tarmac'), N_('Gravel'), N_('Snow'),
    N_('Clear'), N_('Light clouds'), N_('Clouds'), N_('Light fog'), N_('Fog'), N_('Light rain'), N_('Rain'),
    N_('Storm'), N_('Light snow'), N_('Snow blizzard'),
    N_('Morning'), N_('Midday'), N_('Afternoon'), N_('Evening'),
)
_TIME_LABEL = re.compile(r'^(.*?)\s*\((\d{1,2}:\d\d)\)$')


def data(s):
    """A rally's, a surface's or the weather's name from the server in the app's language; a time of day with its hour
    ('Afternoon (16:00)') too; anything else as it is."""
    if not isinstance(s, str) or not s:
        return s
    m = _TIME_LABEL.match(s)
    if m:
        return '%s (%s)' % (_(m.group(1)), m.group(2))
    return _(s)


_DAYS = (N_('Mon'), N_('Tue'), N_('Wed'), N_('Thu'), N_('Fri'), N_('Sat'), N_('Sun'))
_DAYS_LONG = (N_('Monday'), N_('Tuesday'), N_('Wednesday'), N_('Thursday'), N_('Friday'), N_('Saturday'), N_('Sunday'))
_MONTHS = (N_('Jan'), N_('Feb'), N_('Mar'), N_('Apr'), N_('May'), N_('Jun'), N_('Jul'), N_('Aug'), N_('Sep'), N_('Oct'),
           N_('Nov'), N_('Dec'))
_MONTHS_LONG = (N_('January'), N_('February'), N_('March'), N_('April'), N_('May'), N_('June'), N_('July'),
                N_('August'), N_('September'), N_('October'), N_('November'), N_('December'))


def strftime(fmt, t=None):
    """time.strftime with the days' and months' names in the app's language (%a %A %b %B), and %-d / %-m for the day
    and the month without a 0 (as the Japanese 11月9日). The format itself is a translation: _('%a %d %b')."""
    import time
    t = time.localtime() if t is None else t
    for k, v in (('%-d', str(t.tm_mday)), ('%-m', str(t.tm_mon)), ('%a', _(_DAYS[t.tm_wday])),
                 ('%A', _(_DAYS_LONG[t.tm_wday])), ('%b', _(_MONTHS[t.tm_mon - 1])), ('%B', _(_MONTHS_LONG[t.tm_mon - 1]))):
        fmt = fmt.replace(k, v.replace('%', '%%'))
    return time.strftime(fmt, t)


def font(name):
    """The font for the app's words: name, or the language's own when Bahnschrift can't write it."""
    return _CJK_FONT.get(_lang, name)


def spaced(text):
    """A small label's words spaced out letter by letter ('S E T T I N G S'); Japanese and Chinese as they are."""
    return text if _lang in _CJK_FONT else ' '.join(text.upper())


def system_lang():
    """Windows' display language when it is one of ours, else English."""
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return _WIN_LANG.get(lid & 0x3FF, 'en')
    except (AttributeError, OSError):
        pass
    try:
        import locale
        loc = (locale.getlocale()[0] or '').lower()
    except (ValueError, TypeError):
        loc = ''
    code = loc.replace('-', '_').split('_')[0]
    return code if code in CODES else 'en'


def accept_language():
    """The Accept-Language the app sends, so the server's own words (its messages, the weather) come back in it."""
    return _lang if _lang == 'en' else '%s, en;q=0.5' % _lang


def first_start():
    """Before the app is built (run.py): the language saved, or on the first start Windows' own, saved."""
    if os.environ.get('ACR_DAILY_LANG'):            # (development: that language, as _init loaded it)
        return _lang
    from . import settings
    s = settings.load()
    code = s.get('lang')
    if code not in CODES:
        code = system_lang()
        s['lang'] = code
        try:
            settings.save(s)
        except OSError:
            pass
    return load(code)


def _init():
    """The language saved in the settings; ACR_DAILY_LANG instead (development); English under the tests, whatever
    this PC's app is set to."""
    import sys
    code = os.environ.get('ACR_DAILY_LANG')
    if not code and 'unittest' in sys.modules:
        code = 'en'
    try:
        if not code:
            from . import settings
            code = settings.load().get('lang')
        load(code or 'en')
    except Exception:       # (never stop the app over its language)
        load('en')


_init()
