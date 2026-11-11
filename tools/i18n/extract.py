"""The strings ACR Daily shows, for its translations.

    python tools/i18n/extract.py check          what each language lacks, has too much of, or gets wrong
    python tools/i18n/extract.py api            writes server/src/locales/api.js (the API's messages: their patterns)
    python tools/i18n/extract.py list [app|web] the strings, one a line (a plural: one | other)

Where they come from:
  the app      client/acr_daily/*.py: _('...'), n_('one', 'other', n), said('...'), said_n('one', 'other', n), N_('...')
               (%s, %d, %(x)s: Python's; a translation may reorder them POSIX-style, %2$s ... %1$s)
  the website  server/src/*.js: t('...'), tq('...'), ts('...'), tr('...'), N_('...'), tqp / tn / forms('one', 'other'),
               page(L, 'title', 'text') ({0}, {1}...: the values, in any order); the API's messages: err('...'),
               error: '...', throw new Error('...') (a `${...}` in them: {0}, {1}...)
The catalogs: client/acr_daily/locales/<code>.json and server/src/locales/<code>.js, English -> the language; a plural
holds the language's forms (pl: 3, ja / zh / hu: 1, the others: 2).
"""
import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, 'client', 'acr_daily')
WEB = os.path.join(ROOT, 'server', 'src')
CODES = ('pl', 'hu', 'ja', 'de', 'fr', 'it', 'zh')
# translated but not offered for now (the app's and the website's LANGS): checked with `check --all`
PAUSED = ('es', 'pt')
NFORMS = {'pl': 3, 'ja': 1, 'zh': 1, 'hu': 1}

# the API's messages only admins (or a broken client) ever see: left in English
API_SKIP = re.compile(r'^(bad |need |missing |not found$|server error$|no peeking$|unknown |admin|invalid json|'
                      r'posting |the route|route |stage id|a route|no route|pool|schedule|rejected|ban |unban|'
                      r'what every match races|move|trace|dry|fix|discord|webhook|no Discord|the webhook|'
                      r'reports key|.*\bADMIN_KEY\b|.*\bstageId\b|.*\btrack\b.*\bpoints\b|refused: |\{0\} \(or split|'
                      r'send a picture, or|editing the live board|resets: |at: |no finished run|this daily counts the game|'
                      r'this run has no trace|not allowed$|weather: |time: |no time trial run with|no run with that id|'
                      r'could not make a holder|rounds|round \{0\}|no official|the season: |the banner: base64|status: |'
                      r'prUrl|slot: |no time trial stage$|no stage TT|the owner is the owner|invalid$|cancelled$|'
                      r'only today|invalid run: the server did not see|no such file \(files|the weekly results|nothing sent$|'
                      r"paste the webhook|the first round opens)", re.I)


# ---------------------------------------------------------------------- the app (Python)
def app_strings():
    """{msgid: None | one} (a plural: its English one), in order."""
    out = {}
    for p in sorted(glob.glob(os.path.join(APP, '*.py'))):
        tree = ast.parse(open(p, encoding='utf-8-sig').read())
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
                continue
            name, args = n.func.id, n.args
            s = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None for a in args]
            if name in ('_', 'said', 'N_') and s and s[0]:
                out.setdefault(s[0], None)
            elif name in ('n_', 'said_n') and len(s) >= 2 and s[0] and s[1]:
                out[s[1]] = s[0]
    return out


# ---------------------------------------------------------------------- the website (JavaScript)
def js_string(src, i):
    """The JS string literal starting at src[i] ('...', "..." or `...` without ${}) -> (value, end) or None."""
    q = src[i]
    if q not in '\'"`':
        return None
    out, j = [], i + 1
    while j < len(src):
        c = src[j]
        if c == '\\':
            nx = src[j + 1]
            out.append({'n': '\n', 't': '\t', '\\': '\\', "'": "'", '"': '"', '`': '`', '$': '$'}.get(nx, nx))
            j += 2
            continue
        if q == '`' and c == '$' and src[j + 1] == '{':
            return None
        if c == q:
            return ''.join(out), j + 1
        out.append(c)
        j += 1
    return None


