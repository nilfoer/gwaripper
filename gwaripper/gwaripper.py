#! python3
import logging
import os
import time
import datetime
import re
import urllib.request
import urllib.error
import dataclasses
import sqlite3

import praw

from typing import List, Union, Optional, cast, Dict, ClassVar, Tuple, Any

from . import utils
from . import config
from .extractors import find_extractor
from .extractors.base import ExtractorErrorCode, ExtractorReport
from .extractors.reddit import RedditExtractor
from .info import (
        FileInfo, FileCollection, RedditInfo, children_iter_dfs,
        UNKNOWN_USR_FOLDER, DELETED_USR_FOLDER, DownloadType
        )
from . import download as dl
from . import exceptions
from .reddit import reddit_praw
from .db import load_or_create_sql_db, export_table_to_csv, backup_db

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


@dataclasses.dataclass
class DownloadCollectionResult:
    any_audio_downloads: bool
    dl_idx: int
    error_code: dl.DownloadErrorCode


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
    def __init__(self,
                 download_duplicates: bool = False,
                 skip_non_audio: bool = False,
                 dont_write_selftext: bool = False) -> None:
        self.db_con, _ = load_or_create_sql_db(
                os.path.join(config.get_root(), "gwarip_db.sqlite"))
        self.urls: List[str] = []
        self.nr_urls: int = 0
        self.extractor_reports: List[ExtractorReport] = []
        self.download_duplicates = download_duplicates
        self.skip_non_audio = skip_non_audio
        # TODO no tests available
        self.dont_write_selftext = dont_write_selftext

    # return type needed otherwise we don't get type checking if used in with..as
    def __enter__(self) -> 'GWARipper':
        return self  # with GWARipper() as x <- x will be self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # If no exception occurred then these last 3 arguments will all be
        # None. If an exception occurred in the with block, then you can either
        # suppress the exception by returning a true value from this method. If
        # you don't want to suppress errors then you can return a value that
        # evaluates to False.
        export_table_to_csv(
                self.db_con,
                os.path.join(config.get_root(), "gwarip_db_exp.csv"),
                "v_audio_and_collection_combined")
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
            dl_success = True if report.download_error_code in (
                    dl.DownloadErrorCode.DOWNLOADED,
                    dl.DownloadErrorCode.SKIPPED_DUPLICATE,
                    dl.DownloadErrorCode.NO_ERRORS) else False

            contents.append(
                f"<div class=\"{'collection ' if is_collection else 'block '}"
                f"{'indent ' if level else ''}\">")
            contents.append(
                f"{'<span>Collection: </span>' if is_collection else ''}<a href=\""
                f"{report.url}\">{report.url}</a>")
            contents.append(
                f"<div class='info'>EXTRACT: <span class='"
                f"{'success ' if success else 'error '}'>{report.err_code.name}"
                f"</span></div>")
            contents.append(
                f"<div class='info'>DOWNLOAD: <span class='"
                f"{'success ' if dl_success else 'error '}'>"
                f"{report.download_error_code.name}</span></div>")
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
            self._download_file(info, info.author, None)
        else:
            self._download_collection(info, None)

    @staticmethod
    def _pad_filename_if_exists(dirpath: str, filename: str, ext: str):
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
                       top_collection: Optional[FileCollection], file_index: int = 0,
                       dl_idx: int = 1, dl_max: int = 1) -> Optional[str]:
        """
        Will download the file to dl_root in a subfolder named like the reddit user name
        if that one is not available the extracted (from the page) author of the file gets
        used
        Calls info.generate_filename to get a valid filename
        Also calls method to add dl to db commits when download is successful, does a rollback
        when not (exception raised).

        :return subpath: Returns subpath to folder the file is located in relative to root_dir
                         None for unsuccessful downloads
        """
        # TODO re-add request delay?
        already_downloaded = self.already_downloaded(info)
        if already_downloaded and not self.download_duplicates:
            logger.info("File was already downloaded, skipped URL: %s", info.page_url)
            return None
        elif not info.is_audio and self.skip_non_audio:
            logger.info("Non-audio file was skipped! URL: %s", info.page_url)
            return None

        if not author_name:
            author_name = UNKNOWN_USR_FOLDER

        subpath, filename, ext = info.generate_filename(top_collection, file_index)

        mypath = os.path.join(config.get_root(), author_name, subpath)
        os.makedirs(mypath, exist_ok=True)
        filename = self._pad_filename_if_exists(mypath, filename, ext)
        filename = f"{filename}.{ext}"

        logger.info("Downloading: %s..., File %d of %d", filename,
                    dl_idx, dl_max)

        dl_function = (self._download_file_http if info.download_type == DownloadType.HTTP
                       else self._download_file_hls)
        file_info_id_in_db: Optional[int] = None
        # NOTE: we already skipped duplicate files if self.download_duplicates wasn't set as
        # well as non-audio files if self.skip_non_audio was True
        # -> this just needs to branch on audio vs non-audio with regards to adding it to the DB
        try:
            if info.is_audio and not already_downloaded:
                # automatically commits changes to db_con if everything succeeds or does a rollback
                # if an exception is raised; exception is still raised and must be caught
                with self.db_con:
                    # executes the SQL query but leaves commiting it to context manager
                    file_info_id_in_db = self._add_to_db(info, None, filename)
                    dl_function(info, mypath, filename)
            else:
                # don't add to db if it's a redownload or non-audio
                # NOTE: we already skip duplicate audios up top if download_duplicates isn't set
                dl_function(info, mypath, filename)
        except urllib.error.HTTPError as err:
            logger.warning("HTTP Error %d: %s: \"%s\"", err.code, err.reason, info.direct_url)

            try:
                info.downloaded = dl.HTTP_ERR_TO_DL_ERR[err.code]
            except KeyError:
                info.downloaded = dl.DownloadErrorCode.HTTP_ERROR_OTHER
        except urllib.error.ContentTooShortError as err:
            logger.warning(err.reason)
            logger.warning("File information was not added to DB! Reddit selftext might "
                           "not be written if this was the only file! "
                           "It's recommended to manually delete and re-download the file "
                           "using GWARipper!")
            info.downloaded = dl.DownloadErrorCode.HTTP_ERROR_OTHER

            if info.parent:
                logger.warning(
                        "Containing root collection: %s",
                        info.reddit_info.url if info.reddit_info is not None
                        else info.parent.url)

        except urllib.error.URLError as err:
            logger.error("URL Error for %s: %s\nExtractor %s is probably broken! "
                         "Please report this error on github!", info.direct_url,
                         str(err.reason).strip(), info.extractor)
            # TODO inaccurate
            info.downloaded = dl.DownloadErrorCode.HTTP_ERROR_OTHER
        except exceptions.ExternalError:
            info.downloaded = dl.DownloadErrorCode.EXTERNAL_ERROR
        else:
            info.downloaded = dl.DownloadErrorCode.DOWNLOADED
            info.id_in_db = file_info_id_in_db
            return subpath
        
        return None

    def _download_file_http(self, info: FileInfo, mypath: str, filename: str):
        # TODO retries etc. or use requests lib?
        # func passed as kwarg reporthook gets called once on establishment
        # of the network connection and once after each block read thereafter.
        # The hook will be passed three arguments; a count of blocks transferred
        # so far, a block size in bytes, and the total size of the file
        # total size is -1 if unknown
        dl.download_in_chunks(info.direct_url,
                              os.path.abspath(os.path.join(mypath, filename)),
                              prog_bar=True,
                              headers=info.additional_headers)

    def _download_file_hls(self, info: FileInfo, mypath: str, filename: str):

        if not dl.download_hls_ffmpeg(info.direct_url, os.path.abspath(os.path.join(mypath, filename))):
            raise exceptions.ExternalError("FFmpeg concatenation failed!")

    def _download_collection(self, info: FileCollection, top_collection: Optional[FileCollection],
                             dl_idx: int = 1) -> DownloadCollectionResult:
        logger.info("Starting download of collection: %s", info.url)

        if top_collection is None:
            top_collection = info

        # top collection determines best author_name to use
        # priority is 1. reddit 2. file collection author 3. file author 4. fallbacks
        author_name = top_collection.get_preferred_author_name()

        # NOTE: this function needs to be recursive, since otherwise collections
        # that had no (successful) audio downloads will still be added to the DB

        download_err_code = dl.DownloadErrorCode.NO_ERRORS
        any_audio_downloads = False
        with_file_idx = info.nr_files > 1
        rel_idx = 1
        for fi_or_fc in info.children:
            # add FileCollections to DB here
            if isinstance(fi_or_fc, FileCollection):
                # recursive call
                dl_collection_result = self._download_collection(fi_or_fc, top_collection, dl_idx=dl_idx)
                dl_idx = dl_collection_result.dl_idx
                any_audio_downloads = any_audio_downloads or dl_collection_result.any_audio_downloads
                if dl_collection_result.error_code != dl.DownloadErrorCode.NO_ERRORS:
                    download_err_code = dl.DownloadErrorCode.ERROR_IN_CHILDREN
            else:
                fi: FileInfo = fi_or_fc
                # rel_idx is 0-based
                self._download_file(
                        fi, author_name, top_collection,
                        rel_idx if with_file_idx else 0,
                        dl_idx=dl_idx, dl_max=top_collection.nr_files)
                if fi.is_audio and fi.downloaded is dl.DownloadErrorCode.DOWNLOADED:
                    any_audio_downloads = True
                rel_idx += 1
                dl_idx += 1

                if fi.downloaded not in (
                        dl.DownloadErrorCode.DOWNLOADED, dl.DownloadErrorCode.SKIPPED_DUPLICATE):
                    download_err_code = dl.DownloadErrorCode.ERROR_IN_CHILDREN

        # set download status once a collection is finished
        info.downloaded = download_err_code

        # only file collections containing audio files get added to db
        if any_audio_downloads:
            if isinstance(info, RedditInfo):
                with self.db_con:
                    self._add_to_db_ri(cast(RedditInfo, info))

                subpath = top_collection.subpath if top_collection is not None else ""
                # :PassSubpathSelftext
                if not self.dont_write_selftext:
                    cast(RedditInfo, info).write_selftext_file(
                            config.get_root(), os.path.join(author_name, subpath))
            else:
                with self.db_con:
                    self._add_to_db_collection(info, author_name)

        return DownloadCollectionResult(any_audio_downloads, dl_idx, download_err_code)

    @staticmethod
    def add_artist(db_con: sqlite3.Connection, artist: str):
        c = db_con.execute("INSERT OR IGNORE INTO Artist(name) VALUES (?)",
                  (artist,))
        c.execute("""
        INSERT OR IGNORE INTO Alias(name, artist_id) VALUES (
            ?,
            (SELECT id FROM Artist WHERE name = ?)
        )""", (artist, artist))


    # TODO: @CleanUp this RedditInfo stuff is clunky, generalize it to just be added metadata
    # like storing upvotes etc.
    def _add_to_db_collection(self, file_col: FileCollection, author: str) -> Tuple[str, bool]:
        """
        Add FileCollection to DB; will return a pre-existing FileCollection if
        the url column matches file_col.full_url
        :return: Tuple of the alias name of the author
                 that was assigned to this collection and whether FileCollection
                 was found in the DB
        """
        c = self.db_con.cursor()

        # joins usually faster (but it depends on the specific case obv.) and
        # better supported than multiple select statements or subqueries
        # (and better to understand)
        # (DB can optimize the joins better, joins are used more often,
        #  better caching of joins, in the case of subquery (FROM (SELECT ..))
        #  vs join: join works on a table with indices while subquery
        #  does not -> large result -> slow)
        existing_collection = c.execute("""
        SELECT FileCollection.id as collection_id , Alias.name as alias_name
        FROM FileCollection
        JOIN Alias ON Alias.id = FileCollection.alias_id
        WHERE url = ?""", (file_col.full_url,)).fetchone()

        # FileCollection already in DB -> just return id and artist/alias
        if existing_collection:
            file_col.id_in_db = existing_collection['collection_id']
            return existing_collection['alias_name'], True

        self.add_artist(self.db_con, author)

        filecol_dict: Dict[str, Optional[Union[str, int]]] = {
            "url": file_col.full_url,
            "id_on_page": file_col.id,
            "title": file_col.title,
            "subpath": file_col.subpath,
            "parent_id": file_col.parent.id_in_db if file_col.parent else None,
            "alias_name": author
        }

        c.execute("""
        INSERT INTO FileCollection(
            url, id_on_page, title, subpath, parent_id,
            alias_id
        ) VALUES (
            :url, :id_on_page, :title, :subpath, :parent_id,
            (SELECT id FROM Alias WHERE name = :alias_name)
        )""", filecol_dict)
        file_col.id_in_db = c.lastrowid

        # update the parent ids of all our audio files or collections
        for fi_or_fc in file_col.children:
            if isinstance(fi_or_fc, FileCollection):
                fc: FileCollection = fi_or_fc
                if fc.id_in_db is not None:
                    c.execute("UPDATE FileCollection SET parent_id = ? WHERE id = ?",
                              (file_col.id_in_db, fc.id_in_db))
            elif isinstance(fi_or_fc, FileInfo):
                fi: FileInfo = fi_or_fc
                # mypy (0.8+0.961) does not detect the type error of the comparison between
                # bool and DownloadErrorCode (fi.downloaded is True)
                # needs --strict-equality to detect it
                if fi.is_audio and fi.downloaded is dl.DownloadErrorCode.DOWNLOADED:
                    c.execute("UPDATE AudioFile SET collection_id = ? WHERE id = ?",
                              (file_col.id_in_db, fi.id_in_db))

        return author, False


    def _add_to_db_ri(self, r_info: RedditInfo) -> Tuple[int, str]:
        c = self.db_con.cursor()

        # for cases where the post is still available (as well as the linked
        # audio files) but the reddit user has been deleted
        reddit_author = r_info.author if r_info.author else DELETED_USR_FOLDER

        # TODO: check if this will use the correct author
        author, was_in_db = self._add_to_db_collection(r_info, reddit_author)

        # TODO get rid of RedditInfo entirely and add the columns (there's only one) to FileCollection
        if not was_in_db:
            c.execute("INSERT INTO RedditInfo(created_utc) VALUES (?)",
                      (r_info.created_utc,))
            r_info_id = c.lastrowid
            # assign reddit info to collection
            c.execute("UPDATE FileCollection SET reddit_info_id = ? WHERE id = ?",
                      (r_info_id, r_info.id_in_db))

        return cast(int, r_info.id_in_db), author if was_in_db else reddit_author

    def _add_to_db(self, info: FileInfo, collection_id: Optional[int], filename: str) -> int:
        return self.add_to_db(self.db_con, info, collection_id, filename)

    @staticmethod
    def add_to_db(
        db_con: sqlite3.Connection,
        info: FileInfo,
        collection_id: Optional[int],
        filename: str,
        file_author_is_artist: bool = False
    ) -> int:
        """
        Adds instance attributes and reddit_info values to the database using named SQL query
        parameters with a dictionary.
        DOESN'T COMMIT the transaction, since the context manager in GWARipper.download() needs to be
        able to do a rollback if the dl fails

        :param file_author_is_artist: True if the info.author should be treated as an artist name
                                      instead of just as an alias with a possibly unkown artist
        :return: None
        """

        reddit_author: Optional[str] = None
        if info.reddit_info:
            reddit_author = info.reddit_info.author
        elif file_author_is_artist:
            reddit_author = info.author

        c = db_con.execute(f"""
        INSERT OR IGNORE INTO Alias(name, artist_id) VALUES (
            ?,
            {'(SELECT id FROM Artist WHERE Artist.name = ?)' if reddit_author else 'NULL'}
        )""", (info.author, reddit_author) if reddit_author else (info.author,))

        # create dict with keys that correspond to the named parameters in the SQL query
        # set vals contained in reddit_info to None(Python -> SQLITE: NULL)
        audio_file_dict: Dict[str, Optional[Union[str, int, datetime.date]]] = {
            "collection_id": collection_id,
            "date": datetime.datetime.now().date(),
            "description": info.descr,
            "filename": filename,
            "title": info.title,
            "url": info.page_url,
            "alias_name": info.author
        }

        c.execute("""
        INSERT INTO AudioFile(
            collection_id, date, description,
            filename, title, url,
            alias_id
        ) VALUES (
            :collection_id, :date, :description,
            :filename, :title, :url,
            (SELECT id FROM Alias WHERE name = :alias_name)
        )""", audio_file_dict)

        return cast(int, c.lastrowid)

    def already_downloaded(self, info: FileInfo) -> bool:
        """
        Checks by querying for info.page_url and info.direct_url in DB if a file
        was downloaded before
        """
        # check both url and url_file since some rows only have the url_file set
        c = self.db_con.execute("SELECT id, collection_id FROM AudioFile WHERE url = ?"
                                "OR url = ?", (info.page_url, info.direct_url))
        duplicate = c.fetchone()

        if (info.reddit_info and duplicate and not duplicate['collection_id'] and
                config.config.getboolean("Settings", "set_missing_reddit", fallback=False)):
            self.set_missing_reddit_db(duplicate['id'], info)

        if duplicate:
            info.downloaded = dl.DownloadErrorCode.SKIPPED_DUPLICATE
            return True
        else:
            return False

    def set_missing_reddit_db(self, audio_file_id: int, info: FileInfo) -> None:
        """
        Updates row of file entry in db with reddit info, only sets values if previous
        entry was NULL/None
        Commits results to DB
        """
        if not info.reddit_info:
            return
        # NOTE: only set missing reddit info for the first FileInfo per url
        # otherwise we might set it on a file that was downloaded for the first time
        # we know there is a parent otherwise we wouldn't have reddit info
        # and that there are children
        same_url_fi = [fi for fi in cast(List[Union[FileInfo, FileCollection]], 
                                         cast(FileCollection, info.parent).children)
                       if type(fi) is FileInfo and fi.page_url == info.page_url]
        own_index = next(i for i in range(len(same_url_fi)) if same_url_fi[i] is info)
        if own_index != 0:
            return

        with self.db_con:
            collection_id, reddit_author = self._add_to_db_ri(info.reddit_info)

            c = self.db_con.execute("""
            UPDATE AudioFile SET
                collection_id = ?
            WHERE id = ?""", (collection_id, audio_file_id))

            c.execute("""
            SELECT
            filename,
            title,
            Alias.name as alias_name,
            Alias.id as alias_id,
            Alias.artist_id as artist_id
            FROM AudioFile
            JOIN Alias ON Alias.id = AudioFile.alias_id
            WHERE AudioFile.id = ?
            """, (audio_file_id,))

            af_row = c.fetchone()

            # update artist_id of alias if it's NULL
            if af_row['artist_id'] is None:
                artist_id_row = c.execute(
                        "SELECT id FROM Artist WHERE name = ?", (reddit_author,)).fetchone()
                if artist_id_row:
                    artist_id = artist_id_row[0]
                    c.execute("UPDATE Alias SET artist_id = ? WHERE id = ?",
                              (artist_id, af_row['alias_id']))

            if not info.reddit_info.selftext:
                return

            filename_local = af_row['filename']
            author_subdir = af_row['alias_name']

            # NOTE: due to my db having been used with older versions there are a lot of
            # rows where cols filename and url are empty -> gen a filename so we
            # can write the selftext
            if not filename_local:  # prev NULL filename will now be ""
                filename_local = re.sub(
                        r"[^\w\-_.,\[\] ]", "_",
                        af_row['title'][0:110]) + ".m4a"
            # intentionally don't write into subpath that might get used
            # by RedditInfo since this file was downloaded without it
            file_path = os.path.join(author_subdir, filename_local)
            if not self.dont_write_selftext:
                info.reddit_info.write_selftext_file(
                        config.get_root(), file_path, force_path=True)
