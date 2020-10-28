import time
import os
import logging
import re

from typing import Callable, List, Any

import pyperclip

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"^(?:https?://)?(?:[-A-Za-z0-9]{1,61}\.)*[-A-Za-z0-9]{2,61}\.[a-z]{2,61}/.+")


def is_url(s) -> bool:
    return bool(URL_RE.match(s))


def print_to_stdout(clipboard_content) -> None:
    logger.info("Found url: %s" % str(clipboard_content))


def print_write_to_txtf(wstring, linkdir, txtname) -> None:
    print_to_stdout(wstring)
    if not os.path.exists(linkdir):
        os.makedirs(linkdir)
    with open(os.path.join(linkdir, txtname), 'a', encoding="UTF-8") as w:
        w.write(wstring + "\n")


class ClipboardWatcher:
    """Watches for changes in clipboard that fullfill predicate and get sent to callback

    I create a subclass of threading.Thread, override the methods run and __init__ and create an instance of this class.
    By calling watcher.start() (not run()!), you start the thread.
    To safely stop the thread, I wait for -c (Keyboard-interrupt) and tell the thread to stop itself.
    In the initialization of the class, you also have a parameter pause to control how long to wait between tries.
    by Thorsten Kranz"""

    # predicate ist bedingung ob gesuchter clip content
    # hier beim aufruf in main funktion is_url_but_not_sgasm
    def __init__(self, predicate: Callable[[str], bool],
                 callback: Callable[[str, str, str], None],
                 txtpath: str, pause: float = 5.):
        self._predicate = predicate
        self._callback = callback
        self._txtpath = txtpath
        self._pause = pause
        self._stopping: bool = False
        self.txtname: str = time.strftime("%Y-%m-%d_%Hh.txt")
        self.found: List[str] = []

    def run(self) -> None:
        recent_value: str = ""
        while not self._stopping:
            # clipboard value might not be str
            tmp_value: Any = pyperclip.paste()
            if isinstance(tmp_value, str) and tmp_value != recent_value:
                recent_value = tmp_value
                # if predicate is met
                if self._predicate(recent_value):
                    # call callback
                    self._callback(recent_value, self._txtpath, self.txtname)
                    # append to found list so we can return it when closing clipwatcher
                    self.found.append(recent_value)
            time.sleep(self._pause)

    def stop(self) -> None:
        self._stopping = True


def main():
    watcher = ClipboardWatcher(is_url,
                               print_write_to_txtf, os.getcwd(),
                               0.1)

    try:
        logger.info("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        logger.info("Stopped watching clipboard!")
        logger.info("URLs were saved in: {}\n".format(watcher.txtname))


if __name__ == "__main__":
    main()
