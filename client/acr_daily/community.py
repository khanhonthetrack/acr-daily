"""Community content (the COMMUNITY page, communityui.py): tracks, cars and skins made by the community, installed into
the game in one click and taken out again.

The server lists them (GET /api/community, server src/community.js): three categories, each item with a manifest on
GitHub (its release) that says what its package is:

    {"id": "acrdaily-london", "version": "1", "acrBuild": "25170642",
     "zip": {"name": "ACRDaily-London-1.zip", "size": 812345678, "sha256": "..."},
     "files": [{"name": "zz_acrxs_....pak", "size": ..., "sha256": "..."}, ...]}

The zip sits next to the manifest. Its files go into <game>\\acr\\Content\\Paks\\~mods (the folder the game loads mods
from), flat, each checked against its SHA-256; ~mods\\ACRDaily-community.json lists what was put there, so taking an
item out removes exactly that.

The ACR build: a track converted with acr-extrastages brings a menu registry built against one build of the game, and
after a game update a stale registry hides the game's own rows (acr-extrastages docs/additive-plan.md). So an item
is installed only on the build it was made for, and guard() takes it out again when the game has been updated (a
package for the new build then comes as an update). The build is the one Steam installed
(steamapps\\appmanifest_3917090.acf, "buildid").

The game holds its .pak files open while it runs: installing and removing wait until it is closed.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import zipfile

from . import USER_AGENT, settings
from .saveslot import STEAM_APP

INSTALLED = 'ACRDaily-community.json'
CHUNK = 1 << 20


class CommunityError(Exception):
    """kind: 'nogame', 'running', 'build', 'download', 'checksum', 'clash', 'files', 'manifest'."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail


# ---------------------------------------------------------------------- the game

def mods_dir(game):
    """The folder the game loads mod packages from."""
    return os.path.join(game, 'acr', 'Content', 'Paks', '~mods')


def game_build(game):
    """The game's build id as Steam installed it ('25170642'), or None. The game's folder is
    <library>\\steamapps\\common\\<name>: its app manifest is <library>\\steamapps\\appmanifest_<app>.acf."""
    if not game:
        return None
    steamapps = os.path.dirname(os.path.dirname(os.path.normpath(game)))
    try:
        with open(os.path.join(steamapps, 'appmanifest_%d.acf' % STEAM_APP), encoding='utf-8', errors='replace') as f:
            m = re.search(r'"buildid"\s+"(\d+)"', f.read())
    except OSError:
        return None
    return m.group(1) if m else None


def game_running():
    """Whether the game is running (always False away from Windows)."""
    try:
        from .modinstall import _game_pids, _kernel32
        return bool(_game_pids(_kernel32()))
    except Exception:
        return False


# ---------------------------------------------------------------------- what is installed

