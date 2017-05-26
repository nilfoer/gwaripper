#! python3
import argparse
import base64
import configparser
import logging
import os
import re
import sys
import time
import urllib.request
import sqlite3
import csv
from logging.handlers import RotatingFileHandler
from urllib.parse import quote as url_quote

import bs4
import praw

# since gwaripper contains __init__.py -> considered a package, so this becomes a intra-package reference
# we could use an absolute reference with: import gwaripper.clipwatcher_single
# or relative: from . import clipwatcher_single (.. -> would be for par dir and so on)
# for more info see: https://docs.python.org/3/tutorial/modules.html#intra-package-references
# and: http://stackoverflow.com/questions/4142151/how-to-import-the-class-within-the-same-directory-or-sub-directory
# relative imports dont work when i try to run this module as a script!!!! either use __main__.py in package dir
# contents: from .bootstrap import main
#           main()
# and run package with python -m gwaripper or use helper file gwaripper-runner.py that just imports main
# and does if __name__ == "__main__": main() and run that file as script
from . import clipwatcher_single

# by neuro: http://stackoverflow.com/questions/4934806/how-can-i-find-scripts-directory-with-python
# cmd                                               output
# os.getcwd()                       N:\_archive\...\_sgasm-repo\dist (where my cmd was, cwd)
# os.path.dirname(os.path.realpath(sys.argv[0]))    C:\python3.5\Scripts (loc of gwaripper.exe) -> script path
# os.path.dirname(os.path.realpath(__file__))       c:\python3.5\lib\site-packages\gwaripper (loc of module)
# but __file__ is not always defined
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

# init Reddit instance
# installed app -> only client_id needed, but read-only access until we get a refresh_token
# for this script read-only access is enough
reddit_praw = praw.Reddit(client_id=config["Reddit"]["CLIENT_ID"],
                          client_secret=None,
                          user_agent=config["Reddit"]["USER_AGENT"])

SUPPORTED_HOSTS = {
                "sgasm": "soundgasm.net",  # may replace this with regex pattern
                "chirb.it": "chirb.it/",
                "eraudica": "eraudica.com/"
            }

# banned TAGS that will exclude the file from being downloaded (when using reddit)
# load from config ini, split at comma, strip whitespaces, ensure that they are lowercase with .lower()
KEYWORDLIST = [x.strip().lower() for x in config["Settings"]["tag_filter"].split(",")]

# tag1 is only banned if tag2 isnt there, in cfg file: tag1 &! tag2; tag3 &! tag4;...
TAG1_BUT_NOT_TAG2 = []
if config.has_option("Settings", "tag1_in_but_not_tag2"):
    for tag_comb in config["Settings"]["tag1_in_but_not_tag2"].split(";"):
        tag1, tag2 = tag_comb.split("&!")
        TAG1_BUT_NOT_TAG2.append((tag1.strip().lower(), tag2.strip().lower()))

# path to dir where the soundfiles will be stored in subfolders
ROOTDIR = None
try:
    ROOTDIR = config["Settings"]["root_path"]
except KeyError:
    pass

DLTXT_ENTRY_END = "\t" + ("___" * 30) + "\n\n\n"

# configure logging
# logfn = time.strftime("%Y-%m-%d.log")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# only log to file if ROOTDIR is set up so we dont clutter the cwd or the module dir
if ROOTDIR:
    # create a file handler
    # handler = TimedRotatingFileHandler("gwaripper.log", "D", encoding="UTF-8", backupCount=10)
    # max 1MB and keep 5 files
    handler = RotatingFileHandler(os.path.join(ROOTDIR, "gwaripper.log"),
                                  maxBytes=1048576, backupCount=5, encoding="UTF-8")
    handler.setLevel(logging.DEBUG)

    # create a logging format
    formatter = logging.Formatter("%(asctime)-15s - %(name)-9s - %(levelname)-6s - %(message)s")
    # '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handler.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(handler)

# create streamhandler
stdohandler = logging.StreamHandler(sys.stdout)
stdohandler.setLevel(logging.INFO)

# create a logging format
formatterstdo = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%H:%M:%S")
stdohandler.setFormatter(formatterstdo)
logger.addHandler(stdohandler)


