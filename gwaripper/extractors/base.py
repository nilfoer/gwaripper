import urllib.request
import urllib.error
import logging

from typing import Optional, Dict, Union, ClassVar

from ..info import FileInfo, FileCollection

logger = logging.getLogger(__name__)


class BaseExtractor:
    """Custom extractors for different sites should inherit from this class
    and implement the required methods

    is_compatible is called with the url to find an appropriate extractor

    extract is the main method that gets called on a suitable extractor, it
    is expected to return an instance of Info or of a subclass"""

    headers: ClassVar[Dict[str, str]] = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    # these need to be re-defined by sub-classes!!
    EXTRACTOR_NAME: ClassVar[str] = "Base"
    EXTRACTOR_ID: ClassVar[int] = 0
    BASE_URL: ClassVar[str] = ""

    def __init__(self, url: str):
        # TODO: replace http with https by default?
        self.url = url

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        raise NotImplementedError

    def extract(self) -> Optional[Union[FileInfo, FileCollection]]:
        raise NotImplementedError

    @classmethod
    def get_html(cls, url: str,
                 additional_headers: Optional[Dict[str, str]] = None) -> Optional[str]:
        res: Optional[str] = None

        req = urllib.request.Request(url, headers=cls.headers)
        if additional_headers is not None:
            for k, v in additional_headers.items():
                req.add_header(k, v)

        try:
            site = urllib.request.urlopen(req)
        except urllib.error.HTTPError as err:
            logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
        else:
            # leave the decoding up to bs4
            response = site.read()
            site.close()

            # try to read encoding from headers otherwise use utf-8 as fallback
            encoding = site.headers.get_content_charset()
            res = response.decode(encoding.lower() if encoding else "utf-8")
            logger.debug("Getting html done!")

        return res
