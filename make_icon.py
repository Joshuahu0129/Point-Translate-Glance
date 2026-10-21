"""Build glance.ico (the exe / shortcut icon) from appicon.py.

    python make_icon.py

glance.ico is committed, so you only re-run this after changing appicon.py.
The .ico holds several sizes; Windows picks the sharpest for each place
(taskbar, Explorer, desktop shortcut).
"""

import os

from appicon import render

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "glance.ico")
SIZES = (256, 128, 64, 48, 32, 24, 16)


def main():
    frames = [render(s) for s in SIZES]     # each size drawn natively, not shrunk
    frames[0].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES],
                   append_images=frames[1:])
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
