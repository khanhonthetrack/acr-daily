"""The photos behind the cards (as RaceRoom's tiles): real rally photos from Wikimedia Commons, each CC0 or CC BY (who
took them and their licence: photos/photos.json, shown in SETTINGS > About), cut to a card's size with a dark fade at
the bottom for the words on it, a red one from the left on the card on screen, and the stage's road drawn faintly.

card(widget, key, w, h, active, road) -> a Tk image (kept here), or None without Pillow or without that photo (the card
is then drawn flat, tiles.py). Keys: each rally ('wales', 'monte-carlo', 'alsace', 'greece', 'livigno') and each part
of the app ('dailies', 'tt', 'leagues', 'h2h', 'cups', 'live'); for_rally() names a rally's.
"""
import json
import os
from collections import OrderedDict

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:          # (an app built without Pillow: flat cards)
    Image = None

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
RED = (227, 6, 19)
_meta = None
_raw = {}
_cache = OrderedDict()         # (Tk, key, w, h, active, road id) -> PhotoImage, the last few kept
KEEP = 32


def meta():
    """photos/photos.json: {key: {file, title, author, licence, url, focus: [x, y]}} (focus: the point kept in view, 0..1)."""
    global _meta
    if _meta is None:
        try:
            with open(os.path.join(DIR, 'photos.json'), encoding='utf-8') as f:
                _meta = json.load(f)
        except (OSError, ValueError):
            _meta = {}
    return _meta


def for_rally(rally):
    """A rally's photo key ('Monte Carlo' -> 'monte-carlo'), or None for one without a photo."""
    key = (rally or '').strip().lower().replace(' ', '-')
    return key if key in meta() else None


def credits():
    """[(what, title, author, licence, url)] of every photo, for the About panel."""
    return [(k, m.get('title', ''), m.get('author', ''), m.get('licence', ''), m.get('url', '')) for k, m in sorted(meta().items())]


def _photo(key):
    if key not in _raw:
        m = meta().get(key) or {}
        try:
            _raw[key] = Image.open(os.path.join(DIR, m['file'])).convert('RGB')
        except (KeyError, OSError, ValueError):
            _raw[key] = None
    return _raw[key]


def compose(key, w, h, active=False, road=None, fit=None):
    """The card's picture (a PIL image w x h): the photo cut to its size around its focus, darker at the bottom and a
    little at the top, washed red from the left when active, the road (canvas points from fit) drawn on it faintly."""
    src = _photo(key) if Image is not None else None
    if src is None or w < 2 or h < 2:
        return None
    fx, fy = (meta().get(key) or {}).get('focus') or (0.5, 0.5)
    k = max(w / src.width, h / src.height)
    sw, sh = max(w, round(src.width * k)), max(h, round(src.height * k))
    img = src.resize((sw, sh), Image.LANCZOS)
    left = min(max(0, round(fx * sw - w / 2)), sw - w)
    top = min(max(0, round(fy * sh - h / 2)), sh - h)
    img = img.crop((left, top, left + w, top + h)).convert('RGBA')
    shade = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for y in range(h):                             # the fades: dark at the bottom (the words), a little at the top (chips)
        t = y / max(1, h - 1)
        a = 70 + 170 * max(0.0, (t - 0.35) / 0.65) ** 1.4 if t > 0.35 else 70 * (1 - t / 0.35) * 0.9 + 40
        d.line([(0, y), (w, y)], fill=(8, 8, 10, int(min(235, a))))
    img = Image.alpha_composite(img, shade)
    if active:                                     # the card on screen: red from the left
        wash = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(wash)
        for x in range(w):
            t = x / max(1, w - 1)
            if t < 0.75:
                d.line([(x, 0), (x, h)], fill=RED + (int(200 * (1 - t / 0.75) ** 1.3),))
        img = Image.alpha_composite(img, wash)
    if road and len(road) >= 4:                    # the stage's road, faint
        over = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(over).line([(road[i], road[i + 1]) for i in range(0, len(road) - 1, 2)], fill=(255, 255, 255, 70),
                                  width=max(2, round(h / 110)), joint='curve')
        img = Image.alpha_composite(img, over)
    return img.convert('RGB')


def card(widget, key, w, h, active=False, road=None):
    """compose() as a Tk image, made once for each size (the last few kept: the cards are drawn again as the window
    changes)."""
    if Image is None or not key:
        return None
    ck = (id(widget.tk), key, w, h, bool(active), len(road or ()), tuple(road[:4]) if road else None)   # (its Tk's)
    if ck in _cache:
        _cache.move_to_end(ck)
        return _cache[ck]
    img = compose(key, w, h, active, road)
    tk_img = ImageTk.PhotoImage(img, master=widget) if img is not None else None
    _cache[ck] = tk_img
    while len(_cache) > KEEP:
        _cache.popitem(last=False)
    return tk_img
