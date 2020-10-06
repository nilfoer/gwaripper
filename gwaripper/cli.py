#! python3
import argparse
import os
import sys
import time
import logging

from . import utils
from .config import config, write_config_module, ROOTDIR
from .gwaripper import (
        gen_audiodl_from_sglink, rip_audio_dls, rip_usr_to_files,
        watch_clip
        )
from .reddit import reddit_praw, get_sub_from_reddit_urls, \
        parse_subreddit, search_subreddit


logger = logging.getLogger(__name__)


# stub TODO
def parse_submissions_for_links(*args, **kwargs):
    pass


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
    parser_lnk.set_defaults(func=_cl_link)

    parser_sgusr = subparsers.add_parser('sguser', help='Rip sgasm user/s')
    # nargs="+" -> one or more arguments
    parser_sgusr.add_argument("names", help="Names of users to rip.", nargs="+")
    parser_sgusr.set_defaults(func=_cl_rip_users)
    # Required options are generally considered bad form because users expect options to be optional,
    # and thus they should be avoided when possible.

    parser_rusr = subparsers.add_parser('redditor', help='Rip redditor/s')
    parser_rusr.add_argument("limit", type=int, help="How many posts to download when ripping redditor")
    parser_rusr.add_argument("names", help="Names of users to rip.", nargs="+")
    # choices -> available options -> error if not contained; default -> default value if not supplied
    parser_rusr.add_argument("-s", "--sort", choices=("hot", "top", "new"), default="top",
                             help="Reddit post sorting method (default: top)")
    parser_rusr.add_argument("-t", "--timefilter", help="Value for time filter (default: all)", default="all",
                             choices=("all", "day", "hour", "month", "week", "year"))
    parser_rusr.set_defaults(func=_cl_redditor)
    # we could set a function to call with these args parser_foo.set_defaults(func=foo)
    # call with args.func(args) -> let argparse handle which func to call instead of long if..elif
    # However, if it is necessary to check the name of the subparser that was invoked, the dest keyword argument
    # to the add_subparsers(): parser.add_subparsers(dest='subparser_name')
    # Namespace(subparser_name='ripuser', ...)

    parser_txt = subparsers.add_parser('fromtxt', help='Process links in txt file')
    parser_txt.add_argument("type", help="Reddit(r) or sgasm(sg) link/s in txt", choices=("r", "sg"))
    parser_txt.add_argument("filename", help="Filename of txt file")
    parser_txt.set_defaults(func=_cl_fromtxt)

    parser_clip = subparsers.add_parser('watch', help='Watch clipboard for sgasm/reddit links and save them to txt;'
                                                      ' option to process them immediately')
    parser_clip.add_argument("type", help="Type of links to watch for: sgasm(sg) or reddit(r)", choices=("sg", "r"))
    parser_clip.set_defaults(func=_cl_watch)

    # provide shorthands or alt names with aliases
    parser_sub = subparsers.add_parser('subreddit', aliases=["sub"],
                                       help='Parse subreddit and download supported links')

    parser_sub.add_argument("sub", help="Name of subreddit")
    parser_sub.add_argument("limit", type=int, help="How many posts to download")
    parser_sub.add_argument("-s", "--sort", choices=("hot", "top"), help="Reddit post sorting method (default: top)",
                            default="top")
    parser_sub.add_argument("-t", "--timefilter", help="Value for time filter (default: all)", default="all",
                            choices=("all", "day", "hour", "month", "week", "year"))
    # nargs=? One argument will be consumed from the command line if possible
    # no command-line argument -> default
    # optional arguments -> option string is present but not followed by a command-line argument -> value from const
    parser_sub.add_argument("-on", "--only-newer", nargs="?", const=True, default=False, type=float,
                            help="Only download submission if creation time is newer than provided utc"
                                 "timestamp or last_dl_time from config if none provided (default: None)")
    parser_sub.set_defaults(func=_cl_sub)

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
    parser_se.add_argument("sstr", help=("Searchstring in lucene syntax (see: "
                                         "https://www.reddit.com/wiki/search)"),
                           metavar="searchstring")
    parser_se.add_argument("limit", type=int, help="How many posts to download")
    parser_se.add_argument("-s", "--sort", choices=("relevance", "hot", "top", "new", "comments"),
                           help="Reddit post sorting method (default: relevance)", default="relevance")
    parser_se.add_argument("-t", "--timefilter", help="Value for time filter (default: all)", default="all",
                           choices=("all", "day", "hour", "month", "week", "year"))
    parser_se.set_defaults(func=_cl_search)

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
                                                               "is: Tag1;Tag2 Tag3;Tag4",
                            metavar="TAGCOMBO", nargs="+")
    parser_cfg.add_argument("-smr", "--set-missing-reddit", type=int, choices=(0, 1),
                            help="Should gwaripper get the info of soundgasm.net-files when coming from reddit even "
                                 "thouth they already have been downloaded, so missing info can be fille into the DB")
    parser_cfg.add_argument("-ci", "--client-id", metavar="client_id", type=str,
                            help="Set client_id which is needed to use reddit functions")                                 
    parser_cfg.add_argument("-cs", "--client-secret", metavar="client_secret", type=str,
                            help=("Set client_secret which is needed to use reddit functions if you"
                                  " registered for the app type 'script'. Use -cs \"\" to remove "
                                  "client_secret"))  
    parser_cfg.add_argument("-ici", "--imgur-client-id", metavar="imgur_client_id", type=str,
                            help=("Set client_id for imgur which is needed to download imgur "
                                  "images and albumus (but not direct imgur links)"))                                                                                            
    parser_cfg.set_defaults(func=_cl_config)

    # TOCONSIDER implement verbosity with: stdohandler.setLevel(logging.INFO)?
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
            pass
            # llist = get_sub_from_reddit_urls(["https://old.reddit.com/r/gonewildaudio/comments/8wqzen/f4m_overwatch_joip_come_for_her_stroke_that_cock/"])
            # a = reddit_praw().submission(id="9dg1bk")
            # adl_list = parse_submissions_for_links(llist, SUPPORTED_HOSTS)
            # rip_audio_dls(adl_list)
        else:
            # call func that was selected for subparser/command
            args.func(args)
    # rootdir istn set but we want to call _cl_config
    elif not ROOTDIR and args.subcmd == "config":
        _cl_config(args)
    else:
        print("root_path not set in gwaripper_config.ini, use command config -p 'C:\\absolute\\path'"
              " to specify where the files will be downloaded to")


