# CPU Widget

A small borderless Windows desktop widget showing the live CPU load: a large
percentage, a scrolling 60-second graph, and a color going from green to
orange to red as the load rises.

## Install

```
pip install -r requirements.txt
```

Python 3.8 or later, on Windows.

## Run

Without a console window:

```
pythonw.exe cpu_widget.py
```

- Drag it anywhere with the left mouse button.
- Right click for the menu: displayed metric, start with Windows, always on
  top, quit.

Position, size, the "always on top" option and the selected metric are stored
in `%APPDATA%\CpuWidget\config.json`.

## Uninstall

Quit the widget, then remove the auto start entry if you enabled it:

```
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v CpuWidget /f
```

Deleting the folder `%APPDATA%\CpuWidget` removes the saved settings.

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
