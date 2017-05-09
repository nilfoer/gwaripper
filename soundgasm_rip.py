#! python3
import urllib.request
import re
import os
import time
import clipwatcher_single
import praw
import bs4
import logging
import logging.handlers
import sys
import configparser
import pandas as pd
import timeit

# init ConfigParser instance
config = configparser.ConfigParser()
# read config file, ConfigParser pretty much behaves like a dict, sections in in ["Reddit"] is a key that holds
# another dict with keys(USER_AGENT etc.) and values -> nested dict -> access with config["Reddit"]["USER_AGENT"]
# !! keys in sections are case-insensitive and stored in lowercase
config.read("config.ini")

# init Reddit instance
reddit_praw = praw.Reddit(client_id=config["Reddit"]["CLIENT_ID"],
                          client_secret=config["Reddit"]["CLIENT_SECRET"],
                          user_agent=config["Reddit"]["USER_AGENT"])

# banned TAGS that will exclude the file from being downloaded (when using reddit)
# removed: "[daddy]", 
KEYWORDLIST = ["[m4", "[m]", "[request]", "[script offer]", "[cbt]",
               "[ce]", "[cei]", "[cuck]", "[f4f]"]
# path to dir where the soundfiles will be stored in subfolders
ROOTDIR = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
# old os.path.join("N:", os.sep, "_archive", "test", "soundgasmNET")
# old (os.sep, "home", "m", "Dokumente", "test-sg")

DLTXT_ENTRY_END = "\t" + ("___" * 30) + "\n\n\n"

# configure logging
# logfn = time.strftime("%Y-%m-%d.log")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# create a file handler
handler = logging.handlers.TimedRotatingFileHandler("gwaripper.log", "D", encoding="UTF-8", backupCount=10)
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

# load dataframe
df = pd.read_csv("../test.csv", sep=";", encoding="utf-8", index_col=0)
# @Temporary
df["redditTitle"] = None
grped_df = df.groupby("sgasm_user")
# TODO write afer finish and reload when starting main again


def main():
    opt = input("Was moechten Sie tun?\n\n 1. Rip/Update Users\n 2. Rip from single links\n "
                "3. Rip single links from a txt file\n 4. Watch clipboard for sgasm links\n "
                "5. Watch clipboard for reddit links\n 6. Download sgasm posts from subreddit\n "
                "7. Rip single reddit links from a txt file\n 8. Subreddit durchsuchen und Ergebnisse "
                "herunterladen\n 9. Test\n")
    if opt == "1":
        usrurls = input("Enter soundgasm User URLs separated by \",\" - no spaces\n")
        rip_users(usrurls)
        main()
    elif opt == "2":
        adl_list = input("Enter soundgasm post URLs separated by \",\" - no spaces\n")
        llist = gen_audiodl_from_sglink(adl_list.split(","))
        rip_audio_dls(llist)
        main()
    elif opt == "3":
        txtfn = input("Enter filename of txt file containing post URLs separated by newlines\n")
        mypath = os.path.join(ROOTDIR, "_linkcol")

        rip_audio_dls(gen_audiodl_from_sglink(txt_to_list(mypath, txtfn)))
        main()
    elif opt == "4":
        watch_clip("sgasm")
        main()
    elif opt == "5":
        watch_clip("reddit")
        main()
    elif opt == "6":
        subr = input("Enter subreddit name: \n")
        limit = input("Enter post-limit:\n\tGood limit for top posts: week -> 25posts, month -> 100posts\n")
        sort = input("Enter sorting type - 'hot' or 'top':\n")
        if sort == "top":
            time_filter = input("Enter time period (week, month, year, all):\n")
            adl_list = parse_submissions_for_links(parse_subreddit(subr, sort, int(limit), time_filter=time_filter))
        else:
            # fromtxt False -> check lastdltime against submission date of posts when dling from hot posts
            adl_list = parse_submissions_for_links(parse_subreddit(subr, sort, int(limit)), fromtxt=False)
            write_last_dltime()
        rip_audio_dls(adl_list)
        main()
    elif opt == "7":
        txtfn = input("Enter filename of txt file containing post URLs separated by newlines\n")
        llist = get_sub_from_reddit_urls(txt_to_list(os.path.join(ROOTDIR, "_linkcol"), txtfn))
        adl_list = parse_submissions_for_links(llist, True)
        rip_audio_dls(adl_list)
        main()
    elif opt == "8":
        subname = input("Enter name of subreddit\n")
        limit = input("Enter limit for found submissions, max 1000 forced by Reddit:\n")
        searchstring = input("Enter search string:\n")
        found_subs = search_subreddit(subname, searchstring, limit=int(limit))
        adl_list = parse_submissions_for_links(found_subs, True)
        rip_audio_dls(adl_list)
        main()
    elif opt == "9":
        # print(timeit.timeit('filter_alrdy_downloaded(l)',
        #               setup="from __main__ import filter_alrdy_downloaded, txt_to_list, ROOTDIR, l; import os",
        #               number=10000))
        # filter_alrdy_downloaded(txt_to_list(os.path.join(ROOTDIR, "_linkcol"), "test.txt"), "test")

        mypath = os.path.join(ROOTDIR, "_linkcol")

        rip_audio_dls(gen_audiodl_from_sglink(txt_to_list(mypath, "test2.txt")))
        main()


