import urllib.request
import urllib.error
import logging

from typing import (
        Optional, Dict, Union, ClassVar, Tuple, List, Any, TypeVar, Generic
        )
from enum import Enum, auto, unique

from ..exceptions import (
        InfoExtractingError, NoAPIResponseError,
        NoAuthenticationError, AuthenticationFailed
        )
from .. import config
from ..info import FileInfo, FileCollection

logger = logging.getLogger(__name__)


# codes only for indivual extractor errors not for collections
# since those are visible in the reports children
# only exception is NO_SUPPORTED_AUDIO_LINK since that could mean
# that there are no child reports and EMPTY_COLLECTION
# and ERROR_IN_CHILDREN so don't mark a parent as NO_ERRORS when
# a child has errors
@unique
class ExtractorErrorCode(Enum):
    NO_ERRORS = 0
    BROKEN_EXTRACTOR = auto()
    NO_RESPONSE = auto()
    BANNED_TAG = auto()
    NO_EXTRACTOR = auto()
    NO_AUTHENTICATION = auto()

    # collection
    ERROR_IN_CHILDREN = auto()
    EMPTY_COLLECTION = auto()  # no children at all
    NO_SUPPORTED_AUDIO_LINK = auto()  # only use this if there are no child reports


# TODO @CleanUp make this more general since it's not just extractor specific anymore
class ExtractorReport:

    children: List['ExtractorReport']

    def __init__(self, url: str, err_code: ExtractorErrorCode):
        self.url = url
        self.err_code = err_code
        self.children = []
        self.downloaded: bool = False


T = TypeVar('T')


