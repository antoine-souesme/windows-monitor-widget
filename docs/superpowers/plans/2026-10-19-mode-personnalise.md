# Mode personnalisé et fenêtre d'options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third display mode ("Personnalisé") drawing a free grid of compact cells, and move every setting from the context menu into an options window.

**Architecture:** Metrics describe every value they can measure (`slots()`), a new pure module `grid.py` holds the grid arithmetic (cell ids, resizing, first fill, widths), `config.py` stores `mode` and the grid, `ui.py` draws the grid with the existing compact line, and a new `options.py` holds the `tk.Toplevel` options window calling public setters on the widget.

**Tech Stack:** Python 3, tkinter/ttk, psutil, unittest.

**Spec:** `docs/superpowers/specs/2026-10-19-mode-personnalise-design.md`

## Global Constraints

- Code and comments in English, user facing strings in French (exact labels below).
- No blocking call in the UI thread; sampling stays on `after()`.
- A corrupted configuration falls back to defaults, never a crash.
- Config written on meaningful events only (option change, end of drag, exit).
- No metric specific code in `ui.py` or `options.py`: a new `@register` metric shows up in the grid lists on its own.
- Grid bounds: 1 to 6 columns, 1 to 6 rows (`grid.MAX_SIZE = 6`).
- Column width default 200, bounded by `config.MIN_WIDTH`/`config.MAX_WIDTH`, total never wider than the screen.
- Exact French labels: menu `"Options…"`, `"Quitter"`; window title `"Monitor Widget — Options"`; frames `"Affichage"`, `"Métriques affichées"`, `"Grille mode personnalisé"`, `"Options des métriques"`, `"Général"`; radios `"Normal"`, `"Compact"`, `"Personnalisé"`; grid spinners `"Colonnes"`, `"Rangs"`; empty cell `"(vide)"`; checkboxes `SMOOTH_LABEL`, `"Lancer au démarrage"` (hidden when `system.is_packaged()`), `"Toujours au premier plan"`; footer `"Monitor Widget {version}"`.
- Run all tests with `python -m unittest discover -s tests`.

## Review Focus

- A config whose `grid_cells` name an unknown metric, a bad index (`"net:9"`), a non string, or a list of the wrong length: unknown cells become `""`, length is fixed to `columns × rows` (Task 3 test).
- Shrinking then enlarging the grid: cells that stay keep their (row, column), new ones are empty (Task 2 test).
- Six columns on a small screen: column width shrinks so the total fits, never below `MIN_WIDTH` (Task 2 test).
- A custom grid whose cells are all empty: the window shows the empty frame text instead of an empty grid, and sampling reads no metric (Task 2 test on `needed_keys`, manual check in Task 4).
- Leaving custom mode: the network option the user chose comes back and the graph history is restarted with the right number of values (manual check in Task 4, `configured_values` test in Task 1).

---

### Task 1: Metrics list every value they can measure

**Files:**
- Modify: `monitor_widget/probes.py` (`Probe`, `NetworkProbe`, module docstring)
- Test: `tests/test_probes.py`

**Interfaces:**
- Produces:
  - `Probe.slots()` — classmethod, returns `list[str]`: French name of every value the metric can measure whatever its options. Default `[cls.label]`. `NetworkProbe.slots()` returns `["Réseau réception", "Réseau envoi"]`.
  - `Probe.custom_values` — class attribute `dict[str, str]`: option values forced in custom mode. Default `{}`. `NetworkProbe.custom_values = {"network_display": "both"}`.
  - `probes.configured_values(values: dict, custom: bool) -> dict` — copy of `values` where, when `custom`, every metric's `custom_values` override the stored choices. Never mutates `values`.
  - `probes.custom_hidden_options() -> set[str]` — option keys appearing in any `custom_values` (hidden from the options window in custom mode).

- [ ] **Step 1: Write the failing tests** (class `SlotTest`)

