"""Community content (the COMMUNITY page, communityui.py): tracks and cars made by the community, installed into
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

Stages from other tools (the test builds: an item's `install`):
  'manager'  Sando Rally's original stages (sandorally.com): their licence lets them be downloaded only from there and
             never repacked, and only Sando's own Stage Manager may install them (it builds the game's stage list from
             the player's own game files). So INSTALL downloads the official zip (the item's `download`: its address,
             size and SHA-256), checks it, unpacks it in the app's folder and opens the manager, where the player
             installs it; the unpacked download stays for the manager (updates, pace notes, removing) until the player
             lets it go.
  'link'     stages a tool makes on the player's PC (Stage-Exporter: WRC Generations' stages from the player's own copy
             of that game): only a link to the tool; nothing is downloaded from here.
Either way, what is in the game is read from the game's packages themselves (stage_packs): a stage's package lists
its pace notes as DT_Pacenote<stage id> (Sando's Chile BioBio: DT_PacenoteSandoChlBioFull), so the stages each
package carries are known whatever its file is called. The game has one stage list: each tool that adds stages
(acr-extrastages for ACR DAILY London, Sando's Stage Manager, Stage-Exporter) writes its own, so only one tool's
stages show at a time (Sando's and Stage-Exporter's notes say so); pack_groups() names the tools whose stages are in
the game, and the page warns when there are more than one. Nothing here moves another tool's files.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
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


# A package built on the PC from the game's own files (its manifest's 'assemble': the package holds only the stage's
# own files and deltas against the game's, put together with retoc): not done by this app yet (status 'newer').
ASSEMBLES = False


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


def status(item, man, game, build=None, packs=None):
    """What the item's card says and offers (packs: stage_packs(), for an item of another tool's: what is in the game;
    None, not looked at yet, reads as not installed):
      'nogame'      the game isn't found
      'unavailable' no package yet (no manifest)
      'install'     not installed, its package fits this game
      'installed'   installed and up to date
      'update'      installed, a newer package fits this game
      'wait'        its package is for another build of the game (an update of it is coming)
      'newer'       its package is built on this PC from the game's own files (manifest 'assemble': deltas against
                    them and retoc), which this app doesn't do yet: nothing is downloaded (ACR DAILY London from its
                    version 8, 13 Nov 2026)
      an item of another tool's (`install` 'manager' or 'link'):
      'installed'   some of its stages are in the game's packages
      'ready'       (manager) downloaded and unpacked here: its manager installs it
      'install'     (manager) not downloaded yet
      'link'        (link) not in the game: the tool makes it on the player's PC
    """
    if not game:
        return 'nogame'
    if item.get('install') in ('manager', 'link'):
        if stages_in_game(item, packs):
            return 'installed'
        if item['install'] == 'link':
            return 'link'
        return 'ready' if man and manager_exe(man) else 'install'
    build = build or game_build(game)
    have = installed(game).get(item['id'])
    if not man:
        return 'installed' if have else 'unavailable'
    if man.get('assemble') and not ASSEMBLES:
        return 'installed' if have else 'newer'
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
    for one that doesn't read as one. An item installed by its own manager: its official download (manager_package);
    a link: None."""
    if item.get('install') == 'manager':
        return manager_package(item)
    if item.get('install') == 'link':
        return None
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
        # (the version and id name the download's file in the app's folder: plain words only, no path in them)
        assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}', str(m['version'])) and re.fullmatch(r'[a-z0-9-]{1,60}', m['id'])
        for f in m['files']:
            # (a file's name in ~mods: no folder, nor '.' / '..', which name the folders around it)
            assert re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.\-]*', f['name']) and len(f.get('sha256', '')) == 64
    except (ValueError, AssertionError, KeyError, TypeError, AttributeError):
        raise CommunityError('manifest', 'not a package manifest: %s' % url)
    m['zipUrl'] = m['zip'].get('url') or _beside(url, m['zip']['name'])
    return m


