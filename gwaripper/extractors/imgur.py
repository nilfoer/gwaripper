import logging
import re
import json

from typing import (
        Optional, ClassVar, Match, Pattern, cast, Dict, Any, List,
        Union
        )

from ..config import config
from ..exceptions import NoAPIResponseError, NoAuthenticationError, InfoExtractingError

from .base import BaseExtractor
from ..info import FileInfo, FileCollection

logger = logging.getLogger(__name__)

client_id: Optional[str] = config["Imgur"]["client_id"]
if client_id and client_id.startswith("to get a client id"):
    client_id = None


class ImgurImageExtractor(BaseExtractor):
    """Only using this as proxy for ImgurFile when url isnt a direct link to the
    image file but to the image page"""

    EXTRACTOR_NAME: ClassVar[str] = "ImgurImage"
    BASE_URL: ClassVar[str] = "imgur.com"

    IMAGE_FILE_URL_RE: ClassVar[Pattern] = re.compile(
            r"(?:https?://)?i\.imgur\.com/(\w{5,7})\.(\w+)")
    IMAGE_URL_RE: ClassVar[Pattern] = re.compile(
            r"^(?:https?://)?(?:www\.|m\.)?imgur\.com/(\w{5,7})$")

    IMAGE_FILE_URL_FORMAT: ClassVar[str] = "https://i.imgur.com/{image_hash}.{extension}"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0',
        'Authorization': f'Client-ID {client_id}',
        }

    def __init__(self, url: str):
        super().__init__(url)
        if not client_id:
            raise NoAuthenticationError("In order to download imgur images a Client ID "
                                        "is needed!")
        match = self.IMAGE_URL_RE.match(url)
        self.direct_url: Optional[str] = None
        self.ext: Optional[str] = None
        self.is_direct: bool = False
        if not match:
            # since one regex matched before in is_compatible
            match = cast(Match, self.IMAGE_FILE_URL_RE.match(url))
            self.is_direct = True
            self.ext = match.group(2)
            self.url = f"https://imgur.com/{match.group(1)}"
            self.direct_url = url
        self.image_hash = match.group(1)
        self.api_url: str = f"https://api.imgur.com/3/image/{self.image_hash}"
        self.api_response: Optional[Dict[str, Any]] = None

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.IMAGE_FILE_URL_RE.match(url) or cls.IMAGE_URL_RE.match(url))

    def extract(self) -> Optional[FileInfo]:
        # TODO: get image title etc. (for direct link as well using hash)
        direct_url = self.direct_url
        if not self.is_direct:
            resp = ImgurImageExtractor.get_html(self.api_url)
            self.api_response = json.loads(resp) if resp else None
            if self.api_response:
                try:
                    direct_url = self.api_response["data"]["link"]
                except KeyError:
                    raise InfoExtractingError(
                            "Error occured while extracting ImgurImage info - imgur API "
                            "probably changed! See if there are updates available!",
                            self.url, None)
                self.ext = direct_url.rsplit('.', 1)[1]  # type: ignore
            else:
                raise NoAPIResponseError("No Response recieved", self.api_url)

        return FileInfo(self.__class__, False, cast(str, self.ext), self.url,
                        cast(str, direct_url), self.image_hash, self.image_hash, None, None)


class ImgurAlbumExtractor(BaseExtractor):

    ALBUM_URL_RE = re.compile(r"(?:https?://)?(?:www\.|m\.)?imgur\.com/(?:a|gallery)/(\w{5,7})")

    EXTRACTOR_NAME: ClassVar[str] = "ImgurAlbum"
    BASE_URL: ClassVar[str] = "imgur.com"

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0',
        'Authorization': f'Client-ID {client_id}',
        }

    def __init__(self, url: str, mp4_always: bool = True):
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
        self.images: List[ImgurImageExtractor] = []

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return bool(cls.ALBUM_URL_RE.match(url))

    def get_album_title(self) -> str:
        if self.title is None and self.api_response:
            self.title = self.api_response["data"]["title"]
        return cast(str, self.title)

    def _get_single_images(self):
        if self.api_response:
            images: List[str] = self.api_response["data"]["images"]
        else:
            logger.warning("No data recieved when getting images for ImgurAlbum %s",
                           self.album_hash)
            return
        for img in images:
            furl = None
            if img["animated"]:
                # TODO handle mp4_always being False
                furl = img["mp4"]
            else:
                furl = img["link"]

            img_e = ImgurImageExtractor(furl)
            self.images.append(img_e)

    def _fetch_api_response(self):
        api_response = ImgurAlbumExtractor.get_html(self.api_url)
        if not api_response:
            raise NoAPIResponseError("No Response recieved", self.api_url)
        self.api_response = json.loads(api_response)
        self.image_count = int(self.api_response["data"]["images_count"])
        self.get_album_title()

    def extract(self) -> Optional[FileCollection]:
        if not self.api_response:
            self._fetch_api_response()

        self._get_single_images()
        if not self.images:
            logger.warning("No images in album: %s", self.album_hash)
            return None

        fcol = FileCollection(self.__class__, self.url, self.album_hash,
                              self.title if self.title else self.album_hash,
                              None)

        file_infos: List[Union[FileInfo, FileCollection]] = []
        for img_e in self.images:
            # try if ImgurImage is broken then so is probably ImgurAlbum
            # so we don't except here
            fi = img_e.extract()
            if fi is None:
                continue
            fi.parent = fcol
            file_infos.append(fi)
        fcol.children = file_infos

        return fcol
