"""WRC Generations' stages made on this PC (the catalogue's `install: 'export'` items, the test builds; communityui.py).

Stage Exporter (Albert Palahi's add-on to Sando Rally's Stage Export Tool 0.3.7, github.com/Faviogames/Stage-Exporter)
turns a WRC Generations stage into Assetto Corsa Rally's from the player's own copies of both games, and keeps the
stages it made in one pack it installs into the game. INSTALL on a stage's row does all of it from here:
  1. WRC Generations' folder (the one the player showed, else Steam's libraries, else the Epic Games launcher's list;
     FIND GAME for one elsewhere) and Sando's tool (its _internal\\wrcg2acr-worker.exe): the folder kept in the
     settings, else looked for in the usual places (find_tool), else the player shows it once (FIND TOOL: its folder, or
     the zip it came in, unpacked here: unpack_tool). Sando no longer offers his tool
     (sandorally.com/stage-export-tool-discontinued), so it is never downloaded: without it these stages can't be made.
  2. Stage Exporter put into the tool, once a version (ensure_addon): GitHub's archive of the catalogue's commit, every
     file under payload/ checked (the catalogue's payloadSha256: payload_digest), copied as its INSTALAR.bat does
     (payload\\_internal and payload\\custom into the tool), custom\\installs.json written with the two games' folders
     (so its setup asks for none), and its setup run (-m wr_setup: a few files from the player's own ACR).
  3. The stage made and the pack installed: wrcg2acr-worker.exe -m wr export <slug> (40 minutes or more), its log read
     for the progress (Progress: the phase, how far, the time left) and kept (logs\\); cancel() stops it, and the pack
     the game had goes back (restore_aside).
REMOVE: -m wr remove <slug> (the pack again without it: a minute or two). The game must be closed for both.
What is in the game is read from its packages as for any tool's stages (community.stage_packs).
"""
import hashlib
import json
import os
import re
import shutil
import string
import subprocess
import time
import urllib.request
import zipfile

from . import USER_AGENT, settings

WORKER = os.path.join('_internal', 'wrcg2acr-worker.exe')
TOOL_EXE = 'Sando-Rally-Stage-Export-Tool.exe'
WRCG_DIR = 'WRC Generations - The FIA WRC Official Game'
STATE = 'acrdaily.json'            # in the tool's custom\: the Stage Exporter this app put in (its payload's digest)
ASIDE = 'wr_previous_'             # Stage Exporter's name for the pack it moves aside while it makes a new one
NEED_FREE = 15 << 30               # (room for a stage's files while it is made: its WRC Generations export and build)
SETTING = 'stageExportTool'        # settings: the tool's folder, once found or shown
WRCG_SETTING = 'stageExportWrcg'   # settings: WRC Generations' folder, when the player showed it (FIND GAME)
OK_SETTING = 'stageExportOk'       # settings: the player said yes to its terms once
_SKIP = {'windows', '$recycle.bin', 'system volume information', 'programdata', 'appdata', 'node_modules',
         'steamapps', '.git', 'recovery', 'perflogs', 'msocache', 'intel', 'amd', 'nvidia'}


class ExportError(Exception):
    """kind: 'download', 'checksum', 'setup', 'export', 'running' (the game is open), 'busy' (Stage Exporter is already
    working), 'space', 'cancelled', 'files' (a zip that can't be unpacked), 'notool' (a zip without the tool in it)."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


# ---------------------------------------------------------------------- the two games and the tool

def wrcg_dir(steam_dirs=None, programdata=None):
    """WRC Generations' folder (in a Steam library, else installed by the Epic Games launcher), or None."""
    from .modinstall import _steam_dirs, libraries
    for steam in (_steam_dirs() if steam_dirs is None else steam_dirs):
        for lib in libraries(steam):
            p = os.path.join(lib, 'steamapps', 'common', WRCG_DIR)
            if os.path.isdir(p):
                return p
    return wrcg_epic(programdata)


