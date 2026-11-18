"""Rally Weekend for WRC Generations' stages (the COMMUNITY page's 'wrcg' set, stageexport.py).

Stage Exporter's pack (Sando Rally's Stage Export Tool underneath) adds its stages to the game's stage list, marks their
tracks Free Practice only (DT_Tracks RaceEventTypes [FreePractice]) and adds no Rally Weekend calendar, and the game's
Rally Weekend menu lists a location only with calendars of its own. So beside the pack goes a small container of ours,
NAME, loaded after it (its name sorts after the pack's, and starts as the 'wrcg' set's files do: the stage switch
shows and hides it with the pack), holding three tables:
  DT_Tracks                      the pack's, its tracks opened to Free Practice and the offline Rally Weekend (never the
                                 online or challenge modes: TYPES);
  DT_TracksLocations             the pack's, the [MOD] locations' text without "Free Practice only";
  DT_RallyWeekendCalendarPreset  the game's calendars and three per [MOD] location, <location>WeekendShort / Medium /
                                 Long (1, 2 and 3 days, copies of Wales', each day on the location's stages).
It is made on the player's PC with Sando's own tools in their copy of the Stage Export Tool (bin\\retoc\\retoc.exe,
bin\\uatool\\UaTool.exe dumpjson / fromjson, bin\\acr_stage.usmap): the game's and the pack's tables are read from their
containers there, edited as JSON, packed again, and never leave the PC. The tables are the pack's own, so after the pack
changes (a stage made or taken out, a rebuild) they are made again (build), or taken out when they can't be (remove):
an old copy would hide the new stages (stale).
"""
import copy
import json
import os
import re
import shutil
import subprocess

from . import settings

NAME = 'pakchunk99-wrcgzcalendars_P'
PACK = 'pakchunk99-WrcgStages_P'
EXTS = ('pak', 'ucas', 'utoc')
PREFIX = 'Wrcg'                                   # (the pack's location, track and variant rows)
TYPES = ('FreePractice', 'Rally')                 # (DT_RaceEventTypes rows: Free Practice, the offline Rally Weekend)
TEMPLATE = 'Wales'                                # (whose calendars are copied: their days, service parks, weather)
LENGTHS = (('Short', 1), ('Medium', 2), ('Long', 3))
DB = 'acr/Content/Data/Database/Main/'
TABLES = {'tracks': DB + 'TrackSelection/DT_Tracks', 'locations': DB + 'TrackSelection/DT_TracksLocations',
          'calendars': DB + 'Common/DT_RallyWeekendCalendarPreset'}
TEXT = 'Stages imported from WRC Generations.'
SETTING = 'wrcgCalendars'                         # settings: the pack's signature the calendars were made for
WORK = 'ACRDaily-build'


class CalendarError(Exception):
    """kind: 'tools' (the Stage Export Tool's own tools aren't there), 'build' (a step failed: its words)."""

    def __init__(self, kind, detail=''):
        super().__init__(detail or kind)
        self.kind, self.detail = kind, detail


# ---------------------------------------------------------------------- the pack and its calendars

def _paks(game):
    return os.path.join(game, 'acr', 'Content', 'Paks')


def pack_dir(game):
    """The folder Stage Exporter's pack is in (~mods from its 1.5, Paks before), or None without one in the game."""
    for d in (os.path.join(_paks(game), '~mods'), _paks(game)):
        if os.path.isfile(os.path.join(d, PACK + '.utoc')):
            return d
    return None


def parked(game):
    """The pack is in the game but hidden by the stage switch (its files renamed <name>.acrdaily-off)."""
    return any(os.path.isfile(os.path.join(d, PACK + '.utoc.acrdaily-off'))
               for d in (os.path.join(_paks(game), '~mods'), _paks(game)))


def signature(game):
    """The pack as it is now (its index's and data's sizes and times), or None without a pack."""
    d = pack_dir(game)
    if not d:
        return None
    try:
        return ';'.join('%d-%d' % (os.path.getsize(p), int(os.path.getmtime(p)))
                        for p in (os.path.join(d, PACK + '.' + x) for x in ('utoc', 'ucas')))
    except OSError:
        return None


def present(game):
    """The folders holding our calendars (shown, not parked)."""
    return [d for d in (os.path.join(_paks(game), '~mods'), _paks(game))
            if os.path.isfile(os.path.join(d, NAME + '.utoc'))]


def stale(game):
    """Our calendars are in the game but were made for another pack (or none is there now)."""
    return bool(present(game)) and (settings.load().get(SETTING) or None) != signature(game)