class AudioDownload:
    def __init__(self, sgasm_url, reddit_info=None):
        self.sgasm_url = sgasm_url
        self.sgasm_usr = self.sgasm_url.split("/u/", 1)[1].split("/", 1)[0]
        self.reddit_info = reddit_info
        self.url_to_file = None
        self.title = None
        self.filename_local = None
        self.descr = None

    def set_sgasm_info(self):
        logger.info("Getting soundgasm info of: %s" % self.sgasm_url)
        try:
            site = urllib.request.urlopen(self.sgasm_url)
            html = site.read().decode('utf-8')
            site.close()
            nhtml = html.split("aria-label=\"title\">")
            title = nhtml[1].split("</div>", 1)[0]
            # descript = nhtml[1].split("Description: ")[1].split("</li>\r\n", 1)[0]
            descript = \
                nhtml[1].split("<div class=\"jp-description\">\r\n          <p style=\"white-space: pre-wrap;\">")[
                    1].split(
                    "</p>\r\n", 1)[0]
            urlm4a = nhtml[1].split("m4a: \"")[1].split("\"\r\n", 1)[0]
            # set instance values
            self.url_to_file = urlm4a
            self.title = title
            self.filename_local = re.sub("[^\w\-_\.,\[\] ]", "_", title[0:110]) + ".m4a"
            self.descr = descript
        except urllib.request.HTTPError:
            logger.warning("HTTP Error 404: Not Found: \"%s\"" % self.sgasm_url)

    def write_selftext_file(self):
        if self.reddit_info["selftext"]:
            write_to_txtf(self.reddit_info["selftext"], self.filename_local + ".txt", self.sgasm_usr)


def rip_users(sgusr_urls):
    # trennt user url string an den kommas
    sgusr_urllist = sgusr_urls.split(",")
    for usr in sgusr_urllist:
        # geht jede url in der liste durch entfernt das komma und gibt sie an rip_usr_to_files weiter
        rip_usr_to_files(usr.strip(","))


def txt_to_list(path, txtfilename):
    with open(os.path.join(path, txtfilename), "r", encoding="UTF-8") as f:
        llist = f.read().split()
        return llist


def get_sub_from_reddit_urls(urllist):
    sublist = []
    for url in urllist:
        # changed
        sublist.append(reddit_praw.submission(url=url))
    return sublist


# avoid too many function calls since they are expensive in python
def gen_audiodl_from_sglink(sglinks):
    dl_list = []
    for link in sglinks:
        a = AudioDownload(link)
        dl_list.append(a)
    return dl_list


def rip_audio_dls(dl_list, current_usr=None):
    """
    Accepts list of AudioDownload instances and filters them for new downloads and saves them to disk by
    calling rip_file
    :param dl_list: List of AudioDownload instances
    :param current_usr: name of user when called from rip_usr_to_files
    :return: User rip string when downloading sgasm user
    """
    single = True
    if current_usr:
        single = False

    userrip_str = ""
    # when assigning instance Attributs of classes like self.url
    # Whenever we assign or retrieve any object attribute like url, Python searches it in the object's
    # __dict__ dictionary -> Therefore, a_file.url internally becomes a_file.__dict__['url'].
    # could just work with dicts instead since theres no perf loss, but using classes may be easier to
    # implement new featueres
    # TODO refactor better way? or just check for dl with other url/fname etc -> sgasm_url /u/USER/Title.. better
    # create dict that has direct links to files as keys and AudioDownload instances as values
    dl_dict = {}
    for audio in dl_list:
        dl_dict[audio.sgasm_url] = audio

    # returns list of new downloads, dl_dict still holds all of them
    new_dls = filter_alrdy_downloaded(dl_dict, current_usr)

    filestodl = len(new_dls)
    dlcounter = 0

    for url in new_dls:
        audio_dl = dl_dict[url]
        # get direct url, sgasm title etc.
        audio_dl.set_sgasm_info()
        # teilt string in form von https://soundgasm.net/u/USERNAME/link-to-post an /u/,
        # so erhaelt man liste mit https://soundgasm.net/u/, USERNAME/link-to-post
        # wird weiter an / geteilt aber nur ein mal und man hat den username
        currentusr = audio_dl.sgasm_usr
        txtfilename = "sgasm-" + currentusr + "-rip.txt"
        erg = rip_file(audio_dl, txtfilename, currentusr, dlcounter, filestodl,
                       single=single, usrrip_string=userrip_str)
        dlcounter = erg[0]
        # as string is immutable, we cant modify it by passing a reference so we have to return it
        # and assign it her locally, would be working fine for a mutable type e.g. list
        userrip_str = erg[1]

    return userrip_str, dlcounter