def _epic_games(programdata=None):
    """What the Epic Games launcher installed: [(its name, its folder)], from its manifests
    (ProgramData\\Epic\\EpicGamesLauncher\\Data\\Manifests\\*.item) and its list (UnrealEngineLauncher\\LauncherInstalled.dat)."""
    base = programdata or os.environ.get('PROGRAMDATA') or r'C:\ProgramData'
    out = []
    mans = os.path.join(base, 'Epic', 'EpicGamesLauncher', 'Data', 'Manifests')
    try:
        names = sorted(n for n in os.listdir(mans) if n.lower().endswith('.item'))
    except OSError:
        names = []
    for n in names:
        try:
            with open(os.path.join(mans, n), encoding='utf-8-sig', errors='replace') as f:
                d = json.load(f)
            out.append(('%s %s' % (d.get('DisplayName') or '', d.get('AppName') or ''), d.get('InstallLocation') or ''))
        except (OSError, ValueError, AttributeError):
            continue
    try:
        with open(os.path.join(base, 'Epic', 'UnrealEngineLauncher', 'LauncherInstalled.dat'), encoding='utf-8-sig',
                  errors='replace') as f:
            for d in json.load(f).get('InstallationList') or []:
                out.append((d.get('AppName') or '', d.get('InstallLocation') or ''))
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return out


def wrcg_epic(programdata=None):
    """WRC Generations installed by the Epic Games launcher (its name, or its folder's, says so), or None."""
    for name, where in _epic_games(programdata):
        words = re.sub(r'[^a-z]', '', ('%s %s' % (name, os.path.basename(os.path.normpath(where or '.')))).lower())
        if 'wrcgenerations' in words and where and os.path.isdir(where):
            return os.path.normpath(where)
    return None


def looks_like_wrcg(path):
    """Whether a folder the player showed looks like WRC Generations: something in it (or its name) says WRC."""
    if 'wrc' in os.path.basename(os.path.normpath(path)).lower():
        return True
    try:
        return any('wrc' in n.lower() for n in os.listdir(path))
    except OSError:
        return False


def is_tool(path):
    return bool(path) and os.path.isfile(os.path.join(path, WORKER))


def tool_of(path):
    """The tool's folder from one the player picked: itself, its parent (its _internal picked), or the one folder in it
    that has the tool (the folder its zip was unpacked into). None: no tool there."""
    if not path:
        return None
    path = os.path.normpath(path)
    for p in (path, os.path.dirname(path)):
        if is_tool(p):
            return p
    try:
        subs = [os.path.join(path, n) for n in os.listdir(path)]
    except OSError:
        return None
    found = [p for p in subs if is_tool(p)]
    return found[0] if len(found) == 1 else None


def _places():
    """Where a player keeps a tool they downloaded: their own folders (3 deep), each drive's top (2 deep)."""
    home = os.path.expanduser('~')
    out = [(os.path.join(home, n), 3) for n in ('Downloads', 'Desktop', 'Documents')] + [(home, 1), (settings.DIR, 2)]
    if os.name == 'nt':
        out += [(d, 2) for d in _fixed_drives()]
    return out


def _fixed_drives():
    """This PC's own drives (C:\\, D:\\...): no network, card or disc drive, which can keep a look waiting."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        mask = k.GetLogicalDrives()
        roots = ['%s:\\' % d for i, d in enumerate(string.ascii_uppercase) if mask >> i & 1]
        return [r for r in roots if k.GetDriveTypeW(r) == 3]          # DRIVE_FIXED
    except Exception:
        return []


def find_tool(saved=None, places=None, budget=20000):
    """Sando's tool on this PC: the folder kept in the settings, else the first one found in the usual places (its
    _internal\\wrcg2acr-worker.exe; one that has its .exe beside it first). budget: folders looked at, at most."""
    if is_tool(saved):
        return os.path.normpath(saved)
    seen, best = 0, None
    for root, depth in (places if places is not None else _places()):
        stack = [(root, 0)]
        while stack and seen < budget:
            d, n = stack.pop()
            seen += 1
            if is_tool(d):
                if os.path.isfile(os.path.join(d, TOOL_EXE)):
                    return os.path.normpath(d)
                best = best or os.path.normpath(d)
                continue
            if n >= depth:
                continue
            try:
                with os.scandir(d) as it:
                    subs = [e.path for e in it if e.is_dir(follow_symlinks=False)
                            and not e.name.startswith('.') and e.name.lower() not in _SKIP]
            except OSError:
                continue
            stack.extend((s, n + 1) for s in subs)
    return best


def environment(saved=None, search=True, wrcg=None):
    """{'wrcg': its folder or None, 'tool': the tool's folder or None, 'ready': Stage Exporter put in (any version),
    'pack': the slugs of its pack (its custom\\pack.json)}. search: look for the tool beyond the saved folder. wrcg:
    WRC Generations' folder the player showed (FIND GAME), else it is looked for."""
    tool = find_tool(saved) if search else (os.path.normpath(saved) if is_tool(saved) else None)
    game = os.path.normpath(wrcg) if wrcg and os.path.isdir(wrcg) else wrcg_dir()
    return {'wrcg': game, 'tool': tool, 'ready': bool(tool and _state(tool)), 'pack': pack(tool)}


