"""Compose the Store screenshots and the presentation image as HTML pages,
then render them with headless Chrome at 3840x2160.

Run export.py first: python export.py <repo> build/svg"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "build", "svg")
PAGES = os.path.join(HERE, "build", "pages")
OUT = HERE
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SIZES = json.load(open(os.path.join(SVG, "sizes.json")))

TEXT = {
    "fr": {
        "s1": ("Votre PC, d’un coup d’œil", "Processeur, carte graphique, mémoire et réseau, mis à jour chaque seconde, sur votre bureau."),
        "s2": ("Du vert au rouge", "La couleur suit la charge : vous voyez tout de suite quand votre PC peine."),
        "s3": ("Mode compact", "Deux fines lignes par valeur : le graphique, puis une jauge. Discret, toujours lisible."),
        "s4": ("Votre grille, à votre façon", "Placez chaque valeur où vous voulez, une case peut s’étendre sur deux colonnes."),
        "s5": ("Pensé pour le jeu", "Les images par seconde du jeu en plein écran, à côté de la charge et de la température du GPU."),
        "tag": "Monitor Widget",
    },
    "en": {
        "s1": ("Your PC at a glance", "Processor, graphics card, memory and network, refreshed every second, right on your desktop."),
        "s2": ("From green to red", "The color follows the load: you see at once when your PC is struggling."),
        "s3": ("Compact mode", "Two thin lines per value: the graph, then a gauge. Discreet, always readable."),
        "s4": ("Your grid, your way", "Put every value where you want it, a cell can span two columns."),
        "s5": ("Made for gaming", "The frame rate of the full screen game, next to the GPU load and temperature."),
        "tag": "Monitor Widget",
    },
}

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;700&family=Plus+Jakarta+Sans:wght@500;700;800&display=block');
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; background: #0b0d1a; }
body { position: relative; font-family: 'Plus Jakarta Sans', sans-serif; color: #f2f3f5; }
.wall { position: absolute; inset: 0; }
.wall.blue {
  background:
    radial-gradient(900px 700px at 78% 38%, rgba(76,110,255,.55), transparent 70%),
    radial-gradient(700px 600px at 95% 90%, rgba(171,71,188,.45), transparent 70%),
    radial-gradient(800px 700px at 10% 100%, rgba(38,166,154,.30), transparent 70%),
    linear-gradient(135deg, #0a0d24 0%, #121a46 55%, #1b0f3a 100%);
}
.wall.warm {
  background:
    radial-gradient(900px 700px at 75% 40%, rgba(255,152,0,.30), transparent 70%),
    radial-gradient(700px 600px at 95% 95%, rgba(244,67,54,.35), transparent 70%),
    radial-gradient(800px 700px at 15% 90%, rgba(76,175,80,.28), transparent 70%),
    linear-gradient(135deg, #0d1016 0%, #161a26 55%, #22121a 100%);
}
.wall.teal {
  background:
    radial-gradient(900px 700px at 72% 45%, rgba(38,166,154,.45), transparent 70%),
    radial-gradient(700px 600px at 98% 10%, rgba(66,165,245,.40), transparent 70%),
    radial-gradient(700px 600px at 20% 100%, rgba(171,71,188,.25), transparent 70%),
    linear-gradient(135deg, #071418 0%, #0d2230 55%, #111a35 100%);
}
.wall.violet {
  background:
    radial-gradient(900px 700px at 70% 45%, rgba(171,71,188,.50), transparent 70%),
    radial-gradient(700px 600px at 100% 100%, rgba(66,165,245,.35), transparent 70%),
    linear-gradient(135deg, #0e0a1f 0%, #1d1240 55%, #0b1530 100%);
}
.ribbons { position: absolute; inset: 0; opacity: .55; }
.copy { position: absolute; left: 130px; top: 50%; transform: translateY(-58%); width: 700px; }
.tag { display: inline-flex; align-items: center; gap: 14px; font-weight: 700; font-size: 26px;
       color: #c9cdf5; letter-spacing: .02em; margin-bottom: 34px; }
.tag i { width: 40px; height: 40px; border-radius: 11px; display: block;
         background: linear-gradient(135deg,#4caf50,#ff9800 60%,#f44336);
         box-shadow: 0 6px 20px rgba(255,152,0,.35); }
h1 { font-size: 84px; line-height: 1.04; font-weight: 800; letter-spacing: -.025em; margin-bottom: 30px; }
p { font-size: 32px; line-height: 1.45; color: #b9bdd0; font-weight: 500; }
.widget { position: absolute; filter: drop-shadow(0 30px 60px rgba(0,0,0,.55)) drop-shadow(0 4px 12px rgba(0,0,0,.4)); }
.widget svg { display: block; width: 100%; height: 100%; opacity: .94; }
.taskbar { position: absolute; left: 0; right: 0; bottom: 0; height: 56px;
           background: rgba(20,22,34,.72); backdrop-filter: blur(30px);
           border-top: 1px solid rgba(255,255,255,.08);
           display: flex; align-items: center; justify-content: center; gap: 10px; }
.taskbar b { width: 38px; height: 38px; border-radius: 9px; background: rgba(255,255,255,.10); display: block; }
.taskbar b.on { background: rgba(255,255,255,.18); }
.taskbar .clock { position: absolute; right: 26px; text-align: right; font: 400 15px/1.35 'Noto Sans', sans-serif; color: #e6e8ef; }
"""

