# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: turns the sources into dist/MonitorWidget/MonitorWidget.exe.

One directory build (not one file) so that starting with Windows stays fast:
nothing has to be unpacked to a temporary folder at each boot.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

analysis = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
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
    icon=None,              # drop an .ico here when the project gets one
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
