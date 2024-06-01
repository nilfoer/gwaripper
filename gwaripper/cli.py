#! python3
import argparse
import os
import sys
import time
import logging

import praw
import certifi

from typing import List, Optional

from . import utils
from . import clipwatcher_single
from gwaripper import config
from .gwaripper import GWARipper
from .reddit import reddit_praw, parse_subreddit, search_subreddit
from .logging_setup import configure_logging


logger = logging.getLogger(__name__)

# only log to file if ROOTDIR is set up so we dont clutter the cwd or the module dir
root_dir: Optional[str]
try:
    root_dir = config.get_root()
except KeyError:
    root_dir = None
if root_dir and os.path.isdir(root_dir):
    configure_logging(os.path.join(root_dir, "gwaripper.log"))


def main():
    parser = argparse.ArgumentParser(
            description="Script to download audios from supported hosts or extract them from "
                        "reddit submissions the kind of which are found on subreddits like gonewildaudio",
            epilog="NOTE: arguments that are shared over all subcommands need to be put in front of the "
                 "subcommand itself: e.g. gwaripper --ignore-banned links URL URL ...")

    parser.add_argument('--ignore-banned', action='store_true',
                        help="Ignores banned tags in titles and in link text!")
    parser.add_argument('--download-duplicates', action='store_true',
                        help="Downloads files even if they're already in the "
                             "DB/have been downloaded before!")
    parser.add_argument('--skip-non-audio', action='store_true',
                        help="Only download audio files (e.g. this would mean skipping images found "
                             "in a reddit submission)")
    parser.add_argument('--dont-write-selftext', action='store_true',
                        help="Don't write selftext of reddit submissions to "
                             "disk! WARNING: They are not stored in the DB at the "
                             "moment, so the selftext will not be available - even in "
                             "the webGUI")

    # support sub-commands like svn checkout which require different kinds of
    # command-line arguments
    subparsers = parser.add_subparsers(
            title='subcommands', description='valid subcommands', help='sub-command help',
            dest="subcmd")  # save name of used subcmd in var

    #
    # SINGLE LINKS PARSE
    #
    # process single links by default # nargs="*" -> zero or more arguments
    # !! -> doesnt work since we need to specify a subcommand since they work
    # like positional arguements and providing a default subcommand isnt supported atm
    # create the parser for the "links" subcommand
    parser_lnk = subparsers.add_parser(
        'links',
        help='Download all links passed in as positional command line '
             'arguments. URLs to reddit submissions will be searched for supported '
             'audio hosts and then these will be downloaded informing you about '
             'known, but unsupported audio hosts. Links to other reddit submissions '
             'inside another reddit submission will not be processed, but you will '
             'also be informed about them in the report '
             '(found in {gwaripper root}/_reports after the download is done)')
    parser_lnk.add_argument(
        "links",
        help="Links to process (reddit submissions or supported audio hosts).",
        nargs="+", metavar='URL')
    # set funct to call when subcommand is used
    parser_lnk.set_defaults(func=_cl_link)

    # Required options are generally considered bad form because users expect
    # options to be optional, and thus they should be avoided when possible.

    #
    # PARSE LINKS FROM TXT FILE
    #
    parser_txt = subparsers.add_parser(
        'fromtxt',
        help='Specify a path to a text file where each line is a separate URL '
             'to a reddit submission or to a supported audio host. For more '
             'information see the helptext of links: `links -h`')
    parser_txt.add_argument(
        "filename",
        help="Path to the text file containing one reddit submission URL or one supported "
             "audio host URL per line")
    parser_txt.set_defaults(func=_cl_fromtxt)

    #
    # WATCH CLIPBOARD
    #
    parser_clip = subparsers.add_parser(
        'watch',
        help='Starts watching the system clipboard for copied text. If the text '
             'is matched by one of the supported extractors (e.g. reddit submissions '
             'or a soundgasm.net link) it is copied to memory and also appended to a '
             'text file in {gwaripper root}/_linkcol/{YYYY}-{MM}-{DD}_{HH}h.txt '
             'Pressing Ctrl+C will stop watching the clibpoard and will prompt you if '
             'all the URLs should be downloaded immediately.')
    parser_clip.set_defaults(func=_cl_watch)

    # add parser that is used as parent parser for all subcmd parsers so they can have common
    # options without adding arguments to each one
    parent_parser = argparse.ArgumentParser(add_help=False)
    # all subcmd parsers will have options added here (as long as they have this parser as
    # parent)
    parent_parser.add_argument("limit", type=int,
                               help="Maximum number of reddit submissions", metavar='POST_LIMIT')
    parent_parser.add_argument("-s", "--sort", choices=("hot", "top", "new"), default="top",
                               help="Reddit submission sorting method (default: top; choices: hot, top, new)",
                               metavar='SORTBY')
    parent_parser.add_argument(
        "-t", "--timefilter",
        help="Value for time filter (default: all; choices: all, day, hour, month, week, year)",
        default="all", choices=("all", "day", "hour", "month", "week", "year"),
        metavar='TIME_FRAME')

    #
    # RIP REDDITORS
    #
    parser_rusr = subparsers.add_parser(
        'redditor',
        help='Process a maximun of {POST_LIMIT} submissions of the specified redditor.',
        parents=[parent_parser])
    parser_rusr.add_argument("names", help="Reddit user name", nargs="+", metavar='USERNAME')
    parser_rusr.set_defaults(func=_cl_redditor)

    #
    # SUBREDDIT
    #
    # provide shorthands or alt names with aliases
    parser_sub = subparsers.add_parser(
        'subreddit', aliases=["sub"],
        parents=[parent_parser],
        help='Process {POST_LIMIT} of reddit submissions sorted by {SORTBY} from the specified subreddit')
    parser_sub.add_argument("sub", help="Name of subreddit", metavar='SUBREDDIT')
    # nargs=? One argument will be consumed from the command line if possible
    # no command-line argument -> default
    # optional arguments -> option string is present but not followed by a
    # command-line argument -> value from const
    # TODO add back
    # parser_sub.add_argument(
    #         "-on", "--only-newer", nargs="?", const=True, default=False, type=float,
    #         help="Only download submission if creation time is newer than provided utc"
    #              "timestamp or last_dl_time from config if none provided (default: None)")
    parser_sub.set_defaults(func=_cl_sub)

    #
    # REDDIT SEARCH
    #
    parser_se = subparsers.add_parser(
            'search', help='Search subreddit and process at most {POST_LIMIT} matching submissions',
            parents=[parent_parser])
    # parser normally uses name of dest=name (which u use to access value with args.name)
    # var for refering to argument -> --subreddit SUBREDDIT; can be different from option
    # string e.g. -user, dest="name" can be changed with metavar, when
    # nargs=n -> tuple with n elements
    parser_se.add_argument("subname", help="Name of subreddit to search", metavar='SUBREDDIT')
    parser_se.add_argument("sstr", help=("Searchstring in lucene syntax (see: "
                                         "https://www.reddit.com/wiki/search)"),
                           metavar="LUCENE_SEARCH_STRING")
    parser_se.set_defaults(func=_cl_search)

    parser_cfg = subparsers.add_parser("config",
        help="Configure GWARipper: save location etc.",
        epilog="Calling config without any argument will output all current settings!")
    parser_cfg.add_argument("-p", "--path", help="Set path to gwaripper's root directory, "
                                                 "where all the files will be downloaded to")
    parser_cfg.add_argument("-bf", "--backup-freq", metavar="FREQUENCY", type=float,
                            help="Set auto backup frequency of the DB in days")
    parser_cfg.add_argument("-bn", "--backup-nr", metavar="N-BACKUPS", type=int,
                            help="Set max. number of DB backups to keep")
    parser_cfg.add_argument("-tf", "--tagfilter",
                            help="Set banned strings/tags in reddit title", nargs="+",
                            metavar="TAG")
    parser_cfg.add_argument("-tco", "--tag-combo-filter",
                            help="Set banned tag when other isnt present: "
                                 "Tag1 is only banned when Tag2 isnt found, synatx"
                                 "is: Tag1;Tag2 Tag3;Tag4",
                            metavar="TAGCOMBO", nargs="+")
    parser_cfg.add_argument("-smr", "--set-missing-reddit", type=int, choices=(0, 1),
                            help="Should gwaripper get the info of soundgasm.net-files "
                                 "when coming from reddit even thouth they already have "
                                 "been downloaded, so missing reddit info can be filled in")
    parser_cfg.add_argument("-rci", "--reddit-client-id", metavar="client_id", type=str,
                            help="Set reddit client_id which is needed to use reddit functions")
    parser_cfg.add_argument("-rcs", "--reddit-client-secret", metavar="client_secret", type=str,
                            help="Set client_secret which is needed to use reddit "
                                 "functions if you registered for the app type 'script'. "
                                 "Use -rcs \"\" to remove client_secret")
    parser_cfg.add_argument("-ici", "--imgur-client-id", metavar="imgur_client_id", type=str,
                            help="Set client_id for imgur which is needed to download "
                                 "imgur images and albumus (but not direct imgur links)")
    parser_cfg.add_argument(
            "--only-one-mirror", metavar="ZERO_OR_ONE", type=str,
            help="Activate (1: on; 0: off) only downloading the audios from one of the mirrors."
                 "The mirror that's chosen depends on the host priority list, which can "
                 "be set with --host-priority. If there are no entries in the priority "
                 "list an arbitrary host will be picked!")
    parser_cfg.add_argument("--host-priority", action="store_true",
                            help="Set the host priority list that determines which hosts are chosen in "
                                 "what order when only_one_mirror is activated.")
    parser_cfg.set_defaults(func=_cl_config)

    parser.add_argument("-te", "--test", action="store_true", help=argparse.SUPPRESS)

    # check with: if not len(sys.argv) > 1
    # if no arguments were passed and call our old input main func; or use
    # argument with default value args.old
    if not len(sys.argv) > 1:
        print("No arguments passed! Call this script from the command line with "
              "-h to show available commands.")
        argv_str = input("Simulating command line input!!\n\nType in "
                         "command line args:\n").split()

        # simulate shell/cmd way of considering strings with spaces in
        # quotation marks as one single arg/string
        argv_clean = []
        # index of element in list with first quotation mark
        first_i = None
        # iterate over list, keeping track of index with enumerate
        for i, s in enumerate(argv_str):
            # found start of quote and were not currently looking for the end
            # of a quote (first_i not set)
            # ("\"" in s) or ("\'" in s) and not first_i needs to be in extra
            # parentheses  or it will be evaluated like:
            # True | (False & False) -> True, since only ("\'" in s) and not first_i get
            # connected with and (("\"" in s) or ("\'" in s)) and not first_i:
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
                # get slice of list from index of first quot mark to this index:
                # argv_str[first_i:i+1]
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
        # parse_args() will only contain attributes for the main parser and the
        # subparser that was selected
        args = parser.parse_args()

    if root_dir:
        setup_cacerts()

        # set selected ignore-banned option in config
        if args.ignore_banned:
            config.config['Settings']['check_banned_tags'] = 'False'

        if args.test:
            # test code
            pass
            # a = reddit_praw().submission(id="9dg1bk")
        else:
            # call func that was selected for subparser/command
            args.func(args)
    # rootdir istn set but we want to call _cl_config
    elif not root_dir and args.subcmd == "config":
        _cl_config(args)
    else:
        print("root_path not set in gwaripper_config.ini, use command config -p "
              "\"C:\\absolute\\path\" to specify where the files will be downloaded to")


