"""Liveries (COMMUNITY > LIVERIES, communityui.py): the drivers' liveries from the website (/liveries; the server's
src/liveries.js), put into the game in one click and taken out again.

In the game a livery is a folder, Documents\\My Games\\acr\\Liveries\\<car>\\<name>\\ (what ACR Livery Tool exports: the
livery's textures and its icon), 25 a car at most; one whose name starts with _ is skipped (turned off). The game
reads a new one only when it starts.

The website keeps a card for each livery with its link: where its author put the zip. When the link gives the zip
itself (a GitHub release, Dropbox, Google Drive, an address ending in .zip: the server's directUrl, `direct` in the
list), INSTALL downloads it (through the server's /go?direct=1, so it counts as a download) and unzips it: each folder
of the zip that holds files is a livery (a readme next to them left out), put in the car's folder under its own name;
a zip whose files are at its top is one livery, named after the card. %APPDATA%\\ACR Daily\\liveries.json lists what was
put where, so REMOVE takes out exactly that. Any other link (a download page) opens in the browser.

The car's folder: the one already in the Liveries folder or among the game's LiveryTemplates that names the car (the
game's own spelling), else the zip's own (<car>\\<name>\\ inside it), else the car's id in the game (src/cars.js).
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile

from . import USER_AGENT, settings
from .i18n import _, n_
from .names import same_car

PER_CAR = 25                       # the game's limit: user liveries a car
MAX_ZIP = 1 << 30                  # a livery's zip at most (4096 px textures: tens of MB)
MAX_FILES = 400
MAX_UNZIPPED = 2 << 30
CHUNK = 1 << 20
INSTALLED = 'liveries.json'
# never put into the game's folder: programs and scripts (a zip holding one is refused), and the game's mod packages
PROGRAMS = {'.exe', '.dll', '.bat', '.cmd', '.com', '.scr', '.ps1', '.psm1', '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh',
            '.msi', '.msp', '.lnk', '.reg', '.hta', '.cpl', '.jar', '.pif', '.sys', '.drv', '.ocx', '.url', '.sh',
            '.scf', '.library-ms', '.searchconnector-ms', '.appref-ms', '.application', '.settingcontent-ms'}
SKIP = {'.acrlivery', '.pak', '.ucas', '.utoc', '.sig'}      # (a Livery Tool project, mod packages: not a livery)
JUNK = {'.ds_store', 'thumbs.db', 'desktop.ini'}
DOCS = {'.txt', '.md', '.pdf', '.rtf', '.nfo', '.doc', '.docx', '.htm', '.html'}   # (a readme: never part of a livery)
BAD_NAME = re.compile(r'[\x00-\x1f<>:"|?*]')   # (a name Windows takes otherwise: a drive, a stream, a wildcard)
_LOCK = threading.Lock()           # (liveries.json: two installs at once, each its own card)


class LiveryError(Exception):
    """kind: 'page' (the link is a page: the browser), 'download', 'zip', 'files', 'full', 'nodir', 'unpack' (a .rar
    or .7z this PC's Windows can't unpack: its page, by hand)."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail


# ---------------------------------------------------------------------- where

def documents():
    """The user's Documents folder (where Windows keeps it: moved, or in OneDrive), else ~/Documents."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD), ('d', ctypes.c_ubyte * 8)]
        docs = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        out = ctypes.c_wchar_p()
        shell = ctypes.WinDLL('shell32')
        if shell.SHGetKnownFolderPath(ctypes.byref(docs), 0, None, ctypes.byref(out)) == 0 and out.value:
            path = out.value
            ctypes.WinDLL('ole32').CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def root():
    """The game's liveries folder: Documents\\My Games\\acr\\Liveries (ACR_DAILY_LIVERIES: another, for tests)."""
    return os.environ.get('ACR_DAILY_LIVERIES') or os.path.join(documents(), 'My Games', 'acr', 'Liveries')


