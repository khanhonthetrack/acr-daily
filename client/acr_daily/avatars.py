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


def get(url, size):
    """Tk image of the avatar at `url`, `size` px round; None while loading, on failure or without Pillow.
    Call on the Tk thread."""
    if not url or Image is None:
        return None
    key = (url, size)
    if key in _tk:
        return _tk[key]
    with _lock:
        raw = _raw.get(url)
        if raw is None and url not in _busy:
            _busy.add(url)
            threading.Thread(target=_fetch, args=(url,), daemon=True).start()
    if not raw:
        return None
    _tk[key] = ImageTk.PhotoImage(round_image(raw, size))
    return _tk[key]
