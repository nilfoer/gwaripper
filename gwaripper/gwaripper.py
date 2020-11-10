#! python3
import logging
import os
import time
import datetime
import re
import urllib.request

import praw

from typing import List, Union, Optional, cast, Dict, ClassVar, Tuple

from . import utils
from . import config
from .extractors import find_extractor
from .extractors.base import ExtractorErrorCode, ExtractorReport
from .extractors.reddit import RedditExtractor
from .info import (
        FileInfo, FileCollection, RedditInfo, children_iter_dfs,
        UNKNOWN_USR_FOLDER
        )
from . import download as dl
from .reddit import reddit_praw
from .db import load_or_create_sql_db, export_csv_from_sql, backup_db

rqd = utils.RequestDelayer(0.25, 0.75)

# configure logging
# logfn = time.strftime("%Y-%m-%d.log")
# __name__ = 'gwaripper.gwaripper' -> logging of e.g. 'gwaripper.utils' (when
# callin getLogger with __name__
# in utils module) wont be considered a child of this logger
# we could use logging.config.fileConfig to configure our loggers (call it in
# main() for example, but with 'disable_existing_loggers': False, otherwise all loggers
# created by getLogger at module-level will be disabled)
# or we could configure our logging in __init__.py of our package (top-most
# level) with __name__ since that is just 'gwaripper' or we can configure our
# logger for the package by calling getLogger with 'gwaripper'
logger = logging.getLogger("gwaripper")
logger.setLevel(logging.DEBUG)

report_preamble = r"""
<style>
    body {
        background-color: whitesmoke;
    }
    .block:not(:last-child) {
        margin-bottom: .75rem;
    }
    .block:not(:last-child) + .collection {
        margin-top: 1.5rem;
    }
    div.indent {
        margin-left: 1.5rem;
    }
    a {
        font-size: 1.25rem;
    }
    .block .info, .collection .info {
        margin-top: .5rem;
        margin-bottom: .5rem;
    }
    .info span {
        padding: 2px;
        margin-right: 5px;
    }
    .success, .error {
        color: #fff;
        font-weight: bold;
    }
    .success {
        background-color: #14600d;
    }
    .error {
        background-color: #d70000;
    }
    .collection > span {
        font-size: 1.5rem;
        font-weight: bold;
    }
</style>
<h1>GWARipper report</h1>
<p>Collections will count as downloaded if all their children have been downloaded
   in this or any previous runs! Files on the other hand will only have the downloaded
   flag if they were downloaded _this_ run!</p><br/>
"""


