# -*- coding: utf-8 -*-
"""The widget window: drawing, dragging and context menu."""

import tkinter as tk
from collections import deque

from . import config, probes, system
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
        self.probe = probes.get(values["probe"])
        self.probe.start()
        self.history = deque([0.0] * HISTORY_POINTS, maxlen=HISTORY_POINTS)
        self._drag_origin = None
        self._dragged = False
        self._job = None

        self._setup_window()
        self._build_canvas()
        self._build_menu()
        self._restore_position()
        self._draw(0.0)
        self._schedule_sample()

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
                                height=self.values["height"])
        self.canvas.pack(fill="both", expand=True)
        # Drag anywhere on the surface.
        self.canvas.bind("<Button-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<Button-3>", self._open_menu)

    def _build_menu(self):
        self.startup_var = tk.BooleanVar(value=system.is_startup_enabled())
        self.on_top_var = tk.BooleanVar(value=self.values["always_on_top"])
        self.probe_var = tk.StringVar(value=self.probe.key)

        self.menu = tk.Menu(self, tearoff=0)
        # Plain caption, so the installed version is visible without a window.
        self.menu.add_command(label="CPU Widget {}".format(__version__), state="disabled")
        self.menu.add_separator()
        metrics = tk.Menu(self.menu, tearoff=0)
        for key, cls in probes.PROBES.items():
            metrics.add_radiobutton(label=cls.label, value=key,
                                    variable=self.probe_var,
                                    command=self._change_probe)
        self.menu.add_cascade(label="Données affichées", menu=metrics)
        self.menu.add_separator()
        self.menu.add_checkbutton(label="Lancer au démarrage",
                                  variable=self.startup_var,
                                  command=self._toggle_startup)
        self.menu.add_checkbutton(label="Toujours au premier plan",
                                  variable=self.on_top_var,
                                  command=self._toggle_on_top)
        self.menu.add_separator()
        self.menu.add_command(label="Quitter", command=self.quit_widget)

    def _restore_position(self):
        """Restore the saved position, or recenter when it is off screen."""
        width, height = self.values["width"], self.values["height"]
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
        try:
            value = float(self.probe.read())
        except Exception:
            value = 0.0
        self.history.append(value)
        self._draw(value)
        self._schedule_sample()

    def _draw(self, value):
        width, height = self.values["width"], self.values["height"]
        color = load_color(self.probe.ratio(value))
        self.canvas.delete("all")
        self._rounded_rectangle(1, 1, width - 1, height - 1, 12,
                                fill=BACKGROUND, outline=BORDER)
        self.canvas.create_text(MARGIN, 16, anchor="w", text=self.probe.label,
                                fill=CAPTION, font=("Segoe UI", 9))
        self.canvas.create_text(MARGIN, 40, anchor="w", text=self.probe.format(value),
                                fill=TEXT, font=("Segoe UI", 22, "bold"))
        self._draw_graph(MARGIN, height - 32, width - MARGIN, height - MARGIN, color)

    def _draw_graph(self, x0, y0, x1, y1, color):
        """Scrolling graph of the last 60 samples."""
        self.canvas.create_line(x0, y1, x1, y1, fill=BORDER)
        samples = list(self.history)
        if len(samples) < 2:
            return
        step = (x1 - x0) / float(len(samples) - 1)
        span = max(1, y1 - y0)
        points = []
        for index, sample in enumerate(samples):
            points.append(x0 + index * step)
            points.append(y1 - self.probe.ratio(sample) * span)
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

    def _change_probe(self):
        self.probe = probes.get(self.probe_var.get())
        self.probe.start()
        self.history = deque([0.0] * HISTORY_POINTS, maxlen=HISTORY_POINTS)
        self.values["probe"] = self.probe.key
        config.save(self.values)
        self._draw(0.0)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def quit_widget(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
        self.values["x"] = self.winfo_x()
        self.values["y"] = self.winfo_y()
        config.save(self.values)
        self.master.destroy()
