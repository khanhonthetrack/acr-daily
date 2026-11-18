"""One stage list for every set of stages in the game (the COMMUNITY page's TRACKS, communityui.py).

The game lists its stages in nine tables (TABLES: levels, tracks, variants, locations, their pictures, the Rally
Weekend calendars, the loading screens). Every set of stages carries its own copy of them, the game's rows with its
own added: ACR DAILY London's and Lousã's lists (their zz_acrxs_*registry_P), Stage Exporter's WRC Generations pack
and our calendars for it (stagecalendars.py), Sando Rally's list (his Stage Manager's pakchunk99-SandoRegistry_*_P).
The game loads one copy of each table, so on their own only one set's stages show (stageswitch.py parks the others).

With two sets or more in the game, the app makes one more copy, NAME, in ~mods: the game's own tables with every
set's rows added (no set changes a row of the game's: they only add theirs). The game loads it over the sets'
copies: a container whose name ends _<n>_P comes after the plain _P ones and the lower numbers (Sando's list is
_2_P), so _9_P. It is made on the player's PC with Sando's own tools (tools(): retoc, UaTool, the mappings, from the
Stage Export Tool or Sando's stage download), from the game's own files and the sets' tables as they are in the game:
nothing of any set is changed (their files stay where they are, only read), and it never leaves the PC. A set
added, taken out or made again makes it stale (signature): it is made again, or taken out when it can't be.
"""
import json
import os
import re
import shutil
import subprocess

from . import settings

NAME = 'zz_acrdaily_stagelist_9_P'
EXTS = ('pak', 'ucas', 'utoc')
OFF = '.acrdaily-off'
# the tables (under /Game/Data, the game's acr/Content/Data): the stage list
TABLES = ('Database/Main/Common/DT_Levels', 'Database/Main/Common/DT_RallyWeekendCalendarPreset',
          'Database/Main/TrackSelection/DT_Tracks', 'Database/Main/TrackSelection/DT_TracksLocations',
          'Database/Main/TrackSelection/DT_TracksLocationsBackgrounds',
          'Database/Main/TrackSelection/DT_TracksLocationsLogos', 'Database/Main/TrackSelection/DT_TracksTextures',
          'Database/Main/TrackSelection/DT_TracksVariants', 'UI/Datatable/DT_LoadingScreen')
FILTERS = ('Database/Main/', '/DT_LoadingScreen.')  # (retoc's: parts of the paths of the files it reads)
# the game builds whose tables Sando's mappings (acr_stage.usmap) read right: on another the list isn't made (the sets
# then show one at a time) until one for it is checked
BUILDS = ('25170642',)
SETTING = 'stageList'                            # settings: the containers the list was made from
# The sets whose rows come first in the list: ACR Extra Stages' (London, Lousã: AcrXs). After Stage Exporter's rows,
# their Rally Weekends had no tyres to allocate and the game crashed on the tyre allocation's J (18 Nov 2026: London
# and Lousã, with the very same rows; why is not known). First, they and every other set's after them work (London,
# Lousã and Arena Panzerplatte checked in a Rally Weekend). The others keep the game's own load order.
FIRST = ('acrdaily', 'lousa')
WORK = 'ACRDaily-build'
_STOCK = re.compile(r'^(global|pakchunk\d+(optional)?-windows)$', re.I)