def _cl_link(args):
    if args.type == "sg":
        llist = gen_audiodl_from_sglink(args.links)
        rip_audio_dls(llist)
    else:
        llist = get_sub_from_reddit_urls(args.links)
        adl_list = parse_submissions_for_links(llist, {})
        rip_audio_dls(adl_list)


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
        adl_list = parse_submissions_for_links(sublist, {})
        if adl_list:
            rip_audio_dls(adl_list)
        else:
            logger.info("No audios found for user %s with time_filter %s", usr, args.timefilter)


def _cl_rip_users(args):
    for usr in args.names:
        rip_usr_to_files(usr)


def _cl_fromtxt(args):
    if not os.path.isfile(args.filename):
        logger.error("Couldn't find file %s", args.filename)
        return

    if args.type == "sg":
        rip_audio_dls(gen_audiodl_from_sglink(utils.txt_to_list(args.filename)))
    else:
        llist = get_sub_from_reddit_urls(utils.txt_to_list(args.filename))
        adl_list = parse_submissions_for_links(llist, {})
        rip_audio_dls(adl_list)


def _cl_watch(args):
    if args.type == "sg":
        found = watch_clip("sgasm")
        if found:
            llist = gen_audiodl_from_sglink(found)
            rip_audio_dls(llist)
    else:
        found = watch_clip("reddit")
        if found:
            llist = get_sub_from_reddit_urls(found)
            adl_list = parse_submissions_for_links(llist, {})
            rip_audio_dls(adl_list)


def _cl_sub(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter
    if sort == "top":
        adl_list = parse_submissions_for_links(parse_subreddit(args.sub, sort, limit, time_filter=time_filter),
                                               {}, time_check=args.only_newer)
    else:
        # new and hot dont use time_filter
        adl_list = parse_submissions_for_links(parse_subreddit(args.sub, sort, limit), {},
                                               time_check=args.only_newer)
    if args.only_newer:
        write_last_dltime()
    rip_audio_dls(adl_list)


def _cl_search(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter

    found_subs = search_subreddit(args.subname, args.sstr, limit=limit, time_filter=time_filter,
                                  sort=sort)
    adl_list = parse_submissions_for_links(found_subs, {})
    if adl_list:
        rip_audio_dls(adl_list)
    else:
        logger.warning("No matching subs/links found in {}, with: '{}'".format(args.subname, args.sstr))


def _cl_config(args):
    changed = False
    if args.path:
        # normalize path, remove double \ and convert / to \ on windows
        path_in = os.path.normpath(args.path)
        os.makedirs(path_in, exist_ok=True)
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
        # not needed: .strip(", ")
        tf_str = ", ".join(args.tagfilter)
        try:
            config["Settings"]["tag_filter"] = tf_str
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"tag_filter": tf_str}
        changed = True
        print("Banned tags were set to: {}".format(tf_str))
    if args.tag_combo_filter:
        t12_str = ";, ".join(args.tag_combo_filter)
        try:
            config["Settings"]["tag1_in_but_not_tag2"] = t12_str
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"tag1_in_but_not_tag2": t12_str}
        changed = True
        print("Banned tag combos were set to: {}".format(t12_str))
    if args.set_missing_reddit is not None:  # since 0 evaluates to False
        smr_bool = bool(args.set_missing_reddit)
        try:
            config["Settings"]["set_missing_reddit"] = str(smr_bool)
        except KeyError:
            # settings setciton not present
            config["Settings"] = {"set_missing_reddit": str(smr_bool)}
        changed = True
        print("Gwaripper will try to fill in missing reddit info of "
              "soundgasm.net files: {}".format(smr_bool))
    if args.client_id:
        try:
            config["Reddit"]["client_id"] = str(args.client_id)
        except KeyError:
            config["Reddit"] = {"client_id": str(args.client_id)}
        changed = True
        print("Successfully set Client ID")
    if args.client_secret is not None:
        if args.client_secret:
            try:
                config["Reddit"]["client_secret"] = str(args.client_secret)
            except KeyError:
                config["Reddit"] = {"client_secret": str(args.client_secret)}
        else:
            try:
                del config["Reddit"]["client_secret"]
            except KeyError:
                pass
        changed = True
        print("Successfully set Client Secret")    
    if args.imgur_client_id:
        try:
            config["Imgur"]["client_id"] = str(args.imgur_client_id)
        except KeyError:
            config["Imgur"] = {"client_id": str(args.imgur_client_id)}
        changed = True
        print("Successfully set Imgur Client ID")          
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
