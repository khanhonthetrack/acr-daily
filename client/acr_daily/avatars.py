"""Steam avatars as small round images for the overlays (Steam serves JPEGs, which Tk can't read: Pillow does).

get(url, size) returns a Tk image once it has been downloaded (in a thread), None until then or without Pillow,
so the overlays draw a coloured dot instead.
"""
import io
import threading
import urllib.request

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:          # an app built without Pillow: plain dots
    Image = None

_raw = {}        # url -> PIL image (RGBA), or False when it failed
_tk = {}         # (url, size) -> PhotoImage
_busy = set()
_lock = threading.Lock()


def _fetch(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ACR-Daily'})
        with urllib.request.urlopen(req, timeout=8) as r:
            img = Image.open(io.BytesIO(r.read())).convert('RGBA')
        with _lock:
            _raw[url] = img
    except Exception:
        with _lock:
            _raw[url] = False
    finally:
        with _lock:
            _busy.discard(url)


def round_image(img, size):
    """The picture cut to a circle, size x size pixels (drawn at 4x and scaled down for a smooth edge)."""
    big = img.resize((size * 4, size * 4), Image.LANCZOS)
    mask = Image.new('L', big.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big.size[0] - 1, big.size[1] - 1), fill=255)
    big.putalpha(mask)
    return big.resize((size, size), Image.LANCZOS)


def _raw_of(url):
    """The downloaded picture, or None (asked for once, in a thread, the first time)."""
    with _lock:
        raw = _raw.get(url)
        ask = raw is None and url not in _busy
        if ask:
            _busy.add(url)
    if ask:                    # (started outside the lock: a thread run at once, as in the tests, takes it itself)
        threading.Thread(target=_fetch, args=(url,), daemon=True).start()
    return raw or None


def get(url, size):
    """Tk image of the avatar at `url`, `size` px round; None while loading, on failure or without Pillow.
    Call on the Tk thread."""
    if not url or Image is None:
        return None
    key = (url, size)
    if key in _tk:
        return _tk[key]
    raw = _raw_of(url)
    if not raw:
        return None
    _tk[key] = ImageTk.PhotoImage(round_image(raw, size))
    return _tk[key]


FLAG_URL = 'https://flagcdn.com/w40/%s.png'      # (the website's flags, src/site.js: the same pictures)


def flag(code, w=18, h=12):
    """Tk image of a country's flag (ISO code, 'pl'), w x h px; None while loading, on failure or without Pillow."""
    code = str(code or '').lower()
    if len(code) != 2 or not code.isalpha() or Image is None:
        return None
    url = FLAG_URL % code
    key = (url, w, h)
    if key in _tk:
        return _tk[key]
    raw = _raw_of(url)
    if not raw:
        return None
    _tk[key] = ImageTk.PhotoImage(raw.resize((w, h), Image.LANCZOS))
    return _tk[key]


def loading():
    """Is a picture still on its way? (a page drawn meanwhile draws itself again once they are in)"""
    with _lock:
        return bool(_busy)
