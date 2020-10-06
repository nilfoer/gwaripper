#!python3
# Python 3.3 comes with PyLauncher "py.exe", installs it in the path, and registers it as the ".py" extension handler. With it, a special comment at the top of a script tells the launcher which version of Python to run
"""Convenience wrapper for running gwaripper directly from source tree.
    from: https://gehrcke.de/2014/02/distributing-a-python-command-line-application/"""

import sys

from gwaripper.cli import main
from webGUI import create_app

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].lower() == "webgui":
        # use terminal environment vars to set debug etc.
        # windows: set FLASK_ENV=development -> enables debug or set FLASK_DEBUG=1
        app = create_app()
        # use threaded=False so we can leverage MangaDB's id_map
        # also makes sense since we only want to support one user (at least with write access)
        # use host='0.0.0.0' or ip to run on machine's ip address and be accessible over lan
        if len(sys.argv) > 2 and sys.argv[2] == "open":
            app.run(threaded=False, host='0.0.0.0', port=7568)
        else:
            app.run(threaded=False, port=7568)
    else:
        main()
