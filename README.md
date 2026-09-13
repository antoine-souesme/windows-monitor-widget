# CPU Widget

A small borderless Windows desktop widget showing the live CPU load: a large
percentage, a scrolling 60-second graph, and a color going from green to
orange to red as the load rises.

## Install

Download `setup_<version>.exe` from the
[releases](../../releases) and run it. No administrator rights needed: it
installs into `%LOCALAPPDATA%\Programs\CpuWidget` for the current user.
Running a newer installer over an existing copy updates it in place and keeps
the settings.

## Run from the sources

```
pip install -r requirements.txt
pythonw.exe cpu_widget.py
```

Python 3.8 or later, on Windows.

- Drag it anywhere with the left mouse button.
- Right click for the menu: displayed metric, start with Windows, always on
  top, quit.

Position, size, the "always on top" option and the selected metric are stored
in `%APPDATA%\CpuWidget\config.json`.

## Uninstall

Use *Add or remove programs*, entry **CPU Widget**. It closes the widget and
removes the auto start entry.

When it was run from the sources instead, remove the entry by hand:

```
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v CpuWidget /f
```

Deleting the folder `%APPDATA%\CpuWidget` removes the saved settings.

## Releasing

1. Bump `__version__` in `monitor_widget/version.py`.
2. Commit, then tag: `git tag v1.2.0 && git push origin v1.2.0`.

A Windows runner builds the executable with PyInstaller, wraps it with Inno
Setup and attaches `setup_1.2.0.exe` to the GitHub release. The workflow fails
on purpose when the tag and `version.py` disagree.

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
| `cpu_widget.py` | entry point: single instance, hidden root window |
| `monitor_widget/config.py` | reading and writing `config.json` |
| `monitor_widget/system.py` | Win32 styles, displays, registry, mutex |
| `monitor_widget/probes.py` | the measurable metrics |
| `monitor_widget/ui.py` | window, drawing, dragging, context menu |
| `monitor_widget/version.py` | version number, checked against the release tag |
| `packaging/cpu_widget.spec` | PyInstaller recipe |
| `packaging/installer.iss` | Inno Setup script producing `setup_<version>.exe` |
| `.github/workflows/release.yml` | builds and publishes the installer on a tag |