def setup_cacerts() -> None:
    # depending on the packaged libcrypto on Unix systems the cacerts default
    # paths might differ
    # (see: https://github.com/pyinstaller/pyinstaller/issues/7229)
    # to get an actually portable solution we use certifi's bundled cacerts
    # (CAs approved by Mozilla)
    # since that is not what users may want and the bundled cacerts might
    # be outdated we added a config option for this, so a user can
    # set the environment variable `SSL_CERT_FILE` themselve
    from gwaripper import config
    if config.config["Settings"].getboolean("set_ssl_cert_file", True):
        cacerts_path = certifi.where()
        os.environ["SSL_CERT_FILE"] = cacerts_path


def download_all_links(urls: List[str], args: argparse.Namespace) -> None:
    with GWARipper(
            download_duplicates=args.download_duplicates,
            skip_non_audio=args.skip_non_audio,
            dont_write_selftext=args.dont_write_selftext,
            only_one_mirror=config.config.getboolean("Settings", "only_one_mirror", fallback=False),
            host_priority=config.get_host_priorities()) as gw:
        gw.set_urls(urls)
        gw.download_all()


def _cl_link(args: argparse.Namespace) -> None:
    download_all_links(args.links, args)


def _cl_fromtxt(args):
    try:
        url_list = utils.txt_to_list(args.filename)
    except OSError:
        logger.error("Couldn't open file %s", args.filename)
        return

    download_all_links(url_list, args)


