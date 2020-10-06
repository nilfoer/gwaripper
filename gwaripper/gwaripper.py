#! python3
import logging
import os
import time
import re
import urllib.request
import sqlite3

import bs4

from typing import List, Union

from .logging_setup import configure_logging
from . import clipwatcher_single
from . import utils
from .config import config, write_config_module, ROOTDIR
from .extractors import find_extractor
from .info import FileInfo, FileCollection, RedditInfo
from .audio_dl import AudioDownload
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


DELETED_USR_FOLDER = "deleted_users"


class GWARipper:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.db_con, _ = load_or_create_sql_db(os.path.join(ROOTDIR, "gwarip_db.sqlite"))
        self.downloads = []

    def parse_links(self, links: List[str]) -> None:
        for url in links:
            extractor = find_extractor(url)
            try:
                info = extractor(url).extract()
            except InfoExtractingError:
                logger.error("Extraction failed! Skipping URL: %s", url)
                continue
            self.downloads.append(info)

    def generate_filename(self, info: dict) -> str:
        """
        Generates filename to save file locally by replacing chars in the title that are not:
        \\w(regex) - , . _ [ ] or a whitespace(" ")
        with an underscore and limiting its length. If file exists it adds a number padded
        to a width of 2 starting at one till there is no file with that name

        :return: String with filename and added extension
        """
        # [^\w\-_\.,\[\] ] -> match not(^) any of \w \- _  and whitepsace etc.,
        # replace any that isnt in the  [] with _
        filename = re.sub(r"[^\w\-_.,\[\] ]", "_", self.title[0:110])
        ftype = self.file_type

        mypath = os.path.join(self.root_dir, self.name_usr)
        # isfile works without checking if dir exists first
        if os.path.isfile(os.path.join(mypath, filename + ftype)):
            i = 0

            # You don't need to copy a Python string. They are immutable, so concatenating or
            # slicing returns a new string
            filename_old = filename

            # file alrdy exists but it wasnt in the url database -> prob same titles only one tag
            # or the ending is different (since fname got cut off, so we dont exceed win path limit)
            # count up i till file doesnt exist anymore
            while os.path.isfile(os.path.join(mypath, filename + ftype)):
                i += 1
                # :02d -> pad number with 0 to a width of 2, d -> digit(int)
                filename = "{}_{:02d}".format(filename_old, i)
            logger.info("FILE ALREADY EXISTS - ADDED: _{:02d}".format(i))
        return filename + ftype

    def download_all(self) -> None:
        for fi in self.downloads:
            self.download(fi)

    def download(self, info: Union[FileInfo, FileCollection]) -> None:
        if isinstance(info, FileInfo):
            self._download_file(info)
        else:
            self._download_collection(info)

    def _download_file(self):
        """
        Will download the file to dl_root in a subfolder named self.name_usr
        Calls self.gen_filename to get a valid filename and sets date and time of the download.
        Also calls method to add dl to db commits when download is successful, does a rollback
        when not (exception raised). Calls self.write_selftext_file if reddit_info is not None

        :param db_con: Connection to sqlite db
        :param curfnr: Current file number
        :param maxfnr: Max files to download
        :param dl_root: Root dir of script/where dls will be saved in subdirs
        :return: Current file nr(int)
        """
        if self.url_to_file is not None:
            curfnr += 1

            mypath = os.path.join(dl_root, self.name_usr)
            os.makedirs(mypath, exist_ok=True)
            self.filename_local = self.gen_filename(db_con, dl_root)

            if self.filename_local:
                logger.info("Downloading: {}..., File {} of {}".format(self.filename_local, curfnr, maxfnr))
                self.date = time.strftime("%Y-%m-%d")
                self.time = time.strftime("%H:%M:%S")
                # set downloaded
                self.downloaded = True

                try:
                    # automatically commits changes to db_con if everything succeeds or does a rollback if an
                    # exception is raised; exception is still raised and must be caught
                    with db_con:
                        # executes the SQL query but leaves commiting it to with db_con in line above
                        self._add_to_db(db_con)
                        # func passed as kwarg reporthook gets called once on establishment of the network connection
                        # and once after each block read thereafter. The hook will be passed three arguments;
                        # a count of blocks transferred so far, a block size in bytes, and the total size of the file
                        # total size is -1 if unknown
                        urllib.request.urlretrieve(self.url_to_file,
                                                   os.path.abspath(os.path.join(mypath, self.filename_local)),
                                                   reporthook=prog_bar_dl)
                except urllib.request.HTTPError as err:
                    # dl failed set downloaded
                    self.downloaded = False
                    logger.warning("HTTP Error {}: {}: \"{}\"".format(err.code, err.reason, self.url_to_file))
                else:  # only write selftext if file was dled
                    if self.reddit_info:
                        # also write reddit selftext in txtfile with same name as audio
                        self.write_selftext_file(dl_root)
        else:
            logger.warning("FILE DOWNLOAD SKIPPED - NO DATA RECEIVED")

        return curfnr

    def _add_to_db(self, file_info: FileInfo):
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
            "date": self.date,
            "time": self.time,
            "description": self.descr,
            "local_filename": self.filename_local,
            "title": self.title,
            "url_file": self.url_to_file,
            "url": self.page_url,
            "sgasm_user": self.name_usr,
            "created_utc": None,
            "r_post_url": None,
            "reddit_id": None,
            "reddit_title": None,
            "reddit_url": None,
            "reddit_user": None,
            "subreddit_name": None
        }

        # reddit_info not None -> update dict with actual vals from reddit_info dict
        # update([other]): Update the dictionary with the key/value pairs from other, overwriting existing keys
        if self.reddit_info:
            val_dict.update({
                "created_utc": self.reddit_info["created_utc"],
                "r_post_url": self.reddit_info["r_post_url"],
                "reddit_id": self.reddit_info["id"],
                "reddit_title": self.reddit_info["title"],
                "reddit_url": self.reddit_info["permalink"],
                "reddit_user": self.reddit_info["r_user"],
                "subreddit_name": self.reddit_info["subreddit"]
            })

        self.db_con.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                            "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                            "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                            ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                            ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                            ":sgasm_user, :subreddit_name)", val_dict)

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


def filter_alrdy_downloaded(dl_dict, db_con):
    """
    Filters out already downloaded urls and returns a set of new urls
    Logs duplicate downloads

    :param dl_dict: dict with urls as keys and the corresponding AudioDownload obj as values
    :param db_con: connection to sqlite3 db
    :return: set of new urls
    """
    c = db_con.execute("SELECT url FROM Downloads WHERE url IN "
                       f"({', '.join(['?']*len(dl_dict.keys()))})",
                       (*dl_dict.keys(),))
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
        logger.info("{} files were already downloaded!".format(len(duplicate)))
        logger.debug("Already downloaded urls:\n{}".format("\n".join(duplicate)))

    # set.symmetric_difference()
    # Return a new set with elements in either the set or other but not both.
    # -> duplicates will get removed from unique_urls
    result = duplicate.symmetric_difference(dl_dict.keys())

    return result


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
