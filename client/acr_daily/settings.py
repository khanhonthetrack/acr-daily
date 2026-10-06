"""Settings and local files, in %APPDATA%\\ACR Daily."""
import json
import os

# The server the app talks to: build.bat <url> writes it into _server.txt (bundled in the exe).
# A "server" entry in settings.json overrides it on one PC.
def _default_server():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '_server.txt'), encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


DEFAULT_SERVER = _default_server()

DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'ACR Daily')
FILE = os.path.join(DIR, 'settings.json')
PENDING = os.path.join(DIR, 'pending.json')      # runs not sent yet (offline)
RESULTS = os.path.join(DIR, 'results.jsonl')     # every run, kept locally
ROUTES = os.path.join(DIR, 'routes')              # routes recorded in admin mode

DEFAULTS = {
    'server': '',
    'token': '',
    'steamId': '',
    'name': '',
    # onlyOnDaily: the overlays show only while a daily's stage + car are loaded (and the conditions look right)
    # offerNext: after a counted run of one daily, a card under the timer offers to drive the other one
    'overlay': {'x': 60, 'y': 60, 'scale': 1.0, 'visible': True, 'locked': False, 'onlyOnDaily': True,
                'offerNext': True},
    'admin': False,
    'adminKey': '',
}


def load():
    s = json.loads(json.dumps(DEFAULTS))
    try:
        with open(FILE, encoding='utf-8') as f:
            data = json.load(f)
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(s.get(k), dict):
                s[k].update(v)
            else:
                s[k] = v
    except (OSError, ValueError):
        pass
    return s


def save(s):
    os.makedirs(DIR, exist_ok=True)
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, FILE)


def server_url(s):
    return (s.get('server') or DEFAULT_SERVER).rstrip('/')


def append_result(r):
    os.makedirs(DIR, exist_ok=True)
    with open(RESULTS, 'a', encoding='utf-8') as f:
        f.write(json.dumps({k: v for k, v in r.items() if k != 'trace'}) + '\n')
