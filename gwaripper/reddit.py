import logging
import os
import re
import time

import praw
import bs4

from .config import config, KEYWORDLIST, TAG1_BUT_NOT_TAG2, reload_config, ROOTDIR
from .audio_dl import AudioDownload, DELETED_USR_FOLDER
from .imgur import ImgurAlbum, ImgurFile, ImgurImage

logger = logging.getLogger(__name__)

# init Reddit instance
# installed app -> only client_id needed, but read-only access until we get a refresh_token
# for this script read-only access is enough
reddit_praw = praw.Reddit(client_id=config["Reddit"]["CLIENT_ID"],
                          client_secret=None,
                          user_agent=config["Reddit"]["USER_AGENT"])


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
        return redirect_crossposts(sub.hot(limit=limit))
    elif sort == "top":
        return redirect_crossposts(sub.top(time_filter=time_filter, limit=limit))
    else:
        logger.warning("Sort must be either 'hot' or 'top'!")


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
    found_sub_list = redirect_crossposts(found_sub_list)
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


# there must be a blank line between description of func in docstr and :param descriptions
# otherwise presentation of docstr by pycharm will be off, also if the descr of a :param
# is multiline the following lines must be indented(tab) till next :param or :return
def parse_submissions_for_links(sublist, supported_hosts, time_check=False):
    """
    Searches .url and .selftext_html of submissions in sublist for supported urls. Checks for
    every host-type in supported_hosts by searching for the string/regex pattern contained
    as values

    Checks if submission title contains banned tags and if time_check doesnt evaluate to False
    check if submission time is newer than last_dl_time loaded from config or utc timestamp
    if supplied with time_check

    Check if url contains part of supported hoster urls -> add to found_urls as tuple (host, url)
    Search all <a> tags with set href in selftext_html and if main part of support host url is contained
    -> add to found_urls

    If no urls were found log it and append links to html file named like reddit_nurl_%Y-%m-%d_%Hh.html
    so the user is able to check the subs himself for links

    Create dict of reddit info and append AudioDownload/s init with found url, host, and reddit_info to
    dl_list and return it once all submissions have been searched

    :param sublist: List of submission obj
    :param supported_hosts: Dict of host-type keywords as keys and strings/regex patterns as values
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
                if re.search(search_for, sub_url):
                    found_urls.append((host, sub_url))
                    logger.info("{} link found in URL of: {}".format(host, submission.title))
                    break

            # only search selftext if we havent already found url in sub_url and selftext isnt None
            if not found_urls and (submission.selftext_html is not None):
                soup = bs4.BeautifulSoup(submission.selftext_html, "html.parser")
                # selftext_html is not like the normal html it starts with <div class="md"..
                # so i can just go through all a
                # css selector -> tag a with set href attribute
                sgasmlinks = soup.select('a[href]')

                for link in sgasmlinks:
                    href = link["href"]
                    for host, search_for in supported_hosts.items():
                        if re.search(search_for, href):
                            # appends href-attribute of tag object link
                            found_urls.append((host, href))
                            logger.info("{} link found in selftext of: {}".format(host, submission.title))
                            # matched supported host, search next href
                            break
                    # TODO i.redd.it only in sub.url not in selftext and always direct link
                    # so i could just dl it
                    else:
                        if "i.redd.it/" in href:
                            logger.info("Image link found in submission with id '%s': %s",
                                        submission.id, href)

            if not found_urls:
                logger.info("No supported link in \"{}\"".format(submission.shortlink))
                os.makedirs(os.path.join(ROOTDIR, "_linkcol"), exist_ok=True)
                with open(os.path.join(ROOTDIR, "_linkcol", "reddit_nurl_" + time.strftime("%Y-%m-%d_%Hh.html")),
                          'a', encoding="UTF-8") as w:
                    w.write("<h3><a href=\"https://reddit.com{}\">{}"
                            "</a><br/>by {}</h3>\n".format(submission.permalink, submission.title, submission.author))
                # found_urls empty we can skip to next sub
                continue

            try:
                reddit_info = {"title": submission.title, "permalink": str(submission.permalink),
                               "selftext": submission.selftext, "r_user": submission.author.name,
                               "created_utc": submission.created_utc, "id": submission.id,
                               "subreddit": submission.subreddit.display_name, "r_post_url": sub_url}
            except AttributeError:
                logger.warning("Author of submission id {} has been deleted! "
                               "Using None as r_user.".format(submission.id))
                reddit_info = {"title": submission.title, "permalink": str(submission.permalink),
                               "selftext": submission.selftext, "r_user": None,
                               "created_utc": submission.created_utc, "id": submission.id,
                               "subreddit": submission.subreddit.display_name, "r_post_url": sub_url}

            # create AudioDownload from found_urls
            for host, url in found_urls:
                if "imgur" in host:
                    title_sanitized = re.sub("[^\w\-_.,\[\] ]", "_", submission.title[0:100])
                    user_dir = reddit_info['r_user'] or DELETED_USR_FOLDER
                    user_dir = os.path.join(ROOTDIR, f"{user_dir}")
                    # direclty download imgur links
                    if host == "imgur file":
                        imgur = ImgurFile(None, url, user_dir, prefix=title_sanitized)
                    elif host == "imgur album":
                        imgur = ImgurAlbum(url, user_dir, name=title_sanitized)
                    else:
                        imgur = ImgurImage(url, user_dir, prefix=title_sanitized)
                    imgur.download()
                else:
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


def check_submission_time(submission, lastdltime):
    """
    Check if utc timestamp of submission is greater (== older) than lastdltime

    :param submission: praw Submission obj
    :param lastdltime: utc timestamp (float)
    :return: True if submission is newer than lastdltime else False
    """
    if submission.created_utc > lastdltime:
        logger.debug("Submission is newer than lastdltime")
        return True
    else:
        logger.debug("Submission is older than lastdltime")
        return False


def get_sub_from_reddit_urls(urllist):
    """
    Filters duplicate urls and returns a list of Submission obj, that the urls are pointing to
    If the copied submission is a crosspost, the crossposted submission is used instead!

    :param urllist: List with urls point to reddit submissions
    :return: List with Submission obj that were obtained from the urls in urllist
    """
    urls_unique = set(urllist)
    sublist = []
    for url in urls_unique:
        sub = reddit_praw.submission(url=url)
        sublist.append(sub)
    sublist = redirect_crossposts(sublist)
    return sublist


def redirect_crossposts(subs):
    """
    Redirects crossposts to the original submission and returns them as a list - does nothing
    to non-crossposted submissions

    :param subs: Iterable of praw.Submission
    :return: List of praw.Submission
    """
    result = []
    for sub in subs:
        if hasattr(sub, "crosspost_parent"):
            # crosspost_parent has the full name of the submission -> u get id by splitting at '_'
            logger.info("Reddit submission with id %s is a crosspost, using the redirected "
                        "submission with id %s instead!", sub.id, sub.crosspost_parent)
            assert len(sub.crosspost_parent_list) == 1
            sub_redirect = reddit_praw.submission(id=sub.crosspost_parent.split("_")[1])
            result.append(sub_redirect)
        else:
            result.append(sub)
    return result
