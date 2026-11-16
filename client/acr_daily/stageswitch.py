"""Which stages the game shows: London's or WRC Generations' (communityui.py's TRACKS page; the test builds).

The game has one stage list, so only one tool's stages show at a time (community.py). Switching between ACR Daily's
London (acr-extrastages' zz_acrxs_* containers in ~mods) and the WRC Generations stages (Stage Exporter's
pakchunk99-wrcg* pack in Paks) never deletes or rebuilds anything: the one not shown is parked, its files renamed to
<name>.acrdaily-off, which the game doesn't load; showing it renames them back. A second either way, the game closed
(it keeps its files open). Stage Exporter's builds stay where they are, so a stage made once (about 40 minutes) is
never made again for a switch.

Sando Rally's Chile BioBio is left to Sando's own Stage Manager (only it may install or take out his stages; its
install is a copy, not a rebuild).
"""
import os
import re

OFF = '.acrdaily-off'
_EXT = re.compile(r'\.(pak|utoc|ucas)$', re.I)
# a group's files: (the folder under Paks, the name they start with)
GROUPS = {'acrdaily': ('~mods', 'zz_acrxs_'), 'wrcg': ('', 'pakchunk99-wrcg')}
_PACENOTE = re.compile(rb'DT_Pacenote([A-Za-z0-9_]{3,60})')


class SwitchError(Exception):
    """kind: 'running' (the game is open), 'files' (a file couldn't be renamed: all put back as they were)."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


def _folder(game, group):
    sub, _prefix = GROUPS[group]
    return os.path.join(game, 'acr', 'Content', 'Paks', *([sub] if sub else []))


def files(game, group):
    """The group's files: (shown, parked), full paths (parked: with OFF at the end)."""
    d, (_sub, prefix) = _folder(game, group), GROUPS[group]
    try:
        names = os.listdir(d)
    except OSError:
        return [], []
    shown = [os.path.join(d, n) for n in names if n.lower().startswith(prefix) and _EXT.search(n)]
    parked = [os.path.join(d, n) for n in names if n.lower().startswith(prefix) and n.endswith(OFF)
              and _EXT.search(n[:-len(OFF)])]
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
    Exporter installs its pack whole) are old and go."""
    shown, parked = files(game, group)
    live = {os.path.normcase(p) for p in shown}
    stale = [p for p in parked if os.path.normcase(p[:-len(OFF)]) in live]
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


def forget(game, group, names):
    """Parked copies of these files (names in the group's folder) taken out too (an item removed while parked)."""
    d = _folder(game, group)
    for n in names:
        try:
            os.remove(os.path.join(d, n + OFF))
        except OSError:
            pass
