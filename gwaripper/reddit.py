import logging
import os
import re
import time

import praw
import bs4

from .config import config
from .audio_dl import AudioDownload, DELETED_USR_FOLDER
from .exceptions import NoAPIResponseError, NoAuthenticationError

logger = logging.getLogger(__name__)

# installed app -> only client_id needed, but read-only access until we get a refresh_token
# for this script read-only access is enough
reddit_client_id = config["Reddit"]["CLIENT_ID"]
reddit_client_id = (reddit_client_id if
                    (reddit_client_id and not
                     reddit_client_id.startswith("to get a client id"))
                    else None)


def reddit_praw():
    if reddit_client_id is None:
        raise NoAuthenticationError("Client ID is required to access reddit: "
                                    "https://www.reddit.com/prefs/apps/")
    reddit = praw.Reddit(client_id=reddit_client_id,
                         client_secret=config["Reddit"].get("CLIENT_SECRET", None),
                         user_agent=config["Reddit"]["USER_AGENT"])
    reddit.read_only = True
    return reddit


def parse_subreddit(subreddit, sort, limit, time_filter=None):
    """
    Return limit number of submissions in subreddit with sorting method provided with sort

    :param subreddit: Name of subreddit
    :param sort: Sorting method, only "hot" or "top"
    :param limit: Number of submissions to get (1000 max by reddit, 100 per request)
    :param time_filter: Time period to use, can be all, day, hour, month, week, year
    :return: praw.ListingGenerator
    """
    sub = reddit_praw().subreddit(subreddit)
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
    subreddit = reddit_praw().subreddit(subname)

    found_sub_list = []
    # Returns a generator for submissions that match the search query
    matching_sub_gen = subreddit.search(searchstring, sort=sort, limit=limit,
                                        syntax="lucene", params={'include_over_18': 'on'},
                                        **kwargs)
    # iterate over generator and append found submissions to list
    for sub in matching_sub_gen:
        found_sub_list.append(sub)
    found_sub_list = redirect_crossposts(found_sub_list)
    return found_sub_list


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
        sub = reddit_praw().submission(url=url)
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
            sub_redirect = reddit_praw().submission(id=sub.crosspost_parent.split("_")[1])
            result.append(sub_redirect)
        else:
            result.append(sub)
    return result