def rip_usr_to_files(sgasm_usr_url):
    currentusr = sgasm_usr_url.split("/u/", 1)[1].split("/", 1)[0]
    logger.info("Ripping user %s" % currentusr)

    dl_list = gen_audiodl_from_sglink(rip_usr_links(sgasm_usr_url))
    # zeit bei anfang des dl in variable schreiben
    now = time.strftime("%d/%m/%Y %H:%M:%S")

    txtfilename = "sgasm-" + currentusr + "-rip.txt"

    userrip_string, dlcount = rip_audio_dls(dl_list, currentusr)

    # falls dateien beim user rip geladen wurden wird der string in die textdatei geschrieben
    if userrip_string:
        write_to_txtf("User Rip von {} mit {} neuen Dateien am {}\n\n{}".format(currentusr, dlcount,
                                                                                now, userrip_string),
                      txtfilename, currentusr)


# # keep track if we alrdy warned the user
# warned = False
#
# # filestodl decreased by one if a file gets skipped
# if erg[1] != filestodl:
#     skipped_file_counter += 1
# # if the same -> not consecutive -> set to zero
# else:
#     skipped_file_counter = 0
#
# # since new audios show up on the top on sgasm user page and rip_usr_links() writes them to a list
# # from top to bottom -> we can assume the first links we dl are the newest posts
# # -> too many CONSECUTIVE Files already downloaded -> user_rip is probably up-to-date
# # ask if we should continue for the offchance of having downloaded >15--25 newer consecutive files
# # but not the old ones (when using single dl)
# if not warned and skipped_file_counter > 15:
#     option = input("Over 15 consecutive files already had been downloaded. Should we continue?\n"
#                    "y or n?: ")
#     if option == "n":
#         break
#     else:
#         warned = True

def rip_usr_links(sgasm_usr_url):
    site = urllib.request.urlopen(sgasm_usr_url)
    html = site.read().decode('utf-8')
    site.close()
    # links zu den einzelnen posts isolieren
    nhtml = html.split("<div class=\"sound-details\"><a href=\"")
    del nhtml[0]
    user_files = []
    for splits in nhtml:
        # teil str in form von https://soundgasm.net/u/USERNAME/link-to-post> an ">" und schreibt
        # den ersten teil in die variable url
        url = splits.split("\">", 1)[0]
        # url in die liste anfuegen
        user_files.append(url)
    filestodl = len(user_files)
    logger.info("Found " + str(filestodl) + " Files!!")
    return user_files


