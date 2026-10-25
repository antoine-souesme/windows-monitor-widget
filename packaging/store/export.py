"""Draw the real widget with simulated values and export its canvas as SVG.

Usage: python export.py <repo> <out_dir>
"""
import json
import math
import os
import random
import sys
import tkinter as tk

REPO, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, REPO)

from monitor_widget import config, i18n, probes, ui  # noqa: E402

config.save = lambda values: None


def wave(seed, base, amp, noise, n=60, spikes=()):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        v = base + amp * math.sin(i / 6.0 + seed) + amp * 0.5 * math.sin(i / 2.3 + seed * 2)
        v += rnd.uniform(-noise, noise)
        for at, h in spikes:
            v += h * math.exp(-((i - at) ** 2) / 6.0)
        out.append(v)
    return out


def clamp(seq, lo, hi):
    return [max(lo, min(hi, v)) for v in seq]


BASE = {
    "cpu": clamp(wave(1, 34, 9, 5, spikes=[(22, 30), (48, 22)]), 3, 99),
    "gpu": clamp(wave(2, 78, 6, 4, spikes=[(40, 10)]), 3, 99),
    "gpu_temp": clamp(wave(3, 66, 2, 1), 30, 95),
    "ram": clamp(wave(4, 47, 1.5, 0.6), 0, 100),
    "down": [max(0.0, v) * 1024 * 1024 for v in wave(5, 4, 3, 2, spikes=[(18, 22), (35, 14), (52, 26)])],
    "up": [max(0.0, v) * 1024 * 1024 for v in wave(6, 0.6, 0.4, 0.3, spikes=[(30, 3)])],
    "fps": clamp(wave(7, 138, 8, 6, spikes=[(27, -45)]), 20, 240),
}


def prepare(window, series):
    """Fill every history with the simulated series."""
    SERIES = dict(BASE, **series)
    for probe in window.probes:
        key = probe.key
        if key == "net":
            pairs = list(zip(SERIES["down"], SERIES["up"]))
            probe._peaks[0].extend(SERIES["down"])
            probe._peaks[1].extend(SERIES["up"])
            values = [probe._selected(p) for p in pairs]
        elif key == "fps":
            probe._game = True
            probe._peaks.extend(SERIES["fps"])
            values = [(v,) for v in SERIES["fps"]]
        else:
            if key == "ram":
                probe._total = 32 * 1024 ** 3
                probe._used = probe._total * SERIES["ram"][-1] / 100.0
            values = [(v,) for v in SERIES[key]]
        history = window.histories[key]
        for v in values:
            history.append(tuple(v))
    window.gauges.clear()


