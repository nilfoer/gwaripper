#!python3
# Python 3.3 comes with PyLauncher "py.exe", installs it in the path, and registers it as the ".py" extension handler. With it, a special comment at the top of a script tells the launcher which version of Python to run
"""Convenience wrapper for running gwaripper directly from source tree.
    from: https://gehrcke.de/2014/02/distributing-a-python-command-line-application/"""

from gwaripper.gwaripper import main

if __name__ == '__main__':
    main()