class ListError(Exception):
    """kind: 'tools' (Sando's tools aren't on this PC), 'build' (a step failed: its words)."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


# ---------------------------------------------------------------------- which containers carry the tables

_M = (1 << 64) - 1
_K0, _K1, _K2, _KMUL = 0xc3a5c85c97cb3127, 0xb492b66fbe98f273, 0x9ae16a3b2f90404f, 0x9ddfea08eb382d69


def _f64(s, i):
    return int.from_bytes(s[i:i + 8], 'little')


def _rot(v, n):
    return v if n == 0 else ((v >> n) | (v << (64 - n))) & _M


def _h16(u, v, mul=_KMUL):
    a = ((u ^ v) * mul) & _M
    a ^= a >> 47
    b = ((v ^ a) * mul) & _M
    b ^= b >> 47
    return (b * mul) & _M


def _weak(s, i, a, b):
    w, x, y, z = _f64(s, i), _f64(s, i + 8), _f64(s, i + 16), _f64(s, i + 24)
    a = (a + w) & _M
    b = _rot((b + a + z) & _M, 21)
    c = a
    a = (a + x + y) & _M
    b = (b + _rot(a, 44)) & _M
    return (a + z) & _M, (b + c) & _M


def cityhash64(s):
    """CityHash64 (v1.1, as Unreal Engine has it) of bytes longer than 64 (a package's name is: package_id)."""
    n = len(s)
    if n <= 64:
        raise ValueError('only names longer than 64 bytes')
    x = _f64(s, n - 40)
    y = (_f64(s, n - 16) + _f64(s, n - 56)) & _M
    z = _h16((_f64(s, n - 48) + n) & _M, _f64(s, n - 24))
    v = _weak(s, n - 64, n, z)
    w = _weak(s, n - 32, (y + _K1) & _M, x)
    x = (x * _K1 + _f64(s, 0)) & _M
    left, i = (n - 1) & ~63, 0
    while True:
        x = (_rot((x + y + v[0] + _f64(s, i + 8)) & _M, 37) * _K1) & _M
        y = (_rot((y + v[1] + _f64(s, i + 48)) & _M, 42) * _K1) & _M
        x ^= w[1]
        y = (y + v[0] + _f64(s, i + 40)) & _M
        z = (_rot((z + w[0]) & _M, 33) * _K1) & _M
        v = _weak(s, i, (v[1] * _K1) & _M, (x + w[0]) & _M)
        w = _weak(s, i + 32, (z + w[1]) & _M, (y + _f64(s, i + 16)) & _M)
        z, x = x, z
        i += 64
        left -= 64
        if left == 0:
            break
    return _h16((_h16(v[0], w[0]) + (y ^ (y >> 47)) * _K1 + z) & _M, (_h16(v[1], w[1]) + x) & _M)


def package_id(name):
    """A package's id in the game's containers (FPackageId: CityHash64 of its name, lower case, UTF-16)."""
    return cityhash64(name.lower().encode('utf-16-le'))


# a table's data in a container's index: its package id, then chunk 0 of type 1 (ExportBundleData)
_CHUNKS = {t: package_id('/Game/Data/' + t).to_bytes(8, 'little') + b'\x00\x00\x00\x01' for t in TABLES}


def _paks(game):
    return os.path.join(game, 'acr', 'Content', 'Paks')


def _folders(game):
    return [_paks(game), os.path.join(_paks(game), '~mods')]


def pak_order(stem):
    """Where the game loads a container among the others (a higher one wins a table both have): as Unreal does it,
    a patch (_P) above the rest, by its number (_<n>_P) when it has one."""
    base = os.path.basename(stem)
    order = 4 if base.lower().startswith('acr-') else 3
    if base.endswith('_P'):
        m = re.search(r'_(\d+)_P$', base)
        n = int(m.group(1)) if m else 0
        order += 100 * (n + 1 if n >= 1 else 1)
    return order


def carriers(game):
    """The containers in the game (not parked) that carry the stage list's tables, other than the game's own and
    ours: [(path without extension, [its tables])], in the order the game loads them (the last wins)."""
    out = []
    for d in _folders(game):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if not n.lower().endswith('.utoc'):
                continue
            stem = n[:-len('.utoc')]
            if _STOCK.match(stem) or stem.lower() == NAME.lower():
                continue
            try:
                with open(os.path.join(d, n), 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            have = [t for t in TABLES if _CHUNKS[t] in data]
            if have:
                out.append((os.path.join(d, stem), have))
    out.sort(key=lambda c: (pak_order(c[0]), c[0].lower()))
    return out


def _stock(game):
    """The game's own containers that carry the tables (in its Paks)."""
    out = []
    try:
        names = os.listdir(_paks(game))
    except OSError:
        return out
    for n in names:
        if n.lower().endswith('.utoc') and _STOCK.match(n[:-len('.utoc')]) and not n.lower().startswith('global'):
            try:
                with open(os.path.join(_paks(game), n), 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            if any(c in data for c in _CHUNKS.values()):
                out.append(os.path.join(_paks(game), n[:-len('.utoc')]))
    return sorted(out)


def group_of(stem):
    """The set a container is part of (stageswitch's groups; any other container a set of its own)."""
    from . import stageswitch
    base = os.path.basename(stem) + '.utoc'
    g = stageswitch._group_of(base)
    if g:
        return g
    try:
        with open(stem + '.utoc', 'rb') as f:
            data = f.read()
    except OSError:
        data = b''
    if b'DT_PacenoteSando' in data or b'SandoRegistry' in base.encode():
        return 'sando'
    return 'other:' + os.path.basename(stem).lower()


def sets(game, found=None):
    """The sets whose stage lists are in the game: [group], in the order the game loads them."""
    out = []
    for stem, _have in (carriers(game) if found is None else found):
        g = group_of(stem)
        if g not in out:
            out.append(g)
    return out


def supported(game):
    """The game's build is one the list can be made for (BUILDS)."""
    from .community import game_build
    return game_build(game) in BUILDS


def needed(game, found=None):
    """Two sets or more in the game, on a build it can be made for: the list is needed (one set shows its own)."""
    return supported(game) and len(sets(game, found)) >= 2


def signature(game, found=None):
    """What the list is made from (the sets' containers' and the game's own index sizes and times), or None without
    the game."""
    try:
        own = sorted(os.path.join(_paks(game), n[:-len('.utoc')]) for n in os.listdir(_paks(game))
                     if n.lower().endswith('.utoc') and _STOCK.match(n[:-len('.utoc')]))
    except OSError:
        return None
    parts = []
    for stem, exts in [(s, ('utoc',)) for s in own] + [(c[0], ('utoc', 'ucas')) for c in
                                                       (carriers(game) if found is None else found)]:
        for x in exts:
            try:
                st = os.stat(stem + '.' + x)
            except OSError:
                return None
            parts.append('%s.%s:%d-%d' % (os.path.basename(stem).lower(), x, st.st_size, int(st.st_mtime)))
    return ';'.join(parts)


def present(game):
    """Our list is in the game (shown)."""
    return os.path.isfile(os.path.join(_paks(game), '~mods', NAME + '.utoc'))


def stale(game):
    """Our list is in the game but made from other sets (or none is needed now)."""
    return present(game) and (settings.load().get(SETTING) or None) != signature(game)


def remove(game):
    """Our list out of the game (shown or parked). -> whether it was there."""
    gone = False
    for x in EXTS:
        for n in (NAME + '.' + x, NAME + '.' + x + OFF):
            try:
                os.remove(os.path.join(_paks(game), '~mods', n))
                gone = True
            except OSError:
                pass
    s = settings.load()
    if s.pop(SETTING, None) is not None:
        settings.save(s)
    return gone


def tools(tool=None):
    """Sando's tools ({retoc, uatool, usmap}): in the Stage Export Tool (tool: its folder), else in a stage download of
    his this app has (its files\\bin), else None."""
    places = [os.path.join(tool, 'bin')] if tool else []
    try:
        community = os.path.join(settings.DIR, 'community')
        places += [os.path.join(community, n, 'files', 'bin') for n in sorted(os.listdir(community))]
    except OSError:
        pass
    for b in places:
        t = {'retoc': os.path.join(b, 'retoc', 'retoc.exe'), 'uatool': os.path.join(b, 'uatool', 'UaTool.exe'),
             'usmap': os.path.join(b, 'acr_stage.usmap')}
        if all(os.path.isfile(p) for p in t.values()):
            return t
    return None


# ---------------------------------------------------------------------- the tables put together (UaTool's JSON)

def _rows(asset):
    ex = [e for e in asset['Exports'] if isinstance(e.get('Table'), dict)]
    if len(ex) != 1:
        raise ListError('build', 'a table that is not one table')
    return ex[0]['Table']['Data']


def _same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _imports_used(x):
    """Whether a row refers to an import (an object property holding a negative package index): its copy's imports
    must then be the game's. Texts name their string table by key, pictures their package by path: neither does."""
    if isinstance(x, dict):
        if str(x.get('$type', '')).startswith('UAssetAPI.PropertyTypes.Objects.ObjectPropertyData') and \
                isinstance(x.get('Value'), int) and x['Value'] < 0:
            return True
        return any(_imports_used(v) for v in x.values())
    if isinstance(x, list):
        return any(_imports_used(v) for v in x)
    return False


def merge(stock, theirs):
    """The game's table (stock, UaTool's JSON) with the rows each set adds or changes (theirs: [(the set's name, its
    copy)], in the order the game loads them: a later one wins a row both have). A row brought that refers to an
    import needs its copy's imports to be the game's (the sets' rows name their pictures by path and their texts'
    string tables by key: none does so far; a copy read on its own can't name an import of another package of the
    game's, which reads back as /Engine/UnknownPackage). -> (the table, {set: [rows it brought]}, [rows two sets both
    have, the later one's kept])."""
    base = {r['Name']: r for r in _rows(stock)}
    rows = _rows(stock)
    by, brought, clash = {}, {}, []
    for who, asset in theirs:
        same = _same(asset.get('Imports'), stock.get('Imports'))
        for r in _rows(asset):
            name = r['Name']
            if name in base and _same(r, base[name]):
                continue                                 # (the game's own row, as it is)
            if not same and _imports_used(r):
                raise ListError('build', "%s's %s refers to other packages" % (who, _table_name(stock)))
            at = next((i for i, x in enumerate(rows) if x['Name'] == name), None)
            if at is None:
                rows.append(r)
            else:
                if by.get(name, who) != who and not _same(r, rows[at]):
                    clash.append(name)
                rows[at] = r
            if by.get(name) != who:
                brought.setdefault(who, []).append(name)
            by[name] = who
        _names(stock, asset)
    return stock, brought, clash


def _table_name(asset):
    return next((n for n in asset.get('NameMap') or [] if n.startswith('DT_')), 'table')


def _names(stock, asset):
    """The names a set's copy has that the game's hasn't, put in the game's copy's name map among the names its data
    uses (the first NamesReferencedFromExportDataCount: a packed package keeps only those, stagecalendars._name)."""
    have = set(stock['NameMap'])
    at = int(stock.get('NamesReferencedFromExportDataCount') or len(stock['NameMap']))
    for n in asset['NameMap']:
        if n not in have:
            stock['NameMap'].insert(at, n)
            at += 1
            have.add(n)
    if 'NamesReferencedFromExportDataCount' in stock:
        stock['NamesReferencedFromExportDataCount'] = at
    for g in stock.get('Generations') or []:
        if isinstance(g, dict) and 'NameCount' in g:
            g['NameCount'] = len(stock['NameMap'])


# ---------------------------------------------------------------------- made on the PC

def _run(args, what):
    r = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       creationflags=0x08000000 if os.name == 'nt' else 0, timeout=900)
    if r.returncode != 0:
        tail = r.stdout.decode('utf-8', 'replace').strip().splitlines()[-2:]
        raise ListError('build', '%s failed: %s' % (what, ' / '.join(tail) or 'exit %d' % r.returncode))


def work_dir(game):
    """Where it is made: the top of the game's drive (the containers are linked there, not copied: the same drive)."""
    drive = os.path.splitdrive(os.path.abspath(game))[0] or os.path.abspath(os.sep)
    return os.path.join(drive + os.sep, WORK, 'stagelist')


def _link(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)                           # (no hard links on this drive: a copy)


def _read(t, run, game, stems, out):
    """The tables of these containers (linked into a folder of their own with the game's global one) as legacy
    files under out."""
    src = out + '-paks'
    os.makedirs(src)
    for n in os.listdir(_paks(game)):
        if n.lower().startswith('global.'):
            shutil.copy2(os.path.join(_paks(game), n), os.path.join(src, n))
    for stem in stems:
        for x in EXTS:
            if os.path.isfile(stem + '.' + x):
                _link(stem + '.' + x, os.path.join(src, os.path.basename(stem) + '.' + x))
    for f in FILTERS:
        run([t['retoc'], 'to-legacy', '--version', 'UE5_6', '--no-shaders', '--filter', f, src, out],
            'reading %s' % os.path.basename(stems[0]))


def build(game, tool=None, run=None):
    """The list made for the sets in the game now and put in ~mods (None: fewer than two sets, and any list of ours
    taken out). -> {set: number of rows it brought}. Raises ListError ('tools', 'build'): then no list of ours is
    left in the game."""
    run = run or _run
    remove(game)                                         # (ours out first: the sets' copies are read as they are)
    found = carriers(game)
    if not needed(game, found):
        return None
    t = tools(tool)
    if not t:
        raise ListError('tools', "Sando's tools aren't on this PC")
    work = work_dir(game)
    shutil.rmtree(work, ignore_errors=True)
    try:
        sig = signature(game, found)
        stock = _stock(game)
        if not stock:
            raise ListError('build', "the game's stage list isn't where it should be")
        _read(t, run, game, stock, os.path.join(work, 'stock'))
        legacy = []
        found = sorted(found, key=lambda x: FIRST.index(group_of(x[0])) if group_of(x[0]) in FIRST else len(FIRST))
        for i, (stem, _have) in enumerate(found):
            out = os.path.join(work, 'c%d' % i)
            _read(t, run, game, [stem], out)
            legacy.append((group_of(stem), out))

        def load(root, table, key):
            src = os.path.join(root, 'acr', 'Content', 'Data', *table.split('/')) + '.uasset'
            if not os.path.isfile(src):
                return None
            dst = os.path.join(work, 'json', key + '.json')
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            run([t['uatool'], 'dumpjson', src, t['usmap'], dst], 'reading %s' % table.rsplit('/', 1)[-1])
            with open(dst, encoding='utf-8') as f:
                return json.load(f)

        mod, counts = os.path.join(work, 'mod'), {}
        for k, table in enumerate(TABLES):
            theirs = []
            for i, (who, root) in enumerate(legacy):
                j = load(root, table, 'c%d-%d' % (i, k))
                if j is not None:
                    theirs.append((who, j))
            if not theirs:
                continue
            base = load(os.path.join(work, 'stock'), table, 'stock-%d' % k)
            if base is None:
                raise ListError('build', "the game's %s isn't where it should be" % table.rsplit('/', 1)[-1])
            merged, brought, _clash = merge(base, theirs)
            for who, names in brought.items():
                counts[who] = counts.get(who, 0) + len(names)
            jp = os.path.join(work, 'json', 'merged-%d.json' % k)
            with open(jp, 'w', encoding='utf-8') as f:
                json.dump(merged, f)
            dst = os.path.join(mod, 'acr', 'Content', 'Data', *table.split('/')) + '.uasset'
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            run([t['uatool'], 'fromjson', jp, t['usmap'], dst], 'writing %s' % table.rsplit('/', 1)[-1])
        out = os.path.join(work, 'out')
        os.makedirs(out)
        run([t['retoc'], 'to-zen', '--no-parallel', '--version', 'UE5_6', mod, os.path.join(out, NAME + '.utoc')], 'packing')
        mods = os.path.join(_paks(game), '~mods')
        os.makedirs(mods, exist_ok=True)
        for x in EXTS:
            shutil.move(os.path.join(out, NAME + '.' + x), os.path.join(mods, NAME + '.' + x))
        s = settings.load()
        s[SETTING] = sig
        settings.save(s)
        return counts
    except ListError:
        remove(game)
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError) as e:
        remove(game)
        raise ListError('build', str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(work))
        except OSError:
            pass
