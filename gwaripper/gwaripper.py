#! python3
import argparse
import logging
import os
import re
import sys
import time
import urllib.request

import bs4

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
from .logging_setup import configure_logging
from . import clipwatcher_single
from . import utils
from .config import config, write_config_module, ROOTDIR
from .audio_dl import AudioDownload
from .db import load_or_create_sql_db, export_csv_from_sql, backup_db
from .reddit import reddit_praw, parse_submissions_for_links, get_sub_from_reddit_urls, \
        parse_subreddit, search_subreddit
from .imgur import ImgurFile, ImgurAlbum, ImgurImage        

rqd = utils.RequestDelayer(0.25, 0.75)

# configure logging
# logfn = time.strftime("%Y-%m-%d.log")
# __name__ = 'gwaripper.gwaripper' -> logging of e.g. 'gwaripper.utils' (when callin getLogger with __name__
# in utils module) wont be considered a child of this logger
# we could use logging.config.fileConfig to configure our loggers (call it in main() for example, but with
# 'disable_existing_loggers': False, otherwise all loggers created by getLogger at module-level will be disabled)
# or we could configure our logging in __init__.py of our package (top-most level) with __name__ since that is
# just 'gwaripper' or we can configure our logger for the package by calling getLogger with 'gwaripper'
logger = logging.getLogger("gwaripper")
logger.setLevel(logging.DEBUG)

# only log to file if ROOTDIR is set up so we dont clutter the cwd or the module dir
if ROOTDIR and os.path.isdir(ROOTDIR):
    configure_logging(os.path.join(ROOTDIR, "gwaripper.log"))

SUPPORTED_HOSTS = {  # host type keyword: string/regex pattern to search for
                "sgasm": re.compile("soundgasm.net/(?:u|user)/.+/.+", re.IGNORECASE),
                # doesnt rly host files anymore "chirb.it": "chirb.it/",
                "eraudica": "eraudica.com/",
                "imgur file": ImgurFile.IMAGE_FILE_URL_RE,
                "imgur image": ImgurImage.IMAGE_URL_RE,
                "imgur album": ImgurAlbum.ALBUM_URL_RE
            }


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception: ", exc_info=(exc_type, exc_value, exc_traceback))

    if exc_traceback is not None:
        # printing locals by frame from: Python Cookbook p. 343/343 von Alex Martelli,Anna Ravenscroft,David Ascher
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
        # when we've reached the first frame of that file (could use part of __name__ (here: gwaripper.gwaripper))

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
            llist = get_sub_from_reddit_urls(["https://old.reddit.com/r/gonewildaudio/comments/8wqzen/f4m_overwatch_joip_come_for_her_stroke_that_cock/"])
            a = reddit_praw().submission(id="9dg1bk")
            adl_list = parse_submissions_for_links(llist, SUPPORTED_HOSTS)
            rip_audio_dls(adl_list)
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
        adl_list = parse_submissions_for_links(llist, SUPPORTED_HOSTS)
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
        adl_list = parse_submissions_for_links(sublist, SUPPORTED_HOSTS)
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
        adl_list = parse_submissions_for_links(llist, SUPPORTED_HOSTS)
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
            adl_list = parse_submissions_for_links(llist, SUPPORTED_HOSTS)
            rip_audio_dls(adl_list)


