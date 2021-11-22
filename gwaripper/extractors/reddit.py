import re
import logging

import bs4
import prawcore

from typing import Optional, cast, Pattern, ClassVar, List, Tuple, Type, TypeVar

from praw.models import Submission

from .base import BaseExtractor, ExtractorErrorCode, ExtractorReport, title_has_banned_tag
from .soundgasm import SoundgasmUserExtractor
# NOTE: IMPORTANT need to be imported as "import foo" rather than "from foo import bar"
# see :GlobalConfigImport
from .. import config
from ..info import RedditInfo, children_iter_dfs
from ..reddit import reddit_praw, redirect_xpost
from ..exceptions import InfoExtractingError

logger = logging.getLogger(__name__)


# praw is not marked as a PEP 561 compatible package so praw.models.Submission
# will just be typed as Any and mypy won't provide even the most basic
# type-checking
class RedditExtractor(BaseExtractor[Submission]):

    EXTRACTOR_NAME: ClassVar[str] = "Reddit"
    BASE_URL: ClassVar[str] = "reddit.com"

    # grp1: subreddit, grp2: reddit id, grp3: title
    VALID_REDDIT_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.|old\.)?reddit\.com/r/(\w+)/comments/"
            r"([A-Za-z0-9]+)/(\w+)?/?", re.IGNORECASE)

    REDDIT_DOMAIN_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.|old\.)?reddit\.com/(\w+)", re.IGNORECASE)

    def __init__(self, url: str, init_from: Optional[Submission] = None):
        super().__init__(url)
        self.praw = reddit_praw()
        # NOTE: since we don't have static type checking for this, check
        # it dynamically; for more info see comment above class
        if init_from is not None:
            assert isinstance(init_from, Submission)
        self.submission = init_from

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_REDDIT_URL_RE.match(url))

    def _handle_praw_exc(self, exc: prawcore.exceptions.ResponseException) -> Tuple[
            None, ExtractorReport]:
        if BaseExtractor.http_code_is_extractor_broken(exc.response.status_code):
            raise InfoExtractingError(
                    "The Reddit API returned an HTTP status code that "
                    "implies an error on our side! Either we matched an "
                    "erroneous URL or the third-party library PRAW is "
                    "broken!", self.url)
        else:
            return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

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

        # trigger praw lazy object here so we can except ResponseException
        try:
            sub_title = submission.title
        except prawcore.exceptions.ResponseException as err:
            return self._handle_praw_exc(err)

        if not title_has_banned_tag(sub_title):
            # NOTE: IMPORTANT make sure to only use redirected submission from here on!
            try:
                submission = redirect_xpost(submission)
            except prawcore.exceptions.ResponseException as err:
                return self._handle_praw_exc(err)
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
                    # TODO skipping "recursive" FileCollections should be handled in gwaripper.py
                    # NOTE: @Hack checking extractor types directly
                    if extractor is type(self) or extractor is type(SoundgasmUserExtractor):
                        # disallow following refs into other reddit submissions
                        logger.warning("Skipped supported %s url(%s) at %s, since it might lead to"
                                       " downloading a lot of unwanted audios!",
                                       cast(BaseExtractor, extractor).EXTRACTOR_NAME,
                                       href, submission.shortlink)
                        # NOTE: we don't change the error code of the parent here, this it not
                        # technically regarded as an error
                        report.children.append(
                                ExtractorReport(href, ExtractorErrorCode.STOP_RECURSION))
                        continue
                    if extractor is not None:
                        logger.info("%s link found in selftext of: %s",
                                    extractor.EXTRACTOR_NAME, submission.permalink)
                        if title_has_banned_tag(link.text):
                            report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
                            report.children.append(
                                    ExtractorReport(href, ExtractorErrorCode.BANNED_TAG))
                            continue

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