def main():
    parser = argparse.ArgumentParser(description="Script to download gonewildaudio/pta posts from either reddit "
                                                 "or soundgasm.net directly.")
    # support sub-commands like svn checkout which require different kinds of command-line arguments
    subparsers = parser.add_subparsers(title='subcommands', description='valid subcommands', help='sub-command help',
                                       dest="subcmd")  # save name of used subcmd in var

    # process single links by default # nargs="*" -> zero or more arguments
    # !! -> doesnt work since we need to specify a subcommand since they work like positional arguements
    # and providing a default subcommand isnt supported atm
    # create the parser for the "links" subcommand
    parser_lnk = subparsers.add_parser('links', help='Process single link/s')
    parser_lnk.add_argument("type", help="Reddit(r) or sgasm(sg) link/s", choices=("r", "sg"))
    parser_lnk.add_argument("links", help="Links to process. Provide type of links as flag!", nargs="+")
    # set funct to call when subcommand is used
    parser_lnk.set_defaults(func=cl_link)

    parser_sgusr = subparsers.add_parser('sguser', help='Rip sgasm user/s')
    # nargs="+" -> one or more arguments
    parser_sgusr.add_argument("names", help="Names of users to rip.", nargs="+")
    parser_sgusr.set_defaults(func=cl_rip_users)
    # Required options are generally considered bad form because users expect options to be optional,
    # and thus they should be avoided when possible.

    parser_rusr = subparsers.add_parser('redditor', help='Rip redditor/s')
    parser_rusr.add_argument("limit", type=int, help="How many posts to download when ripping redditor")
    parser_rusr.add_argument("names", help="Names of users to rip.", nargs="+")
    # choices -> available options -> error if not contained; default -> default value if not supplied
    parser_rusr.add_argument("-s", "--sort", choices=("hot", "top", "new"), default="top",
                             help="Reddit post sorting method")
    parser_rusr.add_argument("-t", "--timefilter", help="Value for time filter", default="all",
                             choices=("all", "day", "hour", "month", "week", "year"))
    parser_rusr.set_defaults(func=cl_redditor)
    # we could set a function to call with these args parser_foo.set_defaults(func=foo)
    # call with args.func(args) -> let argparse handle which func to call instead of long if..elif
    # However, if it is necessary to check the name of the subparser that was invoked, the dest keyword argument
    # to the add_subparsers(): parser.add_subparsers(dest='subparser_name')
    # Namespace(subparser_name='ripuser', ...)

    parser_txt = subparsers.add_parser('fromtxt', help='Process links in txt file located in _linkcol')
    parser_txt.add_argument("type", help="Reddit(r) or sgasm(sg) link/s in txt", choices=("r", "sg"))
    parser_txt.add_argument("filename", help="Filename of txt file in _linkcol folder")
    parser_txt.set_defaults(func=cl_fromtxt)

    parser_clip = subparsers.add_parser('watch', help='Watch clipboard for sgasm/reddit links and save them to txt;'
                                                      ' option to process them immediately')
    parser_clip.add_argument("type", help="Type of links to watch for: sgasm(sg) or reddit(r)", choices=("sg", "r"))
    parser_clip.set_defaults(func=cl_watch)

    # provide shorthands or alt names with aliases
    parser_sub = subparsers.add_parser('subreddit', aliases=["sub"],
                                       help='Parse subreddit and download supported links')

    parser_sub.add_argument("sub", help="Name of subreddit")
    parser_sub.add_argument("limit", type=int, help="How many posts to download")
    parser_sub.add_argument("-s", "--sort", choices=("hot", "top"), help="Reddit post sorting method",
                            default="top")
    parser_sub.add_argument("-t", "--timefilter", help="Value for time filter", default="all",
                            choices=("all", "day", "hour", "month", "week", "year"))
    parser_sub.add_argument("-on", "--only-newer", nargs="?", default=True, type=float,
                            help="Only download submission if creation time is newer than provided utc"
                                 "timestamp or last_dl_time from config if none provided")
    parser_sub.set_defaults(func=cl_sub)

    parser_se = subparsers.add_parser('search', help='Search subreddit and download supported links')
    # parser normally uses name of dest=name (which u use to access value with args.name) var for refering to
    # argument -> --subreddit SUBREDDIT; can be different from option string e.g. -user, dest="name"
    # can be changed with metavar, when nargs=n -> tuple with n elements
    # bug in argparse: http://bugs.python.org/issue14074
    # no tuples allowed as metavars for positional arguments
    # it works with a list but the help output is wrong:
    # on usage it uses 2x['SUBREDDIT', 'SEARCHSTRING'] instead of SUBREDDIT SEARCHSTRING
    # with a tuple and as optional arg it works correctly: [-subsearch SUBREDDIT SEARCHSTRING]
    # but fails with a list: on opt arg line as well
    # [-subsearch ['SUBREDDIT', 'SEARCHSTRING'] ['SUBREDDIT', 'SEARCHSTRING']]
    # only uniform positional arguments allowed basically as in: searchstring searchstring...
    # always of the same kind
    # metavar=['SUBREDDIT', 'SEARCHSTRING'])
    parser_se.add_argument("subname", help="Name of subreddit")
    parser_se.add_argument("sstr", help="'searchstring' in QUOTES: https://www.reddit.com/wiki/search",
                           metavar="searchstring")
    parser_se.add_argument("limit", type=int, help="How many posts to download")
    parser_se.add_argument("-s", "--sort", choices=("hot", "top"), help="Reddit post sorting method",
                           default="top")
    parser_se.add_argument("-t", "--timefilter", help="Value for time filter", default="all",
                           choices=("all", "day", "hour", "month", "week", "year"))
    parser_se.set_defaults(func=cl_search)

    parser_cfg = subparsers.add_parser("config", help="Configure script: save location etc.")
    parser_cfg.add_argument("-p", "--path", help="Set path to root directory, "
                                                 "where all the files will be downloaded to")
    parser_cfg.add_argument("-bf", "--backup-freq", metavar="FREQUENCY", type=float,
                            help="Set auto backup frequency in days")
    parser_cfg.add_argument("-bn", "--backup-nr", metavar="N-BACKUPS", type=int,
                            help="Set max. number of backups to keep")
    parser_cfg.add_argument("-tf", "--tagfilter", help="Set banned strings/tags in reddit title", nargs="+",
                            metavar="TAG")
    parser_cfg.add_argument("-tco", "--tag-combo-filter", help="Set banned tag when other isnt present: "
                                                               "Tag1 is only banned when Tag2 isnt found, synatx"
                                                               "is: Tag1&!Tag2 Tag3&!Tag4",
                            metavar="TAGCOMBO", nargs="+")
    parser_cfg.set_defaults(func=cl_config)

    # TODO implement verbosity with: stdohandler.setLevel(logging.INFO)?
    # -> for this to make sense change some logging lvls
    # parser.add_argument("-v", "--verbosity", help="How much information is  printed in the console")
    parser.add_argument("-te", "--test", action="store_true")

    # check with: if not len(sys.argv) > 1
    # if no arguments were passed and call our old input main func; or use argument with default value args.old
    if not len(sys.argv) > 1:
        print("No arguments passed! Call this script from the command line with -h to show available commands.")
        argv_str = input("Simulating command line input!!\n\nType in command line args:\n").split()

        # simulate shell/cmd way of considering strings with spaces in quotation marks as one single arg/string
        argv_clean = []
        # index of element in list with first quotation mark
        first_i = None
        # iterate over list, keeping track of index with enumerate
        for i, s in enumerate(argv_str):
            # found start of quote and were not currently looking for the end of a quote (first_i not set)
            # ("\"" in s) or ("\'" in s) and not first_i needs to be in extra parentheses  or it will be evaluated like:
            # True | (False & False) -> True, since only ("\'" in s) and not first_i get connected with and
            # (("\"" in s) or ("\'" in s)) and not first_i:
            # (This OR This must be true) AND not This must be false
            if (s.startswith("\"") or s.startswith("\'")) and not first_i:
                # element contains whole quote
                if s.endswith("\"") or s.endswith("\'"):
                    argv_clean.append(s.strip("\"").strip("\'"))
                else:
                    # save index
                    first_i = i
                # continue with next element in list
                continue
            # found end of quote and were currently looking for the end of a quote (first_i set)
            elif (s.endswith("\"") or s.endswith("\'")) and first_i:
                # get slice of list from index of first quot mark to this index: argv_str[first_i:i+1]
                # due to how slicing works we have to +1 the current i
                # join the slice with spaces to get the spaces back: " ".join()
                # get rid of quot marks with strip("\"")
                # append str to clean list
                argv_clean.append(" ".join(argv_str[first_i:i + 1]).strip("\"").strip("\'"))
                # unset first_i
                first_i = None
                continue
            # quote started (first_i set) but didnt end (last element of list)
            elif i == len(argv_str) - 1 and first_i:
                argv_clean.append(" ".join(argv_str[first_i:i + 1]).strip("\"").strip("\'"))
                continue
            elif not first_i:
                # normal element of list -> append to clean list
                argv_clean.append(s)
        # simulate command line input by passing in list like: ['--sum', '7', '-1', '42']
        # which is the same as prog.py --sum 7 -1 42 -> this is also used in docs of argparse
        args = parser.parse_args(argv_clean)
    else:
        # parse_args() will only contain attributes for the main parser and the subparser that was selected
        args = parser.parse_args()

    # if root dir isnt set
    if ROOTDIR:
        if args.test:
            # test code
            tit = "[F4F][F4M][Daddy] Hypno for both sexes"
            print(check_submission_banned_tags(tit, KEYWORDLIST, TAG1_BUT_NOT_TAG2))

        else:
            # call func that was selected for subparser/command
            args.func(args)
    # rootdir istn set but we want to call cl_config
    elif not ROOTDIR and args.subcmd == "config":
        cl_config(args)
    else:
        print("root_path not set in config.ini, use command config -p 'C:\\absolute\\path' to specify where the"
              "files will be downloaded to")


def cl_link(args):
    if args.type == "sg":
        llist = gen_audiodl_from_sglink(args.links)
        rip_audio_dls(llist)
    else:
        llist = get_sub_from_reddit_urls(args.links)
        adl_list = parse_submissions_for_links(llist)
        rip_audio_dls(adl_list)