def unpack_tool(zip_path, progress=None):
    """The zip Sando's tool came in (the player's own copy), unpacked into the app's folder (tools\\<its name>) -> the
    tool's folder. Every name must stay inside that folder. Raises ExportError('notool') for a zip without the tool,
    ExportError('files') for one that can't be unpacked."""
    name = re.sub(r'[^\w.() -]', '_', os.path.splitext(os.path.basename(zip_path))[0]) or 'Stage Export Tool'
    dest = os.path.join(settings.DIR, 'tools', name)
    tmp = dest + '.part'
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            worker = WORKER.replace(os.sep, '/').lower()
            if not any(i.filename.replace('\\', '/').lower().endswith(worker) for i in infos):
                raise ExportError('notool', 'no %s in it' % WORKER)
            total, done, root = sum(i.file_size for i in infos), 0, os.path.realpath(tmp)
            for i in infos:
                parts = [p for p in i.filename.replace('\\', '/').split('/') if p]
                target = os.path.realpath(os.path.join(tmp, *parts)) if parts else root
                if os.path.isabs(i.filename) or not (target == root or target.startswith(root + os.sep)):
                    raise ExportError('files', '%s would land outside its folder' % i.filename)
                if i.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(i) as src, open(target, 'wb') as out:
                    for b in iter(lambda: src.read(1 << 20), b''):
                        out.write(b)
                        done += len(b)
                        if progress:
                            progress(done, total)
    except ExportError:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ExportError('files', str(e))
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    found = tool_of(dest)
    if not found:                                          # (deeper in: the one folder that has it)
        found = find_tool(None, [(dest, 3)])
    if not found:
        raise ExportError('notool', 'no %s in it' % WORKER)
    return found


def pack(tool):
    """The slugs of the stages in the tool's pack (Stage Exporter's custom\\pack.json), [] without one."""
    try:
        with open(os.path.join(tool, 'custom', 'pack.json'), encoding='utf-8') as f:
            return [str(s) for s in json.load(f).get('stages') or []]
    except (OSError, ValueError, TypeError, AttributeError):
        return []


def running(exe='wrcg2acr-worker.exe'):
    """Whether Stage Exporter (its worker) is working on this PC: from here, or its own window (False away from Windows)."""
    try:
        from .modinstall import _game_pids, _kernel32
        return bool(_game_pids(_kernel32(), exe))
    except Exception:
        return False


def space_short(tool):
    """Bytes short of NEED_FREE on the tool's drive (0: room enough, or not known)."""
    try:
        return max(0, NEED_FREE - shutil.disk_usage(tool).free)
    except OSError:
        return 0


# ---------------------------------------------------------------------- Stage Exporter, put into the tool

