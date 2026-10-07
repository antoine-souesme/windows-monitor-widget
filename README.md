# Monitor Widget

A small borderless Windows desktop widget showing live system metrics: a large
percentage, a scrolling 60-second graph, and a color going from green to
orange to red as the load rises. Tick as many metrics as you like and they
stack from top to bottom; a compact mode gives each value two thin lines: its
name and graph, then its number and a bar filled up to the current value.

## Install

Install it from the Microsoft Store: Windows then takes care of the auto
start and of the updates. The same package is also attached to every
[release](../../releases) as a `.msix` file, for a manual install.

## Run from the sources

```
pip install -r requirements.txt
pythonw.exe main.py
```

Python 3.8 or later, on Windows.

- Drag it anywhere with the left mouse button.
- Drag its left or right edge to change its width: only the graphs stretch.
- Right click for the menu: displayed metrics (check boxes), compact mode,
  start with Windows, always on top, quit.

### On macOS

The window also opens on a Mac, which is enough to check drawing and
sampling. The Python shipped by Apple comes with an old Tk that freezes on
recent macOS, so use the Homebrew one:

```
brew install python-tk@3.13
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Position, width, the "always on top" and "compact" options and the selected
metrics are stored in `%APPDATA%\MonitorWidget\config.json`. The height
follows the number of metrics shown.

## Uninstall

Use *Add or remove programs*, entry **Monitor Widget**.

When it was run from the sources instead, remove the auto start entry by hand:

```
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v MonitorWidget /f
```

Deleting the folder `%APPDATA%\MonitorWidget` removes the saved settings.

## Releasing

1. Bump `__version__` in `monitor_widget/version.py`.
2. Commit, then tag: `git tag v1.2.0 && git push origin v1.2.0`.

A Windows runner builds the executable with PyInstaller, wraps it in an MSIX
package and attaches it to the GitHub release. The workflow fails on purpose
when the tag and `version.py` disagree.

## Adding another metric

`monitor_widget/probes.py` holds one class per displayed value. A new metric
is a subclass of `Probe` with a `key`, a `label` and a `read()` method,
decorated with `@register`; it then shows up in the context menu on its own.

```python
@register
class DiskProbe(Probe):
    key = "disk"
    label = "Disque C:"

    def read(self):
        return psutil.disk_usage("C:\\").percent
```

## Layout

| File | Role |
| --- | --- |
| `main.py` | entry point: single instance, hidden root window |
| `monitor_widget/config.py` | reading and writing `config.json` |
| `monitor_widget/system.py` | Win32 styles, displays, registry, mutex |
| `monitor_widget/probes.py` | the measurable metrics |
| `monitor_widget/ui.py` | window, drawing, dragging, context menu |
| `monitor_widget/version.py` | version number, checked against the release tag |
| `packaging/monitor_widget.spec` | PyInstaller recipe |
| `packaging/msix/` | manifest and logos of the Microsoft Store package |
| `.github/workflows/msix.yml` | builds the package, and publishes it on a tag |