def _subdirs(path):
    try:
        return sorted(n for n in os.listdir(path) if os.path.isdir(os.path.join(path, n)))
    except OSError:
        return []


def _car(car_id, cars):
    """{'car': its name, 'carId': its id} for names.same_car, from the server's list of cars."""
    c = next((c for c in cars or [] if c.get('id') == car_id), None) or {'id': car_id, 'name': car_id}
    return {'car': c.get('name'), 'carId': c.get('id')}


def car_folder(car_id, cars=(), base=None, game=None, hint=None):
    """The name of the car's folder in the liveries folder: one there already (or among the game's LiveryTemplates)
    that names the car, else the zip's own folder for it (hint), else the car's id."""
    want = _car(car_id, cars)
    for name in _subdirs(base or root()) + (_subdirs(os.path.join(game, 'acr', 'Content', 'LiveryTemplates')) if game else []):
        if same_car(name, want):
            return name
    if hint and same_car(hint, want):
        return hint
    return car_id


def in_use(folder):
    """The liveries the game takes from a car's folder (not turned off with a _ in front)."""
    return [n for n in _subdirs(folder) if not n.startswith('_')]


# ---------------------------------------------------------------------- what we put there

def _installed_path():
    return os.path.join(settings.DIR, INSTALLED)


def installed():
    """{livery id (str): {title, car, dirs: [paths], at}}: the ones still there."""
    try:
        with open(_installed_path(), encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if isinstance(v, dict) and any(os.path.isdir(p) for p in v.get('dirs') or [])}


def _save(d):
    os.makedirs(settings.DIR, exist_ok=True)
    path = _installed_path()
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    os.replace(path + '.tmp', path)


def status(lv):
    """What a livery's card says and offers:
      'installed'  in the game (REMOVE)
      'install'    its link gives the zip: INSTALL downloads and unzips it
      'page'       its link is a page (Overtake.gg, MEGA...): DOWNLOAD opens it in the browser
      'showonly'   no link: its author shows it only
    """
    if str(lv.get('id')) in installed():
        return 'installed'
    if not lv.get('go'):
        return 'showonly'
    return 'install' if lv.get('direct') else 'page'


# ---------------------------------------------------------------------- download

def cache_path(lv):
    return os.path.join(settings.DIR, 'liveries', '%s.zip' % int(lv['id']))


