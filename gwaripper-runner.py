#!python3
# Python 3.3 comes with PyLauncher "py.exe", installs it in the path, and registers it as the ".py" extension handler. With it, a special comment at the top of a script tells the launcher which version of Python to run
"""Convenience wrapper for running gwaripper directly from source tree.
    from: https://gehrcke.de/2014/02/distributing-a-python-command-line-application/"""

import sys

from gwaripper.cli import main
from webGUI.start_webgui import main as webgui_main

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].lower() == "webgui":
        del sys.argv[1]  # del webgui arg
        webgui_main()
    else:
        main()