def remove(game):
    """Our calendars out of the game (shown or parked). -> whether any were there."""
    gone = False
    for d in (os.path.join(_paks(game), '~mods'), _paks(game)):
        for x in EXTS:
            for n in (NAME + '.' + x, NAME + '.' + x + '.acrdaily-off'):
                try:
                    os.remove(os.path.join(d, n))
                    gone = True
                except OSError:
                    pass
    s = settings.load()
    if s.pop(SETTING, None) is not None:
        settings.save(s)
    return gone


def tools(tool):
    """Sando's tools in the Stage Export Tool: {retoc, uatool, usmap}, or None when one isn't there."""
    if not tool:
        return None
    t = {'retoc': os.path.join(tool, 'bin', 'retoc', 'retoc.exe'), 'uatool': os.path.join(tool, 'bin', 'uatool', 'UaTool.exe'),
         'usmap': os.path.join(tool, 'bin', 'acr_stage.usmap')}
    return t if all(os.path.isfile(p) for p in t.values()) else None


# ---------------------------------------------------------------------- the tables, as UaTool's JSON (UAssetAPI)

def _rows(asset):
    return asset['Exports'][0]['Table']['Data']


def _prop(row, name):
    return next((p for p in row['Value'] if p.get('Name') == name), None)


def _ref(prop):
    """A DBReference struct's (table, row)."""
    v = {p['Name']: p['Value'] for p in prop['Value']}
    return v.get('Table'), v.get('Row')


def _set_ref(prop, row):
    for p in prop['Value']:
        if p['Name'] == 'Row':
            p['Value'] = row


def _text(prop, s):
    """A text shown as it is in every language (as the pack's own [MOD] names are)."""
    for k in ('TableId', 'Namespace', 'SourceString', 'LocalizedString'):
        prop.pop(k, None)
    prop.update({'Flags': 0, 'HistoryType': 'None', 'CultureInvariantString': s, 'Value': None})


def _name(asset, *names):
    """Names an edited table refers to, in its name map: among the names its data uses (the first
    NamesReferencedFromExportDataCount), which are the only ones a package packed for the game keeps (the rest are
    lost: a row named UnknownExport). Names are strings in the JSON, so the ones after move up a place."""
    have = set(asset['NameMap'])
    at = int(asset.get('NamesReferencedFromExportDataCount') or len(asset['NameMap']))
    for n in names:
        if n and n not in have:
            asset['NameMap'].insert(at, n)
            at += 1
            have.add(n)
    if 'NamesReferencedFromExportDataCount' in asset:
        asset['NamesReferencedFromExportDataCount'] = at


def open_tracks(tracks, types=TYPES):
    """The pack's Wrcg tracks opened to `types`. -> {location row: [its stages' variant rows]} (in the table's order)."""
    stages = {}
    for row in _rows(tracks):
        loc = _prop(row, 'Location')
        if loc is None or not str(_ref(loc)[1] or '').startswith(PREFIX):
            continue
        variants = _prop(row, 'Variants')
        stages.setdefault(_ref(loc)[1], []).extend(_ref(v)[1] for v in (variants or {}).get('Value') or [])
        ev = _prop(row, 'RaceEventTypes')
        if ev is None or not ev.get('Value'):
            raise CalendarError('build', '%s has no race event types to open' % row['Name'])
        model = ev['Value'][0]
        ev['Value'] = []
        for i, t in enumerate(types):
            e = copy.deepcopy(model)
            e['Name'] = str(i)
            _set_ref(e, t)
            ev['Value'].append(e)
        _name(tracks, *types)
    return stages


def word_locations(locations):
    """The [MOD] locations' text, without "Free Practice only"."""
    for row in _rows(locations):
        if row['Name'].startswith(PREFIX):
            p = _prop(row, 'HistoryAndTrivia')
            if p is not None:
                _text(p, TEXT)


def add_calendars(calendars, stages, location_names=None):
    """Three calendars per location with stages (copies of TEMPLATE's), each day's entries cut to its stages."""
    added = []
    for loc, variants in stages.items():
        if not variants:
            continue
        name = (location_names or {}).get(loc) or '[MOD] ' + loc[len(PREFIX):]
        for length, days in LENGTHS:
            key = '%sWeekend%s' % (loc, length)
            if any(r['Name'] == key for r in _rows(calendars)):
                raise CalendarError('build', 'a calendar %s is there already' % key)
            src = next((r for r in _rows(calendars) if r['Name'].lower() == ('%sWeekend%s' % (TEMPLATE, length)).lower()), None)
            if src is None:
                raise CalendarError('build', 'no %sWeekend%s calendar to copy' % (TEMPLATE, length))
            row = copy.deepcopy(src)
            row['Name'] = key
            _text(_prop(row, 'Name'), 'Rally %s - %d day%s' % (name, days, 's' if days > 1 else ''))
            _set_ref(_prop(row, 'Location'), loc)
            desc = _prop(row, 'PresetDescription')
            if desc is not None:
                _text(desc, TEXT)
            for day in _prop(row, 'CalendarDays')['Value']:
                entries = _prop(day, 'Entries')
                entries['Value'] = entries['Value'][:len(variants)]
                for e, entry in zip(entries['Value'], variants):
                    _set_ref(_prop(e, 'Track'), entry)
            _rows(calendars).append(row)
            _name(calendars, key, loc, *variants)
            added.append(key)
    return added


