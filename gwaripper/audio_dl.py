import base64
import logging
import os
import re
import sys
import time
import urllib.request
import sqlite3
from urllib.parse import quote as url_quote

import bs4

from . import utils

logger = logging.getLogger(__name__)

DELETED_USR_FOLDER = "deleted_users"


class AudioDownload:  # TODO docstr
    """
    Represents an audio post that is normally listened to
    """

    def __init__(self, page_url, host, reddit_info=None):
        self.page_url = page_url
        self.host = host
        self.reddit_info = reddit_info
        # use reddit user name if not sgasm
        if host == "sgasm":
            self.name_usr = self.page_url.split("/u/", 1)[1].split("/", 1)[0]
        elif self.reddit_info["r_user"] is None:
            self.name_usr = DELETED_USR_FOLDER
        else:
            self.name_usr = self.reddit_info["r_user"]
        self.downloaded = False
        self.url_to_file = None
        self.file_type = None
        self.title = None
        self.filename_local = None
        self.descr = None
        self.date = None
        self.time = None

    def call_host_get_file_info(self):
        """
        Calls appropriate method to get file info for host type, throws InfoExtractingError if
        the calle function fails to extract the needed info (site structure probably changed)

        :return: None
        """
        if self.host == "sgasm":
            self._set_sgasm_info()
        elif self.host == "chirb.it":
            self._set_chirbit_url()
        elif self.host == "eraudica":
            self._set_eraudica_info()

    def _set_chirbit_url(self):
        """
        Gets and sets the direct url for downloading the audio file on self.page_url, the file type and
        removes special chars from filename

        Use bs4 to get a reversed base64 encoded string from <i> tag's data-fd attribute
        Reverse it with a slice and decode it with base64.b64decode

        :return: None
        """
        try:
            site = urllib.request.urlopen(self.page_url)
        except urllib.request.HTTPError as err:
            logger.warning("HTTP Error {}: {}: \"{}\"".format(err.code, err.reason, self.page_url))
            raise
        else:
            html = site.read().decode('utf-8')
            site.close()
            soup = bs4.BeautifulSoup(html, "html.parser")

            try:
                # selects ONE i tag with set data-fd attribute beneath tag with class .wavholder beneath
                # div with id main then get attribute data-fd
                # TypeError when trying to subscript soup.select_one but its None
                str_b64 = soup.select_one('div#main .wavholder i[data-fd]')["data-fd"]
                # reverse string using a slice -> string[start:stop:step], going through whole string with step -1
                str_b64_rev = str_b64[::-1]
                # decode base64 string to get url to file -> returns byte literal -> decode with appropriate encoding
                # this link EXPIRES so get it right b4 downloading
                self.url_to_file = base64.b64decode(str_b64_rev).decode("utf-8")
                self.file_type = self.url_to_file.split("?")[0][-4:]
                self.title = self.reddit_info["title"]
            except (AttributeError, IndexError, TypeError):
                raise utils.InfoExtractingError("Error occured while extracting chirbit info - site structure "
                                                "probably changed! See if there are updates available!",
                                                self.page_url, html)

    def _set_eraudica_info(self):
        # strip("/gwa") doesnt strip the exact string "/gwa" from the end but instead it strips all the
        # chars contained in that string from the end:
        # "eve/Audio-extravaganza/gwa".strip("/gwa") ->  "eve/Audio-extravaganz"
        # use slice instead (replace might remove that string even if its not at the end)
        # remove /gwa from end of link so we can access file download
        if self.page_url.endswith("/gwa"):
            self.page_url = self.page_url[:-4]

        try:
            site = urllib.request.urlopen(self.page_url)
        except urllib.request.HTTPError as err:
            logger.warning("HTTP Error {}: {}: \"{}\"".format(err.code, err.reason, self.page_url))
            raise
        else:
            html = site.read().decode('utf-8')
            site.close()
            soup = bs4.BeautifulSoup(html, "html.parser")

            try:
                # selects script tags beneath div with id main and div class post
                # returns list of bs4.element.Tag -> access text with .text
                scripts = soup.select("div#main div.post script")[1].text
                # vars that are needed to gen dl link are included in script tag
                # access group of RE (part in '()') with .group(index)
                # Group 0 is always present; it’s the whole RE
                fname = re.search("var filename = \"(.+)\"", scripts).group(1)
                server = re.search("var playerServerURLAuthorityIncludingScheme = \"(.+)\"", scripts).group(1)
                dl_token = re.search("var downloadToken = \"(.+)\"", scripts).group(1)
                # convert unicode escape sequences (\\u0027) that might be in the filename to str
                # fname.encode("utf-8").decode("unicode-escape")
                # bytes(fname, 'ascii').decode('unicode-escape')
                fname = fname.encode("utf-8").decode("unicode-escape")
                # convert fname to make it url safe with urllib.quote (quote_plus replaces spaces with plus signs)
                fname = url_quote(fname)  # renamed so i dont accidentally create a func with same name

                self.url_to_file = "{}/fd/{}/{}".format(server, dl_token, fname)
                self.title = self.reddit_info["title"]
                self.file_type = fname[-4:]
            except (IndexError, AttributeError):
                raise utils.InfoExtractingError("Error occured while extracting eraudica info - site structure "
                                                "probably changed! See if there are updates available!",
                                                self.page_url, html)  # from None -> get rid of Exceptions b4 this one

    def _set_sgasm_info(self):
        logger.info("Getting soundgasm info of: %s" % self.page_url)
        try:
            site = urllib.request.urlopen(self.page_url)
        except urllib.request.HTTPError as err:
            logger.warning("HTTP Error {}: {}: \"{}\"".format(err.code, err.reason, self.page_url))
            raise
        else:  # executes if try clause does not raise an exception
            html = site.read().decode('utf-8')
            site.close()

            soup = bs4.BeautifulSoup(html, "html.parser")

            try:
                title = soup.select_one("div.jp-title").text

                # set instance values
                self.url_to_file = re.search("m4a: \"(.+)\"", html).group(1)
                self.file_type = ".m4a"
                self.title = title
                self.descr = soup.select_one("div.jp-description > p").text
            except AttributeError:
                raise utils.InfoExtractingError("Error occured while extracting sgasm info - site structure "
                                                "probably changed! See if there are updates available!",
                                                self.page_url, html)

    # From Hitchhiker's Guide to Python:
    # When a function grows in complexity it is not uncommon to use multiple return statements inside the function’s
    # body. However, in order to keep a clear intent and a sustainable readability level, it is preferable to avoid
    # returning meaningful values from many output points in the body.
    # [...] [2 main reasons for return -> when it has been processed normally, and the error cases
    # If you do not wish to raise exceptions for the second case -> return None or False -> return as early
    # as possible -> flatten structure ->  all the code after the return­because­of­error statement can
    # assume the condition is met to further compute the function’s main result -> often multiple such returns
    # are necessary]
    # When a function has multiple main exit points for its normal course, it becomes difficult to debug the
    # returned result, so it may be preferable to keep a single exit point. This will also help factoring out
    # some code paths, and the multiple exit points are a probable indication that such a refactoring is needed.
    def gen_filename(self, db_con, dl_root):
        """
        Generates filename to save file locally by replacing chars in the title that are not:
         \w(regex) - , . _ [ ] or a whitespace(" ")
        with an underscore and limiting its length. If file exists it adds a number padded
        to a width of 2 starting at one till there is no file with that name

        :param db_con: Connection to sqlite db
        :param dl_root: Path to root dir of the script (where all the downloads etc. are saved)
        :return: String with filename and added extension
        """
        # [^\w\-_\.,\[\] ] -> match not(^) any of \w \- _  and whitepsace etc.,
        # replace any that isnt in the  [] with _
        filename = re.sub("[^\w\-_.,\[\] ]", "_", self.title[0:110])
        ftype = self.file_type

        mypath = os.path.join(dl_root, self.name_usr)
        # isfile works without checking if dir exists first
        if os.path.isfile(os.path.join(mypath, filename + ftype)):
            if check_direct_url_for_dl(db_con, self.url_to_file):
                # TORELEASE remove
                # set filename since we need it to update in db
                self.filename_local = filename + ftype
                self.set_missing_values_db(db_con, url_type="file")
                logger.warning("!!! File already exists and was found in direct url_file but not in urls! "
                               "--> not renaming --> SKIPPING")
                # No need to return filename since file was already downloaded
                # mb refactor so we dont have to function exits, e.g. setting filename to None and at end of func
                # return with if-else...
                return None
            else:
                i = 0

                # You don't need to copy a Python string. They are immutable, so concatenating or slicing
                # returns a new string
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

    def download(self, db_con, curfnr, maxfnr, dl_root):
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

    # normally docstring only for public! modules, functions, methods..
    def _add_to_db(self, db_con):
        """
        Adds instance attributes and reddit_info values to the database using named SQL query
        parameters with a dictionary.
        DOESN'T COMMIT the transaction, since the context manager in self.download() needs to be
        able to do a rollback if the dl fails, will be commited in

        :param db_con: Connection obj to sqlite db
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

        db_con.execute("INSERT INTO Downloads(date, time, description, local_filename, "
                       "title, url_file, url, created_utc, r_post_url, reddit_id, reddit_title, "
                       "reddit_url, reddit_user, sgasm_user, subreddit_name) VALUES (:date, :time, "
                       ":description, :local_filename, :title, :url_file, :url, :created_utc, "
                       ":r_post_url, :reddit_id, :reddit_title, :reddit_url, :reddit_user, "
                       ":sgasm_user, :subreddit_name)", val_dict)

    def set_missing_values_db(self, db_con, url_type="page"):
        """
        Updates row of file entry in db with information from self like page_url, filename_local
        and reddit_info dict, only sets values if previous entry was NULL/None

        :param db_con: Connection to sqlite db
        :param self: instance of AudioDownload whose entry should be updated
        :param url_type: Use either "page" url or direct "file" url to find row
        :return: Filename string in db-column local_filename
        """
        # Row provides both index-based and case-insensitive name-based access to columns with almost no memory overhead
        db_con.row_factory = sqlite3.Row
        # we need to create new cursor after changing row_factory
        c = db_con.cursor()

        # even though Row class can be accessed both by index (like tuples) and case-insensitively by name
        # reset row_factory to default so we get normal tuples when fetching (should we generate a new cursor)
        # new_c will always fetch Row obj and cursor will fetch tuples
        db_con.row_factory = None

        url_type_file = True if url_type == "file" else False
        if url_type_file:
            c.execute("SELECT * FROM Downloads WHERE url_file = ?", (self.url_to_file,))
        else:
            c.execute("SELECT * FROM Downloads WHERE url = ?", (self.page_url,))
        # get row
        row_cont = c.fetchone()

        set_helper = (("reddit_title", "title"), ("reddit_url", "permalink"), ("reddit_user", "r_user"),
                      ("created_utc", "created_utc"), ("reddit_id", "id"), ("subreddit_name", "subreddit"),
                      ("r_post_url", "r_post_url"))

        upd_cols = []
        upd_vals = []
        # TORELEASE remove url_file stuff
        if row_cont["url"] is None:
            # add col = ? strings to list -> join them later to SQL query
            upd_cols.append("url = ?")
            upd_vals.append(self.page_url)
        if row_cont["local_filename"] is None:
            upd_cols.append("local_filename = ?")
            upd_vals.append(self.filename_local)
        if self.reddit_info:
            for col, key in set_helper:
                if row_cont[col] is None:
                    upd_cols.append("{} = ?".format(col))
                    upd_vals.append(self.reddit_info[key])

        if upd_cols:
            logger.debug("Updating file entry with new info for: {}".format(", ".join(upd_cols)))
            # append url since upd_vals need to include all the param substitutions for ?
            if url_type_file:
                upd_vals.append(self.url_to_file)
            else:
                upd_vals.append(self.page_url)
            # would work in SQLite version 3.15.0 (2016-10-14), but this is 3.8.11, users would have to update as well
            # so not a good idea
            # print("UPDATE Downloads SET ({}) = ({}) WHERE url_file = ?".format(",".join(upd_cols),
            #                                                               ",".join("?"*len(upd_cols))))

            # Connection objects can be used as context managers that automatically commit or rollback transactions.
            # In the event of an exception, the transaction is rolled back; otherwise, the transaction is committed
            # Unlike with open() etc. connection WILL NOT GET CLOSED
            with db_con:
                # join only inserts the string to join on in-between the elements of the iterable (none at the end)
                # format to -> e.g UPDATE Downloads SET url = ?,local_filename = ? WHERE url_file = ?
                if url_type_file:
                    c.execute("UPDATE Downloads SET {} WHERE url_file = ?".format(",".join(upd_cols)), upd_vals)
                else:
                    c.execute("UPDATE Downloads SET {} WHERE url = ?".format(",".join(upd_cols)), upd_vals)
        return row_cont["local_filename"]

    def write_selftext_file(self, dl_root):
        """
        Write selftext to a text file if not None, reddit_info must not be None!!

        :param dl_root: Path of root directory where all downloads are saved to (in username folders)
        :return: None
        """
        if self.reddit_info["selftext"]:
            # write_to_txtf uses append mode, but we'd have the selftext several times in the file since
            # there are reddit posts with multiple sgasm files
            # write_to_txtf(self.reddit_info["selftext"], self.filename_local + ".txt", self.name_usr)
            mypath = os.path.join(dl_root, self.name_usr)
            os.makedirs(mypath, exist_ok=True)
            # if selftext file doesnt already exists
            if not os.path.isfile(os.path.join(mypath, self.filename_local + ".txt")):
                with open(os.path.join(mypath, self.filename_local + ".txt"), "w", encoding="UTF-8") as w:
                    w.write("Title: {}\nPermalink: {}\nSelftext:\n\n{}".format(self.reddit_info["title"],
                                                                               self.reddit_info["permalink"],
                                                                               self.reddit_info["selftext"]))


# Docstrings = How to use code
#
# Comments = Why (rationale) & how code works
#
# Docstrings explain how to use code, and are for the users of your code. Uses of docstrings:
# Explain the purpose of the function even if it seems obvious to you, because it might not be obvious to
# someone else later on.
# Describe the parameters expected, the return values, and any exceptions raised.
# If the method is tightly coupled with a single caller, make some mention of the caller
# (though be careful as the caller might change later).
# Comments explain why, and are for the maintainers of your code. Examples include notes to yourself, like:
# !!! BUG: ...
# !!! FIX: This is a hack
# ??? Why is this here?
def prog_bar_dl(blocknum, blocksize, totalsize):
    """
    Displays a progress bar to sys.stdout

    blocknum * blocksize == bytes read so far
    Only display MB read when total size is -1
    Calc percentage of file download, number of blocks to display is bar length * percent/100
    String to display is Downloading: xx.x% [#*block_nr + "-"*(bar_len-block_nr)] xx.xx MB

    http://stackoverflow.com/questions/13881092/download-progressbar-for-python-3
    by J.F. Sebastian
    combined with:
    http://stackoverflow.com/questions/3160699/python-progress-bar
    by Brian Khuu
    and modified

    :param blocknum: Count of blocks transferred so far
    :param blocksize: Block size in bytes
    :param totalsize: Total size of the file in bytes
    :return: None
    """
    bar_len = 25  # Modify this to change the length of the progress bar
    # blocknum is current block, blocksize the size of each block in bytes
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize  # 1e2 == 100.0
        # nr of blocks
        block_nr = int(round(bar_len*readsofar/totalsize))
        # %5.1f: pad to 5 chars and display one decimal, type float, %% -> escaped %sign
        # %*d -> Parametrized, width -> len(str(totalsize)), value -> readsofar
        # s = "\rDownloading: %5.1f%% %*d / %d" % (percent, len(str(totalsize)), readsofar, totalsize)
        sn = "\rDownloading: {:4.1f}% [{}] {:4.2f} / {:.2f} MB".format(percent, "#"*block_nr + "-"*(bar_len-block_nr),
                                                                       readsofar / 1024**2, totalsize / 1024**2)
        sys.stdout.write(sn)
        if readsofar >= totalsize:  # near the end
            sys.stdout.write("\n")
    else:  # total size is unknown
        sys.stdout.write("\rDownloading: %.2f MB" % (readsofar / 1024**2,))
    # Python's standard out is buffered (meaning that it collects some of the data "written" to standard out before
    # it writes it to the terminal). flush() forces it to "flush" the buffer, meaning that it will write everything
    # in the buffer to the terminal, even if normally it would wait before doing so.
    sys.stdout.flush()


def check_direct_url_for_dl(db_con, direct_url):
    """
    Fetches url_file col from db and unpacks the 1-tuples, then checks if direct_url
    is in the list, if found return True

    :param db_con: Connection to sqlite db
    :param direct_url: String of direct url to file
    :return: True if direct_url is in col url_file of db else False
    """
    c = db_con.execute("SELECT url_file FROM Downloads")
    # converting to set would take just as long (for ~10k entries) as searching for it in list
    # returned as list of 1-tuples, use generator to unpack, so when we find direct_url b4
    # the last row we dont have to generate the remaining tuples and we only use it once
    # only minimally faster (~2ms for 10k rows)
    file_urls = (tup[0] for tup in c.fetchall())
    if direct_url in file_urls:
        return True
    else:
        return False
