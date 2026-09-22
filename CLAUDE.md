# Monitor Widget

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
| `main.py` | entry point: single instance, hidden root window |
| `monitor_widget/config.py` | `%APPDATA%\MonitorWidget\config.json` read/write |
| `monitor_widget/system.py` | Win32 styles, displays, `HKCU\...\Run`, mutex |
| `monitor_widget/probes.py` | the measurable metrics |
| `monitor_widget/ui.py` | window, drawing, dragging, context menu |
| `monitor_widget/version.py` | single source of truth for the version |
| `tests/` | configuration and layout tests (no display needed) |
| `packaging/` | PyInstaller spec and MSIX build script |
| `packaging/msix/` | manifest and logos of the Microsoft Store package |
| `.github/workflows/tests.yml` | runs the tests on every pull request |
| `.github/workflows/msix.yml` | builds the Store package: artifact on a manual run, release on a tag |

## Releasing

The widget is only shipped as an MSIX package, through the Microsoft Store.
There is no `.exe` installer any more and no update code in the widget:
Windows updates a Store install on its own.

Running the Store workflow by hand builds the package and leaves it as an
artifact of the run, so a version can be tried before it is tagged.

Version lives only in `monitor_widget/version.py`. A `v<version>` tag triggers
the same build and attaches the `.msix` to the GitHub release; the workflow
refuses to run when the tag and that file disagree. Settings stay in
`%APPDATA%\MonitorWidget` across updates.

Code that resolves paths must handle the frozen case (`sys.frozen`), since
after packaging there is no `.py` file next to the executable.

## Microsoft Store

The same sources also ship as an MSIX package. `packaging/build_msix.ps1`
runs PyInstaller, drops the manifest and the logos next to the executable and
calls `makeappx`; `-Sign` adds a test signature so the package can be tried
locally, the Store signs the real one. The logos are drawn by
`packaging/make_icons.py`, which needs nothing installed. The same build
runs on GitHub (`msix.yml`), so the package can be obtained without a
Windows machine at hand.

Inside a package Windows owns the auto start (declared as a startup task in
the manifest, turned off from the system settings), so `system.is_packaged()`
hides that menu entry. `Identity` in the manifest must never change, and its
version carries a fourth number that stays at zero.

## Adding a metric

Subclass `Probe` in `probes.py` with a `key`, a `label` and `read()`, decorate
it with `@register`. It appears in the context menu automatically. Do not add
metric specific code to `ui.py`.

A metric can declare `options`: they show up under "Options des métriques",
their default lands in the configuration file on its own, and the answer comes
back through `configure()`. A metric can also draw several values side by side
by returning a tuple from `read()` and saying how many with `columns()`;
`texts()` gives the text of each one and `tint()` its color.

## Run and check

```
pip install -r requirements.txt
pythonw.exe main.py          # Windows, no console
python -m unittest discover -s tests
```

Outside Windows the window still opens (without transparency, tool window
style or registry support), which is enough to check drawing and sampling.
