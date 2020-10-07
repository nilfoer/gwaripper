import re

import bs4

from typing import Optional

from .base import BaseExtractor
from ..info import FileInfo, FileCollection
from ..exceptions import InfoExtractingError


class SoundgasmExtractor(BaseExtractor):
    EXTRACTOR_NAME = "Soundgasm"
    BASE_URL = "soundgasm.net"

    # grp1: sgasm username, grp2: title
    VALID_SGASM_FILE_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?soundgasm\.net/(?:u|user)/"
                                         r"([-A-Za-z0-9_]+)/([-A-Za-z0-9_]+)/?",
                                         re.IGNORECASE)
    VALID_SGASM_USER_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?soundgasm\.net/(?:u|user)/"
                                         r"([-A-Za-z0-9_]+)/?",
                                         re.IGNORECASE)

    def __init__(self, url):
        super().__init__(url)

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_SGASM_FILE_URL_RE.match(url) or
                    cls.VALID_SGASM_USER_URL_RE.match(url))

    def extract(self) -> Optional[FileInfo]:
        match = SoundgasmExtractor.VALID_SGASM_FILE_URL_RE.match(self.url)
        if not match:
            match = SoundgasmExtractor.VALID_SGASM_USER_URL_RE.match(self.url)
            self.author = match.group(1)
            return self._extract_user()
        else:
            self.author = match.group(1)
            return self._extract_file()

    def _extract_file(self) -> Optional[FileInfo]:
        html = SoundgasmExtractor.get_html(self.url)
        soup = bs4.BeautifulSoup(html, "html.parser")

        try:
            title = soup.select_one("div.jp-title").text
            direct_url = re.search("m4a: \"(.+)\"", html).group(1)
            descr = soup.select_one("div.jp-description > p").text

            return FileInfo(self.__class__, True, "m4a", self.url,
                            direct_url, None, title, descr, self.author)
        except AttributeError:
            raise InfoExtractingError("Error occured while extracting sgasm info - site structure "
                                      "probably changed! See if there are updates available!",
                                      self.url, html)

    # @Refactor should an extractor just return a FileCollection with a list of urls
    # or should it resolve all these links and include a list of FileInfo_s?
    def _extract_user(self) -> Optional[FileCollection]:
        """
        Gets all the links to soundgasm.net posts of the user/at user url and returns
        them in a list

         Use bs4 to select all <a> tags directly beneath <div> with class sound-details
         Writes content of href attributes of found tags to list and return it
        """
        html = SoundgasmExtractor.get_html(self.url)
        soup = bs4.BeautifulSoup(html, 'html.parser')

        # decision for bs4 vs regex -> more safe and speed loss prob not significant
        # splits: 874 µs per loop; regex: 1.49 ms per loop; bs4: 84.3 ms per loop
        anchs = soup.select("div.sound-details > a")
        user_files = [a["href"] for a in anchs]

        fcol = FileCollection(self.url, self.author, self.author)
        for url in user_files:
            fi = SoundgasmExtractor(url).extract()
            if fi is None:
                continue
            fi.parent = fcol
            fcol.children.append(fi)

        return fcol