def _beside(where, name):
    """The file `name` next to `where`: an address (its folder on the web) or a path on this PC (tests, a copy at hand:
    C:\\...\\manifest.json on Windows, which has no / to split at)."""
    if where.startswith(('http://', 'https://')):
        return where.rsplit('/', 1)[0] + '/' + name
    return os.path.join(os.path.dirname(where), name)


def cache_path(man):
    return os.path.join(settings.DIR, 'community', '%s-%s.zip' % (man['id'], man['version']))


def _parts(man):
    """The zip's downloads: [(url, size, sha256 or None)]. A zip over GitHub's 2 GB a file comes in parts (zip.parts:
    [{name, size, sha256}], next to the manifest), one after the other making the zip."""
    z = man['zip']
    if z.get('parts'):
        return [(_beside(man['zipUrl'], p['name']), int(p['size']), p['sha256'].lower()) for p in z['parts']]
    return [(man['zipUrl'], int(z.get('size') or 0), None)]


def download(man, progress=None, cancel=None, timeout=60):
    """The item's zip, downloaded (or the one already here; in parts, joined) and checked against its SHA-256 -> its
    path. progress(done_bytes, total_bytes); cancel() -> True stops it. Raises CommunityError('download' / 'checksum').
    A download in one piece that was cut off (a big one: Sando's stages are over 4 GB) goes on from where it stopped,
    when the server sends the rest (a range); else it starts again."""
    path = cache_path(man)
    want, size = man['zip']['sha256'].lower(), int(man['zip'].get('size') or 0)
    if os.path.isfile(path) and _file_sha(path) == want:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    h, done = hashlib.sha256(), 0
    parts = _parts(man)
    have = os.path.getsize(tmp) if len(parts) == 1 and os.path.isfile(tmp) else 0
    if have and size and have >= size:
        have = 0                                         # (all of it there, yet not the file: from the start)
    try:
        with open(tmp, 'ab' if have else 'wb') as out:
            for url, part_size, part_sha in parts:
                ph = hashlib.sha256()
                if url.startswith(('http://', 'https://')):
                    headers = {'User-Agent': USER_AGENT}
                    if have:
                        headers['Range'] = 'bytes=%d-' % have
                    src = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
                    if have and getattr(src, 'status', 200) != 206:   # (no range: the whole file again)
                        have = 0
                        out.seek(0)
                        out.truncate()
                    if len(parts) == 1:
                        size = int(src.headers.get('Content-Length') or 0) + have or size
                else:                                    # (a file: tests, or a copy at hand)
                    src = open(url, 'rb')
                    if have:
                        src.seek(have)
                if have:                                 # (what came before, all of the file: in the checksum)
                    with open(tmp, 'rb') as before:
                        for b in iter(lambda: before.read(CHUNK), b''):
                            h.update(b)
                            ph.update(b)
                    done = have
                with src:
                    while True:
                        if cancel and cancel():
                            raise CommunityError('download', 'cancelled')
                        b = src.read(CHUNK)
                        if not b:
                            break
                        out.write(b)
                        h.update(b)
                        ph.update(b)
                        done += len(b)
                        if progress:
                            progress(done, size)
                if part_sha and ph.hexdigest() != part_sha:
                    raise CommunityError('checksum', 'a part of the download is not the expected file (try again)')
    except CommunityError as e:
        if not (e.detail == 'cancelled' and len(parts) == 1):   # (cancelled: kept, to go on from there next time)
            _rm(tmp)
        raise
    except (OSError, ValueError) as e:
        # (in one piece: kept, to go on from there next time; unless the server can't send its rest, 416)
        if len(parts) != 1 or (isinstance(e, urllib.error.HTTPError) and e.code == 416):
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
    """The item's files from its zip into ~mods (each checked), and listed as ours. Every file is taken out and
    checked first (as .part files beside them); only then do an older version of it and the packages in the way go and
    the new files take their place, so a zip that fails (damaged, the disk full) leaves the game as it was.
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
    parts = []                                           # [(.part file, its name)]: taken out and checked
    try:
        with zipfile.ZipFile(zip_path) as z:
            members = {os.path.basename(i.filename): i for i in z.infolist() if not i.is_dir()}
            for f in man['files']:
                info = members.get(f['name'])
                if info is None:
                    raise CommunityError('files', '%s is not in the package' % f['name'])
                h = hashlib.sha256()
                tmp = os.path.join(dest, f['name'] + '.part')
                parts.append((tmp, f['name']))
                with z.open(info) as src, open(tmp, 'wb') as out:
                    for b in iter(lambda: src.read(CHUNK), b''):
                        out.write(b)
                        h.update(b)
                if h.hexdigest() != f['sha256'].lower():
                    raise CommunityError('files', '%s is damaged in the package' % f['name'])
    except (CommunityError, zipfile.BadZipFile, OSError) as e:
        for tmp, _n in parts:                            # (nothing else was touched)
            _rm(tmp)
        if isinstance(e, CommunityError):
            raise
        raise CommunityError('files', str(e))
    # every file is here and checked: the older version and what is in the way go, the new files in their place
    written = []
    try:
        if game_running():                               # (started while the package was being unpacked)
            raise CommunityError('running', 'close the game first: it keeps its packages open')
        if man['id'] in installed(game):
            uninstall(game, man['id'])
        for n in clash:
            _rm(os.path.join(dest, n))
        for tmp, n in parts:
            os.replace(tmp, os.path.join(dest, n))
            written.append(n)
    except (CommunityError, OSError) as e:
        for tmp, n in parts:                             # (no .part left in ~mods, taken for another mod's file later)
            if n not in written:
                _rm(tmp)
        if written:                                      # (what did go in is ours: REMOVE takes it out)
            d = installed(game)
            d[man['id']] = {'version': str(man['version']), 'acrBuild': str(man.get('acrBuild') or ''),
                            'files': written, 'at': int(time.time()), 'partial': True}
            _save_installed(game, d)
        if isinstance(e, CommunityError):
            raise
        raise CommunityError('files', str(e))
    d = installed(game)
    d[man['id']] = {'version': str(man['version']), 'acrBuild': str(man.get('acrBuild') or ''), 'files': written,
                    'at': int(time.time())}
    _save_installed(game, d)
    if os.path.abspath(zip_path) == os.path.abspath(cache_path(man)):
        _rm(zip_path)                                    # (in the game now: the download goes, not one kept a version)
    return written


def uninstall(game, item_id):
    """The item's files out of ~mods (only what we put there). Raises CommunityError('running')."""
    if game_running():
        raise CommunityError('running', 'close the game first: it keeps its packages open')
    d = installed(game)
    it = d.pop(item_id, None)
    if not it:
        return []
    gone, left = [], []
    for n in it.get('files', []):
        try:
            os.remove(os.path.join(mods_dir(game), n))
        except FileNotFoundError:                        # (gone already)
            pass
        except OSError:                                  # (held open: still ours, still listed, so not lost track of)
            left.append(n)
            continue
        gone.append(n)
    if left:
        d[item_id] = dict(it, files=left)
    _save_installed(game, d)
    if left:
        raise CommunityError('files', "couldn't take out %s" % ', '.join(left))
    return gone


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
    out = []
    for k in stale:
        try:
            uninstall(game, k)
        except CommunityError:                           # (a file held: the rest go, it is tried again later)
            continue
        out.append(k)
    return out