def rip_file(audio_dl, txtfilename, currentusr, curfnr, maxfnr, single=True, usrrip_string=""):
    if audio_dl.url_to_file is not None:
        curfnr += 1

        filename = audio_dl.filename_local
        mypath = os.path.join(ROOTDIR, currentusr)
        if not os.path.exists(mypath):
            os.makedirs(mypath)
        i = 0
        if os.path.isfile(os.path.join(mypath, filename)):
            if check_direct_url_for_dl(audio_dl.url_to_file, currentusr):
                # TODO insert URLsg etc.
                set_missing_values_df(df, audio_dl)
                logger.warning("!!! File already exists and was found in direct urls but not in sg_urls!\n"
                               "--> not renaming --> SKIPPING")
            else:
                logger.info("FILE ALREADY EXISTS - RENAMING:")
                # file alrdy exists but it wasnt in the url databas -> prob same titles only one tag or the ending is
                # different (since fname got cut off, so we dont exceed win path limit)
                # count up i till file doesnt exist anymore
                while os.path.isfile(os.path.join(mypath, filename)):
                    i += 1
                    filename = audio_dl.filename_local[:-8] + "_" + str(i).zfill(3) + ".m4a"
                # set filename on AudioDownload instance
                audio_dl.filename_local = filename

        logger.info("Downloading: " + filename + ", File " + str(curfnr) + " of " + str(maxfnr))

        # try:
        #     urllib.request.urlretrieve(audio_dl.url_to_file, os.path.abspath(os.path.join(mypath, filename)))
        # except urllib.request.HTTPError:
        #     logger.warning("HTTP Error 404: Not Found: \"%s\"" % audio_dl.url_to_file)

        # single -> no user rip; write afer dl so when we get interrupted we can atleast dl the file by renaming it
        if single and audio_dl.reddit_info:
            write_to_txtf(gen_dl_txtstring(("Added", time.strftime("%d/%m/%Y %H:%M:%S")), ("Title", audio_dl.title),
                                           ("Description", audio_dl.descr), ("URL", audio_dl.url_to_file),
                                           ("URLsg", audio_dl.sgasm_url), ("Local filename", filename),
                                           ("redditURL", audio_dl.reddit_info["permalink"]),
                                           ("redditTitle", audio_dl.reddit_info["title"]), ("end", "")),
                          txtfilename, currentusr)
            # also write reddit selftext in txtfile with same name as audio
            audio_dl.write_selftext_file()
        # TODO keep updating txtfile or just use csv?
        elif single and not audio_dl.reddit_info:
            write_to_txtf(gen_dl_txtstring(("Added", time.strftime("%d/%m/%Y %H:%M:%S")), ("Title", audio_dl.title),
                                           ("Description", audio_dl.descr), ("URL", audio_dl.url_to_file),
                                           ("URLsg", audio_dl.sgasm_url), ("Local filename", filename),
                                           ("end", "")), txtfilename, currentusr)
        else:
            usrrip_string += gen_dl_txtstring(("Title", audio_dl.title), ("Description", audio_dl.descr),
                                              ("URL", audio_dl.url_to_file), ("URLsg", audio_dl.sgasm_url),
                                              ("Local filename", filename), ("end", ""))

        return curfnr, usrrip_string
    else:
        logger.warning("FILE DOWNLOAD SKIPPED - NO DATA RECEIVED")
        return curfnr, usrrip_string


def set_missing_values_df(dframe, audiodl_obj):
    # get index of matching direct url in dframe
    index = dframe[dframe["URL"] == audiodl_obj.url_to_file].index[0]
    # fill_dict = {"Local filename": audiodl_obj.filename_local, "URLsg": audiodl_obj.sgasm_url}
    # dframe.iloc[index, :].fillna(fill_dict, inplace=True)
    # isnull on row iloc[index] returns Series with True for null values
    # only np.nan pd.NaT or None are considered null by isnull()
    cell_null_bool = dframe.iloc[index].isnull()
    # if field isnull()
    if cell_null_bool["URLsg"]:
        # dframe["URLsg"][index] = audiodl_obj.sgasm_url
        dframe.set_value(index, "URLsg", audiodl_obj.sgasm_url)
    else:
        logger.warning("Field not set since it wasnt empty when trying to set "
                       "URLsg on row[{}] for {}".format(index, audiodl_obj.title))
    if cell_null_bool["Local_filename"]:
        dframe.set_value(index, "Local_filename", audiodl_obj.filename_local)
    else:
        logger.warning("Field not set since it wasnt empty when trying to set Local filename "
                       "on row for {}[{}]".format(audiodl_obj.title, index))
    # also set reddit info if available
    if audiodl_obj.reddit_info:
        if cell_null_bool["redditURL"]:
            dframe.set_value(index, "redditURL", audiodl_obj.reddit_info["permalink"])
        else:
            logger.warning("Field not set since it wasnt empty when trying to set redditURL "
                           "on row for {}[{}]".format(audiodl_obj.title, index))
        if cell_null_bool["redditTitle"]:
            dframe.set_value(index, "redditTitle", audiodl_obj.reddit_info["title"])
        else:
            logger.warning("Field not set since it wasnt empty when trying to set redditTitle "
                           "on row for {}[{}]".format(audiodl_obj.title, index))


