import re

import bs4

from typing import Optional, Union, cast, Match, ClassVar, Pattern, Tuple, Any

from .base import BaseExtractor, ExtractorReport, ExtractorErrorCode, title_has_banned_tag
from ..info import FileInfo, FileCollection
from ..exceptions import InfoExtractingError


class SoundgasmExtractor(BaseExtractor):
    EXTRACTOR_NAME: ClassVar[str] = "Soundgasm"
    BASE_URL: ClassVar[str] = "soundgasm.net"

    # grp1: sgasm username, grp2: title
    VALID_SGASM_FILE_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?(?:www\.)?soundgasm\.net/(?:u|user)/"
            r"([-A-Za-z0-9_]+)/([-A-Za-z0-9_]+)/?",
            re.IGNORECASE)
    VALID_SGASM_USER_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?(?:www\.)?soundgasm\.net/(?:u|user)/([-A-Za-z0-9_]+)/?",
            re.IGNORECASE)

    author: str

    # NOTE: dont use init_from unless you change base class to BaseExtractor[type of init_from]
    def __init__(self, url: str, init_from: Optional[Any] = None):
        super().__init__(url)
        self.is_user: bool = False
        try:
            # one of them has to match since they matched before in is_compatible
            self.author = cast(Match, SoundgasmExtractor.VALID_SGASM_FILE_URL_RE.match(
                self.url)).group(1)
        except AttributeError:
            self.author = cast(Match, SoundgasmExtractor.VALID_SGASM_USER_URL_RE.match(
                self.url)).group(1)
            self.is_user = True

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_SGASM_FILE_URL_RE.match(url) or
                    cls.VALID_SGASM_USER_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional[Union[FileInfo, FileCollection]],
                                ExtractorReport]:
        if self.is_user:
            return self._extract_user()
        else:
            return self._extract_file()

    def _extract_file(self) -> Tuple[Optional[FileInfo], ExtractorReport]:
        html, http_code = SoundgasmExtractor.get_html(self.url)
        if not html:
            if self.http_code_is_extractor_broken(http_code):
                if self.is_user:
                    msg = ("Retrieving HTML failed! Extracting links from "
                           "soundgasm.net users is probably broken!")
                else:
                    # we did not modify passed in url
                    msg = ("Retrieving HTML failed! The passed in URL "
                           "was wrong and the extractor should not have matched it "
                           "or the site changed and the extractor is broken!")
                raise InfoExtractingError(msg, self.url)
            else:
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        soup = bs4.BeautifulSoup(html, "html.parser")

        title = soup.select_one("div.jp-title").text
        if title_has_banned_tag(title):
            return None, ExtractorReport(self.url, ExtractorErrorCode.BANNED_TAG)

        direct_url = cast(Match, re.search("m4a: \"(.+)\"", html)).group(1)
        ext = direct_url.rsplit('.', 1)[1]
        descr = soup.select_one("div.jp-description > p").text

        return (FileInfo(self.__class__, True, ext, self.url,
                         # use cast supress type checker warning, since we just assume it's
                         # a str and not None because otherwise we would've gotten an Exception
                         # NOTE: cast actually doesn't perform any runtime checks it's
                         # just there to help the type checker
                         cast(str, direct_url), None, title, descr, self.author),
                ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS))

    # @Refactor should an extractor just return a FileCollection with a list of urls
    # or should it resolve all these links and include a list of FileInfo_s?
    def _extract_user(self) -> Tuple[Optional[FileCollection],
                                     ExtractorReport]:
        """
        Gets all the links to soundgasm.net posts of the user/at user url and returns
        them in a list

         Use bs4 to select all <a> tags directly beneath <div> with class sound-details
         Writes content of href attributes of found tags to list and return it
        """
        html, http_code = SoundgasmExtractor.get_html(self.url)
        if not html:
            if self.http_code_is_extractor_broken(http_code):
                # we did not modify passed in url
                msg = ("Retrieving HTML failed! Either the passed in URL "
                       "was wrong and the extractor should not have matched it "
                       "or the site changed and the extractor is broken!")
                raise InfoExtractingError(msg, self.url)
            else:
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        soup = bs4.BeautifulSoup(html, 'html.parser')

        # decision for bs4 vs regex -> more safe and speed loss prob not significant
        # splits: 874 µs per loop; regex: 1.49 ms per loop; bs4: 84.3 ms per loop
        anchs = soup.select("div.sound-details > a")
        user_files = [a["href"] for a in anchs]

        report = ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS)
        fcol = FileCollection(self.__class__, self.url, self.author, self.author, self.author)
        for url in user_files:
            fi, extr_report = SoundgasmExtractor.extract(url, parent=fcol,
                                                         parent_report=report)

        return fcol, report