def _state(tool):
    try:
        with open(os.path.join(tool, 'custom', STATE), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def addon_ready(tool, ex):
    st = _state(tool) or {}
    return st.get('payload') == ex['payloadSha256'] and os.path.isfile(os.path.join(tool, 'custom', 'installs.json'))


def _payload(z):
    """The files under payload/ in GitHub's archive (its one top folder left out): {path: ZipInfo}."""
    out = {}
    for i in z.infolist():
        if i.is_dir():
            continue
        parts = i.filename.replace('\\', '/').split('/')
        if len(parts) > 2 and parts[1] == 'payload' and '..' not in parts and all(parts[1:]):
            out['/'.join(parts[1:])] = i
    return out


def payload_digest(files):
    """SHA-256 of the lines "<path>\\t<SHA-256 of the file>\\n" of every file, sorted by path (the catalogue's
    payloadSha256). files: {path: bytes}."""
    return hashlib.sha256(''.join('%s\t%s\n' % (p, hashlib.sha256(files[p]).hexdigest())
                                  for p in sorted(files)).encode()).hexdigest()


def fetch_addon(ex, timeout=60):
    """GitHub's archive of Stage Exporter at the catalogue's commit, every payload file checked -> {path: bytes}.
    Raises ExportError('download' / 'checksum')."""
    if not re.fullmatch(r'https://codeload\.github\.com/[\w.-]+/[\w.-]+/zip/[0-9a-f]{40}', ex.get('url') or ''):
        raise ExportError('checksum', 'not an archive of a commit: %s' % ex.get('url'))
    path = os.path.join(settings.DIR, 'community', 'stage-exporter-%s.zip' % ex['commit'][:12])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(ex['url'], headers={'User-Agent': USER_AGENT}),
                                    timeout=timeout) as r, open(path + '.part', 'wb') as out:
            shutil.copyfileobj(r, out)
        os.replace(path + '.part', path)
        with zipfile.ZipFile(path) as z:
            files = {p: z.read(i) for p, i in _payload(z).items()}
    except (OSError, zipfile.BadZipFile) as e:
        raise ExportError('download', str(e))
    finally:
        for p in (path, path + '.part'):
            try:
                os.remove(p)
            except OSError:
                pass
    if len(files) != int(ex.get('files') or len(files)) or payload_digest(files) != ex['payloadSha256']:
        raise ExportError('checksum', "Stage Exporter's files are not the expected ones")
    return files


def _env():
    from .community import child_env
    return child_env({'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'})


def _command(tool):
    """How the tool's worker is started (tests: a script of their own)."""
    return [os.path.join(tool, WORKER)]


def _flags():
    return 0x08000000 if os.name == 'nt' else 0          # CREATE_NO_WINDOW: no console window over the app


def install_addon(tool, ex, files, game, wrcg, log=None):
    """Stage Exporter's files into the tool (payload\\_internal -> _internal, payload\\custom -> custom, as its
    INSTALAR.bat), the two games' folders for it (custom\\installs.json), and its setup run. Raises ExportError('setup')."""
    root = os.path.realpath(tool)
    for p, data in files.items():
        rel = p.split('/', 1)[1]                          # payload/_internal/wr.py -> _internal/wr.py
        if not rel.startswith(('_internal/', 'custom/')):
            continue
        target = os.path.realpath(os.path.join(root, *rel.split('/')))
        if not target.startswith(root + os.sep):
            raise ExportError('setup', '%s would land outside the tool' % p)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as f:
            f.write(data)
    os.makedirs(os.path.join(tool, 'custom'), exist_ok=True)
    with open(os.path.join(tool, 'custom', 'installs.json'), 'w', encoding='utf-8') as f:
        json.dump({'wrcg': wrcg.replace('\\', '/'), 'acr': game.replace('\\', '/')}, f, indent=1)
    lines = []
    try:
        r = subprocess.run([*_command(tool), '-m', 'wr_setup'], cwd=tool, env=_env(),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           creationflags=_flags(), timeout=1800)
        lines = r.stdout.decode('utf-8', 'replace').splitlines()
        rc = r.returncode
    except (OSError, subprocess.SubprocessError) as e:
        lines, rc = [str(e)], -1
    for line in lines:
        if log:
            log(line)
    if rc != 0:
        raise ExportError('setup', (lines or ['exit %s' % rc])[-1])
    with open(os.path.join(tool, 'custom', STATE), 'w', encoding='utf-8') as f:
        json.dump({'version': ex.get('version'), 'commit': ex.get('commit'), 'payload': ex['payloadSha256'],
                   'at': int(time.time())}, f, indent=1)


def ensure_addon(tool, ex, game, wrcg, say=None, log=None):
    """Stage Exporter in the tool, at the catalogue's version (fetched and set up when it isn't). say(phase)."""
    if addon_ready(tool, ex):
        return False
    if say:
        say('get')
    files = fetch_addon(ex)
    if say:
        say('setup')
    install_addon(tool, ex, files, game, wrcg, log)
    return True