def size_text(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%.0f %s' if unit in ('B', 'KB') else '%.1f %s') % (n, unit)
        n /= 1024


# ---------------------------------------------------------------------- other tools' stages (the test builds)

_VERSION = r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}'
_FILE = r'[A-Za-z0-9][A-Za-z0-9 ._()-]{0,99}'


def manager_package(item):
    """An item installed by its own manager (`install` 'manager': Sando Rally's original stages): its official
    download (the item's `download`: url, name, size, sha256, version, the manager's file, the ACR build it was made
    for) as a package for download(). Raises CommunityError('manifest') for one that doesn't read as one."""
    d = item.get('download') or {}
    try:
        assert re.fullmatch(r'https://[^\s]+', d['url']) and re.fullmatch(_FILE, d['name']) and d['name'].endswith('.zip')
        assert re.fullmatch(_VERSION, str(d['version'])) and re.fullmatch(r'[a-z0-9-]{1,60}', item['id'])
        assert re.fullmatch(r'[0-9a-f]{64}', d['sha256'].lower()) and int(d['size']) > 0
        assert re.fullmatch(_FILE, d['manager']) and d['manager'].lower().endswith('.exe')
    except (KeyError, TypeError, ValueError, AttributeError, AssertionError):
        raise CommunityError('manifest', 'not a download: %s' % item.get('id'))
    return {'id': item['id'], 'version': str(d['version']), 'acrBuild': str(d.get('acrBuild') or ''),
            'zip': {'name': d['name'], 'size': int(d['size']), 'sha256': d['sha256'].lower(), 'url': d['url']},
            'zipUrl': d['url'], 'manager': d['manager'], 'files': [], 'page': item.get('page')}


