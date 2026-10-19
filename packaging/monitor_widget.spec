# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: turns the sources into dist/MonitorWidget/MonitorWidget.exe.

One directory build (not one file) so that starting with Windows stays fast:
nothing has to be unpacked to a temporary folder at each boot.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(ROOT, "monitor_widget", "icon.ico")

analysis = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    # Read at run time by the notification area icon (system.icon_path).
    datas=[(ICON, "monitor_widget")],
    hiddenimports=[],
    excludes=["numpy", "pandas", "PIL", "unittest", "pydoc", "test"],
    noarchive=False,
)

archive = PYZ(analysis.pure)

executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MonitorWidget",
    console=False,          # no console window
    icon=ICON,              # drawn by packaging/make_icons.py
    debug=False,
    strip=False,
    upx=False,
)

COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="MonitorWidget",
)