RIBBONS = """<svg class="ribbons" viewBox="0 0 1920 1080" preserveAspectRatio="none">
<defs><linearGradient id="r1" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".6" stop-color="#fff" stop-opacity=".10"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>
<path d="M-50 860 C 400 760, 700 980, 1100 820 S 1700 560, 1980 640" stroke="url(#r1)" stroke-width="2" fill="none"/>
<path d="M-50 900 C 420 800, 720 1010, 1120 860 S 1720 600, 1980 690" stroke="url(#r1)" stroke-width="1.5" fill="none"/>
<path d="M-50 940 C 440 840, 740 1040, 1140 900 S 1740 640, 1980 740" stroke="url(#r1)" stroke-width="1" fill="none"/>
<path d="M600 -40 C 900 200, 1300 120, 1980 360" stroke="url(#r1)" stroke-width="1.5" fill="none"/>
<path d="M640 -40 C 940 230, 1340 160, 1980 400" stroke="url(#r1)" stroke-width="1" fill="none"/>
</svg>"""

TASKBAR = """<div class="taskbar"><b class="on"></b><b></b><b></b><b></b><b></b><b></b>
<div class="clock">{time}<br>{date}</div></div>"""


def widget(name, lang, x, y, scale):
    w, h = SIZES["%s_%s" % (name, lang)]
    return ('<div class="widget" style="left:%dpx;top:%dpx;width:%dpx;height:%dpx">'
            '%s</div>' % (x, y, w * scale, h * scale, inline(name, lang)))


def inline(name, lang):
    svg = open(os.path.join(SVG, "%s_%s.svg" % (name, lang)), encoding="utf-8").read()
    return svg.replace('font-family="Segoe UI, Selawik, sans-serif"', 'font-family="Noto Sans, sans-serif"')


def centered(name, lang, cx, cy, scale):
    w, h = SIZES["%s_%s" % (name, lang)]
    return widget(name, lang, cx - w * scale / 2, cy - h * scale / 2, scale)


def page(body, wall, lang, taskbar=True):
    date = "25/10/2026" if lang == "fr" else "10/25/2026"
    bar = TASKBAR.format(time="14:32" if lang == "fr" else "2:32 PM", date=date) if taskbar else ""
    return ("<!doctype html><html><head><meta charset='utf-8'><style>%s</style></head>"
            "<body><div class='wall %s'></div>%s%s%s</body></html>"
            % (BASE_CSS, wall, RIBBONS, body, bar))


def copy(lang, key):
    title, text = TEXT[lang][key]
    return ("<div class='copy'><div class='tag'><i></i>%s</div><h1>%s</h1><p>%s</p></div>"
            % (TEXT[lang]["tag"], title, text))


