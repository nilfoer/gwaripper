import time
import os
import logging
import re

import pyperclip

logger = logging.getLogger(__name__)

# grp1: subreddit, grp2: reddit id, grp3: title
REDDIT_URL_RE = re.compile(
        r"^(?:https?://)?(?:www\.|old\.)?reddit\.com/r/(\w+)/comments/([A-Za-z0-9]+)/(\w+)?/?")
# grp1: sgasm username, grp2: title
SGASM_URL_RE = re.compile(
        r"(?:https?://)?(?:www\.)?soundgasm\.net/(?:u|user)/([-a-zA-Z0-9_]+)/([-a-zA-Z0-9_]+)/?")


def is_sgasm_url(url):
    if re.match(SGASM_URL_RE, url) is None:
        return False
        logger.debug("NO SGASM URL: " + url)
    else:
        return True


def is_reddit_url(url):
    if re.match(REDDIT_URL_RE, url) is None:
        return False
        logger.debug("NO REDDIT URL: " + url)
    else:
        return True


site_keyword_func = {
    "sgasm": is_sgasm_url,
    "reddit": is_reddit_url,
}


def print_to_stdout(clipboard_content):
    logger.info("Found url: %s" % str(clipboard_content))


def print_write_to_txtf(wstring, linkdir, txtname):
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
    def __init__(self, predicate, callback, txtpath, pause=5.):
        self._predicate = predicate
        self._callback = callback
        self._txtpath = txtpath
        self._pause = pause
        self._stopping = False
        self.txtname = time.strftime("%Y-%m-%d_%Hh.txt")
        self.found = []

    def run(self):
        recent_value = ""
        while not self._stopping:
            tmp_value = pyperclip.paste()
            if tmp_value != recent_value:
                recent_value = tmp_value
                # if predicate is met
                if self._predicate(recent_value):
                    # call callback
                    self._callback(recent_value, self._txtpath, self.txtname)
                    # append to found list so we can return it when closing clipwatcher
                    self.found.append(recent_value)
            time.sleep(self._pause)

    def stop(self):
        self._stopping = True


def main():
    watcher = ClipboardWatcher(is_sgasm_url,
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
