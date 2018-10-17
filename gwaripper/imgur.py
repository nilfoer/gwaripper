import os.path
import urllib.request
import logging
import re
import json

from .download import download

MODULE_PATH = os.path.dirname(os.path.realpath(__file__))

logger = logging.getLogger(__name__)

client_id = None
with open(os.path.join(MODULE_PATH, "imgur_cl_id.txt"), "r", encoding="UTF-8") as f:
    client_id = f.read().strip()

# set user agent to use with urrlib
opener = urllib.request.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0')]
# ...and install it globally so it can be used with urlretrieve/open
urllib.request.install_opener(opener)


class ImgurFile:
    IMAGE_FILE_URL_RE = re.compile(r"(https?://)?i\.imgur\.com/(\w{5,7})(\.\w+)")

    IMAGE_FILE_URL_FORMAT = "https://i.imgur.com/{image_hash}.{extension}"

    def __init__(self, parent, url, dest_path, img_nr=None, prefix=None, postfix=None):
        self.parent = parent
        self.dest_path = dest_path
        self.file_url = url
        self.orig_fn, self.ext = url.rsplit("/", 1)[1].rsplit(".", 1)
        self.img_nr = img_nr
        self.filename = self._build_name(prefix, postfix)
        self.downloaded = False

    def _build_name(self, prefix, postfix):
        fn = f"{prefix + '_' if prefix else ''}{self.img_nr + '_' if self.img_nr else ''}"
        fn = f"{fn}{self.orig_fn}{'_' + postfix if postfix else ''}.{self.ext}"
        return fn

    def download(self):
        logger.debug("Downloading imgur file %s as %s", self.file_url, self.filename)
        dl_path = os.path.join(self.dest_path, self.filename)
        # TODO overwrite inclomplete dls and rename if not the same file
        if os.path.isfile(dl_path):
            logger.warning("File '%s' already exists!", dl_path)
        else:
            success, headers = download(self.file_url, dl_path)
            if not success:
                logger.warning("Download of '%s' failed!", self.file_url)
            else:
                self.downloaded = True


class ImgurImage:
    """Only using this as proxy for ImgurFile when url isnt a direct link to the
    image file but to the image page"""

    IMAGE_URL_RE = re.compile(r"(https?://)?(www\.|m\.)?imgur\.com/(\w{5,7})")

    def __init__(self, url, dest_path, prefix=None, postfix=None):
        self.image_page = url
        self.dest_path = dest_path
        self.prefix = prefix
        self.postfix = postfix
        match = self.IMAGE_URL_RE.match(url)
        self.image_hash = match.group(3)
        self.api_response = api_req_imgur(f"https://api.imgur.com/3/image/{self.image_hash}")

    def download(self):
        if self.api_response:
            url = self.api_response["data"]["link"]
            f = ImgurFile(None, url, self.dest_path, prefix=self.prefix, postfix=self.postfix)
            f.download()
        else:
            logger.warning("Couldn't download ImgurImage no data recieved!")
            return


class ImgurAlbum:
    ALBUM_URL_RE = re.compile(r"(https?://)?(www\.|m\.)?imgur\.com/(a|gallery)/(\w{5,7})")

    def __init__(self, url, dest_path, mp4_always=True, name=None):
        self.album_url = url
        self.album_hash = re.search(self.ALBUM_URL_RE, url).group(4)
        self.dest_path = dest_path
        self.mp4_always = mp4_always
        self.images = []
        self.api_response = api_req_imgur(f"https://api.imgur.com/3/album/{self.album_hash}")
        self.image_count = self.api_response["data"]["images_count"]
        self.name = None
        if name is None:
            self.get_album_title()
        else:
            self.name = name
        # save in separate folder if more than 3 imgs
        if self.image_count > 3:
            self.dest_path = os.path.join(self.dest_path, self.name)

    def get_album_title(self):
        if self.name is None:
            self.name = re.sub("[^\w\-_.,\[\] ]", "_", self.api_response["data"]["title"][0:100])
        return self.name

    def _get_single_images(self):
        if self.api_response:
            images = self.api_response["data"]["images"]
        else:
            logger.warning("No data recieved when getting images for ImgurAlbum %s",
                           self.album_hash)
            return
        img_nr = 1
        for img in images:
            furl = None
            if img["animated"]:
                # TODO handle mp4_always being False
                furl = img["mp4"]
            else:
                furl = img["link"]

            if len(images) > 1:
                # add img count if more than one img
                # if more than 3 imgs save in sep folder -> no prefix
                img_file = ImgurFile(self, furl, self.dest_path, img_nr=f"{img_nr:03d}",
                                     prefix=self.name if self.image_count <= 3 else None)
                img_nr += 1
            else:
                img_file = ImgurFile(self, furl, self.dest_path,
                                     prefix=self.name if self.image_count <= 3 else None)
            self.images.append(img_file)

    def download(self):
        self._get_single_images()
        if not self.images:
            logger.warning("No images to download!")
            return
        logger.info("Downloading imgur Album with %d images to %s",
                    len(self.images), self.dest_path)
        for img in self.images:
            img.download()


def api_req_imgur(url):
    content = None
    req = urllib.request.Request(url)
    # add Authorization header otherwise we just get denied
    req.add_header("Authorization", f"Client-ID {client_id}")

    try:
        site = urllib.request.urlopen(req)
    except urllib.request.HTTPError as err:
        logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
    else:
        content = site.read().decode('utf-8')
        site.close()
        logger.debug("Getting html done!")

    return json.loads(content) if content else None
