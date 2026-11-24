"""The tyres and the livery a driver picks for an event (0.2: COMPETITIONS in the game, ig_comp.py), passed to the game
with its in-game DRIVE (ingamedrive.py -> drive.lua). Dailies and time trials keep the game's own tyres, as everyone
drives them alike.

Tyres (probed in the game 21 Nov 2026): the game's compounds (its DT_TireCompounds rows) and TYRES of them for a rally
(its tyre screen's total, 16). Which compounds a rally takes is the game's to say (by its tracks); here they are named
by the rally's surface. drive.lua writes the counts only when they fit what the game offers, else it keeps its own.

Liveries: one official livery a car (the game's DT_Liveries row, the car's id but for the i20's spelling) and the
driver's own, a folder each in Documents\\My Games\\acr\\Liveries\\<car> (what ACR Livery Tool exports, and COMMUNITY's
INSTALL puts there), named "usergen_<folder>" in the game. The game keeps the one picked for each car, as its garage's
pick does: so it is kept here for each car too, not each event.
"""
import os
import threading

from . import liveries, settings
from .i18n import _

TYRES = 16                              # a rally's tyres, all compounds together (the game's tyre screen: 0/16)
GRAVEL = ('GravelSoft', 'GravelMedium', 'GravelHard')
TARMAC = ('TarmacSoft', 'TarmacMedium', 'TarmacHard', 'TarmacWet')
WINTER = TARMAC + ('TarmacWinter', 'TarmacSnow')
SNOW = ('FullSnow',)
BY_RALLY = {'wales': GRAVEL, 'greece': GRAVEL, 'portugal': GRAVEL, 'chile': GRAVEL, 'kenya': GRAVEL,
            'alsace': TARMAC, 'london': TARMAC, 'monte carlo': WINTER, 'sweden': SNOW}
NAMES = {'GravelSoft': _('Soft'), 'GravelMedium': _('Medium'), 'GravelHard': _('Hard'), 'TarmacSoft': _('Soft'),
         'TarmacMedium': _('Medium'), 'TarmacHard': _('Hard'), 'TarmacWet': _('Wet'), 'TarmacWinter': _('Winter'),
         'TarmacSnow': _('Snow'), 'FullSnow': _('Snow')}
OFFICIAL = {'HyundaiI20NRally2': 'Hyundaii20NRally2'}   # (the game's livery row where it isn't spelled as the car)
GAME_CARS = {'AlfaRomeoGTA1300', 'HyundaiI20NRally2', 'MiniCooperS1275', 'CitroenXsaraWRC', 'Fiat131Abarth',
             'LanciaDeltaIntegraleEvo', 'Fiat124Abarth', 'AlpineA110', 'Peugeot208Rally4', 'LanciaStratosHF',
             'LanciaRally037Evo2', 'LanciaFulviaHF', 'SkodaFabiaRSRally2', 'Peugeot306IIMaxiKitCar', 'SubaruImprezaS3',
             'AudiQuattroGr4', 'Peugeot206', 'VWPoloGTIR5', 'LanciaDeltaS4', 'LanciaDeltaS4Evo2'}
USER = 'usergen_'


# ---------------------------------------------------------------------- tyres
# An event in several places may cross surfaces (Alsace's tarmac, then Sweden's snow: leagues.legs, each its own Rally
# Weekend): the driver picks the tyres of each surface at the start (the user, 24 Nov 2026), each leg gets its own.
SURFACES = (('gravel', GRAVEL), ('tarmac', TARMAC), ('winter', WINTER), ('snow', SNOW))
SURFACE_NAMES = {'gravel': 'Gravel', 'tarmac': 'Tarmac', 'winter': 'Winter', 'snow': 'Snow'}   # (i18n.data / _ words)
_KEY_OF = {rows: k for k, rows in SURFACES}


def _surface(name):
    name = (name or '').strip().lower()
    for k, v in BY_RALLY.items():
        if name.startswith(k):
            return v
    return ()


def _tracks(ev, leg=None):
    tracks = [s.get('track') for s in ev.get('stages') or () if s.get('track')]
    if leg is not None and tracks:
        from . import leagues                          # (late: leagues imports this module's neighbours)
        try:
            a, b = leagues.legs(ev)[leg]
            tracks = [s.get('track') for s in ev['stages'][a:b] if s.get('track')]
        except (IndexError, KeyError):
            pass
    return tracks


