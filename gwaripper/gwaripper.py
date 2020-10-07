#! python3
import logging
import os
import time
import datetime
import re
import urllib.request

import praw

from typing import List, Union, Optional

from .logging_setup import configure_logging
from . import utils
from .config import config, ROOTDIR
from .extractors import find_extractor
from .extractors.soundgasm import SoundgasmExtractor
from .extractors.reddit import RedditExtractor
from .info import FileInfo, FileCollection, RedditInfo, children_iter_dfs, children_iter_bfs
from . import download as dl
from .reddit import reddit_praw
from .db import load_or_create_sql_db, export_csv_from_sql, backup_db
from .exceptions import InfoExtractingError

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

# only log to file if ROOTDIR is set up so we dont clutter the cwd or the module dir
if ROOTDIR and os.path.isdir(ROOTDIR):
    configure_logging(os.path.join(ROOTDIR, "gwaripper.log"))


class GWARipper:

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:12.0) Gecko/20100101 Firefox/12.0'
        }

    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.db_con, _ = load_or_create_sql_db(os.path.join(root_dir, "gwarip_db.sqlite"))
        self.downloads = []
        self.nr_downloads = 0
        self.download_index = 1

    def __enter__(self):
        return self  # with GWARipper() as x <- x will be self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # If no exception occurred then these last 3 arguments will all be
        # None. If an exception occurred in the with block, then you can either
        # suppress the exception by returning a true value from this method. If
        # you don't want to suppress errors then you can return a value that
        # evaluates to False.
        export_csv_from_sql(os.path.join(self.root_dir, "gwarip_db_exp.csv"), self.db_con)
        self.db_con.close()

        # auto backup
        backup_db(os.path.join(self.root_dir, "gwarip_db.sqlite"))
        return None

    def parse_links(self, links: List[str]) -> None:
        # NOTE: deduplicates links list
        dls = []
        for url in set(links):
            extractor = find_extractor(url)
            try:
                info = extractor(url).extract()
            except InfoExtractingError:
                logger.error("Extraction failed! Skipping URL: %s", url)
                continue
            if info is not None:
                dls.append(info)

        self.downloads.extend(dls)
        self.nr_downloads += sum(1 for _ in children_iter_dfs(
                                 dls, file_info_only=True))

    def parse_submissions(self, sublist: List[praw.models.Submission]) -> None:
        # NOTE: does not deduplicate sublist!!
        dls = []
        for sub in sublist:
            try:
                reddit = reddit_praw()
                url = f"{reddit.config.reddit_url}{sub.permalink}"
                info = RedditExtractor(url, sub).extract()
            except InfoExtractingError:
                logger.error("Extraction failed! Skipping URL: %s", url)
                continue
            if info is not None:
                dls.append(info)

        self.downloads.extend(dls)
        self.nr_downloads += sum(1 for _ in children_iter_dfs(
                                 dls, file_info_only=True))

    def download_all(self) -> None:
        # TODO mb to restrict to [self.download_index + 1: self.nr_downloads + 1]?
        for fi in self.downloads:
            self.download(fi)

    def download(self, info: Union[FileInfo, FileCollection]) -> None:
        if isinstance(info, FileInfo):
            self._download_file(info, info.author)
            rqd.delay_request()
        else:
            self._download_collection(info)

    def _pad_filename_if_exits(self, dirpath: str, filename: str, ext: str):
        filename_old = filename
        i = 0

        # file alrdy exists but it wasnt in the url database -> prob same titles
        # only one tag or the ending is different (since fname got cut off, so we
        # dont exceed win path limit)
        # count up i till file doesnt exist anymore
        # isfile works without checking if dir exists first
        while os.path.isfile(os.path.join(dirpath, f"{filename}.{ext}")):
            i += 1
            # :02d -> pad number with 0 to a width of 2, d -> digit(int)
            filename = f"{filename_old}_{i:02d}"
        if i:
            logger.info("FILE ALREADY EXISTS - ADDED: _%02d", i)
        return filename

    def _download_file(self, info: FileInfo, author_name: Optional[str],
                       file_index: int = 0) -> str:
        """
        Will download the file to dl_root in a subfolder named like the reddit user name
        if that one is not available the extracted (from the page) author of the file gets
        used
        Calls info.generate_filename to get a valid filename
        Also calls method to add dl to db commits when download is successful, does a rollback
        when not (exception raised).

        :return subpath: Returns subpath to folder file is located in relative to root_dir
        """
        if info.already_downloaded:
            logger.info("File was already downloaded, skipped URL: %s", info.page_url)
            self.nr_downloads -= 1
            return None

        subpath, filename, ext = info.generate_filename(file_index)

        mypath = os.path.join(self.root_dir, author_name, subpath)
        os.makedirs(mypath, exist_ok=True)
        filename = self._pad_filename_if_exits(mypath, filename, ext)
        filename = f"{filename}.{ext}"

        logger.info("Downloading: %s..., File %d of %d", filename,
                    self.download_index, self.nr_downloads)
        self.download_index += 1

        # TODO retries etc. or use requests lib?
        try:
            if info.is_audio:
                # automatically commits changes to db_con if everything succeeds or does a rollback
                # if an exception is raised; exception is still raised and must be caught
                with self.db_con:
                    # executes the SQL query but leaves commiting it to with db_con in line above
                    self._add_to_db(info, filename)
                    # func passed as kwarg reporthook gets called once on establishment
                    # of the network connection and once after each block read thereafter.
                    # The hook will be passed three arguments; a count of blocks transferred
                    # so far, a block size in bytes, and the total size of the file
                    # total size is -1 if unknown
                    #print(info.direct_url, os.path.abspath(os.path.join(mypath, filename)))
                    dl.download_in_chunks(info.direct_url,
                                          os.path.abspath(os.path.join(mypath, filename)),
                                          prog_bar=True)
            else:
                #print(info.direct_url, os.path.abspath(os.path.join(mypath, filename)))
                dl.download_in_chunks(info.direct_url,
                                      os.path.abspath(os.path.join(mypath, filename)),
                                      prog_bar=True)
        except urllib.error.HTTPError as err:
            logger.warning("HTTP Error %d: %s: \"%s\"", err.code, err.reason, info.direct_url)
        except urllib.error.ContentTooShortError as err:
            logger.warning(err.msg)
            # TODO handle this in a better way
            # technically downloaded but might be corrupt
            info.downloaded = True
        else:
            info.downloaded = True

        return subpath

    def _download_collection(self, info: FileCollection):
        if all(fi.already_downloaded for _, fi in
                children_iter_dfs(info.children, file_info_only=True)):
            logger.info("Skipping collection, since all files were already "
                        "downloaded: %s", info.url)
            # TODO do this in mark_alrdy_downloaded?
            self.nr_downloads -= info.nr_files()
            return None

        logger.info("Starting download of collection: %s", info.url)

        # collection determines best author_name to use
        # priority is 1. reddit 2. file collection author 3. file author 4. fallbacks
        author_name = info.get_preferred_author_name()

        any_downloads = False
        with_file_idx = info.nr_files() > 1
        # don't recurse into separate calls for nested FileCollections
        # only have one call per FileCollection that is in self.downloads
        for rel_idx, fi in children_iter_dfs(info.children,
                                             file_info_only=True, relative_enum=True):
            # rel_idx is 0-based
            self._download_file(fi, author_name, (rel_idx + 1) if with_file_idx else 0)
            any_downloads = any_downloads or fi.downloaded
            rqd.delay_request()

        if any_downloads:
            try:
                # :PassSubpathSelftext
                _, fi = next(children_iter_dfs(info.children, file_info_only=True))
                subpath, _, _ = fi.generate_filename()
                info.write_selftext_file(self.root_dir,
                                         os.path.join(author_name, subpath))
            except AttributeError:
                raise
                pass

    def _add_to_db(self, info: FileInfo, filename: str) -> None:
        """
        Adds instance attributes and reddit_info values to the database using named SQL query
        parameters with a dictionary.
        DOESN'T COMMIT the transaction, since the context manager in self.download() needs to be
        able to do a rollback if the dl fails

        :return: None
        """
        # create dict with keys that correspond to the named parameters in the SQL query
        # set vals contained in reddit_info to None(Python -> SQLITE: NULL)
        val_dict = {
            "date": time.strftime("%Y-%m-%d"),
            "time": time.strftime("%H:%M:%S"),
            "description": info.descr,
            "local_filename": filename,
            "title": info.title,
            "url_file": info.direct_url,
            "url": info.page_url,
            "sgasm_user": info.author,  # TODO rename this column
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
                "created_utc":    reddit_info.created_utc,
                "r_post_url":     reddit_info.r_post_url,
                "reddit_id":      reddit_info.id,
                "reddit_title":   reddit_info.title,
                "reddit_url":     reddit_info.permalink,
                "reddit_user":    reddit_info.author,
                "subreddit_name": reddit_info.subreddit
            })

        self.db_con.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                            "title, url_file, url, created_utc, r_post_url, reddit_id, "
                            "reddit_title, reddit_url, reddit_user, sgasm_user, subreddit_name) "
                            " VALUES (:date, :time, :description, :local_filename, :title, "
                            ":url_file, :url, :created_utc, :r_post_url, :reddit_id, "
                            ":reddit_title, :reddit_url, :reddit_user, :sgasm_user, "
                            ":subreddit_name)", val_dict)

    def mark_alrdy_downloaded(self) -> None:
        """
        Marks already downloaded urls from self.downlods as info.already_downloaded = True
        """
        dl_dict = {info.page_url: info for _, info in children_iter_dfs(
                   self.downloads, file_info_only=True)}
        c = self.db_con.execute("SELECT url FROM Downloads WHERE url IN "
                                f"({', '.join(['?']*len(dl_dict.keys()))})",
                                (*dl_dict.keys(),))
        duplicate = {r[0] for r in c.fetchall()}

        if duplicate and config.getboolean("Settings", "set_missing_reddit"):
            logger.info("Filling in missing reddit info: You can disable this "
                        "in the settings")
            for dupe_url in duplicate:
                info = dl_dict[dupe_url]
                # when we got reddit info get sgasm info even if this file was already
                # downloaded b4 then write missing info to db and write selftext to file
                if info.reddit_info:
                    missing, filename_local, added_date, page_usr = (
                            self.set_missing_reddit_db(info))
                    if not missing or not info.reddit_info.selftext:
                        continue

                    legacy_cutoff = datetime.datetime(2020, 10, 6)
                    if ((info.extractor is SoundgasmExtractor and
                            (added_date is None or added_date == "None")) or
                            datetime.datetime.strptime(added_date, "%Y-%m-%d") <= legacy_cutoff):
                        # TODO due to my db having been used with older versions there are a lot of
                        # rows where cols local_filename and url are empty -> gen a filename so we
                        # can write the selftext
                        if filename_local is None:
                            filename_local = re.sub(
                                    r"[^\w\-_.,\[\] ]", "_",
                                    info.title[0:110]) + ".m4a"
                        selftext_fn = os.path.join(self.root_dir, page_usr,
                                                   f"{filename_local}.txt")

                        if not os.path.isfile(selftext_fn):
                            ri = info.reddit_info
                            with open(selftext_fn, "w", encoding="UTF-8") as w:
                                w.write(f"Title: {ri.title}\nPermalink: {ri.permalink}\n"
                                        f"Selftext:\n\n{ri.selftext}")
                    else:
                        # intentionally don't write into subpath that might get used
                        # by RedditInfo since this file was downloaded without it
                        file_path = os.path.join(page_usr, filename_local)
                        info.reddit_info.write_selftext_file(
                                self.root_dir, file_path, force_path=True)
        if duplicate:
            logger.info("%d files were already downloaded!", len(duplicate))

        for dupe_url in duplicate:
            dl_dict[dupe_url].already_downloaded = True

    def set_missing_reddit_db(self, info: FileInfo) -> (bool, Optional[str], str, str):
        """
        Updates row of file entry in db with reddit_info dict, only sets values if previous
        entry was NULL/None

        :param db_con: Connection to sqlite db
        :param self: instance of AudioDownload whose entry should be updated
        :return: Returns local filename of downloaded audio file
        """
        if not info.reddit_info:
            return

        # even though Row class can be accessed both by index (like tuples) and
        # case-insensitively by name
        # reset row_factory to default so we get normal tuples when fetching
        # (should we generate a new cursor)
        # new_c will always fetch Row obj and cursor will fetch tuples

        c = self.db_con.execute("SELECT * FROM Downloads WHERE url = ?", (info.page_url,))
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

        if upd_cols:
            logger.debug("Updating file entry with new info for: {}".format(", ".join(upd_cols)))
            # append url since upd_vals need to include all the param substitutions for ?
            upd_vals.append(info.page_url)
            # would work in SQLite version 3.15.0 (2016-10-14), but this is 3.8.11, users would
            # have to update as well so not a good idea
            # print("UPDATE Downloads SET ({}) = ({}) WHERE url_file = ?".format(
            #   ",".join(upd_cols), ",".join("?"*len(upd_cols))))

            # TODO let caller handle commit?
            with self.db_con:
                c.execute("UPDATE Downloads SET {} WHERE url = ?".format(",".join(upd_cols)),
                          upd_vals)
        return (row_cont["reddit_id"] is None, row_cont["local_filename"],
                row_cont["date"], row_cont["sgasm_user"])
