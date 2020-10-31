import re
import logging

import bs4

from typing import Optional, cast, Pattern, ClassVar, List, Tuple, Type

from praw.models import Submission

from .base import BaseExtractor, ExtractorErrorCode, ExtractorReport
# NOTE: IMPORTANT need to be imported as "import foo" rather than "from foo import bar"
# see :GlobalConfigImport
from .. import config
from ..info import RedditInfo, children_iter_dfs
from ..reddit import reddit_praw, redirect_xpost

logger = logging.getLogger(__name__)


class RedditExtractor(BaseExtractor):

    EXTRACTOR_NAME: ClassVar[str] = "Reddit"
    BASE_URL: ClassVar[str] = "reddit.com"

    # grp1: subreddit, grp2: reddit id, grp3: title
    VALID_REDDIT_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.|old\.)?reddit\.com/r/(\w+)/comments/"
            r"([A-Za-z0-9]+)/(\w+)?/?", re.IGNORECASE)

    REDDIT_DOMAIN_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.|old\.)?reddit\.com/(\w+)", re.IGNORECASE)

    FILTER_URLS_RE: ClassVar[List[Pattern]] = [
            re.compile(r"^(?:https?://)?(?:www\.)?soundcloud\.com/", re.IGNORECASE),
            re.compile(r"^(?:https?://)?(?:www\.)?clyp.it/", re.IGNORECASE),
            re.compile(r"^(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE),
            re.compile(r"^(?:https?://)?(?:www\.)?vocaroo\.com/", re.IGNORECASE),
            re.compile(r"^(?:https?://)?(?:www\.)?sndup\.net/", re.IGNORECASE),
            ]

    def __init__(self, url: str, praw_submission: Optional[Submission] = None):
        super().__init__(url)
        self.praw = reddit_praw()
        self.submission = praw_submission

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_REDDIT_URL_RE.match(url))

    @classmethod
    def is_unsupported_audio_url(cls, url: str) -> bool:
        return any(filtered_re.match(url) for filtered_re in
                   RedditExtractor.FILTER_URLS_RE)

    def _extract(self) -> Tuple[Optional[RedditInfo], ExtractorReport]:
        """
        Searches .url and .selftext_html of a reddit submission for supported urls.

        Checks if submission title contains banned tags
        """
        # @Hack needed since we directly parse and extract found links in the submission
        # but can't import at module level (absolute import also doesn't work since it's
        # the __init__ we're trying to import and that _creates_ the package) because it
        # would lead to circular ref
        from . import find_extractor
        # TODO do the equivalent of the time check code using praw when searching
        # for submissions etc. since that is the only place it was being used at

        ri: Optional[RedditInfo] = None
        report: ExtractorReport = ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS)

        if self.submission is None:
            self.submission = self.praw.submission(url=self.url)
        submission: Submission = self.submission

        if not check_submission_banned_tags(submission,
                                            config.KEYWORDLIST, config.TAG1_BUT_NOT_TAG2):
            # NOTE: IMPORTANT make sure to only use redirected submission from here on!
            submission = redirect_xpost(submission)
            sub_url: str = submission.url

            # rebuild subs url to account for redirection
            redirected_url: str = f"{self.praw.config.reddit_url}{submission.permalink}"
            ri = RedditInfo(self.__class__, redirected_url, submission.id, submission.title,
                            None, submission.subreddit.display_name, str(submission.permalink),
                            submission.created_utc)
            ri.r_post_url = sub_url
            try:
                ri.author = submission.author.name
            except AttributeError:
                logger.warning("Author of submission id %s has been deleted! "
                               "Using None as r_user.", submission.id)
                ri.author = None

            # sub url not pointing to itself
            if not submission.is_self:
                extractor: Optional[Type[BaseExtractor]] = find_extractor(sub_url)

                if extractor is not None:
                    logger.info("%s link found in URL of: %s", extractor.EXTRACTOR_NAME,
                                submission.permalink)
                    fi, child_report = extractor.extract(sub_url, parent=ri,
                                                         parent_report=report)
                    if fi is None:
                        logger.error("Could not extract from URL that the submission "
                                     "points to: %s", sub_url)
                        return None, report
                else:
                    ri = None
                    logger.warning("Outgoing submission URL is not supported: %s", sub_url)
                    report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
                    report.children.append(
                            ExtractorReport(sub_url, ExtractorErrorCode.NO_EXTRACTOR))

            # elif is fine since posts with outgoing urls can't have a selftext
            elif submission.selftext_html is not None:
                ri.selftext = submission.selftext

                soup = bs4.BeautifulSoup(submission.selftext_html, "html.parser")
                # selftext_html is not like the normal html it starts with <div class="md"..
                # so i can just go through all a
                # css selector -> tag a with set href attribute
                links = soup.select('a[href]')

                # TODO i.redd.it is always a direct link append FileInfo for it here
                # without extractor?
                for link in links:
                    href = link["href"]
                    extractor = find_extractor(href)
                    if extractor is type(self):
                        # disallow following refs into other reddit submissions
                        continue
                    if extractor is not None:
                        logger.info("%s link found in selftext of: %s",
                                    extractor.EXTRACTOR_NAME, submission.permalink)
                        fi, extr_msgs = extractor.extract(href, parent=ri,
                                                          parent_report=report)
                    elif RedditExtractor.is_unsupported_audio_url(href):
                        logger.warning("Found unsupported audio link '%s' in "
                                       "submission at '%s'", href, submission.shortlink)
                        report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
                        report.children.append(
                                ExtractorReport(href, ExtractorErrorCode.NO_EXTRACTOR))

            if ri:
                if not (any(c.is_audio for _, c in children_iter_dfs(
                               ri.children, file_info_only=True))):
                    if config.config.getboolean('Settings', 'skip_reddit_without_audio',
                                                fallback=False):
                        # no audio file to download -> don't download anything
                        ri = None
                        # NOTE: only use this code if there are no children
                        report.err_code = ExtractorErrorCode.NO_SUPPORTED_AUDIO_LINK
                    logger.warning("No supported audio link in \"%s\"", submission.shortlink)

                if not cast(RedditInfo, ri).children:
                    report.err_code = ExtractorErrorCode.NO_SUPPORTED_AUDIO_LINK

        else:
            report.err_code = ExtractorErrorCode.BANNED_TAG

        return ri, report


