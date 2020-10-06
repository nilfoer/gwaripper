import os.path
import urllib.request
import logging
import re
import json

from ..config import config
from ..exceptions import NoAPIResponseError, NoAuthenticationError

from .base import BaseExtractor
from ..info import FileInfo, FileCategory, FileCollection

logger = logging.getLogger(__name__)

client_id = config["Imgur"]["client_id"]
if client_id.startswith("to get a client id"):
    client_id = None


class ImgurImageExtractor(BaseExtractor):
    """Only using this as proxy for ImgurFile when url isnt a direct link to the
    image file but to the image page"""

    EXTRACTOR_NAME = "ImgurImage"
    BASE_URL = "imgur.com"

    IMAGE_FILE_URL_RE = re.compile(r"(?:https?://)?i\.imgur\.com/(\w{5,7})\.(\w+)")
    IMAGE_URL_RE = re.compile(r"^(?:https?://)?(?:www\.|m\.)?imgur\.com/(\w{5,7})$")

    IMAGE_FILE_URL_FORMAT = "https://i.imgur.com/{image_hash}.{extension}"

    headers = BaseExtractor.headers.copy().update({"Authorization": f"Client-ID {client_id}"})

    def __init__(self, url):
        super().__init__(url)
        if not client_id:
            raise NoAuthenticationError("In order to download imgur images a Client ID "
                                        "is needed!")
        self.url = url
        self.api_url = f"https://api.imgur.com/3/image/{self.image_hash}"
        self.is_direct = False
        self.ext = None
        match = self.IMAGE_URL_RE.match(url)
        if not match:
            match = self.IMAGE_FILE_URL_RE.match(url)
            self.is_direct = True
            self.ext = match.group(2)
        self.image_hash = match.group(1)
        self.api_response = None

    @classmethod
    def is_compatible(cls, url: str) -> bool:
        return cls.IMAGE_FILE_URL_RE.match(url) or cls.IMAGE_URL_RE.match(url)

    def extract(self):
        direct_url = self.url
        if not self.is_direct:
            resp = ImgurImageExtractor.get_html(self.api_url)
            self.api_response = json.loads(resp) if resp else None
            if self.api_response:
                direct_url = self.api_response["data"]["link"]
            else:
                raise NoAPIResponseError("No Response recieved", self.api_url)

        return FileInfo(self.__class__, FileCategory.IMAGE, self.ext, self.url,
                        direct_url, self.image_hash, None, None, None)


class ImgurAlbumExtractor:

    ALBUM_URL_RE = re.compile(r"(?:https?://)?(?:www\.|m\.)?imgur\.com/(?:a|gallery)/(\w{5,7})")

    EXTRACTOR_NAME = "ImgurAlbum"
    BASE_URL = "imgur.com"

    headers = BaseExtractor.headers.copy().update({"Authorization": f"Client-ID {client_id}"})

    def __init__(self, url, dest_path, mp4_always=True, name=None):
        super().__init__(url)
        if not client_id:
            raise NoAuthenticationError("In order to download imgur images a Client ID "
                                        "is needed!")
        self.album_hash = self.ALBUM_URL_RE.match(url).group(1)
        self.mp4_always = mp4_always
        self.api_url = f"https://api.imgur.com/3/album/{self.album_hash}"
        self.api_response = ImgurAlbumExtractor.get_html(self.api_url)
        if not self.api_response:
            raise NoAPIResponseError("No Response recieved", self.api_url)
        self.image_count = self.api_response["data"]["images_count"]
        self.title = self.get_album_title()

    def get_album_title(self):
        if self.title is None:
            self.title = self.api_response["data"]["title"]
        return self.title

    def _get_single_images(self):
        if self.api_response:
            images = self.api_response["data"]["images"]
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

            img_e = ImgurImageExtractor(self, furl)
            self.images.append(img_e)

    def extract(self):
        self._get_single_images()
        if not self.images:
            logger.warning("No images in album: %s", self.album_hash)
            return

        fcol = FileCollection(self.url, self.album_hash, self.title)
        file_infos = []
        for img_e in self.images:
            fi = img_e.extract()
            fi.parent = fcol
            file_infos.append(fi)

        return fcol