def unpacked_dir(man):
    """Where its download is unpacked for its manager: the app's folder, community/<id>-<version>."""
    return os.path.join(settings.DIR, 'community', '%s-%s' % (man['id'], man['version']))


def manager_exe(man):
    """Its manager, at the top of its unpacked download, or None (not downloaded, or let go)."""
    if not man or not man.get('manager'):
        return None
    p = os.path.join(unpacked_dir(man), man['manager'])
    return p if os.path.isfile(p) else None


def space_needed(man, game):
    """What its download needs that isn't free: [(the folder, bytes short)]: the zip and its unpacked files in the
    app's folder (the zip goes once unpacked), and the stage again in the game's (its manager puts it there)."""
    size = int(man['zip']['size'])
    want = [(settings.DIR, 2 * size + (256 << 20)), (game, size + (256 << 20))]
    try:
        if os.path.isfile(cache_path(man)):
            want[0] = (settings.DIR, want[0][1] - size)       # (downloaded already)
    except OSError:
        pass
    short = []
    for folder, need in want:
        probe = folder
        while probe and not os.path.isdir(probe):
            probe = os.path.dirname(probe) if os.path.dirname(probe) != probe else ''
        try:
            free = shutil.disk_usage(probe or folder).free
        except OSError:
            continue
        if free < need:
            short.append((folder, need - free))
    return short


def unpack(man, zip_path, progress=None):
    """Its download unpacked as it comes, for its manager (its own folder, unpacked_dir), then the zip goes. Every
    name in the zip must stay inside that folder. -> the manager's path. Raises CommunityError('files')."""
    dest = unpacked_dir(man)
    tmp = dest + '.part'
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            total, done = sum(i.file_size for i in infos), 0
            root = os.path.realpath(tmp)
            for i in infos:
                name = i.filename.replace('\\', '/')
                target = os.path.realpath(os.path.join(tmp, *[p for p in name.split('/') if p]))
                if os.path.isabs(name) or not (target == root or target.startswith(root + os.sep)):
                    raise CommunityError('files', '%s would land outside its folder' % i.filename)
                if i.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(i) as src, open(target, 'wb') as out:
                    for b in iter(lambda: src.read(CHUNK), b''):
                        out.write(b)
                        done += len(b)
                        if progress:
                            progress(done, total)
    except CommunityError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise CommunityError('files', str(e))
    if not os.path.isfile(os.path.join(tmp, man['manager'])):
        shutil.rmtree(tmp, ignore_errors=True)
        raise CommunityError('files', '%s is not in the download' % man['manager'])
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    _rm(zip_path)                                        # (unpacked: the zip goes, 4 GB back)
    return os.path.join(dest, man['manager'])


