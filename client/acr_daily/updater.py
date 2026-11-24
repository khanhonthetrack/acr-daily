"""One-click update: download the new exe from the server, check it, swap it in and restart.

Windows can't overwrite a running exe, but it can rename one. So:
  1. download to <exe>.new next to the running exe, check it's a Windows program and matches the
     server's SHA-256 (<download url>.sha256, written by build.bat)
  2. rename the running exe to <exe>.old, move <exe>.new into its place (undone if that fails)
  3. start the new exe and quit; the new one deletes <exe>.old when it starts
Settings, results and queued runs live in %APPDATA%, so nothing is lost.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

from . import USER_AGENT
from .i18n import _

MIN_SIZE = 1_000_000   # a real build is ~15 MB; anything tiny is an error page
# Test builds (four-part versions, 0.1.5.4: GitHub prereleases .github/workflows/dev.yml makes from main on each change of
# the app) look here for a newer one; everyone else follows the server's LATEST_VERSION alone (App.check_update)
RELEASES_API = 'https://api.github.com/repos/khanhonthetrack/acr-daily/releases?per_page=20'


def _ver(v):
    return tuple(int(x) for x in str(v).split('.') if x.isdigit())


def is_test_build(version):
    return len(_ver(version)) == 4


def latest_test_build(timeout=10):
    """The newest test build on GitHub: a prerelease tagged with a four-part version, with the exe (its .sha256 beside
    it, as download() checks). -> (version, the exe's address) or None. Raises OSError / ValueError (offline...)."""
    req = urllib.request.Request(RELEASES_API, headers={'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        releases = json.loads(r.read().decode('utf-8'))
    best = None
    for rel in releases if isinstance(releases, list) else []:
        m = re.fullmatch(r'v(\d+\.\d+\.\d+\.\d+)', str(rel.get('tag_name') or ''))
        if not m or not rel.get('prerelease') or rel.get('draft'):
            continue
        names = {a.get('name'): a.get('browser_download_url') for a in rel.get('assets') or []}
        url = names.get('ACR-Daily.exe')
        if url and 'ACR-Daily.exe.sha256' in names and (best is None or _ver(m.group(1)) > _ver(best[0])):
            best = (m.group(1), url)
    return best


class UpdateError(Exception):
    pass


def can_self_update():
    """Only the built exe can replace itself (running from source: just open the website)."""
    return bool(getattr(sys, 'frozen', False)) and sys.executable.lower().endswith('.exe')


def exe_path():
    return os.path.abspath(sys.executable)


def installed():
    """Is this the installed app (the installer's folder: client/installer.iss, PyInstaller's one-dir with its
    _internal folder beside the exe), not the one-file exe? It updates by running the new installer then."""
    return can_self_update() and os.path.isdir(os.path.join(os.path.dirname(exe_path()), '_internal'))


SETUP = 'ACR-Daily-Setup.exe'


def setup_url(exe_url):
    """The installer's address beside the one-file exe's on the same release."""
    return exe_url.rsplit('/', 1)[0] + '/' + SETUP if '/' in exe_url else SETUP


def download_setup(exe_url, progress=None):
    """The installed app's update: the new installer downloaded to the temp folder and checked (its .sha256 beside it on
    the release). -> its path. Raises UpdateError."""
    import tempfile
    url = setup_url(exe_url)
    dst = os.path.join(tempfile.gettempdir(), 'ACR-Daily-Setup-update.exe')
    return _fetch_checked(url, dst, progress)


def run_setup(path):
    """The new installer started, silently, over this installation (it closes this app if still open and starts the new
    one: installer.iss /UPDATE=1). The caller quits the app right after."""
    subprocess.Popen([path, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', '/UPDATE=1',
                      '/DIR=' + os.path.dirname(exe_path())],
                     close_fds=True, creationflags=0x00000008 | 0x00000200)


def cleanup_old():
    """Delete the previous version left behind by an update (it may still be closing: retry a little)."""
    if not can_self_update():
        return
    for p in (exe_path() + '.old', exe_path() + '.new'):
        for _i in range(10):
            try:
                if os.path.exists(p):
                    os.remove(p)
                break
            except OSError:
                time.sleep(1)


def _get(url, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': USER_AGENT}),
                                  timeout=timeout)


def download(url, progress=None):
    """Download the new exe next to the running one. -> path of the checked file. Raises UpdateError."""
    return _fetch_checked(url, exe_path() + '.new', progress)


def _fetch_checked(url, dst, progress=None):
    """url downloaded to dst, checked against url.sha256 and as a Windows program. -> dst. Raises UpdateError."""
    try:
        with _get(url + '.sha256', timeout=15) as r:
            want = r.read().decode('ascii', 'replace').split()[0].strip().lower()
    except Exception as e:
        raise UpdateError(_('could not get the checksum (%s)') % getattr(e, 'reason', e)) from None
    if len(want) != 64:
        raise UpdateError(_('the server has no valid checksum for this download'))

    h = hashlib.sha256()
    try:
        with _get(url, timeout=60) as r, open(dst, 'wb') as f:
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    except PermissionError:
        raise UpdateError(_('no permission to write next to ACR-Daily.exe; download it from the website instead')) from None
    except Exception as e:
        _remove(dst)
        raise UpdateError(_('download failed (%s)') % getattr(e, 'reason', e)) from None

    with open(dst, 'rb') as f:
        head = f.read(2)
    if head != b'MZ' or os.path.getsize(dst) < MIN_SIZE:
        _remove(dst)
        raise UpdateError(_('the download is not a Windows program'))
    if h.hexdigest() != want:
        _remove(dst)
        raise UpdateError(_('the download is damaged (checksum mismatch); try again'))
    return dst


def install_and_restart(new):
    """Swap the checked exe in and start it. The caller quits the app right after."""
    exe = exe_path()
    old = exe + '.old'
    _remove(old)
    try:
        os.replace(exe, old)
    except OSError as e:
        _remove(new)
        raise UpdateError(_('could not replace the app (%s)') % e) from None
    try:
        os.replace(new, exe)
    except OSError as e:
        os.replace(old, exe)   # put the current version back
        _remove(new)
        raise UpdateError(_('could not replace the app (%s)') % e) from None
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')   # a fresh one-file app, not a child of this one
    subprocess.Popen([exe, '--updated'], cwd=os.path.dirname(exe), env=env, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _remove(p):
    try:
        os.remove(p)
    except OSError:
        pass