# ---------------------------------------------------------------------- making and removing a stage

class Progress:
    """How far a run is, from Stage Exporter's log (as its own window reads it): phase ('prep', 'wrcg': from WRC
    Generations, 'build': for Assetto Corsa Rally, 'pack': the pack written and installed), fraction (0-1), eta (s)."""
    WEIGHTS = (('prep', 2.0), ('wrcg', 25.0), ('build', 62.0), ('pack', 8.0))
    WRCG_STEPS = (('export_stage.py', 0.05), ('tools.wrcg.terrain export', 0.35), ('tools.wrcg.textures export', 0.5),
                  ('ittiri_terrain adjust', 0.65), ('vegetation_replay', 0.75), ('tools.wrcg.vegetation ', 0.75))
    BUILD_STEPS = (('collision container', 0.05), ('level shell, gameplay, marshal', 0.12),
                   ('road layers + terrain tiles', 0.55), ('props', 0.72), ('vegetation', 0.80),
                   ('dressing, cloth, decals, water', 0.85), ('level save', 0.97), ('pacenotes', 1.0))

    def __init__(self, slug, now=None):
        self.slug, self.t0 = slug, time.time() if now is None else now
        self.f = {k: 0.0 for k, _w in self.WEIGHTS}
        self.phase, self.failed = 'prep', False

    def _set(self, phase, v):
        if v > self.f[phase]:
            self.f[phase] = v
        if self.f[phase] > 0:
            self.phase = phase

    def feed(self, line):
        l = line.strip()
        if l.startswith('WRCG files:'):
            self._set('prep', 1.0)
        m = re.match(r'^\[(\w+)\]\s*(.*)$', l)
        if m and m.group(1) == self.slug:
            rest = m.group(2)
            if 'WRCG export kept' in rest or 'WRCG export done' in rest:
                self._set('wrcg', 1.0)
            elif rest.startswith('WRCG export'):
                self._set('prep', 1.0)
                self._set('wrcg', 0.02)
            for key, frac in self.WRCG_STEPS:
                if key in rest:
                    self._set('wrcg', frac)
        if 'building the ACR pack' in l:
            self._set('prep', 1.0)
            self._set('wrcg', 1.0)
        if re.match(r'^building %s \(' % re.escape(self.slug), l):
            self._set('build', 0.02)
        m = re.search(r'\[\w+\] step (.+?): [\d.]+ s', l)
        if m and self.f['wrcg'] >= 1.0:
            for key, frac in self.BUILD_STEPS:
                if m.group(1) == key:
                    self._set('build', frac)
        if re.search(r'\[%s\] built in' % re.escape(self.slug), l):
            self._set('build', 1.0)
        for key, frac in (('locations:', 0.1), ('menu images', 0.1), ('tools.acrmod.install uninstall', 0.3),
                          ('tools.acrmod.install install', 0.5), ('installed into', 0.95), ('installed wrcg_stages', 0.95),
                          ('pack:', 1.0)):
            if l.startswith(key) or (' ' in key and key in l):
                self._set('wrcg', 1.0)
                self._set('build', 1.0)
                self._set('pack', frac)
        if 'stage build failed' in l or l.startswith('ERROR') or l.startswith('Traceback'):
            self.failed = True

    def fraction(self):
        tot = sum(w for _k, w in self.WEIGHTS)
        return sum(w * self.f[k] for k, w in self.WEIGHTS) / tot

    def eta(self, now=None):
        p, el = self.fraction(), (time.time() if now is None else now) - self.t0
        return el * (1.0 - p) / p if p > 0.04 else None


RUN = 'stage-export-run.json'      # in the app's folder: the run going on ({args, log, pid, at}), for an app opened again


