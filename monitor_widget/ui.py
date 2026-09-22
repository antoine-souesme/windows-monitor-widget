# -*- coding: utf-8 -*-
"""The widget window: drawing, dragging and context menu."""

import tkinter as tk
import tkinter.font as tkfont
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
PADDING = 10             # empty space above the first block and below the last
BLOCK_HEIGHT = 70        # one metric: caption, large number, graph
BLOCK_GAP = 10
COMPACT_HEIGHT = 26      # one metric on a single line, graph behind it
COMPACT_GAP = 6
COLUMN_GAP = 10          # empty space between two values of the same metric
BLOCK_SIZES = [22, 18, 15, 12, 10]    # font sizes tried for the large number
COMPACT_SIZES = [13, 11, 10, 9]
PREFIX_SIZE = 13         # the mark before a number, never resized with it
COMPACT_PREFIX_SIZE = 10
PREFIX_GAP = 5           # empty space between that mark and the number
EMPTY_HEIGHT = 60        # height used when no metric is selected
EMPTY_TEXT = "Veuillez sélectionner une métrique à afficher"


def window_height(count, compact):
    """Height needed to stack `count` metric blocks."""
    if count < 1:
        return EMPTY_HEIGHT
    block = COMPACT_HEIGHT if compact else BLOCK_HEIGHT
    gap = COMPACT_GAP if compact else BLOCK_GAP
    return 2 * PADDING + count * block + (count - 1) * gap


_FONTS = {}


def _bold(size):
    """Bold font of that size, created once."""
    font = _FONTS.get(size)
    if font is None:
        font = _FONTS[size] = tkfont.Font(family="Segoe UI", size=size,
                                          weight="bold")
    return font


def fitting_font(text, width, sizes):
    """Largest of `sizes` writing `text` within `width` pixels."""
    for size in sizes:
        try:
            if _bold(size).measure(text) <= width:
                return ("Segoe UI", size, "bold")
        except tk.TclError:
            break
    return ("Segoe UI", sizes[-1], "bold")


def text_width(text, font):
    """Width of a text in pixels, 0 when nothing can be measured."""
    try:
        return _bold(font[1]).measure(text)
    except tk.TclError:
        return 0


def columns(left, right, count):
    """Split a width into `count` side by side areas."""
    if count < 2:
        return [(left, right)]
    span = (right - left - COLUMN_GAP * (count - 1)) / float(count)
    return [(left + index * (span + COLUMN_GAP),
             left + index * (span + COLUMN_GAP) + span) for index in range(count)]


def _as_values(read):
    """A metric returns one number, or one per column: normalize to a tuple."""
    if isinstance(read, (list, tuple)):
        return tuple(float(value) for value in read) or (0.0,)
    return (float(read),)


