# -*- coding: utf-8 -*-
"""The widget window: drawing, dragging and context menu."""

import threading
import time
import tkinter as tk
from collections import deque

from . import config, probes, system, updater
from .version import __version__

# Palette.
BACKGROUND = "#1e1f24"
BORDER = "#3a3d46"
TEXT = "#f2f3f5"
CAPTION = "#9aa0aa"
TRANSPARENT = "#ff00fe"        # unlikely tint, turned invisible by Windows
SCALE = [(0.0, (0x4c, 0xaf, 0x50)),   # green
         (0.6, (0xff, 0x98, 0x00)),   # orange
         (1.0, (0xf4, 0x43, 0x36))]   # red

HISTORY_POINTS = 60      # 60 seconds of history
REFRESH_MS = 1000        # one sample per second
MARGIN = 12
PADDING = 10             # empty space above the first block and below the last
BLOCK_HEIGHT = 70        # one metric: caption, large number, graph
BLOCK_GAP = 10
COMPACT_HEIGHT = 26      # one metric on a single line, graph behind it
COMPACT_GAP = 6
EMPTY_HEIGHT = 60        # height used when no metric is selected
EMPTY_TEXT = "Veuillez sélectionner une métrique à afficher"
UPDATE_COLOR = "#4caf50"   # the dot shown when a new version is available
UPDATE_DOT = 5             # its radius
UPDATE_DELAY_MS = 30000    # time left to the widget to settle before checking
UPDATE_POLL_MS = 3600000   # how often the daily deadline is looked at again


def window_height(count, compact):
    """Height needed to stack `count` metric blocks."""
    if count < 1:
        return EMPTY_HEIGHT
    block = COMPACT_HEIGHT if compact else BLOCK_HEIGHT
    gap = COMPACT_GAP if compact else BLOCK_GAP
    return 2 * PADDING + count * block + (count - 1) * gap


def load_color(ratio):
    """Interpolate the green -> orange -> red color for a 0..1 load."""
    ratio = max(0.0, min(ratio, 1.0))
    for index in range(len(SCALE) - 1):
        start, start_color = SCALE[index]
        end, end_color = SCALE[index + 1]
        if ratio <= end:
            position = 0.0 if end == start else (ratio - start) / (end - start)
            channels = [int(start_color[i] + (end_color[i] - start_color[i]) * position)
                        for i in range(3)]
            return "#%02x%02x%02x" % tuple(channels)
    return "#%02x%02x%02x" % SCALE[-1][1]


