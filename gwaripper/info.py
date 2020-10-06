import os

from enum import Enum


class FileCategory(Enum):
    UNKNOWN = 0
    AUDIO = 1
    IMAGE = 2


class FileInfo:
    def __init__(self, extractor, file_cat, ext, page_url, direct_url, _id, title,
                 descr, author, parent=None):
        self.extractor = extractor
        self.file_cat = file_cat
        self.ext = ext
        self.page_url = page_url
        self.direct_url = direct_url
        self.id = _id
        self.title = title
        self.descr = descr
        self.author = author
        self.parent = parent


class FileCollection:
    def __init__(self, url, _id, title, children=None):
        self.url = url
        self.id = _id
        self.title = title
        if self.children is None:
            children = []
        self.children = children


class RedditInfo(FileCollection):
    def __init__(self, url, _id, title, children=None):
        super().__init__(url, _id, title, children=children)

    def write_selftext_file(self, dl_root):
        """
        Write selftext to a text file if not None, reddit_info must not be None!!
        Doesnt overwrite already existing selftext file!

        :param dl_root: Path of root directory where all downloads are saved to (in username folders)
        :return: None
        """
        if self.reddit_info["selftext"]:
            # write_to_txtf uses append mode, but we'd have the selftext several
            # times in the file since there are reddit posts with multiple sgasm files
            mypath = os.path.join(dl_root, self.name_usr)
            os.makedirs(mypath, exist_ok=True)

            if not os.path.isfile(os.path.join(mypath, self.filename_local + ".txt")):
                with open(os.path.join(mypath, self.filename_local + ".txt"),
                          "w", encoding="UTF-8") as w:
                    w.write("Title: {}\nPermalink: {}\nSelftext:\n\n{}".format(
                        self.reddit_info["title"],
                        self.reddit_info["permalink"],
                        self.reddit_info["selftext"]))