def _blank_history(count):
    """Sixty empty samples, so a new graph starts flat instead of jumping."""
    return deque([(0.0,) * count] * HISTORY_POINTS, maxlen=HISTORY_POINTS)


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

        self._setup_window()
        self._build_canvas()
        self._build_menu()
        self._restore_position()
        self._draw()
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
        selected = [probe.key for probe in self.probes]
        self.probe_vars = {key: tk.BooleanVar(value=key in selected)
                           for key in probes.PROBES}

        self.menu = tk.Menu(self, tearoff=0)
        # Plain caption, so the installed version is visible without a window.
        self.menu.add_command(label="Monitor Widget {}".format(__version__), state="disabled")
        self.menu.add_separator()
        metrics = tk.Menu(self.menu, tearoff=0)
        for key, cls in probes.PROBES.items():
            metrics.add_checkbutton(label=cls.label,
                                    variable=self.probe_vars[key],
                                    command=self._change_probes)
        self.menu.add_cascade(label="Métriques affichées", menu=metrics)
        self._build_option_menu()
        self.menu.add_separator()
        self.menu.add_checkbutton(label="Mode compact",
                                  variable=self.compact_var,
                                  command=self._toggle_compact)
        # In a Store package Windows owns the auto start.
        if not system.is_packaged():
            self.menu.add_checkbutton(label="Lancer au démarrage",
                                      variable=self.startup_var,
                                      command=self._toggle_startup)
        self.menu.add_checkbutton(label="Toujours au premier plan",
                                  variable=self.on_top_var,
                                  command=self._toggle_on_top)
        self.menu.add_separator()
        self.menu.add_command(label="Quitter", command=self.quit_widget)

    def _build_option_menu(self):
        """One sub menu per metric offering choices, built from probes.py."""
        self.option_vars = {}
        families = probes.options()
        if not families:
            return
        root = tk.Menu(self.menu, tearoff=0)
        for cls in families:
            family = tk.Menu(root, tearoff=0)
            for option in cls.options:
                variable = tk.StringVar(value=self.values[option.key])
                self.option_vars[option.key] = variable
                for value, label in option.choices:
                    family.add_radiobutton(
                        label=label, value=value, variable=variable,
                        command=lambda key=option.key: self._change_option(key))
            root.add_cascade(label=cls.label, menu=family)
        self.menu.add_cascade(label="Options des métriques", menu=root)

    def _change_option(self, key):
        """Store a choice and hand it over to the metrics right away."""
        self.values[key] = self.option_vars[key].get()
        config.save(self.values)
        for probe in self.probes:
            probe.configure(self.values)
            # A choice can add or remove a column: start that graph over.
            if len(self.histories[probe.key][-1]) != probe.columns():
                self.histories[probe.key] = _blank_history(probe.columns())
        self._draw()

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
                values = _as_values(probe.read())
            except Exception:
                values = (0.0,)
            history = self.histories[probe.key]
            # An option can change how many values a metric returns.
            if len(history[-1]) != len(values):
                history = self.histories[probe.key] = _blank_history(len(values))
            history.append(values)
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

    def _last(self, probe):
        """Most recent sample of a metric, zeros before the first one."""
        history = self.histories[probe.key]
        return history[-1] if history else (0.0,)

    def _draw_block(self, probe, top, block):
        """Caption, large number, then the graph underneath. A metric showing
        several values gets one number and one graph per column."""
        width = self.values["width"]
        values = self._last(probe)
        texts = probe.texts(values)
        self.canvas.create_text(MARGIN, top + 6, anchor="w", text=probe.label,
                                fill=CAPTION, font=("Segoe UI", 9))
        areas = columns(MARGIN, width - MARGIN, len(values))
        for index, (x0, x1) in enumerate(areas):
            prefix, prefix_font, font = self._fonts(probe, index, texts[index],
                                                    x1 - x0, BLOCK_SIZES,
                                                    PREFIX_SIZE)
            x = x0
            if prefix:
                self.canvas.create_text(x, top + 30, anchor="w", text=prefix,
                                        fill=TEXT, font=prefix_font)
                x += text_width(prefix, prefix_font) + PREFIX_GAP
            self.canvas.create_text(x, top + 30, anchor="w", text=texts[index],
                                    fill=TEXT, font=font)
            self._draw_graph(probe, index, x0, top + 44, x1, top + block,
                             self._color(probe, values[index], index))

    def _draw_compact_block(self, probe, top, block):
        """One line: the graph fills the block, caption and number on top."""
        width = self.values["width"]
        values = self._last(probe)
        texts = probe.texts(values)
        middle = top + block // 2
        single = len(values) == 1
        if single:
            # The caption has room only when one number shares the line.
            self.canvas.create_text(MARGIN, middle, anchor="w", text=probe.label,
                                    fill=CAPTION, font=("Segoe UI", 9))
        areas = columns(MARGIN, width - MARGIN, len(values))
        for index, (x0, x1) in enumerate(areas):
            self._draw_graph(probe, index, x0, top, x1, top + block,
                             self._color(probe, values[index], index),
                             baseline=False)
            prefix, prefix_font, font = self._fonts(probe, index, texts[index],
                                                    x1 - x0, COMPACT_SIZES,
                                                    COMPACT_PREFIX_SIZE)
            self.canvas.create_text(x1, middle, anchor="e", text=texts[index],
                                    fill=TEXT, font=font)
            if prefix:
                # Placed on the room the widest number needs, not on the
                # current one, so it does not walk as the figure changes.
                x = x1 - text_width(self._template(probe, texts[index]), font)
                self.canvas.create_text(x - PREFIX_GAP, middle, anchor="e",
                                        text=prefix, fill=TEXT,
                                        font=prefix_font)

    @staticmethod
    def _template(probe, text):
        """Widest text the metric can write, the current one if it says
        nothing. A broken metric must not stop the drawing."""
        try:
            return probe.template() or text
        except Exception:
            return text

    @classmethod
    def _fonts(cls, probe, index, text, room, sizes, prefix_size):
        """Fixed size mark shown before the number, and the font of the
        number itself, chosen on the widest text so it never resizes."""
        try:
            prefixes = probe.prefixes()
        except Exception:
            prefixes = []
        prefix = prefixes[index] if index < len(prefixes) else None
        prefix_font = None
        if prefix:
            prefix_font = ("Segoe UI", prefix_size, "bold")
            room -= text_width(prefix, prefix_font) + PREFIX_GAP
        return prefix, prefix_font, fitting_font(cls._template(probe, text),
                                                 room, sizes)

    def _color(self, probe, value, column):
        """Color of one column: the metric decides, or the green to red scale."""
        return probe.tint(column) or load_color(probe.ratio(value, column))

    def _draw_graph(self, probe, column, x0, y0, x1, y1, color, baseline=True):
        """Scrolling graph of the last 60 samples of one column."""
        if baseline:
            self.canvas.create_line(x0, y1, x1, y1, fill=BORDER)
        samples = [sample[column] for sample in self.histories[probe.key]
                   if column < len(sample)]
        if len(samples) < 2:
            return
        step = (x1 - x0) / float(len(samples) - 1)
        span = max(1, y1 - y0)
        points = []
        for index, sample in enumerate(samples):
            points.append(x0 + index * step)
            points.append(y1 - probe.ratio(sample, column) * span)
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
        if not system.is_packaged():
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
                probe.configure(self.values)
                probe.start()
            kept.append(probe)
            histories[key] = self.histories.get(
                key, _blank_history(probe.columns()))
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