def gen_dl_txtstring(*args):
    # args is tuple of tuples
    result_string = ""
    for name, value in args:
        if name == "end":
            result_string += DLTXT_ENTRY_END
        elif name == "Added":
            result_string += "\t{}: {},\n\n".format(name, value)
        elif ("http" in value) or (value.endswith(".m4a")) or ("URL" in name):
            result_string += "\t{}: \"{}\",\n".format(name, value)
        else:
            result_string += "\t{}: {},\n".format(name, value)
    return result_string


def write_to_txtf(wstring, filename, currentusr):
    mypath = os.path.join(ROOTDIR, currentusr)
    if not os.path.exists(mypath):
        os.makedirs(mypath)
    with open(os.path.join(mypath, filename), "a", encoding="UTF-8") as w:
        w.write(wstring)


def load_downloaded_urls(txtfilename, currentusr):
    downloaded_urls = []
    mypath = os.path.join(ROOTDIR, currentusr)
    if os.path.isfile(os.path.join(mypath, txtfilename)):
        with open(os.path.join(mypath, txtfilename), 'r', encoding="UTF-8") as f:
            read_data = f.read()
            urllist = read_data.split("\n\tURL: \"")
            del urllist[0]
            for url in urllist:
                downloaded_urls.append(url.split("\"", 1)[0])
    return downloaded_urls


def check_direct_url_for_dl(m4aurl, current_usr=None):
    """
    Returns True if file was already downloaded
    :param m4aurl: direct URL to m4a file
    :param downloaded_urls: list of already downloaded m4a urls
    :return: True if m4aurl is in downloaded_urls, else False
    """
    if current_usr:
        try:
            if m4aurl in grped_df.get_group(current_usr)["URL"].values:
                return True
            else:
                return False
        except KeyError:
            logger.info("User '{}' not yet in databas!".format(current_usr))
            return False
    else:
        if m4aurl in df["URL"].values:
            return True
        else:
            return False


def filter_alrdy_downloaded(dl_dict, currentusr=None):
    # OLD when passing 2pair tuples, unpack tuples in dl_list into two lists
    # url_list, title = zip(*dl_list)
    # filter dupes
    # TODO doesnt keep order, only relevant for user rip
    unique_urls = set(dl_dict.keys())
    if currentusr:
        try:
            duplicate = unique_urls.intersection(grped_df.get_group(currentusr)["URLsg"].values)
        except KeyError:
            logger.info("User '{}' not yet in databas!".format(currentusr))
            duplicate = set()
    else:
        # timeit 1000: 0.19
        duplicate = unique_urls.intersection(df["URLsg"].values)

    dup_titles = ""
    # OLD when passing 2pair tuples -> create dict from it, NOW passing ref to dict
    # next -> Retrieve the next item from the iterator by calling its next() method.
    # iterates over list till it finds match, list comprehension would iterate over whole list
    # timeit: 0.4678
    # for a, b in dl_list -> iterates over dl_list unpacking the tuples
    # returns b if a == url
    # for url in duplicate:
    #     dup_titles += next(b for a, b in dl_list if a == url) + "\n"

    # dl_list is list of 2-tuples (2elements) -> basically key-value-pairs
    # -> turn into dict with dict(), this method(same string concat): 0.4478
    # d = dict(dl_list)
    for dup in duplicate:
        dup_titles += " ".join(dl_dict[dup].sgasm_url[24:].split("-")) + "\n"
    if dup_titles:
        logger.info("{} files were already downloaded: \n{}".format(len(duplicate), dup_titles))

    # set.symmetric_difference()
    # Return a new set with elements in either the set or other but not both.
    # -> duplicates will get removed from unique_urls
    result = list(unique_urls.symmetric_difference(duplicate))
    # str.contains accepts regex patter, join url strings with | -> htt..m4a|htt...m4a etc
    # returns Series/array of boolean values, .any() True if any element is True
    # timeit 1000: 1.129
    # mask = df["URL"].str.contains('|'.join(url_list))
    # isin also works
    # timeit 1000: 0.29
    # mask = df["URL"].isin(unique_urls)
    # print(df["URL"][mask])

    return result


