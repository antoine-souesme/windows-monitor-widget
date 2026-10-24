# -*- coding: utf-8 -*-
"""Arithmetic of the custom grid, kept apart from the drawing so it can be
tested without a display.

A cell names one value of one metric as "<metric key>:<slot index>"
("net:1" is the network upload), or is empty. The cells are stored row by
row. A wide cell spans its own column and the next one: the cell it covers
stays in the list, always empty.
"""

from . import probes
from .i18n import tr

MAX_SIZE = 6             # columns and rows both go from 1 to that
EMPTY = ""
EMPTY_LABEL = "(vide)"


def cell_id(key, index):
    """Cell showing value `index` of metric `key`."""
    return "{}:{}".format(key, index)


def parse(cell):
    """(metric key, slot index) of a cell, None when it is empty or names
    nothing measurable."""
    if not isinstance(cell, str) or ":" not in cell:
        return None
    key, _sep, index = cell.rpartition(":")
    cls = probes.PROBES.get(key)
    if cls is None or not index.isdigit():
        return None
    index = int(index)
    if index >= len(cls.slots()):
        return None
    return key, index


def is_valid(cell):
    return cell == EMPTY or parse(cell) is not None


def choices():
    """What a cell can show: empty first, then every value of every metric
    in registry order, each with its name."""
    listed = [(EMPTY, tr(EMPTY_LABEL))]
    for key, cls in probes.PROBES.items():
        for index, name in enumerate(cls.slots()):
            listed.append((cell_id(key, index), name))
    return listed


def resized(cells, columns, new_columns, new_rows):
    """Cells of the grid once resized: every cell that stays keeps its row
    and column, the new ones are empty."""
    kept = []
    for row in range(new_rows):
        for column in range(new_columns):
            index = row * columns + column
            inside = column < columns and index < len(cells)
            kept.append(cells[index] if inside else EMPTY)
    return kept


def clean_wide(wide, columns, rows):
    """Wide cells, by index, that can be: inside the grid, not on its last
    column and not covered by another one. Sorted, each once."""
    kept = []
    if not isinstance(wide, list):
        return kept
    indexes = {index for index in wide
               if isinstance(index, int) and not isinstance(index, bool)}
    for index in sorted(indexes):
        if (0 <= index < columns * rows and index % columns < columns - 1
                and index - 1 not in kept):
            kept.append(index)
    return kept


def covered(wide):
    """Cells hidden under a wide cell: the one on its right."""
    return {index + 1 for index in wide}


def spanned(cells, wide):
    """The cells, those hidden under a wide cell emptied."""
    hidden = covered(wide)
    return [EMPTY if index in hidden else cell for index, cell in enumerate(cells)]


def resized_wide(wide, columns, new_columns, new_rows):
    """Wide cells once the grid is resized: each keeps its row and column,
    those that no longer fit become normal again."""
    moved = []
    for index in wide:
        row, column = divmod(index, columns)
        if row < new_rows and column < new_columns - 1:
            moved.append(row * new_columns + column)
    return clean_wide(moved, new_columns, new_rows)


def initial(cells):
    """(columns, rows, cells) of a first grid: one column holding `cells`."""
    rows = min(max(len(cells), 1), MAX_SIZE)
    return 1, rows, (list(cells[:rows]) or [EMPTY])


def displayed_cells(values):
    """Cells drawn by the normal and compact modes, in their order."""
    cells = []
    for key in values.get("probes", []):
        cls = probes.PROBES.get(key)
        if cls is None:
            continue
        probe = cls()
        probe.configure(values)
        cells.extend(cell_id(key, index) for index in probe.shown_slots())
    return cells


def needed_keys(cells):
    """Metrics the grid has to read, once each, in order of appearance."""
    keys = []
    for cell in cells:
        parsed = parse(cell)
        if parsed is not None and parsed[0] not in keys:
            keys.append(parsed[0])
    return keys


def fit_column_width(width, columns, screen_width, minimum, maximum):
    """Column width within its bounds, narrowed so that every column fits
    on the screen, but never below `minimum`."""
    width = max(minimum, min(width, maximum))
    if width * columns > screen_width:
        width = screen_width // max(columns, 1)
    return max(minimum, width)