def check_submission_banned_tags(submission: Submission, keywordlist: List[str],
                                 tag1_but_not_2: Optional[List[Tuple[str, str]]] = None) -> bool:
    """
    Checks praw Submission obj for banned tags (case-insensitive) from keywordlist in title
    returns True if tag is contained. Also returns True if one of the first tags in the tag-combos
    in tag1_but_not_2 is contained but the second isnt.

    Example:    tag1:"[f4f" tag2:"4m]"
                title: "[F4F][F4M] For both male and female listeners.." -> return False
                title: "[F4F] For female listeners.." -> return True

    :param submission: praw Submission obj to scan for banned tags in title
    :param keywordlist: banned keywords/tags
    :param tag1_but_not_2: List of 2-tuples, first tag(str) is only banned if
                           second isn't contained
    :return: True if submission is banned from downloading else False
    """
    # checks submissions title for banned words contained in keywordlist
    # returns True if it finds a match
    subtitle = submission.title.lower()

    for keyword in keywordlist:
        if keyword in subtitle:
            logger.warning(
                    "Banned keyword '{}' in: {}\n\t slink: {}".format(
                        keyword, subtitle, submission.shortlink))
            return True

    if tag1_but_not_2:
        for tag_b, tag_in in tag1_but_not_2:
            # tag_b is only banned if tag_in isnt found in subtitle
            if (tag_b in subtitle) and not (tag_in in subtitle):
                logger.warning("Banned keyword: no '{}' in title where '{}' is in: {}\n\t "
                               "slink: {}".format(tag_in, tag_b, subtitle, submission.shortlink))
                return True
    return False


def check_submission_time(submission: Submission, lastdltime: float) -> bool:
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