def cl_redditor(args):
    limit = args.limit
    time_filter = args.timefilter
    for usr in args.names:
        redditor = reddit_praw.redditor(usr)
        if args.sort == "hot":
            sublist = redditor.submissions.hot(limit=limit)
        elif args.sort == "top":
            sublist = redditor.submissions.top(limit=limit, time_filter=time_filter)
        else:  # just get new posts if input doesnt match hot or top
            sublist = redditor.submissions.new(limit=limit)
        adl_list = parse_submissions_for_links(sublist)
        if adl_list:
            rip_audio_dls(adl_list)
        else:
            logger.warning("No subs recieved from user {} with time_filter {}".format(usr, args.timefilter))


def cl_rip_users(args):
    for usr in args.names:
        rip_usr_to_files(usr)


def cl_fromtxt(args):
    mypath = os.path.join(ROOTDIR, "_linkcol")
    if args.type == "sg":
        rip_audio_dls(gen_audiodl_from_sglink(txt_to_list(mypath, args.filename)))
    else:
        llist = get_sub_from_reddit_urls(txt_to_list(mypath, args.filename))
        adl_list = parse_submissions_for_links(llist, True)
        rip_audio_dls(adl_list)


def cl_watch(args):
    if args.type == "sg":
        found = watch_clip("sgasm")
        if found:
            llist = gen_audiodl_from_sglink(found)
            rip_audio_dls(llist)
    else:
        found = watch_clip("reddit")
        if found:
            llist = get_sub_from_reddit_urls(found)
            adl_list = parse_submissions_for_links(llist, True)
            rip_audio_dls(adl_list)


def cl_sub(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter
    if sort == "top":
        adl_list = parse_submissions_for_links(parse_subreddit(args.sub, sort, limit, time_filter=time_filter))
    else:
        # fromtxt False -> check lastdltime against submission date of posts when dling from hot posts
        adl_list = parse_submissions_for_links(parse_subreddit(args.sub, sort, limit), time_check=args.only_newer)
        write_last_dltime()
    rip_audio_dls(adl_list)


def cl_search(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter

    found_subs = search_subreddit(args.subname, args.sstr, limit=limit, time_filter=time_filter,
                                  sort=sort)
    adl_list = parse_submissions_for_links(found_subs, True)
    if adl_list:
        rip_audio_dls(adl_list)
    else:
        logger.warning("No matching subs/links found in {}, with: '{}'".format(args.subname, args.sstr))


def cl_config(args):
    changed = False
    if args.path:
        # normalize path, remove double \ and convert / to \ on windows
        path_in = os.path.normpath(args.path)
        # i dont need to change cwd and ROOTDIR since script gets restarted anyway
        try:
            config["Settings"]["root_path"] = path_in
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"root_path": path_in}
        changed = True
        print("New root dir is: {}".format(path_in))
    # not elif since theyre not mutually exclusive
    if args.backup_freq:
        try:
            config["Settings"]["db_bu_freq"] = str(args.backup_freq)
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"db_bu_freq": str(args.backup_freq)}
        changed = True
        print("Auto backups are due every {} days now!".format(args.backup_freq))
    if args.backup_nr:
        try:
            config["Settings"]["max_db_bu"] = str(args.backup_nr)
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"max_db_bu": str(args.backup_nr)}
        changed = True
        print("{} backups will be kept from now on".format(args.backup_nr))
    if args.tagfilter:
        tf_str = ", ".join(args.tagfilter).strip(", ")
        try:
            config["Settings"]["tag_filter"] = tf_str
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"tag_filter": tf_str}
        changed = True
        print("Banned tags were set to: {}".format(tf_str))
    if args.tag_combo_filter:
        t12_str = "; ".join(args.tag_combo_filter).strip("; ")
        try:
            config["Settings"]["tag1_in_but_not_tag2"] = t12_str
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"tag1_in_but_not_tag2": t12_str}
        changed = True
        print("Banned tag combos were set to: {}".format(t12_str))
    if not changed:
        # print current cfg
        for sec in config.sections():
            print("[{}]".format(sec))
            for option, val in config[sec].items():
                print("{} = {}".format(option, val))
            print("")
        return  # so we dont reach writing of cfg
    # write updated config
    write_config_module()


