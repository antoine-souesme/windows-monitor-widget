# -*- coding: utf-8 -*-
"""Draws the PNG logos the Store package needs, without any dependency.

It also draws monitor_widget/icon.ico, the icon of the executable and of the
notification area. Run it once (or after changing the drawing) to refresh
them:

    python packaging/make_icons.py

The picture is the logo of packaging/store/logo/logo.svg: a curve going
from green to red over a dark blue rounded square, a live point at its end
and a gauge underneath, the same scale the widget uses for its graph.
"""

import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "msix", "Assets")
ICON = os.path.join(HERE, "..", "monitor_widget", "icon.ico")

SUPERSAMPLE = 4                      # drawn larger, then averaged down
CANVAS = 1024.0                      # coordinates below, as in store/logo/logo.svg
BACK_TOP = (20, 28, 77)              # deep blue, top left
BACK_BOTTOM = (36, 16, 70)           # violet, bottom right
GLOW = (76, 110, 255)                # blue light in the top right corner
WHITE = (255, 255, 255)
# The green -> orange -> red scale of the widget.
SCALE = [(0.0, (0x4c, 0xaf, 0x50)), (0.55, (0xff, 0x98, 0x00)),
         (1.0, (0xf4, 0x43, 0x36))]
# The curve: four cubic pieces, each (start, control, control, end).
CURVE = [((150, 640), (230, 640), (250, 560), (320, 575)),
         ((320, 575), (390, 590), (420, 690), (490, 600)),
         ((490, 600), (560, 510), (600, 380), (680, 430)),
         ((680, 430), (760, 480), (790, 300), (874, 250))]
LEFT, RIGHT = 150.0, 874.0           # ends of the curve and of the gauge
AREA_BOTTOM = 760.0
GAUGE = (810.0, 850.0, 710.0)        # top, bottom, end of the filled part

# name -> side in pixels
LOGOS = {
    "Square44x44Logo.png": 44,
    "Square150x150Logo.png": 150,
    "StoreLogo.png": 50,
}
# Sides held by the .ico, Windows picks the one matching the display scale.
ICON_SIDES = [16, 20, 24, 32, 40, 48, 64]


def _mix(low, high, ratio):
    return tuple(a + (b - a) * ratio for a, b in zip(low, high))


def _scale(x):
    """Color of the load scale at horizontal position `x` of the canvas."""
    ratio = max(0.0, min((x - LEFT) / (RIGHT - LEFT), 1.0))
    for (start, low), (end, high) in zip(SCALE, SCALE[1:]):
        if ratio <= end:
            return _mix(low, high, (ratio - start) / (end - start))
    return SCALE[-1][1]


def _over(pixel, color, alpha):
    """Paint `color` with opacity `alpha` over an opaque pixel."""
    alpha = max(0.0, min(alpha, 1.0))
    return _mix(pixel, color, alpha)


def _inside_rounded_square(x, y, side, radius):
    """True when the point falls inside a square with rounded corners."""
    left = radius - x if x < radius else 0
    right = x - (side - radius) if x > side - radius else 0
    top = radius - y if y < radius else 0
    bottom = y - (side - radius) if y > side - radius else 0
    dx, dy = max(left, right), max(top, bottom)
    return dx * dx + dy * dy <= radius * radius


def _curve_points(steps=24):
    """The curve as a list of points close enough to look smooth."""
    points = []
    for p0, p1, p2, p3 in CURVE:
        for index in range(steps + (1 if p3 == CURVE[-1][3] else 0)):
            t = index / float(steps)
            u = 1 - t
            points.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c
                                + t ** 3 * d for a, b, c, d in zip(p0, p1, p2, p3)))
    return points


def _distance(x, y, segments):
    best = 1e9
    for (ax, ay), (bx, by) in segments:
        dx, dy = bx - ax, by - ay
        t = ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(t, 1.0))
        ex, ey = ax + t * dx - x, ay + t * dy - y
        best = min(best, ex * ex + ey * ey)
    return best ** 0.5


def _curve_height(x, points):
    """Height of the curve at `x` (it only goes from left to right)."""
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        if ax <= x <= bx:
            return ay + (by - ay) * (x - ax) / (bx - ax)
    return None


def _draw(side):
    """Return the pixels of one logo as a list of rows of (r, g, b, a).
    Small sizes get a thicker curve and drop the faint area under it."""
    big = side * SUPERSAMPLE
    unit = CANVAS / big                 # canvas units per drawn pixel
    small = side < 40
    # About two pixels of curve whatever the size, never thinner than the logo.
    width = max(46.0, 2.2 * CANVAS / side)
    glow = 0.0 if small else 46.0
    dot = max(42.0, 1.6 * CANVAS / side)
    points = _curve_points()
    segments = list(zip(points, points[1:]))
    end_x, end_y = points[-1]
    reach = width / 2 + glow + 2

    rows = []
    for row in range(big):
        y = (row + 0.5) * unit
        line = []
        for column in range(big):
            x = (column + 0.5) * unit
            if not _inside_rounded_square(column + 0.5, row + 0.5, big, big * 0.22):
                line.append((0, 0, 0, 0))
                continue
            diagonal = (x + y) / (2 * CANVAS)
            pixel = _mix(BACK_TOP, BACK_BOTTOM, diagonal)
            light = ((x - 800) ** 2 + (y - 220) ** 2) ** 0.5 / 620.0
            pixel = _over(pixel, GLOW, 0.5 * max(0.0, 1 - light) ** 2)

            # Area under the curve, fading towards the bottom.
            height = _curve_height(x, points) if LEFT <= x <= RIGHT else None
            if not small and height is not None and height <= y <= AREA_BOTTOM:
                fade = 1 - (y - 250) / (AREA_BOTTOM - 250)
                pixel = _over(pixel, _scale(x), 0.4 * fade)

            # The curve and its glow, only computed near it.
            if 100 <= x <= 930 and 200 <= y <= 720:
                distance = _distance(x, y, segments)
                if distance < reach:
                    edge = distance - width / 2
                    if edge <= 0:
                        pixel = _scale(x)
                    elif glow:
                        pixel = _over(pixel, _scale(x), 0.55 * (1 - edge / glow) ** 2)

            # Live point at the end of the curve.
            spot = ((x - end_x) ** 2 + (y - end_y) ** 2) ** 0.5
            if spot <= dot:
                pixel = WHITE if spot > dot * 0.55 else SCALE[-1][1]

            # Gauge underneath.
            top, bottom, filled = GAUGE
            if not small and LEFT <= x <= RIGHT and top <= y <= bottom:
                pixel = _scale(x) if x <= filled else _over(pixel, WHITE, 0.12)
            line.append(tuple(int(round(value)) for value in pixel) + (255,))
        rows.append(line)
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