def _cl_sub(args):
    sort = args.sort
    limit = args.limit
    time_filter = args.timefilter
    if sort == "top":
        adl_list = parse_submissions_for_links(parse_subreddit(args.sub, sort, limit, time_filter=time_filter),
                                               SUPPORTED_HOSTS, time_check=args.only_newer)
    else:
        # new and hot dont use time_filter
        adl_list = parse_submissions_for_links(parse_subreddit(args.sub, sort, limit), SUPPORTED_HOSTS,
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
    adl_list = parse_submissions_for_links(found_subs, SUPPORTED_HOSTS)
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

    # also possible to use .execute() methods on connection, which then create a cursor object and calls the
    # corresponding mehtod with given params and returns the cursor
    conn, c = load_or_create_sql_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))

    # create dict that has page urls as keys and AudioDownload instances as values
    # dict comrehension: d = {key: value for (key, value) in iterable}
    # duplicate keys -> last key value pair is in dict, values of the same key that came before arent
    # @Hack removing /gwa appendix since we only add the url without /gwa to the db
    # so we might have duplicate downloads otherwise
    dl_dict = {audio.page_url[:-4] if audio.page_url.endswith("/gwa") else audio.page_url:
               audio for audio in dl_list}

    # returns list of new downloads, dl_dict still holds all of them
    new_dls = filter_alrdy_downloaded(dl_dict, conn)

    filestodl = len(new_dls)
    dlcounter = 0

    for url in new_dls:
        audio_dl = dl_dict[url]

        rqd.delay_request()
        try:
            audio_dl.call_host_get_file_info()
        except urllib.request.HTTPError:
            # page with file info doesnt exist
            # nothing was added to db yet so we can just skip ahead
            filestodl -= 1
            continue

        # sleep between requests so we dont stress the server too much or get banned
        # using helper class -> only sleep .25s when last request time was less than .5s ago
        rqd.delay_request()
        dlcounter = audio_dl.download(conn, dlcounter, filestodl, ROOTDIR)

    # export db to csv -> human readable without tools
    export_csv_from_sql(os.path.join(ROOTDIR, "gwarip_db_exp.csv"), conn)
    conn.close()

    # auto backup
    backup_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))


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


def filter_alrdy_downloaded(dl_dict, db_con):
    """
    Filters out already downloaded urls and returns a set of new urls
    Logs duplicate downloads

    :param dl_dict: dict with urls as keys and the corresponding AudioDownload obj as values
    :param db_con: connection to sqlite3 db
    :return: set of new urls
    """
    c = db_con.execute("SELECT url FROM Downloads WHERE url IN "
                       f"({', '.join(['?']*len(dl_dict.keys()))})",
                       (*dl_dict.keys(),))
    duplicate = {r[0] for r in c.fetchall()}

    if config.getboolean("Settings", "set_missing_reddit"):
        for dup in duplicate:
            # when we got reddit info get sgasm info even if this file was already downloaded b4
            # then write missing info to df and write selftext to file
            if dl_dict[dup].reddit_info and ("soundgasm.net/" in dup):
                logger.info("Filling in missing reddit info: You can disable this "
                            "in the settings")
                adl = dl_dict[dup]
                # get filename from db to write selftext
                adl.filename_local = adl.set_missing_reddit_db(db_con)
                # TODO due to my db having been used with older versions there are a lot of
                # rows where cols local_filename and url are empty -> gen a filename so we can
                # write the selftext
                if adl.filename_local is None:  # TORELEASE remove
                    adl.filename_local = re.sub(r"[^\w\-_.,\[\] ]", "_", adl.title[0:110]) + ".m4a"  # TORELEASE remove
                adl.write_selftext_file(ROOTDIR)
    if duplicate:
        logger.info("{} files were already downloaded!".format(len(duplicate)))
        logger.debug("Already downloaded urls:\n{}".format("\n".join(duplicate)))

    # set.symmetric_difference()
    # Return a new set with elements in either the set or other but not both.
    # -> duplicates will get removed from unique_urls
    result = duplicate.symmetric_difference(dl_dict.keys())

    return result


def watch_clip(site_name):
    """
    Watches clipboard for links of domain

    Convert string to python code to be able to pass function to check if clipboard content is
    what we're looking for to ClipboardWatcher init

    :param domain: keyword that points to function is_domain_url in clipwatcher_single module
    :return: List of found links, None if there None
    """
    try:
        dm = clipwatcher_single.site_keyword_func[site_name]
    except KeyError:
        logger.error("Invalid site_name %s", site_name)

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


if __name__ == "__main__":
    main()
