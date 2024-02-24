import re

import bs4

from typing import Optional, Match, cast, Pattern, ClassVar, Tuple, Any
from urllib.parse import quote as url_quote

from .base import BaseExtractor, ExtractorErrorCode, ExtractorReport
from gwaripper import info
from ..exceptions import InfoExtractingError


class EraudicaExtractor(BaseExtractor):

    EXTRACTOR_NAME: ClassVar[str] = "Eraudica"
    EXTRACTOR_ID: ClassVar[int] = 4
    BASE_URL: ClassVar[str] = "eraudica.com"

    VALID_ERAUDICA_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?(?:www\.)?eraudica\.com/e/eve/"
            r"(?:\d+)/([A-Za-z0-9-]+)", re.IGNORECASE)

    # NOTE: dont use init_from unless you change base class to BaseExtractor[type of init_from]
    def __init__(self, url: str, init_from: Optional[Any] = None):
        super().__init__(url)
        # strip("/gwa") doesnt strip the exact string "/gwa" from the end but instead it strips all
        # the chars contained in that string from the end:
        # "eve/Audio-extravaganza/gwa".strip("/gwa") ->  "eve/Audio-extravaganz"
        # use slice instead (replace might remove that string even if its not at the end)
        # remove /gwa from end of link so we can access file download
        if self.url.endswith("/gwa"):
            self.url = self.url[:-4]

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.VALID_ERAUDICA_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional['info.FileInfo'], ExtractorReport]:
        html, http_code = EraudicaExtractor.get_html(self.url)
        if not html:
            if self.http_code_is_extractor_broken(http_code):
                raise InfoExtractingError(
                        "Retrieving HTML failed! Either the site changed or "
                        "the modified URL is invalid. In either case the extractor "
                        "is broken!", self.url)
            else:
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        soup = bs4.BeautifulSoup(html, "html.parser")

        # selects script tags beneath div with id main and div class post
        # returns list of bs4.element.Tag -> access text with .text
        # get script on eraudica that contains ALL dl information (fn etc. theres also
        # one with just the file url
        scripts = [s.text for s in soup.select("div#main div.post script")
                   if "playerServerURLAuthorityIncludingScheme" in s.text][0]
        # vars that are needed to gen dl link are included in script tag
        # access group of RE (part in '()') with .group(index)
        # Group 0 is always present; it’s the whole RE
        # NOTE: ignore mypy errors with # type: ignore
        # since we except any AttributeError as an indication
        # that sth. went wrong during extraction and that is true here since re.search
        # will only result in an AttributeError if the site changed and our extraction
        # method doesn't work anymore (in another language i'd use ifs instead, but
        # this is more 'pythonic' and efficient since it will raise an Exception only in
        # the very rare case that the site changed, if a substantial proportion of
        # runs it would raise then ifs are actually alot faster)
        # cast is better form since it only applies to one specific expression
        fname = cast(Match, re.search("var filename = \"(.+)\"", scripts)).group(1)
        server = cast(Match, re.search("var playerServerURLAuthorityIncludingScheme = "
                                       "\"(.+)\"", scripts)).group(1)
        dl_token = cast(Match, re.search("var downloadToken = \"(.+)\"",
                                         scripts)).group(1)
        # convert unicode escape sequences (\\u0027) that might be in the filename to str
        # fname.encode("utf-8").decode("unicode-escape")
        # bytes(fname, 'ascii').decode('unicode-escape')
        fname = fname.encode("utf-8").decode("unicode-escape")
        # convert fname to make it url safe with urllib.quote (quote_plus replaces spaces
        # with plus signs)
        fname = url_quote(fname)

        direct_url = "{}/fd/{}/{}".format(server, dl_token, fname)
        title = cast(Match, re.search("var title = \"(.+)\";", scripts)).group(1)
        # mixes escaped (\\u..) with unescaped unicode
        # encode to bytes escaping unicode code points
        # already escaped sequences get esacped as \\\\u.. -> remove extra \\
        # and unescape back to unicode
        # NOTE: eraudica doesn't really use tags in the title so don't check for banned ones
        title = title.encode("unicode-escape").replace(
                    b'\\\\u', b'\\u').decode('unicode-escape')
        ext = fname.rsplit(".", 1)[1]

        # :not(.love-and-favorite-row) doesn't work with bs4
        descr = "\n\n".join([p.get_text() for p in soup.select('div.description > p')][1:])

        # hardcoded author name
        return (info.FileInfo(self.__class__, True, ext, self.url,
                         direct_url, None, title, descr, "Eves-garden"),
                ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS))