def _cl_watch(args):
    found = watch_clip()
    download_all_links(found, args)


def download_all_subs(sublist: List[praw.models.Submission], args: argparse.Namespace) -> None:
    with GWARipper(
            download_duplicates=args.download_duplicates,
            skip_non_audio=args.skip_non_audio,
            dont_write_selftext=args.dont_write_selftext,
            only_one_mirror=config.config.getboolean("Settings", "only_one_mirror", fallback=False),
            host_priority=config.get_host_priorities()) as gw:
        gw.download_all(sublist)


def _cl_redditor(args):
    limit = args.limit
    time_filter = args.timefilter
    for usr in args.names:
        redditor = reddit_praw().redditor(usr)
        if args.sort == "hot":
            sublist = redditor.submissions.hot(limit=limit)
        elif args.sort == "top":
            sublist = redditor.submissions.top(limit=limit, time_filter=time_filter)
        else:  # just get new posts if input doesnt match hot or top
            sublist = redditor.submissions.new(limit=limit)
        # to get actual subs sinc praw uses lazy loading
        sublist = list(sublist)
        if not sublist:
            logger.info("No subs recieved from user %s with time_filter %s", usr, args.timefilter)
            return

        download_all_subs(sublist, args)


def _cl_sub(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter
    sublist = None
    if sort == "top":
        sublist = list(parse_subreddit(args.sub, sort, limit, time_filter=time_filter))
    else:
        # new and hot dont use time_filter
        sublist = list(parse_subreddit(args.sub, sort, limit))

    download_all_subs(sublist, args)


def _cl_search(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter

    found_subs = search_subreddit(args.subname, args.sstr, limit=limit, time_filter=time_filter,
                                  sort=sort)
    download_all_subs(found_subs, args)


def _cl_config(args) -> None:
    changed = False
    if args.path:
        # normalize path, remove double \ and convert / to \ on windows
        if args.path[0] == '~':
            # abspath does not expand ~ (and neither does realpath)
            path_in = os.path.abspath(os.path.expanduser(os.path.normpath(args.path)))
        else:
            path_in = os.path.abspath(os.path.normpath(args.path))
        os.makedirs(path_in, exist_ok=True)
        # i dont need to change cwd and ROOTDIR since script gets restarted anyway
        try:
            config.config["Settings"]["root_path"] = path_in
        except KeyError:
            # settings setciton not present
            config.config["Settings"] = {"root_path": path_in}
        changed = True
        print("New root dir is: {}".format(path_in))
    # not elif since theyre not mutually exclusive
    if args.backup_freq:
        try:
            config.config["Settings"]["db_bu_freq"] = str(args.backup_freq)
        except KeyError:
            # settings setciton not present
            config.config["Settings"] = {"db_bu_freq": str(args.backup_freq)}
        changed = True
        print("Auto backups are due every {} days now!".format(args.backup_freq))
    if args.backup_nr:
        try:
            config.config["Settings"]["max_db_bu"] = str(args.backup_nr)
        except KeyError:
            # settings setciton not present
            config.config["Settings"] = {"max_db_bu": str(args.backup_nr)}
        changed = True
        print("{} backups will be kept from now on".format(args.backup_nr))
    if args.tagfilter:
        # not needed: .strip(", ")
        tf_str = ", ".join(args.tagfilter)
        try:
            config.config["Settings"]["tag_filter"] = tf_str
        except KeyError:
            # settings setciton not present
            config.config["Settings"] = {"tag_filter": tf_str}
        changed = True
        print("Banned tags were set to: {}".format(tf_str))
    if args.tag_combo_filter:
        t12_str = ";, ".join(args.tag_combo_filter)
        try:
            config.config["Settings"]["tag1_in_but_not_tag2"] = t12_str
        except KeyError:
            # settings setciton not present
            config.config["Settings"] = {"tag1_in_but_not_tag2": t12_str}
        changed = True
        print("Banned tag combos were set to: {}".format(t12_str))
    if args.set_missing_reddit is not None:  # since 0 evaluates to False
        smr_bool = bool(args.set_missing_reddit)
        try:
            config.config["Settings"]["set_missing_reddit"] = str(smr_bool)
        except KeyError:
            # settings setciton not present
            config.config["Settings"] = {"set_missing_reddit": str(smr_bool)}
        changed = True
        print("Gwaripper will try to fill in missing reddit info: {}" .format(smr_bool))
    if args.reddit_client_id:
        try:
            config.config["Reddit"]["client_id"] = str(args.reddit_client_id)
        except KeyError:
            config.config["Reddit"] = {"client_id": str(args.reddit_client_id)}
        changed = True
        print("Successfully set Client ID")
    if args.reddit_client_secret is not None:
        if args.reddit_client_secret:
            try:
                config.config["Reddit"]["client_secret"] = str(args.reddit_client_secret)
            except KeyError:
                config.config["Reddit"] = {"client_secret": str(args.reddit_client_secret)}
        else:
            try:
                del config.config["Reddit"]["client_secret"]
            except KeyError:
                pass
        changed = True
        print("Successfully set Client Secret")
    if args.imgur_client_id:
        try:
            config.config["Imgur"]["client_id"] = str(args.imgur_client_id)
        except KeyError:
            config.config["Imgur"] = {"client_id": str(args.imgur_client_id)}
        changed = True
        print("Successfully set Imgur Client ID")
    if args.only_one_mirror:
        activated = "True" if args.only_one_mirror == "1" else "False"
        try:
            config.config["Settings"]["only_one_mirror"] = activated
        except KeyError:
            config.config["Settings"] = {"only_one_mirror": activated}
        changed = True
        print("Successfully set only_one_mirror to", activated)
    if args.host_priority:
        config.print_host_options()
        ans = input("Enter the order of hosts by using their __number__ separated by commas. "
                    "The order is highest priority to lowest:\n")
        config.set_host_priorities(ans)
        changed = True
        hosts = ",".join(x.name for x in config.get_host_priorities())
        print("Successfully set host_priority to", hosts)
    if not changed:
        # print current cfg
        for sec in config.config.sections():
            print("[{}]".format(sec))
            for option, val in config.config[sec].items():
                print("{} = {}".format(option, val))
            print("")
        return  # so we dont reach writing of cfg
    # write updated config
    config.write_config_module()


def write_last_dltime():
    """
    Sets last dl time in config, creating the "Time" section if it doesnt exist and then
    writes it to the config file

    :return: None
    """
    if config.config.has_section("Time"):
        config.config["Time"]["LAST_DL_TIME"] = str(time.time())
    else:
        # create section if it doesnt exist
        config.config["Time"] = {"LAST_DL_TIME": str(time.time())}
    config.write_config_module()


# mypy thinks we're not returning if there's not KeyboardInterrupt but that only
# happens if another exception is raised an we crash
def watch_clip() -> Optional[List[str]]:  # type: ignore[return]
    """
    Watches clipboard for links of domain

    Convert string to python code to be able to pass function to check if clipboard content is
    what we're looking for to ClipboardWatcher init

    :param domain: keyword that points to function is_domain_url in clipwatcher_single module
    :return: ClipboardWatcher instance or None
    """
    watcher = clipwatcher_single.ClipboardWatcher(clipwatcher_single.is_url,
                                                  clipwatcher_single.print_write_to_txtf,
                                                  os.path.join(config.get_root(), "_linkcol"), 0.1)
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
                return None
