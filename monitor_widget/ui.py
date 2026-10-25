# -*- coding: utf-8 -*-
"""The widget window: drawing, dragging, context menu and notification area
icon. The settings live in the options window (options.py)."""

import tkinter as tk
import tkinter.font as tkfont
from collections import deque

from . import config, grid, i18n, probes, system
from .i18n import tr
from .options import OptionsWindow

# Palette.
BACKGROUND = "#1e1f24"
BORDER = "#3a3d46"
TEXT = "#f2f3f5"
CAPTION = "#9aa0aa"
OUTLINE = "#000000"            # dark rim keeping texts readable over a graph
TRANSPARENT = "#ff00fe"        # unlikely tint, turned invisible by Windows
SCALE = [(0.0, (0x4c, 0xaf, 0x50)),   # green
         (0.6, (0xff, 0x98, 0x00)),   # orange
         (1.0, (0xf4, 0x43, 0x36))]   # red

HISTORY_POINTS = 60      # 60 seconds of history
REFRESH_MS = 1000        # one sample per second
FRAME_MS = 33            # about 30 frames per second while the gauge moves
EASING = 0.2             # share of the remaining distance covered per frame
SETTLED = 0.002          # the gauge stops moving below that distance
MARGIN = 12
PADDING = 10             # empty space above the first block and below the last
BLOCK_HEIGHT = 70        # one metric: caption, large number, graph
BLOCK_GAP = 10
COMPACT_HEIGHT = 36      # one value: graph with its texts over it, then gauge
COMPACT_GAP = 6
COMPACT_GRAPH = 24       # height of the graph row, the gauge row takes the rest
GAUGE_GAP = 4            # empty space between that graph and the gauge
GAUGE_THICKNESS = 6      # height of the bar showing the current value
FILL_SHARE = 0.35        # share of the value color in the area under a curve
SHADE_SHARE = 0.25       # same, for the lighter shade of the tall blocks
COLUMN_GAP = 10          # empty space between two values of the same metric
BLOCK_SIZES = [22, 18, 15, 12, 10]    # font sizes tried for the large number
COMPACT_SIZES = [10, 9, 8, 7]
PREFIX_SIZE = 13         # the mark before a number, never resized with it
PREFIX_GAP = 5           # empty space between that mark and the number
RESIZE_BORDER = 6        # strip along the sides that resizes instead of moving
EMPTY_HEIGHT = 60        # height used when no metric is selected
EMPTY_TEXT = "Veuillez sélectionner une métrique à afficher"


def window_height(count, compact):
    """Height needed to stack `count` metric blocks, or `count` values in
    compact mode, where each value of a metric gets lines of its own."""
    if count < 1:
        return EMPTY_HEIGHT
    block = COMPACT_HEIGHT if compact else BLOCK_HEIGHT
    gap = COMPACT_GAP if compact else BLOCK_GAP
    return 2 * PADDING + count * block + (count - 1) * gap


def grid_height(rows):
    """Height of a custom grid of `rows` rows of compact lines."""
    return window_height(rows, True)


_FONTS = {}


def held_font(spec):
    """Font object of a ("Segoe UI", size[, "bold"]) tuple, created once.
    Handed a tuple, the canvas builds a Windows font on every drawing and
    frees it with the items: thirty times a second, that churn ends up
    exhausting the graphic resources of Windows (CreateDIBSection error)."""
    font = _FONTS.get(spec)
    if font is None:
        weight = spec[2] if len(spec) > 2 else "normal"
        font = _FONTS[spec] = tkfont.Font(family=spec[0], size=spec[1],
                                          weight=weight)
    return font


def _bold(size):
    """Bold font of that size, created once."""
    return held_font(("Segoe UI", size, "bold"))


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


def resize_edge(x, width):
    """Side grabbed by a click at `x` inside the window, None in the middle."""
    if x < RESIZE_BORDER:
        return "left"
    if x >= width - RESIZE_BORDER:
        return "right"
    return None


