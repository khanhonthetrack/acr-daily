"""Which stages the game shows: London's, Lousã's, WRC Generations' or Sando Rally's (communityui.py's TRACKS page; the
test builds).

The game has one stage list, so only one set of stages shows at a time on its own (community.py): with Sando's tools on
the PC the app makes one list for all of them (stagelist.py) and every set stays in the game; without, this switch
shows one set and parks the others. Switching between ACR Daily's
London (its zz_acrxs_* containers in ~mods), the WRC Generations stages (Stage Exporter's pakchunk99-wrcg*
pack: in ~mods from its 1.5, in Paks before) and Sando Rally's (Chile BioBio: his stage containers, pakchunk99-<pack>_P, whose index names
DT_PacenoteSando..., and the stage list his Stage Manager builds: a container of no other set's that carries the
game's DT_TracksVariants) never deletes or rebuilds anything: the sets not shown are parked, their files renamed to
<name>.acrdaily-off, which the game doesn't load; showing one renames its files back. A second either way, the game
closed (it keeps its files open). Stage Exporter's builds stay where they are, so a stage made once (about 40 minutes)
is never made again for a switch; Sando's files are only renamed, never changed, and are back as they were before his
manager is opened.

Stage Exporter wants no other stage mod in Paks while it makes a stage (it reads the folder as the game's own): the
other sets are parked for that too (park_others).
"""
import os
import re

OFF = '.acrdaily-off'
_EXT = re.compile(r'\.(pak|utoc|ucas)$', re.I)
# a group's files by name: (the folders under Paks: '' is Paks itself, the names they start with); a file is the
# group's whose start fits it best (Lousã's zz_acrxs_lousa_* and its stage aren't London's zz_acrxs_*); Sando's by what
# is in them (_sando). Stage Exporter puts its pack in ~mods from its 1.5 (and moves 1.0's there from Paks on its next
# run). Lousã (Hattori Rally's kit, built on the PC: community.build_kit) has a stage list of its own under its own name.
GROUPS = {'acrdaily': (('~mods',), ('zz_acrxs_',)), 'lousa': (('~mods',), ('zz_acrxs_lousa_', 'zz_acrxs_s_acrxsptlousa_')),
          'wrcg': (('', '~mods'), ('pakchunk99-wrcg',)), 'sando': None}
_PACENOTE = re.compile(rb'DT_Pacenote([A-Za-z0-9_]{3,60})')
_STOCK = re.compile(r'^(global|pakchunk\d+(optional)?-windows)\.', re.I)
_LIST = b'DT_TracksVariants'                             # (a container that carries the game's stage list)


class SwitchError(Exception):
    """kind: 'running' (the game is open), 'files' (a file couldn't be renamed: all put back as they were)."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


def _folders(game, group):
    subs, _prefix = GROUPS[group] or (('',), '')
    return [os.path.join(game, 'acr', 'Content', 'Paks', *([sub] if sub else [])) for sub in subs]


def _named(n):
    """A container file's name as the game would have it (its parked suffix off), or None for any other file."""
    base = n[:-len(OFF)] if n.endswith(OFF) else n
    return base if _EXT.search(base) else None


def _group_of(base):
    """The group a file is by its name (the longest start that fits), or None."""
    low, best = base.lower(), (0, None)
    for g, spec in GROUPS.items():
        for p in (spec or ((), ()))[1]:
            if low.startswith(p) and len(p) > best[0]:
                best = (len(p), g)
    return best[1]


LIST = 'zz_acrdaily_stagelist_'                       # (stagelist.py's one list for all sets: no set's own)


def _ours(base):
    return _group_of(base) is not None or base.lower().startswith(LIST)