```python
def test_single_value_metric_has_one_slot(self):
    self.assertEqual(probes.CpuProbe.slots(), ["CPU"])

def test_network_lists_both_directions(self):
    self.assertEqual(probes.NetworkProbe.slots(),
                     ["Réseau réception", "Réseau envoi"])

def test_custom_mode_forces_both_directions(self):
    values = {"network_display": "upload"}
    self.assertEqual(probes.configured_values(values, True)["network_display"], "both")
    self.assertEqual(probes.configured_values(values, False)["network_display"], "upload")
    self.assertEqual(values["network_display"], "upload")

def test_forced_options_are_hidden(self):
    self.assertIn("network_display", probes.custom_hidden_options())
    self.assertNotIn("ram_display", probes.custom_hidden_options())

def test_every_metric_has_as_many_slots_as_columns_in_custom_mode(self):
    for cls in probes.PROBES.values():
        probe = cls()
        probe.configure(probes.configured_values(config.DEFAULTS, True))
        self.assertEqual(probe.columns(), len(cls.slots()))
```

(Import `config` in the test module for the last one.)

- [ ] **Step 2: Run** `python -m unittest tests.test_probes -v` — Expected: FAIL (`slots` not defined).
- [ ] **Step 3: Implement** the four interfaces above in `probes.py`; update the module docstring to mention `slots()` and `custom_values`.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -am "Les métriques listent chacune de leurs valeurs"`

---

### Task 2: Grid arithmetic

**Files:**
- Create: `monitor_widget/grid.py`
- Test: `tests/test_grid.py`

**Interfaces:**
- Consumes: `probes.PROBES`, `Probe.slots()` (Task 1); `config.MIN_WIDTH`, `config.MAX_WIDTH` — import them lazily inside `fit_column_width` or pass bounds as parameters to avoid a `config ↔ grid` import cycle (the chosen way: `fit_column_width(width, columns, screen_width, minimum, maximum)`).
- Produces:
  - `MAX_SIZE = 6`, `EMPTY = ""`, `EMPTY_LABEL = "(vide)"`.
  - `cell_id(key: str, index: int) -> str` → `"net:1"`.
  - `parse(cell) -> tuple[str, int] | None` — `None` for empty, non string, unknown key or index outside `slots()`.
  - `is_valid(cell) -> bool` — `cell == EMPTY or parse(cell) is not None`.
  - `choices() -> list[tuple[str, str]]` — `[(EMPTY, EMPTY_LABEL)]` then `(cell_id, slot name)` for every metric in registry order.
  - `resized(cells: list[str], columns: int, new_columns: int, new_rows: int) -> list[str]` — keeps each cell at its (row, column), new cells empty.
  - `initial(cells: list[str]) -> tuple[int, int, list[str]]` — one column, `rows = min(max(len(cells), 1), MAX_SIZE)`, cells cut to `rows`, `[""]` when empty.
  - `displayed_cells(values: dict) -> list[str]` — the cells shown by normal/compact mode for `values["probes"]` under the stored options: for each probe key, instantiate the class, `configure(values)`, then the cells of the values it currently draws. Map them through `slots()` order; for the network with `"upload"` only, that is `["net:1"]`. To keep this metric agnostic, add `Probe.shown_slots() -> list[int]` (default `list(range(self.columns()))`, network returns `[0]`, `[1]` or `[0, 1]` from `_display`) in `probes.py`.
  - `needed_keys(cells: list[str]) -> list[str]` — probe keys of the valid cells, first appearance order, no duplicates.
  - `fit_column_width(width: int, columns: int, screen_width: int, minimum: int, maximum: int) -> int` — `width` clamped to `minimum..maximum`, then lowered to `screen_width // columns` if needed, never below `minimum`.

- [ ] **Step 1: Write the failing tests** (`tests/test_grid.py`, same header as the other test files)

