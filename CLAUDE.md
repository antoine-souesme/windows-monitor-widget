# CPU Widget

Borderless Windows desktop widget (Python 3 + tkinter + psutil) showing one
live system metric: large percentage, 60-second scrolling graph, green to red
color scale.

## Conventions

- Code and comments in English. User facing strings (menu labels) in French.
- No blocking calls in the UI thread: sampling runs on `after()` timers,
  never `sleep` or `psutil.cpu_percent(interval=...)`.
- Windows specific calls live in `system.py` only, and every one of them must
  stay harmless on other platforms so the code can be run on macOS/Linux.
- Never crash on bad input: a corrupted config falls back to defaults, a
  failing registry read returns False.
- Config is written on meaningful events (end of a drag, option change, exit),
  not on every mouse move.

## Layout

| File | Role |
| --- | --- |
| `cpu_widget.py` | entry point: single instance, hidden root window |
| `monitor_widget/config.py` | `%APPDATA%\CpuWidget\config.json` read/write |
| `monitor_widget/system.py` | Win32 styles, displays, `HKCU\...\Run`, mutex |
| `monitor_widget/probes.py` | the measurable metrics |
| `monitor_widget/ui.py` | window, drawing, dragging, context menu |

## Adding a metric

Subclass `Probe` in `probes.py` with a `key`, a `label` and `read()`, decorate
it with `@register`. It appears in the context menu automatically. Do not add
metric specific code to `ui.py`.

## Run and check

```
pip install -r requirements.txt
pythonw.exe cpu_widget.py          # Windows, no console
```

Outside Windows the window still opens (without transparency, tool window
style or registry support), which is enough to check drawing and sampling.
