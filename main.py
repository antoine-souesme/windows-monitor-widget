# -*- coding: utf-8 -*-
"""Entry point of the Monitor Widget desktop application.

Run it without a console window:  pythonw.exe main.py
"""

import sys
import tkinter as tk

from monitor_widget import config, system
from monitor_widget.ui import WidgetWindow


def main():
    # A second instance would fight the first one over the config file.
    if not system.acquire_single_instance():
        return 0

    # The hidden root window is the one Windows would list; the visible
    # widget is a child of it and stays out of the taskbar.
    root = tk.Tk()
    root.withdraw()

    values = config.load()
    widget = WidgetWindow(root, values)
    root.protocol("WM_DELETE_WINDOW", widget.quit_widget)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        widget.quit_widget()
    return 0


if __name__ == "__main__":
    sys.exit(main())