```python
def test_cell_round_trip(self):
    self.assertEqual(grid.parse(grid.cell_id("net", 1)), ("net", 1))

def test_bad_cells_are_rejected(self):
    for cell in ("net:9", "nope:0", "cpu", 3, None, "cpu:x"):
        self.assertIsNone(grid.parse(cell))
    self.assertTrue(grid.is_valid(""))

def test_choices_start_with_empty_and_split_the_network(self):
    choices = grid.choices()
    self.assertEqual(choices[0], ("", "(vide)"))
    self.assertIn(("net:0", "Réseau réception"), choices)
    self.assertIn(("net:1", "Réseau envoi"), choices)

def test_shrinking_then_growing_keeps_positions(self):
    cells = ["a", "b", "c", "d", "e", "f"]          # 3 columns × 2 rows
    small = grid.resized(cells, 3, 2, 1)
    self.assertEqual(small, ["a", "b"])
    self.assertEqual(grid.resized(small, 2, 3, 2), ["a", "b", "", "", "", ""])

def test_first_fill_is_one_column(self):
    self.assertEqual(grid.initial(["cpu:0", "net:0", "net:1"]),
                     (1, 3, ["cpu:0", "net:0", "net:1"]))
    self.assertEqual(grid.initial([]), (1, 1, [""]))
    self.assertEqual(grid.initial(["cpu:0"] * 8)[1], 6)

def test_displayed_cells_follow_the_network_option(self):
    values = dict(config.DEFAULTS, probes=["cpu", "net"], network_display="upload")
    self.assertEqual(grid.displayed_cells(values), ["cpu:0", "net:1"])

def test_needed_keys_skip_empty_and_repeats(self):
    self.assertEqual(grid.needed_keys(["", "net:1", "cpu:0", "net:0"]), ["net", "cpu"])
    self.assertEqual(grid.needed_keys(["", ""]), [])

def test_column_width_fits_the_screen(self):
    self.assertEqual(grid.fit_column_width(300, 6, 1200, 140, 600), 200)
    self.assertEqual(grid.fit_column_width(300, 6, 600, 140, 600), 140)
    self.assertEqual(grid.fit_column_width(900, 1, 3000, 140, 600), 600)
```

- [ ] **Step 2: Run** `python -m unittest tests.test_grid -v` — Expected: FAIL (no module).
- [ ] **Step 3: Implement** `grid.py` and `Probe.shown_slots()`.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -am "Ajoute le calcul de la grille du mode personnalisé"`

---

### Task 3: Configuration stores the mode and the grid

**Files:**
- Modify: `monitor_widget/config.py` (`DEFAULTS`, `load`, `_sanitize`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `grid.MAX_SIZE` and `grid.is_valid(cell)` (Task 2).
- Produces: `DEFAULTS` loses `"compact"` and gains `"mode": "normal"`, `"grid_columns": 1`, `"grid_rows": 1`, `"grid_cells": []`, `"grid_column_width": 200`. `config.MODES = ("normal", "compact", "custom")`.

Rules in `_sanitize`: unknown `mode` → `"normal"`; `grid_columns`/`grid_rows` clamped to `1..MAX_SIZE` (bad type → 1); `grid_column_width` clamped to `MIN_WIDTH..MAX_WIDTH` (bad type → 200); `grid_cells` not a list → `[]`; a non empty list is cut or padded with `""` to `columns × rows`, and every entry failing `grid.is_valid` becomes `""`. An empty list stays empty (it means "no grid saved yet"). In `load`, a stored `"compact": true` with no `"mode"` gives `"compact"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_mode_defaults_to_normal(self):
    self.assertEqual(config.load()["mode"], "normal")

def test_old_compact_flag_is_migrated(self):
    self.write({"compact": True})
    self.assertEqual(config.load()["mode"], "compact")

def test_mode_wins_over_the_old_flag(self):
    self.write({"compact": True, "mode": "custom"})
    self.assertEqual(config.load()["mode"], "custom")

def test_unknown_mode_falls_back_to_normal(self):
    self.write({"mode": "giant"})
    self.assertEqual(config.load()["mode"], "normal")

def test_grid_size_is_bounded(self):
    self.write({"grid_columns": 9, "grid_rows": 0})
    values = config.load()
    self.assertEqual((values["grid_columns"], values["grid_rows"]), (6, 1))

