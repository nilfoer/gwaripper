# NOTE: IMPORTANT module config MUST only ever be imported as "import foo" rather than
# "from foo import bar" -> see :GlobalConfigImport
import sys
import os.path
import time
import configparser

from typing import cast, List, Optional, Tuple

# NOTE: pyinstaller single folder dist and one-file exe
# sys.frozen -> packaged inside executable -> need to figure out our path
# and pass changed locations of static and template folders
#
# With the --onefile option your files will be compressed inside the exe. When
# you execute the exe, they are uncompressed and put in a temporal folder
# somewhere.
# Tha somewhere changes everytime you execute the file
#
# PyInstaller manual
# https://pyinstaller.readthedocs.io/en/stable/runtime-information.html#using-file
# PyInstaller bootloader will set the module’s __file__ attribute to the
# correct path relative to the bundle folder.
# if you import mypackage.mymodule from a bundled script, then the __file__
# attribute of that module will be sys._MEIPASS + 'mypackage/mymodule.pyc'
#
# for the bundled main script itself the above might not work, as it is unclear
# where it resides in the package hierarchy. So in when trying to find data
# files relative to the main script, sys._MEIPASS can be used. The following
# will get the path to a file other-file.dat next to the main script if not
# bundled and in the bundle folder if it is bundled
# It is always best to use absolute paths
# SOURCE_PATH = os.path.abspath(getattr(sys, '_MEIPASS',
#                                       os.path.dirname(os.path.realpath(__file__))))
# but this is _NOT_ the location of the exe that gets launched and since the folder
# changes (and gets deleted) every time we need to write to the exe location
# -> use sys.argv[0] or sys.executable
SOURCE_PATH: str
if getattr(sys, 'frozen', False):  # check if we're bundled in an exe
    SOURCE_PATH = os.path.dirname(os.path.realpath(sys.argv[0]))
else:
    SOURCE_PATH = os.path.dirname(os.path.realpath(__file__))

# init ConfigParser instance
config = configparser.ConfigParser()
# read config file, ConfigParser pretty much behaves like a dict, sections in in ["Reddit"] is a key that holds
# another dict with keys(USER_AGENT etc.) and values -> nested dict -> access with config["Reddit"]["USER_AGENT"]
# !! keys in sections are case-insensitive and stored in lowercase
# configparser.read() takes a list of paths if one fails it will be ignored
# An application which requires initial values to be loaded from a file should load the required file or files
# using read_file() before calling read() for any optional files
config.read([
    "gwaripper_config.ini", os.path.expanduser("~/.gwaripper_config.ini"),
    os.path.join(SOURCE_PATH, "gwaripper_config.ini")
], encoding="UTF-8")
# no sections -> empty config
if not config.sections():
    init_cfg = {
        "Reddit": {
            "user_agent": "gwaRipper",
            "client_id": "to get a client id visit: https://www.reddit.com/prefs/apps",
        },
        "Imgur": {
            "client_id": "to get a client id visit: https://api.imgur.com/oauth2/addclient",
        },
        "Settings": {
            "tag_filter": "[request]",
            "tag1_in_but_not_tag2": "[script offer];[script fill]",
            "db_bu_freq": "5",
            "max_db_bu": "5",
            "set_missing_reddit": "True"
        },
        "Time": {
            "last_db_bu": str(time.time()),
            "last_dl_time": "0.0",
        }
    }
    # read initial config from dict (sections are keys with dicts as values with options as keys..)
    config.read_dict(init_cfg)


# make sure to only use ROOTDIR and not the value from config in the rest of the program
# path to dir where the soundfiles will be stored in subfolders
ROOTDIR = None
try:
    ROOTDIR = config["Settings"]["root_path"]
except KeyError:
    pass

# banned TAGS that will exclude the file from being downloaded (when using reddit)
# load from config ini, split at comma, strip whitespaces, ensure that they are lowercase with .lower()
KEYWORDLIST: List[str] = [x.strip().lower() for x in config["Settings"]["tag_filter"].split(",")]

# tag1 is only banned if tag2 isnt there, in cfg file: tag1;tag2;, tag3;tag4;, ...
TAG1_BUT_NOT_TAG2: List[Tuple[str, str]] = []
if config.has_option("Settings", "tag1_in_but_not_tag2"):
    for tag_comb in config["Settings"]["tag1_in_but_not_tag2"].split(";,"):
        tag1, tag2 = tag_comb.strip().split(";")
        TAG1_BUT_NOT_TAG2.append((tag1.strip().lower(), tag2.strip().lower()))


def reload_config() -> None:
    """
    Convenience function to update values in config by reading config file

    :return: None
    """
    config.read(os.path.join(SOURCE_PATH, "config.ini"))


def write_config_module() -> None:
    """
    Convenience function to write config file

    :return: None
    """
    os.makedirs(SOURCE_PATH, exist_ok=True)
    with open(os.path.join(SOURCE_PATH, "gwaripper_config.ini"),
              "w", encoding="UTF-8") as config_file:
        # configparser doesnt preserve comments when writing
        config.write(config_file)
