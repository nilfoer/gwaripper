import re
import logging
import urllib3
import urllib.parse

import bs4

from typing import Optional, cast, Pattern, Match, ClassVar, List, Tuple, Type, TypeVar, Any, Final

from .base import BaseExtractor, ExtractorErrorCode, ExtractorReport, title_has_banned_tag
from .soundgasm import SoundgasmUserExtractor
from ..exceptions import InfoExtractingError
from ..info import FileInfo, FileCollection
from .reddit import RedditExtractor

logger = logging.getLogger(__name__)

class SkittykatExtractor(BaseExtractor):
    # these need to be re-defined by sub-classes!!
    EXTRACTOR_NAME: ClassVar[str] = "Skittkat"
    BASE_URL: ClassVar[str] = "skittykat.cc"

    SKITTYKAT_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.)?skittykat\.cc/"
            r"(gonewildaudio|patreon|[-A-Za-z0-9]+)/([-A-Za-z0-9]+)/?$", re.IGNORECASE)
    AUDIO_FN_RE: ClassVar[Pattern] = re.compile(r"/([^?/]+)(?:\?.+)$", re.IGNORECASE)

    author: Final[str] = 'skitty-gwa'

    def __init__(self, url: str, init_from: Optional[Any] = None):
        super().__init__(url)
        match = cast(Match, SkittykatExtractor.SKITTYKAT_URL_RE.match(url))
        # gonewildaudio or patreon usually
        self.content_category: str = match.group(1)
        self.id: str = match.group(2)

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(SkittykatExtractor.SKITTYKAT_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional[FileCollection],
                                ExtractorReport]:
        # @Hack needed since we directly parse and extract found links in the submission
        # but can't import at module level (absolute import also doesn't work since it's
        # the __init__ we're trying to import and that _creates_ the package) because it
        # would lead to circular ref
        from . import find_extractor

        html, http_code = self.get_html(self.url)
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

        title_el = soup.select_one('h1.entry-title, h2.elementor-heading-title')
        title: str
        if title_el:
            title = title_el.text.strip()
        else:
            # when there's no proper headlline to use as title use website title
            title = soup.select_one("head title").text.strip().replace(" – SkittyKat", "")

        if title_has_banned_tag(title):
            return None, ExtractorReport(self.url, ExtractorErrorCode.BANNED_TAG)
        
        report = ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS)
        # TODO: add a description to FileCollection
        # NOTE: hard-coded author 'skitty-gwa'
        fc = FileCollection(SkittykatExtractor, self.url, self.id, title, self.author)


        # NOTE: strategy for now is:
        # 1. check if there is a reddit link on the sidebar (which normally links to the
        #    corresponding reddit submission) and if it has valid audio links
        # 2. gather all other sidebar links
        # 3. then we look if we have embedded audios that are hosted directly on the site
        # 4. then we search for (additional) links in the description, but it might contain
        #    the main links if all other options did not succeed

        # NOTE: using a[href] or button-link[href] does not work even though it works in
        # the browser console
        extern_links_selector = soup.select(
                '.elementor-top-column .elementor-element.elementor-widget-button '
                'a.elementor-button-link')
        # bool determines whether links came from sidebar next to the description
        found_links: List[Tuple[str, str, bool]] = []

        has_valid_reddit = False
        for lnk in extern_links_selector:
            url = lnk['href']
            # 1. if there's an external reddit link on the sidebar, this will have
            # unless deleted all the same content and is prob more permanent?/convenient
            # so try that one first
            if RedditExtractor.is_compatible(url):
                ri, reddit_report = RedditExtractor(url).extract(url, parent=fc, parent_report=report)
                if reddit_report.err_code == ExtractorErrorCode.NO_ERRORS:
                    # set reddit info on this fc if there are no errors
                    # TODO can only be set on FileInfo should we do this once we collected all links?
                    pass
            else:
                # 2. otherwise gather them
                found_links.append((url, lnk.get_text(strip=True), True))

        description = soup.select('.elementor-column .elementor-element .textwidget, '
                                  '.elementor-column .elementor-element .elementor-widget-text-editor')
        descr_text = "\n".join(text_widget.get_text(strip=True) for text_widget in description)

        # 3. look for embedded audios
        audio_embed_containers = soup.select('.elementor-element .elementor-widget-wp-widget-media_audio')
        for container in audio_embed_containers:
            audio = container.select_one('audio source')
            audio_url = audio['src']
            # we need to use the escaped path of the url for downloading otherwise
            # run into encoding issues with the url
            url_parsed = urllib.parse.urlparse(audio_url)
            # ^ NamedTuple, _replace() will return new obj with changed attr
            url_parsed = url_parsed._replace(path=urllib.parse.quote(url_parsed.path))
            escaped_audio_url = url_parsed.geturl()

            # replace \u200b zero-width space for filename
            match = self.AUDIO_FN_RE.search(audio_url.replace('\u200b', ''))
            audio_fn = urllib.parse.unquote(cast(Match, match).group(1))
            base_fn, ext = audio_fn.rsplit('.', 1)

            heading_el = container.select_one('h1, h2, h3, h4, h5, h6')
            audio_title: str
            if heading_el is not None:
                heading = heading_el.get_text(strip=True)
                audio_title = heading
                if title_has_banned_tag(heading):
                    report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
                    report.children.append(
                            ExtractorReport(audio_url, ExtractorErrorCode.BANNED_TAG))
                    continue
            else:
                audio_title = title

            # NOTE: @CleanUp need to use audio_url as page url here as well
            # IF we have more than one audio on the page, since we
            # use it to check if the file has been downloaded before and this would
            # give wrong results, since here multiple files can be on the same page
            fi_page_url = audio_url if len(audio_embed_containers) > 1 else self.url
            fi = FileInfo(self.__class__, is_audio=True, ext=ext, page_url=fi_page_url,
                          direct_url=escaped_audio_url, title=audio_title, _id = None,
                          descr=descr_text, author=self.author, parent=fc)
            fi_report = ExtractorReport(audio_url, ExtractorErrorCode.NO_ERRORS)
            # add to FileCollection
            fc.add_file(fi)
            report.children.append(fi_report)

        # since there can be multiple text widgets we need to gather the links in all of them first
        for text_widget in description:
            found_links.extend(
                    (lnk['href'], lnk.get_text(strip=True), False)
                    for lnk in text_widget.select('a[href]'))

        # 4. search for (additional) links or the main links inside the description
        for url, anchor_title, from_sidebar in found_links:
            extr = find_extractor(url)
            if extr is not None:
                logger.info("%s link found in description: %s",
                            extr.EXTRACTOR_NAME, url)
                # TODO skipping "recursive" FileCollections should be handled in gwaripper.py
                # NOTE: @Hack checking extractor types directly
                # NOTE: also not recursing into reddit links in the description, since they
                #       usually are only related submissions but not the main submission itself
                if extr is type(self) or extr is SoundgasmUserExtractor or extr is RedditExtractor:
                    # disallow following refs into other reddit submissions
                    logger.warning("Skipped supported %s url(%s), since it might lead to"
                                   "downloading a lot of unwanted audios!",
                                   cast(BaseExtractor, extr).EXTRACTOR_NAME, url)
                    # NOTE: we don't change the error code of the parent here, this is not
                    # technically regarded as an error
                    report.children.append(
                            ExtractorReport(url, ExtractorErrorCode.STOP_RECURSION))
                    continue

                if anchor_title and title_has_banned_tag(anchor_title):
                    report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
                    report.children.append(
                            ExtractorReport(url, ExtractorErrorCode.BANNED_TAG))
                    continue

                # TODO: refactor so filecollections don't extract the links
                # themselves immediately
                _, _ = extr.extract(url, parent=fc, parent_report=report)
            elif BaseExtractor.is_unsupported_audio_url(url):
                logger.warning("Found unsupported audio link '%s' at '%s'", url, self.url)
                report.err_code = ExtractorErrorCode.ERROR_IN_CHILDREN
                report.children.append(
                        ExtractorReport(url, ExtractorErrorCode.NO_EXTRACTOR))

        return fc, report