GAME_CSS = """<style>
.wall.game { background: linear-gradient(180deg, #1a1030 0%, #3b1d4a 40%, #c2563a 72%, #f2a34a 82%, #2a1622 83%, #120a14 100%); }
.sun { position:absolute; left: 1180px; top: 560px; width: 360px; height: 360px; border-radius: 50%;
       background: radial-gradient(circle, #ffd08a 0%, #ff8a3d 55%, rgba(255,90,60,0) 72%); }
.hills { position:absolute; inset:0; }
.shade { position:absolute; inset:0; background: linear-gradient(90deg, rgba(8,6,16,.88) 0%, rgba(8,6,16,.6) 38%, rgba(8,6,16,0) 60%); }
.hud { position:absolute; right: 60px; bottom: 50px; font: 700 22px 'Noto Sans'; color: rgba(255,255,255,.75); letter-spacing:.1em; }
</style>"""

HILLS = """<svg class="hills" viewBox="0 0 1920 1080" preserveAspectRatio="none">
<path d="M0 760 L180 640 L330 720 L520 560 L700 700 L860 620 L1040 730 L1240 600 L1420 700 L1600 580 L1780 690 L1920 640 L1920 1080 L0 1080Z" fill="#2a1430"/>
<path d="M0 860 L220 760 L420 840 L640 740 L900 860 L1120 770 L1360 870 L1600 760 L1920 850 L1920 1080 L0 1080Z" fill="#160b1c"/>
<path d="M0 960 L300 900 L620 950 L980 890 L1300 960 L1640 900 L1920 940 L1920 1080 L0 1080Z" fill="#0a050d"/>
</svg>"""


def scenes(lang):
    s = {}
    s["01_apercu"] = page(copy(lang, "s1") + centered("normal", lang, 1400, 500, 2.5), "blue", lang)
    trio = (widget("cpu_low", lang, 1000, 300, 2.2) + widget("cpu_mid", lang, 1000, 520, 2.2)
            + widget("cpu_high", lang, 1000, 740, 2.2))
    s["02_couleurs"] = page(copy(lang, "s2") + trio, "warm", lang)
    s["03_compact"] = page(copy(lang, "s3") + centered("compact", lang, 1400, 500, 2.6), "teal", lang)
    s["04_grille"] = page(copy(lang, "s4") + centered("custom", lang, 1340, 500, 2.4), "violet", lang)
    game = (GAME_CSS + "<div class='sun'></div>" + HILLS + "<div class='shade'></div>"
            + copy(lang, "s5") + widget("game", lang, 1420, 60, 1.9))
    s["05_jeu"] = page(game, "game", lang, taskbar=False)
    return s


def hero():
    """Presentation image, no text: the three display modes floating."""
    lang = "fr"
    body = ("<style>.wall.hero{background:"
            "radial-gradient(700px 600px at 50% 45%, rgba(76,110,255,.55), transparent 70%),"
            "radial-gradient(800px 700px at 15% 80%, rgba(38,166,154,.40), transparent 70%),"
            "radial-gradient(800px 700px at 88% 20%, rgba(171,71,188,.45), transparent 70%),"
            "radial-gradient(600px 500px at 85% 95%, rgba(255,152,0,.25), transparent 70%),"
            "linear-gradient(135deg,#0a0d24 0%,#121a46 55%,#1b0f3a 100%);}</style>"
            + centered("compact", lang, 420, 560, 2.2)
            + centered("normal", lang, 960, 520, 2.5)
            + centered("custom", lang, 1520, 560, 1.9))
    return ("<!doctype html><html><head><meta charset='utf-8'><style>%s</style></head>"
            "<body><div class='wall hero'></div>%s%s</body></html>" % (BASE_CSS, RIBBONS, body))


def render(html_path, png_path):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--window-size=1920,1080",
                    "--virtual-time-budget=4000", "--allow-file-access-from-files",
                    "--screenshot=" + png_path, "file://" + html_path],
                   check=True, capture_output=True)


def main():
    os.makedirs(PAGES, exist_ok=True)
    jobs = {}
    for lang in ("fr", "en"):
        for name, html in scenes(lang).items():
            jobs["%s/%s" % (lang, name)] = html
    jobs["presentation/presentation"] = hero()
    only = sys.argv[1:]
    for key, html in jobs.items():
        if only and not any(o in key for o in only):
            continue
        folder, name = key.split("/")
        os.makedirs(os.path.join(OUT, folder), exist_ok=True)
        html_path = os.path.join(PAGES, "%s_%s.html" % (folder, name))
        open(html_path, "w", encoding="utf-8").write(html)
        render(html_path, os.path.join(OUT, folder, name + ".png"))
        print("ok", key)


main()
