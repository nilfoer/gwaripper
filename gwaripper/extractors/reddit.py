import os
import time
import re
import logging

import bs4

from typing import Optional

from .base import BaseExtractor
from ..config import KEYWORDLIST, TAG1_BUT_NOT_TAG2, ROOTDIR
from ..info import RedditInfo
from ..reddit import reddit_praw

logger = logging.getLogger(__name__)


class RedditExtractor(BaseExtractor):

    EXTRACTOR_NAME = "Reddit"
    BASE_URL = "reddit.com"

    # grp1: subreddit, grp2: reddit id, grp3: title
    VALID_REDDIT_URL_RE = re.compile(
            r"^(?:https?://)?(?:www\.|old\.)?reddit\.com/r/(\w+)/comments/"
            r"([A-Za-z0-9]+)/(\w+)?/?", re.IGNORECASE)

    def __init__(self, url):
        super().__init__(url)
        self.praw = reddit_praw()

    @classmethod
    def is_compatible(cls, url):
        return cls.VALID_REDDIT_URL_RE.match(url)

    def extract(self) -> Optional[RedditInfo]:
        """
        Searches .url and .selftext_html of a reddit submission for supported urls.

        Checks if submission title contains banned tags and if time_check doesnt evaluate to False
        check if submission time is newer than last_dl_time loaded from config or utc timestamp
        if supplied with time_check

        If no urls were found log it and append links to html file named like reddit_nurl_%Y-%m-%d_%Hh.html
        so the user is able to check the subs himself for links

        :param time_check: True -> check if submission time is newer than last dl time from config, type float use
            this as lastdltime, False or None dont check submission time at all
        :return: RedditInfo
        """
        # @Hack needed since we directly parse and extract found links in the submission
        # but can't import at module level (absolute import also doesn't work since it's
        # the __init__ we're trying to import and that _creates_ the package) because it
        # would lead to circular ref
        from . import find_extractor
        # TODO: time_check=False):

        # time_check can be True, False, or a float, only load dltime if True -> use is True
        # if time_check is True:
        #     # get new lastdltime from cfg
        #     reload_config()
        #     lastdltime = config.getfloat("Time", "last_dl_time", fallback=0.0)
        # elif isinstance(time_check, (int, float)):
        #     lastdltime = time_check
        # else:
        #     lastdltime = None

        # lastdltime gets evaluated first -> only calls func if lastdltime not None
        # if lastdltime and not check_submission_time(submission, lastdltime):
        #     # submission is older than lastdltime -> next sub
        #     continue

        submission = self.praw.submission(url=self.url)

        if not check_submission_banned_tags(submission, KEYWORDLIST, TAG1_BUT_NOT_TAG2):
            sub_url = submission.url

            ri = RedditInfo(self.url, submission.id, submission.title)

            if sub_url:
                extractor = find_extractor(sub_url)
                if extractor is not None:
                    logger.info("{} link found in URL of: {}".format(extractor.EXTRACTOR_NAME,
                                                                     submission.title))
                    fi = extractor(sub_url).extract()
                    fi.parent = ri
                    ri.children.append(fi)
                    return ri

            if submission.selftext_html is not None:
                soup = bs4.BeautifulSoup(submission.selftext_html, "html.parser")
                # selftext_html is not like the normal html it starts with <div class="md"..
                # so i can just go through all a
                # css selector -> tag a with set href attribute
                links = soup.select('a[href]')

                # TODO i.redd.it only in sub.url not in selftext and always direct link
                # so i could just dl it
                for link in links:
                    href = link["href"]
                    extractor = find_extractor(href)
                    if extractor is not None:
                        logger.info("{} link found in selftext of: {}".format(
                            extractor.EXTRACTOR_NAME, submission.title))
                        fi = extractor(href).extract()
                        fi.parent = ri
                        ri.children.append(fi)

            if not ri.children:
                logger.info("No supported link in \"{}\"".format(submission.shortlink))
                os.makedirs(os.path.join(ROOTDIR, "_linkcol"), exist_ok=True)
                with open(os.path.join(ROOTDIR, "_linkcol",
                                       "reddit_nurl_" + time.strftime("%Y-%m-%d_%Hh.html")),
                          'a', encoding="UTF-8") as w:
                    w.write("<h3><a href=\"https://reddit.com{}\">{}"
                            "</a><br/>by {}</h3>\n".format(
                                submission.permalink, submission.title, submission.author))

            reddit_info = {"title": submission.title, "permalink": str(submission.permalink),
                           "selftext": submission.selftext,
                           "created_utc": submission.created_utc, "id": submission.id,
                           "subreddit": submission.subreddit.display_name,
                           "r_post_url": sub_url}
            try:
                reddit_info["r_user"] = submission.author.name
            except AttributeError:
                logger.warning("Author of submission id {} has been deleted! "
                               "Using None as r_user.".format(submission.id))
                reddit_info["r_user"] = None

        # # create AudioDownload from found_urls
        # for host, url in found_urls:
        #     if "imgur" in host:
        #         title_sanitized = re.sub(r"[^\w\-_.,\[\] ]", "_", submission.title[0:100])
        #         user_dir = reddit_info['r_user'] or DELETED_USR_FOLDER
        #         user_dir = os.path.join(ROOTDIR, f"{user_dir}")
        #         # direclty download imgur links
        #         if host == "imgur file":
        #             imgur = ImgurFile(None, url, user_dir, prefix=title_sanitized)
        #         else:
        #             try:
        #                 if host == "imgur album":
        #                     imgur = ImgurAlbum(url, user_dir, name=title_sanitized)
        #                 elif host == "imgur image":
        #                     imgur = ImgurImage(url, user_dir, prefix=title_sanitized)                         
        #                 else:
        #                     logger.error("Unrecognized imgur type: %s", host)
        #                     continue
        #             except NoAuthenticationError as e:
        #                 # repr(e) gives you the exception(and the message string); str(e) only gives the message string
        #                 logger.error(str(e))
        #                 continue
        #             except NoAPIResponseError as e:
        #                 logger.warning(str(e))
        #                 continue                        
        #         imgur.download()
        #     else:
        #         dl_list.append(AudioDownload(url, host, reddit_info=reddit_info))

        return ri


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
            logger.info(
                    "Banned keyword '{}' in: {}\n\t slink: {}".format(
                        keyword, subtitle, submission.shortlink))
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