# make BaseExtractor a generic class so we can specify an optional kwarg that
# the subclass extractrors can be initialized from and still keep type safety as
# long as subclasses explicitly specify type T like so
# BaseExtractor[praw.models.Submission] otherwise T will just be Any and there will
# be no type checking done on it
class BaseExtractor(Generic[T]):
    """
    Custom extractors for different sites should inherit from this class
    and implement the required methods

    is_compatible is called with the url to find an appropriate extractor

    extract or rather _extract is the main method that gets called on a suitable extractor
    """

    headers: ClassVar[Dict[str, str]] = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    # these need to be re-defined by sub-classes!!
    EXTRACTOR_NAME: ClassVar[str] = "Base"
    EXTRACTOR_ID: ClassVar[int] = 0
    BASE_URL: ClassVar[str] = ""

    # set by extractors on their class if an extraction fails and the extractor
    # should be considered broken
    is_broken: ClassVar[bool] = False

    # message for logging error codes
    err_value_msg: Dict[int, str] = {
        ExtractorErrorCode.BROKEN_EXTRACTOR.value: "",
        ExtractorErrorCode.NO_RESPONSE.value: "Request timed out or no response received!",
        ExtractorErrorCode.BANNED_TAG.value: "URL was skipped due to a banned tag!",
        ExtractorErrorCode.NO_EXTRACTOR.value: "No compatible exctractor could be found!",
        # TODO currently only used if no api key was found and raises an exception
        # which will get reported in .extract
        ExtractorErrorCode.NO_AUTHENTICATION.value: "",

        # TODO do we even report this?
        # ExtractorErrorCode.ERROR_IN_CHILDREN.value: "",
        ExtractorErrorCode.EMPTY_COLLECTION.value: (
            "Collection is empty! No supported and known unsupported links found!"),
        ExtractorErrorCode.NO_SUPPORTED_AUDIO_LINK.value: (
            "No supported audio could be extracted but there were known unsupported audio links!"),
    }

    # NOTE: workaround to get type checking to work with passing differently
    # typed kwarg in BaseExtractor.__init__
    # necessary since typing kwargs with different types doesn't work in mypy
    # use a workaround of having a generic type to optionally initialize from
    #
    # NOTE: IMPORTANT extractors that want to use init_from to be able to be
    # initialized with e.g. a dict need to inherit from
    # BaseExtractor[T] while explicitly specifiyng T
    def __init__(self, url: str, init_from: Optional[T] = None):
        # TODO: replace http with https by default?
        self.url = url

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        raise NotImplementedError

    # can raise InfoExtractingError (or exceptions based on it) if
    # they provide more information than the generic InfoExtractingError
    # that is raised by cls.extract on all Exceptions
    #
    # should only raise if event is unexpected and the extractor should
    # be considered broken (needed for exc_info): e.g. site changed their API
    # and should not raise for just a time-out, or a deleted resource
    # that could be expected
    # NOTE: only exception is (so far) NoAuthenticationError (since we currently
    # raise it in the __init__)
    #
    # returned string list are messages that go into the parsing report
    # since it's otherwise too easy to miss skipped urls, unsupported links,
    # in the logs etc.; strings should be formatted with html
    def _extract(self) -> Tuple[Optional[Union[FileInfo, FileCollection]],
                                ExtractorReport]:
        raise NotImplementedError

    # should not raise but rather logs unexpected and expected errors
    # and returns the appropriate error code
    @classmethod
    def extract(cls, url: str, parent: Optional[FileCollection] = None,
                parent_report: Optional[ExtractorReport] = None,
                init_from: Optional[T] = None) -> Tuple[
            Optional[Union[FileInfo, FileCollection]], ExtractorReport]:

        # all reports here have code BROKEN_EXTRACTOR
        report = ExtractorReport(url, ExtractorErrorCode.BROKEN_EXTRACTOR)
        result: Optional[Union[FileInfo, FileCollection]] = None

        if cls.is_broken:
            logger.warning("Skipping URL '%s' due to broken extractor: %s",
                           url, cls.EXTRACTOR_NAME)
        else:
            try:
                extractor = cls(url, init_from=init_from)

                result, report = extractor._extract()
            except NoAuthenticationError as err:
                cls.is_broken = True
                report.err_code = ExtractorErrorCode.NO_AUTHENTICATION

                logger.error("%s: %s Extractor will be marked as broken so subsequent "
                             "downloads of the same type will be skipped!",
                             err.__class__.__name__, err.msg)
            except (InfoExtractingError, NoAPIResponseError, AuthenticationFailed) as err:
                cls.is_broken = True

                logger.error("%s: %s (URL was: %s)", err.__class__.__name__, err.msg,
                             err.url)
                logger.debug("Full exception info for unexpected extraction failure:",
                             cls.EXTRACTOR_NAME, err.url, exc_info=True)
            except Exception:
                cls.is_broken = True
                logger.error("Error occured while extracting information from '%s' "
                             "- site structure or API probably changed! See if there are "
                             "updates available!", url)
                logger.debug("Full exception info for unexpected extraction failure:",
                             cls.EXTRACTOR_NAME, url, exc_info=True)
            else:
                # only log/print if no exc was raised since exc already get logged above
                cls.log_report(report)

        if result is not None:
            if parent is not None:
                if isinstance(result, FileCollection):
                    parent.add_collection(result)
                else:
                    parent.add_file(result)
            # set ref to report on info
            result.report = report
        if parent_report is not None:
            parent_report.children.append(report)
            # set error code for child errors on parent_report if it wasn't set before
            if (report.err_code != ExtractorErrorCode.NO_ERRORS and
                    parent_report.err_code == ExtractorErrorCode.NO_ERRORS):
                parent_report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
        return result, report

    @classmethod
    def log_report(cls, report: ExtractorReport):
        if report.err_code not in (
                ExtractorErrorCode.NO_ERRORS, ExtractorErrorCode.ERROR_IN_CHILDREN):
            logger.warning("ERROR - %s - %s (URL was %s)", report.err_code.name,
                           cls.err_value_msg[report.err_code.value],
                           report.url)

    @staticmethod
    def http_code_is_extractor_broken(http_code: Optional[int]) -> bool:
        # get_html returns None for http_code if an URL instead of HTTPError
        # happened, then it's not the extractors fault
        # NOTE: might still be extractors fault if the domain of the url was
        # completely wrong
        if http_code is None:
            return False

        # not 404: ('Not Found', 408 request timeout, 410: ('Gone', 'URI no longer exists
        # from 400 bad request to 417 expectation failed?
        # or 505: ('HTTP Version Not Supported', 501: ('Not Implemented',
        if ((http_code not in (404, 408, 410) and http_code >= 400 and http_code < 418) or
                http_code in (501, 505)):
            # client errors like forbidden, no authentication etc. means
            # extractor is broken
            # alot of 4xx errors could be caused by an invalid url that was passed in
            # but then the extractor should not have matched it
            return True
        else:
            # 404 not found could be both; if it could be 'not broken', assume it isn't
            # mostly 500er codes that mean that the failure is on the server side
            return False

    @classmethod
    def get_html(cls, url: str,
                 additional_headers: Optional[Dict[str, str]] = None) -> Tuple[
                         Optional[str], Optional[int]]:
        res: Optional[str] = None
        http_code: Optional[int] = None

        req = urllib.request.Request(url, headers=cls.headers)
        if additional_headers is not None:
            for k, v in additional_headers.items():
                req.add_header(k, v)

        try:
            site = urllib.request.urlopen(req)
        except urllib.error.HTTPError as err:
            http_code = err.code
            logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
        except urllib.error.URLError as err:
            # Often, URLError is raised because there is no network connection
            # (no route to the specified server), or the specified server
            # doesn’t exist
            logger.warning("URL Error: %s (url: %s)", err.reason, url)
        else:
            # leave the decoding up to bs4
            response = site.read()
            site.close()

            # try to read encoding from headers otherwise use utf-8 as fallback
            encoding = site.headers.get_content_charset()
            res = response.decode(encoding.lower() if encoding else "utf-8")
            logger.debug("Getting html done!")

        return res, http_code


def title_has_banned_tag(
        title: str, keywordlist: List[str] = config.KEYWORDLIST,
        tag1_but_not_2: Optional[
            List[Tuple[str, str]]] = config.TAG1_BUT_NOT_TAG2) -> bool:
    """
    Checks title for banned tags (case-insensitive) from keywordlist
    returns True if a banned tag is found.
    Also returns True if one of the first tags in the tag-combos
    in tag1_but_not_2 is contained but the second isnt.

    Example:    tag1:"[f4f" tag2:"4m]"
                title: "[F4F][F4M] For both male and female listeners.." -> return False
                title: "[F4F] For female listeners.." -> return True

    :param title: title string
    :param keywordlist: banned keywords/tags
    :param tag1_but_not_2: List of 2-tuples, first tag(str) is only banned if
                           second isn't contained
    :return: True if title contains banned tag
    """
    if not config.config.getboolean('Settings', 'check_banned_tags', fallback=True):
        return False

    title = title.lower()
    for keyword in keywordlist:
        if keyword in title:
            logger.warning(f"Banned keyword '{keyword}' in: {title}")
            return True

    if tag1_but_not_2:
        for tag_b, tag_in in tag1_but_not_2:
            # tag_b is only banned if tag_in isnt found in subtitle
            if (tag_b in title) and not (tag_in in title):
                logger.warning(
                        f"Banned keyword: no '{tag_in}' in title where '{tag_b}' is in: {title}")
                return True
    return False
