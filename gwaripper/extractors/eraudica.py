import re

import bs4

from urllib.parse import quote as url_quote

from .base import BaseExtractor
from ..info import FileInfo, FileCategory
from ..exceptions import InfoExtractingError


class EraudicaExtractor(BaseExtractor):

    EXTRACTOR_NAME = "Eraudica"
    BASE_URL = "eraudica.com"

    VALID_ERAUDICA_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?eraudica\.com/e/eve/"
                                       r"(?:\d+)/([A-Za-z0-9-]+)", re.IGNORECASE)

    def __init__(self, url):
        super().__init__(url)

    @classmethod
    def is_compatible(cls, url):
        return cls.VALID_ERAUDICA_URL_RE.match(url)

    def extract(self):
        # strip("/gwa") doesnt strip the exact string "/gwa" from the end but instead it strips all
        # the chars contained in that string from the end:
        # "eve/Audio-extravaganza/gwa".strip("/gwa") ->  "eve/Audio-extravaganz"
        # use slice instead (replace might remove that string even if its not at the end)
        # remove /gwa from end of link so we can access file download
        if self.url.endswith("/gwa"):
            self.url = self.url[:-4]

            html = EraudicaExtractor.get_html(self.url)
            soup = bs4.BeautifulSoup(html, "html.parser")

            try:
                # selects script tags beneath div with id main and div class post
                # returns list of bs4.element.Tag -> access text with .text
                # get script on eraudica that contains ALL dl information (fn etc. theres also
                # one with just the file url
                scripts = [s.text for s in soup.select("div#main div.post script")
                           if "playerServerURLAuthorityIncludingScheme" in s.text][0]
                # vars that are needed to gen dl link are included in script tag
                # access group of RE (part in '()') with .group(index)
                # Group 0 is always present; it’s the whole RE
                fname = re.search("var filename = \"(.+)\"", scripts).group(1)
                server = re.search("var playerServerURLAuthorityIncludingScheme = \"(.+)\"",
                                   scripts).group(1)
                dl_token = re.search("var downloadToken = \"(.+)\"", scripts).group(1)
                # convert unicode escape sequences (\\u0027) that might be in the filename to str
                # fname.encode("utf-8").decode("unicode-escape")
                # bytes(fname, 'ascii').decode('unicode-escape')
                fname = fname.encode("utf-8").decode("unicode-escape")
                # convert fname to make it url safe with urllib.quote (quote_plus replaces spaces
                # with plus signs)
                fname = url_quote(fname)

                direct_url = "{}/fd/{}/{}".format(server, dl_token, fname)
                title = self.reddit_info["title"]
                ext = fname[-4:]

                # hardcoded author name
                return FileInfo(self.__class__, FileCategory.AUDIO, ext, self.url,
                                direct_url, None, title, None, "Eves-garden")
            except (IndexError, AttributeError):
                raise InfoExtractingError(
                        "Error occured while extracting eraudica info - site structure "
                        "probably changed! See if there are updates available!",
                        self.page_url, html)
