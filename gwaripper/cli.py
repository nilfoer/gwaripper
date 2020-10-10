#! python3
import argparse
import os
import sys
import time
import logging

import praw

from typing import List

from . import utils
from . import clipwatcher_single
# :GlobalConfigImport
# reason why setting from .. import ROOTDIR; ROOTDIR = 'foo' doesn't work
# but config.ROOTDIR = 'foo' does
# The below only applies to immutable objects!!!
# https://stackoverflow.com/a/3536638 aaronasterling
# You are using from bar import a. a becomes a symbol in the global scope of
# the importing module (or whatever scope the import statement occurs in).
#
# When you assign a new value to a, you are just changing which value a points
# too, not the actual value. Try to import bar.py directly with import bar
# and conduct your experiment there by setting bar.a = 1. This way,
# you will actually be modifying bar.__dict__['a'] which is the 'real' value of
# a in this context.
# This is one of the dangers of using the from foo import bar form of the
# import statement: it splits bar into two symbols, one visible globally from
# within foo which starts off pointing to the original value and a different
# symbol visible in the scope where the import statement is executed. Changing
# a where a symbol points doesn't change the value that it pointed too.
#
# This sort of stuff is a killer when trying to reload a module from the interactive interpreter.
#
# NOTE: IMPORTANT not only modules that want to assign to config.ROOTDIR need
# to import it as import config but also _other_ modules that need to
# be able to see the updated value/reference
# -- foo.py
# conifg = 'bar'
# -- baz.py
# import foo
# foo.config = 'foobar'
# -- qux.py
# from foo import config
# print(config) -> 'bar'
# import foo
# print(foo.config) -> 'foobar'
#
# other modules can see the changes using the from .. import .. method
# if the imported type is mutable and you don't use assignment to change
# it -> foo: list = [] -> foo = ['new list'] doesn't work but
# foo.appned('same list') does (as in another module will see ['same list']
# no matter how it was imported)
#
# import foo:
# Imports foo, and creates a reference to that module in the current namespace.
# from foo import bar:
# Imports foo, and creates references to all the members listed (bar). Does not
# set the variable foo.
# => that's why assigning a new value doesn't work since the reference is
# to the old bar (using the 2nd method)
#
# Summary:
# Due to the way references and name binding works in Python, if you want to
# update some symbol in a module, say foo.bar, from outside that module, and
# have other importing code "see" that change, you have to import foo a using
# import foo and mustn't use from foo import bar
# The modules that want to "see" the change need to import it the _SAME_ way!

