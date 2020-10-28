import re
import base64

import bs4

from typing import Optional, ClassVar, Pattern, Match, cast

from .base import BaseExtractor
from ..info import FileInfo
from ..exceptions import InfoExtractingError


class ChirbitExtractor(BaseExtractor):

    EXTRACTOR_NAME: ClassVar[str] = "Chirbit"
    BASE_URL: ClassVar[str] = "chirb.it"

    VALID_CHIRBIT_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.)?chirb\.it/([A-Za-z0-9]+)/?$", re.IGNORECASE)

    def __init__(self, url: str):
        super().__init__(url)
        self.id: str = cast(Match, ChirbitExtractor.VALID_CHIRBIT_URL_RE.match(url)).group(1)

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_CHIRBIT_URL_RE.match(url))

    def extract(self) -> Optional[FileInfo]:
        """
        Use bs4 to get a reversed base64 encoded string from <i> tag's data-fd attribute
        Reverse it with a slice and decode it with base64.b64decode

        :return: FileInfo
        """
        html = ChirbitExtractor.get_html(self.url)
        if not html:
            return None

        soup = bs4.BeautifulSoup(html, "html.parser")

        try:
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

            return FileInfo(self.__class__, True, ext, self.url,
                            direct_url, self.id, title, None, author)
        except (AttributeError, IndexError, TypeError):
            raise InfoExtractingError(
                    "Error occured while extracting chirbit info - site structure "
                    "probably changed! See if there are updates available!",
                    self.url, html)