def installed(game):
    """{item id: {version, acrBuild, files: [names], at}} from ~mods\\ACRDaily-community.json ({} if none)."""
    try:
        with open(os.path.join(mods_dir(game), INSTALLED), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_installed(game, d):
    path = os.path.join(mods_dir(game), INSTALLED)
    if not d:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    os.replace(path + '.tmp', path)


def status(item, man, game, build=None):
    """What the item's card says and offers:
      'nogame'      the game isn't found
      'unavailable' no package yet (no manifest)
      'install'     not installed, its package fits this game
      'installed'   installed and up to date
      'update'      installed, a newer package fits this game
      'wait'        its package is for another build of the game (an update of it is coming)
    """
    if not game:
        return 'nogame'
    build = build or game_build(game)
    have = installed(game).get(item['id'])
    if not man:
        return 'installed' if have else 'unavailable'
    fits = not man.get('acrBuild') or not build or str(man['acrBuild']) == str(build)
    if have and str(have.get('version')) == str(man.get('version')) and fits:
        return 'installed'
    return ('update' if have else 'install') if fits else 'wait'


def requires_ok(item_id, game=None):
    """Whether an item a stage needs (its `requires`) is installed (and for this game's build)."""
    game = game or _game()
    if not game:
        return False
    have = installed(game).get(item_id)
    if not have:
        return False
    build = game_build(game)
    return not have.get('acrBuild') or not build or str(have['acrBuild']) == str(build)


def _game():
    from .modinstall import game_dir
    return game_dir()


# ---------------------------------------------------------------------- the server and GitHub

def _get(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': USER_AGENT}), timeout=timeout) as r:
        return r.read()


def catalog(api):
    """The server's list: {categories: [{id, name, items}]}."""
    return api.community()


def manifest(item, timeout=30):
    """An item's package (its manifest on GitHub), or None when there is none yet. Raises CommunityError('manifest')
    for one that doesn't read as one."""
    url = item.get('manifest')
    if not url:
        return None
    try:
        if url.startswith(('http://', 'https://')):
            data = _get(url, timeout)
        else:                                            # (a file: tests, or a copy at hand)
            with open(url, 'rb') as f:
                data = f.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise CommunityError('download', str(e))
    except (OSError, ValueError) as e:
        raise CommunityError('download', str(e))
    try:
        m = json.loads(data.decode('utf-8'))
        assert m.get('id') == item['id'] and m.get('version') and m.get('zip', {}).get('sha256') and m.get('files')
        for f in m['files']:
            assert re.fullmatch(r'[A-Za-z0-9_.\-]+', f['name']) and len(f.get('sha256', '')) == 64
    except (ValueError, AssertionError, KeyError, TypeError, AttributeError):
        raise CommunityError('manifest', 'not a package manifest: %s' % url)
    m['zipUrl'] = m['zip'].get('url') or url.rsplit('/', 1)[0] + '/' + m['zip']['name']
    return m


def cache_path(man):
    return os.path.join(settings.DIR, 'community', '%s-%s.zip' % (man['id'], man['version']))


def download(man, progress=None, cancel=None, timeout=60):
    """The item's zip, downloaded (or the one already here) and checked against its SHA-256 -> its path.
    progress(done_bytes, total_bytes); cancel() -> True stops it. Raises CommunityError('download' / 'checksum')."""
    path = cache_path(man)
    want, size = man['zip']['sha256'].lower(), int(man['zip'].get('size') or 0)
    if os.path.isfile(path) and _file_sha(path) == want:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    url, tmp = man['zipUrl'], path + '.part'
    h, done = hashlib.sha256(), 0
    try:
        if url.startswith(('http://', 'https://')):
            src = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': USER_AGENT}), timeout=timeout)
            size = int(src.headers.get('Content-Length') or size)
        else:                                            # (a file: tests, or a copy at hand)
            src = open(url, 'rb')
        with src, open(tmp, 'wb') as out:
            while True:
                if cancel and cancel():
                    raise CommunityError('download', 'cancelled')
                b = src.read(CHUNK)
                if not b:
                    break
                out.write(b)
                h.update(b)
                done += len(b)
                if progress:
                    progress(done, size)
    except CommunityError:
        _rm(tmp)
        raise
    except (OSError, ValueError) as e:
        _rm(tmp)
        raise CommunityError('download', str(e))
    if h.hexdigest() != want:
        _rm(tmp)
        raise CommunityError('checksum', 'the download is not the expected file (try again)')
    os.replace(tmp, path)
    return path


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(CHUNK), b''):
            h.update(b)
    return h.hexdigest()


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------- in and out

def clashes(game, man):
    """Packages in ~mods that aren't ours and would be replaced or would replace ours: files of the same name, and
    other acr-extrastages packages (zz_acrxs_*: only one menu registry works at a time)."""
    ours = {n for it in installed(game).values() for n in it.get('files', [])}
    names = {f['name'] for f in man['files']}
    try:
        present = os.listdir(mods_dir(game))
    except OSError:
        return []
    acrxs = any(n.lower().startswith('zz_acrxs_') for n in names)
    return sorted(n for n in present if n not in ours and n != INSTALLED and
                  (n in names or (acrxs and n.lower().startswith('zz_acrxs_'))))


def install(game, man, zip_path, force=False):
    """The item's files from its zip into ~mods (each checked), and listed as ours. An older version of it goes first.
    Raises CommunityError: 'running' (close the game), 'build' (made for another build), 'clash' (other packages
    in the way: force=True replaces them), 'files' (the zip doesn't hold what the manifest says)."""
    if not game:
        raise CommunityError('nogame')
    if game_running():
        raise CommunityError('running', 'close the game first: it keeps its packages open')
    build = game_build(game)
    if man.get('acrBuild') and build and str(man['acrBuild']) != str(build):
        raise CommunityError('build', 'made for ACR build %s; yours is %s' % (man['acrBuild'], build))
    clash = clashes(game, man)
    if clash and not force:
        raise CommunityError('clash', ', '.join(clash))
    dest = mods_dir(game)
    os.makedirs(dest, exist_ok=True)
    if man['id'] in installed(game):
        uninstall(game, man['id'])
    for n in clash:
        _rm(os.path.join(dest, n))
    written = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            members = {os.path.basename(i.filename): i for i in z.infolist() if not i.is_dir()}
            for f in man['files']:
                info = members.get(f['name'])
                if info is None:
                    raise CommunityError('files', '%s is not in the package' % f['name'])
                h = hashlib.sha256()
                tmp = os.path.join(dest, f['name'] + '.part')
                with z.open(info) as src, open(tmp, 'wb') as out:
                    for b in iter(lambda: src.read(CHUNK), b''):
                        out.write(b)
                        h.update(b)
                if h.hexdigest() != f['sha256'].lower():
                    _rm(tmp)
                    raise CommunityError('files', '%s is damaged in the package' % f['name'])
                os.replace(tmp, os.path.join(dest, f['name']))
                written.append(f['name'])
    except (CommunityError, zipfile.BadZipFile, OSError) as e:
        for n in written:
            _rm(os.path.join(dest, n))
        if isinstance(e, CommunityError):
            raise
        raise CommunityError('files', str(e))
    d = installed(game)
    d[man['id']] = {'version': str(man['version']), 'acrBuild': str(man.get('acrBuild') or ''), 'files': written,
                    'at': int(time.time())}
    _save_installed(game, d)
    return written


def uninstall(game, item_id):
    """The item's files out of ~mods (only what we put there). Raises CommunityError('running')."""
    if game_running():
        raise CommunityError('running', 'close the game first: it keeps its packages open')
    d = installed(game)
    it = d.pop(item_id, None)
    if not it:
        return []
    for n in it.get('files', []):
        _rm(os.path.join(mods_dir(game), n))
    _save_installed(game, d)
    return it.get('files', [])


def guard(game, build=None):
    """Items installed for another build of the game (it has been updated): taken out, so their stale menu registry
    can't hide the game's own rows. -> the ids taken out (the game running: none yet, tried again later)."""
    if not game:
        return []
    build = build or game_build(game)
    if not build:
        return []
    stale = [k for k, v in installed(game).items() if v.get('acrBuild') and str(v['acrBuild']) != str(build)]
    if not stale or game_running():
        return []
    for k in stale:
        uninstall(game, k)
    return stale


def size_text(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%.0f %s' if unit in ('B', 'KB') else '%.1f %s') % (n, unit)
        n /= 1024
