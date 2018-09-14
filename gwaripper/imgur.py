import os.path
import urllib.request
import logging
import re
import json

from .download import download

logger = logging.getLogger(__name__)

client_id = None
with open("imgur_cl_id.txt", "r", encoding="UTF-8") as f:
    client_id = f.read().strip()

# set user agent to use with urrlib
opener = urllib.request.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0')]
# ...and install it globally so it can be used with urlretrieve/open
urllib.request.install_opener(opener)

class ImgurFile:
    def __init__(self, parent, url, img_nr=None, prefix=None, postfix=None):
        self.parent = parent
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
        success, headers = download(self.file_url,
                                    os.path.join(self.parent.dest_path, self.filename))
        if not success:
            logger.warning("Download of '%s' failed!", self.file_url)
        else:
            self.downloaded = True


class ImgurAlbum:
    ALBUM_URL_RE = re.compile(r"(https?://)?(www\.|m\.)?imgur\.com/(a/|gallery/)?(\w{5,7})")

    def __init__(self, url, dest_path, mp4_always=True, name=None):
        self.album_url = url
        self.album_hash = re.search(self.ALBUM_URL_RE, url).group(4)
        self.dest_path = dest_path
        self.mp4_always = mp4_always
        self.images = []
        self.api_response = api_req_imgur(f"https://api.imgur.com/3/album/{self.album_hash}")
        self.name = None
        if name is None:
            self.get_album_title()
        else:
            self.name = name

    def get_album_title(self):
        if self.name is None:
            self.name = self.api_response["data"]["title"]
        return self.name

    def _get_single_images(self):
        images = self.api_response["data"]["images"]
        img_nr = 1
        for img in images:
            furl = None
            if img["animated"]:
                # TODO handle mp4_always being False
                furl = img["mp4"]
            else:
                furl = img["link"]

            if len(images) > 1:
                img_file = ImgurFile(self, furl, img_nr=f"{img_nr:03d}", prefix=self.name)
                img_nr += 1
            else:
                img_file = ImgurFile(self, furl, prefix=self.name)
            self.images.append(img_file)

    def download(self):
        self._get_single_images()
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

    return json.loads(content)