class AudioDownload:
    """
    Represents an audio post that is
    """
    def __init__(self, page_url, host, reddit_info=None):
        self.page_url = page_url
        self.host = host
        self.reddit_info = reddit_info
        # use reddit user name if not sgasm
        if host == "sgasm":
            self.name_usr = self.page_url.split("/u/", 1)[1].split("/", 1)[0]
        else:
            self.name_usr = self.reddit_info["r_user"]
        self.downloaded = False
        self.url_to_file = None
        self.file_type = None
        self.title = None
        self.filename_local = None
        self.descr = None
        self.date = None
        self.time = None

    def call_host_get_file_info(self):
        """
        Calls appropriate method to get file info for host type
        :return: None
        """
        if self.host == "sgasm":
            self._set_sgasm_info()
        elif self.host == "chirb.it":
            self._set_chirbit_url()
        elif self.host == "eraudica":
            self._set_eraudica_info()

    def _set_chirbit_url(self):
        """
        Gets and sets the direct url for downloading the audio file on self.page_url, the file type and
        removes special chars from filename

        Use bs4 to get a reversed base64 encoded string from <i> tag's data-fd attribute
        Reverse it with a slice and decode it with base64.b64decode
        :return: None
        """
        site = urllib.request.urlopen(self.page_url)
        html = site.read().decode('utf-8')
        site.close()
        soup = bs4.BeautifulSoup(html, "html.parser")

        # selects ONE i tag with set data-fd attribute beneath tag with class .wavholder beneath div with id main
        # then get attribute data-fd
        str_b64 = soup.select_one('div#main .wavholder i[data-fd]')["data-fd"]
        # reverse string using a slice -> string[start:stop:step], going through whole string with step -1 -> reverse
        str_b64_rev = str_b64[::-1]
        # decode base64 string to get url to file -> returns byte literal -> decode with appropriate encoding
        # this link EXPIRES so get it right b4 downloading
        self.url_to_file = base64.b64decode(str_b64_rev).decode("utf-8")
        self.file_type = self.url_to_file.split("?")[0][-4:]
        self.title = self.reddit_info["title"]

    def _set_eraudica_info(self):
        site = urllib.request.urlopen(self.page_url)
        html = site.read().decode('utf-8')
        site.close()
        soup = bs4.BeautifulSoup(html, "html.parser")

        # selects script tags beneath div with id main and div class post
        # returns list of bs4.element.Tag -> access text with .text
        scripts = soup.select("div#main div.post script")[1].text
        # vars that are needed to gen dl link are included in script tag
        # access group of RE (part in '()') with .group(index)
        # Group 0 is always present; it’s the whole RE
        fname = re.search("var filename = \"(.+)\"", scripts).group(1)
        server = re.search("var playerServerURLAuthorityIncludingScheme = \"(.+)\"", scripts).group(1)
        dl_token = re.search("var downloadToken = \"(.+)\"", scripts).group(1)
        # convert fname to make it url safe with urllib.quote (quote_plus replaces spaces with plus signs)
        fname = url_quote(fname)  # renamed so i dont accidentally create a func with same name

        self.url_to_file = "{}/fd/{}/{}".format(server, dl_token, fname)
        self.title = self.reddit_info["title"]
        self.file_type = fname[-4:]

    def _set_sgasm_info(self):
        # TODO Temporary? check if we alrdy called this so we dont call it twice when we call it to fill
        # in missing information in the df
        if not self.url_to_file:
            logger.info("Getting soundgasm info of: %s" % self.page_url)
            try:
                site = urllib.request.urlopen(self.page_url)
                html = site.read().decode('utf-8')
                site.close()

                soup = bs4.BeautifulSoup(html, "html.parser")

                title = soup.select_one("div.jp-title").text

                # set instance values
                self.url_to_file = re.search("m4a: \"(.+)\"", html).group(1)
                self.file_type = ".m4a"
                self.title = title
                self.descr = soup.select_one("div.jp-description > p").text
            except urllib.request.HTTPError:
                logger.warning("HTTP Error 404: Not Found: \"%s\"" % self.page_url)

    # From Hitchhiker's Guide to Python:
    # When a function grows in complexity it is not uncommon to use multiple return statements inside the function’s
    # body. However, in order to keep a clear intent and a sustainable readability level, it is preferable to avoid
    # returning meaningful values from many output points in the body.
    # [...] [2 main reasons for return -> when it has been processed normally, and the error cases
    # If you do not wish to raise exceptions for the second case -> return None or False -> return as early
    # as possible -> flatten structure ->  all the code after the return­because­of­error statement can
    # assume the condition is met to further compute the function’s main result -> often multiple such returns
    # are necessary]
    # When a function has multiple main exit points for its normal course, it becomes difficult to debug the
    # returned result, so it may be preferable to keep a single exit point. This will also help factoring out
    # some code paths, and the multiple exit points are a probable indication that such a refactoring is needed.
    def gen_filename(self, db_con, dl_root):
        """
        Generates filename to save file locally by replacing chars in the title that are not:
         \w(regex) - , . _ [ ] or a whitespace(" ")
        with an underscore and limiting its length. If file exists it adds a number padded
        to a width of 2 starting at one till there is no file with that name
        :param db_con: Connection to sqlite db
        :param dl_root: Path to root dir of the script (where all the downloads etc. are saved)
        :return: String with filename and added extension
        """
        # [^\w\-_\.,\[\] ] -> match not(^) any of \w \- _  and whitepsace etc.,
        # replace any that isnt in the  [] with _
        filename = re.sub("[^\w\-_.,\[\] ]", "_", self.title[0:110])
        ftype = self.file_type

        mypath = os.path.join(dl_root, self.name_usr)
        # isfile works without checking if dir exists first
        if os.path.isfile(os.path.join(mypath, filename + ftype)):
            if check_direct_url_for_dl(db_con, self.url_to_file):
                # TODO Temporary, missing in docstring
                # set filename since we need it to update in db
                self.filename_local = filename + ftype
                set_missing_values_db(db_con, self)
                logger.warning("!!! File already exists and was found in direct url_file but not in urls! "
                               "--> not renaming --> SKIPPING")
                # No need to return filename since file was already downloaded
                # mb refactor so we dont have to function exits, e.g. setting filename to None and at end of func
                # return with if-else...
                return None
            else:
                i = 0

                # You don't need to copy a Python string. They are immutable, so concatenating or slicing
                # returns a new string
                filename_old = filename

                # file alrdy exists but it wasnt in the url database -> prob same titles only one tag
                # or the ending is different (since fname got cut off, so we dont exceed win path limit)
                # count up i till file doesnt exist anymore
                while os.path.isfile(os.path.join(mypath, filename + ftype)):
                    i += 1
                    # :02d -> pad number with 0 to a width of 2, d -> digit(int)
                    filename = "{}_{:02d}".format(filename_old, i)
                logger.info("FILE ALREADY EXISTS - ADDED: _{:02d}".format(i))

        return filename + ftype

    def download(self, db_con, curfnr, maxfnr, dl_root):
        """
        Will download the file to dl_root in a subfolder named self.name_usr
        Calls self.gen_filename to get a valid filename and sets date and time of the download.
        Also calls method to add dl to db commits when download is successful, does a rollback
        when not (exception raised). Calls self.write_selftext_file if reddit_info is not None
        :param db_con: Connection to sqlite db
        :param curfnr: Current file number
        :param maxfnr: Max files to download
        :param dl_root: Root dir of script/where dls will be saved in subdirs
        :return: Current file nr(int)
        """
        if self.url_to_file is not None:
            curfnr += 1

            mypath = os.path.join(dl_root, self.name_usr)
            if not os.path.exists(mypath):
                os.makedirs(mypath)
            self.filename_local = self.gen_filename(db_con, dl_root)

            if self.filename_local:
                logger.info("Downloading: {}..., File {} of {}".format(self.filename_local, curfnr, maxfnr))
                self.date = time.strftime("%d/%m/%Y")
                self.time = time.strftime("%H:%M:%S")
                # set downloaded
                self.downloaded = True

                try:
                    # automatically commits changes to db_con if everything succeeds or does a rollback if an
                    # exception is raised
                    with db_con:
                        # executes the SQL query but leaves commiting it to with db_con in line above
                        self._add_to_db(db_con)
                        # func passed as kwarg reporthook gets called once on establishment of the network connection
                        # and once after each block read thereafter. The hook will be passed three arguments;
                        # a count of blocks transferred so far, a block size in bytes, and the total size of the file
                        # total size is -1 if unknown
                        urllib.request.urlretrieve(self.url_to_file,
                                                   os.path.abspath(os.path.join(mypath, self.filename_local)),
                                                   reporthook=prog_bar_dl)
                except urllib.request.HTTPError:
                    # dl failed set downloaded
                    self.downloaded = False
                    logger.warning("HTTP Error 404: Not Found: \"%s\"" % self.url_to_file)

                if self.reddit_info:
                    # also write reddit selftext in txtfile with same name as audio
                    self.write_selftext_file(dl_root)
        else:
            logger.warning("FILE DOWNLOAD SKIPPED - NO DATA RECEIVED")

        return curfnr

    # normally docstring only for public! modules, functions, methods..
    def _add_to_db(self, db_con):
        """
        Adds instance attributes and reddit_info values to the database using named SQL query
        parameters with a dictionary.
        DOESN'T COMMIT the transaction, since the context manager in self.download() needs to be
        able to do a rollback if the dl fails, will be commited in
        :param db_con: Connection obj to sqlite db
        :return: None
        """
        # create dict with keys that correspond to the named parameters in the SQL query
        # set vals contained in reddit_info to NULL
        val_dict = {
            "date": self.date,
            "time": self.time,
            "description": self.descr,
            "local_filename": self.filename_local,
            "title": self.title,
            "url_file": self.url_to_file,
            "url": self.page_url,
            "sgasm_user": self.name_usr,
            "created_utc": "NULL",
            "r_post_url": "NULL",
            "reddit_id": "NULL",
            "reddit_title": "NULL",
            "reddit_url": "NULL",
            "reddit_user": "NULL",
            "subreddit_name": "NULL"
        }

        # reddit_info not None -> update dict with actual vals from reddit_info dict
        # update([other]): Update the dictionary with the key/value pairs from other, overwriting existing keys
        if self.reddit_info:
            val_dict.update({
                "created_utc": self.reddit_info["created_utc"],
                "r_post_url": self.reddit_info["r_post_url"],
                "reddit_id": self.reddit_info["id"],
                "reddit_title": self.reddit_info["title"],
                "reddit_url": self.reddit_info["permalink"],
                "reddit_user": self.reddit_info["r_user"],
                "subreddit_name": self.reddit_info["subreddit"]
            })

        db_con.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                       "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                       "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                       ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                       ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                       ":sgasm_user, :subreddit_name)", val_dict)

    def write_selftext_file(self, dl_root):
        """
        Write selftext to a text file if not None, reddit_info must not be None!!
        :param dl_root: Path of root directory where all downloads are saved to (in username folders)
        :return: None
        """
        if self.reddit_info["selftext"]:
            # write_to_txtf uses append mode, but we'd have the selftext several times in the file since
            # there are reddit posts with multiple sgasm files
            # write_to_txtf(self.reddit_info["selftext"], self.filename_local + ".txt", self.name_usr)
            mypath = os.path.join(dl_root, self.name_usr)
            if not os.path.exists(mypath):
                os.makedirs(mypath)
            # if selftext file doesnt already exists
            if not os.path.isfile(os.path.join(mypath, self.filename_local + ".txt")):
                with open(os.path.join(mypath, self.filename_local + ".txt"), "w", encoding="UTF-8") as w:
                    w.write(self.reddit_info["selftext"])


