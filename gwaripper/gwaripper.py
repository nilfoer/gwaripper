#! python3
import logging
import os
import time
import re
import urllib.request
import sqlite3

from typing import List, Union, Optional

from .logging_setup import configure_logging
from . import clipwatcher_single
from . import utils
from .config import config, write_config_module, ROOTDIR
from .extractors import find_extractor
from .info import FileInfo, FileCollection, RedditInfo, children_iter_dfs, children_iter_bfs
from . import download as dl
from .db import load_or_create_sql_db, export_csv_from_sql, backup_db
from .exceptions import InfoExtractingError

rqd = utils.RequestDelayer(0.25, 0.75)

# configure logging
# logfn = time.strftime("%Y-%m-%d.log")
# __name__ = 'gwaripper.gwaripper' -> logging of e.g. 'gwaripper.utils' (when callin getLogger with __name__
# in utils module) wont be considered a child of this logger
# we could use logging.config.fileConfig to configure our loggers (call it in main() for example, but with
# 'disable_existing_loggers': False, otherwise all loggers created by getLogger at module-level will be disabled)
# or we could configure our logging in __init__.py of our package (top-most level) with __name__ since that is
# just 'gwaripper' or we can configure our logger for the package by calling getLogger with 'gwaripper'
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
        self.db_con, _ = load_or_create_sql_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))
        self.downloads = []
        self.nr_downloads = 0
        self.download_index = 1

    def parse_links(self, links: List[str]) -> None:
        for url in links:
            extractor = find_extractor(url)
            try:
                info = extractor(url).extract()
            except InfoExtractingError:
                logger.error("Extraction failed! Skipping URL: %s", url)
                continue
            if info is not None:
                self.downloads.append(info)

        import pickle
        with open("parsed_b4_nrdls_downloads.pickle", "wb") as f:
            pickle.dump(self.downloads, f)
        self.nr_downloads += sum(1 for _, x in children_iter_dfs(self.downloads)
                                 if isinstance(x, FileInfo))

    def download_all(self) -> None:
        # TODO mb to restrict to [self.download_index + 1: self.nr_downloads + 1]?
        for fi in self.downloads:
            self.download(fi)

    def download(self, info: Union[FileInfo, FileCollection]) -> None:
        if isinstance(info, FileInfo):
            self._download_file(info, info.author)
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
        """
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
                dl.download_in_chunks(info.direct_url,
                                      os.path.abspath(os.path.join(mypath, filename)),
                                      prog_bar=True)
        except urllib.error.HTTPError as err:
            logger.warning("HTTP Error %d: %s: \"%s\"", err.code, err.reason, info.direct_url)
        except urllib.error.ContentTooShortError as err:
            logger.warning(err.msg)

    def _download_collection(self, info: FileCollection):
        logger.info("Starting download of collection: %s", info.url)

        # collection determines best author_name to use
        # priority is 1. reddit 2. file collection author 3. file author 4. fallbacks
        author_name = info.get_preferred_author_name()

        # don't recurse into separate calls for nested FileCollections
        # only have one call per FileCollection that is in self.downloads
        for rel_idx, fi in children_iter_dfs(info.children,
                                             file_info_only=True, relative_enum=True):
            self._download_file(fi, author_name, rel_idx)

        # TODO: check for download
        try:
            info.write_selftext_file(os.path.join(self.root_dir, author_name))
        except AttributeError:
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
                            "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                            "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                            ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                            ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                            ":sgasm_user, :subreddit_name)", val_dict)

    def filter_alrdy_downloaded(self) -> None:
        """
        Filters out already downloaded urls from self.downlods
        """
        c = self.db_con.execute("SELECT url FROM Downloads WHERE url IN "
                                f"({', '.join(['?']*len(self.downloads))})",
                                (*self.downloads,))
        duplicate = {r[0] for r in c.fetchall()}

        if config.getboolean("Settings", "set_missing_reddit"):
            for dup in duplicate:
                # when we got reddit info get sgasm info even if this file was already downloaded b4
                # then write missing info to df and write selftext to file
                if dl_dict[dup].reddit_info and ("soundgasm.net/" in dup):
                    logger.info("Filling in missing reddit info: You can disable this "
                                "in the settings")
                    adl = dl_dict[dup]
                    # get filename from db to write selftext
                    adl.filename_local = adl.set_missing_reddit_db(db_con)
                    # TODO due to my db having been used with older versions there are a lot of
                    # rows where cols local_filename and url are empty -> gen a filename so we can
                    # write the selftext
                    if adl.filename_local is None:  # TORELEASE remove
                        adl.filename_local = re.sub(r"[^\w\-_.,\[\] ]", "_", adl.title[0:110]) + ".m4a"  # TORELEASE remove
                    adl.write_selftext_file(ROOTDIR)
        if duplicate:
            logger.info("%d files were already downloaded!", len(duplicate))

        # Return a new set with elements in either the set or other but not both.
        # -> duplicates will get removed from unique_urls
        self.downloads = list(duplicate.symmetric_difference(self.downloads))

    def set_missing_reddit_db(self, db_con):
        """
        Updates row of file entry in db with reddit_info dict, only sets values if previous
        entry was NULL/None

        :param db_con: Connection to sqlite db
        :param self: instance of AudioDownload whose entry should be updated
        :return: Returns local filename of downloaded audio file
        """
        if not self.reddit_info:
            return
        # Row provides both index-based and case-insensitive name-based access to columns with almost no memory overhead
        db_con.row_factory = sqlite3.Row
        # we need to create new cursor after changing row_factory
        c = db_con.cursor()

        # even though Row class can be accessed both by index (like tuples) and case-insensitively by name
        # reset row_factory to default so we get normal tuples when fetching (should we generate a new cursor)
        # new_c will always fetch Row obj and cursor will fetch tuples
        db_con.row_factory = None

        c.execute("SELECT * FROM Downloads WHERE url = ?", (self.page_url,))
        row_cont = c.fetchone()

        set_helper = (("reddit_title", "title"), ("reddit_url", "permalink"),
                      ("reddit_user", "r_user"), ("created_utc", "created_utc"),
                      ("reddit_id", "id"), ("subreddit_name", "subreddit"),
                      ("r_post_url", "r_post_url"))

        upd_cols = []
        upd_vals = []
        for col, key in set_helper:
            if row_cont[col] is None:
                upd_cols.append("{} = ?".format(col))
                upd_vals.append(self.reddit_info[key])

        if upd_cols:
            logger.debug("Updating file entry with new info for: {}".format(", ".join(upd_cols)))
            # append url since upd_vals need to include all the param substitutions for ?
            upd_vals.append(self.page_url)
            # would work in SQLite version 3.15.0 (2016-10-14), but this is 3.8.11, users would
            # have to update as well so not a good idea
            # print("UPDATE Downloads SET ({}) = ({}) WHERE url_file = ?".format(
            #   ",".join(upd_cols), ",".join("?"*len(upd_cols))))

            # Connection objects can be used as context managers that automatically commit or
            # rollback transactions.
            # In the event of an exception, the transaction is rolled back; otherwise, the 
            # transaction is committed
            # Unlike with open() etc. connection WILL NOT GET CLOSED
            with db_con:
                # join only inserts the string to join on in-between the elements of the 
                # iterable (none at the end)
                # format to -> e.g UPDATE Downloads SET url = ?,local_filename = ?
                # WHERE url_file = ?
                c.execute("UPDATE Downloads SET {} WHERE url = ?".format(",".join(upd_cols)), upd_vals)
        return row_cont["local_filename"]


def gen_audiodl_from_sglink(sglinks):
    """
    Generates AudioDownload instances initiated with the sgasm links and returns them in a list

    :param sglinks: Links to soundgasm.net posts
    :return: List containing AudioDownload instances that were created with the urls in sglinks
    """
    dl_list = []
    # set -> remove duplicates
    for link in set(sglinks):
        a = AudioDownload(link, "sgasm")
        dl_list.append(a)
    return dl_list


def rip_audio_dls(dl_list):
    """
    Accepts list of AudioDownload instances, loads sqlite db and fetches downloaded urls from it.
    Filters them for new downloads and saves them to disk by calling call_host_get_file_info and download method.
    Calls backup_db to do automatic backups after all operations are done.

    :param dl_list: List of AudioDownload instances
    """

    # create dict that has page urls as keys and AudioDownload instances as values
    # dict comrehension: d = {key: value for (key, value) in iterable}
    # duplicate keys -> last key value pair is in dict, values of the same key that came before arent
    # @Hack removing /gwa appendix since we only add the url without /gwa to the db
    # so we might have duplicate downloads otherwise
    dl_dict = {audio.page_url[:-4] if audio.page_url.endswith("/gwa") else audio.page_url:
               audio for audio in dl_list}

    # returns list of new downloads, dl_dict still holds all of them
    new_dls = filter_alrdy_downloaded(dl_dict, conn)

    filestodl = len(new_dls)
    dlcounter = 0

    for url in new_dls:
        audio_dl = dl_dict[url]

        rqd.delay_request()
        try:
            audio_dl.call_host_get_file_info()
        except urllib.request.HTTPError:
            # page with file info doesnt exist
            # nothing was added to db yet so we can just skip ahead
            filestodl -= 1
            continue

        # sleep between requests so we dont stress the server too much or get banned
        # using helper class -> only sleep .25s when last request time was less than .5s ago
        rqd.delay_request()
        dlcounter = audio_dl.download(conn, dlcounter, filestodl, ROOTDIR)

    # export db to csv -> human readable without tools
    export_csv_from_sql(os.path.join(ROOTDIR, "gwarip_db_exp.csv"), conn)
    conn.close()

    # auto backup
    backup_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))


def rip_usr_to_files(currentusr):
    """
    Calls functions to download all the files of sgasm user to disk

    :param currentusr: soundgasm.net username string
    :return: None
    """
    sgasm_usr_url = "https://soundgasm.net/u/{}".format(currentusr)
    logger.info("Ripping user %s" % currentusr)

    dl_list = gen_audiodl_from_sglink(rip_usr_links(sgasm_usr_url))

    rip_audio_dls(dl_list)


def watch_clip():
    """
    Watches clipboard for links of domain

    Convert string to python code to be able to pass function to check if clipboard content is
    what we're looking for to ClipboardWatcher init

    :param domain: keyword that points to function is_domain_url in clipwatcher_single module
    :return: List of found links, None if there None
    """
    watcher = clipwatcher_single.ClipboardWatcher(clipwatcher_single.is_url,
                                                  clipwatcher_single.print_write_to_txtf,
                                                  os.path.join(ROOTDIR, "_linkcol"), 0.1)
    try:
        logger.info("Watching clipboard...")
        watcher.run()
    except KeyboardInterrupt:
        watcher.stop()
        logger.info("Stopped watching clipboard!")
        if watcher.found:
            logger.info("URLs were saved in: {}\n".format(watcher.txtname))
            yn = input("Do you want to download found URLs directly? (yes/no):\n")
            if yn == "yes":
                # dont return ref so watcher can die
                return watcher.found.copy()
            else:
                return
