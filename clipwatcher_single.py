import time
import os

import pyperclip

WRITETO = os.path.join("N:", os.sep, "_archive", "test", "soundgasmNET", "_linkcol")
# windows (os.sep, "home", "m", "Dokumente", "test-sg", "_linkcol")

def is_sgasm_url(url):
    if url.startswith("htt") and "soundgasm" in url:
        return True
    print("NO SGASM URL: " + url)
    return False


def is_reddit_url(url):
    if url.startswith("htt") and "reddit" in url:
        return True
    print("NO REDDIT URL: " + url)
    return False


def print_to_stdout(clipboard_content):
    print("Found url: %s" % str(clipboard_content))


def print_write_to_txtf(wstring):
    print_to_stdout(wstring)
    if not os.path.exists(WRITETO):
        os.makedirs(WRITETO)
    with open(os.path.join(WRITETO, time.strftime("%Y-%m-%d_%Hh.txt")), 'a', encoding="UTF-8") as w:
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
    def __init__(self, predicate, callback, pause=5.):
        self._predicate = predicate
        self._callback = callback
        self._pause = pause
        self._stopping = False

    def run(self):
        recent_value = ""
        while not self._stopping:
            tmp_value = pyperclip.paste()
            if tmp_value != recent_value:
                recent_value = tmp_value
                if self._predicate(recent_value):
                    self._callback(recent_value)
            time.sleep(self._pause)

    def stop(self):
        self._stopping = True


def main():
    watcher = ClipboardWatcher(is_sgasm_url,
                               print_write_to_txtf,
                               0.1)

    try:
        print("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        print("Stopped watching clipboard!")


if __name__ == "__main__":
    main()