# Docstrings = How to use code
#
# Comments = Why (rationale) & how code works
#
# Docstrings explain how to use code, and are for the users of your code. Uses of docstrings:
# Explain the purpose of the function even if it seems obvious to you, because it might not be obvious to
# someone else later on.
# Describe the parameters expected, the return values, and any exceptions raised.
# If the method is tightly coupled with a single caller, make some mention of the caller
# (though be careful as the caller might change later).
# Comments explain why, and are for the maintainers of your code. Examples include notes to yourself, like:
# !!! BUG: ...
# !!! FIX: This is a hack
# ??? Why is this here?
def prog_bar_dl(blocknum, blocksize, totalsize):
    """
    Displays a progress bar to sys.stdout

    blocknum * blocksize == bytes read so far
    Only display MB read when total size is -1
    Calc percentage of file download, number of blocks to display is bar length * percent/100
    String to display is Downloading: xx.x% [#*block_nr + "-"*(bar_len-block_nr)] xx.xx MB

    http://stackoverflow.com/questions/13881092/download-progressbar-for-python-3
    by J.F. Sebastian
    combined with:
    http://stackoverflow.com/questions/3160699/python-progress-bar
    by Brian Khuu
    and modified
    :param blocknum: Count of blocks transferred so far
    :param blocksize: Block size in bytes
    :param totalsize: Total size of the file in bytes
    :return: None
    """
    bar_len = 25  # Modify this to change the length of the progress bar
    # blocknum is current block, blocksize the size of each block in bytes
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize  # 1e2 == 100.0
        # nr of blocks
        block_nr = int(round(bar_len*readsofar/totalsize))
        # %5.1f: pad to 5 chars and display one decimal, type float, %% -> escaped %sign
        # %*d -> Parametrized, width -> len(str(totalsize)), value -> readsofar
        # s = "\rDownloading: %5.1f%% %*d / %d" % (percent, len(str(totalsize)), readsofar, totalsize)
        sn = "\rDownloading: {:4.1f}% [{}] {:4.2f} / {:.2f} MB".format(percent, "#"*block_nr + "-"*(bar_len-block_nr),
                                                                       readsofar / 1024**2, totalsize / 1024**2)
        sys.stdout.write(sn)
        if readsofar >= totalsize:  # near the end
            sys.stdout.write("\n")
    else:  # total size is unknown
        sys.stdout.write("\rDownloading: %.2f MB" % (readsofar / 1024**2,))
    # Python's standard out is buffered (meaning that it collects some of the data "written" to standard out before
    # it writes it to the terminal). flush() forces it to "flush" the buffer, meaning that it will write everything
    # in the buffer to the terminal, even if normally it would wait before doing so.
    sys.stdout.flush()


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


def get_sub_from_reddit_urls(urllist):
    """
    Filters duplicate urls and returns a list of Submission obj, that the urls are pointing to
    :param urllist: List with urls point to reddit submissions
    :return: List with Submission obj that were obtained from the urls in urllist
    """
    urls_unique = set(urllist)
    sublist = []
    for url in urls_unique:
        sublist.append(reddit_praw.submission(url=url))
    return sublist


# avoid too many function calls since they are expensive in python
def gen_audiodl_from_sglink(sglinks):
    """
    Generates AudioDownload instances initiated with the sgasm links and returns them in a list
    :param sglinks: Links to soundgasm.net posts
    :return: List containing AudioDownload instances that were created with the urls in sglinks
    """
    dl_list = []
    # set -> remove duplicates
    for link in set(sglinks):
        a = AudioDownload(link, "sgasm")
        dl_list.append(a)
    return dl_list


def rip_audio_dls(dl_list):
    """
    Accepts list of AudioDownload instances, loads sqlite db and fetches downloaded urls from it.
    Filters them for new downloads and saves them to disk by calling call_host_get_file_info and download method.
    Calls backup_db to do automatic backups after all operations are done.
    :param dl_list: List of AudioDownload instances
    """
    # when assigning instance Attributes of classes like self.url
    # Whenever we assign or retrieve any object attribute like url, Python searches it in the object's
    # __dict__ dictionary -> Therefore, a_file.url internally becomes a_file.__dict__['url'].
    # could just work with dicts instead since theres no perf loss, but using classes may be easier to
    # implement new features

    # load dataframe
    # df = pd.read_json("../sgasm_rip_db.json", orient="columns")

    # also possible to use .execute() methods on connection, which then create a cursor object and calls the
    # corresponding mehtod with given params and returns the cursor
    conn, c = load_sql_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))

    # load already downloaded urls -> list -> to set since searching in set is A LOT faster
    c.execute("SELECT url FROM Downloads")
    urls_dled = set([tupe[0] for tupe in c.fetchall()])

    # create dict that has page urls as keys and AudioDownload instances as values
    # dict comrehension: d = {key: value for (key, value) in iterable}
    # duplicate keys -> last key value pair is in dict, values of the same key that came before arent
    dl_dict = {audio.page_url: audio for audio in dl_list}

    # returns list of new downloads, dl_dict still holds all of them
    new_dls = filter_alrdy_downloaded(urls_dled, dl_dict, conn)

    filestodl = len(new_dls)
    dlcounter = 0

    for url in new_dls:
        audio_dl = dl_dict[url]
        # get appropriate func for host to get direct url, sgasm title etc.
        audio_dl.call_host_get_file_info()

        dlcounter = audio_dl.download(conn, dlcounter, filestodl, ROOTDIR)

    # export db to csv -> human readable without tools
    export_csv_from_sql(os.path.join(ROOTDIR, "gwarip_db_exp.csv"), conn)
    conn.close()

    # auto backup
    backup_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))


def load_sql_db(filename):
    """
    Creates connection to sqlite3 db and a cursor object. Creates the table if it doesnt exist yet since,
    the connect function creates the file if it doesnt exist but it doesnt contain any tables then.
    :param filename: Filename string/path to file
    :return: connection to sqlite3 db and cursor instance
    """
    conn = sqlite3.connect(filename)
    c = conn.cursor()
    # create table if it doesnt exist
    c.execute("CREATE TABLE IF NOT EXISTS Downloads (id INTEGER PRIMARY KEY ASC, date TEXT, time TEXT, "
              "description TEXT, local_filename TEXT, title TEXT, url_file TEXT, url TEXT, created_utc REAL, "
              "r_post_url TEXT, reddit_id TEXT, reddit_title TEXT,reddit_url TEXT, reddit_user TEXT, "
              "sgasm_user TEXT, subreddit_name TEXT)")
    # commit changes
    conn.commit()

    return conn, c