def watch_clip(domain):
    dm = eval("clipwatcher_single.is_" + domain + "_url")
    watcher = clipwatcher_single.ClipboardWatcher(dm, clipwatcher_single.print_write_to_txtf, 0.1)
    try:
        logger.info("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        logger.info("Stopped watching clipboard!")


def parse_subreddit(subreddit, sort, limit, time_filter=None):
    sub = reddit_praw.subreddit(subreddit)
    if sort == "hot":
        return sub.hot(limit=limit)
    elif sort == "top":
        return sub.top(time_filter=time_filter, limit=limit)
    else:
        logger.warning("Sort must be either 'hot' or 'top'!")
        main()


def search_subreddit(subname, searchstring, limit=100, sort="top", **kwargs):
    # sort: relevance, hot, top, new, comments (default: relevance).
    # syntax: cloudsearch, lucene, plain (default: lucene) in praw4 cloud
    # time_filter – Can be one of: all, day, hour, month, week, year (default: all)
    subreddit = reddit_praw.subreddit(subname)

    found_sub_list = []

    # Returns a generator for submissions that match the search query
    # TODO add way to pass kwargs from input or modify val for time_filter
    matching_sub_gen = subreddit.search(searchstring, sort=sort, time_filter="all", limit=limit,
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
def parse_submissions_for_links(sublist, fromtxt=True):
    dl_list = []
    lastdltime = get_last_dltime()
    for submission in sublist:
        if (not check_submission_banned_tags(submission, KEYWORDLIST) and
                (fromtxt or check_submission_time(submission, lastdltime))):
            found_urls = []
            if "soundgasm.net" in submission.url:
                found_urls.append(submission.url)
                logger.info("Link found in URL of: " + submission.title)
                check_new_redditor(submission.url, str(submission.author))
            elif (submission.selftext_html is not None) and ("soundgasm.net" in submission.selftext_html):
                soup = bs4.BeautifulSoup(submission.selftext_html, "html.parser")

                # selects all anchors(a) with href attribute that contains "soundgasm.net/u/"
                # ^= is for begins with, $= is for ends with, *= is for is in
                # select returns them as tag objects
                sgasmlinks = soup.select('a[href*="soundgasm.net/u/"]')
                uchecked = False
                for link in sgasmlinks:
                    usrcheck = re.compile("/u/.+/.+", re.IGNORECASE)
                    if usrcheck.search(link["href"]):
                        # appends href-attribute of tag object link
                        found_urls.append(link["href"])
                        logger.info("SGASM link found in text, in submission: " + submission.title)
                        if not uchecked:
                            check_new_redditor(link["href"], str(submission.author))
                            uchecked = True
            else:
                logger.info("No soundgsam link in \"" + submission.shortlink + "\"")
                with open(os.path.join(ROOTDIR, "_linkcol", "reddit_nurl_" + time.strftime("%Y-%m-%d_%Hh.html")),
                          'a', encoding="UTF-8") as w:
                    w.write(
                        "<h3><a href=\"https://reddit.com" + submission.permalink + "\">" + submission.title + "</a><br/>by " +
                        str(submission.author) + "</h3>\n")
            reddit_info = {"title": submission.title, "permalink": str(submission.permalink),
                           "selftext": submission.selftext, "r_user": submission.author.name,
                           "created_utc": submission.created_utc, "id": submission.id,
                           "subreddit": submission.subreddit.display_name, "r_post_url": submission.url}
            # create AudioDownload from found_urls
            for url in found_urls:
                dl_list.append(AudioDownload(url, reddit_info=reddit_info))

    return dl_list


def check_new_redditor(url, username):
    currentusr = url.split("/u/", 1)[1].split("/", 1)[0]
    filename = "reddit_u_" + username + ".txt"
    # check for reddit_u_USERNAME.txt
    # if os.path.isfile(ROOTDIR, currentusr, #FILENAME)
    if os.path.isfile(os.path.join(ROOTDIR, currentusr, filename)):
        return True
    else:
        write_to_txtf(username, filename, currentusr)
        return False


def check_submission_banned_tags(submission, keywordlist):
    # checks submissions title for banned words contained in keywordlist
    # returns True if it finds a match
    for keyword in keywordlist:
        if keyword in submission.title.lower():
            logger.info("Banned keyword in: " + submission.title.lower() + "\n\t slink: " + submission.shortlink)
            return True


def write_last_dltime():
    if not os.path.exists(ROOTDIR):
        os.makedirs(ROOTDIR)
    with open(os.path.join(ROOTDIR, "LASTDLTIME.TXT"), "w") as w:
        w.write(str(time.time()))


def get_last_dltime():
    with open(os.path.join(ROOTDIR, "LASTDLTIME.TXT"), "r") as w:
        return float(w.read())


def check_submission_time(submission, lastdltime):
    if submission.created_utc > lastdltime:
        logger.info("Submission is newer than lastdltime")
        return True
    else:
        logger.info("Submission is older than lastdltime")
        return False


if __name__ == "__main__":
    main()