# TODO: maybe only use config.ROOTDIR to initialize GWARipper root_dir
# instance var so we don't break consistency of where we're writing if
# someone uses us as a library (s1 else might also be using
# us and modifying config.ROOTDIR; only using it when someone uses the cli
# makes it possible to have multiple GWARipper instances that don't write
# to the same place etc.; i know this is prob never going to be an issue...)
from . import config
from .gwaripper import GWARipper
from .reddit import reddit_praw, parse_subreddit, search_subreddit


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
            description="Script to download gonewildaudio/pta posts from either reddit "
                        "or soundgasm.net directly.")
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
    parser_lnk = subparsers.add_parser('links', help='Process single link/s')
    parser_lnk.add_argument("links", help="Links to process.", nargs="+", metavar='URL')
    # set funct to call when subcommand is used
    parser_lnk.set_defaults(func=_cl_link)

    # Required options are generally considered bad form because users expect
    # options to be optional, and thus they should be avoided when possible.

    #
    # PARSE LINKS FROM TXT FILE
    #
    parser_txt = subparsers.add_parser('fromtxt', help='Process links in txt file')
    parser_txt.add_argument("filename", help="Filename of txt file")
    parser_txt.set_defaults(func=_cl_fromtxt)

    #
    # WATCH CLIPBOARD
    #
    parser_clip = subparsers.add_parser(
            'watch', help='Watch clipboard for sgasm/reddit links and save them to txt;'
                          ' option to process them immediately')
    parser_clip.set_defaults(func=_cl_watch)

    # add parser that is used as parent parser for all subcmd parsers so they can have common
    # options without adding arguments to each one
    parent_parser = argparse.ArgumentParser(add_help=False)
    # all subcmd parsers will have options added here (as long as they have this parser as
    # parent)
    parent_parser.add_argument("limit", type=int, help="How many posts to download"
                               "when ripping redditor", metavar='POST_LIMIT')
    parent_parser.add_argument("-s", "--sort", choices=("hot", "top", "new"), default="top",
                               help="Reddit post sorting method (default: top)",
                               metavar='SORTBY')
    parent_parser.add_argument("-t", "--timefilter",
                               help="Value for time filter (default: all)", default="all",
                               choices=("all", "day", "hour", "month", "week", "year"),
                               metavar='TIME_FRAME')

    #
    # RIP REDDITORS
    #
    parser_rusr = subparsers.add_parser('redditor', help='Rip redditor/s',
                                        parents=[parent_parser])
    parser_rusr.add_argument("names", help="Names of users to rip.", nargs="+")
    parser_rusr.set_defaults(func=_cl_redditor)

    #
    # SUBREDDIT
    #
    # provide shorthands or alt names with aliases
    parser_sub = subparsers.add_parser('subreddit', aliases=["sub"],
                                       parents=[parent_parser],
                                       help='Parse subreddit and download supported links')
    parser_sub.add_argument("sub", help="Name of subreddit")
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
            'search', help='Search subreddit and download supported links',
            parents=[parent_parser])
    # parser normally uses name of dest=name (which u use to access value with args.name)
    # var for refering to argument -> --subreddit SUBREDDIT; can be different from option
    # string e.g. -user, dest="name" can be changed with metavar, when
    # nargs=n -> tuple with n elements
    parser_se.add_argument("subname", help="Name of subreddit")
    parser_se.add_argument("sstr", help=("Searchstring in lucene syntax (see: "
                                         "https://www.reddit.com/wiki/search)"),
                           metavar="searchstring")
    parser_se.set_defaults(func=_cl_search)

    parser_cfg = subparsers.add_parser("config", help="Configure GWARipper: save location etc.")
    parser_cfg.add_argument("-p", "--path", help="Set path to root directory, "
                                                 "where all the files will be downloaded to")
    parser_cfg.add_argument("-bf", "--backup-freq", metavar="FREQUENCY", type=float,
                            help="Set auto backup frequency in days")
    parser_cfg.add_argument("-bn", "--backup-nr", metavar="N-BACKUPS", type=int,
                            help="Set max. number of backups to keep")
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
                                 "been downloaded, so missing info can be fille into the DB")
    parser_cfg.add_argument("-rci", "--reddit-client-id", metavar="client_id", type=str,
                            help="Set reddit client_id which is needed to use reddit functions")
    parser_cfg.add_argument("-rcs", "--reddit-client-secret", metavar="client_secret", type=str,
                            help="Set client_secret which is needed to use reddit "
                                 "functions if you registered for the app type 'script'. "
                                 "Use -rcs \"\" to remove client_secret")
    parser_cfg.add_argument("-ici", "--imgur-client-id", metavar="imgur_client_id", type=str,
                            help="Set client_id for imgur which is needed to download "
                                 "imgur images and albumus (but not direct imgur links)")
    parser_cfg.set_defaults(func=_cl_config)

    parser.add_argument("-te", "--test", action="store_true")

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

    if config.ROOTDIR:
        if args.test:
            # test code
            pass
            # a = reddit_praw().submission(id="9dg1bk")
        else:
            # call func that was selected for subparser/command
            args.func(args)
    # rootdir istn set but we want to call _cl_config
    elif not config.ROOTDIR and args.subcmd == "config":
        _cl_config(args)
    else:
        print("root_path not set in gwaripper_config.ini, use command config -p "
              "'C:\\absolute\\path' to specify where the files will be downloaded to")


def download_all_links(urls: List[str]) -> None:
    with GWARipper() as gw:
        gw.parse_links(urls)
        gw.mark_alrdy_downloaded()
        gw.download_all()


def _cl_link(args):
    download_all_links(args.links)


def _cl_fromtxt(args):
    try:
        url_list = utils.txt_to_list(args.filename)
    except OSError:
        logger.error("Couldn't open file %s", args.filename)
        return

    download_all_links(url_list)


def _cl_watch(args):
    found = watch_clip()
    download_all_links(found)


def download_all_subs(sublist: List[praw.models.Submission]) -> None:
    with GWARipper() as gw:
        gw.parse_submissions(sublist)
        gw.mark_alrdy_downloaded()
        gw.download_all()


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

        download_all_subs(sublist)


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

    download_all_subs(sublist)


def _cl_search(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter

    found_subs = search_subreddit(args.subname, args.sstr, limit=limit, time_filter=time_filter,
                                  sort=sort)
    download_all_subs(found_subs)


def _cl_config(args):
    changed = False
    if args.path:
        # normalize path, remove double \ and convert / to \ on windows
        path_in = os.path.normpath(args.path)
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
        print("Gwaripper will try to fill in missing reddit info of "
              "soundgasm.net files: {}".format(smr_bool))
    if args.reddit_client_id:
        try:
            config.config["Reddit"]["client_id"] = str(args.client_id)
        except KeyError:
            config.config["Reddit"] = {"client_id": str(args.client_id)}
        changed = True
        print("Successfully set Client ID")
    if args.reddit_client_secret is not None:
        if args.client_secret:
            try:
                config.config["Reddit"]["client_secret"] = str(args.client_secret)
            except KeyError:
                config.config["Reddit"] = {"client_secret": str(args.client_secret)}
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


def watch_clip() -> List[str]:
    """
    Watches clipboard for links of domain

    Convert string to python code to be able to pass function to check if clipboard content is
    what we're looking for to ClipboardWatcher init

    :param domain: keyword that points to function is_domain_url in clipwatcher_single module
    :return: List of found links, None if there None
    """
    watcher = clipwatcher_single.ClipboardWatcher(clipwatcher_single.is_url,
                                                  clipwatcher_single.print_write_to_txtf,
                                                  os.path.join(config.ROOTDIR, "_linkcol"), 0.1)
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