def surfaces(ev, leg=None):
    """The surfaces an event (or one of its legs) is driven on, in the order driven: ['tarmac', 'snow']. [] when its
    places aren't known here."""
    out = []
    for t in _tracks(ev, leg) or [ev.get('rally')]:
        k = _KEY_OF.get(tuple(_surface(t)))
        if k and k not in out:
            out.append(k)
    return out


def surface_stages(ev, surface):
    """The stage numbers (1..) on that surface: what its picker says it is for."""
    return [k + 1 for k, s in enumerate(ev.get('stages') or ()) if _KEY_OF.get(tuple(_surface(s.get('track')))) == surface]


def _one(ev, leg=None, surface=None):
    """The surface asked for, or the event's (the leg's) only one, or None."""
    if surface:
        return surface
    k = surfaces(ev, leg)
    return k[0] if len(k) == 1 else None


def compounds(ev, leg=None, surface=None):
    """An event's compounds to pick from (its rally's surface), or () when the rally isn't known here. An event on
    several surfaces: () unless one is asked for (surface) or the leg's (leg) is one."""
    k = _one(ev, leg, surface)
    if k:
        return dict(SURFACES)[k]
    return _surface(ev.get('rally')) if not _tracks(ev, leg) else ()


def _kept(s, ev, surface):
    """What is kept for the event: {row: n} for its only surface (as before 24 Nov 2026), or {'@<surface>': {row: n}}
    for one on several."""
    t = (s.get('eventTyres') or {}).get(str(ev.get('id')))
    if not isinstance(t, dict):
        return None
    if any(str(k).startswith('@') for k in t):
        return t.get('@' + surface) if surface else None
    return t if len(surfaces(ev)) <= 1 else None


def tyres_of(s, ev, leg=None, surface=None):
    """The driver's counts for this event ({row: n}) on its surface (the leg's, or the one asked for), or None: the
    game's own."""
    k = _one(ev, leg, surface)
    rows = compounds(ev, leg, k)
    t = _kept(s, ev, k)
    if not isinstance(t, dict) or not rows:
        return None
    t = {r: int(v) for r, v in t.items() if r in rows and int(v) > 0}
    return t if sum(t.values()) == TYRES else None