def js_template(src, i):
    """A template literal at src[i] with its ${...} as {0}, {1}... -> (pattern, end) or None (nested backticks)."""
    if src[i] != '`':
        return None
    out, j, k = [], i + 1, 0
    while j < len(src):
        c = src[j]
        if c == '\\':
            out.append(src[j + 1])
            j += 2
            continue
        if c == '$' and src[j + 1] == '{':
            depth, j = 1, j + 2
            while j < len(src) and depth:
                if src[j] == '`':
                    return None
                depth += {'{': 1, '}': -1}.get(src[j], 0)
                j += 1
            out.append('{%d}' % k)
            k += 1
            continue
        if c == '`':
            return ''.join(out), j + 1
        out.append(c)
        j += 1
    return None


CALL = re.compile(r'(?<![\w$.])(t|tq|ts|tr|N_|tqp|tn|forms|page)\(\s*')


def web_strings():
    out = {}
    for p in sorted(glob.glob(os.path.join(WEB, '*.js'))):
        if os.path.basename(p) == 'i18n.js' or '/locales/' in p:
            continue
        src = open(p, encoding='utf-8').read()
        for m in CALL.finditer(src):
            name, i = m.group(1), m.end()
            if name == 'page':                     # page(L, 'title', 'text', ...)
                if not src.startswith('L,', i):
                    continue
                i = i + 2
                for _k in range(2):
                    while src[i] in ' \n':
                        i += 1
                    got = js_string(src, i)
                    if not got:
                        break
                    out.setdefault(got[0], None)
                    i = got[1]
                    while src[i] in ' \n,':
                        i += 1
                continue
            got = js_string(src, i)
            if not got:
                continue
            first, j = got
            if name in ('tqp', 'tn', 'forms'):
                while src[j] in ' \n,':
                    j += 1
                second = js_string(src, j)
                if second:
                    out[second[0]] = first
                continue
            out.setdefault(first, None)
    # (i18n.js's own: the rallies, the weather...)
    src = open(os.path.join(WEB, 'i18n.js'), encoding='utf-8').read()
    for m in re.finditer(r"N_\('((?:[^'\\]|\\.)*)'\)", src):
        out.setdefault(m.group(1), None)
    return out


API = re.compile(r"(?<![\w$.])(?:err\(\s*|error:\s*|throw new Error\(\s*|new Gone\(\s*|apiTail\(\s*)")


def api_messages():
    """The API's messages as patterns ({0}: a value put in), in order, without the admins' own."""
    out = {}
    for p in sorted(glob.glob(os.path.join(WEB, '*.js'))):
        if os.path.basename(p) in ('i18n.js', 'adminpage.js', 'discord.js', 'discordevents.js', 'discordfaq.js',
                                   'cupdiscord.js', 'leaguediscord.js') or '/locales/' in p:
            continue
        src = open(p, encoding='utf-8').read()
        for m in API.finditer(src):
            i = m.end()
            got = js_string(src, i) or js_template(src, i)
            if not got:
                continue
            msg, j = got
            rest = src[j:j + 40].lstrip()
            if rest.startswith('+'):                    # 'credits start on ' + day
                n = len(re.findall(r'\{\d+\}', msg))
                msg += '{%d}' % n
            msg = msg.strip()
            if len(msg) < 4 or not re.search(r'[a-z]{3}', msg) or API_SKIP.match(msg):
                continue
            out.setdefault(msg, None)
    return out


# ---------------------------------------------------------------------- the catalogs
def load_catalog(kind, code):
    if kind == 'app':
        p = os.path.join(APP, 'locales', code + '.json')
        try:
            return json.load(open(p, encoding='utf-8'))
        except (OSError, ValueError):
            return {}
    p = os.path.join(WEB, 'locales', code + '.js')
    try:
        src = open(p, encoding='utf-8').read()
    except OSError:
        return {}
    body = src[src.index('{'):src.rindex('}') + 1]
    return json.loads(body)


PY_SPEC = re.compile(r'%(?:\((\w+)\))?[-+ #0]*\d*(?:\.\d+)?[sdfrxi%]|%\d+\$[-+ #0]*\d*(?:\.\d+)?[sdfrxi]')
JS_SPEC = re.compile(r'\{\d+\}')