def open_manager(man):
    """Its manager started (Windows), from its own folder. -> the process (wait() on it: the manager closed).
    Raises CommunityError('files') when it isn't there."""
    exe = manager_exe(man)
    if not exe:
        raise CommunityError('files', 'its manager is not downloaded')
    try:
        return subprocess.Popen([exe], cwd=os.path.dirname(exe))
    except OSError as e:
        raise CommunityError('files', str(e))


def delete_download(man):
    """Its unpacked download (and any zip left) let go: its manager can't be opened from here until downloaded again."""
    shutil.rmtree(unpacked_dir(man), ignore_errors=True)
    _rm(cache_path(man))
    _rm(cache_path(man) + '.part')


def download_size(man):
    """The space its unpacked download takes here (0: none)."""
    total = 0
    for dirpath, _dirs, names in os.walk(unpacked_dir(man)):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(dirpath, n))
            except OSError:
                pass
    return total


# the game's own containers (never a stage pack of a tool's): global.utoc, pakchunk12optional-Windows.utoc...
_STOCK = re.compile(r'^(global|pakchunk\d+(optional)?-windows)\.utoc$', re.I)
_PACENOTE = re.compile(rb'DT_Pacenote([A-Za-z0-9_]{3,60})')
PACK_MAX = 256 << 20          # (a stage pack's index is a few MB; a bigger .utoc isn't read)


def stage_packs(game, ids=()):
    """The stage packages in the game (any tool's: the game's own containers left out): {path relative to Paks:
    sorted stage ids}. A package's index (its .utoc) names a stage's pace notes DT_Pacenote<stage id>; the ids given
    (the catalogue's) are looked for by name too, for a tool that names its notes otherwise. {} without the game."""
    paks = os.path.join(game, 'acr', 'Content', 'Paks') if game else ''
    if not paks or not os.path.isdir(paks):
        return {}
    want = [(i, i.encode()) for i in ids if i]
    out = {}
    for dirpath, dirs, names in os.walk(paks):
        if dirpath[len(paks):].count(os.sep) >= 3:
            dirs[:] = []                                 # (a pack sits in Paks, ~mods or a folder in them)
        for n in names:
            if not n.lower().endswith('.utoc') or _STOCK.match(n):
                continue
            p = os.path.join(dirpath, n)
            try:
                if os.path.getsize(p) > PACK_MAX:
                    continue
                with open(p, 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            found = {m.group(1).decode() for m in _PACENOTE.finditer(data)}
            found.update(i for i, b in want if b in data)
            if found:
                out[os.path.relpath(p, paks)] = sorted(found)
    return out


def stages_in_game(item, packs):
    """The item's stage ids that are in the game's packages (packs: stage_packs())."""
    have = {s for ids in (packs or {}).values() for s in ids}
    have_l = {s.lower() for s in have}
    return [s['stageId'] for s in item.get('stages') or [] if s.get('stageId', '').lower() in have_l]


def pack_groups(items, packs, game=None):
    """The tools whose stages are in the game: {group: [its tool's name, else its items']}. An item's `group` ('sando', 'wrcg',
    'acrdaily'...): its stages in a package, or (this app's own) installed here; a package with no catalogue item's
    stages: its file's name, a group of its own. The game shows only one tool's stages at a time (its one stage
    list): more than one group is a clash."""
    groups = {}
    known = set()
    for it in items or []:
        g = it.get('group') or it['id']
        if stages_in_game(it, packs) or (game and it['id'] in installed(game)):
            label = it.get('tool') or it.get('name') or it['id']     # (the tool that put them in: it takes them out)
            if label not in groups.get(g, []):
                groups.setdefault(g, []).append(label)
        known.update(s.get('stageId', '').lower() for s in it.get('stages') or [])
    for path, ids in sorted((packs or {}).items()):
        if not any(i.lower() in known for i in ids):
            groups.setdefault('other:' + path, []).append(os.path.basename(path))
    return groups