def start_counts(ev, surface=None):
    """The counts the picker starts from: the tyres shared out across the rally's compounds, the middle ones first."""
    rows = [r for r in compounds(ev, surface=surface) if r not in ('TarmacWinter', 'TarmacSnow')] or \
        list(compounds(ev, surface=surface))
    if not rows:
        return {}
    out = {r: TYRES // len(rows) for r in rows}
    for r in rows[1:1 + TYRES - sum(out.values())] or rows[:TYRES - sum(out.values())]:
        out[r] += 1
    return out


def step_tyres(s, ev, row, d, surface=None):
    """One tyre more (d +1) or less (-1) of a compound: taken from / given to the others, so they add up to TYRES. ->
    the new counts (kept in the settings). surface: which of an event's surfaces (its only one by default)."""
    k = _one(ev, surface=surface)
    rows = list(compounds(ev, surface=k))
    cur = dict(tyres_of(s, ev, surface=k) or start_counts(ev, k))
    for r in rows:
        cur.setdefault(r, 0)
    if row not in rows or not 0 <= cur[row] + d <= TYRES:
        return cur
    # the other compound that gives (or takes) one: the one with the most (or the least) after it in the list
    others = [r for r in rows if r != row]
    pool = [r for r in others if cur[r] > 0] if d > 0 else others
    if not pool:
        return cur
    other = max(pool, key=lambda r: cur[r]) if d > 0 else min(pool, key=lambda r: cur[r])
    cur[row] += d
    cur[other] -= d
    kept = {r: v for r, v in cur.items() if v}
    all_ = s.setdefault('eventTyres', {})
    if len(surfaces(ev)) > 1:
        t = all_.get(str(ev['id']))
        t = t if isinstance(t, dict) and all(str(x).startswith('@') for x in t) else {}
        t['@' + k] = kept
        all_[str(ev['id'])] = t
    else:
        all_[str(ev['id'])] = kept
    settings.save(s)
    return cur


def auto_tyres(s, ev, surface=None):
    """Back to the game's own choice for this event (on that surface only, for one on several)."""
    all_ = s.get('eventTyres') or {}
    t = all_.get(str(ev['id']))
    if surface and isinstance(t, dict) and len(surfaces(ev)) > 1:
        t.pop('@' + surface, None)
        if not t:
            all_.pop(str(ev['id']), None)
    else:
        all_.pop(str(ev['id']), None)
    settings.save(s)


# ---------------------------------------------------------------------- liveries
_making = set()                         # previews being made (a thread each, one at a time)
_make_lock = threading.Lock()


def preview(car_id, name, w, h):
    """A livery's tile picture: the game's own for its official one ('ue:livery:<row>', appui.lua), else a cut of the
    livery's own paint (its body texture, as ACR Livery Tool exports it: what it looks like, flat) made once in the
    background -> a picture source, or None (none yet: a plain tile meanwhile)."""
    if not name:
        return None
    if name == official(car_id):
        return 'ue:car:%s' % car_id              # (the car as CHANGE CAR shows it: its official look)
    folder = os.path.join(liveries.root(), liveries.car_folder(car_id), name[len(USER):])
    src = os.path.join(folder, 'body_livery_albedo.dds')
    try:
        stamp = int(os.path.getmtime(src))
    except OSError:
        return None
    out = os.path.join(settings.DIR, 'hud', 'app', 'livery-%08x-%d-%dx%d.png'
                       % (zlib_crc(folder.lower()), stamp, w, h))
    if os.path.exists(out):
        return out
    with _make_lock:
        if out in _making:
            return None
        _making.add(out)

    def make():
        try:
            from PIL import Image
            im = Image.open(src).convert('RGB')
            sw, sh = im.size
            # (the middle of the texture, cut to the tile's shape: the car's sides are mostly there)
            cw = sw * 0.55
            ch_ = cw * h / w
            x0, y0 = (sw - cw) / 2, (sh - ch_) / 2
            im = im.crop((round(x0), round(y0), round(x0 + cw), round(y0 + ch_))).resize((w, h), Image.LANCZOS)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            im.save(out + '.tmp', 'PNG')
            os.replace(out + '.tmp', out)
        except Exception:
            pass
        finally:
            with _make_lock:
                _making.discard(out)
    threading.Thread(target=make, daemon=True).start()
    return None


def zlib_crc(s):
    import zlib
    return zlib.crc32(s.encode('utf-8')) & 0xFFFFFFFF


def official(car_id):
    """The car's own livery in the game, or None (a car the game doesn't list: a community car)."""
    if car_id not in GAME_CARS:
        return None
    return OFFICIAL.get(car_id, car_id)


def own(car_id, base=None):
    """The driver's liveries for a car in the game's Liveries folder: [folder name] (sorted; _ off ones skipped)."""
    try:
        folder = liveries.car_folder(car_id, base=base)
        path = os.path.join(base or liveries.root(), folder)
        names = [n for n in os.listdir(path) if os.path.isdir(os.path.join(path, n)) and not n.startswith('_')]
    except Exception:
        return []
    return sorted(names, key=str.lower)[:liveries.PER_CAR]


def choices(car_id, base=None):
    """[(the game's livery name, words)]: its official one first, then the driver's own."""
    out = []
    o = official(car_id)
    if o:
        out.append((o, _('Official')))
    out += [(USER + n, n) for n in own(car_id, base)]
    return out


def livery_of(s, car_id):
    """The livery picked for a car here, or None (the game's own pick stays)."""
    v = (s.get('carLivery') or {}).get(car_id)
    return v if isinstance(v, str) and v else None


def pick_livery(s, car_id, name):
    s.setdefault('carLivery', {})[car_id] = name
    settings.save(s)


def for_daily(s, car_id):
    """A daily's / time trial's in-game DRIVE: only the livery picked (the tyres stay the game's: alike for everyone)."""
    lv = livery_of(s, car_id)
    if lv and (lv == official(car_id) or lv[len(USER):] in own(car_id)):
        return {'livery': lv}
    return {}


def for_setup(s, ev, car_id, leg=None):
    """What an event's in-game DRIVE adds to its set-up: {'tyres': ..., 'livery': ...}, only what was picked. leg: the
    leg being set up (an event in several places: the tyres picked only where their surface is)."""
    out = {}
    if ev.get('kind') != 'live':                        # (a ranked session: everyone alike)
        t = tyres_of(s, ev, leg)
        if t:
            out['tyres'] = t
    lv = livery_of(s, car_id)
    if lv and (lv == official(car_id) or lv[len(USER):] in own(car_id)):
        out['livery'] = lv
    return out
