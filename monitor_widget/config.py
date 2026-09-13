# -*- coding: utf-8 -*-
"""Reading and writing the configuration file.

Location: %APPDATA%\\CpuWidget\\config.json (or ~/.config/CpuWidget outside
Windows, so the code can be run elsewhere without crashing).
A missing or corrupted configuration simply falls back to the defaults: the
widget must never refuse to start because of it.
"""

import json
import os

APP_NAME = "CpuWidget"

# Values used on first launch, or when the file cannot be used.
DEFAULTS = {
    "x": None,              # left position in pixels (None = center)
    "y": None,              # top position in pixels
    "width": 200,
    "height": 90,
    "always_on_top": True,
    "probe": "cpu",         # key of the displayed metric (see probes.py)
}


def config_dir():
    """Directory holding the configuration file."""
    base = os.environ.get("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


def config_path():
    return os.path.join(config_dir(), "config.json")


def load():
    """Return the stored configuration, completed with the defaults."""
    values = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            # Only known keys are kept, and only when the type matches.
            for key, default in DEFAULTS.items():
                if key not in stored:
                    continue
                value = stored[key]
                if default is None or value is None or isinstance(value, type(default)):
                    values[key] = value
    except (OSError, ValueError, TypeError):
        # Missing file, unreadable file or broken JSON: keep the defaults.
        pass
    return _sanitize(values)


def _sanitize(values):
    """Bring out-of-range values back into sane bounds."""
    try:
        values["width"] = max(140, min(int(values["width"]), 600))
        values["height"] = max(70, min(int(values["height"]), 400))
    except (TypeError, ValueError):
        values["width"] = DEFAULTS["width"]
        values["height"] = DEFAULTS["height"]
    for key in ("x", "y"):
        try:
            values[key] = None if values[key] is None else int(values[key])
        except (TypeError, ValueError):
            values[key] = None
    values["always_on_top"] = bool(values.get("always_on_top", True))
    if not isinstance(values.get("probe"), str):
        values["probe"] = DEFAULTS["probe"]
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