def test_broken_cells_become_empty_and_fit_the_grid(self):
    self.write({"grid_columns": 2, "grid_rows": 2,
                "grid_cells": ["cpu:0", "net:9", 3, "nope:0", "ram:0"]})
    self.assertEqual(config.load()["grid_cells"], ["cpu:0", "", "", ""])

def test_short_cell_list_is_padded(self):
    self.write({"grid_columns": 2, "grid_rows": 1, "grid_cells": ["net:1"]})
    self.assertEqual(config.load()["grid_cells"], ["net:1", ""])

def test_column_width_is_bounded(self):
    self.write({"grid_column_width": 5})
    self.assertEqual(config.load()["grid_column_width"], config.MIN_WIDTH)
```

Update `test_save_then_load` to use `values["mode"] = "compact"` and assert it reloads.

- [ ] **Step 2: Run** `python -m unittest tests.test_config -v` — Expected: FAIL.
- [ ] **Step 3: Implement** the rules above.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: all PASS.
- [ ] **Step 5: Commit** `git commit -am "La configuration range le mode et la grille"`

---

### Task 4: The widget draws the custom grid

**Files:**
- Modify: `monitor_widget/ui.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces, public methods of `WidgetWindow` used by the options window (each stores the value, saves the config once, and redraws/resizes):
  - `set_mode(mode: str) -> None` — on the first switch to `"custom"` while `values["grid_cells"] == []`, fill the grid with `grid.initial(grid.displayed_cells(self.values))`.
  - `set_probes(keys: list[str]) -> None`
  - `set_option(key: str, value: str) -> None`
  - `set_grid(columns: int, rows: int, cells: list[str]) -> None`
  - `set_smooth(enabled: bool) -> None`
  - `set_on_top(enabled: bool) -> None`
  - `window_width() -> int` — `values["width"]` outside custom mode, `grid_columns × grid_column_width` in it.
- Module level: `grid_height(rows: int) -> int` returning `window_height(rows, True)`.

Behaviour to implement:
- Every `values["compact"]` read becomes `values["mode"] in ("compact", "custom")` for sizes, or a `mode` test where drawing differs.
- Probes are configured through `probes.configured_values(self.values, custom)`; when the mode or an option changes, reconfigure every probe and restart a history whose column count changed (the existing logic of `_change_option`, moved into one `_reconfigure()` helper).
- Displayed probes: `grid.needed_keys(values["grid_cells"])` in custom mode, `values["probes"]` otherwise, through the existing `_apply_selection`.
- `_height()`: custom → `grid_height(rows)` when at least one cell is filled, `EMPTY_HEIGHT` otherwise.
- `_draw()`: custom with no filled cell → the existing empty text; otherwise each filled cell at (row, column) is a compact line in the area `x0 = column × column_width`, `x1 = x0 + column_width`, `top = PADDING + row × (COMPACT_HEIGHT + COMPACT_GAP)`. Change `_draw_compact_line(probe, column, top, legend)` to `_draw_compact_line(probe, column, top, legend, x0, x1)` with the text starting at `x0 + MARGIN` and drawings ending at `x1 - MARGIN`. The legend width is shared by every cell, computed over the cells shown, with `text_room(column_width)` as the room. Gauges stay keyed by `(probe.key, column)`, so repeated cells share one gauge.
- Every geometry/canvas width call uses `window_width()` instead of `values["width"]`.
- Resizing in custom mode: dragging an edge by `moved` pixels changes the column width through `resized(edge, x, column_width, moved // columns)`, then `grid.fit_column_width(..., self.winfo_screenwidth(), config.MIN_WIDTH, config.MAX_WIDTH)`; the window width is recomputed from it. `set_grid` also refits the column width.
- `resize_edge` and `_update_cursor` receive `window_width()`.

- [ ] **Step 1: Write the failing test**

```python
def test_grid_rows_use_the_compact_height(self):
    self.assertEqual(ui.grid_height(3), ui.window_height(3, True))
```

