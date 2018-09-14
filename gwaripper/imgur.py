import os.path
import urllib.request
import logging

import bs4

from download import download

logger = logging.getLogger(__name__)

# set user agent to use with urrlib
opener = urllib.request.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0')]
# ...and install it globally so it can be used with urlretrieve/open
urllib.request.install_opener(opener)

# TODO use imgur api instead of parsing html
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
        logger.debug("Downloading imgur file %s as %s", self.url, self.filename)
        success, headers = download(self.file_url,
                                    os.path.join(self.parent.dest_path, self.filename))
        if not success:
            logger.warning("Download of '%s' failed!", self.file_url)
        else:
            self.downloaded = True


class ImgurAlbum:
    def __init__(self, url, dest_path, name=None):
        self.album_url = url
        self.dest_path = dest_path
        self.images = []
        self.html = get_html(url)
        self.name = None
        if name is None:
            self.get_album_title()
        else:
            self.name = name

    def get_album_title(self):
        if self.name is None:
            soup = bs4.BeautifulSoup(self.html, "html.parser")
            self.name = soup.select_one(".post-title").text 
        return self.name

    def _extract_single_images(self):
        soup = bs4.BeautifulSoup(self.html, "html.parser")
        # div class="post-image" meta with attr itemprop='contentURL'
        img_meta = soup.select("div.post-image meta[itemprop='contentURL']")
        img_nr = 1
        for img in img_meta:
            # remove http/https first then only use https
            furl = "https:" + img["content"].replace("http:", "").replace("https:", "")
            if len(img_meta) > 1:
                img_file = ImgurFile(self, furl, img_nr=f"{img_nr:03d}", prefix=self.name)
                img_nr += 1
            else:
                img_file = ImgurFile(self, furl, prefix=self.name)
            self.images.append(img_file)

    def download(self):
        self._extract_single_images()
        logger.info("Downloading imgur Album with %d images to %s", 
                    len(self.images), self.dest_path)
        for img in self.images:
            img.download()


def get_html(url):
    html = None

    try:
        site = urllib.request.urlopen(url)
    except urllib.request.HTTPError as err:
        logger.warning("HTTP Error %s: %s: \"%s\"", err.code, err.reason, url)
    else:
        html = site.read().decode('utf-8')
        site.close()
        logger.debug("Getting html done!")

    return html

if __name__ == "__main__":
    a = ImgurAlbum("https://imgur.com/u4Ycj9z", "N:/_archive/test/")
    a.download()