def specs(kind, s):
    if kind == 'app':
        got = []
        for m in PY_SPEC.finditer(s):
            x = m.group(0)
            if x == '%%':
                continue
            x = re.sub(r'^%\d+\$', '%', x)       # %2$s -> %s (reordered: the same kinds)
            got.append(x)
        return sorted(got)
    return sorted(JS_SPEC.findall(s))


def problems(kind, msgid, value, code):
    """What is wrong with a translation (a list of words)."""
    out = []
    forms = value if isinstance(value, list) else [value]
    one = None
    for f in forms:
        if not isinstance(f, str) or not f:
            out.append('empty')
            continue
        want = specs(kind, msgid)
        if kind == 'app' and re.search(r'%-?[aAbBHMYm]', msgid):     # a date's format (i18n.strftime): its own codes
            want = specs(kind, f)
        if kind == 'app' and isinstance(value, list):
            ok = specs(kind, f) == want or (len(specs(kind, f)) == len(want) - 1)   # (a one-form may drop the count)
        else:
            ok = specs(kind, f) == want
        if not ok and not (isinstance(value, list) and set(specs(kind, f)) <= set(want)):
            out.append('placeholders %s, not %s' % (specs(kind, f), want))
        if kind == 'app' and re.search(r'%\d+\$', f) and len(re.findall(r'%\d+\$', f)) != len(specs(kind, f)):
            out.append('%N$ for some placeholders only (all or none)')
        if '"' in f and '"' not in msgid:
            out.append('a " (use typographic quotes)')
        for lead in ('\n', ' '):
            if msgid.startswith(lead) != f.startswith(lead) or msgid.endswith(lead) != f.endswith(lead):
                out.append('leading/trailing %r' % lead)
        for tag in re.findall(r'</?\w+[^>]*>', msgid):
            if tag not in f:
                out.append('missing markup %s' % tag)
    if isinstance(value, list) and len(value) != NFORMS.get(code, 2):
        out.append('%d plural forms, not %d' % (len(value), NFORMS.get(code, 2)))
    return out


def check(codes=CODES):
    bad = 0
    sets = {'app': app_strings(), 'web': {**web_strings(), **api_messages()}}
    for kind, want in sets.items():
        print('%s: %d strings' % (kind, len(want)))
        for code in codes:
            cat = load_catalog(kind, code)
            missing = [k for k in want if k not in cat]
            stale = [k for k in cat if k not in want]
            wrong = [(k, problems(kind, k, cat[k], code)) for k in cat if k in want]
            wrong = [(k, p) for k, p in wrong if p]
            print('  %s: %d missing, %d not used, %d wrong' % (code, len(missing), len(stale), len(wrong)))
            for k in missing[:5]:
                print('      missing: %r' % k)
            for k in stale[:5]:
                print('      not used: %r' % k)
            for k, p in wrong[:20]:
                print('      wrong: %r: %s' % (k, '; '.join(p)))
            bad += len(missing) + len(wrong)
    return bad


def write_api():
    msgs = list(api_messages())
    p = os.path.join(WEB, 'locales', 'api.js')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('// The API\'s messages (written by tools/i18n/extract.py api): src/i18n.js says them in the request\'s\n'
                '// language, as a whole or by their pattern ({0}: a value put in).\nexport const API_MESSAGES = ')
        f.write(json.dumps(msgs, ensure_ascii=False, indent=0).replace('\n', '\n  ').replace('[\n  ', '[\n  ', 1))
        f.write(';\n')
    print('wrote %s: %d messages' % (os.path.relpath(p, ROOT), len(msgs)))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'check':
        all_ = len(sys.argv) > 2 and sys.argv[2] == '--all'
        sys.exit(1 if check(CODES + PAUSED if all_ else CODES) else 0)
    if cmd == 'api':
        write_api()
        return
    if cmd == 'list':
        which = sys.argv[2] if len(sys.argv) > 2 else 'all'
        got = {}
        if which in ('app', 'all'):
            got.update(app_strings())
        if which in ('web', 'all'):
            got.update(web_strings())
            got.update(api_messages())
        for k, one in got.items():
            print(json.dumps([one, k] if one else k, ensure_ascii=False))
        return
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