class WidgetWindow(tk.Toplevel):
    """Small borderless window sitting on the desktop."""

    def __init__(self, root, values):
        super().__init__(root)
        self.values = values
        self.probes = []
        self.histories = {}
        self._apply_selection(values["probes"])
        self._drag_origin = None
        self._dragged = False
        self._job = None
        self._update_job = None
        self._available_update = None

        self._setup_window()
        self._build_canvas()
        self._build_menu()
        self._restore_position()
        self._draw()
        self._schedule_sample()
        self._schedule_update_check()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self):
        self.overrideredirect(True)                       # no border
        self.attributes("-alpha", 0.88)                   # slightly translucent
        self.attributes("-topmost", self.values["always_on_top"])
        self.configure(bg=TRANSPARENT)
        try:
            # Makes the corners outside the rounded rectangle truly invisible.
            self.attributes("-transparentcolor", TRANSPARENT)
            self._canvas_background = TRANSPARENT
        except tk.TclError:
            self._canvas_background = BACKGROUND
        self.update_idletasks()
        system.apply_tool_window_style(self)
        system.round_corners(self)

    def _build_canvas(self):
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=self._canvas_background,
                                width=self.values["width"],
                                height=self._height())
        self.canvas.pack(fill="both", expand=True)
        # Drag anywhere on the surface.
        self.canvas.bind("<Button-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<Button-3>", self._open_menu)

    def _build_menu(self):
        self.startup_var = tk.BooleanVar(value=system.is_startup_enabled())
        self.on_top_var = tk.BooleanVar(value=self.values["always_on_top"])
        self.compact_var = tk.BooleanVar(value=self.values["compact"])
        self.updates_var = tk.BooleanVar(value=self.values["check_updates"])
        selected = [probe.key for probe in self.probes]
        self.probe_vars = {key: tk.BooleanVar(value=key in selected)
                           for key in probes.PROBES}

        self.menu = tk.Menu(self, tearoff=0)
        # Plain caption, so the installed version is visible without a window.
        self.menu.add_command(label="Monitor Widget {}".format(__version__), state="disabled")
        # The update entry is inserted right here, but only once a newer
        # release has been found (see _show_update).
        self.menu.add_separator()
        metrics = tk.Menu(self.menu, tearoff=0)
        for key, cls in probes.PROBES.items():
            metrics.add_checkbutton(label=cls.label,
                                    variable=self.probe_vars[key],
                                    command=self._change_probes)
        self.menu.add_cascade(label="Données affichées", menu=metrics)
        self.menu.add_separator()
        self.menu.add_checkbutton(label="Mode compact",
                                  variable=self.compact_var,
                                  command=self._toggle_compact)
        self.menu.add_checkbutton(label="Lancer au démarrage",
                                  variable=self.startup_var,
                                  command=self._toggle_startup)
        self.menu.add_checkbutton(label="Toujours au premier plan",
                                  variable=self.on_top_var,
                                  command=self._toggle_on_top)
        self.menu.add_checkbutton(label="Vérifier les mises à jour",
                                  variable=self.updates_var,
                                  command=self._toggle_updates)
        self.menu.add_separator()
        self.menu.add_command(label="Quitter", command=self.quit_widget)

    def _restore_position(self):
        """Restore the saved position, or recenter when it is off screen."""
        width, height = self.values["width"], self._height()
        x, y = self.values["x"], self.values["y"]
        on_screen = (x is not None and y is not None
                     and system.is_point_on_screen(x + width // 2, y + height // 2, self)
                     and system.is_point_on_screen(x + 2, y + 2, self))
        if not on_screen:
            x = (self.winfo_screenwidth() - width) // 2
            y = (self.winfo_screenheight() - height) // 2
        self.values["x"], self.values["y"] = x, y
        self.geometry("{}x{}+{}+{}".format(width, height, x, y))

    # ------------------------------------------------------------------
    # Sampling and drawing
    # ------------------------------------------------------------------

    def _schedule_sample(self):
        self._job = self.after(REFRESH_MS, self._sample)

    def _sample(self):
        for probe in self.probes:
            try:
                value = float(probe.read())
            except Exception:
                value = 0.0
            self.histories[probe.key].append(value)
        self._draw()
        self._schedule_sample()

    def _draw(self):
        width, height = self.values["width"], self._height()
        self.canvas.delete("all")
        self._rounded_rectangle(1, 1, width - 1, height - 1, 12,
                                fill=BACKGROUND, outline=BORDER)
        if not self.probes:
            self.canvas.create_text(width // 2, height // 2, text=EMPTY_TEXT,
                                    fill=CAPTION, font=("Segoe UI", 9),
                                    width=width - 2 * MARGIN, justify="center")
        else:
            compact = self.values["compact"]
            block = COMPACT_HEIGHT if compact else BLOCK_HEIGHT
            gap = COMPACT_GAP if compact else BLOCK_GAP
            top = PADDING
            for probe in self.probes:
                if compact:
                    self._draw_compact_block(probe, top, block)
                else:
                    self._draw_block(probe, top, block)
                top += block + gap
        # Drawn last, so no graph ever covers it.
        if self._available_update:
            self._draw_update_dot(width)

    def _last(self, probe):
        """Most recent sample of a metric, 0 before the first one."""
        history = self.histories[probe.key]
        return history[-1] if history else 0.0

    def _draw_block(self, probe, top, block):
        """Caption, large number, then the graph underneath."""
        width = self.values["width"]
        value = self._last(probe)
        color = load_color(probe.ratio(value))
        self.canvas.create_text(MARGIN, top + 6, anchor="w", text=probe.label,
                                fill=CAPTION, font=("Segoe UI", 9))
        self.canvas.create_text(MARGIN, top + 30, anchor="w",
                                text=probe.format(value),
                                fill=TEXT, font=("Segoe UI", 22, "bold"))
        self._draw_graph(probe, MARGIN, top + 44, width - MARGIN, top + block, color)

    def _draw_compact_block(self, probe, top, block):
        """One line: the graph fills the block, caption and number on top."""
        width = self.values["width"]
        value = self._last(probe)
        color = load_color(probe.ratio(value))
        self._draw_graph(probe, MARGIN, top, width - MARGIN, top + block, color,
                         baseline=False)
        middle = top + block // 2
        self.canvas.create_text(MARGIN, middle, anchor="w", text=probe.label,
                                fill=CAPTION, font=("Segoe UI", 9))
        self.canvas.create_text(width - MARGIN, middle, anchor="e",
                                text=probe.format(value),
                                fill=TEXT, font=("Segoe UI", 13, "bold"))

    def _draw_graph(self, probe, x0, y0, x1, y1, color, baseline=True):
        """Scrolling graph of the last 60 samples of one metric."""
        if baseline:
            self.canvas.create_line(x0, y1, x1, y1, fill=BORDER)
        samples = list(self.histories[probe.key])
        if len(samples) < 2:
            return
        step = (x1 - x0) / float(len(samples) - 1)
        span = max(1, y1 - y0)
        points = []
        for index, sample in enumerate(samples):
            points.append(x0 + index * step)
            points.append(y1 - probe.ratio(sample) * span)
        # Shaded area first, then the curve itself.
        self.canvas.create_polygon(points + [x1, y1, x0, y1],
                                   fill=color, outline="", stipple="gray25")
        self.canvas.create_line(points, fill=color, width=1.5, smooth=True)

    def _rounded_rectangle(self, x0, y0, x1, y1, radius, fill, outline):
        """Rounded rectangle drawn as a smoothed polygon."""
        points = [x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius,
                  x1, y1 - radius, x1, y1, x1 - radius, y1, x0 + radius, y1,
                  x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0]
        self.canvas.create_polygon(points, fill=fill, outline=outline,
                                   smooth=True, splinesteps=12)

    # ------------------------------------------------------------------
    # Dragging
    # ------------------------------------------------------------------

    def _start_drag(self, event):
        self._drag_origin = (event.x_root - self.winfo_x(),
                             event.y_root - self.winfo_y())
        self._dragged = False

    def _drag(self, event):
        if self._drag_origin is None:
            return
        offset_x, offset_y = self._drag_origin
        self.geometry("+{}+{}".format(event.x_root - offset_x,
                                      event.y_root - offset_y))
        self._dragged = True

    def _end_drag(self, _event):
        self._drag_origin = None
        if not self._dragged:
            return
        # The file is only written once the move is over.
        self.values["x"] = self.winfo_x()
        self.values["y"] = self.winfo_y()
        config.save(self.values)
        self._dragged = False

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _open_menu(self, event):
        # The check box always mirrors the real registry state.
        self.startup_var.set(system.is_startup_enabled())
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _toggle_startup(self):
        actual = system.set_startup_enabled(self.startup_var.get())
        self.startup_var.set(actual)

    def _toggle_on_top(self):
        self.values["always_on_top"] = self.on_top_var.get()
        self.attributes("-topmost", self.values["always_on_top"])
        config.save(self.values)

    def _change_probes(self):
        selected = [key for key in probes.PROBES if self.probe_vars[key].get()]
        self._apply_selection(selected)
        self.values["probes"] = [probe.key for probe in self.probes]
        config.save(self.values)
        self._resize()

    def _toggle_updates(self):
        self.values["check_updates"] = self.updates_var.get()
        config.save(self.values)
        if self.values["check_updates"]:
            self._schedule_update_check()

    def _toggle_compact(self):
        self.values["compact"] = self.compact_var.get()
        config.save(self.values)
        self._resize()

    def _apply_selection(self, keys):
        """Rebuild the list of probes, keeping the history of those already
        displayed so switching an unrelated metric does not reset the graphs."""
        kept = []
        histories = {}
        for key in keys:
            cls = probes.PROBES.get(key)
            if cls is None or key in histories:
                continue
            probe = next((p for p in self.probes if p.key == key), None)
            if probe is None:
                probe = cls()
                probe.start()
            kept.append(probe)
            histories[key] = self.histories.get(
                key, deque([0.0] * HISTORY_POINTS, maxlen=HISTORY_POINTS))
        self.probes = kept
        self.histories = histories

    def _height(self):
        return window_height(len(self.probes), self.values["compact"])

    def _resize(self):
        """Give the window the height its content needs, then redraw."""
        height = self._height()
        self.canvas.configure(height=height)
        if self.winfo_ismapped():
            # Keep the top left corner where the user left it.
            self.values["x"], self.values["y"] = self.winfo_x(), self.winfo_y()
        self.geometry("{}x{}+{}+{}".format(self.values["width"], height,
                                           self.values["x"], self.values["y"]))
        self._draw()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _schedule_update_check(self, delay=UPDATE_DELAY_MS):
        """Arm the next look at GitHub, without stacking two timers."""
        self._cancel_update_job()
        if not self.values["check_updates"]:
            return
        self._update_job = self.after(delay, self._update_tick)

    def _update_tick(self):
        """Check when the day has passed, then come back later anyway: the
        widget can stay open far longer than the interval."""
        self._update_job = None
        if self._available_update or not self.values["check_updates"]:
            return
        if updater.should_check(self.values["last_update_check"]):
            self.values["last_update_check"] = time.time()
            config.save(self.values)
            updater.check_in_background(self._update_found)
        self._schedule_update_check(UPDATE_POLL_MS)

    def _cancel_update_job(self):
        if self._update_job is None:
            return
        try:
            self.after_cancel(self._update_job)
        except tk.TclError:
            pass
        self._update_job = None

    def _update_found(self, release):
        """Called from the background thread: come back to the UI thread."""
        if release is None:
            return
        try:
            self.after(0, lambda: self._show_update(release))
        except (tk.TclError, RuntimeError):
            # The window is already gone: nothing left to show.
            pass

    def _show_update(self, release):
        """Add the menu entry and the dot telling a version is waiting."""
        if self._available_update:
            return
        self._available_update = release
        self.menu.insert_command(
            1, label="Mettre à jour vers {}".format(release.version),
            command=self._install_update)
        self._draw()

    def _install_update(self):
        """Download the installer in the background, then step aside."""
        release = self._available_update
        if release is None:
            return
        self._available_update = None      # no second click during the download
        self.menu.delete(1)
        self._draw()

        def fetch():
            path = updater.download(release)
            try:
                self.after(0, lambda: self._installer_ready(release, path))
            except (tk.TclError, RuntimeError):
                pass

        threading.Thread(target=fetch, name="update-download", daemon=True).start()

    def _installer_ready(self, release, path):
        """Start the downloaded installer, or put the entry back on failure."""
        if path is not None and updater.install(path):
            # The installer replaces the files, so the running copy must stop.
            self.quit_widget()
            return
        self._show_update(release)

    def _draw_update_dot(self, width):
        """Small colored dot in the top right corner of the widget."""
        x = width - MARGIN + 2
        self.canvas.create_oval(x - UPDATE_DOT, MARGIN - UPDATE_DOT,
                                x + UPDATE_DOT, MARGIN + UPDATE_DOT,
                                fill=UPDATE_COLOR, outline="")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def quit_widget(self):
        self._cancel_update_job()
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self.values["x"] = self.winfo_x()
        self.values["y"] = self.winfo_y()
        config.save(self.values)
        self.master.destroy()
