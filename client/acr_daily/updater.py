"""One-click update: download the new exe from the server, check it, swap it in and restart.

Windows can't overwrite a running exe, but it can rename one. So:
  1. download to <exe>.new next to the running exe, check it's a Windows program and matches the
     server's SHA-256 (<download url>.sha256, written by build.bat)
  2. rename the running exe to <exe>.old, move <exe>.new into its place (undone if that fails)
  3. start the new exe and quit; the new one deletes <exe>.old when it starts
Settings, results and queued runs live in %APPDATA%, so nothing is lost.
"""
import hashlib
import os
import subprocess
import sys
import time
import urllib.request

from . import USER_AGENT

MIN_SIZE = 1_000_000   # a real build is ~15 MB; anything tiny is an error page


class UpdateError(Exception):
    pass


def can_self_update():
    """Only the built exe can replace itself (running from source: just open the website)."""
    return bool(getattr(sys, 'frozen', False)) and sys.executable.lower().endswith('.exe')


def exe_path():
    return os.path.abspath(sys.executable)


def cleanup_old():
    """Delete the previous version left behind by an update (it may still be closing: retry a little)."""
    if not can_self_update():
        return
    for p in (exe_path() + '.old', exe_path() + '.new'):
        for _ in range(10):
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
    try:
        with _get(url + '.sha256', timeout=15) as r:
            want = r.read().decode('ascii', 'replace').split()[0].strip().lower()
    except Exception as e:
        raise UpdateError('could not get the checksum (%s)' % getattr(e, 'reason', e)) from None
    if len(want) != 64:
        raise UpdateError('the server has no valid checksum for this download')

    dst = exe_path() + '.new'
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
        raise UpdateError('no permission to write next to ACR-Daily.exe; download it from the website instead') from None
    except Exception as e:
        _remove(dst)
        raise UpdateError('download failed (%s)' % getattr(e, 'reason', e)) from None

    with open(dst, 'rb') as f:
        head = f.read(2)
    if head != b'MZ' or os.path.getsize(dst) < MIN_SIZE:
        _remove(dst)
        raise UpdateError('the download is not a Windows program')
    if h.hexdigest() != want:
        _remove(dst)
        raise UpdateError('the download is damaged (checksum mismatch); try again')
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
        raise UpdateError('could not replace the app (%s)' % e) from None
    try:
        os.replace(new, exe)
    except OSError as e:
        os.replace(old, exe)   # put the current version back
        _remove(new)
        raise UpdateError('could not replace the app (%s)' % e) from None
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')   # a fresh one-file app, not a child of this one
    subprocess.Popen([exe, '--updated'], cwd=os.path.dirname(exe), env=env, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _remove(p):
    try:
        os.remove(p)
    except OSError:
        pass