def rip_usr_to_files(currentusr):
    """
    Calls functions to download all the files of sgasm user to disk
    :param currentusr: soundgasm.net username string
    :return: None
    """
    sgasm_usr_url = "https://soundgasm.net/u/{}".format(currentusr)
    logger.info("Ripping user %s" % currentusr)

    dl_list = gen_audiodl_from_sglink(rip_usr_links(sgasm_usr_url))

    rip_audio_dls(dl_list)


def rip_usr_links(sgasm_usr_url):
    """
    Gets all the links to soundgasm.net posts of the user/at user url and returns them in a list

     Use bs4 to select all <a> tags directly beneath <div> with class sound-details
     Writes content of href attributes of found tags to list and return it
    :param sgasm_usr_url: Url to soundgasm.net user site
    :return: List of links to soundgasm.net user's posts
    """
    site = urllib.request.urlopen(sgasm_usr_url)
    html = site.read().decode('utf-8')
    site.close()

    soup = bs4.BeautifulSoup(html, 'html.parser')

    # decision for bs4 vs regex -> more safe and speed loss prob not significant
    # splits: 874 µs per loop; regex: 1.49 ms per loop; bs4: 84.3 ms per loop
    anchs = soup.select("div.sound-details > a")
    user_files = [a["href"] for a in anchs]

    logger.info("Found {} Files!!".format(len(user_files)))
    return user_files


def set_missing_values_db(db_con, audiodl_obj):
    """
    Updates row of file entry in db with information from audiodl_obj like page_url, filename_local
    and reddit_info dict, only sets values if previous entry was NULL/None
    :param db_con: Connection to sqlite db
    :param audiodl_obj: instance of AudioDownload whose entry should be updated
    :return: None
    """
    # Row provides both index-based and case-insensitive name-based access to columns with almost no memory overhead
    db_con.row_factory = sqlite3.Row
    # we need to create new cursor after changing row_factory
    c = db_con.cursor()

    # even though Row class can be accessed both by index (like tuples) and case-insensitively by name
    # reset row_factory to default so we get normal tuples when fetching (should we generate a new cursor)
    # new_c will always fetch Row obj and cursor will fetch tuples
    db_con.row_factory = None
    c.execute("SELECT * FROM Downloads WHERE url_file = ?", (audiodl_obj.url_to_file,))
    # get row
    row_cont = c.fetchone()

    set_helper = (("reddit_title", "title"), ("reddit_url", "permalink"), ("reddit_user", "r_user"),
                  ("created_utc", "created_utc"), ("reddit_id", "id"), ("subreddit_name", "subreddit"),
                  ("r_post_url", "r_post_url"))

    upd_cols = []
    upd_vals = []
    if row_cont["url"] is None:
        # add col = ? strings to list -> join them later to SQL query
        upd_cols.append("url = ?")
        upd_vals.append(audiodl_obj.page_url)
    if row_cont["local_filename"] is None:
        upd_cols.append("local_filename = ?")
        upd_vals.append(audiodl_obj.filename_local)
    if audiodl_obj.reddit_info:
        for col, key in set_helper:
            if row_cont[col] is None:
                upd_cols.append("{} = ?".format(col))
                upd_vals.append(audiodl_obj.reddit_info[key])

    if upd_cols:
        logger.debug("Updating file entry with new info for: {}".format(", ".join(upd_cols)))
        # append url since upd_vals need to include all the param substitutions for ?
        upd_vals.append(audiodl_obj.url_to_file)
        # would work in SQLite version 3.15.0 (2016-10-14), but this is 3.8.11, users would have to update as well
        # so not a good idea
        # print("UPDATE Downloads SET ({}) = ({}) WHERE url_file = ?".format(",".join(upd_cols),
        #                                                               ",".join("?"*len(upd_cols))))

        # Connection objects can be used as context managers that automatically commit or rollback transactions.
        # In the event of an exception, the transaction is rolled back; otherwise, the transaction is committed
        # Unlike with open() etc. connection WILL NOT GET CLOSED
        with db_con:
            # join only inserts the string to join on in-between the elements of the iterable (none at the end)
            # format to -> e.g UPDATE Downloads SET url = ?,local_filename = ? WHERE url_file = ?
            c.execute("UPDATE Downloads SET {} WHERE url_file = ?".format(",".join(upd_cols)), upd_vals)


def write_to_txtf(wstring, filename, currentusr):
    """
    Appends wstring to filename in dir named currentusr in ROOTDIR
    :param wstring: String to write to file
    :param filename: Filename
    :param currentusr: soundgasm.net user name
    :return: None
    """
    mypath = os.path.join(ROOTDIR, currentusr)
    if not os.path.exists(mypath):
        os.makedirs(mypath)
    with open(os.path.join(mypath, filename), "a", encoding="UTF-8") as w:
        w.write(wstring)


def check_direct_url_for_dl(db_con, direct_url):
    """
    Fetches url_file col from db and unpacks the 1-tuples, then checks if direct_url
    is in the list, if found return True
    :param db_con: Connection to sqlite db
    :param direct_url: String of direct url to file
    :return: True if direct_url is in col url_file of db else False
    """
    c = db_con.execute("SELECT url_file FROM Downloads")
    # converting to set would take just as long (for ~10k entries) as searching for it in list
    # returned as list of 1-tuples, use generator to unpack, so when we find direct_url b4
    # the last row we dont have to generate the remaining tuples and we only use it once
    # only minimally faster (~2ms for 10k rows)
    file_urls = (tup[0] for tup in c.fetchall())
    if direct_url in file_urls:
        return True
    else:
        return False


def filter_alrdy_downloaded(downloaded_urls, dl_dict, db_con):
    """
    Filters out already downloaded urls and returns a set of new urls
    Intersects downloaded_urls with dict keys -> elements that are in both sets (duplicates)
    Then build the symmetric_difference between dict keys and duplicates -> set with elements that
    are in either of the sets but not both -> duplicates get filtered out
    Logs duplicate downloads
    :param downloaded_urls: set of downloaded urls
    :param dl_dict: dict with urls as keys and the corresponding AudioDownload obj as values
    :param db_con: connection to sqlite3 db
    :return: set of new urls
    """
    to_filter = dl_dict.keys()
    # Return the intersection of two sets as a new set. (i.e. all elements that are in both sets.)
    duplicate = downloaded_urls.intersection(to_filter)

    for dup in duplicate:
        # TODO We can leave this in if we supply a config option for it, but we need to change set_missing_values_db
        # to use url instead of url so we dont have to get sgasm_info (new users will always have url)
        # when we got reddit info get sgasm info even if this file was already downloaded b4
        # then write missing info to df and write selftext to file
        if dl_dict[dup].reddit_info and ("soundgasm" in dup):
            logger.info("Filling in missing reddit info: TEMPORARY")
            dl_dict[dup].call_host_get_file_info()
            set_missing_values_db(db_con, dl_dict[dup])
            dl_dict[dup].write_selftext_file(ROOTDIR)
    if duplicate:
        logger.info("{} files were already downloaded!".format(len(duplicate)))
        logger.debug("Already downloaded urls:\n{}".format("\n".join(duplicate)))

    # set.symmetric_difference()
    # Return a new set with elements in either the set or other but not both.
    # -> duplicates will get removed from unique_urls
    result = to_filter.symmetric_difference(duplicate)

    return result


