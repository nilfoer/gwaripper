import logging

import praw

from typing import Optional, List, Iterator

from .config import config
from .exceptions import NoAuthenticationError

logger = logging.getLogger(__name__)

# installed app -> only client_id needed, but read-only access until we get a refresh_token
# for this script read-only access is enough
reddit_client_id: Optional[str] = config["Reddit"]["CLIENT_ID"]
reddit_client_id = (reddit_client_id if
                    (reddit_client_id and not
                     reddit_client_id.startswith("to get a client id"))
                    else None)
reddit_instance = None


def reddit_praw() -> praw.Reddit:
    if reddit_instance is None:
        if reddit_client_id is None:
            raise NoAuthenticationError("Client ID is required to access reddit: "
                                        "https://www.reddit.com/prefs/apps/")
        reddit = praw.Reddit(client_id=reddit_client_id,
                             client_secret=config["Reddit"].get("CLIENT_SECRET", None),
                             user_agent=config["Reddit"]["USER_AGENT"])
        reddit.read_only = True
    else:
        return reddit_instance
    return reddit


def parse_subreddit(subreddit: str, sort: str, limit: int, time_filter: Optional[str] = None):
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


def search_subreddit(subname: str, searchstring: str, limit: int = 100,
                     sort: str = "top", **kwargs) -> List[praw.models.Submission]:
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

    # Returns a generator for submissions that match the search query
    matching_sub_gen: Iterator[praw.models.Submission] = subreddit.search(
            searchstring, sort=sort, limit=limit,
            syntax="lucene", params={'include_over_18': 'on'},
            **kwargs)
    found_sub_list = redirect_crossposts(matching_sub_gen)
    return found_sub_list


def redirect_xpost(sub: praw.models.Submission) -> praw.models.Submission:
    """
    Redirects crosspost to the original submission - does nothing
    to non-crossposted submissions

    :param sub: praw.models.Submission
    :return: redirected praw.models.Submission
    """
    try:
        parent = sub.crosspost_parent
        logger.info("Reddit submission with id %s is a crosspost, using the redirected "
                    "submission with id %s instead!", sub.id, parent)
        if not sub.crosspost_parent_list:
            logger.warning("Empty parent list, crosspost has most likely been deleted!")
        elif len(sub.crosspost_parent_list) > 1:
            logger.info("Submission has more than one crosspost parent!")
        # crosspost_parent has the full name of the submission -> u get id by splitting at '_'
        # e.g. id 'j6y1n9' has a crosspost_parent of 't3_boo4rq'
        # The fullname of an object is the object’s type followed by an
        # underscore and its base-36 id. An example would be t3_boo4rq, where
        # the t3 signals that it is a Submission, and the submission ID is 1h4f3.
        sub_redirect = reddit_praw().submission(id=parent.split("_")[1])
        return sub_redirect
    except AttributeError:
        return sub


def redirect_crossposts(subs: Iterator[praw.models.Submission]) -> List[praw.models.Submission]:
    """
    Redirects crossposts to the original submission and returns them as a list - does nothing
    to non-crossposted submissions

    :param subs: Iterable of praw.models.Submission
    :return: List of praw.models.Submission
    """
    return [redirect_xpost(sub) for sub in subs]
