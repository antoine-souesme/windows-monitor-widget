# -*- coding: utf-8 -*-
"""Reading and writing the configuration file.

Location: %APPDATA%\\MonitorWidget\\config.json (or ~/.config/MonitorWidget
outside Windows, so the code can be run elsewhere without crashing).
A missing or corrupted configuration simply falls back to the defaults: the
widget must never refuse to start because of it.
"""

import json
import os

from . import probes

APP_NAME = "MonitorWidget"
# Folder used before the rename: read once so settings survive an update.
LEGACY_APP_NAME = "CpuWidget"

# Values used on first launch, or when the file cannot be used.
DEFAULTS = {
    "x": None,              # left position in pixels (None = center)
    "y": None,              # top position in pixels
    "width": 200,
    "always_on_top": True,
    "probes": ["cpu"],      # keys of the displayed metrics (see probes.py)
    "compact": False,       # one line per metric, graph drawn behind it
}
# Every metric adds its own choices here (see probes.Option).
DEFAULTS.update(probes.option_defaults())


def config_dir():
    """Directory holding the configuration file."""
    base = os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


def config_path():
    return os.path.join(config_dir(), "config.json")


def _legacy_config_path():
    """Path of the file written by the versions named CPU Widget."""
    base = os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, LEGACY_APP_NAME, "config.json")


def load():
    """Return the stored configuration, completed with the defaults."""
    values = dict(DEFAULTS)
    path = config_path()
    if not os.path.exists(path):
        path = _legacy_config_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            # Only known keys are kept, and only when the type matches.
            for key, default in DEFAULTS.items():
                if key not in stored:
                    continue
                value = stored[key]
                # A date written without decimals stays a valid date.
                expected = (float, int) if isinstance(default, float) else type(default)
                if default is None or value is None or isinstance(value, expected):
                    values[key] = value
            # Versions up to 1.0.2 stored a single metric under "probe".
            if "probes" not in stored and isinstance(stored.get("probe"), str):
                values["probes"] = [stored["probe"]]
    except (OSError, ValueError, TypeError):
        # Missing file, unreadable file or broken JSON: keep the defaults.
        pass
    return _sanitize(values)


def _sanitize(values):
    """Bring out-of-range values back into sane bounds."""
    try:
        values["width"] = max(140, min(int(values["width"]), 600))
    except (TypeError, ValueError):
        values["width"] = DEFAULTS["width"]
    for key in ("x", "y"):
        try:
            values[key] = None if values[key] is None else int(values[key])
        except (TypeError, ValueError):
            values[key] = None
    values["always_on_top"] = bool(values.get("always_on_top", True))
    values["compact"] = bool(values.get("compact", False))
    # A choice that no longer exists falls back to the default of its metric.
    for cls in probes.options():
        for option in cls.options:
            if values.get(option.key) not in option.values():
                values[option.key] = option.default
    selected = values.get("probes")
    if not isinstance(selected, list):
        selected = list(DEFAULTS["probes"])
    # Keep the order, drop what cannot be a metric key and the repetitions.
    kept = []
    for key in selected:
        if isinstance(key, str) and key not in kept:
            kept.append(key)
    values["probes"] = kept
    return values


def save(values):
    """Write the configuration to disk, never raising."""
    try:
        os.makedirs(config_dir(), exist_ok=True)
        temporary = config_path() + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(values, handle, indent=2)
        os.replace(temporary, config_path())
        return True
    except OSError:
        return False