def watch_clip(domain):
    """
    Watches clipboard for links of domain

    Convert string to python code to be able to pass function to check if clipboard content is
    what we're looking for to ClipboardWatcher init
    :param domain: keyword that points to function is_domain_url in clipwatcher_single module
    :return: List of found links, None if there None
    """
    # function is_domain_url will be predicate
    # eval: string -> python code
    dm = eval("clipwatcher_single.is_" + domain + "_url")
    watcher = clipwatcher_single.ClipboardWatcher(dm, clipwatcher_single.print_write_to_txtf,
                                                  os.path.join(ROOTDIR, "_linkcol"), 0.1)
    try:
        logger.info("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        logger.info("Stopped watching clipboard!")
        if watcher.found:
            logger.info("URLs were saved in: {}\n".format(watcher.txtname))
            yn = input("Do you want to download found URLs directly? (yes/no):\n")
            if yn == "yes":
                # dont return ref so watcher can die
                return watcher.found.copy()
            else:
                return


def parse_subreddit(subreddit, sort, limit, time_filter=None):
    """
    Return limit number of submissions in subreddit with sorting method provided with sort
    :param subreddit: Name of subreddit
    :param sort: Sorting method, only "hot" or "top"
    :param limit: Number of submissions to get (1000 max by reddit, 100 per request)
    :param time_filter: Time period to use, can be all, day, hour, month, week, year
    :return: praw.ListingGenerator
    """
    sub = reddit_praw.subreddit(subreddit)
    if sort == "hot":
        return sub.hot(limit=limit)
    elif sort == "top":
        return sub.top(time_filter=time_filter, limit=limit)
    else:
        logger.warning("Sort must be either 'hot' or 'top'!")
        main()


def search_subreddit(subname, searchstring, limit=100, sort="top", **kwargs):
    """
    Search subreddit(subname) with searchstring and return limit number of submission with
    sorting method = sort. Passes along kwargs to praw's search method.
    :param subname: Name of subreddit
    :param searchstring: Searchstring in lucene syntax, see https://www.reddit.com/wiki/search
    :param limit: Max number of submissions to get
    :param sort: Sorting method -> relevance, hot, top, new, comments
    :param kwargs: Kwargs to pass along to search method of praw
    :return: List containing found praw Submission obj
    """
    # sort: relevance, hot, top, new, comments (default: relevance).
    # syntax: cloudsearch, lucene, plain (default: lucene) in praw4 cloud
    # time_filter – Can be one of: all, day, hour, month, week, year (default: all)
    subreddit = reddit_praw.subreddit(subname)

    found_sub_list = []
    # Returns a generator for submissions that match the search query
    matching_sub_gen = subreddit.search(searchstring, sort=sort, limit=limit,
                                        syntax="lucene", **kwargs)
    # iterate over generator and append found submissions to list
    for sub in matching_sub_gen:
        found_sub_list.append(sub)
    return found_sub_list


# If you have a PRAW object, e.g., Comment, Message, Redditor, or Submission, and you want to see what
# attributes are available along with their values, use the built-in vars() function of python
# import pprint
#
# # assume you have a Reddit instance bound to variable `reddit`
# submission = reddit.submission(id='39zje0') # lazy object -> fewer attributes than expected
# print(submission.title) # to make it non-lazy
# pprint.pprint(vars(submission))
# PRAW uses lazy objects so that network requests to Reddit’s API are only issued when information is needed
# When we try to print its title, additional information is needed, thus a network request is made, and the
# instances ceases to be lazy. Outputting all the attributes of a lazy object will result in fewer attributes
# than expected.


# deactivted LASTDLTIME check by default
def parse_submissions_for_links(sublist, supported_hosts, time_check=False):
    """
    Searches .url and .selftext_html of submissions in sublist for supported urls, if its title
    doesnt contain banned tags

    Checks if submission title contains banned tags and if time_check check if submission time is
    newer than last_dl_time loaded from config or utc timestamp if supplied with time_check

    Check if url contains part of supported hoster urls -> add to found_urls as tuple (host, url)
    Search all <a> tags with set href in selftext_html and if main part of support host url is contained
    -> add to found_urls

    If no urls were found log it and append links to html file named like reddit_nurl_%Y-%m-%d_%Hh.html
    so the user is able to check the subs himself for links

    Create dict of reddit info and append AudioDownload/s init with found url, host, and reddit_info to
    dl_list and return it once all submissions have been searched
    :param sublist: List of submission obj
    :param time_check: True -> check if submission time is newer than last dl time from config, type float use
    this as lastdltime, False or None dont check submission time at all
    :return: List of AudioDownload instances
    """
    dl_list = []

    # Jon blow has talked about how SOME annotation reeaally helps programmer understanding, but too much is real bad.

    # all values stored as strings, configparser wont convert automatically so we do it with float(config[]..)
    # or use provided getfloat, getint method
    # provide fallback value if key isnt available
    # also works on parser-level if section (here: Time) isnt present:
    # float(config.get('Time', 'last_dl_time', fallback='0.0'))
    # configparser provides also a legacy API with explicit get/set methods. While there are valid use cases for the
    # methods outlined below, mapping protocol access is preferred for new projects
    # -> when we dont need fallback value use config["Time"]["last_dl_time"] etc.

    # time_check can be True, False, or a float, only load dltime if True -> use is True
    if time_check is True:
        # get new lastdltime from cfg
        reload_config()
        lastdltime = config.getfloat("Time", "last_dl_time", fallback=0.0)
    elif type(time_check) is float:
        lastdltime = time_check
    else:
        lastdltime = None

    for submission in sublist:

        # lastdltime gets evaluated first -> only calls func if lastdltime not None
        if lastdltime and not check_submission_time(submission, lastdltime):
            # submission is older than lastdltime -> next sub
            continue

        if not check_submission_banned_tags(submission, KEYWORDLIST, TAG1_BUT_NOT_TAG2):

            found_urls = []
            sub_url = submission.url

            for host, search_for in supported_hosts.items():
                if search_for in sub_url:
                    found_urls.append((host, sub_url))
                    logger.info("{} link found in URL of: {}".format(host, submission.title))
                    break

            # TODO /gwa remove in _set_eraudica.., update docstr

            # elif "eraudica.com/" in sub_url:
            #     # remove gwa so we can access dl link directly
            #     if sub_url.endswith("/gwa"):
            #         found_urls.append(("eraudica", sub_url[:-4]))
            #     else:
            #         found_urls.append(("eraudica", sub_url))
            #     logger.info("eraudica link found in URL of: " + submission.title)

            # only search selftext if we havent already found url in sub_url and selftext isnt None
            if not found_urls and (submission.selftext_html is not None):  # TODO refactor into sep func?
                soup = bs4.BeautifulSoup(submission.selftext_html, "html.parser")

                # selftext_html is not like the normal html it starts with <div class="md"..
                # so i can just go through all a
                # css selector -> tag a with set href attribute
                sgasmlinks = soup.select('a[href]')
                usrcheck = re.compile("/u/.+/.+", re.IGNORECASE)

                for link in sgasmlinks:
                    href = link["href"]
                    # make sure we dont get an user link
                    if ("soundgasm.net" in href) and usrcheck.search(href):
                        # appends href-attribute of tag object link
                        found_urls.append(("sgasm", href))
                        logger.info("SGASM link found in text, in submission: " + submission.title)
                    elif "chirb.it/" in href:
                        found_urls.append(("chirb.it", href))
                        logger.info("chirb.it link found in text, in submission: " + submission.title)
                    elif "eraudica.com/" in href:
                        # remove gwa so we can access dl link directly
                        if href.endswith("/gwa"):
                            found_urls.append(("eraudica", href[:-4]))
                        else:
                            found_urls.append(("eraudica", href))
                        logger.info("eraudica link found in text, in submission: " + submission.title)

            if not found_urls:
                logger.info("No supported link in \"{}\"".format(submission.shortlink))
                with open(os.path.join(ROOTDIR, "_linkcol", "reddit_nurl_" + time.strftime("%Y-%m-%d_%Hh.html")),
                          'a', encoding="UTF-8") as w:
                    w.write("<h3><a href=\"https://reddit.com{}\">{}"
                            "</a><br/>by {}</h3>\n".format(submission.permalink, submission.title, submission.author))
                # found_urls empty we can skip to next sub
                continue

            reddit_info = {"title": submission.title, "permalink": str(submission.permalink),
                           "selftext": submission.selftext, "r_user": submission.author.name,
                           "created_utc": submission.created_utc, "id": submission.id,
                           "subreddit": submission.subreddit.display_name, "r_post_url": sub_url}

            # create AudioDownload from found_urls
            for host, url in found_urls:
                dl_list.append(AudioDownload(url, host, reddit_info=reddit_info))

    return dl_list


def check_submission_banned_tags(submission, keywordlist, tag1_but_not_2=None):
    """
    Checks praw Submission obj for banned tags (case-insensitive) from keywordlist in title
    returns True if tag is contained. Also returns True if one of the first tags in the tag-combos
    in tag1_but_not_2 is contained but the second isnt.

    Example:    tag1:"[f4f" tag2:"4m]"
                title: "[F4F][F4M] For both male and female listeners.." -> return False
                title: "[F4F] For female listeners.." -> return True
    :param submission: praw Submission obj to scan for banned tags in title
    :param keywordlist: banned keywords/tags
    :param tag1_but_not_2: List of 2-tuples, first tag(str) is only banned if second isn't contained
    :return: True if submission is banned from downloading else False
    """
    # checks submissions title for banned words contained in keywordlist
    # returns True if it finds a match
    subtitle = submission.title.lower()

    for keyword in keywordlist:
        if keyword in subtitle:
            logger.info("Banned keyword '{}' in: {}\n\t slink: {}".format(keyword, subtitle, submission.shortlink))
            return True

    if tag1_but_not_2:
        for tag_b, tag_in in tag1_but_not_2:
            # tag_b is only banned if tag_in isnt found in subtitle
            if (tag_b in subtitle) and not (tag_in in subtitle):
                logger.info("Banned keyword: no '{}' in title where '{}' is in: {}\n\t "
                            "slink: {}".format(tag_in, tag_b, subtitle, submission.shortlink))
                return True
    return False


def write_last_dltime():
    """
    Sets last dl time in config, creating the "Time" section if it doesnt exist and then
    writes it to the config file
    :return: None
    """
    if config.has_section("Time"):
        config["Time"]["LAST_DL_TIME"] = str(time.time())
    else:
        # create section if it doesnt exist
        config["Time"] = {"LAST_DL_TIME": str(time.time())}
    write_config_module()


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


def export_csv_from_sql(filename, db_con):
    """
    Fetches and writes all rows (with all cols) in db_con's database to the file filename using
    writerows() from the csv module

    writer kwargs: dialect='excel', delimiter=";"
    :param filename: Filename or path to file
    :param db_con: Connection to sqlite db
    :return: None
    """
    # newline="" <- important otherwise weird behaviour with multiline cells (adding \r) etc.
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        # excel dialect -> which line terminator(\r\n), delimiter(,) to use, when to quote cells etc.
        csvwriter = csv.writer(csvfile, dialect="excel", delimiter=";")

        # get rows from db
        c = db_con.execute("SELECT * FROM Downloads")
        rows = c.fetchall()

        # write the all the rows to the file
        csvwriter.writerows(rows)


def backup_db(db_path, force_bu=False):
    bu_dir = os.path.join(ROOTDIR, "_db-autobu")
    if not os.path.exists(bu_dir):
        os.makedirs(bu_dir)
    # time.time() get utc number
    now = time.time()
    # freq in days convert to secs since utc time is in secs since epoch
    # get freq from config.ini use fallback value 3 days
    freq_secs = config.getfloat("Settings", "db_bu_freq", fallback=5.0) * 24 * 60 * 60
    elapsed_time = now - config.getfloat("Time", "last_db_bu", fallback=0.0)

    # if time since last db bu is greater than frequency in settings or we want to force a bu
    # time.time() is in gmt/utc whereas time.strftime() uses localtime
    if (elapsed_time > freq_secs) or force_bu:
        time_str = time.strftime("%Y-%m-%d")
        logger.info("Writing backup of database!")
        os.path.join(ROOTDIR, "_db-autobu", "{}_sgasm_rip_db.csv".format(time_str))

        # update last db bu time
        if config.has_section("Time"):
            config["Time"]["last_db_bu"] = str(now)
        else:
            config["Time"] = {"last_db_bu": str(now)}
        # write config to file
        write_config_module()

        # iterate over listdir, add file to list if isfile returns true
        bu_dir_list = [os.path.join(bu_dir, f) for f in os.listdir(bu_dir) if os.path.isfile(os.path.join(bu_dir, f))]
        # we could also use list(filter(os.path.isfile, bu_dir_list)) but then we need to have a list with PATHS
        # but we need the paths for os.path.getctime anyway
        # filter returns iterator!! that yields items which function is true -> only files
        # iterator -> have to iterate over it or pass it to function that does that -> list() creates a list from it
        # filter prob slower than list comprehension WHEN you call other function (def, lambda, os.path.isfile),
        # WHEREAS you would use a simple if x == "bla" in the list comprehension, here prob same speed

        # if there are more files than number of bu allowed (2 files per bu atm)
        if len(bu_dir_list) > (config.getint("Settings", "max_db_bu", fallback=5) * 2):
            # use creation time (getctime) for sorting, due to how name the files we could also sort alphabetically
            bu_dir_list = sorted(bu_dir_list, key=os.path.getctime)

            logger.info("Too many backups, deleting the oldest one!")
            # remove the oldest two files, keep deleting till nr of bu == max_db_bu? only relevant if user copied
            # files in there
            os.remove(bu_dir_list[0])
            os.remove(bu_dir_list[1])
    else:
        # time in sec that is needed to reach next backup
        next_bu = freq_secs - elapsed_time
        logger.info("Der letzte Sicherungszeitpunkt liegt nocht nicht {} Tage zurück! Die nächste Sicherung ist "
                    "in {: .2f} Tagen!".format(config.getfloat("Settings", "db_bu_freq",
                                                               fallback=5), next_bu / 24 / 60 / 60))


def check_submission_time(submission, lastdltime):
    """
    Check if utc timestamp of submission is greater (== older) than lastdltime
    :param submission: praw Submission obj
    :param lastdltime: utc timestamp (float)
    :return: True if submission is newer than lastdltime else False
    """
    if submission.created_utc > lastdltime:
        logger.info("Submission is newer than lastdltime")
        return True
    else:
        logger.info("Submission is older than lastdltime")
        return False


if __name__ == "__main__":
    main()
