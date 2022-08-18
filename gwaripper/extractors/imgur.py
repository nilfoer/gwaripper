import logging
import re
import json

from typing import (
        Optional, ClassVar, Match, Pattern, cast, Dict, Any, List,
        Tuple
        )

from ..config import config
from ..exceptions import NoAPIResponseError, NoAuthenticationError

from .base import BaseExtractor, ExtractorReport, ExtractorErrorCode
from ..info import FileInfo, FileCollection

logger = logging.getLogger(__name__)

client_id: Optional[str] = config["Imgur"]["client_id"]
if client_id and client_id.startswith("to get a client id"):
    client_id = None


class ImgurImageExtractor(BaseExtractor[Dict[str, Any]]):
    """Only using this as proxy for ImgurFile when url isnt a direct link to the
    image file but to the image page"""

    EXTRACTOR_NAME: ClassVar[str] = "ImgurImage"
    BASE_URL: ClassVar[str] = "imgur.com"

    IMAGE_FILE_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?i\.imgur\.com/(\w{5,7})\.(\w+)")
    IMAGE_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.|m\.)?imgur\.com/(\w{5,7})(?:\?.*)?$")

    IMAGE_FILE_URL_FORMAT: ClassVar[str] = "https://i.imgur.com/{image_hash}.{extension}"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0',
        'Authorization': f'Client-ID {client_id}',
        }

    def __init__(self, url: str, init_from: Optional[Dict[str, Any]] = None):
        super().__init__(url)
        if not client_id:
            raise NoAuthenticationError("In order to download imgur images a Client ID "
                                        "is needed!")
        # NOTE: init_from is a imgur image dict retrieved from the imgur api
        if init_from is None:
            match = self.IMAGE_URL_RE.match(url)
            self.direct_url: Optional[str] = None
            self.ext: Optional[str] = None
            self.is_direct: bool = False
        else:
            match = None

        if not match:
            # since one regex matched before in is_compatible
            match = cast(Match, self.IMAGE_FILE_URL_RE.match(url))
            self.is_direct = True
            self.ext = match.group(2)
            self.url = f"https://imgur.com/{match.group(1)}"
            self.direct_url = url
        self.image_hash = match.group(1)
        self.api_url: str = f"https://api.imgur.com/3/image/{self.image_hash}"
        self.api_response: Optional[Dict[str, Any]] = init_from

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.IMAGE_FILE_URL_RE.match(url) or cls.IMAGE_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional[FileInfo], ExtractorReport]:
        # TODO: get image title etc. (for direct link as well using hash)
        direct_url = self.direct_url
        if not self.is_direct:
            resp, http_code = ImgurImageExtractor.get_html(self.api_url)

            if not resp:
                if self.http_code_is_extractor_broken(http_code):
                    raise NoAPIResponseError(
                            "API endpoint did not return a response! Imgur.com"
                            "probably changed their API!", self.api_url)
                else:
                    return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

            self.api_response = json.loads(resp)
            if self.api_response:
                direct_url = self.api_response["data"]["link"]
                self.ext = direct_url.rsplit('.', 1)[1]  # type: ignore

        return (FileInfo(self.__class__, False, cast(str, self.ext), self.url,
                         cast(str, direct_url), self.image_hash, self.image_hash, None, None),
                ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS))


class ImgurAlbumExtractor(BaseExtractor):

    ALBUM_URL_RE = re.compile(r"(?:https?://)?(?:www\.|m\.)?imgur\.com/(?:a|gallery)/(\w{5,7})")

    EXTRACTOR_NAME: ClassVar[str] = "ImgurAlbum"
    BASE_URL: ClassVar[str] = "imgur.com"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0',
        'Authorization': f'Client-ID {client_id}',
        }

    def __init__(self, url: str, init_from: Optional[Any] = None, mp4_always: bool = True):
        super().__init__(url)
        if not client_id:
            raise NoAuthenticationError("In order to download imgur images a Client ID "
                                        "is needed!")
        self.album_hash = cast(Match, self.ALBUM_URL_RE.match(url)).group(1)
        self.mp4_always = mp4_always
        self.api_url: str = f"https://api.imgur.com/3/album/{self.album_hash}"
        self.api_response: Optional[Dict[str, Any]] = None
        self.image_count: Optional[int] = None
        self.title: Optional[str] = None

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.ALBUM_URL_RE.match(url))

    def _extract(self) -> Tuple[Optional[FileCollection], ExtractorReport]:
        api_response, http_code = ImgurAlbumExtractor.get_html(self.api_url)

        if not api_response:
            if self.http_code_is_extractor_broken(http_code):
                raise NoAPIResponseError(
                        "API endpoint did not return a response! Imgur.com"
                        "probably changed their API!", self.api_url)
            else:
                return None, ExtractorReport(self.url, ExtractorErrorCode.NO_RESPONSE)

        self.api_response = json.loads(api_response)
        self.image_count = int(self.api_response["data"]["images_count"])  # type: ignore
        self.title = self.api_response["data"]["title"]  # type: ignore

        if not self.image_count:
            logger.warning("No images in album: %s", self.album_hash)
            return None, ExtractorReport(self.url, ExtractorErrorCode.EMPTY_COLLECTION)

        fcol = FileCollection(self.__class__, self.url, self.album_hash,
                              self.title if self.title else self.album_hash,
                              None)

        report = ExtractorReport(self.url, ExtractorErrorCode.NO_ERRORS)

        # contains image dicts directly so we don't need to use ImgurImageExtractor
        images: List[Dict[str, Any]] = cast(Dict[str, Any], self.api_response)["data"]["images"]

        for img in images:
            furl: str
            if img["animated"]:
                # TODO handle mp4_always being False
                furl = img["mp4"]
            else:
                furl = img["link"]

            # using ImgurImageExtractor directly since we got the img dicts
            # directly from the api and nothing should fail, if it does anyway
            # extract marks us as broken - as it should
            fi, extr_report = ImgurImageExtractor.extract(
                    furl, parent=fcol, parent_report=report, init_from=img)

        return fcol, report