class GWARipper:
    """
    Uses config.get_root() as base path for writing and reading files
    """

    headers: ClassVar[Dict[str, str]] = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    # we can only omit -> None if at least one arg is typed otherwise it is
    # considered an untyped method
    def __init__(self) -> None:
        self.db_con, _ = load_or_create_sql_db(
                os.path.join(config.get_root(), "gwarip_db.sqlite"))
        self.urls: List[str] = []
        self.nr_urls: int = 0
        self.extractor_reports: List[ExtractorReport] = []

    # return type needed otherwise we don't get type checking if used in with..as
    def __enter__(self) -> 'GWARipper':
        return self  # with GWARipper() as x <- x will be self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # If no exception occurred then these last 3 arguments will all be
        # None. If an exception occurred in the with block, then you can either
        # suppress the exception by returning a true value from this method. If
        # you don't want to suppress errors then you can return a value that
        # evaluates to False.
        export_csv_from_sql(os.path.join(config.get_root(), "gwarip_db_exp.csv"), self.db_con)
        self.db_con.close()

        # so download report will always be written even on KeyboardInterrupt
        if self.extractor_reports:
            self.write_report(self.extractor_reports)
            logger.info("Download report was written to folder _reports")

        # auto backup
        backup_db(os.path.join(config.get_root(), "gwarip_db.sqlite"),
                  os.path.join(config.get_root(), "_db-autobu"))
        return None

    def set_urls(self, urls: List[str]):
        # NOTE: deduplicates urls
        self.urls = list(set(urls))
        self.nr_urls = len(self.urls)

    def extract_and_download(self, url: str) -> None:
        extractor = find_extractor(url)
        if extractor is None:
            self.extractor_reports.append(
                    ExtractorReport(url, ExtractorErrorCode.NO_EXTRACTOR))
            logger.warning("Found no extractor for URL: %s", url)
            return None

        info, extr_report = extractor.extract(url)
        if info is None:
            self.extractor_reports.append(extr_report)
            return None

        self.download(info)
        self.extractor_reports.append(extr_report)

    def parse_and_download_submission(self, sub: praw.models.Submission,
                                      reddit_url: str = "https://www.reddit.com") -> None:
        url = f"{reddit_url}{sub.permalink}"
        # init_from not type-checked for Submission since praw doesn't have
        # type hints
        info, extr_report = RedditExtractor.extract(url, init_from=sub)
        if info is not None:
            self.download(info)
        self.extractor_reports.append(extr_report)

    def write_report(self, reports: List[ExtractorReport]):
        # parsing report!
        # since information is easy to miss when looking at just the log output
        #
        # not outputting html that would be considered 'correct'
        contents = [report_preamble]

        # dfs to traverse reports
        stack: List[Tuple[int, List[ExtractorReport]]] = []
        cur_list: List[ExtractorReport] = reports
        idx = 0
        level = 0
        while True:
            if idx >= len(cur_list):
                try:
                    idx, cur_list = stack.pop()
                except IndexError:
                    assert level == 0
                    break
                else:
                    contents.append('</div>')
                    level -= 1
                    continue

            report = cur_list[idx]
            is_collection = bool(report.children)
            success = True if report.err_code == ExtractorErrorCode.NO_ERRORS else False

            contents.append(
                f"<div class=\"{'collection ' if is_collection else 'block '}"
                f"{'indent ' if level else ''}\">")
            contents.append(
                f"{'<span>Collection: </span>' if is_collection else ''}<a href=\""
                f"{report.url}\">{report.url}</a>")
            contents.append(
                f"<div class='info'><span class='"
                f"{'success ' if success else 'error '}'>{report.err_code.name}"
                f"</span></div>")
            contents.append(
                f"<div class='info'><span class='"
                f"{'success ' if report.downloaded else 'error '}'>"
                f"{'DOWNLOADED' if report.downloaded else 'NOT DOWNLOADED'}</span></div>")
            if not is_collection:
                contents.append('</div>')

            idx += 1
            if is_collection:
                stack.append((idx, cur_list))
                cur_list = report.children
                level += 1
                idx = 0

        root_dir = config.get_root()
        dirname = os.path.join(root_dir, "_reports")
        fn = os.path.join(dirname, f"report_{time.strftime('%Y-%m-%dT%Hh%Mm')}.html")
        while True:
            try:
                with open(fn, 'w', encoding="UTF-8") as w:
                    w.write("\n".join(contents))
                    break
            except FileNotFoundError:
                os.makedirs(dirname)

    def download_all(self, sub_list: Optional[List[praw.models.Submission]] = None) -> None:
        if config.config.getboolean("Settings", "set_missing_reddit", fallback=False):
            logger.info("GWARipper will update already downloaded files with information "
                        "from reddit if they were previously downloaded from the site "
                        "directly. You can disable this in the settings")

        if sub_list is None:
            for idx, url in enumerate(self.urls):
                logger.info("Processing URL %d of %d: %s", idx + 1, self.nr_urls, url)
                self.extract_and_download(url)
        else:
            nr_subs = len(sub_list)
            idx = 1
            for sub in sub_list:
                logger.info("Processing submission %d of %d: %s", idx, nr_subs, sub.permalink)
                self.parse_and_download_submission(sub)

    def download(self, info: Union[FileInfo, FileCollection]):
        if isinstance(info, FileInfo):
            self._download_file(info, info.author)
        else:
            self._download_collection(info)

    def _pad_filename_if_exits(self, dirpath: str, filename: str, ext: str):
        filename_old = filename
        i = 1

        # file alrdy exists but it wasnt in the url database -> prob same titles
        # only one tag or the ending is different (since fname got cut off, so we
        # dont exceed win path limit)
        # count up i till file doesnt exist anymore
        # isfile works without checking if dir exists first
        while os.path.isfile(os.path.join(dirpath, f"{filename}.{ext}")):
            i += 1
            # :02d -> pad number with 0 to a width of 2, d -> digit(int)
            filename = f"{filename_old}_{i:02d}"
        if i > 1:
            logger.info("FILE ALREADY EXISTS - ADDED: _%02d", i)
        return filename

    def _download_file(self, info: FileInfo, author_name: Optional[str],
                       file_index: int = 0, dl_idx: int = 1, dl_max: int = 1) -> Optional[str]:
        """
        Will download the file to dl_root in a subfolder named like the reddit user name
        if that one is not available the extracted (from the page) author of the file gets
        used
        Calls info.generate_filename to get a valid filename
        Also calls method to add dl to db commits when download is successful, does a rollback
        when not (exception raised).

        :return subpath: Returns subpath to folder the file is located in relative to root_dir
        """
        # TODO re-add request delay?
        already_downloaded = self.already_downloaded(info)
        if already_downloaded:
            logger.info("File was already downloaded, skipped URL: %s", info.page_url)
            return None

        if not author_name:
            author_name = UNKNOWN_USR_FOLDER

        subpath, filename, ext = info.generate_filename(file_index)

        mypath = os.path.join(config.get_root(), author_name, subpath)
        os.makedirs(mypath, exist_ok=True)
        filename = self._pad_filename_if_exits(mypath, filename, ext)
        filename = f"{filename}.{ext}"

        logger.info("Downloading: %s..., File %d of %d", filename,
                    dl_idx, dl_max)

        # TODO retries etc. or use requests lib?
        try:
            if info.is_audio:
                # automatically commits changes to db_con if everything succeeds or does a rollback
                # if an exception is raised; exception is still raised and must be caught
                with self.db_con:
                    # executes the SQL query but leaves commiting it to with db_con in line above
                    self._add_to_db(info, author_name, os.path.join(subpath, filename))
                    # func passed as kwarg reporthook gets called once on establishment
                    # of the network connection and once after each block read thereafter.
                    # The hook will be passed three arguments; a count of blocks transferred
                    # so far, a block size in bytes, and the total size of the file
                    # total size is -1 if unknown
                    dl.download_in_chunks(info.direct_url,
                                          os.path.abspath(os.path.join(mypath, filename)),
                                          prog_bar=True)
            else:
                dl.download_in_chunks(info.direct_url,
                                      os.path.abspath(os.path.join(mypath, filename)),
                                      prog_bar=True)
        except urllib.error.HTTPError as err:
            logger.warning("HTTP Error %d: %s: \"%s\"", err.code, err.reason, info.direct_url)
        except urllib.error.ContentTooShortError as err:
            logger.warning(err.reason)
            logger.warning("File information was not added to DB! Reddit selftext might "
                           "not be written if this was the only file! "
                           "It's recommended to manually delete and re-download the file "
                           "using GWARipper!")
            if info.parent:
                logger.warning(
                        "Containging root collection: %s",
                        info.reddit_info.url if info.reddit_info is not None
                        else info.parent.url)
        except urllib.error.URLError as err:
            logger.error("URL Error for %s: %s\nExtractor %s is probably broken! "
                         "Please report this error on github!", info.direct_url,
                         str(err.reason).strip(), info.extractor)
        else:
            info.downloaded = True

        return subpath

    def _download_collection(self, info: FileCollection):
        logger.info("Starting download of collection: %s", info.url)

        # collection determines best author_name to use
        # priority is 1. reddit 2. file collection author 3. file author 4. fallbacks
        author_name = info.get_preferred_author_name()

        any_downloads = False
        files_in_collection = info.nr_files()
        with_file_idx = files_in_collection > 1
        dl_idx = 1
        # don't recurse into separate calls for nested FileCollections
        for rel_idx, fi in children_iter_dfs(info.children,
                                             file_info_only=True, relative_enum=True):
            # rel_idx is 0-based
            self._download_file(fi, author_name, (rel_idx + 1) if with_file_idx else 0,
                                dl_idx=dl_idx, dl_max=files_in_collection)
            any_downloads = any_downloads or fi.downloaded
            dl_idx += 1

        # TODO add status codes for downloads
        info.update_downloaded()

        if any_downloads:
            try:
                # :PassSubpathSelftext
                _, fi = next(children_iter_dfs(info.children, file_info_only=True))
                subpath, _, _ = fi.generate_filename()
                # assuming RedditInfo and excepting AttributeError
                cast(RedditInfo, info).write_selftext_file(
                        config.get_root(), os.path.join(author_name, subpath))
            except AttributeError:
                pass  # not redditinfo

    def _add_to_db(self, info: FileInfo, author_subdir: str, filename: str) -> None:
        """
        Adds instance attributes and reddit_info values to the database using named SQL query
        parameters with a dictionary.
        DOESN'T COMMIT the transaction, since the context manager in self.download() needs to be
        able to do a rollback if the dl fails

        :return: None
        """
        # create dict with keys that correspond to the named parameters in the SQL query
        # set vals contained in reddit_info to None(Python -> SQLITE: NULL)
        val_dict: Dict[str, Optional[str]] = {
            "date": time.strftime("%Y-%m-%d"),
            "time": time.strftime("%H:%M:%S"),
            "description": info.descr,
            "local_filename": filename,
            "title": info.title,
            "url_file": info.direct_url,
            "url": info.page_url,
            "author_page": info.author,
            # represents the preferred author name of the topmost parent or the
            # file's author and at the same time the subdirectory which the
            # local_filename is relative to
            "author_subdir": author_subdir,
            "created_utc": None,
            "r_post_url": None,
            "reddit_id": None,
            "reddit_title": None,
            "reddit_url": None,
            "reddit_user": None,
            "subreddit_name": None
        }

        if info.reddit_info:
            reddit_info = info.reddit_info
            val_dict.update({
                "created_utc":    str(reddit_info.created_utc),
                "r_post_url":     reddit_info.r_post_url,
                "reddit_id":      reddit_info.id,
                "reddit_title":   reddit_info.title,
                "reddit_url":     reddit_info.permalink,
                "reddit_user":    reddit_info.author,
                "subreddit_name": reddit_info.subreddit
            })

        self.db_con.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                            "title, url_file, url, created_utc, r_post_url, reddit_id, "
                            "reddit_title, reddit_url, reddit_user, author_page, "
                            " author_subdir, subreddit_name) "
                            " VALUES (:date, :time, :description, :local_filename, :title, "
                            ":url_file, :url, :created_utc, :r_post_url, :reddit_id, "
                            ":reddit_title, :reddit_url, :reddit_user, :author_page, "
                            ":author_subdir, :subreddit_name)", val_dict)

    def already_downloaded(self, info: FileInfo) -> bool:
        """
        Checks by querying for info.page_url and info.direct_url in DB if a file
        was downloaded before
        """
        # check both url and url_file since some rows only have the url_file set
        c = self.db_con.execute("SELECT url, url_file FROM Downloads WHERE url = ?"
                                "OR url_file = ?", (info.page_url, info.direct_url))
        duplicate = c.fetchone()

        if info.reddit_info and duplicate and config.config.getboolean(
                "Settings", "set_missing_reddit", fallback=False):
            self.set_missing_reddit_db(info, use_file_url=duplicate['url'] is None)

        if duplicate:
            info.already_downloaded = True
            return True
        else:
            info.already_downloaded = False
            return False

    def set_missing_reddit_db(self, info: FileInfo, use_file_url=False) -> None:
        """
        Updates row of file entry in db with reddit info, only sets values if previous
        entry was NULL/None
        """
        if not info.reddit_info:
            return

        # even though Row class can be accessed both by index (like tuples) and
        # case-insensitively by name
        # reset row_factory to default so we get normal tuples when fetching
        # (should we generate a new cursor)
        # new_c will always fetch Row obj and cursor will fetch tuples

        c = self.db_con.execute("SELECT * FROM Downloads WHERE "
                                f"{'url_file' if use_file_url else 'url'} = ?",
                                (info.direct_url if use_file_url else info.page_url,))
        row_cont = c.fetchone()

        set_helper = (("reddit_title", "title"), ("reddit_url", "permalink"),
                      ("reddit_user", "author"), ("created_utc", "created_utc"),
                      ("reddit_id", "id"), ("subreddit_name", "subreddit"),
                      ("r_post_url", "r_post_url"))

        upd_cols = []
        upd_vals = []
        for col, key in set_helper:
            if row_cont[col] is None:
                upd_cols.append("{} = ?".format(col))
                upd_vals.append(getattr(info.reddit_info, key, None))
        if use_file_url:
            upd_cols.append("url = ?")
            upd_vals.append(info.page_url)

        if upd_cols:
            logger.debug("Updating file entry with new info for: {}".format(", ".join(upd_cols)))
            # append url/_file since upd_vals need to include all the param substitutions for ?
            upd_vals.append(info.direct_url if use_file_url else info.page_url)
            # would work in SQLite version 3.15.0 (2016-10-14), but this is 3.8.11, users would
            # have to update as well so not a good idea
            # print("UPDATE Downloads SET ({}) = ({}) WHERE url_file = ?".format(
            #   ",".join(upd_cols), ",".join("?"*len(upd_cols))))

            with self.db_con:
                c.execute(f"UPDATE Downloads SET {','.join(upd_cols)} WHERE "
                          f"{'url_file' if use_file_url else 'url'} = ?", upd_vals)

        if not info.reddit_info.selftext:
            return

        filename_local = row_cont['local_filename']
        author_subdir = row_cont['author_subdir']

        # TODO due to my db having been used with older versions there are a lot of
        # rows where cols local_filename and url are empty -> gen a filename so we
        # can write the selftext
        if filename_local is None:
            filename_local = re.sub(
                    r"[^\w\-_.,\[\] ]", "_",
                    row_cont['title'][0:110]) + ".m4a"
        # intentionally don't write into subpath that might get used
        # by RedditInfo since this file was downloaded without it
        file_path = os.path.join(author_subdir, filename_local)
        info.reddit_info.write_selftext_file(
                config.get_root(), file_path, force_path=True)
