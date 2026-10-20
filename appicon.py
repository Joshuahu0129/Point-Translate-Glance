"""Glance's icon: white "G" on a rounded Apple-blue square.

One drawing shared by the tray (main.py) and the exe/shortcut icon
(make_icon.py -> glance.ico), so they always look the same.
"""

from PIL import Image, ImageDraw

BLUE = (10, 132, 255, 255)
_SUPERSAMPLE = 4          # draw 4x bigger, then shrink: smooth edges at any size


def render(size=64):
    """Return an RGBA image of the icon, size x size pixels."""
    big = size * _SUPERSAMPLE
    k = big / 64.0        # all coordinates below are in a 64-unit design grid

    def pt(*v):
        return [round(x * k) for x in v]

    w = max(1, round(6 * k))
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(pt(4, 4, 60, 60), radius=round(16 * k), fill=BLUE)
    d.arc(pt(15, 13, 49, 51), start=20, end=315, fill="white", width=w)
    d.line(pt(46, 32, 46, 40), fill="white", width=w)   # stub at the opening
    d.line(pt(36, 36, 47, 36), fill="white", width=w)   # inward bar of the G
    return img.resize((size, size), Image.LANCZOS)
