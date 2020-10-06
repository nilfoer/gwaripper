import re
import base64

import bs4

from .base import BaseExtractor
from ..info import FileInfo, FileCategory
from ..exceptions import InfoExtractingError


class ChirbitExtractor(BaseExtractor):

    EXTRACTOR_NAME = "Eraudica"
    BASE_URL = "eraudica.com"

    VALID_CHIRBIT_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?chirb\.it/"
                                      r"([A-Za-z0-9]+)", re.IGNORECASE)

    def __init__(self, url):
        super().__init__(url)

    @classmethod
    def is_compatible(cls, url):
        return cls.VALID_CHIRBIT_URL_RE.match(url)

    def extract(self):
        """
        Gets and sets the direct url for downloading the audio file on self.page_url, the file type and
        removes special chars from filename

        Use bs4 to get a reversed base64 encoded string from <i> tag's data-fd attribute
        Reverse it with a slice and decode it with base64.b64decode

        :return: None
        """
        html = ChirbitExtractor.get_html(self.url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        try:
            # selects ONE i tag with set data-fd attribute beneath tag with class .wavholder
            # beneath div with id main then get attribute data-fd
            # TypeError when trying to subscript soup.select_one but its None
            str_b64 = soup.select_one('div#main .wavholder i[data-fd]')["data-fd"]
            # reverse string using a slice -> string[start:stop:step], going through whole string with step -1
            str_b64_rev = str_b64[::-1]
            # decode base64 string to get url to file -> returns byte literal -> decode with
            # appropriate encoding
            # this link EXPIRES so get it right b4 downloading
            direct_url = base64.b64decode(str_b64_rev).decode("utf-8")
            ext = self.url_to_file.split("?")[0][-4:]
            title = self.reddit_info["title"]

            return FileInfo(self.__class__, FileCategory.AUDIO, ext, self.url,
                            direct_url, None, title, None, None)
        except (AttributeError, IndexError, TypeError):
            raise InfoExtractingError(
                    "Error occured while extracting chirbit info - site structure "
                    "probably changed! See if there are updates available!",
                    self.page_url, html)
