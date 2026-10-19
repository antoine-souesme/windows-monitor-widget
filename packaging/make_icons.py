# -*- coding: utf-8 -*-
"""Draws the PNG logos the Store package needs, without any dependency.

It also draws monitor_widget/icon.ico, the icon of the executable and of the
notification area. Run it once (or after changing the drawing) to refresh
them:

    python packaging/make_icons.py

The picture is a dark rounded square holding five bars going from green to
red, the same scale the widget uses for its graph.
"""

import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "msix", "Assets")
ICON = os.path.join(HERE, "..", "monitor_widget", "icon.ico")

SUPERSAMPLE = 4                      # drawn larger, then averaged down
BACKGROUND = (27, 29, 33)            # near black, matches the widget
LOW = (62, 208, 106)                 # green, a quiet metric
HIGH = (228, 72, 59)                 # red, a busy one
BARS = 5

# name -> side in pixels
LOGOS = {
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "StoreLogo.png": 50,
}
# Sides held by the .ico, Windows picks the one matching the display scale.
ICON_SIDES = [16, 20, 24, 32, 40, 48, 64]


def _mix(low, high, ratio):
    return tuple(int(round(a + (b - a) * ratio)) for a, b in zip(low, high))


def _inside_rounded_square(x, y, side, radius):
    """True when the point falls inside a square with rounded corners."""
    left = radius - x if x < radius else 0
    right = x - (side - radius) if x > side - radius else 0
    top = radius - y if y < radius else 0
    bottom = y - (side - radius) if y > side - radius else 0
    dx, dy = max(left, right), max(top, bottom)
    return dx * dx + dy * dy <= radius * radius


def _draw(side):
    """Return the pixels of one logo as a list of rows of (r, g, b, a)."""
    big = side * SUPERSAMPLE
    radius = big * 0.20
    margin = big * 0.16
    width = (big - 2 * margin) / (BARS * 2 - 1)   # a bar, then a gap

    # Height of each bar, from a third of the room to almost all of it.
    heights = [(0.34 + 0.62 * index / (BARS - 1)) * (big - 2 * margin)
               for index in range(BARS)]
    colors = [_mix(LOW, HIGH, index / (BARS - 1)) for index in range(BARS)]

    rows = []
    for y in range(big):
        row = []
        for x in range(big):
            if not _inside_rounded_square(x + 0.5, y + 0.5, big, radius):
                row.append((0, 0, 0, 0))
                continue
            pixel = BACKGROUND + (255,)
            for index in range(BARS):
                start = margin + index * 2 * width
                if start <= x < start + width and y >= big - margin - heights[index]:
                    pixel = colors[index] + (255,)
                    break
            row.append(pixel)
        rows.append(row)
    return _shrink(rows, side)


def _shrink(rows, side):
    """Average SUPERSAMPLE x SUPERSAMPLE blocks into one pixel."""
    step = SUPERSAMPLE
    count = step * step
    out = []
    for y in range(side):
        line = []
        for x in range(side):
            totals = [0, 0, 0, 0]
            for dy in range(step):
                for dx in range(step):
                    pixel = rows[y * step + dy][x * step + dx]
                    for channel in range(4):
                        totals[channel] += pixel[channel]
            line.append(tuple(value // count for value in totals))
        out.append(line)
    return out


def _write_png(path, rows):
    """Minimal RGBA writer: no filtering, one zlib stream."""
    raw = b"".join(b"\x00" + bytes(value for pixel in row for value in pixel)
                   for row in rows)
    side = len(rows)

    def chunk(kind, data):
        block = kind + data
        return (struct.pack(">I", len(data)) + block
                + struct.pack(">I", zlib.crc32(block) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", side, side, 8, 6, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", header))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        handle.write(chunk(b"IEND", b""))


def _bitmap(rows):
    """One .ico entry: a 32 bit BGRA bitmap, bottom row first, followed by
    the (unused but required) transparency mask."""
    side = len(rows)
    header = struct.pack("<IiiHHIIiiII", 40, side, side * 2, 1, 32, 0, 0,
                         0, 0, 0, 0)
    pixels = b"".join(bytes((b, g, r, a)) for row in reversed(rows)
                      for (r, g, b, a) in row)
    mask = b"\x00" * (((side + 31) // 32) * 4 * side)
    return header + pixels + mask


def _write_ico(path, sides):
    images = [_bitmap(_draw(side)) for side in sides]
    offset = 6 + 16 * len(images)
    directory = b""
    for side, image in zip(sides, images):
        directory += struct.pack("<BBBBHHII", side % 256, side % 256, 0, 0,
                                 1, 32, len(image), offset)
        offset += len(image)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(images)))
        handle.write(directory)
        for image in images:
            handle.write(image)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for name, side in LOGOS.items():
        path = os.path.join(ASSETS, name)
        _write_png(path, _draw(side))
        print("written", path)
    _write_ico(ICON, ICON_SIDES)
    print("written", os.path.normpath(ICON))


if __name__ == "__main__":
    main()