def smooth_path(pts, closed):
    pairs = list(zip(pts[0::2], pts[1::2]))
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    f = lambda p: "%.2f %.2f" % p
    if closed:
        n = len(pairs)
        d = "M " + f(mid(pairs[-1], pairs[0]))
        for i in range(n):
            d += " Q " + f(pairs[i]) + " " + f(mid(pairs[i], pairs[(i + 1) % n]))
        return d + " Z"
    if len(pairs) < 3:
        return "M " + " L ".join(f(p) for p in pairs)
    d = "M " + f(pairs[0])
    for i in range(1, len(pairs) - 2):
        d += " Q " + f(pairs[i]) + " " + f(mid(pairs[i], pairs[i + 1]))
    d += " Q " + f(pairs[-2]) + " " + f(pairs[-1])
    return d


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_svg(canvas, width, height):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
           % (width, height, width, height)]
    outlined = False
    for item in canvas.find_all():
        kind = canvas.type(item)
        if kind == "text" and canvas.itemcget(item, "fill") == ui.OUTLINE:
            # The eight dark copies of an outlined text become one stroke.
            outlined = True
            continue
        c = canvas.coords(item)
        g = lambda o: canvas.itemcget(item, o)
        if kind == "polygon":
            fill = g("fill") or "none"
            stroke = g("outline") or "none"
            if g("smooth") not in ("0", "", "false"):
                d = smooth_path(c, True)
            else:
                d = "M " + " L ".join("%.2f %.2f" % p for p in zip(c[0::2], c[1::2])) + " Z"
            out.append('<path d="%s" fill="%s" stroke="%s"/>' % (d, fill, stroke))
        elif kind == "line":
            smooth = g("smooth") not in ("0", "", "false")
            d = smooth_path(c, False) if smooth else \
                "M " + " L ".join("%.2f %.2f" % p for p in zip(c[0::2], c[1::2]))
            out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s" '
                       'stroke-linejoin="round" stroke-linecap="round"/>'
                       % (d, g("fill"), g("width")))
        elif kind == "rectangle":
            x0, y0, x1, y1 = c
            out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>'
                       % (x0, y0, x1 - x0, y1 - y0, g("fill")))
        elif kind == "text":
            parts = canvas.tk.splitlist(g("font"))
            size = float(parts[1]) * 96 / 72
            weight = "700" if "bold" in parts[2:] else "400"
            anchor = {"w": "start", "e": "end"}.get(g("anchor"), "middle")
            stroke = (' stroke="#000" stroke-width="2.2" stroke-linejoin="round" '
                      'paint-order="stroke"' if outlined else "")
            outlined = False
            out.append('<text x="%.2f" y="%.2f" font-family="Segoe UI, Selawik, sans-serif" '
                       'font-size="%.2f" font-weight="%s" fill="%s" text-anchor="%s" '
                       'dominant-baseline="central"%s>%s</text>'
                       % (c[0], c[1], size, weight, g("fill"), anchor, stroke, esc(g("text"))))
    out.append("</svg>")
    return "\n".join(out)


SCENES = {
    "normal": dict(mode="normal", probes=["cpu", "gpu", "ram", "net"], width=230),
    "normal_cpu": dict(mode="normal", probes=["cpu"], width=200),
    "game": dict(mode="normal", probes=["fps", "gpu", "gpu_temp"], width=200),
    "compact": dict(mode="compact", probes=["cpu", "gpu", "gpu_temp", "ram", "net"], width=230),
    "custom": dict(mode="custom", probes=["cpu"], grid_columns=2, grid_rows=4,
                   grid_column_width=190,
                   grid_cells=["cpu:0", "gpu:0", "ram:0", "gpu_temp:0",
                               "net:0", "", "net:1", "fps:0"],
                   grid_wide=[4]),
    "ram_both": dict(mode="normal", probes=["cpu", "ram"], width=260, ram_display="both"),
    "cpu_low": dict(mode="normal", probes=["cpu"], width=200,
                    series={"cpu": clamp(wave(11, 14, 4, 3), 2, 99)}),
    "cpu_mid": dict(mode="normal", probes=["cpu"], width=200,
                    series={"cpu": clamp(wave(12, 58, 7, 4, spikes=[(50, 8)]), 2, 99)}),
    "cpu_high": dict(mode="normal", probes=["cpu"], width=200,
                     series={"cpu": clamp(wave(13, 86, 5, 3, spikes=[(55, 12)]), 2, 99)}),
}


def main():
    root = tk.Tk()
    root.withdraw()
    root.tk.call("tk", "scaling", 96 / 72.0)
    meta = {}
    for lang in ("en", "fr"):
        for name, scene in SCENES.items():
            values = dict(config.DEFAULTS)
            scene = dict(scene)
            series = scene.pop("series", {})
            values.update(scene)
            values.update(language=lang, tray_icon=False, x=50, y=50)
            win = ui.WidgetWindow(root, values)
            prepare(win, series)
            win._draw()
            w, h = win.window_width(), win._height()
            path = os.path.join(OUT, "%s_%s.svg" % (name, lang))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(to_svg(win.canvas, w, h))
            meta["%s_%s" % (name, lang)] = [w, h]
            for p in win.probes:
                p.stop()
            win.destroy()
    with open(os.path.join(OUT, "sizes.json"), "w") as handle:
        json.dump(meta, handle, indent=1)
    root.destroy()


main()