def resized(edge, x, width, moved):
    """Left position and width after dragging `edge` by `moved` pixels. The
    opposite side stays where it is."""
    if edge == "left":
        new_width = max(config.MIN_WIDTH, min(width - moved, config.MAX_WIDTH))
        return x + width - new_width, new_width
    return x, max(config.MIN_WIDTH, min(width + moved, config.MAX_WIDTH))


def text_room(width):
    """Window width the numbers are sized for: widening the window only
    stretches the drawings, narrowing it may shrink the numbers to fit."""
    return min(width, config.DEFAULTS["width"])


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


def eased(shown, target):
    """Next position of a gauge gliding from `shown` towards `target`:
    fast at first, slower when it gets close, exactly on it once near."""
    if abs(target - shown) < SETTLED:
        return target
    return shown + (target - shown) * EASING


def _blank_history(count):
    """Sixty empty samples, so a new graph starts flat instead of jumping."""
    return deque([(0.0,) * count] * HISTORY_POINTS, maxlen=HISTORY_POINTS)


def blend(color, background, share):
    """Mix `share` of `color` with the rest of `background`: tkinter has no
    transparency, so a faded color stands for a see-through one."""
    share = max(0.0, min(share, 1.0))
    front = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    back = [int(background[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(f * share + b * (1.0 - share))
                                   for f, b in zip(front, back))


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
        i18n.set_language(values["language"])
        self.probes = []
        self.histories = {}
        self._apply_selection(self._displayed_keys())
        self._drag_origin = None
        self._edge = None
        self._dragged = False
        self._job = None
        self._frame = None
        self.options_window = None
        self.menu = None
        self.gauges = {}         # (probe key, column) -> ratio on screen,
                                 # behind the latest value when animated

        self._setup_window()
        if self._custom():
            # The grid may have been saved on a wider screen.
            self.values["grid_column_width"] = self._fit_column_width(
                self.values["grid_column_width"])
        self._build_canvas()
        self._build_menu()
        self._restore_position()
        self._draw()
        self._schedule_sample()
        # Windows calls the icon back from inside its own message handling:
        # the actions wait for Tk to be idle.
        self.tray = system.TrayIcon(
            "Monitor Widget",
            lambda: self.after_idle(self.show_widget),
            self._tray_menu)
        if self.values["tray_icon"]:
            self.tray.show()

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
                                width=self.window_width(),
                                height=self._height())
        self.canvas.pack(fill="both", expand=True)
        # Drag anywhere on the surface.
        self.canvas.bind("<Button-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._end_drag)
        self.canvas.bind("<Button-3>", self._open_menu)
        # The sides resize: the pointer says so when it passes over them.
        self.canvas.bind("<Motion>", self._update_cursor)

    def _build_menu(self):
        """Context menu, built again when the language changes."""
        if self.menu is not None:
            self.menu.destroy()
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label=tr("Options…"), command=self.open_options)
        self.menu.add_separator()
        self.menu.add_command(label=tr("Quitter"), command=self.quit_widget)

    def _tray_menu(self):
        """Entries of the notification area menu, in the current language."""
        return [(tr("Afficher le widget"), lambda: self.after_idle(self.show_widget)),
                (tr("Options…"), lambda: self.after_idle(self.open_options)),
                None,
                (tr("Quitter"), lambda: self.after_idle(self.quit_widget))]

    def _restore_position(self):
        """Restore the saved position, or recenter when it is off screen."""
        width, height = self.window_width(), self._height()
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
        height = self._height()
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
        if self._height() != height:
            self._resize()
        else:
            self._draw()
        self._schedule_sample()
        if self.values["smooth"]:
            self._schedule_frame()

    def _schedule_frame(self):
        if self._frame is None:
            self._frame = self.after(FRAME_MS, self._animate)

    def _animate(self):
        """Move every gauge a step closer to its latest value, and keep
        going only while one of them is still on its way."""
        self._frame = None
        moving = False
        for probe in self.probes:
            for column, value in enumerate(self._last(probe)):
                target = self._ratio(probe, value, column)
                key = (probe.key, column)
                shown = self.gauges.get(key, target)
                self.gauges[key] = eased(shown, target)
                moving = moving or self.gauges[key] != target
        self._draw()
        if moving:
            self._schedule_frame()

    @staticmethod
    def _ratio(probe, value, column):
        """Bounded fill ratio of one value. A broken metric shows empty."""
        try:
            return max(0.0, min(probe.ratio(value, column), 1.0))
        except Exception:
            return 0.0

    def _draw(self):
        width, height = self.window_width(), self._height()
        self.canvas.delete("all")
        self._rounded_rectangle(1, 1, width - 1, height - 1, 12,
                                fill=BACKGROUND, outline=BORDER)
        if not self.probes:
            self.canvas.create_text(width // 2, height // 2, text=tr(EMPTY_TEXT),
                                    fill=CAPTION,
                                    font=held_font(("Segoe UI", 9)),
                                    width=width - 2 * MARGIN, justify="center")
        elif self._custom():
            self._draw_grid()
        else:
            compact = self.values["mode"] in ("compact", "custom")
            block = COMPACT_HEIGHT if compact else BLOCK_HEIGHT
            gap = COMPACT_GAP if compact else BLOCK_GAP
            top = PADDING
            for probe in self.probes:
                if compact:
                    for column in range(len(self._last(probe))):
                        self._draw_compact_line(probe, column, top, 0, width)
                        top += block + gap
                else:
                    self._draw_block(probe, top, block)
                    top += block + gap

    def _draw_grid(self):
        """Every filled cell of the custom grid as a compact line, twice as
        long for a wide cell. Cells showing the same value share its probe,
        history and gauge."""
        shown = {probe.key: probe for probe in self.probes}
        columns = self.values["grid_columns"]
        width = self.values["grid_column_width"]
        wide = set(self.values["grid_wide"])
        for index, cell in enumerate(self.values["grid_cells"]):
            parsed = grid.parse(cell)
            if parsed is None or parsed[0] not in shown:
                continue
            probe, slot = shown[parsed[0]], parsed[1]
            if slot >= len(self._last(probe)):
                continue
            row, column = divmod(index, columns)
            x0 = column * width
            top = PADDING + row * (COMPACT_HEIGHT + COMPACT_GAP)
            span = 2 if index in wide else 1
            self._draw_compact_line(probe, slot, top, x0, x0 + span * width)

    def _last(self, probe):
        """Most recent sample of a metric, zeros before the first one."""
        history = self.histories[probe.key]
        return history[-1] if history else (0.0,)

    def _draw_block(self, probe, top, block):
        """Caption, large number, then the graph underneath. A metric showing
        several values gets one number and one graph per column."""
        width = self.window_width()
        values = self._last(probe)
        texts = probe.texts(values)
        self.canvas.create_text(MARGIN, top + 6, anchor="w", text=tr(probe.label),
                                fill=CAPTION, font=held_font(("Segoe UI", 9)))
        areas = columns(MARGIN, width - MARGIN, len(values))
        rooms = columns(MARGIN, text_room(width) - MARGIN, len(values))
        for index, (x0, x1) in enumerate(areas):
            room = rooms[index][1] - rooms[index][0]
            prefix, prefix_font, font = self._fonts(probe, index, texts[index],
                                                    room, BLOCK_SIZES,
                                                    PREFIX_SIZE)
            x = x0
            if prefix:
                self.canvas.create_text(x, top + 30, anchor="w", text=prefix,
                                        fill=TEXT, font=held_font(prefix_font))
                x += text_width(prefix, prefix_font) + PREFIX_GAP
            self.canvas.create_text(x, top + 30, anchor="w", text=texts[index],
                                    fill=TEXT, font=held_font(font))
            self._draw_graph(probe, index, x0, top + 44, x1, top + block,
                             self._color(probe, values[index], index))

    def _captions(self, probe):
        """Name written before each graph. A broken metric falls back on
        its label."""
        try:
            return probe.captions()
        except Exception:
            return [probe.label] * len(self._last(probe))

    def _outlined_text(self, x, y, text, font, anchor):
        """Light text rimmed with a dark outline, readable over any curve:
        the text is drawn dark one pixel away all around, then on top."""
        font = held_font(font)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    self.canvas.create_text(x + dx, y + dy, anchor=anchor,
                                            text=text, fill=OUTLINE, font=font)
        self.canvas.create_text(x, y, anchor=anchor, text=text, fill=TEXT,
                                font=font)

    def _draw_compact_line(self, probe, column, top, x0, x1):
        """Graph across the whole line with the name on its left and the
        number on its right written over it, then the gauge underneath."""
        values = self._last(probe)
        value = values[column]
        texts = probe.texts(values)
        captions = self._captions(probe)
        caption = captions[column] if column < len(captions) else ""
        # When animated, the gauge glides towards the value and takes its
        # colors along; otherwise it jumps straight to it.
        target = self._ratio(probe, value, column)
        if self.values["smooth"]:
            ratio = self.gauges.setdefault((probe.key, column), target)
        else:
            ratio = self.gauges[(probe.key, column)] = target
        color = probe.tint(column) or load_color(
            self._scale_ratio(probe, value, column, ratio))
        left = x0 + MARGIN
        right = x1 - MARGIN
        bottom = top + COMPACT_GRAPH

        self._draw_graph(probe, column, left, top, right, bottom, color,
                         baseline=False, fill=blend(color, BACKGROUND, FILL_SHARE))
        middle = (top + bottom) // 2
        self._outlined_text(left, middle, caption, ("Segoe UI", 10, "bold"), "w")
        font = fitting_font(self._template(probe, texts[column]),
                            (right - left) // 2, COMPACT_SIZES)
        self._outlined_text(right, middle, texts[column], font, "e")
        gauge = (bottom + GAUGE_GAP + top + COMPACT_HEIGHT) // 2
        self._draw_gauge(ratio, left, gauge, right, color)

    def _draw_gauge(self, ratio, x0, middle, x1, color):
        """Bar filled as far as the current value goes."""
        y0 = middle - GAUGE_THICKNESS // 2
        y1 = y0 + GAUGE_THICKNESS
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=BORDER, outline="")
        filled = x0 + (x1 - x0) * max(0.0, min(ratio, 1.0))
        if filled > x0:
            self.canvas.create_rectangle(x0, y0, filled, y1, fill=color,
                                         outline="")

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
        return probe.tint(column) or load_color(
            self._scale_ratio(probe, value, column, probe.ratio(value, column)))

    @staticmethod
    def _scale_ratio(probe, value, column, ratio):
        """Place on the green to red scale: the metric's own when it has
        one, the height of its graph otherwise."""
        scale = probe.color_ratio(value, column)
        return ratio if scale is None else scale

    def _draw_graph(self, probe, column, x0, y0, x1, y1, color, baseline=True,
                    fill=None):
        """Scrolling graph of the last 60 samples of one column. A `fill`
        color gives the area a plain tint and the curve a bolder line."""
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
        # Shaded area first, then the curve itself. A plain blended color, not
        # a stipple: on Windows Tk allocates a bitmap for every stippled shape
        # it draws, and fails with "Tk_GetPixmap" when memory runs short.
        shade = fill or blend(color, BACKGROUND, SHADE_SHARE)
        self.canvas.create_polygon(points + [x1, y1, x0, y1],
                                   fill=shade, outline="")
        self.canvas.create_line(points, fill=color,
                                width=1.5 if fill is None else 2, smooth=True)

    def _rounded_rectangle(self, x0, y0, x1, y1, radius, fill, outline):
        """Rounded rectangle drawn as a smoothed polygon."""
        points = [x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius,
                  x1, y1 - radius, x1, y1, x1 - radius, y1, x0 + radius, y1,
                  x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0]
        self.canvas.create_polygon(points, fill=fill, outline=outline,
                                   smooth=True, splinesteps=12)

    # ------------------------------------------------------------------
    # Dragging and resizing
    # ------------------------------------------------------------------

    def _update_cursor(self, event):
        if self._drag_origin is not None:
            return
        edge = resize_edge(event.x, self.window_width())
        self.canvas.configure(cursor="sb_h_double_arrow" if edge else "")

    def _start_drag(self, event):
        self._edge = resize_edge(event.x, self.window_width())
        if self._edge:
            self._drag_origin = (event.x_root, self.winfo_x(),
                                 self.window_width(),
                                 self.values["grid_column_width"])
        else:
            self._drag_origin = (event.x_root - self.winfo_x(),
                                 event.y_root - self.winfo_y())
        self._dragged = False

    def _drag(self, event):
        if self._drag_origin is None:
            return
        if self._edge:
            start, x, width, column_width = self._drag_origin
            moved = event.x_root - start
            if self._custom():
                # Every column follows the edge by its share of the move.
                columns = self.values["grid_columns"]
                _x, column_width = resized(self._edge, x, column_width,
                                           moved // columns)
                column_width = self._fit_column_width(column_width)
                new_width = column_width * columns
                if self._edge == "left":
                    x += width - new_width
                width = new_width
                changed = column_width != self.values["grid_column_width"]
                self.values["grid_column_width"] = column_width
            else:
                x, width = resized(self._edge, x, width, moved)
                changed = width != self.values["width"]
                self.values["width"] = width
            if changed:
                self.canvas.configure(width=width)
                self.geometry("{}x{}+{}+{}".format(width, self._height(), x,
                                                   self.winfo_y()))
                self._draw()
        else:
            offset_x, offset_y = self._drag_origin
            self.geometry("+{}+{}".format(event.x_root - offset_x,
                                          event.y_root - offset_y))
        self._dragged = True

    def _end_drag(self, _event):
        self._drag_origin = None
        if not self._dragged:
            return
        # The file is only written once the move or the resize is over.
        self.values["x"] = self.winfo_x()
        self.values["y"] = self.winfo_y()
        config.save(self.values)
        self._dragged = False

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _open_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def open_options(self):
        """Show the options window, bringing back the one already open."""
        window = self.options_window
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_force()
            return
        self.options_window = OptionsWindow(self)

    def show_widget(self):
        """Bring the widget back in sight: in front of the other windows,
        and back to the middle of the screen when it is no longer on one."""
        self.deiconify()
        self.values["x"], self.values["y"] = self.winfo_x(), self.winfo_y()
        self._restore_position()
        # A window that is not always on top only comes in front this way.
        self.attributes("-topmost", True)
        self.lift()
        if not self.values["always_on_top"]:
            self.attributes("-topmost", False)
        config.save(self.values)

    # ------------------------------------------------------------------
    # Settings, applied at once and saved
    # ------------------------------------------------------------------

    def set_mode(self, mode):
        if mode == "custom" and not self.values["grid_cells"]:
            # First grid: one column holding what was on screen until now.
            columns, rows, cells = grid.initial(grid.displayed_cells(self.values))
            self.values["grid_columns"] = columns
            self.values["grid_rows"] = rows
            self.values["grid_cells"] = cells
            self.values["grid_wide"] = []
        self.values["mode"] = mode
        if mode == "custom":
            self.values["grid_column_width"] = self._fit_column_width(
                self.values["grid_column_width"])
        self._reconfigure()
        config.save(self.values)
        self._resize()

    def set_probes(self, keys):
        self.values["probes"] = [key for key in keys if key in probes.PROBES]
        self._reconfigure()
        config.save(self.values)
        self._resize()

    def set_option(self, key, value):
        self.values[key] = value
        self._reconfigure()
        config.save(self.values)
        self._resize()

    def set_grid(self, columns, rows, cells, wide):
        self.values["grid_columns"] = columns
        self.values["grid_rows"] = rows
        self.values["grid_cells"] = list(cells)
        self.values["grid_wide"] = list(wide)
        self.values["grid_column_width"] = self._fit_column_width(
            self.values["grid_column_width"])
        self._reconfigure()
        config.save(self.values)
        self._resize()

    def set_smooth(self, enabled):
        self.values["smooth"] = enabled
        config.save(self.values)
        if not enabled and self._frame is not None:
            self.after_cancel(self._frame)
            self._frame = None
        self._draw()

    def set_on_top(self, enabled):
        self.values["always_on_top"] = enabled
        self.attributes("-topmost", enabled)
        config.save(self.values)

    def set_tray_icon(self, enabled):
        self.values["tray_icon"] = enabled
        if enabled:
            self.tray.show()
        else:
            self.tray.hide()
        config.save(self.values)

    def set_language(self, language):
        """Switch every text at once: the menu and the options window are
        built again, and the widget redrawn."""
        i18n.set_language(language)
        self.values["language"] = i18n.language()
        config.save(self.values)
        self._build_menu()
        self._draw()
        window = self.options_window
        if window is not None and window.winfo_exists():
            # Rebuilt once the list that asked for it is done with its event.
            self.after_idle(self._reopen_options)

    def _reopen_options(self):
        window = self.options_window
        if window is None or not window.winfo_exists():
            return
        x, y = window.winfo_x(), window.winfo_y()
        window.close()
        self.open_options()
        self.options_window.geometry("+{}+{}".format(x, y))

    def window_width(self):
        """Width of the window: the user's one, or the whole custom grid."""
        if self._custom():
            return self.values["grid_columns"] * self.values["grid_column_width"]
        return self.values["width"]

    def _custom(self):
        return self.values["mode"] == "custom"

    def _fit_column_width(self, width):
        return grid.fit_column_width(width, self.values["grid_columns"],
                                     self.winfo_screenwidth(),
                                     config.MIN_WIDTH, config.MAX_WIDTH)

    def _displayed_keys(self):
        """Metrics to read: those of the grid cells in custom mode."""
        if self._custom():
            return grid.needed_keys(self.values["grid_cells"])
        return self.values["probes"]

    def _configured(self):
        return probes.configured_values(self.values, self._custom())

    def _reconfigure(self):
        """Pick the metrics the mode displays and hand them the choices it
        implies. A choice can add or remove a column: that graph starts over."""
        self._apply_selection(self._displayed_keys())
        configured = self._configured()
        for probe in self.probes:
            probe.configure(configured)
            if len(self.histories[probe.key][-1]) != probe.columns():
                self.histories[probe.key] = _blank_history(probe.columns())

    def _apply_selection(self, keys):
        """Rebuild the list of probes, keeping the history of those already
        displayed so switching an unrelated metric does not reset the graphs.
        Those no longer displayed are stopped."""
        kept = []
        histories = {}
        for key in keys:
            cls = probes.PROBES.get(key)
            if cls is None or key in histories:
                continue
            probe = next((p for p in self.probes if p.key == key), None)
            if probe is None:
                probe = cls()
                probe.configure(self._configured())
                probe.start()
            kept.append(probe)
            histories[key] = self.histories.get(
                key, _blank_history(probe.columns()))
        for probe in self.probes:
            if probe not in kept:
                probe.stop()
        self.probes = kept
        self.histories = histories

    def _height(self):
        if self._custom():
            # The grid keeps its size, unless nothing at all is chosen.
            if self.probes:
                return grid_height(self.values["grid_rows"])
            return EMPTY_HEIGHT
        if self.values["mode"] == "compact":
            # One pair of lines for each value a metric shows.
            return window_height(sum(len(self.histories[probe.key][-1])
                                     for probe in self.probes), True)
        return window_height(len(self.probes), False)

    def _resize(self):
        """Give the window the height its content needs, then redraw."""
        width, height = self.window_width(), self._height()
        self.canvas.configure(width=width, height=height)
        if self.winfo_ismapped():
            # Keep the top left corner where the user left it.
            self.values["x"], self.values["y"] = self.winfo_x(), self.winfo_y()
        self.geometry("{}x{}+{}+{}".format(width, height,
                                           self.values["x"], self.values["y"]))
        self._draw()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def quit_widget(self):
        for job in (self._job, self._frame):
            if job is None:
                continue
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        if self.options_window is not None:
            try:
                self.options_window.destroy()
            except tk.TclError:
                pass
        self.tray.hide()
        for probe in self.probes:
            probe.stop()
        self.values["x"] = self.winfo_x()
        self.values["y"] = self.winfo_y()
        config.save(self.values)
        self.master.destroy()
