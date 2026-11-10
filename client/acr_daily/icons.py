"""The app's icons (acr_daily/icons/<name>-<px>.png, drawn by make_icons.py: Lucide's, ISC licence, and the Discord
mark): white drawings, tinted to the colour they are shown in, at the size the screen's scale wants.

get(widget, 'settings', 18, '#A1A1AA') -> a Tk image (kept here, so Tk always has it), or None when it can't be made
(without Pillow only white ones can: a dark one is then left out, the caller shows its words instead).
"""
import os

try:
    from PIL import Image, ImageTk
except ImportError:          # (an app built without Pillow: white icons only)
    Image = None

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
SIZES = (18, 27, 36, 48, 72, 96)
_cache = {}


def drawn_size(px):
    """The smallest drawn size at least px big (the biggest if none is)."""
    return next((s for s in SIZES if s >= px), SIZES[-1])


def get(widget, name, px, colour='#F4F4F5'):
    """Icon `name` about px pixels big on this screen (px at 96 dpi, scaled), in colour (#RRGGBB)."""
    k = widget.winfo_fpixels('1i') / 96
    size = drawn_size(round(px * k))
    key = (id(widget.tk), name, size, colour.upper())   # (an image is its Tk's: each window's own, the tests' new ones)
    if key in _cache:
        return _cache[key]
    path = os.path.join(DIR, '%s-%d.png' % (name, size))
    img = None
    try:
        if Image is not None:
            src = Image.open(path).convert('RGBA')
            tinted = Image.new('RGBA', src.size, colour)
            tinted.putalpha(src.getchannel('A'))
            img = ImageTk.PhotoImage(tinted, master=widget)
        elif colour.upper() in ('#FFFFFF', '#F4F4F5', '#D4D4D8', '#A1A1AA'):
            import tkinter as tk
            img = tk.PhotoImage(file=path, master=widget)
    except (OSError, ValueError):
        img = None
    _cache[key] = img
    return img