def download(lv, progress=None, cancel=None, timeout=60):
    """The livery's zip (through the server's /go?direct=1: counted as a download) -> its path. progress(done, total);
    cancel() -> True stops it. Raises LiveryError: 'page' (what came is a web page, not the zip), 'download', 'zip'."""
    url = lv.get('go')
    if not url or not lv.get('direct'):
        raise LiveryError('page')
    path = cache_path(lv)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    done = 0
    try:
        if url.startswith(('http://', 'https://')):
            sep = '&' if '?' in url else '?'
            src = urllib.request.urlopen(urllib.request.Request(url + sep + 'direct=1', headers={'User-Agent': USER_AGENT}),
                                         timeout=timeout)
            final = src.geturl() if hasattr(src, 'geturl') else url
            if url.startswith('https://') and not str(final or '').startswith('https://'):
                src.close()                          # (sent on to a plain address: anyone on the way could swap it)
                raise LiveryError('download', 'the link went on to an address that is not https')
            kind = (src.headers.get('Content-Type') or '').lower()
            size = int(src.headers.get('Content-Length') or 0)
            if kind.startswith('text/html'):
                src.close()
                raise LiveryError('page', 'the link gives a web page, not the zip')
        else:                                        # (a file: tests, or a copy at hand)
            src, size = open(url, 'rb'), os.path.getsize(url)
        if size > MAX_ZIP:
            src.close()
            raise LiveryError('download', 'over %d MB: not a livery' % (MAX_ZIP >> 20))
        with src, open(tmp, 'wb') as out:
            while True:
                if cancel and cancel():
                    raise LiveryError('download', 'cancelled')
                b = src.read(CHUNK)
                if not b:
                    break
                done += len(b)
                if done > MAX_ZIP:
                    raise LiveryError('download', 'over %d MB: not a livery' % (MAX_ZIP >> 20))
                out.write(b)
                if progress:
                    progress(done, size)
    except LiveryError:
        _rm(tmp)
        raise
    except urllib.error.HTTPError as e:
        _rm(tmp)
        raise LiveryError('page' if e.code == 409 else 'download', 'the server says %s' % e.code)
    except (OSError, ValueError) as e:
        _rm(tmp)
        raise LiveryError('download', str(e))
    kind = archive_kind(tmp)
    if kind in ('rar', '7z'):                        # (ModsCloud's are .rar: made a zip, then installed as any other)
        try:
            to_zip(tmp, path, kind)
        finally:
            _rm(tmp)
        return path
    if kind != 'zip':
        _rm(tmp)
        raise LiveryError('zip', 'what came is not a zip (the file may have been moved: report the link)')
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------- a .rar or .7z (ModsCloud's liveries)

def archive_kind(path):
    """'zip', 'rar', '7z' (by its first bytes) or None."""
    try:
        with open(path, 'rb') as f:
            head = f.read(8)
    except OSError:
        return None
    if head.startswith(b'Rar!\x1a\x07'):
        return 'rar'
    if head.startswith(b'7z\xbc\xaf\x27\x1c'):
        return '7z'
    return 'zip' if zipfile.is_zipfile(path) else None


def tar_exe():
    """Windows' own tar (libarchive's bsdtar, in System32 from Windows 10 1803): it unpacks .rar (RAR5 from Windows 11's)
    and .7z. None away from Windows."""
    p = os.path.join(os.environ.get('SystemRoot') or r'C:\Windows', 'System32', 'tar.exe')
    return p if os.name == 'nt' and os.path.isfile(p) else None


def _unpack(archive, dest):
    """The archive unpacked into dest with Windows' tar (bsdtar keeps every file inside dest: no absolute paths, no
    '..'). Raises LiveryError('unpack') when it can't (no tar; an older Windows 10's can't read RAR5)."""
    exe = tar_exe()
    if not exe:
        raise LiveryError('unpack', "this PC's Windows has no tool to unpack it")
    try:
        r = subprocess.run([exe, '-xf', archive, '-C', dest], capture_output=True, timeout=300,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise LiveryError('unpack', str(e))
    if r.returncode != 0:
        raise LiveryError('unpack', (r.stderr or b'').decode('utf-8', 'replace').strip()[:200] or 'tar failed')


def to_zip(archive, path, kind='rar'):
    """A .rar or .7z made the zip the installer reads (plan, install: every check of theirs on it): unpacked into a
    folder of its own, each file checked to be inside it, the sizes within a livery's, then zipped as path."""
    work = path + '.x'
    shutil.rmtree(work, True)
    os.makedirs(work)
    try:
        _unpack(archive, work)
        root_ = os.path.realpath(work)
        files, total = [], 0
        for dirpath, _dirs, names in os.walk(work):
            for n in names:
                full = os.path.join(dirpath, n)
                if os.path.islink(full) or not os.path.realpath(full).startswith(root_ + os.sep):
                    raise LiveryError('files', 'the %s has a file outside its folder' % kind)
                total += os.path.getsize(full)
                files.append(full)
        if not files:
            raise LiveryError('files', 'the %s holds nothing' % kind)
        if len(files) > MAX_FILES or total > MAX_UNZIPPED:
            raise LiveryError('files', 'too many files for a livery')
        tmp = path + '.zip.part'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:
            for full in files:
                z.write(full, os.path.relpath(full, work).replace(os.sep, '/'))
        os.replace(tmp, path)
    finally:
        shutil.rmtree(work, True)
        _rm(path + '.zip.part')


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


# ---------------------------------------------------------------------- what the zip holds

def clean_name(s, fallback='Livery'):
    """A folder name Windows takes and the game doesn't skip: no \\ / : * ? " < > |, no leading _ or ., at most 60."""
    s = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', ' ', str(s or '')).strip().lstrip('_.').strip().rstrip('. ')
    s = re.sub(r'\s+', ' ', s)[:60].rstrip('. ')
    if s.upper().split('.')[0] in ('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'LPT1', 'LPT2', 'LPT3'):
        s = '_' + s
    return s or fallback


def plan(zip_path, lv, cars=()):
    """The liveries in the zip: [{'src': the folder in the zip ('' its top), 'name': its folder name in the game,
    'car': the car's id, 'hint': the zip's own name for the car's folder or None, 'files': [(member, relative path)]}].
    Raises LiveryError('zip' / 'files')."""
    try:
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise LiveryError('zip', str(e))
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
    files, total = [], 0
    for i in infos:
        p = i.filename.replace('\\', '/')
        parts = [x for x in p.split('/') if x not in ('', '.')]
        if not parts or p.startswith('/') or '..' in parts or any(BAD_NAME.search(x) for x in parts):
            raise LiveryError('files', 'the zip has a file outside its folder (%s)' % i.filename)
        if parts[0] == '__MACOSX' or parts[-1].lower() in JUNK or parts[-1].startswith('._'):
            continue
        # (Windows drops a name's trailing dots and spaces: "run.exe." is run.exe)
        ext = os.path.splitext(parts[-1].rstrip('. '))[1].lower()
        if ext in PROGRAMS:
            raise LiveryError('files', 'the zip holds a program (%s): not installed' % parts[-1])
        if ext in SKIP or ext in DOCS:
            continue
        total += i.file_size
        files.append((i, parts))
    if not files:
        raise LiveryError('files', 'the zip holds no livery files')
    if len(files) > MAX_FILES or total > MAX_UNZIPPED:
        raise LiveryError('files', 'too many files for a livery')
    # the folders that hold files; the zip's top left out when there are folders (a readme, a preview next to them),
    # and a folder inside another's part of it (its textures in a subfolder)
    dirs = sorted({tuple(parts[:-1]) for _i, parts in files})
    if len(dirs) > 1 and () in dirs:
        dirs.remove(())
        files = [(i, parts) for i, parts in files if len(parts) > 1]
    tops = [d for d in dirs if not any(d[:len(o)] == o and d != o for o in dirs)]
    known = [c.get('id') for c in cars or []]
    out = []
    for d in tops:
        name = clean_name(d[-1] if d else lv.get('title'), clean_name(lv.get('title')))
        car, hint = lv.get('car'), None
        if len(d) >= 2:                              # <car>\<name>\ in the zip: a pack for several cars
            for cid in known:
                if same_car(d[-2], _car(cid, cars)):
                    car, hint = cid, d[-2]
                    break
        if len(tops) == 1 and not d:
            name = clean_name(lv.get('title'))
        mine = [(i, '/'.join(parts[len(d):])) for i, parts in files if tuple(parts[:len(d)]) == d]
        out.append({'src': '/'.join(d), 'name': name, 'car': car, 'hint': hint, 'files': mine})
    return out


# ---------------------------------------------------------------------- in and out

def install(lv, zip_path, cars=(), base=None, game=None):
    """The zip's liveries into the game's liveries folder (an older install of this one taken out first), listed as
    ours -> [the folders made]. Raises LiveryError: 'files' (a bad zip), 'full' (25 for that car already)."""
    base = base or root()
    lid = str(lv['id'])
    todo = plan(zip_path, lv, cars)
    if lid in installed():
        uninstall(lid, base)
    # where each goes, and the game's 25 a car checked before anything is written
    adding = {}
    for t in todo:
        t['folder'] = os.path.join(base, car_folder(t['car'], cars, base, game, t['hint']))
        if not os.path.abspath(t['folder']).startswith(os.path.abspath(base) + os.sep):
            raise LiveryError('files', 'a car folder outside the liveries folder')
        adding[t['folder']] = adding.get(t['folder'], 0) + 1
    for folder, n in adding.items():
        have = len(in_use(folder))
        if have + n > PER_CAR:
            car = next((c.get('name') for c in cars or [] if c.get('id') == todo[0]['car']), None) or os.path.basename(folder)
            raise LiveryError('full', 'the game takes %d liveries a car and %s has %d: turn some off or remove them '
                                      'first' % (PER_CAR, car, have))
    made = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            for t in todo:
                os.makedirs(t['folder'], exist_ok=True)
                name, n = t['name'], 2
                while os.path.exists(os.path.join(t['folder'], name)):        # (one of the same name: not ours)
                    name, n = '%s (%d)' % (t['name'], n), n + 1
                tmp = os.path.join(t['folder'], '_acrdaily-%s-%d' % (lid, int(time.time() * 1000) % 100000))   # (skipped)
                os.makedirs(tmp)
                try:
                    for info, rel in t['files']:
                        dest = os.path.join(tmp, *rel.split('/'))
                        if not os.path.abspath(dest).startswith(os.path.abspath(tmp) + os.sep):
                            raise LiveryError('files', 'a file outside its folder')
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with z.open(info) as src, open(dest, 'wb') as out:
                            shutil.copyfileobj(src, out, CHUNK)
                    final = os.path.join(t['folder'], name)
                    os.rename(tmp, final)
                except BaseException:
                    shutil.rmtree(tmp, True)
                    raise
                made.append(final)
    except LiveryError:
        _undo(made)
        raise
    except Exception as e:                           # (anything: an encrypted file, a compression zipfile can't read)
        _undo(made)
        raise LiveryError('files', str(e) or type(e).__name__)
    with _LOCK:
        d = installed()
        d[lid] = {'title': lv.get('title', ''), 'car': lv.get('car', ''), 'dirs': made, 'at': int(time.time())}
        _save(d)
    if os.path.abspath(zip_path) == os.path.abspath(cache_path(lv)):
        _rm(zip_path)                                # (in the game now: the download is not kept)
    return made


def _undo(made):
    for p in made:
        shutil.rmtree(p, True)


def uninstall(livery_id, base=None):
    """The livery's folders out of the game (only what we put there) -> the folders taken out."""
    base = os.path.abspath(base or root())
    with _LOCK:
        d = installed()
        it = d.pop(str(livery_id), None)
        if not it:
            return []
        gone, left = [], []
        for p in it.get('dirs') or []:
            ap = os.path.abspath(p)
            if ap.startswith(base + os.sep) and os.path.isdir(ap):       # (never anything outside the liveries folder)
                shutil.rmtree(ap, True)
                (left if os.path.isdir(ap) else gone).append(p)          # (a file held open: still ours, REMOVE again)
        if left:
            d[str(livery_id)] = dict(it, dirs=left)
        _save(d)
    return gone


def open_folder(base=None):
    """The liveries folder in Explorer (made if there is none yet)."""
    base = base or root()
    os.makedirs(base, exist_ok=True)
    try:
        os.startfile(base)                           # (Windows)
    except (AttributeError, OSError):
        pass
    return base


def size_text(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%.0f %s' if unit in ('B', 'KB') else '%.1f %s') % (n, unit)
        n /= 1024


def stars_text(lv):
    """'★★★★☆ 4.5 · 2 votes' (the average, rounded to whole stars), or 'No votes yet'."""
    if not lv.get('votes'):
        return _('No votes yet')
    n = int(round(float(lv.get('stars') or 0)))
    return '%s%s %.1f · %s' % ('★' * n, '☆' * (5 - n), float(lv['stars']), n_('%d vote', '%d votes', lv['votes']) % lv['votes'])