class Job:
    """A run of Stage Exporter (export <slug> / remove <slug>). Its log goes straight to logs\\stage-export-<time>.log
    (not through this app: closed halfway, the app leaves it working, and an app opened again picks it up: attach),
    read as it grows for on_line(line). wait() -> True when it went through. cancel() stops it (its processes too)."""

    def __init__(self, tool=None, args=(), on_line=None, attach=None):
        self.on_line, self.cancelled, self.lines, self.proc = on_line, False, [], None
        if attach:                                        # (a run this app started before it was closed)
            self.args, self.log, self.pid = list(attach['args']), attach['log'], attach.get('pid')
            return
        self.args = list(args)
        logs = os.path.join(settings.DIR, 'logs')
        os.makedirs(logs, exist_ok=True)
        self.log = os.path.join(logs, 'stage-export-%s.log' % time.strftime('%Y%m%d-%H%M%S'))
        with open(self.log, 'ab') as logf:
            logf.write(('wr %s\n' % ' '.join(self.args)).encode())
            logf.flush()
            self.proc = subprocess.Popen([*_command(tool), '-m', 'wr', *self.args], cwd=tool, env=_env(),
                                         stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                                         creationflags=_flags())
        self.pid = self.proc.pid
        _write_run({'args': self.args, 'log': self.log, 'pid': self.pid, 'at': int(time.time())})

    def _alive(self):
        return self.proc.poll() is None if self.proc is not None else running()

    def wait(self, poll=0.5):
        pos, rest = 0, b''
        while True:
            alive = self._alive()
            try:
                with open(self.log, 'rb') as f:
                    f.seek(pos)
                    data = f.read()
            except OSError:
                data = b''
            pos += len(data)
            *done, rest = (rest + data).split(b'\n')
            for raw in done:
                self._line(raw)
            if not alive:
                break
            time.sleep(poll)
        if rest:
            self._line(rest)
        _write_run(None)
        if self.proc is not None:
            ok = self.proc.wait() == 0
        else:                                             # (attached: its log says how it ended)
            ok = any(l.startswith(('pack:', 'pack removed from the game')) for l in self.lines)
        return ok and not self.cancelled

    def _line(self, raw):
        line = raw.decode('utf-8', 'replace').rstrip('\r')
        self.lines = (self.lines + [line])[-40:]
        if self.on_line:
            self.on_line(line)

    def cancel(self):
        self.cancelled = True
        if self.proc is not None and self.proc.poll() is not None:
            return
        if os.name == 'nt':                               # (its own processes too: the pipeline starts several)
            who = ['/PID', str(self.pid)] if self.pid else ['/IM', 'wrcg2acr-worker.exe']
            subprocess.run(['taskkill', *who, '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=_flags())
        elif self.proc is not None:
            self.proc.kill()

    def last(self, n=3):
        return [l for l in self.lines if l.strip() and not l.startswith('wr ')][-n:]


def _write_run(d):
    path = os.path.join(settings.DIR, RUN)
    try:
        if d is None:
            os.remove(path)
        else:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(d, f)
    except OSError:
        pass


def current_run():
    """The run this app started that is still working (the app was closed and opened again): {args, log, pid}, else
    None (a run that ended meanwhile: forgotten)."""
    try:
        with open(os.path.join(settings.DIR, RUN), encoding='utf-8') as f:
            d = json.load(f)
        assert isinstance(d.get('args'), list) and os.path.isfile(d['log'])
    except (OSError, ValueError, AssertionError, AttributeError, KeyError, TypeError):
        return None
    if not running():
        _write_run(None)
        return None
    return d


def restore_aside(game):
    """The pack Stage Exporter moved aside while it made a new one, back in its place (a run stopped halfway: the game
    keeps the stages it had). -> the names put back."""
    paks = os.path.join(game, 'acr', 'Content', 'Paks')
    back = []
    try:
        names = os.listdir(paks)
    except OSError:
        return back
    for n in names:
        if n.startswith(ASIDE) and n.endswith('.bak'):
            orig = n[len(ASIDE):-len('.bak')]
            if orig and not os.path.exists(os.path.join(paks, orig)):
                try:
                    os.rename(os.path.join(paks, n), os.path.join(paks, orig))
                    back.append(orig)
                except OSError:
                    pass
    return back


def start(tool, args, on_line=None):
    """A run started (export <slug> / remove <slug>) -> its Job. Raises ExportError('busy') when Stage Exporter is
    already working (its own window, or a run this app started before it was closed)."""
    if running():
        raise ExportError('busy')
    try:
        return Job(tool, args, on_line)
    except OSError as e:
        raise ExportError('export', str(e))
