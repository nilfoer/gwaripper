#!python3
# Python 3.3 comes with PyLauncher "py.exe", installs it in the path, and registers it as the ".py" extension handler. With it, a special comment at the top of a script tells the launcher which version of Python to run
"""Convenience wrapper for running gwaripper directly from source tree.
    from: https://gehrcke.de/2014/02/distributing-a-python-command-line-application/"""

import sys

from gwaripper.cli import main
from gwaripper_webGUI.start_webgui import main as webgui_main
from gwaripper.config import ROOTDIR

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].lower() == "webgui":
        if ROOTDIR is None:
            print("Can't start webGUI before GWARipper has it's path set! Use gwaripper config -p")
        else:
            # messes with flask restart and takes the else branch below del sys.argv[1]  # del webgui arg
            webgui_main()
    else:
        main()
