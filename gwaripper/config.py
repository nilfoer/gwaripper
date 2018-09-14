import os.path
import time
import re
import configparser

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))

# init ConfigParser instance
config = configparser.ConfigParser()
# read config file, ConfigParser pretty much behaves like a dict, sections in in ["Reddit"] is a key that holds
# another dict with keys(USER_AGENT etc.) and values -> nested dict -> access with config["Reddit"]["USER_AGENT"]
# !! keys in sections are case-insensitive and stored in lowercase
# configparser.read() takes a list of paths if one fails it will be ignored
# An application which requires initial values to be loaded from a file should load the required file or files
# using read_file() before calling read() for any optional files
try:
    with open(os.path.join(MODULE_PATH, "config.ini"), "r") as cfg:
        config.read_file(cfg)
except FileNotFoundError:
    init_cfg = {
        "Reddit": {
            "user_agent": "gwaRipper",
            "client_id": "***REMOVED***",
        },
        "Settings": {
            "tag_filter": "[request], [script offer]",
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
    # write cfg file
    with open(os.path.join(MODULE_PATH, "config.ini"), "w") as cfg:
        config.write(cfg)


# path to dir where the soundfiles will be stored in subfolders
ROOTDIR = None
try:
    ROOTDIR = config["Settings"]["root_path"]
except KeyError:
    pass

SUPPORTED_HOSTS = {  # host type keyword: string/regex pattern to search for
                "sgasm": re.compile("soundgasm.net/u/.+/.+", re.IGNORECASE),
                "chirb.it": "chirb.it/",
                "eraudica": "eraudica.com/",
                "imgur": re.compile(r"(https?://)?i\.imgur\.com/(\w{5,7})(\.\w+)"),
                "imgur album": re.compile(r"(https?://)?(www\.|m\.)?imgur\.com/(a/|gallery/)?(\w{5,7})")
            }

# banned TAGS that will exclude the file from being downloaded (when using reddit)
# load from config ini, split at comma, strip whitespaces, ensure that they are lowercase with .lower()
KEYWORDLIST = [x.strip().lower() for x in config["Settings"]["tag_filter"].split(",")]

# tag1 is only banned if tag2 isnt there, in cfg file: tag1 &! tag2; tag3 &! tag4;...
TAG1_BUT_NOT_TAG2 = []
if config.has_option("Settings", "tag1_in_but_not_tag2"):
    for tag_comb in config["Settings"]["tag1_in_but_not_tag2"].split(";,"):
        tag1, tag2 = tag_comb.strip().split(";")
        TAG1_BUT_NOT_TAG2.append((tag1.strip().lower(), tag2.strip().lower()))


def reload_config():
    """
    Convenience function to update values in config by reading config file

    :return: None
    """
    config.read(os.path.join(MODULE_PATH, "config.ini"))


def write_config_module():
    """
    Convenience function to write config file

    :return: None
    """
    with open(os.path.join(MODULE_PATH, "config.ini"), "w") as config_file:
        # configparser doesnt preserve comments when writing
        config.write(config_file)
