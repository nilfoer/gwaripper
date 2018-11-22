import os
import time
import logging

logger = logging.getLogger(__name__)


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


def txt_to_list(path, txtfilename):
    """
    Reads in file, splits at newline and returns that list

    :param path: Path to dir the file is in
    :param txtfilename: Filename
    :return: List with lines of read text file as elements
    """
    with open(os.path.join(path, txtfilename), "r", encoding="UTF-8") as f:
        llist = f.read().split()
        return llist


def write_to_txtf(wstring, filename, currentusr):
    """
    Appends wstring to filename in dir named currentusr in ROOTDIR

    :param wstring: String to write to file
    :param filename: Filename
    :param currentusr: soundgasm.net user name
    :return: None
    """
    mypath = os.path.join(ROOTDIR, currentusr)
    os.makedirs(mypath, exist_ok=True)
    with open(os.path.join(mypath, filename), "a", encoding="UTF-8") as w:
        w.write(wstring)