def _sando(game):
    """Sando Rally's files (Paks and ~mods): every file of a container whose index names a Sando stage's pace notes,
    or that carries the stage list and is no other set's (his manager's), the game's own left out."""
    paks, out = os.path.join(game, 'acr', 'Content', 'Paks'), []
    for d in (paks, os.path.join(paks, '~mods')):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        stems = set()
        for n in names:
            base = _named(n)
            if not base or not base.lower().endswith('.utoc') or _STOCK.match(base) or _ours(base):
                continue
            try:
                with open(os.path.join(d, n), 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            if b'DT_PacenoteSando' in data or _LIST in data:
                stems.add(base[:-len('.utoc')].lower())
        out += [os.path.join(d, n) for n in names if _named(n) and os.path.splitext(_named(n))[0].lower() in stems]
    return out


def files(game, group):
    """The group's files: (shown, parked), full paths (parked: with OFF at the end)."""
    if GROUPS[group] is None:
        found = _sando(game)
    else:
        found = []
        for d in _folders(game, group):
            try:
                found += [os.path.join(d, n) for n in os.listdir(d) if _named(n) and _group_of(_named(n)) == group]
            except OSError:
                pass
    shown = [p for p in found if not p.endswith(OFF)]
    parked = [p for p in found if p.endswith(OFF)]
    return sorted(shown), sorted(parked)


def state(game):
    """{group: 'on' (in the game) or 'off' (parked only)} for the groups with any files."""
    out = {}
    for g in GROUPS:
        shown, parked = files(game, g)
        if shown:
            out[g] = 'on'
        elif parked:
            out[g] = 'off'
    return out


def parked_packs(game, ids=()):
    """The parked packages' stages: {path relative to Paks: sorted stage ids} (as community.stage_packs reads the
    shown ones: their index names each stage's pace notes)."""
    paks, out = os.path.join(game, 'acr', 'Content', 'Paks'), {}
    want = [(i, i.encode()) for i in ids if i]
    for g in GROUPS:
        for p in files(game, g)[1]:
            if not p.lower().endswith('.utoc' + OFF):
                continue
            try:
                with open(p, 'rb') as f:
                    data = f.read()
            except OSError:
                continue
            found = {m.group(1).decode() for m in _PACENOTE.finditer(data)}
            found.update(i for i, b in want if b in data)
            if found:
                out[os.path.relpath(p, paks)] = sorted(found)
    return out


def _renames(pairs):
    """Rename each (from, to); on a failure the ones done go back, and SwitchError('files')."""
    done = []
    try:
        for a, b in pairs:
            if os.path.exists(b):
                os.remove(b)                              # (an old parked copy: the newer files win)
            os.rename(a, b)
            done.append((a, b))
    except OSError as e:
        for a, b in reversed(done):
            try:
                os.rename(b, a)
            except OSError:
                pass
        raise SwitchError('files', str(e))


def park(game, group):
    """The group out of the game: its files renamed to <name>.acrdaily-off."""
    _renames([(p, p + OFF) for p in files(game, group)[0]])


def unpark(game, group):
    """The group back in the game. Parked copies of files that are in the game again (made anew meanwhile: Stage
    Exporter installs its pack whole), in any of its folders (its 1.0 pack in Paks, 1.5's in ~mods), are old and go:
    every file of a container (.pak, .utoc, .ucas) one of whose files is in the game again."""
    def stem(p):
        return os.path.normcase(os.path.splitext(os.path.basename(_named(os.path.basename(p))))[0])
    shown, parked = files(game, group)
    live = {stem(p) for p in shown}
    stale = [p for p in parked if stem(p) in live]
    for p in stale:
        try:
            os.remove(p)
        except OSError:
            pass
    if shown:
        return
    _renames([(p, p[:-len(OFF)]) for p in parked if p not in stale])


def show(game, group, running=None):
    """Only this group's stages in the game: the others parked, it unparked. Raises SwitchError('running') with the
    game open (it keeps its files open), SwitchError('files') when a file can't be renamed (nothing half done)."""
    if running is None:
        from .community import game_running as running
    if running():
        raise SwitchError('running')
    others = [g for g, s in state(game).items() if g != group and s == 'on']
    for g in others:
        park(game, g)
    try:
        unpark(game, group)
    except SwitchError:
        for g in others:                                  # (it couldn't come back: the others stay as they were)
            try:
                unpark(game, g)
            except SwitchError:
                pass
        raise
    if others:                                            # (a list for all of them would name stages not in the game)
        from . import stagelist
        stagelist.remove(game)


def park_others(game, group, running=None):
    """Every set but this one parked (Stage Exporter makes its stages with no other stage mod in Paks). -> the groups
    parked, to put back with unpark when what it was for didn't go through. Raises SwitchError as show()."""
    if running is None:
        from .community import game_running as running
    if running():
        raise SwitchError('running')
    done = []
    try:
        for g, s in state(game).items():
            if g != group and s == 'on':
                park(game, g)
                done.append(g)
    except SwitchError:
        for g in done:
            try:
                unpark(game, g)
            except SwitchError:
                pass
        raise
    return done


def forget(game, group, names):
    """Parked copies of these files (names in the group's folders) taken out too (an item removed while parked)."""
    for d in _folders(game, group):
        for n in names:
            try:
                os.remove(os.path.join(d, n + OFF))
            except OSError:
                pass
