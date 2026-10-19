# -*- coding: utf-8 -*-
"""The options window: every setting of the widget, applied at once.

It holds no setting of its own: each change is handed to a public setter of
the widget, which stores it, saves the configuration and redraws. Metrics,
their values and their options are all read from probes.py and grid.py, so a
new metric shows up here on its own. Its texts are French, translated with
tr(): the window is built again when the language changes.
"""

import tkinter as tk
from tkinter import ttk

from . import grid, i18n, probes, system
from .i18n import tr
from .version import __version__

TITLE = "Monitor Widget — Options"
SMOOTH_LABEL = "Animations fluides (consomme plus de CPU)"
MODES = [("normal", "Normal"), ("compact", "Compact"), ("custom", "Personnalisé")]
FOOTER = "#888888"


class OptionsWindow(tk.Toplevel):
    """Ordinary window with a title bar, one per widget."""

    def __init__(self, widget):
        super().__init__(widget.master)
        self.widget = widget
        self.title(TITLE)
        self.resizable(False, False)
        # A topmost widget would otherwise hide its own options.
        self.attributes("-topmost", widget.values["always_on_top"])
        self.protocol("WM_DELETE_WINDOW", self.close)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self._build_mode(body)
        # The metrics or the grid, depending on the mode, keep their place
        # above the other frames.
        self._switched = ttk.Frame(body)
        self._switched.pack(fill="x")
        self._build_probes(self._switched)
        self._build_grid(self._switched)
        self._options_holder = ttk.Frame(body)
        self._options_holder.pack(fill="x")
        self._build_options(self._options_holder)
        self._build_general(body)
        ttk.Label(body, text="Monitor Widget {}".format(__version__),
                  foreground=FOOTER, font=("Segoe UI", 8)).pack(anchor="w")
        self._show_mode()

    def close(self):
        self.widget.options_window = None
        self.destroy()

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    @staticmethod
    def _frame(parent, text):
        frame = ttk.LabelFrame(parent, text=text, padding=(10, 6))
        frame.pack(fill="x", pady=(0, 10))
        return frame

    def _build_mode(self, parent):
        frame = self._frame(parent, tr("Affichage"))
        self.mode_var = tk.StringVar(value=self.widget.values["mode"])
        for mode, label in MODES:
            ttk.Radiobutton(frame, text=tr(label), value=mode,
                            variable=self.mode_var,
                            command=self._change_mode).pack(anchor="w")

    def _build_probes(self, parent):
        self.probes_frame = self._frame(parent, tr("Métriques affichées"))
        shown = self.widget.values["probes"]
        self.probe_vars = {}
        for key, cls in probes.PROBES.items():
            variable = tk.BooleanVar(value=key in shown)
            self.probe_vars[key] = variable
            ttk.Checkbutton(self.probes_frame, text=tr(cls.label),
                            variable=variable,
                            command=self._change_probes).pack(anchor="w")

    def _build_grid(self, parent):
        self.grid_frame = self._frame(parent, tr("Grille mode personnalisé"))
        sizes = ttk.Frame(self.grid_frame)
        sizes.pack(anchor="w")
        self.columns_var = tk.StringVar()
        self.rows_var = tk.StringVar()
        for column, (label, variable) in enumerate((("Colonnes", self.columns_var),
                                                    ("Rangs", self.rows_var))):
            ttk.Label(sizes, text=tr(label)).grid(row=0, column=2 * column,
                                              padx=(16 if column else 0, 6))
            ttk.Spinbox(sizes, from_=1, to=grid.MAX_SIZE, width=3,
                        state="readonly", textvariable=variable,
                        command=self._change_size).grid(row=0,
                                                        column=2 * column + 1)
        self.cells_frame = ttk.Frame(self.grid_frame)
        self.cells_frame.pack(fill="x", pady=(8, 0))
        self.cell_boxes = []

    def _build_options(self, parent):
        self.options_frame = self._frame(parent, tr("Options des métriques"))
        self.option_rows = []      # (option key, widgets of its row)
        row = 0
        for cls in probes.options():
            for option in cls.options:
                label = ttk.Label(self.options_frame, text=tr(cls.label))
                label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
                names = [tr(name) for _value, name in option.choices]
                box = ttk.Combobox(self.options_frame, values=names,
                                   state="readonly", width=24)
                values = option.values()
                current = self.widget.values.get(option.key, option.default)
                box.current(values.index(current) if current in values else 0)
                box.bind("<<ComboboxSelected>>",
                         lambda _event, option=option, box=box:
                         self.widget.set_option(option.key,
                                                option.values()[box.current()]))
                box.grid(row=row, column=1, sticky="w", pady=2)
                self.option_rows.append((option.key, (label, box)))
                row += 1

    def _build_general(self, parent):
        frame = self._frame(parent, tr("Général"))
        values = self.widget.values
        language = ttk.Frame(frame)
        language.pack(anchor="w", pady=(0, 4))
        ttk.Label(language, text=tr("Langue")).pack(side="left", padx=(0, 10))
        codes = i18n.codes()
        self.language_box = ttk.Combobox(
            language, values=[name for _code, name in i18n.LANGUAGES],
            state="readonly", width=12)
        self.language_box.current(codes.index(i18n.language()))
        self.language_box.bind("<<ComboboxSelected>>",
                               lambda _event: self.widget.set_language(
                                   codes[self.language_box.current()]))
        self.language_box.pack(side="left")
        self.smooth_var = tk.BooleanVar(value=values["smooth"])
        ttk.Checkbutton(frame, text=tr(SMOOTH_LABEL), variable=self.smooth_var,
                        command=lambda: self.widget.set_smooth(
                            self.smooth_var.get())).pack(anchor="w")
        # In a Store package Windows owns the auto start.
        if not system.is_packaged():
            self.startup_var = tk.BooleanVar(value=system.is_startup_enabled())
            ttk.Checkbutton(frame, text=tr("Lancer au démarrage"),
                            variable=self.startup_var,
                            command=self._change_startup).pack(anchor="w")
        self.on_top_var = tk.BooleanVar(value=values["always_on_top"])
        ttk.Checkbutton(frame, text=tr("Toujours au premier plan"),
                        variable=self.on_top_var,
                        command=self._change_on_top).pack(anchor="w")
        if system.has_tray():
            self.tray_var = tk.BooleanVar(value=values["tray_icon"])
            ttk.Checkbutton(frame, text=tr("Icône dans la zone de notification"),
                            variable=self.tray_var,
                            command=lambda: self.widget.set_tray_icon(
                                self.tray_var.get())).pack(anchor="w")

    # ------------------------------------------------------------------
    # Mode dependent parts
    # ------------------------------------------------------------------

    def _show_mode(self):
        """Metrics or grid, and the metric options that mean something in
        this mode."""
        custom = self.widget.values["mode"] == "custom"
        if custom:
            self.probes_frame.pack_forget()
            self.grid_frame.pack(fill="x", pady=(0, 10))
            self._fill_grid()
        else:
            self.grid_frame.pack_forget()
            self.probes_frame.pack(fill="x", pady=(0, 10))
        hidden = probes.custom_hidden_options() if custom else set()
        visible = 0
        for key, widgets in self.option_rows:
            for item in widgets:
                if key in hidden:
                    item.grid_remove()
                else:
                    item.grid()
            visible += key not in hidden
        if visible:
            self.options_frame.pack(fill="x", pady=(0, 10))
        else:
            self.options_frame.pack_forget()

    def _fill_grid(self):
        """One list per cell, laid out like the grid itself."""
        values = self.widget.values
        columns, rows = values["grid_columns"], values["grid_rows"]
        self.columns_var.set(str(columns))
        self.rows_var.set(str(rows))
        for box in self.cell_boxes:
            box.destroy()
        choices = grid.choices()
        ids = [cell for cell, _name in choices]
        names = [name for _cell, name in choices]
        cells = values["grid_cells"]
        self.cell_boxes = []
        for index in range(columns * rows):
            box = ttk.Combobox(self.cells_frame, values=names,
                               state="readonly", width=18)
            cell = cells[index] if index < len(cells) else grid.EMPTY
            box.current(ids.index(cell) if cell in ids else 0)
            box.bind("<<ComboboxSelected>>", self._change_cell)
            row, column = divmod(index, columns)
            box.grid(row=row, column=column, padx=2, pady=2, sticky="ew")
            self.cell_boxes.append(box)

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def _change_mode(self):
        self.widget.set_mode(self.mode_var.get())
        self._show_mode()

    def _change_probes(self):
        self.widget.set_probes([key for key, variable in self.probe_vars.items()
                                if variable.get()])

    def _change_size(self):
        values = self.widget.values
        columns, rows = int(self.columns_var.get()), int(self.rows_var.get())
        cells = grid.resized(values["grid_cells"], values["grid_columns"],
                             columns, rows)
        self.widget.set_grid(columns, rows, cells)
        self._fill_grid()

    def _change_cell(self, _event=None):
        values = self.widget.values
        ids = [cell for cell, _name in grid.choices()]
        cells = [ids[box.current()] for box in self.cell_boxes]
        self.widget.set_grid(values["grid_columns"], values["grid_rows"], cells)

    def _change_startup(self):
        self.startup_var.set(system.set_startup_enabled(self.startup_var.get()))

    def _change_on_top(self):
        enabled = self.on_top_var.get()
        self.widget.set_on_top(enabled)
        self.attributes("-topmost", enabled)