def location_names(locations):
    """{location row: its name as the game shows it} for the pack's locations ('[MOD] France')."""
    out = {}
    for row in _rows(locations):
        p = _prop(row, 'Name')
        if row['Name'].startswith(PREFIX) and p is not None and p.get('CultureInvariantString'):
            out[row['Name']] = p['CultureInvariantString']
    return out


# ---------------------------------------------------------------------- made on the PC

def _run(args, what):
    r = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       creationflags=0x08000000 if os.name == 'nt' else 0, timeout=900)
    if r.returncode != 0:
        tail = r.stdout.decode('utf-8', 'replace').strip().splitlines()[-2:]
        raise CalendarError('build', '%s failed: %s' % (what, ' / '.join(tail) or 'exit %d' % r.returncode))


def work_dir(game):
    """Where they are made: the top of the game's drive (the pack is linked there, not copied: the same drive)."""
    drive = os.path.splitdrive(os.path.abspath(game))[0] or os.path.abspath(os.sep)
    return os.path.join(drive + os.sep, WORK, 'calendars')


def build(game, tool, run=None):
    """Our calendars made for the pack in the game now and put beside it (None: no pack, and any calendars of ours
    taken out). -> the calendars added. Raises CalendarError ('tools', 'build'): then any old ones are taken out too."""
    run = run or _run
    d = pack_dir(game)
    if not d:
        if not parked(game):                      # (hidden by the stage switch: left as they are, with the pack)
            remove(game)
        return None
    t = tools(tool)
    if not t:
        remove(game)
        raise CalendarError('tools', "the Stage Export Tool's own tools aren't there")
    work = work_dir(game)
    shutil.rmtree(work, ignore_errors=True)
    remove(game)                                  # (ours first: the game's calendars are read from its folders)
    try:
        sig = signature(game)
        paks = os.path.join(work, 'paks')
        os.makedirs(paks)
        for x in EXTS:
            os.link(os.path.join(d, PACK + '.' + x), os.path.join(paks, PACK + '.' + x))
        for n in os.listdir(_paks(game)):
            if n.lower().startswith('global.'):
                shutil.copy2(os.path.join(_paks(game), n), os.path.join(paks, n))
        legacy = os.path.join(work, 'legacy')
        run([t['retoc'], 'to-legacy', '--version', 'UE5_6', '--no-shaders', '--filter', 'DT_Tracks', paks, legacy],
            "reading the pack's tables")
        run([t['retoc'], 'to-legacy', '--version', 'UE5_6', '--no-shaders', '--filter', 'DT_RallyWeekendCalendarPreset',
             _paks(game), legacy], "reading the game's calendars")
        js = {}
        for k, rel in TABLES.items():
            src = os.path.join(legacy, *rel.split('/')) + '.uasset'
            if not os.path.isfile(src):
                raise CalendarError('build', '%s is not where it should be' % rel.rsplit('/', 1)[-1])
            out = os.path.join(work, k + '.json')
            run([t['uatool'], 'dumpjson', src, t['usmap'], out], 'reading %s' % rel.rsplit('/', 1)[-1])
            with open(out, encoding='utf-8') as f:
                js[k] = json.load(f)
        stages = open_tracks(js['tracks'])
        word_locations(js['locations'])
        added = add_calendars(js['calendars'], stages, location_names(js['locations']))
        mod = os.path.join(work, 'mod')
        for k, rel in TABLES.items():
            jp = os.path.join(work, k + '.edited.json')
            with open(jp, 'w', encoding='utf-8') as f:
                json.dump(js[k], f)
            dst = os.path.join(mod, *rel.split('/')) + '.uasset'
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            run([t['uatool'], 'fromjson', jp, t['usmap'], dst], 'writing %s' % rel.rsplit('/', 1)[-1])
        out = os.path.join(work, 'out')
        os.makedirs(out)
        run([t['retoc'], 'to-zen', '--no-parallel', '--version', 'UE5_6', mod, os.path.join(out, NAME + '.utoc')], 'packing')
        remove(game)
        for x in EXTS:
            shutil.move(os.path.join(out, NAME + '.' + x), os.path.join(d, NAME + '.' + x))
        s = settings.load()
        s[SETTING] = sig
        settings.save(s)
        return added
    except CalendarError:
        remove(game)
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError) as e:
        remove(game)
        raise CalendarError('build', str(e))
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(work))
        except OSError:
            pass
