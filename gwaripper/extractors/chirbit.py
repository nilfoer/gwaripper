import re
import base64

import bs4

from typing import Optional, ClassVar, Pattern, Match, cast, Tuple, Any

from .base import BaseExtractor, ExtractorErrorCode, ExtractorReport
from ..info import FileInfo
from ..exceptions import InfoExtractingError


class ChirbitExtractor(BaseExtractor):

    EXTRACTOR_NAME: ClassVar[str] = "Chirbit"
    BASE_URL: ClassVar[str] = "chirb.it"

    VALID_CHIRBIT_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.)?chirb\.it/([A-Za-z0-9]+)/?$", re.IGNORECASE)

    # NOTE: dont use init_from unless you change base class to BaseExtractor[type of init_from]
    def __init__(self, url: str, init_from: Optional[Any] = None):
        super().__init__(url)
        # already matched in is_compatible
        self.id: str = cast(Match, ChirbitExtractor.VALID_CHIRBIT_URL_RE.match(url)).group(1)

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_CHIRBIT_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional[FileInfo], ExtractorReport]:
        """
        Use bs4 to get a reversed base64 encoded string from <i> tag's data-fd attribute
        Reverse it with a slice and decode it with base64.b64decode
        """
        html, http_code = ChirbitExtractor.get_html(self.url)
        if not html:
            if self.http_code_is_extractor_broken(http_code):
                # we did not modify passed in url
                raise InfoExtractingError(
                        "Retrieving HTML failed! Either the passed in URL "
                        "was wrong and the extractor should not have matched it "
                        "or the site changed and the extractor is broken!",
                        self.url)
            else:
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        soup = bs4.BeautifulSoup(html, "html.parser")

        # selects ONE i tag with set data-fd attribute beneath tag with class .wavholder
        # beneath div with id main then get attribute data-fd
        # TypeError when trying to subscript soup.select_one but its None
        str_b64 = soup.select_one('div#main .wavholder i[data-fd]')["data-fd"]
        # reverse string using a slice -> string[start:stop:step], going through whole
        # string with step -1
        str_b64_rev = str_b64[::-1]
        # decode base64 string to get url to file -> returns byte literal -> decode with
        # appropriate encoding
        # this link EXPIRES so get it right b4 downloading
        direct_url = base64.b64decode(str_b64_rev).decode("utf-8")
        ext = direct_url.split("?")[0].rsplit(".", 1)[1]
        title = soup.select_one('div.chirbit-title').text
        author = soup.select_one('#chirbit-username').text

        return (FileInfo(self.__class__, True, ext, self.url,
                         direct_url, self.id, title, None, author),
                ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS))
