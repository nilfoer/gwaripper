import sys
import os
import time
import re
import logging

logger = logging.getLogger(__name__)


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception: ", exc_info=(exc_type, exc_value, exc_traceback))

    if exc_traceback is not None:
        # printing locals by frame from: Python Cookbook p. 343/343 von Alex Martelli,
        # Anna Ravenscroft, David Ascher
        tb = exc_traceback
        # get innermost traceback
        while tb.tb_next:
            tb = tb.tb_next

        stack = []
        frame = tb.tb_frame
        # walk backwards to outermost frame -> innermost first in list
        while frame:
            stack.append(frame)
            frame = frame.f_back
        stack.reverse()  # remove if you want innermost frame first

        # we could filter ouput by filename (frame.f_code.co_filename) so that we only print locals
        # when we've reached the first frame of that file (could use part of __name__
        # (here: gwaripper.gwaripper))

        # build debug string by creating list of lines and join them on \n instead of concatenation
        # since adding strings together means creating a new string (and potentially destroying the old ones)
        # for each addition
        # add first string in list literal instead of appending it in the next line -> would be bad practice
        debug_strings = ["Locals by frame, innermost last"]

        for frame in stack:
            debug_strings.append("Frame {} in {} at line {}\n{}\n".format(frame.f_code.co_name,
                                                                          frame.f_code.co_filename,
                                                                          frame.f_lineno, "-"*100))
            for key, val in frame.f_locals.items():
                try:
                    debug_strings.append("\t{:>20} = {}".format(key, val))
                # we must absolutely avoid propagating exceptions, and str(value) could cause any
                # exception, so we must catch any
                except:
                    debug_strings.append("ERROR WHILE PRINTING VALUES")

            debug_strings.append("\n" + "-" * 100 + "\n")

        logger.debug("\n".join(debug_strings))


# sys.excepthook is invoked every time an exception is raised and uncaught
# set own custom function so we can log traceback etc to file
# from: https://stackoverflow.com/questions/6234405/logging-uncaught-exceptions-in-python by gnu_lorien
sys.excepthook = handle_exception


class RequestDelayer:
    """
    Helper class to sleep delay seconds if time_gap number of seconds have passed since
    last delay on mode "last-delay"

    Sleep if time since last request is smaller than time_gap on mode "last-request" (default)
    example for time_gap 1s delay:0.25s:
    RQ 0.25s -> DELAY RQ 0.1s -> DELAY RQ 1.5s RQ 10s RQ...
    -> min time between RQ: 0.25s(delay), max time between RQ when delay was issued < time_gap+delay

    Note: self.last_delay or request will be set to current time after delaying

    :param delay: Delay time in seconds (float)
    :param time_gap: Time to check before delay is issued (float)
    :param mode: Check if delay is needed based on either "last-request" or "last-delay"
    """

    def __init__(self, delay, time_gap, mode="last-request"):
        self.delay = delay
        self.time_gap = time_gap
        self.last_delay = None
        self.last_request = None
        if mode == "last-delay":
            self.delay_func = self._delay_mode_delay
        else:
            self.delay_func = self._delay_mode_request

    def delay_request(self):
        self.delay_func()

    def _delay_mode_delay(self):
        now = time.time()
        # delay based on last delay time
        # time since last delay > time_gap -> delay
        if self.last_delay:
            if (now - self.last_delay) > self.time_gap:
                logger.debug("Delaying by {} seconds".format(self.delay))
                time.sleep(self.delay)
                self.last_delay = now
            else:
                logger.debug("Not delayed: time since last delay {} s".format(now - self.last_delay))
        else:
            time.sleep(self.delay)
            self.last_delay = now

    def _delay_mode_request(self):
        now = time.time()
        # delay based on last request time
        # time since last request < time_gap -> delay
        if self.last_request:
            if (now - self.last_request) < self.time_gap:
                logger.debug("Delaying by {} seconds".format(self.delay))
                time.sleep(self.delay)
                self.last_request = now
            else:
                logger.debug("Not delayed: time since last request {} s".format(now - self.last_request))
                self.last_request = now
        else:
            # dont sleep on first request
            self.last_request = now


def txt_to_list(txtfilename):
    """
    Reads in file, splits at newline and returns that list

    :param path: Path to dir the file is in
    :param txtfilename: Filename
    :return: List with lines of read text file as elements
    """
    with open(txtfilename, "r", encoding="UTF-8") as f:
        llist = f.read().split()
        return llist


# src: https://gist.github.com/slowkow/7a7f61f495e3dbb7e3d767f97bd7304b
EMOJI_RE = re.compile("["
                      u"\U0001F600-\U0001F64F"  # emoticons
                      u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                      u"\U0001F680-\U0001F6FF"  # transport & map symbols
                      u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                      u"\U00002500-\U00002BEF"  # chinese char
                      u"\U00002702-\U000027B0"
                      u"\U00002702-\U000027B0"
                      u"\U000024C2-\U0001F251"
                      u"\U0001f926-\U0001f937"
                      u"\U00010000-\U0010ffff"
                      u"\u2640-\u2642"
                      u"\u2600-\u2B55"
                      u"\u200d"
                      u"\u23cf"
                      u"\u23e9"
                      u"\u231a"
                      u"\ufe0f"  # dingbats
                      u"\u3030"
                      "]+", flags=re.UNICODE)