- [ ] **Step 2: Run** `python -m unittest tests.test_layout -v` — Expected: FAIL.
- [ ] **Step 3: Implement** the behaviour above. Keep the current menu for now, only replacing `_toggle_compact` with a call to `set_mode`, so the widget still runs between tasks.
- [ ] **Step 4: Run** `python -m unittest discover -s tests` — Expected: all PASS.
- [ ] **Step 5: Manual check (macOS or Windows).** Write a config with `"mode": "custom", "grid_columns": 2, "grid_rows": 2, "grid_cells": ["cpu:0", "net:1", "", "cpu:0"]` into `~/.config/MonitorWidget/config.json` (macOS) and run `python main.py`. Expected: 2 × 2 grid, CPU twice with the same values, upload only in the second cell, bottom left empty; dragging the right edge widens both columns. Then set every cell to `""`: the empty frame text shows. Restore the config afterwards.
- [ ] **Step 6: Commit** `git commit -am "Dessine la grille du mode personnalisé"`

---

### Task 5: Options window and two-entry context menu

**Files:**
- Create: `monitor_widget/options.py`
- Modify: `monitor_widget/ui.py` (`_build_menu`, remove `_build_option_menu` and the toggles moved to setters, add `open_options`)
- Modify: `CLAUDE.md` (layout table: `grid.py`, `options.py`; "Adding a metric": options now show in the options window, `slots()` / `custom_values` for multi value metrics)

**Interfaces:**
- Consumes: the `WidgetWindow` setters and `window_width()` (Task 4), `grid.choices()`, `grid.resized()`, `grid.MAX_SIZE` (Task 2), `probes.options()`, `probes.custom_hidden_options()` (Task 1), `system.is_packaged()`, `system.is_startup_enabled()`, `system.set_startup_enabled()`.
- Produces: `class OptionsWindow(tk.Toplevel)` built as `OptionsWindow(widget)`; `WidgetWindow.open_options()` creates it, or `deiconify()` + `lift()` + `focus_force()` on the existing one; the window clears the widget's reference on `WM_DELETE_WINDOW`.

Layout (ttk, `padding` around frames, title `"Monitor Widget — Options"`, not resizable): `LabelFrame "Affichage"` with three `Radiobutton`s → `widget.set_mode`. Below, one frame swapped with `pack_forget()` on mode change: in normal/compact `LabelFrame "Métriques affichées"` with one `Checkbutton` per `probes.PROBES` entry → `widget.set_probes(selected keys in registry order)`; in custom `LabelFrame "Grille mode personnalisé"` with two `Spinbox`es `"Colonnes"` / `"Rangs"` (`from_=1, to=grid.MAX_SIZE`, `state="readonly"`) and a sub frame of read only `Combobox`es showing the labels of `grid.choices()`, rebuilt whenever the size changes (`grid.resized` keeps the choices) and calling `widget.set_grid` on every change. `LabelFrame "Options des métriques"`: one row per option (metric label, read only `Combobox` of the French choice labels) → `widget.set_option`; rows whose key is in `custom_hidden_options()` hidden in custom mode; the frame hidden when it has no visible row. `LabelFrame "Général"`: smooth, startup (absent when packaged; reads `system.is_startup_enabled()` when the window opens and shows the value `set_startup_enabled` returns), on top. Footer label `"Monitor Widget {}".format(__version__)`. The window follows `always_on_top` so it is never hidden behind a topmost widget.

The context menu becomes exactly: `"Options…"` → `open_options`, separator, `"Quitter"` → `quit_widget`. `quit_widget` also destroys an open options window.

- [ ] **Step 1: Implement** `options.py` and the menu change.
- [ ] **Step 2: Run** `python -m unittest discover -s tests` — Expected: all PASS.
- [ ] **Step 3: Manual check** with `python main.py`: right click shows only "Options…" and "Quitter"; "Options…" twice opens a single window; switching Normal → Personnalisé fills one column with the displayed values; 3 columns × 2 rows, picking "Réseau envoi" in two cells, updates the widget at once; going back to 2 × 1 keeps the first two choices; the network option is hidden in Personnalisé and back in Normal with the previous choice; RAM option changes every RAM cell; closing and relaunching restores the same grid and mode.
- [ ] **Step 4: Commit** `git commit -am "Déplace les réglages dans une fenêtre d'options"`
